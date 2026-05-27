# 后端可维护化第一阶段收口

## 一、阶段目标

本阶段的目标不是把产品做成生产级系统，而是把仓库从“能跑的 MVP 后端”整理成“可维护、可协作、可继续演进的后端项目”。

核心判断标准：

- 主干验证可重复执行，而不是依赖个人口头确认。
- 文档、接口事实和实际实现不再互相打架。
- 高风险边界有最小护栏，后续重构不必继续在混乱中推进。
- provider 细节不继续渗入 service，关键链路能被测试和观测。

## 二、已完成 PR

| 阶段 | 主题 | 工程价值 |
|---|---|---|
| PR 0.5 | 验证基线修绿 | 先恢复 `ruff / mypy / pytest` 基线，避免在红灯上叠新改动 |
| PR 1 | CI 与验收命令统一 | 让 GitHub Actions 和本地验收口径一致 |
| PR 2 | 文档契约对齐 | 让 README、状态文档和接口事实说同一件事 |
| PR 3 | 错误 envelope 统一 | 收口 credits/recharge 的错误响应结构 |
| PR 4 | 权限隔离测试矩阵 | 给跨用户访问边界加回归护栏 |
| PR 5 | structured AI adapter 边界 | 把非流式 AI 细节从 service 下沉到 adapter |
| PR 6 | storage adapter 边界 | 把 mock upload 与 public URL 拼接收进 storage adapter |
| PR 7 | evaluation 状态边界 | 显式化 run / cancel / finalize 的现有状态规则 |
| PR 9 | pytest warning 清理 | 清除噪音，避免真实 warning 被长期背景噪声吞没 |
| PR 10 | evaluation observability | 让 run / task / persona / finalize 链路可追踪 |

> 注：PR 编号沿用阶段内工作命名，PR 8 为 evaluation reliability design / audit only，没有作为本阶段实现 PR 合并。

## 三、这一阶段解决了什么

### 1. 主干开始可验证

当前后端已有统一验收链路：

```bash
uv run ruff check .
uv run mypy app
uv run pytest
uv run alembic upgrade head
uv run alembic check
uv run python scripts/seed_personas.py
uv run python scripts/export_openapi.py
uv run python scripts/dev_check.py
```

配合 mock API 与 `scripts/e2e_mock_flow.py`，主干是否可用不再依赖个人经验。

### 2. 文档事实开始统一

`API_CONTRACT.md`、`README.md`、`backend/README.md`、`docs/API_STATUS.md`、`docs/DELIVERY_CHECKLIST.md` 已对齐以下事实：

- `report export-pdf / share` 当前未实现，属于 P1 planned。
- `credit balance / transactions` 已实现，`recharge` 仍返回 501。
- health live / ready 与实际接口一致。
- evaluation / Celery 属于 partial，而非生产可靠性已完成。

### 3. 关键边界开始清楚

- structured AI 调用已收敛到 AI adapter。
- 产品上传 URL 与 public URL 拼接已收敛到 storage adapter。
- evaluation 状态转移规则已显式化，不再散落在隐含条件里。

### 4. 高风险点有了最小护栏

- 权限隔离测试覆盖 owner / non-owner / list / detail / mutation。
- 错误结构有回归测试。
- evaluation 状态边界有回归测试。
- evaluation 链路具备基础结构化日志，可定位 request、task、persona、finalize。

## 四、现在 main 已具备的工程护栏

| 护栏 | 当前状态 |
|---|---|
| CI 门禁 | 已建立 |
| 统一验收命令 | 已建立 |
| 文档事实一致性 | 已收口 |
| 错误 envelope | 已统一 |
| 权限隔离回归测试 | 已补齐 |
| AI adapter 边界 | 已建立 |
| storage adapter 边界 | 已建立 |
| evaluation 状态边界 | 已显式化 |
| pytest warning 噪音 | 已清零 |
| evaluation observability | 已建立基础链路 |

## 五、明确不属于本阶段的事项

以下问题仍然重要，但它们属于后续产品化或生产化，不属于“可维护化第一阶段”是否完成的判定条件：

- 真实 TOS / OSS 接入
- 真实微信登录
- 充值 / 支付闭环
- report PDF / share
- 生产级内容审核
- mem0 / Qdrant 真实向量记忆
- evaluation watchdog / retry / 自动恢复
- 生产部署、监控、告警与密钥治理

## 六、后续三条路线

后续工作不再统一归入“继续整理仓库”，建议明确拆成三条路线：

| 路线 | 典型事项 |
|---|---|
| 产品能力线 | persona 质量、report 输出、PDF/share、充值闭环 |
| 生产可靠性线 | stale detection、durable schema、watchdog、retry/recovery |
| 基础设施线 | 真实 TOS、真实微信、部署、监控、告警 |

## 七、阶段结论

截至 PR 10 合并后，后端已经达到：

```text
可维护后端工程：已达成
生产级可靠性：未完成
商业闭环产品：未完成
```

因此，本阶段可以正式收口。后续新增工作应按新的路线单独立项，而不是继续无限延长“仓库整理”任务。
