import { api } from '../../services/api';
import type { PersonaSummary } from '../../types/api';
import { hasToken, loginWithPhoneCode, clearAuth } from '../../utils/auth';
import { decoratePersonasWithAvatars } from '../../utils/personaAvatar';

type HomeBubble = {
  id: string;
  x: number;
  y: number;
  floatClass: string;
  personaKey: string;
  avatarSlot: number;
  group: string;
  label: string;
  labelTags: string[];
};

const BUBBLE_LAYOUT = [
  { x: 8, y: 35, floatClass: 'fa' },
  { x: 454, y: 164, floatClass: 'fb' },
  { x: 8, y: 302, floatClass: 'fc' },
  { x: 452, y: 490, floatClass: 'fd' },
  { x: 70, y: 610, floatClass: 'fe' },
];

// 32 personas matching DB system personas (male slots: 5 9 15 16 18 22 25 29)
const PERSONA_POOL: Array<{ personaKey: string; avatarSlot: number; group: string; label: string }> = [
  { personaKey: 'female', avatarSlot: 1,  group: '成分党',       label: '理性消费 / 一线城市白领' },
  { personaKey: 'female', avatarSlot: 2,  group: '性价比党',     label: '家庭预算敏感 / 直播间常客' },
  { personaKey: 'female', avatarSlot: 3,  group: '彩妆尝鲜',     label: '线下零售观察者 / 颜值包装敏感' },
  { personaKey: 'female', avatarSlot: 4,  group: '学生党',       label: '小红书重度用户 / 平价种草' },
  { personaKey: 'male',   avatarSlot: 5,  group: '男性护肤人群', label: '结果导向 / 渠道运营视角' },
  { personaKey: 'female', avatarSlot: 6,  group: '轻熟龄抗老',   label: '功效派 / 高消费力职场' },
  { personaKey: 'female', avatarSlot: 7,  group: '小镇青年',     label: '社媒种草 / 跟风消费' },
  { personaKey: 'female', avatarSlot: 8,  group: '敏感肌人群',   label: '成分避雷 / 安全至上' },
  { personaKey: 'male',   avatarSlot: 9,  group: '中年男性',     label: '被动护肤 / 妻子推荐' },
  { personaKey: 'female', avatarSlot: 10, group: '新手妈妈',     label: '安全至上 / 母婴交叉' },
  { personaKey: 'female', avatarSlot: 11, group: '医美术后',     label: '高客单 / 修护维稳' },
  { personaKey: 'female', avatarSlot: 12, group: '退休阿姨',     label: '传统渠道 / 口碑信任' },
  { personaKey: 'female', avatarSlot: 13, group: '海归白领',     label: '国际品牌对标 / 成分体验' },
  { personaKey: 'female', avatarSlot: 14, group: '下沉市场',     label: '直播间重度用户 / 主播信任' },
  { personaKey: 'male',   avatarSlot: 15, group: 'Z世代男生',    label: '颜值经济 / 潮流尝鲜' },
  { personaKey: 'male',   avatarSlot: 16, group: '直男选品',     label: '礼品购买 / 三线城市中年' },
  { personaKey: 'female', avatarSlot: 17, group: '纯线下消费者', label: '四线小城 / 实用主义' },
  { personaKey: 'male',   avatarSlot: 18, group: '运动男性',     label: '控油清爽 / 形象管理' },
  { personaKey: 'female', avatarSlot: 19, group: '品牌死忠',     label: '只买大牌 / 中年稳定消费' },
  { personaKey: 'female', avatarSlot: 20, group: '代购依赖',     label: '只信进口 / 国货偏见' },
  { personaKey: 'female', avatarSlot: 21, group: '极简节俭派',   label: '县城 / 护肤极简' },
  { personaKey: 'male',   avatarSlot: 22, group: '商务形象男',   label: '送礼刚需 / 品牌即面子' },
  { personaKey: 'female', avatarSlot: 23, group: '务实教师',     label: '性价比敏感 / 国货信任' },
  { personaKey: 'female', avatarSlot: 24, group: '高消费中年',   label: '抗老刚需 / 专柜忠实' },
  { personaKey: 'male',   avatarSlot: 25, group: '外表导向男',   label: '抖音种草 / 爱尝新' },
  { personaKey: 'female', avatarSlot: 26, group: '高消费学生党', label: '大牌入门 / 社交展示' },
  { personaKey: 'female', avatarSlot: 27, group: '学生成分党',   label: '药学背景 / 理性极致' },
  { personaKey: 'female', avatarSlot: 28, group: '跟风从众型',   label: '什么火买什么 / 无固定品牌' },
  { personaKey: 'male',   avatarSlot: 29, group: '理工直男',     label: '护肤零基础 / 能用就行' },
  { personaKey: 'female', avatarSlot: 30, group: '都市蓝领',     label: '性价比极致 / 务实节俭' },
  { personaKey: 'female', avatarSlot: 31, group: '小镇年轻宝妈', label: '社群团购 / 赠品敏感' },
  { personaKey: 'female', avatarSlot: 32, group: '都市银发',     label: '退休金充裕 / 抗老执着' },
];

function buildFallbackBubbles(): HomeBubble[] {
  const pool = PERSONA_POOL.slice().sort(() => Math.random() - 0.5).slice(0, BUBBLE_LAYOUT.length);
  return pool.map((p, i) => ({
    id: `fallback_${i + 1}`,
    x: BUBBLE_LAYOUT[i].x,
    y: BUBBLE_LAYOUT[i].y,
    floatClass: BUBBLE_LAYOUT[i].floatClass,
    personaKey: p.personaKey,
    avatarSlot: p.avatarSlot,
    group: p.group,
    label: p.label,
    labelTags: p.label.split(' / ').filter(Boolean),
  }));
}

function splitTag(tag: string): string[] {
  return tag
    .split(/[\/｜|、,，;；]+/)
    .map(item => item.trim())
    .filter(Boolean);
}

function groupFromPersona(persona: PersonaSummary): string {
  const [firstTag] = splitTag(persona.persona_tag);
  if (firstTag) return firstTag.endsWith('人群') || firstTag.endsWith('党') ? firstTag : `${firstTag}人群`;
  if (persona.occupation) return `${persona.occupation}人群`;
  return '代表消费人群';
}

function labelFromPersona(persona: PersonaSummary): string {
  const tags = splitTag(persona.persona_tag).slice(1);
  if (tags.length) return tags.slice(0, 2).join(' / ');
  const meta = [persona.city, persona.occupation].filter(Boolean);
  return meta.length ? meta.join(' / ') : '代表标签';
}

function buildHomeBubbles(personas: PersonaSummary[]): HomeBubble[] {
  const shuffled = personas.slice().sort(() => Math.random() - 0.5);
  const decorated = decoratePersonasWithAvatars(shuffled).slice(0, BUBBLE_LAYOUT.length);
  const bubbles = decorated.map((persona, index) => {
    const layout = BUBBLE_LAYOUT[index];
    const label = labelFromPersona(persona);
    return {
      id: persona.id,
      x: layout.x,
      y: layout.y,
      floatClass: layout.floatClass,
      personaKey: persona.avatar,
      avatarSlot: persona.avatarSlot,
      group: groupFromPersona(persona),
      label,
      labelTags: label.split(' / ').filter(Boolean),
    };
  });
  return bubbles.length ? bubbles : buildFallbackBubbles();
}

Page({
  data: {
    bubbles: buildFallbackBubbles(),
    bubblesVisible: false,
    showAuthModal: false,
    authLoading: false,
    showProfileSheet: false,
    profileAvatarTemp: '',
    profileNickname: '',
    profileSubmitting: false,
    showPersonaSheet: false,
    activePersona: null as HomeBubble | null,
    showDailyCreditModal: false,
    dailyCreditAmount: 10,
    dailyCreditBalance: 0,
  },

  onShow() {
    if (!hasToken()) {
      this.setData({ showAuthModal: false, bubbles: buildFallbackBubbles(), bubblesVisible: false });
      wx.nextTick(() => this.setData({ bubblesVisible: true }));
      return;
    }
    this.setData({ showAuthModal: false });
    this.loadBubbles();
    this.claimDailyLoginCredits();
  },

  async loadBubbles() {
    this.setData({ bubblesVisible: false });
    try {
      const personas = await api.listPersonas({ is_system: false });
      this.setData({ bubbles: buildHomeBubbles(personas), bubblesVisible: true });
    } catch {
      clearAuth();
      this.setData({ bubbles: buildFallbackBubbles(), bubblesVisible: true });
    }
  },

  async claimDailyLoginCredits() {
    try {
      const reward = await api.claimDailyLoginCredits();
      if (!reward.awarded) return;
      this.setData({
        showDailyCreditModal: true,
        dailyCreditAmount: reward.amount,
        dailyCreditBalance: reward.balance,
      });
    } catch (err) {
      console.warn('[home] daily login credits skipped', err);
    }
  },

  onCloseDailyCreditModal() {
    this.setData({ showDailyCreditModal: false });
  },

  onTapCreate() {
    if (!this.requireAuth()) return;
    wx.navigateTo({ url: '/pages/create/create' });
  },

  onTapBubble(e: any) {
    const id = String(e.currentTarget.dataset.id || '');
    if (!hasToken()) {
      const bubble = this.data.bubbles.find((b: HomeBubble) => b.id === id) || null;
      this.setData({ showPersonaSheet: true, activePersona: bubble });
      return;
    }
    if (!id || id.startsWith('fallback_')) {
      wx.navigateTo({ url: '/pages/personas/personas' });
      return;
    }
    wx.navigateTo({ url: `/pages/persona-edit/persona-edit?id=${id}` });
  },

  onClosePersonaSheet() {
    this.setData({ showPersonaSheet: false, activePersona: null });
  },

  onPersonaSheetLogin() {
    this.setData({ showPersonaSheet: false, activePersona: null, showAuthModal: true });
  },

  requireAuth(): boolean {
    if (hasToken()) return true;
    this.setData({ showAuthModal: true });
    return false;
  },

  async onGetPhoneNumber(e: any) {
    const detail = e.detail || {};
    const errMsg = String(detail.errMsg || '');
    const phoneOk = errMsg === 'getPhoneNumber:ok' || detail.errno === 0;
    const cancelled = errMsg.includes('cancel') || detail.errno === 20;

    if (cancelled) {
      wx.showToast({ title: '需要授权手机号后才能继续使用', icon: 'none' });
      this.setData({ showAuthModal: true });
      return;
    }
    if (!phoneOk || !detail.code) {
      wx.showToast({ title: '手机号授权失败，请重试', icon: 'none' });
      this.setData({ showAuthModal: true });
      return;
    }
    if (this.data.authLoading) return;

    this.setData({ authLoading: true });
    wx.showLoading({ title: '登录中' });
    try {
      const user = await loginWithPhoneCode(String(detail.code));
      wx.hideLoading();
      const pendingPersona = this.data.activePersona;
      const needsProfileSetup = !!user.is_new_user || !user.nickname || user.nickname === '未设置' || !user.avatar_url;
      if (needsProfileSetup) {
        this.setData({ showAuthModal: false, showPersonaSheet: false, activePersona: null, showProfileSheet: true });
      } else {
        this.setData({ showAuthModal: false, showPersonaSheet: false, activePersona: null });
        await this.loadBubbles();
        await this.claimDailyLoginCredits();
        wx.showToast({ title: '登录成功', icon: 'success' });
        if (pendingPersona) {
          if (pendingPersona.id.startsWith('fallback_')) {
            wx.navigateTo({ url: '/pages/personas/personas' });
          } else {
            wx.navigateTo({ url: `/pages/persona-edit/persona-edit?id=${pendingPersona.id}` });
          }
        }
      }
    } catch (err) {
      console.error('[home] login failed', err);
      clearAuth();
      this.setData({ showAuthModal: true });
      wx.hideLoading();
      wx.showToast({ title: '登录失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ authLoading: false });
    }
  },

  onProfileChooseAvatar(e: any) {
    const avatarUrl = e.detail?.avatarUrl as string | undefined;
    if (avatarUrl) this.setData({ profileAvatarTemp: avatarUrl });
  },

  onProfileNicknameInput(e: any) {
    this.setData({ profileNickname: (e.detail?.value || '').trim() });
  },

  async onProfileSubmit() {
    const { profileAvatarTemp, profileNickname, profileSubmitting } = this.data;
    if (!profileAvatarTemp || !profileNickname || profileSubmitting) return;
    this.setData({ profileSubmitting: true });
    wx.showLoading({ title: '保存中' });
    try {
      const res = await api.uploadAvatar(profileAvatarTemp);
      await api.updateProfile({ nickname: profileNickname, avatar_url: res.avatar_url });
      this.setData({ showProfileSheet: false, profileAvatarTemp: '', profileNickname: '' });
      await this.loadBubbles();
      await this.claimDailyLoginCredits();
      wx.showToast({ title: '设置成功', icon: 'success' });
    } catch {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
    } finally {
      this.setData({ profileSubmitting: false });
      wx.hideLoading();
    }
  },
});
