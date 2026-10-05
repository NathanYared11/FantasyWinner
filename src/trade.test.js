import { test } from "node:test";
import assert from "node:assert/strict";
import { rosValue, evaluateTrade, teamNeeds, findTrades, powerRankings } from "./trade.js";
import { buildLeague } from "./league.js";

const W = 4;
const P = (name, pos, pts) => ({ name, pos, team: "XX", w: new Array(W).fill(pts) });
const slots = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1 };
const team = (id, name, roster, mine = false) => ({ id, name, mine, roster });
const filler = (prefix, rb = 8, wr = 8) => [P(prefix + "Q", "QB", 18), P(prefix + "R1", "RB", rb), P(prefix + "R2", "RB", rb), P(prefix + "W1", "WR", wr), P(prefix + "W2", "WR", wr), P(prefix + "T", "TE", 9), P(prefix + "FX", "WR", 5)];

test("byes (zero weeks) lower rosValue", () => {
  const full = [P("Q", "QB", 20)];
  const bye = [{ name: "Q", pos: "QB", team: "X", w: [20, 20, 0, 20] }];
  assert.ok(rosValue(bye, { QB: 1 }, W) < rosValue(full, { QB: 1 }, W));
});

test("trade grades: filling a hole is an A, giving away your RB1 for nothing is an F", () => {
  const me = team(1, "Me", [...filler("m", 8, 8), P("StarWR", "WR", 20)], true);
  me.roster = me.roster.filter((p) => p.name !== "mW2"); // hole at WR2 until the trade
  const them = team(2, "Them", [...filler("t", 8, 8), P("SpareWR", "WR", 14), P("RB1", "RB", 20)]);
  const good = evaluateTrade(me, them, [me.roster.find((p) => p.name === "mFX")], [them.roster.find((p) => p.name === "SpareWR")], slots, W);
  assert.ok(good.myDelta > 0.3 && ["A+", "A", "B+", "B"].includes(good.grade));
  const bad = evaluateTrade(me, them, [me.roster.find((p) => p.name === "StarWR")], [them.roster.find((p) => p.name === "tFX")], slots, W);
  assert.ok(bad.myDelta < -0.6 && bad.grade === "F");
});

test("2-for-1 settles roster size (the receiving team drops its worst player)", () => {
  const me = team(1, "Me", filler("m"), true), them = team(2, "Them", [...filler("t"), P("Bust", "WR", 0.5)]);
  const r = evaluateTrade(me, them, [me.roster[3], me.roster[6]], [them.roster[3]], slots, W);
  assert.ok(Number.isFinite(r.myDelta) && Number.isFinite(r.theirDelta));
});

test("needs flag the weakest position and find win-win trades", () => {
  const me = team(1, "Me", [P("mQ", "QB", 18), P("mR1", "RB", 15), P("mR2", "RB", 14), P("mR3", "RB", 13), P("mW1", "WR", 6), P("mW2", "WR", 5), P("mT", "TE", 8), P("mFX", "WR", 4)], true);
  const t2 = team(2, "Two", [...filler("a", 6, 15), P("aW3", "WR", 14), P("aW4", "WR", 14)]);
  const t3 = team(3, "Three", [...filler("b", 9, 12), P("bR3", "RB", 3)]);
  const league = { teams: [me, t2, t3], freeAgents: [P("FA", "WR", 7)], weeks: [5, 6, 7, 8] };
  const n = teamNeeds(league, 1, slots);
  assert.equal(n.needs[0].pos, "WR");
  const trades = findTrades(league, 1, slots);
  assert.ok(trades.length > 0);
  assert.ok(trades.every((t) => t.myDelta > 0 && t.theirDelta >= 0));
  assert.equal(powerRankings(league, slots).length, 3);
});

test("buildLeague matches names, tracks unmatched players and leaves free agents", () => {
  const ros = new Map([["josh allen|QB", P("Josh Allen", "QB", 20)], ["x y|WR", P("X Y", "WR", 9)]]);
  const l = buildLeague([{ id: 1, name: "A", roster: [{ name: "Josh Allen", pos: "QB" }, { name: "Nobody Here", pos: "WR" }] }], ros, [5, 6, 7, 8]);
  assert.equal(l.teams[0].roster[0].matched, true);
  assert.equal(l.teams[0].roster[1].matched, false);
  assert.deepEqual(l.freeAgents.map((p) => p.name), ["X Y"]);
});

import { marketDelta, FantasyCalcClient } from "./providers/fantasycalc.js";
test("market delta uses normalized names", async () => {
  const fake = async () => ({ ok: true, json: async () => [{ player: { name: "A.J. Brown" }, value: 6000 }, { player: { name: "Zay Flowers" }, value: 4000 }] });
  const values = await new FantasyCalcClient({ fetchImpl: fake }).values();
  assert.equal(marketDelta(values, ["Zay Flowers"], ["AJ Brown"]), 2000);
});
