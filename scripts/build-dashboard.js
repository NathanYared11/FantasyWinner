// Builds dashboard/dist/index.html: the template + this week's projections + the optimizer code.
//   node scripts/build-dashboard.js [season] [week]
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { loadStats, loadGames, loadInjuries } from "../src/data/nflverse.js";
import { buildDefenseIndex } from "../src/model/features.js";
import { projectWeek } from "./predict.js";

const stats = loadStats(), games = loadGames(), injuries = loadInjuries();
const models = JSON.parse(readFileSync("models/ridge.json", "utf8"));
const season = Number(process.argv[2]) || stats.at(-1).season;
const week = Number(process.argv[3]) || stats.at(-1).week + 1;
const proj = projectWeek({ stats, games, injuries, models, season, week, def: buildDefenseIndex(stats) }).filter((p) => p.mean >= 0.5);

// Walk-forward accuracy numbers come from scripts/train.js output (relevant players, 2024+).
const acc = JSON.parse(readFileSync("dashboard/accuracy.json", "utf8"));
// Your team: live from ESPN when ESPN_LEAGUE_ID + ESPN_TEAM_ID are set, else dashboard/roster.json
// ({ "team": "Name", "roster": [{"name","pos"}], "slots": {...optional}, "free": ["names"...] }), else an example.
async function loadTeam() {
  if (process.env.ESPN_LEAGUE_ID && process.env.ESPN_TEAM_ID) {
    const { fromEnv } = await import("../src/espn.js");
    const { espnPlayer, slotsFromSettings } = await import("../src/espn-roster.js");
    const espn = fromEnv(process.env, { season });
    const data = await espn.league(["mRoster", "mTeam", "mSettings"]);
    const t = data.teams.find((x) => x.id === Number(process.env.ESPN_TEAM_ID));
    if (!t) throw new Error(`team ${process.env.ESPN_TEAM_ID} not found; ids: ${data.teams.map((x) => x.id)}`);
    const taken = new Set(data.teams.flatMap((x) => x.roster.entries.map((e) => e.playerId)));
    const free = (await espn.players({ limit: 200, statusIds: ["FREEAGENT", "WAIVERS"] })).map((e) => espnPlayer(e)).filter((p) => p && !taken.has(p.espnId));
    return { name: t.name ?? `${t.location} ${t.nickname}`, roster: t.roster.entries.map(espnPlayer).filter(Boolean).map((p) => ({ n: p.name, p: p.pos })), slots: slotsFromSettings(data.settings), free: free.map((p) => p.name), example: false };
  }
  if (existsSync("dashboard/roster.json")) {
    const f = JSON.parse(readFileSync("dashboard/roster.json", "utf8"));
    return { name: f.team ?? "My team", roster: f.roster.map((p) => ({ n: p.name, p: p.pos })), slots: f.slots, free: f.free, example: false };
  }
  return { name: "Example team", roster: sample, slots: undefined, free: undefined, example: true };
}

const sample = ["Josh Allen QB", "Bijan Robinson RB", "Jonathan Taylor RB", "Kyren Williams RB", "Puka Nacua WR", "Chris Olave WR", "Zay Flowers WR", "Trey McBride TE", "Brandon Aubrey K", "CIN D/ST DST"]
  .map((s) => ({ n: s.slice(0, s.lastIndexOf(" ")), p: s.slice(s.lastIndexOf(" ") + 1) }));
const team = await loadTeam();
const data = {
  season, week, team, ...acc,
  players: proj.map((p) => ({ n: p.name, p: p.pos, t: p.team, o: p.opp, s: p.spread, m: +p.mean.toFixed(2), l: +p.low.toFixed(1), h: +p.high.toFixed(1), q: p.injury })),
};
const lineup = readFileSync("src/lineup.js", "utf8").replace(/^export /gm, "");
const html = readFileSync("dashboard/template.html", "utf8").replace("__DATA__", () => JSON.stringify(data)).replace("__LINEUP__", () => lineup);
mkdirSync("dashboard/dist", { recursive: true });
writeFileSync("dashboard/dist/index.html", html);
console.log(`dashboard/dist/index.html: ${data.players.length} players, ${(html.length / 1024).toFixed(0)} KB`);
