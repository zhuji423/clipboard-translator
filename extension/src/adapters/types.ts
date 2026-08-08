export type SubtitleCue = {
  text: string;
  key: string;
};

export interface SubtitleAdapter {
  readonly name: string;
  start(onCue: (cue: SubtitleCue | null) => void): void;
  stop(): void;
  getVideo(): HTMLVideoElement | null;
  getPlayerElement(): HTMLElement | null;
  hideNativeCaptions(hidden: boolean): void;
}
