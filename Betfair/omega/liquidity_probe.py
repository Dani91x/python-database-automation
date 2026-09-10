"""liquidity_probe — REPORT di certificazione liquidità per Omega (Correct Score / Half Time Score).

PERCHÉ (richiesta 09/09/2026 sera): Omega laya risultati esatti a quota 20–120 su
leghe minori; le size (4–8 €) devono trovare controparte REALE al lay e, per
l'uscita in green-up, al BACK dopo il gol.

SOLO REPORT (decisione utente 10/09): nessun processo di registrazione, nessun
poller. I dati arrivano dalle registrazioni che avvia l'utente (Segui live / REC)
o da snapshot del feed convertiti con ``snapshot_lines``; il report legge righe
JSONL con questa forma:

    {"ts": epoch, "event_id": "...", "name": "A v B", "blk": "cs"|"ht",
     "minute": 40, "sh": 1, "sa": 0,
     "sel": [{"sid": 7, "name": "2 - 1", "st": "ACTIVE",
              "lay": 60.0, "ls": 40.0, "back": 50.0, "bs": 3.0}, ...]}

Funzioni PURE: copertura lato LAY (size richiesta vs best-lay size), persistenza a
~5 s (proxy del bet delay in-play Betfair), GREEN-UP: per ogni gol, sulle
selezioni che erano layabili prima del gol e diventano raggiungibili (≤1 gol)
dopo, quanto BACK c'è al nuovo prezzo, quanta size serve per chiudere a rischio
equalizzato e in quanti secondi la liquidità compare.

Uso:
    python -m Betfair.omega.liquidity_probe report file1.jsonl [file2.jsonl ...]
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Betfair.omega import omega_engine as E

logger = logging.getLogger(__name__)

BLOCKS = ("cs", "ht")
# fascia Omega di default (omega_config: price_min 20 / price_max 120)
PRICE_MIN, PRICE_MAX = 20.0, 120.0
# size lay "tipica" di Omega oggi (target 3,5–7,5 € → size 3,7–7,9 €): si certifica
# a 6 € e a 10 € (margine per target più alti dopo una perdita spalmata)
SIZE_NEEDS = (6.0, 10.0)
BANDS = ((20.0, 40.0), (40.0, 80.0), (80.0, 120.0))
GREENUP_WINDOW_S = 180.0
PERSIST_MAX_GAP_S = 12.0


# ---------------------------------------------------------------------------
# Conversione da payload del feed (PURA) — per snapshot già disponibili
# ---------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def snapshot_lines(event_id: str, payload: Dict[str, Any], ts: float) -> List[Dict[str, Any]]:
    """Righe JSONL (una per blocco cs/ht con selezioni) da un payload ``safe_strategy_scan``."""
    out: List[Dict[str, Any]] = []
    if not isinstance(payload, dict) or not payload.get("inplay"):
        return out
    sh, sa = _num(payload.get("score_home")), _num(payload.get("score_away"))
    if sh is None or sa is None:
        return out
    for blk in BLOCKS:
        b = payload.get(blk) or {}
        sels = b.get("selections") or []
        if not sels:
            continue
        rows = []
        for s in sels:
            rows.append({
                "sid": s.get("selection_id"), "name": s.get("name"),
                "st": s.get("runner_status"),
                "lay": _num(s.get("lay")), "ls": _num(s.get("lay_size")),
                "back": _num(s.get("back")), "bs": _num(s.get("back_size")),
            })
        out.append({
            "ts": round(ts, 3), "event_id": str(event_id),
            "name": payload.get("event_name"), "blk": blk,
            "market_id": b.get("market_id"), "mstatus": b.get("status"),
            "minute": payload.get("minute"), "sh": int(sh), "sa": int(sa),
            "sel": rows,
        })
    return out


# ---------------------------------------------------------------------------
# Report (PURO)
# ---------------------------------------------------------------------------
@dataclass
class EligibleObs:
    ts: float
    event_id: str
    name: str
    blk: str
    minute: Any
    score: Tuple[int, int]
    sid: Any
    sel_name: str
    lay: float
    lay_size: float
    back: Optional[float]
    back_size: Optional[float]


@dataclass
class GreenUpCase:
    event_id: str
    name: str
    blk: str
    sel_name: str
    goal_ts: float
    minute_after: Any
    score_before: Tuple[int, int]
    score_after: Tuple[int, int]
    lay_price: float          # prezzo a cui Omega avrebbe layato (ultimo snapshot pre-gol)
    lay_size: float           # size lay ipotizzata (size_need)
    samples: List[Dict[str, Any]] = field(default_factory=list)  # post-gol: dt, back, back_size, need, ok, loss

    @property
    def first_ok_dt(self) -> Optional[float]:
        for s in self.samples:
            if s["ok"]:
                return s["dt"]
        return None


def parse_score(name: str) -> Optional[Tuple[int, int]]:
    return E.parse_scoreline(name or "")


def read_lines(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in paths:
        with Path(p).open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    try:
                        out.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
    out.sort(key=lambda ln: (ln.get("ts", 0.0), ln.get("event_id", ""), ln.get("blk", "")))
    return out


def eligible_observations(
    lines: List[Dict[str, Any]], *, price_min: float = PRICE_MIN, price_max: float = PRICE_MAX,
    min_goal_distance: int = 2,
) -> List[EligibleObs]:
    """Selezioni 'Omega-layabili' in ogni snapshot: ACTIVE, punteggio parsabile,
    raggiungibile e ad almeno ``min_goal_distance`` gol, prezzo lay in fascia."""
    out: List[EligibleObs] = []
    for ln in lines:
        sh, sa = ln.get("sh"), ln.get("sa")
        if sh is None or sa is None:
            continue
        for s in ln.get("sel") or []:
            if s.get("st") != "ACTIVE":
                continue
            lay = s.get("lay")
            if lay is None or lay < price_min or lay > price_max:
                continue
            parsed = parse_score(s.get("name") or "")
            if parsed is None:
                continue
            h, a = parsed
            if h < sh or a < sa or (h - sh) + (a - sa) < min_goal_distance:
                continue
            out.append(EligibleObs(
                ts=float(ln["ts"]), event_id=str(ln["event_id"]), name=str(ln.get("name")),
                blk=str(ln["blk"]), minute=ln.get("minute"), score=(int(sh), int(sa)),
                sid=s.get("sid"), sel_name=str(s.get("name")), lay=float(lay),
                lay_size=float(s.get("ls") or 0.0), back=s.get("back"), back_size=s.get("bs"),
            ))
    return out


def lay_coverage(obs: List[EligibleObs], size_needs: Tuple[float, ...] = SIZE_NEEDS) -> Dict[str, Any]:
    """Copertura lato LAY: quota di osservazioni con best-lay size ≥ size richiesta."""
    if not obs:
        return {"n": 0}
    sizes = [o.lay_size for o in obs]
    res: Dict[str, Any] = {
        "n": len(obs), "events": len({o.event_id for o in obs}),
        "lay_size_min": min(sizes), "lay_size_median": statistics.median(sizes),
        "lay_size_p10": sorted(sizes)[max(0, int(len(sizes) * 0.10) - 1)],
        "coverage": {}, "bands": {},
    }
    for need in size_needs:
        res["coverage"][str(need)] = sum(1 for s in sizes if s >= need) / len(sizes)
    for lo, hi in BANDS:
        sub = [o.lay_size for o in obs if lo <= o.lay < hi or (hi == PRICE_MAX and o.lay == hi)]
        if sub:
            res["bands"][f"{lo:g}-{hi:g}"] = {
                "n": len(sub), "median": statistics.median(sub),
                **{f"cov_{need:g}": sum(1 for s in sub if s >= need) / len(sub) for need in size_needs},
            }
    return res


def persistence(obs: List[EligibleObs], size_need: float = SIZE_NEEDS[0], max_gap_s: float = PERSIST_MAX_GAP_S) -> Dict[str, Any]:
    """Proxy del bet delay: fra due snapshot consecutivi (≤ max_gap) della stessa
    selezione, quante volte prezzo lay invariato e size ancora ≥ size_need."""
    by_key: Dict[Tuple[str, str, Any], List[EligibleObs]] = {}
    for o in obs:
        by_key.setdefault((o.event_id, o.blk, o.sid), []).append(o)
    pairs = same_price = still_ok = worse_price = 0
    for seq in by_key.values():
        seq.sort(key=lambda o: o.ts)
        for a, b in zip(seq, seq[1:]):
            dt = b.ts - a.ts
            if dt <= 0 or dt > max_gap_s or a.lay_size < size_need:
                continue
            pairs += 1
            if b.lay == a.lay:
                same_price += 1
                if b.lay_size >= size_need:
                    still_ok += 1
            elif b.lay < a.lay:
                worse_price += 1  # lay più basso = per chi laya PEGGIO
    return {"pairs": pairs,
            "same_price": same_price / pairs if pairs else None,
            "same_price_and_size_ok": still_ok / pairs if pairs else None,
            "price_worse_for_layer": worse_price / pairs if pairs else None}


def greenup_need(lay_size: float, lay_price: float, back_price: float) -> Tuple[float, float]:
    """Back a rischio equalizzato: size = S·L/B; perdita bloccata = S·(L/B − 1)."""
    need = lay_size * lay_price / back_price
    return round(need, 2), round(lay_size * (lay_price / back_price - 1.0), 2)


def greenup_cases(
    lines: List[Dict[str, Any]], *, size_need: float = SIZE_NEEDS[0], price_min: float = PRICE_MIN,
    price_max: float = PRICE_MAX, window_s: float = GREENUP_WINDOW_S, min_goal_distance: int = 2,
) -> List[GreenUpCase]:
    """Per ogni GOL: le selezioni layabili nell'ultimo snapshot pre-gol che dopo
    il gol sono a ≤1 gol → cosa offre il lato BACK nei ``window_s`` successivi."""
    by_ev: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for ln in lines:
        if ln.get("sh") is None:
            continue
        by_ev.setdefault((str(ln["event_id"]), str(ln["blk"])), []).append(ln)
    cases: List[GreenUpCase] = []
    for (eid, blk), seq in by_ev.items():
        seq.sort(key=lambda ln: ln["ts"])
        for i in range(1, len(seq)):
            prev, cur = seq[i - 1], seq[i]
            if (cur["sh"], cur["sa"]) == (prev["sh"], prev["sa"]):
                continue
            if cur["sh"] + cur["sa"] < prev["sh"] + prev["sa"]:
                continue  # correzione punteggio, non un gol
            pre = eligible_observations([prev], price_min=price_min, price_max=price_max,
                                        min_goal_distance=min_goal_distance)
            for o in pre:
                parsed = parse_score(o.sel_name)
                if parsed is None:
                    continue
                h, a = parsed
                if h < cur["sh"] or a < cur["sa"]:
                    continue  # irraggiungibile dopo il gol: la gamba è vinta, niente da chiudere
                if (h - cur["sh"]) + (a - cur["sa"]) > 1:
                    continue  # ancora lontano: nessun trigger
                case = GreenUpCase(
                    event_id=eid, name=o.name, blk=blk, sel_name=o.sel_name, goal_ts=float(cur["ts"]),
                    minute_after=cur.get("minute"), score_before=(prev["sh"], prev["sa"]),
                    score_after=(cur["sh"], cur["sa"]), lay_price=o.lay, lay_size=size_need,
                )
                for ln in seq[i:]:
                    dt = float(ln["ts"]) - float(cur["ts"])
                    if dt > window_s:
                        break
                    if (ln["sh"], ln["sa"]) != (cur["sh"], cur["sa"]):
                        break  # altro gol: scenario diverso
                    s = next((x for x in ln.get("sel") or [] if x.get("sid") == o.sid), None)
                    if not s:
                        continue
                    back, bs = s.get("back"), s.get("bs") or 0.0
                    if back is None or back <= 1.0:
                        case.samples.append({"dt": round(dt, 1), "back": back, "back_size": bs,
                                             "need": None, "ok": False, "loss": None})
                        continue
                    need, loss = greenup_need(size_need, o.lay, float(back))
                    case.samples.append({"dt": round(dt, 1), "back": back, "back_size": bs,
                                         "need": need, "ok": bs >= need, "loss": loss})
                cases.append(case)
    return cases


def greenup_summary(cases: List[GreenUpCase]) -> Dict[str, Any]:
    if not cases:
        return {"n": 0, "with_samples": 0}
    with_samples = [c for c in cases if c.samples]
    ok_any = [c for c in with_samples if c.first_ok_dt is not None]
    ok_60 = [c for c in ok_any if c.first_ok_dt <= 60]
    first_losses = [next(s for s in c.samples if s["ok"])["loss"] for c in ok_any]
    return {
        "n": len(cases), "with_samples": len(with_samples),
        "closable_in_window": len(ok_any) / len(with_samples) if with_samples else None,
        "closable_within_60s": len(ok_60) / len(with_samples) if with_samples else None,
        "first_ok_dt_median": statistics.median([c.first_ok_dt for c in ok_any]) if ok_any else None,
        "loss_at_first_close_median": statistics.median(first_losses) if first_losses else None,
        "loss_at_first_close_max": max(first_losses) if first_losses else None,
    }


def build_report(lines: List[Dict[str, Any]], *, size_needs: Tuple[float, ...] = SIZE_NEEDS) -> Dict[str, Any]:
    obs = eligible_observations(lines)
    return {
        "lines": len(lines), "events": len({ln.get("event_id") for ln in lines}),
        "span_min": round((lines[-1]["ts"] - lines[0]["ts"]) / 60.0, 1) if lines else 0.0,
        "lay": lay_coverage(obs, size_needs),
        "persistence": persistence(obs, size_needs[0]),
        "greenup": {str(n): greenup_summary(greenup_cases(lines, size_need=n)) for n in size_needs},
    }


def verdict(rep: Dict[str, Any], *, size_need: float = SIZE_NEEDS[0]) -> List[str]:
    """Certificazione leggibile: PASS/FAIL/INSUFFICIENTE per lato lay, persistenza, green-up."""
    out = []
    lay = rep.get("lay") or {}
    if lay.get("n", 0) < 50:
        out.append(f"LAY: DATI INSUFFICIENTI (n={lay.get('n', 0)} osservazioni, servono ≥50)")
    else:
        cov = lay["coverage"].get(str(size_need), 0.0)
        out.append(f"LAY {size_need:g} €: {'PASS' if cov >= 0.95 else 'FAIL'} — copertura {cov:.1%} su {lay['n']} osservazioni "
                   f"({lay['events']} partite), best-lay size mediana {lay['lay_size_median']:.0f} €, p10 {lay['lay_size_p10']:.0f} €")
    per = rep.get("persistence") or {}
    if not per.get("pairs"):
        out.append("PERSISTENZA ~5s: DATI INSUFFICIENTI")
    else:
        v = per["same_price_and_size_ok"]
        out.append(f"PERSISTENZA ~5s: {'PASS' if v >= 0.90 else 'ATTENZIONE'} — {v:.1%} delle coppie mantiene prezzo e size "
                   f"({per['pairs']} coppie; prezzo peggiorato {per['price_worse_for_layer']:.1%})")
    g = (rep.get("greenup") or {}).get(str(size_need)) or {}
    if g.get("with_samples", 0) < 10:
        out.append(f"GREEN-UP {size_need:g} €: DATI INSUFFICIENTI ({g.get('with_samples', 0)} gol osservati con gamba aperta, servono ≥10)")
    else:
        c60 = g["closable_within_60s"] or 0.0
        out.append(f"GREEN-UP {size_need:g} €: {'PASS' if c60 >= 0.90 else 'FAIL'} — chiudibile entro 60s nel {c60:.1%} dei casi "
                   f"({g['with_samples']} gol), perdita bloccata mediana {g['loss_at_first_close_median']} € (max {g['loss_at_first_close_max']} €)")
    return out


def format_report(rep: Dict[str, Any], *, cases: Optional[List[GreenUpCase]] = None) -> str:
    lines = [f"Righe {rep['lines']} · partite {rep['events']} · finestra {rep['span_min']} min", ""]
    lines += verdict(rep)
    lay = rep.get("lay") or {}
    if lay.get("bands"):
        lines += ["", "Lato LAY per fascia prezzo:"]
        for k, v in lay["bands"].items():
            covs = "  ".join(f"≥{kk[4:]}€ {vv:.0%}" for kk, vv in v.items() if kk.startswith("cov_"))
            lines.append(f"  {k:>8}: n={v['n']:<5} mediana {v['median']:.0f} €   {covs}")
    if cases:
        lines += ["", "Green-up per gol (prime 30):"]
        for c in cases[:30]:
            first = next((s for s in c.samples if s["ok"]), None)
            s0 = c.samples[0] if c.samples else None
            lines.append(
                f"  {(c.name or '')[:30]:30} {c.blk} {c.sel_name:6} lay@{c.lay_price:<5g} "
                f"{c.score_before[0]}-{c.score_before[1]}→{c.score_after[0]}-{c.score_after[1]} {c.minute_after}' | "
                f"1° back {s0['back'] if s0 else '-'} size {s0['back_size'] if s0 else '-'} need {s0['need'] if s0 else '-'}"
                f" | ok dopo {c.first_ok_dt}s perdita {first['loss'] if first else '-'} €")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("report")
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:  # console Windows cp1252: il report usa ≥/→/€
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    lines = read_lines([Path(f) for f in a.files])
    rep = build_report(lines)
    if a.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(format_report(rep, cases=greenup_cases(lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
