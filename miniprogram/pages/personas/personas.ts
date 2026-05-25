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

  onTapCreate() {
    wx.navigateTo({ url: '/pages/persona-edit/persona-edit' });
  },

  onTapCard(e: any) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/persona-edit/persona-edit?id=${id}` });
  },

  async onDeletePersona(e: any) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '删除测品官',
      content: '确定要删除这位测品官吗？',
      confirmColor: '#EF4444',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await api.deletePersona(id);
          wx.showToast({ title: '已删除', icon: 'success' });
          this.loadPersonas();
        } catch {
          wx.showToast({ title: '删除失败', icon: 'none' });
        }
      },
    });
  },
});
