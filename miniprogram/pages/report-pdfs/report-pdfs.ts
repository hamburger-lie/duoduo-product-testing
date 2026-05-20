import { api } from '../../services/api';
import { getToken, resolveMediaUrl } from '../../services/http';
import type { ReportPdfListItem } from '../../types/api';

interface ReportPdfVM extends ReportPdfListItem {
  dateStr: string;
  selected: boolean;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

Page({
  data: {
    loading: true,
    reports: [] as ReportPdfVM[],
    selecting: false,
    selectedCount: 0,
    allSelected: false,
  },

  async onShow() {
    await this.loadReports();
  },

  async loadReports() {
    this.setData({ loading: true });
    try {
      const res = await api.listReportPdfs();
      const reports: ReportPdfVM[] = res.items.map(item => ({
        ...item,
        pdf_url: resolveMediaUrl(item.pdf_url),
        dateStr: formatDate(item.generated_at),
        selected: false,
      }));
      this.setData({ reports, loading: false, selecting: false, selectedCount: 0, allSelected: false });
    } catch (err) {
      console.error('[report-pdfs.onShow]', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  async onPullDownRefresh() {
    await this.loadReports();
    wx.stopPullDownRefresh();
  },

  onTapOpen(e: any) {
    if (this.data.selecting) {
      this.onTapCardSelect(e);
      return;
    }
    const url = e.currentTarget.dataset.url as string;
    const name = (e.currentTarget.dataset.name as string) || '测品报告';
    if (!url) return;
    wx.showLoading({ title: '打开中…' });
    wx.downloadFile({
      url,
      header: getToken() ? { Authorization: 'Bearer ' + getToken() } : {},
      success: res => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          wx.hideLoading();
          wx.showToast({ title: '下载失败', icon: 'none' });
          return;
        }
        wx.openDocument({
          filePath: res.tempFilePath,
          fileType: 'pdf',
          showMenu: true,
          success: () => wx.hideLoading(),
          fail: () => {
            wx.hideLoading();
            wx.showToast({ title: `${name} 打开失败`, icon: 'none' });
          },
        });
      },
      fail: () => {
        wx.hideLoading();
        wx.showToast({ title: '下载失败', icon: 'none' });
      },
    });
  },

  onTapDeleteSingle(e: any) {
    const idx = Number(e.currentTarget.dataset.idx);
    const report = this.data.reports[idx];
    if (!report) return;
    wx.showModal({
      title: '删除报告',
      content: `确定删除「${report.product_name}」的 PDF 报告？`,
      confirmText: '删除',
      confirmColor: '#EF4444',
      success: async (res) => {
        if (!res.confirm) return;
        await this._doDelete([report.report_id]);
      },
    });
  },

  onTapSelect() {
    const reports = this.data.reports.map(r => ({ ...r, selected: false }));
    this.setData({ selecting: true, reports, selectedCount: 0, allSelected: false });
  },

  onTapCancelSelect() {
    const reports = this.data.reports.map(r => ({ ...r, selected: false }));
    this.setData({ selecting: false, reports, selectedCount: 0, allSelected: false });
  },

  onTapCardSelect(e: any) {
    const idx = Number(e.currentTarget.dataset.idx);
    const reports = this.data.reports.map((r, i) =>
      i === idx ? { ...r, selected: !r.selected } : r
    );
    const selectedCount = reports.filter(r => r.selected).length;
    this.setData({ reports, selectedCount, allSelected: selectedCount === reports.length });
  },

  onTapToggleAll() {
    const next = !this.data.allSelected;
    const reports = this.data.reports.map(r => ({ ...r, selected: next }));
    this.setData({ reports, allSelected: next, selectedCount: next ? reports.length : 0 });
  },

  async onTapDeleteSelected() {
    const ids = this.data.reports.filter(r => r.selected).map(r => r.report_id);
    if (ids.length === 0) {
      wx.showToast({ title: '请先选择报告', icon: 'none' });
      return;
    }
    wx.showModal({
      title: '批量删除',
      content: `确定删除选中的 ${ids.length} 份 PDF 报告？`,
      confirmText: '删除',
      confirmColor: '#EF4444',
      success: async (res) => {
        if (!res.confirm) return;
        await this._doDelete(ids);
      },
    });
  },

  async _doDelete(ids: string[]) {
    wx.showLoading({ title: '删除中…' });
    try {
      await api.deleteReportPdfs(ids);
      wx.hideLoading();
      wx.showToast({ title: '已删除', icon: 'success' });
      await this.loadReports();
    } catch {
      wx.hideLoading();
      wx.showToast({ title: '删除失败，请重试', icon: 'none' });
    }
  },
});
