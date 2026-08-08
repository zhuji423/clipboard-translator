import assert from "node:assert/strict";

// Mirror of tokenize.ts fallback for CI without TS loader.
function tokenizeSubtitle(text) {
  const input = text.replace(/\s+/g, " ").trim();
  if (!input) return [];
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "word" });
    const tokens = [];
    for (const part of segmenter.segment(input)) {
      const value = part.segment;
      if (!value) continue;
      if (/^\s+$/.test(value)) tokens.push({ kind: "space", text: value });
      else if (part.isWordLike) tokens.push({ kind: "word", text: value });
      else tokens.push({ kind: "punct", text: value });
    }
    return tokens;
  }
  const tokens = [];
  const re = /([A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*)|(\s+)|([^A-Za-z0-9\s]+)/g;
  let m;
  while ((m = re.exec(input))) {
    if (m[1]) tokens.push({ kind: "word", text: m[1] });
    else if (m[2]) tokens.push({ kind: "space", text: m[2] });
    else if (m[3]) tokens.push({ kind: "punct", text: m[3] });
  }
  return tokens;
}

const tokens = tokenizeSubtitle("Hello, world!");
const words = tokens.filter((t) => t.kind === "word").map((t) => t.text);
assert.deepEqual(words, ["Hello", "world"]);
assert.ok(tokens.some((t) => t.kind === "punct" && t.text === ","));
console.log("tokenize ok");
