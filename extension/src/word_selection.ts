/** Pure keyboard word/phrase selection over word indexes (no DOM). */

export type WordSelectionRange = {
  from: number;
  to: number;
};

export class WordSelectionState {
  active = false;
  anchorIndex = -1;
  focusIndex = -1;
  wordCount = 0;

  enter(wordCount: number, startIndex?: number): boolean {
    if (wordCount <= 0) {
      this.exit();
      return false;
    }
    const last = wordCount - 1;
    const index =
      startIndex === undefined
        ? last
        : Math.max(0, Math.min(last, Math.trunc(startIndex)));
    this.active = true;
    this.wordCount = wordCount;
    this.anchorIndex = index;
    this.focusIndex = index;
    return true;
  }

  exit(): void {
    this.active = false;
    this.anchorIndex = -1;
    this.focusIndex = -1;
    this.wordCount = 0;
  }

  /** Move focus and collapse selection to that single word. */
  move(delta: number): boolean {
    if (!this.active || this.wordCount <= 0) return false;
    const next = this.clampIndex(this.focusIndex + delta);
    const changed = next !== this.focusIndex || this.anchorIndex !== next;
    this.focusIndex = next;
    this.anchorIndex = next;
    return changed;
  }

  /** Keep anchor; move focus end (Shift+arrow expand/shrink). */
  extend(delta: number): boolean {
    if (!this.active || this.wordCount <= 0) return false;
    const next = this.clampIndex(this.focusIndex + delta);
    if (next === this.focusIndex) return false;
    this.focusIndex = next;
    return true;
  }

  range(): WordSelectionRange | null {
    if (!this.active || this.wordCount <= 0) return null;
    return {
      from: Math.min(this.anchorIndex, this.focusIndex),
      to: Math.max(this.anchorIndex, this.focusIndex),
    };
  }

  isSingleWord(): boolean {
    const range = this.range();
    return range !== null && range.from === range.to;
  }

  private clampIndex(index: number): number {
    return Math.max(0, Math.min(this.wordCount - 1, index));
  }
}
