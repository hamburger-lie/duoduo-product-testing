import { api } from '../../services/api';

Page({
  data: {
    userId: '',
  },

  async onLoad() {
    try {
      const user = await api.getMe();
      this.setData({ userId: user.id });
    } catch {
      // Not logged in — page still renders, share link won't carry ref
    }
  },

  onShareAppMessage() {
    const userId = this.data.userId;
    return {
      title: '我在测品官用 AI 测评消费品，快来体验！注册即送 50 积分',
      path: `/pages/home/home${userId ? '?ref=' + userId : ''}`,
    };
  },

  onShareTimeline() {
    const userId = this.data.userId;
    return {
      title: '用 AI 测品，快来体验测品官！注册即送 50 积分',
      query: userId ? `ref=${userId}` : '',
    };
  },
});
