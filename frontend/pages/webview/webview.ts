Page({
  data: {
    url: '',
  },

  onLoad(query: Record<string, string | undefined>) {
    const url = decodeURIComponent(query.url || '');
    console.log('[webview] loading url:', url);
    if (!url) { wx.navigateBack(); return; }
    this.setData({ url });
    wx.setNavigationBarTitle({ title: '详细报告导出' });
  },

  onMessage(_e: any) {
    // no-op
  },
});
