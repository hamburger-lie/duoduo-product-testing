import { api } from '../../services/api';
import { BASE_URL, getToken } from '../../services/http';
import type { BackendReport, BusinessReport, DeepAnalysis, DeepAnalysisSection } from '../../types/api';

const WHITEPAPER_VIEWER_PATH = '/whitepaper-static/index.html';
const REPORT_CACHE_PREFIX = 'business_report_cache_';

interface CachedReportSnapshot {
  report: BusinessReport;
  productName?: string;
}

function whitepaperBase(): string {
  return BASE_URL.replace(/\/api\/v1\/?$/, '').replace(/\/$/, '');
}

const DIM_LABELS: Record<string, string> = {
  // 购买意向
  first_impression: '第一印象',
  purchase_intent: '购买意向',
  purchase_motivation: '购买动机',
  purchase_willingness: '购买意愿',
  // 推荐/口碑
  recommendation: '推荐意愿',
  nps_recommendation: '推荐意愿',
  nps: '推荐意愿',
  // 差异化/独特性
  uniqueness: '独特性',
  distinctiveness: '差异化',
  novelty: '新颖性',
  // 相关性/契合度
  relevance: '相关性',
  brand_fit: '品牌契合度',
  // 价值/价格
  value_for_money: '性价比',
  price_perception: '价格感知',
  price_sensitivity: '价格敏感度',
  price_acceptance: '价格接受度',
  // 可信度
  believability: '可信度',
  credibility: '可信度',
  trust: '信任度',
  // 喜好/吸引力
  likeability: '喜好度',
  appeal: '整体吸引力',
  // 信息清晰度
  clarity: '信息清晰度',
  // 高端感
  premium: '高端感',
  // 包装
  packaging: '包装设计',
  package_appearance: '外观包装',
  // 功效/成分
  ingredient_safety: '成分安全',
  efficacy: '功效感知',
  safety: '安全感知',
  // 渠道/触达
  channel_touchpoint: '渠道触达感',
  channel_touch: '渠道触达感',
  channel_fit: '渠道匹配度',
  // 竞品
  competitor_comparison: '竞品对比力',
  competitive_advantage: '竞争优势',
  // 痛点
  painpoint_improvement: '痛点改善',
  pain_point: '痛点解决',
  // 综合/满意度
  overall: '整体评价',
  satisfaction: '满意度',
  // 肤感/体验
  texture: '质地体验',
  scent: '气味体验',
  absorption: '吸收效果',
  moisturizing: '保湿效果',
  whitening: '美白效果',
  anti_aging: '抗衰效果',
  sunscreen: '防晒效果',
};

const SEGMENT_LABEL_MAP: Record<string, string> = {
  female: '女性消费者',
  male: '男性消费者',
  gender_female: '女性消费者',
  gender_male: '男性消费者',
  young: '年轻群体',
  young_adult: '青年群体',
  middle_age: '中年群体',
  senior: '中老年群体',
  student: '学生群体',
  office_worker: '职场人群',
  freelancer: '自由职业者',
  stay_at_home_mom: '宝妈群体',
  mother: '宝妈群体',
  homemaker: '家庭主妇',
  frequent_buyer: '高频购买者',
  occasional_buyer: '偶尔购买者',
  price_sensitive: '价格敏感型',
  budget_conscious: '预算敏感型',
  premium_seeker: '品质追求型',
  quality_focused: '品质优先型',
  channel_touch: '渠道触达用户',
  channel_touch_users: '渠道触达用户',
  social_media: '社媒活跃用户',
  social_media_user: '社媒活跃用户',
  online_shopper: '线上购物者',
  offline_shopper: '线下购物者',
  ecommerce_user: '电商用户',
  high_intent: '高意向消费者',
  medium_intent: '中等意向消费者',
  low_intent: '低意向消费者',
  high_value: '高价值消费者',
  skincare_enthusiast: '护肤达人',
  makeup_user: '彩妆用户',
  sensitive_skin: '敏感肌群体',
  brand_loyal: '品牌忠诚用户',
  brand_switcher: '品牌切换用户',
  new_category_tryer: '新品尝鲜族',
  segment_1: '消费群体A',
  segment_2: '消费群体B',
  segment_3: '消费群体C',
  segment_4: '消费群体D',
  group_a: '消费群体A',
  group_b: '消费群体B',
  group_c: '消费群体C',
};

const GROUP_KEYWORDS = ['消费者', '用户', '群体', '人群', '人士', '女性', '男性', '年轻', '中年', '老年', '职场', '宝妈', '学生', '达人', '一族', '族群', '类', '型'];

/** 从评测答案构建 { 名字 → persona_tag, id → persona_tag } 映射表 */
function buildPersonaTagMap(answers: Array<{ persona_id?: string; persona_name?: string; persona_tag?: string }>): Record<string, string> {
  const map: Record<string, string> = {};
  for (const a of (answers || [])) {
    const tag = a.persona_tag || '';
    if (!tag) continue;
    if (a.persona_name) map[a.persona_name] = tag;
    if (a.persona_id)   map[a.persona_id]   = tag;
    map[tag] = tag; // 自映射，防止 segment 直接就是 tag
  }
  return map;
}

/** 优先从 persona 答案映射表里查真实群体标签，找不到再走通用规则 */
function resolveSegmentLabel(segment: string, tagMap: Record<string, string>): string {
  if (!segment) return '消费群体';
  if (tagMap[segment]) return tagMap[segment];
  return normalizeSegmentLabel(segment);
}

function normalizeSegmentLabel(segment: string): string {
  if (!segment) return '消费群体';
  if (/[\u4e00-\u9fa5]/.test(segment)) {
    // If it's 2-3 Chinese chars with no group keyword, treat as a personal name
    const cnChars = segment.match(/[\u4e00-\u9fa5]/g) || [];
    const hasGroupKeyword = GROUP_KEYWORDS.some(kw => segment.includes(kw));
    if (cnChars.length <= 3 && !hasGroupKeyword) return '消费者';
    return segment;
  }
  const key = segment.toLowerCase().replace(/[\s-]/g, '_');
  if (SEGMENT_LABEL_MAP[key]) return SEGMENT_LABEL_MAP[key];
  for (const [mapKey, mapVal] of Object.entries(SEGMENT_LABEL_MAP)) {
    if (key.includes(mapKey)) return mapVal;
  }
  return '消费群体';
}

const INTENT_DESCS: Record<string, string> = {
  '1': '不感兴趣',
  '2': '兴趣不大',
  '3': '一般',
  '4': '有购买意向',
  '5': '非常想买',
};

const DIM_WORD_MAP: Record<string, string> = {
  channel: '渠道', touch: '触达', touchpoint: '触达',
  competitor: '竞品', comparison: '对比', competitive: '竞争', advantage: '优势',
  purchase: '购买', intent: '意向', motivation: '动机', willingness: '意愿',
  nps: '推荐', recommendation: '推荐意愿', recommend: '推荐',
  package: '包装', appearance: '外观', packaging: '包装',
  pain: '痛点', painpoint: '痛点', improvement: '改善',
  price: '价格', sensitivity: '敏感度', perception: '感知', acceptance: '接受度',
  first: '第一', impression: '印象',
  ingredient: '成分', safety: '安全', safe: '安全',
  efficacy: '功效', effect: '效果',
  brand: '品牌', fit: '契合度',
  value: '价值', money: '性价比',
  unique: '独特', uniqueness: '独特性',
  novel: '新颖', novelty: '新颖性',
  appeal: '吸引力', like: '喜好', likeability: '喜好度',
  trust: '信任', credibility: '可信度', believability: '可信度',
  clarity: '清晰度', premium: '高端感', relevance: '相关性',
  overall: '综合', satisfaction: '满意度',
};

function dimLabel(dim: string): string {
  if (!dim) return '评分项';
  const exact = DIM_LABELS[dim] || DIM_LABELS[dim.toLowerCase()];
  if (exact) return exact;
  if (/[\u4e00-\u9fa5]/.test(dim)) return dim;
  // Try to translate word by word
  const words = dim.toLowerCase().replace(/[-\s]/g, '_').split('_').filter(Boolean);
  const translated = words.map(w => DIM_WORD_MAP[w] || null).filter(Boolean);
  if (translated.length > 0) return translated.join('');
  return '评分项';
}

function nonEmpty(items: Array<string | undefined>, fallback: string): string[] {
  const filtered = items.map(x => String(x || '').trim()).filter(Boolean);
  return filtered.length ? filtered : [fallback];
}

function normalizeText(text: string): string {
  return String(text || '').replace(/[，。、""\s]/g, '').trim();
}

function cleanReportText(text: string): string {
  return String(text || '')
    .replace(/目标角色/g, '目标消费者')
    .replace(/两位目标角色/g, '目标消费者')
    .replace(/多位目标角色/g, '目标消费者')
    .replace(/([0-9]+)位角色/g, '$1类角色标签所属群体')
    .replace(/([0-9]+)位消费者/g, '$1类角色标签所属群体')
    .replace(/([0-9]+)\s*类角色标签所属群体/g, '$1类角色标签所属群体')
    .replace(/角色回答/g, '消费者反馈')
    .replace(/角色反馈/g, '消费者反馈')
    .replace(/角色群体/g, '消费群体')
    .replace(/角色/g, '消费者');
}

/** 移除文本中形如"（如刘璇、陈婷婷）"的具体角色名引用 */
function stripPersonaNames(text: string): string {
  return String(text || '')
    // 移除全角括号内的"如姓名"引用，如：（如刘璇、陈婷婷）
    .replace(/（如[\u4e00-\u9fa5]{1,4}(?:[、，][\u4e00-\u9fa5]{1,4})*）/g, '')
    // 移除半角括号内的"如姓名"引用，如：(如林雪)
    .replace(/\(如[\u4e00-\u9fa5]{1,4}(?:[、，][\u4e00-\u9fa5]{1,4})*\)/g, '')
    // 移除"（包括/含 姓名）"类似表达
    .replace(/（(?:包括|含|例如)[\u4e00-\u9fa5]{1,4}(?:[、，][\u4e00-\u9fa5]{1,4})*）/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function uniqueText(items: string[], fallback: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const text = String(item || '').trim();
    const key = normalizeText(text);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(text);
  }
  return result.length ? result : [fallback];
}

function uniqueCards<T extends { title: string; note: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter(item => {
    const key = normalizeText(`${item.title}${item.note}`);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function actionTitleFromRecommendation(text: string): string {
  const value = String(text || '').trim();
  if (value.includes('控油')) return '验证控油持久度';
  if (value.includes('价格') || value.includes('定价')) return '复测价格接受度';
  if (value.includes('包装')) return '优化包装表达';
  if (value.includes('渠道')) return '验证渠道素材';
  if (value.includes('卖点')) return '复测核心卖点';
  return '明确下一轮验证';
}

function shortProductName(name: string): string {
  const chars = Array.from(String(name || '').trim());
  return chars.slice(0, 10).join('');
}

function reportCacheKey(evalId: string): string {
  return `${REPORT_CACHE_PREFIX}${evalId}`;
}

function readCachedReport(evalId: string): CachedReportSnapshot | null {
  try {
    const raw = wx.getStorageSync(reportCacheKey(evalId));
    if (!raw) return null;
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return parsed?.report ? parsed as CachedReportSnapshot : null;
  } catch {
    return null;
  }
}

function writeCachedReport(evalId: string, snapshot: CachedReportSnapshot): void {
  try {
    wx.setStorageSync(reportCacheKey(evalId), JSON.stringify(snapshot));
  } catch {
    // cache is only for faster history display
  }
}

// ── New helper functions ─────────────────────────────────────────────────────

const INTENT_COLORS: Record<string, string> = {
  '1': '#EF4444',
  '2': '#F97316',
  '3': '#EAB308',
  '4': '#34D399',
  '5': '#7C3AED',
};

function calcBoxScores(distribution: Record<string, number>): {
  topBoxPct: number;
  top2BoxPct: number;
  bottom2BoxPct: number;
  total: number;
} {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  const topBox = distribution['5'] || 0;
  const top2 = Object.entries(distribution)
    .filter(([k]) => parseFloat(k) >= 4)
    .reduce((s, [, v]) => s + v, 0);
  const bottom2 = Object.entries(distribution)
    .filter(([k]) => parseFloat(k) <= 2)
    .reduce((s, [, v]) => s + v, 0);
  return {
    topBoxPct: total > 0 ? Math.round((topBox / total) * 100) : 0,
    top2BoxPct: total > 0 ? Math.round((top2 / total) * 100) : 0,
    bottom2BoxPct: total > 0 ? Math.round((bottom2 / total) * 100) : 0,
    total,
  };
}

function buildStackedBar(distribution: Record<string, number>): Array<{ key: string; color: string; width: number; scoreWidth: number; count: number; desc: string }> {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  if (total === 0) return [];
  return ['1', '2', '3', '4', '5'].map(k => ({
    key: k,
    color: INTENT_COLORS[k] || '#ccc',
    width: Math.round(((distribution[k] || 0) / total) * 100),
    scoreWidth: Math.round((parseInt(k) / 5) * 100),
    count: distribution[k] || 0,
    desc: INTENT_DESCS[k] || '',
  })).filter(s => s.count > 0);
}

function buildDimensionBars(dims: Array<{ dim: string; score: number }>) {
  return dims.slice(0, 8).map(d => ({
    label: dimLabel(d.dim),
    value: d.score.toFixed(1),
    width: Math.round(Math.min(100, (d.score / 5) * 100)),
  }));
}

/**
 * 综合评分：Likert 标准化公式
 * score = round(avg_intent / 5 × 100)
 * 将 1-5 购买意愿均值线性映射到 0-100 分段，与 Qualtrics / Ipsos 行业惯例一致。
 *
 * 子维度：直接取后端 dimension_scores，同样按 score/5×100 归一化，
 * 不补零、不混入其他指标，保证数据来源可溯。
 */
function buildCompositeScore(dims: Array<{ dim: string; score: number }>, avgIntent: number) {
  const score = Math.round((avgIntent / 5) * 100);
  const grade = score >= 90 ? 'S' : score >= 75 ? 'A' : score >= 60 ? 'B' : score >= 45 ? 'C' : 'D';
  const label = score >= 75 ? '建议推进' : score >= 60 ? '可测试上市' : score >= 45 ? '优化后复测' : '建议深度优化';
  const comment = score >= 90 ? '强势概念，立即推进'
    : score >= 75 ? '概念成熟，可以投放'
    : score >= 60 ? '有潜力，打磨后上'
    : score >= 45 ? '信号偏弱，先优化'
    : '概念未成立，回炉';

  // 子维度：保留原始 1-5 分值；不足 6 个时用占位补齐，确保模板下标安全
  const filled = Array.from({ length: 6 }, (_, i) => {
    const d = dims[i];
    if (!d) return { label: '', rawScore: '', value: 0, width: 0, weight: 0, empty: true };
    return {
      label: dimLabel(d.dim),
      rawScore: d.score.toFixed(1),
      value: Math.round((d.score / 5) * 100),
      width: Math.round((d.score / 5) * 100),
      weight: 0,
      empty: false,
    };
  });

  return { compositeScore: score, compositeGrade: grade, compositeLabel: label, compositeComment: comment, compositeBars: filled };
}

const ORDINAL_ZH = ['一', '二', '三', '四', '五', '六'];

const SIX_DIM_WEIGHTS = [
  { dimKeys: ['purchase_intent', 'purchase_willingness', 'purchase_motivation', 'first_impression'], label: '高意向购买率', weight: 35, isTop2: true },
  { dimKeys: ['uniqueness', 'distinctiveness', 'novelty', 'differentiation'], label: '差异化', weight: 20 },
  { dimKeys: ['relevance', 'brand_fit', 'clarity'], label: '相关性', weight: 15 },
  { dimKeys: ['believability', 'credibility', 'trust'], label: '可信度', weight: 15 },
  { dimKeys: ['appeal', 'likeability', 'premium', 'competitive_advantage', 'competitor_comparison', 'overall', 'satisfaction'], label: '优势感', weight: 10 },
  { dimKeys: ['value_for_money', 'price_perception', 'price_acceptance', 'price_sensitivity'], label: '价值感', weight: 5 },
];

function buildReverseDimMap(): Record<string, string> {
  const map: Record<string, string> = {};
  for (const [eng, cn] of Object.entries(DIM_LABELS)) {
    map[cn] = eng;
    map[eng] = eng;
  }
  for (const [cnWord, engWord] of Object.entries(DIM_WORD_MAP)) {
    if (!map[engWord]) map[engWord] = engWord;
  }
  return map;
}
let _reverseDimMap: Record<string, string> | null = null;
function reverseDimMapCache(): Record<string, string> {
  if (!_reverseDimMap) _reverseDimMap = buildReverseDimMap();
  return _reverseDimMap;
}

function matchDimCategory(raw: string): string | null {
  const rev = reverseDimMapCache();
  const lower = raw.toLowerCase().replace(/[-\s]/g, '_');
  if (rev[lower]) {
    const eng = rev[lower];
    for (const cfg of SIX_DIM_WEIGHTS) {
      if (cfg.dimKeys.includes(eng)) return cfg.label;
    }
  }
  const cn = dimLabel(raw);
  if (cn && rev[cn]) {
    const eng = rev[cn];
    for (const cfg of SIX_DIM_WEIGHTS) {
      if (cfg.dimKeys.includes(eng)) return cfg.label;
    }
  }
  for (const cfg of SIX_DIM_WEIGHTS) {
    if (cfg.dimKeys.includes(lower)) return cfg.label;
  }
  return null;
}

function buildSixDimBreakdown(
  dims: Array<{ dim: string; score: number }>,
  top2BoxPct: number,
  avgIntent: number,
): Array<{ label: string; weight: number; score: number; contribution: number }> {
  const categoryScores: Record<string, number[]> = {};
  for (const d of dims) {
    const cat = matchDimCategory(d.dim);
    if (cat) {
      if (!categoryScores[cat]) categoryScores[cat] = [];
      categoryScores[cat].push(Math.round((d.score / 5) * 100));
    }
  }
  const avgNorm = Math.round((avgIntent / 5) * 100);

  return SIX_DIM_WEIGHTS.map(cfg => {
    let score: number;
    if (cfg.isTop2) {
      score = top2BoxPct;
    } else {
      const scores = categoryScores[cfg.label];
      score = scores && scores.length > 0
        ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
        : avgNorm;
    }
    const contribution = parseFloat(((cfg.weight / 100) * score).toFixed(1));
    return { label: cfg.label, weight: cfg.weight, score, contribution };
  });
}

function pickSegmentLabel(
  segment: string,
  idx: number,
  tagMap: Record<string, string>,
  sortedAnswers: Array<{ persona_tag?: string }>,
): string {
  // 策略1：tagMap 精确匹配（名字/id → persona_tag）
  const mapped = resolveSegmentLabel(segment, tagMap);
  if (mapped !== '消费者' && mapped !== '消费群体') return mapped;
  // 策略2：按意向排序后，用下标从 answers 里拿 persona_tag
  const ansTag = sortedAnswers[idx]?.persona_tag || '';
  if (ansTag) return ansTag;
  // 策略3：兜底序号标签
  return `消费群体${ORDINAL_ZH[idx] ?? idx + 1}`;
}

function buildSegmentRows(
  segments: Array<{ segment: string; count: number; avg_intent: number }>,
  tagMap: Record<string, string> = {},
  answers: Array<{ persona_tag?: string; overall_intent?: number }> = [],
) {
  const sortedAnswers = [...answers].sort((a, b) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));
  return [...segments]
    .sort((a, b) => b.avg_intent - a.avg_intent)
    .slice(0, 6)
    .map((s, i) => ({
      label: pickSegmentLabel(s.segment, i, tagMap, sortedAnswers),
      count: s.count,
      value: `${s.avg_intent.toFixed(1)}/5`,
      width: Math.round(Math.min(100, (s.avg_intent / 5) * 100)),
    }));
}

function buildConclusion(
  audiences: string[],
  opportunities: Array<{ title: string; shortTitle?: string }>,
  cons: Array<{ title: string; shortTitle?: string }>,
  top2BoxPct: number,
  compositeGrade: string,
): { text: string } {
  // 主力受众：取前2个，过长则截断
  const topAudiences = audiences.slice(0, 2).map(a => {
    const parts = String(a || '').split(/[/／·×\s]/);
    return parts[0].trim();
  }).filter(Boolean);

  // 核心卖点短标题
  const topPro = opportunities[0];
  const proLabel = topPro ? (topPro.shortTitle || topPro.title) : '';

  // 首要顾虑
  const topCon = cons[0];
  const conLabel = topCon ? (topCon.shortTitle || topCon.title) : '';

  // 组装结论句
  const audienceStr = topAudiences.length ? topAudiences.join('、') : '目标受众';
  const intentStr = top2BoxPct > 0 ? `高意向购买率 ${top2BoxPct}%` : '';

  let text = '';
  if (compositeGrade === 'S' || compositeGrade === 'A') {
    text = `概念整体成熟，${intentStr ? intentStr + '，' : ''}${audienceStr}群体共鸣明确`;
    if (proLabel) text += `，${proLabel}是核心驱动卖点`;
    text += '，可推进投放验证。';
  } else if (compositeGrade === 'B') {
    text = `概念具备潜力，${intentStr ? intentStr + '，' : ''}${audienceStr}群体反馈积极`;
    if (proLabel) text += `，${proLabel}形成初步共鸣`;
    if (conLabel) text += `，但${conLabel}仍是主要阻力`;
    text += '，建议优化表达后再扩量。';
  } else {
    text = `概念尚需打磨，${audienceStr}群体接受度有限`;
    if (conLabel) text += `，${conLabel}是最主要的决策障碍`;
    if (proLabel) text += `，${proLabel}可作为下阶段优化重点`;
    text += '，建议深度复测后再推进。';
  }
  return { text };
}

function buildPersonaCards(
  segments: Array<{ segment: string; count: number; avg_intent: number }>,
  tagMap: Record<string, string> = {},
  answers: Array<{ persona_tag?: string; overall_intent?: number }> = [],
): Array<{ name: string; score: number; tag: string; tone: string }> {
  const tones = ['green', 'violet', 'amber', 'blue', 'slate'];
  const sortedAnswers = [...answers].sort((a, b) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));
  const sorted = [...segments].sort((a, b) => b.avg_intent - a.avg_intent);
  const all = sorted.map((s, i) => {
    const score = Math.round(Math.min(100, (s.avg_intent / 5) * 100));
    const tag = score >= 90 ? '强推荐' : score >= 75 ? '推荐' : score >= 65 ? '可推' : score >= 55 ? '观望' : '谨慎';
    return { name: pickSegmentLabel(s.segment, i, tagMap, sortedAnswers), score, tag, tone: tones[i] || 'slate' };
  });
  // 显示所有 score≥80 的群体，最少保留最高分一个
  const filtered = all.filter(c => c.score >= 80);
  return filtered.length > 0 ? filtered : all.slice(0, 1);
}

function hmCellBg(score: number | null): string {
  if (score === null) return 'rgb(158,149,184)';
  // 米色 rgb(240,230,208) → 深紫 rgb(124,92,252)
  const t = (score - 1) / 4;
  const r = Math.round(240 + (124 - 240) * t);
  const g = Math.round(230 + (92 - 230) * t);
  const b = Math.round(208 + (252 - 208) * t);
  return `rgb(${r},${g},${b})`;
}

function buildHeatmapRows(
  segments: Array<{ segment: string; count: number; avg_intent: number }>,
  dims: Array<{ dim: string; score: number }>,
  overallAvg: number,
  tagMap: Record<string, string> = {},
  answers: Array<{
    persona_tag?: string;
    overall_intent?: number;
    answers?: Array<{ qid: string; answer: string | number | string[] }> | Record<string, any>;
  }> = [],
): Array<{ segment: string; cells: Array<{ score: number; bg: string; label: string }> }> {
  const topDims = dims.slice(0, 5);
  const sortedSegs = [...segments].sort((a, b) => b.avg_intent - a.avg_intent).slice(0, 5);
  const sortedAnswers = [...answers].sort((a, b) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));

  // 按 persona_tag 归集真实的逐维度打分（qid → 数值）
  const tagScoreMap: Record<string, Record<string, number[]>> = {};
  for (const a of answers) {
    const tag = a.persona_tag || '';
    if (!tag) continue;
    const items = Array.isArray(a.answers) ? a.answers : [];
    for (const item of items) {
      const v = Number(item.answer);
      if (!item.qid || isNaN(v) || v < 1 || v > 5) continue;
      if (!tagScoreMap[tag]) tagScoreMap[tag] = {};
      if (!tagScoreMap[tag][item.qid]) tagScoreMap[tag][item.qid] = [];
      tagScoreMap[tag][item.qid].push(v);
    }
  }

  return sortedSegs.map((seg, i) => {
    const fullLabel = pickSegmentLabel(seg.segment, i, tagMap, sortedAnswers);
    // 只取第一个标签（/ 前面的部分）
    const segLabel = fullLabel.split('/')[0].trim();
    const segTag = tagMap[seg.segment] || sortedAnswers[i]?.persona_tag || '';
    const dimScores = tagScoreMap[segTag] || {};

    return {
      segment: segLabel,
      cells: topDims.map(d => {
        const realVals = dimScores[d.dim];
        // 优先用真实逐维度均值，无数据则用群体整体意向均值兜底
        const score: number =
          realVals && realVals.length > 0
            ? parseFloat((realVals.reduce((s, v) => s + v, 0) / realVals.length).toFixed(1))
            : parseFloat(seg.avg_intent.toFixed(1));
        return { score, bg: hmCellBg(score), label: dimLabel(d.dim) };
      }),
    };
  });
}

function buildHeatmapDimHeaders(dims: Array<{ dim: string; score: number }>): string[] {
  return dims.slice(0, 5).map(d => dimLabel(d.dim));
}

/** 从长标题中提取关键词，例如"品牌背书是主要正向信号"→"品牌背书" */
function extractShortTitle(title: string): string {
  const t = String(title || '').trim();
  let m = t.match(/^(.+?)是主要/);
  if (m) return m[1];
  m = t.match(/^(.{1,6})是/);
  if (m) return m[1];
  m = t.match(/^(.+?)(?:可信度|不足|过于|较低|偏高|偏低|不够|较高|太高|太低|程度)/);
  if (m && m[1].length <= 8) return m[1];
  return Array.from(t).slice(0, 5).join('');
}

function stripInsightSuffix(text: string): string {
  return String(text || '')
    .replace(/^用户原声[:：]\s*/, '')
    .replace(/[“”"]/g, '')
    .replace(/^[-·\s]+/, '')
    .replace(/价格是?主要决策顾虑点?/g, '价格顾虑')
    .replace(/是?主要决策顾虑点/g, '')
    .replace(/是?主要正向信号/g, '')
    .replace(/是?主要决策顾虑/g, '')
    .replace(/是?主要购买驱动/g, '')
    .replace(/是?主要风险/g, '')
    .trim();
}

function looksLikePersonaTag(text: string): boolean {
  const value = String(text || '').trim();
  if (!value) return false;
  if (/价格|成分|证据|安全|功效|肤感|包装|品牌|背书|信任|刺激|过敏|油腻|清爽|补水|保湿|修护|温和|逻辑/.test(value)) {
    return false;
  }
  return /男性|女性|学生|宝妈|经理|用户|人群|群体|视角|入门|导向|预算|渠道|观察者|问客|党|敏感/.test(value);
}

function firstClause(text: string): string {
  const parts = String(text || '')
    .split(/[。；;！!？?\n，,、/／]/)
    .map(stripInsightSuffix)
    .filter(Boolean);
  const picked = parts.find(part => !looksLikePersonaTag(part)) || parts[0] || '';
  return picked.trim();
}

function cleanNextStep(text: string): string {
  return String(text || '')
    // 引号内的泛化标签只保留核心名词，后面的动作描述保留原文
    .replace(/['''"「」]([^'''"「」]+)['''"「」]/g, (_, inner) => extractShortTitle(inner))
    .replace(/是?主要正向信号|是?主要决策顾虑|是?主要购买驱动|是?主要风险/g, '')
    // 简化难懂的术语，不替换整句
    .replace(/A\/B\s*(?:文案)?测试/g, '多版本对比测试')
    .replace(/种草/g, '引发购买兴趣')
    .replace(/私域/g, '微信社群')
    .replace(/触达/g, '接触到')
    .replace(/投放素材/g, '广告内容')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function compactProductPoint(title: string, note?: string, quote?: string): string {
  // 只从本次调研返回字段提取：标题优先，业务解释补充，真实原声兜底；不做预设模板改写。
  const candidates = [title, note, quote]
    .map(v => firstClause(v || ''))
    .map(v => cleanReportText(v))
    .filter(v => {
      if (!v || Array.from(v).length < 2) return false;
      if (looksLikePersonaTag(v)) return false;
      if (/该优势在本轮调研|该风险需要|优先从/.test(v)) return false;
      return true;
    });
  const picked = candidates[0] || firstClause(title) || '';
  return Array.from(picked).slice(0, 24).join('');
}

function buildProsRanked(
  pros: Array<{ title: string; support_count: number; evidence_quotes?: Array<{ persona_name: string; quote: string }>; business_implication?: string }>,
  total: number,
): Array<{ title: string; shortTitle: string; count: number; pct: number; width: number }> {
  return (pros || []).slice(0, 5).map(p => {
    const pct = total > 0 ? Math.round((p.support_count / total) * 100) : 0;
    return {
      title: p.title,
      shortTitle: extractShortTitle(p.title),
      count: p.support_count,
      pct,
      width: Math.min(100, pct),
    };
  });
}

function buildConsRanked(
  cons: Array<{ title: string; support_count: number; evidence_quotes?: Array<{ persona_name: string; quote: string }>; improvement_suggestion?: string }>,
  total: number,
): Array<{ title: string; shortTitle: string; count: number; pct: number; width: number }> {
  return (cons || []).slice(0, 5).map(c => {
    const pct = total > 0 ? Math.round((c.support_count / total) * 100) : 0;
    return {
      title: c.title,
      shortTitle: extractShortTitle(c.title),
      count: c.support_count,
      pct,
      width: Math.min(100, pct),
    };
  });
}

function buildThemeBubbles(
  pros: Array<{ title: string; support_count: number }>,
  cons: Array<{ title: string; support_count: number }>,
): { positive: Array<{ title: string; count: number; size: string }>; negative: Array<{ title: string; count: number; size: string }> } {
  const sizeClass = (count: number) => count >= 5 ? 'lg' : count >= 3 ? 'md' : 'sm';
  return {
    positive: (pros || []).slice(0, 5).map(p => ({ title: p.title, count: p.support_count, size: sizeClass(p.support_count) })),
    negative: (cons || []).slice(0, 5).map(c => ({ title: c.title, count: c.support_count, size: sizeClass(c.support_count) })),
  };
}

function buildPriceBars(
  priceSensitivity: Array<{ range: string; count: number }>,
): {
  slices: Array<{ range: string; count: number; pct: number; color: string }>;
  pieStyle: string;
  total: number;
} {
  const colors = ['#7C3AED', '#14B8A6', '#F59E0B', '#F43F5E'];
  const rows = (priceSensitivity || []).filter(p => p.count > 0);
  const total = rows.reduce((sum, p) => sum + p.count, 0);
  let cursor = 0;
  const slices = rows.map((p, idx) => {
    const pct = total > 0 ? Math.round((p.count / total) * 100) : 0;
    const start = cursor;
    const end = idx === rows.length - 1 ? 100 : cursor + (total > 0 ? (p.count / total) * 100 : 0);
    cursor = end;
    return {
      range: p.range,
      count: p.count,
      pct,
      color: colors[idx % colors.length],
      start,
      end,
    };
  });
  const pieStyle = slices.length
    ? `background: conic-gradient(${slices
        .map(s => `${s.color} ${s.start.toFixed(2)}% ${s.end.toFixed(2)}%`)
        .join(', ')});`
    : '';
  return {
    slices: slices.map(({ start, end, ...slice }) => slice),
    pieStyle,
    total,
  };
}

function buildPriorityMatrix(
  pros: Array<{
    title: string;
    support_count: number;
    evidence_quotes?: Array<{ persona_name?: string; quote?: string }>;
    quotes?: Array<{ persona_name?: string; quote?: string }>;
    business_implication?: string;
  }>,
  cons: Array<{
    title: string;
    support_count: number;
    evidence_quotes?: Array<{ persona_name?: string; quote?: string }>;
    quotes?: Array<{ persona_name?: string; quote?: string }>;
    improvement_suggestion?: string;
  }>,
  totalRespondents: number,
): {
  topRight: Array<{ title: string; count: number; pct: number; audience: string; action: string }>;
  topLeft: Array<{ title: string; count: number; pct: number; audience: string; action: string }>;
  bottomRight: Array<{ title: string; count: number; pct: number; audience: string; action: string }>;
  bottomLeft: Array<{ title: string; count: number; pct: number; audience: string; action: string }>;
} {
  const highThreshold = totalRespondents > 0 ? Math.ceil(totalRespondents * 0.35) : 2;
  const toAudience = (item: { evidence_quotes?: Array<{ persona_name?: string }>; quotes?: Array<{ persona_name?: string }> }) => {
    const labels = [...(item.evidence_quotes || []), ...(item.quotes || [])]
      .map(q => cleanReportText(stripPersonaNames(q.persona_name || '')))
      .filter(Boolean);
    const unique = Array.from(new Set(labels)).slice(0, 3);
    return unique.length ? unique.join('、') : '本轮受访群体';
  };
  const toItem = <T extends { title: string; support_count: number; evidence_quotes?: Array<{ persona_name?: string }>; quotes?: Array<{ persona_name?: string }> }>(
    item: T,
    action: string,
  ) => ({
    title: cleanReportText(item.title),
    count: item.support_count || 0,
    pct: totalRespondents > 0 ? Math.round(((item.support_count || 0) / totalRespondents) * 100) : 0,
    audience: toAudience(item),
    action,
  });
  const prosHigh = (pros || []).filter(p => p.support_count >= highThreshold).slice(0, 1);
  const prosLow = (pros || []).filter(p => p.support_count < highThreshold).slice(0, 1);
  const consHigh = (cons || []).filter(c => c.support_count >= highThreshold).slice(0, 1);
  const consLow = (cons || []).filter(c => c.support_count < highThreshold).slice(0, 1);
  return {
    topRight: prosHigh.map(p => toItem(p, '放大到首屏卖点、短视频开场或私域话术')),
    bottomRight: prosLow.map(p => toItem(p, '作为备选卖点低成本复用')),
    topLeft: consHigh.map(c => toItem(c, '优先补证据、调价格解释或重写表达')),
    bottomLeft: consLow.map(c => toItem(c, '暂不投入大改，保留观察')),
  };
}

function buildMarketingAngles(
  angles: Array<{ angle: string; suitable_segment: string; risk_note: string }>,
): Array<{ angle: string; segment: string; risk: string }> {
  return (angles || []).slice(0, 5).map(a => ({
    angle: a.angle,
    segment: normalizeSegmentLabel(stripPersonaNames(a.suitable_segment)),
    risk: a.risk_note,
  }));
}

function buildAttributedQuotes(
  pros: Array<{ title: string; evidence_quotes?: Array<{ quote: string }> }>,
  cons: Array<{ title: string; evidence_quotes?: Array<{ quote: string }> }>,
): Array<{ role: string; quote: string; positive: boolean }> {
  const result: Array<{ role: string; quote: string; positive: boolean }> = [];
  for (const item of (pros || [])) {
    const q = item.evidence_quotes?.[0];
    if (q?.quote && result.length < 3) result.push({ role: `认可「${item.title}」的消费者`, quote: q.quote, positive: true });
  }
  for (const item of (cons || [])) {
    const q = item.evidence_quotes?.[0];
    if (q?.quote && result.length < 5) result.push({ role: `顾虑「${item.title}」的消费者`, quote: q.quote, positive: false });
  }
  return result;
}

function buildBaseAttributedQuotes(
  pros: Array<{ title: string; quotes?: Array<{ quote: string }> }>,
  cons: Array<{ title: string; quotes?: Array<{ quote: string }> }>,
): Array<{ role: string; quote: string; positive: boolean }> {
  const result: Array<{ role: string; quote: string; positive: boolean }> = [];
  for (const item of (pros || [])) {
    const q = item.quotes?.[0];
    if (q?.quote && result.length < 3) result.push({ role: `认可「${item.title}」的消费者`, quote: q.quote, positive: true });
  }
  for (const item of (cons || [])) {
    const q = item.quotes?.[0];
    if (q?.quote && result.length < 5) result.push({ role: `顾虑「${item.title}」的消费者`, quote: q.quote, positive: false });
  }
  return result;
}

// ── Deep analysis fallback generator ─────────────────────────────────────────

/**
 * 从调研 vm 数据生成深度研究报告的分析内容。
 * 仅在后端 API 不可用且无缓存时作为兜底使用。
 * 正常流程下，深度分析优先使用后端 AI 生成的真实内容。
 *
 * 内容特点：基于实际调研数据（卖点排名、顾虑分布、受众画像）构建分析叙事，
 * 通过归因推理和因果链条增强说服力，避免平铺罗列。
 *
 * 每段结构：
 *   highlight —— 气泡摘要，突出核心结论，用 \n 分隔多行
 *   content   —— 正文详解，数据驱动归因，突出关键发现
 *
 * 章节设计：
 *   一、卖点共鸣与群体锁定 —— 正向信号 + 高转化群体决策路径
 *   二、失效信号与阻力区间 —— 决策顾虑归因 + 低转化群体分析
 *   三、市场建议           —— 两阶段策略 + 渠道执行 + 边界提示
 */
function buildDeepSectionsFromVM(
  vm: {
    prosRanked: Array<{ title: string; shortTitle: string; pct: number }>;
    consRanked: Array<{ title: string; shortTitle: string; pct: number }>;
    themeBubbles: { positive: Array<{ title: string }>; negative: Array<{ title: string }> };
    audiences: string[];
    leastLikelyAudiences: string[];
    channels: string[];
    top2BoxPct: number;
  },
): DeepAnalysisSection[] {
  const pros = vm.prosRanked.filter(p => p.pct > 0).slice(0, 3);
  const cons = vm.consRanked.filter(c => c.pct > 0).slice(0, 3);
  const posThemes = vm.themeBubbles.positive.map(t => t.title).filter(Boolean).slice(0, 3);
  const negThemes = vm.themeBubbles.negative.map(t => t.title).filter(Boolean).slice(0, 3);
  const buyAudiences = vm.audiences.filter(Boolean).slice(0, 3);
  const noBuyAudiences = vm.leastLikelyAudiences.filter(Boolean).slice(0, 3);
  const chs = vm.channels.filter(Boolean).slice(0, 3);

  // 提取短标题用于气泡展示
  const prosTags = pros.map(p => p.shortTitle || p.title);
  const consTags = cons.map(c => c.shortTitle || c.title);

  // ── 一、卖点共鸣与群体锁定 ──
  const h1Lines: string[] = [];
  if (prosTags.length) h1Lines.push(`共鸣卖点：${prosTags.join(' · ')}`);
  if (buyAudiences.length) h1Lines.push(`精准群体：${buyAudiences.join(' · ')}`);
  if (vm.top2BoxPct > 0) h1Lines.push(`高意向购买率：${vm.top2BoxPct}%`);

  const s1: string[] = [];
  if (pros.length && posThemes.length) {
    const prosText = pros.map(p => `${p.shortTitle || p.title}（${p.pct}%）`).join('、');
    s1.push(
      `本轮调研量化评分与开放反馈形成双重印证：卖点支持度前三位为${prosText}，` +
      `消费者自发提及的正向信号同步集中于${posThemes.join('、')}维度。` +
      `两项数据的重叠表明产品在上述方向上已建立起清晰的差异化认知，共鸣信号明确。`,
    );
  } else if (pros.length) {
    const prosText = pros.map(p => `${p.shortTitle || p.title}（${p.pct}%）`).join('、');
    s1.push(`本轮调研卖点支持度前三位为${prosText}，上述卖点在受访群体中形成明确的正向共鸣。`);
  }
  if (buyAudiences.length && pros.length >= 2) {
    s1.push(
      `${buyAudiences.join('、')}是当前购买意愿最强的受访群体，` +
      `其决策路径高度依赖"${pros[0].shortTitle || pros[0].title}→${pros[1].shortTitle || pros[1].title}"的评估链条。` +
      `建议将这两个核心卖点作为首轮投放的信息锚点，优先锁定该群体的完整转化路径。`,
    );
  } else if (buyAudiences.length) {
    s1.push(
      `${buyAudiences.join('、')}是当前购买意愿最强的受访群体，` +
      `建议将上述共鸣卖点作为首轮投放的核心信息，优先锁定该群体的完整转化路径。`,
    );
  }

  // ── 二、失效信号与阻力区间 ──
  const h2Lines: string[] = [];
  if (negThemes.length) h2Lines.push(`主要顾虑：${negThemes.join(' · ')}`);
  if (noBuyAudiences.length) h2Lines.push(`阻力群体：${noBuyAudiences.join(' · ')}`);

  const s2: string[] = [];
  if (negThemes.length && cons.length) {
    const consText = cons.map(c => `${c.shortTitle || c.title}（${c.pct}%）`).join('、');
    s2.push(
      `本轮识别出主要决策顾虑：${negThemes.join('、')}，` +
      `与卖点层面的正面信号形成对照——提及率依次为${consText}。` +
      `其中"${cons[0].shortTitle || cons[0].title}"影响范围最广，是最主要的购买拦截因素；` +
      `建议在下轮调研中针对每个顾虑设计定向追问，明确触发条件和可改善幅度。`,
    );
  } else if (negThemes.length) {
    s2.push(
      `本轮识别出主要决策顾虑：${negThemes.join('、')}，` +
      `这些顾虑构成当前产品表达的薄弱环节，建议在下轮调研中逐一设计定向追问。`,
    );
  }
  if (noBuyAudiences.length) {
    s2.push(
      `${noBuyAudiences.join('、')}是本轮转化效率最低的群体，` +
      `现有卖点组合未能有效覆盖其核心决策维度，` +
      `单纯的曝光增量无法弥补其评估框架中的证据缺口。` +
      `建议下一阶段通过定向深访明确该群体的决策优先级排序，再制定差异化触达策略。`,
    );
  }

  // ── 三、市场建议 ──
  const h3Lines: string[] = [];
  h3Lines.push(`策略路径：高意向群体优先收割 → 阻力群体阶段性突破`);
  if (buyAudiences.length) h3Lines.push(`首轮重点：${buyAudiences.join(' · ')}`);

  const s3: string[] = [];
  s3.push(
    `建议采取两阶段投放路径：首轮资源集中于${buyAudiences.length ? buyAudiences.join('、') : '高意向受众'}，` +
    `以${prosTags.length >= 2 ? prosTags.slice(0, 2).join('和') : (prosTags[0] || '核心卖点')}为信息锚点构建投放素材；` +
    `针对价格敏感群体，建议通过降低首次决策门槛（如试用装、限时优惠）来突破转化障碍。`,
  );
  if (chs.length) {
    s3.push(`渠道执行层面：${chs.join('；')}。`);
  }
  if (noBuyAudiences.length) {
    s3.push(
      `第二阶段突破${noBuyAudiences.slice(0, 2).join('、')}等阻力群体前，` +
      `须优先通过实证数据和真实用户口碑构建信任基础——` +
      `单纯的曝光增量无法弥补消费者决策链路中的证据缺口。`,
    );
  }

  return [
    { title: '一、卖点共鸣与群体锁定', highlight: h1Lines.join('\n'), content: s1.join('') },
    { title: '二、失效信号与阻力区间', highlight: h2Lines.join('\n'), content: s2.join('') },
    { title: '三、市场建议', highlight: h3Lines.join('\n'), content: s3.join('') },
  ];
}

// ── Default VM shape ─────────────────────────────────────────────────────────

function defaultVM() {
  return {
    productName: '',
    generatedAt: '',
    verdictText: '',
    verdictClass: '',
    verdictReason: '',
    intent: '0.0/5',
    intentBarWidth: 0,
    confidence: '0%',
    topBoxPct: 0,
    top2BoxPct: 0,
    bottom2BoxPct: 0,
    top2BoxTotal: 0,
    signals: [] as Array<{ label: string; active: boolean; value: string }>,
    summary: [] as string[],
    stackedBar: [] as Array<{ key: string; color: string; width: number; count: number }>,
    conclusion: { text: '' },
    personaCards: [] as Array<{ name: string; score: number; tag: string }>,
    segmentRows: [] as Array<{ label: string; count: number; value: string; width: number }>,
    heatmapDimHeaders: [] as string[],
    heatmapRows: [] as Array<{ segment: string; cells: Array<{ score: number; bg: string; label: string }> }>,
    dimensionBars: [] as Array<{ label: string; value: string; width: number }>,
    prosRanked: [] as Array<{ title: string; shortTitle: string; count: number; pct: number; width: number }>,
    consRanked: [] as Array<{ title: string; shortTitle: string; count: number; pct: number; width: number }>,
    themeBubbles: { positive: [] as Array<{ title: string; count: number; size: string }>, negative: [] as Array<{ title: string; count: number; size: string }> },
    priceBars: [] as Array<{ range: string; count: number; pct: number; color: string }>,
    pricePieStyle: '',
    priceTotal: 0,
    benchmarkRows: [] as Array<{ label: string; ourScore: string; ourWidth: number; benchScore: string; benchWidth: number; aboveBench: boolean }>,
    compositeScore: 0,
    compositeGrade: '',
    compositeLabel: '',
    compositeComment: '',
    compositeBars: [] as Array<{ label: string; rawScore: string; weight: number; value: number; width: number; empty: boolean }>,
    priorityMatrix: {
      topRight: [] as Array<{ title: string; count: number; pct: number; audience: string; action: string }>,
      topLeft: [] as Array<{ title: string; count: number; pct: number; audience: string; action: string }>,
      bottomRight: [] as Array<{ title: string; count: number; pct: number; audience: string; action: string }>,
      bottomLeft: [] as Array<{ title: string; count: number; pct: number; audience: string; action: string }>,
    },
    marketingAngles: [] as Array<{ angle: string; segment: string; risk: string }>,
    audiences: [] as string[],
    leastLikelyAudiences: [] as string[],
    channels: [] as string[],
    attributedQuotes: [] as Array<{ role: string; quote: string; positive: boolean }>,
    quotes: [] as string[],
    evidenceChains: [] as Array<{ conclusion: string; roles: string; action: string; quote: string }>,
    focusCards: [] as Array<{ label: string; title: string; text: string }>,
    nextSteps: [] as string[],
    opportunities: [] as Array<{ title: string; note: string; concise: string; count: number }>,
    risks: [] as Array<{ title: string; note: string; concise: string; count: number }>,
    sixDimBreakdown: [] as Array<{ label: string; weight: number; score: number; contribution: number }>,
    formulaNotes: [
      '购买均值 = 购买意愿评分总和 / 有效样本数。',
      '最高档占比 = 5分人数 / 有效样本数；高意向占比 = 4-5分人数 / 有效样本数；低意向占比 = 1-2分人数 / 有效样本数。',
      '核心指标均值 = 该指标评分总和 / 有效回答数；提及占比 = 提及该主题的人数 / 有效样本数。',
      '价格接受度 = 各价格区间提及人数 / 明确给出价格回答的人数。',
    ] as string[],
    disclaimer: '',
  };
}

Page({
  data: {
    phase: 'loading' as 'loading' | 'ready' | 'error',
    evaluationId: '',
    error: '',
    vm: defaultVM(),
    deepAnalysis: null as DeepAnalysis | null,
    deepAnalysisExpanded: false,
    deepAnalysisLoading: false,
  },

  async onLoad(query: Record<string, string | undefined>) {
    const evalId = query.evaluation_id || '';
    this.setData({ evaluationId: evalId });
    if (!evalId) {
      this.setData({ phase: 'error', error: '无效的调研 ID' });
      return;
    }
    wx.showShareMenu({ withShareTicket: false, menus: ['shareAppMessage'] });
    const cached = readCachedReport(evalId);
    if (cached) {
      this.setData({ phase: 'ready', vm: this.buildVM(cached.report, cached.productName || '') });
      this.drawRadarChart();
      await this.loadReport(false);
      this.loadDeepAnalysis(evalId);
      return;
    }
    await this.loadReport(true);
    this.loadDeepAnalysis(evalId);
  },

  onShareAppMessage() {
    return {
      title: '查看测品调研报告',
      path: `/pages/report/report?evaluation_id=${this.data.evaluationId}`,
    };
  },

  async loadReport(showLoading = true) {
    const evalId = this.data.evaluationId;
    if (showLoading) {
      this.setData({ phase: 'loading', error: '' });
    } else {
      this.setData({ error: '' });
    }
    try {
      const [businessReport, evaluation, answers] = await Promise.all([
        api.getBusinessReportByEval(evalId),
        api.getEvaluation(evalId).catch(() => null),
        api.getEvaluationAnswers(evalId).catch(() => [] as any[]),
      ]);
      const tagMap = buildPersonaTagMap((answers as any[]) || []);
      let productName = '';
      if (evaluation?.product_id) {
        const product = await api.getProduct(evaluation.product_id).catch(() => null);
        productName = product?.name || '';
        api.generateWhitepaper({
          evaluation_id: evalId,
          product_name: shortProductName(product?.name || '') || '未命名产品',
          product_description: product?.description || undefined,
        }).catch(() => {});
      }
      writeCachedReport(evalId, { report: businessReport, productName });
      this.setData({ phase: 'ready', vm: this.buildVM(businessReport, productName, tagMap, (answers as any[]) || []) });
      this.drawRadarChart();
    } catch (err: any) {
      if (!showLoading) {
        return;
      }
      try {
        const [report, evaluation, baseAnswers] = await Promise.all([
          api.getReportByEval(evalId),
          api.getEvaluation(evalId).catch(() => null),
          api.getEvaluationAnswers(evalId).catch(() => [] as any[]),
        ]);
        const tagMap = buildPersonaTagMap((baseAnswers as any[]) || []);
        let productName = '';
        if (evaluation?.product_id) {
          const product = await api.getProduct(evaluation.product_id).catch(() => null);
          productName = product?.name || '';
        }
        this.setData({ phase: 'ready', vm: this.buildBaseVM(report, productName, tagMap, (baseAnswers as any[]) || []) });
        this.drawRadarChart();
      } catch {
        this.setData({
          phase: 'error',
          error: err?.message || '调研报告加载失败，请稍后重试',
        });
      }
    }
  },

  buildBaseVM(report: BackendReport, productName: string, tagMap: Record<string, string> = {}, answers: Array<{ persona_tag?: string; overall_intent?: number }> = []) {
    const avg = report.metrics?.overall_intent?.average || 0;

    // Build distribution map from array
    const distMap: Record<string, number> = {};
    for (const d of report.metrics?.overall_intent?.distribution || []) {
      distMap[String(d.score)] = d.count;
    }
    const { topBoxPct, top2BoxPct, bottom2BoxPct, total: top2BoxTotal } = calcBoxScores(distMap);

    const opportunities = (report.top_pros || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.quotes?.[0]?.quote ? `用户原声：${item.quotes[0].quote}` : '该优势在本轮调研中被消费者多次提及。',
      concise: compactProductPoint(item.title, '', item.quotes?.[0]?.quote || ''),
      count: item.support_count || 0,
    }));
    const risks = (report.top_cons || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.quotes?.[0]?.quote ? `用户原声：${item.quotes[0].quote}` : '该风险需要在卖点表达或后续验证中优先处理。',
      concise: compactProductPoint(item.title, '', item.quotes?.[0]?.quote || ''),
      count: item.support_count || 0,
    }));

    const dims = report.metrics?.dimensions_radar || [];
    const segs = report.metrics?.segment_intent || [];
    const priceArr = report.metrics?.price_sensitivity?.distribution || [];
    const priceChart = buildPriceBars(priceArr);

    const attributedQuotes = buildBaseAttributedQuotes(report.top_pros || [], report.top_cons || []);
    const top2BoxTotal2 = top2BoxTotal || segs.reduce((s, g) => s + g.count, 0) || 1;

    return {
      ...defaultVM(),
      productName: shortProductName(productName) || '本次测品',
      generatedAt: String(report.generated_at || '').slice(0, 10),
      verdictText: '',
      verdictClass: '',
      verdictReason: '',
      intent: `${avg.toFixed(1)}/5`,
      intentBarWidth: Math.round(Math.min(100, (avg / 5) * 100)),
      confidence: '已完成',
      topBoxPct,
      top2BoxPct,
      bottom2BoxPct,
      top2BoxTotal: top2BoxTotal2,
      signals: [],
      summary: nonEmpty(
        [report.summary],
        '本轮调研已完成，建议结合机会点、风险点和用户原声判断下一步动作。',
      ).slice(0, 3),
      stackedBar: buildStackedBar(distMap),
      personaCards: buildPersonaCards(segs, tagMap, answers),
      segmentRows: buildSegmentRows(segs, tagMap, answers),
      heatmapDimHeaders: buildHeatmapDimHeaders(dims),
      heatmapRows: buildHeatmapRows(segs, dims, avg, tagMap, answers),
      dimensionBars: buildDimensionBars(dims),
      ...buildCompositeScore(dims, avg),
      prosRanked: buildProsRanked(
        (report.top_pros || []).map(p => ({ title: p.title, support_count: p.support_count, evidence_quotes: p.quotes })),
        top2BoxTotal2,
      ),
      consRanked: buildConsRanked(
        (report.top_cons || []).map(c => ({ title: c.title, support_count: c.support_count })),
        top2BoxTotal2,
      ),
      themeBubbles: buildThemeBubbles(report.top_pros || [], report.top_cons || []),
      priceBars: priceChart.slices,
      pricePieStyle: priceChart.pieStyle,
      priceTotal: priceChart.total,
      benchmarkRows: [],
      priorityMatrix: buildPriorityMatrix(report.top_pros || [], report.top_cons || [], top2BoxTotal2),
      marketingAngles: [],
      audiences: nonEmpty(report.persona_segments?.most_positive || [], '购买意向较高群体待进一步验证').slice(0, 3).map(stripPersonaNames),
      leastLikelyAudiences: nonEmpty(report.persona_segments?.most_negative || [], '暂无').slice(0, 3).map(stripPersonaNames),
      channels: nonEmpty(report.persona_segments?.highest_value || [], '建议结合核心渠道继续验证').slice(0, 3).map(stripPersonaNames),
      attributedQuotes,
      quotes: [],
      evidenceChains: [],
      focusCards: [
        { label: '首要机会', title: opportunities[0]?.title || '机会点待识别', text: opportunities[0]?.note || '优先从高意向消费者反馈中找可放大的卖点。' },
        { label: '主要风险', title: risks[0]?.title || '风险点待识别', text: risks[0]?.note || '优先从低意向消费者反馈中找转化阻力。' },
        { label: '优先动作', title: '明确下一轮验证', text: '优先复核购买意向较低的问题，定位价格、功效或信任阻碍。' },
      ],
      opportunities,
      risks,
      conclusion: buildConclusion(
        buildPersonaCards(segs, tagMap, answers).map(c => c.name),
        opportunities,
        risks,
        top2BoxPct,
        buildCompositeScore(dims, avg).compositeGrade,
      ),
      nextSteps: (() => {
        const steps: string[] = [];
        if (risks[0]?.title) {
          steps.push(`针对「${cleanReportText(risks[0].title)}」，优先调整产品说明或补充使用证明`);
        }
        if (opportunities[0]?.title) {
          steps.push(`围绕「${cleanReportText(opportunities[0].title)}」，制作更多内容素材验证传播效果`);
        }
        if (risks[1]?.title) {
          steps.push(`跟进「${cleanReportText(risks[1].title)}」问题，在下轮复测中收集定向反馈`);
        }
        if (steps.length === 0) {
          steps.push('结合机会点和风险点，制定下一轮复测方向');
        }
        return steps;
      })(),
      sixDimBreakdown: buildSixDimBreakdown(dims, top2BoxPct, avg),
      disclaimer: report.ai_disclaimer || '报告由 AI 聚合调研回答生成，仅供决策参考。',
    };
  },

  buildVM(report: BusinessReport, productName: string, tagMap: Record<string, string> = {}, answers: Array<{ persona_tag?: string; overall_intent?: number }> = []) {
    const avg = report.metrics?.overall_intent_avg || 0;

    const distMap = report.metrics?.intent_distribution || {};
    const { topBoxPct, top2BoxPct, bottom2BoxPct, total: top2BoxTotal } = calcBoxScores(distMap);

    const dims = report.metrics?.dimension_scores || [];
    const segs = report.metrics?.persona_segments || [];
    const priceArr = report.metrics?.price_sensitivity || [];
    const priceChart = buildPriceBars(priceArr);
    const totalRespondents = top2BoxTotal || segs.reduce((s, g) => s + g.count, 0) || 1;

    const opportunities = (report.top_pros || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.business_implication,
      concise: compactProductPoint(item.title, item.business_implication || '', item.evidence_quotes?.[0]?.quote || ''),
      count: item.support_count || 0,
    }));
    const risks = (report.top_cons || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.improvement_suggestion,
      concise: compactProductPoint(item.title, item.improvement_suggestion || '', item.evidence_quotes?.[0]?.quote || ''),
      count: item.support_count || 0,
    }));

    const evidenceChains = (report.evidence_chains || []).slice(0, 6).map(chain => ({
      conclusion: chain.conclusion,
      roles: (chain.source_roles || []).map(r => resolveSegmentLabel(r, tagMap)).join('、'),
      action: chain.business_action,
      quote: chain.source_answers?.[0]?.quote || '',
    }));

    const dedupedOpportunities = uniqueCards(opportunities);
    const dedupedRisks = uniqueCards(risks);
    const nextSteps = uniqueText(
      report.next_test_recommendations || [],
      '继续验证价格、卖点和渠道表达。',
    ).slice(0, 4).map(cleanReportText).map(cleanNextStep);
    const firstAction = nextSteps[0] || '继续验证价格、卖点和渠道表达。';
    const focusCards = [
      { label: '首要机会', title: dedupedOpportunities[0]?.title || '机会点待识别', text: dedupedOpportunities[0]?.note || '优先从高意向消费者反馈中找可放大的卖点。' },
      { label: '主要风险', title: dedupedRisks[0]?.title || '风险点待识别', text: dedupedRisks[0]?.note || '优先从低意向消费者反馈中找转化阻力。' },
      { label: '优先动作', title: actionTitleFromRecommendation(firstAction), text: firstAction },
    ];
    const attributedQuotes = buildAttributedQuotes(report.top_pros || [], report.top_cons || []);

    return {
      ...defaultVM(),
      productName: shortProductName(productName) || '本次测品',
      generatedAt: String(report.generated_at || '').slice(0, 10),
      verdictText: '',
      verdictClass: '',
      verdictReason: cleanReportText(report.decision_suggestion?.reason || ''),
      intent: `${avg.toFixed(1)}/5`,
      intentBarWidth: Math.round(Math.min(100, (avg / 5) * 100)),
      confidence: `${Math.round((report.decision_suggestion?.confidence || 0) * 100)}%`,
      topBoxPct,
      top2BoxPct,
      bottom2BoxPct,
      top2BoxTotal: totalRespondents,
      signals: [],
      summary: nonEmpty(
        [
          report.decision_suggestion?.reason,
          ...(report.executive_summary || []).slice(0, 2),
        ],
        '本轮调研已完成，建议结合机会点、风险点和用户原声判断下一步动作。',
      ).slice(0, 3).map(cleanReportText),
      stackedBar: buildStackedBar(distMap),
      personaCards: buildPersonaCards(segs, tagMap, answers),
      segmentRows: buildSegmentRows(segs, tagMap, answers),
      heatmapDimHeaders: buildHeatmapDimHeaders(dims),
      heatmapRows: buildHeatmapRows(segs, dims, avg, tagMap, answers),
      dimensionBars: buildDimensionBars(dims),
      ...buildCompositeScore(dims, avg),
      prosRanked: buildProsRanked(report.top_pros || [], totalRespondents),
      consRanked: buildConsRanked(report.top_cons || [], totalRespondents),
      themeBubbles: buildThemeBubbles(report.top_pros || [], report.top_cons || []),
      priceBars: priceChart.slices,
      pricePieStyle: priceChart.pieStyle,
      priceTotal: priceChart.total,
      benchmarkRows: [],
      priorityMatrix: buildPriorityMatrix(report.top_pros || [], report.top_cons || [], totalRespondents),
      marketingAngles: buildMarketingAngles(report.marketing_copy_angles || []),
      audiences: nonEmpty(report.target_audience?.most_likely_to_buy || [], '购买意向较高群体待进一步验证').slice(0, 3).map(stripPersonaNames),
      leastLikelyAudiences: nonEmpty(report.target_audience?.least_likely_to_buy || [], '暂无').slice(0, 3).map(stripPersonaNames),
      channels: nonEmpty(report.target_audience?.channel_recommendation || [], '建议结合核心渠道继续验证').slice(0, 3).map(stripPersonaNames),
      attributedQuotes,
      quotes: [],
      evidenceChains,
      focusCards,
      opportunities: dedupedOpportunities,
      risks: dedupedRisks,
      conclusion: buildConclusion(
        buildPersonaCards(segs, tagMap, answers).map(c => c.name),
        dedupedOpportunities,
        dedupedRisks,
        top2BoxPct,
        buildCompositeScore(dims, avg).compositeGrade,
      ),
      nextSteps,
      sixDimBreakdown: buildSixDimBreakdown(dims, top2BoxPct, avg),
      disclaimer: report.ai_disclaimer || '报告由 AI 聚合调研回答生成，仅供决策参考。',
    };
  },

  drawRadarChart() {
    wx.nextTick(() => {
      const breakdown = this.data.vm.sixDimBreakdown;
      if (!breakdown || !breakdown.length) return;
      const ctx = wx.createCanvasContext('rp-radar', this);
      const SIZE = 280;
      const cx = SIZE / 2;   // 140
      const cy = SIZE / 2;   // 140
      const maxR = 90;       // outer ring radius
      const labelR = 118;    // label distance from center
      const n = 6;
      const values = breakdown.map((d: { score: number }) => d.score / 100);
      const labels = breakdown.map((d: { label: string }) => d.label);

      // textAlign per axis position (clockwise from top)
      const aligns: Array<'center' | 'left' | 'right'> = ['center', 'left', 'left', 'center', 'right', 'right'];
      // vertical nudge per position so text is visually centred on the axis tip
      const vNudge = [0, 4, 4, 14, 4, 4];

      // Grid rings
      for (let ring = 1; ring <= 3; ring++) {
        const rr = maxR * (ring / 3);
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const a = (Math.PI * 2 * i / n) - Math.PI / 2;
          const px = cx + rr * Math.cos(a);
          const py = cy + rr * Math.sin(a);
          if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.setStrokeStyle('rgba(180, 170, 210, 0.5)');
        ctx.setLineWidth(0.8);
        ctx.stroke();
      }

      // Axes
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i / n) - Math.PI / 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + maxR * Math.cos(a), cy + maxR * Math.sin(a));
        ctx.setStrokeStyle('rgba(180, 170, 210, 0.5)');
        ctx.setLineWidth(0.8);
        ctx.stroke();
      }

      // Data polygon
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i / n) - Math.PI / 2;
        const v = values[i] ?? 0;
        const px = cx + maxR * v * Math.cos(a);
        const py = cy + maxR * v * Math.sin(a);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.closePath();
      ctx.setFillStyle('rgba(220, 56, 100, 0.18)');
      ctx.fill();
      ctx.setStrokeStyle('#DC3864');
      ctx.setLineWidth(1.5);
      ctx.stroke();

      // Dots
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i / n) - Math.PI / 2;
        const v = values[i] ?? 0;
        const px = cx + maxR * v * Math.cos(a);
        const py = cy + maxR * v * Math.sin(a);
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.setFillStyle('#DC3864');
        ctx.fill();
        // White inner dot for ring effect
        ctx.beginPath();
        ctx.arc(px, py, 2, 0, Math.PI * 2);
        ctx.setFillStyle('#FFFFFF');
        ctx.fill();
      }

      // Axis labels
      ctx.setFontSize(14);
      ctx.setFillStyle('#1A1A2E');
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i / n) - Math.PI / 2;
        const lx = cx + labelR * Math.cos(a);
        const ly = cy + labelR * Math.sin(a) + vNudge[i];
        ctx.setTextAlign(aligns[i]);
        ctx.fillText(labels[i], lx, ly);
      }

      ctx.draw();
    });
  },

  onTapRadarCanvas(e: WechatMiniprogram.TouchEvent) {
    const breakdown = this.data.vm.sixDimBreakdown;
    if (!breakdown?.length) return;
    wx.createSelectorQuery().in(this)
      .select('#rp-radar')
      .boundingClientRect((rect: WechatMiniprogram.BoundingClientRectCallbackResult) => {
        if (!rect) return;
        const touch = e.changedTouches?.[0];
        if (!touch) return;
        const tapX = touch.clientX - rect.left;
        const tapY = touch.clientY - rect.top;
        const cx = 140;
        const cy = 140;
        const maxR = 90;
        const n = 6;

        // Find nearest dot
        let nearest = -1;
        let minDist = 28; // tap radius threshold (CSS px)
        for (let i = 0; i < n; i++) {
          const a = (Math.PI * 2 * i / n) - Math.PI / 2;
          const v = (breakdown[i].score ?? 0) / 100;
          const px = cx + maxR * v * Math.cos(a);
          const py = cy + maxR * v * Math.sin(a);
          const dist = Math.sqrt((tapX - px) ** 2 + (tapY - py) ** 2);
          if (dist < minDist) { minDist = dist; nearest = i; }
        }

        if (nearest >= 0) {
          const d = breakdown[nearest];
          wx.showToast({
            title: `${d.label}：${d.score}分\n权重 ${d.weight}%  贡献 ${d.contribution}`,
            icon: 'none',
            duration: 2500,
          });
        }
      })
      .exec();
  },

  async loadDeepAnalysis(evalId: string) {
    const cacheKey = `deep_analysis_cache_${evalId}`;

    try {
      const cached = wx.getStorageSync(cacheKey);
      if (cached) {
        const parsed = typeof cached === 'string' ? JSON.parse(cached) : cached;
        if (parsed?.sections?.length) {
          this.setData({ deepAnalysis: parsed });
        }
      }
    } catch { /* ignore */ }

    try {
      const result = await api.getDeepAnalysis(evalId);
      if (result?.sections?.length) {
        this.setData({ deepAnalysis: result });
        try { wx.setStorageSync(cacheKey, JSON.stringify(result)); } catch { /* ignore */ }
        return;
      }
    } catch { /* ignore */ }

    if (!this.data.deepAnalysis) {
      const sections = buildDeepSectionsFromVM(this.data.vm);
      this.setData({
        deepAnalysis: { sections, generated_at: new Date().toISOString() },
      });
    }
  },

  onTapBar(e: any) {
    const { type, idx } = e.currentTarget.dataset;
    const items = type === 'pro' ? this.data.vm.prosRanked : this.data.vm.consRanked;
    const item = items[idx];
    if (!item) return;
    const typeLabel = type === 'pro' ? '卖点' : '顾虑';
    const total = this.data.vm.top2BoxTotal;
    wx.showModal({
      title: item.title,
      content: `${item.count} 位受访者在开放题中明确提及此${typeLabel}（有效受访者共 ${total} 位）。\n\n统计口径：逐条归纳每位受访者的答案，同一受访者仅计一次，数据直接来自本轮调研原始回答。`,
      showCancel: false,
      confirmText: '知道了',
    });
  },

  onTapDeepToggle() {
    this.setData({ deepAnalysisExpanded: !this.data.deepAnalysisExpanded });
  },

  onTapRetry() {
    this.loadReport();
  },

  onTapFollowUp() {
    wx.navigateTo({
      url: `/pages/chat/chat?evaluation_id=${this.data.evaluationId}&auto=0`,
    });
  },

  onTapExport() {
    const evalId = this.data.evaluationId;
    if (!evalId) {
      wx.showToast({ title: '缺少调研 ID', icon: 'none' });
      return;
    }
    wx.showActionSheet({
      itemList: ['调研报告导出', '白皮书导出'],
      success: (res) => {
        const token = getToken() || '';
        const version = `${Date.now()}`;
        const base = `${whitepaperBase()}${WHITEPAPER_VIEWER_PATH}`
          + `?evaluation_id=${encodeURIComponent(evalId)}`
          + `&token=${encodeURIComponent(token)}`
          + `&api_base=${encodeURIComponent(whitepaperBase())}`
          + `&v=${encodeURIComponent(version)}`;

        if (res.tapIndex === 0) {
          // 调研报告导出：静默触发后端更新，直接跳转
          api.generateWhitepaper({
            evaluation_id: evalId,
            product_name: this.data.vm.productName,
          }).catch(() => {/* ignore */});
          wx.navigateTo({ url: `/pages/webview/webview?url=${encodeURIComponent(base)}` });
        } else {
          // 白皮书导出：使用本地白皮书查看器，mode=whitepaper
          const wpUrl = base + `&mode=${encodeURIComponent('whitepaper')}`;
          wx.navigateTo({ url: `/pages/webview/webview?url=${encodeURIComponent(wpUrl)}` });
        }
      },
    });
  },
});
