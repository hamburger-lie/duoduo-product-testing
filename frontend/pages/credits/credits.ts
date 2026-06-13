import { api } from '../../services/api';
import type { CreditTransaction } from '../../types/api';

type TxVM = CreditTransaction & { dateStr: string; isIncome: boolean };

function formatDate(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}年${pad(d.getMonth() + 1)}月${pad(d.getDate())}日 ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

Page({
  data: {
    balance: 0,
    transactions: [] as TxVM[],
    loading: true,
    empty: false,
  },

  async onLoad() {
    this.loadData();
  },

  async loadData() {
    try {
      const [balRes, txRes] = await Promise.all([
        api.getCreditsBalance(),
        api.listCreditTransactions(),
      ]);
      const transactions: TxVM[] = txRes.items.map(tx => ({
        ...tx,
        dateStr: formatDate(tx.created_at),
        isIncome: tx.amount > 0,
      }));
      this.setData({
        balance: balRes.balance,
        transactions,
        loading: false,
        empty: transactions.length === 0,
      });
    } catch {
      this.setData({ loading: false, empty: true });
    }
  },

});
