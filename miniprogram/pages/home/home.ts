import { api } from '../../services/api';
import type { PersonaSummary } from '../../types/api';
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
};

const BUBBLE_LAYOUT = [
  { x: 8, y: 35, floatClass: 'fa' },
  { x: 454, y: 164, floatClass: 'fb' },
  { x: 8, y: 302, floatClass: 'fc' },
  { x: 452, y: 490, floatClass: 'fd' },
  { x: 70, y: 610, floatClass: 'fe' },
];

const FALLBACK_BUBBLES: HomeBubble[] = [
  { id: 'fallback_1', x: 8, y: 35, floatClass: 'fa', personaKey: 'male', avatarSlot: 7, group: '男性护肤人群', label: '结果导向 / 渠道运营' },
  { id: 'fallback_2', x: 454, y: 164, floatClass: 'fb', personaKey: 'female', avatarSlot: 1, group: '学生党', label: '小红书重度用户' },
  { id: 'fallback_3', x: 8, y: 302, floatClass: 'fc', personaKey: 'female', avatarSlot: 2, group: '彩妆尝鲜人群', label: '线下零售观察者' },
  { id: 'fallback_4', x: 452, y: 490, floatClass: 'fd', personaKey: 'female', avatarSlot: 5, group: '性价比党', label: '家庭预算敏感' },
  { id: 'fallback_5', x: 70, y: 610, floatClass: 'fe', personaKey: 'female', avatarSlot: 4, group: '成分党', label: '理性消费 / 一线城市' },
];

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
  const decorated = decoratePersonasWithAvatars(personas).slice(0, BUBBLE_LAYOUT.length);
  const bubbles = decorated.map((persona, index) => {
    const layout = BUBBLE_LAYOUT[index];
    return {
      id: persona.id,
      x: layout.x,
      y: layout.y,
      floatClass: layout.floatClass,
      personaKey: persona.avatar,
      avatarSlot: persona.avatarSlot,
      group: groupFromPersona(persona),
      label: labelFromPersona(persona),
    };
  });
  return bubbles.length ? bubbles : FALLBACK_BUBBLES;
}

Page({
  data: {
    bubbles: FALLBACK_BUBBLES,
  },

  onShow() {
    this.loadBubbles();
  },

  async loadBubbles() {
    try {
      await api.ensureAuth();
      const personas = await api.listPersonas({ is_system: false });
      this.setData({ bubbles: buildHomeBubbles(personas) });
    } catch {
      this.setData({ bubbles: FALLBACK_BUBBLES });
    }
  },

  onTapCreate() {
    wx.navigateTo({ url: '/pages/create/create' });
  },

  onTapBubble(e: any) {
    const id = String(e.currentTarget.dataset.id || '');
    if (!id || id.startsWith('fallback_')) {
      wx.navigateTo({ url: '/pages/personas/personas' });
      return;
    }
    wx.navigateTo({ url: `/pages/persona-edit/persona-edit?id=${id}` });
  },
});
