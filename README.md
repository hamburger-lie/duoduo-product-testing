# Duoduo Product Testing

多角色 AI 测品工具后端 MVP-Lite。项目用于快速跑通：

```text
登录 → 创建产品 → 生成问卷 → 选择角色 → 多角色答题 → 生成报告 → 单角色流式对话
```

当前版本面向前端联调和产品闭环验证，默认使用 mock/规则实现外部依赖；真实微信、真实 TOS、Celery、mem0、内容审核、支付、PDF/分享等能力后续迭代接入。

## 当前状态

| 模块 | 状态 | 说明 |
|---|---|---|
| Auth | mock / done | mock 微信登录，JWT 鉴权可用 |
| Product | mock / done | mock 上传 URL，mock ai_summary，真实 DB CRUD |
| Persona | done | 系统角色 seed、私有角色、推荐、CRUD |
| Survey | ai_optional | 默认种子模板，Ark 可选 |
| Evaluation | ai_optional | 默认同步 mock answer，Ark 可选 |
| Report | done / mock | metrics 基于 DB 聚合，文案规则生成 |
| Conversation | ai_optional | SSE 流式对话，默认 mock，Ark 可选 |
| Credit / PDF / Share | p1_not_implemented | 字段或入口预留，暂不建议前端展示 |

## 快速启动

```powershell
cd backend
Copy-Item .env.example .env
docker compose up -d postgres redis qdrant
uv sync
uv run alembic upgrade head
uv run python scripts/seed_personas.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 18000 --reload
```

打开 Swagger：

```text
http://127.0.0.1:18000/docs
```

如果端口冲突，可以换端口启动，并设置 `API_BASE_URL` 跑 E2E：

```powershell
$env:API_BASE_URL="http://127.0.0.1:18001"
uv run python scripts/e2e_mock_flow.py
```

## 验收命令

```powershell
cd backend
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

主流程 HTTP E2E 需要先在一个终端启动 API：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再在另一个终端执行：

```powershell
uv run python scripts/e2e_mock_flow.py
```

成功时输出：

```text
E2E_MOCK_FLOW_OK
```

## 文档入口

| 文档 | 用途 |
|---|---|
| [backend/README.md](backend/README.md) | 后端启动、测试、Docker 与端口说明 |
| [docs/FRONTEND_HANDOFF.md](docs/FRONTEND_HANDOFF.md) | 前端联调指南 |
| [docs/API_STATUS.md](docs/API_STATUS.md) | 接口实现状态冻结表 |
| [docs/DELIVERY_CHECKLIST.md](docs/DELIVERY_CHECKLIST.md) | MVP-Lite 交付验收清单 |
| [docs/openapi.v0.1.json](docs/openapi.v0.1.json) | 冻结版 OpenAPI |
| [API_CONTRACT.md](API_CONTRACT.md) | 前后端接口唯一契约 |

## 兼容性约定

当前部分接口为 mock 或 ai_optional。后续替换为真实微信、真实 TOS、真实 AI、异步任务或内容审核时，应保持 `API_CONTRACT.md` 已定义的响应字段、错误结构、ID 字符串格式和状态枚举兼容。

前端不要依赖 mock 文案的具体内容，应依赖字段结构、枚举值、状态流转和 SSE 事件格式。

## 技术栈

- Python 3.11
- FastAPI
- SQLAlchemy 2.0 async
- Alembic
- PostgreSQL
- Redis
- Qdrant
- Pydantic v2
- pytest / ruff / mypy
- OpenAI-compatible Ark/Doubao client boundary
