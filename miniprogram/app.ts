// 测品官小程序 — 全局入口
// Phase A (USE_MOCK=true): 不调真接口，不需要登录
// Phase B (USE_MOCK=false): onLaunch 自动走微信登录换 JWT

import { api, USE_MOCK } from './services/api';

App({
  onLaunch(options: WechatMiniprogram.App.LaunchShowOption) {
    // 捕获分享裂变 ref 参数，登录时回传后端
    const ref = options.query?.ref;
    if (ref) {
      wx.setStorageSync('referral_code', ref);
    }
    if (!USE_MOCK) {
      api.ensureAuth().catch(e => console.error('[app] ensureAuth failed', e));
    }
  },

  onError(msg: string) {
    // chooseAvatar:fail cancel is expected when user dismisses the avatar picker
    if (msg?.includes('chooseAvatar:fail cancel')) return;
    console.error('[app.onError]', msg);
  },
});
