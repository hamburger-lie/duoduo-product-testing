# API 契约文档

> 版本：v0.1
> 配套：PRD v0.1 / TECH_DESIGN v0.1
> 路径前缀：`/api/v1`
> 说明：本文档是前后端约定的唯一来源；任何未在此列出的接口不得调用，任何变更必须 PR 同步更新本文件并加版本号。

---

## 0. 通用约定

### 0.1 基础规范
- **协议**：HTTPS only（生产）；本地开发可走 HTTP
- **编码**：所有请求与响应 body 均为 UTF-8 JSON（流式接口除外，见 §0.6）
- **时间**：所有时间字段统一 ISO 8601 + UTC，例 `2026-05-09T12:00:00Z`
- **ID**：所有资源 ID 为 64 位整数（snowflake），JSON 中以 **字符串** 传输（避免 JS 精度丢失），例 `"id": "1234567890123456789"`
- **分页**：游标分页为主，部分场景支持 offset，详见 §0.5

### 0.2 鉴权
- 除 `/auth/wechat/login` 与 `/health/*` 外，所有接口必须带 header：
```
  Authorization: Bearer <jwt_token>
```
- Token 失效返回 `401 + AUTH_TOKEN_INVALID`
- Token 即将过期可调 `/auth/refresh` 续期

### 0.3 通用 Header
| Header | 必填 | 说明 |
|---|---|---|
| `Authorization` | 是（除登录） | `Bearer <jwt>` |
| `Content-Type` | POST/PUT/PATCH 必填 | `application/json` |
| `X-Request-Id` | 否 | 客户端可传，否则服务端生成；用于链路追踪 |
| `X-Client-Version` | 建议 | `wxmini/0.1.0` 等 |

### 0.4 通用响应包装
**成功**：直接返回业务对象或数组（不再包 `data` 字段，避免双层嵌套）。
**失败**：统一错误格式见 §0.7。
**响应必带 header**：`X-Request-Id`。

### 0.5 分页规范
- 游标分页参数：`?cursor=xxx&limit=20`
  - `cursor` 为不透明字符串（base64 编码的时间戳+id）
  - 响应：
```json
    {
      "items": [...],
      "next_cursor": "xxx",
      "has_more": true
    }
```
- offset 分页（仅角色库等列表）：`?page=1&page_size=20`
  - 响应：
```json
    {
      "items": [...],
      "page": 1,
      "page_size": 20,
      "total": 156,
      "total_pages": 8
    }
```

### 0.6 流式协议（SSE-like over HTTP chunked）
**适用**：单角色对话 `POST /conversations/{id}/messages`
**响应 Header**：
```
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
X-Accel-Buffering: no
Transfer-Encoding: chunked
```
**消息格式**（每条以 `\n\n` 分隔）：
```
data: {"event":"delta","content":"你好"}

data: {"event":"delta","content":"，我是"}

data: {"event":"meta","message_id":"123","tokens":{"input":100,"output":20}}

data: {"event":"done"}
```
**事件类型**：
| event | 说明 |
|---|---|
| `delta` | 文本增量片段；`content` 字段是新增字符 |
| `meta` | 元信息（消息 ID、token 用量），最多 1 次，通常在 `done` 前 |
| `error` | 出错；`code` + `message`，之后立即关闭流 |
| `done` | 流结束 |

**客户端处理建议**：按 `\n\n` 切分，逐条 JSON.parse；遇 `done` 或连接关闭即结束。

### 0.7 错误响应

```json
{
  "code": "PERSONA_NOT_FOUND",
  "message": "指定的角色不存在",
  "details": { "persona_id": "12345" },
  "request_id": "req_8a7c...",
  "timestamp": "2026-05-09T12:00:00Z"
}
```

完整错误码表见 §10。

### 0.8 限流
- 用户级：100 req/min（普通接口），20 req/min（生成类接口）
- 超限返回 `429 + RATE_LIMITED`，header 带 `Retry-After`（秒）

### 0.9 幂等性
- `POST` 创建类接口支持 `Idempotency-Key` header（uuid），24h 内重复请求返回首次结果

### 0.10 服务端回传 Webhook
**适用**：后端向已配置的 `FOLLOWUP_WEBHOOK_URL` 推送测评跟进事件。该能力不是客户端 API，不使用 `/api/v1` 路径。

**触发时机**：
- `evaluation.done`：测评任务完成，至少部分角色答题成功。
- `evaluation.failed`：测评任务终态失败。
- `canceled` 暂不回传。

**请求 Header**：
| Header | 必填 | 说明 |
|---|---|---|
| `Content-Type` | 是 | `application/json` |
| `X-Webhook-Event-Id` | 是 | 幂等键，格式如 `evaluation.done:456` |
| `X-Webhook-Signature` | 是 | `sha256=<hmac>`，使用 `FOLLOWUP_WEBHOOK_SECRET` 对原始 body 做 HMAC-SHA256 |

**Body 示例**：
```json
{
  "event": "evaluation.done",
  "event_id": "evaluation.done:456",
  "occurred_at": "2026-05-21T10:00:00Z",
  "user_id": "123",
  "evaluation_id": "456",
  "product_id": "789",
  "status": "done",
  "user": {
    "id": "123",
    "openid": "wx_openid_xxx",
    "nickname": "用户昵称"
  },
  "product": {
    "id": "789",
    "image_keys": ["tos/products/demo-image.png"]
  },
  "summary": {
    "total_personas": 5,
    "completed_personas": 5,
    "failed_personas": 0,
    "average_intent": 4.2,
    "overall_sentiment": "positive"
  },
  "answers": [
    {
      "persona_id": "101",
      "status": "done",
      "answers": [
        { "qid": "q1", "type": "scale_1_5", "answer": 5 }
      ],
      "overall_intent": 5,
      "sentiment": "positive",
      "summary_comment": "喜欢温和成分",
      "thinking_process": "判断过程",
      "token_input": 100,
      "token_output": 20,
      "cost_yuan": "0.1200",
      "error_message": null
    }
  ]
}
```

**投递规则**：
- 接收方返回任意 `2xx` 视为成功。
- 非 `2xx` 或网络错误会记录失败、增加 `attempt_count`，并设置指数退避的 `next_attempt_at`。
- 回传失败不影响测评状态、报告生成或用户可见结果。
- 接收方必须按 `X-Webhook-Event-Id` 做幂等处理。

**隐私边界**：
- 当前回传包含用户 `openid`/`nickname`、产品图片存储 key、角色原始答题内容、token/cost 统计。
- 仍禁止回传对话全文、prompt、内部 task id、数据库错误栈、API key、JWT、微信 code 或签名 URL。

---

## 1. Auth 鉴权

### 1.1 微信小程序登录
`POST /auth/wechat/login`

**请求**：
```json
{
  "code": "微信 wx.login() 返回的 code"
}
```

**响应 200**：
```json
{
  "token": "eyJhbGc...",
  "expires_in": 604800,
  "user": {
    "id": "123456",
    "nickname": "未设置",
    "avatar_url": null,
    "role_type": null,
    "credit_balance": 1000,
    "is_new_user": true
  }
}
```

**说明**：
- 首次登录 `is_new_user=true`，前端引导用户选择 `role_type`
- `role_type=null` 表示尚未选择身份；后续敏感接口会校验

**错误**：
- `400 WECHAT_CODE_INVALID` — code 无效或过期
- `503 WECHAT_API_FAILED` — 调微信接口失败

---

### 1.2 设置 / 修改身份
`PATCH /auth/profile`

**请求**：
```json
{
  "role_type": "manufacturer",     // manufacturer | channel
  "nickname": "可选"
}
```

**响应 200**：返回完整 user 对象
```json
{
  "id": "123456",
  "nickname": "...",
  "avatar_url": "...",
  "role_type": "manufacturer",
  "credit_balance": 1000
}
```

**错误**：
- `400 INVALID_ROLE_TYPE`

---

### 1.3 刷新 Token
`POST /auth/refresh`

**请求**：（无 body，依赖 Authorization header 中的旧 token）

**响应 200**：
```json
{ "token": "new_jwt", "expires_in": 604800 }
```

**错误**：
- `401 AUTH_TOKEN_INVALID`
- `401 AUTH_TOKEN_EXPIRED` — 已彻底过期，需重新 login

---

### 1.4 查询当前用户
`GET /auth/me`

**响应 200**：完整 user 对象（同 1.1）

---

## 2. Product 产品

### 2.1 上传产品图（获取预签名 URL）
`POST /products/upload-url`

**请求**：
```json
{
  "filename": "front.jpg",
  "mime_type": "image/jpeg",
  "size_bytes": 1234567
}
```

**响应 200**：
```json
{
  "upload_url": "https://tos-cn-beijing.volces.com/...?X-Tos-Signature=...",
  "method": "PUT",
  "headers": { "Content-Type": "image/jpeg" },
  "object_key": "products/2026/05/abcd.jpg",
  "expires_in": 600
}
```

**说明**：
- 客户端用 `PUT` 直传 TOS
- 上传完成后调 §2.2 时传 `object_key` 列表
- `expires_in` 单位秒

**错误**：
- `400 INVALID_FILE_TYPE` — 仅允许 jpg/png
- `400 FILE_TOO_LARGE` — > 5MB

---

### 2.2 创建产品（含多模态理解）
`POST /products`

**请求**：
```json
{
  "name": "焕颜修护面霜",          // 可选；空则由 AI 提取
  "description": "添加5%烟酰胺...", // 必填，10-500 字
  "image_object_keys": ["products/2026/05/abcd.jpg"],   // 1-5 张
  "brand": "可选",
  "price": 199.00,                  // 可选
  "target_channel": "ec"            // 可选，ec/offline/livestream
}
```

**响应 200**：
```json
{
  "id": "p_123",
  "name": "焕颜修护面霜",
  "description": "...",
  "image_urls": ["https://cdn.../abcd.jpg"],
  "category": "美妆",
  "sub_category": "面霜",
  "brand": null,
  "price": 199.00,
  "price_range": "200-400",
  "target_channel": "ec",
  "ai_summary": {
    "main_selling_points": ["5%烟酰胺", "温和不刺激", "适合敏感肌"],
    "key_ingredients": ["烟酰胺", "神经酰胺", "玻尿酸"],
    "suitable_skin_types": ["敏感肌", "干性肌"],
    "target_audience": "25-35 岁注重成分的都市女性",
    "competitive_position": "成分党中端面霜"
  },
  "status": "ready",
  "created_at": "2026-05-09T12:00:00Z"
}
```

**说明**：
- 同步返回（包含 AI 理解结果）；如理解失败 `status=failed` + `error_message`
- 理解失败时仍创建产品记录，可调 §2.4 重试

**错误**：
- `400 VALIDATION_ERROR` — 字段校验失败
- `400 IMAGE_NOT_UPLOADED` — object_key 在 TOS 不存在
- `503 AI_SERVICE_UNAVAILABLE`

---

### 2.3 查询产品详情
`GET /products/{product_id}`

**响应 200**：同 2.2 响应结构

---

### 2.4 重试产品理解
`POST /products/{product_id}/reanalyze`

**响应 200**：同 2.2 响应结构

---

### 2.5 列出我的产品
`GET /products?cursor=&limit=20`

**响应 200**：
```json
{
  "items": [{ /* 同 2.2 简化版 */ }],
  "next_cursor": "...",
  "has_more": true
}
```

---

## 3. Persona 角色

### 3.1 列出角色（系统库 + 我的私有）
`GET /personas?category=美妆&page=1&page_size=20&include_critical=true`

**Query 参数**：
| 参数 | 说明 |
|---|---|
| `category` | 品类过滤，可空 |
| `page`, `page_size` | offset 分页，page_size 默认 20、最大 100 |
| `include_critical` | 是否包含挑剔型角色，默认 true |
| `owner_scope` | `system` / `mine` / `all`，默认 `all` |
| `keyword` | 模糊搜索 name/persona_tag |

**响应 200**：
```json
{
  "items": [
    {
      "id": "persona_001",
      "name": "林雪",
      "avatar": "👩",
      "age": 28,
      "gender": "female",
      "city": "上海",
      "city_tier": 1,
      "occupation": "互联网产品经理",
      "income_monthly": 25000,
      "persona_tag": "成分党 / 理性消费",
      "categories": ["美妆", "护肤"],
      "is_critical": true,
      "is_system": true
    }
  ],
  "page": 1, "page_size": 20, "total": 100, "total_pages": 5
}
```

---

### 3.2 查询角色详情（完整人设）
`GET /personas/{persona_id}`

**响应 200**：
```json
{
  "id": "persona_001",
  "name": "林雪",
  "avatar": "👩",
  "age": 28, "gender": "female",
  "city": "上海", "city_tier": 1,
  "occupation": "互联网产品经理",
  "income_monthly": 25000,
  "ocean": { "o": 75, "c": 80, "e": 50, "a": 60, "n": 55 },
  "persona_tag": "成分党 / 理性消费",
  "categories": ["美妆", "护肤"],
  "is_critical": true,
  "is_system": true,
  "profile": {
    "bio": "在上海陆家嘴上班的产品经理，关注成分研究...",
    "shopping_habits": "...",
    "skincare_concerns": ["毛孔", "暗沉"],
    "brand_preferences": ["The Ordinary", "修丽可"],
    "price_sensitivity": "中等",
    "info_channels": ["小红书", "B站", "公众号"],
    "decision_style": "理性、看成分表",
    "pet_phrases": ["这成分浓度也太低了吧", "性价比怎么样"],
    "pain_points": ["不想被营销话术忽悠", "成分功效要看得见"],
    "lifestyle": "996，护肤步骤精简但讲究"
  },
  "version": 1,
  "created_at": "2026-05-09T12:00:00Z"
}
```

---

### 3.3 推荐角色（按产品自动匹配）
`GET /personas/recommend?product_id=p_123&count=20`

**响应 200**：返回与 3.1 相同结构的列表，按匹配度排序

**说明**：
- 推荐策略 MVP 阶段：按 `category` 匹配 + 强制包含 ≥ 20% 挑剔型角色，保证报告平衡

---

### 3.4 创建私有角色
`POST /personas`

**请求**：
```json
{
  "name": "张美丽",
  "avatar": "👩‍🦰",
  "age": 35,
  "gender": "female",
  "city": "成都",
  "occupation": "全职妈妈",
  "income_monthly": 8000,
  "persona_tag": "性价比党 / 天猫深度用户",
  "categories": ["美妆"],
  "is_critical": false,
  "profile": { /* 同 3.2 profile 结构 */ },
  "ocean": { "o": 50, "c": 60, "e": 70, "a": 65, "n": 50 }
}
```

**响应 200**：完整 persona 对象（含分配的 id）

**错误**：
- `400 VALIDATION_ERROR`
- `400 PERSONA_PROFILE_INVALID` — profile 缺关键字段

---

### 3.5 更新私有角色
`PATCH /personas/{persona_id}` — 仅 owner 可改

---

### 3.6 删除私有角色
`DELETE /personas/{persona_id}` — 软删

---

## 4. Survey 问卷

### 4.1 生成问卷
`POST /surveys/generate`

**请求**：
```json
{
  "product_id": "p_123",
  "evaluation_id": "e_456",        // 必填，关联到测评
  "extra_focus": "重点关注价格敏感度"  // 可选
}
```

**响应 200**：
```json
{
  "id": "s_789",
  "evaluation_id": "e_456",
  "product_id": "p_123",
  "version": 1,
  "generated_by": "ai",
  "questions": [
    {
      "id": "q1",
      "dim": "first_impression",
      "type": "scale_1_5",
      "question": "看到这款产品的第一印象，整体吸引力评分？",
      "options": null
    },
    {
      "id": "q2",
      "dim": "purchase_motivation",
      "type": "single",
      "question": "促使你购买这款面霜的最主要原因是？",
      "options": [
        "成分有效",
        "品牌信任",
        "性价比高",
        "朋友推荐",
        "其他"
      ]
    },
    {
      "id": "q15",
      "dim": "price_sensitivity",
      "type": "open",
      "question": "你能接受的最高价格是多少？为什么？",
      "options": null
    }
  ],
  "created_at": "..."
}
```

**问卷题型**：
- `single` — 单选，options 必填
- `multi` — 多选，options 必填
- `scale_1_5` — 1-5 分量表
- `open` — 开放题

---

### 4.2 查询问卷
`GET /surveys/{survey_id}`

---

### 4.3 编辑问卷（P1，MVP 可只占位）
`PUT /surveys/{survey_id}/questions`

**请求**：完整 questions 数组（覆盖式更新）
**响应 200**：更新后的问卷
**错误**：`400 SURVEY_LOCKED` — 测评已开始答题，禁止改

---

## 5. Evaluation 测评

### 5.1 创建测评
`POST /evaluations`

**请求**：
```json
{
  "product_id": "p_123"
}
```

**响应 200**：
```json
{
  "id": "e_456",
  "user_id": "u_001",
  "product_id": "p_123",
  "survey_id": null,
  "selected_persona_ids": [],
  "status": "pending",
  "progress": 0,
  "credit_cost": 0,
  "created_at": "..."
}
```

---

### 5.2 选择角色
`PUT /evaluations/{evaluation_id}/personas`

**请求**：
```json
{
  "persona_ids": ["persona_001", "persona_002", "..."]
}
```

**响应 200**：更新后的 evaluation
**错误**：
- `400 PERSONA_COUNT_INVALID` — 数量不在 5-100 之间
- `400 EVALUATION_NOT_EDITABLE` — 状态不允许修改

---

### 5.3 启动测评（异步答题）
`POST /evaluations/{evaluation_id}/run`

**前置条件**：survey 已生成、persona_ids 已选择

**响应 202**：
```json
{
  "id": "e_456",
  "status": "answering",
  "progress": 0,
  "estimated_seconds": 180,
  "task_id": "celery_task_xxx"
}
```

**错误**：
- `400 EVALUATION_NOT_READY` — 缺 survey 或 personas
- `400 EVALUATION_ALREADY_RUNNING`
- `402 INSUFFICIENT_CREDITS` — 积分不足（MVP 阶段不强制返回，仅日志）

---

### 5.4 查询测评状态（轮询用）
`GET /evaluations/{evaluation_id}`

**响应 200**：
```json
{
  "id": "e_456",
  "user_id": "u_001",
  "product_id": "p_123",
  "survey_id": "s_789",
  "selected_persona_ids": ["persona_001", "..."],
  "status": "answering",
  "progress": 45,
  "credit_cost": 0,
  "started_at": "...",
  "finished_at": null,
  "error_message": null,
  "stats": {
    "total_personas": 20,
    "completed_personas": 9,
    "failed_personas": 0
  }
}
```

**status 取值**：
- `pending` — 已创建，待生成问卷
- `generating_survey` — 生成问卷中
- `answering` — 角色答题中
- `generating_report` — 报告合成中
- `done` — 完成
- `failed` — 失败
- `canceled` — 已取消

**轮询建议**：客户端 2s 一次；状态变 `done` / `failed` / `canceled` 时停止。

---

### 5.5 取消测评
`POST /evaluations/{evaluation_id}/cancel`

**响应 200**：返回 evaluation（status=`canceled`）
**说明**：未完成部分扣减积分按比例返还（MVP 仅记录）

---

### 5.6 列出我的测评
`GET /evaluations?cursor=&limit=20&status=done`

**响应 200**：游标分页 items + next_cursor

---

### 5.7 查询单角色答题
`GET /evaluations/{evaluation_id}/answers/{persona_id}`

**响应 200**：
```json
{
  "evaluation_id": "e_456",
  "persona_id": "persona_001",
  "persona_snapshot": { /* 答题时的角色快照 */ },
  "overall_intent": 4,
  "sentiment": "positive",
  "summary_comment": "我会愿意继续了解，但还想先确认真实肤感和长期效果。",
  "answers": [
    {
      "qid": "q1",
      "type": "scale_1_5",
      "answer": 4,
      "reason": "包装看起来挺有质感的，但配色再清爽点会更好"
    },
    {
      "qid": "q2",
      "type": "single",
      "answer": "成分有效",
      "reason": "5% 烟酰胺浓度对我够用了"
    }
  ],
  "created_at": "..."
}
```

---

### 5.8 列出本次测评所有答题（聚合视图）
`GET /evaluations/{evaluation_id}/answers`

**响应 200**：数组，每项简化为
```json
[
  {
    "persona_id": "persona_001",
    "persona_name": "林雪",
    "persona_tag": "成分党",
    "overall_intent": 4,
    "sentiment": "positive",
    "summary_comment": "我会愿意继续了解，但还想先确认真实肤感和长期效果。"
  }
]
```

---

## 6. Report 报告

### 6.1 查询报告
`GET /reports/by-evaluation/{evaluation_id}`

**响应 200**：
```json
{
  "id": "r_321",
  "evaluation_id": "e_456",
  "summary": "整体反馈积极。最大卖点是成分（5%烟酰胺被多次提及），最大风险是价格...",
  "metrics": {
    "overall_intent": {
      "average": 3.8,
      "distribution": [
        {"score": 1, "count": 1},
        {"score": 2, "count": 2},
        {"score": 3, "count": 4},
        {"score": 4, "count": 8},
        {"score": 5, "count": 5}
      ],
      "nps": 25
    },
    "dimensions_radar": [
      {"dim": "first_impression", "score": 4.1},
      {"dim": "ingredient_recognition", "score": 4.3},
      {"dim": "price_acceptance", "score": 3.2},
      {"dim": "packaging", "score": 3.8},
      {"dim": "brand_trust", "score": 3.5},
      {"dim": "purchase_intent", "score": 3.8},
      {"dim": "repurchase_intent", "score": 3.6},
      {"dim": "recommendation_intent", "score": 3.7},
      {"dim": "competitive_advantage", "score": 3.4},
      {"dim": "improvement_room", "score": 3.5}
    ],
    "price_sensitivity": {
      "median_acceptable_price": 159,
      "distribution": [
        {"range": "0-100", "count": 2},
        {"range": "100-200", "count": 8},
        {"range": "200-400", "count": 7},
        {"range": "400+", "count": 3}
      ]
    },
    "segment_intent": [
      {"segment": "成分党", "count": 6, "avg_intent": 4.2},
      {"segment": "性价比党", "count": 7, "avg_intent": 3.5},
      {"segment": "品牌党", "count": 4, "avg_intent": 3.3},
      {"segment": "懒人党", "count": 3, "avg_intent": 4.0}
    ]
  },
  "top_pros": [
    {
      "title": "5% 烟酰胺浓度合理且温和",
      "support_count": 12,
      "quotes": [
        {"persona_id": "persona_001", "persona_name": "林雪", "quote": "这个浓度对敏感肌来说是友好的"},
        {"persona_id": "persona_007", "persona_name": "...", "quote": "..."}
      ]
    }
  ],
  "top_cons": [
    {
      "title": "价格高于同浓度竞品",
      "support_count": 9,
      "quotes": [...]
    }
  ],
  "persona_segments": {
    "most_positive": ["persona_001", "persona_004"],
    "most_negative": ["persona_009"],
    "highest_value": ["persona_001"]
  },
  "ai_disclaimer": "本报告由 AI 模拟生成，仅供决策参考",
  "generated_at": "...",
  "pdf_url": null,
  "share_token": null
}
```

---

### 6.2 生成 PDF（P1）
`POST /reports/{report_id}/export-pdf`

> 状态：P1 planned / not implemented。当前版本仅保留契约与字段，不提供实现。

**响应 200**：
```json
{ "pdf_url": "https://cdn.../report_xxx.pdf", "expires_in": 86400 }
```

---

### 6.3 创建分享链接（P1）
`POST /reports/{report_id}/share`

> 状态：P1 planned / not implemented。当前版本仅保留契约与字段，不提供实现。

**响应 200**：
```json
{ "share_url": "https://app.../share/xxxx", "share_token": "xxxx", "expires_at": "..." }
```

---

### 6.4 通过 share token 查看（公开）
`GET /reports/share/{share_token}` — 不需要鉴权

> 状态：P1 planned / not implemented。

---

## 7. Conversation 单角色对话

### 7.1 创建或获取对话
`POST /conversations`

**请求**：
```json
{
  "evaluation_id": "e_456",
  "persona_id": "persona_001"
}
```

**响应 200**：
```json
{
  "id": "c_999",
  "evaluation_id": "e_456",
  "persona_id": "persona_001",
  "persona_name": "林雪",
  "persona_avatar": "👩",
  "title": "关于焕颜修护面霜的深度访谈",
  "message_count": 0,
  "last_message_at": null,
  "created_at": "..."
}
```

**说明**：
- 同一 user + evaluation + persona 组合只允许一个 active 对话；重复创建返回已有对话
- title 由系统根据产品名生成

---

### 7.2 列出对话历史消息
`GET /conversations/{conversation_id}/messages?cursor=&limit=50`

**响应 200**：
```json
{
  "items": [
    {
      "id": "msg_001",
      "role": "assistant",
      "content": "你好，我是林雪。",
      "created_at": "..."
    },
    {
      "id": "msg_002",
      "role": "user",
      "content": "你为什么给这款只打了 4 分？",
      "created_at": "..."
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

---

### 7.3 发送消息（流式）
`POST /conversations/{conversation_id}/messages`

**请求**：
```json
{
  "content": "你为什么觉得包装可以更清爽？"
}
```

**响应**：流式 SSE，见 §0.6
```
data: {"event":"delta","content":"嗯"}

data: {"event":"delta","content":"，主要是"}

data: {"event":"delta","content":"现在的"}

data: {"event":"delta","content":"配色偏暖..."}

data: {"event":"meta","message_id":"msg_003","tokens":{"input":520,"output":89},"cost_yuan":0.0012}

data: {"event":"done"}
```

**错误事件**：
```
data: {"event":"error","code":"AI_SERVICE_TIMEOUT","message":"模型响应超时"}
```

---

### 7.4 列出我的对话
`GET /conversations?evaluation_id=&cursor=&limit=20`

---

### 7.5 删除对话
`DELETE /conversations/{conversation_id}`
**说明**：软删；同时异步清理对应 mem0 记忆

---

## 8. Credit 积分

### 8.1 查询积分余额
`GET /credits/balance`

> 状态：已实现。

**响应 200**：
```json
{ "balance": 990, "updated_at": "..." }
```

---

### 8.2 查询积分流水
`GET /credits/transactions?cursor=&limit=20`

> 状态：已实现。

**响应 200**：
```json
{
  "items": [
    {
      "id": "ct_001",
      "amount": -1,
      "balance_after": 999,
      "reason": "persona_answer",
      "ref_type": "evaluation",
      "ref_id": "e_456",
      "note": "角色 林雪 答题",
      "created_at": "..."
    }
  ],
  "next_cursor": "...",
  "has_more": true
}
```

**reason 取值**：`init` | `survey_gen` | `persona_answer` | `chat` | `recharge` | `refund` | `manual_adjust`

---

### 8.3 创建充值订单（供应商中立骨架）
`POST /credits/recharge`

> 当前仅实现订单与结算骨架，不包含真实微信支付/商户号/证书/对账能力。

Headers:

```http
Authorization: Bearer <jwt>
Idempotency-Key: optional-client-key
```

Request:

```json
{
  "amount_yuan": "9.90",
  "credits": 990,
  "provider": "manual"
}
```

Response:

```json
{
  "id": "123",
  "order_no": "rch_xxx",
  "provider": "manual",
  "amount_yuan": "9.90",
  "credits": 990,
  "status": "pending",
  "created_at": "2026-05-23T15:00:00Z",
  "paid_at": null
}
```

Rules:

- 创建订单不增加积分。
- 同一用户携带相同 `Idempotency-Key` 重复请求时，返回第一次创建的订单。
- 当前 `provider` 仅支持 `manual`。

### 8.4 充值回调（内部签名结算）
`POST /credits/recharge/callback`

Headers:

```http
X-Recharge-Signature: <hex hmac-sha256(raw_body, RECHARGE_CALLBACK_SECRET)>
```

Request:

```json
{
  "order_no": "rch_xxx",
  "provider_transaction_id": "provider-tx-001",
  "paid_at": "2026-05-23T15:01:00Z"
}
```

Response: same as `POST /credits/recharge`, with `status = "paid"`.

Rules:

- 签名错误返回 `INVALID_RECHARGE_SIGNATURE`。
- 未配置 `RECHARGE_CALLBACK_SECRET` 返回 `RECHARGE_SIGNATURE_NOT_CONFIGURED`。
- 重复回调或重复 `provider_transaction_id` 不重复加积分。
- 成功结算会写一条 `CreditTransaction`，`reason = "recharge"`，`ref_type = "credit_recharge_order"`。

---

## 9. Health 健康检查

### 9.1 存活探针
`GET /health/live`
**响应 200**：`{"status": "ok"}`

### 9.2 就绪探针
`GET /health/ready`
**响应 200**：
```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "qdrant": "ok",
    "ark": "ok"
  }
}
```
**响应 503**：任一组件不可用时

---

## 10. 错误码表

### 10.1 通用错误（HTTP 4xx/5xx）

| HTTP | code | 说明 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 请求参数校验失败，details 含字段级错误 |
| 400 | `INVALID_REQUEST` | 通用业务参数错 |
| 401 | `AUTH_REQUIRED` | 缺 token |
| 401 | `AUTH_TOKEN_INVALID` | token 无效 |
| 401 | `AUTH_TOKEN_EXPIRED` | token 过期 |
| 403 | `PERMISSION_DENIED` | 无权限访问该资源 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在（兜底） |
| 409 | `RESOURCE_CONFLICT` | 状态冲突 |
| 422 | `BUSINESS_RULE_VIOLATION` | 通过校验但违反业务规则 |
| 429 | `RATE_LIMITED` | 限流 |
| 500 | `INTERNAL_ERROR` | 服务端内部错误 |
| 503 | `SERVICE_UNAVAILABLE` | 依赖服务不可达 |
| 501 | `NOT_IMPLEMENTED` | 接口未实现 |

### 10.2 业务错误码

#### Auth
| code | HTTP | 说明 |
|---|---|---|
| `WECHAT_CODE_INVALID` | 400 | 微信 code 无效 |
| `WECHAT_API_FAILED` | 503 | 调微信失败 |
| `INVALID_ROLE_TYPE` | 400 | role_type 非法 |

#### Product
| code | HTTP | 说明 |
|---|---|---|
| `INVALID_FILE_TYPE` | 400 | 文件类型不允许 |
| `FILE_TOO_LARGE` | 400 | 文件 > 5MB |
| `IMAGE_NOT_UPLOADED` | 400 | TOS 找不到对应 object_key |
| `PRODUCT_NOT_FOUND` | 404 | |
| `PRODUCT_ANALYSIS_FAILED` | 500 | 多模态理解失败 |

#### Persona
| code | HTTP | 说明 |
|---|---|---|
| `PERSONA_NOT_FOUND` | 404 | |
| `PERSONA_PROFILE_INVALID` | 400 | profile 字段缺失 |
| `PERSONA_NOT_OWNED` | 403 | 非 owner 修改私有角色 |

#### Survey
| code | HTTP | 说明 |
|---|---|---|
| `SURVEY_NOT_FOUND` | 404 | |
| `SURVEY_LOCKED` | 409 | 测评已运行，禁止改问卷 |
| `SURVEY_GENERATION_FAILED` | 500 | |

#### Evaluation
| code | HTTP | 说明 |
|---|---|---|
| `EVALUATION_NOT_FOUND` | 404 | |
| `EVALUATION_NOT_READY` | 400 | 缺 survey 或 personas |
| `EVALUATION_ALREADY_RUNNING` | 409 | |
| `EVALUATION_NOT_EDITABLE` | 409 | 状态不允许修改 |
| `PERSONA_COUNT_INVALID` | 400 | 角色数不在 5-100 |
| `INSUFFICIENT_CREDITS` | 402 | 积分不足（MVP 不强制） |

#### Conversation
| code | HTTP | 说明 |
|---|---|---|
| `CONVERSATION_NOT_FOUND` | 404 | |
| `CONVERSATION_LIMIT_REACHED` | 429 | 单次对话超 20 轮 |
| `MESSAGE_TOO_LONG` | 400 | 单条 > 500 字 |

#### AI
| code | HTTP | 说明 |
|---|---|---|
| `AI_SERVICE_UNAVAILABLE` | 503 | 方舟不可达 |
| `AI_SERVICE_TIMEOUT` | 504 | 模型超时 |
| `AI_RATE_LIMITED` | 429 | 模型侧限流 |
| `AI_CONTENT_BLOCKED` | 422 | 内容审核拒绝 |
| `AI_RESPONSE_INVALID` | 502 | 模型返回无法解析 |

#### Credit
| code | HTTP | 说明 |
|---|---|---|
| `CREDIT_TRANSACTION_FAILED` | 500 | 积分扣减失败 |

---

## 11. 接口清单速查（按模块）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/auth/wechat/login` | ❌ | 小程序登录 |
| PATCH | `/auth/profile` | ✅ | 设置/改身份 |
| POST | `/auth/refresh` | ✅ | 刷新 token |
| GET | `/auth/me` | ✅ | 当前用户 |
| POST | `/products/upload-url` | ✅ | 获取上传 URL |
| POST | `/products` | ✅ | 创建产品 |
| GET | `/products/{id}` | ✅ | 产品详情 |
| POST | `/products/{id}/reanalyze` | ✅ | 重试理解 |
| GET | `/products` | ✅ | 我的产品列表 |
| GET | `/personas` | ✅ | 角色列表 |
| GET | `/personas/{id}` | ✅ | 角色详情 |
| GET | `/personas/recommend` | ✅ | 推荐角色 |
| POST | `/personas` | ✅ | 创建私有角色 |
| PATCH | `/personas/{id}` | ✅ | 改私有角色 |
| DELETE | `/personas/{id}` | ✅ | 删私有角色 |
| POST | `/surveys/generate` | ✅ | 生成问卷 |
| GET | `/surveys/{id}` | ✅ | 问卷详情 |
| PUT | `/surveys/{id}/questions` | ✅ | 改问卷（P1） |
| POST | `/evaluations` | ✅ | 创建测评 |
| PUT | `/evaluations/{id}/personas` | ✅ | 选角色 |
| POST | `/evaluations/{id}/run` | ✅ | 启动答题 |
| GET | `/evaluations/{id}` | ✅ | 测评状态 |
| POST | `/evaluations/{id}/cancel` | ✅ | 取消 |
| GET | `/evaluations` | ✅ | 我的测评列表 |
| GET | `/evaluations/{id}/answers/{pid}` | ✅ | 单角色答题 |
| GET | `/evaluations/{id}/answers` | ✅ | 答题汇总 |
| GET | `/reports/by-evaluation/{id}` | ✅ | 报告 |
| POST | `/reports/{id}/export-pdf` | ✅ | 导 PDF（P1 planned，当前未实现） |
| POST | `/reports/{id}/share` | ✅ | 分享链接（P1 planned，当前未实现） |
| GET | `/reports/share/{token}` | ❌ | 公开查看（P1 planned，当前未实现） |
| POST | `/conversations` | ✅ | 创建对话 |
| GET | `/conversations/{id}/messages` | ✅ | 历史消息 |
| POST | `/conversations/{id}/messages` | ✅ | 发消息（流式） |
| GET | `/conversations` | ✅ | 我的对话列表 |
| DELETE | `/conversations/{id}` | ✅ | 删对话 |
| GET | `/credits/balance` | ✅ | 积分余额（已实现） |
| GET | `/credits/transactions` | ✅ | 积分流水（已实现） |
| POST | `/credits/recharge` | ✅ | 创建充值订单骨架 |
| POST | `/credits/recharge/callback` | ✅ | 内部签名结算骨架 |
| GET | `/health/live` | ❌ | 存活（已实现） |
| GET | `/health/ready` | ❌ | 就绪（已实现） |

---

## 12. 版本演进策略

- 当前版本：`v1`，路径前缀 `/api/v1`
- 兼容性：v1 内不允许破坏性变更（删字段、改语义）；只允许新增可选字段、新增端点
- 破坏性变更：必须升 `/api/v2`；v1 至少保留 6 个月
- MVP-Lite 当前部分能力使用 mock 实现（如微信登录、上传 URL、产品理解、问卷/答题/对话 AI）。后续替换为真实微信、真实 TOS、真实 AI、异步任务或内容审核时，必须保持本契约已定义的成功响应字段、错误响应结构、ID 字符串格式和状态枚举兼容；如确需新增信息，只能新增可选字段，不得删除或重命名既有字段。
- 前端不得依赖 mock 文案的具体内容，应依赖本契约定义的字段结构、枚举值、状态流转和 SSE 事件格式。

---

## 13. 待定项

- [ ] 异步任务进度推送：MVP 用轮询；M2 评估是否上 WebSocket（小程序原生支持）
- [ ] 角色头像生成：MVP 用 emoji；M2 接入豆包文生图
- [ ] 报告 PDF 生成方案：weasyprint vs 服务端 puppeteer，M2 决定
- [ ] OpenAPI YAML：在 FastAPI 自动生成基础上，提交一份 frozen 版本到 repo（每次 release 更新）
