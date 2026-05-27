# TASKS.md

> 项目：多角色 AI 测品工具  
> 版本：v0.1  
> 粒度：每个任务 1–4 小时，按依赖顺序排列  
> 原则：先跑通完整闭环，再补增强体验；任何任务未满足验收标准不得标记完成。

---

## 0. 任务状态约定

| 状态 | 含义 |
|---|---|
| `TODO` | 未开始 |
| `DOING` | 进行中 |
| `BLOCKED` | 被依赖或外部条件阻塞 |
| `DONE` | 已完成并通过验收 |

## 1. 里程碑总览

| 里程碑 | 目标 | 完成标志 |
|---|---|---|
| M0 | 项目骨架与本地依赖可运行 | `uv sync`、`docker-compose up`、`/health/live` 全通过 |
| M1 | 数据模型 + 迁移 + 种子角色 | PostgreSQL 有完整表，5 个角色种子可导入 |
| M2 | AI 编排层 | 产品理解、问卷生成、角色答题、报告合成 prompt 可冒烟 |
| M3 | P0 API 闭环 | 按 API_CONTRACT 跑通产品 → 问卷 → 角色 → 测评 → 报告 |
| M4 | 记忆与单角色对话 | 角色能基于问卷答案进行流式深聊 |
| M5 | 稳定性与合规 | 内容审核、错误码、限流、日志、测试、部署文档齐全 |
| M6 | 小程序对接预留 | API 与流式协议可被前端直接接入 |

---

## 2. M0：项目骨架与工程基线

### T001 初始化后端项目
- 预估：2h
- 依赖：无
- 内容：
  - 创建 `backend/` 目录
  - 使用 `uv init`
  - 配置 Python 3.11
  - 创建 `app/main.py`
  - 增加 `/health/live`
- 验收：
  - `uv run uvicorn app.main:app --reload` 可启动
  - `GET /health/live` 返回 `{"status":"ok"}`

### T002 配置 ruff / mypy / pytest
- 预估：2h
- 依赖：T001
- 内容：
  - 在 `pyproject.toml` 配置 ruff、mypy strict、pytest
  - 新增 `tests/test_health.py`
- 验收：
  - `uv run ruff check .` 通过
  - `uv run mypy app` 通过
  - `uv run pytest` 通过

### T003 建立标准目录结构
- 预估：2h
- 依赖：T001
- 内容：
  - 创建 `core/ db/ schemas/ routers/ services/ ai/ tasks/ storage/ utils/`
  - 每层加 `__init__.py`
  - `main.py` 只注册 router，不写业务
- 验收：
  - 目录结构与 TECH_DESIGN 一致
  - 无反向 import

### T004 增加 Docker Compose 本地依赖
- 预估：3h
- 依赖：T001
- 内容：
  - `docker-compose.yml` 包含 postgres、redis、qdrant
  - 增加 `.env.example`
- 验收：
  - `docker-compose up -d postgres redis qdrant` 成功
  - 本地端口不冲突
  - README 有启动命令

### T005 配置 Settings 与结构化日志
- 预估：3h
- 依赖：T003, T004
- 内容：
  - `app/core/config.py` 用 Pydantic Settings
  - `app/core/logging.py` 输出 request_id、level、module
- 验收：
  - 缺必填环境变量时启动失败且错误清晰
  - 日志不打印 JWT / API Key

---

## 3. M1：数据库、模型与种子数据

### T006 配置 SQLAlchemy async session
- 预估：3h
- 依赖：T004, T005
- 内容：
  - `db/session.py`
  - async engine / async session
  - FastAPI dependency
- 验收：
  - 测试中能打开和关闭 session
  - 连接串来自 Settings

### T007 配置 Alembic
- 预估：2h
- 依赖：T006
- 内容：
  - 初始化 `alembic/`
  - 支持 async migration
- 验收：
  - `uv run alembic current` 可执行
  - 空迁移可生成

### T008 实现基础模型 mixin
- 预估：2h
- 依赖：T006
- 内容：
  - `id`
  - `created_at`
  - `updated_at`
  - `deleted_at`
- 验收：
  - 所有模型继承统一 mixin
  - 时间字段使用 UTC

### T009 实现 User / Product 模型与迁移
- 预估：3h
- 依赖：T008
- 内容：
  - `users`
  - `products`
  - 必要索引
- 验收：
  - migration 可升级/回滚
  - 字段与 TECH_DESIGN 对齐

### T010 实现 Persona / Survey / Evaluation 模型与迁移
- 预估：4h
- 依赖：T009
- 内容：
  - `personas`
  - `surveys`
  - `evaluations`
- 验收：
  - JSONB 字段可写入/读取
  - persona categories 支持 GIN 索引

### T011 实现 Answer / Conversation / Report / Credit 模型与迁移
- 预估：4h
- 依赖：T010
- 内容：
  - `answers`
  - `conversations`
  - `conversation_messages`
  - `reports`
  - `credit_transactions`
- 验收：
  - 唯一约束 `(evaluation_id, persona_id)` 生效
  - `reports.evaluation_id` unique 生效

### T012 实现 Repository 基类与常用 CRUD
- 预估：4h
- 依赖：T011
- 内容：
  - `get_by_id`
  - `create`
  - `update`
  - `soft_delete`
  - cursor pagination helper
- 验收：
  - 单元测试覆盖正常/不存在/软删场景

### T013 导入 5 个 Persona 种子
- 预估：2h
- 依赖：T010, T012
- 内容：
  - `scripts/seed_personas.py`
  - 读取 `seeds/personas/*.json`
  - upsert by `seed_key`
- 验收：
  - 重复执行不会重复插入
  - `/personas` 后续能查到 5 个角色

### T014 导入美妆问卷与报告模板
- 预估：2h
- 依赖：T012
- 内容：
  - 导入 `survey_templates/beauty_survey_template.json`
  - 导入 `report_templates/beauty_report_template.json`
- 验收：
  - 模板 JSON schema 校验通过
  - 缺字段时脚本失败

---

## 4. M2：AI 编排层

### T015 实现 ModelRouter
- 预估：2h
- 依赖：T005
- 内容：
  - `TaskType`
  - endpoint env 映射
  - fallback 策略占位
- 验收：
  - 每个 TaskType 可解析到 endpoint id
  - 缺 endpoint 时错误明确

### T016 实现 Doubao OpenAI-Compatible Client
- 预估：3h
- 依赖：T015
- 内容：
  - `app/ai/client.py`
  - async client
  - timeout、retry、错误映射
- 验收：
  - mock 测试覆盖 timeout、rate limit、invalid response
  - 不在日志打印 API Key

### T017 实现 PromptManager
- 预估：3h
- 依赖：T003
- 内容：
  - 从 `app/ai/prompts/*.j2` 加载模板
  - 渲染时返回 `(rendered, version)`
- 验收：
  - 模板不存在返回内部错误
  - 渲染变量缺失有明确错误

### T018 落地产品理解 prompt
- 预估：2h
- 依赖：T017
- 内容：
  - 创建 `product_understand.j2`
  - 定义 JSON schema
- 验收：
  - prompt snapshot 测试通过
  - 不含硬编码具体产品

### T019 落地问卷生成 prompt
- 预估：2h
- 依赖：T017
- 内容：
  - 创建 `survey_generate.j2`
  - 强制 30 题/10 维度
- 验收：
  - prompt snapshot 测试通过
  - schema 校验规则写入测试

### T020 落地角色答题 prompt
- 预估：2h
- 依赖：T017
- 内容：
  - 创建 `persona_answer.j2`
  - 强制第一人称、禁止 AI 元话语
- 验收：
  - snapshot 测试通过
  - 检查 prompt 包含禁用语规则

### T021 落地角色对话 prompt
- 预估：2h
- 依赖：T017
- 内容：
  - 创建 `persona_chat.j2`
  - 注入 memory_context、answer_history、conversation_history
- 验收：
  - snapshot 测试通过
  - 输出说明为自然语言流式文本，不要求 JSON

### T022 落地报告合成 prompt
- 预估：2h
- 依赖：T017
- 内容：
  - 创建 `report_synthesize.j2`
  - 定义报告 JSON schema
- 验收：
  - snapshot 测试通过
  - 强制包含 disclaimer、top pros、top cons

### T023 实现 JSON 结构化输出解析与校验
- 预估：4h
- 依赖：T016, T018, T019, T020, T022
- 内容：
  - `ai/json_parser.py`
  - 去除代码块兜底
  - Pydantic schema 校验
  - 失败重试一次
- 验收：
  - 非法 JSON 返回 `AI_RESPONSE_INVALID`
  - JSON 外多余文本可安全处理或拒绝

### T024 实现 MemoryAdapter
- 预估：4h
- 依赖：T016
- 内容：
  - mem0 配置
  - `add_questionnaire`
  - `search`
  - `add_chat_turn`
- 验收：
  - 可用 fake memory 跑单测
  - user_id / agent_id / run_id 隔离正确

### T025 实现内容审核 Adapter
- 预估：3h
- 依赖：T005
- 内容：
  - 输入审核
  - 输出审核
  - 本地 fake mode
- 验收：
  - 测试可模拟通过/拒绝/服务不可用
  - 拒绝映射到 `AI_CONTENT_BLOCKED`

---

## 5. M3：P0 API 业务闭环

### T026 实现统一错误响应
- 预估：3h
- 依赖：T003
- 内容：
  - `AppError`
  - 全局 exception handler
  - request_id
- 验收：
  - 错误格式与 API_CONTRACT 一致
  - 每个响应带 `X-Request-Id`

### T027 实现 Auth 微信登录 mock 版
- 预估：3h
- 依赖：T009, T026
- 内容：
  - `/auth/wechat/login`
  - 本地 mock code
  - JWT 签发
- 验收：
  - 新用户默认 1000 积分
  - token 可访问 `/auth/me`

### T028 实现 Profile 修改
- 预估：2h
- 依赖：T027
- 内容：
  - `PATCH /auth/profile`
- 验收：
  - role_type 只能是 manufacturer/channel
  - 返回 user 对象

### T029 实现 Product upload-url
- 预估：3h
- 依赖：T026
- 内容：
  - 文件类型校验
  - size 校验
  - TOS fake client
- 验收：
  - jpg/png 通过
  - >5MB 返回 `FILE_TOO_LARGE`

### T030 实现 Product 创建
- 预估：4h
- 依赖：T018, T023, T025, T029
- 内容：
  - `/products`
  - 调产品理解
  - 写入 `products.ai_summary`
- 验收：
  - 成功返回 API_CONTRACT 结构
  - AI 失败时 status=failed 或返回明确错误

### T031 实现 Product 查询与列表
- 预估：3h
- 依赖：T030
- 内容：
  - `GET /products/{id}`
  - `GET /products`
  - 游标分页
- 验收：
  - 只能查自己的产品
  - 分页结构正确

### T032 实现 Persona 列表与详情
- 预估：3h
- 依赖：T013, T026
- 内容：
  - `GET /personas`
  - `GET /personas/{id}`
- 验收：
  - 支持 category / owner_scope / keyword
  - 私有角色权限正确

### T033 实现 Persona 推荐
- 预估：3h
- 依赖：T032, T030
- 内容：
  - `GET /personas/recommend`
  - MVP：category 匹配 + 20% critical
- 验收：
  - count 参数生效
  - 推荐列表包含挑剔型角色

### T034 实现 Evaluation 创建与选角色
- 预估：4h
- 依赖：T030, T032
- 内容：
  - `POST /evaluations`
  - `PUT /evaluations/{id}/personas`
- 验收：
  - 角色数量限制 5-100
  - 非 pending 状态不可改

### T035 实现 Survey 生成
- 预估：4h
- 依赖：T019, T023, T034
- 内容：
  - `POST /surveys/generate`
  - 写入 surveys
  - evaluation 关联 survey_id
- 验收：
  - 必须生成 30 题
  - 每个维度 3 题
  - 失败返回 `SURVEY_GENERATION_FAILED`

### T036 实现 Survey 查询与编辑占位
- 预估：3h
- 依赖：T035
- 内容：
  - `GET /surveys/{id}`
  - `PUT /surveys/{id}/questions`
- 验收：
  - 已运行测评返回 `SURVEY_LOCKED`
  - MVP 可允许编辑但必须校验 30 题规则

### T037 实现单角色答题 Service
- 预估：4h
- 依赖：T020, T023, T024
- 内容：
  - `PersonaAnswerService.answer_one`
  - 写 `answers`
  - 写 memory
- 验收：
  - 输入 persona/survey/product 输出 answers JSON
  - 失败不影响其它角色

### T038 实现 Celery 配置
- 预估：3h
- 依赖：T004
- 内容：
  - `tasks/celery_app.py`
  - Redis broker/backend
- 验收：
  - worker 可启动
  - demo task 可执行

### T039 实现 Evaluation run 编排任务
- 预估：4h
- 依赖：T037, T038
- 内容：
  - 并发限制 20
  - 状态流转 answering → generating_report
  - progress 更新
- 验收：
  - 5 个角色可并行答题
  - 部分失败仍可生成报告

### T040 实现 Evaluation 状态查询/列表/取消
- 预估：4h
- 依赖：T039
- 内容：
  - `GET /evaluations/{id}`
  - `POST /evaluations/{id}/cancel`
  - `GET /evaluations`
- 验收：
  - 轮询响应含 stats
  - canceled 后任务不再继续写入新答案

### T041 实现 Report 生成 Service
- 预估：4h
- 依赖：T022, T023, T039
- 内容：
  - 聚合 answers
  - 调报告合成
  - 写 reports
- 验收：
  - `top_pros`、`top_cons` 均不少于 3
  - `ai_disclaimer` 存在

### T042 实现 Report 查询
- 预估：2h
- 依赖：T041
- 内容：
  - `GET /reports/{evaluation_id}`
- 验收：
  - 只能查自己的 report
  - 结构与 API_CONTRACT 一致

### T043 实现单角色答案查询
- 预估：2h
- 依赖：T037, T040
- 内容：
  - `GET /evaluations/{id}/answers/{persona_id}`
- 验收：
  - 返回该角色完整逐题答案
  - 无权限返回 403

---

## 6. M4：单角色对话与流式协议

### T044 实现 Conversation 创建/获取
- 预估：3h
- 依赖：T011, T043
- 内容：
  - 按 user/evaluation/persona 获取或创建 conversation
- 验收：
  - 同一个用户同一角色复用同一 conversation
  - 不允许跨用户访问

### T045 实现流式响应工具
- 预估：3h
- 依赖：T026
- 内容：
  - `ai/streaming.py`
  - SSE-like chunk 格式
  - delta/meta/done/error
- 验收：
  - 格式与 API_CONTRACT §0.6 一致
  - 单测能按 `\n\n` 切分解析

### T046 实现单角色对话接口
- 预估：4h
- 依赖：T021, T024, T044, T045
- 内容：
  - `POST /conversations/{id}/messages`
  - memory.search
  - LLM streaming
  - 保存 user/assistant message
  - memory.add_chat_turn
- 验收：
  - 首 chunk < 2 秒（mock 环境）
  - 20 轮后返回 `CONVERSATION_LIMIT_REACHED`
  - 单条 > 500 字返回 `MESSAGE_TOO_LONG`

### T047 实现对话历史查询
- 预估：2h
- 依赖：T046
- 内容：
  - `GET /conversations/{id}/messages`
- 验收：
  - 按时间升序
  - 支持 limit

---

## 7. M5：积分、限流、合规、测试

### T048 实现积分流水基础服务
- 预估：3h
- 依赖：T011
- 内容：
  - 初始化积分
  - 记录消费和返还
  - MVP 不强制扣费开关
- 验收：
  - 所有生成类操作可记录 credit_cost
  - 流水 balance_after 正确

### T049 实现积分查询接口
- 预估：2h
- 依赖：T048
- 内容：
  - `GET /credits/balance`
  - `GET /credits/transactions`
- 验收：
  - 分页正常
  - 只返回当前用户流水

### T050 实现 Redis 限流
- 预估：4h
- 依赖：T004, T026
- 内容：
  - 普通接口 100 req/min
  - 生成类 20 req/min
- 验收：
  - 超限返回 `RATE_LIMITED`
  - Header 包含 `Retry-After`

### T051 实现健康检查 ready
- 预估：3h
- 依赖：T006, T004, T016
- 内容：
  - 检查 DB/Redis/Qdrant/Ark
- 验收：
  - 任一依赖失败返回 503
  - 成功返回 API_CONTRACT 结构

### T052 实现 E2E 完整闭环测试
- 预估：4h
- 依赖：T042, T046
- 内容：
  - 登录
  - 创建产品
  - 创建测评
  - 生成问卷
  - 选 5 角色
  - run
  - 查询报告
  - 单角色对话
- 验收：
  - `uv run pytest tests/e2e/test_full_flow.py` 通过
  - mock LLM 下稳定可重复

### T053 实现角色多样性评估脚本
- 预估：4h
- 依赖：T037
- 内容：
  - `scripts/eval_persona_diversity.py`
  - 检查购买意愿分布
  - 检查元话语
  - 检查角色回答相似度
- 验收：
  - 输出 pass/fail
  - 低多样性时明确列出问题角色

### T054 完善 API 错误码测试
- 预估：4h
- 依赖：T026, T043, T046, T049
- 内容：
  - 对照 API_CONTRACT 错误码表
  - 每类至少一个反例
- 验收：
  - 关键错误码均有测试
  - 错误 body 包含 code/message/request_id/timestamp

### T055 日志脱敏与审计检查
- 预估：3h
- 依赖：T005
- 内容：
  - 脱敏 JWT、API key、上传 URL
  - 禁止记录产品图原始内容
- 验收：
  - 单测覆盖敏感字段
  - grep 日志不出现 key/token

### T056 内容审核接入到产品/对话/报告
- 预估：4h
- 依赖：T025, T030, T046, T041
- 内容：
  - 产品输入审核
  - 对话输入审核
  - 报告输出审核
- 验收：
  - 被拒绝内容返回 `AI_CONTENT_BLOCKED`
  - 审核服务不可用时策略明确：生成类 fail closed，对话可提示重试

---

## 8. M6：部署与交付

### T057 编写 Dockerfile
- 预估：3h
- 依赖：T052
- 内容：
  - uv sync
  - non-root 用户
  - healthcheck
- 验收：
  - 镜像可构建
  - 容器内 `/health/live` 通过

### T058 编写生产 docker-compose
- 预估：3h
- 依赖：T057
- 内容：
  - app
  - worker
  - nginx
  - qdrant
- 验收：
  - `docker compose up -d` 成功
  - app 和 worker 使用同一份 env

### T059 编写 README 部署步骤
- 预估：3h
- 依赖：T058
- 内容：
  - 本地启动
  - 迁移
  - 灌种子
  - worker
  - 常见错误
- 验收：
  - 新开发者按 README 能启动本地服务

### T060 编写前端对接说明
- 预估：3h
- 依赖：T046
- 内容：
  - 登录流程
  - 上传流程
  - 测评轮询
  - 流式对话解析示例
- 验收：
  - 微信小程序开发者不看后端代码也能接入

### T061 交付前验收清单
- 预估：2h
- 依赖：T052, T054, T056, T059
- 内容：
  - 形成 `docs/ACCEPTANCE.md`
- 验收：
  - 列出 P0 接口、命令、测试、已知限制
  - 明确哪些是 MVP 不做事项

---

## 9. 推荐执行顺序

第一周：
- T001–T014

第二周：
- T015–T025

第三周：
- T026–T036

第四周：
- T037–T043

第五周：
- T044–T047

第六周：
- T048–T056

第七周：
- T057–T061

第八周：
- 小程序联调、真实模型灰度、种子用户试用、修 bug

---

## 10. 不允许跳过的验收命令

每次合并前必须跑：

```bash
uv run ruff check .
uv run mypy app
uv run pytest
```

涉及数据库变更必须跑：

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

涉及 AI prompt 变更必须跑：

```bash
uv run pytest tests/ai
uv run python scripts/eval_persona_diversity.py --sample 20
```

涉及完整流程变更必须跑：

```bash
docker-compose up -d postgres redis qdrant
uv run pytest tests/e2e/test_full_flow.py
```
