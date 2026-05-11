# 前端交接文档

当前后端是 **MVP-Lite Backend v0.1**，用于前端主流程页面联调，不是生产版。前端现在可以开始开发并联调主流程页面：登录、产品、角色、问卷、测评、报告、单角色对话。

## 一、后端启动方式

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

服务默认监听 `http://127.0.0.1:8000`。

本地默认配置：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/duoduo
REDIS_URL=redis://localhost:6380/0
AI_PROVIDER=mock
```

说明：

1. PostgreSQL 使用 Docker Compose 的宿主机端口 `5433`，避免占用本机已有 `5432`。
2. Redis 使用 Docker Compose 的宿主机端口 `6380`，避免占用本机常见 `6379`。
3. Docker profile 内部 API 使用 `redis://redis:6379/0`，本机 uvicorn 使用 `redis://localhost:6380/0`。
4. `alembic/env.py` 从 `.env` / 环境变量读取 `DATABASE_URL`，不要依赖 `alembic.ini` 修改端口。
5. 前端联调前必须先执行 `uv run python scripts/seed_personas.py`，否则 `/personas/recommend` 可能为空。

可选本地检查：

```bash
uv run python scripts/dev_check.py
```

如果 API 未启动，`dev_check.py` 会跳过 HTTP health 并提示启动 API。

## 二、Swagger / OpenAPI 地址

| 用途 | 地址 |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |
| 导出本地 JSON | `uv run python scripts/export_openapi.py` → `docs/openapi.v0.1.json` |

`docs/openapi.v0.1.json` 是当前冻结版 OpenAPI。接口实现状态以 `docs/API_STATUS.md` 为准。

人工 E2E 联调脚本：

```bash
uv run python scripts/e2e_mock_flow.py
```

成功时会输出 `E2E_MOCK_FLOW_OK`。

## 三、前端联调基础规则

1. **接口前缀**：所有业务接口 `/api/v1`
2. **鉴权**：除 `POST /api/v1/auth/wechat/login` 和 `GET /health*` 外，都需要 `Authorization: Bearer <token>` 请求头
3. **成功响应**：直接返回数据对象，不包 `data` 字段
4. **失败响应**：统一格式
   ```json
   {
     "code": "ERROR_CODE",
     "message": "人类可读消息",
     "details": {},
     "request_id": "uuid",
     "timestamp": "2026-05-11T01:00:00Z"
   }
   ```
5. **ID 格式**：所有 id 都是数字字符串（如 `"12345"`）
6. **时间格式**：ISO 8601（如 `"2026-05-11T01:00:00Z"`）
7. **mock 文案**：前端不要依赖 mock 文案内容，只依赖字段结构、枚举、状态流转和 SSE 事件类型。

## 四、推荐联调主流程

### 4.1 登录

```
POST /api/v1/auth/wechat/login
```

请求：
```json
{"code": "wx_auth_code_from_wechat"}
```

响应关键字段：
```json
{
  "token": "eyJhbGci...",
  "user": {
    "id": "12345",
    "role_type": null,
    "nickname": null
  }
}
```

前端保存：`token`、`user.id`

### 4.2 设置身份

```
PATCH /api/v1/auth/profile
```

请求：
```json
{
  "role_type": "manufacturer",
  "nickname": "品牌方用户"
}
```

响应关键字段：
```json
{
  "id": "12345",
  "role_type": "manufacturer",
  "nickname": "品牌方用户"
}
```

前端保存：更新本地用户信息

### 4.3 获取上传 URL

```
POST /api/v1/products/upload-url
```

请求：
```json
{
  "filename": "product_front.jpg",
  "mime_type": "image/jpeg",
  "size_bytes": 204800
}
```

响应关键字段：
```json
{
  "upload_url": "https://tos-bucket.../signed-url",
  "object_key": "products/2026/05/abc123_product_front.jpg"
}
```

前端保存：`object_key`（用于创建产品）

> 当前 mock 模式下 upload_url 不可用，前端可跳过实际上传。

### 4.4 创建产品

```
POST /api/v1/products
```

请求：
```json
{
  "name": "焕颜修护面霜",
  "description": "添加烟酰胺和神经酰胺，主打温和修护和提亮。",
  "image_object_keys": ["products/2026/05/abc123_front.jpg"]
}
```

响应关键字段：
```json
{
  "id": "100",
  "name": "焕颜修护面霜",
  "status": "ready"
}
```

前端保存：`product.id`

### 4.5 创建测评

```
POST /api/v1/evaluations
```

请求：
```json
{"product_id": "100"}
```

响应关键字段：
```json
{
  "id": "200",
  "product_id": "100",
  "status": "pending",
  "survey_id": null
}
```

前端保存：`evaluation.id`

### 4.6 生成问卷

```
POST /api/v1/surveys/generate
```

请求：
```json
{
  "product_id": "100",
  "evaluation_id": "200",
  "extra_focus": "重点关注价格敏感度"
}
```

响应关键字段：
```json
{
  "id": "300",
  "questions": [
    {
      "id": "q01",
      "dim": "first_impression",
      "type": "scale_1_5",
      "question": "整体吸引力？",
      "options": null
    }
  ]
}
```

前端保存：`survey.id`，可展示/编辑 questions

### 4.7 推荐角色

```
GET /api/v1/personas/recommend?product_id=100&count=20
```

响应关键字段：
```json
{
  "items": [
    {
      "id": "50",
      "name": "林雪",
      "persona_tag": "成分党",
      "age": 28,
      "city": "上海"
    }
  ]
}
```

前端保存：用户勾选的 persona id 列表

如果返回 `items: []`，通常是还没有导入系统角色。请后端先执行：

```bash
uv run python scripts/seed_personas.py
```

### 4.8 选择角色

```
PUT /api/v1/evaluations/{evaluation_id}/personas
```

请求：
```json
{"persona_ids": ["50", "51", "52"]}
```

### 4.9 启动测评

```
POST /api/v1/evaluations/{evaluation_id}/run
```

响应关键字段：
```json
{
  "id": "200",
  "status": "done",
  "progress": 100
}
```

> mock 模式下同步完成。ark 模式下仍为同步，未来可改为异步。

### 4.10 轮询 evaluation 状态

```
GET /api/v1/evaluations/{evaluation_id}
```

前端轮询建议：POST /run 后 2 秒开始轮询，间隔 2 秒。当 `status` 为 `done`、`failed` 或 `canceled` 时停止。

### 4.11 查询 answers

```
GET /api/v1/evaluations/{evaluation_id}/answers
```

响应关键字段：
```json
{
  "items": [
    {
      "persona_id": "50",
      "overall_intent": 4,
      "sentiment": "positive",
      "answers": [...]
    }
  ]
}
```

### 4.12 查询 report

```
GET /api/v1/reports/by-evaluation/{evaluation_id}
```

响应关键字段：
```json
{
  "id": "400",
  "summary": "...",
  "metrics": {
    "overall_intent": {
      "average": 4.2,
      "distribution": [{"score": 5, "count": 3, "pct": 0.6}],
      "nps": 60
    },
    "dimensions_radar": [{"dim": "first_impression", "score": 4.0}],
    "price_sensitivity": {"distribution": [...], "median_acceptable_price": 159},
    "segment_intent": [{"segment": "成分党", "count": 5, "avg_intent": 4.2}]
  },
  "top_pros": [{"title": "...", "support_count": 5, "quotes": [...]}],
  "top_cons": [{"title": "...", "support_count": 3, "quotes": [...]}],
  "ai_disclaimer": "...",
  "pdf_url": null,
  "share_token": null
}
```

前端保存：`report.id`

### 4.13 创建 conversation

```
POST /api/v1/conversations
```

请求：
```json
{
  "evaluation_id": "200",
  "persona_id": "50"
}
```

响应关键字段：
```json
{
  "id": "500",
  "persona_name": "林雪",
  "title": "关于焕颜修护面霜的深度访谈",
  "message_count": 0
}
```

前端保存：`conversation.id`

### 4.14 流式发送消息

```
POST /api/v1/conversations/{conversation_id}/messages
Content-Type: application/json

{"content": "你好，请问你对这款面霜怎么看？"}
```

响应：`text/event-stream`

## 五、小程序流式处理说明

微信小程序使用 `wx.request` 的 `enableChunked` 模式接收 SSE：

```javascript
const task = wx.request({
  url: `${BASE}/api/v1/conversations/${conversationId}/messages`,
  method: 'POST',
  header: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  data: { content: userMessage },
  enableChunked: true,
  success() {}
});

let buffer = '';
task.onChunkReceived(function(res) {
  // res.data 是 ArrayBuffer
  const text = new TextDecoder('utf-8').decode(res.data);
  buffer += text;

  // 按 \n\n 切分事件
  const parts = buffer.split('\n\n');
  buffer = parts.pop(); // 最后一个可能不完整

  for (const part of parts) {
    if (!part.startsWith('data: ')) continue;
    const json = JSON.parse(part.slice(6));

    switch (json.event) {
      case 'delta':
        // 拼接文本到聊天气泡
        appendText(json.content);
        break;
      case 'meta':
        // 保存 message_id 和 tokens
        saveMessageMeta(json.message_id, json.tokens);
        break;
      case 'done':
        // 流结束，更新 UI 状态
        finishStream();
        break;
      case 'error':
        // 展示错误：json.code + json.message
        showError(json.code, json.message);
        break;
    }
  }
});
```

流式调试建议：

1. 先在 Swagger 或 `scripts/e2e_mock_flow.py` 确认 conversation 能创建。
2. 调试时打印原始 chunk 文本，确认是否按 `\n\n` 分隔。
3. 每条事件必须去掉 `data: ` 前缀后再 `JSON.parse`。
4. 遇到 `event=error` 时展示 `code/message`，不要继续等待后续 delta。
5. mock 模式下回复较短；`AI_PROVIDER=ark` 时才会走真实豆包流式。
6. 小程序端要处理 chunk 粘包/拆包，不能假设一次 chunk 就是一条完整 `data:` 事件。
7. `done` 后关闭 loading；`meta` 可能在 `done` 前最后到达，用于保存 `message_id/tokens`。

## 六、轮询建议

| 场景 | 方式 |
|---|---|
| POST /evaluations/{id}/run 后 | 2 秒后开始轮询 GET /evaluations/{id} |
| 轮询间隔 | 2 秒 |
| 停止条件 | status = done / failed / canceled |

## 七、当前 mock / 真实状态说明

| 模块 | 默认状态 | 说明 |
|---|---|---|
| 微信登录 | mock | 任意 code 均可登录，不验证微信 |
| TOS 上传 | mock | 返回 mock URL，不可实际上传 |
| 产品理解 | mock | 创建后直接 ready，无 AI 分析 |
| Survey 生成 | mock / ai_optional | 默认用种子模板，设 AI_PROVIDER=ark 可调 AI 生成 |
| Persona Answer | mock / ai_optional | 默认 mock 答卷，设 AI_PROVIDER=ark 可调 AI |
| Conversation | mock / ai_optional | 默认 mock 流式回复，设 AI_PROVIDER=ark 可调 AI 对话 |
| Report | done | metrics 真实聚合，文案规则生成，可后续 AI 化 |
| PDF 导出 | p1_not_implemented | pdf_url 字段保留，逻辑未实现 |
| 分享链接 | p1_not_implemented | share_token 字段保留，逻辑未实现 |
| 充值 | p1_not_implemented | — |

## 八、前端暂时不要做的入口

以下功能后端未实现，前端不要展示入口：

1. PDF 导出按钮
2. 分享链接按钮
3. 充值/购买积分
4. 多产品对比
5. 团队协作/邀请成员
6. 真实支付流程

## 九、详细 API 状态表

请参考 `docs/API_STATUS.md`。

## 十、常见错误

| 错误 | 常见原因 | 处理建议 |
|---|---|---|
| 401 AUTH_REQUIRED / AUTH_TOKEN_INVALID | 没有带 `Authorization: Bearer <token>` 或 token 错误 | 登录后保存 token，除 login/health 外每个请求都带 Bearer |
| PRODUCT_NOT_FOUND | 产品不存在，或不是当前 token 用户创建的产品 | 确认 product_id 来自当前登录用户 |
| EVALUATION_NOT_READY | 未生成问卷、未选择角色，或 conversation 对应角色没有 answer | 按主流程先生成 survey、选择 persona、run evaluation |
| SURVEY_LOCKED | 测评已经开始或完成后再编辑问卷 | 编辑问卷必须在 run 之前完成 |
| /personas/recommend 返回空 | 未导入系统角色 seed | 执行 `uv run python scripts/seed_personas.py` |
| 连接数据库失败 | PostgreSQL 未启动或 `.env` 端口不对 | 执行 `docker compose up -d postgres`，确认 `DATABASE_URL` 使用 `localhost:5433` |
| Redis 端口冲突 | 本机已有服务占用 6379 | 项目默认使用宿主机 `6380`，确认 `REDIS_URL=redis://localhost:6380/0` |
