"""refresh_analytics_bets.py -- rinfresca analytics_bets (motore strategie) UN
GIORNO ALLA VOLTA, invece di una sola chiamata su tutta la finestra.

PERCHE'
  L'action chiamava `refresh_analytics_bets(p_days=5)`, che e' solo un wrapper di
  `refresh_analytics_bets_range((now() utc)::date - p_days, (now() utc)::date + 2)`
  (migrations/analytics_strategy.sql:268). Quella funzione, in UNA transazione,
  ricostruisce book_odds_cache (unnest di raw_json_odds bookmaker x bet x value)
  e analytics_bets per TUTTI i giorni della finestra: su 7 giorni supera i due
  minuti e il client chiude la connessione (httpx.ReadTimeout), lasciando la
  tabella ferma al giorno prima. Il timeout NON e' del server: entrambe le
  funzioni hanno `SET statement_timeout = 0`.

PERCHE' A FINESTRE DI UN GIORNO IL RISULTATO E' LO STESSO (letto dal SQL)
  1) book_odds_cache: `delete ... using fixture_predictions where fixture_date >=
     p_from and < p_to` + insert con lo stesso filtro di data. Ogni fixture_date
     cade in UNA sola finestra giornaliera, e l'unione delle finestre e' esattamente
     [from, to) -> stesse righe cancellate e riscritte.
  2) analytics_bets: l'insieme trattato e' `distinct fixture_id from
     analytics_signals where kickoff >= p_from and < p_to`; delete e insert usano
     lo STESSO insieme e l'insert AGGREGA TUTTI i segnali del fixture (non solo
     quelli nella finestra). Quindi il contenuto scritto per un fixture NON dipende
     dalla finestra: e' idempotente. L'unione degli insiemi giornalieri e' l'insieme
     della finestra intera; un fixture con segnali a cavallo di due giorni viene
     riscritto identico due volte. Stato finale IDENTICO.
  3) Unica differenza: il NUMERO RITORNATO. La funzione ritorna le righe inserite
     nell'ultima insert; qui si sommano le finestre, quindi un fixture con segnali
     in piu' giorni e' contato piu' volte. E' un numero di log, non un dato.

Uso (equivalente a `refresh_analytics_bets(p_days=5)`):
  python refresh_analytics_bets.py --days 5
  python refresh_analytics_bets.py --from 2026-09-01 --to 2026-10-01   # backfill
  python refresh_analytics_bets.py --days 5 --dry-run                  # solo le finestre
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client

_RPC = "refresh_analytics_bets_range"
_HTTP_TIMEOUT = 600.0   # secondi per finestra (il server non ha statement_timeout)
_RETRY = 3              # tentativi su errori TRANSITORI (MAI sul timeout del client)
_PAUSA = 1.0            # pausa fra finestre: il DB respira

# Errori TRANSITORI (si ritentano). Gli errori LOGICI non si ritentano.
_TRANSIENT_CODES = {"57014", "53300", "53400", "55P03", "40001", "40P01",
                    "08006", "08003", "08000", "57P01", "57P02", "57P03",
                    "PGRST002", "408", "500", "502", "503", "504"}


def _timeout_client(e: Exception) -> bool:
    """Timeout/interruzione LATO CLIENT: la richiesta e' partita e la risposta non
    e' arrivata, ma le due RPC hanno statement_timeout=0, quindi lo statement puo'
    essere ANCORA VIVO sul server. Questo NON si ritenta MAI: una seconda chiamata
    sulla stessa finestra farebbe delete+insert in concorrenza sulle stesse righe
    (lock, deadlock 40P01, violazioni di chiave)."""
    if isinstance(e, httpx.ConnectTimeout):
        return False      # la connessione non si e' aperta: lo statement non e' mai partito
    return isinstance(e, (httpx.TimeoutException, httpx.RemoteProtocolError,
                          httpx.ReadError, httpx.WriteError))


def _is_transient(e: Exception) -> bool:
    """True solo per gli errori che ha senso ritentare. ATTENZIONE: esclude i
    timeout del client (vedi _timeout_client), che NON si ritentano."""
    if _timeout_client(e):
        return False
    if isinstance(e, httpx.TransportError):   # ConnectError, ConnectTimeout gia' escluso, PoolTimeout...
        return True
    code = getattr(e, "code", None)
    if code is not None and str(code) in _TRANSIENT_CODES:
        return True
    msg = str(getattr(e, "message", "") or "").lower()
    return "timeout" in msg or "temporarily unavailable" in msg


def _sleep_backoff(attempt: int) -> None:
    """Attesa LUNGA con jitter: il DB e' fragile e la finestra appena fallita puo'
    aver lasciato lavoro in corso."""
    time.sleep(min(60.0, 10.0 * (2 ** attempt)) * (0.7 + random.random() * 0.6))


def finestre(giorno: date, days: int) -> list[tuple[date, date]]:
    """Le finestre giornaliere [d, d+1) che coprono ESATTAMENTE lo stesso
    intervallo del wrapper SQL: [giorno - days, giorno + 2)."""
    inizio, fine = giorno - timedelta(days=days), giorno + timedelta(days=2)
    out, d = [], inizio
    while d < fine:
        out.append((d, d + timedelta(days=1)))
        d += timedelta(days=1)
    return out


def finestre_da_intervallo(p_from: date, p_to: date) -> list[tuple[date, date]]:
    """Finestre giornaliere che coprono [p_from, p_to)."""
    out, d = [], p_from
    while d < p_to:
        out.append((d, d + timedelta(days=1)))
        d += timedelta(days=1)
    return out


def rinfresca_finestra(sb, p_from: date, p_to: date) -> tuple[bool, int]:
    """Chiama la RPC per UNA finestra. Ritorna (riuscita, righe_scritte).
    Sul TIMEOUT DEL CLIENT non ritenta: vedi _timeout_client."""
    for attempt in range(_RETRY):
        try:
            res = sb.rpc(_RPC, {"p_from": p_from.isoformat(),
                                "p_to": p_to.isoformat()}).execute()
            return True, (res.data if isinstance(res.data, int) else 0)
        except Exception as e:  # noqa: BLE001
            if _timeout_client(e):
                print(f"  [ERR] {p_from} -> {p_to}: {type(e).__name__} dopo "
                      f"{_HTTP_TIMEOUT:.0f}s: NON ritento. Lo statement PUO' ESSERE "
                      f"ANCORA IN ESECUZIONE sul server (le RPC hanno "
                      f"statement_timeout=0): NON rilanciare a mano subito, "
                      f"verifica prima che non stia ancora girando.")
                return False, 0
            if not _is_transient(e) or attempt == _RETRY - 1:
                print(f"  [ERR] {p_from} -> {p_to}: {type(e).__name__}: {str(e)[:140]}")
                return False, 0
            print(f"  [retry {attempt + 1}] {p_from} -> {p_to}: "
                  f"{type(e).__name__}: {str(e)[:80]}")
            _sleep_backoff(attempt)
    return False, 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5,
                    help="come refresh_analytics_bets(p_days): copre [oggi-N, oggi+2)")
    ap.add_argument("--from", dest="dal", default=None, help="YYYY-MM-DD (con --to)")
    ap.add_argument("--to", dest="al", default=None, help="YYYY-MM-DD escluso (con --from)")
    ap.add_argument("--dry-run", action="store_true", help="stampa le finestre, non chiama")
    args = ap.parse_args()
    if bool(args.dal) != bool(args.al):
        raise SystemExit("--from e --to vanno insieme.")

    if args.dal:
        p_from = date.fromisoformat(args.dal)
        p_to = date.fromisoformat(args.al)
        if p_to <= p_from:
            raise SystemExit("--to deve essere maggiore di --from.")
        win = finestre_da_intervallo(p_from, p_to)
    else:
        if args.days < 0:
            raise SystemExit("--days non puo' essere negativo.")
        # stesso estremo del wrapper SQL, calcolato UNA volta per tutte le finestre
        win = finestre(datetime.now(timezone.utc).date(), args.days)

    print(f"analytics_bets: {len(win)} finestre da 1 giorno "
          f"({win[0][0]} -> {win[-1][1]}).")
    if args.dry_run:
        for a, b in win:
            print(f"  [DRY-RUN] {_RPC}({a}, {b})")
        return

    sb = get_supabase_client()
    # il server non ha statement_timeout su queste funzioni: il limite e' il client
    sb.postgrest.session.timeout = httpx.Timeout(_HTTP_TIMEOUT)

    tot, falliti = 0, []
    for i, (a, b) in enumerate(win):
        t0 = time.time()
        ok, n = rinfresca_finestra(sb, a, b)
        if ok:
            tot += n
            print(f"  {a}: {n} righe ({time.time() - t0:.1f}s)")
        else:
            falliti.append(a)
        if i < len(win) - 1:
            time.sleep(_PAUSA)

    print(f"analytics_bets refresh: {tot} righe scritte su {len(win)} finestre "
          f"(somma per finestra; i fixture presenti in piu' giorni contano piu' volte).")
    if falliti:
        raise SystemExit(f"ATTENZIONE: {len(falliti)} finestre NON rinfrescate: "
                         f"{[d.isoformat() for d in falliti]}")


if __name__ == "__main__":
    main()
