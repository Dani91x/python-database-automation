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

LIMITE NOTO (trade-off deliberato verso la prudenza, review 17/07): senza il
CLOSED di un mercato PRINCIPALE nel raw la fine della partita non è confermata
e il verdetto non può MAI essere COMPLETE — anche per registrazioni "buone" il
cui unico difetto è un settlement lento (mercato principale rimasto SUSPENDED
oltre la fine della registrazione). Falso negativo accettato: meglio declassare
una registrazione buona che certificare COMPLETE una partita senza la fase
finale/supplementari. Con il default warning-only l'impatto è solo informativo;
diventa filtrante solo con ``min_coverage`` esplicito. Possibile evoluzione:
CLOSED "implicito" da SUSPENDED ininterrotto + punteggio finale dal sidecar.

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

# SPORT: `eventTypeId` di Betfair, che sta nella `marketDefinition` del raw.
# 1 = calcio, 2 = tennis. Non si passa da fuori: si LEGGE dal file, cosi' una
# registrazione non puo' essere validata con la finestra dello sport sbagliato
# per una svista di chi chiama.
EVENT_TYPE_CALCIO = "1"
EVENT_TYPE_TENNIS = "2"
SPORT_CALCIO = "calcio"
SPORT_TENNIS = "tennis"
# tolleranza (minuti) fra la durata della registrazione e quella che il sidecar
# dei punteggi dichiara: sotto, la registrazione e' piu' corta della partita
TOLLERANZA_SIDECAR_MIN: float = 5.0

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
    # pt dell'ULTIMA marketDefinition CLOSED dei mercati PRINCIPALI (full-match,
    # non di primo tempo): quando presente la fine REALE della partita è nota
    # (supplementari inclusi) — fix 17/07 "validatore cieco oltre KO+115'".
    main_closed_pt: Optional[int] = None
    first_inplay_pt: Optional[int] = None
    # `eventTypeId` della prima marketDefinition: decide QUALE FINESTRA usare
    event_type_id: str = ""
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
    # QUALE sidecar dei punteggi e' stato trovato ("" = nessuno). Il calcio
    # scrive `<id>.scores.jsonl`, il tennis `<id>.score.jsonl` (senza la "s"):
    # dirlo e' meta' della correzione, perche' un verdetto che non nomina il
    # file che ha letto non e' verificabile.
    scores_name: str = ""
    # SPORT letto dal raw e FINESTRA ATTESA usata per la copertura: due
    # registrazioni con la stessa percentuale ma finestre diverse non dicono la
    # stessa cosa, quindi il verdetto deve dichiarare quale ha usato.
    sport: str = ""
    finestra: str = ""
    # durata della partita secondo il sidecar dei punteggi (controllo di
    # plausibilita' del tennis): None = sidecar assente o illeggibile
    durata_sidecar_min: Optional[float] = None
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
            "scores_name": self.scores_name,
            "sport": self.sport,
            "finestra": self.finestra,
            "durata_sidecar_min": self.durata_sidecar_min,
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


def _is_main_market_type(market_type: Any) -> bool:
    """True se il marketType è un mercato FULL-MATCH (il suo CLOSED = fine partita).

    I mercati di primo tempo (HALF_TIME, FIRST_HALF_GOALS_*, HALF_TIME_SCORE,
    HALF_WITH_MOST_GOALS, ...) chiudono all'intervallo: il loro CLOSED NON prova
    la fine della partita. ECCEZIONE (fix 17/07, terza review):
    HALF_TIME_FULL_TIME (doppio risultato HT/FT) si liquida a FINE partita —
    il substring-match su "HALF" lo escludeva a torto dal ruolo di prova di
    fine-gara. marketType assente → True (prudenza/retro-compat).
    """
    mt = str(market_type or "").upper()
    if not mt:
        return True
    return "HALF" not in mt or mt == "HALF_TIME_FULL_TIME"


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
                if not scan.event_type_id and md.get("eventTypeId") is not None:
                    scan.event_type_id = str(md.get("eventTypeId"))
                start_ms = _parse_start_ms(md)
                if start_ms is not None and (scan.kickoff_ms is None or start_ms < scan.kickoff_ms):
                    scan.kickoff_ms = start_ms
                if md.get("inPlay") and scan.first_inplay_pt is None and isinstance(pt, int):
                    scan.first_inplay_pt = pt
                if md.get("status") == "CLOSED":
                    scan.closed_seen = True
                    if _is_main_market_type(md.get("marketType")) and isinstance(pt, int):
                        scan.main_closed_pt = max(scan.main_closed_pt or 0, pt)
    return scan


def _overlap_ms(a0: int, a1: int, b0: int, b1: int) -> int:
    """Lunghezza (ms) dell'intersezione [a0,a1] ∩ [b0,b1] (0 se disgiunti)."""
    return max(0, min(a1, b1) - max(a0, b0))


def sport_di(scan: RawScan) -> str:
    """Lo sport della registrazione, dal raw. Default: calcio (retro-compat)."""
    return SPORT_TENNIS if str(scan.event_type_id or "") == EVENT_TYPE_TENNIS         else SPORT_CALCIO


def durata_sidecar_min(path: Optional[str]) -> Optional[float]:
    """Durata della partita secondo il SIDECAR dei punteggi, in minuti.

    E' il controllo di plausibilita' della finestra del tennis: il raw dice
    quanto ha registrato, il sidecar dice quanto e' durata la partita. Se la
    registrazione e' piu' corta, la finestra «dal primo book al CLOSED» sta
    misurando un pezzo di partita e lo deve dichiarare, altrimenti una
    registrazione che comincia al terzo set risulterebbe coperta al 100 %.

    Legge i due formati veri: calcio `{"ts_ms":…}`, tennis `{"t": <epoch s>}`.
    None = sidecar assente, vuoto o illeggibile (nessun controllo possibile)."""
    if not path or not os.path.isfile(path):
        return None
    primo = ultimo = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for riga in fh:
            riga = riga.strip()
            if not riga:
                continue
            try:
                rec = json.loads(riga)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            ts = rec.get("ts_ms")
            if ts is None and rec.get("t") is not None:
                try:
                    ts = float(rec["t"]) * 1000.0
                except (TypeError, ValueError):
                    ts = None
            if ts is None:
                continue
            ts = float(ts)
            primo = ts if primo is None else min(primo, ts)
            ultimo = ts if ultimo is None else max(ultimo, ts)
    if primo is None or ultimo is None or ultimo <= primo:
        return None
    return round((ultimo - primo) / 60_000.0, 1)


def classify(
    scan: RawScan,
    *,
    min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT,
    match_window_min: float = MATCH_WINDOW_MIN,
    sessions: Optional[List[Dict[str, Any]]] = None,
    sport: Optional[str] = None,
    durata_partita_min: Optional[float] = None,
) -> Tuple[str, Optional[float], List[str], List[Tuple[int, int]], str]:
    """PURA: (verdetto, copertura %, motivi, gap in-finestra) da una RawScan.

    Torna anche la FINESTRA usata, in chiaro: due registrazioni con la stessa
    percentuale ma finestre diverse non dicono la stessa cosa.

    LA FINESTRA DIPENDE DALLO SPORT (16/09).
      * CALCIO — invariata: [kickoff, kickoff + ``match_window_min``], estesa
        al CLOSED del mercato principale o all'ultima attivita'.
      * TENNIS — una partita di tennis NON ha una durata attesa (3 set possono
        durare 50 minuti o 3 ore e mezza: misurato su queste registrazioni, da
        61 a 235 minuti). Misurarla su una finestra di 115 minuti e' misurarla
        con il metro di un altro sport: una partita lunga risultava scoperta
        nella parte finale, una corta senza CLOSED al massimo al 50 %. La
        finestra attesa e' quindi **[primo book, CLOSED del mercato]**, e
        l'ultimo book quando il CLOSED non c'e'.
        Il prezzo di quella scelta e' che l'INIZIO TARDIVO non si vede piu' da
        solo (chi comincia al terzo set coprirebbe il 100 % di cio' che ha
        registrato): lo dice il CONTROLLO DI PLAUSIBILITA'
        ``durata_partita_min`` (dal sidecar set/game). Registrazione piu' corta
        della partita = motivo esplicito e MAI ``COMPLETE``.

    ``sessions`` (opzionale, fix 17/07 terza review): i marker del sidecar
    ``.recmeta.jsonl`` (open/close/resubscribe). Non cambiano il verdetto ma
    ARRICCHISCONO i motivi: un buco che coincide con un marker è spiegato
    (restart del recorder/resubscribe F3), non un mistero forense."""
    sport = str(sport or sport_di(scan))
    if scan.n_lines == 0 or scan.first_pt is None or scan.last_pt is None:
        return VERDICT_EMPTY, 0.0, ["nessuna riga mcm utile nel raw"], [], ""

    kickoff = scan.kickoff_ms if scan.kickoff_ms is not None else scan.first_inplay_pt
    if kickoff is None and sport != SPORT_TENNIS:
        return (
            VERDICT_UNKNOWN,
            None,
            ["kickoff non determinabile (nessuna marketDefinition con openDate/marketTime)"],
            [],
            "",
        )

    reasons: List[str] = []
    if sport == SPORT_TENNIS:
        return _classify_tennis(scan, min_coverage_pct=min_coverage_pct,
                                sessions=sessions,
                                durata_partita_min=durata_partita_min,
                                kickoff=kickoff)

    win_a = int(kickoff)
    win_b = int(kickoff + match_window_min * 60_000)
    finestra = f"calcio: ko + {match_window_min:.0f}m"

    # FINE REALE (fix 17/07, "validatore cieco oltre KO+115'"):
    #  * CLOSED di un mercato principale nel raw → la fine vera è NOTA e la
    #    finestra attesa termina lì (partita chiusa prima dei 115' = COMPLETE
    #    legittimo; supplementari registrati fino in fondo = finestra estesa);
    #  * attività oltre KO+115' SENZA CLOSED (supplementari?) → la finestra si
    #    estende all'ultima attività vista (mai dichiarare coperta una fase
    #    che sappiamo esistere solo in parte).
    end_confirmed = scan.main_closed_pt is not None and scan.main_closed_pt > win_a
    if end_confirmed:
        win_b = max(int(scan.main_closed_pt), win_a + 60_000)  # type: ignore[arg-type]
        finestra = "calcio: ko -> CLOSED del mercato principale"
    elif scan.last_pt > win_b:
        reasons.append(
            f"attività oltre ko+{match_window_min:.0f}m senza CLOSED "
            f"(finestra estesa a ko+{(scan.last_pt - win_a) / 60_000.0:.0f}m)"
        )
        win_b = int(scan.last_pt)
        finestra = "calcio: ko -> ultima attivita' (nessun CLOSED)"

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
        # marker recmeta dentro (o a ridosso di) un buco = buco SPIEGATO da un
        # restart del recorder/resubscribe, non da un guasto ignoto.
        marker_ts = [
            int(s["ts_ms"]) for s in (sessions or [])
            if isinstance(s, dict) and isinstance(s.get("ts_ms"), (int, float))
            and str(s.get("kind")) in ("open", "resubscribe")
        ]
        if marker_ts:
            margin = 30_000  # il marker può precedere di poco il buco reale
            explained = sum(
                1 for a, b in gaps_in_window
                if any(a - margin <= ts <= b + margin for ts in marker_ts)
            )
            if explained:
                reasons.append(
                    f"{explained} buchi spiegati da restart/resubscribe del "
                    "recorder (marker recmeta)"
                )

    verdict = VERDICT_COMPLETE if coverage >= min_coverage_pct else VERDICT_PARTIAL
    # SENZA CLOSED dei mercati principali la fine vera è IGNOTA: una
    # registrazione che termina dopo il 95' "sembra" completa ma la partita può
    # essere andata oltre (recupero lungo, supplementari) con la fase decisiva
    # ASSENTE → mai COMPLETE (fix 17/07), verdetto sospetto con motivo esplicito.
    if not end_confirmed:
        if end_offset_min >= TRUNCATED_BEFORE_MIN:
            reasons.append(
                "fine NON confermata: nessun mercato principale CLOSED nel raw "
                "(possibile fase finale/supplementari mancante)"
            )
        if verdict == VERDICT_COMPLETE:
            verdict = VERDICT_PARTIAL
    return verdict, round(coverage, 1), reasons, gaps_in_window, finestra


def _classify_tennis(
    scan: RawScan,
    *,
    min_coverage_pct: float,
    sessions: Optional[List[Dict[str, Any]]],
    durata_partita_min: Optional[float],
    kickoff: Optional[int],
) -> Tuple[str, Optional[float], List[str], List[Tuple[int, int]], str]:
    """La finestra del TENNIS: dal primo book al CLOSED (o all'ultimo book).

    Il verdetto resta severo dove deve: senza CLOSED la fine e' IGNOTA e non si
    dichiara COMPLETE (stessa regola del calcio), e se il sidecar dice che la
    partita e' durata piu' di quanto si e' registrato, la registrazione e'
    parziale anche se dentro la sua finestra non ha buchi.
    """
    reasons: List[str] = []
    win_a = int(scan.first_pt)          # type: ignore[arg-type]
    fine_nota = scan.main_closed_pt is not None and scan.main_closed_pt > win_a
    if fine_nota:
        win_b = int(scan.main_closed_pt)        # type: ignore[arg-type]
        finestra = "tennis: primo book -> CLOSED del mercato"
    else:
        win_b = int(scan.last_pt)                # type: ignore[arg-type]
        finestra = "tennis: primo book -> ultimo book (nessun CLOSED)"
    if win_b <= win_a:
        return VERDICT_EMPTY, 0.0, ["registrazione di durata nulla"], [], finestra

    gaps_in_window = [(a, b) for a, b in scan.gaps if _overlap_ms(a, b, win_a, win_b) > 0]
    gap_ms = sum(_overlap_ms(a, b, win_a, win_b) for a, b in gaps_in_window)
    coverage = max(0.0, min(100.0, 100.0 * (win_b - win_a - gap_ms) / (win_b - win_a)))
    registrati_min = (win_b - win_a) / 60_000.0
    reasons.append(f"finestra tennis: {registrati_min:.0f}m registrati")
    if kickoff is not None and scan.first_pt - kickoff > LATE_START_TOLERANCE_S * 1000:
        reasons.append(
            f"registrazione iniziata +{(scan.first_pt - kickoff) / 60_000.0:.0f}m "
            f"dopo l'orario del mercato")
    if gaps_in_window:
        reasons.append(
            f"{len(gaps_in_window)} buchi interni in-finestra ({gap_ms / 60_000.0:.1f}m persi)")
        marker_ts = [int(x["ts_ms"]) for x in (sessions or [])
                     if isinstance(x, dict) and isinstance(x.get("ts_ms"), (int, float))
                     and str(x.get("kind")) in ("open", "resubscribe")]
        if marker_ts:
            spiegati = sum(1 for a, b in gaps_in_window
                           if any(a - 30_000 <= t <= b + 30_000 for t in marker_ts))
            if spiegati:
                reasons.append(f"{spiegati} buchi spiegati da restart/resubscribe "
                               f"del recorder (marker recmeta)")

    verdict = VERDICT_COMPLETE if coverage >= min_coverage_pct else VERDICT_PARTIAL
    # CONTROLLO DI PLAUSIBILITA': quanto e' durata la partita secondo il
    # sidecar (set/game) contro quanto si e' registrato. E' cio' che impedisce a
    # una registrazione cominciata al terzo set di dichiararsi coperta al 100 %.
    if durata_partita_min is not None:
        mancano = durata_partita_min - registrati_min
        if mancano > TOLLERANZA_SIDECAR_MIN:
            reasons.append(
                f"registrazione piu' CORTA della partita: il sidecar dei punteggi "
                f"copre {durata_partita_min:.0f}m, il raw {registrati_min:.0f}m "
                f"(mancano {mancano:.0f}m)")
            verdict = VERDICT_PARTIAL
    else:
        reasons.append("nessun sidecar dei punteggi: la durata della partita non e' "
                       "verificabile (finestra non falsificabile)")
    if not fine_nota:
        reasons.append("fine NON confermata: nessun mercato CLOSED nel raw")
        verdict = VERDICT_PARTIAL
    return verdict, round(coverage, 1), reasons, gaps_in_window, finestra


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


# NOMI DEL SIDECAR DEI PUNTEGGI, nell'ordine in cui si cercano.
# 16/09 - il validatore cercava SOLO `<id>.scores.jsonl`, che e' il nome del
# CALCIO (`Betfair/stream/runner.py`). Il recorder del TENNIS
# (`Betfair/stream/tennis_live/tennis_recorder.py`) scrive `<id>.score.jsonl`,
# al singolare: su OGNI registrazione tennis il verdetto usciva con `scores=NO`
# anche con centinaia di record dentro - un falso negativo sistematico, ed e' il
# difetto 32 del catalogo («sidecar cercato con il nome sbagliato»). Misurato su
# 35790650: 207 record nel sidecar, `has_scores` False.
SIDECAR_PUNTEGGI = ("scores.jsonl", "score.jsonl")


def _sidecar_punteggi(ev_dir: str, event_id: str) -> Tuple[Optional[str], str]:
    """(percorso, nome) del sidecar dei punteggi trovato; (None, "") se manca.

    Si prova prima il nome del calcio e poi quello del tennis, e il NOME
    trovato torna al chiamante e finisce nel referto: «l'ho letto» e «l'ho
    cercato con il nome giusto» sono due fatti diversi, e finora il referto
    diceva il primo senza aver fatto il secondo."""
    for suffisso in SIDECAR_PUNTEGGI:
        percorso = os.path.join(ev_dir, f"{event_id}.{suffisso}")
        if os.path.isfile(percorso):
            return percorso, f"{event_id}.{suffisso}"
    return None, ""


def validate_event(
    data_dir: str,
    event_id: str,
    *,
    min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT,
) -> RecordingReport:
    """Valida la registrazione di UN evento (raw + sidecar scores/recmeta)."""
    ev_dir = os.path.join(data_dir, str(event_id))
    raw_path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
    recmeta_path = os.path.join(ev_dir, f"{event_id}.recmeta.jsonl")
    scores_path, scores_name = _sidecar_punteggi(ev_dir, event_id)
    has_scores = scores_path is not None
    sessions = _load_recmeta(recmeta_path)

    if not os.path.isfile(raw_path):
        return RecordingReport(
            event_id=str(event_id),
            raw_path=raw_path,
            verdict=VERDICT_NO_RAW,
            coverage_pct=0.0,
            reasons=["file raw mancante"],
            has_scores=has_scores,
            scores_name=scores_name,
            sessions=sessions,
        )

    scan = scan_raw(raw_path)
    sport = sport_di(scan)
    # la DURATA VERA della partita dal sidecar: e' il controllo di plausibilita'
    # della finestra del tennis (vedi `classify`)
    durata = durata_sidecar_min(scores_path)
    verdict, coverage, reasons, gaps_in_window, finestra = classify(
        scan, min_coverage_pct=min_coverage_pct, sessions=sessions,
        sport=sport, durata_partita_min=durata,
    )
    kickoff = scan.kickoff_ms if scan.kickoff_ms is not None else scan.first_inplay_pt
    report = RecordingReport(
        sport=sport,
        finestra=finestra,
        durata_sidecar_min=durata,
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
        scores_name=scores_name,
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
        if (os.path.isfile(os.path.join(ev_dir, f"{name}.raw.jsonl"))
                or _sidecar_punteggi(ev_dir, name)[0] is not None):
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


def _gate_report(rep: RecordingReport, label: str, min_coverage: Optional[float]) -> bool:
    """Decisione condivisa della guardia backtest per UN report: True = tenere.

    Non-COMPLETE → sempre WARNING visibile; con ``min_coverage`` la copertura
    NOTA sotto soglia esclude (copertura ignota → incluso per prudenza).
    """
    if rep.verdict == VERDICT_COMPLETE:
        return True
    cov = "?" if rep.coverage_pct is None else f"{rep.coverage_pct:.0f}%"
    detail = "; ".join(rep.reasons) or "n/d"
    if min_coverage is None:
        logger.warning(
            "[recordings] %s: registrazione %s (copertura %s) — %s "
            "(incluso: nessun min_coverage richiesto)", label, rep.verdict, cov, detail,
        )
        return True
    if rep.coverage_pct is None:
        logger.warning(
            "[recordings] %s: copertura NON determinabile (%s) — %s "
            "(incluso per prudenza)", label, rep.verdict, detail,
        )
        return True
    if rep.coverage_pct >= float(min_coverage):
        logger.warning(
            "[recordings] %s: registrazione %s (copertura %s >= %.0f%% richiesto) — %s",
            label, rep.verdict, cov, float(min_coverage), detail,
        )
        return True
    logger.warning(
        "[recordings] %s ESCLUSO dal backtest: registrazione %s "
        "(copertura %s < %.0f%%) — %s", label, rep.verdict, cov, float(min_coverage), detail,
    )
    return False


def _raise_if_all_filtered(requested: Sequence[Any], kept: Sequence[Any],
                           min_coverage: Optional[float]) -> None:
    if min_coverage is not None and requested and not kept:
        raise ValueError(
            f"nessun evento con copertura >= {float(min_coverage):.0f}% "
            "(registrazioni parziali: vedi python -m Betfair.stream.tools.validate_recordings)"
        )


def check_events_with_reports(
    event_ids: Sequence[str],
    data_dir: str,
    min_coverage: Optional[float] = None,
) -> Tuple[List[str], Dict[str, RecordingReport]]:
    """Come :func:`check_events_for_backtest` ma ritorna ANCHE i report per
    evento (fix 17/07 "warning coverage invisibile": i backtest li scrivono nei
    risultati letti dal frontend — ``coverage_pct``/``coverage_verdict``)."""
    kept: List[str] = []
    reports: Dict[str, RecordingReport] = {}
    for ev in event_ids:
        ev = str(ev)
        try:
            rep = validate_event(data_dir, ev)
        except Exception as exc:  # noqa: BLE001 - la guardia non rompe il backtest
            logger.warning("[recordings] validazione %s KO (incluso comunque): %s", ev, exc)
            kept.append(ev)
            continue
        reports[ev] = rep
        if _gate_report(rep, f"evento {ev}", min_coverage):
            kept.append(ev)
    _raise_if_all_filtered(event_ids, kept, min_coverage)
    return kept, reports


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
    kept, _reports = check_events_with_reports(event_ids, data_dir, min_coverage)
    return kept


def complete_event_ids(
    data_dir: str, *, min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT
) -> List[str]:
    """Event id con registrazione COMPLETE in ``data_dir`` (filtro a RUNTIME del
    validatore — fix 17/07: sostituisce le liste COMPLETE hardcoded nei lab)."""
    return [
        rep.event_id
        for rep in validate_all(data_dir, min_coverage_pct=min_coverage_pct)
        if rep.verdict == VERDICT_COMPLETE
    ]


def validate_raw_file(
    raw_path: str, *, min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT
) -> RecordingReport:
    """Valida UN file ``.raw.jsonl`` per PATH esplicito (layout dei lab tennis:
    ``<dir>/<event>/<event>.raw.jsonl`` oppure file flat). Stessa pipeline di
    :func:`validate_event`, senza sidecar scores/recmeta."""
    name = os.path.basename(raw_path)
    event_id = name[:-len(".raw.jsonl")] if name.endswith(".raw.jsonl") else name
    if not os.path.isfile(raw_path):
        return RecordingReport(
            event_id=event_id, raw_path=raw_path, verdict=VERDICT_NO_RAW,
            coverage_pct=0.0, reasons=["file raw mancante"],
        )
    scan = scan_raw(raw_path)
    base = raw_path[:-len(".raw.jsonl")] if raw_path.endswith(".raw.jsonl") else raw_path
    sport = sport_di(scan)
    durata = durata_sidecar_min(
        next((c for c in (f"{base}.{suf}" for suf in SIDECAR_PUNTEGGI)
              if os.path.isfile(c)), None))
    verdict, coverage, reasons, gaps_in_window, finestra = classify(
        scan, min_coverage_pct=min_coverage_pct,
        sessions=_load_recmeta(base + ".recmeta.jsonl"),
        sport=sport, durata_partita_min=durata,
    )
    kickoff = scan.kickoff_ms if scan.kickoff_ms is not None else scan.first_inplay_pt
    report = RecordingReport(
        sport=sport, finestra=finestra, durata_sidecar_min=durata,
        event_id=event_id, raw_path=raw_path, verdict=verdict,
        coverage_pct=coverage, reasons=reasons, n_lines=scan.n_lines,
        size_bytes=os.path.getsize(raw_path), first_pt=scan.first_pt,
        last_pt=scan.last_pt, kickoff_ms=kickoff, closed_seen=scan.closed_seen,
        gaps_in_window=gaps_in_window,
        gap_in_window_min=round(sum((b - a) for a, b in gaps_in_window) / 60_000.0, 1),
    )
    if kickoff is not None and scan.first_pt is not None:
        report.start_delay_min = round((scan.first_pt - kickoff) / 60_000.0, 1)
    if kickoff is not None and scan.last_pt is not None:
        report.end_offset_min = round((scan.last_pt - kickoff) / 60_000.0, 1)
    return report


def check_raw_paths_for_backtest(
    raw_paths: Sequence[str],
    min_coverage: Optional[float] = None,
) -> List[str]:
    """Guardia per i lab che lavorano su PATH raw espliciti (tennis tune/grid/
    flb/validate — fix 17/07 "tuning senza guardia"). Semantica identica a
    :func:`check_events_for_backtest`: default = solo WARNING visibile;
    ``min_coverage`` esclude sotto soglia (ValueError se non resta nulla)."""
    kept: List[str] = []
    for path in raw_paths:
        path = str(path)
        try:
            rep = validate_raw_file(path)
        except Exception as exc:  # noqa: BLE001 - la guardia non rompe il backtest
            logger.warning("[recordings] validazione %s KO (incluso comunque): %s", path, exc)
            kept.append(path)
            continue
        if _gate_report(rep, f"raw {rep.event_id}", min_coverage):
            kept.append(path)
    _raise_if_all_filtered(raw_paths, kept, min_coverage)
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
            f"scores={r.scores_name if r.has_scores else 'NO'}"
        )
        # LA FINESTRA SI DICHIARA: due registrazioni con la stessa percentuale
        # ma finestre diverse non dicono la stessa cosa.
        if r.finestra:
            print(f"{'':>14}finestra: {r.finestra}"
                  + (f" | partita dal sidecar: {r.durata_sidecar_min:.0f}m"
                     if r.durata_sidecar_min is not None else ""))
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
