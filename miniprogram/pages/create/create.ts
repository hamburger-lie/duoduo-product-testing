import { api, USE_MOCK } from '../../services/api';
import type { ImageExtractResponse } from '../../types/api';

const CONFIDENCE_THRESHOLD = 0.8;

// 性能日志开关：正式版保持 false，本地调试时可临时改为 true
const DEBUG_PERF = false;

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
    // Extract state
    extracting: false,
    extractDone: false,
    extractError: '',
    extractNeedsReview: false,
    extractRawText: '',
    rawTextExpanded: false,
    lowConfidenceFields: '',
    fieldWarnings: {} as Record<string, boolean>,
    filledByAI: {} as Record<string, boolean>,
  },

  /** Track which fields the user has manually typed into */
  _userEdited: {} as Record<string, boolean>,
  /** Cached upload results from the extract flow (reused in onSubmit to avoid double upload) */
  _uploadedKeys: [] as string[],
  /** Extra extracted fields passed through to createProduct */
  _extractedBrand: undefined as string | undefined,
  _extractedPrice: undefined as number | undefined,
  _progressTimer: null as ReturnType<typeof setInterval> | null,

  _setProgress(pct: number, msg: string) {
    this.setData({ createProgress: Math.round(pct), createMsg: msg });
  },

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
    this._userEdited['productName'] = true;
    this.setData({ productName: e.detail.value });
  },

  onDescInput(e: any) {
    this._userEdited['researchDesc'] = true;
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
          // Reset extract state when images change
          extractDone: false,
          extractError: '',
        });
        // Invalidate cached upload keys since image set changed
        this._uploadedKeys = [];
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
    this.setData({
      productImages: list,
      extractDone: false,
      extractError: '',
    });
    this._uploadedKeys = [];
  },

  onToggleRawText() {
    this.setData({ rawTextExpanded: !this.data.rawTextExpanded });
  },

  // ============ Image Extract ============

  async onExtractFromImages() {
    if (this.data.extracting || this.data.productImages.length === 0) return;

    this.setData({ extracting: true, extractError: '', extractDone: false });
    const t0 = Date.now();

    try {
      // Step 1: Upload images and get both object_key and public image_url
      let imageUrls: string[];

      if (USE_MOCK) {
        // Mock mode: fabricate placeholder URLs
        imageUrls = this.data.productImages.map((_p, i) =>
          `https://mock-cdn.local/product_${i}.jpg`
        );
      } else {
        // Limit to first 2 images for extract (speed vs completeness trade-off)
        const imagesToUpload = this.data.productImages.slice(0, 2);
        if (this.data.productImages.length > 2) {
          if (DEBUG_PERF) console.log(`[extract] using first 2 of ${this.data.productImages.length} images for speed`);
        }
        const tUpload0 = Date.now();
        const uploadResults = await api.uploadProductImagesWithUrls(imagesToUpload);
        if (DEBUG_PERF) console.log(`[perf] upload ${imagesToUpload.length} images: ${Date.now() - tUpload0}ms`);
        // Cache object keys so onSubmit can skip re-uploading
        this._uploadedKeys = uploadResults.map(r => r.object_key);
        // Use the public image_url for the extract API
        imageUrls = uploadResults.map(r => r.image_url);
      }

      // Step 2: Call extract API with actual image URLs
      const tExtract0 = Date.now();
      const result: ImageExtractResponse = await api.extractFromImages({
        image_urls: imageUrls,
      });
      if (DEBUG_PERF) console.log(`[perf] extract-from-images API: ${Date.now() - tExtract0}ms`);

      // Step 3: Process result and apply to form with conflict detection
      await this._applyExtractResult(result);
      if (DEBUG_PERF) console.log(`[perf] onExtractFromImages total: ${Date.now() - t0}ms`);

    } catch (err: any) {
      if (DEBUG_PERF) console.log(`[perf] onExtractFromImages failed after: ${Date.now() - t0}ms`);
      let msg = '识别失败，请手动填写或稍后重试';
      const raw = err?.message || err?.code || '';
      if (raw.includes('timeout') || raw.includes('Timeout') || err?.code === 'IMAGE_EXTRACT_TIMEOUT') {
        msg = '识别超时，请减少图片后重试';
      } else if (raw.includes('IMAGE_TOO_LARGE') || err?.code === 'IMAGE_TOO_LARGE') {
        msg = '图片过大，请重新选择';
      } else if (raw.includes('IMAGE_URL_NOT_ACCESSIBLE') || err?.statusCode === 400) {
        msg = '图片无法访问，请重试';
      }
      this.setData({ extractError: String(msg).slice(0, 30) });
      console.error('[onExtractFromImages] message:', err?.message || err?.code, '\nstack:', err?.stack, '\nraw:', JSON.stringify(err));
    } finally {
      this.setData({ extracting: false });
    }
  },

  async _applyExtractResult(result: ImageExtractResponse) {
    const fields = result.fields || {};
    const warnings: Record<string, boolean> = {};
    const lowConfidence: string[] = [];
    const pendingUpdates: Record<string, string> = {};

    // --- Field mapping: backend field → form data key ---
    // name → productName (form input)
    if (fields['name']?.value) {
      const val = String(fields['name'].value);
      if (fields['name'].confidence < CONFIDENCE_THRESHOLD) {
        lowConfidence.push('产品名');
        warnings['productName'] = true;
      }
      pendingUpdates['productName'] = val;
    }

    // suggested_description → researchDesc (form textarea)
    // Compose from multiple extracted fields for a richer description
    if (result.suggested_description) {
      pendingUpdates['researchDesc'] = result.suggested_description;
      const descFields = ['selling_points', 'ingredients', 'claims', 'usage_scenario'];
      const hasLowConf = descFields.some(
        f => fields[f] && fields[f].confidence < CONFIDENCE_THRESHOLD
      );
      if (hasLowConf) {
        lowConfidence.push('产品描述');
        warnings['researchDesc'] = true;
      }
    }

    // brand → passed to createProduct (no dedicated form input, stored for submit)
    if (fields['brand']?.value) {
      this._extractedBrand = String(fields['brand'].value);
      if (fields['brand'].confidence < CONFIDENCE_THRESHOLD) {
        lowConfidence.push('品牌');
      }
    }

    // price → passed to createProduct (no dedicated form input, stored for submit)
    if (fields['price']?.value) {
      const parsed = parseFloat(String(fields['price'].value));
      if (!isNaN(parsed) && parsed > 0) {
        this._extractedPrice = parsed;
        if (fields['price'].confidence < CONFIDENCE_THRESHOLD) {
          lowConfidence.push('价格');
        }
      }
    }

    // Fields without a form input: category, specification, ingredients,
    // selling_points, usage_scenario, claims — only shown in the result card
    // and indirectly influence suggested_description. They contribute to
    // lowConfidence warnings but don't map to form fields.
    const displayOnlyFields: Record<string, string> = {
      category: '品类', specification: '规格', ingredients: '成分',
      selling_points: '卖点', usage_scenario: '使用场景', claims: '声称',
    };
    for (const [key, label] of Object.entries(displayOnlyFields)) {
      if (fields[key] && fields[key].confidence < CONFIDENCE_THRESHOLD && fields[key].value) {
        lowConfidence.push(label);
      }
    }


    // --- Conflict detection: only for fields with a form input ---
    const conflictFields: string[] = [];
    for (const [formKey, newValue] of Object.entries(pendingUpdates)) {
      const currentValue = (this.data as any)[formKey] as string;
      if (this._userEdited[formKey] && currentValue.trim() && currentValue !== newValue) {
        const label = formKey === 'productName' ? '产品名' : '产品描述';
        conflictFields.push(label);
      }
    }

    if (conflictFields.length > 0) {
      const confirmed = await new Promise<boolean>(resolve => {
        wx.showModal({
          title: '覆盖确认',
          content: `${conflictFields.join('、')}已有内容，是否用识别结果替换？`,
          confirmText: '替换',
          cancelText: '保留原值',
          success: (res) => resolve(res.confirm),
          fail: () => resolve(false),
        });
      });

      if (!confirmed) {
        for (const formKey of Object.keys(pendingUpdates)) {
          const currentValue = (this.data as any)[formKey] as string;
          if (this._userEdited[formKey] && currentValue.trim()) {
            delete pendingUpdates[formKey];
          }
        }
      }
    }

    // Track which form fields were filled by AI (for badge display)
    const filledByAI: Record<string, boolean> = {};
    for (const key of Object.keys(pendingUpdates)) {
      filledByAI[key] = true;
    }

    // Apply updates — note: setData does NOT trigger bindinput, so _userEdited is not polluted
    const payload = {
      ...pendingUpdates,
      extractDone: true,
      extractNeedsReview: result.needs_review,
      extractRawText: result.raw_text || '',
      rawTextExpanded: false,
      lowConfidenceFields: lowConfidence.join('、'),
      fieldWarnings: warnings,
      filledByAI,
    };
    this.setData(payload);
  },

  // ============ Submit (original logic, enhanced with extracted fields) ============

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
      // If extract flow already uploaded, reuse cached keys to avoid double upload
      this._setProgress(5, this.data.productImages.length > 0 ? '上传产品图片…' : '准备产品信息…');
      this._animateTo(35);
      let imageObjectKeys: string[];
      if (this._uploadedKeys.length > 0 && this._uploadedKeys.length === this.data.productImages.length) {
        imageObjectKeys = this._uploadedKeys;
      } else {
        imageObjectKeys = !USE_MOCK && this.data.productImages.length > 0
          ? await api.uploadProductImages(this.data.productImages)
          : [];
      }

      // 步骤 2：创建产品（35 → 65%）
      this._setProgress(38, 'AI 分析产品信息…');
      this._animateTo(65);
      const product = await api.createProduct({
        ...(name ? { name: name.slice(0, 128) } : {}),
        description: desc || name,
        image_object_keys: imageObjectKeys,
        // Pass through extracted fields if available
        ...(this._extractedBrand ? { brand: this._extractedBrand } : {}),
        ...(this._extractedPrice ? { price: this._extractedPrice } : {}),
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
