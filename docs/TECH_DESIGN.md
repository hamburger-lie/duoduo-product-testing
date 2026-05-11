# 技术设计文档

> 版本：v0.1
> 配套：PRD v0.1 / API_CONTRACT v0.1
> 范围：后端（前端仅为对接预留契约）

---

## 1. 总体架构

### 1.1 架构图（文字版）

```
┌─────────────────────────────────────────────────────────────┐
│                  微信小程序（未来对接）                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS / chunked
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Nginx (TLS / WAF / 静态资源)                    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI 应用层（无状态、可水平扩展）             │
│  ┌──────────┬──────────┬──────────┬──────────┬───────────┐  │
│  │ auth     │ product  │ survey   │ persona  │ report    │  │
│  │ router   │ router   │ router   │ router   │ router    │  │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴─────┬─────┘  │
│       │          │          │          │           │        │
│       ▼          ▼          ▼          ▼           ▼        │
│   ┌────────────────── services 层 ──────────────────────┐   │
│   │ AuthSvc  ProductSvc  SurveySvc  PersonaSvc  ReportSvc │ │
│   └─────────────────────┬─────────────────────────────────┘ │
│                         ▼                                    │
│   ┌──────────────── ai 编排层 ─────────────────────┐         │
│   │ ModelRouter / PromptManager / MemoryAdapter   │         │
│   │ ContextCache / RateLimiter / Retry / Fallback │         │
│   └────┬──────────────────┬───────────────────┬───┘         │
└────────┼──────────────────┼───────────────────┼─────────────┘
         ▼                  ▼                   ▼
   火山方舟 API         mem0 + Qdrant      内容审核 API
   (豆包多模型)         (角色记忆)          (绿网/盾)
         │                  │                   
         └──────────┬───────┘
                    ▼
   ┌─────────────────────────────────────────┐
   │ 数据持久化                               │
   │ ├─ PostgreSQL（业务主库）                │
   │ ├─ Redis（缓存/限流/会话）               │
   │ ├─ Qdrant（向量库）                      │
   │ ├─ TOS/OSS（产品图、报告 PDF）           │
   │ └─ Celery + Redis broker（异步任务）     │
   └─────────────────────────────────────────┘
```

### 1.2 模块边界与职责

| 模块 | 职责 | 不该做的事 |
|---|---|---|
| `routers/` | HTTP 入参出参、鉴权依赖注入、调 service | 不写业务逻辑、不直接调 LLM |
| `services/` | 业务编排、事务边界、调 ai 层与 db 层 | 不直接处理 HTTP、不直接调外部 API |
| `ai/` | 模型路由、prompt 渲染、记忆读写、流式封装 | 不感知业务实体（产品/问卷只作为参数传入） |
| `db/` | ORM 模型、CRUD、迁移 | 不写业务逻辑 |
| `tasks/` | Celery 异步任务（角色批量答题、报告生成） | 不直接对外暴露 |
| `core/` | 配置、日志、异常、依赖注入工具 | 不依赖业务模块 |

**强制规则**：依赖只能向"内"流动 —— `routers → services → ai/db/tasks → core`，反向 import 一律禁止。Codex 写代码时这条要写进 `AGENTS.md`。

---

## 2. 技术栈与版本

| 层 | 技术 | 版本 | 说明 |
|---|---|---|---|
| 语言 | Python | 3.11.x | 不上 3.12，部分依赖兼容性 |
| 包管理 | uv | latest | 全程用 uv，禁止 pip 直接装 |
| Web 框架 | FastAPI | ≥ 0.110 | 异步 |
| ASGI | Uvicorn + Gunicorn | latest | 生产用 gunicorn -k uvicorn.workers.UvicornWorker |
| ORM | SQLAlchemy | 2.0+ async | 全异步 |
| 迁移 | Alembic | latest | 强制走迁移、禁止直接改库 |
| 校验 | Pydantic | v2 | API 入出参全部用 BaseModel |
| 数据库 | PostgreSQL | 15+ | jsonb 存问卷答案 |
| 缓存 | Redis | 7+ | 会话、限流、Celery broker |
| 向量 | Qdrant | 1.10+ | mem0 默认后端 |
| 异步任务 | Celery | 5+ | broker = Redis，backend = Redis |
| LLM SDK | openai | latest | 火山方舟 OpenAI 兼容接口 |
| 记忆 | mem0ai | latest | LLM/embedder 全指向豆包 |
| 对象存储 | volcengine-tos-sdk | latest | 火山 TOS |
| 内容审核 | volcengine SDK | latest | 绿网 |
| 测试 | pytest + pytest-asyncio + httpx | latest | |
| Lint/Format | ruff + mypy | latest | mypy strict |
| 部署 | Docker + docker-compose（MVP） | — | 后期上 K8s |

**uv 用法约定**：
- 初始化：`uv init && uv add fastapi[standard] sqlalchemy[asyncio] ...`
- 锁定：`uv lock`
- 同步：`uv sync`（CI 与生产都用这个）
- 运行：`uv run uvicorn app.main:app`

---

## 3. 项目目录结构

```
backend/
├── pyproject.toml              # uv 管理
├── uv.lock
├── .env.example                # 环境变量样板
├── .gitignore
├── README.md
├── docker-compose.yml          # MVP 一键起本地依赖
├── Dockerfile
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口
│   ├── core/
│   │   ├── config.py           # Pydantic Settings
│   │   ├── logging.py          # 结构化日志
│   │   ├── exceptions.py       # 自定义异常 + 全局 handler
│   │   ├── security.py         # JWT、密码哈希
│   │   ├── deps.py             # 通用依赖（get_current_user 等）
│   │   └── constants.py
│   ├── db/
│   │   ├── base.py             # Base = declarative_base()
│   │   ├── session.py          # async session
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── product.py
│   │   │   ├── survey.py
│   │   │   ├── persona.py
│   │   │   ├── evaluation.py
│   │   │   ├── answer.py
│   │   │   ├── conversation.py
│   │   │   ├── report.py
│   │   │   └── credit.py
│   │   └── repositories/       # 每个 model 配一个 repo（CRUD 封装）
│   ├── schemas/                # Pydantic API schemas
│   │   ├── auth.py
│   │   ├── product.py
│   │   ├── survey.py
│   │   ├── persona.py
│   │   ├── evaluation.py
│   │   ├── conversation.py
│   │   ├── report.py
│   │   └── common.py           # 分页、错误响应等
│   ├── routers/
│   │   ├── auth.py             # /api/v1/auth/*
│   │   ├── product.py          # /api/v1/products/*
│   │   ├── survey.py           # /api/v1/surveys/*
│   │   ├── persona.py          # /api/v1/personas/*
│   │   ├── evaluation.py       # /api/v1/evaluations/*
│   │   ├── conversation.py     # /api/v1/conversations/*
│   │   ├── report.py           # /api/v1/reports/*
│   │   ├── credit.py           # /api/v1/credits/*
│   │   └── health.py           # /health
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── product_service.py
│   │   ├── survey_service.py
│   │   ├── persona_service.py
│   │   ├── evaluation_service.py
│   │   ├── conversation_service.py
│   │   ├── report_service.py
│   │   └── credit_service.py
│   ├── ai/
│   │   ├── client.py           # 豆包 client 单例
│   │   ├── models.py           # ModelEnum + 路由策略
│   │   ├── prompts/            # 所有 prompt 模板（jinja2）
│   │   │   ├── product_understand.j2
│   │   │   ├── survey_generate.j2
│   │   │   ├── persona_answer.j2
│   │   │   ├── persona_chat.j2
│   │   │   └── report_synthesize.j2
│   │   ├── prompt_manager.py   # 加载 + 渲染 + 版本号
│   │   ├── memory.py           # mem0 封装
│   │   ├── moderation.py       # 内容审核
│   │   ├── streaming.py        # SSE chunk 工具
│   │   └── exceptions.py
│   ├── tasks/
│   │   ├── celery_app.py
│   │   ├── persona_answer.py   # 单角色答题任务
│   │   ├── evaluation_run.py   # 整次测评编排
│   │   └── report_generate.py
│   ├── storage/
│   │   ├── tos_client.py       # 火山 TOS
│   │   └── upload.py           # 预签名 URL
│   └── utils/
│       ├── pagination.py
│       ├── ids.py              # snowflake / nanoid
│       └── time.py
├── seeds/                      # 种子数据（json，部署时 import）
│   ├── personas/               # 100 角色 json
│   ├── survey_templates/
│   └── report_templates/
├── scripts/
│   ├── seed_personas.py        # 把 seeds/personas/*.json 灌入库
│   ├── recreate_db.py          # 开发用：drop & create
│   └── eval_persona_diversity.py  # 评估角色一致性/多样性
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_product.py
    ├── test_survey.py
    ├── test_persona.py
    ├── test_evaluation.py
    ├── test_conversation.py
    ├── test_report.py
    ├── ai/
    │   ├── test_prompt_manager.py
    │   └── test_memory.py
    └── e2e/
        └── test_full_flow.py
```

---

## 4. 数据模型

### 4.1 ER 概览

```
User ────< Evaluation >──── Product
              │
              ├──< EvaluationPersona >── Persona
              │            │
              │            └──< Answer
              │            └──< Conversation ──< ConversationMessage
              │
              └── Report

User ──< CreditTransaction
```

### 4.2 表结构（SQLAlchemy 2.0 风格描述）

> 所有表统一字段：`id BIGINT PK`（snowflake）、`created_at TIMESTAMPTZ`、`updated_at TIMESTAMPTZ`、`deleted_at TIMESTAMPTZ NULL`（软删）。下面的"字段"列只列业务字段。

#### users
| 字段 | 类型 | 说明 |
|---|---|---|
| openid | VARCHAR(64) UNIQUE NOT NULL | 微信小程序 openid |
| unionid | VARCHAR(64) NULL INDEX | 多端预留 |
| nickname | VARCHAR(64) | |
| avatar_url | VARCHAR(512) | |
| role_type | VARCHAR(16) NOT NULL | `manufacturer` / `channel` |
| credit_balance | INTEGER NOT NULL DEFAULT 1000 | 当前积分 |
| status | VARCHAR(16) DEFAULT 'active' | `active` / `banned` |

索引：`(openid)`、`(unionid)`

#### products
| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | BIGINT FK | 所有者 |
| name | VARCHAR(128) | 用户填或 AI 生成 |
| description | TEXT | 用户填，10–500 字 |
| category | VARCHAR(32) | AI 提取（美妆/食品/...） |
| sub_category | VARCHAR(64) | 美妆下细分（面霜/口红/...） |
| brand | VARCHAR(64) NULL | |
| price | DECIMAL(10,2) NULL | |
| price_range | VARCHAR(32) NULL | AI 推断 |
| target_channel | VARCHAR(32) NULL | `ec`/`offline`/`livestream` |
| image_urls | JSONB | `["tos://..."]` |
| ai_summary | JSONB | 多模态理解结果（含卖点、成分、目标人群） |
| status | VARCHAR(16) DEFAULT 'ready' | `pending` / `ready` / `failed` |

索引：`(user_id, created_at DESC)`、`(category)`

#### personas
| 字段 | 类型 | 说明 |
|---|---|---|
| owner_id | BIGINT NULL | NULL=系统公共角色；非 NULL=用户私有 |
| name | VARCHAR(32) NOT NULL | |
| avatar | VARCHAR(64) | emoji 或图片 URL |
| age | SMALLINT NOT NULL | |
| gender | VARCHAR(8) NOT NULL | `female`/`male`/`other` |
| city | VARCHAR(32) NOT NULL | |
| city_tier | SMALLINT | 1/2/3/4/5 线 |
| occupation | VARCHAR(64) | |
| income_monthly | INTEGER | 月收入（元） |
| ocean_o | SMALLINT | 0–100 |
| ocean_c | SMALLINT | |
| ocean_e | SMALLINT | |
| ocean_a | SMALLINT | |
| ocean_n | SMALLINT | |
| persona_tag | VARCHAR(32) | 一句话标签 |
| profile | JSONB NOT NULL | 完整人设（见 SEEDS/personas/*.json schema） |
| categories | JSONB | 适配品类 `["美妆","护肤"]` |
| is_critical | BOOLEAN DEFAULT FALSE | 是否挑剔型（强制保证报告平衡） |
| version | INTEGER DEFAULT 1 | 角色版本 |
| status | VARCHAR(16) DEFAULT 'active' | |

索引：`(owner_id)`、`(categories)` GIN、`(is_critical)`、`(persona_tag)`

#### evaluations
| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | BIGINT FK | |
| product_id | BIGINT FK | |
| survey_id | BIGINT FK | 关联本次测评用的问卷 |
| selected_persona_ids | JSONB NOT NULL | `[id1, id2, ...]` |
| status | VARCHAR(16) NOT NULL | `pending`/`generating_survey`/`answering`/`generating_report`/`done`/`failed`/`canceled` |
| progress | SMALLINT DEFAULT 0 | 0–100 |
| credit_cost | INTEGER DEFAULT 0 | 本次消耗积分（先记录不扣） |
| error_message | TEXT NULL | |
| started_at | TIMESTAMPTZ NULL | |
| finished_at | TIMESTAMPTZ NULL | |

索引：`(user_id, created_at DESC)`、`(status)`

#### surveys
| 字段 | 类型 | 说明 |
|---|---|---|
| evaluation_id | BIGINT FK | |
| product_id | BIGINT FK | |
| questions | JSONB NOT NULL | 完整题目数组（见 SEEDS/survey_templates/） |
| version | INTEGER DEFAULT 1 | |
| generated_by | VARCHAR(16) DEFAULT 'ai' | `ai`/`user_edited` |

#### answers
> 一条记录 = 一个角色对一份问卷的全部回答

| 字段 | 类型 | 说明 |
|---|---|---|
| evaluation_id | BIGINT FK | |
| survey_id | BIGINT FK | |
| persona_id | BIGINT FK | |
| answers | JSONB NOT NULL | `[{"qid":"q1","answer":"...","reason":"..."}]` |
| overall_intent | SMALLINT | 1–5 综合购买意愿（用于报告聚合） |
| sentiment | VARCHAR(16) | `positive`/`neutral`/`negative` |
| token_input | INTEGER | 本次答题输入 token |
| token_output | INTEGER | |
| cost_yuan | DECIMAL(10,4) | |
| status | VARCHAR(16) | `done`/`failed` |
| error_message | TEXT NULL | |

索引：`(evaluation_id, persona_id)` UNIQUE、`(persona_id, created_at DESC)`

#### conversations
| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | BIGINT FK | |
| evaluation_id | BIGINT FK | |
| persona_id | BIGINT FK | |
| title | VARCHAR(128) | |
| message_count | INTEGER DEFAULT 0 | |
| last_message_at | TIMESTAMPTZ | |

索引：`(user_id, evaluation_id, persona_id)`

#### conversation_messages
| 字段 | 类型 | 说明 |
|---|---|---|
| conversation_id | BIGINT FK | |
| role | VARCHAR(16) | `user`/`assistant` |
| content | TEXT | |
| token_input | INTEGER NULL | |
| token_output | INTEGER NULL | |
| cost_yuan | DECIMAL(10,4) NULL | |

索引：`(conversation_id, created_at)`

#### reports
| 字段 | 类型 | 说明 |
|---|---|---|
| evaluation_id | BIGINT FK UNIQUE | |
| summary | TEXT | 3–5 条核心洞察 |
| metrics | JSONB | 量化结果（NPS、雷达图数据、分布等） |
| top_pros | JSONB | `[{title, support_count, quotes}]` |
| top_cons | JSONB | 同上 |
| persona_segments | JSONB | 人群分布 |
| pdf_url | VARCHAR(512) NULL | |
| share_token | VARCHAR(32) NULL UNIQUE | 分享链接 token |

#### credit_transactions
| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | BIGINT FK | |
| amount | INTEGER NOT NULL | 正=收入、负=消耗 |
| balance_after | INTEGER | |
| reason | VARCHAR(32) | `init`/`survey_gen`/`persona_answer`/`chat`/`recharge`/`refund` |
| ref_type | VARCHAR(32) NULL | `evaluation`/`conversation` |
| ref_id | BIGINT NULL | |
| note | TEXT NULL | |

索引：`(user_id, created_at DESC)`

#### prompt_versions（运营用）
| 字段 | 类型 | 说明 |
|---|---|---|
| name | VARCHAR(64) NOT NULL | `survey_generate`/`persona_answer`/... |
| version | VARCHAR(16) NOT NULL | `v1.0.0` |
| template | TEXT NOT NULL | jinja2 模板 |
| model | VARCHAR(64) | 默认匹配模型 |
| is_active | BOOLEAN DEFAULT FALSE | |
| meta | JSONB | |

UNIQUE `(name, version)`。MVP 阶段 prompt 直接读文件，但库里建表，方便后期热更新。

---

## 5. 关键流程时序

### 5.1 创建测评（产品理解 + 问卷生成）

```
Client          API Router       Service           AI Layer        DB
  │ POST /products  │                │                │             │
  │ (text+image_urls)│                │                │             │
  ├────────────────►│                │                │             │
  │                 │ create_product()                │             │
  │                 ├───────────────►│                │             │
  │                 │                │ save(status=pending) ─────►  │
  │                 │                │ understand_product()         │
  │                 │                ├───────────────►│             │
  │                 │                │                │ vision-pro  │
  │                 │                │                │ + parse JSON│
  │                 │                │◄───────────────┤             │
  │                 │                │ update(ai_summary, status=ready)│
  │                 │                │              ─────────────►  │
  │                 │◄───────────────┤                │             │
  │◄────────────────┤ 200 OK {product_id, ai_summary} │             │
  │                                                                  │
  │ POST /surveys (product_id) ────►│                │             │
  │                 │ generate_survey()              │             │
  │                 ├───────────────►│                │             │
  │                 │                │ render prompt + call LLM     │
  │                 │                ├───────────────►│             │
  │                 │                │◄─── questions JSON ─────────┤
  │                 │                │ save survey ──────────────►  │
  │                 │◄───────────────┤                │             │
  │◄────────────────┤ 200 {survey_id, questions[]}    │             │
```

### 5.2 角色批量答题（异步）

```
Client       API           EvalService         Celery          Worker        DB
  │ POST     │                │                  │              │           │
  │ /evaluations/{id}/run     │                  │              │           │
  ├─────────►│                │                  │              │           │
  │          │ start_eval()  │                  │              │           │
  │          ├──────────────►│                  │              │           │
  │          │                │ enqueue task ──►│              │           │
  │          │◄──────────────┤                  │              │           │
  │◄─────────┤ 202 Accepted   │                  │              │           │
  │ {evaluation_id, status: 'answering'}        │              │           │
  │                                              │              │           │
  │                                              │ dispatch ──►│ for each   │
  │                                              │              │ persona:  │
  │                                              │              │  - load   │
  │                                              │              │    profile│
  │                                              │              │  - render │
  │                                              │              │    prompt │
  │                                              │              │  - call   │
  │                                              │              │    LLM    │
  │                                              │              │  - parse  │
  │                                              │              │  - save   │
  │                                              │              │    answer │
  │                                              │              │  - mem0   │
  │                                              │              │    .add() │
  │                                              │              │  - update │
  │                                              │              │    progress
  │                                              │              │           │
  │ GET /evaluations/{id}                         │              │           │
  │ (轮询或后续做 WS)                              │              │           │
  │ 返回 status / progress                        │              │           │
  │                                              │ 全部完成后    │           │
  │                                              │ 触发报告任务  │           │
```

### 5.3 单角色流式对话

```
Client                   API Router          ConvService        AI/Memory      DB
  │ POST /conversations/  │                    │                  │            │
  │ {persona_id,          │                    │                  │            │
  │  evaluation_id}       │                    │                  │            │
  ├──────────────────────►│                    │                  │            │
  │                       │ create_or_get()    │                  │            │
  │                       ├───────────────────►│                  │            │
  │                       │                    │ insert/find ──────────────►   │
  │                       │◄───────────────────┤                  │            │
  │◄──────────────────────┤ {conversation_id}  │                  │            │
  │                                                                            │
  │ POST /conversations/{id}/messages (stream=true)                            │
  ├──────────────────────►│                    │                  │            │
  │                       │ chat_stream()      │                  │            │
  │                       ├───────────────────►│                  │            │
  │                       │                    │ memory.search ──►│            │
  │                       │                    │                  │ 返回相关记忆│
  │                       │                    │ build messages  │            │
  │                       │                    │ (system+memory+history+q)    │
  │                       │                    │ stream call LLM ────────────► │
  │ ◄════════ HTTP chunked: data:{...}\n\n ════════════════════════════════════│
  │ ◄════════ data:{...}\n\n ═══════════════════════════════════════════════   │
  │ ◄════════ data:[DONE]\n\n ══════════════════════════════════════════════   │
  │                       │                    │ memory.add() ──►│            │
  │                       │                    │ save messages ─────────────►  │
```

---

## 6. AI 编排层设计

### 6.1 ModelRouter（关键代码骨架）

```python
# app/ai/models.py
from enum import Enum

class TaskType(str, Enum):
    PRODUCT_UNDERSTAND = "product_understand"
    SURVEY_GENERATE = "survey_generate"
    PERSONA_ANSWER = "persona_answer"
    PERSONA_CHAT = "persona_chat"
    REPORT_SYNTHESIZE = "report_synthesize"
    MEMORY_EXTRACT = "memory_extract"

# 模型映射；endpoint_id 从环境变量读
MODEL_ROUTING = {
    TaskType.PRODUCT_UNDERSTAND: "ARK_EP_VISION_PRO",
    TaskType.SURVEY_GENERATE:    "ARK_EP_DOUBAO_SEED_16",
    TaskType.PERSONA_ANSWER:     "ARK_EP_DOUBAO_15_PRO_CHARACTER",
    TaskType.PERSONA_CHAT:       "ARK_EP_DOUBAO_15_LITE",  # 可降级
    TaskType.REPORT_SYNTHESIZE:  "ARK_EP_DOUBAO_SEED_16",  # 启用思考
    TaskType.MEMORY_EXTRACT:     "ARK_EP_DOUBAO_15_LITE",
}
```

### 6.2 PromptManager
- 模板文件位于 `app/ai/prompts/*.j2`，jinja2 渲染
- 每次渲染产出 `(rendered_str, prompt_version_string)` 二元组
- 版本字符串写入对应记录，便于 A/B 与回溯

### 6.3 MemoryAdapter（mem0 封装）

```python
# app/ai/memory.py
class PersonaMemory:
    def __init__(self, mem0_client): ...

    def add_questionnaire(self, *, evaluation_id, persona_id, user_id,
                          messages: list[dict], product_meta: dict) -> None:
        """问卷答完后调用，沉淀为长期记忆。"""

    def search(self, *, persona_id, user_id, query: str, limit: int = 8) -> list[str]:
        """对话前检索相关记忆。"""

    def add_chat_turn(self, *, conversation_id, persona_id, user_id,
                      user_msg: str, assistant_msg: str) -> None:
        """对话后异步写回。"""
```

**ID 约定**（强一致性，必须严格执行）：
- `agent_id = f"persona_{persona_id}"`
- `user_id  = f"user_{owner_user_id}_eval_{evaluation_id}"`（同一用户对同一测评的所有角色记忆隔离）
- `run_id   = f"conv_{conversation_id}"`（单次对话）

### 6.4 流式封装

```python
# app/ai/streaming.py
async def sse_generator(stream) -> AsyncGenerator[bytes, None]:
    """把 OpenAI 兼容 stream 转为 SSE chunk 格式。"""
    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n".encode()
    yield b"data: [DONE]\n\n"
```

Nginx 配置必须：
```
proxy_buffering off;
proxy_cache off;
proxy_http_version 1.1;
chunked_transfer_encoding on;
add_header X-Accel-Buffering no;
```

### 6.5 限流与重试
- Semaphore：同一 evaluation 内并发调用 ≤ 20（可配置）
- 全局 RPM 限流：基于 Redis token bucket
- 重试：3 次指数退避（0.5s / 2s / 5s），仅对 5xx / 网络错误重试，4xx 直接抛
- 超时：单次调用 60s

---

## 7. 鉴权设计（小程序为主，多端预留）

### 7.1 流程
1. 小程序 `wx.login()` → `code`
2. `POST /api/v1/auth/wechat/login {code}`
3. 后端用 code 换 openid + session_key（调微信接口）
4. 查/建 user，签发 JWT（含 `user_id`、`role_type`、`exp`）
5. 后续请求 header：`Authorization: Bearer <token>`
6. JWT 有效期 7 天；提供 `/api/v1/auth/refresh` 静默续期

### 7.2 多端预留
- 鉴权层抽象成 `AuthProvider` 接口，目前仅实现 `WechatMiniProgramProvider`
- user 表 `openid` 与 `unionid` 分开，未来加 `mobile`、`email` 列即可
- 中间件 `get_current_user(request)` 始终返回 `User` 对象，不依赖具体登录方式

### 7.3 内部接口鉴权
- `/internal/*` 路径用 IP 白名单 + 静态 API Key（用于 Celery worker 回调、运营脚本）

---

## 8. 错误处理与错误码

### 8.1 统一错误响应

```json
{
  "code": "PERSONA_NOT_FOUND",
  "message": "指定的角色不存在",
  "details": { "persona_id": 12345 },
  "request_id": "req_xxx",
  "timestamp": "2026-05-09T12:00:00Z"
}
```

HTTP 状态码 + 业务码并存。详细错误码表见 `API_CONTRACT.md` 第 10 节。

### 8.2 异常分层
- `AppException` 基类（含 code/message/http_status）
- 子类：`AuthException`、`ResourceNotFoundException`、`ValidationException`、`AIServiceException`、`CreditException` 等
- FastAPI 全局 handler 把 `AppException` 转为统一响应；未捕获异常返回 500 + `INTERNAL_ERROR`

---

## 9. 配置与环境变量

`.env.example`：
```
# 应用
APP_ENV=development          # development / staging / production
APP_PORT=8000
APP_SECRET_KEY=change_me
APP_JWT_EXPIRE_DAYS=7

# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/cepin
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333

# 微信
WECHAT_APPID=
WECHAT_SECRET=

# 火山方舟
ARK_API_KEY=
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_EP_DOUBAO_SEED_16=ep-xxxx
ARK_EP_DOUBAO_15_PRO_CHARACTER=ep-xxxx
ARK_EP_DOUBAO_15_LITE=ep-xxxx
ARK_EP_VISION_PRO=ep-xxxx
ARK_EP_EMBEDDING=ep-xxxx

# 火山 TOS
TOS_AK=
TOS_SK=
TOS_BUCKET=cepin-prod
TOS_REGION=cn-beijing
TOS_ENDPOINT=tos-cn-beijing.volces.com

# 内容审核
MODERATION_AK=
MODERATION_SK=

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 日志
LOG_LEVEL=INFO
SENTRY_DSN=
```

`app/core/config.py` 用 Pydantic Settings 加载，必须有类型校验。

---

## 10. 部署与运维

### 10.1 本地开发
```bash
# 一键起依赖
docker-compose up -d postgres redis qdrant

# 装依赖
uv sync

# 迁移
uv run alembic upgrade head

# 灌种子
uv run python scripts/seed_personas.py

# 启动
uv run uvicorn app.main:app --reload

# 启动 Celery worker
uv run celery -A app.tasks.celery_app worker -l info -c 4
```

### 10.2 生产
- 火山引擎 ECS 2 台 8C16G + 同 region 方舟
- Nginx 反向代理 + Let's Encrypt
- PostgreSQL 用云 RDS、Redis 用云 Redis、Qdrant 用 Docker 起在 ECS
- TOS 私有 bucket + 预签名 URL
- 单 ECS docker-compose 部署 app/worker/nginx 三个容器
- 备份：RDS 自动每日备份，Qdrant 每周快照到 TOS

### 10.3 健康检查
- `GET /health/live` 返回 200
- `GET /health/ready` 检查 DB/Redis/Qdrant/方舟可达性

### 10.4 监控
- Prometheus 抓 `/metrics`（fastapi-prometheus-instrumentator）
- 关键指标：QPS、延迟 p95/p99、5xx 比例、token 消耗（按模型）、积分消耗、Celery 队列长度
- Sentry 抓异常

---

## 11. 安全与合规

| 项 | 要求 |
|---|---|
| HTTPS | 强制 TLS 1.2+ |
| 密码 | 暂无密码（仅小程序登录） |
| JWT | 用 HS256，secret 至少 32 字节随机 |
| SQL 注入 | 全程 ORM，禁止字符串拼接 SQL |
| 文件上传 | 仅允许 jpg/png，大小 ≤ 5MB，magic number 校验 |
| 输入审核 | 产品描述 + 用户对话先过内容审核 API |
| 输出审核 | LLM 生成结果再过一次审核（角色对话流式时旁路异步审核 + 关键词兜底） |
| AI 标识 | 报告与对话 UI 必须显式标注"AI 生成内容仅供参考"（强制国标） |
| 数据删除 | 用户主动删除：软删 30 天后硬删；产品图与对话有保留期 |
| 算法备案 | MVP 借火山方舟备案，需在小程序 / 隐私政策中明示使用方 |
| 日志脱敏 | 不记录用户产品图原文、不记录 JWT、不记录方舟 API key |

---

## 12. 测试策略

| 层 | 工具 | 覆盖目标 |
|---|---|---|
| 单元测试 | pytest | services/ai/utils；目标覆盖率 ≥ 70% |
| 接口测试 | pytest + httpx | 所有 P0 接口正反例 |
| AI 集成测试 | pytest + 真实方舟 key（独立 ci 环境） | prompt 关键链路冒烟 |
| 端到端 | pytest + docker-compose | 完整测评流程跑一遍 |
| 角色一致性评估 | 自研脚本 + DeepEval | `scripts/eval_persona_diversity.py` |

CI（GitHub Actions）：
1. ruff check
2. mypy
3. pytest（不调真实 LLM 的部分）
4. 构建 Docker 镜像

---

## 13. 关键非功能性约束（强制 Codex 遵守）

1. **全异步**：所有 IO 用 async；DB session 用 async session；HTTP 客户端用 httpx.AsyncClient
2. **类型严格**：所有函数签名必须有完整类型；mypy --strict 通过
3. **不在 router 写业务**：router 只做参数校验 + 调 service + 拼响应
4. **不在 service 直接调 LLM**：必须经过 ai 层
5. **不在代码里硬编码 prompt**：必须放在 `app/ai/prompts/*.j2`
6. **所有外部 API 调用必须有超时与重试**
7. **所有写库操作在事务内**：service 层用 async context manager 管理 session
8. **Celery 任务必须幂等**：用 evaluation_id + persona_id 做唯一约束防重
9. **金额/积分用整数**：积分 INTEGER；钱用 DECIMAL，禁止 float
10. **日志结构化**：JSON 格式，每条日志带 request_id / user_id

---

## 14. 待定项 / TODO

- [ ] 火山方舟具体 endpoint id 待运营在控制台创建后填入
- [ ] 内容审核服务最终选型（绿网 vs 阿里云盾）—— 看价格与接入难度
- [ ] PDF 报告生成方案（weasyprint vs 服务端 puppeteer）—— M2 决定
- [ ] WebSocket vs HTTP 轮询用于异步任务进度推送 —— MVP 先用轮询
- [ ] Qdrant 生产部署模式（自建单机 vs 集群 vs 火山 VikingDB）—— M2 决定
