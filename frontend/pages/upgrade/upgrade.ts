import { api } from '../../services/api';
import { request } from '../../services/http';
import { E } from '../../services/endpoints';
import type { PersonaSummary } from '../../types/api';
import { decoratePersonasWithAvatars } from '../../utils/personaAvatar';

const FREE_PERSONA_NAMES = ['林雪', '陈婷婷', '赵小萌', '刘骁', '孙雨桐'];

interface PersonaItem {
  id: string;
  avatar: string;
  avatarSlot: string;
  personaTag: string;
}

interface PlusOrderRes {
  out_trade_no: string;
  timeStamp: string;
  nonceStr: string;
  package: string;
  signType: string;
  paySign: string;
}

Page({
  data: {
    isPlus: false,
    freePersonas: [] as PersonaItem[],
    plusPersonas: [] as PersonaItem[],
    paying: false,
  },

  async onLoad() {
    try {
      const [user, personas] = await Promise.all([
        api.getMe().catch(() => null),
        api.listPersonas({ owner_scope: 'system' }).catch(() => [] as PersonaSummary[]),
      ]);

      const seen = new Map<string, PersonaSummary>();
      personas.forEach(p => seen.set(p.name, p));
      const unique = Array.from(seen.values());
      const decorated = decoratePersonasWithAvatars(unique);

      const toItem = (p: typeof decorated[0]): PersonaItem => ({
        id: p.id,
        avatar: p.avatar,
        avatarSlot: (p as any).avatarSlot ?? '',
        personaTag: p.persona_tag || '',
      });

      this.setData({
        isPlus: user?.is_plus ?? false,
        freePersonas: decorated.filter(p => FREE_PERSONA_NAMES.includes(p.name)).map(toItem),
        plusPersonas: decorated.filter(p => !FREE_PERSONA_NAMES.includes(p.name)).map(toItem),
      });
    } catch {
      // fail silently
    }
  },

  async onTapUpgrade() {
    if (this.data.isPlus || this.data.paying) return;
    this.setData({ paying: true });
    wx.showLoading({ title: '下单中…' });

    try {
      const order = await request<PlusOrderRes>({
        url: E.UPGRADE_PLUS_ORDER,
        method: 'POST',
      });

      wx.hideLoading();

      await new Promise<void>((resolve, reject) => {
        wx.requestPayment({
          timeStamp: order.timeStamp,
          nonceStr: order.nonceStr,
          package: order.package,
          signType: order.signType as any,
          paySign: order.paySign,
          success: () => resolve(),
          fail: (err: any) => reject(err),
        });
      });

      // Payment success — refresh user info
      const user = await api.getMe();
      this.setData({ isPlus: user.is_plus ?? false });
      wx.showToast({ title: 'Plus 已开通！', icon: 'success', duration: 2500 });
    } catch (err: any) {
      wx.hideLoading();
      const msg = String(err?.errMsg || err?.message || '');
      if (msg.includes('cancel')) {
        // user cancelled — no toast
      } else if (msg.includes('503') || msg.includes('尚未开通')) {
        wx.showModal({
          title: '支付功能开通中',
          content: '微信虚拟支付审核中，通过后即可订阅。感谢您的耐心等待！',
          showCancel: false,
          confirmText: '知道了',
        });
      } else {
        wx.showToast({ title: '支付失败，请稍后重试', icon: 'none' });
      }
    } finally {
      this.setData({ paying: false });
    }
  },
});
