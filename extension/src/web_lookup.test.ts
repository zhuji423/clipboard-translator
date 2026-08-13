import {
  extractSentenceByPunctuation,
  extractCurrentSentence,
  normalizeLookupWord,
} from "./web_lookup";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

assertEqual(normalizeLookupWord(" predictable "), "predictable");
assertEqual(normalizeLookupWord("can't"), "can't");
assertEqual(normalizeLookupWord("two words"), "");
assertEqual(normalizeLookupWord("abc123"), "");
assertEqual(normalizeLookupWord("a".repeat(65)), "");

const context = extractCurrentSentence(
  "The first sentence is short. The outcome was unpredictable. A third one follows.",
  "unpredictable",
);
assertEqual(context, "The outcome was unpredictable.");

const capped = extractCurrentSentence(`word ${"x".repeat(800)}.`, "word");
assertEqual(capped.length, 500);

const repeated = extractCurrentSentence(
  "Issue appears first. This issue is the selected one.",
  "issue",
  31,
);
assertEqual(repeated, "This issue is the selected one.");

const repeatedFallback = extractSentenceByPunctuation(
  "Issue appears first. This issue is the selected one.",
  31,
);
assertEqual(repeatedFallback, "This issue is the selected one.");
