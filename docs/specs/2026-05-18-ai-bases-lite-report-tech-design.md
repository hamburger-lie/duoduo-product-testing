# 技术实现文档：AI 产品理解 + BASES-lite 测品报告

**创建日期**：2026-05-18  
**文档状态**：新版技术草案  
**关联需求**：[2026-05-18-ai-bases-lite-report-requirement.md](./2026-05-18-ai-bases-lite-report-requirement.md)

---

## 1. 总体架构

```text
小程序产品输入
  ↓
ProductService
  ↓
AI 产品理解快照生成
  ↓
Product.ai_summary / research_snapshot 持久化
  ↓
SurveyService 基于产品快照生成问卷
  ↓
EvaluationService 组织角色答题
  ↓
Answer 表保存所有角色回答
  ↓
ReportService 计算确定性 metrics
  ↓
ReportService 调用 report_synthesize 大模型聚类报告洞察
  ↓
BusinessReportResponse
  ├── 小程序未导出报告
  └── PDF 独立白皮书模板
        ↓
      用户导出 PDF
        ↓
      上传后端 /static/reports/{user_id}/...
```

核心原则：

- 大模型负责“理解、聚类、解释、建议”。
- 后端负责“样本数、分数、分布、图表数据、PDF 存储”。
- 小程序和 PDF 共用同一份 business report 数据。
- AI 失败时允许规则兜底，但不能影响已有报告可用性。

---

## 2. 现有系统基础

### 2.1 后端

后端位于：

```text
D:\soul\backend\backend
```

关键模块：

| 模块 | 现状 |
|---|---|
| `app/services/product_service.py` | 创建产品并生成 AI 产品理解 |
| `app/services/survey_service.py` | 根据产品生成问卷 |
| `app/services/evaluation_service.py` | 角色答题与 evaluation 状态 |
| `app/services/report_service.py` | 报告生成、business report、PDF 存储 |
| `app/ai/prompts/report_synthesize.j2` | 已存在报告聚类提示词 |
| `app/ai/client.py` | OpenAI-compatible DeepSeek / Ark / Mock client |
| `app/ai/models.py` | `TaskType.REPORT_SYNTHESIZE` 模型路由 |

### 2.2 小程序

关键模块：

| 模块 | 作用 |
|---|---|
| `miniprogram/pages/report/report.ts` | 未导出报告数据构建、雷达图绘制、导出入口 |
| `miniprogram/pages/report/report.wxml` | 报告页结构 |
| `miniprogram/pages/report/report.wxss` | 报告样式 |
| `miniprogram/pages/report-pdfs/` | 我的调研报告 PDF 列表 |
| `miniprogram/services/api.ts` | API 适配 |

### 2.3 PDF 模板

当前 PDF 专用页面：

```text
D:\AI报告生成模板工具\public\bases-report.html
```

该页面通过 WebView 打开，读取 business report、evaluation 和 product 数据，渲染白皮书式页面并使用 `jsPDF + html2canvas` 导出 PDF。

---

## 3. 数据模型设计

### 3.1 Product.ai_summary 扩展

当前 `products.ai_summary` 已用于产品理解。新版可在不新增表的前提下扩展字段：

```json
{
  "main_selling_points": ["温和修护", "提亮肤色"],
  "key_ingredients": ["烟酰胺", "神经酰胺"],
  "suitable_skin_types": ["敏感肌", "干皮"],
  "target_audience": "关注成分透明的一二线白领",
  "competitive_position": "温和功效型日常护肤",
  "category_hypothesis": "护肤 / 修护精华",
  "use_scenarios": ["通勤前护肤", "换季修护"],
  "substitute_solutions": ["普通保湿乳", "高功效美白精华"],
  "purchase_barriers": ["担心刺激", "不相信提亮效果", "价格理由不足"],
  "claim_hypotheses": ["温和提亮", "屏障修护", "敏感肌友好"],
  "validation_questions": ["可信证明是否足够", "价格是否被接受", "哪类人群更愿意尝试"],
  "source_note": "基于用户输入和 AI 品类知识生成，不代表真实市场数据。"
}
```

### 3.2 未来可选：ProductResearchSnapshot 表

如果后续需要版本化产品理解快照，可新增表：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT | 主键 |
| product_id | BIGINT | 产品 |
| snapshot | JSONB | 产品理解快照 |
| model | string | 使用模型 |
| prompt_version | string | prompt 版本 |
| created_at | datetime | 生成时间 |

当前阶段优先复用 `Product.ai_summary`，避免增加迁移复杂度。

### 3.3 Report.metrics

`reports.metrics` 保持确定性统计结果。

主要结构：

```json
{
  "overall_intent": {
    "average": 3.5,
    "distribution": [
      {"score": 1, "count": 0},
      {"score": 2, "count": 0},
      {"score": 3, "count": 1},
      {"score": 4, "count": 1},
      {"score": 5, "count": 0}
    ],
    "nps": -50
  },
  "dimensions_radar": [
    {"dim": "painpoint_improvement", "score": 4.1}
  ],
  "price_sensitivity": {
    "median_acceptable_price": 159,
    "distribution": [
      {"range": "0-100", "count": 0},
      {"range": "100-200", "count": 2}
    ]
  },
  "segment_intent": [
    {"segment": "成分党", "count": 1, "avg_intent": 4.0}
  ]
}
```

### 3.4 BusinessReportResponse

Business report 对前端输出：

- `executive_summary`：AI 聚类洞察
- `decision_suggestion`：AI 结合 metrics 给出决策
- `metrics`：后端确定性统计，不由 AI 覆盖
- `top_pros`：AI 聚类机会点
- `top_cons`：AI 聚类风险点
- `target_audience`：AI 总结人群
- `marketing_copy_angles`：AI 生成话术角度
- `next_test_recommendations`：AI 生成下一步策略

---

## 4. 服务层设计

### 4.1 ProductService

职责：

- 保存产品基础信息和图片。
- 调用产品理解 prompt。
- 将产品理解快照写入 `Product.ai_summary`。

实现要求：

- 产品理解不联网。
- DeepSeek / Ark 调用通过 `get_ai_client()`。
- AI 失败时写入 mock / 规则版 summary，产品仍可继续创建。
- `ai_summary.source_note` 必须说明内容来源限制。

### 4.2 SurveyService

职责：

- 读取产品基础信息和 `ai_summary`。
- 将产品理解快照输入 `survey_generate.j2`。
- 生成更贴合当前产品的问卷。

要求：

- 问卷必须覆盖 BASES-lite 关键维度：
  - 购买意愿
  - 相关性
  - 差异化
  - 可信度
  - 优势感
  - 价值感
  - 卖点选择
  - 疑虑选择
  - 开放建议

### 4.3 EvaluationService

职责：

- 组织选定角色答题。
- 每个角色答题 prompt 输入：
  - 产品基础信息
  - 产品理解快照
  - 角色画像
  - 问卷题目

要求：

- `Answer.overall_intent` 使用 1–5 分。
- 每个 answer item 保留 `qid`、`type`、`answer`、`reason`。
- 开放题和 reason 是后续 AI 聚类报告的主要素材。

### 4.4 ReportService

职责分两层：

#### 4.4.1 确定性统计层

函数：

- `_calc_overall_intent`
- `_calc_dimensions_radar`
- `_calc_price_sensitivity`
- `_calc_segment_intent`
- `_calc_top_pros`
- `_calc_top_cons`

这些函数只从数据库记录计算，不调用 AI。

#### 4.4.2 AI 聚类报告层

新增 / 已接入函数：

- `_build_ai_business_response`
- `_merge_ai_business_data`
- `_product_summary_for_prompt`
- `_answers_for_prompt`
- `_business_template_for_prompt`

流程：

```text
get_or_create_business_report
  ↓
get_or_create_report 得到确定性 ReportResponse
  ↓
加载 evaluation / product / survey / answers / personas
  ↓
render_prompt("report_synthesize")
  ↓
get_ai_client().complete_json(...)
  ↓
parse_json_response
  ↓
validate_required_keys
  ↓
合并 AI 洞察 + 后端确定性 metrics
  ↓
BusinessReportResponse
```

合并规则：

- AI 可以覆盖：
  - `executive_summary`
  - `decision_suggestion`
  - `top_pros`
  - `top_cons`
  - `target_audience`
  - `marketing_copy_angles`
  - `next_test_recommendations`
  - `ai_disclaimer`

- AI 不可以覆盖：
  - `metrics.overall_intent_avg`
  - `metrics.nps`
  - `metrics.intent_distribution`
  - `metrics.dimension_scores`
  - `metrics.price_sensitivity`
  - `metrics.persona_segments`

如果 AI 失败，回退 `_build_business_response` 规则版报告。

---

## 5. Prompt 设计

### 5.1 product_understand.j2

输入：

- 产品描述
- 产品图片 URL
- 品牌
- 价格
- 目标渠道

输出：

- 产品一句话定义
- 品类和场景
- 目标人群假设
- 替代方案
- 核心卖点
- 购买阻力
- 需要验证的问题
- 来源限制说明

### 5.2 survey_generate.j2

输入：

- 产品基础信息
- 产品理解快照
- 用户额外关注点

输出：

- 10–30 道问卷题
- 每题带 `dim`
- 类型为 `single`、`multi`、`scale_1_5`、`open`

### 5.3 persona_answer.j2

输入：

- 产品基础信息
- 产品理解快照
- 角色画像
- 问卷

输出：

- 完整答题 JSON
- `overall_intent`
- `sentiment`
- `summary_comment`

### 5.4 report_synthesize.j2

输入：

- 产品理解快照
- 问卷
- 全部角色回答
- 规则版 report template
- 确定性 metrics

输出：

- business report JSON
- 洞察必须引用角色回答或具体数据
- 不允许捏造真实市场数据
- 不允许捏造 evidence quotes
- metrics 可输出但后端不会信任其覆盖

---

## 6. BASES-lite 指标计算

### 6.1 后端确定性计算

后端计算：

```text
Top2Box = (4分人数 + 5分人数) / 有效答题人数 × 100
```

NPS 计算：

```text
Promoter = 5分人数
Detractor = 1分 + 2分 + 3分人数
NPS = (Promoter / total - Detractor / total) × 100
```

维度分：

```text
维度分 = 同 dim 下 scale_1_5 分数均值
```

### 6.2 前端 / PDF BASES-lite 映射

当后端问卷维度不足时，前端和 PDF 使用 BASES-lite 六维兜底：

| BASES-lite 维度 | 映射来源 |
|---|---|
| Top2Box | intent_distribution |
| 差异化 | competitor_comparison / first_impression / package_appearance |
| 相关性 | painpoint_improvement / usage_scenario / purchase_motivation |
| 可信度 | nps_recommendation / repurchase_intent / confidence |
| 优势感 | competitor_comparison / repurchase_intent |
| 价值感 | price_sensitivity |

### 6.3 图表数据保护

必须有测试保证：

```text
如果 AI 返回错误 metrics，例如 intent_distribution 全部为 99，
BusinessReportResponse 仍保留后端真实统计。
```

---

## 7. PDF 生成设计

### 7.1 页面位置

PDF 专用模板：

```text
D:\AI报告生成模板工具\public\bases-report.html
```

小程序 report 页导出入口：

```text
miniprogram/pages/report/report.ts
REPORT_TOOL_REPORT_PATH = "/static/bases-report.html"
```

### 7.2 PDF 数据加载

PDF 页面加载：

```text
GET /api/v1/reports/by-evaluation/{evaluation_id}/business
GET /api/v1/evaluations/{evaluation_id}
GET /api/v1/products/{product_id}
```

用途：

- business report 提供报告洞察和指标
- evaluation 提供 product_id
- product 提供产品图和产品基础信息

### 7.3 PDF 图片规则

```text
if product.image_urls[0] 可访问:
    显示真实产品图
else:
    显示模板化产品视觉占位
```

### 7.4 PDF 导出和上传

```text
html2canvas 渲染每个 page
  ↓
jsPDF 生成 PDF
  ↓
POST /api/v1/reports/by-evaluation/{evaluation_id}/pdf
  ↓
后端保存到 uploads/reports/{user_id}/
  ↓
Report.pdf_url 更新
  ↓
小程序“我的 / 调研报告 PDF”可查看
```

### 7.5 A4 尺寸保护

导出时每个页面必须放入完整 A4 画布，避免短页面被压扁。

---

## 8. 小程序报告页设计

### 8.1 数据构建

`report.ts` 的 `buildVM(raw: BusinessReport)` 负责将 business report 转为页面 VM。

要求：

- `compositeScore` 使用 BASES-lite 六维分。
- `radarData` 优先用后端真实维度。
- 如果真实维度少于 3 个，用 BASES-lite 六维兜底。
- `personaChips` 来自 `metrics.persona_segments`。
- `consumerVm` 来自原始 report 和角色 answer。

### 8.2 雷达图显示

要求：

- 小程序中雷达图居中。
- 画布尺寸合理。
- 图例不挤压图表。
- PDF 中雷达图放入独立图表面板。

### 8.3 PDF 列表入口

“我的”页保留常用功能，其中包含：

- 调研报告 PDF

页面：

```text
miniprogram/pages/report-pdfs/
```

打开 PDF：

```text
wx.downloadFile
wx.openDocument({ fileType: "pdf", showMenu: true })
```

---

## 9. API 设计

### 9.1 获取原始报告

```http
GET /api/v1/reports/by-evaluation/{evaluation_id}
```

返回：

- 原始 ReportResponse
- 适合角色反馈、基础统计和兼容旧页面

### 9.2 获取 business report

```http
GET /api/v1/reports/by-evaluation/{evaluation_id}/business
```

行为：

- 若 report 不存在，先生成确定性 report。
- 再尝试 AI 聚类 business report。
- AI 成功：返回差异化洞察 + 确定性 metrics。
- AI 失败：返回规则兜底 business report。

### 9.3 上传 PDF

```http
POST /api/v1/reports/by-evaluation/{evaluation_id}/pdf
Content-Type: multipart/form-data
file: report.pdf
```

校验：

- 文件必须以 `%PDF` 开头。
- evaluation 必须属于当前用户。

返回：

```json
{
  "report_id": "string",
  "evaluation_id": "string",
  "pdf_url": "/static/reports/{user_id}/evaluation_xxx.pdf"
}
```

### 9.4 列出 PDF

```http
GET /api/v1/reports/pdfs
```

返回当前用户已生成并存储的 PDF。

---

## 10. 错误与兜底策略

| 场景 | 处理 |
|---|---|
| 产品理解 AI 失败 | 写入规则版 `ai_summary`，产品仍可创建 |
| 问卷生成 AI 失败 | 使用种子问卷模板 |
| 角色答题部分失败 | 报告只统计完成答题的角色 |
| report_synthesize AI 失败 | 返回规则版 business report |
| AI 返回 JSON 非法 | 记录 warning，返回规则版 business report |
| AI 返回错误 metrics | 丢弃 AI metrics，使用后端确定性 metrics |
| 产品图加载失败 | PDF 显示模板占位图 |
| PDF 上传失败 | 本地仍保存 PDF，前端提示同步失败 |

---

## 11. 测试策略

### 11.1 后端测试

新增或维护以下测试：

1. AI 聚类结果进入 business report

```text
fake AI 返回“烟酰胺 / 价格证明 / A/B 测试”
断言 business report 的摘要、机会点、风险点、话术和建议使用 fake AI 内容
```

2. AI metrics 不覆盖后端统计

```text
fake AI 返回 intent_distribution 全部 99
断言返回 metrics 的总人数仍等于实际完成答题人数
```

3. AI 失败兜底

```text
fake AI 抛异常
断言接口仍返回 200 且包含规则版 business report
```

4. PDF 上传

```text
上传以 %PDF 开头的文件
断言 Report.pdf_url 更新
```

运行命令：

```powershell
cd D:\soul\backend\backend
.\.venv\Scripts\python.exe -m pytest tests\test_report.py -q
```

### 11.2 小程序测试

运行：

```powershell
cd D:\soul\miniprogram
npx tsc --noEmit
```

检查：

- report 页类型通过
- API 类型与后端响应一致
- 雷达图数据不足时仍显示 BASES-lite 六维

### 11.3 PDF 模板测试

脚本语法：

```powershell
$env:REPORT_HTML='D:\AI报告生成模板工具\public\bases-report.html'
@'
const fs = require('fs');
const html = fs.readFileSync(process.env.REPORT_HTML, 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]).join('\n');
new Function(scripts);
console.log('script syntax ok');
'@ | node -
```

服务访问：

```powershell
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:5678/static/bases-report.html'
```

预期：

- HTTP 200
- 页面可加载
- 产品图或占位图可显示
- 导出 PDF 不压扁

---

## 12. 实施分阶段

### 阶段 1：锁定数据可信边界

- business report 使用 AI 聚类洞察。
- metrics 永远使用后端确定性统计。
- 增加测试保护。

### 阶段 2：产品理解快照标准化

- 扩展 `Product.ai_summary` 字段。
- 更新 `product_understand.j2`。
- 更新 `survey_generate.j2` 和 `persona_answer.j2` 使用快照。

### 阶段 3：报告体验统一

- 小程序报告页使用 BASES-lite 六维。
- PDF 使用白皮书式模板。
- 图表、图片、样本数统一。

### 阶段 4：质量评估

- 对比 3–5 个不同产品，检查报告差异化。
- 检查 AI 是否出现真实市场数据包装。
- 检查图表是否匹配实际答题人数。

---

## 13. 验收清单

- [ ] 产品输入后可生成 AI 产品理解快照。
- [ ] 问卷生成使用产品理解快照。
- [ ] 角色答题使用产品理解快照。
- [ ] business report 使用 AI 聚类输出差异化洞察。
- [ ] AI 失败时返回规则兜底报告。
- [ ] AI metrics 无法覆盖后端真实统计。
- [ ] 小程序未导出报告雷达图稳定显示。
- [ ] PDF 雷达图位置正确、尺寸不压扁。
- [ ] PDF 产品图优先使用用户上传图。
- [ ] PDF 导出后上传后端并能在“我的”查看。

