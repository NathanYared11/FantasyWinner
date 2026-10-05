import { test } from "node:test";
import assert from "node:assert/strict";
import { EspnClient } from "./espn.js";

const fake = (body, status = 200) => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url: String(url), opts });
    return { ok: status < 300, status, statusText: "x", json: async () => body };
  };
  return { calls, fetchImpl };
};

test("builds league url with views", async () => {
  const { calls, fetchImpl } = fake({ teams: [{ id: 1 }] });
  const c = new EspnClient({ leagueId: 42, season: 2026, fetchImpl });
  assert.deepEqual(await c.teams(), [{ id: 1 }]);
  assert.match(calls[0].url, /ffl\/seasons\/2026\/segments\/0\/leagues\/42\?view=mTeam&view=mRoster/);
});

test("sends cookies for private leagues", async () => {
  const { calls, fetchImpl } = fake({});
  await new EspnClient({ leagueId: 1, espnS2: "abc", swid: "{X}", fetchImpl }).league();
  assert.equal(calls[0].opts.headers.cookie, "espn_s2=abc; SWID={X}");
});

test("auth failure gives helpful error", async () => {
  const { fetchImpl } = fake({}, 401);
  await assert.rejects(new EspnClient({ leagueId: 1, fetchImpl }).league(), /espn_s2/);
});

test("scoreboard filters by week", async () => {
  const { fetchImpl } = fake({ schedule: [{ matchupPeriodId: 1 }, { matchupPeriodId: 2 }] });
  assert.equal((await new EspnClient({ leagueId: 1, fetchImpl }).scoreboard(2)).length, 1);
});

import { leagueEnv } from "./espn.js";
test("named leagues read LEAGUE_<NAME> and TEAM_<NAME>", () => {
  const env = { ESPN_LEAGUE: "CUZFF", LEAGUE_CUZFF: "111", TEAM_CUZFF: "2", LEAGUE_LEGOAT: "222", TEAM_LEGOAT: "2" };
  assert.deepEqual(leagueEnv(env), { leagueId: "111", teamId: "2" });
  assert.deepEqual(leagueEnv({ ...env, ESPN_LEAGUE: "LEGOAT" }), { leagueId: "222", teamId: "2" });
  assert.deepEqual(leagueEnv({ ESPN_LEAGUE_ID: "9", ESPN_TEAM_ID: "4" }), { leagueId: "9", teamId: "4" });
});

import { leagueSpecs } from "./espn.js";
test("leagueSpecs finds every named league, default first", () => {
  const env = { ESPN_LEAGUE: "LEGOAT", LEAGUE_CUZFF: "160", TEAM_CUZFF: "2", LEAGUE_LEGOAT: "223", TEAM_LEGOAT: "2", LEAGUE_NOTEAM: "5" };
  assert.deepEqual(leagueSpecs(env).map((s) => [s.key, s.leagueId, s.teamId]), [["LEGOAT", "223", "2"], ["CUZFF", "160", "2"]]);
  assert.deepEqual(leagueSpecs({ ESPN_LEAGUE_ID: "9", ESPN_TEAM_ID: "4" }).map((s) => s.leagueId), ["9"]);
});
