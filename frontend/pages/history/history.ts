import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/http';

type Filter = 'all' | 'done' | 'active';

interface HistoryVM {
  evaluation_id: string;
  dateStr: string;
  status: string;
  status_label: string;
  progress: number;
  persona_count: number;
  product_name: string;
  product_brand: string;
  product_image: string;
  product_initial: string;
  question_count: number;
  report_summary: string;
  has_report: boolean;
  is_active: boolean;
  convs: ConvVM[];
}

interface ConvVM {
  id: string;
  evaluation_id: string;
  persona_id: string;
  persona_name: string;
  persona_initial: string;
  title: string;
  message_count: number;
  dateStr: string;
}

interface HistoryData {
  all: HistoryVM[];
  filtered: HistoryVM[];
  filter: Filter;
  keyword: string;
  countAll: number;
  countDone: number;
  countActive: number;
  loading: boolean;
}

function normalizeProductImage(url: string): string {
  return resolveMediaUrl(url);
}

function statusLabel(s: string): string {
  if (s === 'done') return '已完成';
  if (s === 'failed') return '失败';
  if (s === 'canceled' || s === 'cancelled') return '已取消';
  if (s === 'pending') return '准备中';
  return '进行中';
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

function businessReportCacheKey(evalId: string): string {
  return `business_report_cache_${evalId}`;
}

function hasBusinessReportCache(evalId: string): boolean {
  try {
    const raw = wx.getStorageSync(businessReportCacheKey(evalId));
    if (!raw) return false;
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return !!parsed?.report;
  } catch {
    return false;
  }
}

Page({
  data: {
    all: [] as HistoryVM[],
    filtered: [] as HistoryVM[],
    filter: 'all' as Filter,
    keyword: '',
    countAll: 0,
    countDone: 0,
    countActive: 0,
    loading: true,
  },

  reportCacheTasks: {} as Record<string, Promise<boolean>>,

  async onShow() {
    // 立即显示缓存数据，避免白屏等待
    try {
      const cached = wx.getStorageSync('history_cache');
      if (cached) {
        const { all } = JSON.parse(cached) as HistoryData;
        const countAll = all.length;
        const countDone = all.filter(c => c.status === 'done').length;
        const countActive = all.filter(c => c.is_active).length;
        this.setData({ all, countAll, countDone, countActive, loading: false });
        this._applyFilter();
        this._warmReportCaches(all);
      }
    } catch { /* 缓存读取失败忽略 */ }

    this.setData({ loading: !this.data.all.length });
    try {
      const [res, convRes] = await Promise.allSettled([
        api.listHistory(),
        api.listConversations(),
      ]);

      // Build conversation map keyed by evaluation_id
      const convMap: Record<string, ConvVM[]> = {};
      if (convRes.status === 'fulfilled') {
        const rawConvs: any[] = Array.isArray(convRes.value)
          ? convRes.value
          : (convRes.value?.items ?? []);
        rawConvs.forEach((c: any) => {
          const vm: ConvVM = {
            id: c.id,
            evaluation_id: c.evaluation_id,
            persona_id: c.persona_id,
            persona_name: c.persona_name || 'AI 测品官',
            persona_initial: (c.persona_name || 'A').charAt(0),
            title: c.title || '追问对话',
            message_count: c.message_count || 0,
            dateStr: formatDate(c.last_message_at || c.created_at),
          };
          (convMap[c.evaluation_id] ??= []).push(vm);
        });
      }

      if (res.status === 'fulfilled') {
        const rawItems: any[] = Array.isArray(res.value) ? res.value : (res.value?.items ?? []);
        const all: HistoryVM[] = rawItems.map((item: any) => ({
          evaluation_id: item.evaluation_id,
          dateStr: formatDate(item.created_at),
          status: item.status,
          status_label: statusLabel(item.status),
          progress: item.progress,
          persona_count: item.persona_count,
          product_name: (item.product?.name || '未知产品').slice(0, 10),
          product_brand: item.product?.brand || '',
          product_image: normalizeProductImage(item.product?.image_url || ''),
          product_initial: (item.product?.name || '?').charAt(0),
          question_count: item.survey?.question_count ?? 0,
          report_summary: (item.report?.summary || '').slice(0, 50),
          has_report: !!item.report,
          is_active: !['done', 'failed', 'canceled', 'cancelled'].includes(item.status),
          convs: convMap[item.evaluation_id] ?? [],
        }));
        const countAll = all.length;
        const countDone = all.filter(c => c.status === 'done').length;
        const countActive = all.filter(c => c.is_active).length;
        this.setData({ all, countAll, countDone, countActive });
        // 存缓存，供下次快速显示
        try { wx.setStorageSync('history_cache', JSON.stringify({ all })); } catch { /* ignore */ }
        this._warmReportCaches(all);
      }

      this.setData({ loading: false });
      this._applyFilter();
    } catch (err: any) {
      console.error('[history.onShow]', err);
      this.setData({ loading: false });
    }
  },

  _applyFilter() {
    const { all, filter, keyword } = this.data;
    const kw = keyword.trim();
    const filtered = all.filter(c => {
      const matchFilter =
        filter === 'all' ||
        (filter === 'done' && c.status === 'done') ||
        (filter === 'active' && c.is_active);
      const matchKw = !kw || c.product_name.indexOf(kw) >= 0;
      return matchFilter && matchKw;
    });
    this.setData({ filtered });
  },

  onSetFilter(e: any) {
    this.setData({ filter: e.currentTarget.dataset.f as Filter });
    this._applyFilter();
  },

  onSearch(e: any) {
    this.setData({ keyword: e.detail.value });
    this._applyFilter();
  },

  onTapCard(e: any) {
    const id: string = e.currentTarget.dataset.id;
    const card = this.data.all.find(c => c.evaluation_id === id);
    if (card?.status === 'done') {
      this._openCompletedReport(card);
    } else {
      wx.navigateTo({ url: `/pages/chat/chat?evaluation_id=${id}` });
    }
  },

  async _openCompletedReport(card: HistoryVM) {
    const ready = await this._ensureBusinessReportCache(card);
    if (!ready) {
      wx.showToast({ title: '完整报告还未生成完成', icon: 'none' });
      return;
    }
    wx.navigateTo({ url: `/pages/report/report?evaluation_id=${card.evaluation_id}` });
  },

  _warmReportCaches(items: HistoryVM[]) {
    items
      .filter(item => item.status === 'done' && item.has_report && !hasBusinessReportCache(item.evaluation_id))
      .slice(0, 20)
      .forEach(item => { this._ensureBusinessReportCache(item).catch(() => false); });
  },

  async _ensureBusinessReportCache(item: HistoryVM): Promise<boolean> {
    if (hasBusinessReportCache(item.evaluation_id)) return true;
    const existing = this.reportCacheTasks[item.evaluation_id];
    if (existing) return existing;

    const task = api.getBusinessReportByEval(item.evaluation_id)
      .then(report => {
        wx.setStorageSync(
          businessReportCacheKey(item.evaluation_id),
          JSON.stringify({ report, productName: item.product_name || '' }),
        );
        return true;
      })
      .catch(() => false)
      .finally(() => {
        delete this.reportCacheTasks[item.evaluation_id];
      });
    this.reportCacheTasks[item.evaluation_id] = task;
    return task;
  },

  onTapConvEntry(e: any) {
    const evalId: string = e.currentTarget.dataset.evalId;
    if (!evalId) return;
    wx.navigateTo({ url: `/pages/chat/chat?evaluation_id=${evalId}&auto=0` });
  },

  async onCancelEval(e: any) {
    const id = e.currentTarget.dataset.id;
    const confirmed = await new Promise<boolean>(resolve =>
      wx.showModal({
        title: '取消调研',
        content: '确定要取消这个调研吗？',
        confirmText: '取消调研',
        cancelText: '继续',
        success: r => resolve(r.confirm),
      })
    );
    if (!confirmed) return;
    try {
      await api.cancelEvaluation(id);
      wx.showToast({ title: '已取消', icon: 'success' });
      this.onShow();
    } catch {
      wx.showToast({ title: '操作失败', icon: 'none' });
    }
  },

  async onDeleteEval(e: any) {
    const id = e.currentTarget.dataset.id;
    const confirmed = await new Promise<boolean>(resolve =>
      wx.showModal({
        title: '删除调研',
        content: '删除后无法恢复，确定要删除吗？',
        confirmText: '删除',
        cancelText: '取消',
        confirmColor: '#EF4444',
        success: r => resolve(r.confirm),
      })
    );
    if (!confirmed) return;
    try {
      await api.deleteEvaluation(id);
      wx.showToast({ title: '已删除', icon: 'success' });
      this.onShow();
    } catch {
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },
});
