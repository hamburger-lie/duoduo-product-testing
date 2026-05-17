# Duoduo Product Testing Backend

多角色 AI 测品工具后端。当前版本：**v0.2.0**

## 更新日志

### v0.2.0（2026-05-15）

- **问卷提示词 v2**：全面升级为"闺蜜聊天"风格，7 种心理学技法（注意力验证、投射法、PSM 价格三问、行为场景、损失框架、三秒直觉、认知失调探针），题型/维度严格约束
- **`summary_comment` 字段**：角色答卷新增第一人称 2-3 句社群短评，随答案接口一并返回
- **AI 路由优化**：有图片时 GLM 专门做图片→文字识别，DeepSeek 负责产品理解推理；无图片直接走 DeepSeek
- **Persona Chat v3**：注入 Nuwa-style 消费心智模型、表达 DNA、诚实边界
- **全流程演示脚本** `scripts/demo_full_flow.py`：12 步 CLI 自动演示，覆盖完整业务链路
- **Bug 修复**：`stream()` 方法名拼写错误 / JSON 懒惰正则截断 / 浮点数量表答案类型错误 / `complete_json` 新增自动重试

### v0.1.0（2026-05-12）

- 初始 MVP-Lite 交付，完成 Health / Auth / Product / Persona / Survey / Evaluation / Report / Conversation 核心模块

---

## 已实现模块

- **Health** — 健康检查、存活探针、就绪探针
- **Auth** — mock 微信登录、JWT、profile
- **Product** — 产品创建、列表、详情、mock 上传 URL；`AI_PROVIDER=deepseek` 时走双阶段 AI 理解（GLM 视觉 + DeepSeek 推理）
- **Persona** — 系统角色、自定义角色、推荐、CRUD；seed 已支持 Persona v2 Nuwa-style 心智模型
- **Survey** — mock 种子模板生成，`AI_PROVIDER=deepseek` 时走 AI 生成 30 题问卷（7 种心理技法）
- **Evaluation** — 创建、选角色、run、取消、answers 查询（含 `summary_comment`）；本地默认 sync，`EVALUATION_RUN_MODE=celery` 时走 Celery 异步队列
- **Report** — 按 evaluation 查询，metrics 真实聚合，summary/top_pros/top_cons 规则生成
- **Conversation** — 创建、消息列表、SSE 流式对话，mock 默认，deepseek 可选
- **Credit** — balance / transactions 已实现，recharge 仍为 P1（返回 501）

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
| worker | 本地 Dockerfile | 无 | 可选，使用 profile `worker`，处理 evaluation 队列 |

如需同时启动 API 容器：

```bash
docker compose --profile api up -d
```

如需启动生产异步链路（API 入队 + worker 消费）：

```bash
docker compose --profile api --profile worker up -d --build
```

本机运行 API 时也可以单独启动 worker：

```bash
uv run celery -A app.tasks.celery_app.celery_app worker -Q evaluations -l info -c 4
```

## Evaluation Run Mode

默认 `.env.example` 使用：

```env
EVALUATION_RUN_MODE=sync
```

这是本地测试和普通前端联调模式：`POST /api/v1/evaluations/{id}/run` 会同步生成 answer，并返回 `status=done`。

生产异步模式使用：

```env
EVALUATION_RUN_MODE=celery
REDIS_URL=redis://localhost:6380/0
```

此时 `/run` 只做校验和入队，立即返回 `202 + status=answering + task_id`，前端每 2 秒轮询 `GET /api/v1/evaluations/{id}`，直到 `status=done/failed/canceled`。Docker `api` + `worker` profile 内部使用 `redis://redis:6379/0`。

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

人工联调演示脚本（需先完成上面的 seed 步骤，并在一个终端启动 API）：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再在另一个终端执行：

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

## Persona v2 / Nuwa-style 心智模型

当前角色 seed 支持 Nuwa-style 消费者心智蒸馏，但不引入外部 runtime 依赖，也不改 DB schema。`Persona.profile` 仍是 JSON 字段。

Persona v2 profile 重点字段：

| 字段 | 说明 |
|---|---|
| mind_model | 角色如何理解产品、消费、风险和证据 |
| decision_heuristics | 看到什么信号会买，看到什么信号会拒买 |
| expression_dna | 语气、句式、关键词、口头禅 |
| anti_patterns | 角色反感或不会被打动的内容 |
| scoring_bias | 默认评分倾向、高分/低分条件 |
| honest_boundaries | 不能假装知道、不能假装真实长期使用的边界 |

构建 Persona v2 seed：

```bash
uv run python scripts/build_persona_v2.py
```

导入 seed 时会优先读取 `../docs/SEEDS/personas_v2/`；如果该目录不存在或为空，则回退到旧版 `../docs/SEEDS/personas/`。

Prompt 行为：

- `persona_answer.j2` 会把角色心智模型、启发式、表达 DNA、反模式和诚实边界注入答卷约束。
- `persona_chat.j2` 保持微信聊天风格，但如果用户追问身份，会诚实说明是基于消费者画像生成的模拟反馈，不会声称自己是真实消费者本人。

## 当前状态摘要

| 模块 | 状态 |
|---|---|
| Health | done |
| Auth | mock（微信登录）/ done（其余） |
| Product | mock（上传/AI 理解）/ done（CRUD） |
| Persona | done |
| Survey | ai_optional |
| Evaluation | ai_optional / partial |
| Report | done / mock |
| Conversation | ai_optional |
| Credit | partial（balance / transactions done，recharge P1 / 501） |
| PDF / Share | p1_planned / not implemented |

详见 `../docs/API_STATUS.md`。

## 当前工程结论

截至 PR 10，后端可维护化第一阶段已完成。当前仓库已经具备统一验收命令、CI 门禁、文档事实对齐、权限隔离测试、AI / storage adapter 边界、evaluation 状态边界和基础 observability，可作为一个可维护的后端 MVP 继续迭代。

这并不代表生产级能力已经完成：真实基础设施、支付闭环、watchdog / retry、生产监控和告警仍属于后续路线。阶段收口说明见 `../docs/BACKEND_MAINTAINABILITY_PHASE1_CLOSEOUT.md`。
