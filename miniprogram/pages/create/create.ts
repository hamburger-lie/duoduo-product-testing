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
    createProgress: 0,
    createMsg: '',
  },

  _progressTimer: null as ReturnType<typeof setInterval> | null,

  _setProgress(pct: number, msg: string) {
    this.setData({ createProgress: Math.round(pct), createMsg: msg });
  },

  /** 在两个真实检查点之间平滑推进伪进度，上限 targetCap */
  _animateTo(targetCap: number) {
    if (this._progressTimer) clearInterval(this._progressTimer);
    this._progressTimer = setInterval(() => {
      const cur = this.data.createProgress;
      if (cur >= targetCap) return;
      this.setData({ createProgress: Math.min(targetCap, cur + 2) });
    }, 120);
  },

  _stopProgress() {
    if (this._progressTimer) { clearInterval(this._progressTimer); this._progressTimer = null; }
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
    this._setProgress(0, '准备中…');

    try {
      // 步骤 1：上传图片（0 → 35%）
      this._setProgress(5, this.data.productImages.length > 0 ? '上传产品图片…' : '准备产品信息…');
      this._animateTo(35);
      const imageObjectKeys = !USE_MOCK && this.data.productImages.length > 0
        ? await api.uploadProductImages(this.data.productImages)
        : [];

      // 步骤 2：创建产品（35 → 65%）
      this._setProgress(38, 'AI 分析产品信息…');
      this._animateTo(65);
      const product = await api.createProduct({
        ...(name ? { name: name.slice(0, 128) } : {}),
        description: desc || name,
        image_object_keys: imageObjectKeys,
      });

      // 步骤 3：创建调研（65 → 90%）
      this._setProgress(68, '生成调研方案…');
      this._animateTo(90);
      const evaluation = await api.createEvaluation(product.id);

      // 步骤 4：完成（90 → 100%）
      this._stopProgress();
      this._setProgress(100, '即将进入调研设置…');

      api.generateWhitepaper({
        evaluation_id: evaluation.id,
        product_name: shortProductName(name || product.name) || '未命名产品',
        product_description: desc || undefined,
      }).catch(() => {});

      redirected = true;
      wx.navigateTo({
        url: `/pages/survey-review/survey-review?evaluation_id=${evaluation.id}&product_id=${product.id}&generating=1&focus=${encodeURIComponent(desc.slice(0, 900))}`,
      });
    } catch (err: any) {
      this._stopProgress();
      const raw = err?.message || err?.code || '';
      const msg = raw.includes('request:fail')
        ? '无法连接后端，请先启动服务'
        : raw.includes('HTTP_401') || raw.includes('HTTP_403')
        ? '登录已过期，请重新登录'
        : String(raw).slice(0, 20) || '提交失败';
      wx.showToast({ title: msg, icon: 'none', duration: 3000 });
      console.error('[onSubmit]', JSON.stringify(err));
    } finally {
      if (!redirected) this.setData({ submitting: false, createProgress: 0, createMsg: '' });
    }
  },
});
