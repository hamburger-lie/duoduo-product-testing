# 技术实现文档：聊天视图跟随内容滚动

**关联需求**：[2026-05-16-scroll-follow-requirement.md](./2026-05-16-scroll-follow-requirement.md)
**作者**：Claude
**创建日期**：2026-05-16
**核心代码**：`miniprogram/pages/chat/chat.ts` / `chat.wxml`

---

## 1. 实现原理

### 1.1 scroll-view 自动滚到底的本质

`scroll-view` 的 `scroll-top` 属性表示「内容顶部到视口顶部的距离」。要让视图始终显示内容底部，等价于设置：

```
scrollTop = 内容总高度 − scroll-view 容器高度
```

示意：

```
┌──────────────────────────┐  ← 内容顶部（scrollTop=0 时这里在视口顶部）
│                          │
│   ↑ scrollTop 距离       │
│                          │
│  ┌───────────────────┐   │  ← 视口顶部
│  │                   │   │
│  │  scroll-view      │   │
│  │   可视区域         │   │
│  │   (高度 H_view)    │   │
│  │                   │   │
│  └───────────────────┘   │  ← 视口底部 = 内容底部
└──────────────────────────┘  ← 内容底部（高度 H_content）

H_content = H_view + scrollTop
=> scrollTop = H_content − H_view
```

只要在每次内容追加后重新测量 `H_content` 并更新 `scrollTop`，视图就自动跟随。

### 1.2 为什么必须用 `wx.createSelectorQuery`

- 内容高度 (`H_content`) 随打字机/SSE 动态增长，无法用静态值；
- WeChat 没有同步 API 获取元素高度，必须走 `createSelectorQuery().boundingClientRect()`（异步）；
- **Page 实例必须用 `wx.createSelectorQuery().in(this)`，而不是 `this.createSelectorQuery()`**——后者只有 Component 实例才有，Page 上调用会静默失败（这是真机一直不滚的真凶）。

### 1.3 为什么需要 prop 抖动

WeChat 的 `scroll-view` 在 `scroll-top` 接收到「与上次相同的值」时不会重新触发滚动。
打字机 50ms tick 内容只多几个字符，且内容若包在同一行内（不换行），`H_content` 可能不变，算出的 `scrollTop` 也不变 → 滚动被跳过。

解决：在 `scrollTop` 上叠加一个 0/1 交替的微小抖动，保证 prop 始终变化。

---

## 2. WXML 结构

```xml
<scroll-view
  class="messages"
  scroll-y="{{true}}"
  scroll-top="{{scrollTop}}"
  scroll-with-animation="{{true}}"
  enhanced="{{true}}"
  lower-threshold="100"
  bindtouchstart="onScrollTouchStart"
  bindtouchmove="onScrollTouchMove"
  bindscrolltolower="onScrollToLower"
>
  <view id="messages-inner" class="messages-inner">
    <!-- 所有消息气泡 -->
    <block wx:for="{{turns}}" wx:key="id">
      <view id="turn-{{item.id}}">...</view>
    </block>
    <view class="bottom-spacer"></view>
  </view>
</scroll-view>
```

关键点：

| 属性 | 必须值 | 理由 |
|------|--------|------|
| `scroll-top` | `{{scrollTop}}` | 单一受控滚动入口 |
| `scroll-with-animation` | `true` | 同值时只有开启动画才会重触发；`false` 配合相同值完全不滚 |
| `enhanced` | `true` | 启用 iOS 边界弹性、更平滑滚动 |
| `lower-threshold` | `100` | 距底 100rpx 内触发 `scrolltolower` 恢复自动追随 |
| 内层 `#messages-inner` | 必须有 | 用作测量「内容总高度」的目标 |
| `bindtouchstart` / `bindtouchmove` | 必须 | 检测用户主动上拉，暂停自动跟随 |
| `bindscrolltolower` | 必须 | 用户拖回底部时恢复跟随 |

⚠️ 不要同时设置 `scroll-into-view`——文档明确「scroll-into-view 优先级高于 scroll-top」，并存会让 `scroll-top` 失效。

---

## 3. TS 核心实现

### 3.1 Page data 与实例变量

```ts
Page({
  data: {
    scrollTop: 0,
    // ... 其他业务字段
  },

  _atBottom: true as boolean,        // 是否处于「贴底」状态，决定要不要自动追随
  _touchStartY: 0 as number,         // 触摸起点 Y，用于判断上滑
  _scrollTick: 0 as number,          // 0/1 交替，scrollTop prop 抖动
  typeTimer: null as ReturnType<typeof setInterval> | null,
  // ...
});
```

### 3.2 核心方法：测量并滚到底

> 参考文章方案，但与项目集成。

```ts
/**
 * 异步测量 scroll-view 容器和内部容器高度，
 * 算出 scrollTop = content高度 − 容器高度，加微小抖动确保 prop 变化。
 * 返回 Promise，便于串行化。
 */
_handleScrollTop(): Promise<void> {
  return new Promise(resolve => {
    if (!this._atBottom) { resolve(); return; }

    // Page 实例必须用 wx.createSelectorQuery().in(this)
    const query = wx.createSelectorQuery().in(this);
    query.select('.messages').boundingClientRect();
    query.select('#messages-inner').boundingClientRect();
    query.exec((res: any[]) => {
      const viewRect = res?.[0];
      const contentRect = res?.[1];
      if (!viewRect || !contentRect || !this._atBottom) {
        resolve();
        return;
      }
      // 内容比容器低时无需滚动
      if (contentRect.height <= viewRect.height) {
        resolve();
        return;
      }
      this._scrollTick = (this._scrollTick + 1) % 2;
      const nextTop = Math.ceil(contentRect.height - viewRect.height) + this._scrollTick;
      this.setData({ scrollTop: nextTop }, () => resolve());
    });
  });
},
```

### 3.3 入口：内部 / 外部调用

```ts
/** 流式输出 / 打字机内部触发——尊重用户上滑状态 */
_scrollToBottom() {
  // _handleScrollTop 自己会判 _atBottom，这里只是语义入口
  this._handleScrollTop();
},

/** 用户主动行为（发送、加载完成）触发——强制贴底并恢复追随 */
scrollToBottom() {
  this._atBottom = true;
  this._handleScrollTop();
},
```

### 3.4 智能暂停：触摸事件

```ts
onScrollTouchStart(e: any) {
  this._touchStartY = e.touches[0]?.clientY ?? 0;
},

/**
 * dy > 8 表示手指向下移动（视觉上内容上滑，用户在看较早内容）。
 * 阈值 8px 避免普通点击/微动误触发。
 */
onScrollTouchMove(e: any) {
  const dy = (e.touches[0]?.clientY ?? 0) - this._touchStartY;
  if (dy > 8) {
    this._atBottom = false;
  }
},

/** 拖回底部时（lower-threshold=100rpx 内）恢复自动追随 */
onScrollToLower() {
  this._atBottom = true;
},
```

### 3.5 集成点 A：打字机（逐字渲染）

文章原方案是 `setTimeout(20ms)` 递归 + `await handleScollTop` 串行化。我们的项目用 `setInterval(50ms)`，已有天然节流，不需要严格串行；但每帧 setData 完成的 callback 里调用 `_scrollToBottom` 即可：

```ts
typeNextPersona(questions: SurveyQuestion[], answers: EvaluationAnswer[], idx: number) {
  // ... 省略边界条件
  const fullText = buildPersonaText(questions, answers[idx]);
  const bubbleId = `qa_${idx}`;

  this.setData({
    turns: [...this.data.turns, {
      id: bubbleId,
      kind: 'speak' as const,
      // ...
      content: '',
    }],
  }, () => this._scrollToBottom());      // 新气泡出现先滚一次

  let typed = 0;
  this.typeTimer = setInterval(() => {
    if (typed >= fullText.length) {
      clearInterval(this.typeTimer!);
      this.typeTimer = null;
      setTimeout(() => this.typeNextPersona(questions, answers, idx + 1), 600);
      return;
    }
    typed = Math.min(typed + 4, fullText.length);
    const list = this.data.turns.slice();
    const i = list.findIndex(t => t.id === bubbleId);
    if (i < 0) return;
    list[i] = { ...list[i], content: fullText.slice(0, typed) };
    this.setData({ turns: list }, () => this._scrollToBottom());  // 渲染后追随
  }, 50);
},
```

### 3.6 集成点 B：用户追问 SSE

```ts
this.activeStream = api.sendMessageStream(this.data.conversationId, text, {
  onEvent: (evt) => {
    if (evt.event === 'think_delta')      accThink += evt.content || '';
    else if (evt.event === 'delta')       accContent += evt.content || '';
    else return;

    const list = this.data.turns.slice();
    const idx = list.findIndex(t => t.id === bubbleId);
    if (idx < 0) return;
    list[idx] = { ...list[idx], thinkContent: accThink, content: accContent };
    this.setData({ turns: list }, () => this._scrollToBottom());
  },
  // ...
});
```

### 3.7 集成点 C：初始加载

```ts
async loadConversation(evalId: string, personaId = '') {
  // ... 拉取数据并 setData(turns)
  this.setData({ turns: data.turns }, () => this.scrollToBottom());
  //                                       ↑ 用强制版，无视 _atBottom
}
```

---

## 4. 性能优化

### 4.1 节流策略

打字机 50ms 一次 setData，每次都触发一次 `createSelectorQuery` 异步测量。在大量消息场景下（>50 气泡），单次测量 ~5-15ms，可能堆积。

策略：

| 场景 | 频率 |
|------|------|
| 流式 SSE 内（每个 delta） | 每帧都调（delta 通常 100ms+ 一次，不会堆积） |
| 打字机（50ms tick） | 每帧都调（实测真机 OK） |
| 极端高频（<30ms） | 加节流：上次测量未完成则跳过 |

简单节流版本：

```ts
_pendingMeasure: false as boolean,

_handleScrollTop(): Promise<void> {
  return new Promise(resolve => {
    if (!this._atBottom || this._pendingMeasure) { resolve(); return; }
    this._pendingMeasure = true;
    const query = wx.createSelectorQuery().in(this);
    query.select('.messages').boundingClientRect();
    query.select('#messages-inner').boundingClientRect();
    query.exec((res: any[]) => {
      this._pendingMeasure = false;
      // ... 同上
    });
  });
},
```

### 4.2 不必要的 setData 跳过

如果 `nextTop` 和当前 `data.scrollTop` 完全相等（含抖动后），可以跳过 setData——但这与「prop 抖动」目标冲突。**保持每次都 setData，让抖动保证 prop diff 是更稳的选择。**

---

## 5. 关键差异对照（vs 文章方案）

| 差异点 | 文章方案 | 本项目方案 | 选择理由 |
|--------|---------|------------|---------|
| scrollTop 计算 | `content − view` 精确值 | `content − view + (0或1抖动)` | 增加抖动防止 prop 相同被跳过 |
| 渲染节奏 | setTimeout 递归 + await 串行 | setInterval(50ms) + callback 内调用 | 项目已用 setInterval，不破坏现有节奏 |
| 暂停机制 | 文章未提 | `_atBottom` + 触摸阈值 | 满足 FR-2 用户回看场景 |
| 容器命名 | `.scroll-view-content` | `#messages-inner` | 沿用现有 WXML 类名 |

---

## 6. 已知风险与回滚

### 6.1 风险

- **R-1**：高频 setData（50ms × N 气泡）可能在低端 Android（基础库 < 2.20）卡顿；
  - **缓解**：本节 4.1 节流；监控真机 FPS。
- **R-2**：`messages-inner` 高度计算包含未渲染图片（懒加载）→ 测量偏小；
  - **缓解**：图片占位用固定高度 placeholder。
- **R-3**：iOS 边界弹性可能让 `scrollToLower` 提前/延后触发；
  - **缓解**：`lower-threshold="100"` 给 100rpx 缓冲。

### 6.2 回滚路径

若新方案出现严重回归：

1. WXML 把 `scroll-top` 改回 `scroll-into-view`，加双锚点 `msg-sa` / `msg-sb`；
2. `_handleScrollTop` 改为交替 anchor 写法；
3. 仍保留 `_atBottom` 智能暂停逻辑。

---

## 7. 验证清单（实施完成自查）

- [ ] WXML：`scroll-top="{{scrollTop}}"`、`scroll-with-animation="{{true}}"`、内层有 `#messages-inner`；
- [ ] TS：用 `wx.createSelectorQuery().in(this)`，不要用 `this.createSelectorQuery()`；
- [ ] `scrollTop = content − view + tick`，`tick` 在 0/1 之间交替；
- [ ] 触摸阈值 `dy > 8` 才暂停，避免点击误判；
- [ ] `bindscrolltolower` 恢复 `_atBottom = true`；
- [ ] `onUnload` 清理 `typeTimer` / `pollTimer` / `pseudoProgTimer`；
- [ ] 真机走完一遍：3 个测品官完整打字 → 用户上滑 → 拖回底部 → 发追问；
- [ ] 微信开发者工具 + iOS + Android 三端表现一致。

---

## 8. 参考资料

- 微信小程序官方文档：[scroll-view](https://developers.weixin.qq.com/miniprogram/dev/component/scroll-view.html)
- 微信公众号文章「前端 Sharing」第三章「如何实现视图跟随内容滚动」（用户提供）
- 项目内代码：`miniprogram/pages/chat/chat.ts`、`miniprogram/pages/chat/chat.wxml`
