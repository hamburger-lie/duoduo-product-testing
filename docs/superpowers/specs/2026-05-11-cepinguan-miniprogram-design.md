# 测品官小程序 — 前端骨架设计稿 (Phase A)

> 日期：2026-05-11
> 阶段：Phase A — 纯前端 + mock 数据，对齐 API_CONTRACT.md 的接口形状
> 项目根：`D:\soul\miniprogram\`（独立目录，可整体打包迁移到另一个微信账号）

---

## 1. 目标

把 `D:\soul\mockup\index.html` 中的 5 屏设计稿落地为可在微信开发者工具运行的小程序，并满足：

1. **品牌**：产品名 = **测品官**（不是"百面测品官"，不是"内容特工队"）。
2. **配色**：**白底**主题（设计稿为深紫黑，本次重做色板）；雾紫 #7B6FA8 作为强调色。
3. **可迁移**：项目自成一体，复制 `miniprogram/` 目录 + 改 AppID 即可在另一个账号导入并上传。
4. **后端预留**：现在不调真接口，但目录结构、请求函数签名、类型定义都按 `D:\soul\docs\specs\API_CONTRACT.md` 形状写好，Phase B 切真后端时只改 `services/api.ts` 的 adapter 实现。

## 2. 范围（页面）

按设计稿原样落地 **5 个页面**：

| 路径 | 标题 | 来源 | 底部 Tab |
|---|---|---|---|
| `pages/home/home` | 首页（Hero + 统计 + 最近调研） | PHONE 1 | 首页 |
| `pages/create/create` | 新建调研（话题 / 上传 / 选角色） | PHONE 2 | 新建 |
| `pages/chat/chat` | 调研对话（内心独白 + 表达流） | PHONE 3 | —（非 Tab，从 create / history 进入） |
| `pages/history/history` | 历史档案（搜索 + 筛选 + 卡片） | PHONE 4 | 历史 |
| `pages/profile/profile` | 个人中心（头像 + 数据卡 + 功能列表） | PHONE 5 | 我的 |

底部 TabBar 4 个 tab：**首页 / 新建 / 历史 / 我的**。`chat` 不在 tab，从首页"最近调研"或 history 卡片跳入。

> "角色登场"动画作为 `create → chat` 的转场遮罩处理（非独立路由），保留实现位但不强制。

## 3. 视觉规范（白底版）

设计 token 写入 `styles/tokens.wxss`，全程使用 `rpx`（设计稿 1px ≈ 2rpx）：

| Token | 值 | 用途 |
|---|---|---|
| `--bg-page` | `#FFFFFF` | 页面底色 |
| `--bg-card` | `#F7F7F8` | 卡片底色 |
| `--bg-card-hover` | `#EFEEF3` | 卡片按下态 |
| `--border` | `rgba(0,0,0,0.08)` | 卡片边框 |
| `--border-strong` | `rgba(123,111,168,0.35)` | 选中态边框 |
| `--accent` | `#7B6FA8` | 主色（CTA、链接、强调） |
| `--accent-soft` | `#EFEAF7` | 主色 8% 背景（chip selected） |
| `--text-primary` | `#1A1A1F` | 正文 |
| `--text-sub` | `rgba(0,0,0,0.55)` | 次文本 |
| `--text-muted` | `rgba(0,0,0,0.35)` | 弱文本 |
| `--success` | `#3F9D5C` | 已完成徽章 |
| `--warning` | `#D88A2C` | 进行中徽章 |
| `--r-card` | `24rpx` | 卡片圆角 |
| `--r-pill` | `100rpx` | 胶囊圆角 |

**Hero 渐变**：浅紫 → 白（`linear-gradient(155deg, #EFEAF7 0%, #FFFFFF 100%)`），原稿的深紫黑 hero 在白底下变成柔和紫雾。

**字体**：`PingFang SC, -apple-system, sans-serif`，系统默认即可。

**头像**：暂时保留设计稿里的内联 SVG（小芸 / 王姐 / 丛丛），放进 `assets/avatars/*.wxs` 或直接作为 `wxml` 内联 svg-template 组件复用。

## 4. 工程结构

```
D:\soul\miniprogram\
├── project.config.json           AppID="touristappid" 占位
├── project.private.config.json   （本地配置，可忽略上传）
├── app.json                       窗口 + tabBar + pages 路由
├── app.ts                         全局状态 + 启动 hook
├── app.wxss                       全局重置 + import tokens
├── sitemap.json                   全部允许
├── tsconfig.json                  使用官方 miniprogram-ci 模板
├── pages/
│   ├── home/        home.{ts,wxml,wxss,json}
│   ├── create/      create.{ts,wxml,wxss,json}
│   ├── chat/        chat.{ts,wxml,wxss,json}
│   ├── history/     history.{ts,wxml,wxss,json}
│   └── profile/     profile.{ts,wxml,wxss,json}
├── components/
│   ├── avatar/         persona-id → 内联 SVG 头像
│   ├── research-card/  首页/历史共用的产品调研卡
│   ├── chip/           话题选项胶囊
│   ├── badge/          进行中/已完成徽章
│   ├── progress-bar/   进度条
│   ├── bubble-think/   内心独白气泡（chat）
│   └── bubble-speak/   表达气泡（chat）
├── services/
│   ├── http.ts         wx.request 封装：base url、JWT、X-Request-Id、错误码
│   ├── endpoints.ts    所有 API 路径常量（对齐 API_CONTRACT §11 速查表）
│   ├── api.ts          Adapter：现在调 mocks/，Phase B 切真 http
│   └── stream.ts       SSE-like chunked 解析（chat 用，Phase A 用 setInterval mock）
├── mocks/
│   ├── personas.ts     3 个固定角色（小芸/王姐/丛丛）
│   ├── evaluations.ts  最近调研 + 历史档案数据
│   ├── conversations.ts 对话 mock，含话题切换/内心独白/表达
│   └── credits.ts      积分余额 + 流水
├── types/
│   ├── api.ts          所有请求/响应类型（对齐 API_CONTRACT）
│   └── domain.ts       前端领域模型（去掉雪花 ID 字符串包装等）
├── styles/
│   ├── tokens.wxss     §3 设计 token
│   └── reset.wxss      box-sizing / safe-area
├── assets/
│   └── icons/          tab 图标（emoji 也可，看是否需要 PNG）
└── README.md           迁移步骤 + Phase B 切真后端方法
```

**Adapter 模式关键点**：每个页面只 `import { api } from '@/services/api'`，不直接 import mock。`api.ts` 内部 `if (USE_MOCK) return mock else return http.request(...)`。Phase B 切换只需翻一个开关。

## 5. API 接口预留（对照 API_CONTRACT §11）

`services/endpoints.ts` 全量声明，但 Phase A 只为以下页面用到的接口实现 mock：

| 页面 | 用到的接口 | mock 文件 |
|---|---|---|
| home | `GET /evaluations?limit=3`, `GET /credits/balance` | evaluations.ts, credits.ts |
| create | `POST /products/upload-url`, `POST /products`, `GET /personas/recommend`, `POST /evaluations`, `PUT /evaluations/{id}/personas`, `POST /evaluations/{id}/run` | personas.ts |
| chat | `GET /conversations`, `POST /conversations/{id}/messages` (流式) | conversations.ts |
| history | `GET /evaluations?cursor=&limit=20`（+ 搜索/筛选客户端做） | evaluations.ts |
| profile | `GET /auth/me`, `GET /credits/balance`, `GET /credits/transactions` | credits.ts |

请求/响应类型 100% 按 `API_CONTRACT.md` 定义。**雪花 ID 永远是 string**（按 §0.1）。所有时间字段 ISO 8601 + UTC。

## 6. 可迁移到另一账号的打包流程（写进 README）

1. 复制 `D:\soul\miniprogram\` 整个目录到目标位置。
2. 修改 `project.config.json` 的 `appid` 为新账号 AppID。
3. 在新账号的 mp.weixin.qq.com → 开发管理 → 开发设置，把后端域名（Phase B 后）加入合法域名白名单。
4. 微信开发者工具"导入项目"，指向该目录。
5. 上传 → 提交审核。

**没有任何隐藏依赖**：所有资源在目录内；不依赖 `D:\soul\` 其他目录在运行时存在。

## 7. 非目标（明确不做）

- ❌ 不实现真 HTTP（Phase B 才做）。
- ❌ 不实现微信登录、支付、分享面板。
- ❌ 不实现 PDF 导出、社媒分享。
- ❌ 不引入 UI 组件库（Vant / TDesign）—— 直接 wxss，保持轻量与可控。
- ❌ 不做"角色登场"独立页（合并为 create→chat 转场动画位）。
- ❌ 不动 `D:\soul\mockup\` 原始设计稿。

## 8. 风险 & 决策点

- **TS 还是 JS**：选 **TypeScript**（小程序原生支持，类型对 API_CONTRACT 帮助极大）。
- **Tab 数量**：底部 4 个 tab（首页/新建/历史/我的）。新建作为 tab 同时也是路由，符合设计稿。
- **chat 页面进入路径**：从 home 的 research-card 或 history-card 点入，带 `evaluation_id` 参数；create 完成后 `wx.redirectTo` 到 chat。
- **流式协议**：Phase A 用 `setInterval` 逐字 mock 模拟流式；`services/stream.ts` 留好真实 SSE 解析接口，Phase B 替换实现。
