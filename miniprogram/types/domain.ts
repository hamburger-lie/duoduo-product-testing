// 前端领域视图模型 — 在 API 类型之上做轻量裁剪，便于页面展示

import type { Evaluation, PersonaSummary } from './api';

/** 首页 / 历史卡片视图 */
export interface EvaluationCardVM {
  id: string;
  title: string;          // 通常 = product.name
  thumb_emoji: string;
  thumb_url?: string;     // 产品图片 URL（有则优先显示）
  meta_text: string;      // 例 "2天前 · 3位测品官"
  progress: number;       // 0-100
  status: Evaluation['status'];
  status_label: '进行中' | '已完成' | '已取消' | '失败' | '准备中';
  persona_ids: string[];
  message_count: number;
  insight_count: number;
}

/** 三位固定测品官的内部 id（mock 用） */
export type PersonaKey = 'yun' | 'jie' | 'cong';

export interface PersonaWithKey extends PersonaSummary {
  key: PersonaKey;
  trait: string;          // 一句话描述（mockup 用）
}

/** 创建调研页选择话题 */
export interface TopicOption {
  id: string;
  emoji: string;
  label: string;
}

/** 结构化 Q&A 条目（每道题独立展示） */
export interface QAItem {
  question: string;         // 题目文字
  dim?: string;             // 维度标签（如 '第一印象'）
  type: string;             // 题型：open / scale_1_5 / single / multi
  answer: string;           // 作答内容（打字机逐字填入）
  reason: string;           // 作答理由
  reasonDone?: boolean;     // 思考是否已经打字完成，完成后默认折叠
  reasonPreview?: string;   // 思考折叠态预览文案
  scaleValue?: number;      // 评分题数值（1-5）
  scaleDots?: Array<{ filled: boolean }>; // 评分题圆点数组
}

/** 调研对话页消息（单气泡，思考+表达合并） */
export interface ChatTurn {
  id: string;
  kind: 'topic_switch' | 'speak' | 'user' | 'status';
  persona_key?: PersonaKey;
  persona_name?: string;
  /** 数据库 persona ID，用于点击头像发起单独追问 */
  persona_id?: string;
  /** 角色整体内心想法（来自 summary_comment） */
  summaryComment?: string;
  /** 头像编号 1-10，顺序分配避免 hash 碰撞 */
  avatarSlot?: number;
  /** 结构化 Q&A 列表（每题独立展示） */
  qaItems?: QAItem[];
  /** AI 表达内容（流式追加，追问 SSE 场景 / 无结构化数据时使用） */
  content: string;
  /** AI 思考内容（追问 SSE 场景用） */
  thinkContent?: string;
  // 仅 topic_switch 用
  topic_from?: string;
  topic_to?: string;
  // 仅 status 用（评测进度）
  evalProgress?: number;
  evalRemaining?: number;
  evalStatus?: string;
}
