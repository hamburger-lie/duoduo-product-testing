# MVP-Lite Backend v0.1 交付验收清单

本文档是后端 MVP-Lite 交付总览，供前端联调、验收和后续排期使用。

## 1. 当前版本

**MVP-Lite Backend v0.1**

目标：跑通“登录 → 创建产品 → 生成问卷 → 选择角色 → 多角色答题 → 报告 → 单角色流式对话”的后端闭环。

## 2. 已完成能力

| 能力 | 状态 | 说明 |
|---|---|---|
| Auth mock + JWT | 已完成 | mock 微信 code 登录，签发 JWT |
| Product mock upload + AI optional ai_summary | 已完成 | 上传 URL 为 mock；产品理解默认 mock，可通过 DeepSeek/vision client 生成 ai_summary |
| Persona 系统/私有角色 | 已完成 | 支持 seed 系统角色、私有角色 CRUD、推荐 |
| Survey mock / AI optional | 已完成 | 默认种子模板，可通过 `AI_PROVIDER=deepseek` 走 AI adapter |
| Evaluation mock / AI optional run | 已完成 | 默认 `sync` 本地模式；`EVALUATION_RUN_MODE=celery` 时生产异步入队，answer 内容可 mock/deepseek |
| Answer 查询 | 已完成 | 支持汇总和单 persona 答案查询 |
| Report 聚合 | 已完成 | metrics 基于 DB answers 聚合，文案规则生成 |
| Conversation mock / AI optional SSE | 已完成 | 默认 mock SSE，deepseek 可走真实流式对话 |
| Local keyword moderation | 部分完成 | 本地关键词拦截可用；生产审核未完成 |
| DB-backed memory adapter | 部分完成 | 可记录/检索 DB 记忆；mem0/Qdrant 向量记忆未完成 |
| Celery evaluation queue | 部分完成 | 主 run 已支持 Celery 入队和 worker 消费；默认本地 `sync`，生产需启动 worker profile |
| OpenAPI 导出 | 已完成 | `docs/openapi.v0.1.json` |
| Docker 本地依赖 | 已完成 | postgres / redis / qdrant |
| dev_check | 已完成 | 本地环境 readiness 检查 |
| E2E mock flow | 已完成 | pytest E2E 与 HTTP 脚本 |

## 3. 未完成 / 后置能力

| 能力 | 后置原因 |
|---|---|
| 真实微信登录 | MVP-Lite 使用 mock code |
| 真实 TOS / OSS | MVP-Lite 不做真实对象存储 |
| Celery 生产运维完善 | Evaluation run 已可异步；后续还需监控、重试策略、死信/告警和生产部署治理 |
| mem0 / Qdrant 真实记忆 | 当前仅 DB-backed memory adapter；未接 mem0/Qdrant 向量检索 |
| 生产级内容审核 | 当前仅 local keyword moderation；未接第三方审核、图像审核和策略治理 |
| 积分扣费闭环 | 当前仅保留 credit 模型/字段 |
| 充值 / 支付 | P1 后置 |
| PDF 导出 | P1 后置，字段保留 |
| 分享链接 | P1 后置，字段保留 |
| 管理后台 | MVP 不做 |
| 生产部署 | 需后续 Dockerfile/compose 生产化、HTTPS、密钥治理 |

## 4. 前端联调前必须确认

在 `backend/` 目录执行：

```bash
cp .env.example .env
docker compose up -d postgres redis qdrant
uv sync
uv run alembic upgrade head
uv run python scripts/seed_personas.py
uv run uvicorn app.main:app --reload
```

如果需要验证生产异步链路，设置 `EVALUATION_RUN_MODE=celery` 并启动 worker：

```bash
uv run celery -A app.tasks.celery_app.celery_app worker -Q evaluations -l info -c 4
```

或使用 Docker profiles：

```bash
docker compose --profile api --profile worker up -d --build
```

检查：

```bash
uv run python scripts/dev_check.py
uv run python scripts/e2e_mock_flow.py
```

打开：

| 用途 | 地址 |
|---|---|
| Swagger | http://127.0.0.1:8000/docs |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |
| 冻结版 OpenAPI | `docs/openapi.v0.1.json` |

## 5. 前端联调顺序

1. Auth：登录并保存 token。
2. Product：获取 upload-url，创建产品。
3. Persona：推荐角色，必要时先 seed。
4. Survey：生成问卷，run 前可编辑。
5. Evaluation：创建测评、选择角色、启动 run、轮询状态；`celery` 模式下前端只认 evaluation.status/progress，不依赖 Celery task 状态。
6. Report：按 evaluation 查询报告。
7. Conversation：创建对话，发送 SSE 流式消息，读取历史消息。

## 6. 常见问题

| 问题 | 原因 | 处理 |
|---|---|---|
| 401 | token 缺失、格式错误或过期 | 除 login/health 外都带 `Authorization: Bearer <token>` |
| PRODUCT_NOT_FOUND | 产品不存在或不属于当前用户 | 使用当前 token 创建并保存的 `product_id` |
| PERSONA_NOT_FOUND | 角色不可见或未 seed | 执行 `uv run python scripts/seed_personas.py` |
| EVALUATION_NOT_READY | 未生成问卷、未选角色或未 run | 按主流程补齐 survey/personas/run |
| SURVEY_LOCKED | 测评已开始或完成后编辑问卷 | 只能在 run 前编辑 |
| CONVERSATION_LIMIT_REACHED | 对话消息数达到 40 条 | 新建/复用其他 conversation，或后续做归档策略 |
| Redis 端口冲突 | 本机已有 6379 服务 | 项目默认宿主机端口为 6380，确认 `.env` 使用 `redis://localhost:6380/0` |
| /personas/recommend 返回空 | 系统角色未导入 | 运行 seed 脚本后重试 |

## 7. 最终验收命令

```bash
docker compose up -d postgres redis qdrant
uv sync
uv run alembic upgrade head
uv run alembic check
uv run python scripts/seed_personas.py
uv run ruff check .
uv run mypy app
uv run pytest
uv run python scripts/export_openapi.py
uv run python scripts/dev_check.py
```

先在一个终端启动 API：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再在另一个终端执行 HTTP 主流程验收：

```bash
uv run python scripts/e2e_mock_flow.py
```

## 8. 交付文件

| 文件 | 用途 |
|---|---|
| `backend/README.md` | 后端本地启动与测试说明 |
| `docs/FRONTEND_HANDOFF.md` | 前端联调指南 |
| `docs/API_STATUS.md` | 接口状态冻结表 |
| `docs/openapi.v0.1.json` | 冻结版 OpenAPI |
| `docs/DELIVERY_CHECKLIST.md` | 本交付验收清单 |
| `backend/scripts/e2e_mock_flow.py` | HTTP 主流程演示脚本 |
| `backend/scripts/dev_check.py` | 本地环境检查脚本 |
