// 调研对话 mock — 对应 PHONE 3 设计稿

import type { ChatTurn } from '../types/domain';

export interface MockConversation {
  id: string;
  evaluation_id: string;
  persona_key: 'yun' | 'jie' | 'cong';
  persona_name: string;
  persona_role: string;
  product_title: string;
  current_topic: { index: number; total: number; emoji: string; label: string };
  turns: ChatTurn[];
}

export const MOCK_CONVERSATIONS: Record<string, MockConversation> = {
  eval_001: {
    id: 'conv_001',
    evaluation_id: 'eval_001',
    persona_key: 'yun',
    persona_name: '小芸',
    persona_role: '职场白领 · 护肤达人 · 成分党',
    product_title: '燕泽修护精华液 30ml',
    current_topic: { index: 3, total: 9, emoji: '💰', label: '价格与性价比' },
    turns: [
      {
        id: 't1',
        kind: 'topic_switch',
        content: '',
        topic_from: '成分与功效',
        topic_to: '价格与性价比',
      },
      {
        id: 't2',
        kind: 'speak',
        persona_key: 'yun',
        persona_name: '小芸',
        thinkContent:
          '这款精华标价 380 元一瓶，说实话有点肉疼……但看成分表里有积雪草苷和烟酰胺，感觉跟大牌成分差不多，但贵那么多是因为品牌溢价吗？还是真的有核心专利？',
        content:
          '380 块对我来说确实不算便宜，毕竟一个月护肤预算就 500 多。不过如果真的能快速修复屏障、三天看到效果，我觉得还是值得的。现在大家都说贵的不一定好，便宜的也能找到平替——但我还是更愿意为成分买单，而不是品牌名字。',
      },
      {
        id: 't3',
        kind: 'speak',
        persona_key: 'yun',
        persona_name: '小芸',
        thinkContent:
          '其实我想问问有没有小样试用装……380 直接入手风险有点大，如果能先 79 试个小样再决定就完美了。',
        content:
          '你们有没有出小样或者试用装？380 直接入正装对我来说门槛有点高，如果能先体验一下再决定会更有安全感。毕竟现在网上平替太多，我会先货比三家。',
      },
    ],
  },
};

/** 模拟 follow-up 的内心独白 + 表达流（用于 send 后追加） */
export const FOLLOW_UP_SCRIPTS: Array<{ think: string; speak: string }> = [
  {
    think: '嗯，让我想想他到底在意什么……如果只是单纯比价格，那其实可以聊聊场景。',
    speak:
      '说实话，单看 380 这个数字会觉得贵；但如果一瓶能用 3 个月、每天不到 5 块钱，跟一杯奶茶差不多，心理账户就完全不一样了。我会更愿意把它当成日常护肤投资，而不是一次性消费。',
  },
  {
    think: '他可能在意复购率，那我就从效果反馈和包装回购两个角度说。',
    speak:
      '能不能复购很大程度看「看不看得见效果」。如果一瓶用完皮肤状态明显好转，朋友也夸了我，我大概率会回购；反之如果只是「好像有用」，那 380 就成了犹豫点。包装如果方便最后一滴挤干净，会很加分。',
  },
];
