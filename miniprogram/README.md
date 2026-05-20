# 测品官小程序（Phase A 前端骨架）

> 微信小程序 · TypeScript · 白底主题
> AI 消费者洞察平台 — 三位虚拟测品官（小芸 / 王姐 / 丛丛）协助产品调研

---

## 项目状态

**Phase A — 纯前端 + Mock 数据**
- 所有页面已落地（首页 / 新建 / 历史 / 我的 / 对话）
- 数据来自 `mocks/` 下的静态 fixture
- 后端接口在 `services/endpoints.ts` 中按 `D:\soul\docs\specs\API_CONTRACT.md` 全量声明，但尚未真实调用

切换到 Phase B（接真后端）只需两步：
1. `services/api.ts` 改 `export const USE_MOCK = false;`
2. `services/http.ts` 改 `export const BASE_URL = 'https://api.your-domain.com';`

---

## 本地运行

1. 用微信开发者工具（≥ 1.06.x）打开
2. 项目目录指向 `D:\soul\miniprogram\`
3. AppID 已写为 `touristappid`（游客模式，无需登录账号即可预览）

---

## 迁移到另一个微信账号

本项目是**独立目录**，不依赖 `D:\soul\` 下其他文件运行时存在。打包步骤：

1. 复制整个 `D:\soul\miniprogram\` 目录到目标位置
2. 修改 `project.config.json` 的 `appid` 字段：
   ```json
   "appid": "wxXXXXXXXXXXXXXXXX"
   ```
3. （可选）改 `project.config.json` 的 `projectname`
4. 微信开发者工具 → 导入项目 → 选择该目录 → 选对应 AppID
5. 上传 → 提交审核

---

## 切换到 Phase B（接真后端）的清单

- [ ] `services/api.ts`：`USE_MOCK = false`
- [ ] `services/http.ts`：填 `BASE_URL`
- [ ] mp.weixin.qq.com → 开发管理 → 开发设置 → request 合法域名加入后端域名
- [ ] 若使用 SSE 流式：检查后端 `Transfer-Encoding: chunked` 是否兼容小程序 `wx.request` 流式（必要时改成轮询或自建长链）
- [ ] `app.ts onLaunch` 中放开微信登录调用：`wx.login` → `api.wechatLogin(code)` → 存 token
- [ ] 删除 `mocks/` 目录或保留作为测试用

---

## 目录结构

```
miniprogram/
├── project.config.json          AppID + 编译设置
├── project.private.config.json  本地配置
├── app.json                     页面注册 + tabBar
├── app.ts / app.wxss            全局入口与全局样式
├── sitemap.json
├── tsconfig.json
│
├── styles/
│   ├── tokens.wxss              设计 Token（颜色 / 圆角 / 间距）
│   └── reset.wxss               基础重置
│
├── types/
│   ├── api.ts                   严格对齐 API_CONTRACT.md 的请求/响应类型
│   └── domain.ts                前端视图模型
│
├── services/
│   ├── endpoints.ts             所有接口路径常量（对齐 §11 速查表）
│   ├── http.ts                  wx.request 封装（JWT、错误映射）
│   ├── stream.ts                流式协议（Phase A 用 setInterval 模拟）
│   └── api.ts                   Adapter — 唯一对页面暴露的 API 入口
│
├── mocks/                       Phase A 数据（personas/evaluations/conversations/credits）
│
├── components/
│   ├── avatar/                  三位测品官头像
│   ├── badge/                   状态徽章
│   ├── chip/                    话题胶囊
│   ├── progress-bar/            进度条
│   ├── research-card/           首页调研卡
│   ├── bubble-think/            "内心独白" 气泡
│   └── bubble-speak/            "口头表达" 气泡
│
└── pages/
    ├── home/                    首页（hero + 统计 + 最近调研）
    ├── create/                  新建调研（话题 / 上传 / 选测品官）
    ├── chat/                    调研对话（双流：think + speak）
    ├── history/                 历史档案（搜索 + 筛选）
    └── profile/                 个人中心
```

---

## 设计参考

视觉来源：`D:\soul\mockup\index.html`

本项目相对设计稿的差异：
- **白底**主题，雾紫 `#7B6FA8` 作为强调色（设计稿是深紫黑）
- 产品名 = **测品官**（设计稿写"百面测品官"）
- 头像简化为 emoji + 渐变背景，未使用设计稿里的内联 SVG（保留升级空间）

---

## 接口契约

`D:\soul\docs\specs\API_CONTRACT.md` 是前后端唯一约定来源。本前端仅消费其中：

| 模块 | 接口 | 当前实现 |
|---|---|---|
| Auth §1 | `GET /auth/me` | mock |
| Product §2 | upload-url / create | 占位 |
| Persona §3 | list / recommend | mock 固定 3 位 |
| Evaluation §5 | create / attach / run / list | mock |
| Conversation §7 | get / send（流式） | mock setInterval 模拟 |
| Credit §8 | balance / transactions | mock |

Phase B 切真后端时仅 `services/api.ts` 内部分支变更，**页面代码不需要改**。
