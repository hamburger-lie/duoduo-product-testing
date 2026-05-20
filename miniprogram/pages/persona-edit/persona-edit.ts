import { api } from '../../services/api';
import type { PersonaDetail } from '../../types/api';

interface FormData {
  name: string;
  avatar: string;
  age: number;
  gender: 'female' | 'male' | 'other';
  city: string;
  occupation: string;
  income_monthly: number;
  persona_tag: string;
  bio: string;
}

const GENDER_OPTIONS = ['female', 'male', 'other'];
const GENDER_LABELS = ['女', '男', '其他'];

function buildProfile(bio: string) {
  const text = bio.trim() || '关注产品体验、真实使用感受和购买决策。';
  return {
    bio: text,
    shopping_habits: '会结合真实评价、价格和使用场景后再决定是否购买。',
    skincare_concerns: ['效果', '安全感', '性价比'],
    brand_preferences: [],
    price_sensitivity: '中等',
    info_channels: ['小红书', '电商评价', '朋友推荐'],
    decision_style: '理性比较后决策',
    pet_phrases: ['这个产品适合我吗？'],
    pain_points: ['担心产品效果不稳定', '担心宣传和实际体验不一致'],
    lifestyle: '日常消费谨慎，重视真实体验和长期使用反馈。',
  };
}

function buildOceanScores() {
  return { o: 60, c: 65, e: 50, a: 60, n: 45 };
}

Page({
  data: {
    isEdit: false,
    personaId: '',
    loading: false,
    saving: false,
    form: {
      name: '',
      avatar: '👤',
      age: 25,
      gender: 'female' as 'female' | 'male' | 'other',
      city: '',
      occupation: '',
      income_monthly: 8000,
      persona_tag: '',
      bio: '',
    } as FormData,
    genderLabels: GENDER_LABELS,
    genderIndex: 0,
  },

  async onLoad(options: { id?: string }) {
    if (options.id) {
      this.setData({ isEdit: true, personaId: options.id, loading: true });
      try {
        const p = await api.getPersona(options.id);
        const genderIndex = Math.max(0, GENDER_OPTIONS.indexOf(p.gender));
        this.setData({
          loading: false,
          genderIndex,
          form: {
            name: p.name,
            avatar: p.avatar || '👤',
            age: p.age,
            gender: p.gender,
            city: p.city,
            occupation: p.occupation,
            income_monthly: p.income_monthly,
            persona_tag: p.persona_tag,
            bio: (p as PersonaDetail).profile?.bio || '',
          },
        });
      } catch {
        this.setData({ loading: false });
        wx.showToast({ title: '加载失败', icon: 'none' });
      }
    }
  },

  onInput(e: any) {
    const field = e.currentTarget.dataset.field as keyof FormData;
    this.setData({ [`form.${field}`]: e.detail.value });
  },

  onAgeInput(e: any) {
    const v = parseInt(e.detail.value) || 25;
    this.setData({ 'form.age': Math.min(80, Math.max(16, v)) });
  },

  onIncomeInput(e: any) {
    const v = parseInt(e.detail.value) || 0;
    this.setData({ 'form.income_monthly': v });
  },

  onGenderChange(e: any) {
    const idx = parseInt(e.detail.value);
    this.setData({
      genderIndex: idx,
      'form.gender': GENDER_OPTIONS[idx] as 'female' | 'male' | 'other',
    });
  },

  async onSave() {
    const { form, isEdit, personaId, saving } = this.data;
    if (saving) return;
    if (!form.name.trim()) { wx.showToast({ title: '请填写名称', icon: 'none' }); return; }
    if (!form.city.trim()) { wx.showToast({ title: '请填写城市', icon: 'none' }); return; }
    if (!form.occupation.trim()) { wx.showToast({ title: '请填写职业', icon: 'none' }); return; }
    if (!form.persona_tag.trim()) { wx.showToast({ title: '请填写标签', icon: 'none' }); return; }

    this.setData({ saving: true });
    const payload = {
      name: form.name.trim(),
      avatar: form.avatar.trim() || '👤',
      age: form.age,
      gender: form.gender,
      city: form.city.trim(),
      occupation: form.occupation.trim(),
      income_monthly: form.income_monthly,
      persona_tag: form.persona_tag.trim(),
      categories: ['美妆'],
      is_critical: false,
      profile: buildProfile(form.bio),
      ocean: buildOceanScores(),
    };

    try {
      if (isEdit) {
        await api.updatePersona(personaId, payload);
      } else {
        await api.createPersona(payload as any);
      }
      wx.showToast({ title: '保存成功', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 800);
    } catch {
      this.setData({ saving: false });
      wx.showToast({ title: '保存失败', icon: 'none' });
    }
  },
});
