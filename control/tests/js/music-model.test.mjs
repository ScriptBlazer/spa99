import test from "node:test";
import assert from "node:assert/strict";
import * as M from "../../../common/static/common/js/control/music-model.js";

const T = (n, dur = 100) => ({ id: `t${n}`, title: `T${n}`, artist: "A", dur, kind: "spot", assetId: n === 9 ? "x9" : undefined });
const zone = () => ({ queue: [], i: -1, pos: 0, playing: false, shuffle: false, repeat: "off", orig: [] });
const titles = (z) => z.queue.map((e) => e.title).join(",");
const noShuffle = () => 0.999;

test("play now starts the first track and lists the rest as up next", () => {
  const z = zone();
  M.playNow(z, [T(1), T(2), T(3)]);
  assert.equal(M.current(z).title, "T1");
  assert.equal(M.upcoming(z).length, 2);
  assert.ok(z.playing);
});

test("a position past the end of a track moves to the next one, keeping the overflow", () => {
  const z = zone();
  M.playNow(z, [T(1, 100), T(2, 100)]);
  assert.equal(M.advance(z, 130), "track");
  assert.equal(M.current(z).title, "T2");
  assert.equal(Math.round(z.pos), 30);
});

test("the queue ends: playback stops without repeat, wraps with repeat all, loops with repeat one", () => {
  let z = zone();
  M.playNow(z, [T(1, 10)]);
  assert.equal(M.advance(z, 15), "ended");
  assert.equal(z.playing, false);
  z = zone(); z.repeat = "all";
  M.playNow(z, [T(1, 10), T(2, 10)], 1);
  assert.equal(M.advance(z, 12), "track");
  assert.equal(M.current(z).title, "T1");
  z = zone(); z.repeat = "one";
  M.playNow(z, [T(1, 10), T(2, 10)]);
  M.advance(z, 25);
  assert.equal(M.current(z).title, "T1");
  assert.ok(z.playing);
});

test("a long absence catches up through many tracks without looping forever", () => {
  const z = zone(); z.repeat = "all";
  M.playNow(z, [T(1, 60), T(2, 60), T(3, 60)]);
  M.advance(z, 60 * 60 * 24 * 3);
  assert.ok(z.playing);
  assert.ok(z.pos >= 0 && z.pos < 60);
});

test("previous restarts a track after 3 seconds, else goes back", () => {
  const z = zone();
  M.playNow(z, [T(1), T(2), T(3)], 2);
  z.pos = 10; M.stepPrev(z);
  assert.equal(M.current(z).title, "T3"); assert.equal(z.pos, 0);
  M.stepPrev(z);
  assert.equal(M.current(z).title, "T2");
});

test("shuffle keeps the current track and mixes only what is up next; turning it off restores the order", () => {
  const z = zone();
  M.playNow(z, [1, 2, 3, 4, 5, 6].map((n) => T(n)));
  M.setShuffle(z, true, () => 0.1);
  assert.equal(M.current(z).title, "T1");
  assert.notEqual(titles(z), "T1,T2,T3,T4,T5,T6");
  M.setShuffle(z, false);
  assert.equal(titles(z), "T1,T2,T3,T4,T5,T6");
});

test("reorder, remove, clear and undo of up next", () => {
  const z = zone();
  M.playNow(z, [1, 2, 3, 4].map((n) => T(n)));
  assert.ok(M.moveUpcoming(z, 2, 0));
  assert.equal(titles(z), "T1,T4,T2,T3");
  const gone = M.removeUpcoming(z, 1);
  assert.equal(gone.entry.title, "T2");
  assert.equal(titles(z), "T1,T4,T3");
  const removed = M.clearUpcoming(z);
  assert.equal(titles(z), "T1");
  M.restoreUpcoming(z, removed, 1);
  assert.equal(titles(z), "T1,T4,T3");
});

test("enqueue on an empty zone starts playing", () => {
  const z = zone();
  M.enqueue(z, [T(1), T(2)]);
  assert.ok(z.playing);
  assert.equal(M.current(z).title, "T1");
});

test("deleting a Library file drops it, and stops playback when it was playing", () => {
  const z = zone();
  const a = { ...T(9), assetId: "x9" };
  M.playNow(z, [T(1), a, T(3)], 1);
  const r = M.dropAsset(z, "x9");
  assert.ok(r.stopped);
  assert.equal(z.playing, false);
  assert.equal(titles(z), "T1,T3");
  assert.ok(z.i >= 0 && z.i < z.queue.length);
});
