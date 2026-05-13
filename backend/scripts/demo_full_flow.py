"""全流程演示脚本 — demo_full_flow.py

无需前端，一条命令跑通完整产品测评链路：
    登录 → 创建产品 → 生成问卷 → 创建测评 → 选角色 →
    运行答题 → 查看 summary_comment → 获取报告 → 对话追问

使用方式（推荐 mock 模式，秒回）：
    # PowerShell
    $env:AI_PROVIDER="mock"; uv run python scripts/demo_full_flow.py

    # Bash / Git Bash
    AI_PROVIDER=mock uv run python scripts/demo_full_flow.py

    # 真实 AI 模式（需配置 .env 里的 API Key，较慢）
    uv run python scripts/demo_full_flow.py

可选环境变量：
    BASE_URL       服务地址，默认 http://localhost:8000
    PERSONA_COUNT  参与角色数，默认 3（建议 1-5，越多越慢）
    AI_PROVIDER    mock / deepseek，控制服务端行为（需在启动 uvicorn 前设置）
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
PERSONA_COUNT = int(os.getenv("PERSONA_COUNT", "3"))
POLL_INTERVAL = 2          # 秒，轮询间隔
POLL_TIMEOUT = 180         # 秒，最大等待时间
STREAM_TIMEOUT = 60        # 秒，SSE 流超时
REQUEST_TIMEOUT = 120      # 秒，单个 HTTP 请求超时（AI 生成类接口可能较慢）

# ──────────────────────────────────────────────
# 终端颜色
# ──────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
DIM    = "\033[2m"
MAGENTA = "\033[95m"


def _h(title: str) -> None:
    width = 60
    print(f"\n{CYAN}{BOLD}{'─' * width}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * width}{RESET}")


def _ok(label: str, value: Any = "") -> None:
    v = f"  {DIM}{value}{RESET}" if value != "" else ""
    print(f"  {GREEN}✓{RESET} {label}{v}")


def _info(label: str, value: Any = "") -> None:
    v = f"  {DIM}{value}{RESET}" if value != "" else ""
    print(f"  {YELLOW}→{RESET} {label}{v}")


def _err(msg: str) -> None:
    print(f"\n{RED}{BOLD}✗ 错误：{msg}{RESET}\n", file=sys.stderr)


def _json_block(data: Any, indent: int = 4) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


# ──────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────

class DemoClient:
    def __init__(self, base_url: str) -> None:
        self._base = base_url
        self._token: str | None = None
        self._client = httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT)

    def set_token(self, token: str) -> None:
        self._token = token

    def _auth(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    async def get(self, path: str, **kw: Any) -> dict[str, Any]:
        r = await self._client.get(path, headers=self._auth(), **kw)
        self._check(r)
        return r.json()

    async def post(self, path: str, body: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        r = await self._client.post(path, json=body, headers=self._auth(), **kw)
        self._check(r)
        return r.json()

    async def put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.put(path, json=body, headers=self._auth())
        self._check(r)
        return r.json()

    async def stream_post(self, path: str, body: dict[str, Any]) -> str:
        """POST with SSE streaming — collect all delta chunks and return full text."""
        full = []
        async with self._client.stream(
            "POST", path,
            json=body,
            headers={**self._auth(), "Accept": "text/event-stream"},
            timeout=STREAM_TIMEOUT,
        ) as resp:
            self._check(resp)
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") == "delta":
                    chunk = ev.get("content", "")
                    full.append(chunk)
                    print(chunk, end="", flush=True)
                elif ev.get("event") == "done":
                    break
                elif ev.get("event") == "error":
                    raise RuntimeError(f"SSE error: {ev}")
        print()  # 换行
        return "".join(full)

    def _check(self, r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            _err(f"HTTP {r.status_code}  {r.request.method} {r.request.url}\n{_json_block(detail)}")
            if r.status_code == 500 and "ModuleNotFoundError" in str(detail):
                _err("提示：服务端缺少依赖，请用 uv run python -m uvicorn app.main:app --reload 启动")
            sys.exit(1)

    async def aclose(self) -> None:
        await self._client.aclose()


# ──────────────────────────────────────────────
# 演示步骤
# ──────────────────────────────────────────────

async def step_health(c: DemoClient) -> None:
    _h("0. 健康检查")
    data = await c.get("/health")
    _ok("服务在线", f"{data.get('name', '')} {data.get('version', '')}")

    ready = await c.get("/health/ready")
    statuses = {k: v for k, v in ready.items() if k != "status"}
    _ok(f"就绪状态: {ready.get('status', '?')}", statuses)


async def step_login(c: DemoClient) -> dict[str, Any]:
    _h("1. 微信登录（mock 模式）")
    data = await c.post("/api/v1/auth/wechat/login", {"code": "DEMO_CODE_001"})
    token = data["token"]
    user  = data["user"]
    c.set_token(token)
    _ok("登录成功", f"user_id={user['id']}  新用户={user['is_new_user']}")
    _ok("JWT token", f"{token[:20]}…")
    return user


async def step_create_product(c: DemoClient) -> dict[str, Any]:
    _h("2. 创建产品")
    payload = {
        "name": "珀莱雅双抗精华 2.0",
        "description": (
            "珀莱雅双抗精华2.0，主打抗氧化+抗糖化双重功效。"
            "核心成分：虾青素0.1%、麦角硫因、烟酰胺3%。"
            "适合25岁以上轻熟龄肌，特别是城市通勤、熬夜人群。"
            "定价239元/30ml，对标同价位修丽可CE精华。"
        ),
        "brand": "珀莱雅",
        "price": "239.00",
        "image_object_keys": ["demo/polaar-serum-2.0.jpg"],
    }
    data = await c.post("/api/v1/products", payload)
    _ok("产品创建成功", f"id={data['id']}  name={data['name']}")
    _ok("AI 理解状态", data.get("status", "?"))
    summary = data.get("ai_summary", {})
    if summary.get("main_selling_points"):
        _ok("卖点", "、".join(summary["main_selling_points"][:3]))
    return data


async def step_create_evaluation(c: DemoClient, product_id: str) -> dict[str, Any]:
    _h("3. 创建测评")
    data = await c.post("/api/v1/evaluations", {"product_id": product_id})
    _ok("测评创建", f"id={data['id']}  status={data['status']}")
    return data


async def step_generate_survey(
    c: DemoClient,
    product_id: str,
    evaluation_id: str,
) -> dict[str, Any]:
    _h("4. AI 生成问卷")
    _info("生成中，请稍等…")
    data = await c.post("/api/v1/surveys/generate", {
        "product_id": product_id,
        "evaluation_id": evaluation_id,
        "extra_focus": "价格敏感度和成分认知",
    })
    questions = data.get("questions", [])
    _ok("问卷生成", f"id={data['id']}  题数={len(questions)}")
    for i, q in enumerate(questions[:3], 1):
        _info(f"  Q{i} [{q['type']}]", q["question"][:50] + ("…" if len(q["question"]) > 50 else ""))
    if len(questions) > 3:
        _info(f"  … 共 {len(questions)} 题")
    return data


async def step_pick_personas(c: DemoClient, count: int) -> list[dict[str, Any]]:
    _h("5. 选取参与角色")
    data = await c.get("/api/v1/personas", params={"limit": 20, "owner_scope": "system"})
    items: list[dict[str, Any]] = data.get("items", [])
    if not items:
        _err("角色库为空，请先运行: uv run python scripts/seed_personas.py")
        sys.exit(1)

    picked = items[:count]
    for p in picked:
        crit = "⚡挑剔" if p.get("is_critical") else ""
        _ok(f"{p['name']} {crit}", f"id={p['id']}  tag={p.get('persona_tag','')}  age={p.get('age','?')}")
    return picked


async def step_set_personas(
    c: DemoClient,
    evaluation_id: str,
    persona_ids: list[str],
) -> None:
    _h("6. 绑定角色到测评")
    await c.put(f"/api/v1/evaluations/{evaluation_id}/personas", {
        "persona_ids": persona_ids,
    })
    _ok("角色已绑定", f"{len(persona_ids)} 个角色")


async def step_run_evaluation(c: DemoClient, evaluation_id: str) -> None:
    _h("7. 启动测评（角色答题）")
    _info("发送 run 指令…")
    data = await c.post(f"/api/v1/evaluations/{evaluation_id}/run")
    _ok("已启动", f"status={data['status']}  task_id={data.get('task_id','')}")


async def step_poll_completion(c: DemoClient, evaluation_id: str) -> None:
    _h("8. 等待答题完成")
    deadline = time.time() + POLL_TIMEOUT
    last_progress = -1
    while time.time() < deadline:
        data = await c.get(f"/api/v1/evaluations/{evaluation_id}")
        status = data.get("status", "?")
        progress = data.get("progress", 0)
        if progress != last_progress:
            bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
            print(f"\r  {YELLOW}[{bar}] {progress}%  {status}{RESET}   ", end="", flush=True)
            last_progress = progress
        if status in ("done", "failed", "canceled"):
            print()
            if status == "done":
                _ok("答题完成！")
            else:
                _err(f"测评结束但状态为 {status}")
                sys.exit(1)
            return
        await asyncio.sleep(POLL_INTERVAL)
    print()
    _err(f"超时（{POLL_TIMEOUT}s）仍未完成，请检查 Celery worker 是否启动")
    sys.exit(1)


async def step_get_answers(
    c: DemoClient,
    evaluation_id: str,
) -> list[dict[str, Any]]:
    _h("9. 查看角色答案摘要（含 summary_comment）")
    items: list[dict[str, Any]] = await c.get(f"/api/v1/evaluations/{evaluation_id}/answers")

    for item in items:
        name    = item.get("persona_name", "?")
        intent  = item.get("overall_intent", "?")
        senti   = item.get("sentiment", "?")
        comment = item.get("summary_comment") or "(mock 模式无 summary_comment)"

        senti_color = GREEN if senti == "positive" else (RED if senti == "negative" else YELLOW)
        stars = "★" * (intent or 0) + "☆" * (5 - (intent or 0))

        print(f"\n  {BOLD}{MAGENTA}{name}{RESET}  {stars}  {senti_color}{senti}{RESET}")
        print(f"  {DIM}─────────────────────────────────────────────{RESET}")
        # 每 44 字换行，缩进对齐
        words = comment
        line_len = 44
        for i in range(0, len(words), line_len):
            print(f"  {words[i:i+line_len]}")

    return items


async def step_get_full_answer(
    c: DemoClient,
    evaluation_id: str,
    persona_id: str,
    persona_name: str,
) -> None:
    _h(f"10. 单角色完整答案（{persona_name}）")
    data = await c.get(f"/api/v1/evaluations/{evaluation_id}/answers/{persona_id}")

    answers = data.get("answers", [])
    _ok(f"共 {len(answers)} 题答案，展示前 3 题：")
    for ans in answers[:3]:
        _info(f"  [{ans.get('type','')}] {str(ans.get('answer',''))}", ans.get("reason", "")[:60])

    comment = data.get("summary_comment") or "(mock 模式无 summary_comment)"
    print(f"\n  {BOLD}summary_comment:{RESET}")
    line_len = 50
    for i in range(0, len(comment), line_len):
        print(f"    {comment[i:i+line_len]}")


async def step_get_report(c: DemoClient, evaluation_id: str) -> dict[str, Any]:
    _h("11. 获取测评报告")
    _info("生成报告（首次访问自动触发）…")
    data = await c.get(f"/api/v1/reports/by-evaluation/{evaluation_id}")

    _ok("报告生成", f"id={data['id']}")
    print(f"\n  {BOLD}摘要：{RESET}")
    summary = data.get("summary", "")
    for i in range(0, len(summary), 55):
        print(f"    {summary[i:i+55]}")

    metrics = data.get("metrics", {})
    oi = metrics.get("overall_intent", {})
    _ok("整体购买意向均值", f"{oi.get('average', '?'):.1f} / 5.0  NPS={oi.get('nps', '?')}")

    for pro in data.get("top_pros", [])[:2]:
        _ok(f"✚ 优势：{pro['title']}", f"({pro['support_count']} 人提到)")
    for con in data.get("top_cons", [])[:2]:
        _info(f"✖ 风险：{con['title']}", f"({con['support_count']} 人提到)")

    print(f"\n  {DIM}ai_disclaimer: {data.get('ai_disclaimer','')[:80]}…{RESET}")
    return data


async def step_conversation(
    c: DemoClient,
    evaluation_id: str,
    persona_id: str,
    persona_name: str,
) -> None:
    _h(f"12. 与角色对话（{persona_name}）")

    # 创建 / 获取对话
    conv = await c.post("/api/v1/conversations", {
        "evaluation_id": evaluation_id,
        "persona_id": persona_id,
    })
    conv_id = conv["id"]
    _ok("对话创建", f"id={conv_id}  title={conv.get('title','')}")

    # 发送第一条追问
    question = "你给了这个分数，主要是哪个点让你犹豫？"
    _info(f"用户提问", question)
    print(f"\n  {BOLD}{persona_name}：{RESET}", end="", flush=True)

    reply = await c.stream_post(
        f"/api/v1/conversations/{conv_id}/messages",
        {"content": question},
    )

    if not reply:
        _info("（SSE 流为空，可能是 mock 模式返回空响应）")
    else:
        _ok("对话完成", f"回复长度={len(reply)} 字")

    # 第二条追问
    question2 = "如果打折到 179 元，你会买吗？"
    _info(f"用户追问", question2)
    print(f"\n  {BOLD}{persona_name}：{RESET}", end="", flush=True)
    await c.stream_post(
        f"/api/v1/conversations/{conv_id}/messages",
        {"content": question2},
    )


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ai_hint = os.getenv("AI_PROVIDER", "(由服务端 .env 决定)")
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  多多测评 — 全流程自动演示{RESET}")
    print(f"{BOLD}{CYAN}  BASE_URL      = {BASE_URL}{RESET}")
    print(f"{BOLD}{CYAN}  PERSONA_COUNT = {PERSONA_COUNT}{RESET}")
    print(f"{BOLD}{CYAN}  AI_PROVIDER   = {ai_hint}{RESET}")
    if ai_hint not in ("mock",):
        print(f"{YELLOW}  提示：如遇超时，用 mock 模式启动 uvicorn 可秒回{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    c = DemoClient(BASE_URL)
    t0 = time.time()

    try:
        await step_health(c)
        await step_login(c)
        product     = await step_create_product(c)
        evaluation  = await step_create_evaluation(c, product["id"])
        await step_generate_survey(c, product["id"], evaluation["id"])
        personas    = await step_pick_personas(c, PERSONA_COUNT)
        persona_ids = [str(p["id"]) for p in personas]
        await step_set_personas(c, evaluation["id"], persona_ids)
        await step_run_evaluation(c, evaluation["id"])
        await step_poll_completion(c, evaluation["id"])
        answers     = await step_get_answers(c, evaluation["id"])
        if answers:
            first = answers[0]
            await step_get_full_answer(c, evaluation["id"], first["persona_id"], first["persona_name"])
            await step_get_report(c, evaluation["id"])
            await step_conversation(c, evaluation["id"], first["persona_id"], first["persona_name"])

    except httpx.ReadTimeout:
        _err(
            f"请求超时（{REQUEST_TIMEOUT}s）—— AI 接口响应太慢。\n"
            "建议用 mock 模式演示（秒回）：\n"
            '  PowerShell:  $env:AI_PROVIDER="mock"; uv run python -m uvicorn app.main:app --reload\n'
            "  Bash:        AI_PROVIDER=mock uv run python -m uvicorn app.main:app --reload\n"
            "然后重新运行演示脚本。"
        )
        sys.exit(1)
    except httpx.ConnectError:
        _err(
            f"无法连接 {BASE_URL} —— 请确认 uvicorn 已启动：\n"
            "  uv run python -m uvicorn app.main:app --reload"
        )
        sys.exit(1)
    finally:
        await c.aclose()

    elapsed = time.time() - t0
    print(f"\n{GREEN}{BOLD}{'═' * 60}{RESET}")
    print(f"{GREEN}{BOLD}  全流程演示完成  耗时 {elapsed:.1f}s{RESET}")
    print(f"{GREEN}{BOLD}{'═' * 60}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
