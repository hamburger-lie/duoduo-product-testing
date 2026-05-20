# 技术实现文档：测品调研总结报告系统

**关联需求**：[2026-05-16-report-requirement.md](./2026-05-16-report-requirement.md)
**创建日期**：2026-05-16
**文档状态**：草稿

---

## 1. 系统架构概览

```
数据输入层
  ├── 产品基础信息
  ├── 市场调研数据
  ├── 竞品数据
  ├── 测品数据
  ├── 用户反馈数据
  └── 风险数据
        ↓
数据处理层（Python + Pandas）
  ├── 数据清洗
  ├── 指标计算
  └── 评分模型
        ↓
报告生成层
  ├── 可视化数据看板（React / Next.js + ECharts）
  ├── Excel 数据文件（openpyxl）
  └── PPT / PDF 报告（python-pptx / HTML → PDF）
```

---

## 2. 数据输入结构

### 2.1 产品基础信息

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | string | 唯一标识 |
| name | string | 产品名称 |
| category | string | 产品类别 |
| image_url | string | 产品图片 URL |
| product_url | string | 产品链接 |
| target_audience | string | 目标用户描述 |
| use_scenario | string | 使用场景 |
| key_selling_points | list[string] | 核心卖点列表 |
| cost_price | decimal | 成本价（元） |
| suggested_price | decimal | 建议售价（元） |
| gross_margin | float | 毛利率（0–1） |
| supplier | string | 供应商名称 |
| moq | int | 最小起订量 |
| lead_time_days | int | 交期（天） |
| stock_status | string | 库存状态：充足 / 紧张 / 缺货 |

### 2.2 市场调研数据

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | string | 关联产品 |
| search_heat | int | 搜索热度（指数） |
| social_discussion_volume | int | 社媒讨论量 |
| content_platform_heat | int | 内容平台热度 |
| keyword_heat | int | 关键词热度 |
| trend_growth_rate | float | 趋势增长率（%） |
| demand_strength | int | 用户需求强度（1–10） |
| target_audience_size | string | 目标人群规模描述 |
| seasonality | string | 季节性因素描述 |
| market_maturity | string | 市场成熟度：成长期 / 成熟期 / 饱和期 |

### 2.3 竞品数据

| 字段 | 类型 | 说明 |
|------|------|------|
| competitor_id | string | 竞品唯一标识 |
| product_id | string | 关联被测产品 |
| competitor_name | string | 竞品名称 |
| competitor_url | string | 竞品链接 |
| price | decimal | 竞品售价（元） |
| monthly_sales | int | 月销量（件） |
| rating | float | 评分（0–5） |
| review_count | int | 评论数量 |
| positive_keywords | list[string] | 好评关键词 |
| negative_keywords | list[string] | 差评关键词 |
| key_selling_points | list[string] | 核心卖点 |
| material_style | string | 素材风格描述 |
| packaging | string | 包装方式 |
| shipping_days | int | 发货周期（天） |
| after_sale_issues | list[string] | 售后常见问题 |
| market_positioning | string | 市场定位 |

### 2.4 测品数据

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | string | 关联产品 |
| test_period | string | 测试周期（如 2026-04-01 至 2026-04-30） |
| test_channel | string | 测试渠道（如 抖音 / 天猫 / 小红书） |
| impressions | int | 曝光量 |
| clicks | int | 点击量 |
| ctr | float | 点击率（自动计算） |
| favorites | int | 收藏量 |
| favorite_rate | float | 收藏率（自动计算） |
| add_to_cart | int | 加购量 |
| add_to_cart_rate | float | 加购率（自动计算） |
| orders | int | 下单量 |
| conversion_rate | float | 转化率（自动计算） |
| avg_order_value | decimal | 客单价（元） |
| ad_cost | decimal | 广告成本（元） |
| gmv | decimal | 成交金额（元） |
| gross_profit | decimal | 毛利（元） |
| roi | float | ROI（自动计算） |
| material_id | string | 素材 ID |
| material_ctr | float | 素材点击率 |
| material_cvr | float | 素材转化率 |

### 2.5 用户反馈数据

| 字段 | 类型 | 说明 |
|------|------|------|
| feedback_id | string | 反馈唯一标识 |
| product_id | string | 关联产品 |
| source | string | 反馈来源（评论区 / 私信 / 问卷） |
| content | string | 反馈原文 |
| sentiment | string | 情绪：positive / neutral / negative |
| feedback_type | string | 类型：功能 / 外观 / 价格 / 物流 / 质量 / 售后 |
| purchase_motivation | string | 购买动机 |
| main_pain_point | string | 主要痛点 |
| positive_reason | string | 好评原因 |
| negative_reason | string | 差评原因 |
| unpurchased_reason | string | 未购买原因（调研场景） |
| after_sale_issue | string | 售后问题描述 |
| improvement_suggestion | string | 改进建议 |

### 2.6 风险数据

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | string | 关联产品 |
| supply_chain_risk | int | 供应链风险（1–5） |
| quality_risk | int | 质量风险（1–5） |
| logistics_risk | int | 物流风险（1–5） |
| compliance_risk | int | 合规风险（1–5） |
| after_sale_risk | int | 售后风险（1–5） |
| seasonality_risk | int | 季节性风险（1–5） |
| competition_risk | int | 竞争加剧风险（1–5） |
| profit_risk | int | 利润压缩风险（1–5） |
| overall_risk_level | string | 综合风险等级：低 / 中 / 高 |

---

## 3. 数据处理逻辑

### 3.1 数据清洗规则

- 去除 product_id 重复的记录，保留最新一条
- 统一货币单位为人民币元，保留两位小数
- 统一时间格式为 `YYYY-MM-DD`
- 缺失数值字段填 `null`，不以 0 替代（避免影响统计）
- 异常值：点击率 > 50%、转化率 > 30% 等视为异常，标记但不删除
- 统一类目名称（例如：「护肤品」→「护肤」）
- 清洗用户反馈：去除纯广告、不相关内容

### 3.2 指标自动计算

```python
# 测品指标
ctr              = clicks / impressions
favorite_rate    = favorites / impressions
add_to_cart_rate = add_to_cart / clicks
conversion_rate  = orders / clicks
gross_margin     = gross_profit / gmv
roi              = gmv / ad_cost
```

### 3.3 评分模型实现

```python
WEIGHTS = {
    "market_demand":          0.20,
    "competition_strength":   0.15,
    "product_selling_point":  0.15,
    "test_performance":       0.20,
    "profit_margin":          0.15,
    "supply_chain_stability": 0.10,
    "risk_factor":            0.05,
}

def calc_composite_score(scores: dict[str, float]) -> float:
    """每个维度满分 100，返回加权综合得分。"""
    return sum(scores[dim] * weight for dim, weight in WEIGHTS.items())

def get_tier(score: float) -> str:
    if score >= 85: return "重点推进"
    if score >= 70: return "继续优化测试"
    if score >= 60: return "谨慎观察"
    return "暂停 / 淘汰"
```

---

## 4. 图表实现规范

### 4.1 技术选型

| 场景 | 推荐库 |
|------|--------|
| Web 数据看板 | ECharts（主选）/ Recharts |
| Python 脚本生成图片 | Plotly（导出 PNG）/ Matplotlib |
| 嵌入 PPT/Excel | Plotly → PNG → python-pptx / openpyxl |

### 4.2 各图表字段映射

**产品机会四象限图（气泡图）**

```json
{
  "x": "market_demand_score",
  "y": "test_performance_score",
  "bubble_size": "profit_margin_score",
  "color": "overall_risk_level",
  "quadrant_labels": {
    "right_top":    "重点推进",
    "right_bottom": "优化后继续测试",
    "left_top":     "短期机会，谨慎推进",
    "left_bottom":  "暂停 / 淘汰"
  }
}
```

**转化漏斗图路径**

```
曝光量 → 点击量 → 加购量 → 下单量 → 成交金额（GMV）
```

**风险热力图**

- 行：各产品
- 列：supply_chain / quality / logistics / compliance / after_sale / competition
- 颜色：1–2（绿）→ 3（黄）→ 4–5（红）

**产品综合评分排行榜**

- 类型：横向条形图
- 按 composite_score 降序排列
- 超过 85 分标注「重点推进」，低于 60 分标注「暂停」

---

## 5. 报告自动生成逻辑

### 5.1 执行摘要自动生成

```python
def generate_executive_summary(products):
    total_surveyed = len(products)
    total_tested   = len([p for p in products if p.has_test_data])
    tiers = Counter(p.tier for p in products)
    top3 = sorted(products, key=lambda p: p.composite_score, reverse=True)[:3]
    highest_risk = max(products, key=lambda p: p.overall_risk_score)
    # 填入摘要模板
    ...
```

### 5.2 单产品结论文本生成

```python
CONCLUSION_TEMPLATE = """
结论：该产品建议归类为【{tier}】。

数据依据：综合得分 {score:.1f} 分，市场需求 {market:.1f} 分，\
测试表现 {test:.1f} 分，利润空间 {profit:.1f} 分，风险等级【{risk_level}】。

原因分析：{strength_desc}；{weakness_desc}，需重点关注{key_risk}。

行动建议：{action_desc}
"""
```

---

## 6. 输出文件规范

### 6.1 Excel 数据文件（9 个工作表）

| 工作表名称 | 主要内容 |
|-----------|---------|
| 产品基础信息 | 所有产品基础字段 |
| 市场调研数据 | 搜索热度、社媒讨论等 |
| 竞品数据 | 竞品矩阵全量数据 |
| 测品数据 | 各渠道测品指标原始值 |
| 用户反馈 | 原始反馈与情绪分类 |
| 风险评估 | 各维度风险打分 |
| 综合评分 | 7 维度得分 + 综合得分 + 分层结论 |
| 图表数据源 | 供图表引用的结构化数据 |
| 产品分层结果 | 最终四类分层结论汇总 |

### 6.2 数据看板（8 个页面）

| 页面 | 核心图表 |
|------|---------|
| 总览页 | 数据卡片 + 仪表盘 |
| 产品评分页 | 综合评分排行榜 + 雷达图 |
| 四象限机会页 | 气泡四象限图 |
| 竞品对比页 | 竞品矩阵 + 价格区间图 |
| 测品复盘页 | 漏斗图 + 折线趋势图 |
| 用户反馈页 | 痛点分布图 + 词云 |
| 风险评估页 | 风险热力图 + 等级表 |
| 行动计划页 | 甘特图 + 优先级矩阵 |

### 6.3 PPT / PDF 报告

- 使用 `python-pptx` 生成 PPT，再通过 LibreOffice 或 headless Chrome 导出 PDF
- 备选方案：生成 HTML 模板（Jinja2），用 Puppeteer 导出 PDF（更灵活的图表支持）
- 每页结构：**顶部结论 → 中间图表 → 底部数据解读 + 行动建议**

---

## 7. 技术栈汇总

| 层级 | 推荐技术 | 备注 |
|------|---------|------|
| 数据处理 | Python 3.11 + Pandas + NumPy | 清洗、指标计算、评分模型 |
| 图表（Web） | ECharts / Recharts | 数据看板 |
| 图表（离线导出） | Plotly → PNG | 嵌入 PPT / Excel |
| Excel 输出 | openpyxl | 9 张工作表 + 图表插入 |
| PPT 输出 | python-pptx | 结构化幻灯片生成 |
| PDF 导出 | Puppeteer / LibreOffice headless | 从 HTML 或 PPT 转换 |
| 前端看板框架 | Next.js + Tailwind CSS + Shadcn UI | Web 端数据看板 |
| 数据存储（开发阶段） | Excel / CSV 或 SQLite | 按项目规模选择 |
| 数据存储（生产阶段） | Supabase / PostgreSQL | 对接小程序后端 |

---

## 8. 与测品官小程序的集成方案

测品官小程序已有评测结论（`EvaluationAnswerResponse`），可作为本报告「用户反馈」和「产品卖点」部分的数据来源：

| 小程序数据字段 | 映射到报告字段 |
|--------------|--------------|
| `overall_intent`（1–5） | 测品数据 → 用户意向得分 |
| `sentiment` | 用户反馈 → sentiment |
| `summary_comment` | 用户反馈 → content |
| `answers[].answer`（scale_1_5） | 测品数据 → 各维度打分 |
| `persona_snapshot` | 目标用户画像 |
| Report API（`/api/v1/reports/`） | 报告生成入口，供本系统调用 |

后续可在后端新增 `POST /api/v1/reports/{evaluation_id}/export` 接口，触发 Python 报告生成任务，返回 PDF / Excel 下载链接。

---

## 9. 已知风险与限制

| 风险 | 缓解措施 |
|------|---------|
| AI 测品官反馈数据维度有限（缺乏曝光/点击等电商数据） | 报告生成时明确标注「数据来源：AI 模拟调研」，真实电商数据需手动导入 |
| PPT/PDF 图表渲染在服务端较重 | 考虑异步生成 + 任务队列（Celery）+ 下载链接通知 |
| Excel 大数据量时生成较慢 | 超过 500 行时分批写入，启用 `write_only` 模式 |
| 评分模型权重主观 | 提供权重配置接口，支持用户按项目调整 |
