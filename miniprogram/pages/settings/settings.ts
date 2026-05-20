Page({
  data: {
    version: 'v1.0.0',
  },

  onTapPrivacy() {
    wx.openPrivacyContract({
      fail: () => {
        wx.showToast({ title: '隐私政策暂未配置', icon: 'none' });
      },
    });
  },

  onTapAgreement() {
    wx.showModal({
      title: '用户协议',
      content:
        '欢迎使用测品官。\n\n' +
        '本服务用于 AI 驱动的消费品测评。使用本服务时请遵守相关法律法规，不得用于违法用途。\n\n' +
        '本协议持续更新中，详细条款敬请关注后续版本。如有疑问请通过"联系我们"与我们沟通。',
      showCancel: false,
      confirmText: '知道了',
    });
  },

  onTapLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号？',
      confirmColor: '#EF4444',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync('auth_token');
          wx.setStorageSync('manual_logout', true);
          wx.navigateBack();
        }
      },
    });
  },
});
