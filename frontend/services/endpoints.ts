// API 路径常量 — 对齐 API_CONTRACT.md §11 速查表
// Phase B 切换真后端时，仅需修改 services/http.ts 的 BASE_URL

export const API_VERSION_PREFIX = '/api/v1';

export const E = {
  // §1 Auth
  AUTH_WECHAT_LOGIN: '/auth/wechat/login',
  AUTH_PROFILE:      '/auth/profile',
  AUTH_REFRESH:      '/auth/refresh',
  AUTH_LOGOUT:       '/auth/logout',
  AUTH_ME:           '/auth/me',
  AUTH_AVATAR:       '/auth/avatar',

  // §2 Product
  PRODUCT_UPLOAD_URL:        '/products/upload-url',
  PRODUCT_CREATE:            '/products',
  PRODUCT_DETAIL: (id: string) => `/products/${id}`,
  PRODUCT_REANALYZE: (id: string) => `/products/${id}/reanalyze`,
  PRODUCT_LIST:              '/products',
  PRODUCT_EXTRACT_FROM_IMAGES: '/products/extract-from-images',

  // §3 Persona
  PERSONA_LIST:              '/personas',
  PERSONA_DETAIL: (id: string) => `/personas/${id}`,
  PERSONA_RECOMMEND:         '/personas/recommend',
  PERSONA_CREATE:            '/personas',
  PERSONA_UPDATE: (id: string) => `/personas/${id}`,
  PERSONA_DELETE: (id: string) => `/personas/${id}`,

  // §4 Survey
  SURVEY_GENERATE:           '/surveys/generate',
  SURVEY_GENERATE_STREAM:    '/surveys/generate-stream',
  SURVEY_DETAIL: (id: string) => `/surveys/${id}`,
  SURVEY_UPDATE_QUESTIONS: (id: string) => `/surveys/${id}/questions`,

  // §5 Evaluation
  EVAL_CREATE:               '/evaluations',
  EVAL_ATTACH_PERSONAS: (id: string) => `/evaluations/${id}/personas`,
  EVAL_RUN: (id: string) => `/evaluations/${id}/run`,
  EVAL_DETAIL: (id: string) => `/evaluations/${id}`,
  EVAL_CANCEL: (id: string) => `/evaluations/${id}/cancel`,
  EVAL_DELETE: (id: string) => `/evaluations/${id}`,
  EVAL_LIST:                 '/evaluations',
  EVAL_ANSWER: (eid: string, pid: string) => `/evaluations/${eid}/answers/${pid}`,
  EVAL_ANSWERS_ALL: (id: string) => `/evaluations/${id}/answers`,

  // §6 Report
  REPORT_BY_EVAL: (eid: string) => `/reports/by-evaluation/${eid}`,
  REPORT_BUSINESS_BY_EVAL: (eid: string) => `/reports/by-evaluation/${eid}/business`,
  REPORT_PDFS: '/reports/pdfs',
  REPORT_EXPORT_PDF: (rid: string) => `/reports/${rid}/export-pdf`,
  REPORT_SHARE: (rid: string) => `/reports/${rid}/share`,

  // §6.5 Whitepaper
  WHITEPAPER_GENERATE: '/whitepapers/generate',
  WHITEPAPER_BY_EVAL: (eid: string) => `/whitepapers/by-evaluation/${eid}`,

  // §6.6 Deep Analysis
  DEEP_ANALYSIS_BY_EVAL: (eid: string) => `/evaluations/${eid}/deep-analysis`,

  // §7 Conversation
  CONV_CREATE:               '/conversations',
  CONV_MESSAGES_LIST: (cid: string) => `/conversations/${cid}/messages`,
  CONV_MESSAGE_SEND: (cid: string) => `/conversations/${cid}/messages`,
  CONV_LIST:                 '/conversations',
  CONV_DELETE: (cid: string) => `/conversations/${cid}`,

  // §8 Credit
  CREDIT_BALANCE:            '/credits/balance',
  CREDIT_TRANSACTIONS:       '/credits/transactions',
  CREDIT_RECHARGE:           '/credits/recharge',
  CREDIT_DAILY_LOGIN:        '/credits/daily-login',

  // §9 History
  HISTORY_LIST:              '/history',
};
