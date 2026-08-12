import { YouTubeAdapter } from "./adapters/youtube";
import { SubtitleOverlay } from "./overlay";
import type { LookupResponse, TranslateResponse } from "./shared";
import { SubtitleContextBuffer } from "./subtitle_context";
import type { SubtitleTranslationContext } from "./subtitle_context";

const adapter = new YouTubeAdapter();
const overlay = new SubtitleOverlay();
overlay.setPlayerGetter(() => adapter.getPlayerElement());

let requestSeq = 0;
let activeRequestId = "";
let pauseOwned = false;
let wasPlayingBeforePause = false;
let contextSession = "";
let pendingContextCue: string | null = null;
const subtitleContext = new SubtitleContextBuffer();

function getVideo(): HTMLVideoElement | null {
  return adapter.getVideo();
}

function pauseForLookup(): void {
  const video = getVideo();
  if (!video) return;
  wasPlayingBeforePause = !video.paused;
  if (!video.paused) {
    video.pause();
    pauseOwned = true;
  } else {
    pauseOwned = false;
  }
}

function resumeIfOwned(): void {
  const video = getVideo();
  if (video && pauseOwned && wasPlayingBeforePause) {
    void video.play().catch(() => undefined);
  }
  pauseOwned = false;
  wasPlayingBeforePause = false;
}

function invalidateActiveRequest(): void {
  activeRequestId = "";
}

function closeTipQuietly(): void {
  if (!overlay.isTipVisible()) return;
  overlay.hideTip();
  invalidateActiveRequest();
  resumeIfOwned();
}

function enterKeyboardMode(): void {
  if (pauseOwned) return;
  if (overlay.isKeyboardMode()) return;
  if (overlay.wordCount() <= 0) return;
  closeTipQuietly();
  overlay.enterKeyboardSelection();
}

function exitKeyboardMode(options?: {
  play?: boolean;
  keepTip?: boolean;
}): void {
  if (!overlay.isKeyboardMode()) {
    if (options?.play) {
      void getVideo()?.play().catch(() => undefined);
    }
    return;
  }
  if (!options?.keepTip) {
    closeTipQuietly();
  }
  overlay.exitKeyboardSelection();
  if (options?.play) {
    pauseOwned = false;
    wasPlayingBeforePause = false;
    void getVideo()?.play().catch(() => undefined);
  }
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const el =
    target instanceof HTMLElement
      ? target
      : target.parentElement;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return Boolean(el.closest("input, textarea, select, [contenteditable='true']"));
}

function onDocumentKeyDown(ev: KeyboardEvent): void {
  if (!overlay.isKeyboardMode()) return;
  if (isEditableTarget(ev.target)) return;

  const key = ev.key;
  if (key === "ArrowLeft" || key === "ArrowRight") {
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTipQuietly();
    const delta = key === "ArrowLeft" ? -1 : 1;
    if (ev.shiftKey) overlay.extendKeyboardSelection(delta);
    else overlay.moveKeyboardSelection(delta);
    return;
  }

  if (key === "Enter") {
    if (ev.ctrlKey || ev.altKey || ev.metaKey || ev.shiftKey) return;
    ev.preventDefault();
    ev.stopPropagation();
    overlay.submitKeyboardSelection();
    return;
  }

  if (key === "Escape") {
    ev.preventDefault();
    ev.stopPropagation();
    if (overlay.isTipVisible()) {
      closeTipQuietly();
      return;
    }
    exitKeyboardMode();
    return;
  }

  if (key === " " || key === "Spacebar") {
    // Exit tip/keyboard mode first, then let YouTube handle Space for play.
    // preventDefault + video.play() desyncs the player (short press fails, long press "works").
    exitKeyboardMode();
    return;
  }
}

function onVideoPause(): void {
  if (pauseOwned) return;
  enterKeyboardMode();
}

function onVideoPlay(): void {
  exitKeyboardMode();
}

overlay.onCloseTip = () => {
  activeRequestId = "";
  if (overlay.isKeyboardMode()) {
    overlay.exitKeyboardSelection();
    pauseOwned = false;
    wasPlayingBeforePause = false;
    void getVideo()?.play().catch(() => undefined);
    return;
  }
  resumeIfOwned();
};

overlay.mountClickHandler(({ word, context, anchor }) => {
  pauseForLookup();
  requestSeq += 1;
  const requestId = `r${requestSeq}`;
  activeRequestId = requestId;
  overlay.showLoading(anchor, word);

  chrome.runtime.sendMessage(
    {
      type: "LOOKUP",
      word,
      context,
      requestId,
    },
    (response: LookupResponse | undefined) => {
      if (chrome.runtime.lastError) {
        if (activeRequestId !== requestId) return;
        overlay.showError(anchor, word, chrome.runtime.lastError.message || "扩展通信失败");
        return;
      }
      if (!response || activeRequestId !== requestId) return;
      if (!response.ok) {
        overlay.showError(anchor, word, response.error || "查词失败");
        return;
      }
      overlay.showResult(anchor, word, response);
    },
  );
  flushPendingContextCue();
});

overlay.mountPhraseSelectHandler(({ text, context }) => {
  const translationContext = subtitleContext.snapshot(
    text,
    context,
    contextSession,
  );
  flushPendingContextCue();
  if (overlay.isKeyboardMode()) {
    void sendPhraseInline(text, translationContext);
    return;
  }
  void sendPhraseToDesktop(text, translationContext);
});

async function sendPhraseInline(
  text: string,
  context: SubtitleTranslationContext,
): Promise<void> {
  const value = text.replace(/\s+/g, " ").trim();
  if (!value) return;

  requestSeq += 1;
  const requestId = `ti${requestSeq}`;
  activeRequestId = requestId;
  const anchor = overlay.keyboardSelectionAnchor();
  overlay.showTranslationLoading(anchor, value);

  chrome.runtime.sendMessage(
    {
      type: "TRANSLATE",
      text: value,
      context,
      requestId,
      inline: true,
    },
    (response: TranslateResponse | undefined) => {
      if (chrome.runtime.lastError) {
        if (activeRequestId !== requestId) return;
        overlay.showError(
          anchor,
          value,
          chrome.runtime.lastError.message || "扩展通信失败",
        );
        return;
      }
      if (!response || activeRequestId !== requestId) return;
      if (
        response.contextSession &&
        response.contextSession !== contextSession
      ) {
        contextSession = response.contextSession;
        subtitleContext.reset();
        pendingContextCue = null;
      }
      if (!response.ok || !response.translation) {
        overlay.showError(anchor, value, response.error || "翻译失败");
        return;
      }
      overlay.showTranslation(anchor, value, response.translation);
    },
  );
}

async function sendPhraseToDesktop(
  text: string,
  context: SubtitleTranslationContext,
): Promise<void> {
  const value = text.replace(/\s+/g, " ").trim();
  if (!value) return;

  // Best-effort clipboard sync (may not notify Qt on some browsers).
  void writeClipboardText(value).catch(() => undefined);

  const requestId = `t${Date.now()}`;
  chrome.runtime.sendMessage(
    { type: "TRANSLATE", text: value, context, requestId },
    (response: TranslateResponse | undefined) => {
      if (chrome.runtime.lastError) {
        overlay.showToast(chrome.runtime.lastError.message || "扩展通信失败");
        return;
      }
      if (!response?.ok) {
        overlay.showToast(response?.error || "未能唤起桌面翻译");
        return;
      }
      if (
        response.contextSession &&
        response.contextSession !== contextSession
      ) {
        contextSession = response.contextSession;
        subtitleContext.reset();
        pendingContextCue = null;
      }
      overlay.showToast("已发送到桌面端翻译…");
    },
  );
}

async function writeClipboardText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // fall through to legacy copy
    }
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  ta.style.top = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  if (!ok) throw new Error("execCommand copy failed");
}

adapter.hideNativeCaptions(true);
adapter.start((cue) => {
  if (!cue) {
    if (overlay.isKeyboardMode()) {
      // Keep frozen keyboard selection; YouTube often clears CC DOM on pause.
      overlay.clear();
      return;
    }
    overlay.clear();
    if (overlay.isTipVisible()) {
      // Keep tip if user is reading, but clear subtitle line.
      return;
    }
    return;
  }
  if (overlay.isCueFrozen()) pendingContextCue = cue.text;
  else subtitleContext.push(cue.text);
  overlay.render(cue.text);
});

function flushPendingContextCue(): void {
  if (pendingContextCue === null) return;
  subtitleContext.push(pendingContextCue);
  pendingContextCue = null;
}

// YouTube SPA navigations
let lastHref = location.href;
const navObserver = new MutationObserver(() => {
  if (location.href !== lastHref) {
    lastHref = location.href;
    invalidateActiveRequest();
    overlay.hideTip();
    exitKeyboardMode();
    overlay.clear();
    pauseOwned = false;
    wasPlayingBeforePause = false;
    subtitleContext.reset();
    pendingContextCue = null;
    overlay.layout();
  }
});
navObserver.observe(document.documentElement, { childList: true, subtree: true });

// Player size changes (theater / sidebar) often don't fire window.resize alone.
const playerResize = new ResizeObserver(() => overlay.layout());
let observedPlayer: HTMLElement | null = null;
let observedVideo: HTMLVideoElement | null = null;
const onVideoSeeking = () => {
  subtitleContext.reset();
  pendingContextCue = null;
};
const bindPlayerResize = () => {
  const player = adapter.getPlayerElement();
  if (player && player !== observedPlayer) {
    if (observedPlayer) playerResize.unobserve(observedPlayer);
    observedPlayer = player;
    playerResize.observe(player);
  }
  const video = adapter.getVideo();
  if (video && video !== observedVideo) {
    if (observedVideo) {
      observedVideo.removeEventListener("seeking", onVideoSeeking);
      observedVideo.removeEventListener("pause", onVideoPause);
      observedVideo.removeEventListener("play", onVideoPlay);
    }
    observedVideo = video;
    observedVideo.addEventListener("seeking", onVideoSeeking);
    observedVideo.addEventListener("pause", onVideoPause);
    observedVideo.addEventListener("play", onVideoPlay);
    if (observedVideo.paused && !pauseOwned) {
      enterKeyboardMode();
    }
  }
};
bindPlayerResize();
setInterval(bindPlayerResize, 2000);

document.addEventListener("keydown", onDocumentKeyDown, true);

window.addEventListener("beforeunload", () => {
  adapter.stop();
  if (observedVideo) {
    observedVideo.removeEventListener("seeking", onVideoSeeking);
    observedVideo.removeEventListener("pause", onVideoPause);
    observedVideo.removeEventListener("play", onVideoPlay);
  }
  document.removeEventListener("keydown", onDocumentKeyDown, true);
  exitKeyboardMode();
  overlay.destroy();
  navObserver.disconnect();
});
