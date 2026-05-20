import { api, USE_MOCK } from '../../services/api';
import type { SurveyQuestion, PersonaSummary, Survey } from '../../types/api';
import type { StreamHandle } from '../../services/stream';

/** Assign avatars sequentially per gender to avoid duplicates.
 *  female → 01-05 cycling, male → 06-10 cycling */
function assignAvatars(
  personas: PersonaSummary[],
): Array<PersonaSummary & { selected: boolean; avatarSrc: string }> {
  let femaleIdx = 0;
  let maleIdx = 0;
  return personas.map(p => {
    const isMale = p.gender === 'male';
    let slot: number;
    if (isMale) {
      slot = (maleIdx % 5) + 6;
      maleIdx++;
    } else {
      slot = (femaleIdx % 5) + 1;
      femaleIdx++;
    }
    const avatarSrc = `/assets/persona-avatars/avatar-${String(slot).padStart(2, '0')}.png`;
    return { ...p, selected: false, avatarSrc };
  });
}

type EditableQuestion = SurveyQuestion & { changed?: boolean };

Page({
  data: {
    loading: true,
    questionsLoading: false,
    genProgress: 0,
    genRemaining: 100,
    genMsg: '正在连接…',
    confirming: false,
    evaluationId: '',
    productId: '',
    surveyId: '',
    questions: [] as EditableQuestion[],
    questionsExpanded: false,
    personas: [] as Array<PersonaSummary & { selected: boolean }>,
    selectedCount: 0,
    editingIdx: -1,
    editingText: '',
    questionsChanged: false,
  },

  pollTimer: null as ReturnType<typeof setTimeout> | null,
  progressTimer: null as ReturnType<typeof setInterval> | null,
  streamHandle: null as StreamHandle | null,

  async onLoad(query: Record<string, string | undefined>) {
    const evalId    = query.evaluation_id || '';
    const productId = query.product_id || '';
    const generating = query.generating === '1';
    const focus = decodeURIComponent(query.focus || '');
    if (!evalId || !productId) { wx.navigateBack(); return; }
    this.setData({ evaluationId: evalId, productId });
    wx.setNavigationBarTitle({ title: '确认调研方案' });
    if (generating) {
      this.setData({ loading: false, questionsLoading: true, genProgress: 0, genRemaining: 100, genMsg: '正在连接…' });
      this.loadPersonas(productId);
      if (USE_MOCK) {
        // mock 模式：直接轮询
        setTimeout(() => this.setData({ genProgress: 5, genRemaining: 95 }), 60);
        this._startProgressAnimation(5);
        this.pollSurvey(evalId, productId, 0);
      } else {
        // 真实模式：SSE 流式进度
        this._startSurveyStream(evalId, productId, focus);
      }
    } else {
      await this.loadData(evalId, productId);
    }
  },

  onUnload() {
    if (this.pollTimer)    { clearTimeout(this.pollTimer);    this.pollTimer    = null; }
    if (this.progressTimer){ clearInterval(this.progressTimer); this.progressTimer = null; }
    if (this.streamHandle) { this.streamHandle.abort();        this.streamHandle  = null; }
  },

  // ── SSE 流式生成 ───────────────────────────────────────────────

  _startSurveyStream(evalId: string, productId: string, focus: string) {
    this.streamHandle = api.generateSurveyStream(evalId, productId, focus, {
      onProgress: (pct: number, msg: string) => {
        if (this.progressTimer) { clearInterval(this.progressTimer); this.progressTimer = null; }
        this.setData({ genProgress: pct, genMsg: msg });
        this._startProgressAnimation(pct);
      },
      onDone: (surveyId: string) => {
        this.streamHandle = null;
        this._finishGeneration(surveyId);
      },
      onError: (err: Error) => {
        console.warn('[survey-review] SSE error, falling back to poll:', err);
        this.streamHandle = null;
        // 降级到轮询
        this._startProgressAnimation(this.data.genProgress || 5);
        this.pollSurvey(evalId, productId, 0);
      },
    });
  },

  // ── 伪进度动画（在两次真实事件之间平滑推进） ───────────────────

  _startProgressAnimation(fromPct: number) {
    if (this.progressTimer) { clearInterval(this.progressTimer); this.progressTimer = null; }
    this.progressTimer = setInterval(() => {
      const cur = this.data.genProgress;
      if (cur >= 88) return;
      const step = cur < 40 ? 3 : cur < 70 ? 2 : 1;
      const next = Math.min(88, cur + step);
      this.setData({ genProgress: next, genRemaining: 100 - next });
    }, 1000);
    // 立即同步到起始值
    if (fromPct > this.data.genProgress) {
      this.setData({ genProgress: fromPct, genRemaining: 100 - fromPct });
    }
  },

  _finishGeneration(surveyId: string) {
    if (this.progressTimer) { clearInterval(this.progressTimer); this.progressTimer = null; }
    this.setData({ genProgress: 100, genRemaining: 0, genMsg: '问卷生成完成' });
    // 加载题目，等进度条动画播完再显示
    api.getSurvey(surveyId).then((survey: Survey) => {
      setTimeout(() => {
        this.setData({
          loading: false,
          questionsLoading: false,
          surveyId: survey.id,
          questions: survey.questions,
        });
      }, 1300);
    }).catch(() => {
      // 直接用 surveyId 存着，onConfirm 时会二次拉取
      setTimeout(() => {
        this.setData({ loading: false, questionsLoading: false, surveyId });
      }, 1300);
    });
  },

  // ── 轮询兜底（mock / SSE 失败时使用） ─────────────────────────

  pollSurvey(evalId: string, productId: string, attempts: number) {
    if (attempts > 90) {
      if (this.progressTimer) { clearInterval(this.progressTimer); this.progressTimer = null; }
      this.setData({ loading: false, questionsLoading: false });
      wx.showToast({ title: '问卷生成超时，请重试', icon: 'none' });
      return;
    }
    this.pollTimer = setTimeout(async () => {
      try {
        const evaluation = await api.getEvaluation(evalId);
        if (evaluation.survey_id) {
          const survey = await api.getSurvey(evaluation.survey_id);
          this._finishGeneration(survey.id);
          this.setData({ questions: survey.questions });
        } else {
          this.pollSurvey(evalId, productId, attempts + 1);
        }
      } catch {
        this.pollSurvey(evalId, productId, attempts + 1);
      }
    }, 1000);
  },

  // ── 加载数据（已有问卷场景） ──────────────────────────────────

  async loadPersonas(productId: string) {
    try {
      const personas = await api.recommendPersonas(productId, 20);
      const decorated = assignAvatars(personas);
      this.setData({ personas: decorated, selectedCount: 0 });
    } catch { /* ignore */ }
  },

  async loadData(evalId: string, productId: string) {
    try {
      const evaluation = await api.getEvaluation(evalId);
      const surveyId = evaluation.survey_id || '';

      const [survey, personas] = await Promise.all([
        surveyId
          ? api.getSurvey(surveyId)
          : Promise.resolve({ id: '', questions: [] } as Survey),
        api.recommendPersonas(productId, 20),
      ]);

      const decorated = assignAvatars(personas);
      this.setData({
        loading: false,
        surveyId: survey.id,
        questions: survey.questions,
        personas: decorated,
        selectedCount: 0,
      });
    } catch (err: any) {
      this.setData({ loading: false });
      wx.showToast({ title: (err?.message || '加载失败').slice(0, 20), icon: 'none' });
    }
  },

  // ── 题目编辑 ──────────────────────────────────────────────────

  onTogglePersona(e: any) {
    const idx = Number(e.currentTarget.dataset.idx);
    const personas = this.data.personas.slice();
    personas[idx] = { ...personas[idx], selected: !personas[idx].selected };
    const count = personas.filter(p => p.selected).length;
    this.setData({ personas, selectedCount: count });
  },

  onTapQuestion(e: any) {
    const idx = Number(e.currentTarget.dataset.idx);
    if (this.data.editingIdx === idx) return;
    const q = this.data.questions[idx];
    this.setData({ editingIdx: idx, editingText: q.question || q.text || '' });
  },

  onEditQuestionInput(e: any) {
    this.setData({ editingText: e.detail.value });
  },

  onSaveQuestion(e: any) {
    e.stopPropagation();
    const idx = this.data.editingIdx;
    if (idx < 0) return;
    const text = this.data.editingText.trim();
    if (!text) return;
    const questions = this.data.questions.slice() as EditableQuestion[];
    questions[idx] = { ...questions[idx], question: text, text, changed: true };
    this.setData({ questions, editingIdx: -1, editingText: '', questionsChanged: true });
  },

  onCancelEditQuestion(e: any) {
    e.stopPropagation();
    this.setData({ editingIdx: -1, editingText: '' });
  },

  onToggleQuestions() {
    if (this.data.questionsLoading || !this.data.questions.length) return;
    this.setData({ questionsExpanded: !this.data.questionsExpanded, editingIdx: -1, editingText: '' });
  },

  // ── 确认启动调研 ──────────────────────────────────────────────

  async onConfirm() {
    if (this.data.confirming || this.data.questionsLoading) return;
    if (this.data.editingIdx >= 0) this.setData({ editingIdx: -1 });

    const selectedIds = this.data.personas.filter(p => p.selected).map(p => p.id);
    if (selectedIds.length === 0) {
      wx.showToast({ title: '请至少选择一位测品官', icon: 'none' });
      return;
    }

    this.setData({ confirming: true });
    wx.showLoading({ title: '检查问卷…' });
    try {
      let surveyId = this.data.surveyId;
      if (!surveyId) {
        const evaluation = await api.getEvaluation(this.data.evaluationId);
        surveyId = evaluation.survey_id || '';
      }
      if (!surveyId) {
        const survey = await api.generateSurvey(this.data.evaluationId, this.data.productId);
        surveyId = survey.id;
        this.setData({ surveyId, questions: survey.questions || [], genProgress: 100, genRemaining: 0 });
      }

      if (this.data.questionsChanged && surveyId && this.data.questions.length > 0) {
        await api.updateSurveyQuestions(surveyId, this.data.questions);
      }

      wx.showLoading({ title: '分配测品官…' });
      await api.attachPersonas(this.data.evaluationId, selectedIds);

      wx.hideLoading();
      api.runEvaluation(this.data.evaluationId).catch(err => {
        console.error('[survey-review] runEvaluation kick-off failed', err);
      });
      wx.redirectTo({
        url: `/pages/chat/chat?evaluation_id=${this.data.evaluationId}&auto=1`,
      });
    } catch (err: any) {
      wx.hideLoading();
      this.setData({ confirming: false });
      wx.showToast({ title: (err?.message || '启动失败').slice(0, 20), icon: 'none' });
    }
  },
});
