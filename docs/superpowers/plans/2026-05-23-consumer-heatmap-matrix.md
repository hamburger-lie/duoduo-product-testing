# 消费者群体热力矩阵 实施计划

> **执行说明：** 逐任务执行，步骤使用 `- [ ]` 复选框跟踪进度。

**目标：** 将「消费者群体分布」条形卡片面板替换为「群体 × 维度」热力矩阵，数值来自真实调研均值。

**架构：** 三个文件改动 —— `report.ts` 新增单元格样式辅助函数并启用 `buildHeatmapRows`；`report.wxml` 替换条形卡片区块为矩阵结构；`report.wxss` 新增 `rp-hm-*` 样式并删除 `rp-seg-*` 样式。

**技术栈：** 微信小程序（WXML / WXSS / TypeScript），无新依赖。

---

## 文件清单

| 文件 | 改动内容 |
|---|---|
| `miniprogram/pages/report/report.ts` | 新增 `hmCellStyle`，改造 `buildHeatmapRows`（缺数据返回 null），新增 `buildHeatmapBaselineRow`，更新 `defaultVM` 类型，两处调用点启用 `heatmapRows` |
| `miniprogram/pages/report/report.wxml` | 替换第 69–82 行（`rp-seg-cards` 区块）为矩阵标记 |
| `miniprogram/pages/report/report.wxss` | 新增 `rp-hm-*` 样式；删除 `rp-seg-*` 样式（第 412–469 行） |

---

### 任务一：新增 `hmCellStyle` 辅助函数，改造 `buildHeatmapRows`

**涉及文件：**
- 修改：`miniprogram/pages/report/report.ts:427-482`

现有 `buildHeatmapRows` 在缺少真实数据时会用近似公式（`d.score + deviation * 0.8`）填充，本次将其替换为 `null`。新增 `hmCellStyle` 辅助函数，根据分值计算内联背景色和文字样式类。

- [ ] **第 1 步：在 `buildHeatmapRows` 上方（第 426 行之后）插入 `hmCellStyle` 函数**

```typescript
function hmCellStyle(score: number | null): { bg: string; textCls: string } {
  if (score === null) return { bg: 'rgba(240,237,247,1)', textCls: 'rp-hm-ct--empty' };
  const opacity = parseFloat(((score - 1) / 4).toFixed(2));
  return {
    bg: `rgba(124,92,252,${opacity})`,
    textCls: opacity >= 0.5 ? 'rp-hm-ct--light' : 'rp-hm-ct--dark',
  };
}
```

- [ ] **第 2 步：将整个 `buildHeatmapRows` 函数（第 427–482 行）替换为以下内容**

```typescript
function buildHeatmapRows(
  segments: Array<{ segment: string; count: number; avg_intent: number }>,
  dims: Array<{ dim: string; score: number }>,
  overallAvg: number,
  tagMap: Record<string, string> = {},
  answers: Array<{
    persona_tag?: string;
    overall_intent?: number;
    answers?: Array<{ qid: string; answer: string | number | string[] }> | Record<string, any>;
  }> = [],
): Array<{ segment: string; cells: Array<{ score: number | null; bg: string; textCls: string; label: string }> }> {
  const topDims = dims.slice(0, 5);
  const sortedSegs = [...segments].sort((a, b) => b.avg_intent - a.avg_intent).slice(0, 5);
  const sortedAnswers = [...answers].sort((a, b) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));

  const tagScoreMap: Record<string, Record<string, number[]>> = {};
  for (const a of answers) {
    const tag = a.persona_tag || '';
    if (!tag) continue;
    const items = Array.isArray(a.answers) ? a.answers : [];
    for (const item of items) {
      const v = Number(item.answer);
      if (!item.qid || isNaN(v) || v < 1 || v > 5) continue;
      if (!tagScoreMap[tag]) tagScoreMap[tag] = {};
      if (!tagScoreMap[tag][item.qid]) tagScoreMap[tag][item.qid] = [];
      tagScoreMap[tag][item.qid].push(v);
    }
  }

  return sortedSegs.map((seg, i) => {
    const segLabel = pickSegmentLabel(seg.segment, i, tagMap, sortedAnswers);
    const segTag = tagMap[seg.segment] || sortedAnswers[i]?.persona_tag || '';
    const dimScores = tagScoreMap[segTag] || {};

    return {
      segment: segLabel,
      cells: topDims.map(d => {
        const realVals = dimScores[d.dim];
        const score: number | null =
          realVals && realVals.length > 0
            ? parseFloat((realVals.reduce((s, v) => s + v, 0) / realVals.length).toFixed(1))
            : null;
        return { score, ...hmCellStyle(score), label: dimLabel(d.dim) };
      }),
    };
  });
}
```

- [ ] **第 3 步：在微信开发者工具中确认无编译错误**

打开开发者工具控制台，确认 `report.ts` 无红色报错。

---

### 任务二：新增 `buildHeatmapBaselineRow`，更新 `defaultVM` 类型

**涉及文件：**
- 修改：`miniprogram/pages/report/report.ts:484`（`buildHeatmapDimHeaders` 之后）
- 修改：`miniprogram/pages/report/report.ts:681`（`defaultVM` 类型定义）

- [ ] **第 1 步：在 `buildHeatmapDimHeaders` 之后（第 486 行后）插入以下函数**

```typescript
function buildHeatmapBaselineRow(
  dims: Array<{ dim: string; score: number }>,
): Array<{ score: number; bg: string; textCls: string; label: string }> {
  return dims.slice(0, 5).map(d => {
    const score = parseFloat(d.score.toFixed(1));
    return { score, ...hmCellStyle(score), label: dimLabel(d.dim) };
  });
}
```

- [ ] **第 2 步：更新 `defaultVM` 中第 681 行的类型定义**

将：
```typescript
    heatmapRows: [] as Array<{ segment: string; cells: Array<{ score: number; cls: string; label: string }> }>,
```
改为：
```typescript
    heatmapRows: [] as Array<{ segment: string; cells: Array<{ score: number | null; bg: string; textCls: string; label: string }> }>,
    heatmapBaselineRow: [] as Array<{ score: number; bg: string; textCls: string; label: string }>,
```

- [ ] **第 3 步：确认开发者工具无编译错误**

---

### 任务三：两处调用点启用 `heatmapRows` 和 `heatmapBaselineRow`

**涉及文件：**
- 修改：`miniprogram/pages/report/report.ts` 约第 861–862 行（第一处调用）
- 修改：`miniprogram/pages/report/report.ts` 约第 970–971 行（第二处调用）

- [ ] **第 1 步：第一处调用点（约第 861 行）**

将：
```typescript
      heatmapDimHeaders: buildHeatmapDimHeaders(dims),
      heatmapRows: [],
```
改为：
```typescript
      heatmapDimHeaders: buildHeatmapDimHeaders(dims),
      heatmapRows: buildHeatmapRows(segs, dims, avg, tagMap, answers),
      heatmapBaselineRow: buildHeatmapBaselineRow(dims),
```

- [ ] **第 2 步：第二处调用点（约第 970 行）**

将：
```typescript
      heatmapDimHeaders: buildHeatmapDimHeaders(dims),
      heatmapRows: [],
```
改为：
```typescript
      heatmapDimHeaders: buildHeatmapDimHeaders(dims),
      heatmapRows: buildHeatmapRows(segs, dims, avg, tagMap, answers),
      heatmapBaselineRow: buildHeatmapBaselineRow(dims),
```

- [ ] **第 3 步：提交**

```bash
git add miniprogram/pages/report/report.ts
git commit -m "feat: 启用热力矩阵数据——真实调研均值，缺数据格子返回 null"
```

---

### 任务四：替换 WXML 条形卡片为矩阵结构

**涉及文件：**
- 修改：`miniprogram/pages/report/report.wxml:69-82`

- [ ] **第 1 步：将第 69–82 行整块替换为以下内容**

删除：
```xml
    <!-- ══ 2. 消费者群体分布 ══ -->
    <view class="rp-section" wx:if="{{vm.segmentRows.length}}">
      <view class="rp-section-title">消费者群体分布</view>
      <view class="rp-seg-cards">
        <view class="rp-seg-card" wx:for="{{vm.segmentRows}}" wx:key="label">
          <view class="rp-seg-card-top">
            <view class="rp-seg-card-name">{{item.label}}</view>
          </view>
          <view class="rp-seg-bar-track">
            <view class="rp-seg-bar-fill" style="width:{{item.width}}%"></view>
          </view>
          <view class="rp-seg-card-val">购买意向 {{item.value}}</view>
        </view>
      </view>
    </view>
```

替换为：
```xml
    <!-- ══ 2. 消费者群体分布 ══ -->
    <view class="rp-section" wx:if="{{vm.heatmapRows.length || vm.heatmapBaselineRow.length}}">
      <view class="rp-section-title">消费者群体分布</view>
      <view class="rp-hm-wrap">

        <!-- 列标题 -->
        <view class="rp-hm-header-row">
          <view class="rp-hm-row-label rp-hm-row-label--header"></view>
          <view class="rp-hm-col-header" wx:for="{{vm.heatmapDimHeaders}}" wx:key="*this">{{item}}</view>
        </view>

        <!-- 数据行 -->
        <view class="rp-hm-row" wx:for="{{vm.heatmapRows}}" wx:key="segment">
          <view class="rp-hm-row-label">{{item.segment}}</view>
          <view
            class="rp-hm-cell {{cell.score === null ? 'rp-hm-cell--empty' : ''}}"
            wx:for="{{item.cells}}"
            wx:for-item="cell"
            wx:key="label"
            style="background:{{cell.bg}}"
          >
            <text class="rp-hm-cell-text {{cell.textCls}}">{{cell.score !== null ? cell.score : '—'}}</text>
          </view>
        </view>

        <!-- 全体均值行 -->
        <view class="rp-hm-row rp-hm-row--baseline" wx:if="{{vm.heatmapBaselineRow.length}}">
          <view class="rp-hm-row-label rp-hm-row-label--baseline">全体均值</view>
          <view
            class="rp-hm-cell"
            wx:for="{{vm.heatmapBaselineRow}}"
            wx:key="label"
            style="background:{{item.bg}}"
          >
            <text class="rp-hm-cell-text {{item.textCls}}">{{item.score}}</text>
          </view>
        </view>

        <!-- 图例 -->
        <view class="rp-hm-legend">
          <text class="rp-hm-legend-label">1</text>
          <view class="rp-hm-legend-bar"></view>
          <text class="rp-hm-legend-label">5</text>
          <text class="rp-hm-legend-unit">调研均值（1–5）</text>
        </view>

      </view>
    </view>
```

- [ ] **第 2 步：在开发者工具中确认矩阵区块出现，无 JS 报错（样式暂未加，可能无样式）**

---

### 任务五：新增 `rp-hm-*` 样式，删除 `rp-seg-*` 样式

**涉及文件：**
- 修改：`miniprogram/pages/report/report.wxss:412-469`

- [ ] **第 1 步：删除 `.rp-seg-cards` 到 `.rp-seg-card-val` 的整块样式（第 412–469 行）**

- [ ] **第 2 步：在原位置插入以下样式**

```css
/* ══ 热力矩阵 ══ */
.rp-hm-wrap {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.rp-hm-header-row,
.rp-hm-row {
  display: flex;
  flex-direction: row;
  align-items: stretch;
}
.rp-hm-row-label {
  width: 180rpx;
  min-width: 180rpx;
  font-size: 22rpx;
  color: #4A3F7A;
  font-weight: 600;
  padding: 10rpx 12rpx 10rpx 0;
  display: flex;
  align-items: center;
  overflow: hidden;
}
.rp-hm-row-label--header {
  min-height: 56rpx;
}
.rp-hm-row-label--baseline {
  font-size: 22rpx;
  color: #7C5CFC;
  font-weight: 700;
}
.rp-hm-col-header {
  flex: 1;
  font-size: 20rpx;
  color: #7B7499;
  font-weight: 600;
  text-align: center;
  padding: 8rpx 4rpx;
  line-height: 1.3;
  word-break: break-all;
}
.rp-hm-cell {
  flex: 1;
  margin: 3rpx;
  border-radius: 8rpx;
  min-height: 52rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rp-hm-cell--empty {
  background: rgba(240,237,247,1) !important;
}
.rp-hm-cell-text {
  font-size: 22rpx;
  font-weight: 700;
}
.rp-hm-ct--dark {
  color: #3D2E7C;
}
.rp-hm-ct--light {
  color: #FFFFFF;
}
.rp-hm-ct--empty {
  color: #B0A8CC;
  font-size: 24rpx;
}
.rp-hm-row--baseline {
  border-top: 2rpx dashed #DDD6F3;
  margin-top: 4rpx;
  padding-top: 4rpx;
}
.rp-hm-legend {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8rpx;
  margin-top: 16rpx;
  padding-left: 180rpx;
}
.rp-hm-legend-bar {
  width: 100rpx;
  height: 10rpx;
  border-radius: 999rpx;
  background: linear-gradient(90deg, rgba(124,92,252,0), rgba(124,92,252,1));
}
.rp-hm-legend-label {
  font-size: 20rpx;
  color: #7B7499;
}
.rp-hm-legend-unit {
  font-size: 20rpx;
  color: #B0A8CC;
  margin-left: 8rpx;
}
```

- [ ] **第 3 步：在开发者工具中验证**

确认：矩阵颜色渐变正确（高分深紫、低分浅色）；全体均值行有虚线上边框；图例显示正常；手机宽度（375px）下不溢出。

- [ ] **第 4 步：提交**

```bash
git add miniprogram/pages/report/report.wxml miniprogram/pages/report/report.wxss
git commit -m "feat: 热力矩阵 WXML/WXSS——替换条形卡片，新增全体均值行和图例"
```
