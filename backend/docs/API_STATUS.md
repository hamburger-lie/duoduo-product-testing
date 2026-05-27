# API 实现状态表

冻结版本：**MVP-Lite Backend v0.1**

兼容性承诺：当前部分接口为 mock 或 ai_optional。后续替换为真实微信、真实 TOS、真实 AI、异步任务或内容审核时，应保持 `API_CONTRACT.md` 已定义的响应字段、错误结构、ID 字符串格式和状态枚举兼容；前端不要依赖 mock 文案具体内容。

状态说明：

| 状态 | 含义 |
|---|---|
| done | 真实 DB 可用 |
| mock | 接口可用但依赖是 mock |
| ai_optional | mock 默认，可通过 AI_PROVIDER=deepseek 切换真实 AI |
| partial | 本地/适配器能力已接入，但不是生产完整能力 |
| p1_not_implemented | P1 暂未实现 |
| p1_planned | 契约已定义，但当前版本尚未实现 |
| not_started | 未开始 |

---

## 前端当前可联调模块

- Health
- Auth
- Product
- Persona
- Survey
- Evaluation
- Report
- Conversation

## 前端暂不建议做入口

- Credit recharge
- PDF 导出
- 分享链接
- 充值
- 多产品对比
- 团队协作
- 真实支付

## Mock / AI Optional 摘要

| 类型 | 接口 / 能力 |
|---|---|
| mock | 微信登录（可配真实 jscode2session）、TOS upload-url |
| ai_optional | Survey 生成、Evaluation Persona Answer、Conversation messages（deepseek/mock） |
| done/mock | Report metrics 真实聚合，summary/top_pros/top_cons 规则生成或后续 AI 化 |
| partial | Credit（balance / transactions 已实现，recharge 未实现） |
| p1_planned | PDF export、share |
| p1_not_implemented | Credit/recharge |
| partial | local keyword moderation、DB-backed memory adapter、Celery evaluation run（需 EVALUATION_RUN_MODE=celery + worker） |

## Health

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| GET | /health | done | 基础健康检查 |
| GET | /health/live | done | 存活探针 |
| GET | /health/ready | done | 就绪探针（检查 DB / Redis / Qdrant） |

## Auth

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| POST | /api/v1/auth/wechat/login | mock/real | 默认 mock（任意 code），配置 WECHAT_APP_ID/SECRET 后走真实 jscode2session |
| PATCH | /api/v1/auth/profile | done | 真实 DB + JWT，设置 role_type/nickname |
| POST | /api/v1/auth/refresh | done | JWT 刷新 |
| GET | /api/v1/auth/me | done | 返回当前用户信息 |

## Product

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| POST | /api/v1/products/upload-url | mock | mock TOS 签名 URL，返回 mock object_key |
| POST | /api/v1/products | ai_optional | 真实 DB，mock 默认；deepseek/vision client 可生成 ai_summary，多图当前为 object_key/mock CDN 路径 |
| GET | /api/v1/products | done | 真实 DB 分页查询 |
| GET | /api/v1/products/{product_id} | done | 真实 DB |
| POST | /api/v1/products/{product_id}/reanalyze | ai_optional | 真实 DB，mock 默认；deepseek/vision client 可重新分析 |

## Persona

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| GET | /api/v1/personas | done | 真实 DB 分页查询 |
| GET | /api/v1/personas/recommend | done | 真实 DB + mock 推荐策略 |
| POST | /api/v1/personas | done | 真实 DB 创建自定义角色 |
| GET | /api/v1/personas/{persona_id} | done | 真实 DB |
| PATCH | /api/v1/personas/{persona_id} | done | 真实 DB 更新 |
| DELETE | /api/v1/personas/{persona_id} | done | 真实 DB 软删除 |

## Survey

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| POST | /api/v1/surveys/generate | ai_optional | mock 默认用种子模板，deepseek 时调 AI 生成 30 题 |
| GET | /api/v1/surveys/{survey_id} | done | 真实 DB |
| PUT | /api/v1/surveys/{survey_id}/questions | done | 真实 DB，evaluation 未开始时可编辑 |

## Evaluation

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| POST | /api/v1/evaluations | done | 真实 DB 创建 |
| GET | /api/v1/evaluations | done | 真实 DB 分页查询 |
| GET | /api/v1/evaluations/{evaluation_id} | done | 真实 DB |
| PUT | /api/v1/evaluations/{evaluation_id}/personas | done | 真实 DB 选择角色 |
| POST | /api/v1/evaluations/{evaluation_id}/run | partial | `sync` 本地模式同步完成；`celery` 生产异步模式返回 answering/task_id，由 worker 生成 answers；answer 内容仍可 mock/deepseek |
| POST | /api/v1/evaluations/{evaluation_id}/cancel | done | 真实 DB 协作式取消；有 task_id 时 revoke Celery task |
| GET | /api/v1/evaluations/{evaluation_id}/answers | done | 真实 DB |
| GET | /api/v1/evaluations/{evaluation_id}/answers/{persona_id} | done | 真实 DB |

## Report

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| GET | /api/v1/reports/by-evaluation/{evaluation_id} | done/mock | metrics 真实聚合，summary/top_pros/top_cons 为规则生成，可后续 AI 化 |

## Conversation

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| POST | /api/v1/conversations | done | 真实 DB 创建/获取 |
| GET | /api/v1/conversations | done | 真实 DB 分页 |
| GET | /api/v1/conversations/{conversation_id}/messages | done | 真实 DB 消息列表 |
| POST | /api/v1/conversations/{conversation_id}/messages | ai_optional | SSE 流式，mock 默认，deepseek 可选真实 AI 对话 |
| DELETE | /api/v1/conversations/{conversation_id} | done | 真实 DB 软删除 |

## Credit

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| GET | /api/v1/credits/balance | done | 查询当前用户余额 |
| POST | /api/v1/credits/recharge | p1_not_implemented | 当前返回 501 |
| GET | /api/v1/credits/transactions | done | 查询当前用户积分流水 |

## 其他未实现

| 功能 | 状态 | 说明 |
|---|---|---|
| PDF 导出 | p1_planned | 契约已定义，report.pdf_url 字段保留，逻辑未实现 |
| 分享链接 | p1_planned | 契约已定义，report.share_token 字段保留，逻辑未实现 |
| 多产品对比 | not_started | — |
| 团队协作 | not_started | — |
| 真实支付 | not_started | — |
| 内容审核 | partial | LocalModerationAdapter 关键词过滤可用；生产级第三方审核、图像审核、策略治理未完成 |
| 对话记忆 | partial | DB-backed memory adapter 可用；mem0/Qdrant 真实向量记忆未完成 |
| Celery 异步任务 | partial | Evaluation run 已支持 `EVALUATION_RUN_MODE=celery` 入队和 worker 消费；默认本地 `sync`，生产需启动 worker profile |
