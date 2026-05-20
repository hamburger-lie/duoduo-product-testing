Component({
  properties: {
    personaKey:      { type: String,  value: 'yun' },
    personaName:     { type: String,  value: '' },
    personaId:       { type: String,  value: '' },
    avatarSlot:      { type: Number,  value: 0 },
    summaryComment:  { type: String,  value: '' },
    qaItems:         { type: Array,   value: [] },
    content:         { type: String,  value: '' },
    thinkContent:    { type: String,  value: '' },
    self:            { type: Boolean, value: false },
  },
  data: {
    /** 每题思考折叠状态，key = qi，默认收起（false） */
    expandedMap: {} as Record<number, boolean>,
    flatThinkExpanded: false,
    qaAnswersCollapsed: false,
    flatContentCollapsed: false,
    qaAnswerPreview: '',
  },
  observers: {
    'qaItems'(items: any[]) {
      if (!items || !items.length) return;
      const map = { ...this.data.expandedMap };
      let changed = false;
      items.forEach((_: any, i: number) => {
        if (map[i] === undefined) { map[i] = false; changed = true; }
      });
      const firstAnswer = items
        .map((item: any) => String(item?.answer || item?.question || '').trim())
        .find((text: string) => !!text) || '';
      const patch: Record<string, unknown> = {};
      if (changed) patch.expandedMap = map;
      if (firstAnswer !== this.data.qaAnswerPreview) patch.qaAnswerPreview = firstAnswer;
      if (Object.keys(patch).length) this.setData(patch);
    },
  },
  methods: {
    onToggleReason(e: any) {
      const qi: number = e.currentTarget.dataset.qi;
      const map = { ...this.data.expandedMap };
      map[qi] = !map[qi];
      this.setData({ expandedMap: map });
    },
    onToggleFlatThink() {
      this.setData({ flatThinkExpanded: !this.data.flatThinkExpanded });
    },
    onToggleQaAnswers() {
      this.setData({ qaAnswersCollapsed: !this.data.qaAnswersCollapsed });
    },
    onToggleFlatContent() {
      this.setData({ flatContentCollapsed: !this.data.flatContentCollapsed });
    },
    onAvatarTap() {
      if (this.properties.self) return;
      this.triggerEvent('avatarTap', {
        personaId:   this.properties.personaId,
        personaName: this.properties.personaName,
      });
    },
  },
});
