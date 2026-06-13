from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

PLUS_PRICE_FEN = 19900          # ¥199.00 in cents
PLUS_DESCRIPTION = "测品官 Plus 会员（年费）"
NOTIFY_URL_PATH = "/api/v1/upgrade/plus/notify"
PAY_API = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"


def _load_private_key():
    settings = get_settings()
    pem = settings.wechat_pay_private_key.replace("\\n", "\n")
    return serialization.load_pem_private_key(pem.encode(), password=None)


def _sign(message: str) -> str:
    """Sign message with merchant RSA private key, return base64."""
    private_key = _load_private_key()
    signature = private_key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def _build_auth_header(method: str, url_path: str, body: str) -> str:
    settings = get_settings()
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    sig = _sign(message)
    return (
        f'WECHAT-PAY-AUTH-V3 mchid="{settings.wechat_mch_id}",'
        f'serial_no="{settings.wechat_pay_serial_no}",'
        f'nonce_str="{nonce}",'
        f'timestamp="{timestamp}",'
        f'signature="{sig}"'
    )


def build_wx_pay_params(prepay_id: str) -> dict:
    """Build wx.requestPayment params to send to mini-program client."""
    settings = get_settings()
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    message = f"{settings.wechat_app_id}\n{timestamp}\n{nonce}\n{package}\n"
    pay_sign = _sign(message)
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


async def create_prepay_order(openid: str, out_trade_no: str, notify_base_url: str) -> str:
    """Call WeChat Pay JSAPI to create order. Returns prepay_id."""
    settings = get_settings()
    url_path = "/v3/pay/transactions/jsapi"
    body = json.dumps({
        "appid": settings.wechat_app_id,
        "mchid": settings.wechat_mch_id,
        "description": PLUS_DESCRIPTION,
        "out_trade_no": out_trade_no,
        "notify_url": f"{notify_base_url}{NOTIFY_URL_PATH}",
        "amount": {"total": PLUS_PRICE_FEN, "currency": "CNY"},
        "payer": {"openid": openid},
    }, ensure_ascii=False, separators=(",", ":"))

    auth = _build_auth_header("POST", url_path, body)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            PAY_API,
            content=body,
            headers={
                "Authorization": auth,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    if resp.status_code != 200:
        logger.error("WeChat Pay create order failed: %s %s", resp.status_code, resp.text)
        raise ValueError(f"支付下单失败: {resp.status_code}")
    return resp.json()["prepay_id"]


def decrypt_notify(resource: dict) -> dict:
    """Decrypt AES-GCM encrypted notify payload using v3 API key."""
    settings = get_settings()
    api_key = settings.wechat_pay_key.encode()
    nonce = resource["nonce"].encode()
    ciphertext = base64.b64decode(resource["ciphertext"])
    associated_data = resource.get("associated_data", "").encode()
    # AES-256-GCM: key = SHA256(api_key) NOT needed — key is the raw 32-byte api_key
    aesgcm = AESGCM(api_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
    return json.loads(plaintext)


_WX_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
_WX_UPLOAD_SHIPPING_URL = "https://api.weixin.qq.com/wxa/sec/order/upload_shipping_info"


async def _get_access_token(app_id: str, app_secret: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_WX_TOKEN_URL, params={
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        })
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ValueError(f"获取 access_token 失败: {data}")
    return token


async def upload_shipping_info(out_trade_no: str, openid: str) -> None:
    """上报虚拟商品订单到微信订单中心（物流类型4=虚拟发货）。

    支付成功后调用，失败仅记录日志，不影响主流程。
    """
    settings = get_settings()
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        logger.info("upload_shipping_info skipped: wechat not configured")
        return

    try:
        access_token = await _get_access_token(settings.wechat_app_id, settings.wechat_app_secret)
        body = {
            "order_key": {
                "order_number_type": 2,
                "out_trade_no": out_trade_no,
            },
            "logistics_type": 4,
            "delivery_mode": 1,
            "is_all_delivered": True,
            "shipping_list": [{
                "tracking_no": "",
                "express_company": "",
                "item_desc": PLUS_DESCRIPTION,
            }],
            "payer": {"openid": openid},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _WX_UPLOAD_SHIPPING_URL,
                params={"access_token": access_token},
                json=body,
            )
        data = resp.json()
        if data.get("errcode", 0) != 0:
            logger.warning("upload_shipping_info failed: %s", data)
        else:
            logger.info("upload_shipping_info ok out_trade_no=%s", out_trade_no)
    except Exception as e:
        logger.error("upload_shipping_info error: %s", e)
