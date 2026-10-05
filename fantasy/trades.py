"""Stage 4: trade discovery, offer generation, acceptance model and championship impact.

    python -m fantasy.trades cuzff legoat          # SCAN TRADES: top realistic trades, with odds before/after

Funnel: (1) every player on every other roster is a possible target; (2) a fast expected-points model
screens every give-set from my roster; (3) offers are picked at four price points by acceptance
probability; (4) the Monte Carlo re-simulates only the finalists (the two teams involved) to get
championship odds before/after on common random numbers.

What is and isn't validated: projections come from the backtested model. The acceptance model is a
HEURISTIC (no trade history large enough to fit): the other manager is assumed to accept when they win
on perceived value (preseason reputation + production so far) AND/OR their lineup improves.
"""
import itertools
import math
import sys
from collections import defaultdict

import numpy as np

from . import config as C
from . import model as M
from .analyze import FLEX_POS
from .simulate import PARAMS, Sim

PLAYOFF_WEIGHT = 1.5          # playoff weeks count more than regular-season weeks in the screening model
MAX_TARGETS_MC = 10
VALUE_POWER = 1.25            # stars are worth more than the sum of their parts (consolidation)
# Acceptance heuristic: z = A*perceived_value_gain + B*their_lineup_gain_ppw + TRADER_BIAS - SKEPTIC
A_VALUE, B_LINEUP, SKEPTIC = .55, .55, 1.0


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


class Trader:
    def __init__(self, sim):
        self.sim = sim
        self.snap = sim.snap
        self.me = sim.snap["my_team_id"]
        self.tid = {t["id"]: t for t in sim.snap["teams"]}
        self.weeks = [w for w in sim.weeks if w > sim.week]           # current week is locked for trades
        self.wt = {w: (PLAYOFF_WEIGHT if w > sim.reg_end else 1.0) for w in self.weeks}
        self.slots = sim.slots
        # expected availability-weighted points by week for every player we know about
        self.mw = {}
        for pid, p in sim.players.items():
            self.mw[pid] = [0.0 if p["bye"] == w else p["raw_ppg"] * M.p_play(PARAMS, p["injury"], w - sim.week) for w in self.weeks]
        self.repl = sim.repl
        self.market = {pid: self.market_value(p) for pid, p in sim.players.items()}
        self.true = {pid: max(0.0, p["ppg"] - self.repl.get(p["pos"], 6)) for pid, p in sim.players.items()}

    # ---- values ------------------------------------------------------------------------------------
    def market_ppg(self, p):
        st = p.get("stats", {})
        rep = st.get("proj_ppg_2026") or p["raw_ppg"]
        perf = st.get("ppg_2026")
        return .5 * rep + .5 * perf if perf and st.get("games_2026", 0) >= 3 else rep

    def market_value(self, p):
        """What a typical manager believes he is worth: preseason reputation + production so far, over replacement."""
        return max(0.0, self.market_ppg(p) * min(1.0, p["health"] + .1) - self.repl.get(p["pos"], 6))

    def bundle_value(self, ids, table):
        return sum(table[i] ** VALUE_POWER for i in ids)

    # ---- fast expected-points model -----------------------------------------------------------------
    def expected_points_per_week(self, roster_ids):
        """Average weekly expected points of the best lineup over the remaining weeks (byes + availability aware)."""
        pl = [self.sim.players[i] for i in roster_ids]
        total = wsum = 0.0
        for j, w in enumerate(self.weeks):
            m = {p["id"]: self.mw[p["id"]][j] for p in pl}
            used, pts = set(), 0.0
            for ps in ("QB", "RB", "WR", "TE", "K", "D/ST"):
                cand = sorted([p for p in pl if p["pos"] == ps], key=lambda p: -m[p["id"]])
                n = self.slots.get(ps, 0)
                for p in cand[:n]:
                    used.add(p["id"]); pts += m[p["id"]]
                pts += max(0, n - len(cand)) * self.repl[ps] * .95
            kf = self.slots.get("FLEX", 0)
            flex = sorted([p for p in pl if p["pos"] in FLEX_POS and p["id"] not in used], key=lambda p: -m[p["id"]])
            pts += sum(m[p["id"]] for p in flex[:kf]) + max(0, kf - len(flex)) * self.repl["WR"] * .95
            total += self.wt[w] * pts
            wsum += self.wt[w]
        return total / wsum

    # ---- trade evaluation -------------------------------------------------------------------------------
    def roster_ids(self, tid):
        return [p["id"] for p in self.tid[tid]["roster"]]

    def apply(self, tid_a, give, tid_b, get):
        """New rosters after A gives `give` to B for `get`. The side that ends up with extra players drops its worst bench player."""
        a = [i for i in self.roster_ids(tid_a) if i not in give] + list(get)
        b = [i for i in self.roster_ids(tid_b) if i not in get] + list(give)
        for side, n0 in ((a, len(self.tid[tid_a]["roster"])), (b, len(self.tid[tid_b]["roster"]))):
            while len(side) > n0:
                side.remove(min(side, key=lambda i: self.sim.players[i]["raw_ppg"] if self.sim.players[i]["pos"] in M.POS else 99))
        return a, b

    def trader_bias(self, tid):
        t = self.tid[tid]
        n = t.get("trades") or 0
        return .4 if n >= 3 else .15 if n >= 1 else -.35

    def evaluate(self, other, give, get, base_me, base_other):
        a, b = self.apply(self.me, give, other, get)
        mine, theirs = self.expected_points_per_week(a), self.expected_points_per_week(b)
        gain_me, gain_them = mine - base_me, theirs - base_other
        dv = self.bundle_value(give, self.market) - self.bundle_value(get, self.market)      # >0: they win on perceived value
        z = A_VALUE * dv + B_LINEUP * gain_them + self.trader_bias(other) - SKEPTIC
        return {"give": give, "get": get, "gain_me": gain_me, "gain_them": gain_them, "value_for_them": dv,
                "accept": sigmoid(z), "cost": self.bundle_value(give, self.market), "a": a, "b": b}

    def target_pool(self):
        out = []
        base_me = self.expected_points_per_week(self.roster_ids(self.me))
        for tid, t in self.tid.items():
            if tid == self.me:
                continue
            for p in t["roster"]:
                if p["pos"] in M.POS and p["injury"] not in ("INJURY_RESERVE",):
                    g = self.expected_points_per_week(self.roster_ids(self.me) + [p["id"]]) - base_me
                    if g > .15:
                        out.append((g, tid, p))
        return base_me, sorted(out, key=lambda x: -x[0])

    def offers_for(self, tid, p, base_me, base_other, give_pool, base):
        """All give-sets (1 or 2 of my players) that improve me. Within each acceptance band take the best
        rival-adjusted deal (helping a title contender costs me, so their gain is penalised by their title odds)."""
        sim = self.sim
        rival = min(1.0, base[tid]["title"] / (1 / len(self.tid)))        # 1.0 = owner is at least an average title threat
        cands = []
        for r in (1, 2):
            for give in itertools.combinations(give_pool, r):
                ev = self.evaluate(tid, list(give), [p["id"]], base_me, base_other)
                if ev["gain_me"] > .1:
                    ev["net"] = ev["gain_me"] - .5 * rival * max(0.0, ev["gain_them"])
                    cands.append(ev)
        if not cands:
            return None
        band = lambda lo, hi: max((e for e in cands if lo <= e["accept"] < hi and e["net"] > 0), key=lambda e: e["net"] - .02 * e["cost"], default=None)
        offers = {"opening": band(.30, .50), "fair": band(.50, .70), "aggressive": band(.70, .92)}
        pricey = sorted([e for e in cands if e["net"] >= .5], key=lambda e: -e["cost"])
        offers["maximum"] = None
        for e in pricey[:4]:                       # the max price must still raise MY title odds in the simulation
            r = sim.run({self.me: [dict(sim.players[i], slot=None) for i in e["a"]], tid: [dict(sim.players[i], slot=None) for i in e["b"]]})
            if r[self.me]["title"] - base[self.me]["title"] > .002:
                offers["maximum"] = e
                break
        return offers

    def classify(self, p, offers, gap):
        fair = offers.get("fair")
        if p["injury"] in ("OUT",) or (offers.get("fair") and offers["fair"]["gain_me"] < .2):
            return "AVOID"
        if gap >= 2.0:
            return "BUY LOW"
        if fair and fair["gain_me"] < 1.0:
            return "DEPTH TARGET"
        if not fair:
            return "DREAM TARGET"
        if self.market[p["id"]] >= np.percentile(list(self.market.values()), 92) and fair["accept"] < .6:
            return "DREAM TARGET"
        if self.market[p["id"]] >= np.percentile(list(self.market.values()), 80):
            return "PREMIUM TARGET"
        return "REALISTIC TARGET"

    def fit_score(self, p, offer):
        pct = lambda v, vals: 100 * np.mean(np.array(vals) <= v)
        mine = [q for q in self.sim.players.values() if q["pos"] == p["pos"]]
        parts = {
            "lineup": min(1.0, offer["gain_me"] / 6) * 100, "scarcity": pct(self.true[p["id"]], [self.true[q["id"]] for q in mine]),
            "ros": pct(p["ppg"], [q["ppg"] for q in mine]), "ceiling": pct(p["ceil"], [q["ceil"] for q in mine]),
            "floor": pct(p["floor"], [q["floor"] for q in mine]), "injury": p["health"] * 100,
            "cost": 100 * (1 - min(1.0, offer["cost"] / 40)), "accept": offer["accept"] * 100}
        w = {"lineup": .35, "scarcity": .10, "ros": .10, "ceiling": .05, "floor": .05, "injury": .10, "cost": .10, "accept": .15}
        return round(sum(w[k] * parts[k] for k in w), 1)

    # ---- full scan ----------------------------------------------------------------------------------------------
    def scan(self, base=None, top=10):
        sim = self.sim
        base = base or sim.run()
        base_me, targets = self.target_pool()
        my_roster = self.tid[self.me]["roster"]
        give_pool = [p["id"] for p in my_roster if p["pos"] in M.POS or p["slot"] == "BE"]
        base_others = {tid: self.expected_points_per_week(self.roster_ids(tid)) for tid in self.tid}
        found = []
        self.partner_best = defaultdict(float)
        self.buy_low = sorted([(self.true[p["id"]] - self.market[p["id"]], g, tid, p) for g, tid, p in targets if g > .3], key=lambda x: -x[0])
        for g, tid, p in targets[:60]:
            offers = self.offers_for(tid, p, base_me, base_others[tid], give_pool, base)
            if offers and offers["fair"]:
                found.append((g, tid, p, offers))
                self.partner_best[tid] = max(self.partner_best[tid], offers["fair"]["net"] * offers["fair"]["accept"])
        found.sort(key=lambda x: -x[3]["fair"]["net"] * x[3]["fair"]["accept"])
        results = []
        for g, tid, p, offers in found[:MAX_TARGETS_MC + 4]:
            row = {"target": p, "owner": tid, "offers": offers, "gap": self.true[p["id"]] - self.market[p["id"]]}
            for kind, e in offers.items():
                if e:
                    r = sim.run({self.me: [dict(sim.players[i], slot=None) for i in e["a"]],
                                 tid: [dict(sim.players[i], slot=None) for i in e["b"]]})
                    e["d_title"] = r[self.me]["title"] - base[self.me]["title"]
                    e["d_playoffs"] = r[self.me]["playoffs"] - base[self.me]["playoffs"]
                    e["title_after"] = r[self.me]["title"]
                    e["owner_d_title"] = r[tid]["title"] - base[tid]["title"]
            row["class"] = self.classify(p, offers, row["gap"])
            row["fit"] = self.fit_score(p, offers["fair"])
            fair = offers["fair"]
            row["ev"] = fair["accept"] * fair["d_title"]
            row["roi"] = fair["d_title"] * 100 / max(fair["cost"], 1)
            if fair["d_title"] > 0:
                results.append(row)
        results.sort(key=lambda r: -r["ev"])
        return base, results[:top]


def names(trader, ids):
    return " + ".join(f'{trader.sim.players[i]["name"]} ({trader.sim.players[i]["pos"]}, {trader.sim.players[i]["ppg"]:.1f})' for i in ids)


def render(sim, trader, base, rows):
    me = trader.me
    nm = {t["id"]: t["name"] for t in sim.snap["teams"]}
    L = [f'## {sim.snap["settings"]["name"]} — SCAN TRADES for {nm[me]}',
         f'_ESPN data {sim.snap["refreshed_at"]}, nflverse {sim.snap["nfl_refreshed_at"]}. Title odds now: **{base[me]["title"]*100:.1f}%**. '
         f'Trade deadline {C_deadline(sim)}. Acceptance probabilities are heuristic estimates._', ""]
    for i, r in enumerate(rows, 1):
        p, o = r["target"], r["offers"]
        t = trader.tid[r["owner"]]
        fair = o["fair"]
        L += [f'### {i}. {p["name"]} ({p["pos"]}, {p["nfl_team"]}) — {nm[r["owner"]]}  ·  **{r["class"]}**  ·  fit {r["fit"]}',
              f'- **Why I want him:** projects {p["ppg"]:.1f} ppg (floor {p["floor"]:.1f} / ceiling {p["ceil"]:.1f}); lifts my lineup {fair["gain_me"]:+.1f} pts/wk '
              f'over the rest of the year. Market-vs-true gap {r["gap"]:+.1f} ppg over replacement ({"undervalued" if r["gap"] > 0 else "priced in"}).',
              f'- **Why they may trade:** their lineup {"improves" if fair["gain_them"] > 0 else "changes"} by {fair["gain_them"]:+.1f} pts/wk; '
              f'{t["name"]} has made {t.get("trades") or 0} trades / {t.get("moves") or 0} moves this season.']
        for kind in ("opening", "fair", "aggressive", "maximum"):
            e = o.get(kind)
            if e:
                flag = "" if e["d_title"] > 0 else " ⚠ lowers my title odds — don't offer"
                L.append(f'- **{kind.upper()}:** give {names(trader, e["give"])} · accept {e["accept"]*100:.0f}% · my lineup {e["gain_me"]:+.1f}/wk, theirs {e["gain_them"]:+.1f}/wk · '
                         f'title {base[me]["title"]*100:.1f}% → {e["title_after"]*100:.1f}% ({e["d_title"]*100:+.1f} pts){flag}')
        L += [f'- **Expected deal:** {names(trader, fair["give"])}. **Max price:** ' +
              (names(trader, o["maximum"]["give"]) if o.get("maximum") else "none (not worth overpaying)") +
              f'. **Trade ROI:** {r["roi"]:+.2f} title-pts per unit of value given.', ""]
    return "\n".join(L)


def C_deadline(sim):
    import time
    return time.strftime("%b %d", time.gmtime(sim.snap["settings"]["trade"]["deadlineDate"] / 1000))


def main(argv):
    for lg in argv or C.LEAGUES:
        sim = Sim(lg, 10000)
        sim.calibrate()
        tr = Trader(sim)
        base, rows = tr.scan()
        text = render(sim, tr, base, rows)
        (C.DATA_DIR / lg / "trades.md").write_text(text)
        print(text, "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
