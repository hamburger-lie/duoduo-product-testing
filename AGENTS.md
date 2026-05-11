# AGENTS.md

> 项目：多角色 AI 测品工具  
> 适用对象：Claude / Codex / Cursor / 其他 AI 编码助手  
> 优先级：本文件高于临时口头建议；如与 PRD、TECH_DESIGN、API_CONTRACT 冲突，以 API_CONTRACT 和 TECH_DESIGN 为准。

---

## 0. 项目目标

本项目是一个“多角色 AI 测品工具”后端 MVP。

核心闭环：

```text
用户登录
→ 创建产品
→ AI 理解产品
→ 生成问卷
→ 选择消费者角色
→ 多角色并行答题
→ 生成测评报告
→ 单角色流式深聊
```

MVP 不做：

- B 端控制台
- 团队协作
- 数据导出 API
- 多产品横向对比
- 真实支付闭环
- 承诺替代真人调研或功效测试

---

## 1. 强制技术栈

| 项 | 要求 |
|---|---|
| Python | 3.11.x |
| 包管理 | uv，禁止直接使用 pip |
| Web | FastAPI |
| ORM | SQLAlchemy 2.0 async |
| Migration | Alembic |
| Schema | Pydantic v2 |
| DB | PostgreSQL |
| Cache / Broker | Redis |
| Vector | Qdrant |
| Task | Celery |
| LLM SDK | OpenAI-compatible client for 火山方舟 |
| Test | pytest + pytest-asyncio + httpx |
| Lint | ruff |
| Type | mypy strict |

---

## 2. 架构边界

强制依赖方向：

```text
routers → services → ai / db / tasks / storage → core
```

禁止：

- `services` import `routers`
- `ai` import 具体 router
- `db` import service
- `core` import 业务模块
- 在 router 写业务逻辑
- 在 service 里直接写 OpenAI/Doubao 调用
- 在代码里硬编码 prompt

### 2.1 各层职责

| 层 | 可以做 | 禁止做 |
|---|---|---|
| `routers/` | 参数接收、鉴权依赖、调用 service、返回 schema | 业务编排、数据库事务、LLM 调用 |
| `services/` | 业务流程、事务边界、调用 repo/ai/tasks | HTTP 细节、外部 API 底层封装 |
| `ai/` | 模型路由、prompt 渲染、JSON 解析、记忆、流式 | 感知具体 HTTP endpoint |
| `db/` | ORM model、repository、migration | 业务判断 |
| `tasks/` | 异步任务、长流程编排 | 对外暴露 HTTP |
| `core/` | config、logging、security、exception | 业务依赖 |

---

## 3. API 契约规则

`API_CONTRACT.md` 是唯一接口来源。

开发接口前必须确认：

1. 路径是否已在 API_CONTRACT 中存在。
2. 请求字段是否完全一致。
3. 响应结构是否完全一致。
4. 错误码是否使用文档中定义的 code。
5. ID 在 JSON 中必须用字符串传输，避免 JS 精度丢失。
6. 响应错误必须包含：
   - `code`
   - `message`
   - `details`
   - `request_id`
   - `timestamp`

禁止：

- 私自新增未记录接口。
- 私自把成功响应包成 `{data: ...}`。
- 私自改字段名。
- 直接返回 Python exception 文本。
- 返回内部 task id、数据库错误栈、API key。

---

## 4. 代码风格

### 4.1 Python

必须：

- 所有函数有完整类型标注。
- 所有 public function 有 docstring。
- 使用 `from __future__ import annotations`。
- Pydantic v2 使用 `model_config = ConfigDict(...)`。
- SQLAlchemy 使用 2.0 风格。
- 所有 IO 使用 async。
- 外部 API 必须设置 timeout。
- 所有写库操作必须在 transaction 中。

禁止：

- 裸 `except Exception` 后吞掉错误。
- `print()` 日志。
- 字符串拼接 SQL。
- 全局可变状态保存用户数据。
- 在代码中硬编码密钥、endpoint、prompt。
- 在测试中调用真实 LLM，除非该测试被明确标记为 integration。

### 4.2 命名

| 类型 | 规则 | 示例 |
|---|---|---|
| 文件 | snake_case | `product_service.py` |
| 类 | PascalCase | `ProductService` |
| 函数 | snake_case | `create_product` |
| 常量 | UPPER_SNAKE_CASE | `MAX_PERSONA_COUNT` |
| API schema | PascalCase + Request/Response | `CreateProductRequest` |
| DB model | PascalCase | `Product` |

---

## 5. Prompt 规则

所有 prompt 文件必须位于：

```text
backend/app/ai/prompts/*.j2
```

禁止：

- 在 service 里写大段 prompt。
- 在 task 里拼接 prompt。
- 不带版本号修改 prompt。
- 让模型输出无法解析的自由文本，除单角色对话流式接口外。

每个结构化 prompt 必须：

1. 明确输出 JSON schema。
2. 明确禁止 Markdown。
3. 明确禁止编造。
4. 有对应 Pydantic 校验。
5. 有 snapshot test。

当前核心 prompt：

- `product_understand.j2`
- `survey_generate.j2`
- `persona_answer.j2`
- `persona_chat.j2`
- `report_synthesize.j2`
- `memory_extract.j2`

---

## 6. AI 与模型调用规则

所有模型调用必须经过：

```text
ai/client.py → ai/models.py(ModelRouter) → ai/prompt_manager.py
```

禁止 service 直接调用 SDK。

### 6.1 TaskType

必须使用以下任务类型：

- `PRODUCT_UNDERSTAND`
- `SURVEY_GENERATE`
- `PERSONA_ANSWER`
- `PERSONA_CHAT`
- `REPORT_SYNTHESIZE`
- `MEMORY_EXTRACT`

### 6.2 错误映射

| 模型/外部错误 | API 错误码 |
|---|---|
| timeout | `AI_SERVICE_TIMEOUT` |
| rate limit | `AI_RATE_LIMITED` |
| invalid JSON | `AI_RESPONSE_INVALID` |
| content blocked | `AI_CONTENT_BLOCKED` |
| service unavailable | `AI_SERVICE_UNAVAILABLE` |

### 6.3 重试

允许：

- 网络临时错误：最多 2 次，指数退避。
- JSON 解析失败：最多 1 次，带“只返回合法 JSON”重试。

禁止：

- 对内容审核拒绝进行自动绕过重试。
- 无限重试。
- 在任务中无上限并发调用模型。

---

## 7. 数据库规则

### 7.1 基础字段

所有业务表必须有：

- `id`
- `created_at`
- `updated_at`
- `deleted_at`

### 7.2 软删

默认使用软删。

用户主动删除数据：

- 先 `deleted_at`
- 30 天后再硬删
- 产品图、报告 PDF、对话记录按保留期清理

### 7.3 JSONB

可用 JSONB 存：

- 产品 AI summary
- persona profile
- survey questions
- answers
- report metrics

但必须有 Pydantic schema 校验，不能随意存未知结构。

### 7.4 Migration

每次改 model 必须生成 migration。

必须验证：

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

禁止：

- 直接手动改库。
- 生产环境 drop table。
- migration 中写不可逆危险操作，除非明确注释。

---

## 8. 安全与合规

必须：

- HTTPS only for production。
- JWT secret 至少 32 字节。
- 文件上传只允许 jpg/png。
- 图片大小 ≤ 5MB。
- 校验 magic number，不只看后缀。
- 输入和输出都接内容审核。
- 报告和对话页面显式标注：`AI 生成内容仅供参考`。
- 日志脱敏。

禁止记录：

- JWT
- 方舟 API Key
- TOS 签名 URL
- 用户产品图原文
- 详细隐私信息
- 微信 code

---

## 9. 流式协议规则

单角色对话使用 HTTP chunked 的 SSE-like 协议。

必须输出：

```text
data: {"event":"delta","content":"你好"}

data: {"event":"meta","message_id":"123","tokens":{"input":100,"output":20}}

data: {"event":"done"}
```

禁止：

- 使用 WebSocket 替代当前协议。
- 输出非 `data:` 前缀。
- 忽略 `error` 事件。
- 在 done 后继续写 chunk。

---

## 10. 测试要求

### 10.1 每次提交必须通过

```bash
uv run ruff check .
uv run mypy app
uv run pytest
```

### 10.2 必测范围

| 变更类型 | 必须新增/更新测试 |
|---|---|
| router | 接口正反例 |
| service | 业务状态流转 |
| db model | migration + repository |
| ai prompt | prompt snapshot + JSON parse |
| task | mock 异步任务 |
| stream | chunk 格式解析 |
| auth | token 有效/无效/过期 |
| permission | 跨用户访问禁止 |

### 10.3 测试隔离

默认测试不能访问：

- 真实方舟 API
- 真实微信 API
- 真实 TOS
- 真实内容审核

必须用 fake / mock。

真实服务测试必须放在：

```text
tests/integration/
```

并通过环境变量显式开启。

---

## 11. 任务执行方式

AI 编码助手每次只做一个 TASKS.md 中的任务或一组强相关小任务。

每次输出必须包含：

1. 改了哪些文件。
2. 为什么改。
3. 如何验证。
4. 哪些测试已通过。
5. 哪些风险还没处理。

禁止：

- 一次性大改多个模块。
- 未经说明重构目录。
- 删除已有功能。
- 改 API_CONTRACT 但不说明兼容性。
- 为了测试方便绕过鉴权、权限或审核。

---

## 12. 提交前自检清单

提交前逐项确认：

- [ ] 没有 hardcoded secret。
- [ ] 没有 router 业务逻辑。
- [ ] 没有 service 直接调 LLM。
- [ ] 没有 prompt 写在代码里。
- [ ] 所有外部 API 有 timeout。
- [ ] 所有错误使用统一 AppError。
- [ ] 所有 response 与 API_CONTRACT 对齐。
- [ ] ruff 通过。
- [ ] mypy 通过。
- [ ] pytest 通过。
- [ ] 数据库变更有 migration。
- [ ] prompt 变更有测试。
- [ ] 日志不泄露敏感信息。

---

## 13. AI 助手禁止事项

绝对禁止：

1. 为了“跑通”删除鉴权。
2. 为了“省事”跳过内容审核。
3. 为了“简单”把 prompt 写进 service。
4. 为了“方便”使用同步 DB session。
5. 为了“快”绕过 Alembic。
6. 为了“展示效果”编造真实用户数据。
7. 为了“优化”擅自改变 API 字段。
8. 为了“减少报错”吞异常。
9. 为了“兼容”把所有字段设为 optional。
10. 为了“先做出来”把测试删掉或改弱。

---

## 14. 默认开发命令

```bash
# 安装依赖
uv sync

# 启动依赖
docker-compose up -d postgres redis qdrant

# 数据库迁移
uv run alembic upgrade head

# 导入种子
uv run python scripts/seed_personas.py

# 启动服务
uv run uvicorn app.main:app --reload

# 启动 worker
uv run celery -A app.tasks.celery_app worker -l info -c 4

# 质量检查
uv run ruff check .
uv run mypy app
uv run pytest
```
