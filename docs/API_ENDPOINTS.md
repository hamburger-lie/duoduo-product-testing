# API 接口功能表

> 版本：v0.2（M5 完成后更新）
> 前缀：所有接口以 `/api/v1` 开头（健康检查除外）
> 鉴权：除 `/auth/wechat/login`、`/health/*` 外，所有接口需携带 `Authorization: Bearer <token>`

---

## 1. 鉴权 Auth

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| POST | `/api/v1/auth/wechat/login` | 微信小程序登录 / 注册 | 无 | 无 appid 时走 mock 模式 |
| POST | `/api/v1/auth/refresh` | 刷新 JWT Token | 标准 | — |
| GET  | `/api/v1/auth/me` | 查询当前用户信息 | 标准 | 返回 credit_balance |
| PATCH | `/api/v1/auth/profile` | 修改昵称 / 角色类型 | 标准 | role_type: manufacturer \| channel |

---

## 2. 产品 Product

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| POST | `/api/v1/products/upload-url` | 获取图片上传预签名 URL | 标准 | 支持 jpg/png，最大 5MB |
| POST | `/api/v1/products` | 创建产品（含 AI 理解）| 标准 | 支持 image_object_keys 或 image_base64_list |
| GET  | `/api/v1/products` | 分页列出我的产品 | 标准 | 游标分页 |
| GET  | `/api/v1/products/{id}` | 查询单个产品详情 | 标准 | — |
| POST | `/api/v1/products/{id}/reanalyze` | 重新触发 AI 产品理解 | 标准 | — |

---

## 3. 角色 Persona

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| GET  | `/api/v1/personas` | 分页列出角色库（offset 分页）| 标准 | 支持 category / owner_scope / keyword 过滤 |
| GET  | `/api/v1/personas/recommend` | 按产品推荐角色 | 标准 | 含挑剔型角色 |
| POST | `/api/v1/personas` | 创建自定义私有角色 | 标准 | owner_scope=private |
| GET  | `/api/v1/personas/{id}` | 查询单个角色详情 | 标准 | — |
| PATCH | `/api/v1/personas/{id}` | 修改私有角色信息 | 标准 | 仅 owner 可操作 |
| DELETE | `/api/v1/personas/{id}` | 软删除私有角色 | 标准 | 204 No Content |

---

## 4. 测评 Evaluation

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| POST | `/api/v1/evaluations` | 创建测评（关联产品）| 标准 | 初始状态 pending |
| GET  | `/api/v1/evaluations` | 分页列出我的测评 | 标准 | 支持 status 过滤 |
| GET  | `/api/v1/evaluations/{id}` | 查询测评详情 / 进度 | 标准 | 含 stats |
| PUT  | `/api/v1/evaluations/{id}/personas` | 选择参与角色 | 标准 | 1–100 个 |
| POST | `/api/v1/evaluations/{id}/run` | 启动测评（角色答题）| **生成类 20/min** | 同步或 Celery 异步 |
| POST | `/api/v1/evaluations/{id}/cancel` | 取消进行中测评 | 标准 | — |
| GET  | `/api/v1/evaluations/{id}/answers` | 列出所有角色答案摘要 | 标准 | 含 `summary_comment` |
| GET  | `/api/v1/evaluations/{id}/answers/{persona_id}` | 查询单角色完整答案 | 标准 | 逐题明细，含 `summary_comment` |

---

## 5. 问卷 Survey

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| POST | `/api/v1/surveys/generate` | AI 生成问卷（30 题）| **生成类 20/min** | 关联 evaluation |
| GET  | `/api/v1/surveys/{id}` | 查询问卷详情 | 标准 | — |
| PUT  | `/api/v1/surveys/{id}/questions` | 编辑问卷题目 | 标准 | 测评运行中返回 SURVEY_LOCKED |

---

## 6. 报告 Report

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| GET  | `/api/v1/reports/by-evaluation/{evaluation_id}` | 查询报告（不存在则自动生成）| 标准 | 含 top_pros、top_cons、ai_disclaimer、metrics |

---

## 7. 对话 Conversation

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| POST | `/api/v1/conversations` | 创建 / 获取对话（幂等）| 标准 | 同一 evaluation+persona 复用 |
| GET  | `/api/v1/conversations` | 列出我的对话 | 标准 | 游标分页 |
| GET  | `/api/v1/conversations/{id}/messages` | 查询历史消息 | 标准 | 按时间升序 |
| POST | `/api/v1/conversations/{id}/messages` | 发送消息（SSE 流式）| 标准 | text/event-stream，事件：delta / meta / done / error |
| DELETE | `/api/v1/conversations/{id}` | 删除对话 | 标准 | 软删除 |

---

## 8. 积分 Credit

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| GET  | `/api/v1/credits/balance` | 查询当前积分余额 | 标准 | — |
| GET  | `/api/v1/credits/transactions` | 分页查询积分流水 | 标准 | 游标分页，newest-first |
| POST | `/api/v1/credits/recharge` | 充值（MVP 未开放）| 标准 | 固定返回 501 NOT_IMPLEMENTED |

---

## 9. 历史记录 History

| 方法 | 路径 | 功能 | 限流 | 备注 |
|------|------|------|------|------|
| GET  | `/api/v1/history` | 分页查询评测历史（含产品/问卷/报告摘要）| 标准 | 游标分页，newest-first |

---

## 10. 健康检查 Health

| 方法 | 路径 | 功能 | 鉴权 | 备注 |
|------|------|------|------|------|
| GET  | `/health` | 服务基础信息 | 无 | 返回 name + version |
| GET  | `/health/live` | 存活探针（Liveness）| 无 | 始终 200 |
| GET  | `/health/ready` | 就绪探针（Readiness）| 无 | 检查 DB / Redis / Qdrant，任一失败返回 503 |

---

## 附：限流规则

| 类型 | 限制 | 适用接口 |
|------|------|---------|
| 标准（std）| 100 请求 / 分钟 / 用户 | 除生成类外所有接口 |
| 生成类（gen）| 20 请求 / 分钟 / 用户 | `POST /surveys/generate`、`POST /evaluations/{id}/run` |

超限返回 `429 RATE_LIMITED`，响应头含 `Retry-After`（秒）。

---

## 附：SSE 流式事件格式

适用接口：`POST /api/v1/conversations/{id}/messages`

```
data: {"event":"delta","content":"你好"}

data: {"event":"meta","message_id":"123","tokens":{"input":100,"output":20}}

data: {"event":"done"}
```

| event | 说明 |
|-------|------|
| `delta` | 文本增量片段 |
| `meta` | 元信息（消息 ID、token 用量），done 前最多 1 次 |
| `error` | 出错，立即关闭流 |
| `done` | 流结束 |

---

## 附：角色答案字段说明

### `summary_comment` — 角色总结性发言

适用接口：`GET /evaluations/{id}/answers` 和 `GET /evaluations/{id}/answers/{persona_id}`

答题完成后，AI 以该角色第一人称生成 2–3 句总结短评，风格模拟真实消费者在社群里的点评，体现该角色的消费心智和表达风格（60–150 字）。

**示例值（`GET /evaluations/{id}/answers/{persona_id}` 响应片段）：**

```json
{
  "persona_id": "42",
  "persona_snapshot": { "name": "林雪", "persona_tag": "成分党" },
  "overall_intent": 3,
  "sentiment": "neutral",
  "summary_comment": "这款面霜质地确实不错，上脸很润但不黏腻。不过 169 的价格对我来说偏高了，成分表里烟酰胺浓度也没标清楚，如果有试用装我会先试试再决定。",
  "answers": [ ... ],
  "created_at": "2026-05-13T10:00:00Z"
}
```

**示例值（`GET /evaluations/{id}/answers` 摘要列表单条）：**

```json
{
  "persona_id": "42",
  "persona_name": "林雪",
  "persona_tag": "成分党",
  "overall_intent": 3,
  "sentiment": "neutral",
  "summary_comment": "这款面霜质地确实不错，上脸很润但不黏腻。不过 169 的价格对我来说偏高了，成分表里烟酰胺浓度也没标清楚，如果有试用装我会先试试再决定。"
}
```

> `summary_comment` 为可选字段（`string | null`）。mock 模式下为 `null`；AI 模式下由 `persona_answer` prompt 生成并持久化到 `answers` 表，不额外消耗 API 调用。

---

## 附：错误响应格式

```json
{
  "code": "EVALUATION_NOT_FOUND",
  "message": "指定的测评不存在",
  "details": { "evaluation_id": "12345" },
  "request_id": "req_8a7c...",
  "timestamp": "2026-05-13T10:00:00Z"
}
```

每个响应均携带 `X-Request-Id` header。

---

*最后更新：2026-05-13（M5 + T022 + summary_comment 完成后）*
