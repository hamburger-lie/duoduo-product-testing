# 产品接口表

> 来源：`API_CONTRACT.md` 第 2 章 Product 产品、`docs/API_STATUS.md` Product 状态、`backend/app/schemas/product.py`。
> 当前服务统一前缀：`/api/v1`。`API_CONTRACT.md` 中的路径未带此前缀，实际联调用下表路径。

## 1. 接口清单

| 模块 | 方法 | 实际路径 | 契约路径 | 鉴权 | 当前状态 | 说明 |
|---|---|---|---|---|---|---|
| Product | POST | `/api/v1/products/upload-url` | `/products/upload-url` | 是 | mock | 获取产品图上传 URL；当前返回 mock TOS 签名 URL 和 mock `object_key` |
| Product | POST | `/api/v1/products` | `/products` | 是 | ai_optional | 创建产品并执行产品理解；默认 mock，可配置 deepseek/vision client 生成 `ai_summary` |
| Product | GET | `/api/v1/products` | `/products` | 是 | done | 分页列出当前用户产品，游标分页 |
| Product | GET | `/api/v1/products/{product_id}` | `/products/{product_id}` | 是 | done | 查询当前用户拥有的单个产品详情 |
| Product | POST | `/api/v1/products/{product_id}/reanalyze` | `/products/{product_id}/reanalyze` | 是 | ai_optional | 重新触发产品理解；默认 mock，可配置 deepseek/vision client 重新分析 |

## 2. 上传产品图

### `POST /api/v1/products/upload-url`

| 项 | 内容 |
|---|---|
| 用途 | 获取产品图直传 URL |
| Content-Type | `application/json` |
| 鉴权 | Bearer JWT |
| 成功响应 | `200 ProductUploadUrlResponse` |

### 请求字段

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `filename` | string | 是 | 1-255 字符 | 原始文件名 |
| `mime_type` | string | 是 | 仅允许 jpg/png 对应类型 | 文件 MIME 类型 |
| `size_bytes` | integer | 是 | `> 0`，业务限制不超过 5MB | 文件大小，单位字节 |

### 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `upload_url` | string | 客户端用于 `PUT` 直传的 URL |
| `method` | string | 上传方法，当前为 `PUT` |
| `headers` | object | 上传时需要携带的 header，例如 `Content-Type` |
| `object_key` | string | 上传完成后创建产品时传入的对象 key |
| `expires_in` | integer | URL 有效期，单位秒 |

### 主要错误

| HTTP | code | 说明 |
|---|---|---|
| 400 | `INVALID_FILE_TYPE` | 文件类型不允许，仅允许 jpg/png |
| 400 | `FILE_TOO_LARGE` | 文件超过 5MB |

## 3. 创建产品

### `POST /api/v1/products`

| 项 | 内容 |
|---|---|
| 用途 | 创建产品，并同步返回产品理解结果 |
| Content-Type | `application/json` |
| 鉴权 | Bearer JWT |
| 成功响应 | `200 ProductResponse` |

### 请求字段

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `name` | string/null | 否 | 最多 128 字符 | 产品名；为空时可由 AI 提取或服务端兜底 |
| `description` | string | 是 | 10-500 字符 | 产品描述 |
| `image_object_keys` | string[] | 条件必填 | 最多 5 张 | 来自上传 URL 流程的对象 key；与 `image_base64_list` 至少提供一种 |
| `image_base64_list` | string[]/null | 条件必填 | 最多 5 张；单项小于 8MB | 直接提交 base64、data URL 或 HTTPS 图片 URL；与 `image_object_keys` 至少提供一种 |
| `brand` | string/null | 否 | 最多 64 字符 | 品牌 |
| `price` | number/null | 否 | Decimal | 价格 |
| `target_channel` | string/null | 否 | 最多 32 字符 | 目标渠道，例如 `ec`、`offline`、`livestream` |

### 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 产品 ID，JSON 中必须按字符串传输 |
| `name` | string | 产品名 |
| `description` | string | 产品描述 |
| `image_urls` | string[] | 产品图片访问 URL |
| `category` | string/null | 一级品类 |
| `sub_category` | string/null | 二级品类 |
| `brand` | string/null | 品牌 |
| `price` | number/null | 价格 |
| `price_range` | string/null | 价格区间 |
| `target_channel` | string/null | 目标渠道 |
| `ai_summary` | object | 产品理解结构化结果 |
| `status` | string | 产品理解状态；契约示例包含 `ready`，失败时可为 `failed` 并由服务端错误信息描述 |
| `created_at` | string | ISO 8601 创建时间 |

### `ai_summary` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `main_selling_points` | string[] | 核心卖点 |
| `key_ingredients` | string[] | 关键成分或功能点 |
| `suitable_skin_types` | string[] | 适合肤质 |
| `target_audience` | string | 目标人群 |
| `competitive_position` | string | 竞争定位 |
| `category` | string/null | AI 识别品类 |
| `sub_category` | string/null | AI 识别子品类 |
| `brand` | string/null | AI 识别品牌 |
| `price` | number/null | AI 识别或归一化价格 |
| `price_range` | string/null | AI 识别价格带 |
| `target_channel` | string/null | AI 识别渠道 |
| `claims_detected` | string[] | 识别到的功效或营销声明 |
| `risk_or_uncertainty_points` | string[] | 风险或不确定点 |
| `usage_scenarios` | string[] | 使用场景 |
| `questionnaire_focus` | string[] | 后续问卷重点 |
| `confidence` | number/null | 产品理解置信度 |

### 主要错误

| HTTP | code | 说明 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 字段校验失败 |
| 400 | `IMAGE_NOT_UPLOADED` | `object_key` 在 TOS 不存在 |
| 500 | `PRODUCT_ANALYSIS_FAILED` | 多模态理解失败 |
| 503 | `AI_SERVICE_UNAVAILABLE` | AI 服务不可用 |

## 4. 查询产品详情

### `GET /api/v1/products/{product_id}`

| 项 | 内容 |
|---|---|
| 用途 | 查询当前用户拥有的单个产品 |
| 鉴权 | Bearer JWT |
| Path 参数 | `product_id`：产品 ID |
| 成功响应 | `200 ProductResponse`，结构同创建产品响应 |

### 主要错误

| HTTP | code | 说明 |
|---|---|---|
| 404 | `PRODUCT_NOT_FOUND` | 产品不存在，或不属于当前用户 |

## 5. 重试产品理解

### `POST /api/v1/products/{product_id}/reanalyze`

| 项 | 内容 |
|---|---|
| 用途 | 对已有产品重新执行产品理解 |
| 鉴权 | Bearer JWT |
| Path 参数 | `product_id`：产品 ID |
| 成功响应 | `200 ProductResponse`，结构同创建产品响应 |

### 主要错误

| HTTP | code | 说明 |
|---|---|---|
| 404 | `PRODUCT_NOT_FOUND` | 产品不存在，或不属于当前用户 |
| 500 | `PRODUCT_ANALYSIS_FAILED` | 多模态理解失败 |
| 503 | `AI_SERVICE_UNAVAILABLE` | AI 服务不可用 |

## 6. 产品列表

### `GET /api/v1/products?cursor=&limit=20`

| 项 | 内容 |
|---|---|
| 用途 | 分页列出当前用户产品 |
| 鉴权 | Bearer JWT |
| 成功响应 | `200 ProductListResponse` |

### Query 参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cursor` | string/null | 否 | 空 | 游标；为空时返回第一页 |
| `limit` | integer | 否 | 20 | 每页条数 |

### 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `items` | ProductResponse[] | 产品列表，元素结构同创建产品响应 |
| `next_cursor` | string/null | 下一页游标；无下一页时为空 |
| `has_more` | boolean | 是否还有下一页 |

## 7. 统一错误响应

所有错误响应必须使用统一结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | string | 业务错误码 |
| `message` | string | 面向客户端的错误描述 |
| `details` | object/null | 结构化错误详情 |
| `request_id` | string | 请求 ID |
| `timestamp` | string | 错误发生时间 |

## 8. 联调备注

| 项 | 说明 |
|---|---|
| ID 格式 | 所有 ID 在 JSON 中按字符串传输，避免 JS 精度丢失 |
| 上传流程 | 先调 `POST /api/v1/products/upload-url`，客户端上传成功后，再把 `object_key` 放入 `POST /api/v1/products` |
| 图片限制 | 产品图 1-5 张；仅 jpg/png；单张不超过 5MB |
| 当前实现 | 上传 URL 当前为 mock；产品理解默认 mock，配置真实 AI 后可生成真实 `ai_summary` |
| 内容提示 | 报告和对话页面需显式标注：`AI 生成内容仅供参考` |
