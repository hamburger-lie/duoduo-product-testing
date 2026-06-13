# 测品官 · AI 产品测评平台

> 微信小程序 + FastAPI 后端 · 全栈 AI 消费者洞察工具

**让虚拟消费者替你测品——上传产品、生成问卷、多角色 AI 答题、一键输出洞察报告**

---

## 项目简介

测品官是一款面向品牌方和产品经理的 AI 测品工具。用户上传产品信息后，系统自动生成调研问卷，由多个具备独立人格的虚拟消费者（测品官）进行评测，最终输出结构化的洞察报告和白皮书。

### 核心流程

```
登录 → 上传产品 → AI 生成问卷 → 选择虚拟人群 → 流式对话评测 → 生成报告 → 导出白皮书 PDF
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | 微信小程序 (Native)、TypeScript、WXSS |
| **后端** | Python 3.11、FastAPI、SQLAlchemy 2.0 async |
| **数据库** | PostgreSQL 15、Redis 7、Qdrant (向量库) |
| **AI** | DeepSeek / 智谱 GLM (OpenAI 兼容接口)、Jinja2 Prompt 模板 |
| **异步任务** | Celery 5 + Redis Broker |
| **部署** | Docker Compose、Nginx、Prometheus |

---

## 仓库结构

本仓库同时托管前端小程序和后端服务，通过分支前缀区分：

```
branches
├── 前端小程序 (默认无前缀)
│   ├── main                       # 基础项目配置
│   ├── feature/design-system      # 设计 Token + 静态资源
│   ├── feature/type-system        # TypeScript 类型层
│   ├── feature/service-layer      # API 封装层 (http/SSE/endpoints)
│   ├── feature/mock-data          # Phase A Mock 数据
│   ├── feature/ui-components      # 可复用组件库 (7个组件)
│   ├── feature/home-page          # 首页 (浮动人群气泡)
│   ├── feature/product-management # 产品库 + 产品详情
│   ├── feature/persona-system     # 人群库 + 人群编辑 (OCEAN)
│   ├── feature/evaluation-workflow# 创建调研 + 问卷审视
│   ├── feature/chat-streaming     # SSE 流式对话 (think+speak)
│   ├── feature/report-generation  # 报告详情 + PDF 白皮书
│   ├── feature/history-archive    # 历史档案
│   ├── feature/user-profile       # 个人中心 + 设置 + 余额
│   ├── feature/webview            # Web 容器
│   └── develop                    # 完整前端集成
│
└── 后端服务 (backend/ 前缀)
    ├── backend/main                       # 后端基础配置
    ├── backend/feature/db-foundation      # SQLAlchemy + Alembic
    ├── backend/feature/core-infrastructure# 配置/安全/日志/异常
    ├── backend/feature/auth               # 微信登录 + JWT
    ├── backend/feature/health             # 健康检查接口
    ├── backend/feature/storage            # 文件上传抽象层
    ├── backend/feature/product            # 产品管理 CRUD
    ├── backend/feature/persona            # 虚拟人群系统 (OCEAN)
    ├── backend/feature/ai-layer           # LLM 集成 (流式/记忆/断路器)
    ├── backend/feature/survey             # AI 问卷生成
    ├── backend/feature/evaluation         # 调研工作流
    ├── backend/feature/celery-tasks       # Celery 异步任务队列
    ├── backend/feature/conversation       # SSE 流式对话
    ├── backend/feature/report             # 报告生成与洞察综合
    ├── backend/feature/credit             # 积分系统
    ├── backend/feature/history            # 历史档案查询
    ├── backend/feature/whitepaper-pdf     # 白皮书生成 + PDF 导出
    ├── backend/feature/webhook            # Webhook 投递
    ├── backend/feature/observability      # Redis 缓存/限流/Prometheus
    ├── backend/feature/integration-tests  # 集成/E2E/安全/性能测试
    └── backend/develop                    # 完整后端集成
```

---

## 前端快速开始

**环境要求：** 微信开发者工具 ≥ 1.06.x

```bash
# 1. 切换到完整前端代码
git checkout develop

# 2. 用微信开发者工具打开 miniprogram/ 目录
# AppID: wx81beb2cf47c0ebfb
```

**Mock 模式（无需后端）：**

`miniprogram/services/api.ts` 中 `USE_MOCK = true` 即可用 mock 数据运行所有页面。

**接入真实后端：**

```typescript
// miniprogram/services/api.ts
export const USE_MOCK = false;

// miniprogram/services/http.ts
export const BASE_URL = 'http://127.0.0.1:18000';
```

---

## 后端快速开始

```powershell
# 1. 切换到完整后端代码
git checkout backend/develop
cd backend

# 2. 复制环境变量（填入 API Key 等配置）
Copy-Item .env.example .env

# 3. 启动基础设施
docker compose up -d postgres redis qdrant

# 4. 安装依赖 & 初始化数据库
uv sync
uv run alembic upgrade head
uv run python scripts/seed_personas.py

# 5. 启动服务
uv run uvicorn app.main:app --host 127.0.0.1 --port 18000 --reload
```

Swagger 文档：`http://127.0.0.1:18000/docs`

---

## 主要功能模块

### 前端页面 (16个)

| 页面 | 功能 |
|------|------|
| 首页 | 6个浮动虚拟人群气泡 + 创建调研入口 |
| 产品库 | 产品 CRUD + 图片上传 + AI 摘要展示 |
| 人群库 | 系统/自定义人群管理，OCEAN 人格模型 |
| 创建调研 | 填写产品信息 → AI 生成问卷 → 选择人群 |
| 调研对话 | 实时 SSE 双流（内心独白 + 口头表达） |
| 历史档案 | 评测卡片列表 + 搜索/筛选 |
| 报告详情 | 各人群答题汇总 + 意向星评 + 关键洞察 |
| PDF 白皮书 | 生成白皮书 + 在线预览 + 下载 |
| 个人中心 | 头像上传 + 用户信息 + 功能导航 |
| 余额充值 | 积分余额 + 交易历史 |

### 后端接口 (11个路由模块)

| 模块 | 说明 |
|------|------|
| `/auth` | 微信登录、token 刷新、用户信息 |
| `/product` | 产品 CRUD、图片上传 URL、AI 分析 |
| `/persona` | 系统/自定义人群、推荐算法 |
| `/survey` | AI 问卷生成（流式）、问题管理 |
| `/evaluation` | 创建/运行/状态查询、深度分析 |
| `/conversation` | SSE 流式对话、历史记录 |
| `/report` | 报告查询、商业报告、洞察导出 |
| `/credit` | 余额查询、交易记录、充值 |
| `/history` | 评测历史卡片列表 |
| `/whitepaper` | 白皮书生成、状态查询、PDF 导出 |
| `/health` | 服务健康、DB/Redis 连通性 |

---

## 环境变量说明

后端关键配置（详见 `backend/.env.example`）：

```env
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/cepinguan

# AI 提供商 (选其一)
AI_PROVIDER=deepseek           # mock | deepseek | zhipu
DEEPSEEK_API_KEY=sk-xxx

# 微信
WECHAT_APP_ID=wx...
WECHAT_APP_SECRET=...

# 评测运行模式
EVALUATION_RUN_MODE=sync       # sync | celery
```

---

## 项目文档

| 文档 | 位置 | 说明 |
|------|------|------|
| 接口契约 | `API_CONTRACT.md` | 前后端唯一接口约定 |
| API 状态表 | `docs/API_STATUS.md` | 各接口实现状态 |
| 前端联调指南 | `docs/FRONTEND_HANDOFF.md` | 前后端联调说明 |
| 技术设计 | `docs/TECH_DESIGN.md` | 架构设计文档 |
| PRD | `docs/PRD.md` | 产品需求文档 |
| 交付清单 | `docs/DELIVERY_CHECKLIST.md` | MVP 验收标准 |

---

## 设计规范

- **主色：** 雾紫 `#7B6FA8`
- **背景：** 纯白 `#FFFFFF`
- **字体色：** 深灰 `#1A1A1A`
- **设计原则：** 零 emoji，纯 CSS/SVG 图形，符合微信小程序设计规范
