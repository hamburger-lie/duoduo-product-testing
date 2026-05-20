Page({
  data: {
    url: '',
  },

  onLoad(query: Record<string, string | undefined>) {
    const url = decodeURIComponent(query.url || '');
    if (!url) { wx.navigateBack(); return; }
    this.setData({ url });
    wx.setNavigationBarTitle({ title: '测品报告 PDF 导出' });
  },

  onMessage(e: any) {
    const messages = e.detail?.data || [];
    const latest = Array.isArray(messages) ? messages[messages.length - 1] : null;
    if (latest?.type === 'report_pdf_uploaded') {
      wx.showToast({ title: 'PDF 已同步', icon: 'success' });
    }
  },
});
