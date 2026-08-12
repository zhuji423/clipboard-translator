import assert from "node:assert/strict";
import { WordSelectionState } from "./word_selection";

const empty = new WordSelectionState();
assert.equal(empty.enter(0), false);
assert.equal(empty.active, false);

const state = new WordSelectionState();
assert.equal(state.enter(5), true);
assert.equal(state.active, true);
assert.equal(state.anchorIndex, 4);
assert.equal(state.focusIndex, 4);
assert.deepEqual(state.range(), { from: 4, to: 4 });
assert.equal(state.isSingleWord(), true);

assert.equal(state.move(-1), true);
assert.deepEqual(state.range(), { from: 3, to: 3 });
assert.equal(state.move(-10), true);
assert.deepEqual(state.range(), { from: 0, to: 0 });
assert.equal(state.move(-1), false);
assert.deepEqual(state.range(), { from: 0, to: 0 });

assert.equal(state.move(2), true);
assert.deepEqual(state.range(), { from: 2, to: 2 });
assert.equal(state.extend(1), true);
assert.deepEqual(state.range(), { from: 2, to: 3 });
assert.equal(state.isSingleWord(), false);
assert.equal(state.extend(1), true);
assert.deepEqual(state.range(), { from: 2, to: 4 });
assert.equal(state.extend(1), false);
assert.deepEqual(state.range(), { from: 2, to: 4 });
assert.equal(state.extend(-1), true);
assert.deepEqual(state.range(), { from: 2, to: 3 });

// Ordinary move collapses from current focus end
assert.equal(state.move(-1), true);
assert.deepEqual(state.range(), { from: 2, to: 2 });
assert.equal(state.isSingleWord(), true);

const custom = new WordSelectionState();
assert.equal(custom.enter(4, 1), true);
assert.deepEqual(custom.range(), { from: 1, to: 1 });
custom.extend(2);
assert.deepEqual(custom.range(), { from: 1, to: 3 });
custom.extend(-5);
assert.deepEqual(custom.range(), { from: 0, to: 1 });

custom.exit();
assert.equal(custom.active, false);
assert.equal(custom.range(), null);
assert.equal(custom.isSingleWord(), false);
assert.equal(custom.move(1), false);
assert.equal(custom.extend(1), false);

console.log("word_selection ok");
