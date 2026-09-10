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

Uso:
  python -m Betfair.safe_strategy.tools.validate_opportunity --event 35674515
  python -m Betfair.safe_strategy.tools.validate_opportunity --all --bucket 15
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from Betfair.safe_strategy.opportunity import DEFAULT_OPP_PARAMS, OpportunityModel

DEFAULT_DATA_DIR = "_live_raw"


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
    model = model or OpportunityModel()
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
    args = ap.parse_args(argv)

    events = list(args.event)
    if args.all or not events:
        events = available_events(args.data_dir)
    if not events:
        print(f"nessuna registrazione con punteggi in {args.data_dir}")
        return 1

    lambdas = None
    if args.lambda_home and args.lambda_away:
        lambdas = (float(args.lambda_home), float(args.lambda_away))
    model = OpportunityModel()
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
