# CLAUDE.md

本项目的 AI 编码助手全局规约以 `AGENTS.md` 为唯一主文件。

Claude 在执行任何代码任务前，必须先读取并遵守：

1. `AGENTS.md`
2. `docs/PRD.md`
3. `docs/TECH_DESIGN.md`
4. `API_CONTRACT.md`
5. `docs/TASKS.md`

执行规则：

- 每次只处理 `docs/TASKS.md` 中一个明确任务。
- 不允许擅自改 API 契约。
- 不允许删除已有功能。
- 不允许绕过测试、鉴权、内容审核、迁移。
- 完成后必须说明：改了哪些文件、如何验证、测试是否通过、剩余风险。

如 `CLAUDE.md` 与 `AGENTS.md` 冲突，以 `AGENTS.md` 为准。
