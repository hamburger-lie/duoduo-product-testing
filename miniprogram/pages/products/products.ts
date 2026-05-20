import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/http';

interface HistoryProductVM {
  id: string;
  name: string;
  image_url: string;
  has_image: boolean;
}

function toHistoryProducts(items: any[]): HistoryProductVM[] {
  const seen = new Set<string>();
  const products: HistoryProductVM[] = [];
  items.forEach(item => {
    const product = item?.product;
    if (!product?.id || seen.has(product.id)) return;
    seen.add(product.id);
    const imageUrl = resolveMediaUrl(product.image_url || '');
    products.push({
      id: product.id,
      name: product.name || '未命名产品',
      image_url: imageUrl,
      has_image: !!imageUrl,
    });
  });
  return products;
}

Page({
  data: {
    products: [] as HistoryProductVM[],
    loading: true,
    hasMore: false,
    cursor: null as string | null,
  },

  async onLoad() {
    this.loadProducts();
  },

  async loadProducts(append = false) {
    if (!append) this.setData({ loading: true, cursor: null });
    try {
      const res = await api.listHistory(append ? this.data.cursor ?? undefined : undefined);
      const incoming = toHistoryProducts(res.items ?? []);
      const products = append
        ? [
            ...this.data.products,
            ...incoming.filter(item => !this.data.products.some(existing => existing.id === item.id)),
          ]
        : incoming;
      this.setData({
        products,
        loading: false,
        hasMore: res.has_more,
        cursor: res.next_cursor,
      });
    } catch {
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onLoadMore() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadProducts(true);
    }
  },

  onTapCard(e: any) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/product-detail/product-detail?id=${id}` });
  },
});
