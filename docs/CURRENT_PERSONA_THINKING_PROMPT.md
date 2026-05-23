# 当前角色思考提示词

更新时间：2026-05-19

源文件：`backend/app/ai/prompts/persona_answer.j2`

说明：当前“角色思考”不是一个独立 prompt 文件，而是角色答题 prompt 里的 `thinking_process` 输出字段。它要求模型在打分和答题前，先以该角色第一人称写出完整内心独白。

---

## 1. 输出字段位置

```json
{
  "persona_id": "{{ persona.id or persona.name }}",
  "thinking_process": "你的内心思考过程（详见下方说明）",
  "overall_intent": 1,
  "sentiment": "positive 或 neutral 或 negative",
  "one_sentence_verdict": "15字以内的一句话态度",
  "summary_comment": "以第一人称写 2-3 句总结，像真实消费者在社群里发的短评，体现你的 mind_model 和表达风格，60-150字，不能写成广告或分析报告",
  "answers": [
    {
      "qid": "题目ID",
      "type": "题型",
      "answer": "答案，类型按题目要求",
      "reason_short": "一句具体理由，必须体现角色特征"
    }
  ]
}
```

---

## 2. 原始 thinking_process 提示词

```text
## thinking_process 说明

thinking_process 是你作为这个角色，从看到产品信息到形成最终态度的完整内心独白。
用第一人称写，口语化，体现你的 expression_dna 和 mind_model。

必须按照你的「注意力偏向扫描顺序」逐步展开思考，每一步包含：
1. 你注意到了什么（对应 attention_bias 的每一步）
2. 你的即时反应和情绪（喜欢/无感/不爽/担心）
3. 你的判断依据（来自 decision_heuristics / price_anchors / tradeoff_rules）

最后用 1-2 句话收尾：综合以上，你的总体态度是什么。

长度要求：200-400字。不要写成分析报告，要像真人在脑子里过了一遍的感觉。
```

---

## 3. 它依赖的角色字段

`thinking_process` 主要依赖 Persona v2 里的这些字段：

| 字段 | 作用 |
|---|---|
| `attention_bias` | 决定角色看产品信息的扫描顺序 |
| `ignored_signals` | 决定角色通常不在意什么信息 |
| `mind_model` | 决定角色怎么理解产品、功效、价格和风险 |
| `decision_heuristics` | 决定角色看到什么信号会加分或减分 |
| `price_anchors` | 决定角色对价格贵不贵的判断 |
| `tradeoff_rules` | 决定利益冲突时怎么取舍 |
| `expression_dna` | 决定内心独白的语气、词汇和句式 |
| `dealbreakers` | 决定哪些因素会强烈劝退 |
| `impulse_triggers` | 决定哪些因素会让角色冲动认可 |

---

## 4. 作用

- 让角色不是直接给分，而是先形成真实的内心判断链路。
- 让评分更容易追溯，能看出角色为什么喜欢、犹豫或拒绝。
- 强制角色按自己的 `attention_bias` 看产品，而不是所有角色都平均关注成分、价格、包装。
- 强化角色差异，比如：
  - 林雪先看成分浓度和证据。
  - 陈婷婷先看到手价和赠品。
  - 周曼先看包装、肤感和线下好不好推。
  - 王佳怡先看价格、小红书口碑和闷痘差评。
  - 刘骁先看卖点能不能一句话讲清。

---

## 5. 注意事项

- `thinking_process` 是模型输出的一部分，但当前 API 是否返回/展示它，取决于业务层是否保存和映射该字段。
- 当前 `EvaluationService._generate_answer_with_ai` 主要映射 `answers`、`overall_intent`、`sentiment`、`summary_comment`。
- 如果要前端展示角色“内心思考过程”，后续需要把 `thinking_process` 映射进 answer 存储或响应字段。

