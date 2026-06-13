import { api } from '../../services/api';
import type { Product } from '../../types/api';

Page({
  data: {
    product: null as Product | null,
    loading: true,
    imgIndex: 0,
    reanalyzing: false,
  },

  async onLoad(options: { id: string }) {
    if (!options.id) { wx.navigateBack(); return; }
    try {
      const product = await api.getProduct(options.id);
      wx.setNavigationBarTitle({ title: product.name });
      this.setData({ product, loading: false });
    } catch {
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onImgSwipe(e: any) {
    this.setData({ imgIndex: e.detail.current });
  },

  onPreviewImage(e: any) {
    const current = e.currentTarget.dataset.src as string;
    wx.previewImage({ current, urls: this.data.product!.image_urls });
  },

  async onReanalyze() {
    if (this.data.reanalyzing || !this.data.product) return;
    this.setData({ reanalyzing: true });
    try {
      const updated = await api.reanalyzeProduct(this.data.product.id);
      this.setData({ product: updated, reanalyzing: false });
      wx.showToast({ title: 'AI 分析已更新', icon: 'success' });
    } catch {
      this.setData({ reanalyzing: false });
      wx.showToast({ title: '分析失败，请重试', icon: 'none' });
    }
  },

  onStartEval() {
    const id = this.data.product?.id;
    if (!id) return;
    wx.navigateTo({ url: `/pages/create/create?product_id=${id}` });
  },
});
