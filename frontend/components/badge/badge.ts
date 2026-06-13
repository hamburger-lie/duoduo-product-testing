Component({
  properties: {
    kind: { type: String, value: 'active' },   // 'active' | 'done' | 'failed' | 'canceled'
    text: { type: String, value: '' },
  },
});
