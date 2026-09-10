"""backtest_opportunity.py — P&L SIMULATO del motore opportunita' sulle
registrazioni reali (cache compatta di ``validate_opportunity.build_event_cache``).

Cosa fa, evento per evento, istantanea per istantanea (ogni ``step_s`` secondi
di tempo-evento):
  1. ricostruisce il payload NELLA FORMA del feed unico (``snapshot_payload``:
     stessi builder e gate dello scanner) e chiama ``OpportunityModel.evaluate``
     con GLI STESSI parametri della produzione (soglie, size minima, cooldown
     post-gol, cap per evento);
  2. per ogni opportunita' simula la puntata di ``stake`` EUR al prezzo
     registrato SOLO se la size registrata a quel prezzo copre lo stake;
  3. bet delay: la puntata entra nel book ``delay_s`` secondi dopo; si abbina
     solo se in quel momento il mercato e' OPEN e la size disponibile a un
     prezzo uguale o migliore copre ancora lo stake (altrimenti: NON abbinata);
  4. regola ogni scommessa sull'ESITO VERO del mercato (stato WINNER/LOSER
     dello stream Betfair), commissione 5% sul NETTO per mercato (come Betfair);
  5. una sola scommessa per (mercato, selezione, lato) per evento: il primo
     segnale vale, i successivi sullo stesso runner non si sommano.

Modalita' a confronto:
  · ``raw``         probabilita' grezze del modello;
  · ``calibrated``  tabelle di ``data/opp_calibration.json`` (IN-SAMPLE: le
                    tabelle sono state stimate anche su questi eventi);
  · ``cv``          leave-one-event-out: per ogni evento le tabelle sono
                    ristimate SENZA quell'evento (e' il numero onesto).

Uso:
  python -m Betfair.safe_strategy.tools.backtest_opportunity            # tutte le modalita'
  python -m Betfair.safe_strategy.tools.backtest_opportunity --raw
  python -m Betfair.safe_strategy.tools.backtest_opportunity --calibrated --stake 5
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.safe_strategy.calibration import (
    DEFAULT_CALIBRATION_PATH, CalSample, Calibrator, family_of_market, fit_calibration,
)
from Betfair.safe_strategy.opportunity import OpportunityModel
from Betfair.safe_strategy.tools import validate_opportunity as V

DEFAULT_REPORT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "backtest_report.md",
)
MODES = ("raw", "calibrated", "cv")


@dataclass(frozen=True)
class Bet:
    """Una scommessa simulata (segnale → piazzata? → abbinata? → regolata)."""

    event_id: str
    ts: int
    minute: int
    score: str
    family: str
    market_type: str
    market_id: str
    selection_id: int
    selection_name: str
    side: str
    price: float
    stake: float
    size_at_signal: float
    p_model: float
    p_model_raw: float
    edge: float
    ev: float
    confidence: float
    placed: bool            # size al segnale >= stake
    matched: bool           # ancora abbinabile dopo il bet delay
    reason: str
    outcome: Optional[int]  # 1 = la selezione ha vinto, 0 = ha perso, None = non regolato
    pnl_gross: float        # lordo commissione (0 se non abbinata/non regolata)
    lambda_source: str


# ---------------------------------------------------------------------------
# Book: size disponibile a un prezzo uguale o migliore
# ---------------------------------------------------------------------------
def available_size(ladder: Sequence[Sequence[float]], side: str, price: float) -> float:
    """Somma delle size ai livelli che ci ABBINANO a ``price`` o meglio:
    back → offerte in back con prezzo >= price; lay → offerte in lay <= price."""
    tot = 0.0
    for lv in ladder or []:
        try:
            p, s = float(lv[0]), float(lv[1])
        except (TypeError, ValueError, IndexError):
            continue
        if (side == "back" and p >= price - 1e-9) or (side == "lay" and p <= price + 1e-9):
            tot += max(0.0, s)
    return tot


def settle(side: str, price: float, stake: float, outcome: Optional[int]) -> float:
    """P&L LORDO per stake EUR: back vince (price-1)*stake / perde stake;
    lay incassa stake / paga (price-1)*stake."""
    if outcome is None:
        return 0.0
    if side == "back":
        return stake * (price - 1.0) if outcome else -stake
    return -stake * (price - 1.0) if outcome else stake


# ---------------------------------------------------------------------------
# Simulazione di un evento
# ---------------------------------------------------------------------------
def simulate_event(
    cache: Dict[str, Any], model: OpportunityModel, *, stake: float = 5.0,
    lambdas: Optional[Tuple[float, float]] = None, lambda_source: Optional[str] = None,
    league_id: Optional[int] = None, dedupe: bool = True,
) -> List[Bet]:
    """Replay di un evento in cache → scommesse simulate (una per runner/lato)."""
    if lambdas is None:
        lambdas, lambda_source = V.event_lambdas(cache)
    src = lambda_source or "pre_ko"
    eid = str(cache.get("event_id") or "")
    bets: List[Bet] = []
    seen: set = set()
    for snap in cache.get("snapshots") or []:
        payload = V.snapshot_payload(cache, snap)
        opps = model.evaluate(payload, sport="calcio", lambdas=lambdas, league_id=league_id,
                              now_ts=float(snap["ts"]) / 1000.0, lambda_source=src)
        for o in opps:
            mid = str(o.get("market_id") or "")
            sid = int(o.get("selection_id") or 0)
            side = str(o.get("side"))
            key = (mid, sid, side)
            if dedupe and key in seen:
                continue
            seen.add(key)
            price = float(o["price"])
            size_now = float(o.get("size_available") or 0.0)
            placed = size_now >= stake
            matched = False
            reason = "size al segnale < stake"
            if placed:
                d = (snap.get("delayed") or {}).get(mid)
                if not d:
                    reason = "book assente dopo il delay"
                elif d[0] != "OPEN":
                    reason = f"mercato {d[0]} dopo il delay"
                else:
                    lad = (d[2].get(str(sid)) or [[], []])
                    avail = available_size(lad[0] if side == "back" else lad[1], side, price)
                    if avail >= stake:
                        matched, reason = True, "abbinata"
                    else:
                        reason = f"prezzo peggiorato/size {avail:.0f} dopo il delay"
            outcome = V.market_outcome(cache, mid, sid)
            md = (cache.get("markets") or {}).get(mid) or {}
            mt_raw = str(md.get("type") or o.get("market_type"))
            fam = family_of_market(mt_raw, None) or "?"
            if fam == "cs_cell" and "any" in str(o.get("selection_name") or "").lower():
                fam = "cs_any_other"
            bets.append(Bet(
                event_id=eid, ts=int(snap["ts"]), minute=int(o.get("minute") or 0),
                score=str(o.get("score")), family=fam, market_type=mt_raw, market_id=mid,
                selection_id=sid, selection_name=str(o.get("selection_name")), side=side,
                price=price, stake=float(stake), size_at_signal=size_now,
                p_model=float(o.get("p_model") or 0.0), p_model_raw=float(o.get("p_model_raw") or 0.0),
                edge=float(o.get("edge") or 0.0), ev=float(o.get("ev") or 0.0),
                confidence=float(o.get("confidence") or 0.0),
                placed=placed, matched=matched, reason=reason, outcome=outcome,
                pnl_gross=settle(side, price, stake, outcome) if (matched and outcome is not None) else 0.0,
                lambda_source=src,
            ))
    return bets


# ---------------------------------------------------------------------------
# Commissione (netto per mercato) e aggregati
# ---------------------------------------------------------------------------
def net_pnl(bets: Sequence[Bet], commission: float = 0.05) -> Dict[int, float]:
    """{indice scommessa: P&L NETTO}. La commissione si paga sul netto POSITIVO
    di ogni (evento, mercato) e si ripartisce tra le scommesse vincenti del
    mercato in proporzione al loro lordo."""
    groups: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for i, b in enumerate(bets):
        if b.matched and b.outcome is not None:
            groups[(b.event_id, b.market_id)].append(i)
    out: Dict[int, float] = {i: 0.0 for i in range(len(bets))}
    for idx in groups.values():
        gross = sum(bets[i].pnl_gross for i in idx)
        comm = max(0.0, gross) * float(commission)
        pos = sum(bets[i].pnl_gross for i in idx if bets[i].pnl_gross > 0)
        for i in idx:
            share = (bets[i].pnl_gross / pos * comm) if (comm > 0 and pos > 0 and bets[i].pnl_gross > 0) else 0.0
            out[i] = bets[i].pnl_gross - share
    return out


def max_drawdown(pnls: Sequence[float]) -> float:
    peak = cum = 0.0
    dd = 0.0
    for x in pnls:
        cum += x
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return abs(dd)


def summarize(bets: Sequence[Bet], commission: float = 0.05) -> Dict[str, Any]:
    """Aggregati per (famiglia, lato) + totale + per evento."""
    net = net_pnl(bets, commission)
    order = sorted(range(len(bets)), key=lambda i: (bets[i].event_id, bets[i].ts))

    def row(idx: Sequence[int]) -> Dict[str, Any]:
        matched = [i for i in idx if bets[i].matched]
        settled = [i for i in matched if bets[i].outcome is not None]
        wins = [i for i in settled if (bets[i].outcome == 1) == (bets[i].side == "back")]
        staked = sum(bets[i].stake for i in settled)
        pnl = sum(net[i] for i in settled)
        return {
            "n_signals": len(idx), "n_placed": sum(1 for i in idx if bets[i].placed),
            "n_matched": len(matched), "n_settled": len(settled),
            "matched_pct": (100.0 * len(matched) / len(idx)) if idx else 0.0,
            "staked": staked, "pnl": pnl, "roi": (100.0 * pnl / staked) if staked else 0.0,
            "hit_rate": (100.0 * len(wins) / len(settled)) if settled else 0.0,
            "max_dd": max_drawdown([net[i] for i in order if i in set(settled)]),
        }

    by_fam: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    by_ev: Dict[str, List[int]] = defaultdict(list)
    for i, b in enumerate(bets):
        by_fam[(b.family, b.side)].append(i)
        by_ev[b.event_id].append(i)
    return {
        "total": row(list(range(len(bets)))),
        "families": {f"{fam}/{side}": row(idx) for (fam, side), idx in sorted(by_fam.items())},
        "events": {eid: row(idx) for eid, idx in sorted(by_ev.items())},
        "unmatched_reasons": _count(b.reason for b in bets if not b.matched),
    }


def _count(items: Any) -> Dict[str, int]:
    c: Dict[str, int] = defaultdict(int)
    for x in items:
        c[str(x)] += 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------------------
# Esecuzione multi-evento / multi-modalita'
# ---------------------------------------------------------------------------
def _loo_calibrator(all_samples: Dict[str, List[CalSample]], skip: str, *,
                    min_n: int, shrink_n: float) -> Calibrator:
    samples = [s for eid, ss in all_samples.items() if eid != skip for s in ss]
    return Calibrator.from_dict(fit_calibration(samples, min_n=min_n, shrink_n=shrink_n))


def run_backtest(
    paths: Sequence[str], *, modes: Sequence[str] = MODES, stake: float = 5.0,
    commission: float = 0.05, calibration_path: str = DEFAULT_CALIBRATION_PATH,
    params: Optional[dict] = None, min_n: int = 50, shrink_n: float = 50.0,
    only_pre_ko: bool = False, log: bool = True,
) -> Dict[str, Any]:
    """{mode: {"bets": [...], "summary": {...}}, "events": {...}, ...}."""
    t0 = time.time()
    caches: List[Dict[str, Any]] = []
    for p in paths:
        c = V.load_event_cache(p)
        _lam, src = V.event_lambdas(c)
        if only_pre_ko and src != "pre_ko":
            continue
        caches.append(c)
    all_samples: Dict[str, List[CalSample]] = {}
    if "cv" in modes:
        raw_model = OpportunityModel(params, calibration="off")
        for c in caches:
            all_samples[str(c["event_id"])] = V.calibration_samples(c, model=raw_model)
    out: Dict[str, Any] = {"modes": {}, "events": {}, "stake": stake, "commission": commission,
                           "n_events": len(caches)}
    for c in caches:
        lam, src = V.event_lambdas(c)
        out["events"][str(c["event_id"])] = {
            "home": c.get("home"), "away": c.get("away"), "final": c.get("final"),
            "lambda_source": src, "snapshots": len(c.get("snapshots") or []),
        }
    for mode in modes:
        bets: List[Bet] = []
        if mode == "raw":
            model = OpportunityModel(params, calibration="off")
        elif mode == "calibrated":
            model = OpportunityModel(params, calibration=calibration_path)
            if model.calibrator is None and log:
                print(f"[backtest] ATTENZIONE: nessuna calibrazione in {calibration_path}: "
                      f"'calibrated' == 'raw'")
        else:
            model = None
        for i, c in enumerate(caches, 1):
            eid = str(c["event_id"])
            if mode == "cv":
                cal = _loo_calibrator(all_samples, eid, min_n=min_n, shrink_n=shrink_n)
                model = OpportunityModel(params, calibration=cal)
            got = simulate_event(c, model, stake=stake)
            bets.extend(got)
            if log:
                n_m = sum(1 for b in got if b.matched)
                print(f"[backtest:{mode}] {i}/{len(caches)} {eid}: {len(got)} segnali, "
                      f"{n_m} abbinati ({time.time() - t0:.0f}s)")
        out["modes"][mode] = {"bets": bets, "summary": summarize(bets, commission)}
    out["elapsed_s"] = time.time() - t0
    return out


# ---------------------------------------------------------------------------
# Report Markdown (solo ASCII)
# ---------------------------------------------------------------------------
def _fmt_row(name: str, r: Dict[str, Any]) -> str:
    return (f"| {name} | {r['n_signals']} | {r['n_placed']} | {r['n_matched']} | "
            f"{r['matched_pct']:.0f}% | {r['staked']:.0f} | {r['pnl']:+.2f} | {r['roi']:+.1f}% | "
            f"{r['hit_rate']:.0f}% | {r['max_dd']:.2f} |")


_HEAD = ("| segmento | segnali | piazzabili | abbinati | abbinati % | puntato EUR | P&L EUR | ROI | hit | max DD EUR |\n"
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")


def render_report(result: Dict[str, Any], *, calibration_info: Optional[Dict[str, Any]] = None) -> str:
    lines: List[str] = []
    lines.append("# Backtest opportunita' in-play (registrazioni reali)")
    lines.append("")
    lines.append(f"Generato: {datetime.now(timezone.utc).isoformat(timespec='seconds')} | "
                 f"eventi: {result['n_events']} | stake: {result['stake']:.2f} EUR | "
                 f"commissione: {result['commission'] * 100:.0f}% sul netto per mercato | "
                 f"durata: {result.get('elapsed_s', 0):.0f}s")
    src = _count(e["lambda_source"] for e in result["events"].values())
    lines.append(f"Fonte lambda: {src} (default = lambda generici del bot, confidenza penalizzata)")
    if calibration_info:
        lines.append(f"Calibrazione: eventi {calibration_info.get('n_events')}, campioni "
                     f"{calibration_info.get('n_samples')}, tabelle applicate "
                     f"{calibration_info.get('tables_applied')}/{calibration_info.get('tables_total')}, "
                     f"Brier {_f(calibration_info.get('brier_before'))} -> {_f(calibration_info.get('brier_after'))} "
                     f"(CV: {_f(calibration_info.get('brier_cv_before'))} -> {_f(calibration_info.get('brier_cv_after'))}), "
                     f"ECE {_f(calibration_info.get('ece_before'))} -> {_f(calibration_info.get('ece_after'))}")
    lines.append("")
    lines.append("## Sintesi per modalita'")
    lines.append("")
    lines.append(_HEAD)
    for mode, node in result["modes"].items():
        lines.append(_fmt_row(mode, node["summary"]["total"]))
    lines.append("")
    for mode, node in result["modes"].items():
        s = node["summary"]
        lines.append(f"## Modalita' `{mode}` - per famiglia/lato")
        lines.append("")
        lines.append(_HEAD)
        for name, r in s["families"].items():
            lines.append(_fmt_row(name, r))
        lines.append("")
        lines.append(f"Non abbinate (motivi): {s['unmatched_reasons']}")
        lines.append("")
        lines.append(f"## Modalita' `{mode}` - per evento")
        lines.append("")
        lines.append("| evento | partita | finale | lambda | segnali | abbinati | P&L EUR | ROI |")
        lines.append("|---|---|---|---|---:|---:|---:|---:|")
        for eid, r in s["events"].items():
            e = result["events"].get(eid, {})
            fin = e.get("final")
            lines.append(f"| {eid} | {e.get('home')} v {e.get('away')} | "
                         f"{fin[0]}-{fin[1] if fin else ''} | {e.get('lambda_source')} | "
                         f"{r['n_signals']} | {r['n_matched']} | {r['pnl']:+.2f} | {r['roi']:+.1f}% |"
                         if fin else
                         f"| {eid} | {e.get('home')} v {e.get('away')} | ? | {e.get('lambda_source')} | "
                         f"{r['n_signals']} | {r['n_matched']} | {r['pnl']:+.2f} | {r['roi']:+.1f}% |")
        lines.append("")
    lines.append("## Avvertenze")
    lines.append("")
    lines.append("- `calibrated` usa tabelle stimate ANCHE su questi eventi (in-sample): guardare `cv` (leave-one-event-out).")
    lines.append("- Una scommessa per (mercato, selezione, lato) per evento; nessun cash-out, nessuna uscita: si regola al risultato.")
    lines.append("- Il book registrato e' il best 3 livelli del feed: l'abbinamento dopo il delay e' una stima, non un fill certo.")
    lines.append("- Atlante Hazard non caricato (controincrocio assente, come nel bot senza atlante).")
    lines.append("- Gli eventi senza quote 1X2 pre-KO usano i lambda generici del bot (fonte `default`).")
    lines.append("- Esiti correlati dentro la stessa partita: n eventi e' la vera numerosita', non n segnali.")
    return "\n".join(lines) + "\n"


def _f(x: Any) -> str:
    return f"{float(x):.4f}" if isinstance(x, (int, float)) else "n/d"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backtest P&L del motore opportunita'")
    ap.add_argument("--cache-dir", default=V.DEFAULT_CACHE_DIR)
    ap.add_argument("--data-dir", default=V.DEFAULT_DATA_DIR,
                    help="registrazioni: usate con --build-cache se la cache manca")
    ap.add_argument("--build-cache", action="store_true")
    ap.add_argument("--event", action="append", default=[])
    ap.add_argument("--stake", type=float, default=5.0)
    ap.add_argument("--commission", type=float, default=0.05)
    ap.add_argument("--raw", action="store_true", help="solo probabilita' grezze")
    ap.add_argument("--calibrated", action="store_true", help="solo tabelle del file di calibrazione")
    ap.add_argument("--cv", action="store_true", help="solo leave-one-event-out")
    ap.add_argument("--calibration", default=DEFAULT_CALIBRATION_PATH)
    ap.add_argument("--min-n", type=int, default=50)
    ap.add_argument("--shrink-n", type=float, default=50.0)
    ap.add_argument("--only-pre-ko", action="store_true")
    ap.add_argument("--report", default=DEFAULT_REPORT_PATH)
    ap.add_argument("--max-events", type=int, default=None)
    args = ap.parse_args(argv)

    if args.build_cache:
        events = args.event or V.available_events(args.data_dir)
        for i, eid in enumerate(events, 1):
            path = V.build_event_cache(args.data_dir, eid, args.cache_dir)
            print(f"[cache] {i}/{len(events)} {eid}: {'ok' if path else 'saltato'}")
    paths = V.cached_events(args.cache_dir)
    if args.event:
        wanted = set(args.event)
        paths = [p for p in paths if os.path.basename(p).split(".")[0] in wanted]
    if args.max_events:
        paths = paths[: int(args.max_events)]
    if not paths:
        print("nessuna cache: esegui prima validate_opportunity --build-cache (o --build-cache qui)")
        return 1
    modes = [m for m, on in (("raw", args.raw), ("calibrated", args.calibrated), ("cv", args.cv)) if on]
    if not modes:
        modes = list(MODES)
    result = run_backtest(paths, modes=modes, stake=args.stake, commission=args.commission,
                          calibration_path=args.calibration, min_n=args.min_n,
                          shrink_n=args.shrink_n, only_pre_ko=args.only_pre_ko)
    cal_info = Calibrator.load(args.calibration).info() if os.path.isfile(args.calibration) else None
    report = render_report(result, calibration_info=cal_info)
    os.makedirs(os.path.dirname(os.path.abspath(args.report)) or ".", exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)
    print()
    print(_HEAD)
    for mode, node in result["modes"].items():
        print(_fmt_row(mode, node["summary"]["total"]))
    print()
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
