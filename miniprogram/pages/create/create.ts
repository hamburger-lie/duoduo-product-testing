import { api, USE_MOCK } from '../../services/api';

function shortProductName(name: string): string {
  return Array.from(String(name || '').trim()).slice(0, 10).join('');
}

Page({
  data: {
    productName: '',
    productImages: [] as string[],
    researchDesc: '',
    submitting: false,
  },

  onProductNameInput(e: any) {
    this.setData({ productName: e.detail.value });
  },

  onDescInput(e: any) {
    this.setData({ researchDesc: e.detail.value });
  },

  onChooseImages() {
    wx.chooseMedia({
      count: 5 - this.data.productImages.length,
      mediaType: ['image'],
      success: res => {
        const paths = res.tempFiles.map(f => f.tempFilePath);
        this.setData({
          productImages: [...this.data.productImages, ...paths].slice(0, 5),
        });
      },
    });
  },

  onPreviewImage(e: any) {
    const idx = Number(e.currentTarget.dataset.idx);
    wx.previewImage({
      current: this.data.productImages[idx],
      urls: this.data.productImages,
    });
  },

  onRemoveImage(e: any) {
    const idx = Number(e.currentTarget.dataset.idx);
    const list = this.data.productImages.slice();
    list.splice(idx, 1);
    this.setData({ productImages: list });
  },

  async onSubmit() {
    if (this.data.submitting) return;
    let redirected = false;
    const desc = this.data.researchDesc.trim();
    const name = this.data.productName.trim();

    if (!USE_MOCK && desc.length < 10) {
      wx.showToast({ title: '产品描述至少 10 个字', icon: 'none', duration: 2500 });
      return;
    }
    if (!name) {
      wx.showToast({ title: '请填写产品名', icon: 'none', duration: 2500 });
      return;
    }
    this.setData({ submitting: true });
    wx.showLoading({ title: '创建产品中...' });

    try {
      const imageObjectKeys = !USE_MOCK && this.data.productImages.length > 0
        ? await api.uploadProductImages(this.data.productImages)
        : [];

      const product = await api.createProduct({
        ...(name ? { name: name.slice(0, 128) } : {}),
        description: desc || name,
        image_object_keys: imageObjectKeys,
      });

      wx.showLoading({ title: '生成调研方案...' });
      const evaluation = await api.createEvaluation(product.id);

      // Kick off whitepaper generation in parallel with the survey/chat flow.
      // The proxy call is long-running; we fire-and-forget here and poll later
      // from the report page. Failure here must not block survey navigation.
      api.generateWhitepaper({
        evaluation_id: evaluation.id,
        product_name: shortProductName(name || product.name) || '未命名产品',
        product_description: desc || undefined,
      }).catch(() => {});

      wx.hideLoading();
      redirected = true;
      // 问卷由 survey-review 页通过 SSE 流式生成（generating=1）
      wx.navigateTo({
        url: `/pages/survey-review/survey-review?evaluation_id=${evaluation.id}&product_id=${product.id}&generating=1&focus=${encodeURIComponent(desc.slice(0, 900))}`,
      });
    } catch (err: any) {
      wx.hideLoading();
      const raw = err?.message || err?.code || '';
      const msg = raw.includes('request:fail')
        ? '无法连接后端，请先启动服务'
        : raw.includes('HTTP_401') || raw.includes('HTTP_403')
        ? '登录已过期，请重新登录'
        : String(raw).slice(0, 20) || '提交失败';
      wx.showToast({ title: msg, icon: 'none', duration: 3000 });
      console.error('[onSubmit]', JSON.stringify(err));
    } finally {
      if (!redirected) this.setData({ submitting: false });
    }
  },
});
