export const MAX_PHRASE_CHARS = 8000;

export function normalizePhrase(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function joinPhraseSegments(segments: string[]): string {
  return normalizePhrase(segments.join(" "));
}

export type PhraseBufferResult = {
  segments: string[];
  joined: string;
  toast: string;
  truncated: boolean;
};

/**
 * Pure session-buffer update for YouTube phrase select.
 * `append=false` replaces the buffer with a single phrase.
 */
export function updatePhraseBuffer(
  segments: string[],
  text: string,
  append: boolean,
): PhraseBufferResult {
  const phrase = normalizePhrase(text);
  if (!phrase) {
    return {
      segments: [...segments],
      joined: "",
      toast: "",
      truncated: false,
    };
  }

  if (!append) {
    const next = [phrase];
    return {
      segments: next,
      joined: phrase,
      toast: "已发送到桌面端翻译…",
      truncated: false,
    };
  }

  const next = [...segments];
  const last = next[next.length - 1];
  if (last !== undefined && last === phrase) {
    // Same cue selected again — keep buffer.
  } else if (last !== undefined && phrase.startsWith(last) && phrase.length > last.length) {
    next[next.length - 1] = phrase;
  } else if (last !== undefined && last.startsWith(phrase) && last.length > phrase.length) {
    // Shorter re-select — keep the longer last segment.
  } else {
    next.push(phrase);
  }

  let joined = joinPhraseSegments(next);
  let truncated = false;
  if (joined.length > MAX_PHRASE_CHARS) {
    joined = joined.slice(0, MAX_PHRASE_CHARS);
    truncated = true;
  }
  const n = next.length;
  const toast = truncated
    ? `已追加第 ${n} 句（过长已截断）并翻译`
    : `已追加第 ${n} 句并翻译`;
  return { segments: next, joined, toast, truncated };
}
