# Duoduo Product Testing Backend

多角色 AI 测品工具后端 MVP-Lite。当前版本用于前端主流程联调，不是生产版。

## 已实现模块

- **Health** — 健康检查、存活探针、就绪探针
- **Auth** — mock 微信登录、JWT、profile
- **Product** — 产品创建、列表、详情、mock 上传 URL、mock AI 理解
- **Persona** — 系统角色、自定义角色、推荐、CRUD
- **Survey** — mock 种子模板生成，`AI_PROVIDER=ark` 时可走 AI adapter
- **Evaluation** — 创建、选角色、同步 run、取消、answers 查询
- **Report** — 按 evaluation 查询，metrics 真实聚合，文案规则生成
- **Conversation** — 创建、消息列表、SSE 流式对话，mock 默认，ark 可选

## 环境要求

- Python 3.11.x
- uv
- Docker / Docker Compose

## 本地一键启动

PowerShell：

```powershell
cd backend
Copy-Item .env.example .env
docker compose up -d postgres redis qdrant
uv sync
uv run alembic upgrade head
uv run python scripts/seed_personas.py
uv run uvicorn app.main:app --reload
```

Bash：

```bash
cd backend
cp .env.example .env
docker compose up -d postgres redis qdrant
uv sync
uv run alembic upgrade head
uv run python scripts/seed_personas.py
uv run uvicorn app.main:app --reload
```

服务默认地址：http://127.0.0.1:8000

本地 Compose 默认端口：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/duoduo
REDIS_URL=redis://localhost:6380/0
```

如果本机运行 API + Docker 依赖，使用上面的 localhost 地址。

如果使用 Docker profile 跑 API 容器，容器内部会使用：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/duoduo
REDIS_URL=redis://redis:6379/0
```

`alembic/env.py` 会从 `app.core.config` 读取 `DATABASE_URL`。`alembic.ini` 里的连接串只是通用 fallback，不作为本地端口配置来源。

## Docker Compose 服务

```bash
docker compose up -d postgres redis qdrant
```

| 服务 | 镜像 | 端口 | 用途 |
|---|---|---|---|
| postgres | postgres:15 | 5433:5432 | 主数据库 |
| redis | redis:7 | 6380:6379 | 后续 cache/broker 预留，避开常见 6379 冲突 |
| qdrant | qdrant/qdrant | 6333:6333, 6334:6334 | 后续向量检索预留 |
| api | 本地 Dockerfile | 8000:8000 | 可选，使用 profile `api` |

如需同时启动 API 容器：

```bash
docker compose --profile api up -d
```

## 开发检查

`dev_check.py` 会检查 Python/uv、数据库连接、Alembic current/head、seed persona 数量、HTTP health（API 未启动时跳过并提示）、OpenAPI 导出。

```bash
uv run python scripts/dev_check.py
```

成功时最后输出：

```text
DEV_CHECK_OK
```

如果 seed 数量不足，请先运行：

```bash
uv run python scripts/seed_personas.py
```

## 质量检查

```bash
uv sync
uv run ruff check .
uv run mypy app
uv run pytest
uv run alembic upgrade head
uv run alembic check
uv run python scripts/export_openapi.py
uv run python scripts/dev_check.py
```

## Swagger / OpenAPI

| 用途 | 地址 |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |

导出 OpenAPI JSON：

```bash
uv run python scripts/export_openapi.py
# 输出到 ../docs/openapi.v0.1.json
```

## E2E Mock Flow

自动化 E2E 测试（pytest，使用内存 SQLite）：

```bash
uv run pytest tests/e2e/test_full_mock_flow.py -v
```

人工联调演示脚本（需先启动 API，并建议先 seed）：

```bash
uv run python scripts/e2e_mock_flow.py
```

可通过 `API_BASE_URL` 覆盖默认地址：

```bash
$env:API_BASE_URL="http://127.0.0.1:8000"
uv run python scripts/e2e_mock_flow.py
```

脚本成功时输出 `E2E_MOCK_FLOW_OK`。

## 端口冲突处理

| 端口 | 当前默认 | 如果冲突 |
|---|---|---|
| PostgreSQL | 宿主机 5433 → 容器 5432 | 修改 `docker-compose.yml` 端口和 `.env` 的 `DATABASE_URL` |
| Redis | 宿主机 6380 → 容器 6379 | 修改 `docker-compose.yml` 端口和 `.env` 的 `REDIS_URL` |
| Qdrant | 6333/6334 | 停掉占用服务或调整 Compose 端口 |
| API | 8000 | 用 `uvicorn ... --port <port>` 并设置 `API_BASE_URL` 跑 E2E |
 
Redis 容器内部仍是 `redis:6379`，不要把 Docker profile 的 `REDIS_URL` 改成 `redis://redis:6380/0`。

## 前端交接资料

- 前端联调指南：`../docs/FRONTEND_HANDOFF.md`
- 接口实现状态表：`../docs/API_STATUS.md`
- 交付验收清单：`../docs/DELIVERY_CHECKLIST.md`
- OpenAPI 导出：`../docs/openapi.v0.1.json`

## AI Provider

默认 `AI_PROVIDER=mock`，普通本地开发和测试不需要真实 Ark key。

如需试用真实豆包 AI，请在本地 `.env` 或环境变量设置：

```env
AI_PROVIDER=ark
ARK_API_KEY=<your-ark-api-key>
ARK_EP_DOUBAO_15_LITE=<endpoint-id>
ARK_EP_DOUBAO_SEED_16=<endpoint-id>
ARK_EP_DOUBAO_15_PRO_CHARACTER=<endpoint-id>
ARK_EP_VISION_PRO=<endpoint-id>
```

不要把真实 key 写入代码、README、测试或 `.env.example`。

## 当前状态摘要

| 模块 | 状态 |
|---|---|
| Health | done |
| Auth | mock（微信登录）/ done（其余） |
| Product | mock（上传/AI 理解）/ done（CRUD） |
| Persona | done |
| Survey | ai_optional |
| Evaluation | ai_optional |
| Report | done/mock |
| Conversation | ai_optional |
| Credit | p1_not_implemented |

详见 `../docs/API_STATUS.md`。
