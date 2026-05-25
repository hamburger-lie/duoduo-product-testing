import { api, USE_MOCK } from '../../services/api';
import type { ChatTurn, PersonaKey } from '../../types/domain';
import type { EvaluationAnswer, PersonaAnswerItem, SurveyQuestion } from '../../types/api';
import type { StreamHandle } from '../../services/stream';


const PERSONA_KEYS: PersonaKey[] = ['yun', 'jie', 'cong'];

function avatarSrcForSeed(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) { h = ((h << 5) - h) + seed.charCodeAt(i); h |= 0; }
  const idx = (Math.abs(h) % 10) + 1;
  return `/assets/persona-avatars/avatar-${String(idx).padStart(2, '0')}.png`;
}

function reasonPreview(text: string): string {
  const chars = Array.from((text || '').trim());
  if (!chars.length) return '';
  return chars.slice(0, 10).join('') + (chars.length > 10 ? '......' : '');
}

const STATUS_LABELS: Record<string, string> = {
  pending:           '调研准备中',
  generating_survey: '正在生成调研问卷…',
  answering:         'AI 测品官正在认真作答…',
  generating_report: '正在汇总分析结果…',
  done:              '调研完成，正在加载结果…',
  failed:            '调研失败，请返回重试',
};

/** Retrieve a single answer value by qid; falls back to position index */
function getAnswerValue(
  ans: EvaluationAnswer,
  qid: string,
  fallbackIdx?: number,
): string | number | string[] | undefined {
  if (Array.isArray(ans.answers)) {
    const items = ans.answers as PersonaAnswerItem[];
    const item = items.find(a => a.qid === qid);
    if (item !== undefined) return item.answer;
    // Index fallback: AI sometimes uses sequential IDs that don't match survey qids
    if (fallbackIdx !== undefined && fallbackIdx < items.length) {
      return items[fallbackIdx].answer;
    }
    return undefined;
  }
  return (ans.answers as Record<string, string | number | string[]>)[qid];
}

/**
 * Build the display text for one persona.
 * Shows intent + summary + ALL answered Q&A pairs in question order.
 */
function buildPersonaText(questions: SurveyQuestion[], ans: EvaluationAnswer): string {
  const parts: string[] = [];

  // Intent stars
  const intent = ans.overall_intent || 0;
  if (intent >= 1 && intent <= 5) {
    parts.push(`整体意向：${'★'.repeat(intent)}${'☆'.repeat(5 - intent)}  ${intent}/5`);
  }

  // Summary comment (AI-generated natural language overview)
  if (ans.summary_comment) parts.push(ans.summary_comment);

  if (questions.length > 0) {
    const lines: string[] = [];
    questions.forEach((q, qi) => {
      const raw = getAnswerValue(ans, q.id, qi);
      if (raw === undefined || raw === null || raw === '') return;
      const label = q.question || q.text || ('第' + (qi + 1) + '题');
      lines.push(`问：${label}\n答：${formatAnswerQ(q, raw)}`);
    });
    if (lines.length) parts.push(lines.join('\n\n'));
  } else if (!ans.summary_comment) {
    // Fallback when no questions loaded
    const openTexts = Array.isArray(ans.answers)
      ? (ans.answers as PersonaAnswerItem[])
          .filter(a => typeof a.answer === 'string' && (a.answer as string).length > 5)
          .map(a => String(a.answer))
          .join('\n\n')
      : Object.values(ans.answers as Record<string, any>)
          .filter((v): v is string => typeof v === 'string' && v.length > 5)
          .join('\n\n');
    if (openTexts) parts.push(openTexts);
  }

  return parts.join('\n\n').trim();
}

function personaLabel(ans: EvaluationAnswer): string {
  return ans.persona_tag || '测品官群体';
}

/**
 * 把一个角色的 EvaluationAnswer 拆解为 QAItem[]，
 * 每道有作答的题目生成一条，包含题目、维度、答案、理由。
 */
function buildQAItems(questions: SurveyQuestion[], ans: EvaluationAnswer): import('../../types/domain').QAItem[] {
  const items: import('../../types/domain').QAItem[] = [];

  // 建立 qid → answerItem 映射
  const answerMap: Record<string, PersonaAnswerItem> = {};
  if (Array.isArray(ans.answers)) {
    (ans.answers as PersonaAnswerItem[]).forEach(a => { answerMap[a.qid] = a; });
  }

  // 逐题
  questions.forEach((q, qi) => {
    const raw = getAnswerValue(ans, q.id, qi);
    if (raw === undefined || raw === null || raw === '') return;
    const ansItem = answerMap[q.id] || (Array.isArray(ans.answers) ? (ans.answers as PersonaAnswerItem[])[qi] : undefined);
    const reason = ansItem?.reason || '';
    const type = q.type || 'open';
    const scaleValue = type === 'scale_1_5' ? Math.max(1, Math.min(5, Number(raw))) : undefined;
    const scaleDots = scaleValue
      ? ([1, 2, 3, 4, 5] as number[]).map(n => ({ filled: n <= scaleValue }))
      : undefined;
    items.push({
      question: q.question || q.text || `第${qi + 1}题`,
      dim: q.dim,
      type,
      answer: formatAnswerQ(q, raw as string | number | string[]),
      reason,
      scaleValue,
      scaleDots,
    });
  });

  // 若没有 questions 但有 summary，退化成一条
  if (items.length === 0 && ans.summary_comment) {
    items.push({ question: '综合评价', type: 'open', answer: ans.summary_comment, reason: '' });
  }

  return items;
}

function formatAnswerQ(q: SurveyQuestion, value: string | number | string[]): string {
  if (q.type === 'scale_1_5') {
    const n = Number(value);
    if (!n || n < 1 || n > 5) return String(value);
    return '★'.repeat(n) + '☆'.repeat(5 - n) + `  ${n} 分（满分 5 分）`;
  }
  if (q.type === 'single') {
    if (q.options && q.options.length > 0 && typeof q.options[0] === 'object') {
      const opts = q.options as { id: string; text: string }[];
      const opt = opts.find(o => o.id === value);
      if (opt) return opt.text;
    }
    return String(value);
  }
  if (q.type === 'multi' && Array.isArray(value)) {
    if (q.options && q.options.length > 0) {
      if (typeof q.options[0] === 'object') {
        const opts = q.options as { id: string; text: string }[];
        return (value as string[]).map(id => opts.find(o => o.id === id)?.text ?? id).join('、');
      }
      // Plain-string options: AI may return numeric indices or the text itself
      const strOpts = q.options as string[];
      return (value as string[]).map(v => {
        const n = Number(v);
        if (!isNaN(n) && Number.isInteger(n) && n >= 0 && n < strOpts.length) return strOpts[n];
        return v;
      }).join('、');
    }
    return (value as string[]).join('、');
  }
  return String(value);
}

Page({
  data: {
    autoPlay: false,
    autoPlayDone: false,
    showReportBtn: false,
    reportStatus: 'idle' as string,
    evalStatusText: '',
    evalProgress: 0,
    evalRemaining: 100,

    loading: true as boolean,
    conversationId: '',
    evaluationId: '',
    personaKey: 'yun' as PersonaKey,
    followPersonaId: '' as string,
    personaName: '',
    personaRole: '',
    productTitle: '',
    displayTitle: '',
    topicIndex: 0,
    topicTotal: 1,
    topicEmoji: '',
    topicLabel: '',
    topicPercent: 0,
    turns: [] as ChatTurn[],
    inputValue: '',
    sending: false,
    scrollTop: 0,
    showFollowUpTip: false,
    followUpPersonas: [] as Array<{ id: string; name: string; initial: string; tag: string }>,
    showFollowUpModal: false,
    pausedFollow: false,  // 用户上划暂停自动跟随时显示"跳到最新"按钮
  },

  activeStream:    null as StreamHandle | null,
  pollTimer:       null as ReturnType<typeof setTimeout> | null,
  typeTimer:       null as ReturnType<typeof setInterval> | null,
  pseudoProgTimer: null as ReturnType<typeof setInterval> | null,
  turnSeq:         0 as number,
  _atBottom:          true as boolean,   // whether scroll is at (or near) the bottom
  _touchStartY:       0 as number,       // Y position when finger first touched scroll-view
  _scrollTopSeed:     0 as number,       // monotonically grows so scroll-top always changes
  _currentScrollTop:  0 as number,       // last real scroll position from bindscroll
  _typingStopped:     false as boolean,  // set true on unload to stop typing loop

  // ─── 页面生命周期 ────────────────────────────────────────

  async onLoad(query: Record<string, string | undefined>) {
    const evalId          = query.evaluation_id || 'eval_001';
    const auto            = query.auto === '1';
    const starting        = query.starting === '1';
    const personaId       = query.persona_id || '';
    // persona_ids 存在 storage 里以避免 URL 编解码问题
    const personaIds: string[] = (() => {
      try {
        const raw = wx.getStorageSync('_pending_persona_ids');
        if (raw) { wx.removeStorageSync('_pending_persona_ids'); return JSON.parse(raw) as string[]; }
      } catch { /* ignore */ }
      return [];
    })();
    const surveyId        = query.survey_id || '';
    const productId       = query.product_id || '';
    const questionsChanged = query.questions_changed === '1';
    this.setData({ evaluationId: evalId, autoPlay: auto, followPersonaId: personaId });

    if (!USE_MOCK) {
      try { await api.ensureAuth(); } catch { /* ignore */ }
    }

    if (auto) {
      this.setData({
        loading: false,
        turns: [{
          id: 'status_main',
          kind: 'status' as const,
          content: '调研准备中',
          evalProgress: 0,
          evalRemaining: 100,
          evalStatus: 'pending',
        }],
      });
      this._startPseudoProgress();
      if (starting && personaIds.length > 0) {
        this._doStartupSetup(evalId, surveyId, productId, personaIds, questionsChanged);
      } else {
        this.pollEvaluation(evalId, 0);
      }
    } else {
      this.loadConversation(evalId, personaId);
    }
  },

  async _doStartupSetup(
    evalId: string, surveyId: string, productId: string,
    personaIds: string[], questionsChanged: boolean,
  ) {
    try {
      // 1. 确认 surveyId
      let sid = surveyId;
      if (!sid) {
        const evaluation = await api.getEvaluation(evalId);
        sid = evaluation.survey_id || '';
      }
      if (!sid) {
        const survey = await api.generateSurvey(evalId, productId);
        sid = survey.id;
      }

      // 2. 若有题目改动，更新问卷
      if (questionsChanged && sid) {
        try {
          const raw = wx.getStorageSync('_pending_questions');
          if (raw) {
            wx.removeStorageSync('_pending_questions');
            await api.updateSurveyQuestions(sid, JSON.parse(raw));
          }
        } catch { /* ignore */ }
      }

      // 3. 绑定测品官（409 = 已绑定，视为成功）
      await api.attachPersonas(evalId, personaIds).catch((err: any) => {
        if (err?.statusCode !== 409) throw err;
      });

      // 4. 启动评测
      await api.runEvaluation(evalId).catch(err => {
        console.error('[chat] runEvaluation failed', err);
      });
    } catch (err) {
      console.error('[chat] startup setup failed', err);
    }
    this.pollEvaluation(evalId, 0);
  },

  onUnload() {
    this._typingStopped = true;
    if (this.activeStream)    { this.activeStream.abort(); this.activeStream = null; }
    if (this.pollTimer)       { clearTimeout(this.pollTimer); this.pollTimer = null; }
    if (this.typeTimer)       { clearInterval(this.typeTimer!); this.typeTimer = null; }
    if (this.pseudoProgTimer) { clearInterval(this.pseudoProgTimer!); this.pseudoProgTimer = null; }
  },

  // ─── 伪进度动画（立即显示 3%，每秒更新，上限 90%） ────────────────
  _startPseudoProgress() {
    // 先渲染 0，60ms 后推到 5% 触发平滑入场动画
    setTimeout(() => {
      this.updateStatusTurn('调研准备中', 5, 'pending');
      this.pseudoProgTimer = setInterval(() => {
        const cur = this.data.evalProgress;
        if (cur >= 88) return;
        const step = cur < 40 ? 3 : cur < 70 ? 2 : 1;
        const next = Math.min(88, cur + step);
        this.updateStatusTurn(this.data.evalStatusText || '调研准备中', next, 'pending');
      }, 1000);
    }, 60);
  },

  _stopPseudoProgress() {
    if (this.pseudoProgTimer) {
      clearInterval(this.pseudoProgTimer!);
      this.pseudoProgTimer = null;
    }
  },

  // ─── 普通对话模式 ────────────────────────────────────────

  async loadConversation(evalId: string, personaId = '') {
    try {
      const [data, evaluation] = await Promise.all([
        api.getConversation(evalId, personaId || undefined),
        api.getEvaluation(evalId).catch(() => null),
      ]);

      const pName = data.conversation.persona_name;
      const pRole = data.persona_role || '测品官群体';
      const productTitle = data.conversation.title || '产品调研';
      const cleanTitle = productTitle.replace(/^关于/, '').slice(0, 10);
      const displayTitle = personaId
        ? `${pRole}关于产品的深度访谈`
        : `关于${cleanTitle}的访谈`;
      wx.setNavigationBarTitle({ title: displayTitle });

      this.setData({
        loading: false,
        conversationId: data.conversation.id,
        personaKey:  data.conversation.persona_avatar as PersonaKey,
        personaName: pRole,
        personaRole: pRole,
        productTitle,
        displayTitle,
        topicIndex:  data.current_topic.index,
        topicTotal:  data.current_topic.total,
        topicEmoji:  data.current_topic.emoji,
        topicLabel:  data.current_topic.label,
        topicPercent: Math.round((data.current_topic.index / data.current_topic.total) * 100),
        turns: data.turns,
      });

      if (evaluation?.status === 'done' && data.turns.length === 0 && personaId) {
        const [surveyRes, answers] = await Promise.all([
          evaluation.survey_id ? api.getSurvey(evaluation.survey_id).catch(() => null) : Promise.resolve(null),
          api.getEvaluationAnswers(evaluation.id, [personaId]).catch(() => [] as EvaluationAnswer[]),
        ]);
        const ans = answers.find(a => a.persona_id === personaId) || answers[0];
        if (ans) {
          const contextTurn = { ...this._buildCompletedQATurn(surveyRes?.questions ?? [], ans, 0, data.conversation.persona_avatar as PersonaKey), avatarSlot: 0 };
          const divider: ChatTurn = {
            id: 'divider_followup',
            kind: 'topic_switch',
            content: '',
            topic_from: '该角色调研内容',
            topic_to: '继续追问',
          };
          this.setData({
            turns: [contextTurn, divider],
            autoPlayDone: true,
            showReportBtn: true,
            reportStatus: 'ready',
          }, () => this.forceScrollToBottom());
          return;
        }
      }

      // Only auto-replay all-persona Q&A in the main evaluation view (no specific persona targeted)
      if (evaluation?.status === 'done' && data.turns.length === 0 && !personaId) {
        const [surveyRes, answers] = await Promise.all([
          evaluation.survey_id ? api.getSurvey(evaluation.survey_id).catch(() => null) : Promise.resolve(null),
          api.getEvaluationAnswers(evaluation.id, evaluation.selected_persona_ids).catch(() => []),
        ]);
        if (answers.length > 0) {
          this.renderCompletedQA(surveyRes?.questions ?? [], answers);
          return;
        }
      }

      if (evaluation?.status === 'done') {
        this.setData({ autoPlayDone: true, showReportBtn: true, reportStatus: 'ready' });
      }

      this.scrollToBottom();
    } catch (err: any) {
      this.setData({ loading: false });
      wx.showToast({ title: (err?.message || '加载失败').slice(0, 20), icon: 'none', duration: 3000 });
    }
  },

  // ─── 评测进度轮询 ────────────────────────────────────────

  pollEvaluation(evalId: string, attempts: number) {
    if (attempts > 150) {
      this._stopPseudoProgress();
      this.updateStatusTurn('评测超时，请返回重试', 0, 'failed');
      return;
    }
    this.pollTimer = setTimeout(async () => {
      try {
        const ev = await api.getEvaluation(evalId);
        // 真实进度比伪进度高时才接管（避免回退）
        const displayProg = Math.max(this.data.evalProgress, ev.progress);
        this.updateStatusTurn(
          STATUS_LABELS[ev.status] || '处理中…',
          displayProg,
          ev.status,
        );
        if (ev.status === 'done') {
          this._stopPseudoProgress();
          await this.onEvaluationDone(ev);
        } else if (ev.status === 'failed') {
          this._stopPseudoProgress();
        } else {
          if (ev.status === 'answering' && ev.progress > 0) {
            this.tryShowPartialAnswers(ev).catch(() => {});
          }
          this.pollEvaluation(evalId, attempts + 1);
        }
      } catch {
        this.pollEvaluation(evalId, attempts + 1);
      }
    }, 1500);
  },

  async tryShowPartialAnswers(ev: { id: string; survey_id: string | null; selected_persona_ids: string[]; progress: number }) {
    const answers = await api.getEvaluationAnswers(ev.id, ev.selected_persona_ids).catch(() => [] as EvaluationAnswer[]);
    if (!answers.length) return;

    const alreadyStreaming = this.data.turns.some(t => t.kind === 'speak');
    if (alreadyStreaming) return;

    const surveyRes = ev.survey_id
      ? await api.getSurvey(ev.survey_id).catch(() => null)
      : null;

    this.streamQA(surveyRes?.questions ?? [], answers, true);
  },

  updateStatusTurn(text: string, progress: number, status: string) {
    const safeProgress = Math.max(0, Math.min(100, Math.round(progress || 0)));
    const remaining = Math.max(0, 100 - safeProgress);
    const turns = this.data.turns.slice();
    const idx = turns.findIndex(t => t.id === 'status_main');
    const t: ChatTurn = {
      id: 'status_main',
      kind: 'status',
      content: text,
      evalProgress: safeProgress,
      evalRemaining: remaining,
      evalStatus: status,
    };
    if (idx >= 0) turns[idx] = t; else turns.unshift(t);
    this.setData({ turns, evalStatusText: text, evalProgress: safeProgress, evalRemaining: remaining });
  },

  // ─── 评测完成 ─────────────────────────────────────────────

  async onEvaluationDone(evaluation: { id: string; survey_id: string | null; selected_persona_ids: string[] }) {
    this.updateStatusTurn('正在加载调研结果…', 100, 'done');

    const [surveyRes, answers] = await Promise.all([
      evaluation.survey_id ? api.getSurvey(evaluation.survey_id).catch(() => null) : Promise.resolve(null),
      api.getEvaluationAnswers(evaluation.id, evaluation.selected_persona_ids).catch(() => [] as EvaluationAnswer[]),
    ]);

    let convId = '';
    try {
      const data = await api.getConversation(evaluation.id);
      convId = data.conversation.id;
      this.setData({
        personaKey:   data.conversation.persona_avatar as PersonaKey,
        personaName:  data.persona_role || '测品官群体',
        personaRole:  data.persona_role || '测品官群体',
        productTitle: data.conversation.title,
        displayTitle: `关于${(data.conversation.title || '产品调研').replace(/^关于/, '').slice(0, 10)}的访谈`,
      });
    } catch { /* ignore */ }
    if (convId) this.setData({ conversationId: convId });

    const questions: SurveyQuestion[] = surveyRes?.questions ?? [];
    const baseTurns = this.data.turns.filter(t => t.id !== 'status_main');

    // 立即静默预热报告缓存，和打字机动画并行，避免用户点「查看报告」时再等
    api.getBusinessReportByEval(evaluation.id)
      .then(report => {
        try {
          wx.setStorageSync(
            `business_report_cache_${evaluation.id}`,
            JSON.stringify({ report, productName: this.data.productTitle || '' }),
          );
        } catch { /* cache only */ }
      })
      .catch(() => {});

    // 评测完成后立即在后台预生成白皮书，用户到导出页时大概率已就绪
    api.generateWhitepaper({
      evaluation_id: evaluation.id,
      product_name: this.data.productTitle || '未命名产品',
    }).catch(() => {});

    this.setData({ turns: baseTurns, evalStatusText: '', evalProgress: 100, evalRemaining: 0 }, () => {
      if (answers.length === 0 && questions.length === 0) {
        this.setData({ autoPlayDone: true }, () => this.scrollToBottom());
        return;
      }

      this.setData({ reportStatus: 'ready' }, () => this.streamQA(questions, answers));
    });
  },

  onTapReport() {
    wx.navigateTo({ url: '/pages/report/report?evaluation_id=' + this.data.evaluationId });
  },

  // ─── 点击角色头像：进入单独追问对话 ─────────────────────

  onAvatarTap(e: any) {
    const { personaId } = e.detail;
    if (!personaId) return;
    wx.navigateTo({
      url: `/pages/chat/chat?evaluation_id=${this.data.evaluationId}&persona_id=${personaId}&auto=0`,
    });
  },

  noop() {},

  onDeleteConversation() {
    const convId = this.data.conversationId;
    if (!convId) return;
    wx.showModal({
      title: '删除对话',
      content: '确认删除这条对话记录吗？',
      confirmText: '删除',
      confirmColor: '#EF4444',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await api.deleteConversation(convId);
          wx.showToast({ title: '已删除', icon: 'success' });
          setTimeout(() => wx.navigateBack(), 800);
        } catch {
          wx.showToast({ title: '删除失败', icon: 'none' });
        }
      },
    });
  },

  // ─── Q&A 展示：instant=true 直接渲染，否则逐人打字机 ─────

  streamQA(questions: SurveyQuestion[], answers: EvaluationAnswer[], _instant = false) {
    if (!answers.length) {
      this.setData({ autoPlayDone: true, showReportBtn: true });
      return;
    }
    this.setData({ reportStatus: 'ready' });
    // 始终走逐题打字机路径，不再有 instant 捷径
    this.typeNextPersona(questions, answers, 0);
  },

  _buildCompletedQATurn(
    questions: SurveyQuestion[],
    ans: EvaluationAnswer,
    idx: number,
    personaKey?: PersonaKey,
  ): ChatTurn {
    const qaItems = buildQAItems(questions, ans).map(item => ({
      ...item,
      reasonDone: !!item.reason,
      reasonPreview: item.reason ? reasonPreview(item.reason) : '',
    }));
    return {
      id: `qa_done_${ans.persona_id || idx}`,
      kind: 'speak',
      persona_key: personaKey || PERSONA_KEYS[idx % PERSONA_KEYS.length],
      persona_name: personaLabel(ans),
      persona_id: ans.persona_id,
      avatarSlot: (idx % 10) + 1,
      summaryComment: ans.summary_comment || '',
      qaItems,
      content: '',
    };
  },

  renderCompletedQA(questions: SurveyQuestion[], answers: EvaluationAnswer[]) {
    const qaTurns = answers
      .map((ans, idx) => this._buildCompletedQATurn(questions, ans, idx))
      .filter(turn => (turn.qaItems || []).length > 0);
    const divider: ChatTurn = {
      id: 'divider_chat',
      kind: 'topic_switch',
      content: '',
      topic_from: '调研完成',
      topic_to: '可以继续追问',
    };
    const followUpPersonas = answers.map(a => ({
      id: a.persona_id,
      name: a.persona_tag || '测品官群体',
      initial: (a.persona_tag || '测').charAt(0),
      tag: a.persona_tag || '测品官群体',
      avatarSrc: avatarSrcForSeed(a.persona_id || a.persona_tag || ''),
    }));
    this.setData({
      autoPlay: false,
      autoPlayDone: true,
      showReportBtn: true,
      showFollowUpModal: false,
      followUpPersonas,
      reportStatus: 'ready',
      turns: [...qaTurns, divider],
    }, () => this.forceScrollToBottom());
  },

  // ─── 逐人打字机 ──────────────────────────────────────────

  _onAllPersonasDone(answers: EvaluationAnswer[]) {
    const followUpPersonas = answers.map(a => ({
      id: a.persona_id,
      name: a.persona_tag || '测品官群体',
      initial: (a.persona_tag || '测').charAt(0),
      tag: a.persona_tag || '测品官群体',
      avatarSrc: avatarSrcForSeed(a.persona_id || a.persona_tag || ''),
    }));
    this.setData({ followUpPersonas, showFollowUpModal: true });
  },

  onCloseFollowUpModal() {
    this.setData({ showFollowUpModal: false, showFollowUpTip: true });
  },

  onTapFollowUpPersona(e: any) {
    const { id } = e.currentTarget.dataset;
    if (!id) return;
    this.setData({ showFollowUpModal: false, showFollowUpTip: false });
    wx.navigateTo({
      url: `/pages/chat/chat?evaluation_id=${this.data.evaluationId}&persona_id=${id}&auto=0`,
    });
  },

  typeNextPersona(questions: SurveyQuestion[], answers: EvaluationAnswer[], idx: number) {
    if (idx >= answers.length) {
      this.setData({
        turns: [...this.data.turns, {
          id: 'divider_chat', kind: 'topic_switch' as const, content: '',
          topic_from: '调研完成', topic_to: '可以继续追问',
        }],
        autoPlayDone: true,
        showReportBtn: true,
      }, () => { this._syncPausedFollow(); this.scrollToBottom(); });
      this._onAllPersonasDone(answers);
      return;
    }

    const ans = answers[idx];
    const qaItems = buildQAItems(questions, ans);
    if (!qaItems.length) { this.typeNextPersona(questions, answers, idx + 1); return; }

    const bubbleId = `qa_${idx}`;
    // 先只插入第一题（answer/reason 为空），后续题目打字完成后逐一追加
    const isScale = qaItems[0].type === 'scale_1_5';
    const firstItem = {
      ...qaItems[0],
      question: '',
      answer: '',
      reason: '',
      reasonDone: false,
      reasonPreview: '',
      ...(isScale ? { scaleDots: [], scaleValue: 0 } : {}),
    };
    this.setData({
      turns: [...this.data.turns, {
        id: bubbleId,
        kind: 'speak' as const,
        persona_key: PERSONA_KEYS[idx % PERSONA_KEYS.length],
        persona_name: personaLabel(ans),
        persona_id: ans.persona_id,
        avatarSlot: (idx % 10) + 1,
        summaryComment: '',
        qaItems: [firstItem],
        content: '',
      }],
    }, () => this.scrollToBottom());

    this._typeSummaryComment(bubbleId, ans.summary_comment || '', () => {
      this._typeQAItems(bubbleId, qaItems, 0, questions, answers, idx);
    });
  },

  /** 将第 qIdx 题追加到气泡（answer 留空，scale 题保留圆点数据） */
  _appendQAItem(bubbleId: string, qaItems: any[], qIdx: number) {
    if (qIdx >= qaItems.length) return;
    const list = this.data.turns.slice();
    const ti = list.findIndex((t: any) => t.id === bubbleId);
    if (ti < 0) return;
    const item = qaItems[qIdx];
    const isScale = item.type === 'scale_1_5';
    const newItem = {
      ...item,
      question: '',
      answer: '',
      reason: '',
      reasonDone: false,
      reasonPreview: '',
      ...(isScale ? { scaleDots: [], scaleValue: 0 } : {}),
    };
    const updatedItems = [...(list[ti].qaItems as any[]), newItem];
    list[ti] = { ...list[ti], qaItems: updatedItems };
    this.setData({ turns: list }, () => this.scrollToBottom());
  },

  _typeSummaryComment(bubbleId: string, fullText: string, onDone: () => void) {
    if (!fullText) { onDone(); return; }
    let typed = 0;
    this.typeTimer = setInterval(() => {
      if (this._typingStopped) {
        clearInterval(this.typeTimer!);
        this.typeTimer = null;
        return;
      }
      if (typed >= fullText.length) {
        clearInterval(this.typeTimer!);
        this.typeTimer = null;
        onDone();
        return;
      }
      typed = Math.min(typed + 4, fullText.length);
      const list = this.data.turns.slice();
      const ti = list.findIndex(t => t.id === bubbleId);
      if (ti < 0) return;
      list[ti] = { ...list[ti], summaryComment: fullText.slice(0, typed) };
      this.setData({ turns: list }, () => this.scrollToBottom());
    }, 50);
  },

  _collapseReasons(bubbleId: string) {
    const list = this.data.turns.slice();
    const ti = list.findIndex(t => t.id === bubbleId);
    if (ti < 0) return;
    const updatedItems = ((list[ti].qaItems || []) as any[]).map(item => ({
      ...item,
      reasonDone: !!item.reason,
      reasonPreview: item.reason ? reasonPreview(item.reason) : '',
    }));
    list[ti] = { ...list[ti], qaItems: updatedItems };
    this.setData({ turns: list }, () => this.scrollToBottom());
  },

  /** 逐题打字机：题目直接显示，回答和作答依据逐字填入 */
  _typeQAItems(
    bubbleId: string,
    qaItems: any[],
    qIdx: number,
    questions: SurveyQuestion[],
    answers: EvaluationAnswer[],
    personaIdx: number,
  ) {
    if (qIdx >= qaItems.length) {
      this._collapseReasons(bubbleId);
      setTimeout(() => this.typeNextPersona(questions, answers, personaIdx + 1), 600);
      return;
    }

    const advance = () => {
      // 追加下一题后再开始打
      setTimeout(() => {
        this._appendQAItem(bubbleId, qaItems, qIdx + 1);
        this._typeQAItems(bubbleId, qaItems, qIdx + 1, questions, answers, personaIdx);
      }, 300);
    };

    const fullReason = qaItems[qIdx].reason || '';
    const fullAnswer = qaItems[qIdx].answer;
    const fullQuestion = qaItems[qIdx].question;
    const isScale = qaItems[qIdx].type === 'scale_1_5';
    const targetScaleValue = isScale ? qaItems[qIdx].scaleValue || 0 : 0;

    const typeField = (
      fullText: string,
      field: 'question' | 'reason' | 'answer',
      onDone: () => void,
    ) => {
      if (!fullText) { onDone(); return; }
      let typed = 0;
      this.typeTimer = setInterval(() => {
        if (this._typingStopped) {
          clearInterval(this.typeTimer!);
          this.typeTimer = null;
          return;
        }
        if (typed >= fullText.length) {
          clearInterval(this.typeTimer!);
          this.typeTimer = null;
          onDone();
          return;
        }
        typed = Math.min(typed + 4, fullText.length);
        const list = this.data.turns.slice();
        const ti = list.findIndex(t => t.id === bubbleId);
        if (ti < 0) return;
        const updatedItems = (list[ti].qaItems as any[]).slice();
        updatedItems[qIdx] = {
          ...updatedItems[qIdx],
          [field]: fullText.slice(0, typed),
          ...(field === 'reason' ? { reasonDone: false, reasonPreview: '' } : {}),
        };
        list[ti] = { ...list[ti], qaItems: updatedItems };
        this.setData({ turns: list }, () => this.scrollToBottom());
      }, 50);
    };

    if (isScale && targetScaleValue > 0) {
      typeField(fullQuestion, 'question', () => {
        this._typeScaleDots(bubbleId, qIdx, targetScaleValue, () => {
          typeField(fullReason, 'reason', advance);
        });
      });
    } else {
      typeField(fullQuestion, 'question', () => {
        typeField(fullAnswer, 'answer', () => {
          typeField(fullReason, 'reason', advance);
        });
      });
    }
  },

  /** 评分题圆点逐颗点亮 + scaleValue 递增 */
  _typeScaleDots(bubbleId: string, qIdx: number, targetValue: number, onDone: () => void) {
    let step = 0;
    this.typeTimer = setInterval(() => {
      if (this._typingStopped) {
        clearInterval(this.typeTimer!);
        this.typeTimer = null;
        return;
      }
      step++;
      if (step > targetValue) {
        clearInterval(this.typeTimer!);
        this.typeTimer = null;
        onDone();
        return;
      }
      const list = this.data.turns.slice();
      const ti = list.findIndex(t => t.id === bubbleId);
      if (ti < 0) return;
      const updatedItems = (list[ti].qaItems as any[]).slice();
      updatedItems[qIdx] = {
        ...updatedItems[qIdx],
        scaleValue: step,
        scaleDots: ([1, 2, 3, 4, 5] as number[]).map(n => ({ filled: n <= step })),
      };
      list[ti] = { ...list[ti], qaItems: updatedItems };
      this.setData({ turns: list }, () => this.scrollToBottom());
    }, 250);
  },

  // ─── 滚动辅助 ────────────────────────────────────────────

  /** 用户主动操作（发消息、页面加载）触发——立即贴底并恢复跟随。 */
  scrollToBottom() {
    if (!this._atBottom) return;
    wx.nextTick(() => {
      this._scrollTopSeed += 9999;
      this.setData({ scrollTop: this._scrollTopSeed });
    });
  },

  forceScrollToBottom() {
    this._atBottom = true;
    this._syncPausedFollow();
    wx.nextTick(() => {
      this._scrollTopSeed += 9999;
      this.setData({ scrollTop: this._scrollTopSeed });
    });
  },

  /** 实时记录 scroll-view 真实滚动位置，供上划暂停时钉住用。 */
  onScroll(e: any) {
    this._currentScrollTop = e.detail?.scrollTop ?? this._currentScrollTop;
  },

  /** 记录手指落点 Y，用于判断滑动方向。 */
  onScrollTouchStart(e: any) {
    this._touchStartY = e.touches[0]?.clientY ?? 0;
  },

  /** 手指向上移动（内容向上滚，查看旧消息）超过 8px，停止自动追随并固定在当前位置。
   *  关键：把 scrollTop 钉到当前真实位置，避免大值在内容增长时被 clamp 到新底部。 */
  onScrollTouchMove(e: any) {
    const dy = (e.touches[0]?.clientY ?? 0) - this._touchStartY;
    if (dy < -8 && this._atBottom) {
      this._atBottom = false;
      // 钉住当前滚动位置，防止内容增长时 scroll-view 自动跟底
      this.setData({ scrollTop: Math.round(this._currentScrollTop) });
      this._syncPausedFollow();
    }
  },

  /** scroll-view bindscrolltolower：内容到达底部，恢复自动追随。 */
  onScrollToLower() {
    this._atBottom = true;
    this._syncPausedFollow();
  },

  /** 同步 pausedFollow 数据：仅在 autoPlay 未完成时才显示"跳到最新"提示。 */
  _syncPausedFollow() {
    const paused = !this._atBottom && this.data.autoPlay && !this.data.autoPlayDone;
    if (paused !== this.data.pausedFollow) {
      this.setData({ pausedFollow: paused });
    }
  },

  /** 用户点击"跳到最新"按钮：强制回底并恢复自动跟随。 */
  onBackToBottom() {
    this.forceScrollToBottom();
  },

  /** scroll-guide 上箭头：暂停自动跟随，向上滚动一屏约 60% */
  onScrollGuideUp() {
    this._atBottom = false;
    this._syncPausedFollow();
    const step = Math.round(wx.getWindowInfo().windowHeight * 0.6);
    const next = Math.max(0, this._currentScrollTop - step);
    this._currentScrollTop = next;
    this.setData({ scrollTop: next });
  },

  /** scroll-guide 下箭头：恢复自动跟随并跳到最新输出 */
  onScrollGuideDown() {
    this.forceScrollToBottom();
  },

  // ─── 用户追问（流式） ────────────────────────────────────

  nextId(): string {
    this.turnSeq++;
    return 'u' + Date.now() + '_' + this.turnSeq;
  },

  onInputChange(e: any) {
    this.setData({ inputValue: e.detail.value });
  },

  onSend() {
    const text = this.data.inputValue.trim();
    if (!text || this.data.sending) return;
    if (this.data.autoPlay && !this.data.autoPlayDone) return;

    const userTurn: ChatTurn = { id: this.nextId(), kind: 'user', content: text };
    const bubbleId = this.nextId();

    this.setData({
      turns: [
        ...this.data.turns, userTurn,
        { id: bubbleId, kind: 'speak' as const, persona_key: this.data.personaKey, persona_name: this.data.personaName, persona_id: this.data.followPersonaId, thinkContent: '', content: '' },
      ],
      inputValue: '',
      sending: true,
    }, () => this.forceScrollToBottom());

    let accThink = '';
    let accContent = '';

    this.activeStream = api.sendMessageStream(this.data.conversationId, text, {
      onEvent: (evt) => {
        if (evt.event === 'think_delta') {
          accThink += (evt as any).content || '';
        } else if (evt.event === 'delta') {
          accContent += (evt as any).content || '';
        } else {
          return;
        }
        const list = this.data.turns.slice();
        const idx  = list.findIndex((t: ChatTurn) => t.id === bubbleId);
        if (idx < 0) return;
        list[idx] = { ...list[idx], thinkContent: accThink, content: accContent };
        this.setData({ turns: list }, () => this.scrollToBottom());
      },
      onDone:  () => { this.setData({ sending: false }, () => this.scrollToBottom()); this.activeStream = null; },
      onError: () => { this.setData({ sending: false }); this.activeStream = null; wx.showToast({ title: '回复失败', icon: 'none' }); },
    });
  },
});
