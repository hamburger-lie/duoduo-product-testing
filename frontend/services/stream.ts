// 流式协议
// Phase A: startMockStream — setInterval 模拟逐字推送
// Phase B: startRealStream — wx.request enableChunked 接收真实 SSE

import type { StreamEvent } from '../types/api';

export interface StreamHandle {
  abort: () => void;
}

export interface StreamHandlers {
  onEvent(evt: StreamEvent): void;
  onError?(err: Error): void;
  onDone?(): void;
}

export interface MockStreamScript {
  think?: string;   // 内心独白文本
  speak: string;    // 表达文本
  /** 每个 token 间隔毫秒 */
  intervalMs?: number;
  /** 每次 emit 的字符数 */
  chunkSize?: number;
}

// ---------- helpers ----------

function arrayBufferToText(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let raw = '';
  for (let i = 0; i < bytes.length; i++) {
    raw += String.fromCharCode(bytes[i]);
  }
  try { return decodeURIComponent(escape(raw)); } catch { return raw; }
}

// ---------- Phase A ----------

/** Phase A：用脚本驱动模拟流。Phase B 调真接口时替换。 */
export function startMockStream(script: MockStreamScript, h: StreamHandlers): StreamHandle {
  const interval = script.intervalMs ?? 40;
  const chunk = script.chunkSize ?? 2;
  let cancelled = false;

  const queue: StreamEvent[] = [];

  // 1) think 流（如果有）
  if (script.think) {
    const t = script.think;
    for (let i = 0; i < t.length; i += chunk) {
      queue.push({ event: 'think_delta', content: t.slice(i, i + chunk) });
    }
  }
  // 2) speak 流
  const s = script.speak;
  for (let i = 0; i < s.length; i += chunk) {
    queue.push({ event: 'delta', content: s.slice(i, i + chunk) });
  }
  // 3) meta + done
  queue.push({
    event: 'meta',
    message_id: 'mock_' + Date.now(),
    tokens: { input: 100, output: s.length },
    cost_yuan: 0,
  });
  queue.push({ event: 'done' });

  const timer = setInterval(() => {
    if (cancelled) return;
    const evt = queue.shift();
    if (!evt) {
      clearInterval(timer);
      h.onDone && h.onDone();
      return;
    }
    h.onEvent(evt);
    if (evt.event === 'done') {
      clearInterval(timer);
      h.onDone && h.onDone();
    }
  }, interval);

  return {
    abort() {
      cancelled = true;
      clearInterval(timer);
    },
  };
}

// ---------- Phase B ----------

/**
 * Phase B：用 wx.request enableChunked 接收真实 SSE。
 * @param url  完整请求 URL（含 BASE_URL + /api/v1/...）
 * @param body POST body
 * @param headers  含 Authorization 的请求头
 */
export function startRealStream(
  url: string,
  body: unknown,
  headers: Record<string, string>,
  h: StreamHandlers,
): StreamHandle {
  let aborted = false;
  let textBuffer = '';

  const task = (wx.request as any)({
    url,
    method: 'POST',
    data: body as any,
    header: headers,
    enableChunked: true,
    timeout: 300000, // 5 分钟，AI 生成可能较慢
    success(res: any) {
      // enableChunked=true 时，错误体可能在 res.data 也可能在 textBuffer
      if (res && res.statusCode && (res.statusCode < 200 || res.statusCode >= 300)) {
        if (!aborted) {
          let msg = `stream failed: HTTP ${res.statusCode}`;
          let errData: any = {};

          // 1) 先看 res.data（非分块错误响应通常在这里）
          if (res.data) {
            if (typeof res.data === 'string') {
              try { errData = JSON.parse(res.data); } catch { errData = { raw: res.data }; }
            } else if (typeof res.data === 'object') {
              errData = res.data;
            }
          }
          // 2) 再看 textBuffer（onChunkReceived 收来的）
          if (!errData?.message && !errData?.detail && !errData?.error && textBuffer) {
            try { errData = JSON.parse(textBuffer); } catch { errData = { raw: textBuffer }; }
          }

          const code = errData?.code || errData?.error?.code || '';
          const detail = errData?.message || errData?.detail || errData?.error?.message;
          if (detail) msg = `[${res.statusCode}] ${code} ${detail}`;

          console.error('[stream] backend error full:', {
            url,
            statusCode: res.statusCode,
            requestBody: body,
            resData: res.data,
            textBuffer,
            parsed: errData,
          });
          h.onError?.(new Error(msg));
        }
      }
    },
    fail(err: any) {
      if (!aborted) h.onError?.(new Error(err.errMsg || 'stream request failed'));
    },
  }) as WechatMiniprogram.RequestTask;

  (task as any).onChunkReceived((res: { data: ArrayBuffer }) => {
    if (aborted) return;
    textBuffer += arrayBufferToText(res.data);
    const lines = textBuffer.split('\n');
    textBuffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const json = line.slice(5).trim();
      if (!json) continue;
      try {
        const evt = JSON.parse(json) as StreamEvent;
        h.onEvent(evt);
        if (evt.event === 'done') h.onDone?.();
      } catch { /* ignore malformed chunks */ }
    }
  });

  return {
    abort() {
      aborted = true;
      task.abort();
    },
  };
}
