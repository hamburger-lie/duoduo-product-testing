import { api } from '../../services/api';

interface OrderItem {
  id: number;
  out_trade_no: string;
  amount_yuan: number;
  status: string;
  statusLabel: string;
  created_at_fmt: string;
  paid_at_fmt: string;
}

function fmtDatetime(iso: string | null): string {
  if (!iso) return '';
  // "2026-05-30T11:17:36.123456+00:00" → "2026/05/30 19:17:36" (UTC+8)
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

Page({
  data: {
    orders: [] as OrderItem[],
    loading: true,
    empty: false,
    highlightTradeNo: '',
  },

  async onLoad(options: Record<string, string>) {
    // 微信订单中心跳入时会带 id=out_trade_no
    const highlightTradeNo = options.id || '';
    this.setData({ highlightTradeNo });

    try {
      const raw = await api.listPlusOrders();
      const orders: OrderItem[] = raw.map(o => ({
        id: o.id,
        out_trade_no: o.out_trade_no,
        amount_yuan: o.amount_yuan,
        status: o.status,
        statusLabel: o.status === 'paid' ? '已支付' : o.status === 'pending' ? '待支付' : '失败',
        created_at_fmt: fmtDatetime(o.created_at),
        paid_at_fmt: fmtDatetime(o.paid_at),
      }));
      this.setData({ orders, loading: false, empty: orders.length === 0 });
    } catch {
      this.setData({ loading: false, empty: true });
    }
  },

  onTapUpgrade() {
    wx.navigateTo({ url: '/pages/upgrade/upgrade' });
  },
});
