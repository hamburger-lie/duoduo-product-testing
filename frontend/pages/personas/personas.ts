import { api } from '../../services/api';
import type { PersonaSummary } from '../../types/api';
import { decoratePersonasWithAvatars, type AvatarDecorated } from '../../utils/personaAvatar';

Page({
  data: {
    personas: [] as Array<AvatarDecorated<PersonaSummary>>,
    loading: true,
  },

  async onLoad() {
    this.loadPersonas();
  },

  onShow() {
    // refresh after edit/create
    this.loadPersonas();
  },

  async loadPersonas() {
    this.setData({ loading: true });
    try {
      const items = await api.listPersonas({ is_system: false });
      this.setData({ personas: decoratePersonasWithAvatars(items), loading: false });
    } catch {
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onTapCard(e: any) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/persona-edit/persona-edit?id=${id}` });
  },
});
