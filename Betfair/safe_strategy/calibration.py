"""calibration.py — CALIBRAZIONE delle probabilita' del modello opportunita'
sui NOSTRI dati registrati (`_live_raw`), puro: nessuna rete, nessun DB.

Domanda: "quando il modello dice 92%, quante volte succede davvero?". La
risposta sono le TABELLE DI AFFIDABILITA' per famiglia di mercato × fascia di
minuti × bin di probabilita' (n, p media dichiarata, frequenza realizzata,
Brier). Da quelle si stima una correzione MONOTONA ``p_cal = f(p_model)``:

  · per ogni bin: media pesata tra la frequenza reale e la probabilita' del
    modello, con SHRINKAGE verso l'identita' (peso ``shrink_n`` campioni): un
    bin con 5 campioni non sposta quasi nulla, uno con 500 comanda;
  · poi PAV (pool-adjacent-violators, isotonic) sui nodi pesati per n: la
    correzione non puo' MAI invertire l'ordine (p piu' alta → p_cal piu' alta);
  · interpolazione lineare tra i nodi, estremi (0,0) e (1,1) fissi: mai oltre
    0/1, mai una certezza toccata (p=0 e p=1 passano invariate);
  · tabelle con meno di ``min_n`` campioni → identita' (n piccolo = si sta zitti).

Le famiglie: ``mo`` (1X2), ``ou_line`` (Over/Under, tutte le linee insieme),
``btts``, ``ht`` (1X2 primo tempo), ``cs_any_other`` (aggregati del Correct
Score), ``cs_cell`` (celle del Correct Score), ``hts_cell`` (Half Time Score).

API:
  reliability_table(samples)          → righe famiglia × fascia × bin
  fit_calibration(samples, ...)       → dict serializzabile (tables + meta)
  Calibrator.load(path) / from_dict   → .apply(p, family, minute), .info()
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FAMILIES: Tuple[str, ...] = (
    "mo", "ou_line", "btts", "ht", "cs_any_other", "cs_cell", "hts_cell",
)
# fasce di minuti: l'ultima assorbe il recupero (mai un '90-105' con 3 campioni)
MINUTE_BUCKETS: Tuple[Tuple[int, int], ...] = (
    (0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90),
)
N_BINS = 10
DEFAULT_MIN_N = 50        # sotto: la tabella e' identita'
DEFAULT_SHRINK_N = 50     # peso (in campioni) dell'identita' in ogni bin
_EPS = 1e-6

DEFAULT_CALIBRATION_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "opp_calibration.json",
)


@dataclass(frozen=True)
class CalSample:
    """Un campione (p dichiarata dal modello, esito reale 0/1)."""

    family: str
    minute: int
    p_model: float
    outcome: int
    event_id: str = ""


def bucket_of(minute: Optional[int]) -> str:
    """Minuto → etichetta della fascia ('0-15' … '75-90')."""
    m = 0 if minute is None else int(minute)
    if m < 0:
        m = 0
    for lo, hi in MINUTE_BUCKETS:
        if lo <= m < hi:
            return f"{lo}-{hi}"
    lo, hi = MINUTE_BUCKETS[-1]
    return f"{lo}-{hi}"


def family_of_market(market_type: Optional[str], prob_key: Optional[str] = None) -> Optional[str]:
    """market_type del feed (+ chiave del book) → famiglia di calibrazione."""
    mt = str(market_type or "").upper()
    if mt == "MATCH_ODDS":
        return "mo"
    if mt.startswith("OVER_UNDER"):
        return "ou_line"
    if mt == "BOTH_TEAMS_TO_SCORE":
        return "btts"
    if mt == "HALF_TIME":
        return "ht"
    if mt == "CORRECT_SCORE":
        return "cs_any_other" if "any_" in str(prob_key or "") else "cs_cell"
    if mt == "HALF_TIME_SCORE":
        return "hts_cell"
    return None


def _bin_index(p: float, n_bins: int = N_BINS) -> int:
    if p >= 1.0:
        return n_bins - 1
    if p <= 0.0:
        return 0
    return min(n_bins - 1, int(p * n_bins))


def _table_key(family: str, bucket: str) -> str:
    return f"{family}|{bucket}"


# ---------------------------------------------------------------------------
# Tabelle di affidabilita'
# ---------------------------------------------------------------------------
def reliability_table(samples: Iterable[CalSample], n_bins: int = N_BINS) -> List[Dict[str, Any]]:
    """Righe {family, bucket, bin_lo, bin_hi, n, p_mean, realised, brier}
    ordinate per famiglia, fascia, bin."""
    acc: Dict[Tuple[str, str, int], List[float]] = {}
    for s in samples:
        key = (s.family, bucket_of(s.minute), _bin_index(float(s.p_model), n_bins))
        node = acc.setdefault(key, [0.0, 0.0, 0.0, 0.0])
        node[0] += 1
        node[1] += float(s.p_model)
        node[2] += int(s.outcome)
        node[3] += (float(s.p_model) - int(s.outcome)) ** 2
    order = {f: i for i, f in enumerate(FAMILIES)}
    rows: List[Dict[str, Any]] = []
    for (fam, bucket, b), (n, sp, so, sb) in sorted(
        acc.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][0], int(kv[0][1].split("-")[0]), kv[0][2]),
    ):
        rows.append({
            "family": fam, "bucket": bucket,
            "bin_lo": b / n_bins, "bin_hi": (b + 1) / n_bins,
            "n": int(n), "p_mean": sp / n, "realised": so / n, "brier": sb / n,
        })
    return rows


def brier(samples: Sequence[CalSample], calibrator: Optional["Calibrator"] = None) -> Optional[float]:
    """Brier medio (con o senza calibrazione). None senza campioni."""
    n = 0
    tot = 0.0
    for s in samples:
        p = float(s.p_model)
        if calibrator is not None:
            p = calibrator.apply(p, s.family, s.minute)
        tot += (p - int(s.outcome)) ** 2
        n += 1
    return tot / n if n else None


def ece(samples: Sequence[CalSample], calibrator: Optional["Calibrator"] = None,
        n_bins: int = N_BINS) -> Optional[float]:
    """Expected Calibration Error: media pesata di |p media − frequenza reale|
    sui bin di probabilita' (pooled su tutte le famiglie)."""
    acc: Dict[int, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    n_tot = 0
    for s in samples:
        p = float(s.p_model)
        if calibrator is not None:
            p = calibrator.apply(p, s.family, s.minute)
        node = acc[_bin_index(p, n_bins)]
        node[0] += 1
        node[1] += p
        node[2] += int(s.outcome)
        n_tot += 1
    if not n_tot:
        return None
    return sum(n * abs(sp / n - so / n) for n, sp, so in acc.values()) / n_tot


# ---------------------------------------------------------------------------
# Fit: shrinkage + isotonic
# ---------------------------------------------------------------------------
def _pav(xs: Sequence[float], ys: Sequence[float], ws: Sequence[float]) -> List[float]:
    """Pool-adjacent-violators: regressione isotonica NON decrescente pesata."""
    blocks: List[List[float]] = []   # [somma y*w, somma w, count]
    for y, w in zip(ys, ws):
        blocks.append([y * w, w, 1])
        while len(blocks) >= 2 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            b = blocks.pop()
            blocks[-1][0] += b[0]
            blocks[-1][1] += b[1]
            blocks[-1][2] += b[2]
    out: List[float] = []
    for sy, sw, cnt in blocks:
        out.extend([sy / sw] * int(cnt))
    return out


def fit_table(samples: Sequence[CalSample], *, min_n: int = DEFAULT_MIN_N,
              shrink_n: float = DEFAULT_SHRINK_N, n_bins: int = N_BINS) -> Dict[str, Any]:
    """Tabella di UNA coppia (famiglia, fascia): bins + nodi monotoni."""
    n_tot = len(samples)
    acc: Dict[int, List[float]] = {}
    for s in samples:
        node = acc.setdefault(_bin_index(float(s.p_model), n_bins), [0.0, 0.0, 0.0, 0.0])
        node[0] += 1
        node[1] += float(s.p_model)
        node[2] += int(s.outcome)
        node[3] += (float(s.p_model) - int(s.outcome)) ** 2
    bins: List[Dict[str, Any]] = []
    xs: List[float] = []
    ys: List[float] = []
    ws: List[float] = []
    for b in sorted(acc):
        n, sp, so, sb = acc[b]
        p_mean, realised = sp / n, so / n
        bins.append({"bin_lo": b / n_bins, "bin_hi": (b + 1) / n_bins, "n": int(n),
                     "p_mean": round(p_mean, 6), "realised": round(realised, 6),
                     "brier": round(sb / n, 6)})
        # shrinkage verso l'identita': con n piccolo il nodo resta ~ p_mean
        corrected = (n * realised + float(shrink_n) * p_mean) / (n + float(shrink_n))
        xs.append(p_mean)
        ys.append(corrected)
        ws.append(n)
    applied = n_tot >= int(min_n) and len(xs) >= 1
    knots: List[List[float]] = []
    if applied:
        iso = _pav(xs, ys, ws)
        merged: Dict[float, Tuple[float, float]] = {}
        for x, y, w in zip(xs, iso, ws):
            x = round(x, 6)
            if x in merged:                # x duplicati: media pesata
                y0, w0 = merged[x]
                merged[x] = ((y0 * w0 + y * w) / (w0 + w), w0 + w)
            else:
                merged[x] = (y, w)
        knots = [[x, max(0.0, min(1.0, y))] for x, (y, _w) in sorted(merged.items())]
        # con gli estremi fissi (0,0) e (1,1) la spezzata resta monotona
        for i in range(1, len(knots)):
            knots[i][1] = max(knots[i][1], knots[i - 1][1])
    return {"n": int(n_tot), "applied": bool(applied), "bins": bins, "knots": knots}


def fit_calibration(samples: Sequence[CalSample], *, min_n: int = DEFAULT_MIN_N,
                    shrink_n: float = DEFAULT_SHRINK_N, n_bins: int = N_BINS,
                    n_events: Optional[int] = None) -> Dict[str, Any]:
    """Fit completo (tutte le famiglie × fasce) → dict serializzabile.

    ``meta`` porta Brier/ECE prima e dopo IN-SAMPLE e, se i campioni portano
    ``event_id``, una cross-validation a 2 fold PER EVENTO (fit sugli eventi
    pari, valutazione sui dispari e viceversa): e' il numero onesto.
    """
    groups: Dict[Tuple[str, str], List[CalSample]] = defaultdict(list)
    for s in samples:
        groups[(s.family, bucket_of(s.minute))].append(s)
    tables: Dict[str, Dict[str, Any]] = {}
    for (fam, bucket), grp in sorted(groups.items()):
        tables[_table_key(fam, bucket)] = fit_table(grp, min_n=min_n, shrink_n=shrink_n, n_bins=n_bins)
    cal = Calibrator({"version": 1, "tables": tables, "meta": {}})
    events = sorted({s.event_id for s in samples if s.event_id})
    meta: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_events": int(n_events if n_events is not None else len(events)),
        "n_samples": len(samples),
        "min_n": int(min_n), "shrink_n": float(shrink_n), "n_bins": int(n_bins),
        "brier_before": brier(samples), "brier_after": brier(samples, cal),
        "ece_before": ece(samples), "ece_after": ece(samples, cal),
        "families": {f: sum(1 for s in samples if s.family == f) for f in FAMILIES},
        "tables_applied": sum(1 for t in tables.values() if t["applied"]),
        "tables_total": len(tables),
    }
    if len(events) >= 2:
        meta.update(_cross_validate(samples, events, min_n=min_n, shrink_n=shrink_n, n_bins=n_bins))
    return {"version": 1, "meta": meta, "tables": tables}


def _cross_validate(samples: Sequence[CalSample], events: Sequence[str], **kw: Any) -> Dict[str, Any]:
    fold = {e: i % 2 for i, e in enumerate(events)}
    tot_before = tot_after = 0.0
    n = 0
    for k in (0, 1):
        train = [s for s in samples if fold.get(s.event_id) != k]
        test = [s for s in samples if fold.get(s.event_id) == k]
        if not train or not test:
            continue
        groups: Dict[Tuple[str, str], List[CalSample]] = defaultdict(list)
        for s in train:
            groups[(s.family, bucket_of(s.minute))].append(s)
        tables = {_table_key(f, b): fit_table(g, **kw) for (f, b), g in groups.items()}
        cal = Calibrator({"version": 1, "tables": tables, "meta": {}})
        for s in test:
            tot_before += (float(s.p_model) - s.outcome) ** 2
            tot_after += (cal.apply(float(s.p_model), s.family, s.minute) - s.outcome) ** 2
            n += 1
    if not n:
        return {}
    return {"brier_cv_before": tot_before / n, "brier_cv_after": tot_after / n, "cv_n": n}


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------
class Calibrator:
    """Applica le tabelle: ``apply(p, family, minute)`` → p calibrata."""

    def __init__(self, data: Optional[Dict[str, Any]] = None, *, path: Optional[str] = None) -> None:
        data = data or {}
        self.tables: Dict[str, Dict[str, Any]] = dict(data.get("tables") or {})
        self.meta: Dict[str, Any] = dict(data.get("meta") or {})
        self.path = path

    # ------------------------------------------------------------ costruzione
    @classmethod
    def identity(cls) -> "Calibrator":
        return cls({})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Calibrator":
        return cls(data)

    @classmethod
    def load(cls, path: str) -> "Calibrator":
        """Legge il JSON; file assente o rotto → identita' (mai un'eccezione
        che fermi lo scanner per una tabella)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError, TypeError):
            return cls({}, path=path)
        return cls(data if isinstance(data, dict) else {}, path=path)

    def to_dict(self) -> Dict[str, Any]:
        return {"version": 1, "meta": self.meta, "tables": self.tables}

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1, sort_keys=True)

    # ------------------------------------------------------------- interrogazione
    @property
    def empty(self) -> bool:
        return not any(t.get("applied") for t in self.tables.values())

    def lookup(self, family: Optional[str], minute: Optional[int]) -> Tuple[bool, int]:
        """(tabella applicata?, n campioni della coppia famiglia/fascia)."""
        if not family:
            return False, 0
        t = self.tables.get(_table_key(family, bucket_of(minute)))
        if not t:
            return False, 0
        return bool(t.get("applied")) and bool(t.get("knots")), int(t.get("n") or 0)

    def apply(self, p: float, family: Optional[str], minute: Optional[int]) -> float:
        """p calibrata: monotona, mai oltre (0,1), identita' con n piccolo o
        famiglia sconosciuta; le certezze (p<=0, p>=1) passano invariate."""
        try:
            p = float(p)
        except (TypeError, ValueError):
            return p
        if not math.isfinite(p) or p <= 0.0 or p >= 1.0 or not family:
            return p
        t = self.tables.get(_table_key(family, bucket_of(minute)))
        if not t or not t.get("applied"):
            return p
        knots = t.get("knots") or []
        if not knots:
            return p
        pts: List[Tuple[float, float]] = [(0.0, 0.0)]
        pts += [(float(x), float(y)) for x, y in knots]
        pts.append((1.0, 1.0))
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= p <= x1:
                if x1 - x0 <= _EPS:
                    out = max(y0, y1)
                else:
                    out = y0 + (y1 - y0) * (p - x0) / (x1 - x0)
                return max(_EPS, min(1.0 - _EPS, out))
        return p

    def info(self) -> Dict[str, Any]:
        """Riassunto (meta + tabelle applicate) per log/UI."""
        applied = {k: int(t.get("n") or 0) for k, t in self.tables.items() if t.get("applied")}
        return {
            "path": self.path,
            "loaded": bool(self.tables),
            "n_events": self.meta.get("n_events"),
            "n_samples": self.meta.get("n_samples"),
            "created_at": self.meta.get("created_at"),
            "brier_before": self.meta.get("brier_before"),
            "brier_after": self.meta.get("brier_after"),
            "brier_cv_before": self.meta.get("brier_cv_before"),
            "brier_cv_after": self.meta.get("brier_cv_after"),
            "ece_before": self.meta.get("ece_before"),
            "ece_after": self.meta.get("ece_after"),
            "tables_applied": len(applied),
            "tables_total": len(self.tables),
            "applied": applied,
        }


def format_reliability(rows: Sequence[Dict[str, Any]]) -> str:
    """Tabella ASCII (console Windows cp1252: mai caratteri non ASCII)."""
    head = (f"{'famiglia':<13}{'fascia':>7}{'bin':>12}{'n':>7}{'p_media':>9}"
            f"{'reale':>8}{'errore':>8}{'brier':>8}")
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(
            f"{r['family']:<13}{r['bucket']:>7}{r['bin_lo']:>6.1f}-{r['bin_hi']:<5.1f}"
            f"{r['n']:>7}{r['p_mean']:>9.3f}{r['realised']:>8.3f}"
            f"{r['p_mean'] - r['realised']:>+8.3f}{r['brier']:>8.4f}"
        )
    return "\n".join(out)
