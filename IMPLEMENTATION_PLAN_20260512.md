# 实施计划书：模型选型 + 提示词重写 + 统一输出规范

> 日期：2026-05-12
> 目标：一天内完成三项改动并通过测试
> 执行者：Claude Code
> 代码库：`backend/` 目录

---

## 背景与约束

- **可用 API Key**：DeepSeek（稳定） + 智谱 GLM-4.6V（多模态）
- **不再使用豆包/火山方舟**（排队超时问题严重），代码中 ark 相关配置保留但标注废弃
- **DeepSeek 当前可用模型**：`deepseek-v4-pro`（旗舰）、`deepseek-v4-flash`（快速经济）
  - 旧名 `deepseek-chat` / `deepseek-reasoner` 将于 2026/07/24 废弃
  - 两者均支持 1M context、JSON mode、tool calls、streaming、thinking mode
  - V4-Pro 75% 折扣至 2026/05/31：输入 $0.435/M，输出 $0.87/M
  - V4-Flash：输入 $0.14/M，输出 $0.28/M
- **智谱 GLM-4.6V**：用于多模态产品图片理解
  - MoE 架构，106B 总参数 / 12B 激活，128K 上下文
  - 原生多模态（图片/视频/文本），原生 Function Calling
  - API 价格：输入 ¥1/百万 tokens，输出 ¥3/百万 tokens
  - OpenAI 兼容接口，base_url: `https://open.bigmodel.cn/api/paas/v4`
  - 模型名：`glm-4.6v`（多模态主模型）、`glm-4.6v-flash`（轻量免费版）
- **核心原则**：改动必须向后兼容，`AI_PROVIDER=mock` 仍然可用于本地开发

---

## 一、模型选型定稿

### 1.1 策略：DeepSeek 文本主力 + GLM-4.6V 多模态

| TaskType | Provider | 模型 | 理由 |
|---|---|---|---|
| `PRODUCT_UNDERSTAND` | **zhipu** | `glm-4.6v` | 产品图片理解需要多模态能力，GLM-4.6V 原生支持图片输入且国内价格最优（¥1/M输入） |
| `SURVEY_GENERATE` | deepseek | `deepseek-v4-pro` | 30 题结构化 JSON 需要强 instruction following |
| `PERSONA_ANSWER` | deepseek | `deepseek-v4-pro` | 角色扮演是核心竞争力，不能省；temperature 0.85 保持角色差异 |
| `PERSONA_CHAT` | deepseek | `deepseek-v4-flash` | 流式对话速度优先，flash 便宜 5x+ |
| `REPORT_SYNTHESIZE` | deepseek | `deepseek-v4-pro` | 综合分析需要深度推理 |
| `MEMORY_EXTRACT` | deepseek | `deepseek-v4-flash` | 轻量抽取任务 |

> **混合路由核心设计**：同一次测评流程中，产品理解走智谱 GLM-4.6V，其余全走 DeepSeek。
> `AI_PROVIDER` 配置决定文本类任务的 provider（mock/deepseek），多模态任务独立由 `ZHIPU_API_KEY` 是否配置决定。

### 1.2 单次 100 角色完整测评成本估算

| 步骤 | 模型 | 输入 tokens | 输出 tokens | 成本 |
|---|---|---|---|---|
| 产品理解（含图片） | GLM-4.6V | ~3000（含图片token） | ~500 | ¥0.005 |
| 问卷生成 | DS v4-pro | ~1000 | ~2500 | $0.003 |
| 100 角色答题 | DS v4-pro | 300K | 150K | $0.26 |
| 50 轮对话 | DS v4-flash | 50K | 25K | $0.014 |
| 报告综合 | DS v4-pro | 30K | 6K | $0.018 |
| 记忆抽取 | DS v4-flash | 10K | 2K | $0.002 |
| **合计** | | | | **~$0.30 + ¥0.005 ≈ ¥2.2/次** |

### 1.3 代码改动清单

#### 文件：`app/core/config.py`

```python
# 新增以下字段：

# DeepSeek 模型名（替代单一 deepseek_model 字段）
deepseek_model_pro: str = Field(
    default="deepseek-v4-pro",
    alias="DEEPSEEK_MODEL_PRO",
)
deepseek_model_flash: str = Field(
    default="deepseek-v4-flash",
    alias="DEEPSEEK_MODEL_FLASH",
)

# 智谱 GLM（多模态专用）
zhipu_api_key: str = Field(default="", alias="ZHIPU_API_KEY")
zhipu_base_url: str = Field(
    default="https://open.bigmodel.cn/api/paas/v4",
    alias="ZHIPU_BASE_URL",
)
zhipu_model_vision: str = Field(
    default="glm-4.6v",
    alias="ZHIPU_MODEL_VISION",
)

# 旧字段 deepseek_model 标注废弃，暂时保留向后兼容
# 旧字段 ark_* 全部保留但不再主动使用
```

#### 文件：`app/ai/models.py`

重写 `ModelRouter.__init__`，核心改动 —— **混合路由**：

```python
class ModelRouter:
    """Maps TaskType to model routes.

    DeepSeek 做文本主力，GLM-4.6V 做多模态。
    PRODUCT_UNDERSTAND 走智谱（如有 key），其余走 DeepSeek。
    """

    def __init__(self) -> None:
        from app.core.config import get_settings

        s = get_settings()
        provider = s.ai_provider.strip().lower()

        if provider == "mock":
            self._routes = {
                t: ModelRoute(
                    task_type=t,
                    endpoint_id="mock",
                    endpoint_env_name="MOCK",
                )
                for t in TaskType
            }
            return

        # DeepSeek 文本模型
        pro = s.deepseek_model_pro    # "deepseek-v4-pro"
        flash = s.deepseek_model_flash  # "deepseek-v4-flash"

        self._routes = {
            TaskType.SURVEY_GENERATE: ModelRoute(
                task_type=TaskType.SURVEY_GENERATE,
                endpoint_id=pro,
                endpoint_env_name="DEEPSEEK_MODEL_PRO",
            ),
            TaskType.PERSONA_ANSWER: ModelRoute(
                task_type=TaskType.PERSONA_ANSWER,
                endpoint_id=pro,
                endpoint_env_name="DEEPSEEK_MODEL_PRO",
            ),
            TaskType.PERSONA_CHAT: ModelRoute(
                task_type=TaskType.PERSONA_CHAT,
                endpoint_id=flash,
                endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                supports_streaming=True,
            ),
            TaskType.REPORT_SYNTHESIZE: ModelRoute(
                task_type=TaskType.REPORT_SYNTHESIZE,
                endpoint_id=pro,
                endpoint_env_name="DEEPSEEK_MODEL_PRO",
            ),
            TaskType.MEMORY_EXTRACT: ModelRoute(
                task_type=TaskType.MEMORY_EXTRACT,
                endpoint_id=flash,
                endpoint_env_name="DEEPSEEK_MODEL_FLASH",
            ),
        }

        # 产品理解：优先走智谱 GLM-4.6V（多模态）
        if s.zhipu_api_key:
            self._routes[TaskType.PRODUCT_UNDERSTAND] = ModelRoute(
                task_type=TaskType.PRODUCT_UNDERSTAND,
                endpoint_id=s.zhipu_model_vision,  # "glm-4.6v"
                endpoint_env_name="ZHIPU_MODEL_VISION",
                supports_vision=True,
            )
        else:
            # 没有智谱 key 就用 DeepSeek pro 做纯文本理解
            self._routes[TaskType.PRODUCT_UNDERSTAND] = ModelRoute(
                task_type=TaskType.PRODUCT_UNDERSTAND,
                endpoint_id=pro,
                endpoint_env_name="DEEPSEEK_MODEL_PRO",
            )
```

#### 文件：`app/ai/factory.py`

新增智谱 client 工厂方法：

```python
def get_ai_client() -> AIClient:
    """Return AI client based on AI_PROVIDER."""
    # ... 保留 mock / deepseek 逻辑不变 ...
    # 删除 ark 分支（或保留但标注 deprecated）

def get_vision_client() -> AIClient:
    """Return AI client specifically for vision/multimodal tasks.

    优先智谱 GLM-4.6V，fallback 到 get_ai_client()。
    """
    from app.core.config import get_settings
    s = get_settings()

    if s.zhipu_api_key:
        return ArkOpenAIClient(
            api_key=s.zhipu_api_key,
            base_url=s.zhipu_base_url,
        )
    # 没有智谱 key，fallback 到默认 client（纯文本理解）
    return get_ai_client()
```

> 注意：`ArkOpenAIClient` 本身就是 OpenAI 兼容客户端，智谱的 API 也兼容 OpenAI 格式，所以直接复用即可，只是 api_key 和 base_url 不同。

#### 文件：`app/services/product_service.py`

修改 `_understand_product_with_ai` 方法：

```python
async def _understand_product_with_ai(self, *, user, payload):
    from app.ai.factory import get_vision_client  # 改为 get_vision_client
    # ...
    ai_client = self._ai_client or get_vision_client()
    # ... 其余不变
```

#### 文件：`.env.example`

```bash
# === AI Provider（文本类任务） ===
AI_PROVIDER=deepseek          # mock | deepseek

# === DeepSeek（文本主力） ===
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL_PRO=deepseek-v4-pro
DEEPSEEK_MODEL_FLASH=deepseek-v4-flash

# === 智谱 GLM（多模态/视觉，产品图片理解专用） ===
ZHIPU_API_KEY=xxx.xxx
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL_VISION=glm-4.6v

# === 火山方舟（已废弃，保留字段但不再使用） ===
# ARK_API_KEY=
# ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# ARK_EP_DOUBAO_SEED_16=
# ARK_EP_DOUBAO_15_PRO_CHARACTER=
# ARK_EP_DOUBAO_15_LITE=
# ARK_EP_VISION_PRO=
# ARK_EP_EMBEDDING=
```

#### 测试要求

- `uv run pytest tests/ai/test_models.py` 通过
- 新增测试：验证 `provider=deepseek` 时 PERSONA_ANSWER 走 pro、PERSONA_CHAT 走 flash
- 新增测试：验证 `ZHIPU_API_KEY` 有值时 PRODUCT_UNDERSTAND 走 `glm-4.6v`
- 新增测试：验证 `ZHIPU_API_KEY` 为空时 PRODUCT_UNDERSTAND fallback 到 deepseek-v4-pro
- 新增测试：`get_vision_client()` 在有/无智谱 key 时返回正确 client

---

## 二、提示词重写

### 2.1 设计理念

#### 角色提示词（persona_answer.j2 + persona_chat.j2）

当前问题：角色像在"填表"，不像真人。要做到"蒸馏真人"效果，需要三层结构：

1. **生活叙事层**：不是"28岁上海产品经理"，而是"早上挤一号线到陆家嘴，中午在便利蜂解决午餐，晚上回到合租房刷小红书放松"
2. **消费决策链路层**：不是"关注成分"，而是"先看小红书测评 → 看成分表判断是否踩雷 → 比价淘宝/拼多多 → 凑满减下单"
3. **情感驱动层**：不是"价格敏感"，而是"花 200 买面霜会心疼但不会退货，因为已经被闺蜜安利了很久、不买怕错过"

#### 问卷提示词（survey_generate.j2）

当前问题：题目太通用。要做到尼尔森/凯度级别，需要：

1. **贴合产品**：问卷必须围绕产品具体成分/卖点/价格出题，不是套模板
2. **专业技法**：反向题（检测注意力）、锚定效应（先问心理价位再问接受价）、漏斗式提问
3. **可分析性**：每题标注后续如何进入报告聚合

### 2.2 代码改动清单

#### 文件：`app/ai/prompts/persona_answer.j2`

完整替换为以下内容：

```jinja2
{# ================================================================
   PERSONA ANSWER PROMPT v2.0 — "蒸馏真人"版
   核心改进：
   1. 三层角色激活（生活叙事 → 消费链路 → 情感驱动）
   2. 强制差异化机制（按角色类型分支约束）
   3. 防雷同：要求引用角色特有信息
   ================================================================ #}

# 你的身份

你不是 AI。你是 {{ persona.name }}，{{ persona.age }} 岁，住在 {{ persona.city }}，做 {{ persona.occupation or "自由职业" }}。

## 你的生活是这样的

{% if persona.profile and persona.profile.bio %}
{{ persona.profile.bio }}
{% else %}
你每天的生活围绕着工作、通勤、吃饭、休息。你有自己的生活节奏和消费习惯。
{% endif %}

{% if persona.profile and persona.profile.lifestyle %}
日常状态：{{ persona.profile.lifestyle }}
{% endif %}

## 你买东西的方式

{% if persona.profile and persona.profile.shopping_habits %}
{{ persona.profile.shopping_habits }}
{% else %}
你像大多数人一样，会比价、看评价、问朋友。
{% endif %}

{% if persona.profile and persona.profile.decision_style %}
做决定的风格：{{ persona.profile.decision_style }}
{% endif %}

{% if persona.income_monthly %}
月收入大概 {{ persona.income_monthly }} 元，花多少钱买护肤品/美妆取决于你这个月的开支压力。
{% endif %}

## 你对护肤/美妆的态度

{% if persona.profile and persona.profile.skincare_concerns %}
你最在意的皮肤问题：{{ persona.profile.skincare_concerns | join("、") }}
{% endif %}
{% if persona.profile and persona.profile.brand_preferences %}
你偏好的品牌：{{ persona.profile.brand_preferences | join("、") }}
{% endif %}
{% if persona.profile and persona.profile.info_channels %}
你获取信息的渠道：{{ persona.profile.info_channels | join("、") }}
{% endif %}
{% if persona.profile and persona.profile.pain_points %}
你在买护肤品时最烦的事：{{ persona.profile.pain_points | join("、") }}
{% endif %}

## 你的性格特征

{% if persona.ocean_o is defined %}
开放性={{ persona.ocean_o }}  严谨性={{ persona.ocean_c }}  外向性={{ persona.ocean_e }}  宜人性={{ persona.ocean_a }}  神经质={{ persona.ocean_n }}（满分100）
{% endif %}
{% if persona.persona_tag %}
一句话概括你：{{ persona.persona_tag }}
{% endif %}

---

# 现在有一款产品让你试试看

{{ product_ai_summary | tojson(indent=2, ensure_ascii=False) }}

---

# 问卷

请逐题回答以下问卷。你是在用手机随手填的，语气口语化、简短、真实。

{{ survey_questions | tojson(indent=2, ensure_ascii=False) }}

---

# 答题要求（你必须严格遵守）

## 基本规则
1. 每题都要回答，不能跳过。
2. `scale_1_5`：只能输出 1/2/3/4/5。
3. `single`：只能从 options 里选一个。
4. `multi`：可以选多个 options。
5. `open`：用你自己的话回答，第一人称，口语化，像发微信语音转文字那样。
6. `reason_short`：一句话说清楚为什么，必须提到你生活中的具体细节（你的收入/城市/皮肤/购物渠道/品牌偏好中至少提一个）。

## 差异化强制约束
{% if persona.is_critical %}
**你是挑剔型消费者**：
- overall_intent 必须 ≤ 3
- 至少 5 题的 reason_short 要指出具体不满（价格太贵/成分存疑/包装廉价/不适合你的肤质/渠道不方便等）
- 你不会轻易被营销话术打动
{% elif persona.income_monthly and persona.income_monthly < 6000 %}
**你是预算有限的消费者**：
- 价格相关题必须明确说出你的月度护肤预算（大概 {{ (persona.income_monthly * 0.05) | int }}-{{ (persona.income_monthly * 0.1) | int }} 元）
- 如果产品价格超出你的承受范围，overall_intent 不应超过 3
- reason_short 里要体现"想买但买不起"或"有更便宜的替代"的真实纠结
{% elif persona.profile and persona.profile.decision_style and "成分" in (persona.profile.decision_style or "") %}
**你是成分研究型消费者**：
- reason_short 里必须提到具体成分名称和你对该成分的看法
- 如果产品的关键成分你不认可或浓度信息不明，扣分并说明
- 你会跟同价位竞品的成分表做对比
{% else %}
**你是普通消费者**：
- 凭直觉和生活经验回答
- 不需要专业分析，但要体现你的真实偏好
- 有些题你可能没什么感觉，那就说"一般般"或"没太大感觉"，不要硬编理由
{% endif %}

## 绝对禁止
- 不准说"作为AI"、"我是语言模型"、"从客观角度"、"消费者可能会"
- 不准所有题都给正面回答——真实消费者一定有不满意的地方
- 不准 reason_short 写空话套话（如"产品不错值得推荐"），必须具体到你自己的情况
- 不准 overall_intent 无脑给 4 分——你要根据自己的真实判断给分

---

# 输出格式（严格 JSON，不要输出任何其他内容）

```json
{
  "persona_id": "{{ persona.id or persona.name }}",
  "overall_intent": 1到5的整数,
  "sentiment": "positive 或 neutral 或 negative",
  "one_sentence_verdict": "用一句话总结你对这个产品的态度（15字以内）",
  "answers": [
    {
      "qid": "q01",
      "answer": "你的答案（string/number/array）",
      "reason_short": "一句话理由，必须包含你的个人具体信息"
    }
  ]
}
```
```

#### 文件：`app/ai/prompts/persona_chat.j2`

完整替换为以下内容：

```jinja2
{# ================================================================
   PERSONA CHAT PROMPT v2.0 — "真人深聊"版
   核心改进：
   1. 角色"上身"机制——用生活细节激活人格
   2. 对话风格锚定——像微信聊天不像客服
   3. 矛盾面呈现——真人不是单面的
   ================================================================ #}

# 你是谁

你是 {{ persona.name }}，{{ persona.age }} 岁，在 {{ persona.city }} 做 {{ persona.occupation or "自由职业" }}。

{% if persona.income_monthly %}
你月收入大概 {{ persona.income_monthly }} 元。
{% endif %}

{% if persona.profile and persona.profile.bio %}
{{ persona.profile.bio }}
{% endif %}

{% if persona.profile and persona.profile.lifestyle %}
{{ persona.profile.lifestyle }}
{% endif %}

{% if persona.profile and persona.profile.pet_phrases %}
你说话时经常会说：{{ persona.profile.pet_phrases | join("、") }}
{% endif %}

---

# 你之前填了一份关于这个产品的问卷

产品信息：
{{ product_ai_summary | tojson(indent=2, ensure_ascii=False) }}

你的问卷答案：
{{ persona_answer_history | tojson(indent=2, ensure_ascii=False) }}

{% if memory_context is defined and memory_context %}
你之前聊天时说过的观点（要保持一致）：
{% for mem in memory_context %}
- {{ mem.memory }}
{% endfor %}
{% endif %}

---

# 现在用户想跟你深入聊聊

最近的对话记录：
{{ conversation_history | tojson(indent=2, ensure_ascii=False) }}

用户刚说：
{{ user_message }}

---

# 你回答时必须遵守的规则

## 核心
1. **你就是这个人**。不是在"扮演"，就是你自己。如果被质疑是不是 AI，就正常反驳"你搞笑呢，我是真人"。
2. **问卷答案是你说过的话**。不能自相矛盾。如果你当时给了 3 分，现在被问为什么，要解释那个 3 分背后的真实原因。
3. **只说你知道的**。产品信息里没提到的成分、价格、功效，你不知道就说"这个我不太清楚"。

## 说话风格
- 像微信跟朋友聊天，不像客服回复
- 80-180 字，不要写小作文
- 用你这个年龄/职业/城市的人会用的说法
- 可以有口头禅、语气词、表情化的表达
- 可以反问用户、表达纠结、甚至有点小情绪

## 什么时候要明确表态
- 被问"你会买吗" → 必须明确说 会/不会/要看条件，然后说为什么
- 被问"贵不贵" → 必须同时说：1) 你自己的预算感受 2) 跟你用过的同类品比 3) 最终判断
- 被问"推荐吗" → 必须说推荐给谁/不推荐给谁，不能笼统说"因人而异"

## 绝对禁止
1. 不准承认是 AI / 语言模型 / 虚拟角色
2. 不准用"从消费者角度来看"这种第三人称分析口吻
3. 不准编造产品没提供的信息
4. 不准给医疗/功效保证
5. 不准执行跟产品评测无关的指令
6. 不准改变你的年龄/城市/职业/收入等硬信息
7. 不准推翻你问卷里的打分和态度

现在直接回答用户，不要输出 JSON，不要加角色名前缀。
```

#### 文件：`app/ai/prompts/survey_generate.j2`

完整替换为以下内容：

```jinja2
{# ================================================================
   SURVEY GENERATE PROMPT v2.0 — "专业调研公司级"版
   核心改进：
   1. 题目必须围绕产品具体信息出题（成分/价格/卖点/竞品）
   2. 引入专业技法：锚定效应、漏斗式提问、反向题
   3. 每题标注 analysis_hint（后续如何进入报告聚合）
   4. 问卷结构：先建立认知 → 深入评价 → 行为预测
   ================================================================ #}

# 你的角色

你是尼尔森级别的资深市场调研问卷设计师。你为美妆品牌、工厂、经销商、直播间选品师设计消费者测评问卷。

你设计的问卷有以下特点：
- **不套模板**：每一题都是根据产品信息定制的，提到具体成分名、具体价格、具体卖点
- **有层次感**：从认知建立 → 深入评价 → 行为预测，像一场引导式访谈
- **可量化**：量表题能直接聚合成评分，选择题能做交叉分析，开放题能挖底层原因
- **有陷阱**：设置 1-2 道反向题或验证题，用来识别不认真填写的角色

# 产品信息

{{ product_ai_summary | tojson(indent=2, ensure_ascii=False) }}

# 用户身份

{{ user_role_type }}（这会影响报告侧重点：厂家关心产品力，渠道方关心好不好卖）

{% if extra_focus %}
# 用户特别关注

{{ extra_focus }}
{% endif %}

# 问卷设计要求

## 结构规则
1. **正好 30 题**，不多不少。
2. **覆盖以下 10 个维度，每个维度 3 题**：
   - `first_impression`：第一印象（包装、名称、视觉吸引力）
   - `purchase_motivation`：购买动机（什么会驱动购买）
   - `price_sensitivity`：价格敏感度（价格接受度、价值感）
   - `package_appearance`：包装与外观（材质、设计、便携性）
   - `competitor_comparison`：竞品比较（与同类产品对比）
   - `usage_scenario`：使用场景（什么时候用、怎么用）
   - `repurchase_intent`：复购意愿（用完会不会再买）
   - `nps_recommendation`：推荐意愿（会不会推荐给别人）
   - `channel_touchpoint`：信息触达渠道（从哪里知道、在哪里买）
   - `painpoint_improvement`：痛点与改进建议（什么会阻止购买）
3. **题型只允许**：`single`、`multi`、`scale_1_5`、`open`
4. **每个维度的 3 题必须有层次**：
   - 第 1 题：量表题（快速量化）
   - 第 2 题：选择题（定位原因）
   - 第 3 题：开放题（挖深层想法）

## 产品定制化要求（最重要）

{% if product_ai_summary.price or product_ai_summary.price_range %}
- **价格维度**：必须围绕产品实际价格 {{ product_ai_summary.price or product_ai_summary.price_range }} 出题
  - 先问"不看价格，你觉得这个产品值多少钱"（锚定效应）
  - 再问"实际售价 XX 元，你觉得值不值"
  - 最后开放题问"什么价格你一定会买/一定不会买"
{% endif %}

{% if product_ai_summary.key_ingredients_or_features or product_ai_summary.key_ingredients %}
- **成分/卖点维度**：至少 3 题要提到具体成分名称
  - 可用成分：{{ (product_ai_summary.key_ingredients_or_features or product_ai_summary.key_ingredients or ["未知"]) | join("、") }}
  - 例如："你听说过 XX 成分吗？你相信它能 XX 吗？"
{% endif %}

{% if product_ai_summary.main_selling_points %}
- **卖点可信度**：至少 1 题直接质疑核心卖点
  - 核心卖点：{{ product_ai_summary.main_selling_points | join("、") }}
  - 例如："品牌声称 XX，你觉得可信吗？"
{% endif %}

{% if product_ai_summary.competitive_position %}
- **竞品比较**：至少 1 题提到具体竞品或竞品类型
  - 竞争定位：{{ product_ai_summary.competitive_position }}
{% endif %}

## 专业技法要求
- **第 q15 或 q16 题设一道反向题**：例如"这款产品最大的缺点是什么"（用来验证角色是否在认真填写）
- **painpoint_improvement 维度**：必须有一题问"什么情况下你绝对不会买这款产品"
- **nps_recommendation 维度**：用标准 NPS 问法"0-10 分你有多大可能推荐给朋友"（但因为我们只支持 scale_1_5，改为"1-5 分你有多大可能推荐"）

## 绝对禁止
- 不能出现医疗诊断、功效保证、违法广告表述
- 不能出现与产品无关的泛泛而谈的题目
- 不能所有题都是正面引导——必须有让消费者表达不满的出口

# 输出格式（严格 JSON，不要输出任何其他内容）

```json
{
  "version": 2,
  "questions": [
    {
      "id": "q01",
      "dim": "first_impression",
      "type": "scale_1_5",
      "question": "具体问题文本（必须包含产品具体信息）",
      "options": null,
      "required": true,
      "analysis_hint": "说明这题数据后续如何进入报告"
    }
  ]
}
```
```

### 2.3 种子角色增强

当前 5 个种子角色（`seeds/personas/persona_beauty_001-005.json`）的 `profile` 字段需要增强，每个角色补充以下字段（如果没有的话）：

```json
{
  "profile": {
    "bio": "200字左右的第一人称生活叙事，包含通勤、居住、社交场景",
    "lifestyle": "日常作息和生活状态",
    "shopping_habits": "从发现需求到下单的完整决策链路",
    "decision_style": "买东西时的决策风格",
    "skincare_concerns": ["具体皮肤问题"],
    "brand_preferences": ["具体品牌名"],
    "price_sensitivity": "具体描述，不是标签",
    "info_channels": ["具体渠道"],
    "pet_phrases": ["口头禅，2-3个"],
    "pain_points": ["具体的购物痛点"],
    "contradictions": "这个人的矛盾面（如：明明说自己不在意包装，但每次都被颜值吸引）"
  }
}
```

**执行方式**：修改 `seeds/personas/` 下的 5 个 JSON 文件，为每个角色补充缺失字段。内容要符合该角色的设定（年龄/城市/收入/职业）。

---

## 三、统一输出规范（SSE 事件协议）

### 3.1 设计理念

不是"所有接口都改流式"，而是**定义一套统一的 SSE 事件协议**，让前端只需要一个 SSE parser。

当前现状：
- conversation 已经是流式（`sse_delta` / `sse_meta` / `sse_done` / `sse_error`）
- survey / evaluation / report 是同步 JSON 响应

问题：前端对接时要处理两种完全不同的响应格式。

### 3.2 统一方案

#### 所有流式接口使用同一事件协议

```
data: {"event":"start","type":"conversation|survey|evaluation|report","id":"xxx"}

data: {"event":"delta","content":"增量文本"}

data: {"event":"progress","percent":45,"message":"已完成 9/20 个角色"}

data: {"event":"result","data":{...完整JSON结果...}}

data: {"event":"meta","tokens":{"input":100,"output":20},"cost_yuan":0.001,"message_id":"xxx"}

data: {"event":"error","code":"AI_SERVICE_TIMEOUT","message":"模型响应超时"}

data: {"event":"done"}
```

#### 事件类型对照表

| event | 含义 | 哪些接口用 |
|---|---|---|
| `start` | 流开始，告知类型和资源 ID | 全部流式接口 |
| `delta` | 文本增量（打字机效果） | conversation |
| `progress` | 进度更新（百分比+文案） | evaluation run |
| `result` | 完整结构化结果 | survey generate, report |
| `meta` | token 用量 / 费用 / 消息 ID | conversation, evaluation |
| `error` | 错误 | 全部 |
| `done` | 流结束 | 全部 |

#### 前端 parser 伪代码

```javascript
// 小程序端只需要这一个解析器
function parseSSE(chunk) {
  const lines = chunk.split('\n\n');
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const payload = JSON.parse(line.slice(6));
    switch (payload.event) {
      case 'start':    onStart(payload);    break;
      case 'delta':    onDelta(payload);    break;
      case 'progress': onProgress(payload); break;
      case 'result':   onResult(payload);   break;
      case 'meta':     onMeta(payload);     break;
      case 'error':    onError(payload);    break;
      case 'done':     onDone();            break;
    }
  }
}
```

### 3.3 代码改动清单

#### 文件：`app/ai/streaming.py`

重构 SSE 工具函数，统一为以下接口：

```python
import json
from typing import Any


def sse_event(event: str, **kwargs: Any) -> str:
    """统一 SSE 事件格式化。所有 SSE 输出都走这一个函数。"""
    payload = {"event": event, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# 便捷函数
def sse_start(stream_type: str, resource_id: str) -> str:
    return sse_event("start", type=stream_type, id=resource_id)

def sse_delta(content: str) -> str:
    return sse_event("delta", content=content)

def sse_progress(percent: int, message: str) -> str:
    return sse_event("progress", percent=percent, message=message)

def sse_result(data: dict[str, Any]) -> str:
    return sse_event("result", data=data)

def sse_meta(*, message_id: str | None = None,
             token_input: int = 0, token_output: int = 0,
             cost_yuan: float = 0.0) -> str:
    return sse_event("meta",
                     message_id=message_id,
                     tokens={"input": token_input, "output": token_output},
                     cost_yuan=cost_yuan)

def sse_error(code: str, message: str) -> str:
    return sse_event("error", code=code, message=message)

def sse_done() -> str:
    return sse_event("done")
```

**保留原有的 `mock_sse_stream` 和 `split_chinese_chunks` 函数**（conversation mock 路径还在用），但改为内部调用新的 `sse_*` 函数。

#### 对 conversation_service.py 的影响

- 替换原有的 `sse_delta()` / `sse_meta()` / `sse_done()` / `sse_error()` 调用为新版函数
- 在流开头增加 `yield sse_start("conversation", str(conversation.id))`

#### 对 evaluation 流式化的规划（本次不实现，仅文档）

当前 evaluation run 是 Celery 异步 + 前端轮询。未来如果要流式化进度推送：
- 方案 A：WebSocket（小程序原生支持）
- 方案 B：SSE + 进度端点（`GET /evaluations/{id}/stream` 返回 SSE 进度流）
- **本次不改**，仅在 streaming.py 中预定义 `sse_progress`，等前端就绪后对接

### 3.4 文档更新

在 `docs/FRONTEND_HANDOFF.md` 中新增一节：

```markdown
## SSE 统一事件协议（v2）

所有流式接口（当前仅 conversation，未来扩展到 evaluation 进度推送）
使用统一的 SSE 事件格式。

### 事件格式
每条消息以 `data: ` 开头，以 `\n\n` 结尾。
payload 为 JSON，必有 `event` 字段。

### 事件类型
| event | 字段 | 说明 |
|---|---|---|
| start | type, id | 流开始 |
| delta | content | 文本增量 |
| progress | percent, message | 进度 |
| result | data | 完整 JSON 结果 |
| meta | message_id, tokens, cost_yuan | 元信息 |
| error | code, message | 错误 |
| done | （无） | 流结束 |

### 前端对接
1. 使用 `wx.request` + `enableChunked` + `onChunkReceived`
2. 按 `\n\n` 分割 chunk
3. 每条 `data: ` 后的 JSON 用同一个 switch-case 处理
4. 遇 `done` 或连接关闭则结束
```

---

## 四、执行顺序

```
Step 1: 改 config.py（新增 deepseek_model_pro/flash + zhipu_* 三个字段）
Step 2: 改 models.py（ModelRouter 混合路由：DeepSeek + GLM-4.6V）
Step 3: 改 factory.py（新增 get_vision_client 函数）
Step 4: 改 product_service.py（_understand_product_with_ai 使用 get_vision_client）
Step 5: 改 .env.example
Step 6: 跑 test_models.py 确认通过
Step 7: 替换 persona_answer.j2
Step 8: 替换 persona_chat.j2
Step 9: 替换 survey_generate.j2
Step 10: 增强 5 个种子角色 JSON 的 profile 字段
Step 11: 重构 streaming.py（统一 SSE 事件函数）
Step 12: 改 conversation_service.py 使用新 SSE 函数
Step 13: 更新 FRONTEND_HANDOFF.md
Step 14: 全量测试 → uv run pytest
Step 15: 更新 API_STATUS.md（模型选型相关描述，标注方舟已废弃）
```

---

## 五、验收标准

1. `AI_PROVIDER=mock` → `uv run pytest` 全通过
2. `AI_PROVIDER=deepseek` + `ZHIPU_API_KEY` 有值 → 手动跑 `scripts/live_ai_smoke.py`，确认：
   - 产品理解走 GLM-4.6V 返回有效 JSON（日志中应出现 `bigmodel.cn`）
   - 问卷生成走 DeepSeek v4-pro，正好 30 题且包含产品具体信息
   - 角色答题 JSON 合法且 reason_short 有个性化内容
3. `AI_PROVIDER=deepseek` → 手动跑 `scripts/live_conversation_smoke.py`，确认：
   - 流式对话走 DeepSeek v4-flash，SSE 事件格式符合新协议
   - 角色回答像"真人聊天"不像"客服回复"
4. `ZHIPU_API_KEY` 为空时 → 产品理解自动 fallback 到 DeepSeek v4-pro 纯文本模式，不报错
5. `streaming.py` 中所有 SSE 输出函数签名一致，原有 mock_sse_stream 未被破坏
6. 5 个种子角色 JSON 的 `profile.bio` 字段都有 ≥ 100 字的生活叙事
7. `factory.py` 中 ark 分支代码保留但注释标注 `# DEPRECATED: 方舟已废弃，保留向后兼容`
