Page({
  data: {
    url: '',
  },

  onLoad(query: Record<string, string | undefined>) {
    const url = decodeURIComponent(query.url || '');
    if (!url) { wx.navigateBack(); return; }
    this.setData({ url });
    wx.setNavigationBarTitle({ title: '测品报告导出' });
  },

  onMessage(e: any) {
    const messages = e.detail?.data || [];
    const latest = Array.isArray(messages) ? messages[messages.length - 1] : null;
    if (latest?.type === 'report_pdf_uploaded') {
      wx.showModal({
        title: 'PDF 已同步',
        content: '报告已保存到个人中心的「调研报告 PDF」。',
        confirmText: '去查看',
        cancelText: '留在此页',
        success: res => {
          if (!res.confirm) return;
          wx.navigateTo({ url: '/pages/report-pdfs/report-pdfs' });
        },
      });
    }
  },
});
