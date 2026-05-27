# 消费者群体热力矩阵 — Design Spec

**Date:** 2026-05-23
**Branch:** feature/report-and-pdf-export
**Replaces:** `rp-seg-cards` 条形卡片区块（消费者群体分布）

---

## 背景与决策

当前"消费者群体分布"面板用条形卡片展示每个群体的"购买意向 4.0/5"，存在一个核心问题：

- 只展示单一维度（购买意向），无法跨维度比较不同群体的表现差异

数值来源：真实调研用户在问卷中对各维度打分（1-5），按 `persona_tag` 分群后取算术均值。改为热力矩阵图，直接使用 `tagScoreMap` 聚合路径，彻底移除近似公式兜底，无数据格子显示 `—`。

---

## 数据结构

### 行：消费群体（最多 5 行）
- 来源：`report.persona_segments`（或等价字段），按 `avg_intent` 降序排列
- 标签：`pickSegmentLabel` 输出（真实 persona_tag 或序号兜底"群体N"）
- 额外最后一行：**全体均值**，取各维度 `dims[i].score`

### 列：调研维度（最多 5 列）
- 来源：`buildHeatmapDimHeaders(dims)` — 取 `dims.slice(0,5)` 的 `dimLabel`
- 示例列名：第一印象 / 购买意向 / 推荐意愿 / 外观包装 / 价格接受度

### 格子内容
| 情况 | 显示 | 样式 |
|---|---|---|
| 有真实答案 | 算术均值，1位小数（如 `3.8`） | 紫色渐变背景 |
| 无真实答案 | `—` | 浅灰背景，文字灰色 |

**移除 `buildHeatmapMatrix` 的近似公式分支**（`d.score + deviation * 0.8`），无数据直接返回 null → 前端渲染 `—`。

---

## 视觉设计

### 配色
- 渐变方向：1.0（低）→ 浅米色 `#F5F3FF` ；5.0（高）→ 深紫 `#7C5CFC`
- 实现方式：CSS 背景色用 `opacity` 或 `rgba(124,92,252, opacity)` 线性映射
- `全体均值` 行：同色系但用虚线上边框区分，字体加粗

### 图例
- 矩阵正下方：一条渐变色条（宽约 80px），左端标 `1`，右端标 `5`
- 标注文字："调研均值（1-5）"

### 尺寸
- 格子最小宽度：列等分，行高约 44px（rpx 适配）
- 行标签区：左侧固定宽度约 160rpx，文字超长截断加省略号
- 列标签：顶部，文字竖排或斜排（小程序限制：优先换行缩短）

---

## 代码改动范围

### report.ts
1. `buildHeatmapMatrix`：移除近似公式分支，无数据格子 `score` 字段设为 `null`
2. `heatmapRows: []` → `heatmapRows: buildHeatmapMatrix(segs, dims, overallAvg, tagMap, answers)`
3. 新增 `heatmapBaselineRow`：`dims.slice(0,5).map(d => ({ score: d.score, label: dimLabel(d.dim) }))`，追加到 vm

### report.wxml
1. 删除 `rp-seg-cards` 区块（条形卡片）
2. 新增矩阵区块：列头行 + 数据行循环 + 全体均值行 + 图例

### report.wxss
1. 新增矩阵相关样式类：`rp-hm-*` 前缀
2. 移除 `rp-seg-*` 样式（卡片相关）

---

## 不变动的部分
- 章节标题"消费者群体分布"
- 其余 report 章节（pros/cons、优先矩阵、营销角度等）
- 后端 API，不新增任何接口

---

## 验收标准
- [ ] 矩阵正确渲染：行 = 群体，列 = 维度，格子 = 真实均值
- [ ] 无数据格子显示 `—`，样式区分
- [ ] 全体均值行在矩阵最底部，有视觉分隔
- [ ] 颜色渐变与分值正相关（高分深色）
- [ ] 图例正确显示
- [ ] 移除条形卡片后无样式残留
