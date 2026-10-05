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
