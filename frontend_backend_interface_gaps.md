# 前后端接口补齐记录

本文件记录当前小程序前端和后端接口不一致的功能。以后发现“前端已有、后端没有”或“后端已有、前端没有”的功能，先补到这里，避免遗漏。

## 后端已有、前端原来没有

### 退出登录

- 后端接口：`POST /api/v1/auth/logout`
- 原状态：后端已有，前端 `services/endpoints.ts` 和 `services/api.ts` 没有封装。
- 本次处理：前端新增 `AUTH_LOGOUT` 和 `api.logout()`，调用后端退出登录接口，并清理本地 `auth_token`。

## 前端已有、后端原来没有

### 删除历史调研记录

- 前端入口：`api.deleteEvaluation(id)`
- 前端接口：`DELETE /api/v1/evaluations/{evaluation_id}`
- 原状态：前端历史页已经调用，但后端没有对应路由，所以会返回 `405 Method Not Allowed`。
- 本次处理：后端新增同名接口，按当前数据模型执行软删除，删除后不会再出现在调研列表/历史列表中。

### 商业报告详情

- 前端入口：`api.getBusinessReportByEval(evalId)`
- 前端接口：`GET /api/v1/reports/by-evaluation/{evaluation_id}/business`
- 原状态：前端报告页、历史页、聊天页会调用，但后端没有对应路由，所以会返回 `404 Not Found`。
- 本次处理：后端新增同名接口，基于已有基础报告数据转换为前端 `BusinessReport` 结构返回。

### 报告导出 PDF

- 前端定义：`REPORT_EXPORT_PDF`
- 前端接口：`/reports/{report_id}/export-pdf`
- 当前状态：前端只定义了 endpoint，业务代码暂未实际调用；后端也没有该接口。
- 后续处理：等页面实际接入导出动作时，再补后端路由、PDF 生成服务和前端调用方法。

### 报告分享

- 前端定义：`REPORT_SHARE`
- 前端接口：`/reports/{report_id}/share`
- 当前状态：前端只定义了 endpoint，业务代码暂未实际调用；后端也没有该接口。
- 后续处理：等页面实际接入分享动作时，再补后端路由、分享 token 生成和前端调用方法。

### 深度研究报告（新增，待后端实现）

- 前端入口：`api.getDeepAnalysis(evalId)`，在 `report.ts` 的 `onLoad` 中并行预取
- 前端接口：`GET /api/v1/evaluations/{evaluation_id}/deep-analysis`
- 当前状态：**前后端均已完整实现**。
  - 前端：类型、端点、API 方法、UI、样式均已上线，有完整降级（请求失败时面板展开后显示"深度分析生成失败，请稍后重试"）。
  - 后端：commit `6bbeee2`，路由 `GET /evaluations/{evaluation_id}/deep-analysis`，`DeepAnalysisResponse`，`ReportService.get_deep_analysis()`。
- 后端实现：`app/schemas/report.py`（新增 `DeepAnalysisSectionItem`、`DeepAnalysisResponse`），`app/services/report_service.py`（新增 `get_deep_analysis`，调用 LLM 生成三节叙述），`app/routers/evaluation.py`（新增路由）。
- 完整契约见：`docs/superpowers/plans/2026-05-23-deep-analysis-panel.md` § Backend Contract Reference

## 接口存在但行为原来不兼容

### 会话创建

- 前端入口：`api.getConversation(evalId, personaId)`
- 前端接口：`POST /api/v1/conversations`
- 原状态：前后端都有接口，但后端要求该 `evaluation_id + persona_id` 必须已经有答卷 answer；前端聊天页可能先创建会话再补充展示内容，因此会收到 `400 Bad Request`。
- 本次处理：后端允许先创建会话；如果后续发送消息时缺少答卷，上下文会自动降级为空答卷上下文。

### 问卷流式生成

- 前端入口：`api.generateSurveyStream(evalId, productId, focus)`
- 前端接口：`POST /api/v1/surveys/generate-stream`
- 原状态：前后端都有接口，但后端先检查 evaluation 状态再返回已有问卷；已开始或已完成的调研重新进入问卷页时会返回错误。
- 本次处理：后端先返回已有问卷，只有确实需要新生成时才检查是否允许生成。
