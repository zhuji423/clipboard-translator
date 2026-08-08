import { YouTubeAdapter } from "./adapters/youtube";
import { SubtitleOverlay } from "./overlay";
import type { LookupResponse } from "./shared";

const adapter = new YouTubeAdapter();
const overlay = new SubtitleOverlay();
overlay.setPlayerGetter(() => adapter.getPlayerElement());

let requestSeq = 0;
let activeRequestId = "";
let pauseOwned = false;
let wasPlayingBeforePause = false;

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
});

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
  overlay.render(cue.text);
});

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
    overlay.layout();
  }
});
navObserver.observe(document.documentElement, { childList: true, subtree: true });

// Player size changes (theater / sidebar) often don't fire window.resize alone.
const playerResize = new ResizeObserver(() => overlay.layout());
let observedPlayer: HTMLElement | null = null;
const bindPlayerResize = () => {
  const player = adapter.getPlayerElement();
  if (!player || player === observedPlayer) return;
  if (observedPlayer) playerResize.unobserve(observedPlayer);
  observedPlayer = player;
  playerResize.observe(player);
};
bindPlayerResize();
setInterval(bindPlayerResize, 2000);

window.addEventListener("beforeunload", () => {
  adapter.stop();
  overlay.destroy();
  navObserver.disconnect();
});
