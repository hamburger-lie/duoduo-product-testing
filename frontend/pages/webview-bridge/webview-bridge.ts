Page({
  onLoad(query: Record<string, string | undefined>) {
    const target = decodeURIComponent(query.target || '');
    if (target === 'report-pdfs') {
      wx.redirectTo({ url: '/pages/report-pdfs/report-pdfs' });
      return;
    }
    wx.navigateBack();
  },
});
