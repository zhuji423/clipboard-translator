import assert from "node:assert/strict";
import {
  SubtitleContextBuffer,
  estimateContextTokens,
  trimContextTail,
} from "./subtitle_context";

assert.equal(estimateContextTokens("中文测试"), 4);
assert.equal(estimateContextTokens("abcdefgh"), 2);
assert.equal(trimContextTail("开".repeat(20) + "结尾", 4), "开开结尾");

let now = 1000;
const buffer = new SubtitleContextBuffer(() => now);
for (let index = 0; index < 7; index += 1) buffer.push(`cue ${index}`);
const latest = buffer.snapshot("target", "cue 6", "session-a");
assert.deepEqual(latest.previous, ["cue 1", "cue 2", "cue 3", "cue 4", "cue 5"]);
assert.equal(latest.current, "cue 6");

const duplicate = buffer.snapshot("cue 6", "cue 6", "session-a");
assert.equal(duplicate.current, "");
const longCue = "中".repeat(700);
assert.equal(buffer.snapshot(longCue, longCue, "session-a").current, "");

const overlap = new SubtitleContextBuffer(() => now);
overlap.push("Hello world this is");
overlap.push("this is a test");
assert.deepEqual(
  overlap.snapshot("test", "this is a test", "session-a").previous,
  ["Hello world"],
);

const expanding = new SubtitleContextBuffer(() => now);
expanding.push("Hello world");
expanding.push("Hello world again");
assert.deepEqual(
  expanding.snapshot("again", "Hello world again", "session-a").previous,
  [],
);

now += 5 * 60 * 1000 + 1;
assert.deepEqual(buffer.snapshot("new", "new", "session-a").previous, []);

console.log("subtitle context ok");
