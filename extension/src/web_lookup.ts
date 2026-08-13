const WORD_RE = /^[A-Za-z]+(?:['’-][A-Za-z]+)*$/;
const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function normalizeLookupWord(value: string): string {
  const word = value.trim().replace(/’/g, "'");
  return word.length <= 64 && WORD_RE.test(word) ? word : "";
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (EDITABLE_TAGS.has(target.tagName)) return true;
  return Boolean(target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])"));
}

export type SelectionContext = { text: string; offset: number };

const MAX_TEXT_BLOCK_CONTEXT = 4000;

export function contextForSelection(
  selection: Selection,
  target: EventTarget | null,
): SelectionContext {
  if (!(target instanceof Element) || selection.rangeCount === 0) {
    return { text: "", offset: 0 };
  }
  const block = target.closest("p, li, blockquote, td, th, dd, dt, figcaption, h1, h2, h3, h4, h5, h6");
  const container = block || target.parentElement || target;
  const range = selection.getRangeAt(0);
  const prefix = document.createRange();
  try {
    prefix.selectNodeContents(container);
    prefix.setEnd(range.startContainer, range.startOffset);
  } catch {
    return { text: (container.textContent || "").replace(/\s+/g, " ").trim(), offset: 0 };
  }
  const rawPrefix = prefix.toString();
  const rawText = container.textContent || "";
  const normalizedPrefix = rawPrefix.replace(/\s+/g, " ").trimStart();
  const normalizedText = rawText.replace(/\s+/g, " ").trim();
  const selectionOffset = Math.min(normalizedPrefix.length, normalizedText.length);
  const windowStart = Math.max(
    0,
    Math.min(
      selectionOffset - Math.floor(MAX_TEXT_BLOCK_CONTEXT / 2),
      normalizedText.length - MAX_TEXT_BLOCK_CONTEXT,
    ),
  );
  return {
    text: normalizedText.slice(windowStart, windowStart + MAX_TEXT_BLOCK_CONTEXT),
    offset: selectionOffset - windowStart,
  };
}

export function extractSentenceByPunctuation(text: string, selectionOffset = -1): string {
  const matches = text.matchAll(/[^.!?。！？]+(?:[.!?。！？]+|$)/g);
  let first = "";
  for (const match of matches) {
    const sentence = match[0].trim();
    if (!sentence) continue;
    if (!first) first = sentence;
    const start = match.index;
    const end = start + match[0].length;
    if (selectionOffset >= start && selectionOffset <= end) return sentence;
  }
  return first || text;
}

export function extractCurrentSentence(
  text: string,
  selectedWord: string,
  selectionOffset = -1,
): string {
  const input = text.replace(/\s+/g, " ").trim();
  if (!input) return selectedWord.slice(0, 500);
  const selected = selectedWord.toLowerCase();
  const SegmenterCtor = (Intl as unknown as { Segmenter?: typeof Intl.Segmenter }).Segmenter;
  if (typeof SegmenterCtor === "function") {
    const segmenter = new SegmenterCtor(undefined, { granularity: "sentence" });
    for (const part of segmenter.segment(input)) {
      const sentence = part.segment.trim();
      const segmentStart = part.index;
      const segmentEnd = segmentStart + part.segment.length;
      if (
        (selectionOffset >= segmentStart && selectionOffset <= segmentEnd) ||
        (selectionOffset < 0 && sentence.toLowerCase().includes(selected))
      ) {
        return sentence.slice(0, 500);
      }
    }
  }
  const sentenceAtSelection = extractSentenceByPunctuation(input, selectionOffset);
  if (selectionOffset >= 0) return sentenceAtSelection.slice(0, 500);
  const sentences = input.split(/(?<=[.!?。！？])\s+/);
  const wordMatch = sentences.find((sentence) => sentence.toLowerCase().includes(selected));
  return (wordMatch || sentenceAtSelection).slice(0, 500);
}
