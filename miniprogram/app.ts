// 测品官小程序 — 全局入口
// Phase A (USE_MOCK=true): 不调真接口，不需要登录
// Phase B (USE_MOCK=false): 首页底部弹窗触发用户主动授权登录

App({
  onLaunch(options: WechatMiniprogram.App.LaunchShowOption) {
    // 捕获分享裂变 ref 参数，登录时回传后端
    const ref = options.query?.ref;
    if (ref) {
      wx.setStorageSync('referral_code', ref);
    }
  },

  onError(msg: string) {
    // chooseAvatar:fail cancel is expected when user dismisses the avatar picker
    if (msg?.includes('chooseAvatar:fail cancel')) return;
    console.error('[app.onError]', msg);
  },
});
