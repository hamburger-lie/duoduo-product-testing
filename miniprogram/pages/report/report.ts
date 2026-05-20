import { api } from '../../services/api';
import { BASE_URL, getToken } from '../../services/http';
import type { BackendReport, BusinessReport } from '../../types/api';

const WHITEPAPER_PORT = 5678;
const WHITEPAPER_VIEWER_PATH = '/static/index.html';
const REPORT_CACHE_PREFIX = 'business_report_cache_';

interface CachedReportSnapshot {
  report: BusinessReport;
  productName?: string;
}

function whitepaperBase(): string {
  const m = BASE_URL.match(/^(https?:\/\/)([^/:]+)(?::\d+)?/);
  const protocol = m?.[1] || 'http://';
  const host = m?.[2] || '127.0.0.1';
  return `${protocol}${host}:${WHITEPAPER_PORT}`;
}

function verdictMeta(verdict: string): { text: string; cls: string } {
  if (verdict === 'go') return { text: '可推进', cls: 'go' };
  if (verdict === 'pause') return { text: '暂缓推进', cls: 'pause' };
  return { text: '建议迭代', cls: 'iterate' };
}

function scoreFromReport(report: BusinessReport): number {
  const intent = Math.max(0, Math.min(100, (report.metrics?.overall_intent_avg || 0) / 5 * 100));
  const nps = Math.max(0, Math.min(100, ((report.metrics?.nps || 0) + 100) / 2));
  const confidence = Math.max(0, Math.min(100, (report.decision_suggestion?.confidence || 0) * 100));
  return Math.round(intent * 0.55 + nps * 0.25 + confidence * 0.2);
}

function firstQuote(items: BusinessReport['top_pros'] | BusinessReport['top_cons']): string {
  for (const item of items || []) {
    const quote = item.evidence_quotes?.[0];
    if (quote?.quote) return `“${quote.quote}”`;
  }
  return '';
}

function firstBaseQuote(items: BackendReport['top_pros'] | BackendReport['top_cons']): string {
  for (const item of items || []) {
    const quote = item.quotes?.[0];
    if (quote?.quote) return `“${quote.quote}”`;
  }
  return '';
}

function nonEmpty(items: Array<string | undefined>, fallback: string): string[] {
  const filtered = items.map(x => String(x || '').trim()).filter(Boolean);
  return filtered.length ? filtered : [fallback];
}

function shortProductName(name: string): string {
  const chars = Array.from(String(name || '').trim());
  return chars.slice(0, 10).join('');
}

function reportCacheKey(evalId: string): string {
  return `${REPORT_CACHE_PREFIX}${evalId}`;
}

function readCachedReport(evalId: string): CachedReportSnapshot | null {
  try {
    const raw = wx.getStorageSync(reportCacheKey(evalId));
    if (!raw) return null;
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return parsed?.report ? parsed as CachedReportSnapshot : null;
  } catch {
    return null;
  }
}

function writeCachedReport(evalId: string, snapshot: CachedReportSnapshot): void {
  try {
    wx.setStorageSync(reportCacheKey(evalId), JSON.stringify(snapshot));
  } catch {
    // cache is only for faster history display
  }
}

Page({
  data: {
    phase: 'loading' as 'loading' | 'ready' | 'error',
    evaluationId: '',
    error: '',
    vm: {
      productName: '',
      generatedAt: '',
      verdictText: '',
      verdictClass: '',
      score: 0,
      intent: '0.0/5',
      nps: '0',
      confidence: '0%',
      summary: [] as string[],
      opportunities: [] as Array<{ title: string; note: string; count: number }>,
      risks: [] as Array<{ title: string; note: string; count: number }>,
      audiences: [] as string[],
      channels: [] as string[],
      quotes: [] as string[],
      nextSteps: [] as string[],
      disclaimer: '',
    },
  },

  async onLoad(query: Record<string, string | undefined>) {
    const evalId = query.evaluation_id || '';
    this.setData({ evaluationId: evalId });
    if (!evalId) {
      this.setData({ phase: 'error', error: '无效的调研 ID' });
      return;
    }
    wx.showShareMenu({ withShareTicket: false, menus: ['shareAppMessage'] });
    const cached = readCachedReport(evalId);
    if (cached) {
      this.setData({ phase: 'ready', vm: this.buildVM(cached.report, cached.productName || '') });
      await this.loadReport(false);
      return;
    }
    await this.loadReport(true);
  },

  onShareAppMessage() {
    return {
      title: '查看测品调研报告',
      path: `/pages/report/report?evaluation_id=${this.data.evaluationId}`,
    };
  },

  async loadReport(showLoading = true) {
    const evalId = this.data.evaluationId;
    if (showLoading) {
      this.setData({ phase: 'loading', error: '' });
    } else {
      this.setData({ error: '' });
    }
    try {
      const [businessReport, evaluation] = await Promise.all([
        api.getBusinessReportByEval(evalId),
        api.getEvaluation(evalId).catch(() => null),
      ]);
      let productName = '';
      if (evaluation?.product_id) {
        const product = await api.getProduct(evaluation.product_id).catch(() => null);
        productName = product?.name || '';
        api.generateWhitepaper({
          evaluation_id: evalId,
          product_name: shortProductName(product?.name || '') || '未命名产品',
          product_description: product?.description || undefined,
        }).catch(() => {});
      }
      writeCachedReport(evalId, { report: businessReport, productName });
      this.setData({ phase: 'ready', vm: this.buildVM(businessReport, productName) });
    } catch (err: any) {
      if (!showLoading) {
        return;
      }
      try {
        const [report, evaluation] = await Promise.all([
          api.getReportByEval(evalId),
          api.getEvaluation(evalId).catch(() => null),
        ]);
        let productName = '';
        if (evaluation?.product_id) {
          const product = await api.getProduct(evaluation.product_id).catch(() => null);
          productName = product?.name || '';
        }
        this.setData({ phase: 'ready', vm: this.buildBaseVM(report, productName) });
      } catch {
        this.setData({
          phase: 'error',
          error: err?.message || '调研报告加载失败，请稍后重试',
        });
      }
    }
  },

  buildBaseVM(report: BackendReport, productName: string) {
    const avg = report.metrics?.overall_intent?.average || 0;
    const nps = report.metrics?.overall_intent?.nps ?? 0;
    const score = Math.round(Math.max(0, Math.min(100, (avg / 5) * 70 + ((nps + 100) / 200) * 30)));
    const verdict = verdictMeta(score >= 70 ? 'go' : score < 45 ? 'pause' : 'iterate');
    const opportunities = (report.top_pros || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.quotes?.[0]?.quote ? `用户原声：${item.quotes[0].quote}` : '该优势在本轮角色回答中被多次提及。',
      count: item.support_count || 0,
    }));
    const risks = (report.top_cons || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.quotes?.[0]?.quote ? `用户原声：${item.quotes[0].quote}` : '该风险需要在卖点表达或后续验证中优先处理。',
      count: item.support_count || 0,
    }));
    const quoteList = [
      firstBaseQuote(report.top_pros || []),
      firstBaseQuote(report.top_cons || []),
    ].filter(Boolean);
    return {
      productName: shortProductName(productName) || '本次测品',
      generatedAt: String(report.generated_at || '').slice(0, 10),
      verdictText: verdict.text,
      verdictClass: verdict.cls,
      score,
      intent: `${avg.toFixed(1)}/5`,
      nps: String(nps),
      confidence: '已完成',
      summary: nonEmpty(
        [report.summary],
        '本轮调研已完成，建议结合机会点、风险点和用户原声判断下一步动作。',
      ).slice(0, 3),
      opportunities: opportunities.length ? opportunities : [{ title: '机会点待识别', note: '可结合角色原声继续查看具体反馈。', count: 0 }],
      risks: risks.length ? risks : [{ title: '风险点待识别', note: '可结合低分回答继续判断阻碍因素。', count: 0 }],
      audiences: nonEmpty(report.persona_segments?.most_positive || [], '高潜购买人群待进一步验证').slice(0, 3),
      channels: nonEmpty(report.persona_segments?.highest_value || [], '建议结合核心渠道继续验证').slice(0, 3),
      quotes: nonEmpty(quoteList, '暂无可展示的用户原声，建议回到调研对话查看角色回答。').slice(0, 3),
      nextSteps: [
        '优先复核购买意向较低的问题，定位价格、功效或信任阻碍。',
        '围绕高频机会点制作 2-3 个卖点表达版本进行复测。',
        '保留用户原声中反复出现的顾虑，作为详情页和投放素材的证明点。',
      ],
      disclaimer: report.ai_disclaimer || '报告由 AI 聚合调研回答生成，仅供决策参考。',
    };
  },

  buildVM(report: BusinessReport, productName: string) {
    const verdict = verdictMeta(report.decision_suggestion?.verdict || 'iterate');
    const opportunities = (report.top_pros || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.business_implication,
      count: item.support_count || 0,
    }));
    const risks = (report.top_cons || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.improvement_suggestion,
      count: item.support_count || 0,
    }));
    const quoteList = [
      firstQuote(report.top_pros || []),
      firstQuote(report.top_cons || []),
    ].filter(Boolean);
    return {
      productName: shortProductName(productName) || '本次测品',
      generatedAt: String(report.generated_at || '').slice(0, 10),
      verdictText: verdict.text,
      verdictClass: verdict.cls,
      score: scoreFromReport(report),
      intent: `${(report.metrics?.overall_intent_avg || 0).toFixed(1)}/5`,
      nps: String(report.metrics?.nps ?? 0),
      confidence: `${Math.round((report.decision_suggestion?.confidence || 0) * 100)}%`,
      summary: nonEmpty(
        [
          report.decision_suggestion?.reason,
          ...(report.executive_summary || []).slice(0, 2),
        ],
        '本轮调研已完成，建议结合机会点、风险点和用户原声判断下一步动作。',
      ).slice(0, 3),
      opportunities,
      risks,
      audiences: nonEmpty(report.target_audience?.most_likely_to_buy || [], '高潜购买人群待进一步验证').slice(0, 3),
      channels: nonEmpty(report.target_audience?.channel_recommendation || [], '建议结合核心渠道继续验证').slice(0, 3),
      quotes: nonEmpty(quoteList, '暂无可展示的用户原声，建议回到调研对话查看角色回答。').slice(0, 3),
      nextSteps: nonEmpty(report.next_test_recommendations || [], '继续验证价格、卖点和渠道表达。').slice(0, 4),
      disclaimer: report.ai_disclaimer || '报告由 AI 聚合调研回答生成，仅供决策参考。',
    };
  },

  onTapRetry() {
    this.loadReport();
  },

  onTapFollowUp() {
    wx.navigateTo({
      url: `/pages/chat/chat?evaluation_id=${this.data.evaluationId}&auto=0`,
    });
  },

  onTapExport() {
    const evalId = this.data.evaluationId;
    if (!evalId) {
      wx.showToast({ title: '缺少调研 ID', icon: 'none' });
      return;
    }
    const token = getToken() || '';
    const reportUrl = `${whitepaperBase()}${WHITEPAPER_VIEWER_PATH}`
      + `?eid=${encodeURIComponent(evalId)}`
      + `&token=${encodeURIComponent(token)}`
      + `&api=${encodeURIComponent(BASE_URL)}`;
    wx.navigateTo({
      url: `/pages/webview/webview?url=${encodeURIComponent(reportUrl)}`,
    });
  },
});
