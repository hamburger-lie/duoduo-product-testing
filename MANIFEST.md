# Generated Follow-up Docs

本包根据已上传的调研报告、PRD、TECH_DESIGN、API_CONTRACT 生成，用于补齐后续工程交付文件。

文件结构：

```text
docs/
  PROMPTS.md
  TASKS.md
  SEEDS/
    personas/
      persona_beauty_001.json
      persona_beauty_002.json
      persona_beauty_003.json
      persona_beauty_004.json
      persona_beauty_005.json
    survey_templates/
      beauty_survey_template.json
    report_templates/
      beauty_report_template.json
AGENTS.md
CLAUDE.md
```

使用方式：

1. 把 `docs/PROMPTS.md` 放入项目文档目录。
2. 把 `docs/SEEDS/` 中 JSON 按 TECH_DESIGN 规划复制到后端 `seeds/` 目录，或保留在 docs 做参考。
3. 把 `docs/TASKS.md` 作为 Claude/Codex 的实施任务清单。
4. 把 `AGENTS.md` 或 `CLAUDE.md` 放在项目根目录，作为 AI 编码助手规约。
