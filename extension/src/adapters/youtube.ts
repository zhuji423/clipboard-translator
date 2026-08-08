import type { SubtitleAdapter, SubtitleCue } from "./types";

const CAPTION_WINDOW = ".ytp-caption-window-container";
const CAPTION_SEGMENT = ".ytp-caption-segment";

export class YouTubeAdapter implements SubtitleAdapter {
  readonly name = "youtube";
  private observer: MutationObserver | null = null;
  private onCue: ((cue: SubtitleCue | null) => void) | null = null;
  private lastKey = "";
  private styleEl: HTMLStyleElement | null = null;

  start(onCue: (cue: SubtitleCue | null) => void): void {
    this.onCue = onCue;
    this.observer = new MutationObserver(() => this.emitCurrent());
    this.observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    this.emitCurrent();
  }

  stop(): void {
    this.observer?.disconnect();
    this.observer = null;
    this.onCue = null;
    this.hideNativeCaptions(false);
  }

  getVideo(): HTMLVideoElement | null {
    return document.querySelector("video.html5-main-video");
  }

  getPlayerElement(): HTMLElement | null {
    return (
      document.querySelector<HTMLElement>("#movie_player") ||
      document.querySelector<HTMLElement>(".html5-video-player")
    );
  }

  hideNativeCaptions(hidden: boolean): void {
    if (hidden) {
      if (!this.styleEl) {
        this.styleEl = document.createElement("style");
        this.styleEl.id = "ct-hide-native-captions";
        this.styleEl.textContent = `
          .ytp-caption-window-container { opacity: 0 !important; pointer-events: none !important; }
        `;
        document.documentElement.appendChild(this.styleEl);
      }
    } else if (this.styleEl) {
      this.styleEl.remove();
      this.styleEl = null;
    }
  }

  private emitCurrent(): void {
    if (!this.onCue) return;
    const segments = Array.from(
      document.querySelectorAll(`${CAPTION_WINDOW} ${CAPTION_SEGMENT}`),
    ) as HTMLElement[];
    const text = segments
      .map((el) => (el.innerText || el.textContent || "").trim())
      .filter(Boolean)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) {
      if (this.lastKey) {
        this.lastKey = "";
        this.onCue(null);
      }
      return;
    }
    const key = text;
    if (key === this.lastKey) return;
    this.lastKey = key;
    this.onCue({ text, key });
  }
}
