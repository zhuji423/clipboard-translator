const MAX_ITEMS = 5;
const MAX_ITEM_TOKENS = 500;
const MAX_TOTAL_TOKENS = 2000;
const IDLE_MS = 5 * 60 * 1000;

export type SubtitleTranslationContext = {
  source: "youtube";
  session: string;
  previous: string[];
  current: string;
};

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function isCjk(char: string): boolean {
  const code = char.codePointAt(0) || 0;
  return (
    (code >= 0x3400 && code <= 0x4dbf) ||
    (code >= 0x4e00 && code <= 0x9fff) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0x3040 && code <= 0x30ff) ||
    (code >= 0xac00 && code <= 0xd7af)
  );
}

export function estimateContextTokens(text: string): number {
  const chars = Array.from(normalize(text));
  if (!chars.length) return 0;
  const cjk = chars.filter(isCjk).length;
  return cjk + Math.ceil((chars.length - cjk) / 4);
}

export function trimContextTail(text: string, maxTokens: number): string {
  const chars = Array.from(normalize(text));
  if (!chars.length || maxTokens <= 0) return "";
  if (estimateContextTokens(chars.join("")) <= maxTokens) return chars.join("");
  let low = 0;
  let high = chars.length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (estimateContextTokens(chars.slice(mid).join("")) <= maxTokens) high = mid;
    else low = mid + 1;
  }
  return chars.slice(low).join("").trimStart();
}

function overlapCarry(previous: string, next: string): string {
  if (next.startsWith(previous)) return "";
  const previousWords = previous.split(" ");
  const nextWords = next.split(" ");
  const maxWords = Math.min(previousWords.length, nextWords.length);
  for (let size = maxWords; size >= 2; size -= 1) {
    if (
      previousWords.slice(-size).join(" ") === nextWords.slice(0, size).join(" ")
    ) {
      return previousWords.slice(0, -size).join(" ");
    }
  }

  const previousChars = Array.from(previous);
  const nextChars = Array.from(next);
  const maxChars = Math.min(previousChars.length, nextChars.length);
  for (let size = maxChars; size >= 4; size -= 1) {
    if (
      previousChars.slice(-size).join("") === nextChars.slice(0, size).join("")
    ) {
      return previousChars.slice(0, -size).join("");
    }
  }
  return previous;
}

export class SubtitleContextBuffer {
  private previous: string[] = [];
  private current = "";
  private lastActivity = 0;

  constructor(private readonly now: () => number = () => Date.now()) {}

  reset(): void {
    this.previous = [];
    this.current = "";
    this.lastActivity = 0;
  }

  push(rawText: string): void {
    this.expireIfIdle();
    const text = trimContextTail(rawText, MAX_ITEM_TOKENS);
    if (!text) return;
    this.lastActivity = this.now();
    if (!this.current) {
      this.current = text;
      return;
    }
    if (text === this.current) return;

    const carry = trimContextTail(
      overlapCarry(this.current, text),
      MAX_ITEM_TOKENS,
    );
    if (carry && this.previous.at(-1) !== carry) {
      this.previous.push(carry);
      this.previous = this.previous.slice(-MAX_ITEMS);
    }
    this.current = text;
  }

  snapshot(
    targetText: string,
    currentCue: string,
    session: string,
  ): SubtitleTranslationContext {
    this.expireIfIdle();
    const target = normalize(targetText);
    const fullCurrent = normalize(currentCue || this.current);
    const current = trimContextTail(fullCurrent, MAX_ITEM_TOKENS);
    const candidates: Array<{ kind: "previous" | "current"; text: string }> =
      this.previous.slice(-MAX_ITEMS).map((text) => ({ kind: "previous", text }));
    if (current && fullCurrent !== target) candidates.push({ kind: "current", text: current });

    const selected: Array<{ kind: "previous" | "current"; text: string }> = [];
    let remaining = MAX_TOTAL_TOKENS;
    for (const candidate of candidates.slice().reverse()) {
      if (remaining <= 0) break;
      const text = trimContextTail(
        candidate.text,
        Math.min(MAX_ITEM_TOKENS, remaining),
      );
      if (!text) continue;
      selected.push({ ...candidate, text });
      remaining -= estimateContextTokens(text);
    }
    selected.reverse();

    return {
      source: "youtube",
      session,
      previous: selected
        .filter((item) => item.kind === "previous")
        .map((item) => item.text),
      current: selected.find((item) => item.kind === "current")?.text || "",
    };
  }

  private expireIfIdle(): void {
    if (this.lastActivity && this.now() - this.lastActivity > IDLE_MS) this.reset();
  }
}
