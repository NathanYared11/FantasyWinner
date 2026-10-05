#!/usr/bin/env node
import { fromEnv } from "./espn.js";

const [cmd = "teams", arg] = process.argv.slice(2);
const espn = fromEnv();

const commands = {
  teams: async () => (await espn.teams()).map((t) => ({
    id: t.id,
    name: t.name ?? `${t.location ?? ""} ${t.nickname ?? ""}`.trim(),
    record: t.record?.overall,
    roster: (t.roster?.entries ?? []).map((e) => e.playerPoolEntry?.player?.fullName),
  })),
  scoreboard: () => espn.scoreboard(arg),
  players: () => espn.players({ limit: Number(arg) || 25 }),
  league: () => espn.league(),
};

if (!commands[cmd]) {
  console.error(`usage: npm run espn -- <${Object.keys(commands).join("|")}> [arg]\n` +
    "env: ESPN_LEAGUE_ID (required), ESPN_SEASON, ESPN_SPORT, ESPN_S2, ESPN_SWID");
  process.exit(2);
}
try {
  console.log(JSON.stringify(await commands[cmd](), null, 2));
} catch (e) {
  console.error(e.message);
  process.exit(1);
}
