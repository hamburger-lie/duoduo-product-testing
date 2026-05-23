// API 类型 — 严格对齐 D:\soul\docs\specs\API_CONTRACT.md
// 所有 ID 字段以 string 传输（snowflake 防 JS 精度丢失，详见 §0.1）
// 时间字段统一 ISO 8601 + UTC 字符串

// ---------- 通用 ----------
export interface CursorPaged<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface OffsetPaged<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ApiError {
  code: string;
  message: string;
  statusCode?: number;
  request_id?: string;
  details?: Record<string, unknown>;
}

// ---------- Auth §1 ----------
export type RoleType = 'manufacturer' | 'channel' | null;

export interface User {
  id: string;
  nickname: string;
  avatar_url: string | null;
  role_type: RoleType;
  credit_balance: number;
  is_new_user?: boolean;
}

export interface WechatLoginReq { code: string }
export interface WechatLoginRes {
  token: string;
  expires_in: number;
  user: User;
}

export interface ProfileUpdateReq {
  role_type?: string;
  nickname?: string | null;
  avatar_url?: string | null;
}

export interface AvatarUploadRes {
  avatar_url: string;
}

// ---------- Product §2 ----------
export interface ProductAiSummary {
  main_selling_points: string[];
  key_ingredients: string[];
  suitable_skin_types: string[];
  target_audience: string;
  competitive_position: string;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  image_urls: string[];
  category: string;
  sub_category: string | null;
  brand: string | null;
  price: number | null;
  price_range: string | null;
  target_channel: 'ec' | 'offline' | 'livestream' | null;
  ai_summary: ProductAiSummary | null;
  status: 'pending' | 'ready' | 'failed';
  error_message?: string | null;
  created_at: string;
}

export interface UploadUrlReq {
  filename: string;
  mime_type: string;
  size_bytes: number;
}
export interface UploadUrlRes {
  upload_url: string;
  method: 'PUT';
  headers: Record<string, string>;
  object_key: string;
  expires_in: number;
}

export interface CreateProductReq {
  name?: string;
  description: string;
  image_object_keys: string[];
  brand?: string;
  price?: number;
  target_channel?: 'ec' | 'offline' | 'livestream';
}

// ---------- Persona §3 ----------
export interface PersonaSummary {
  id: string;
  name: string;
  avatar: string;          // emoji 或 url 或 internal SVG id (yun/jie/cong)
  age: number;
  gender: 'female' | 'male' | 'other';
  city: string;
  city_tier: 1 | 2 | 3 | 4;
  occupation: string;
  income_monthly: number;
  persona_tag: string;
  categories: string[];
  is_critical: boolean;
  is_system: boolean;
}

export interface PersonaDetail extends PersonaSummary {
  ocean: { o: number; c: number; e: number; a: number; n: number };
  profile: {
    bio: string;
    shopping_habits: string;
    skincare_concerns: string[];
    brand_preferences: string[];
    price_sensitivity: string;
    info_channels: string[];
    decision_style: string;
    pet_phrases: string[];
    pain_points: string[];
    lifestyle: string;
  };
  version: number;
  created_at: string;
}

// ---------- Evaluation §5 ----------
export type EvaluationStatus =
  | 'pending'
  | 'generating_survey'
  | 'answering'
  | 'generating_report'
  | 'done'
  | 'failed'
  | 'canceled';

export interface Evaluation {
  id: string;
  user_id: string;
  product_id: string;
  survey_id: string | null;
  selected_persona_ids: string[];
  status: EvaluationStatus;
  progress: number;        // 0-100
  credit_cost: number;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  created_at: string;
  stats?: {
    total_personas: number;
    completed_personas: number;
    failed_personas: number;
  };
}

export interface CreateEvaluationReq { product_id: string }
export interface AttachPersonasReq { persona_ids: string[] }

// ---------- Conversation §7 ----------
export interface Conversation {
  id: string;
  evaluation_id: string;
  persona_id: string;
  persona_name: string;
  persona_avatar: string;
  title: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
}

export type MessageRole = 'user' | 'assistant';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  // 测品官扩展：assistant 消息可以带 "内心独白"（think）+ "口头表达"（speak）双流
  think?: string;
  created_at: string;
}

export type StreamEvent =
  | { event: 'delta'; content: string }
  | { event: 'think_delta'; content: string }
  | { event: 'meta'; message_id: string; tokens: { input: number; output: number }; cost_yuan?: number }
  | { event: 'done' }
  | { event: 'error'; code: string; message: string };

// ---------- Survey §4b ----------
export interface SurveyQuestion {
  id: string;
  dim?: string;        // dimension label (e.g. '第一印象') from real backend
  text?: string;       // mock format
  question?: string;   // real backend format (§4.1 API contract)
  type: 'open' | 'scale_1_5' | 'single' | 'multi';
  /** Real backend: string[] — Mock: {id,text}[] */
  options: Array<string | { id: string; text: string }> | null;
}
export interface Survey {
  id: string;
  questions: SurveyQuestion[];
}

// ---------- Evaluation Answer §5b ----------
/** Per-answer item returned by real backend (§5.7) */
export interface PersonaAnswerItem {
  qid: string;
  type: string;
  answer: string | number | string[];
  reason?: string;
}

export interface EvaluationAnswer {
  id?: string;
  evaluation_id: string;
  persona_id: string;
  persona_name?: string;
  persona_tag?: string;
  overall_intent: number;           // NPS 0-10
  sentiment: 'positive' | 'neutral' | 'negative';
  summary_comment?: string;
  thinking_process?: string;        // 角色答题前的内心推理过程（v4.1+）
  /** Real backend: PersonaAnswerItem[] — Mock: Record<string, value> */
  answers: PersonaAnswerItem[] | Record<string, string | number | string[]>;
  created_at?: string;
}

// ---------- Report §6 ----------
export interface BackendReport {
  id: string;
  evaluation_id: string;
  summary: string;
  metrics: {
    overall_intent: {
      average: number;
      distribution: Array<{ score: number; count: number }>;
      nps: number;
    };
    dimensions_radar: Array<{ dim: string; score: number }>;
    price_sensitivity: {
      median_acceptable_price: number;
      distribution: Array<{ range: string; count: number }>;
    };
    segment_intent: Array<{ segment: string; count: number; avg_intent: number }>;
  };
  top_pros: Array<{
    title: string;
    support_count: number;
    quotes: Array<{ persona_id: string; persona_name: string; quote: string }>;
  }>;
  top_cons: Array<{
    title: string;
    support_count: number;
    quotes: Array<{ persona_id: string; persona_name: string; quote: string }>;
  }>;
  persona_segments: {
    most_positive: string[];
    most_negative: string[];
    highest_value: string[];
  };
  ai_disclaimer: string;
  generated_at: string;
  pdf_url: string | null;
  share_token: string | null;
}

export interface BusinessReport {
  id: string;
  evaluation_id: string;
  template_key: string;
  ai_disclaimer: string;
  executive_summary: string[];
  decision_suggestion: {
    verdict: 'go' | 'iterate' | 'pause';
    reason: string;
    confidence: number;
  };
  metrics: {
    overall_intent_avg: number;
    nps: number;
    intent_distribution: Record<string, number>;
    dimension_scores: Array<{ dim: string; score: number }>;
    price_sensitivity: Array<{ range: string; count: number }>;
    persona_segments: Array<{ segment: string; count: number; avg_intent: number }>;
  };
  top_pros: Array<{
    title: string;
    support_count: number;
    evidence_quotes: Array<{ persona_name: string; quote: string }>;
    business_implication: string;
  }>;
  top_cons: Array<{
    title: string;
    support_count: number;
    evidence_quotes: Array<{ persona_name: string; quote: string }>;
    improvement_suggestion: string;
  }>;
  target_audience: {
    most_likely_to_buy: string[];
    least_likely_to_buy: string[];
    channel_recommendation: string[];
  };
  marketing_copy_angles: Array<{
    angle: string;
    suitable_segment: string;
    risk_note: string;
  }>;
  evidence_chains?: Array<{
    evidence_type: string;
    conclusion: string;
    support_count: number;
    source_roles: string[];
    source_answers: Array<{ persona_name: string; quote: string }>;
    business_action: string;
  }>;
  next_test_recommendations: string[];
  generated_at: string;
}

export interface DeepAnalysisSection {
  title: string;
  content: string;
}

export interface DeepAnalysis {
  sections: DeepAnalysisSection[];
  generated_at: string;
}

export interface ReportPdfListItem {
  report_id: string;
  evaluation_id: string;
  product_name: string;
  pdf_url: string;
  generated_at: string;
}

export interface ReportPdfListResponse {
  items: ReportPdfListItem[];
}

// ---------- Credit §8 ----------
export interface CreditBalance {
  balance: number;
  updated_at: string;
}
export interface CreditTransaction {
  id: string;
  type: 'recharge' | 'evaluation' | 'conversation' | 'adjust' | 'referral' | 'init';
  amount: number;          // 正数=入账，负数=消耗
  balance_after: number;
  description: string;
  created_at: string;
}
