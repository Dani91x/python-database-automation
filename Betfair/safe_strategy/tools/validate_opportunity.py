"""validate_opportunity.py — AFFIDABILITA' del modello opportunita' sulle
registrazioni reali (`_live_raw/<evento>/`).

Domanda a cui risponde: "quando il modello dice 95%, quante volte succede
davvero?". Senza questa risposta un edge e' solo un numero.

Come funziona (nessuna chiamata di rete, nessun DB):
  1. `<evento>.raw.jsonl` (stream Betfair nativo) → quote 1X2 PRE-KO congelate
     all'ultimo messaggio con ``inPlay: false``: e' la stessa fonte di λ che usa
     lo scanner in diretta (``omega_model.lambdas_from_pre_ko``). La lettura si
     ferma al kickoff: nessun replay dei 10 MB di prezzi in-play.
  2. `<evento>.scores.jsonl` (STESSO formato di
     ``Betfair.stream.backtest.run_backtest._load_scores``: ts_ms/minute/
     score_home/score_away) → traiettoria (minuto, punteggio) e RISULTATO FINALE.
  3. per ogni campione si calcola il book del modello (``OpportunityModel.book``)
     e lo si confronta con l'esito REALE del mercato a fine partita.
  4. tabella di affidabilita' per mercato × fascia di minuti: n, probabilita'
     media dichiarata, frequenza realizzata, errore (media dichiarata − realizzata)
     e Brier score.

LIMITI (dichiarati, non nascosti):
  · e' una verifica di CALIBRAZIONE del modello, non un backtest di P&L: qui non
    si simulano ordini, code o commissioni;
  · un evento solo non dice nulla (n piccolo, esiti correlati dentro la stessa
    partita): serve una popolazione di registrazioni;
  · i prezzi in-play non vengono confrontati (il replay si ferma al kickoff):
    l'edge di mercato va misurato a parte.

CACHE + CALIBRAZIONE (seconda fase, 10/09/2026):
  · ``build_event_cache``: legge UNA volta, riga per riga (mai in memoria), lo
    stream mercati `<evento>.jsonl` + `<evento>.raw.jsonl` (definizioni dei
    mercati, esiti WINNER/LOSER) + punteggi, e salva un JSON.gz compatto in
    ``data/cache/`` con un'istantanea del book ogni ``step_s`` secondi di
    tempo-evento (piu' il book ``delay_s`` secondi dopo, per il bet delay);
  · ``snapshot_payload``: ricostruisce da un'istantanea il payload NELLA STESSA
    FORMA del feed unico (stessi builder di ``scanner.py``, stessi gate);
  · ``calibration_samples`` + ``--fit``: campioni (p grezza, esito reale per
    famiglia) e fit delle tabelle → ``data/opp_calibration.json``.

Uso:
  python -m Betfair.safe_strategy.tools.validate_opportunity --event 35674515
  python -m Betfair.safe_strategy.tools.validate_opportunity --all --bucket 15
  python -m Betfair.safe_strategy.tools.validate_opportunity --build-cache --fit
"""
from __future__ import annotations

import argparse
import copy
import gzip
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from Betfair.safe_strategy import scanner as S
from Betfair.safe_strategy.calibration import (
    DEFAULT_CALIBRATION_PATH, CalSample, Calibrator, fit_calibration,
    format_reliability, reliability_table,
)
from Betfair.safe_strategy.opportunity import DEFAULT_OPP_PARAMS, OpportunityModel

DEFAULT_DATA_DIR = "_live_raw"
DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache",
)
# λ generici usati dal bot quando NON c'e' nessuna fonte pre-match
# (bot_service.DEFAULT_LAMBDAS): la confidenza viene penalizzata dal modello
DEFAULT_LAMBDAS: Tuple[float, float] = (1.35, 1.15)


# ---------------------------------------------------------------------------
# Caricamento registrazioni
# ---------------------------------------------------------------------------
def load_scores(data_dir: str, event_id: str) -> List[Tuple[int, Optional[int], int, int]]:
    """`<evento>.scores.jsonl` → [(ts_ms, minute, score_home, score_away)].

    Formato IDENTICO a ``run_backtest._load_scores`` (che non importiamo per non
    tirarci dentro flumine in uno strumento di sola analisi)."""
    path = os.path.join(data_dir, str(event_id), f"{event_id}.scores.jsonl")
    out: List[Tuple[int, Optional[int], int, int]] = []
    if not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            ts = rec.get("ts_ms")
            if ts is None:
                continue
            out.append((int(ts), rec.get("minute"),
                        int(rec.get("score_home") or 0), int(rec.get("score_away") or 0)))
    return out


def _best_back(ladder: Dict[float, float]) -> Optional[float]:
    live = [p for p, s in ladder.items() if s and s > 0]
    return max(live) if live else None


def prematch_1x2(data_dir: str, event_id: str, max_lines: int = 400_000) -> Optional[Dict[str, float]]:
    """Quote 1X2 (best back) all'ultimo messaggio PRE-KICKOFF del MATCH_ODDS.

    Ricostruisce la ladder ``atb`` dai delta dello stream nativo (size 0 = livello
    rimosso) e si ferma appena ``inPlay`` diventa vero: e' esattamente il
    riferimento che lo scanner congela in diretta (``scanner.freeze_pre_ko``).
    """
    path = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    if not os.path.isfile(path):
        return None
    market_id: Optional[str] = None
    sort_by_runner: Dict[int, int] = {}
    ladders: Dict[int, Dict[float, float]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if n >= max_lines:
                break
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            for mc in rec.get("mc") or []:
                md = mc.get("marketDefinition")
                if md is not None:
                    if str(md.get("marketType") or "") == "MATCH_ODDS":
                        market_id = mc.get("id")
                        # i sort restano quelli gia' visti se la definizione
                        # aggiornata non li ripete (succede sui delta di stato)
                        sorts = {
                            int(r["id"]): int(r.get("sortPriority") or 0)
                            for r in (md.get("runners") or []) if r.get("id") is not None
                        }
                        if sorts:
                            sort_by_runner = sorts
                    if mc.get("id") == market_id and md.get("inPlay"):
                        return _triple(ladders, sort_by_runner)   # kickoff: congelato
                if market_id is None or mc.get("id") != market_id:
                    continue
                for rc in mc.get("rc") or []:
                    rid = rc.get("id")
                    if rid is None:
                        continue
                    lad = ladders.setdefault(int(rid), {})
                    for price, size in (rc.get("atb") or []):
                        lad[float(price)] = float(size)
    return _triple(ladders, sort_by_runner)


def _triple(ladders: Dict[int, Dict[float, float]],
            sort_by_runner: Dict[int, int]) -> Optional[Dict[str, float]]:
    """Regola Betfair: sortPriority 1 = casa, 2 = trasferta, 3 = pareggio."""
    by_sort = {sp: rid for rid, sp in sort_by_runner.items()}
    out: Dict[str, float] = {}
    for side, sp in (("home", 1), ("away", 2), ("draw", 3)):
        rid = by_sort.get(sp)
        price = _best_back(ladders.get(rid, {})) if rid is not None else None
        if price is None or price <= 1.0:
            return None
        out[side] = price
    return out


# ---------------------------------------------------------------------------
# Esiti reali
# ---------------------------------------------------------------------------
def market_keys(params: Optional[dict] = None) -> List[str]:
    """Mercati verificabili dal solo punteggio finale."""
    p = params or DEFAULT_OPP_PARAMS
    keys = ["home", "draw", "away", "btts_yes"]
    keys += [f"over_{str(float(ln)).replace('.', '_')}" for ln in p["ou_lines"]]
    return keys


def realised(key: str, final_home: int, final_away: int) -> Optional[int]:
    """Esito REALE (1/0) del mercato dato il risultato finale. None = non valutabile."""
    if key == "home":
        return int(final_home > final_away)
    if key == "draw":
        return int(final_home == final_away)
    if key == "away":
        return int(final_home < final_away)
    if key == "btts_yes":
        return int(final_home >= 1 and final_away >= 1)
    if key.startswith("over_"):
        line = float(key[len("over_"):].replace("_", "."))
        return int(final_home + final_away > line)
    return None


@dataclass(frozen=True)
class Sample:
    event_id: str
    minute: int
    market: str
    p_model: float
    outcome: int


# ---------------------------------------------------------------------------
# Replay di un evento
# ---------------------------------------------------------------------------
def replay_event(
    data_dir: str,
    event_id: str,
    *,
    model: Optional[OpportunityModel] = None,
    lambdas: Optional[Tuple[float, float]] = None,
    league_id: Optional[int] = None,
    scores: Optional[Sequence[Tuple[int, Optional[int], int, int]]] = None,
    pre_ko: Optional[Dict[str, float]] = None,
    step_min: int = 1,
) -> List[Sample]:
    """Campioni (p_modello, esito reale) di UN evento registrato.

    Un campione per minuto di gioco (``step_min``), per ogni mercato verificabile
    dal punteggio finale. [] se mancano punteggi o λ (mai stime a caso).
    """
    model = model or OpportunityModel(calibration="off")
    rows = list(scores if scores is not None else load_scores(data_dir, event_id))
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return []
    if lambdas is None:
        pre = pre_ko if pre_ko is not None else prematch_1x2(data_dir, event_id)
        from Betfair.omega.omega_model import lambdas_from_pre_ko
        lam = lambdas_from_pre_ko(pre)
        if lam is None:
            return []
        lambdas = (float(lam[0]), float(lam[1]))
    final_home, final_away = rows[-1][2], rows[-1][3]
    keys = market_keys(model.params)

    out: List[Sample] = []
    seen: set = set()
    for _ts, minute, sh, sa in rows:
        # il recupero finisce nella fascia dell'ultimo quarto d'ora: le fasce
        # restano 0-90, mai un '90-105' con un campione solo
        m = max(0, min(89, int(minute)))
        if (m % max(1, int(step_min))) != 0 or m in seen:
            continue
        seen.add(m)
        payload = {"minute": m, "score_home": sh, "score_away": sa,
                   "red_home": 0, "red_away": 0}
        book = model.book(payload, lambdas=lambdas, league_id=league_id)
        for key in keys:
            p = book.get(key)
            real = realised(key, final_home, final_away)
            if p is None or real is None:
                continue
            out.append(Sample(str(event_id), m, key, float(p), int(real)))
    return out


# ---------------------------------------------------------------------------
# Tabella di affidabilita'
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReliabilityRow:
    market: str
    bucket: str
    n: int
    p_mean: float
    realised_rate: float
    error: float          # p_mean - realised_rate (>0 = il modello e' ottimista)
    brier: float


def reliability(samples: Iterable[Sample], bucket_min: int = 15) -> List[ReliabilityRow]:
    """Aggrega i campioni per mercato × fascia di minuti."""
    b = max(1, int(bucket_min))
    acc: Dict[Tuple[str, int], List[float]] = {}
    for s in samples:
        lo = (s.minute // b) * b
        key = (s.market, lo)
        node = acc.setdefault(key, [0.0, 0.0, 0.0, 0.0])
        node[0] += 1
        node[1] += s.p_model
        node[2] += s.outcome
        node[3] += (s.p_model - s.outcome) ** 2
    rows: List[ReliabilityRow] = []
    for (market, lo), (n, sp, so, sb) in sorted(acc.items()):
        rows.append(ReliabilityRow(
            market=market, bucket=f"{lo}-{lo + b}", n=int(n),
            p_mean=sp / n, realised_rate=so / n,
            error=sp / n - so / n, brier=sb / n,
        ))
    return rows


def format_table(rows: Sequence[ReliabilityRow]) -> str:
    """Tabella ASCII (console Windows cp1252: mai caratteri non ASCII)."""
    head = f"{'mercato':<12}{'fascia':>9}{'n':>7}{'p_media':>10}{'reale':>9}{'errore':>9}{'brier':>9}"
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(
            f"{r.market:<12}{r.bucket:>9}{r.n:>7}{r.p_mean:>10.3f}"
            f"{r.realised_rate:>9.3f}{r.error:>+9.3f}{r.brier:>9.4f}"
        )
    return "\n".join(out)


def available_events(data_dir: str) -> List[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        d for d in os.listdir(data_dir)
        if os.path.isfile(os.path.join(data_dir, d, f"{d}.scores.jsonl"))
    )


# ---------------------------------------------------------------------------
# CACHE compatta per evento (stream mercati campionato ogni step_s secondi)
# ---------------------------------------------------------------------------
CACHE_VERSION = 1
# mercati che il motore opportunita' sa prezzare (gli altri non entrano in cache)
_OU_RE = re.compile(r"^OVER_UNDER_\d\d$")
_KEEP_TYPES = ("MATCH_ODDS", "HALF_TIME", "BOTH_TEAMS_TO_SCORE", "CORRECT_SCORE", "HALF_TIME_SCORE")

# selection_id Betfair (VERIFICATI sugli esiti WINNER delle registrazioni):
# CORRECT_SCORE e HALF_TIME_SCORE condividono gli id delle celle
_SCORE_IDS: Dict[int, Tuple[int, int]] = {
    1: (0, 0), 2: (1, 0), 3: (1, 1), 4: (0, 1), 5: (2, 0), 6: (2, 1), 7: (2, 2), 8: (1, 2),
    9: (0, 2), 10: (3, 0), 11: (3, 1), 12: (3, 2), 13: (3, 3), 14: (2, 3), 15: (1, 3), 16: (0, 3),
}
_AGG_IDS: Dict[int, str] = {
    9063254: "Any Other Home Win", 9063255: "Any Other Away Win",
    9063256: "Any Other Draw", 4506345: "Any Unquoted",
}
_BTTS_IDS = {30246: "Yes", 30247: "No"}


def selection_name(market_type: str, sid: int, sort: int, home: str, away: str) -> str:
    """Nome Betfair del runner (lo stream nativo NON porta i nomi): dalla
    regola sortPriority/id verificata sulle registrazioni."""
    mt = str(market_type or "")
    if mt in ("MATCH_ODDS", "HALF_TIME"):
        return {1: home or "Home", 2: away or "Away", 3: "The Draw"}.get(sort, f"#{sid}")
    if _OU_RE.match(mt):
        line = S.ou_line_from_market_type(mt)
        return f"{'Under' if sort == 1 else 'Over'} {line} Goals"
    if mt == "BOTH_TEAMS_TO_SCORE":
        return _BTTS_IDS.get(sid, "Yes" if sort == 1 else "No")
    if mt in ("CORRECT_SCORE", "HALF_TIME_SCORE"):
        if sid in _SCORE_IDS:
            h, a = _SCORE_IDS[sid]
            return f"{h} - {a}"
        if sid in _AGG_IDS:
            return _AGG_IDS[sid]
        if mt == "CORRECT_SCORE":
            return {17: "Any Other Home Win", 18: "Any Other Away Win",
                    19: "Any Other Draw"}.get(sort, f"#{sid}")
        return "Any Unquoted"
    return f"#{sid}"


def prob_key_for(market_type: str, sid: int, sort: int) -> Optional[str]:
    """Runner → chiave del book del modello (stessa convenzione di
    ``OpportunityModel.book``). None = runner non prezzabile."""
    mt = str(market_type or "")
    if mt == "MATCH_ODDS":
        return {1: "home", 2: "away", 3: "draw"}.get(sort)
    if mt == "HALF_TIME":
        return {1: "ht_home", 2: "ht_away", 3: "ht_draw"}.get(sort)
    if _OU_RE.match(mt):
        line = S.ou_line_from_market_type(mt)
        k = str(float(line)).replace(".", "_")
        return f"{'under' if sort == 1 else 'over'}_{k}"
    if mt == "BOTH_TEAMS_TO_SCORE":
        return "btts_yes" if sid == 30246 or sort == 1 else "btts_no"
    if mt in ("CORRECT_SCORE", "HALF_TIME_SCORE"):
        prefix = "cs_" if mt == "CORRECT_SCORE" else "hts_"
        if sid in _SCORE_IDS:
            h, a = _SCORE_IDS[sid]
            return f"{prefix}{h}_{a}"
        agg = {9063254: "any_other_home", 9063255: "any_other_away",
               9063256: "any_other_draw", 4506345: "any_unquoted"}.get(sid)
        if agg is None:
            agg = {17: "any_other_home", 18: "any_other_away",
                   19: "any_other_draw"}.get(sort, "any_unquoted")
        return prefix + agg
    return None


def load_market_defs(data_dir: str, event_id: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[int]]]:
    """`<evento>.raw.jsonl` (riga per riga, solo le righe con una definizione) →
    ({market_id: {type, runners:{sid: sort}}}, {market_id: [sid WINNER]}).

    Gli esiti WINNER/LOSER dell'ultima definizione (mercato SETTLED/CLOSED)
    sono il RISULTATO VERO di ogni mercato: e' su quelli che si regola."""
    path = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    defs: Dict[str, Dict[str, Any]] = {}
    winners: Dict[str, List[int]] = {}
    if not os.path.isfile(path):
        return defs, winners
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if '"marketDefinition"' not in line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            for mc in rec.get("mc") or []:
                md = mc.get("marketDefinition")
                mid = mc.get("id")
                if not isinstance(md, dict) or not mid:
                    continue
                mt = str(md.get("marketType") or "")
                node = defs.setdefault(mid, {"type": mt, "runners": {}})
                if mt:
                    node["type"] = mt
                won: List[int] = []
                for r in md.get("runners") or []:
                    if r.get("id") is None:
                        continue
                    sid = int(r["id"])
                    sp = r.get("sortPriority")
                    if sp is not None:
                        node["runners"][sid] = int(sp)
                    if r.get("status") == "WINNER":
                        won.append(sid)
                if won:
                    winners[mid] = won
    return defs, winners


def load_score_rows(data_dir: str, event_id: str) -> List[Dict[str, Any]]:
    """`<evento>.scores.jsonl` → righe {ts_ms, minute, sh, sa, rh, ra, home, away}
    (come ``load_scores`` ma con cartellini rossi e nomi squadra dal payload IPS)."""
    path = os.path.join(data_dir, str(event_id), f"{event_id}.scores.jsonl")
    out: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            ts = rec.get("ts_ms")
            if ts is None:
                continue
            sc = ((rec.get("payload") or {}).get("score") or {})
            h, a = sc.get("home") or {}, sc.get("away") or {}
            out.append({
                "ts_ms": int(ts), "minute": rec.get("minute"),
                "sh": int(rec.get("score_home") or 0), "sa": int(rec.get("score_away") or 0),
                "rh": int(h.get("numberOfRedCards") or 0), "ra": int(a.get("numberOfRedCards") or 0),
                "home": h.get("name"), "away": a.get("name"),
            })
    return out


def cache_path(cache_dir: str, event_id: str) -> str:
    return os.path.join(cache_dir, f"{event_id}.cache.json.gz")


def _ladder(levels: Any) -> List[List[float]]:
    out: List[List[float]] = []
    for lv in (levels or [])[:3]:
        try:
            out.append([float(lv[0]), float(lv[1])])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def build_event_cache(
    data_dir: str, event_id: str, cache_dir: str = DEFAULT_CACHE_DIR, *,
    step_s: float = 10.0, delay_s: float = 5.0, force: bool = False,
) -> Optional[str]:
    """Stream `<evento>.jsonl` riga per riga → cache JSON.gz. None se mancano
    stream o punteggi. La cache esistente viene riusata (``force`` la rifa')."""
    out_path = cache_path(cache_dir, event_id)
    if os.path.isfile(out_path) and not force:
        return out_path
    stream = os.path.join(data_dir, str(event_id), f"{event_id}.jsonl")
    rows = load_score_rows(data_dir, event_id)
    if not os.path.isfile(stream) or not rows:
        return None
    defs, winners = load_market_defs(data_dir, event_id)
    keep = {mid: d for mid, d in defs.items()
            if d["type"] in _KEEP_TYPES or _OU_RE.match(d["type"])}
    home = next((r["home"] for r in rows if r.get("home")), None) or "Home"
    away = next((r["away"] for r in rows if r.get("away")), None) or "Away"
    goals: List[Dict[str, Any]] = []
    prev = (0, 0)
    for r in rows:
        cur = (r["sh"], r["sa"])
        if cur != prev and r.get("minute") is not None:
            goals.append({"minute": int(r["minute"]), "ts_ms": r["ts_ms"],
                          "team": "home" if cur[0] > prev[0] else "away"})
        prev = cur
    ht_row = None
    for r in rows:
        if r.get("minute") is not None and int(r["minute"]) <= 45:
            ht_row = r
    last = rows[-1]

    step_ms, delay_ms = int(step_s * 1000), int(delay_s * 1000)
    state: Dict[str, Dict[str, Any]] = {}
    snapshots: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    next_ts: Optional[int] = None
    si = 0                      # indice sui punteggi

    def book_copy() -> Dict[str, Any]:
        return {mid: [st["status"], st["pt"], {sid: [copy.copy(v[0]), copy.copy(v[1])]
                                                for sid, v in st["runners"].items()}]
                for mid, st in state.items()}

    def flush_delayed(pt: int) -> None:
        while pending and pt > pending[0]["ts"] + delay_ms:
            snap = pending.pop(0)
            snap["delayed"] = book_copy()
            snapshots.append(snap)

    with open(stream, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            mid = rec.get("market_id")
            pt = rec.get("pt")
            if mid not in keep or not isinstance(pt, (int, float)):
                continue
            pt = int(pt)
            flush_delayed(pt)
            if next_ts is None and rec.get("inplay"):
                next_ts = pt                                  # kickoff: prima istantanea
            # istantanee a cavallo di questo aggiornamento (stato PRIMA di applicarlo)
            while next_ts is not None and pt >= next_ts:
                while si + 1 < len(rows) and rows[si + 1]["ts_ms"] <= next_ts:
                    si += 1
                srow = rows[si] if rows[si]["ts_ms"] <= next_ts else None
                if srow is not None and srow.get("minute") is not None and state:
                    pending.append({
                        "ts": next_ts, "minute": int(srow["minute"]),
                        "sh": srow["sh"], "sa": srow["sa"], "rh": srow["rh"], "ra": srow["ra"],
                        "books": book_copy(),
                    })
                next_ts += step_ms
            st = state.setdefault(mid, {"status": None, "pt": pt, "runners": {}})
            st["status"] = rec.get("status")
            st["pt"] = pt
            for sid, r in (rec.get("runners") or {}).items():
                st["runners"][str(sid)] = [_ladder(r.get("b")), _ladder(r.get("l"))]
            if keep[mid]["type"] == "MATCH_ODDS" and rec.get("status") == "CLOSED":
                break
    for snap in pending:                                       # coda: book finale
        snap["delayed"] = book_copy()
        snapshots.append(snap)

    markets = {
        mid: {"type": d["type"], "line": S.ou_line_from_market_type(d["type"]),
              "runners": [[sid, sp, selection_name(d["type"], sid, sp, home, away),
                           prob_key_for(d["type"], sid, sp)]
                          for sid, sp in sorted(d["runners"].items(), key=lambda kv: kv[1])]}
        for mid, d in keep.items()
    }
    cache = {
        "version": CACHE_VERSION, "event_id": str(event_id), "home": home, "away": away,
        "pre_ko": prematch_1x2(data_dir, event_id),
        "final": [last["sh"], last["sa"]], "final_minute": last.get("minute"),
        "ht": [ht_row["sh"], ht_row["sa"]] if ht_row else None,
        "goals": goals, "markets": markets,
        "winners": {mid: w for mid, w in winners.items() if mid in keep},
        "step_s": step_s, "delay_s": delay_s, "snapshots": snapshots,
    }
    os.makedirs(cache_dir, exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8") as fh:
        json.dump(cache, fh, separators=(",", ":"))
    return out_path


def load_event_cache(path: str) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def cached_events(cache_dir: str = DEFAULT_CACHE_DIR) -> List[str]:
    if not os.path.isdir(cache_dir):
        return []
    return sorted(os.path.join(cache_dir, f) for f in os.listdir(cache_dir)
                  if f.endswith(".cache.json.gz"))


def event_lambdas(cache: Dict[str, Any]) -> Tuple[Tuple[float, float], str]:
    """(λ, fonte): 'pre_ko' dalle quote 1X2 congelate, altrimenti 'default'
    (λ generici del bot, confidenza penalizzata dal modello)."""
    from Betfair.omega.omega_model import lambdas_from_pre_ko
    lam = lambdas_from_pre_ko(cache.get("pre_ko"))
    if lam is not None:
        return (float(lam[0]), float(lam[1])), "pre_ko"
    return DEFAULT_LAMBDAS, "default"


# ---------------------------------------------------------------------------
# Payload nella FORMA del feed unico (stessi builder e gate dello scanner)
# ---------------------------------------------------------------------------
def _best(levels: List[List[float]]) -> Tuple[Optional[float], Optional[float]]:
    if not levels:
        return None, None
    return float(levels[0][0]), float(levels[0][1])


def _selections(runners: List[list], book: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for sid, _sp, name, _pk in runners:
        lad = book.get(str(sid)) or [[], []]
        b, bs = _best(lad[0])
        l, ls = _best(lad[1])
        out.append({"selection_id": int(sid), "name": name, "runner_status": "ACTIVE",
                    "back": b, "lay": l, "back_size": bs, "lay_size": ls})
    return out


def snapshot_payload(cache: Dict[str, Any], snap: Dict[str, Any]) -> Dict[str, Any]:
    """Istantanea della cache → payload calcio come lo pubblica lo scanner
    (blocchi ``odds``/``ou``/``btts``/``ht_result``/``cs``/``ht``), con gli
    STESSI gate di rilevanza (linea indecisa, 1T in corso, ...)."""
    m, sh, sa = int(snap["minute"]), int(snap["sh"]), int(snap["sa"])
    payload: Dict[str, Any] = {
        "event_id": cache.get("event_id"), "event_name": f"{cache.get('home')} v {cache.get('away')}",
        "home": cache.get("home"), "away": cache.get("away"),
        "inplay": True, "minute": m, "score_home": sh, "score_away": sa,
        "red_home": int(snap.get("rh") or 0), "red_away": int(snap.get("ra") or 0),
        "pre_ko": cache.get("pre_ko"),
        "timeline": [{"update_id": i, "type": "Goal", "minute": g["minute"], "ts_ms": g["ts_ms"]}
                     for i, g in enumerate(cache.get("goals") or []) if g["ts_ms"] <= snap["ts"]],
        "ou": [], "btts": None, "ht_result": None, "cs": None, "ht": None,
    }
    markets = cache.get("markets") or {}
    for mid, (status, pt, book) in (snap.get("books") or {}).items():
        md = markets.get(mid)
        if not md:
            continue
        mt = md["type"]
        sels = _selections(md["runners"], book)
        if mt == "MATCH_ODDS":
            by_sort = {sp: s for (sid, sp, _n, _pk), s in zip(md["runners"], sels)}
            odds = {}
            for side, sp in (("home", 1), ("away", 2), ("draw", 3)):
                s = by_sort.get(sp)
                if s:
                    odds[side] = {k: s[k] for k in ("back", "lay", "back_size", "lay_size", "selection_id")}
            payload.update(odds=odds or None, mo_market_id=mid, mo_status=status, odds_ts_ms=pt)
        elif _OU_RE.match(mt):
            line = md.get("line")
            if S.is_live_ou_line(line, sh, sa):
                payload["ou"].append(S.build_market_block(
                    mid, status, sels, True, None, market_type=mt, line=line, ts_ms=pt))
        elif mt == "BOTH_TEAMS_TO_SCORE":
            if S.is_live_btts(sh, sa):
                payload["btts"] = S.build_market_block(mid, status, sels, True, None,
                                                       market_type=mt, ts_ms=pt)
        elif mt == "HALF_TIME":
            if S.is_ht_result_candidate(m):
                payload["ht_result"] = S.build_market_block(mid, status, sels, True, None,
                                                            market_type=mt, ts_ms=pt)
        elif mt == "CORRECT_SCORE":
            blk = S.build_cs_block(mid, status, sels, True, None)
            if blk is not None:
                blk["ts_ms"] = pt
            payload["cs"] = blk
        elif mt == "HALF_TIME_SCORE":
            if S.is_ht_candidate(m):
                payload["ht"] = S.build_market_block(mid, status, sels, True, None,
                                                     market_type=mt, ts_ms=pt)
    payload["ou"].sort(key=lambda b: b.get("line") or 0.0)
    if not payload["ou"]:
        payload["ou"] = None
    return payload


def market_outcome(cache: Dict[str, Any], market_id: str, selection_id: int) -> Optional[int]:
    """1 se la selezione ha VINTO il mercato (esito WINNER dello stream),
    0 se il mercato e' regolato e ha vinto un'altra, None se non regolato."""
    won = (cache.get("winners") or {}).get(market_id)
    if not won:
        return None
    return int(int(selection_id) in {int(x) for x in won})


# ---------------------------------------------------------------------------
# Campioni di calibrazione (per famiglia, esito dal mercato regolato)
# ---------------------------------------------------------------------------
def calibration_samples(
    cache: Dict[str, Any], *, model: Optional[OpportunityModel] = None,
    lambdas: Optional[Tuple[float, float]] = None, league_id: Optional[int] = None,
    step_min: int = 1,
) -> List[CalSample]:
    """Un campione per minuto (prima istantanea del minuto) per ogni runner
    prezzabile di ogni mercato REGOLATO: (famiglia, minuto, p grezza, esito).
    Le certezze (p<=0 o p>=1: esito gia' deciso) non si campionano."""
    from Betfair.safe_strategy.calibration import family_of_market

    model = model or OpportunityModel(calibration="off")
    if lambdas is None:
        lambdas, _src = event_lambdas(cache)
    markets = cache.get("markets") or {}
    eid = str(cache.get("event_id") or "")
    out: List[CalSample] = []
    seen: set = set()
    for snap in cache.get("snapshots") or []:
        m = int(snap["minute"])
        if m in seen or (m % max(1, int(step_min))) != 0:
            continue
        seen.add(m)
        payload = {"minute": m, "score_home": snap["sh"], "score_away": snap["sa"],
                   "red_home": snap.get("rh") or 0, "red_away": snap.get("ra") or 0}
        book = model.book(payload, lambdas=lambdas, league_id=league_id)
        for mid in (snap.get("books") or {}):
            md = markets.get(mid)
            if not md or mid not in (cache.get("winners") or {}):
                continue
            mt = md["type"]
            if mt in ("HALF_TIME", "HALF_TIME_SCORE") and m >= 45:
                continue
            for sid, _sp, _name, pk in md["runners"]:
                if not pk or pk not in book:
                    continue
                p = float(book[pk])
                if p <= 0.0 or p >= 1.0:
                    continue
                real = market_outcome(cache, mid, sid)
                fam = family_of_market(mt, pk)
                if real is None or fam is None:
                    continue
                out.append(CalSample(fam, m, p, real, eid))
    return out


def fit_from_cache(
    paths: Sequence[str], *, min_n: int = 50, shrink_n: float = 50.0,
    only_pre_ko: bool = False, log: bool = True,
) -> Tuple[Dict[str, Any], List[CalSample]]:
    """Campioni da tutte le cache → dict di calibrazione (``fit_calibration``)."""
    model = OpportunityModel(calibration="off")
    samples: List[CalSample] = []
    n_events = 0
    for path in paths:
        cache = load_event_cache(path)
        lambdas, src = event_lambdas(cache)
        if only_pre_ko and src != "pre_ko":
            continue
        got = calibration_samples(cache, model=model, lambdas=lambdas)
        if got:
            n_events += 1
        if log:
            print(f"[calib] {cache.get('event_id')}: {len(got)} campioni (lambda {src})")
        samples.extend(got)
    data = fit_calibration(samples, min_n=min_n, shrink_n=shrink_n, n_events=n_events)
    return data, samples


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Affidabilita' del modello opportunita'")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    ap.add_argument("--event", action="append", default=[], help="event_id (ripetibile)")
    ap.add_argument("--all", action="store_true", help="tutti gli eventi registrati")
    ap.add_argument("--bucket", type=int, default=15, help="ampiezza fascia minuti")
    ap.add_argument("--step", type=int, default=1, help="un campione ogni N minuti")
    ap.add_argument("--lambda-home", type=float, default=None)
    ap.add_argument("--lambda-away", type=float, default=None)
    ap.add_argument("--league-id", type=int, default=None)
    ap.add_argument("--csv", default=None, help="scrive la tabella anche in CSV")
    # cache + calibrazione
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    ap.add_argument("--build-cache", action="store_true",
                    help="costruisce la cache compatta degli eventi (riusa quella esistente)")
    ap.add_argument("--force-cache", action="store_true", help="rifa' la cache anche se esiste")
    ap.add_argument("--fit", action="store_true",
                    help="fit delle tabelle di calibrazione dalla cache -> --calibration-out")
    ap.add_argument("--calibration-out", default=DEFAULT_CALIBRATION_PATH)
    ap.add_argument("--min-n", type=int, default=50)
    ap.add_argument("--shrink-n", type=float, default=50.0)
    ap.add_argument("--only-pre-ko", action="store_true",
                    help="fit solo sugli eventi con quote 1X2 pre-KO (lambda reali)")
    args = ap.parse_args(argv)

    events = list(args.event)
    if args.all or not events:
        events = available_events(args.data_dir)

    if args.build_cache or args.fit:
        if args.build_cache:
            t0 = time.time()
            done = 0
            for i, eid in enumerate(events, 1):
                path = build_event_cache(args.data_dir, eid, args.cache_dir, force=args.force_cache)
                print(f"[cache] {i}/{len(events)} {eid}: {'ok' if path else 'saltato (stream/punteggi assenti)'}"
                      f" ({time.time() - t0:.0f}s)")
                done += int(path is not None)
            print(f"[cache] {done} eventi in {args.cache_dir}")
        if args.fit:
            paths = cached_events(args.cache_dir)
            if args.event and not args.all:
                paths = [p for p in paths if os.path.basename(p).split(".")[0] in set(args.event)]
            if not paths:
                print("nessuna cache: usa --build-cache")
                return 1
            data, samples = fit_from_cache(paths, min_n=args.min_n, shrink_n=args.shrink_n,
                                           only_pre_ko=args.only_pre_ko)
            Calibrator.from_dict(data).save(args.calibration_out)
            print()
            print(format_reliability(reliability_table(samples)))
            meta = data["meta"]
            print()
            print(f"eventi {meta['n_events']} | campioni {meta['n_samples']} | "
                  f"tabelle applicate {meta['tables_applied']}/{meta['tables_total']}")
            print(f"Brier prima {meta['brier_before']:.4f} -> dopo {meta['brier_after']:.4f} (in-sample)")
            if meta.get("brier_cv_before") is not None:
                print(f"Brier CV 2-fold per evento: prima {meta['brier_cv_before']:.4f} -> "
                      f"dopo {meta['brier_cv_after']:.4f}")
            print(f"ECE prima {meta['ece_before']:.4f} -> dopo {meta['ece_after']:.4f}")
            print(f"calibrazione scritta in {args.calibration_out}")
        return 0

    if not events:
        print(f"nessuna registrazione con punteggi in {args.data_dir}")
        return 1

    lambdas = None
    if args.lambda_home and args.lambda_away:
        lambdas = (float(args.lambda_home), float(args.lambda_away))
    model = OpportunityModel(calibration="off")
    samples: List[Sample] = []
    for eid in events:
        got = replay_event(args.data_dir, eid, model=model, lambdas=lambdas,
                           league_id=args.league_id, step_min=args.step)
        print(f"[validate] {eid}: {len(got)} campioni")
        samples.extend(got)
    if not samples:
        print("nessun campione: punteggi o quote pre-KO mancanti")
        return 1
    rows = reliability(samples, args.bucket)
    print()
    print(format_table(rows))
    print()
    brier = sum(r.brier * r.n for r in rows) / sum(r.n for r in rows)
    print(f"eventi {len(events)} | campioni {len(samples)} | Brier medio {brier:.4f}")
    print("NB: calibrazione del modello, non un backtest di P&L. Un evento solo "
          "non e' una prova: servono molte registrazioni.")
    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write("mercato,fascia,n,p_media,reale,errore,brier\n")
            for r in rows:
                fh.write(f"{r.market},{r.bucket},{r.n},{r.p_mean:.6f},"
                         f"{r.realised_rate:.6f},{r.error:.6f},{r.brier:.6f}\n")
        print(f"CSV: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
