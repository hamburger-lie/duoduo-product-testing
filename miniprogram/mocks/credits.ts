// 积分 mock — Profile 页与首页统计使用

import type { CreditBalance, CreditTransaction, User } from '../types/api';

export const MOCK_USER: User = {
  id: 'u_001',
  nickname: '云裳',
  avatar_url: null,
  role_type: 'manufacturer',
  credit_balance: 8420,
  is_new_user: false,
};

export const MOCK_BALANCE: CreditBalance = {
  balance: 8420,
  updated_at: '2026-05-11T08:00:00Z',
};

export const MOCK_TRANSACTIONS: CreditTransaction[] = [
  {
    id: 'tx_001',
    type: 'evaluation',
    amount: -120,
    balance_after: 8420,
    description: '燕泽修护精华液 调研',
    created_at: '2026-05-09T10:12:00Z',
  },
  {
    id: 'tx_002',
    type: 'evaluation',
    amount: -90,
    balance_after: 8540,
    description: '烁光唇膏 调研',
    created_at: '2026-05-06T14:30:00Z',
  },
  {
    id: 'tx_003',
    type: 'recharge',
    amount: +5000,
    balance_after: 8630,
    description: '高级会员充值',
    created_at: '2026-05-01T09:00:00Z',
  },
];

/** 首页统计卡片用 */
export const MOCK_HOME_STATS = {
  total_evaluations: 12,
  total_insights: 1420,
};
