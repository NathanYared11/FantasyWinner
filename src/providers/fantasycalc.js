// FantasyCalc crowd-sourced trade values (public API): a market cross-check on top of our own projections.
import { normName } from "../espn-roster.js";

export class FantasyCalcClient {
  constructor({ fetchImpl = fetch, numTeams = 12, ppr = 1, numQbs = 1 } = {}) {
    this.fetch = fetchImpl;
    this.qs = `isDynasty=false&numQbs=${numQbs}&numTeams=${numTeams}&ppr=${ppr}`;
  }
  async values() {
    const res = await this.fetch(`https://api.fantasycalc.com/values/current?${this.qs}`, { headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`FantasyCalc request failed: ${res.status}`);
    const rows = await res.json();
    return new Map(rows.map((r) => [normName(r.player.name), r.value]));
  }
}

// Market view of a trade: total value received minus value given (positive favors you).
export function marketDelta(values, give, get) {
  const v = (n) => values.get(normName(n)) ?? 0;
  return get.reduce((s, n) => s + v(n), 0) - give.reduce((s, n) => s + v(n), 0);
}
