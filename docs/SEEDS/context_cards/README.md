# Context Cards (场景卡片)

场景卡片为 AI 人设注入动态情境变量，模拟真实消费者在不同状态下的决策差异。

## 使用方式

在调用 `render_prompt()` 时传入 `context_card` 参数（字符串），会被注入到 persona_answer.j2 的产品信息之前。

```python
prompt = render_prompt(
    "persona_answer.j2",
    persona=persona,
    product_ai_summary=product,
    survey_questions=questions,
    context_card="刚发了工资，心情不错，晚上躺在床上刷抖音，看到了这个产品的广告。"
)
```

## 设计原则

1. **可控性**：场景卡片是显式输入，不是 AI 自己编造的随机状态
2. **可复现**：同一场景卡片 + 同一人设 + 同一产品 = 可对比的结果
3. **正交性**：场景卡片影响心态和决策倾向，不改变角色的基本画像
