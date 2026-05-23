import { api } from '../../services/api';
import { BASE_URL, getToken } from '../../services/http';
import type { BackendReport, BusinessReport, DeepAnalysis } from '../../types/api';

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
): Array<{ segment: string; cells: Array<{ score: number | null; bg: string; label: string }> }> {
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
    const segLabel = pickSegmentLabel(seg.segment, i, tagMap, sortedAnswers);
    const segTag = tagMap[seg.segment] || sortedAnswers[i]?.persona_tag || '';
    const dimScores = tagScoreMap[segTag] || {};

    return {
      segment: segLabel,
      cells: topDims.map(d => {
        const realVals = dimScores[d.dim];
        const score: number | null =
          realVals && realVals.length > 0
            ? parseFloat((realVals.reduce((s, v) => s + v, 0) / realVals.length).toFixed(1))
            : null;
        return { score, bg: hmCellBg(score), label: dimLabel(d.dim) };
      }),
    };
  });
}

function buildHeatmapDimHeaders(dims: Array<{ dim: string; score: number }>): string[] {
  return dims.slice(0, 5).map(d => dimLabel(d.dim));
}

function buildProsRanked(
  pros: Array<{ title: string; support_count: number; evidence_quotes?: Array<{ persona_name: string; quote: string }>; business_implication?: string }>,
  total: number,
): Array<{ title: string; count: number; pct: number; width: number }> {
  return (pros || []).slice(0, 5).map(p => {
    const pct = total > 0 ? Math.round((p.support_count / total) * 100) : 0;
    return {
      title: p.title,
      count: p.support_count,
      pct,
      width: Math.min(100, pct),
    };
  });
}

function buildConsRanked(
  cons: Array<{ title: string; support_count: number; evidence_quotes?: Array<{ persona_name: string; quote: string }>; improvement_suggestion?: string }>,
  total: number,
): Array<{ title: string; count: number; pct: number; width: number }> {
  return (cons || []).slice(0, 5).map(c => {
    const pct = total > 0 ? Math.round((c.support_count / total) * 100) : 0;
    return {
      title: c.title,
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
    segmentRows: [] as Array<{ label: string; count: number; value: string; width: number }>,
    heatmapDimHeaders: [] as string[],
    heatmapRows: [] as Array<{ segment: string; cells: Array<{ score: number | null; bg: string; label: string }> }>,
    dimensionBars: [] as Array<{ label: string; value: string; width: number }>,
    prosRanked: [] as Array<{ title: string; count: number; pct: number; width: number }>,
    consRanked: [] as Array<{ title: string; count: number; pct: number; width: number }>,
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
    opportunities: [] as Array<{ title: string; note: string; count: number }>,
    risks: [] as Array<{ title: string; note: string; count: number }>,
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
      count: item.support_count || 0,
    }));
    const risks = (report.top_cons || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.quotes?.[0]?.quote ? `用户原声：${item.quotes[0].quote}` : '该风险需要在卖点表达或后续验证中优先处理。',
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
      nextSteps: [
        '优先复核购买意向较低的问题，定位价格、功效或信任阻碍。',
        '围绕高频机会点制作 2-3 个卖点表达版本进行复测。',
        '保留用户原声中反复出现的顾虑，作为详情页和投放素材的证明点。',
      ],
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
      count: item.support_count || 0,
    }));
    const risks = (report.top_cons || []).slice(0, 3).map(item => ({
      title: item.title,
      note: item.improvement_suggestion,
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
    ).slice(0, 4).map(cleanReportText);
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
      nextSteps,
      disclaimer: report.ai_disclaimer || '报告由 AI 聚合调研回答生成，仅供决策参考。',
    };
  },

  async loadDeepAnalysis(evalId: string) {
    const cacheKey = `deep_analysis_cache_${evalId}`;
    try {
      const cached = wx.getStorageSync(cacheKey);
      if (cached) {
        const parsed = typeof cached === 'string' ? JSON.parse(cached) : cached;
        if (parsed?.sections?.length) {
          this.setData({ deepAnalysis: parsed });
          return;
        }
      }
    } catch { /* ignore */ }
    this.setData({ deepAnalysisLoading: true });
    try {
      const result = await api.getDeepAnalysis(evalId);
      this.setData({ deepAnalysis: result, deepAnalysisLoading: false });
      try { wx.setStorageSync(cacheKey, JSON.stringify(result)); } catch { /* ignore */ }
    } catch {
      this.setData({ deepAnalysisLoading: false });
    }
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

  async onTapExport() {
    const evalId = this.data.evaluationId;
    if (!evalId) {
      wx.showToast({ title: '缺少调研 ID', icon: 'none' });
      return;
    }
    const token = getToken() || '';
    const reportUrl = `${whitepaperBase()}${WHITEPAPER_VIEWER_PATH}`
      + `?evaluation_id=${encodeURIComponent(evalId)}`
      + `&token=${encodeURIComponent(token)}`
      + `&api_base=${encodeURIComponent(whitepaperBase())}`;
    const ok = await new Promise<boolean>(resolve => {
      wx.request({
        url: `${whitepaperBase()}${WHITEPAPER_VIEWER_PATH}`,
        method: 'GET',
        timeout: 5000,
        success: res => resolve(res.statusCode >= 200 && res.statusCode < 400),
        fail: () => resolve(false),
      });
    });
    if (!ok) {
      wx.showToast({ title: '白皮书页面服务未启动', icon: 'none' });
      return;
    }
    wx.navigateTo({
      url: `/pages/webview/webview?url=${encodeURIComponent(reportUrl)}`,
    });
  },
});
