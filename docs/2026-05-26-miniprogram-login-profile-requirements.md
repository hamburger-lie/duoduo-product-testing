# 美博会测品官小程序用户授权登录需求与技术实现

## 1. 项目目标

美博会测品官小程序需要建立清晰、真实、可上线的用户登录体系。用户打开小程序后，先进入现有首页，也就是“小侦探”所在的首页画面；如果用户未登录，则在首页底部弹出微信手机号授权登录弹窗。用户必须完成授权登录后，才能正常使用创建产品、测评、历史档案、报告、个人中心、积分等业务功能。

本期目标不是做独立登录页，也不是账号密码系统，而是打通微信小程序官方登录链路：

```text
小程序首页
-> 用户点击手机号授权
-> wx.login 获取 login code
-> getPhoneNumber 获取 phone_code
-> 小程序调用后端登录接口
-> 后端调用微信接口换 openid / unionid / phone_number
-> 后端写入 users 表
-> 后端签发业务 token
-> 小程序后续请求都带 token
-> 后端按 current_user.id 隔离所有业务数据
```

最终结果：

1. 每个微信账号在系统内对应一条独立用户记录。
2. 用户真实授权手机号保存到后端数据库。
3. 不同用户的产品、测评、历史、报告、对话、积分、个人资料互相隔离。
4. 个人中心展示当前登录用户的头像、昵称、脱敏手机号和积分。
5. 当前没有域名和正式服务器时，可以先在本地完成代码和联调；上线时再切换 HTTPS 域名和微信后台配置。

## 2. 当前阶段说明

当前项目处于“本地先完成登录能力，服务器和域名后续补齐”的阶段。

本地开发时：

```text
小程序开发者工具
-> http://127.0.0.1:18000
-> 本地后端 FastAPI
-> 本地 PostgreSQL 数据库
```

上线后：

```text
正式小程序
-> https://你的后端域名
-> 线上后端服务
-> 线上数据库
```

阶段边界：

1. 域名和服务器没完成，不阻塞先做前端授权弹窗、后端入库、数据隔离。
2. 本地调试可以使用 `http://127.0.0.1:18000`，微信开发者工具需要勾选“不校验合法域名”。
3. 真机预览和正式上线必须使用 HTTPS 域名，并在微信公众平台配置 request 合法域名。
4. 本地自动化测试和本地调试允许 mock openid 或 mock 手机号。
5. 真实验收和生产环境必须配置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`，并调用微信真实接口。

## 3. 微信官方能力边界

根据微信小程序官方登录能力，前端不能直接拿到用户身份主数据，必须通过开发者服务器完成登录。

| 信息 | 是否能获取 | 获取方式 | 说明 |
| --- | --- | --- | --- |
| 真实微信号 | 否 | 无 | 微信官方不向小程序开放真实微信号 |
| `openid` | 是 | `wx.login` + 后端 `auth.code2Session` | 当前小程序内唯一用户标识 |
| `unionid` | 条件可获取 | `auth.code2Session` | 需要小程序绑定微信开放平台 |
| 手机号 | 是 | `button open-type="getPhoneNumber"` + 后端手机号接口 | 必须用户主动授权 |
| 头像 | 是 | `button open-type="chooseAvatar"` | 必须用户主动选择 |
| 昵称 | 是 | `input type="nickname"` | 必须用户主动填写或确认 |
| `session_key` | 后端可获取 | `auth.code2Session` | 不能返回给小程序前端 |

关键限制：

1. `wx.login` 返回的 `code` 只能使用一次。
2. `code` 必须传给后端，由后端调用微信 `auth.code2Session`。
3. `session_key` 是敏感信息，只能留在后端，不能下发给小程序。
4. 小程序不能静默获取真实微信头像和昵称。
5. 小程序不能获取真实微信号。

参考资料：

- 微信小程序登录：https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html
- `wx.login`：https://developers.weixin.qq.com/miniprogram/dev/api/open-api/login/wx.login.html
- 手机号快速验证：https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/getPhoneNumber.html

## 4. 用户数据回传和入库

用户数据回传到自己的后端，不回传到微信，也不长期存储在小程序前端。

数据流：

```text
用户点击微信手机号登录
-> 小程序拿到 login_code 和 phone_code
-> POST /api/v1/auth/wechat/login
-> 后端用 login_code 调微信 code2Session
-> 后端拿到 openid / unionid
-> 后端用 phone_code 调微信手机号接口
-> 后端拿到 phone_number
-> 后端按 openid 查 users 表
-> 不存在则创建 users 记录
-> 存在则复用 users 记录并更新手机号等资料
-> 后端返回 token + user
```

用户主记录位置：

```text
后端数据库
-> users 表
-> backend/backend/app/db/models/user.py
-> User 模型
```

数据库连接由后端环境变量 `DATABASE_URL` 决定，读取位置为：

```text
backend/backend/app/core/config.py
```

当前本地示例：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/duoduo
```

`users` 表需要保存：

| 字段 | 说明 |
| --- | --- |
| `id` | 系统内用户 ID，所有业务数据按这个 ID 归属 |
| `openid` | 微信小程序内用户唯一标识 |
| `unionid` | 微信开放平台统一标识，满足条件时保存 |
| `phone_number` | 用户授权手机号，后端保存完整值 |
| `nickname` | 用户主动填写或确认的昵称 |
| `avatar_url` | 用户主动选择或上传的头像 |
| `role_type` | 用户角色类型 |
| `credit_balance` | 用户积分余额 |
| `status` | 用户状态 |
| `created_at` / `updated_at` | 创建和更新时间 |

前端展示时：

1. 个人中心默认展示脱敏手机号，例如 `138****1234`。
2. 小程序本地只保存 `auth_token` 和必要的展示缓存。
3. 不在小程序本地长期保存完整手机号。

## 5. 账号与数据隔离规则

账号隔离以服务端 token 解析出的 `current_user.id` 为准，不能相信前端传入的用户 ID。

规则：

1. 每个 `openid` 对应 `users` 表中的一条独立用户记录。
2. 同一个微信账号再次登录时，复用同一条 `users` 记录。
3. 不同微信账号登录时，创建或使用不同 `users` 记录。
4. 产品、测评、历史档案、报告、对话、积分流水、个人资料都必须归属到当前 `users.id`。
5. 所有业务列表接口必须按 `current_user.id` 查询。
6. 所有业务详情接口必须校验资源属于 `current_user.id`。
7. 用户 A 不能看到或操作用户 B 的产品、测评、历史、报告、对话、积分和个人资料。
8. 用户切换微信账号后，前端必须重新拉取当前账号数据，不能沿用旧账号页面缓存。
9. 原来已有的历史数据如果要归到当前登录微信号，必须把历史业务数据的 `user_id` 指向当前用户的 `users.id`。

需要重点检查的业务表：

| 业务 | 隔离字段 |
| --- | --- |
| 产品 | `products.user_id` |
| 测评 | `evaluations.user_id` |
| 对话 | `conversations.user_id` |
| 积分流水 | `credit_transactions.user_id` |
| 自定义人群 | `personas.owner_id` |
| 报告 | 通过测评或报告关联的用户归属判断 |
| 历史档案 | 通过测评和产品的用户归属判断 |

## 6. 前端需求

### 6.1 首页登录入口

不新增独立登录页。用户打开小程序后仍进入原首页，保留现有“小侦探”首页画面。

未登录时：

1. 首页底部弹出用户授权登录弹窗。
2. 弹窗从底部出现，可带半透明遮罩。
3. 弹窗不可点击遮罩关闭。
4. 用户只能选择微信手机号登录，或退出小程序。
5. 用户点击业务入口时，不跳转登录页，而是保持首页弹窗并提示需要登录。

已登录时：

1. 不展示授权弹窗。
2. 首页按原有逻辑加载当前用户可见的数据。
3. 所有业务入口正常可用。

弹窗按钮：

```xml
<button
  open-type="getPhoneNumber"
  bindgetphonenumber="onGetPhoneNumber"
>
  微信手机号登录
</button>
```

退出入口：

```xml
<navigator target="miniProgram" open-type="exit">
  暂不使用，退出小程序
</navigator>
```

### 6.2 登录流程

前端登录流程：

```text
onGetPhoneNumber
-> 判断 e.detail.errMsg 是否为 getPhoneNumber:ok
-> 读取 e.detail.code 作为 phone_code
-> 调用 wx.login 获取 login_code
-> api.loginWithPhone(login_code, phone_code)
-> 保存 auth_token
-> 保存当前用户基础信息
-> 关闭首页底部授权弹窗
-> 重新拉取首页和个人中心数据
```

失败处理：

| 场景 | 前端行为 |
| --- | --- |
| 用户取消手机号授权 | 留在首页，继续展示底部授权弹窗 |
| `e.detail.code` 不存在 | 提示“手机号授权失败，请重试” |
| `wx.login` 失败 | 提示“微信登录失败，请重试” |
| 后端登录失败 | 提示“登录失败，请稍后重试” |
| token 失效 | 清除 token，重新展示首页底部授权弹窗 |

### 6.3 取消静默登录

`app.ts` 不应在启动时静默调用 `api.ensureAuth()`。启动时只保留分享参数、基础初始化和错误监听。

原因：

1. 本期需要用户主动授权手机号。
2. 静默登录只能拿 openid，不能拿手机号。
3. 用户未授权时不能直接创建完整业务账号。
4. 登录入口应由首页底部弹窗承载。

### 6.4 业务入口拦截

所有业务入口在跳转前都需要检查登录态。

未登录时：

1. 不跳转业务页。
2. 首页展示底部授权弹窗。
3. 显示轻提示“请先完成授权登录”。

需要拦截的入口：

1. 首页开始调研。
2. 首页人群气泡进入详情。
3. 创建产品。
4. 历史档案。
5. 报告。
6. 个人中心。
7. 积分页面。
8. 设置页面。

业务页被直接打开但没有 token 时：

1. 停止加载业务数据。
2. 清理无效 token。
3. 返回首页或提示后回到首页。
4. 首页继续展示授权弹窗。

### 6.5 个人中心

个人中心只负责展示和完善资料，不作为主登录入口。

登录后展示：

1. 头像：优先展示用户主动选择的头像，没有则展示默认头像。
2. 昵称：优先展示用户主动填写或确认的昵称，没有则展示“未设置”。
3. 手机号：展示后端返回的脱敏手机号。
4. 积分：展示 `credit_balance`。

资料完善：

```xml
<button open-type="chooseAvatar" bindchooseavatar="onChooseAvatar">
  选择头像
</button>
```

```xml
<input
  type="nickname"
  value="{{user.nickname}}"
  bindchange="onNicknameChange"
  placeholder="点击设置昵称"
/>
```

## 7. 后端需求

### 7.1 登录接口

继续使用现有接口：

```http
POST /api/v1/auth/wechat/login
```

请求体：

```json
{
  "code": "wx.login 返回的 code",
  "phone_code": "getPhoneNumber 返回的 code",
  "ref_code": "可选分享邀请码"
}
```

响应体：

```json
{
  "token": "业务 JWT",
  "expires_in": 604800,
  "user": {
    "id": "7280000000000000",
    "nickname": "未设置",
    "avatar_url": null,
    "role_type": null,
    "credit_balance": 1000,
    "phone_number": "13800138000",
    "phone_masked": "138****8000",
    "is_new_user": true
  }
}
```

要求：

1. `code` 必传。
2. 本期用户强制登录场景中，`phone_code` 必传。
3. 本地测试可允许仅传 `code` 走 mock 登录。
4. 生产和真实验收必须传真实 `phone_code`。
5. 后端不能返回 `session_key`。
6. 后端日志不能记录完整 `code`、`phone_code`、手机号和完整 `openid`。

### 7.2 当前用户接口

继续使用：

```http
GET /api/v1/auth/me
```

要求：

1. 必须带 `Authorization: Bearer <token>`。
2. 返回当前 token 对应的用户资料。
3. 返回手机号脱敏字段 `phone_masked`。
4. 不能通过前端传入用户 ID 查询用户资料。

### 7.3 资料更新接口

继续使用：

```http
PATCH /api/v1/auth/profile
```

可更新：

1. `nickname`
2. `avatar_url`
3. `role_type`

要求：

1. 只能更新当前登录用户。
2. 不能更新其他用户资料。
3. 手机号不通过该接口修改，本期不做手机号换绑。

## 8. 当前代码状态

### 8.1 后端已有能力

当前后端已经具备以下能力：

1. `POST /api/v1/auth/wechat/login`。
2. `WechatLoginRequest` 支持 `code`、`phone_code`、`ref_code`。
3. `AuthService` 支持真实 `code2Session`。
4. `AuthService` 支持通过 `phone_code` 调微信手机号接口。
5. `users` 表模型包含 `phone_number` 字段。
6. 登录后按 `openid` 创建或复用用户。
7. 登录后返回 JWT token。
8. `GET /api/v1/auth/me` 返回当前用户资料。
9. 多数业务接口通过 `get_current_user` 获取当前用户。
10. 产品、测评、对话、积分等服务已大量使用 `user.id` 做查询条件。

### 8.2 前端已有能力

当前前端已经具备以下能力：

1. `api.loginWithPhone(code, phone_code)`。
2. `api.loginSilent(code)`。
3. `request` 自动带 `Authorization`。
4. 本地 `auth_token` 存储。
5. 个人中心已有头像选择和昵称输入逻辑。
6. 首页已有“小侦探”画面和业务入口。

### 8.3 仍需完成

后续实现时重点做这些：

1. 首页增加底部授权登录弹窗。
2. 取消 `app.ts` 启动静默登录。
3. 建立统一 `requireAuth` 入口拦截。
4. 首页 `onGetPhoneNumber` 完成手机号授权登录。
5. 登录成功后清理旧账号页面缓存并重新拉取数据。
6. 个人中心展示脱敏手机号。
7. 为业务数据隔离补充测试。
8. 清理 `app.json` 中错误页面配置，不能把组件路径注册到 `pages`。

## 9. 技术实现计划

### Task 1: 前端登录状态工具

文件：

```text
miniprogram/utils/auth.ts
miniprogram/services/api.ts
```

目标：

1. 提供 `hasToken()`。
2. 提供 `loginWithPhoneCode(phone_code)`。
3. 提供 `clearAuth()`。
4. 登录成功后统一保存 `auth_token` 和用户资料。

建议接口：

```ts
export function hasToken(): boolean;
export function clearAuth(): void;
export function getStoredUser(): User | null;
export async function loginWithPhoneCode(phoneCode: string): Promise<User>;
```

### Task 2: 首页底部授权弹窗

文件：

```text
miniprogram/pages/home/home.ts
miniprogram/pages/home/home.wxml
miniprogram/pages/home/home.wxss
```

目标：

1. 首页未登录时展示底部授权弹窗。
2. 弹窗不替换原首页。
3. 弹窗按钮使用 `open-type="getPhoneNumber"`。
4. 用户取消授权时停留首页。
5. 登录成功后关闭弹窗并重新加载首页数据。

### Task 3: 取消启动静默登录

文件：

```text
miniprogram/app.ts
```

目标：

1. 删除启动时 `api.ensureAuth()`。
2. 保留分享参数 `ref` 存储。
3. 不在 `app.ts` 跳转登录页。

### Task 4: 业务入口统一拦截

文件：

```text
miniprogram/pages/home/home.ts
miniprogram/pages/profile/profile.ts
miniprogram/pages/history/history.ts
miniprogram/pages/create/create.ts
```

目标：

1. 进入业务页前检查 token。
2. 未登录时回到首页或显示首页弹窗。
3. 不能加载旧账号缓存数据。

### Task 5: 个人中心展示当前用户资料

文件：

```text
miniprogram/pages/profile/profile.ts
miniprogram/pages/profile/profile.wxml
miniprogram/pages/profile/profile.wxss
miniprogram/types/api.ts
```

目标：

1. 展示当前用户昵称、头像、脱敏手机号和积分。
2. 支持用户主动修改头像和昵称。
3. 未登录时不在个人中心弹独立登录页，提示回首页授权。

### Task 6: 后端验证与补强

文件：

```text
backend/backend/tests/test_auth.py
backend/backend/tests/test_frontend_route_contract.py
backend/backend/tests/test_error_codes.py
```

目标：

1. 确认 `code + phone_code` 可以创建用户并保存手机号。
2. 确认同一 `openid` 复用同一用户。
3. 确认不同 `openid` 对应不同用户。
4. 确认返回值包含 `phone_masked`。
5. 确认后端不返回 `session_key`。

### Task 7: 数据隔离测试

文件：

```text
backend/backend/tests/
```

目标：

1. 用户 A 创建产品后，用户 B 看不到。
2. 用户 A 创建测评后，用户 B 访问详情失败。
3. 用户 A 的报告、对话、积分流水不出现在用户 B 的列表中。
4. 所有业务接口都以 token 对应用户为准，不接受前端传入用户 ID 改归属。

## 10. 本地联调流程

### 10.1 启动后端

```powershell
cd D:\soul\backend
.\start_dev.bat
```

或：

```powershell
cd D:\soul\backend\backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 18000 --reload
```

验证：

```text
http://127.0.0.1:18000/health
```

### 10.2 数据库迁移

```powershell
cd D:\soul\backend\backend
uv run alembic upgrade head
```

### 10.3 小程序开发者工具

1. 打开 `D:\soul\miniprogram`。
2. 勾选“不校验合法域名”。
3. 清除编译缓存。
4. 编译小程序。
5. 确认首页出现“小侦探”画面。
6. 未登录时看到底部授权弹窗。
7. 点击手机号授权。
8. 登录成功后确认后端 `users` 表出现用户记录。

## 11. 验收标准

### 11.1 本地开发验收

1. 小程序能正常打开原首页。
2. `app.json` 不包含不存在的页面路径。
3. 未登录时首页底部出现授权登录弹窗。
4. 用户取消手机号授权后不会生成 `auth_token`。
5. 用户同意手机号授权后，小程序保存 `auth_token`。
6. 后端 `users` 表能看到用户记录。
7. 用户记录包含 `openid`。
8. 有手机号授权时，用户记录包含 `phone_number`。
9. 个人中心展示脱敏手机号。
10. 后端响应不包含 `session_key`。

### 11.2 账号隔离验收

1. 同一个微信账号再次登录时复用同一条用户记录。
2. 不同微信账号登录时使用不同用户记录。
3. 用户 A 的产品，用户 B 看不到。
4. 用户 A 的测评，用户 B 访问不到。
5. 用户 A 的历史、报告、对话、积分，用户 B 看不到。
6. 切换账号后，前端不会继续展示上一个账号的数据。

### 11.3 真实微信验收

真实验收前必须配置：

```env
WECHAT_APP_ID=真实小程序 AppID
WECHAT_APP_SECRET=真实小程序 AppSecret
```

验收项：

1. 登录接口使用真实 `wx.login` code。
2. `users.openid` 不是 mock 值。
3. 手机号来自真实 `getPhoneNumber` 授权和微信手机号接口。
4. `users.phone_number` 不是 mock 值。
5. 生产和验收环境没有使用 `WECHAT_MOCK_OPENID`。

## 12. 上线切换清单

上线前需要完成：

1. 购买域名。
2. 如果服务器在中国大陆，完成 ICP 备案。
3. 域名解析到服务器 IP。
4. 服务器部署后端代码。
5. 服务器部署 PostgreSQL 或连接云数据库。
6. 生产 `.env` 配置 `DATABASE_URL`。
7. 生产 `.env` 配置 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET`。
8. 配置 Nginx 反向代理。
9. 配置 HTTPS 证书。
10. 验证 `https://你的域名/health` 可访问。
11. 微信公众平台配置 request 合法域名。
12. 小程序前端 `BASE_URL` 从本地地址切换为 HTTPS 域名。
13. 使用体验版小程序完成真实登录和数据隔离验收。

上线后请求链路：

```text
正式小程序
-> https://api.your-domain.com/api/v1/auth/wechat/login
-> 线上后端
-> 微信官方接口
-> 线上数据库 users 表
```

## 13. 安全与合规

1. 小程序端不能保存 `WECHAT_APP_SECRET`。
2. 后端不能把 `session_key` 返回给小程序。
3. 日志不能完整记录 `code`、`phone_code`、手机号、完整 `openid`。
4. 个人中心默认展示脱敏手机号。
5. 除登录、健康检查外，业务接口继续要求 `Authorization: Bearer <token>`。
6. 后端不能信任前端传入的用户 ID。
7. 所有用户相关数据查询必须带当前用户条件。
8. 生产和验收环境不得使用 mock openid、mock unionid 或 mock 手机号作为真实用户数据。
9. 本期不做真实微信号获取，因为微信官方不开放。
10. 本期不做手机号换绑，避免账号归属规则不清导致数据混乱。

## 14. 回滚方案

如果登录功能上线后出现问题：

1. 前端可临时让首页底部弹窗提示“登录服务维护中”，不允许进入业务页。
2. 后端保留 `phone_number` 字段，不影响旧用户数据。
3. 如果微信手机号接口异常，禁止创建不完整正式账号，避免后续数据归属混乱。
4. 如果 token 校验异常，清除本地 token，并要求用户重新授权登录。
5. 数据库迁移不建议立即回滚，空字段对旧逻辑无影响。

