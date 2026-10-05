import { test } from "node:test";
import assert from "node:assert/strict";
import { optimizeLineup, waiverTargets, closeCalls } from "./lineup.js";
import { normName, slotsFromSettings, attachProjections, espnPlayer } from "./espn-roster.js";

const P = (name, pos, mean, spread = 5) => ({ name, pos, mean, low: mean - spread, high: mean + spread });
const roster = [P("Q", "QB", 20), P("R1", "RB", 15), P("R2", "RB", 12), P("R3", "RB", 11), P("W1", "WR", 14), P("W2", "WR", 9), P("T", "TE", 8), P("K", "K", 7), P("D", "DST", 6)];
const slots = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 };

test("optimizer fills FLEX with the best leftover and benches the rest", () => {
  const r = optimizeLineup(roster, slots);
  assert.equal(r.starters.find((s) => s.slot === "FLEX").player.name, "R3");
  assert.equal(r.total, 20 + 15 + 12 + 14 + 9 + 8 + 11 + 7 + 6);
  assert.equal(r.bench.length, 0);
});

test("optimizer handles scarce positions and superflex exactly", () => {
  const r = optimizeLineup([P("Q1", "QB", 20), P("Q2", "QB", 18), P("R", "RB", 10)], { QB: 1, SUPERFLEX: 1, RB: 1 });
  assert.equal(r.total, 48);
});

test("floor objective prefers the safer player", () => {
  const players = [P("boom", "WR", 12, 10), P("safe", "WR", 11, 2)];
  assert.equal(optimizeLineup(players, { WR: 1 }, "mean").starters[0].player.name, "boom");
  assert.equal(optimizeLineup(players, { WR: 1 }, "floor").starters[0].player.name, "safe");
});

test("waiver gain equals marginal lineup improvement", () => {
  const w = waiverTargets(roster, [P("FA-WR", "WR", 13), P("FA-K", "K", 5)], slots);
  assert.equal(w.length, 1);
  assert.equal(w[0].player.name, "FA-WR");
  assert.equal(w[0].gain, 13 - 9); // displaces W2
});

test("close calls flag near-ties", () => {
  const r = optimizeLineup([P("a", "WR", 10), P("b", "WR", 9.5), P("c", "WR", 3)], { WR: 1 });
  assert.equal(closeCalls(r)[0].bench.name, "b");
});

test("ESPN mapping: names, slots, DST, projections", () => {
  assert.equal(normName("Kenneth Walker III"), "kenneth walker");
  assert.deepEqual(slotsFromSettings({ rosterSettings: { lineupSlotCounts: { 0: 1, 2: 2, 4: 2, 6: 1, 23: 1, 16: 1, 17: 1, 20: 6, 21: 1 } } }), { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, DST: 1, K: 1 });
  assert.equal(espnPlayer({ playerPoolEntry: { player: { fullName: "Bills D/ST", defaultPositionId: 16, proTeamId: 2 } } }).name, "BUF D/ST");
  const [a] = attachProjections([{ name: "A.J. Brown", pos: "WR" }], [{ name: "AJ Brown", pos: "WR", mean: 14, low: 8, high: 20 }]);
  assert.equal(a.mean, 14);
});
