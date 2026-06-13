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

  onTapPrivacyPolicy() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  onTapShareInvite() {
    wx.navigateTo({ url: '/pages/share-invite/share-invite' });
  },

  onTapCustomize() {
    wx.navigateTo({ url: '/pages/customize/customize' });
  },

  onTapLoginHome() {
    wx.switchTab({ url: '/pages/home/home' });
  },

  onTapLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号？',
      confirmColor: '#EF4444',
      success: async (res) => {
        if (res.confirm) {
          try {
            await api.logout();
          } catch {
            // 即使服务端退出失败，也清理本地登录态，避免用户被卡住。
          }
          wx.removeStorageSync('auth_token');
          wx.setStorageSync('manual_logout', true);
          this.setData({ isLoggedIn: false });
          wx.switchTab({ url: '/pages/home/home' });
        }
      },
    });
  },

  onTapContact() {
    wx.showToast({ title: '联系我们 · 敬请期待', icon: 'none' });
  },
});
