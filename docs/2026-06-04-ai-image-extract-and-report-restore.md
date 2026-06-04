# 2026-06-04 AI 识图提取 & Report 页面恢复

## 1. 本次恢复来源

- **恢复来源**：`D:\workspace\soul2.0`（可用备份）
- **旧坏目录备份**：`D:\workspace\soul-broken-20260604-102412`
- 旧目录存在 UI 和功能被回退问题，从 soul2.0 完整恢复

---

## 2. 本次主要变更

### 小程序前端

#### create 页面 — AI 识图 UI 样式恢复
- `miniprogram/pages/create/create.wxss`：新增 AI 图片识别相关样式类
  - `.section-tag` / `.ai-tag`：标签样式
  - `.extract-card` / `.extract-card-inner`：AI 识别卡片布局
  - `.extract-notice`：识别结果提示区域

#### report 页面 — 完整版本恢复
- `miniprogram/pages/report/report.ts`：完整版（2282 行，101,888 bytes），从 soul2.0 恢复
- `miniprogram/pages/report/report.wxml`：报告页面模板完整恢复
- `miniprogram/pages/report/report.wxss`：报告页面样式完整恢复（4030 行）

#### AI 识图上传链路保留
- `miniprogram/services/endpoints.ts`：包含
  - `PRODUCT_UPLOAD_URL: '/products/upload-url'`
  - `PRODUCT_EXTRACT_FROM_IMAGES: '/products/extract-from-images'`
- `miniprogram/services/api.ts`：上传 + 识图 API 链路完整

#### 调试日志收口（默认关闭）
- `miniprogram/pages/report/report.ts`：`DEBUG_RADAR = false`（雷达图调试日志关闭）
- `miniprogram/pages/create/create.ts`：`DEBUG_PERF = false`（上传性能日志关闭）
- `miniprogram/services/api.ts`：`DEBUG_UPLOAD_PERF = false`（上传耗时日志关闭）
- 所有 `[radar]` / `[perf]` 日志默认不输出，本地调试时将对应开关改为 `true`

### 后端

- `backend/backend/app/ai/client.py`：AI 客户端更新
- `backend/backend/app/ai/moderation.py`：内容审核更新
- `backend/backend/app/ai/adapters/structured_generation.py`：结构化生成适配器
- `backend/backend/app/ai/prompts/persona_answer.j2`：Persona 回答 prompt 更新
- `backend/backend/app/ai/prompts/survey_generate.j2`：问卷生成 prompt 更新
- `backend/backend/app/db/models/report.py`：Report 数据模型更新
- `backend/backend/app/schemas/report.py`：Report Schema 更新
- `backend/backend/app/services/evaluation_service.py`：评测服务更新
- `backend/backend/app/services/report_service.py`：报告服务大幅扩展
- `backend/backend/app/tasks/evaluation_tasks.py`：评测任务更新
- `backend/backend/tests/`：对应测试文件更新

---

## 3. 已验证

- `tsc --noEmit`：✅ 0 错误
- create 页面 AI 识图 UI：✅ 恢复（上传区 + AI 识别卡片 + 结果提示）
- report 页面文件：✅ 完整版恢复（101.8KB report.ts）
- `PRODUCT_UPLOAD_URL` endpoint：✅ 存在
- `PRODUCT_EXTRACT_FROM_IMAGES` endpoint：✅ 存在
- 后端健康检查：✅ `{"status":"ok","service":"duoduo-product-testing-api"}`
- `.env` 已从工作区删除，不在本次提交中

---

## 4. 已知问题（存量，不是本次新增）

pytest 有 8 个存量失败，集中在：
- `test_evaluation_survey`（2 个）
- `test_frontend_route_contract`（2 个）
- `test_permission_matrix`（4 个）

这些失败在 soul2.0 备份中已存在，不是本次恢复引入的问题，后续单独分支处理。

---

## 5. 安全提醒

- **不提交** `.env` / `backend/backend/.env`（已从工作区删除）
- 密钥后续需要重新配置到本地 `.env` 或服务器环境变量
- 头像上传安全（SSRF 防护）后续单独分支处理，不在本次变更范围
