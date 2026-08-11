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

overlay.onCloseTip = () => {
  activeRequestId = "";
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
  void sendPhraseToDesktop(text, translationContext);
});

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
    overlay.clear();
    if (overlay.isTipVisible()) {
      // Keep tip if user is reading, but clear subtitle line.
      return;
    }
    return;
  }
  if (overlay.isSelecting()) pendingContextCue = cue.text;
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
    activeRequestId = "";
    overlay.hideTip();
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
    observedVideo?.removeEventListener("seeking", onVideoSeeking);
    observedVideo = video;
    observedVideo.addEventListener("seeking", onVideoSeeking);
  }
};
bindPlayerResize();
setInterval(bindPlayerResize, 2000);

window.addEventListener("beforeunload", () => {
  adapter.stop();
  observedVideo?.removeEventListener("seeking", onVideoSeeking);
  overlay.destroy();
  navObserver.disconnect();
});
