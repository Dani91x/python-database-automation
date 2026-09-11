"""omega_validate_models — CONFRONTO DEI MODELLI DI PROBABILITÀ sullo storico (§15).

Uso (una tantum, sola lettura, campione leggero):
    python -m tools.omega_validate_models --n 600 --out Betfair/omega/reports

Per un campione di partite recenti con i gol a minuto (match_events), a minuti
fissi (25′ → risultato al 45′; 60′ e 70′ → finale) confronta:
  • ``poisson``   : Poisson-Dixon-Coles con λ di lega (media gol casa/trasferta
                    della lega nel campione di TRAINING) + tassi residui live
                    (lo stesso motore del servizio, senza fixture);
  • ``empirical`` : tabella per minuto costruita SOLO sul training (stesso
                    algoritmo della migrazione omega_models_v3, in Python);
  • ``blend``     : media delle due;
sul TEST (partite diverse). Metriche: log-loss multiclasse e calibrazione della
CODA (risultati con P ≤ 2 %: usciti / previsti) — il numero che decide se il lay
di Omega è a valore atteso ≥ 0. Scrive un rapporto Markdown.
NON tocca Betfair; il modello "mercato intero" si valida sulle registrazioni REC
(stesso banco, ``omega_validate``), non qui.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import random
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Betfair.omega import omega_empirical as EMP  # noqa: E402
from Betfair.omega import omega_model as M  # noqa: E402
from Betfair.omega import omega_validate as V  # noqa: E402

Score = Tuple[int, int]
MINUTES = ((25, True), (60, False), (70, False))


def load_sample(n: int, seed: int) -> List[dict]:
    from db_client import get_supabase_client
    sb = get_supabase_client()
    # lettura LEGGERA: per chiave primaria (id) decrescente, filtro sui nulli in Python
    rows = []
    last = None
    while len(rows) < int(n * 2.5):
        q = (sb.table("matches")
             .select("id,fixture_id,league_id,home_team_id,away_team_id,halftime_home,halftime_away,fulltime_home,fulltime_away,fixture_date")
             .eq("status_short", "FT").order("id", desc=True).limit(1000))
        if last is not None:
            q = q.lt("id", last)
        chunk = q.execute().data or []
        if not chunk:
            break
        last = chunk[-1]["id"]
        rows += [r for r in chunk if r.get("halftime_home") is not None and r.get("fulltime_home") is not None
                 and r.get("halftime_away") is not None and r.get("fulltime_away") is not None]
    random.Random(seed).shuffle(rows)
    out: List[dict] = []
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        ids = [r["fixture_id"] for r in chunk]
        ev = (sb.table("match_events").select("fixture_id,team_id,detail,minute")
              .eq("event_type", "Goal").in_("fixture_id", ids).execute().data or [])
        by = collections.defaultdict(list)
        for e in ev:
            if e.get("detail") == "Missed Penalty" or e.get("minute") is None or e["minute"] > 90:
                continue
            by[e["fixture_id"]].append(e)
        for r in chunk:
            goals = [(int(e["minute"]), 1 if e["team_id"] == r["home_team_id"] else 0,
                      1 if e["team_id"] == r["away_team_id"] else 0) for e in by.get(r["fixture_id"], [])]
            gh, ga = sum(g[1] for g in goals), sum(g[2] for g in goals)
            if (gh, ga) != (r["fulltime_home"], r["fulltime_away"]):
                continue                     # eventi incoerenti col finale: scartata
            r["goals"] = goals
            out.append(r)
        if len(out) >= n:
            break
    return out[:n]


def score_at(goals, minute: int) -> Score:
    return (sum(g[1] for g in goals if g[0] <= minute), sum(g[2] for g in goals if g[0] <= minute))


def build_minute_rows(train: List[dict]) -> List[dict]:
    cnt: Dict[Tuple[int, str, str, str], int] = collections.Counter()
    for r in train:
        for b in range(0, 90, 5):
            sc = EMP.score_key(*score_at(r["goals"], b))
            cnt[(b, sc, "ft", EMP.score_key(r["fulltime_home"], r["fulltime_away"]))] += 1
            if b <= 40:
                cnt[(b, sc, "ht", EMP.score_key(r["halftime_home"], r["halftime_away"]))] += 1
    return [{"league_id": 0, "bucket": b, "score": s, "target": t, "result": res, "n": n}
            for (b, s, t, res), n in cnt.items()]


def league_lambdas(train: List[dict]) -> Dict[int, Tuple[float, float]]:
    acc: Dict[int, List[float]] = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in train:
        a = acc[r.get("league_id") or 0]
        a[0] += r["fulltime_home"]; a[1] += r["fulltime_away"]; a[2] += 1
    out = {lg: (v[0] / v[2], v[1] / v[2]) for lg, v in acc.items() if v[2] >= 20}
    tot = [sum(v[0] for v in acc.values()), sum(v[1] for v in acc.values()), sum(v[2] for v in acc.values())]
    out[0] = (tot[0] / tot[2], tot[1] / tot[2]) if tot[2] else (1.4, 1.1)
    return out


def empirical_dist(table: EMP.MinuteTable, minute: int, cur: Score, half: bool) -> Dict[Score, float]:
    target = "ht" if half else "ft"
    key = (0, EMP.minute_bucket(minute, half=half), EMP.score_key(*cur), target)
    counts = table._n.get(key, {})       # noqa: SLF001 — strumento di validazione
    tot = sum(counts.values())
    if tot < EMP.MIN_GLOBAL_N:
        return {}
    out = {}
    for k, n in counts.items():
        h, a = k.split("-")
        out[(int(h), int(a))] = n / tot
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="Betfair/omega/reports")
    ap.add_argument("--tail-factor", dest="tail_factor", type=float, default=M.DEFAULT_TAIL_FACTOR)
    ap.add_argument("--cv", type=float, default=M.DEFAULT_LAMBDA_CV,
                    help="coefficiente di variazione della mistura lognormale sui λ (§16)")
    args = ap.parse_args()
    sample = load_sample(args.n, args.seed)
    if len(sample) < 100:
        print("campione insufficiente:", len(sample)); return
    cut = int(len(sample) * 0.6)
    train, test = sample[:cut], sample[cut:]
    table = EMP.MinuteTable(build_minute_rows(train))
    lam = league_lambdas(train)
    results = {}
    for minute, half in MINUTES:
        cases: Dict[str, List[Tuple[Dict[Score, float], Score]]] = {
            "poisson": [], "poisson_cal": [], "poisson_tail": [], "poisson_cv": [], "poisson_cv_tail": [],
            "empirical": [], "blend": [], "blend_tail": []}
        cal = M.load_calibrator(None)
        fam = M.CALIBRATION_FAMILY_HT if half else M.CALIBRATION_FAMILY_FT
        for r in test:
            cur = score_at(r["goals"], minute)
            actual = (r["halftime_home"], r["halftime_away"]) if half else (r["fulltime_home"], r["fulltime_away"])
            lh, la = lam.get(r.get("league_id") or 0, lam[0])
            st = M.LiveState(minute=minute, score_home=cur[0], score_away=cur[1])
            p_pois = M.score_probs(lh_pre=lh, la_pre=la, rho=M.DEFAULT_RHO, state=st, league_id=r.get("league_id"), half=half)
            p_emp = empirical_dist(table, minute, cur, half)
            cases["poisson"].append((p_pois, actual))
            p_cal = {k: M.apply_calibration(v, fam, minute, cal) for k, v in p_pois.items()}
            cases["poisson_cal"].append((p_cal, actual))
            p_tail = {k: M.apply_tail_factor(v, args.tail_factor) for k, v in p_pois.items()}
            cases["poisson_tail"].append((p_tail, actual))
            p_cv = M.score_probs(lh_pre=lh, la_pre=la, rho=M.DEFAULT_RHO, state=st, league_id=r.get("league_id"),
                                 half=half, cv=args.cv)
            cases["poisson_cv"].append((p_cv, actual))
            cases["poisson_cv_tail"].append(({k: M.apply_tail_factor(v, args.tail_factor) for k, v in p_cv.items()}, actual))
            if p_emp:
                cases["empirical"].append((p_emp, actual))
                bl = V.blend_probs([p_pois, p_emp])
                cases["blend"].append((bl, actual))
                cases["blend_tail"].append(({k: M.apply_tail_factor(v, args.tail_factor) for k, v in bl.items()}, actual))
        # coda: P ≤ 3 % (model_p_max_pct); bancabile: P ≥ 1/120 (price_max) — come il servizio
        results[f"{minute}'{' (45)' if half else ' (finale)'}"] = V.compare_models(cases, p_max=0.03, p_min=1.0 / 120.0)
    os.makedirs(args.out, exist_ok=True)
    day = dt.date.today().isoformat()
    path = os.path.join(args.out, f"validazione_modelli_{day}.md")
    lines = [f"# Validazione modelli Omega — {day}", "",
             f"Campione: {len(sample)} partite FT con gol a minuto coerenti (training {len(train)}, test {len(test)}).",
             "Coda = risultati con P ≤ 3 % (model_p_max_pct): `ratio` = usciti / previsti dal modello",
             "(1 = calibrato; > 1 = il modello SOTTOSTIMA la coda → i lay perdono più del previsto).",
             f"Modelli: poisson (λ di lega + residui live), poisson_cal (calibratore condiviso, famiglie cs_cell/hts_cell), "
             f"poisson_tail (fattore di coda ×{args.tail_factor}), poisson_cv (mistura lognormale sui λ, cv {args.cv}), "
             f"poisson_cv_tail, empirical (tabella per minuto dal training), blend, blend_tail.",
             "`IC` = intervallo 90 % bootstrap per partita. `lay` = la SOLA selezione che Omega farebbe",
             "(il risultato meno probabile con 1/120 ≤ P ≤ 3 %, cioè quotato a mercato): usciti / previsti, con IC.", ""]
    for k, res in results.items():
        lines += [f"## Minuto {k}", "",
                  "| modello | n | log-loss | coda n | previsti | usciti | ratio | IC 90 % | lay n | lay prev. | lay usciti | lay ratio | lay IC |",
                  "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|"]
        for name, m in res.items():
            t = m["tail"]
            ci = t.get("ratio_ci"); lci = t.get("lay_ratio_ci")
            lines.append(f"| {name} | {m['n']} | {m['log_loss']} | {t['n']} | {t['expected_hits']} | {t['hits']} | {t['ratio']} | "
                         f"{'–' if not ci else f'{ci[0]}–{ci[1]}'} | {t['lay_n']} | {t['lay_expected']} | {t['lay_hits']} | {t['lay_ratio']} | "
                         f"{'–' if not lci else f'{lci[0]}–{lci[1]}'} |")
        lines.append("")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print(json.dumps(results, indent=1, ensure_ascii=False))
    print("rapporto:", path)


if __name__ == "__main__":
    main()
