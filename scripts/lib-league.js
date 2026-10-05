// Shared by scripts/league.js and scripts/build-dashboard.js.
import { readFileSync, existsSync } from "node:fs";
import { loadStats, loadGames, loadInjuries } from "../src/data/nflverse.js";
import { buildDefenseIndex } from "../src/model/features.js";
import { projectWeek } from "./predict.js";
import { rosProjections, buildLeague, sum } from "../src/league.js";
import { DEFAULT_SLOTS } from "../src/lineup.js";

export function loadModelData() {
  const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
  const models = JSON.parse(readFileSync("models/ridge.json", "utf8"));
  const last = stats.at(-1);
  return { stats, games, injuries, models, season: last.season, week: last.week + 1, def: buildDefenseIndex(stats) };
}

// Weekly projections from `week` through `lastWeek` (default 14, the usual end of the fantasy regular season).
export function projectRos(ctx, lastWeek = Number(process.env.FW_LAST_WEEK) || 14) {
  const weeks = [];
  for (let w = ctx.week; w <= lastWeek; w++) weeks.push(w);
  const ros = rosProjections((w) => projectWeek({ ...ctx, week: w, featureWeek: ctx.week }), weeks);
  return { ros, weeks };
}

// Where the league comes from: live ESPN, then dashboard/league.json, then a simulated demo league.
export async function loadRawLeague(ctx, ros) {
  const { fromEnv, leagueEnv } = await import("../src/espn.js");
  const { leagueId, teamId } = leagueEnv(process.env);
  if (leagueId) {
    const { espnPlayer, slotsFromSettings } = await import("../src/espn-roster.js");
    const data = await fromEnv(process.env, { season: ctx.season }).league(["mRoster", "mTeam", "mSettings"]);
    return {
      source: "ESPN", example: false, slots: slotsFromSettings(data.settings) ?? DEFAULT_SLOTS,
      teams: data.teams.map((t) => ({
        id: t.id, name: t.name ?? `${t.location} ${t.nickname}`, mine: t.id === Number(teamId),
        roster: t.roster.entries.map(espnPlayer).filter(Boolean).map((p) => ({ name: p.name, pos: p.pos })),
      })),
    };
  }
  if (existsSync("dashboard/league.json")) {
    const f = JSON.parse(readFileSync("dashboard/league.json", "utf8"));
    return { source: "league.json", example: false, slots: f.slots ?? DEFAULT_SLOTS, teams: f.teams.map((t, i) => ({ id: t.id ?? i + 1, name: t.name, mine: Boolean(t.mine), roster: t.roster })) };
  }
  return demoLeague(ros);
}

// Snake draft of the best projected players into 10 teams. Clearly an example, not the user's league.
export function demoLeague(ros) {
  const need = { QB: 2, RB: 5, WR: 5, TE: 2, K: 1, DST: 1 };
  const pool = [...ros.values()].filter((p) => sum(p.w) > 0).sort((a, b) => sum(b.w) - sum(a.w));
  const teams = Array.from({ length: 10 }, (_, i) => ({ id: i + 1, name: `Team ${i + 1}`, mine: i === 3, roster: [], left: { ...need } }));
  const taken = new Set();
  for (let round = 0; round < 16; round++) {
    const order = round % 2 ? [...teams].reverse() : teams;
    for (const t of order) {
      // Draft by value, but K/D/ST late like real drafts, and never beyond positional needs.
      const pick = pool.find((p) => !taken.has(p) && t.left[p.pos] > 0 && !((p.pos === "K" || p.pos === "DST") && round < 12));
      if (!pick) continue;
      taken.add(pick); t.left[pick.pos]--; t.roster.push({ name: pick.name, pos: pick.pos });
    }
  }
  return { source: "demo", example: true, slots: DEFAULT_SLOTS, teams: teams.map(({ left, ...t }) => t) };
}

export async function getLeague(ctx = loadModelData()) {
  const { ros, weeks } = projectRos(ctx);
  const raw = await loadRawLeague(ctx, ros);
  const league = buildLeague(raw.teams, ros, weeks);
  return { ctx, ros, weeks, raw, league, slots: raw.slots, meId: league.teams.find((t) => t.mine)?.id ?? league.teams[0].id };
}
