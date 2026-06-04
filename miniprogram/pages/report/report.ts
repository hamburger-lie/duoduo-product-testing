import { api } from '../../services/api';
import { BASE_URL, getToken } from '../../services/http';
import type { BackendReport, BusinessReport, DeepAnalysis, DeepAnalysisSection } from '../../types/api';

const WHITEPAPER_VIEWER_PATH = '/whitepaper-static/index.html';
const REPORT_CACHE_PREFIX = 'business_report_cache_';
const REQUIRED_RAW_DIMS = [
  'first_impression',
  'purchase_motivation',
  'price_sensitivity',
  'package_appearance',
  'competitor_comparison',
  'usage_scenario',
  'repurchase_intent',
  'nps_recommendation',
  'channel_touchpoint',
  'painpoint_improvement',
];

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
  differentiation: '差异化',
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
    if (!parsed?.report) return null;
    if (!hasCompleteRawRadarDims(parsed.report)) {
      if (DEBUG_RADAR) console.log('[radar-real] discard stale report cache:', {
        evaluationId: evalId,
        extractedDims: extractRadarDims(parsed.report).map(d => d.dim),
      });
      wx.removeStorageSync(reportCacheKey(evalId));
      return null;
    }
    return parsed as CachedReportSnapshot;
  } catch {
    return null;
  }
}

function writeCachedReport(evalId: string, snapshot: CachedReportSnapshot): void {
  try {
    if (!hasCompleteRawRadarDims(snapshot.report)) {
      if (DEBUG_RADAR) console.log('[radar-real] skip sparse report cache:', {
        evaluationId: evalId,
        extractedDims: extractRadarDims(snapshot.report).map(d => d.dim),
      });
      wx.removeStorageSync(reportCacheKey(evalId));
      return;
    }
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

/**
 * 六维商业判断框架 — 对齐后端真实问卷 10 个维度。
 *
 * 分数方向说明（来自 seed 模板 beauty_survey_template.json）：
 *   price_sensitivity  → 实际题目：「性价比如何」，高分 = 性价比好 = 正向，无需反向。
 *   painpoint_improvement → 实际题目：「综合购买意愿」，高分 = 意愿强 = 正向，无需反向。
 *   competitor_comparison / channel_touchpoint → 无 scale_1_5 题，由 LLM 分析时才有数据。
 */
/**
 * ══════════════════════════════════════════════════════════════════
 * 六维商业诊断雷达图配置
 * ══════════════════════════════════════════════════════════════════
 *
 * 六维雷达图 ≠ 问卷原始维度。它是由 10 个问卷采集维度归并成的 6 个商业判断维度。
 *
 *   问卷 10 维（原始采集层）          六维雷达图（商业判断层）
 *   ──────────────────────────────    ──────────────────────
 *   first_impression   q01–q03  ──┐
 *   purchase_motivation q04–q06  ──┘→ ① 购买意愿
 *   package_appearance  q10–q12  ──┐
 *   usage_scenario      q16–q18  ──┘→ ② 产品感知
 *   price_sensitivity   q07–q09  ────→ ③ 价格接受度  ⚠ 见下方方向说明
 *   competitor_comparison q13–q15 ────→ ④ 竞争力
 *   repurchase_intent   q19–q21  ──┐
 *   nps_recommendation  q22–q24  ──┘→ ⑤ 口碑潜力
 *   painpoint_improvement q28–q30 ──┐
 *   channel_touchpoint   q25–q27  ──┘→ ⑥ 痛点解决
 *
 * 数据来源：
 *   后端 _resolve_dimensions_radar 优先使用 LLM 文本分析分数（dimension_analysis），
 *   LLM 分析覆盖所有题型（open / single / multi / scale_1_5），不仅限于 scale 题。
 *   当 LLM 分析未就绪时，回退到 scale_1_5 题的规则均值（仅 ≤4 道题），
 *   此时雷达图数据覆盖不完整——没有 scale 题的维度将显示为无数据。
 *
 * ⚠ 价格接受度方向说明：
 *   后端原始字段是 price_sensitivity，由 LLM 基于 PSM 三问（q07–q09）评分。
 *   当前 LLM prompt 让 AI "为每个维度打分"，高分含义取决于 LLM 对题目的理解。
 *   根据问卷设计，q07–q09 实际问的是"性价比如何"，高分 = 性价比好 = 正向。
 *   因此当前直接使用 LLM 分数，不做反向处理。
 *   如果后续发现 LLM 将高分解读为"越敏感"，需在此处或后端做 100 - score 反向。
 */
const SIX_DIM_CONFIG = [
  {
    label: '购买意愿',
    sourceKeys: ['first_impression', 'purchase_motivation'],
    sourceText: '来自第一印象、购买动机',
    explainText: '判断用户是否有兴趣继续了解并形成购买理由。',
    actionText: '若偏低，优先强化首屏卖点和购买动机。',
    bubbleDesc: '用户是否愿意了解并形成购买理由。',
    bubbleAction: '建议：强化首屏卖点和购买动机。',
  },
  {
    label: '产品感知',
    sourceKeys: ['package_appearance', 'usage_scenario'],
    sourceText: '来自包装外观、使用场景',
    explainText: '判断用户是否理解产品，并能代入真实使用场景。',
    actionText: '若偏低，优化包装识别和场景表达。',
    bubbleDesc: '用户是否理解产品并代入使用场景。',
    bubbleAction: '建议：优化包装识别和场景表达。',
  },
  {
    label: '竞争力',
    sourceKeys: ['competitor_comparison'],
    sourceText: '来自竞品对比',
    explainText: '判断产品相比同类是否有清晰优势。',
    actionText: '若偏低，补强差异化卖点和对比理由。',
    bubbleDesc: '产品相比同类是否有清晰优势。',
    bubbleAction: '建议：补强差异化卖点和对比理由。',
  },
  {
    label: '口碑潜力',
    sourceKeys: ['nps_recommendation', 'repurchase_intent'],
    sourceText: '来自复购意向、推荐意愿',
    explainText: '判断用户是否愿意复购或推荐给别人。',
    actionText: '若偏低，强化使用后确定性和分享理由。',
    bubbleDesc: '用户是否愿意复购或推荐给他人。',
    bubbleAction: '建议：强化确定感和分享理由。',
  },
  {
    label: '价格接受度',
    sourceKeys: ['price_sensitivity'],
    sourceText: '来自 PSM 价格三问',
    explainText: '判断当前价格是否会成为下单阻力。',
    actionText: '若偏低，补充价格锚点、试用装或组合装。',
    bubbleDesc: '当前价格是否落在可接受范围内。',
    bubbleAction: '建议：补充价格锚点或试用装。',
  },
  {
    label: '痛点解决',
    sourceKeys: ['painpoint_improvement', 'channel_touchpoint'],
    sourceText: '来自痛点改善、渠道触达',
    explainText: '判断产品是否解决真实顾虑，购买路径是否顺畅。',
    actionText: '若偏低，优化核心痛点表达和购买路径。',
    bubbleDesc: '是否解决真实顾虑，购买路径是否顺畅。',
    bubbleAction: '建议：优化痛点表达和购买路径。',
  },
] as const;

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

/**
 * 将后端 score 归一化到 0-100 整数。
 * 兼容三种单位：[0,1] → ×100；(1,5] → /5×100；(5,100] → 直接取整。
 */
function normalizeRadarScore(raw: number): number {
  if (!isFinite(raw) || raw < 0) return 0;
  if (raw <= 1)   return Math.round(raw * 100);
  if (raw <= 5)   return Math.round((raw / 5) * 100);
  return Math.round(Math.min(raw, 100));
}

/** 简短截断 JSON，避免控制台爆炸 */
function _short(v: unknown, maxLen = 600): string {
  try { const s = JSON.stringify(v); return s.length > maxLen ? s.slice(0, maxLen) + '…' : s; }
  catch { return String(v).slice(0, maxLen); }
}

// 调试开关：正式版保持 false，本地调试时可临时改为 true
const DEBUG_RADAR = false;

/** @deprecated 旧递归扫描，仅保留供调试，不在主逻辑中调用 */
function debugRadarPaths(obj: any, path = 'report', depth = 0): void {
  if (!DEBUG_RADAR) return;
  if (!obj || typeof obj !== 'object' || depth > 3) return;
  if (depth === 0) console.log('[radar-debug] report root keys:', Object.keys(obj));
  const HINTS = ['dim', 'dimension', 'radar', 'score'];
  for (const k of Object.keys(obj)) {
    const kLow = k.toLowerCase();
    if (!HINTS.some(h => kLow.includes(h))) continue;
    const val = obj[k];
    if (val == null) continue;
    console.log(`[radar-debug] path="${path}.${k}" val=${_short(val, 300)}`);
    if (val && typeof val === 'object' && depth < 3) debugRadarPaths(val, `${path}.${k}`, depth + 1);
  }
}

/**
 * 从完整 report 对象中提取雷达图维度数据，兼容多种字段名和数据格式。
 * 先搜 metrics 下，再搜 report 根层，都找不到返回空数组。
 * 不补默认值，不伪造维度分数。
 */
type RadarDim = { dim: string; score: number | null };

function extractRadarDims(report: any): RadarDim[] {
  if (!report) return [];
  const metrics = report.metrics ?? report;

  // 候选来源：先 metrics 下，再 report 根
  const candidates: Array<[string, any]> = [
    ['metrics.dimensions_radar',  metrics?.dimensions_radar],
    ['metrics.dimension_scores',  metrics?.dimension_scores],
    ['metrics.dimensionsRadar',   metrics?.dimensionsRadar],
    ['metrics.dimensionScores',   metrics?.dimensionScores],
    ['metrics.radar_dimensions',  metrics?.radar_dimensions],
    ['metrics.radar',             metrics?.radar],
    ['root.dimensions_radar',     report?.dimensions_radar],
    ['root.dimension_scores',     report?.dimension_scores],
    ['root.radar',                report?.radar],
  ];

  let firstParsed: RadarDim[] = [];
  for (const [label, raw] of candidates) {
    if (!raw) continue;
    if (DEBUG_RADAR) console.log(`[radar] trying ${label}:`, _short(raw, 300));

    if (Array.isArray(raw) && raw.length > 0) {
      const parsed = (raw as any[]).map((item: any) => {
        const dimKey   = item.dim   ?? item.name  ?? item.label ?? item.key ?? '';
        const scoreVal = item.score ?? item.value ?? item.avg   ?? null;
        if (!dimKey) return null;
        if (scoreVal == null) return { dim: String(dimKey), score: null };
        if (!isFinite(Number(scoreVal))) return null;
        return { dim: String(dimKey), score: Number(scoreVal) };
      }).filter(Boolean) as RadarDim[];
      if (parsed.length > 0) {
        if (DEBUG_RADAR) console.log(`[radar-real] extracted dims from ${label}:`, parsed);
        if (hasAllRequiredRawDims(parsed)) return parsed;
        if (firstParsed.length === 0) firstParsed = parsed;
      }
    }

    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      const parsed = Object.entries(raw as Record<string, unknown>)
        .filter(([, v]) => v == null || (typeof v === 'number' && isFinite(v as number)))
        .map(([k, v]) => ({ dim: k, score: v == null ? null : v as number }));
      if (parsed.length > 0) {
        if (DEBUG_RADAR) console.log(`[radar-real] extracted dims from ${label} (obj):`, parsed);
        if (hasAllRequiredRawDims(parsed)) return parsed;
        if (firstParsed.length === 0) firstParsed = parsed;
      }
    }
  }

  if (firstParsed.length > 0) return firstParsed;
  if (DEBUG_RADAR) console.log('[radar] ✗ no valid radar field found → []');
  return [];
}

function hasAllRequiredRawDims(dims: RadarDim[]): boolean {
  const present = new Set(
    dims
      .filter(d => d.score !== null)
      .map(d => d.dim.toLowerCase().replace(/[-\s]/g, '_')),
  );
  return REQUIRED_RAW_DIMS.every(dim => present.has(dim));
}

function hasCompleteRawRadarDims(report: any): boolean {
  return hasAllRequiredRawDims(extractRadarDims(report));
}

/**
 * 将后端 10 个问卷维度映射到 6 个商业判断维度，构建雷达图数据。
 *
 * 分数可信度原则：
 *   - 只使用 extractRadarDims 返回的真实问卷维度数据
 *   - 某维度 sourceKeys 全部无匹配 → hasRealData=false, score=null
 *   - 不使用 avgIntent / top2BoxPct 填充任何维度（已删除 isTop2 逻辑）
 */
function buildSixDimBreakdown(
  dims: RadarDim[],
  _top2BoxPct: number,   // 已不再使用：新六维不依赖 Top-2 Box 补齐任何维度
  _avgIntent: number,
): Array<{ label: string; weight: number; score: number | null; contribution: number; hasRealData: boolean; sourceText: string; explainText: string; actionText: string; bubbleDesc: string; bubbleAction: string }> {
  if (!dims || dims.length === 0) return [];

  // 构建 key → scores 映射（normalizeRadarScore 兼容 0-1/0-5/0-100）
  const keyScores: Record<string, number[]> = {};
  for (const d of dims) {
    if (d.score === null) continue;
    const k = d.dim.toLowerCase().replace(/[-\s]/g, '_');
    if (!keyScores[k]) keyScores[k] = [];
    keyScores[k].push(normalizeRadarScore(d.score));
  }

  if (DEBUG_RADAR) {
    console.log('[radar] raw dims:', JSON.stringify(dims));
    console.log('[radar] keyScores:', JSON.stringify(keyScores));
  }

  const result = SIX_DIM_CONFIG.map(cfg => {
    const foundScores: number[] = [];
    const matchedKeys: string[] = [];
    for (const srcKey of cfg.sourceKeys) {
      const k = srcKey.toLowerCase().replace(/[-\s]/g, '_');
      if (keyScores[k]) {
        foundScores.push(...keyScores[k]);
        matchedKeys.push(k);
      }
    }

    const hasRealData = foundScores.length > 0;
    const score = hasRealData
      ? Math.round(foundScores.reduce((a, b) => a + b, 0) / foundScores.length)
      : null;
    const contribution = hasRealData && score !== null
      ? parseFloat(((100 / SIX_DIM_CONFIG.length / 100) * score).toFixed(1))
      : 0;

    if (DEBUG_RADAR) {
      console.log('[radar-real] dimension mapping:', {
        label: cfg.label,
        sourceKeys: cfg.sourceKeys,
        matchedKeys,
        matchedScores: foundScores,
        score,
        hasRealData,
      });
    }

    return {
      label: cfg.label,
      weight: Math.round(100 / SIX_DIM_CONFIG.length),
      score,
      contribution,
      hasRealData,
      sourceText: cfg.sourceText,
      explainText: cfg.explainText,
      actionText: cfg.actionText,
      bubbleDesc: cfg.bubbleDesc,
      bubbleAction: cfg.bubbleAction,
    };
  });

  if (DEBUG_RADAR) {
    const realCount = result.filter(d => d.hasRealData).length;
    console.log('[radar-real] sixDimBreakdown:', result.map(d => ({
      label: d.label,
      score: d.score,
      hasRealData: d.hasRealData,
    })));
    console.log('[radar] radarRealCount:', realCount);
  }

  return result;
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
  void audiences;
  void opportunities;
  void top2BoxPct;
  const risk = joinTopSignals(cons, '信任证据');
  if (compositeGrade === 'S' || compositeGrade === 'A') return { text: `购买兴趣成立，但${risk}仍需补强。` };
  if (compositeGrade === 'B') return { text: `购买兴趣成立，但${risk}仍需补强。` };
  return { text: '购买兴趣偏弱，需重构卖点。' };
}

function buildHeroAdvice(compositeGrade: string): string {
  if (compositeGrade === 'S' || compositeGrade === 'A') return '建议：先小规模验证';
  if (compositeGrade === 'B') return '建议：补强证据后复测';
  return '建议：重构卖点再验证';
}

function buildPersonaCards(
  segments: Array<{ segment: string; count: number; avg_intent: number }>,
  tagMap: Record<string, string> = {},
  answers: Array<{ persona_id?: string; persona_name?: string; persona_tag?: string; overall_intent?: number }> = [],
): Array<{ name: string; score: number; tag: string; tone: string }> {
  const tones = ['green', 'violet', 'amber', 'blue', 'slate'];
  const sortedAnswers = [...answers].sort((a, b) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));
  const answerSegments = sortedAnswers
    .filter(a => (a.persona_tag || a.persona_name || a.persona_id) && typeof a.overall_intent === 'number')
    .map(a => ({
      segment: a.persona_tag || a.persona_name || a.persona_id || '',
      count: 1,
      avg_intent: (a.overall_intent || 0) > 5 ? (a.overall_intent || 0) / 2 : (a.overall_intent || 0),
    }));
  const source = answerSegments.length > segments.length ? answerSegments : segments;
  const sorted = [...source].sort((a, b) => b.avg_intent - a.avg_intent);
  const all = sorted.map((s, i) => {
    const score = Math.round(Math.min(100, (s.avg_intent / 5) * 100));
    const tag = score >= 90 ? '强推荐' : score >= 75 ? '推荐' : score >= 65 ? '可推' : score >= 55 ? '观望' : '谨慎';
    return { name: pickSegmentLabel(s.segment, i, tagMap, sortedAnswers), score, tag, tone: tones[i] || 'slate' };
  });
  return all.slice(0, 6);
}

function shortSignalTitle(text: string, fallback: string): string {
  // extractShortTitle 先提取关键名词（如"品牌背书"而非"品牌背书是主要正向信号"）
  const extracted = extractShortTitle(String(text || ''));
  const cleaned = cleanReportText(stripPersonaNames(extracted || text || '')).replace(/[。；;，,].*$/g, '').trim();
  const chars = Array.from(cleaned || fallback);
  return chars.slice(0, 5).join(''); // 每个关键词最多 5 个字
}

function joinTopSignals(items: Array<{ title?: string; shortTitle?: string }>, fallback: string): string {
  const signals = items
    .map(item => shortSignalTitle(item.shortTitle || item.title || '', ''))
    .filter(Boolean)
    .slice(0, 2);
  return signals.length ? signals.join('、') : fallback; // 用顿号而非"与"
}

function compactSignalAction(title: string, positive: boolean): string {
  const value = cleanReportText(title || '');
  if (value.includes('品牌') || value.includes('背书') || value.includes('信任')) return positive ? '放大品牌信任' : '补强品牌信任';
  if (value.includes('温和') || value.includes('修护')) return positive ? '强化温和修护' : '补强温和证明';
  if (value.includes('价格') || value.includes('性价比') || value.includes('贵')) return positive ? '验证价格优势' : '降低价格门槛';
  if (value.includes('成分') || value.includes('安全')) return positive ? '突出成分安全' : '补强成分安全';
  if (value.includes('功效') || value.includes('效果')) return positive ? '放大功效证据' : '补充功效证据';
  if (value.includes('包装') || value.includes('颜值')) return positive ? '强化包装记忆' : '优化包装表达';
  return positive ? '放大核心卖点' : '补强决策证据';
}

function firstOpenAnswerText(answerItems: unknown): string {
  if (!Array.isArray(answerItems)) return '';
  const open = answerItems.find((item: any) => {
    const value = item?.answer;
    return item?.type === 'open' && typeof value === 'string' && value.trim();
  }) as any;
  return String(open?.answer || '').trim();
}

/** 从长句中提取关键词短语，精简到一句话 */
function compactVoiceText(text: string, max = 12): string {
  const value = cleanReportText(String(text || '').replace(/\s+/g, ' ').trim());
  if (!value) return '';
  // 按句号等拆分，取第一个语义片段
  const clauses = value.split(/[。；;！!？?\n]/).map(s => s.trim()).filter(Boolean);
  let phrase = clauses[0] || value;
  // 去掉引导词，提取核心
  phrase = phrase
    .replace(/^(?:被|对|因为|由于|主要是|觉得|认为|希望|感觉|看重|关注)\s*/g, '')
    .replace(/(?:所以|因此|但是|不过|然而).*$/g, '')
    .trim();
  // 按逗号/顿号再拆，取最有信息量的短关键词
  const subParts = phrase.split(/[，,、]/).map(s => s.trim()).filter(s => s.length >= 2);
  if (subParts.length > 1) {
    const best = subParts.find(s => Array.from(s).length >= 4 && Array.from(s).length <= 8) || subParts[0];
    phrase = best;
  }
  const chars = Array.from(phrase);
  if (chars.length <= max) return phrase;
  return chars.slice(0, max).join('');
}

function compactGroupTitle(text: string, fallback: string): string {
  const value = stripPersonaNames(normalizeSegmentLabel(text || '')).trim();
  if (!value || value === '消费者' || value === '消费群体') return fallback;
  if (value.includes('学生') || value.includes('小红书')) return '学生党';
  if (value.includes('家庭')) return '家庭用户';
  if (value.includes('男士') || value.includes('男性')) return '男士新手';
  if (value.includes('成分') || value.includes('理性')) return '成分党';
  if (value.includes('彩妆') || value.includes('尝鲜')) return '彩妆尝鲜';
  if (value.includes('价格') || value.includes('预算') || value.includes('性价比')) return '预算用户';
  const labels = value
    .split(/[/／｜|、，,·×\s\-_—]+/)
    .map(label => label.trim())
    .filter(Boolean);
  const title = (labels.length ? labels[0] : value).trim();
  return Array.from(title).slice(0, 6).join('');
}

function personaAttractionText(score: number, opportunities: Array<{ title?: string; shortTitle?: string }>): string {
  if (opportunities[0]?.title || opportunities[0]?.shortTitle) return joinTopSignals(opportunities.slice(0, 1), '核心卖点');
  return score >= 4 ? '整体兴趣较强' : '有初步兴趣';
}

function personaHesitationText(score: number, risks: Array<{ title?: string; shortTitle?: string }>): string {
  if (risks[0]?.title || risks[0]?.shortTitle) return joinTopSignals(risks.slice(0, 1), '决策证据');
  return score >= 4 ? '仍需更多证据' : '购买理由不足';
}

function splitPersonaQuote(
  quote: string,
  score: number,
  opportunities: Array<{ title?: string; shortTitle?: string }>,
  risks: Array<{ title?: string; shortTitle?: string }>,
): { attractedBy: string; hesitation: string } {
  const cleaned = cleanReportText(quote || '').trim();
  if (!cleaned) {
    return {
      attractedBy: personaAttractionText(score, opportunities),
      hesitation: personaHesitationText(score, risks),
    };
  }
  const parts = cleaned.split(/[。；;，,]/).map(p => p.trim()).filter(Boolean);
  return {
    attractedBy: compactVoiceText(parts[0] || personaAttractionText(score, opportunities)),
    hesitation: compactVoiceText(parts[1] || personaHesitationText(score, risks)),
  };
}

/**
 * 生成角色总结性发言：
 * 优先使用 summary_comment / 开放题原声（rawQuote），
 * 无真实内容时按评分+吸引点+犹豫点组合第一人称短句。
 */
function buildPersonaStatement(
  rawQuote: string,
  score: number,
  attractedBy: string,
  hesitation: string,
): string {
  const FALLBACK_TEXTS = ['核心卖点', '整体兴趣较强', '有初步兴趣', '决策证据', '仍需更多证据', '购买理由不足'];
  const cleaned = cleanReportText(String(rawQuote || '').replace(/\s+/g, ' ').trim());
  // 真实原声 ≥ 8 字时直接使用（弹窗完整展示，不截断）
  if (cleaned && Array.from(cleaned).length >= 8) {
    return cleaned;
  }
  const hasA = attractedBy && !FALLBACK_TEXTS.includes(attractedBy);
  const hasH = hesitation && !FALLBACK_TEXTS.includes(hesitation);
  if (score >= 4.5) {
    if (hasA && hasH) return `愿意优先尝试，${attractedBy}很打动我，还会关注${hesitation}。`;
    if (hasA) return `很感兴趣，${attractedBy}是主要吸引点。`;
    return '整体印象不错，有较强购买意愿。';
  }
  if (score >= 3.5) {
    if (hasA && hasH) return `有购买兴趣，${attractedBy}加分，但${hesitation}会影响下单。`;
    if (hasH) return `有初步兴趣，还想弄清楚${hesitation}再决定。`;
    return '有一定兴趣，需要再考虑一下。';
  }
  if (score >= 3) {
    if (hasH) return `先观望，${hesitation}是主要顾虑。`;
    return '目前还在观望，不会马上购买。';
  }
  return '目前购买意愿较低，还需要更多理由。';
}

/** 从吸引点/犹豫点提取 1-2 个关注点标签 */
function buildPersonaTags(attractedBy: string, hesitation: string): string[] {
  const NOISE = ['核心卖点', '整体兴趣较强', '有初步兴趣', '决策证据', '仍需更多证据', '购买理由不足'];
  const tags: string[] = [];
  if (attractedBy && !NOISE.includes(attractedBy)) tags.push(Array.from(attractedBy).slice(0, 5).join(''));
  if (hesitation  && !NOISE.includes(hesitation))  tags.push(Array.from(hesitation).slice(0, 5).join(''));
  return [...new Set(tags)].slice(0, 2);
}

function buildPersonaVoices(
  answers: Array<{
    persona_id?: string;
    persona_name?: string;
    persona_tag?: string;
    overall_intent?: number;
    summary_comment?: string;
    answers?: unknown;
  }> = [],
  opportunities: Array<{ title?: string; shortTitle?: string }> = [],
  risks: Array<{ title?: string; shortTitle?: string }> = [],
): Array<{ groupTitle: string; score: string; statement: string; tags: string[]; attractedBy: string; hesitation: string; tone: string; avatar: string }> {
  const tones = ['violet', 'green', 'amber', 'blue', 'slate'];
  return [...answers]
    .filter(item => item.persona_name || item.persona_tag || item.summary_comment)
    .sort((a, b) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0))
    .slice(0, 5)
    .map((item, index) => {
      const rawScore = item.overall_intent ?? 0;
      const score = rawScore > 5 ? rawScore / 2 : rawScore;
      const quote = item.summary_comment || firstOpenAnswerText(item.answers);
      const split = splitPersonaQuote(quote || '', score, opportunities, risks);
      const statement = buildPersonaStatement(quote || '', score, split.attractedBy, split.hesitation);
      const tags = buildPersonaTags(split.attractedBy, split.hesitation);
      return {
        groupTitle: compactGroupTitle(item.persona_tag || item.persona_name || '', `群体${ORDINAL_ZH[index] ?? index + 1}`),
        score: score ? `${score.toFixed(1)}/5` : '未评分',
        statement,
        tags,
        attractedBy: split.attractedBy,
        hesitation: split.hesitation,
        tone: tones[index] || 'slate',
        avatar: `/assets/persona-avatars/avatar-${String((index % 10) + 1).padStart(2, '0')}.png`,
      };
    });
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
 *   highlight —— 章节重点，前端只取一句放在正文前
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
    { title: '一、卖点共鸣与群体锁定', highlight: h1Lines.join('\n'), content: s1.join('\n\n') },
    { title: '二、失效信号与阻力区间', highlight: h2Lines.join('\n'), content: s2.join('\n\n') },
    { title: '三、市场建议', highlight: h3Lines.join('\n'), content: s3.join('\n\n') },
  ];
}

type DeepAnalysisViewSection = DeepAnalysisSection & {
  highlightText: string;
  contentParagraphs: string[];
};
type DeepAnalysisView = DeepAnalysis & { sections: DeepAnalysisViewSection[] };

function splitDeepSentences(text: string): string[] {
  return (cleanReportText(text).replace(/\s+/g, ' ').match(/[^。！？；]+[。！？；]?/g) || [])
    .map(item => item.trim())
    .filter(Boolean);
}

function splitDeepParagraphs(content: string): string[] {
  const explicit = String(content || '')
    .split(/\n{2,}/)
    .map(item => cleanReportText(item))
    .filter(Boolean);
  if (explicit.length > 1) return explicit;

  const sentences = splitDeepSentences(content);
  if (sentences.length > 1) return sentences;

  return explicit.length ? explicit : [cleanReportText(content || '暂无更多正文分析。')];
}

function pickDeepSentence(sentences: string[], patterns: RegExp[], fallbackIndex: number): string {
  const matched = sentences.find(sentence => patterns.some(pattern => pattern.test(sentence)));
  return matched || sentences[Math.min(fallbackIndex, Math.max(sentences.length - 1, 0))] || '暂无明确结论。';
}

function trimDeepHighlight(text: string): string {
  const sentences = splitDeepSentences(text);
  return (sentences[0] || cleanReportText(text)).slice(0, 96);
}

function buildDeepHighlightText(section: DeepAnalysisSection): string {
  const highlightLines = String(section.highlight || '')
    .split(/\n+/)
    .map(item => cleanReportText(item))
    .filter(Boolean);
  const paragraphs = splitDeepParagraphs(section.content);
  const sentences = paragraphs.flatMap(splitDeepSentences);

  const core = highlightLines[0] || pickDeepSentence(sentences, [/表明|形成|集中|明确|最高|最强|成立|核心|共鸣|建议|优先/], 0);
  const risk = pickDeepSentence(
    sentences,
    [/风险|顾虑|阻力|犹豫|不足|薄弱|缺口|拦截|失效|敏感|依赖|无法|未能|须优先/],
    Math.min(1, Math.max(sentences.length - 1, 0)),
  );

  if (core === risk || risk === '暂无明确结论。') return trimDeepHighlight(core);
  return trimDeepHighlight(`${core.replace(/[。！？；]$/, '')}，但${risk.replace(/^[但，。；\s]+/, '')}`);
}

function normalizeDeepAnalysis(raw: DeepAnalysis): DeepAnalysisView {
  return {
    ...raw,
    sections: (raw.sections || []).map(section => ({
      ...section,
      highlightText: buildDeepHighlightText(section),
      contentParagraphs: splitDeepParagraphs(section.content),
    })),
  };
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
    heroAdviceText: '',
    topOpportunityText: '',
    topRiskText: '',
    personaCards: [] as Array<{ name: string; score: number; tag: string }>,
    personaVoices: [] as Array<{ groupTitle: string; score: string; statement: string; tags: string[]; attractedBy: string; hesitation: string; tone: string; avatar: string }>,
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
    sixDimBreakdown: [] as Array<{ label: string; weight: number; score: number | null; contribution: number; hasRealData: boolean; sourceText: string; explainText: string; actionText: string; bubbleDesc: string; bubbleAction: string }>,
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
    deepAnalysis: null as DeepAnalysisView | null,
    deepAnalysisExpanded: false,
    /** 01 机会与阻力 swiper 当前页索引（0=机会, 1=阻力） */
    diSwiperIdx: 0,
    /** 01 进度条展开动画开关 */
    diBarAnimating: true,
    deepAnalysisLoading: false,
    flippedVoiceIdx: -1,
    /** 03 雷达图：真实维度数量（< 3 时不绘图） */
    radarRealCount: 0,
    /** 03 雷达图：当前选中的维度下标 */
    selectedRadarDimIndex: 0,
    /** 03 雷达图：气泡是否可见 */
    radarBubbleVisible: false,
    /** 03 雷达图：气泡 position 样式 */
    radarBubbleStyle: '',
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
      this.initRadarDimSelection(); // drawRadarChart 由其 setData 回调触发
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
      const [businessReport, evaluation] = await Promise.all([
        api.getBusinessReportByEval(evalId),
        api.getEvaluation(evalId).catch(() => null),
      ]);
      const answers = await api.getEvaluationAnswers(evalId, evaluation?.selected_persona_ids || []).catch(() => [] as any[]);
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
      this.initRadarDimSelection(); // drawRadarChart 由其 setData 回调触发
    } catch (err: any) {
      if (!showLoading) {
        return;
      }
      try {
        const [report, evaluation] = await Promise.all([
          api.getReportByEval(evalId),
          api.getEvaluation(evalId).catch(() => null),
        ]);
        const baseAnswers = await api.getEvaluationAnswers(evalId, evaluation?.selected_persona_ids || []).catch(() => [] as any[]);
        const tagMap = buildPersonaTagMap((baseAnswers as any[]) || []);
        let productName = '';
        if (evaluation?.product_id) {
          const product = await api.getProduct(evaluation.product_id).catch(() => null);
          productName = product?.name || '';
        }
        this.setData({ phase: 'ready', vm: this.buildBaseVM(report, productName, tagMap, (baseAnswers as any[]) || []) });
        this.initRadarDimSelection(); // drawRadarChart 由其 setData 回调触发
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

    debugRadarPaths(report);
    if (DEBUG_RADAR) {
      console.log('[radar-real] report.metrics keys:', Object.keys(report.metrics || {}));
      console.log('[radar-real] dimensions_radar:', _short(report.metrics?.dimensions_radar));
      console.log('[radar-real] dimension_scores:', _short((report.metrics as any)?.dimension_scores));
    }
    const dims = extractRadarDims(report);
    if (DEBUG_RADAR) console.log('[radar-real] extracted dims:', dims);
    const scoredDims = dims.filter((d): d is { dim: string; score: number } => d.score !== null);
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
      heatmapDimHeaders: buildHeatmapDimHeaders(scoredDims),
      heatmapRows: buildHeatmapRows(segs, scoredDims, avg, tagMap, answers),
      dimensionBars: buildDimensionBars(scoredDims),
      ...buildCompositeScore(scoredDims, avg),
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
        { label: '首要机会', title: opportunities[0]?.title || '机会点待识别', text: compactSignalAction(opportunities[0]?.title || '', true) },
        { label: '主要风险', title: risks[0]?.title || '风险点待识别', text: compactSignalAction(risks[0]?.title || '', false) },
        { label: '优先动作', title: '明确下一轮验证', text: '优先复核购买意向较低的问题，定位价格、功效或信任阻碍。' },
      ],
      opportunities,
      risks,
      conclusion: buildConclusion(
        buildPersonaCards(segs, tagMap, answers).map(c => c.name),
        opportunities,
        risks,
        top2BoxPct,
        buildCompositeScore(scoredDims, avg).compositeGrade,
      ),
      heroAdviceText: buildHeroAdvice(buildCompositeScore(scoredDims, avg).compositeGrade),
      topOpportunityText: joinTopSignals(opportunities, '高意向卖点'),
      topRiskText: joinTopSignals(risks, '决策证据不足'),
      personaVoices: (() => {
        const primary = buildPersonaVoices(answers as any[], opportunities, risks);
        if (primary.length) return primary;
        // fallback：从群体意向数据生成，确保 02 模块始终有内容
        const tones = ['violet', 'green', 'amber', 'blue', 'slate'];
        const sortedA = [...(answers as any[])].sort((a: any, b: any) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));
        return [...segs].sort((a, b) => b.avg_intent - a.avg_intent).slice(0, 5).map((seg, i) => ({
          groupTitle: compactGroupTitle(pickSegmentLabel(seg.segment, i, tagMap, sortedA), `群体${ORDINAL_ZH[i] ?? i + 1}`),
          score: `${seg.avg_intent.toFixed(1)}/5`,
          statement: buildPersonaStatement('', seg.avg_intent, joinTopSignals(opportunities.slice(0, 1), ''), joinTopSignals(risks.slice(0, 1), '')),
          tags: buildPersonaTags(joinTopSignals(opportunities.slice(0, 1), ''), joinTopSignals(risks.slice(0, 1), '')),
          attractedBy: joinTopSignals(opportunities.slice(0, 1), '核心卖点'),
          hesitation: joinTopSignals(risks.slice(0, 1), '决策证据'),
          tone: tones[i] || 'slate',
          avatar: `/assets/persona-avatars/avatar-${String((i % 10) + 1).padStart(2, '0')}.png`,
        }));
      })(),
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

    debugRadarPaths(report);
    if (DEBUG_RADAR) {
      console.log('[radar-real] report.metrics keys:', Object.keys(report.metrics || {}));
      console.log('[radar-real] dimensions_radar:', _short((report.metrics as any)?.dimensions_radar));
      console.log('[radar-real] dimension_scores:', _short(report.metrics?.dimension_scores));
    }
    const dims = extractRadarDims(report);
    if (DEBUG_RADAR) console.log('[radar-real] extracted dims:', dims);
    const scoredDims = dims.filter((d): d is { dim: string; score: number } => d.score !== null);
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
      { label: '首要机会', title: dedupedOpportunities[0]?.title || '机会点待识别', text: compactSignalAction(dedupedOpportunities[0]?.title || '', true) },
      { label: '主要风险', title: dedupedRisks[0]?.title || '风险点待识别', text: compactSignalAction(dedupedRisks[0]?.title || '', false) },
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
      heatmapDimHeaders: buildHeatmapDimHeaders(scoredDims),
      heatmapRows: buildHeatmapRows(segs, scoredDims, avg, tagMap, answers),
      dimensionBars: buildDimensionBars(scoredDims),
      ...buildCompositeScore(scoredDims, avg),
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
        buildCompositeScore(scoredDims, avg).compositeGrade,
      ),
      heroAdviceText: buildHeroAdvice(buildCompositeScore(scoredDims, avg).compositeGrade),
      topOpportunityText: joinTopSignals(dedupedOpportunities, '高意向卖点'),
      topRiskText: joinTopSignals(dedupedRisks, '决策证据不足'),
      personaVoices: (() => {
        const primary = buildPersonaVoices(answers as any[], dedupedOpportunities, dedupedRisks);
        if (primary.length) return primary;
        // fallback：从群体意向数据生成，确保 02 模块始终有内容
        const tones = ['violet', 'green', 'amber', 'blue', 'slate'];
        const sortedA = [...(answers as any[])].sort((a: any, b: any) => (b.overall_intent ?? 0) - (a.overall_intent ?? 0));
        return [...segs].sort((a, b) => b.avg_intent - a.avg_intent).slice(0, 5).map((seg, i) => ({
          groupTitle: compactGroupTitle(pickSegmentLabel(seg.segment, i, tagMap, sortedA), `群体${ORDINAL_ZH[i] ?? i + 1}`),
          score: `${seg.avg_intent.toFixed(1)}/5`,
          attractedBy: joinTopSignals(dedupedOpportunities.slice(0, 1), '核心卖点'),
          hesitation: joinTopSignals(dedupedRisks.slice(0, 1), '决策证据'),
          tone: tones[i] || 'slate',
          avatar: `/assets/persona-avatars/avatar-${String((i % 10) + 1).padStart(2, '0')}.png`,
        }));
      })(),
      nextSteps,
      sixDimBreakdown: buildSixDimBreakdown(dims, top2BoxPct, avg),
      disclaimer: report.ai_disclaimer || '报告由 AI 聚合调研回答生成，仅供决策参考。',
    };
  },

  /** 雷达图维度选择初始化：计算 radarRealCount 并选中第一个有真实数据的维度 */
  initRadarDimSelection() {
    const breakdown = this.data.vm.sixDimBreakdown;
    const realCount = breakdown.filter((d: { hasRealData: boolean }) => d.hasRealData).length;
    const defaultIdx = breakdown.findIndex((d: { hasRealData: boolean }) => d.hasRealData);

    // 与 drawRadarChart 完全一致的坐标系：r = maxR*(score/100)
    // hit-area 叠在红色折线数据节点上；_px/_py 供气泡定位使用
    const SIZE = 280, cx = SIZE / 2, cy = SIZE / 2, maxR = 68, n = 6;
    const updatedBreakdown = breakdown.map((d: any, i: number) => {
      const a = (Math.PI * 2 * i / n) - Math.PI / 2;
      const ratio = d.hasRealData && typeof d.score === 'number' ? d.score / 100 : 0;
      const r = maxR * ratio;
      const px = cx + Math.cos(a) * r;
      const py = cy + Math.sin(a) * r;
      return {
        ...d,
        _px: px,   // 像素坐标，供 buildRadarBubbleStyle 使用
        _py: py,
        // CSS margin-left/margin-top 负半宽居中，无需 transform
        nodeStyle: `left:${(px / SIZE * 100).toFixed(2)}%;top:${(py / SIZE * 100).toFixed(2)}%;`,
      };
    });

    // setData 回调：canvas 挂载完成后再绘图，避免 wx.nextTick 早于 canvas 挂载
    this.setData({
      radarRealCount: realCount,
      selectedRadarDimIndex: defaultIdx >= 0 ? defaultIdx : 0,
      'vm.sixDimBreakdown': updatedBreakdown,
    }, () => {
      this.drawRadarChart();
    });
  },

  /** 点击雷达数据节点：高亮 + 显示气泡卡 */
  onTapRadarNode(e: WechatMiniprogram.TouchEvent) {
    const index = Number(e.currentTarget.dataset.index);
    const item = (this.data.vm.sixDimBreakdown as any[])[index];
    if (!item || !item.hasRealData) return;
    this.setData({
      selectedRadarDimIndex: index,
      radarBubbleVisible: true,
      radarBubbleStyle: this.buildRadarBubbleStyle(index),
    });
  },

  /** 点击雷达图空白处，收起气泡 */
  onTapRadarBlank() {
    if ((this.data as any).radarBubbleVisible) {
      this.setData({ radarBubbleVisible: false });
    }
  },

  /** 阻止气泡点击事件冒泡到空白区，防止气泡自身关闭 */
  noop() {},

  /**
   * 根据数据点位置 (_px, _py) 计算气泡的 absolute 定位样式。
   * 上半区 → 气泡出现在点下方；下半区 → 气泡出现在点上方。
   * 横向以数据点为中心，边界夹拢不超出容器。
   */
  buildRadarBubbleStyle(index: number): string {
    const breakdown = this.data.vm.sixDimBreakdown as any[];
    const item = breakdown[index];
    if (!item) return '';

    const SIZE = 280;                        // 容器与 canvas 等宽 (px)
    const px: number = typeof item._px === 'number' ? item._px : SIZE / 2;
    const py: number = typeof item._py === 'number' ? item._py : SIZE / 2;

    // 气泡宽度约占容器 89%（500rpx ≈ 250px on 375px 设备 / 280px 容器）
    const BW = 0.89;
    const BH_EST = 0.45;   // 估算气泡高度占容器比例（更大尺寸）
    const GAP = 14 / SIZE; // 点到气泡边缘间距

    // 纵向：上半区气泡放点下方，下半区放点上方
    let topFrac = py / SIZE <= 0.5
      ? py / SIZE + GAP
      : py / SIZE - GAP - BH_EST;
    topFrac = Math.max(0.01, Math.min(topFrac, 1 - BH_EST - 0.01));

    // 横向：以点为中心，夹拢在 [0, 1-BW]
    let leftFrac = px / SIZE - BW / 2;
    leftFrac = Math.max(0, Math.min(leftFrac, 1 - BW));

    return `left:${(leftFrac * 100).toFixed(1)}%;top:${(topFrac * 100).toFixed(1)}%;`;
  },

  drawRadarChart() {
    wx.nextTick(() => {
      const breakdown = this.data.vm.sixDimBreakdown;
      if (!breakdown || !breakdown.length) return;
      // 真实维度不足 3 个时不绘图，避免展示无意义图形
      const realCount = (this.data as any).radarRealCount as number;
      if (realCount < 3) return;
      const ctx = wx.createCanvasContext('rp-radar', this);
      const SIZE = 280;
      const cx = SIZE / 2;
      const cy = SIZE / 2;
      const maxR = 68;       // 缩小：给 15px 标签留足 canvas 内安全边距
      const labelR = 90;     // 标签离圆心距离
      const n = 6;
      // 无真实数据的维度绘制在圆心（score=0），不伪造图形
      const values = breakdown.map((d: { score: number | null; hasRealData: boolean }) =>
        d.hasRealData && d.score !== null ? d.score / 100 : 0
      );
      const labels = breakdown.map((d: { label: string }) => d.label);

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

      // Axis labels — 根据角度动态设置 textAlign，防止右侧/左侧标签越界
      ctx.setFontSize(15);
      ctx.setFillStyle('#374151');
      const SAFE_X = 46;   // 左右安全边距（中文标签宽约 60-75px）
      const SAFE_Y = 18;   // 上下安全边距
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i / n) - Math.PI / 2;
        const cosA = Math.cos(a);
        const sinA = Math.sin(a);
        let lx = cx + labelR * cosA;
        let ly = cy + labelR * sinA;
        // textAlign：右半区 left，左半区 right，顶底 center
        let align: 'center' | 'left' | 'right' = 'center';
        if (cosA > 0.35) {
          align = 'left';
          lx = Math.min(lx, SIZE - SAFE_X);
        } else if (cosA < -0.35) {
          align = 'right';
          lx = Math.max(lx, SAFE_X);
        }
        // 垂直微调：底部文字往下推，顶部文字往上提
        if (sinA < -0.3) ly -= 4;   // 上方
        if (sinA > 0.3) ly += 10;   // 下方
        // clamp Y
        ly = Math.max(SAFE_Y, Math.min(SIZE - SAFE_Y, ly));
        ctx.setTextAlign(align);
        ctx.fillText(labels[i], lx, ly);
      }

      ctx.draw();
    });
  },

  /** 01 swiper 翻页（滑动触发） */
  onDiSwiperChange(e: WechatMiniprogram.SwiperChange) {
    const idx = (e.detail as any).current as number;
    this.setData({ diSwiperIdx: idx, diBarAnimating: false });
    setTimeout(() => { this.setData({ diBarAnimating: true }); }, 30);
  },

  /** 01 segmented tab 点击 */
  onTapDiTab(e: WechatMiniprogram.TouchEvent) {
    const idx = Number(e.currentTarget.dataset.idx);
    this.setData({ diSwiperIdx: idx, diBarAnimating: false });
    setTimeout(() => { this.setData({ diBarAnimating: true }); }, 30);
  },

  /** 点击六维 chip，更新选中维度 */
  onTapRadarDimChip(e: WechatMiniprogram.TouchEvent) {
    const idx = e.currentTarget.dataset.idx as number;
    this.setData({ selectedRadarDimIndex: idx });
  },

  async loadDeepAnalysis(evalId: string) {
    const cacheKey = `deep_analysis_cache_${evalId}`;

    try {
      const cached = wx.getStorageSync(cacheKey);
      if (cached) {
        const parsed = typeof cached === 'string' ? JSON.parse(cached) : cached;
        if (parsed?.sections?.length) {
          this.setData({ deepAnalysis: normalizeDeepAnalysis(parsed) });
        }
      }
    } catch { /* ignore */ }

    try {
      const result = await api.getDeepAnalysis(evalId);
      if (result?.sections?.length) {
        this.setData({ deepAnalysis: normalizeDeepAnalysis(result) });
        try { wx.setStorageSync(cacheKey, JSON.stringify(result)); } catch { /* ignore */ }
        return;
      }
    } catch { /* ignore */ }

    if (!this.data.deepAnalysis) {
      const sections = buildDeepSectionsFromVM(this.data.vm);
      this.setData({
        deepAnalysis: normalizeDeepAnalysis({ sections, generated_at: new Date().toISOString() }),
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

  onTapVoiceCard(e: any) {
    const idx = Number(e.currentTarget.dataset.idx ?? -1);
    this.setData({ flippedVoiceIdx: idx === this.data.flippedVoiceIdx ? -1 : idx });
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
          // 调研报告导出：渲染调研报告数据为 PDF
          const reportUrl = base
            + `&mode=${encodeURIComponent('report')}`
            + `&product_name=${encodeURIComponent(this.data.vm.productName || '')}`;
          wx.navigateTo({ url: `/pages/webview/webview?url=${encodeURIComponent(reportUrl)}` });
        } else {
          // 白皮书导出：使用白皮书查看器
          api.generateWhitepaper({
            evaluation_id: evalId,
            product_name: this.data.vm.productName,
          }).catch(() => {/* ignore */});
          const wpUrl = base
            + `&mode=${encodeURIComponent('whitepaper')}`
            + `&product_name=${encodeURIComponent(this.data.vm.productName || '')}`;
          wx.navigateTo({ url: `/pages/webview/webview?url=${encodeURIComponent(wpUrl)}` });
        }
      },
    });
  },
});
