// wx.request 封装 — Phase A 不会真正被调用（USE_MOCK 拦截）
// Phase B 切换：设置 BASE_URL，并把 services/api.ts 的 USE_MOCK 改成 false

import { API_VERSION_PREFIX } from './endpoints';
import type { ApiError } from '../types/api';

/**
 * 本地调试：http://127.0.0.1:18000
 * DevTools → 详情 → 本地设置 → 勾选"不校验合法域名"
 * 上线时改成正式域名并在小程序后台白名单添加，例如 'https://api.cepinguan.com'
 */
// ⚠️ 真机调试时需要填你电脑的局域网 IP（cmd → ipconfig → IPv4 地址）
// 建议在路由器或 Windows 网络设置里给这台电脑分配固定 IP，这样永远不用改
const DEV_LAN_IP = '192.168.3.114';

const _platform = wx.getDeviceInfo().platform;
const IS_LOCAL = _platform === 'devtools' || _platform === 'windows' || _platform === 'mac';
export const BASE_URL = IS_LOCAL
  ? 'http://127.0.0.1:18000'
  : `http://${DEV_LAN_IP}:18000`;

interface RequestOptions {
  url: string;                 // 不含 BASE_URL 与版本前缀
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  data?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  header?: Record<string, string>;
  /** 不带版本前缀（例 /health/live） */
  raw?: boolean;
  /** 超时毫秒，默认 120000 (2 分钟) */
  timeout?: number;
  /** 内部：已重试过，防死循环 */
  _retried?: boolean;
}

function uuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function getToken(): string | null {
  try {
    return wx.getStorageSync('auth_token') || null;
  } catch {
    return null;
  }
}

let _refreshing: Promise<string> | null = null;

/** wx.login → POST /auth/wechat/login → 存储 token */
function silentLogin(): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    wx.login({
      success(loginRes) {
        wx.request({
          url: BASE_URL + API_VERSION_PREFIX + '/auth/wechat/login',
          method: 'POST',
          header: { 'Content-Type': 'application/json' },
          data: { code: loginRes.code },
          success(res: any) {
            if (res.statusCode === 200 && res.data?.token) {
              wx.setStorageSync('auth_token', res.data.token);
              resolve();
            } else {
              reject(new Error('silent login failed: ' + res.statusCode));
            }
          },
          fail: (e: any) => reject(new Error(e.errMsg)),
        });
      },
      fail: (e: any) => reject(new Error(e.errMsg)),
    });
  });
}

function refreshToken(): Promise<string> {
  if (_refreshing) return _refreshing;
  _refreshing = new Promise<string>((resolve, reject) => {
    wx.request({
      url: BASE_URL + API_VERSION_PREFIX + '/auth/refresh',
      method: 'POST',
      header: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + (getToken() || '') },
      success(res: any) {
        if (res.statusCode === 200 && res.data?.token) {
          wx.setStorageSync('auth_token', res.data.token);
          resolve(res.data.token as string);
        } else {
          reject(new Error('refresh failed'));
        }
      },
      fail: (e: any) => reject(new Error(e.errMsg)),
    });
  }).finally(() => { _refreshing = null; }) as Promise<string>;
  return _refreshing;
}

function buildQuery(q?: RequestOptions['query']): string {
  if (!q) return '';
  const parts: string[] = [];
  Object.keys(q).forEach(k => {
    const v = q[k];
    if (v === undefined || v === null) return;
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(String(v)));
  });
  return parts.length ? '?' + parts.join('&') : '';
}

export function request<T>(opts: RequestOptions): Promise<T> {
  const path = (opts.raw ? '' : API_VERSION_PREFIX) + opts.url + buildQuery(opts.query);
  const url = BASE_URL + path;

  const header: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-Id': uuid(),
    'X-Client-Version': 'wxmini/0.1.0',
    ...(opts.header || {}),
  };
  const token = getToken();
  if (token) header['Authorization'] = 'Bearer ' + token;

  return new Promise<T>((resolve, reject) => {
    wx.request({
      url,
      method: (opts.method || 'GET') as any,
      data: opts.data as any,
      header,
      timeout: opts.timeout ?? 120000,
      async success(res) {
        const code = res.statusCode;
        if (code >= 200 && code < 300) {
          resolve(res.data as T);
          return;
        }
        // 401 先尝试刷新 token，失败则重新 wx.login 静默登录，最多重试一次
        if (code === 401 && !opts._retried) {
          try {
            await refreshToken();
          } catch {
            // refresh 失败：清掉旧 token，重新 wx.login 静默登录
            wx.removeStorageSync('auth_token');
            try {
              await silentLogin();
            } catch { /* 登录失败则继续走下面的 reject */ }
          }
          if (getToken()) {
            try {
              resolve(await request<T>({ ...opts, _retried: true }));
              return;
            } catch { /* fall through to reject */ }
          }
          reject({ code: 'HTTP_401', message: '登录已过期，请重新登录', statusCode: 401 } as ApiError);
          return;
        }
        const err: ApiError = {
          code: 'HTTP_' + code,
          message: '请求失败',
          ...((res.data as ApiError) || {}),
          statusCode: code,
        };
        reject(err);
      },
      fail(e) {
        reject({ code: 'NETWORK_ERROR', message: e.errMsg } as ApiError);
      },
    });
  });
}

/**
 * 把后端返回的绝对 URL 中的 127.0.0.1/localhost 替换为当前 BASE_URL，
 * 这样真机调试也能正确加载静态资源。
 */
export function resolveMediaUrl(url: string | null | undefined): string {
  if (!url) return '';
  if (url.includes('mock-cdn.local') || url.includes('mock-tos.local')) return '';
  if (url.startsWith('http://127.0.0.1') || url.startsWith('http://localhost')) {
    return BASE_URL + url.replace(/^https?:\/\/[^/]+/, '');
  }
  if (url.startsWith('/')) return BASE_URL + url;
  return url;
}
