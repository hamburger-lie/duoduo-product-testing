Component({
  properties: {
    text: { type: String, value: '' },
    selected: { type: Boolean, value: false },
  },
  methods: {
    onTap() {
      this.triggerEvent('tap');
    },
  },
});
