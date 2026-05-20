import { api, USE_MOCK } from '../../services/api';
import { resolveMediaUrl } from '../../services/http';
import type { User } from '../../types/api';

function fullAvatarUrl(path: string | null | undefined): string | null {
  const url = resolveMediaUrl(path);
  return url || null;
}

Page({
  data: {
    isLoggedIn: false,
    authLoading: false,
    avatarUploading: false,
    user: { id: '', nickname: '', avatar_url: null, role_type: null, credit_balance: 0 } as User,
  },

  async onShow() {
    try {
      const user = await api.getMe();
      this.setData({
        user: { ...user, avatar_url: fullAvatarUrl(user.avatar_url) },
        isLoggedIn: !!user.id,
      });
    } catch {
      this.setData({ isLoggedIn: false });
    }
  },

  onShareAppMessage() {
    const userId = this.data.user.id;
    return {
      title: '我在测品官用 AI 测评消费品，快来体验！',
      path: `pages/home/home${userId ? '?ref=' + userId : ''}`,
    };
  },

  async onGetPhoneNumber(e: any) {
    const detail = e.detail || {};
    const errMsg: string = detail.errMsg || '';
    const phoneOk = errMsg === 'getPhoneNumber:ok' || detail.errno === 0;
    const cancelled = errMsg.includes('cancel') || detail.errno === 20;

    if (cancelled) return;

    this.setData({ authLoading: true });
    try {
      const login_code = await new Promise<string>((resolve, reject) => {
        wx.login({ success: r => resolve(r.code), fail: reject });
      });

      let token: string;
      if (phoneOk && detail.code) {
        const res = await api.loginWithPhone(login_code, detail.code as string);
        token = res.token;
      } else {
        const res = await api.loginSilent(login_code);
        token = res.token;
      }

      wx.setStorageSync('auth_token', token);
      wx.removeStorageSync('manual_logout');
      wx.removeStorageSync('referral_code');

      const user = await api.getMe();
      this.setData({
        user: { ...user, avatar_url: fullAvatarUrl(user.avatar_url) },
        isLoggedIn: !!user.id,
      });
      wx.showToast({ title: '登录成功', icon: 'success' });
    } catch (err) {
      console.error('[profile] login failed', err);
      wx.showToast({ title: '登录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ authLoading: false });
    }
  },

  async onChooseAvatar(e: any) {
    const avatarUrl = e.detail?.avatarUrl as string | undefined;
    if (!avatarUrl) return;

    if (this.data.avatarUploading) return;
    this.setData({ avatarUploading: true });
    try {
      const res = await api.uploadAvatar(avatarUrl);
      const user = await api.updateProfile({ avatar_url: res.avatar_url });
      this.setData({
        user: { ...user, avatar_url: fullAvatarUrl(res.avatar_url) },
        avatarUploading: false,
      });
      wx.showToast({ title: '头像已更新', icon: 'success' });
    } catch {
      this.setData({ avatarUploading: false });
      wx.showToast({ title: '头像上传失败', icon: 'none' });
    }
  },

  async onNicknameChange(e: any) {
    const nickname = (e.detail?.value || '').trim();
    if (!nickname || nickname === this.data.user.nickname) return;
    try {
      const user = await api.updateProfile({ nickname });
      this.setData({ user: { ...user, avatar_url: fullAvatarUrl(user.avatar_url) } });
      wx.showToast({ title: '昵称已更新', icon: 'success' });
    } catch {
      wx.showToast({ title: '昵称保存失败', icon: 'none' });
    }
  },

  async onTapRole(e: any) {
    const role = e.currentTarget?.dataset?.role as string | undefined;
    if (!role) return;
    if (role === this.data.user.role_type) return;
    const roleLabel = role === 'manufacturer' ? '品牌方' : '渠道方';
    try {
      const user = await api.updateProfile({ role_type: role });
      this.setData({ user: { ...user, avatar_url: fullAvatarUrl(user.avatar_url) } });
      wx.showToast({ title: `已切换为${roleLabel}`, icon: 'success' });
    } catch {
      wx.showToast({ title: '角色切换失败', icon: 'none' });
    }
  },

  onTapPersonas() {
    wx.navigateTo({ url: '/pages/personas/personas' });
  },

  onTapProducts() {
    wx.navigateTo({ url: '/pages/products/products' });
  },

  onTapCredits() {
    wx.navigateTo({ url: '/pages/credits/credits' });
  },

  onTapReportPdfs() {
    wx.navigateTo({ url: '/pages/report-pdfs/report-pdfs' });
  },

  onTapSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  onTapShare() {
    // 通过 open-type="share" 的 button 触发
  },

  onTapContact() {
    wx.showToast({ title: '联系我们 · 敬请期待', icon: 'none' });
  },
});
