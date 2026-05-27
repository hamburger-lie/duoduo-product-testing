# Deep Analysis Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible "深度研究报告" panel at the bottom of the report page that fetches and displays paragraph-style analysis (卖点×群体匹配 / 无效卖点 / 市场适配建议) from a new backend endpoint, pre-fetched on page load and cached in WX Storage.

**Architecture:** Pre-fetch `GET /api/v1/evaluations/{eval_id}/deep-analysis` in parallel with `loadReport()` on `onLoad`; cache result under key `deep_analysis_cache_{evalId}`; render a collapsible panel with `wx:if` expand/collapse toggled by `deepAnalysisExpanded`. No changes to any existing report logic or UI elements.

**Tech Stack:** WeChat Mini-Program (WXML/WXSS/TypeScript), existing `api` + `request` + `E` patterns from `services/api.ts` / `services/endpoints.ts`.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `miniprogram/types/api.ts` | Modify | Add `DeepAnalysisSection` and `DeepAnalysis` interfaces |
| `miniprogram/services/endpoints.ts` | Modify | Add `DEEP_ANALYSIS_BY_EVAL` endpoint |
| `miniprogram/services/api.ts` | Modify | Add `getDeepAnalysis()` method |
| `miniprogram/pages/report/report.ts` | Modify | Add 3 data fields, `loadDeepAnalysis()`, `onTapDeepToggle()` |
| `miniprogram/pages/report/report.wxml` | Modify | Insert collapsible panel block between 下一步策略 and rp-actions |
| `miniprogram/pages/report/report.wxss` | Modify | Add ~55 lines of `rp-deep-*` styles |

---

## Task 1: Add TypeScript Types

**Files:**
- Modify: `miniprogram/types/api.ts` (append after `BusinessReport` block, before `ReportPdfListItem`)

- [ ] **Step 1: Add the two interfaces**

Open `miniprogram/types/api.ts`. After the closing `}` of the `BusinessReport` interface (line ~333) and before `export interface ReportPdfListItem`, insert:

```typescript
export interface DeepAnalysisSection {
  title: string;
  content: string;
}

export interface DeepAnalysis {
  sections: DeepAnalysisSection[];
  generated_at: string;
}
```

- [ ] **Step 2: Commit**

```bash
git add miniprogram/types/api.ts
git commit -m "feat: add DeepAnalysis types for deep-analysis panel"
```

---

## Task 2: Add Endpoint Constant

**Files:**
- Modify: `miniprogram/services/endpoints.ts`

- [ ] **Step 1: Add endpoint under the §6 Report block**

Open `miniprogram/services/endpoints.ts`. After the line:
```typescript
  WHITEPAPER_BY_EVAL: (eid: string) => `/whitepapers/by-evaluation/${eid}`,
```
Add:
```typescript
  // §6.6 Deep Analysis
  DEEP_ANALYSIS_BY_EVAL: (eid: string) => `/evaluations/${eid}/deep-analysis`,
```

- [ ] **Step 2: Commit**

```bash
git add miniprogram/services/endpoints.ts
git commit -m "feat: add DEEP_ANALYSIS_BY_EVAL endpoint constant"
```

---

## Task 3: Add API Method

**Files:**
- Modify: `miniprogram/services/api.ts`

- [ ] **Step 1: Add import for DeepAnalysis type**

In `miniprogram/services/api.ts`, find the import block at the top:
```typescript
import type {
  CursorPaged, User, CreditBalance, CreditTransaction,
  Evaluation, EvaluationAnswer, Survey, SurveyQuestion, Conversation, Message, PersonaSummary,
  Product, CreateProductReq, UploadUrlRes, PersonaDetail, BackendReport, BusinessReport,
  AvatarUploadRes, ProfileUpdateReq, ReportPdfListResponse,
} from '../types/api';
```
Replace with:
```typescript
import type {
  CursorPaged, User, CreditBalance, CreditTransaction,
  Evaluation, EvaluationAnswer, Survey, SurveyQuestion, Conversation, Message, PersonaSummary,
  Product, CreateProductReq, UploadUrlRes, PersonaDetail, BackendReport, BusinessReport,
  AvatarUploadRes, ProfileUpdateReq, ReportPdfListResponse, DeepAnalysis,
} from '../types/api';
```

- [ ] **Step 2: Add getDeepAnalysis method**

In `miniprogram/services/api.ts`, find the Whitepaper section ending with:
```typescript
  async getWhitepaperByEval(evalId: string): Promise<any> {
    return request<any>({ url: E.WHITEPAPER_BY_EVAL(evalId) });
  },
```
After that closing `},`, add:

```typescript
  async getDeepAnalysis(evalId: string): Promise<DeepAnalysis> {
    return request<DeepAnalysis>({ url: E.DEEP_ANALYSIS_BY_EVAL(evalId) });
  },
```

- [ ] **Step 3: Commit**

```bash
git add miniprogram/services/api.ts
git commit -m "feat: add getDeepAnalysis API method"
```

---

## Task 4: Add State and Logic to report.ts

**Files:**
- Modify: `miniprogram/pages/report/report.ts`

- [ ] **Step 1: Add DeepAnalysis to the import**

Find the existing type import at the top of `report.ts`:
```typescript
import type { BackendReport, BusinessReport } from '../../types/api';
```
Replace with:
```typescript
import type { BackendReport, BusinessReport, DeepAnalysis } from '../../types/api';
```

- [ ] **Step 2: Add three fields to `data`**

Find the `data: {` block inside `Page({`:
```typescript
  data: {
    phase: 'loading' as 'loading' | 'ready' | 'error',
    evaluationId: '',
    error: '',
    vm: defaultVM(),
  },
```
Replace with:
```typescript
  data: {
    phase: 'loading' as 'loading' | 'ready' | 'error',
    evaluationId: '',
    error: '',
    vm: defaultVM(),
    deepAnalysis: null as DeepAnalysis | null,
    deepAnalysisExpanded: false,
    deepAnalysisLoading: false,
  },
```

- [ ] **Step 3: Call loadDeepAnalysis from onLoad**

Find the line inside `onLoad` that reads:
```typescript
    await this.loadReport(true);
```
(The last line of `onLoad`, after the `if (cached)` block.)

This is actually two branches. Find the very end of `onLoad`:

```typescript
    const cached = readCachedReport(evalId);
    if (cached) {
      this.setData({ phase: 'ready', vm: this.buildVM(cached.report, cached.productName || '') });
      await this.loadReport(false);
      return;
    }
    await this.loadReport(true);
  },
```
Replace with:
```typescript
    const cached = readCachedReport(evalId);
    if (cached) {
      this.setData({ phase: 'ready', vm: this.buildVM(cached.report, cached.productName || '') });
      await this.loadReport(false);
      this.loadDeepAnalysis(evalId);
      return;
    }
    await this.loadReport(true);
    this.loadDeepAnalysis(evalId);
  },
```

- [ ] **Step 4: Add loadDeepAnalysis method**

Find the existing `onTapRetry()` method:
```typescript
  onTapRetry() {
    this.loadReport();
  },
```
Before it, add the new method:

```typescript
  async loadDeepAnalysis(evalId: string) {
    const cacheKey = `deep_analysis_cache_${evalId}`;
    try {
      const cached = wx.getStorageSync(cacheKey);
      if (cached) {
        const parsed = typeof cached === 'string' ? JSON.parse(cached) : cached;
        if (parsed?.sections?.length) {
          this.setData({ deepAnalysis: parsed });
          return;
        }
      }
    } catch { /* ignore */ }
    this.setData({ deepAnalysisLoading: true });
    try {
      const result = await api.getDeepAnalysis(evalId);
      this.setData({ deepAnalysis: result, deepAnalysisLoading: false });
      try { wx.setStorageSync(cacheKey, JSON.stringify(result)); } catch { /* ignore */ }
    } catch {
      this.setData({ deepAnalysisLoading: false });
    }
  },
```

- [ ] **Step 5: Add onTapDeepToggle method**

After the `onTapRetry` method:
```typescript
  onTapRetry() {
    this.loadReport();
  },
```
Add:
```typescript
  onTapDeepToggle() {
    this.setData({ deepAnalysisExpanded: !this.data.deepAnalysisExpanded });
  },
```

- [ ] **Step 6: Commit**

```bash
git add miniprogram/pages/report/report.ts
git commit -m "feat: add deep analysis state and loadDeepAnalysis to report page"
```

---

## Task 5: Add UI to report.wxml

**Files:**
- Modify: `miniprogram/pages/report/report.wxml`

- [ ] **Step 1: Insert the collapsible panel**

Find the exact block in `report.wxml`:
```xml
    <!-- ══ Actions ══ -->
    <view class="rp-actions">
```
Insert the following block immediately before it (keep a blank line before `<!-- ══ Actions ══ -->`):

```xml
    <!-- ══ 深度研究报告（可折叠）══ -->
    <view class="rp-deep-panel">
      <view class="rp-deep-toggle" bindtap="onTapDeepToggle">
        <view class="rp-deep-toggle-left">
          <view class="rp-deep-toggle-title">深度研究报告</view>
          <view class="rp-deep-toggle-sub">卖点群体匹配 · 无效卖点识别 · 市场适配建议</view>
        </view>
        <view class="rp-deep-chevron {{deepAnalysisExpanded ? 'rp-deep-chevron--open' : ''}}"></view>
      </view>
      <view wx:if="{{deepAnalysisExpanded}}" class="rp-deep-body">
        <view wx:if="{{deepAnalysisLoading}}" class="rp-deep-loading">正在生成深度分析…</view>
        <block wx:elif="{{deepAnalysis}}">
          <view class="rp-deep-section" wx:for="{{deepAnalysis.sections}}" wx:key="title">
            <view class="rp-deep-section-title">{{item.title}}</view>
            <view class="rp-deep-section-content">{{item.content}}</view>
          </view>
        </block>
        <view wx:else class="rp-deep-loading">深度分析生成失败，请稍后重试</view>
      </view>
    </view>

```

- [ ] **Step 2: Verify no existing nodes were touched**

Run a visual diff. The only change is the new `rp-deep-panel` block. All nodes from `rp-hero` through `rp-section` through `rp-actions` must remain exactly as before.

- [ ] **Step 3: Commit**

```bash
git add miniprogram/pages/report/report.wxml
git commit -m "feat: add deep analysis collapsible panel to report wxml"
```

---

## Task 6: Add Styles to report.wxss

**Files:**
- Modify: `miniprogram/pages/report/report.wxss`

- [ ] **Step 1: Append styles at end of file**

Open `miniprogram/pages/report/report.wxss` and append the following block at the very end:

```css
/* ══════════════════════════════════════════
   深度研究报告（可折叠）
══════════════════════════════════════════ */
.rp-deep-panel {
  background: #fff;
  border-radius: 18rpx;
  box-shadow: 0 4rpx 20rpx rgba(26, 26, 46, 0.04);
  overflow: hidden;
}

.rp-deep-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 28rpx;
  gap: 16rpx;
}

.rp-deep-toggle-left {
  flex: 1;
  min-width: 0;
}

.rp-deep-toggle-title {
  font-size: 30rpx;
  font-weight: 800;
  color: #19172B;
  line-height: 1.35;
}

.rp-deep-toggle-sub {
  margin-top: 6rpx;
  font-size: 23rpx;
  color: #7C3AED;
  line-height: 1.4;
}

.rp-deep-chevron {
  width: 18rpx;
  height: 18rpx;
  border-right: 3rpx solid #9B96A8;
  border-bottom: 3rpx solid #9B96A8;
  transform: rotate(45deg);
  transition: transform 0.2s ease;
  flex-shrink: 0;
  margin-top: -4rpx;
}

.rp-deep-chevron--open {
  transform: rotate(-135deg);
  margin-top: 4rpx;
}

.rp-deep-body {
  padding: 0 28rpx 28rpx;
  border-top: 1rpx solid #F0EEF4;
}

.rp-deep-loading {
  padding: 40rpx 0;
  text-align: center;
  font-size: 26rpx;
  color: #9B96A8;
  line-height: 1.6;
}

.rp-deep-section {
  padding: 28rpx 0;
  border-bottom: 1rpx solid #F0EEF4;
}

.rp-deep-section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.rp-deep-section-title {
  font-size: 28rpx;
  font-weight: 800;
  color: #19172B;
  margin-bottom: 14rpx;
  line-height: 1.4;
}

.rp-deep-section-content {
  font-size: 26rpx;
  color: #4C485E;
  line-height: 1.75;
}
```

- [ ] **Step 2: Verify class name uniqueness**

Confirm no existing class in `report.wxss` starts with `rp-deep-`. (All new classes use this prefix exclusively.)

- [ ] **Step 3: Commit**

```bash
git add miniprogram/pages/report/report.wxss
git commit -m "feat: add rp-deep-* styles for deep analysis collapsible panel"
```

---

## Backend Contract Reference (for backend team)

**Endpoint:** `GET /api/v1/evaluations/{eval_id}/deep-analysis`

**Auth:** Bearer token (same as all other evaluation endpoints)

**Response 200:**
```json
{
  "sections": [
    {
      "title": "一、卖点与群体匹配",
      "content": "「控油持久」是本轮共鸣最强卖点，在油皮群体中认可率达78%，职场人群紧随其后达65%。干皮及中年群体对此卖点反应冷淡（12%），触达此群体时应弱化该表达，转而主打保湿修护方向。"
    },
    {
      "title": "二、无人感兴趣的卖点",
      "content": "「高端礼品定位」在全部参与群体中认可率均低于20%，为本轮调研中的死亡卖点。各群体对溢价礼品属性均无购买动机，建议从正式传播物料中移除该表达，避免稀释核心卖点的传达效率。"
    },
    {
      "title": "三、市场适配建议",
      "content": "综合以上分析，产品应在油皮及职场人群中优先建立控油场景的强认知，以「熬夜急救」和「带妆全天候」为核心素材方向集中投放。对干皮群体重新设计触达角度，放大成分温和与保湿修护维度，避免以控油为主轴的推广话语体系造成排斥。"
    }
  ],
  "generated_at": "2026-05-23T10:00:00Z"
}
```

**LLM generation inputs the backend should use:**
- `top_pros` (卖点列表 + support_count + evidence_quotes)
- `top_cons` (劝退因素)
- `persona_segments` (群体意向分布)
- `evidence_chains` (if available)
- `marketing_copy_angles` (if available)

**Writing style rules for the LLM prompt:**
- 群体视角，不出现「AI」「虚拟」「置信度」等字样
- 分析师语气，正式报告文体
- 每节 100-200 字，不说废话，有具体数字支撑
- 章节标题格式：「一、」「二、」「三、」

---

## Verification Checklist

After all tasks complete, verify in WeChat DevTools:

- [ ] Report page loads normally, no console errors
- [ ] Bottom of report shows new "深度研究报告" card with subtitle text
- [ ] Tapping the card expands the body (chevron rotates)
- [ ] If API returns data: three sections render with title + paragraph text
- [ ] If API is loading: "正在生成深度分析…" shows
- [ ] If API fails: "深度分析生成失败，请稍后重试" shows
- [ ] Tapping again collapses the panel
- [ ] All sections above (核心结论, 消费者群体分布, etc.) unchanged
- [ ] WX Storage contains `deep_analysis_cache_{evalId}` after successful fetch
- [ ] Second page open loads from cache (no network request for deep-analysis)
