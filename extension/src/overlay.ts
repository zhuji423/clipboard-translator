import { tokenizeSubtitle } from "./tokenize";

export type WordClickPayload = {
  word: string;
  context: string;
  anchor: DOMRect;
};

export type PhraseSelectPayload = {
  text: string;
  context: string;
};

const TIP_SIZE_KEY = "ct.tipSize";
const MIN_TIP_W = 200;
const MIN_TIP_H = 120;
const DEFAULT_TIP_W = 280;
const DEFAULT_TIP_H = 160;
const BOTTOM_SAFE_PX = 72;
const SIDE_PAD = 12;
const CLICK_MOVE_PX = 4;
const SNAP_PX = 64;
const MIN_PHRASE_CHARS = 2;
const MAX_PHRASE_CHARS = 8000;

type TipSize = { width: number; height: number };

export class SubtitleOverlay {
  private host: HTMLDivElement;
  private root: ShadowRoot;
  private wrapEl: HTMLDivElement;
  private lineEl: HTMLDivElement;
  private tipEl: HTMLDivElement;
  private tipTitleEl: HTMLDivElement;
  private tipMetaEl: HTMLDivElement;
  private tipGlossEl: HTMLDivElement;
  private tipBodyEl: HTMLDivElement;
  private tipActionsEl: HTMLDivElement;
  private tipResizeEl: HTMLDivElement;
  private onWordClick: ((payload: WordClickPayload) => void) | null = null;
  private onPhraseSelect: ((payload: PhraseSelectPayload) => void) | null = null;
  private currentContext = "";
  private getPlayer: (() => HTMLElement | null) | null = null;
  private tipUserMoved = false;
  private tipVisible = false;
  private layoutRaf = 0;
  private toastEl: HTMLDivElement | null = null;
  private toastTimer = 0;
  private selecting = false;
  private pendingCue: string | null = null;
  private capturePointerId: number | null = null;
  private dragStartIndex = -1;
  private dragEndIndex = -1;
  private dragStartX = 0;
  private dragStartY = 0;
  private dragStartWord = "";
  private onViewportChange = () => this.scheduleLayout();
  private onLinePointerMove = (ev: PointerEvent) => {
    if (!this.selecting) return;
    this.updateDragEnd(ev.clientX, ev.clientY);
  };
  private onLinePointerUp = (ev: PointerEvent) => {
    if (!this.selecting) return;
    this.finishSelect(ev);
  };
  private onLinePointerCancel = () => {
    if (!this.selecting) return;
    this.showToast("划词被中断，请在字幕条上重新拖选");
    this.abortSelect();
  };

  constructor() {
    this.host = document.createElement("div");
    this.host.id = "ct-subtitle-host";
    this.root = this.host.attachShadow({ mode: "open" });
    this.root.innerHTML = `
      <style>
        :host { all: initial; }
        .wrap {
          position: fixed;
          z-index: 2147483646;
          pointer-events: none;
          font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
          box-sizing: border-box;
        }
        .line {
          pointer-events: auto;
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          gap: 0.12em;
          background: rgba(8, 8, 10, 0.72);
          color: #fff;
          padding: 0.35em 0.7em;
          border-radius: 8px;
          font-size: clamp(16px, 2.2vw, 28px);
          line-height: 1.45;
          text-align: center;
          box-sizing: border-box;
          max-width: 100%;
          user-select: none;
          -webkit-user-select: none;
          cursor: text;
          touch-action: none;
        }
        .word {
          cursor: pointer;
          border-radius: 4px;
          padding: 0 0.06em;
          user-select: none;
          -webkit-user-select: none;
        }
        .word:hover, .word:focus {
          background: rgba(60, 120, 216, 0.55);
          outline: none;
        }
        .word.word-selected {
          background: rgba(60, 120, 216, 0.75);
        }
        .punct, .space { white-space: pre; user-select: none; }
        .toast {
          pointer-events: none;
          position: fixed;
          z-index: 2147483647;
          left: 50%;
          transform: translateX(-50%);
          bottom: 18%;
          background: rgba(30, 31, 34, 0.92);
          color: #e8eaed;
          border: 1px solid #3c4048;
          border-radius: 8px;
          padding: 8px 14px;
          font-size: 13px;
          opacity: 0;
          transition: opacity 0.15s ease;
          max-width: min(90vw, 420px);
          text-align: center;
        }
        .toast.visible { opacity: 1; }
        .tip {
          pointer-events: auto;
          position: fixed;
          z-index: 2147483647;
          min-width: ${MIN_TIP_W}px;
          min-height: ${MIN_TIP_H}px;
          background: #1e1f22;
          color: #e8eaed;
          border: 1px solid #3c4048;
          border-radius: 10px;
          box-shadow: 0 8px 28px rgba(0,0,0,0.45);
          font-size: 14px;
          line-height: 1.4;
          display: none;
          flex-direction: column;
          overflow: hidden;
          box-sizing: border-box;
        }
        .tip.visible { display: flex; }
        .tip-title {
          cursor: move;
          user-select: none;
          padding: 10px 12px 6px;
          font-size: 15px;
          font-weight: 600;
          color: #fff;
          flex: 0 0 auto;
        }
        .tip-meta, .tip-gloss {
          color: #9aa0a6;
          font-size: 12px;
          padding: 0 12px 4px;
          flex: 0 0 auto;
        }
        .tip-meta:empty, .tip-gloss:empty { display: none; }
        .tip-body {
          padding: 0 12px;
          white-space: pre-wrap;
          overflow: auto;
          flex: 1 1 auto;
          min-height: 0;
        }
        .tip-actions {
          margin-top: 4px;
          padding: 8px 12px 10px;
          display: flex;
          gap: 8px;
          flex: 0 0 auto;
        }
        .tip button {
          background: #3c78d8;
          color: white;
          border: none;
          border-radius: 6px;
          padding: 4px 10px;
          cursor: pointer;
        }
        .tip button.secondary { background: #3c4048; }
        .tip-resize {
          position: absolute;
          right: 2px;
          bottom: 2px;
          width: 14px;
          height: 14px;
          cursor: nwse-resize;
          background:
            linear-gradient(135deg, transparent 50%, #9aa0a6 50%) no-repeat;
          opacity: 0.85;
        }
        .hidden { display: none !important; }
      </style>
      <div class="wrap">
        <div class="line hidden"></div>
      </div>
      <div class="toast"></div>
      <div class="tip" part="tip">
        <div class="tip-title"></div>
        <div class="tip-meta"></div>
        <div class="tip-gloss"></div>
        <div class="tip-body"></div>
        <div class="tip-actions"></div>
        <div class="tip-resize" title="拖动缩放"></div>
      </div>
    `;
    this.wrapEl = this.root.querySelector(".wrap") as HTMLDivElement;
    this.lineEl = this.root.querySelector(".line") as HTMLDivElement;
    this.toastEl = this.root.querySelector(".toast") as HTMLDivElement;
    this.tipEl = this.root.querySelector(".tip") as HTMLDivElement;
    this.tipTitleEl = this.root.querySelector(".tip-title") as HTMLDivElement;
    this.tipMetaEl = this.root.querySelector(".tip-meta") as HTMLDivElement;
    this.tipGlossEl = this.root.querySelector(".tip-gloss") as HTMLDivElement;
    this.tipBodyEl = this.root.querySelector(".tip-body") as HTMLDivElement;
    this.tipActionsEl = this.root.querySelector(".tip-actions") as HTMLDivElement;
    this.tipResizeEl = this.root.querySelector(".tip-resize") as HTMLDivElement;
    document.documentElement.appendChild(this.host);

    this.lineEl.addEventListener("pointerdown", (ev) => {
      this.beginSelectFromPoint(ev);
    });
    this.lineEl.addEventListener("pointermove", this.onLinePointerMove);
    this.lineEl.addEventListener("pointerup", this.onLinePointerUp);
    this.lineEl.addEventListener("pointercancel", this.onLinePointerCancel);

    this.applyStoredTipSize();
    this.bindTipDrag();
    this.bindTipResize();
    this.tipActionsEl.addEventListener("click", (ev) => {
      const target = ev.target as HTMLElement | null;
      if (target?.dataset?.action === "close") {
        this.hideTip();
        this.onCloseTip?.();
      }
    });

    window.addEventListener("resize", this.onViewportChange);
    window.addEventListener("scroll", this.onViewportChange, true);
    document.addEventListener("fullscreenchange", this.onViewportChange);
  }

  onCloseTip: (() => void) | null = null;

  setPlayerGetter(getter: () => HTMLElement | null): void {
    this.getPlayer = getter;
    this.layout();
  }

  mountClickHandler(handler: (payload: WordClickPayload) => void): void {
    this.onWordClick = handler;
  }

  mountPhraseSelectHandler(handler: (payload: PhraseSelectPayload) => void): void {
    this.onPhraseSelect = handler;
  }

  showToast(message: string, ms = 1800): void {
    if (!this.toastEl) return;
    this.toastEl.textContent = message;
    this.toastEl.classList.add("visible");
    if (this.toastTimer) window.clearTimeout(this.toastTimer);
    this.toastTimer = window.setTimeout(() => {
      this.toastEl?.classList.remove("visible");
      this.toastTimer = 0;
    }, ms);
  }

  isSelecting(): boolean {
    return this.selecting;
  }

  destroy(): void {
    this.releaseCapture();
    this.lineEl.removeEventListener("pointermove", this.onLinePointerMove);
    this.lineEl.removeEventListener("pointerup", this.onLinePointerUp);
    this.lineEl.removeEventListener("pointercancel", this.onLinePointerCancel);
    window.removeEventListener("resize", this.onViewportChange);
    window.removeEventListener("scroll", this.onViewportChange, true);
    document.removeEventListener("fullscreenchange", this.onViewportChange);
    if (this.layoutRaf) cancelAnimationFrame(this.layoutRaf);
    if (this.toastTimer) window.clearTimeout(this.toastTimer);
    this.host.remove();
  }

  clear(): void {
    if (this.selecting) {
      this.pendingCue = "";
      return;
    }
    this.currentContext = "";
    this.pendingCue = null;
    this.lineEl.classList.add("hidden");
    this.lineEl.replaceChildren();
  }

  render(text: string): void {
    if (this.selecting) {
      this.pendingCue = text;
      return;
    }
    this.applyRender(text);
  }

  private applyRender(text: string): void {
    this.currentContext = text;
    this.pendingCue = null;
    const tokens = tokenizeSubtitle(text);
    this.lineEl.replaceChildren();
    let wordIndex = 0;
    for (const token of tokens) {
      if (token.kind === "word") {
        const span = document.createElement("span");
        span.className = "word";
        span.textContent = token.text;
        span.tabIndex = 0;
        span.dataset.word = token.text;
        span.dataset.wordIndex = String(wordIndex);
        wordIndex += 1;
        span.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.onWordClick?.({
              word: token.text,
              context: this.currentContext,
              anchor: span.getBoundingClientRect(),
            });
          }
        });
        this.lineEl.appendChild(span);
      } else {
        const span = document.createElement("span");
        span.className = token.kind;
        span.textContent = token.text;
        this.lineEl.appendChild(span);
      }
    }
    this.lineEl.classList.toggle("hidden", tokens.length === 0);
    this.layout();
  }

  private beginSelectFromPoint(ev: PointerEvent): void {
    if (ev.button !== 0) return;
    const wordEl =
      this.wordElFromPoint(ev.clientX, ev.clientY) ||
      this.nearestWordEl(ev.clientX, ev.clientY, SNAP_PX);
    if (!wordEl) {
      this.showToast("未选中字幕，请在字幕条上拖选");
      return;
    }
    const index = Number(wordEl.dataset.wordIndex ?? "-1");
    if (Number.isNaN(index) || index < 0) {
      this.showToast("未选中字幕，请在字幕条上拖选");
      return;
    }

    this.selecting = true;
    this.dragStartIndex = index;
    this.dragEndIndex = index;
    this.dragStartX = ev.clientX;
    this.dragStartY = ev.clientY;
    this.dragStartWord = wordEl.dataset.word || wordEl.textContent || "";
    this.paintSelectionHighlight();

    try {
      this.lineEl.setPointerCapture(ev.pointerId);
      this.capturePointerId = ev.pointerId;
    } catch {
      this.capturePointerId = null;
    }
    ev.preventDefault();
  }

  private updateDragEnd(x: number, y: number): void {
    const wordEl =
      this.wordElFromPoint(x, y) || this.nearestWordEl(x, y, SNAP_PX * 2);
    if (!wordEl) return;
    const index = Number(wordEl.dataset.wordIndex ?? "-1");
    if (Number.isNaN(index) || index < 0) return;
    if (index === this.dragEndIndex) return;
    this.dragEndIndex = index;
    this.paintSelectionHighlight();
  }

  private finishSelect(ev: PointerEvent): void {
    if (ev.button !== 0 && ev.type === "pointerup") return;
    this.updateDragEnd(ev.clientX, ev.clientY);

    const startIndex = this.dragStartIndex;
    const endIndex = this.dragEndIndex;
    const startWord = this.dragStartWord;
    const moved =
      Math.hypot(ev.clientX - this.dragStartX, ev.clientY - this.dragStartY) >
      CLICK_MOVE_PX;
    const from = Math.min(startIndex, endIndex);
    const to = Math.max(startIndex, endIndex);
    const phrase = this.textBetweenWordIndexes(from, to);
    const words = Array.from(this.lineEl.querySelectorAll<HTMLElement>(".word"));
    const anchorEl = words[startIndex] || words[from] || null;

    this.releaseCapture();
    this.clearSelectionHighlight();
    this.selecting = false;
    const pending = this.pendingCue;
    this.pendingCue = null;
    this.dragStartIndex = -1;
    this.dragEndIndex = -1;

    try {
      if ((moved || from !== to) && phrase.length >= MIN_PHRASE_CHARS) {
        this.onPhraseSelect?.({
          text: phrase.length > MAX_PHRASE_CHARS ? phrase.slice(0, MAX_PHRASE_CHARS) : phrase,
          context: this.currentContext,
        });
        return;
      }

      if (!moved && startWord) {
        this.onWordClick?.({
          word: startWord,
          context: this.currentContext,
          anchor: (anchorEl || this.lineEl).getBoundingClientRect(),
        });
        return;
      }

      this.showToast("未选中字幕，请在字幕条上拖选");
    } finally {
      if (pending !== null) {
        this.applyRender(pending);
      }
    }
  }

  private abortSelect(): void {
    this.releaseCapture();
    this.clearSelectionHighlight();
    this.selecting = false;
    this.dragStartIndex = -1;
    this.dragEndIndex = -1;
    const pending = this.pendingCue;
    this.pendingCue = null;
    if (pending !== null) {
      this.applyRender(pending);
    }
  }

  private releaseCapture(): void {
    if (this.capturePointerId == null) return;
    try {
      if (this.lineEl.hasPointerCapture(this.capturePointerId)) {
        this.lineEl.releasePointerCapture(this.capturePointerId);
      }
    } catch {
      // ignore
    }
    this.capturePointerId = null;
  }

  private paintSelectionHighlight(): void {
    const words = Array.from(this.lineEl.querySelectorAll<HTMLElement>(".word"));
    if (!words.length || this.dragStartIndex < 0) return;
    const from = Math.min(this.dragStartIndex, this.dragEndIndex);
    const to = Math.max(this.dragStartIndex, this.dragEndIndex);
    words.forEach((word, i) => {
      word.classList.toggle("word-selected", i >= from && i <= to);
    });
  }

  private clearSelectionHighlight(): void {
    for (const word of this.lineEl.querySelectorAll(".word-selected")) {
      word.classList.remove("word-selected");
    }
  }

  private wordElFromPoint(x: number, y: number): HTMLElement | null {
    const words = Array.from(this.lineEl.querySelectorAll<HTMLElement>(".word"));
    for (const word of words) {
      const r = word.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
        return word;
      }
    }
    return null;
  }

  private nearestWordEl(x: number, y: number, maxDist: number): HTMLElement | null {
    const words = Array.from(this.lineEl.querySelectorAll<HTMLElement>(".word"));
    if (!words.length) return null;
    let best: HTMLElement | null = null;
    let bestDist = Number.POSITIVE_INFINITY;
    for (const word of words) {
      const r = word.getBoundingClientRect();
      const cx = Math.min(Math.max(x, r.left), r.right);
      const cy = Math.min(Math.max(y, r.top), r.bottom);
      const dist = Math.hypot(x - cx, y - cy);
      if (dist < bestDist) {
        bestDist = dist;
        best = word;
      }
    }
    return bestDist <= maxDist ? best : null;
  }

  private textBetweenWordIndexes(from: number, to: number): string {
    const words = Array.from(this.lineEl.querySelectorAll<HTMLElement>(".word"));
    if (!words.length) return "";
    const a = Math.max(0, from);
    const b = Math.min(words.length - 1, to);
    if (a > b) return "";
    const parts: string[] = [];
    for (let i = a; i <= b; i += 1) {
      const w = (words[i].dataset.word || words[i].textContent || "").trim();
      if (w) parts.push(w);
    }
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  showLoading(anchor: DOMRect, word: string): void {
    this.setTipContent({
      word,
      meta: "",
      gloss: "",
      body: "查词中…",
      closeLabel: "关闭",
      secondary: true,
    });
    this.openTip(anchor);
  }

  showResult(
    anchor: DOMRect,
    word: string,
    data: { lemma?: string; pos?: string; gloss?: string; meaning_in_context?: string },
  ): void {
    const meta = [data.lemma, data.pos].filter(Boolean).join(" · ");
    const body = data.meaning_in_context || data.gloss || "（无释义）";
    const gloss =
      data.gloss && data.gloss !== body ? `词典：${data.gloss}` : "";
    this.setTipContent({
      word,
      meta,
      gloss,
      body,
      closeLabel: "关闭并继续",
      secondary: false,
    });
    this.openTip(anchor);
  }

  showError(anchor: DOMRect, word: string, error: string): void {
    this.setTipContent({
      word,
      meta: "",
      gloss: "",
      body: error,
      closeLabel: "关闭",
      secondary: true,
    });
    this.openTip(anchor);
  }

  hideTip(): void {
    this.tipVisible = false;
    this.tipUserMoved = false;
    this.tipEl.classList.remove("visible");
  }

  isTipVisible(): boolean {
    return this.tipVisible;
  }

  layout(): void {
    const player = this.getPlayer?.() ?? null;
    const rect =
      player?.getBoundingClientRect() ??
      ({
        left: window.innerWidth * 0.05,
        top: window.innerHeight * 0.1,
        width: window.innerWidth * 0.9,
        height: window.innerHeight * 0.5,
        right: window.innerWidth * 0.95,
        bottom: window.innerHeight * 0.6,
      } as DOMRect);

    if (rect.width < 40 || rect.height < 40) return;

    const maxWidth = Math.max(160, rect.width - SIDE_PAD * 2);
    const left = rect.left + SIDE_PAD;
    // Place subtitle inside player, above control bar / metadata boundary.
    const lineHeight = Math.max(36, this.lineEl.offsetHeight || 40);
    const top = rect.bottom - BOTTOM_SAFE_PX - lineHeight;
    const clampedTop = Math.max(rect.top + 8, Math.min(top, rect.bottom - lineHeight - 8));

    this.wrapEl.style.left = `${left}px`;
    this.wrapEl.style.top = `${clampedTop}px`;
    this.wrapEl.style.width = `${maxWidth}px`;
    this.wrapEl.style.bottom = "auto";
    this.wrapEl.style.transform = "none";

    if (this.tipVisible && !this.tipUserMoved) {
      // Keep initial anchored placement relative only when user hasn't dragged.
      // Re-clamp into viewport on resize.
      this.clampTipInViewport();
    } else if (this.tipVisible) {
      this.clampTipInViewport();
    }
  }

  private scheduleLayout(): void {
    if (this.layoutRaf) cancelAnimationFrame(this.layoutRaf);
    this.layoutRaf = requestAnimationFrame(() => {
      this.layoutRaf = 0;
      this.layout();
    });
  }

  private setTipContent(opts: {
    word: string;
    meta: string;
    gloss: string;
    body: string;
    closeLabel: string;
    secondary: boolean;
  }): void {
    this.tipTitleEl.textContent = opts.word;
    this.tipMetaEl.textContent = opts.meta;
    this.tipGlossEl.textContent = opts.gloss;
    this.tipBodyEl.textContent = opts.body;
    this.tipActionsEl.replaceChildren();
    const btn = document.createElement("button");
    btn.dataset.action = "close";
    btn.textContent = opts.closeLabel;
    if (opts.secondary) btn.className = "secondary";
    this.tipActionsEl.appendChild(btn);
  }

  private openTip(anchor: DOMRect): void {
    const wasVisible = this.tipVisible;
    this.tipVisible = true;
    this.tipEl.classList.add("visible");
    if (!wasVisible) {
      this.tipUserMoved = false;
      this.positionTipAtAnchor(anchor);
    } else if (!this.tipUserMoved) {
      this.positionTipAtAnchor(anchor);
    } else {
      this.clampTipInViewport();
    }
  }

  private positionTipAtAnchor(anchor: DOMRect): void {
    const width = this.tipEl.offsetWidth || this.readTipSize().width;
    const height = this.tipEl.offsetHeight || this.readTipSize().height;
    let left = anchor.left + anchor.width / 2 - width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    let top = anchor.top - height - 10;
    if (top < 8) top = Math.min(anchor.bottom + 10, window.innerHeight - height - 8);
    this.tipEl.style.left = `${left}px`;
    this.tipEl.style.top = `${Math.max(8, top)}px`;
    this.tipEl.style.width = `${width}px`;
    this.tipEl.style.height = `${height}px`;
  }

  private clampTipInViewport(): void {
    const width = this.tipEl.offsetWidth || MIN_TIP_W;
    const height = this.tipEl.offsetHeight || MIN_TIP_H;
    let left = parseFloat(this.tipEl.style.left || "8");
    let top = parseFloat(this.tipEl.style.top || "8");
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
    this.tipEl.style.left = `${left}px`;
    this.tipEl.style.top = `${top}px`;
  }

  private applyStoredTipSize(): void {
    const size = this.readTipSize();
    this.tipEl.style.width = `${size.width}px`;
    this.tipEl.style.height = `${size.height}px`;
  }

  private readTipSize(): TipSize {
    try {
      const raw = sessionStorage.getItem(TIP_SIZE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as TipSize;
        if (
          typeof parsed.width === "number" &&
          typeof parsed.height === "number" &&
          parsed.width >= MIN_TIP_W &&
          parsed.height >= MIN_TIP_H
        ) {
          return {
            width: Math.min(parsed.width, window.innerWidth * 0.9),
            height: Math.min(parsed.height, window.innerHeight * 0.9),
          };
        }
      }
    } catch {
      // ignore
    }
    return { width: DEFAULT_TIP_W, height: DEFAULT_TIP_H };
  }

  private saveTipSize(width: number, height: number): void {
    try {
      sessionStorage.setItem(
        TIP_SIZE_KEY,
        JSON.stringify({ width: Math.round(width), height: Math.round(height) }),
      );
    } catch {
      // ignore
    }
  }

  private bindTipDrag(): void {
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let origLeft = 0;
    let origTop = 0;

    const onMove = (ev: PointerEvent) => {
      if (!dragging) return;
      const width = this.tipEl.offsetWidth;
      const height = this.tipEl.offsetHeight;
      let left = origLeft + (ev.clientX - startX);
      let top = origTop + (ev.clientY - startY);
      left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
      top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
      this.tipEl.style.left = `${left}px`;
      this.tipEl.style.top = `${top}px`;
    };

    const onUp = (ev: PointerEvent) => {
      if (!dragging) return;
      dragging = false;
      this.tipUserMoved = true;
      try {
        this.tipTitleEl.releasePointerCapture(ev.pointerId);
      } catch {
        // ignore
      }
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    this.tipTitleEl.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      dragging = true;
      startX = ev.clientX;
      startY = ev.clientY;
      origLeft = parseFloat(this.tipEl.style.left || "0");
      origTop = parseFloat(this.tipEl.style.top || "0");
      this.tipTitleEl.setPointerCapture(ev.pointerId);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      ev.preventDefault();
    });
  }

  private bindTipResize(): void {
    let resizing = false;
    let startX = 0;
    let startY = 0;
    let origW = 0;
    let origH = 0;

    const onMove = (ev: PointerEvent) => {
      if (!resizing) return;
      const maxW = window.innerWidth * 0.9;
      const maxH = window.innerHeight * 0.9;
      const width = Math.max(MIN_TIP_W, Math.min(maxW, origW + (ev.clientX - startX)));
      const height = Math.max(MIN_TIP_H, Math.min(maxH, origH + (ev.clientY - startY)));
      this.tipEl.style.width = `${width}px`;
      this.tipEl.style.height = `${height}px`;
      this.clampTipInViewport();
    };

    const onUp = (ev: PointerEvent) => {
      if (!resizing) return;
      resizing = false;
      this.saveTipSize(this.tipEl.offsetWidth, this.tipEl.offsetHeight);
      try {
        this.tipResizeEl.releasePointerCapture(ev.pointerId);
      } catch {
        // ignore
      }
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    this.tipResizeEl.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      resizing = true;
      startX = ev.clientX;
      startY = ev.clientY;
      origW = this.tipEl.offsetWidth;
      origH = this.tipEl.offsetHeight;
      this.tipResizeEl.setPointerCapture(ev.pointerId);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      ev.preventDefault();
      ev.stopPropagation();
    });
  }
}
