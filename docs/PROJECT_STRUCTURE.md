# 工程前后端分布文档

本文用于快速判断 Soul 工程中前端、后端、接口契约、运行配置和本地资产的分布。当前联调默认端口统一为 `8000`。

## 一、总体结构

| 路径 | 分类 | 说明 |
|---|---|---|
| `miniprogram/` | 前端主工程 | 微信小程序代码，使用 TypeScript、WXML、WXSS |
| `backend/backend/` | 后端主工程 | FastAPI 应用、数据库迁移、测试、Docker 配置 |
| `backend/docs/` | 后端文档 | API 状态、前端交接、交付清单、Prompt 与种子资料 |
| `docs/` | 项目文档 | 跨端需求、设计记录、当前工程总览 |
| `mockup/` | 原型资料 | HTML 原型和页面截图 |
| `tmp_pdf_compare/` | 临时对比资料 | PDF 与图片对比缓存 |
| 根目录 `app.ts/app.json/app.wxss` | 旧/镜像入口 | 根目录保留的小程序入口文件，当前主前端以 `miniprogram/` 为准 |

## 二、前端分布

前端主目录是 `miniprogram/`。

| 路径 | 分类 | 说明 |
|---|---|---|
| `miniprogram/app.json` | 小程序入口配置 | 页面列表、窗口配置、tabBar、懒加载策略 |
| `miniprogram/pages/` | 页面 | 首页、创建、历史、我的、聊天、报告、产品、角色等页面 |
| `miniprogram/components/` | 组件 | 头像、气泡、进度条、研究卡片、chip 等复用组件 |
| `miniprogram/services/` | API 与网络层 | 后端接口封装、endpoint 常量、SSE 流式请求 |
| `miniprogram/types/` | 类型定义 | API 响应与领域 ViewModel 类型 |
| `miniprogram/mocks/` | Mock 数据 | 本地 mock 人设、测评、积分、对话数据 |
| `miniprogram/assets/` | 静态资源 | tab 图标、报告图标、人设头像、hero 图 |
| `miniprogram/styles/` | 样式基础 | token 和 reset |

关键前端文件：

- `miniprogram/services/http.ts`：`wx.request` 封装，当前 `BASE_URL = 'http://127.0.0.1:8000'`
- `miniprogram/services/api.ts`：页面统一调用的 API 适配层，当前 `USE_MOCK = false`
- `miniprogram/services/endpoints.ts`：所有 `/api/v1` 业务路径常量
- `miniprogram/services/stream.ts`：SSE-like over HTTP chunked 流式请求

## 三、后端分布

后端主目录是 `backend/backend/`。

| 路径 | 分类 | 说明 |
|---|---|---|
| `backend/backend/app/main.py` | FastAPI 入口 | 中间件、异常处理、路由注册、静态目录挂载 |
| `backend/backend/app/routers/` | 路由层 | Auth、Product、Persona、Survey、Evaluation、Report、Conversation 等 API |
| `backend/backend/app/services/` | 业务层 | 各模块业务编排 |
| `backend/backend/app/schemas/` | Schema | Pydantic 请求/响应模型 |
| `backend/backend/app/db/models/` | 数据模型 | SQLAlchemy ORM 模型 |
| `backend/backend/app/db/repositories/` | 数据访问层 | 数据库 CRUD 与查询封装 |
| `backend/backend/app/ai/` | AI 边界 | Prompt、AI 客户端、适配器、流式生成、内容安全 |
| `backend/backend/app/tasks/` | 异步任务 | Celery、evaluation task、watchdog、DLQ |
| `backend/backend/app/storage/` | 存储层 | 本地/mock/TOS 上传适配 |
| `backend/backend/tests/` | 测试 | 单元、API、集成、安全、性能、E2E 测试 |
| `backend/backend/docker-compose.yml` | 本地依赖 | PostgreSQL、Redis、Qdrant、可选 API/worker profile |
| `backend/backend/Dockerfile` | 后端镜像 | API 容器启动端口为 `8000` |

已注册的主要后端路由：

| 模块 | Prefix | 说明 |
|---|---|---|
| Auth | `/api/v1/auth` | 微信登录、profile、头像、refresh、logout、me |
| Product | `/api/v1/products` | 产品创建、列表、详情、上传 URL、图片提取、重新分析 |
| Persona | `/api/v1/personas` | 人设列表、推荐、自定义 CRUD |
| Survey | `/api/v1/surveys` | 问卷生成、流式生成、详情、题目更新 |
| Evaluation | `/api/v1/evaluations` | 测评创建、选角色、运行、答案、深度分析、取消、删除 |
| Report | `/api/v1/reports` | 报告、商业报告、PDF 列表与删除 |
| Whitepaper | `/api/v1/whitepapers` | 白皮书生成与查询 |
| Conversation | `/api/v1/conversations` | 对话创建、列表、消息、流式聊天、删除 |
| Credit | `/api/v1/credits` | 余额、流水、充值占位 |
| History | `/api/v1/history` | 历史记录 |
| Health | `/health` `/health/live` `/health/ready` | 健康检查 |

## 四、前后端连接关系

前端统一通过 `miniprogram/services/api.ts` 调用后端，路径来自 `miniprogram/services/endpoints.ts`。

```text
小程序页面
  -> miniprogram/services/api.ts
  -> miniprogram/services/http.ts 或 stream.ts
  -> http://127.0.0.1:8000/api/v1/...
  -> backend/backend/app/routers/*.py
  -> services / repositories / ai / storage
```

接口契约与状态文档：

| 文件 | 用途 |
|---|---|
| `backend/API_CONTRACT.md` | 前后端接口唯一契约 |
| `backend/docs/API_STATUS.md` | 接口实现状态 |
| `backend/docs/FRONTEND_HANDOFF.md` | 前端联调说明 |
| `backend/docs/openapi.v0.1.json` | 冻结版 OpenAPI |
| `backend/docs/API_ENDPOINTS.md` | API 端点说明 |

## 五、端口与启动

当前 API 端口统一为 `8000`。

后端本机启动：

```powershell
cd backend\backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

使用脚本启动：

```powershell
cd backend
.\start_dev.bat
```

前端本地请求地址：

```text
http://127.0.0.1:8000
```

Swagger / OpenAPI：

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/openapi.json
```

Docker Compose 中 API 映射：

```text
8000:8000
```

## 六、本地资产与上传注意事项

仓库当前工作区包含本地运行资产和生成缓存。上传 GitHub 时应优先提交业务代码与文档，不建议提交以下内容：

| 分类 | 示例 | 说明 |
|---|---|---|
| 环境变量 | `.env` `backend/backend/.env` | 可能包含本地配置或密钥 |
| 虚拟环境 | `backend/backend/.venv/` | 本地依赖目录，体积大且不可移植 |
| Python 缓存 | `__pycache__/` `.mypy_cache/` `.pytest_cache/` | 可重新生成 |
| Node 依赖 | `node_modules/` `miniprogram/node_modules/` | 可通过 lockfile 重新安装 |
| 日志 | `*.log` | 本地运行输出 |
| 微信私有配置 | `project.private.config.json` | 开发者本机配置 |
| 临时对比资料 | `tmp_pdf_compare/` | 仅用于本地视觉对比 |

## 七、推荐交接阅读顺序

1. `README.md`：仓库总览与快速启动
2. `docs/PROJECT_STRUCTURE.md`：前后端分布、端口、接口边界
3. `backend/docs/FRONTEND_HANDOFF.md`：前端联调细节
4. `backend/API_CONTRACT.md`：接口契约
5. `backend/docs/API_STATUS.md`：接口实现状态
6. `backend/backend/README.md`：后端完整启动、测试、Docker 说明
