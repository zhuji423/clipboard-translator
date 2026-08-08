export type Token =
  | { kind: "word"; text: string }
  | { kind: "space"; text: string }
  | { kind: "punct"; text: string };

export function tokenizeSubtitle(text: string): Token[] {
  const input = text.replace(/\s+/g, " ").trim();
  if (!input) return [];

  const SegmenterCtor = (Intl as unknown as { Segmenter?: typeof Intl.Segmenter }).Segmenter;
  if (typeof SegmenterCtor === "function") {
    const segmenter = new SegmenterCtor(undefined, { granularity: "word" });
    const tokens: Token[] = [];
    for (const part of segmenter.segment(input)) {
      const value = part.segment;
      if (!value) continue;
      if (/^\s+$/.test(value)) {
        tokens.push({ kind: "space", text: value });
      } else if (part.isWordLike) {
        tokens.push({ kind: "word", text: value });
      } else {
        tokens.push({ kind: "punct", text: value });
      }
    }
    return tokens;
  }

  // Fallback for older engines
  const tokens: Token[] = [];
  const re = /([A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*)|(\s+)|([^A-Za-z0-9\s]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(input))) {
    if (m[1]) tokens.push({ kind: "word", text: m[1] });
    else if (m[2]) tokens.push({ kind: "space", text: m[2] });
    else if (m[3]) tokens.push({ kind: "punct", text: m[3] });
  }
  return tokens;
}
