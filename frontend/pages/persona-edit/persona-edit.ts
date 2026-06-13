import { api } from '../../services/api';
import type { PersonaDetail } from '../../types/api';
import { fixedSlotForPersona, parseBackendAvatarSlot, preferredSlots } from '../../utils/personaAvatar';

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

type PersonaProfile = PersonaDetail['profile'];

function splitKeywords(text: string): string[] {
  return text
    .split(/[、,，/｜|;；\s]+/)
    .map(item => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function inferCategories(tag: string, occupation: string): string[] {
  const source = `${tag} ${occupation}`;
  const categories = ['美妆'];
  if (/家|母婴|孩子|妈妈|宝妈/.test(source)) categories.push('家清', '母婴');
  if (/学生|大学|小红书|潮|颜值|彩妆/.test(source)) categories.push('彩妆', '潮流');
  if (/男|剃须|运动|户外/.test(source)) categories.push('男士护理');
  if (/直播|渠道|导购|运营|线下|门店/.test(source)) categories.push('零售渠道');
  return Array.from(new Set(categories)).slice(0, 5);
}

function nameFromGroupTag(tag: string, fallback = ''): string {
  const cleanTag = tag.trim();
  if (!cleanTag) return fallback.trim() || '代表测品官';
  return cleanTag.replace(/[\/｜|、,，;；\s]+/g, '').slice(0, 12) || '代表测品官';
}

function buildProfile(form: FormData): PersonaProfile {
  const baseBio = form.bio.trim() || `${form.persona_tag}，生活在${form.city}，目前从事${form.occupation}。`;
  const tagWords = splitKeywords(form.persona_tag);
  const isStudent   = /学生|大学|校园/.test(form.occupation + form.persona_tag);
  const isRetail    = /导购|门店|渠道|运营|直播|电商/.test(form.occupation + form.persona_tag);
  const isFamily    = /家庭|宝妈|妈妈|亲子|孩子/.test(form.persona_tag + form.occupation);
  const isValue     = /性价比|预算|平价|价格|省钱/.test(form.persona_tag);
  const isIngredient= /成分|功效|理性|护肤/.test(form.persona_tag);
  const isYoung     = form.age <= 25;
  const isMiddle    = form.age >= 35;
  const isHighIncome= form.income_monthly >= 15000;
  const isLowIncome = form.income_monthly < 6000;

  const infoChannels = Array.from(new Set([
    isStudent  ? '小红书种草帖' : '小红书真实测评',
    isRetail   ? '线下门店顾客反馈' : '淘宝/京东商品评价',
    isFamily   ? '家庭成员和宝妈群推荐' : '朋友真实口碑',
    isRetail   ? '直播间讲解与顾客问答' : '抖音/B站短视频测评',
    isIngredient ? '成分表和功效研究贴' : '品牌官方说明',
  ]));

  const personalityTraits = Array.from(new Set([
    isIngredient ? '理性分析型' : isStudent ? '感性冲动型' : '务实判断型',
    isValue      ? '价格敏感型' : isHighIncome ? '品质优先型' : '均衡考量型',
    isRetail     ? '行业洞察型' : isFamily ? '责任保障型' : '自我体验型',
    isYoung      ? '社交驱动型' : isMiddle ? '经验积累型' : '信息主动型',
    isStudent    ? '口碑依赖型' : '独立判断型',
  ])).slice(0, 4);

  const purchaseTriggers = [
    isStudent   ? '身边同学反复推荐，且价格在自己预算范围内' : '长期关注后看到真实用户的多条正面反馈',
    isRetail    ? '发现这个产品卖点好讲、顾客问题少、退货率低' : isFamily ? '看到对家人安全有保障的权威认证或成分说明' : '找到与自己肤质或使用场景高度匹配的使用说明',
    isValue     ? '遇到限时折扣或赠品力度超出预期' : isHighIncome ? '在专柜/旗舰店体验后确认效果达到预期' : '试用装效果超出预期，决定购买正装',
    isIngredient ? '成分逻辑清晰，配方有研究背书，无明显刺激成分' : '被有真实感的用户故事或场景代入打动',
  ];

  const trustSignals = [
    isIngredient ? '成分表透明，有皮肤科医生背书或专利配方说明' : '大量真实用户的长期使用反馈',
    isRetail     ? '产品卖点精简易懂，顾客试用后反应自然正面' : isFamily ? '含有国际/国内权威机构安全认证标志' : '品牌有可查询的真实用户案例或使用前后对比',
    isStudent    ? '小红书/抖音博主真实测评，评论区讨论热烈且具体' : '朋友或家人的亲身使用推荐',
    isValue      ? '清晰标注容量和使用周期，算下来每次使用成本合理' : '品牌有完善的售后保障和无理由退换货政策',
    isHighIncome ? '产品线历史稳定，没有频繁改配或负面新闻' : '曾经使用过同品牌其他产品，建立过基础信任',
  ];

  const objectionPatterns = [
    '担心产品宣传效果和实际使用体验不一致，上脸后和图片/视频差距大',
    isValue || isLowIncome
      ? '容量和使用周期折算下来，实际单次使用成本比看起来贵很多'
      : '价格较高但看不出与平价替代品的本质差异，难以说服自己值这个价',
    isIngredient
      ? '成分表里有争议成分或香精，担心对自己肤质造成刺激'
      : isStudent
        ? '种草内容太多，不知道哪些是真实体验哪些是广告软文'
        : '产品定位模糊，不确定是否适合自己的年龄、肤质或使用场景',
    isRetail
      ? '卖点不够清晰，上手讲解时容易被顾客问倒，影响成交自信'
      : isFamily
        ? '缺乏针对家庭成员（特别是孩子和老人）的专项安全说明'
        : '复购成本高，担心一旦离开活动价格后难以持续使用',
    isMiddle
      ? '品牌过于年轻化，感觉不是为自己这个年龄段设计的，使用场景对不上'
      : '太多同类产品，这个品牌/产品没有令人印象深刻的差异化记忆点',
  ];

  const evaluationCriteria = Array.from(new Set([
    isIngredient ? '成分配方的安全性与功效逻辑' : '上脸后的即时感官体验',
    isRetail     ? '卖点是否好讲、顾客常见疑问是否好回答' : '真实用户的长期使用反馈',
    isValue      ? '容量/规格折算后的单次使用成本' : '使用体验相对于价格的综合性价比',
    isFamily     ? '成分安全认证与低刺激保障' : '与自身肤质、使用习惯的匹配程度',
    isStudent    ? '外观颜值与社交分享属性' : '品牌口碑稳定性与售后保障',
  ])).slice(0, 5);

  const contentPreferences = [
    isStudent    ? '真实开箱视频和上脸对比，喜欢有质感的拍摄和真实评论区' : '详细的长期使用日记和before/after对比图文',
    isIngredient ? '成分解析和功效原理科普，偏好数据和研究引用' : isFamily ? '安全测评和家庭实用性分析' : '具体使用场景和真实日常融入分享',
    isRetail     ? '行业分析和顾客心理洞察，关注销售技巧和市场趋势' : isValue ? '横向价格对比和平替推荐清单' : '品牌故事和产品研发背景',
    isYoung      ? '短视频和图文并茂的快速内容，信息密度高' : '深度长文和有深度的视频内容，不喜欢过度包装',
  ];

  const socialMediaBehavior = isStudent
    ? '每天活跃在小红书和抖音，喜欢保存和转发种草内容，会主动在评论区提问；购买后习惯发使用反馈帖，对互动响应敏感。'
    : isRetail
      ? '主要用微信行业群和直播平台获取产品信息，自己也会在朋友圈分享门店热销品；对品牌投放广告有较高识别度。'
      : isFamily
        ? '活跃在微信家长群和母婴社区，信任熟人推荐超过陌生博主；偶尔看小红书，但更多依赖口碑和家庭经验积累。'
        : isIngredient
          ? '在成分党相关论坛、小红书成分讨论区和B站科普视频中活跃，会主动研究品牌背景和配方迭代历史。'
          : `活跃在小红书和微博，每周固定浏览护肤类内容；关注${Math.min(3, tagWords.length) > 0 ? tagWords.slice(0, 2).join('和') : '真实测评'}类账号，偶尔参与话题讨论。`;

  const typicalScenario = isRetail
    ? `在门店或直播间工作时，会实时观察顾客对不同产品的反应，把顾客的真实疑问和购买障碍记下来，用来判断哪些产品值得主推。日常也会把自己当成顾客，用产品的角度想"我会在哪一步卡住"。`
    : isFamily
      ? `周末逛超市或母婴店时随手看同类产品的成分表，遇到陌生成分会当场搜索。家庭购买决策通常经过一到两周观察，会先买小样或试用装，确认家人用后没问题再下单正装。`
      : isStudent
        ? `在宿舍或图书馆刷手机时被种草，第一反应是截图存档；下课后和室友讨论，参考大家的使用经验；月底发生活费时集中下单，倾向买套装或多件折扣。`
        : `工作日晚上睡前是主要的内容消费时间，在这时候被种草的产品会加入购物车；周末有时间会去线下体验；通常会在同一产品上反复考虑一到两周后才决定购买。`;

  return {
    bio: baseBio,
    lifestyle: `${form.age}岁，常驻${form.city}，月收入约${form.income_monthly}元。${isStudent ? '在校学生，消费以生活费为主要来源。' : isRetail ? '从事零售/渠道相关工作，对产品卖点和顾客心理有一线感知。' : `从事${form.occupation}，消费预算相对${isHighIncome ? '充裕' : isLowIncome ? '有限' : '稳定'}。`}日常关注${tagWords.join('、') || '真实体验'}，有主见，会把产品放到自己的实际生活场景里判断。`,
    personality_traits: personalityTraits,
    shopping_habits: isRetail
      ? '每天会观察顾客在货架、试用和直播讲解中的真实反应，自己购买前也会先评估卖点是否好讲、上脸效果和退换货风险。'
      : isStudent
        ? '容易被社交平台内容种草，但下单前会反复比较同类产品的价格、颜值、评价和同学朋友的使用反馈，习惯在月底集中购买。'
        : isFamily
          ? '购买前优先确认安全认证和家庭成员的适用性，通常先买小样，确认无过敏反应后才下单正装，决策周期较长。'
          : '会先判断产品是否符合自己当前的肤质状态和使用场景，再结合真实评价、价格带、试用体验和长期复购成本综合决定。',
    decision_style: isIngredient
      ? '先系统研究成分配方的安全性和功效逻辑，再筛选真实用户的长期使用反馈，最后用价格、试用风险和替代方案综合取舍'
      : isRetail
        ? '先从顾客实际问题和销售转化率判断卖点是否好讲，再评估自己是否愿意主动推荐，对"讲不清楚的产品"保持谨慎'
        : isFamily
          ? '先确认产品对家庭成员是否安全无刺激，再考虑使用效果和价格；任何成分疑虑都是否决条件'
          : '先被具体使用场景或视觉表达吸引，再通过评价数量、价格合理性和身边人的反馈完成最终决策',
    price_sensitivity: isValue || isLowIncome
      ? '高，会认真计算容量折算的单次使用成本和复购压力，对活动价格和赠品力度敏感，正价时购买意愿明显下降'
      : isHighIncome
        ? '低，愿意为有明确功效背书和稳定使用体验支付溢价，但仍然要求价格与实际体验相符，不接受"智商税"'
        : '中等，愿意在效果明确的情况下支付合理溢价，但会认真评估性价比，价格带超出预期时会寻找平替',
    purchase_triggers: purchaseTriggers,
    trust_signals: trustSignals,
    objection_patterns: objectionPatterns,
    skincare_concerns: Array.from(new Set([
      ...tagWords,
      isIngredient ? '成分安全与配方透明' : '实际使用效果',
      isValue ? '性价比与复购成本' : '使用体验与质地',
      isFamily ? '低刺激安全认证' : '适合自身肤质',
      '包装设计与便携性',
    ])).slice(0, 6),
    brand_preferences: isValue
      ? ['定价稳定的平价口碑品牌', '有正规试用装或小样的品牌', '活动力度可预期的大众品牌']
      : isIngredient
        ? ['成分表透明、配方说明详细的品牌', '有皮肤科背书或专利成分的品牌', '历史配方稳定、少有负面新闻的品牌']
        : isFamily
          ? ['有国际安全认证的品牌', '产品线专注、定位明确的品牌', '线下可体验、售后有保障的品牌']
          : ['口碑稳定的国货新锐品牌', '定位清晰、卖点表达诚实的品牌', '有真实用户社群的品牌'],
    evaluation_criteria: evaluationCriteria,
    info_channels: infoChannels,
    content_preferences: contentPreferences,
    social_media_behavior: socialMediaBehavior,
    typical_scenario: typicalScenario,
    pain_points: [
      '担心宣传效果和实际体验不一致，上脸后和图片/视频差距大',
      isValue || isLowIncome
        ? '容量和使用周期折算后，实际单次成本比表面价格高，难以持续复购'
        : '价格较高但难以感知与平价替代品的本质差异，说服自己"值这个价"有障碍',
      isRetail
        ? '产品卖点不够清晰易懂，向顾客解释时容易被问倒，影响推荐信心'
        : isFamily
          ? '缺乏针对敏感人群（孩子/老人/孕妇）的专项安全说明，不敢轻易推荐给家人'
          : '同类产品太多，这个品牌没有令人印象深刻的差异化记忆点，容易被遗忘',
      isIngredient
        ? '成分表里有争议成分或添加香精，担心对自身肤质造成刺激，需要额外时间验证'
        : isStudent
          ? '种草内容真假难辨，不确定哪些是真实体验哪些是恰饭广告，决策成本高'
          : '复购成本高或活动价结束后价格不稳定，担心无法长期使用',
    ],
    pet_phrases: [
      isIngredient
        ? '这个成分浓度够吗？配方逻辑说得通吗？'
        : isRetail
          ? '如果顾客问我"这个和那个有什么区别"，我能回答上来吗？'
          : '这个卖点是真的解决我的问题，还是只是包装话术？',
      isValue
        ? '算下来一天用多少钱？用完一瓶要几个月？'
        : isFamily
          ? '成分表里有没有我不放心的东西？给孩子用安全吗？'
          : '如果让我自己花钱买，我会卡在哪一步？',
      isStudent
        ? '同款有没有平替？学姐/博主用过吗？'
        : isMiddle
          ? '这个品牌靠不靠谱？配方稳定吗？有没有改过方？'
          : '有没有试用装？能不能先试试再决定？',
    ],
    communication_style: isIngredient
      ? '表达严谨，习惯用数据和逻辑支撑观点；提问直接，会要求品牌给出有依据的答复；不接受模糊性描述，对"滋润""修护"等无量化指标的说法持怀疑态度'
      : isRetail
        ? '表达简练务实，习惯从销售和顾客角度出发；反馈直接，会直接说"这个卖点不好讲""顾客会问这个问题"；重视可执行性'
        : isStudent
          ? '表达活泼，喜欢用网络用语和表情包；反馈感性，容易被情绪和视觉打动；分享欲强，喜欢把体验发到社交平台'
          : isFamily
            ? '表达谨慎，倾向在做决定前询问多方意见；提问聚焦安全和实用，对过于营销化的语言警觉；重视他人的真实经验'
            : '表达务实，习惯结合自己的具体使用场景评价；反馈较为克制，更多关注实际效果而非外观包装；有主见，不轻易被广告打动',
  };
}

function formatDetailedBio(p: PersonaDetail): string {
  const profile = p.profile;
  if (!profile) return '';
  const lines = [
    profile.bio,
    `生活方式：${profile.lifestyle}`,
    profile.personality_traits?.length
      ? `性格特征：${profile.personality_traits.join('、')}`
      : '',
    `消费习惯：${profile.shopping_habits}`,
    `决策方式：${profile.decision_style}`,
    `价格敏感度：${profile.price_sensitivity}`,
    profile.purchase_triggers?.length
      ? `促成购买的关键：${profile.purchase_triggers.join('；')}`
      : '',
    profile.trust_signals?.length
      ? `建立信任的信号：${profile.trust_signals.join('；')}`
      : '',
    profile.evaluation_criteria?.length
      ? `评估产品的核心维度：${profile.evaluation_criteria.join('、')}`
      : '',
    `重点关注：${(profile.skincare_concerns || []).join('、') || '真实效果、使用体验、性价比'}`,
    `偏好品牌：${(profile.brand_preferences || []).join('、') || '口碑稳定、表达清晰、体验可信的品牌'}`,
    `信息来源：${(profile.info_channels || []).join('、') || '社交平台、电商评价、朋友推荐'}`,
    profile.content_preferences?.length
      ? `内容偏好：${profile.content_preferences.join('；')}`
      : '',
    profile.social_media_behavior
      ? `社媒行为：${profile.social_media_behavior}`
      : '',
    profile.typical_scenario
      ? `典型场景：${profile.typical_scenario}`
      : '',
    `常见顾虑：${(profile.pain_points || []).join('；')}`,
    profile.objection_patterns?.length
      ? `异议模式：${profile.objection_patterns.join('；')}`
      : '',
    profile.communication_style
      ? `表达风格：${profile.communication_style}`
      : '',
    `典型口头禅：${(profile.pet_phrases || []).join(' / ')}`,
  ];
  return lines.filter(Boolean).join('\n\n');
}

function buildOceanScores() {
  return { o: 60, c: 65, e: 50, a: 60, n: 45 };
}

/** 从现有角色列表中找出第一个未被使用的槽位，性别优先 */
async function pickUniqueAvatarSlot(
  gender: 'female' | 'male' | 'other',
  currentPersonaId = '',
): Promise<string> {
  try {
    const existing = await api.listPersonas({ is_system: false });
    const usedSlots = new Set<number>();
    for (const p of existing) {
      if (p.id === currentPersonaId) continue;
      const slot = parseBackendAvatarSlot(p.avatar || '');
      if (slot) usedSlots.add(slot);
    }
    const slots = preferredSlots(gender);
    for (const slot of slots) {
      if (!usedSlots.has(slot)) return String(slot);
    }
    // 全部占满时循环复用（正常不会超过10个角色）
    return String(slots[0]);
  } catch {
    return String(preferredSlots(gender)[0]);
  }
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
            bio: formatDetailedBio(p as PersonaDetail),
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
    if (!form.city.trim()) { wx.showToast({ title: '请填写城市', icon: 'none' }); return; }
    if (!form.occupation.trim()) { wx.showToast({ title: '请填写职业', icon: 'none' }); return; }
    if (!form.persona_tag.trim()) { wx.showToast({ title: '请填写所属群类标签', icon: 'none' }); return; }

    this.setData({ saving: true });

    // 新建时自动分配唯一头像槽位；编辑时若已有数字槽位则保留，否则重新分配
    let avatarValue = form.avatar.trim();
    const existingSlot = parseBackendAvatarSlot(avatarValue);
    if (!existingSlot) {
      avatarValue = String(
        fixedSlotForPersona({
          avatar: avatarValue,
          gender: form.gender,
          persona_tag: form.persona_tag,
          name: form.name,
        }) || await pickUniqueAvatarSlot(form.gender, isEdit ? personaId : ''),
      );
    }

    const payload = {
      name: nameFromGroupTag(form.persona_tag, form.name),
      avatar: avatarValue,
      age: form.age,
      gender: form.gender,
      city: form.city.trim(),
      occupation: form.occupation.trim(),
      income_monthly: form.income_monthly,
      persona_tag: form.persona_tag.trim(),
      categories: inferCategories(form.persona_tag, form.occupation),
      is_critical: false,
      profile: buildProfile(form),
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
