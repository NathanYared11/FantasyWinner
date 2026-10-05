// Start/sit + waiver advice for an ESPN team.
//   Live:    ESPN_LEAGUE_ID=... ESPN_TEAM_ID=3 [ESPN_S2=.. ESPN_SWID=..] node scripts/lineup.js [week] [floor|mean|ceiling]
//   Offline: node scripts/lineup.js [week] [objective] --roster roster.json   (roster.json: [{"name","pos"}], optional "free": [...])
import { readFileSync } from "node:fs";
import { loadStats, loadGames, loadInjuries } from "../src/data/nflverse.js";
import { buildDefenseIndex } from "../src/model/features.js";
import { projectWeek } from "./predict.js";
import { optimizeLineup, waiverTargets, closeCalls, DEFAULT_SLOTS } from "../src/lineup.js";
import { espnPlayer, slotsFromSettings, attachProjections } from "../src/espn-roster.js";
import { fromEnv, leagueEnv } from "../src/espn.js";

const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const rosterFile = process.argv.includes("--roster") ? process.argv[process.argv.indexOf("--roster") + 1] : null;
const positional = args.filter((a) => a !== rosterFile);
const objective = ["floor", "mean", "ceiling"].find((o) => positional.includes(o)) ?? "mean";
const weekArg = positional.find((a) => /^\d+$/.test(a));

const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
const models = JSON.parse(readFileSync("models/ridge.json", "utf8"));
const season = stats.at(-1).season;
const week = Number(weekArg) || stats.at(-1).week + 1;
const projections = projectWeek({ stats, games, injuries, models, season, week, def: buildDefenseIndex(stats) });

let roster, free = [], slots = DEFAULT_SLOTS;
if (rosterFile) {
  const f = JSON.parse(readFileSync(rosterFile, "utf8"));
  [roster, free] = Array.isArray(f) ? [f, []] : [f.roster, f.free ?? []];
  if (f.slots) slots = f.slots;
} else {
  const espn = fromEnv(process.env, { season });
  const teamId = Number(leagueEnv(process.env).teamId);
  if (!teamId) { console.error("Set ESPN_TEAM_ID (your team's id in the league) or pass --roster file.json"); process.exit(2); }
  const data = await espn.league(["mRoster", "mTeam", "mSettings"]);
  slots = slotsFromSettings(data.settings) ?? DEFAULT_SLOTS;
  const mine = data.teams.find((t) => t.id === teamId);
  if (!mine) { console.error(`team ${teamId} not found; ids: ${data.teams.map((t) => t.id)}`); process.exit(2); }
  roster = mine.roster.entries.map(espnPlayer).filter(Boolean);
  const rosteredIds = new Set(data.teams.flatMap((t) => t.roster.entries.map((e) => e.playerId)));
  free = (await espn.players({ limit: 150, statusIds: ["FREEAGENT", "WAIVERS"] }))
    .map((e) => espnPlayer(e)).filter((p) => p && !rosteredIds.has(p.espnId));
}

const mine = attachProjections(roster, projections);
const res = optimizeLineup(mine, slots, objective);
const fmt = (p) => `${p.name.padEnd(24)} ${p.pos.padEnd(3)} ${p.mean.toFixed(1).padStart(5)} [${p.low.toFixed(0)}-${p.high.toFixed(0)}]${p.projected ? "" : "  (no projection)"}`;
console.log(`Week ${week} lineup, optimizing for ${objective}: ${res.total.toFixed(1)} pts`);
for (const { slot, player } of res.starters) console.log(`  ${slot.padEnd(9)} ${fmt(player)}`);
console.log("Bench");
for (const p of res.bench) console.log(`  ${" ".repeat(9)} ${fmt(p)}`);
const calls = closeCalls(res).slice(0, 5);
if (calls.length) {
  console.log("Close calls (start vs sit within 2 pts; consider upside)");
  for (const c of calls) console.log(`  ${c.slot}: ${c.starter.name} ${c.starter.mean.toFixed(1)} vs ${c.bench.name} ${c.bench.mean.toFixed(1)} (high ${c.starter.high.toFixed(0)} vs ${c.bench.high.toFixed(0)})`);
}
if (free.length) {
  console.log("Best waiver adds (points added to your lineup)");
  for (const { player, gain } of waiverTargets(mine, attachProjections(free, projections).filter((p) => p.projected), slots, { objective })) {
    console.log(`  +${gain.toFixed(1)}  ${fmt(player)}`);
  }
}
