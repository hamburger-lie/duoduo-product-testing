# 测品官小程序 Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Adaptations:** No TDD ceremony (mini-program WXML lacks a sensible unit-test harness for Phase A pure-UI scaffolding). No git commits (`D:\soul\` is not a git repo). Verification = open in WeChat DevTools and eyeball-check that pages render.

**Goal:** Build a standalone, packageable WeChat mini-program "测品官" at `D:\soul\miniprogram\` that matches `D:\soul\mockup\index.html` visually (in white theme) and exposes API stubs aligned to `D:\soul\docs\specs\API_CONTRACT.md`.

**Architecture:** TypeScript native mini-program. 5 pages (home/create/chat/history/profile) + 7 shared components. `services/api.ts` is an Adapter — Phase A reads from `mocks/*.ts`, Phase B will switch to `services/http.ts`. Types in `types/api.ts` mirror API_CONTRACT 1:1.

**Tech Stack:** WeChat Mini-Program native (TypeScript), no UI library, WXSS with CSS variables.

---

## File Structure

```
D:\soul\miniprogram\
├── project.config.json
├── project.private.config.json
├── app.json / app.ts / app.wxss
├── sitemap.json
├── tsconfig.json
├── styles/{tokens,reset}.wxss
├── types/{api,domain}.ts
├── services/{http,endpoints,api,stream}.ts
├── mocks/{personas,evaluations,conversations,credits}.ts
├── components/{avatar,badge,chip,progress-bar,research-card,bubble-think,bubble-speak}/*.{wxml,wxss,ts,json}
├── pages/{home,create,chat,history,profile}/*.{wxml,wxss,ts,json}
└── README.md
```

---

## Task 1: Project skeleton & config

**Files:**
- Create: `D:\soul\miniprogram\project.config.json`
- Create: `D:\soul\miniprogram\project.private.config.json`
- Create: `D:\soul\miniprogram\sitemap.json`
- Create: `D:\soul\miniprogram\tsconfig.json`
- Create: `D:\soul\miniprogram\app.json`
- Create: `D:\soul\miniprogram\app.ts`
- Create: `D:\soul\miniprogram\app.wxss`
- Create: `D:\soul\miniprogram\styles\tokens.wxss`
- Create: `D:\soul\miniprogram\styles\reset.wxss`

- [ ] **Step 1.1**: Write all skeleton files (config + app shell + design tokens + reset). Content specified in code blocks below in Task 1 execution notes.
- [ ] **Step 1.2**: Open DevTools, import `D:\soul\miniprogram\`. Project should load without errors (blank pages OK at this stage).

**Verification:** Project imports; DevTools console shows no syntax errors.

---

## Task 2: Types layer (mirror API_CONTRACT)

**Files:**
- Create: `D:\soul\miniprogram\types\api.ts` (all request/response types per API_CONTRACT)
- Create: `D:\soul\miniprogram\types\domain.ts` (frontend-friendly view models)

Types covered: `Persona`, `Product`, `Evaluation`, `Conversation`, `Message`, `Report`, `Credit*`, `User`, `Paginated<T>`, `CursorPaged<T>`, `ApiError`. All IDs are `string` (snowflake-as-string per §0.1).

**Verification:** `tsc --noEmit` reports zero errors (run via DevTools' built-in TS check or skip if not configured — types are visual-only for now).

---

## Task 3: Services layer (http stub + endpoints + api adapter + stream stub)

**Files:**
- Create: `D:\soul\miniprogram\services\endpoints.ts` — all API path constants from API_CONTRACT §11.
- Create: `D:\soul\miniprogram\services\http.ts` — `wx.request` wrapper with `Authorization`, `X-Request-Id`, `X-Client-Version` headers, base URL constant (empty for now), unified error mapping.
- Create: `D:\soul\miniprogram\services\stream.ts` — interface `StreamHandle { onDelta, onMeta, onDone, onError, abort }`; Phase A `setInterval` mock implementation; placeholder for real SSE parser.
- Create: `D:\soul\miniprogram\services\api.ts` — exports `api.*` methods used by pages; flag `USE_MOCK = true`; branches to mocks/* or http.

**Verification:** Files type-check. Pages will import these in later tasks.

---

## Task 4: Mock fixtures

**Files:**
- Create: `D:\soul\miniprogram\mocks\personas.ts` — 3 personas: `p_yun` 小芸 / `p_jie` 王姐 / `p_cong` 丛丛 (matching mockup avatars and roles).
- Create: `D:\soul\miniprogram\mocks\evaluations.ts` — 7 evaluations matching PHONE 4 history list (5 done + 2 active) and PHONE 1 "最近调研" 3 cards.
- Create: `D:\soul\miniprogram\mocks\conversations.ts` — 1 conversation for 燕泽修护精华 with topic-switch + think/speak bubbles matching PHONE 3.
- Create: `D:\soul\miniprogram\mocks\credits.ts` — balance + transaction list.

**Verification:** All mocks export typed const arrays; no TS errors.

---

## Task 5: Shared components

Build in this order — each is a `Component({})` definition with WXML/WXSS/TS/JSON.

- [ ] **5.1 `avatar/`** — props: `personaId: 'yun'|'jie'|'cong'`, `size: number` (rpx). Renders the SVG matching PHONE 1's hero-avatars (extract inline SVG from mockup line 993/996/999). Use `wx:if` to switch.
- [ ] **5.2 `badge/`** — props: `kind: 'active'|'done'`, `text: string`. Pill, color from `--warning`/`--success`.
- [ ] **5.3 `chip/`** — props: `text: string`, `selected: boolean`, event `tap`.
- [ ] **5.4 `progress-bar/`** — props: `percent: number`. Background track + `--accent` fill.
- [ ] **5.5 `research-card/`** — props: `evaluation: Evaluation`. Used by home "最近调研" and (compact variant via slot) history. Renders thumb + title + meta + progress + badge.
- [ ] **5.6 `bubble-think/`** — props: `content: string`. The "💭 内心独白" purple-bordered bubble.
- [ ] **5.7 `bubble-speak/`** — props: `personaId`, `personaName`, `content`. Avatar + label + speech bubble.

**Verification:** Add each to a temporary route or include in `home.json` `usingComponents` to spot-render once.

---

## Task 6: Home page

**Files:** `pages/home/home.{ts,wxml,wxss,json}`

Layout (top to bottom):
- `top-bar`: logo 🎭 + "测品官" + 🔔 🔍 actions
- Hero card: eyebrow "AI · 消费者洞察平台" / title "读懂每一位<br>消费者内心" / sub "3位AI测品官..." / 3 avatar previews + "3位测品官待命" / CTA "✨ 开启新调研"
- Stats row: 累计调研次数 / 已获洞察观点 (2 cards)
- Section: "最近调研 / 查看全部 →" + 3 `<research-card>` from `api.listEvaluations({limit:3})`

**onLoad**: `api.listEvaluations({limit:3})` → `setData({recents})`; `api.getCreditsBalance()` → updates stats.

**Navigation**:
- CTA → `wx.switchTab({url:'/pages/create/create'})`
- Research card tap → `wx.navigateTo({url:'/pages/chat/chat?evaluation_id=' + id})`
- "查看全部" → `wx.switchTab({url:'/pages/history/history'})`

**Verification:** Page renders hero + stats + 3 cards; tapping CTA switches to Create tab; tapping a card opens Chat.

---

## Task 7: Create page

**Files:** `pages/create/create.{ts,wxml,wxss,json}`

Layout (PHONE 2):
- `back-bar` with title "新建调研"
- Step indicator: 3 steps (选话题 / 上传产品 / 选测品官). All three sections shown stacked; the indicator highlights current logical step but UI is one scroll.
- Section: "选择调研话题 / 已选 N" + 9 chips. Toggle on tap; min 1 required.
- Section: "上传产品图片" upload zone (`wx.chooseMedia`, max 6, JPG/PNG). Thumbnail row appears after pick. Product-name input below.
- Section: "选择测品官 / 已选 3/3" + 3 `persona-select-card` (custom local layout, not a shared component for this stage). All 3 preselected.
- `btn-primary`: "✨ 开始调研" → calls in sequence: `api.uploadProduct(files)` → `api.createEvaluation()` → `api.attachPersonas(evalId, personaIds)` → `api.runEvaluation(evalId)` → `wx.redirectTo({url:'/pages/chat/chat?evaluation_id=' + evalId})`.

**Verification:** Toggling chips updates count; choose-media adds thumbnails; "开始调研" navigates to chat with mock evaluation id.

---

## Task 8: Chat page

**Files:** `pages/chat/chat.{ts,wxml,wxss,json}`

Layout (PHONE 3):
- `chat-header` (sticky top): back arrow + selected persona avatar+name+role + 在线 dot + topic label + N/9 progress + progress-bar.
- `chat-messages` (scrollable): topic-switch separator + alternating `<bubble-think>` / `<bubble-speak>`.
- `chat-input` (sticky bottom above tabbar): textinput + send button.

**onLoad**: read `evaluation_id` from query; `api.getConversation(evaluation_id)` → load message list + meta.

**Send**: append user "follow-up" entry; call `api.streamMessage(convId, text, handlers)`; handlers append a new `bubble-think` then `bubble-speak`, streamed token-by-token via the mock stream.

**Verification:** Page loads with seeded mock messages; sending a follow-up appends a new think+speak pair with progressive text rendering.

---

## Task 9: History page

**Files:** `pages/history/history.{ts,wxml,wxss,json}`

Layout (PHONE 4):
- `top-bar`: 📂 + "历史档案" + ⋯
- Search input (client-side filter on title)
- Filter tabs: 全部 / 已完成 / 进行中 (counts from data)
- Scrollable list of history-cards: thumb + title + meta + status badge + persona avatars row + 💬 N条 / 💡 N洞察 stats

**onLoad**: `api.listEvaluations({limit:20})`.

**Tap card** → `wx.navigateTo` to chat (matches home behavior).

**Verification:** All 7 mock evaluations show; filter tabs filter correctly; search filters by title substring.

---

## Task 10: Profile page

**Files:** `pages/profile/profile.{ts,wxml,wxss,json}`

Layout (PHONE 5 — need to peek at lines 1488–1592 for exact content):
- `top-bar` simple
- Profile card: avatar + nickname + "测品官 · 高级会员" + edit button
- Stats grid: 累计调研 / 消耗积分 (mock numbers from credits)
- Function list: 测品官档案 / 积分明细 / 通知设置 / 关于
- Bottom signature: "测品官" version

**onLoad**: `api.getMe()` + `api.getCreditsBalance()`.

**Verification:** Renders profile + stats + list. Item taps `wx.showToast({title:'敬请期待'})`.

---

## Task 11: README & final polish

**Files:** `D:\soul\miniprogram\README.md`

Contents:
- Project overview (1 paragraph)
- Run locally: open DevTools → import this directory → AppID "touristappid" (visitor mode)
- Migration to another WeChat account: replace `appid` in `project.config.json`, upload via DevTools
- Phase B switch (when backend ready): set `USE_MOCK=false` in `services/api.ts` and `BASE_URL` in `services/http.ts`; whitelist domain in mp.weixin.qq.com
- Project layout diagram

**Final spot-check:** click through all 5 pages in DevTools; no console errors; tab nav works; navigation in/out of chat works.

---

## Self-review notes

- Spec §2 (5 pages) — all 5 covered in Tasks 6–10 ✓
- Spec §3 (white tokens) — Task 1 ✓
- Spec §4 (file structure) — matches §File Structure above ✓
- Spec §5 (API alignment) — Tasks 2–4 ✓
- Spec §6 (migration) — Task 11 ✓
- Spec §7 non-goals respected ✓
