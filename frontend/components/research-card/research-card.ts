// 调研卡片 — 首页 "最近调研" 行内卡片
// 历史档案的卡片有不同布局，单独在 history 页内实现

Component({
  properties: {
    card: { type: Object, value: null as any },   // EvaluationCardVM
  },
  methods: {
    onTap() {
      const card = this.data.card as any;
      if (!card) return;
      this.triggerEvent('tap', { id: card.id });
    },
  },
});
