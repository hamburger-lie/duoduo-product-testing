// API 适配层 — 所有页面只 import 本文件
// Phase A: USE_MOCK=true，调 mocks/*
// Phase B: USE_MOCK=false，调真后端 (http://127.0.0.1:18000)
//
// 切换方式：把 USE_MOCK 改成 false，并在 DevTools 详情→本地设置勾选"不校验合法域名"

import type {
  CursorPaged, User, CreditBalance, CreditTransaction,
  Evaluation, EvaluationAnswer, Survey, SurveyQuestion, Conversation, Message, PersonaSummary,
  Product, CreateProductReq, UploadUrlRes, PersonaDetail, BackendReport, BusinessReport,
  AvatarUploadRes, ProfileUpdateReq, ReportPdfListResponse, DeepAnalysis,
  ImageExtractResponse,
} from '../types/api';
import type {
  EvaluationCardVM, PersonaWithKey,
} from '../types/domain';

import { MOCK_PERSONAS } from '../mocks/personas';
import { MOCK_EVAL_CARDS } from '../mocks/evaluations';
import { MOCK_CONVERSATIONS, FOLLOW_UP_SCRIPTS } from '../mocks/conversations';
import { MOCK_USER, MOCK_BALANCE, MOCK_TRANSACTIONS, MOCK_HOME_STATS } from '../mocks/credits';

import { request, BASE_URL, getToken } from './http';
import { API_VERSION_PREFIX } from './endpoints';
import { E } from './endpoints';
import { startMockStream, startRealStream, type StreamHandle, type StreamHandlers } from './stream';

/** true = 本地 mock，false = 真后端 (需先运行 start-backend.bat) */
export const USE_MOCK = false;

function delay<T>(value: T, ms = 200): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(value), ms));
}

// ============ 域对象 API ============

export const api = {

  // ---------- Auth ----------

  /** 检查登录态；本期必须由首页手机号授权弹窗完成登录 */
  async ensureAuth(): Promise<void> {
    if (wx.getStorageSync('auth_token')) return;
    throw new Error('AUTH_REQUIRED');
  },

  async getMe(): Promise<User> {
    if (USE_MOCK) return delay(MOCK_USER);
    return request<User>({ url: E.AUTH_ME });
  },

  /** 手机号授权登录：同时传 wx.login code 和 phone_code（换手机号） */
  async loginWithPhone(code: string, phone_code: string): Promise<{ token: string; user: User }> {
    const ref_code = wx.getStorageSync('referral_code') || undefined;
    return request<{ token: string; user: User }>({
      url: E.AUTH_WECHAT_LOGIN,
      method: 'POST',
      data: { code, phone_code, ...(ref_code ? { ref_code } : {}) },
    });
  },

  /** 静默登录（仅 openid，无手机号）：getPhoneNumber 权限未开通时的降级方案 */
  async loginSilent(code: string): Promise<{ token: string; user: User }> {
    const ref_code = wx.getStorageSync('referral_code') || undefined;
    return request<{ token: string; user: User }>({
      url: E.AUTH_WECHAT_LOGIN,
      method: 'POST',
      data: { code, ...(ref_code ? { ref_code } : {}) },
    });
  },

  // ---------- Product ----------

  async uploadProductImages(filePaths: string[]): Promise<string[]> {
    const results = await this._uploadProductImagesInternal(filePaths);
    return results.map(r => r.object_key);
  },

  /** Upload images and return both object_key (for createProduct) and public URL (for extractFromImages). */
  async uploadProductImagesWithUrls(filePaths: string[]): Promise<{ object_key: string; image_url: string }[]> {
    return this._uploadProductImagesInternal(filePaths);
  },

  async _uploadProductImagesInternal(filePaths: string[]): Promise<{ object_key: string; image_url: string }[]> {
    if (USE_MOCK || !filePaths.length) return [];

    async function uploadOne(filePath: string): Promise<{ object_key: string; image_url: string }> {
      const tOne0 = Date.now();
      // 1. 获取文件信息（PC/DevTools 下 tempFilePath 为 http://tmp/... 不支持 getFileInfo，降级为 0）
      let fileSize = 0;
      if (!filePath.startsWith('http')) {
        try {
          const fi = await new Promise<{ size: number }>((resolve, reject) => {
            wx.getFileSystemManager().getFileInfo({ filePath, success: (r: any) => resolve(r), fail: reject });
          });
          fileSize = fi.size;
        } catch { /* ignore */ }
      }
      const ext = filePath.split('.').pop()?.split('?')[0]?.toLowerCase() || 'jpg';
      const mimeType = ext === 'png' ? 'image/png' : 'image/jpeg';

      // 2. 申请预签名 URL
      const tUrl0 = Date.now();
      const urlRes = await request<UploadUrlRes>({
        url: E.PRODUCT_UPLOAD_URL,
        method: 'POST',
        data: {
          filename: `product_${Date.now()}.${ext}`,
          mime_type: mimeType,
          size_bytes: fileSize,
        },
      });
      console.log(`[perf] upload-url request: ${Date.now() - tUrl0}ms`);

      // 3. 若是 mock URL（本地开发），跳过真实上传
      const isMockUrl = urlRes.upload_url.includes('mock-tos.local');
      if (!isMockUrl) {
        const tPut0 = Date.now();
        const fileContent = wx.getFileSystemManager().readFileSync(filePath);
        console.log(`[perf] file read: ${Date.now() - tPut0}ms, size=${(fileContent as ArrayBuffer).byteLength || 'unknown'}`);
        const tPut1 = Date.now();
        await new Promise<void>((resolve, reject) => {
          wx.request({
            url: urlRes.upload_url,
            method: urlRes.method,
            data: fileContent,
            header: { ...urlRes.headers, 'Content-Type': mimeType },
            success: (r: any) => (r.statusCode < 300 ? resolve() : reject(new Error(`Upload failed: ${r.statusCode}`))),
            fail: (e: any) => reject(new Error(e.errMsg)),
          });
        });
        console.log(`[perf] PUT upload: ${Date.now() - tPut1}ms`);
      }

      // 4. Use the backend-provided image_url directly.
      //    Backend always returns this field; never derive a URL from upload_url.
      const imageUrl = urlRes.image_url;
      if (!imageUrl) {
        console.error('[upload-url] response missing image_url. Full response:', JSON.stringify(urlRes));
        throw new Error('Backend upload-url response missing image_url. Please update backend.');
      }

      console.log(`[perf] uploadOne total: ${Date.now() - tOne0}ms`);
      return { object_key: urlRes.object_key, image_url: imageUrl };
    }

    // 并行上传所有图片，保留顺序
    return Promise.all(filePaths.map(uploadOne));
  },

  async extractFromImages(opts: {
    image_urls: string[];
    target_fields?: string[];
    locale?: string;
  }): Promise<ImageExtractResponse> {
    if (USE_MOCK) {
      return delay({
        status: 'ok',
        source_image_count: opts.image_urls.length,
        raw_text: '焕颜修护精华面霜 50ml 烟酰胺+神经酰胺 温和修护 适合敏感肌 建议零售价¥199',
        fields: {
          name:           { value: '焕颜修护精华面霜', confidence: 0.92, source: 'image_ocr' },
          brand:          { value: '测试品牌',         confidence: 0.88, source: 'image_ocr' },
          category:       { value: '护肤品',           confidence: 0.75, source: 'llm_inference' },
          price:          { value: '199',              confidence: 0.70, source: 'image_ocr' },
          specification:  { value: '50ml',             confidence: 0.85, source: 'image_ocr' },
          ingredients:    { value: ['烟酰胺', '神经酰胺', '玻尿酸'], confidence: 0.78, source: 'vision_llm' },
          selling_points: { value: ['温和修护', '长效保湿', '提亮肤色'], confidence: 0.72, source: 'vision_llm' },
          usage_scenario: { value: '日常护肤',         confidence: 0.68, source: 'llm_inference' },
          claims:         { value: ['经皮肤科测试', '适合敏感肌'], confidence: 0.65, source: 'vision_llm' },
        },
        suggested_description: '一款主打温和修护和提亮功效的面霜，含烟酰胺与神经酰胺核心成分，适合敏感肌日常使用。',
        needs_review: true,
      }, 800);
    }
    // Limit to 2 images to keep Zhipu response time reasonable
    const limitedUrls = opts.image_urls.slice(0, 2);
    if (opts.image_urls.length > 2) {
      console.warn(`[extract] limiting images from ${opts.image_urls.length} to 2 for speed`);
    }
    return request<ImageExtractResponse>({
      url: E.PRODUCT_EXTRACT_FROM_IMAGES,
      method: 'POST',
      data: {
        image_urls: limitedUrls,
        target_fields: opts.target_fields || [],
        locale: opts.locale || 'zh-CN',
      },
      timeout: 120000, // 2 min timeout for vision AI
    });
  },

  async listProducts(cursor?: string): Promise<CursorPaged<Product>> {
    if (USE_MOCK) return delay({ items: [], next_cursor: null, has_more: false });
    return request<CursorPaged<Product>>({
      url: E.PRODUCT_LIST,
      query: { limit: 20, ...(cursor ? { cursor } : {}) },
    });
  },

  async getProduct(id: string): Promise<Product> {
    if (USE_MOCK) return delay({ id, name: '', description: '', image_urls: [], category: '', sub_category: null, brand: null, price: null, price_range: null, target_channel: null, ai_summary: null, status: 'ready' as const, created_at: '' });
    return request<Product>({ url: E.PRODUCT_DETAIL(id) });
  },

  async reanalyzeProduct(id: string, _imageObjectKeys?: string[]): Promise<Product> {
    return request<Product>({ url: E.PRODUCT_REANALYZE(id), method: 'POST' });
  },

  async createProduct(opts: {
    name?: string;
    description: string;
    image_object_keys?: string[];
    brand?: string;
    price?: number;
    target_channel?: 'ec' | 'offline' | 'livestream';
  }): Promise<Product> {
    if (USE_MOCK) {
      return delay({
        id: 'p_mock_' + Date.now(),
        name: opts.name || opts.description.slice(0, 12) || '未命名产品',
        description: opts.description,
        image_urls: [],
        category: 'skincare',
        sub_category: null,
        brand: null,
        price: null,
        price_range: null,
        target_channel: null,
        ai_summary: null,
        status: 'ready' as const,
        created_at: new Date().toISOString(),
      });
    }
    return request<Product>({
      url: E.PRODUCT_CREATE,
      method: 'POST',
      data: {
        name: opts.name,
        description: opts.description || opts.name,
        // 后端要求至少1个 key；无真实图片时传占位符（mock模式下不实际访问）
        image_object_keys: opts.image_object_keys?.length
          ? opts.image_object_keys
          : ['placeholder/no_image.jpg'],
        ...(opts.brand ? { brand: opts.brand } : {}),
        ...(opts.price ? { price: opts.price } : {}),
        ...(opts.target_channel ? { target_channel: opts.target_channel } : {}),
      } as CreateProductReq,
    });
  },

  // ---------- Report ----------

  async getReportByEval(evalId: string): Promise<BackendReport> {
    return request<BackendReport>({ url: E.REPORT_BY_EVAL(evalId) });
  },

  async getBusinessReportByEval(evalId: string): Promise<BusinessReport> {
    return request<BusinessReport>({ url: E.REPORT_BUSINESS_BY_EVAL(evalId) });
  },

  async listReportPdfs(): Promise<ReportPdfListResponse> {
    return request<ReportPdfListResponse>({ url: E.REPORT_PDFS });
  },

  async deleteReportPdfs(reportIds: string[]): Promise<void> {
    return request<void>({
      url: E.REPORT_PDFS + '/delete',
      method: 'POST',
      data: { report_ids: reportIds },
    });
  },

  // ---------- Whitepaper ----------

  async generateWhitepaper(opts: {
    evaluation_id: string;
    product_name: string;
    product_description?: string;
  }): Promise<any> {
    return request<any>({
      url: E.WHITEPAPER_GENERATE,
      method: 'POST',
      data: {
        evaluation_id: Number(opts.evaluation_id),
        product_name: opts.product_name,
        ...(opts.product_description ? { product_description: opts.product_description } : {}),
      },
    });
  },

  async getWhitepaperByEval(evalId: string): Promise<any> {
    return request<any>({ url: E.WHITEPAPER_BY_EVAL(evalId) });
  },

  async getDeepAnalysis(evalId: string): Promise<DeepAnalysis> {
    return request<DeepAnalysis>({ url: E.DEEP_ANALYSIS_BY_EVAL(evalId) });
  },

  async listConversations(evalId?: string): Promise<CursorPaged<Conversation>> {
    return request<CursorPaged<Conversation>>({
      url: E.CONV_LIST,
      query: { limit: 20, ...(evalId ? { evaluation_id: evalId } : {}) },
    });
  },

  async deleteConversation(id: string): Promise<void> {
    await request({ url: E.CONV_DELETE(id), method: 'DELETE' });
  },

  // ---------- Evaluation ----------

  async listEvaluationCards(opts: { limit?: number } = {}): Promise<EvaluationCardVM[]> {
    const limit = opts.limit ?? 20;
    if (USE_MOCK) return delay(MOCK_EVAL_CARDS.slice(0, limit));
    const res = await request<CursorPaged<Evaluation>>({
      url: E.EVAL_LIST, query: { limit },
    });
    function toLabel(s: string): '进行中' | '已完成' | '已取消' | '失败' | '准备中' {
      if (s === 'done') return '已完成';
      if (s === 'failed') return '失败';
      if (s === 'canceled') return '已取消';
      if (s === 'pending') return '准备中';
      return '进行中';
    }
    // 并行拉取每个评测对应的产品信息
    const evalItems = res.items;
    const products = await Promise.all(
      evalItems.map(e => request<any>({ url: E.PRODUCT_DETAIL(e.product_id) }).catch(() => null))
    );
    return evalItems.map((e, i) => {
      const p = products[i];
      return {
        id: e.id,
        title: p?.name || ('调研 ' + e.id.slice(-6)),
        thumb_url: (p?.image_urls?.[0]) || '',
        thumb_emoji: '研',
        meta_text: new Date(e.created_at).toLocaleDateString(),
        progress: e.progress,
        status: e.status,
        status_label: toLabel(e.status),
        persona_ids: e.selected_persona_ids,
        message_count: 0,
        insight_count: 0,
      };
    });
  },

  async createEvaluation(product_id: string): Promise<Evaluation> {
    if (USE_MOCK) {
      return delay({
        id: 'eval_mock_' + Date.now(),
        user_id: MOCK_USER.id,
        product_id,
        survey_id: null,
        selected_persona_ids: [],
        status: 'pending',
        progress: 0,
        credit_cost: 0,
        created_at: new Date().toISOString(),
      });
    }
    return request<Evaluation>({ url: E.EVAL_CREATE, method: 'POST', data: { product_id } });
  },

  async generateSurvey(evaluation_id: string, product_id: string, focus_area?: string): Promise<any> {
    if (USE_MOCK) return delay({ id: 's_mock', questions: [] });
    return request<any>({
      url: E.SURVEY_GENERATE,
      method: 'POST',
      data: { evaluation_id, product_id, extra_focus: focus_area || null },
    });
  },

  /**
   * 流式生成问卷。后端 SSE 先推进度事件，AI 完成后推 done。
   * onProgress(pct, msg) — 收到真实进度；onDone(surveyId) — 生成完成。
   */
  generateSurveyStream(
    evaluation_id: string,
    product_id: string,
    focus_area: string,
    handlers: {
      onProgress(pct: number, msg: string): void;
      onDone(surveyId: string): void;
      onError(err: Error): void;
    },
  ): StreamHandle {
    const token = getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return startRealStream(
      BASE_URL + API_VERSION_PREFIX + E.SURVEY_GENERATE_STREAM,
      { evaluation_id, product_id, extra_focus: focus_area || null },
      headers,
      {
        onEvent(evt: any) {
          if (evt.event === 'progress') handlers.onProgress(evt.pct ?? 0, evt.msg ?? '');
          else if (evt.event === 'done') handlers.onDone(String(evt.survey_id ?? ''));
          else if (evt.event === 'error') handlers.onError(new Error(evt.msg || '问卷生成失败'));
        },
        onError: handlers.onError,
      },
    );
  },

  async updateSurveyQuestions(surveyId: string, questions: SurveyQuestion[]): Promise<Survey> {
    return request<Survey>({
      url: E.SURVEY_UPDATE_QUESTIONS(surveyId),
      method: 'PUT',
      data: questions,
    });
  },

  async attachPersonas(evaluation_id: string, persona_ids: string[]): Promise<Evaluation> {
    if (USE_MOCK) {
      return delay({
        id: evaluation_id,
        user_id: MOCK_USER.id,
        product_id: 'p_mock',
        survey_id: 's_mock',
        selected_persona_ids: persona_ids,
        status: 'pending',
        progress: 0,
        credit_cost: 0,
        created_at: new Date().toISOString(),
      });
    }
    return request<Evaluation>({
      url: E.EVAL_ATTACH_PERSONAS(evaluation_id),
      method: 'PUT',
      data: { persona_ids },
    });
  },

  async getEvaluation(id: string): Promise<Evaluation> {
    if (USE_MOCK) {
      return delay({
        id, user_id: MOCK_USER.id, product_id: 'p_mock',
        survey_id: 'survey_mock', selected_persona_ids: ['p1', 'p2', 'p3'],
        status: 'done' as const, progress: 100, credit_cost: 10,
        created_at: new Date().toISOString(),
      });
    }
    return request<Evaluation>({ url: E.EVAL_DETAIL(id) });
  },

  async getSurvey(surveyId: string): Promise<Survey> {
    if (USE_MOCK) {
      return delay({
        id: surveyId,
        questions: [
          { id: 'q1', text: '您对该产品的整体体验满意度如何？', type: 'scale_1_5' as const, options: null },
          { id: 'q2', text: '您认为该产品最吸引您的特点是什么？请详细说明。', type: 'open' as const, options: null },
          { id: 'q3', text: '您是否会向朋友或家人推荐该产品？为什么？', type: 'open' as const, options: null },
          { id: 'q4', text: '该产品的价格相对于其质量，您认为是否合理？', type: 'scale_1_5' as const, options: null },
          { id: 'q5', text: '您在使用该产品时有遇到不满意的地方吗？请描述。', type: 'open' as const, options: null },
        ],
      });
    }
    return request<Survey>({ url: E.SURVEY_DETAIL(surveyId) });
  },

  async getEvaluationAnswers(id: string, personaIds: string[] = []): Promise<EvaluationAnswer[]> {
    if (USE_MOCK) {
      return delay([
        {
          evaluation_id: id, persona_id: 'p1', persona_name: '云云',
          overall_intent: 8, sentiment: 'positive' as const,
          answers: [
            { qid: 'q1', type: 'scale_1_5', answer: 4, reason: '保湿效果不错' },
            { qid: 'q2', type: 'open', answer: '保湿效果很好，用后皮肤感觉滋润，气垫设计精致便携。' },
            { qid: 'q3', type: 'open', answer: '会推荐！特别适合偏干性肤质的朋友，保湿力强，上妆不起皮。' },
            { qid: 'q4', type: 'scale_1_5', answer: 4 },
            { qid: 'q5', type: 'open', answer: '香味稍微有点重，对香料敏感的人可能不太适合。' },
          ],
        },
        {
          evaluation_id: id, persona_id: 'p2', persona_name: '洁洁',
          overall_intent: 6, sentiment: 'neutral' as const,
          answers: [
            { qid: 'q1', type: 'scale_1_5', answer: 3 },
            { qid: 'q2', type: 'open', answer: '遮瑕力还可以，日常通勤够用了，不用额外再打粉底。' },
            { qid: 'q3', type: 'open', answer: '可能会推荐给追求自然妆效的人，但需要高遮瑕的朋友就不太适合。' },
            { qid: 'q4', type: 'scale_1_5', answer: 3 },
            { qid: 'q5', type: 'open', answer: '持妆时间一般，到下午会有点浮粉。成分表里有些防腐剂不太放心。' },
          ],
        },
        {
          evaluation_id: id, persona_id: 'p3', persona_name: '聪聪',
          overall_intent: 9, sentiment: 'positive' as const,
          answers: [
            { qid: 'q1', type: 'scale_1_5', answer: 5 },
            { qid: 'q2', type: 'open', answer: '质地轻薄，贴合度很好，妆感自然通透，完全看不出来在化妆！成分也相对温和。' },
            { qid: 'q3', type: 'open', answer: '强烈推荐！已经给闺蜜安利了，她们用了也很喜欢。' },
            { qid: 'q4', type: 'scale_1_5', answer: 5 },
            { qid: 'q5', type: 'open', answer: '目前没发现明显缺点，如果要说的话就是色号不够多，希望能出更多深色系。' },
          ],
        },
      ]);
    }
    // Real backend: per-persona endpoint returns EvaluationAnswerResponse
    // which has persona_snapshot instead of persona_name/persona_tag — map here
    if (personaIds.length > 0) {
      const results = await Promise.all(
        personaIds.slice(0, 10).map(pid =>
          request<any>({ url: E.EVAL_ANSWER(id, pid) }).catch(() => null)
        )
      );
      return results
        .filter((r): r is any => r !== null)
        .map((r: any): EvaluationAnswer => ({
          ...r,
          persona_name: r.persona_snapshot?.name ?? r.persona_name,
          persona_tag:  r.persona_snapshot?.persona_tag ?? r.persona_tag,
          avatar:       r.persona_snapshot?.avatar ?? r.avatar,
        }));
    }
    // Fallback: summary-only list (no full answer data)
    const res = await request<any>({ url: E.EVAL_ANSWERS_ALL(id) });
    return Array.isArray(res) ? res : (res?.items ?? res?.answers ?? []);
  },

  async cancelEvaluation(id: string): Promise<void> {
    if (USE_MOCK) return delay(undefined as any);
    await request({ url: E.EVAL_CANCEL(id), method: 'POST' });
  },

  async deleteEvaluation(id: string): Promise<void> {
    if (USE_MOCK) return delay(undefined as any);
    await request({ url: E.EVAL_DELETE(id), method: 'DELETE' });
  },

  async updateProfile(opts: { role_type?: string; nickname?: string; avatar_url?: string }): Promise<User> {
    const data: ProfileUpdateReq = { role_type: opts.role_type || undefined };
    if (opts.nickname !== undefined) data.nickname = opts.nickname;
    if (opts.avatar_url !== undefined) data.avatar_url = opts.avatar_url;
    return request<User>({ url: E.AUTH_PROFILE, method: 'PATCH', data });
  },

  async uploadAvatar(filePath: string): Promise<AvatarUploadRes> {
    const token = getToken();
    return new Promise<AvatarUploadRes>((resolve, reject) => {
      wx.uploadFile({
        url: BASE_URL + API_VERSION_PREFIX + E.AUTH_AVATAR,
        filePath,
        name: 'file',
        header: token ? { Authorization: 'Bearer ' + token } : {},
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(JSON.parse(res.data) as AvatarUploadRes);
          } else {
            reject({ code: 'HTTP_' + res.statusCode, message: 'Upload failed' });
          }
        },
        fail(e) {
          reject({ code: 'NETWORK_ERROR', message: e.errMsg });
        },
      });
    });
  },

  async rechargeCredits(_amount: number): Promise<CreditBalance> {
    if (USE_MOCK) return delay(MOCK_BALANCE);
    return request<CreditBalance>({
      url: E.CREDIT_RECHARGE,
      method: 'POST',
      data: { amount: _amount },
    });
  },

  async runEvaluation(evaluation_id: string): Promise<void> {
    if (USE_MOCK) {
      return delay(undefined as any);
    }
    // Backend returns 202 EvaluationRunResponse; we don't use the body
    await request<any>({ url: E.EVAL_RUN(evaluation_id), method: 'POST' });
  },

  // ---------- Persona ----------

  async recommendPersonas(product_id: string, count = 20): Promise<PersonaSummary[]> {
    if (USE_MOCK) return delay(MOCK_PERSONAS as any[]);
    const res = await request<{ items: PersonaSummary[] }>({
      url: E.PERSONA_RECOMMEND,
      query: { product_id, count },
    });
    return res.items;
  },

  async listFixedPersonas(): Promise<PersonaWithKey[]> {
    if (USE_MOCK) return delay(MOCK_PERSONAS);
    const res = await request<{ items: PersonaSummary[] }>({
      url: E.PERSONA_LIST,
      query: { page: 1, page_size: 20 },
    });
    return res.items.map(p => ({ ...p, key: 'yun', trait: '' })) as PersonaWithKey[];
  },

  async listPersonas(opts: { is_system?: boolean } = {}): Promise<PersonaSummary[]> {
    if (USE_MOCK) return delay(MOCK_PERSONAS as any[]);
    const res = await request<{ items: PersonaSummary[] }>({
      url: E.PERSONA_LIST,
      query: { page: 1, page_size: 50, ...(opts.is_system !== undefined ? { is_system: opts.is_system } : {}) },
    });
    return res.items;
  },

  async getPersona(id: string): Promise<PersonaDetail> {
    return request<PersonaDetail>({ url: E.PERSONA_DETAIL(id) });
  },

  async createPersona(data: Partial<PersonaSummary> & { name: string }): Promise<PersonaSummary> {
    return request<PersonaSummary>({ url: E.PERSONA_CREATE, method: 'POST', data });
  },

  async updatePersona(id: string, data: Partial<PersonaSummary>): Promise<PersonaSummary> {
    return request<PersonaSummary>({ url: E.PERSONA_UPDATE(id), method: 'PATCH', data });
  },

  async deletePersona(id: string): Promise<void> {
    await request({ url: E.PERSONA_DELETE(id), method: 'DELETE' });
  },

  // ---------- Conversation ----------

  async getConversation(evaluation_id: string, overridePersonaId?: string): Promise<any> {
    if (USE_MOCK) {
      const mock = MOCK_CONVERSATIONS[evaluation_id] || MOCK_CONVERSATIONS['eval_001'];
      const conversation: Conversation = {
        id: mock.id,
        evaluation_id: mock.evaluation_id,
        persona_id: 'persona_' + mock.persona_key,
        persona_name: mock.persona_name,
        persona_avatar: mock.persona_key,
        title: mock.product_title,
        message_count: mock.turns.length,
        last_message_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      };
      return delay({
        conversation,
        turns: mock.turns,
        current_topic: mock.current_topic,
        persona_role: mock.persona_role,
      });
    }

    // Phase B
    // 1. 获取 evaluation，找 persona（优先使用传入的 overridePersonaId）
    // evaluation may have been deleted while conversation still exists — handle 404 gracefully
    let evaluation: Evaluation | null = null;
    try {
      evaluation = await request<Evaluation>({ url: E.EVAL_DETAIL(evaluation_id) });
    } catch { /* continue without evaluation data */ }
    const personaId = overridePersonaId || evaluation?.selected_persona_ids?.[0] || '';

    // 2. 获取 persona 详情
    let personaName = 'AI测品官';
    let personaAvatar = 'yun';
    let personaRole = 'AI 消费者测品官';
    if (personaId) {
      try {
        const p = await request<PersonaSummary>({ url: E.PERSONA_DETAIL(personaId) });
        personaName = p.name;
        personaAvatar = (['yun','jie','cong'].includes((p as any).avatar)
          ? (p as any).avatar : 'yun');
        personaRole = p.persona_tag;
      } catch { /* fallback to defaults */ }
    }

    // 3. 创建/获取 conversation
    const rawConv = await request<any>({
      url: E.CONV_CREATE,
      method: 'POST',
      data: { evaluation_id, persona_id: personaId },
    });

    const conversation: Conversation = {
      id: rawConv.id,
      evaluation_id: rawConv.evaluation_id,
      persona_id: rawConv.persona_id,
      persona_name: personaName,
      persona_avatar: personaAvatar,
      title: rawConv.title || '产品调研对话',
      message_count: rawConv.message_count || 0,
      last_message_at: rawConv.last_message_at || null,
      created_at: rawConv.created_at,
    };

    // 4. 获取历史消息，映射为 ChatTurn
    let turns: any[] = [];
    try {
      const msgs = await request<CursorPaged<Message>>({
        url: E.CONV_MESSAGES_LIST(rawConv.id),
        query: { limit: 50 },
      });
      turns = msgs.items.map((m, i) => ({
        id: m.id || 'msg_' + i,
        kind: m.role === 'user' ? 'user' : 'speak',
        content: m.content,
        persona_key: personaAvatar,
        persona_name: personaName,
      }));
    } catch { /* empty history is fine */ }

    return {
      conversation,
      turns,
      current_topic: { index: 1, total: 1, emoji: '💬', label: '产品调研' },
      persona_role: personaRole,
    };
  },

  /**
   * 流式发消息。
   * Phase A: setInterval 模拟双流。
   * Phase B: wx.request enableChunked 接真实 SSE。
   */
  sendMessageStream(
    conversation_id: string,
    content: string,
    handlers: StreamHandlers,
  ): StreamHandle {
    if (USE_MOCK) {
      const script = FOLLOW_UP_SCRIPTS[Math.floor(Math.random() * FOLLOW_UP_SCRIPTS.length)];
      return startMockStream(
        { think: script.think, speak: script.speak, intervalMs: 35, chunkSize: 2 },
        handlers,
      );
    }
    // Phase B: 真实 SSE
    const token = getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'X-Request-Id': Math.random().toString(36).slice(2),
    };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return startRealStream(
      BASE_URL + API_VERSION_PREFIX + E.CONV_MESSAGE_SEND(conversation_id),
      { content },
      headers,
      handlers,
    );
  },

  // ---------- Credit ----------
  // 注：后端暂无独立 credits 路由。余额从 /auth/me 的 credit_balance 字段读取。
  // 明细与充值接口后端未实现，前端优雅降级。

  async getCreditsBalance(): Promise<CreditBalance> {
    if (USE_MOCK) return delay(MOCK_BALANCE);
    const res = await request<{ balance: number; updated_at: string }>({ url: E.CREDIT_BALANCE });
    return { balance: res.balance, updated_at: res.updated_at };
  },

  async listCreditTransactions(): Promise<CursorPaged<CreditTransaction>> {
    if (USE_MOCK) {
      return delay({ items: MOCK_TRANSACTIONS, next_cursor: null, has_more: false });
    }
    const res = await request<any>({ url: E.CREDIT_TRANSACTIONS });
    // 后端返回字段: id, amount, balance_after, reason, ref_type, ref_id, note, created_at
    const items: CreditTransaction[] = (res.items ?? []).map((t: any) => ({
      id: t.id,
      type: t.reason ?? 'adjust',
      amount: t.amount,
      balance_after: t.balance_after ?? 0,
      description: t.note || t.reason || '',
      created_at: t.created_at,
    }));
    return { items, next_cursor: res.next_cursor ?? null, has_more: res.has_more ?? false };
  },

  async listHistory(cursor?: string): Promise<any> {
    return request<any>({
      url: E.HISTORY_LIST,
      query: { limit: 20, ...(cursor ? { cursor } : {}) },
    });
  },

  // ---------- Home 统计 ----------
  async getHomeStats(): Promise<{ total_evaluations: number; total_insights: number }> {
    if (USE_MOCK) return delay(MOCK_HOME_STATS);
    return MOCK_HOME_STATS;
  },
};

export type { Message };
