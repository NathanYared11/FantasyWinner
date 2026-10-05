// League-wide model: every team's roster valued over the rest of the season.
import { normName } from "./espn-roster.js";

export const pkey = (name, pos) => `${normName(name)}|${pos}`;

// projectFn(week) -> [{name,pos,team,opp,mean,...}]. Returns Map key -> {name,pos,team,w:[mean per week]} (0 on bye).
export function rosProjections(projectFn, weeks) {
  const out = new Map();
  weeks.forEach((wk, i) => {
    for (const p of projectFn(wk)) {
      const k = pkey(p.name, p.pos);
      if (!out.has(k)) out.set(k, { name: p.name, pos: p.pos, team: p.team, w: new Array(weeks.length).fill(0) });
      out.get(k).w[i] = Math.max(0, p.mean);
    }
  });
  return out;
}

// rawTeams: [{id,name,mine?,roster:[{name,pos}]}] -> teams with projected players attached.
export function buildLeague(rawTeams, ros, weeks) {
  const zero = () => new Array(weeks.length).fill(0);
  const taken = new Set();
  const teams = rawTeams.map((t) => ({
    id: t.id, name: t.name, mine: Boolean(t.mine),
    roster: t.roster.map((r) => {
      const pos = r.pos ?? r.p, name = r.name ?? r.n;
      const hit = ros.get(pkey(name, pos)) ?? [...ros.values()].find((p) => normName(p.name) === normName(name));
      if (hit) taken.add(pkey(hit.name, hit.pos));
      return hit ? { ...hit, matched: true } : { name, pos, team: "", w: zero(), matched: false };
    }),
  }));
  const freeAgents = [...ros.entries()].filter(([k]) => !taken.has(k)).map(([, p]) => p).sort((a, b) => sum(b.w) - sum(a.w));
  return { teams, freeAgents, weeks };
}

export const sum = (a) => a.reduce((x, y) => x + y, 0);
