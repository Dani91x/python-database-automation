"""Validazione delle registrazioni raw (`_live_raw/<event>/<event>.raw.jsonl`).

PROBLEMA (indagine 2026-07-16): il recorder produce registrazioni PARZIALI.
La registrazione esiste solo nell'INTERSEZIONE tra la vita del runner/stream e
la vita del follow — NON copre automaticamente la partita. Cause osservate:

  * inizio tardivo   — evento seguito (o runner avviato) a partita gia' in corso;
  * troncamento      — runner spento / stream morto prima del fischio finale;
  * buchi interni    — ricostruzioni della subscription (F3), retry con backoff,
                       cadute di rete: gap CONDIVISI da tutti gli eventi simultanei;
  * raw mancante     — stream mai connesso per quel follow (es. incidente 16/07:
                       stream muto per ~1.5h con runner vivo → nessun file).

Un backtest su un raw monco MENTE (gol/fasi mai visti dal simulatore). Questo
modulo classifica ogni registrazione COMPLETA/PARZIALE con una % di copertura
della finestra attesa della partita, cosi' i backtest possono filtrare.

Definizioni:
  * kickoff        = min(openDate|marketTime) tra le marketDefinition nel raw;
  * finestra attesa= [kickoff, kickoff + 115'] (90' + intervallo + recupero);
  * gap            = distanza > 60s tra i publish-time (pt) di due righe adiacenti;
  * copertura      = quota % della finestra attesa coperta da [first_pt, last_pt]
                     al netto dei gap interni alla finestra.

Verdetti: COMPLETE (copertura >= soglia, default 90%), PARTIAL, EMPTY (file senza
righe utili), NO_RAW (file assente), UNKNOWN (kickoff non determinabile).

Uso CLI:
    python -m Betfair.stream.tools.validate_recordings                # tutti gli eventi
    python -m Betfair.stream.tools.validate_recordings 35828026 ...   # solo alcuni
    python -m Betfair.stream.tools.validate_recordings --min-coverage 95 --ids-only
    python -m Betfair.stream.tools.validate_recordings --json

API per i backtest (run_backtest / run_theta):
    check_events_for_backtest(event_ids, data_dir, min_coverage)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# soglia oltre cui due pt adiacenti sono un "buco" di registrazione (secondi)
GAP_THRESHOLD_S: float = 60.0
# finestra attesa della partita dal kickoff (90' + intervallo + recupero tipico)
MATCH_WINDOW_MIN: float = 115.0
# copertura minima (percento) perche' una registrazione sia COMPLETE
DEFAULT_MIN_COVERAGE_PCT: float = 90.0
# tolleranza (secondi) sull'inizio: prima di questa NON e' "inizio tardivo"
LATE_START_TOLERANCE_S: float = 120.0
# fine attesa minima (minuti dal kickoff) sotto cui, senza CLOSED, e' "troncata"
TRUNCATED_BEFORE_MIN: float = 95.0

VERDICT_COMPLETE = "COMPLETE"
VERDICT_PARTIAL = "PARTIAL"
VERDICT_EMPTY = "EMPTY"
VERDICT_NO_RAW = "NO_RAW"
VERDICT_UNKNOWN = "UNKNOWN"


@dataclass
class RawScan:
    """Statistiche PURE estratte da un file `.raw.jsonl` (una sola passata)."""

    n_lines: int = 0
    bad_lines: int = 0
    first_pt: Optional[int] = None
    last_pt: Optional[int] = None
    kickoff_ms: Optional[int] = None
    closed_seen: bool = False
    first_inplay_pt: Optional[int] = None
    gaps: List[Tuple[int, int]] = field(default_factory=list)  # [(pt_prima, pt_dopo)]


@dataclass
class RecordingReport:
    """Esito della validazione di una registrazione per-evento."""

    event_id: str
    raw_path: str
    verdict: str
    coverage_pct: Optional[float]
    reasons: List[str] = field(default_factory=list)
    n_lines: int = 0
    size_bytes: int = 0
    first_pt: Optional[int] = None
    last_pt: Optional[int] = None
    kickoff_ms: Optional[int] = None
    start_delay_min: Optional[float] = None    # >0 = registrazione iniziata DOPO il kickoff
    end_offset_min: Optional[float] = None     # ultimo pt in minuti dal kickoff
    gaps_in_window: List[Tuple[int, int]] = field(default_factory=list)
    gap_in_window_min: float = 0.0
    closed_seen: bool = False
    has_scores: bool = False
    sessions: List[Dict[str, Any]] = field(default_factory=list)  # da .recmeta.jsonl

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "verdict": self.verdict,
            "coverage_pct": self.coverage_pct,
            "reasons": list(self.reasons),
            "n_lines": self.n_lines,
            "size_bytes": self.size_bytes,
            "first_pt": self.first_pt,
            "last_pt": self.last_pt,
            "kickoff_ms": self.kickoff_ms,
            "start_delay_min": self.start_delay_min,
            "end_offset_min": self.end_offset_min,
            "gaps_in_window": [list(g) for g in self.gaps_in_window],
            "gap_in_window_min": self.gap_in_window_min,
            "closed_seen": self.closed_seen,
            "has_scores": self.has_scores,
            "n_sessions": len(self.sessions),
        }


def _parse_start_ms(md: Dict[str, Any]) -> Optional[int]:
    """openDate|marketTime (ISO con 'Z') → epoch ms; None se non parsabile."""
    for key in ("openDate", "marketTime"):
        raw = md.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    return None


def scan_raw(path: str, gap_threshold_s: float = GAP_THRESHOLD_S) -> RawScan:
    """Una passata sul raw nativo: pt primo/ultimo, gap, kickoff, CLOSED visti.

    Tollerante alle righe corrotte (contate in ``bad_lines``, mai eccezioni).
    """
    scan = RawScan()
    prev_pt: Optional[int] = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                scan.bad_lines += 1
                continue
            if not isinstance(msg, dict) or msg.get("op") != "mcm":
                continue
            scan.n_lines += 1
            pt = msg.get("pt")
            if isinstance(pt, (int, float)):
                pt = int(pt)
                if scan.first_pt is None:
                    scan.first_pt = pt
                if prev_pt is not None and pt - prev_pt > gap_threshold_s * 1000:
                    scan.gaps.append((prev_pt, pt))
                prev_pt = pt
                scan.last_pt = pt
            for change in msg.get("mc") or []:
                md = change.get("marketDefinition") if isinstance(change, dict) else None
                if not isinstance(md, dict):
                    continue
                start_ms = _parse_start_ms(md)
                if start_ms is not None and (scan.kickoff_ms is None or start_ms < scan.kickoff_ms):
                    scan.kickoff_ms = start_ms
                if md.get("inPlay") and scan.first_inplay_pt is None and isinstance(pt, int):
                    scan.first_inplay_pt = pt
                if md.get("status") == "CLOSED":
                    scan.closed_seen = True
    return scan


def _overlap_ms(a0: int, a1: int, b0: int, b1: int) -> int:
    """Lunghezza (ms) dell'intersezione [a0,a1] ∩ [b0,b1] (0 se disgiunti)."""
    return max(0, min(a1, b1) - max(a0, b0))


def classify(
    scan: RawScan,
    *,
    min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT,
    match_window_min: float = MATCH_WINDOW_MIN,
) -> Tuple[str, Optional[float], List[str], List[Tuple[int, int]]]:
    """PURA: (verdetto, copertura %, motivi, gap in-finestra) da una RawScan."""
    if scan.n_lines == 0 or scan.first_pt is None or scan.last_pt is None:
        return VERDICT_EMPTY, 0.0, ["nessuna riga mcm utile nel raw"], []

    kickoff = scan.kickoff_ms if scan.kickoff_ms is not None else scan.first_inplay_pt
    if kickoff is None:
        return (
            VERDICT_UNKNOWN,
            None,
            ["kickoff non determinabile (nessuna marketDefinition con openDate/marketTime)"],
            [],
        )

    win_a = int(kickoff)
    win_b = int(kickoff + match_window_min * 60_000)
    reasons: List[str] = []

    gaps_in_window = [
        (a, b) for a, b in scan.gaps if _overlap_ms(a, b, win_a, win_b) > 0
    ]
    gap_ms = sum(_overlap_ms(a, b, win_a, win_b) for a, b in gaps_in_window)
    covered_ms = _overlap_ms(scan.first_pt, scan.last_pt, win_a, win_b) - gap_ms
    coverage = max(0.0, min(100.0, 100.0 * covered_ms / (win_b - win_a)))

    start_delay_min = (scan.first_pt - kickoff) / 60_000.0
    end_offset_min = (scan.last_pt - kickoff) / 60_000.0
    if scan.last_pt <= win_a:
        reasons.append("solo pre-match (nessun dato dopo il kickoff)")
    if scan.first_pt - kickoff > LATE_START_TOLERANCE_S * 1000:
        reasons.append(f"inizio tardivo (+{start_delay_min:.0f}m dal kickoff)")
    if not scan.closed_seen and end_offset_min < TRUNCATED_BEFORE_MIN:
        reasons.append(
            f"fine troncata (ultimo dato a ko+{end_offset_min:.0f}m, nessun mercato CLOSED)"
        )
    if gaps_in_window:
        reasons.append(
            f"{len(gaps_in_window)} buchi interni in-finestra ({gap_ms / 60_000.0:.1f}m persi)"
        )

    verdict = VERDICT_COMPLETE if coverage >= min_coverage_pct else VERDICT_PARTIAL
    return verdict, round(coverage, 1), reasons, gaps_in_window


def _load_recmeta(path: str) -> List[Dict[str, Any]]:
    """Legge il sidecar `.recmeta.jsonl` (sessioni di registrazione), best-effort."""
    if not os.path.isfile(path):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        return out
    return out


def validate_event(
    data_dir: str,
    event_id: str,
    *,
    min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT,
) -> RecordingReport:
    """Valida la registrazione di UN evento (raw + sidecar scores/recmeta)."""
    ev_dir = os.path.join(data_dir, str(event_id))
    raw_path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
    scores_path = os.path.join(ev_dir, f"{event_id}.scores.jsonl")
    recmeta_path = os.path.join(ev_dir, f"{event_id}.recmeta.jsonl")
    has_scores = os.path.isfile(scores_path)
    sessions = _load_recmeta(recmeta_path)

    if not os.path.isfile(raw_path):
        return RecordingReport(
            event_id=str(event_id),
            raw_path=raw_path,
            verdict=VERDICT_NO_RAW,
            coverage_pct=0.0,
            reasons=["file raw mancante"],
            has_scores=has_scores,
            sessions=sessions,
        )

    scan = scan_raw(raw_path)
    verdict, coverage, reasons, gaps_in_window = classify(
        scan, min_coverage_pct=min_coverage_pct
    )
    kickoff = scan.kickoff_ms if scan.kickoff_ms is not None else scan.first_inplay_pt
    report = RecordingReport(
        event_id=str(event_id),
        raw_path=raw_path,
        verdict=verdict,
        coverage_pct=coverage,
        reasons=reasons,
        n_lines=scan.n_lines,
        size_bytes=os.path.getsize(raw_path),
        first_pt=scan.first_pt,
        last_pt=scan.last_pt,
        kickoff_ms=kickoff,
        closed_seen=scan.closed_seen,
        has_scores=has_scores,
        sessions=sessions,
        gaps_in_window=gaps_in_window,
        gap_in_window_min=round(
            sum((b - a) for a, b in gaps_in_window) / 60_000.0, 1
        ),
    )
    if kickoff is not None and scan.first_pt is not None:
        report.start_delay_min = round((scan.first_pt - kickoff) / 60_000.0, 1)
    if kickoff is not None and scan.last_pt is not None:
        report.end_offset_min = round((scan.last_pt - kickoff) / 60_000.0, 1)
    return report


def iter_event_ids(data_dir: str) -> List[str]:
    """Eventi presenti in ``data_dir``: cartelle (non riservate ``_*``/``.*``)
    che contengono almeno un sidecar noto (`raw`/`scores`)."""
    out: List[str] = []
    try:
        entries = sorted(os.listdir(data_dir))
    except OSError:
        return out
    for name in entries:
        if name.startswith(("_", ".")):
            continue
        ev_dir = os.path.join(data_dir, name)
        if not os.path.isdir(ev_dir):
            continue
        if os.path.isfile(os.path.join(ev_dir, f"{name}.raw.jsonl")) or os.path.isfile(
            os.path.join(ev_dir, f"{name}.scores.jsonl")
        ):
            out.append(name)
    return out


def validate_all(
    data_dir: str, *, min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT
) -> List[RecordingReport]:
    """Valida tutte le registrazioni in ``data_dir``."""
    return [
        validate_event(data_dir, ev, min_coverage_pct=min_coverage_pct)
        for ev in iter_event_ids(data_dir)
    ]


def check_events_for_backtest(
    event_ids: Sequence[str],
    data_dir: str,
    min_coverage: Optional[float] = None,
) -> List[str]:
    """Guardia per i backtest: valida gli ``event_ids`` richiesti.

    * ``min_coverage=None`` (default, comportamento storico): NESSUN filtro —
      ogni registrazione non-COMPLETE produce solo un WARNING visibile.
    * ``min_coverage=<pct>``: gli eventi con copertura NOTA sotto soglia vengono
      ESCLUSI (warning con motivo); kickoff ignoto (UNKNOWN) → incluso per
      prudenza. Se il filtro svuota la lista → ValueError (il backtest non deve
      girare "verde" su zero eventi senza dirlo).
    """
    kept: List[str] = []
    for ev in event_ids:
        ev = str(ev)
        try:
            rep = validate_event(data_dir, ev)
        except Exception as exc:  # noqa: BLE001 - la guardia non rompe il backtest
            logger.warning("[recordings] validazione %s KO (incluso comunque): %s", ev, exc)
            kept.append(ev)
            continue
        if rep.verdict == VERDICT_COMPLETE:
            kept.append(ev)
            continue
        cov = "?" if rep.coverage_pct is None else f"{rep.coverage_pct:.0f}%"
        detail = "; ".join(rep.reasons) or "n/d"
        if min_coverage is None:
            logger.warning(
                "[recordings] evento %s: registrazione %s (copertura %s) — %s "
                "(incluso: nessun min_coverage richiesto)", ev, rep.verdict, cov, detail,
            )
            kept.append(ev)
        elif rep.coverage_pct is None:
            logger.warning(
                "[recordings] evento %s: copertura NON determinabile (%s) — %s "
                "(incluso per prudenza)", ev, rep.verdict, detail,
            )
            kept.append(ev)
        elif rep.coverage_pct >= float(min_coverage):
            logger.warning(
                "[recordings] evento %s: registrazione %s (copertura %s >= %.0f%% richiesto) — %s",
                ev, rep.verdict, cov, float(min_coverage), detail,
            )
            kept.append(ev)
        else:
            logger.warning(
                "[recordings] evento %s ESCLUSO dal backtest: registrazione %s "
                "(copertura %s < %.0f%%) — %s", ev, rep.verdict, cov, float(min_coverage), detail,
            )
    if min_coverage is not None and event_ids and not kept:
        raise ValueError(
            f"nessun evento con copertura >= {float(min_coverage):.0f}% "
            "(registrazioni parziali: vedi python -m Betfair.stream.tools.validate_recordings)"
        )
    return kept


def _fmt_ts(ms: Optional[int]) -> str:
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classifica le registrazioni raw COMPLETE/PARZIALI (copertura partita)."
    )
    parser.add_argument("event_ids", nargs="*", help="solo questi eventi (default: tutti)")
    parser.add_argument("--data-dir", default=None, help="radice dei raw (default: DATA_DIR)")
    parser.add_argument(
        "--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE_PCT,
        help=f"soglia %% per COMPLETE (default {DEFAULT_MIN_COVERAGE_PCT:.0f})",
    )
    parser.add_argument("--json", action="store_true", help="output JSON (una riga per evento)")
    parser.add_argument(
        "--ids-only", action="store_true",
        help="stampa SOLO gli event_id COMPLETE (per comporre i backtest)",
    )
    args = parser.parse_args(argv)

    data_dir = args.data_dir
    if data_dir is None:
        from ..config_stream import DATA_DIR  # import locale: CLI-only

        data_dir = DATA_DIR

    ids = [str(e) for e in args.event_ids] or iter_event_ids(data_dir)
    reports = [
        validate_event(data_dir, ev, min_coverage_pct=args.min_coverage) for ev in ids
    ]

    if args.ids_only:
        for r in reports:
            if r.verdict == VERDICT_COMPLETE:
                print(r.event_id)
        return 0
    if args.json:
        for r in reports:
            print(json.dumps(r.to_dict(), separators=(",", ":")))
        return 0

    n_complete = 0
    for r in reports:
        if r.verdict == VERDICT_COMPLETE:
            n_complete += 1
        cov = "  n/d" if r.coverage_pct is None else f"{r.coverage_pct:5.1f}"
        print(
            f"{r.event_id:>12}  {r.verdict:<8} cov={cov}%  "
            f"ko={_fmt_ts(r.kickoff_ms)}  primo={_fmt_ts(r.first_pt)}  "
            f"ultimo={_fmt_ts(r.last_pt)}  righe={r.n_lines}  "
            f"scores={'si' if r.has_scores else 'NO'}"
        )
        for reason in r.reasons:
            print(f"{'':>14}- {reason}")
    print(
        f"\n{len(reports)} registrazioni: {n_complete} COMPLETE, "
        f"{len(reports) - n_complete} non complete "
        f"(soglia {args.min_coverage:.0f}%)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
