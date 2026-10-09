"""enrich_analytics_snapshots.py — riempie freq_*/delay_* in analytics_signals con
lo SNAPSHOT POINT-IN-TIME (valore del mercato AL MOMENTO di quella partita), per
OGNI (fixture × mercato × SELEZIONE).

⚠️ FIX BUG STORICO: la v1 applicava lo STESSO snapshot a Over e Under (e non
copriva H/D/A, btts, dc, ht_ft, ...). Sbagliato: freq/ritardo sono DIVERSI per ogni
selezione. Ora ogni riga (fixture, market, selection) riceve lo snapshot DELLA SUA
selezione, calcolato con la matematica certificata di analytics_market_stats
(replica 1:1 di get_market_frequency / get_market_delays — vedi test).

POINT-IN-TIME: per ogni fixture, freq_current = mm10 (media mobile su 10 esiti fino
a quella giornata), freq_baseline = baseline lega (mode all), freq_deviation =
mm10-baseline; delay_current = ritardo a quella giornata, delay_record = record
storico, delay_avg = media ritardi. Tutto sulle partite settlate a 90'.

──────────────────────────────────────────────────────────────────────────────
SCRITTURA BULK A FETTE (veloce + poco stressante per il DB):
  Niente UPDATE riga-per-riga (46k round-trip -> I/O-bound), ma nemmeno UN SOLO
  UPDATE per l'intera lega (sulle leghe grandi supera lo statement_timeout di 8s
  -> 57014 -> lega intera NON aggiornata, in silenzio). Ora, per FETTE di poche
  centinaia di righe:
    1) calcola gli snapshot in Python (compute_market_snapshots, INVARIATO),
    2) carica la FETTA in `analytics_snap_staging` (un upsert),
    3) UPDATE ... FROM scopato alla lega (RPC flush_analytics_snap_staging), che
       aggiorna e poi CANCELLA dalla staging le chiavi appena flushate,
    4) fetta successiva (staging di nuovo vuota per quella lega).
  STAGING PULITA IN PARTENZA (23/09, revisore A - P2): la RPC aggiorna TUTTE le
  righe della lega presenti in staging, quindi prima della PRIMA fetta si
  cancellano dalla staging le righe dei fixture della lega (residui di run
  andati in errore: oggi ~67.000). Altrimenti il primo flush se li porta
  dietro: UPDATE pesante (57014 ogni giorno sulle leghe 131/253) e chiavi non
  ricalcolate in questo run riscritte con valori VECCHI. E se un flush fallisce
  si cancellano le chiavi della fetta appena caricata: i residui non si
  accumulano piu'.
  -> stato finale IDENTICO al flush unico: le fette sono disgiunte, ogni chiave e'
  aggiornata una volta sola e la somma delle righe aggiornate coincide. I numeri
  scritti sono IDENTICI, riga-per-riga, a quelli del metodo riga-per-riga (lo
  staging e' solo trasporto + JOIN set-based).

MODO INCREMENTALE (--days N / --today, per le partite del GIORNO, pre-match):
  Enrichisce SOLO le fixture recenti presenti in analytics_signals. ATTENZIONE
  POINT-IN-TIME: le partite del giorno NON sono ancora settlate → il loro
  freq/ritardo è lo STATO CORRENTE del mercato (il valore "in entrata", calcolato
  sulla storia settlata PRECEDENTE: delay_current = ritardo dopo l'ultima partita
  giocata, freq_current = mm10 corrente). Le fixture recenti GIÀ settlate ricevono
  invece il loro snapshot point-in-time normale. Vedi compute_current_state.

  Una LEGA che non si riesce a leggere (57014 & co. anche dopo i tentativi ed i
  dimezzamenti di blocco, vedi _PAGE_LEGA/_PAGE_MIN) NON ferma le altre: si
  registra come RINVIATA (09/10: prima "leghe_fallite" -> exit != 0 sempre) e
  si passa alla lega successiva (vedi run 35837906029: la lega 929 in 57014
  aveva fatto morire lo script PRIMA di elaborare le leghe dopo). Stessa sorte
  per una SCRITTURA che non passa dopo i ritentativi (run 37927426667, lega
  850). Esito: exit 0 con ::warning:: se le rinviate sono entro la soglia
  (ENRICH_SOGLIA_RINVII_PCT, 25%) e nessuna lo e' da 3 run di fila; altrimenti
  exit 1. Vedi _esito_rinvii.
  Un errore LOGICO (colonna inesistente, vincolo, ...) propaga SUBITO: non è un
  DB sotto pressione, è un difetto da vedere e basta, non da inghiottire lega
  per lega.

Uso:
  python enrich_analytics_snapshots.py --league 256              # storico lega
  python enrich_analytics_snapshots.py --league 256 --dry-run
  python enrich_analytics_snapshots.py --days 4                  # incrementale (action)
  python enrich_analytics_snapshots.py --today                   # solo oggi
  python enrich_analytics_snapshots.py --days 4 --leagues 292,293  # recupero leghe fallite
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import classifica_guasto_rete, get_supabase_client, ritentativi_del_chiamante
from analytics_market_stats import (
    Snapshot,
    compute_current_state,
    compute_market_snapshots,
)

_MATCH_COLS = ("fixture_id,fixture_date,status_short,season_year,goals_home,goals_away,"
               "fulltime_home,fulltime_away,halftime_home,halftime_away")
_STAGE_BATCH = 500      # tetto massimo di righe in UNA richiesta di upsert
_FLUSH_SLICE = 400      # righe per FETTA carica->flush (adattiva: dimezza sui transitori)
_FLUSH_MIN = 50         # fetta minima
_PAGE = 1000            # righe per pagina RICHIESTE in lettura (storico/incrementale)
_PAGE_LEGA = 100        # blocco INIZIALE per la lettura analytics_signals di UNA lega
                        # (la lettura "per lega" e' la piu' delicata: e' quella che ha
                        # dato 57014 in produzione sulla lega 929, vedi run 35837906029)
_PAGE_MIN = 25          # blocco minimo dopo i dimezzamenti sui transitori (100 -> 50 -> 25).
                        # PRIMA era 100: il floor coincideva col blocco iniziale della
                        # lettura per lega, quindi quella lettura non si dimezzava MAI
                        # davvero e restava a riprovare 5 volte lo STESSO blocco -> 57014
                        # ripetuto, RuntimeError, intero script morto (vedi _leggi_pagine).
_RETRY = 5              # tentativi su errori TRANSITORI
_CLEAN_FIXTURES = 100   # fixture per richiesta di DELETE sulla staging (URL corto)

# ---------------------------------------------------------------------------
# 09/10/2026 - RINVIO DICHIARATO (AUDIT_2026-10-09/fallimenti_action/ENRICH_RINVIO.md)
# ---------------------------------------------------------------------------
# Run 37927426667: dopo 116 minuti il flush della lega 850 e' andato in ReadTimeout
# (client a 120 s = statement_timeout della RPC lato server, 120 s: gara persa dal
# server), 5 tentativi a 0,5-4 s di distanza, lega abbandonata, 3612 righe contate
# come "falliti" -> exit 1 -> run ROSSA per un DB sotto carico.
# Ora le SCRITTURE (upsert in staging, RPC di flush, pulizia staging):
#   - timeout di lettura del client 150 s SOLO durante la scrittura (oltre i 120 s
#     della RPC: decide il server, con un 57014 chiaro invece di un esito ignoto);
#   - ritentativi sui transitori con attese 2-4-8-16-32-60 s (jitter +-25%), un solo
#     strato (il TrasportoResiliente non ritenta qui sotto, vedi _scrittura);
#   - transitorio ancora presente: lega RINVIATA (contatore separato da "failed"),
#     riga chiara, avviso in live_alerts, riepilogo; ripresa al giro successivo;
#   - errore LOGICO (4xx, vincolo, colonna): RuntimeError SUBITO -> exit 1.
_ATTESE_SCRITTURA_S = (2.0, 4.0, 8.0, 16.0, 32.0, 60.0)
_TIMEOUT_SCRITTURA_S = 150.0      # env ENRICH_TIMEOUT_SCRITTURA_S
_CONNECT_SCRITTURA_S = 10.0
_SOGLIA_RINVII_PCT = 25.0         # env ENRICH_SOGLIA_RINVII_PCT (% delle leghe elaborate)
_RUN_RINVIO_PERSISTENTE = 3       # stessa lega rinviata in 3 run di fila -> exit 1
_RINVII_DI_FILA_MAX = 3           # 3 leghe rinviate una dopo l'altra: il DB non risponde
_GIORNI_STORIA_RINVII = 14        # quanto indietro si legge live_alerts
COD_RINVIO = "ENRICH_RINVIO"
COD_RINVIO_PERSISTENTE = "ENRICH_RINVIO_PERSISTENTE"
COD_RIPRESA = "ENRICH_RIPRESA"
_RE_LEGA_ALLARME = re.compile(r"^lega (\d+):")


class _Rinvio(Exception):
    """Scrittura non riuscita dopo tutti i ritentativi su un errore TRANSITORIO."""

# Errori TRANSITORI (si ritentano): statement timeout, DB occupato/riavvio,
# deadlock/serializzazione, connessione persa, 5xx del gateway, PGRST002 (schema
# cache non pronta). Gli errori LOGICI (vincoli, 4xx di validazione) NON si ritentano.
_TRANSIENT_CODES = {"57014", "53300", "53400", "55P03", "40001", "40P01",
                    "08006", "08003", "08000", "57P01", "57P02", "57P03",
                    "PGRST002", "408", "500", "502", "503", "504"}


def _is_transient(e: Exception) -> bool:
    """True solo per gli errori che ha senso ritentare."""
    if isinstance(e, httpx.TransportError):   # ReadTimeout, ConnectError, PoolTimeout...
        return True
    code = getattr(e, "code", None)
    if code is not None and str(code) in _TRANSIENT_CODES:
        return True
    msg = str(getattr(e, "message", "") or "").lower()
    if "timeout" in msg or "temporarily unavailable" in msg:
        return True
    # 09/10: anche i guasti di gateway/rete che db_client riconosce (pagine Cloudflare
    # 520-530, 5xx, PGRST000-003, 08xxx, errori h2/httpcore): stessa classificazione
    # del TrasportoResiliente. 4xx ed errori applicativi restano NON transitori.
    return classifica_guasto_rete(e) is not None


def _is_retry_esauriti(err: RuntimeError) -> bool:
    """True se il RuntimeError arriva da `_leggi_pagine` per TENTATIVI ESAURITI su
    un errore TRANSITORIO (57014 & co. dopo _RETRY prove). In questo caso la lega
    puo' essere saltata e le altre leghe proseguono.

    False per un errore LOGICO (colonna inesistente, vincolo, 4xx di validazione):
    `_leggi_pagine` lo rilancia SUBITO (al primo tentativo, non esaurisce i retry)
    ed e' un difetto del codice/schema, non del DB sotto pressione -> deve
    propagare e fermare lo script, non essere inghiottito lega per lega.

    `_leggi_pagine` fa sempre `raise RuntimeError(...) from e`: la causa originale
    resta in `__cause__` ed e' li' che si legge se era transitoria."""
    causa = err.__cause__
    return causa is not None and _is_transient(causa)


def _sleep_backoff(attempt: int) -> None:
    """Attesa crescente con jitter (0,7x-1,3x)."""
    time.sleep(min(8.0, 0.5 * (2 ** attempt)) * (0.7 + random.random() * 0.6))


def _cursore_id(r: dict):
    """Cursore keyset di default: la chiave primaria `id` dell'ultima riga letta."""
    return r["id"]


def _leggi_pagine(fai_query, what: str, page: int = _PAGE,
                  cursore=_cursore_id) -> list[dict]:
    """Legge TUTTE le pagine di una query con paginazione KEYSET (24/09).

    `fai_query(dopo, size)` costruisce la query di UNA pagina: `dopo` e' None
    alla prima pagina, poi il cursore dell'ultima riga ricevuta (`cursore(riga)`);
    il chiamante filtra `> dopo` sulla colonna d'ordine e mette `.limit(size)`.
    MAI OFFSET: con OFFSET il server deve SCORRERE e scartare tutte le righe
    precedenti a ogni pagina. Sulla lettura per lega di analytics_signals il
    piano era `Index Scan using analytics_signals_pkey ... Filter: (league_id =
    N)` -> per arrivare alla pagina k scorreva l'intera tabella (945.156 righe)
    fino a trovare k*blocco righe della lega: 57014 anche a blocco 25 sulle
    leghe piccole (run 35976004167: 292, 293, 653, 251, 401, 164, 253, 489,
    650, 243). Con il keyset ogni pagina riparte dal cursore: con l'indice
    (league_id, id) e' un Index Scan con Limit che legge SOLO `size` righe.

    Tre regole, contro la perdita silenziosa di righe:
      1) ORDINE TOTALE server-side (lo mette il chiamante su una colonna UNICA,
         la stessa del cursore): senza ordine totale il cursore salterebbe o
         ripeterebbe righe;
      2) si esce SOLO a pagina VUOTA: una pagina piu' corta di quanto chiesto
         puo' essere il cap del server (PostgREST max-rows), non la fine dei dati;
      3) retry sui soli errori transitori, con pagina dimezzata: se non si riesce
         a leggere, l'errore ESCE (mai una storia troncata scambiata per completa).
    """
    out: list[dict] = []
    dopo, size = None, page
    while True:
        righe = None
        for attempt in range(_RETRY):
            try:
                righe = fai_query(dopo, size).execute().data or []
                break
            except Exception as e:  # noqa: BLE001
                if not _is_transient(e) or attempt == _RETRY - 1:
                    raise RuntimeError(
                        f"lettura {what} (dopo {dopo!r}, blocco {size}) fallita dopo "
                        f"{attempt + 1} tentativi: {type(e).__name__}: {str(e)[:120]}") from e
                _sleep_backoff(attempt)
                size = max(_PAGE_MIN, size // 2)
        if not righe:
            return out
        out.extend(righe)
        dopo = cursore(righe[-1])


def _dopo(q, col: str, dopo):
    """Applica il filtro keyset `col > dopo` (niente alla prima pagina)."""
    return q if dopo is None else q.gt(col, dopo)


def _dopo_season_fixture(q, dopo):
    """Filtro keyset sul cursore composto (season_year, fixture_id): righe DOPO
    l'ultima letta nell'ordine `season_year, fixture_id` (24/09, fix lega 667,
    vedi _fetch_matches)."""
    if dopo is None:
        return q
    sy, fid = dopo
    return q.or_(f'season_year.gt.{sy},and(season_year.eq.{sy},fixture_id.gt.{fid})')


def _fetch_matches(sb, league_id: int) -> list[dict]:
    """Tutte le partite settlate (status 90') della lega, per la serie cronologica
    (l'ordine di LETTURA non conta per i calcoli: compute_market_snapshots e
    compute_current_state riordinano SEMPRE con chrono_key=(fixture_date,
    fixture_id), vedi test_snapshot_non_cambiano_con_l_ordine_di_lettura -- qui
    l'ordine serve SOLO al cursore keyset, che deve restare un ordine TOTALE
    sulle righe restituite).

    ORDINE (season_year, fixture_id), NON (fixture_id) da solo (24/09, lega 667):
    fixture_id e' un ID GLOBALE crescente nel tempo su TUTTE le leghe (non per
    lega). Senza un indice (league_id, fixture_id) -- su `matches` esiste solo
    idx_matches_league_season (league_id, season_year) e idx_matches_fixture_id
    (fixture_id) da solo, vedi sql/perf_indexes.sql -- un Index Scan ordinato per
    fixture_id deve scorrere l'INTERA matches filtrando per lega: sulla lega 667
    (44.533 partite, 39.750 settlate, sparse su tutto lo storico) andava in
    57014 anche a blocco 62 (5 tentativi, dopo=None) e persino su un ORDER BY
    fixture_id LIMIT 1 (letture di sola misura, 24/09). (season_year, fixture_id)
    sfrutta l'indice GIA' ESISTENTE idx_matches_league_season: misurato sulla
    STESSA lega 667, prima pagina in 0,24s (prima: timeout dopo ~40s di
    tentativi). fixture_id resta il tie-breaker (UNICO in matches,
    matches_fixture_unique): l'ordine totale regge lo stesso.

    GUARDIA season_year NULL: vedi _cursore_matches sotto -- un NULL romperebbe
    il filtro `season_year.gt.Y` (NULL > Y e' sconosciuto/falso in SQL) e la riga
    sparirebbe dalle pagine successive IN SILENZIO. Oggi (24/09, misurato) matches
    non ha righe con season_year NULL; se mai comparisse e' un difetto dei dati
    (schema), non un DB sotto pressione, e deve fermare lo script SUBITO come gli
    altri errori LOGICI (vedi _is_retry_esauriti), non essere inghiottito lega per
    lega. Una storia partite TRONCATA darebbe freq/ritardi FALSI scritti come se
    fossero buoni."""
    def _cursore_matches(r: dict):
        if r.get("season_year") is None:
            raise RuntimeError(
                f"matches lega {league_id} fixture_id={r.get('fixture_id')}: "
                "season_year NULL, il cursore keyset (season_year, fixture_id) "
                "non e' sicuro per questa riga (si fermerebbe la lettura o si "
                "perderebbe la riga in silenzio).")
        return (r["season_year"], r["fixture_id"])

    return _leggi_pagine(
        lambda dopo, size: _dopo_season_fixture(
            sb.table("matches").select(_MATCH_COLS)
            .eq("league_id", league_id)
            .in_("status_short", ["FT", "AET", "PEN"]), dopo)
        .order("season_year").order("fixture_id").limit(size),
        f"matches lega {league_id}", cursore=_cursore_matches)


def _fetch_signal_targets(sb, league_id: int) -> dict[tuple[str, str], set[int]]:
    """{(market, selection): {fixture presenti}} per i SOLI (fixture×market×selection)
    in analytics_signals della lega -- cosi' non si fanno UPDATE a vuoto.
    ORDER BY id (chiave primaria, unica) = ordine totale; keyset `id > cursore`
    (con l'indice idx_as_league_id_id = Index Scan (league_id, id) + Limit;
    senza l'indice resta corretta, solo piu' lenta)."""
    by_ms: dict[tuple[str, str], set[int]] = defaultdict(set)
    for x in _leggi_pagine(
            lambda dopo, size: _dopo(sb.table("analytics_signals")
                                     .select("id,fixture_id,market,selection")
                                     .eq("league_id", league_id), "id", dopo)
            .order("id").limit(size),
            f"analytics_signals lega {league_id}", page=_PAGE_LEGA):
        by_ms[(x["market"], x["selection"])].add(x["fixture_id"])
    return by_ms


def _snap_payload(s: Snapshot) -> dict:
    return {
        "freq_baseline": s.freq_baseline,
        "freq_current": s.freq_current,
        "freq_deviation": s.freq_deviation,
        "delay_current": s.delay_current,
        "delay_record": s.delay_record,
        "delay_avg": s.delay_avg,
    }


def _stage_row(fid: int, market: str, selection: str, s: Snapshot) -> dict:
    return {"fixture_id": fid, "market": market, "selection": selection, **_snap_payload(s)}


def _timeout_scrittura() -> httpx.Timeout:
    """Timeout del client durante le SCRITTURE (override ENRICH_TIMEOUT_SCRITTURA_S)."""
    try:
        lettura = float((os.environ.get("ENRICH_TIMEOUT_SCRITTURA_S") or "").strip())
    except ValueError:
        lettura = _TIMEOUT_SCRITTURA_S
    if lettura <= 0:
        lettura = _TIMEOUT_SCRITTURA_S
    return httpx.Timeout(lettura, connect=_CONNECT_SCRITTURA_S, pool=_CONNECT_SCRITTURA_S)


@contextmanager
def _scrittura(sb) -> Iterator[None]:
    """Contesto di UNA richiesta di scrittura di questo script:
    1) timeout di lettura 150 s sul client PostgREST di QUESTO processo, solo per la
       durata della richiesta (poi torna quello di prima): il client non deve chiudere
       prima del server (RPC flush: statement_timeout 120 s, pg_proc 09/10);
    2) il TrasportoResiliente non ritenta (db_client.ritentativi_del_chiamante): ritenta
       _scrivi_con_ritentativi, un solo strato. Client finti senza sessione httpx: solo 2)."""
    sessione = getattr(getattr(sb, "postgrest", None), "session", None)
    prima = None
    if isinstance(sessione, httpx.Client):
        prima = sessione.timeout
        sessione.timeout = _timeout_scrittura()
    try:
        with ritentativi_del_chiamante():
            yield
    finally:
        if prima is not None:
            sessione.timeout = prima


def _descrivi(e: Exception) -> str:
    codice = getattr(e, "code", None)
    testo = str(getattr(e, "message", None) or e)
    return (f"{type(e).__name__}" + (f" code={codice}" if codice is not None else "")
            + f": {testo[:100]}")


def _scrivi_con_ritentativi(fai, cosa: str, sb=None):
    """Esegue UNA richiesta di scrittura `fai()` con i ritentativi del 09/10.
    Transitorio (ReadTimeout, 57014, 5xx, pagina Cloudflare, GOAWAY...) -> attese
    2-4-8-16-32-60 s (jitter +-25%), poi _Rinvio. Errore LOGICO -> RuntimeError
    subito (from e: la causa resta in __cause__ e _is_retry_esauriti la vede logica).
    Tutte le scritture qui sono ripetibili senza effetti doppi: upsert in staging,
    DELETE per chiave, RPC di flush (UPDATE ... FROM staging + DELETE delle chiavi
    flushate: rieseguita dopo un esito ignoto trova la staging gia' vuota per quelle
    chiavi e aggiorna 0 righe, stato finale identico)."""
    totale = len(_ATTESE_SCRITTURA_S) + 1
    for i in range(totale):
        try:
            with _scrittura(sb):
                return fai()
        except Exception as e:  # noqa: BLE001 - classificata sotto
            if not _is_transient(e):
                raise RuntimeError(f"errore LOGICO su {cosa}: {_descrivi(e)}") from e
            if i + 1 >= totale:
                raise _Rinvio(f"{cosa}: {_descrivi(e)} dopo {totale} tentativi") from e
            attesa = _ATTESE_SCRITTURA_S[i] * (0.75 + 0.5 * random.random())
            print(f"    [RITENTO] {cosa}: {_descrivi(e)} (tentativo {i + 1}/{totale}) "
                  f"-> attendo {attesa:.0f} s", flush=True)
            time.sleep(attesa)
    raise RuntimeError("non raggiungibile")  # pragma: no cover


def _registra_rinvio(counters: dict, league_id: int, righe: Optional[int], motivo: str,
                     aggiornate: int = 0) -> None:
    counters.setdefault("rinviate", []).append(
        {"lega": league_id, "righe": righe, "motivo": motivo, "aggiornate": aggiornate})


def _upsert_stage(sb, rows: list[dict], counters: dict) -> bool:
    """Carica UNA fetta nella staging (una sola richiesta). True se scritta;
    _Rinvio su transitorio persistente, RuntimeError su errore logico."""
    _scrivi_con_ritentativi(
        lambda: (sb.table("analytics_snap_staging")
                 .upsert(rows, on_conflict="fixture_id,market,selection").execute()),
        f"upsert staging ({len(rows)} righe)", sb)
    return True


def _flush_league(sb, league_id: int) -> tuple[bool, int]:
    """UN UPDATE ... FROM (RPC) sulle righe ATTUALMENTE in staging per la lega.
    La RPC cancella dalla staging le sole chiavi flushate -> le fette successive
    partono da una staging vuota. Ritorna (True, righe_aggiornate); _Rinvio su
    transitorio persistente, RuntimeError su errore logico."""
    res = _scrivi_con_ritentativi(
        lambda: sb.rpc("flush_analytics_snap_staging", {"p_league_id": league_id}).execute(),
        f"flush lega {league_id}", sb)
    return True, (res.data if isinstance(res.data, int) else 0)


def _delete_stage_fixtures(sb, fids: set[int], what: str) -> bool:
    """Cancella dalla staging le righe dei fixture `fids` (a blocchi di
    _CLEAN_FIXTURES, ritentativi sui transitori). True se TUTTE le richieste sono
    riuscite; _Rinvio su transitorio persistente, RuntimeError su errore logico.
    La staging non ha league_id: la RPC scopa alla lega con il JOIN
    su analytics_signals, e un fixture appartiene a una sola lega, quindi
    cancellare per fixture_id toglie esattamente cio' che il flush della lega
    toccherebbe (e niente delle altre leghe)."""
    ordinati = sorted(fids)
    for i in range(0, len(ordinati), _CLEAN_FIXTURES):
        blocco = ordinati[i:i + _CLEAN_FIXTURES]
        _scrivi_con_ritentativi(
            lambda b=blocco: (sb.table("analytics_snap_staging").delete()
                              .in_("fixture_id", b).execute()),
            f"pulizia staging {what}", sb)
    return True


def _flush_staging(sb, league_id: int, stage_rows: list[dict], counters: dict,
                   slice_state: Optional[dict] = None,
                   league_fids: Optional[set[int]] = None) -> int:
    """Scrive gli snapshot A FETTE: per ogni fetta di poche centinaia di righe
    -> upsert in staging + UNA RPC di flush. Ritorna le righe aggiornate.

    PERCHE' A FETTE: la RPC fa UN SOLO UPDATE ... FROM per tutta la staging della
    lega; sulle leghe grandi (migliaia di righe) supera lo statement_timeout di 8s
    (57014) e l'intera lega resta NON aggiornata. Le fette danno lo STESSO stato
    finale: la RPC cancella dalla staging le chiavi appena flushate, quindi le
    fette sono sequenziali e disgiunte, ogni chiave viene aggiornata UNA volta, e
    la somma delle righe aggiornate e' identica a quella del flush unico.

    STAGING PULITA (P2, 23/09): prima della PRIMA fetta si cancellano dalla
    staging le righe dei fixture della lega (`league_fids`: tutti i fixture
    della lega in analytics_signals; se manca, quelli di `stage_rows`), cosi'
    il flush tocca SOLO le chiavi calcolate in questo run. Se la pulizia non
    riesce la lega viene RINVIATA SENZA flush (flushare i residui riscriverebbe
    valori vecchi).

    09/10 - RINVIO: se una scrittura non riesce dopo i ritentativi (transitorio:
    DB sotto carico) la LEGA viene RINVIATA (caricarne altre renderebbe l'UPDATE
    ancora piu' pesante): fetta dimezzata per le leghe successive, chiavi della
    fetta appena caricata tolte dalla staging, righe non scritte in
    counters['rinviate'] (NON in 'failed'). Le riprende il giro successivo: ogni
    giro ricalcola e riscrive TUTTE le righe della lega (vedi _enrich_league).
    Un errore LOGICO risale come RuntimeError (exit 1).
    """
    if not stage_rows:
        return 0
    fids_lega = set(league_fids) if league_fids is not None else set()
    fids_lega |= {r["fixture_id"] for r in stage_rows}
    try:
        _delete_stage_fixtures(sb, fids_lega, f"lega {league_id}")
    except _Rinvio as r:
        motivo = f"staging non ripulita, nessun flush: {r}"
        _registra_rinvio(counters, league_id, len(stage_rows), motivo)
        print(f"    RINVIATA lega {league_id}: {len(stage_rows)} righe, motivo: {motivo}",
              flush=True)
        return 0
    state = slice_state if slice_state is not None else {"size": _FLUSH_SLICE}
    updated = 0
    i = 0
    while i < len(stage_rows):
        size = max(_FLUSH_MIN, min(int(state["size"]), _STAGE_BATCH))
        part = stage_rows[i:i + size]
        i += len(part)
        try:
            _upsert_stage(sb, part, counters)
            _ok, n = _flush_league(sb, league_id)
        except _Rinvio as r:
            state["size"] = max(_FLUSH_MIN, size // 2)   # fetta adattiva
            rinviate = len(part) + (len(stage_rows) - i)
            # la fetta caricata non deve restare in staging come residuo (se anche
            # questo non riesce, la toglie la pulizia P2 del giro successivo)
            try:
                _delete_stage_fixtures(sb, {r_["fixture_id"] for r_ in part},
                                       f"fetta rinviata lega {league_id}")
            except (_Rinvio, RuntimeError) as e:
                print(f"    [AVVISO] fetta rinviata lega {league_id} non tolta dalla staging "
                      f"({e}): la toglie la pulizia della lega al giro successivo", flush=True)
            motivo = str(r)
            _registra_rinvio(counters, league_id, rinviate, motivo, aggiornate=updated)
            print(f"    RINVIATA lega {league_id}: {rinviate} righe, motivo: {motivo} "
                  f"(fetta ridotta a {state['size']})", flush=True)
            return updated
        updated += n
    return updated


def _build_stage_rows(by_ms: dict[tuple[str, str], set[int]],
                      matches: list[dict],
                      current_fids: Optional[set[int]] = None,
                      dry_examples: Optional[list[str]] = None) -> list[dict]:
    """Costruisce le righe di staging per la lega.
    - per i fixture SETTLATI (in matches): snapshot point-in-time (compute_market_snapshots).
    - per i fixture in `current_fids` (recenti/non-settlati, modo incrementale):
      STATO CORRENTE del mercato (compute_current_state) — il valore "in entrata".
    """
    current_fids = current_fids or set()
    stage: list[dict] = []
    for (market, selection), present_fids in sorted(by_ms.items()):
        snaps = compute_market_snapshots(market, selection, matches)
        # fixture settlati realmente in tabella per QUESTA (market, selection)
        hit_fids = present_fids & set(snaps)
        for fid in hit_fids:
            if dry_examples is not None and len(dry_examples) < 40:
                dry_examples.append(f"    {market}/{selection} fix {fid}: {_snap_payload(snaps[fid])}")
            stage.append(_stage_row(fid, market, selection, snaps[fid]))
        # fixture recenti NON settlati di questa (market, selection) → stato corrente
        cur_targets = (present_fids & current_fids) - set(snaps)
        if cur_targets:
            cur = compute_current_state(market, selection, matches)
            for fid in cur_targets:
                if dry_examples is not None and len(dry_examples) < 40:
                    dry_examples.append(f"    [CUR] {market}/{selection} fix {fid}: {_snap_payload(cur)}")
                stage.append(_stage_row(fid, market, selection, cur))
    return stage


def _enrich_league(sb, league_id: int, dry: bool, counters: dict,
                   current_fids: Optional[set[int]] = None,
                   slice_state: Optional[dict] = None) -> tuple[int, int]:
    """Enrichisce UNA lega (bulk). Ritorna (n_righe_target, n_aggiornate)."""
    by_ms = _fetch_signal_targets(sb, league_id)
    if not by_ms:
        return 0, 0
    matches = _fetch_matches(sb, league_id)
    if not matches:
        return sum(len(v) for v in by_ms.values()), 0
    dry_examples: list[str] = [] if dry else None  # type: ignore[assignment]
    stage = _build_stage_rows(by_ms, matches, current_fids, dry_examples)
    n_target = len(stage)
    if dry:
        print(f"  [DRY-RUN] lega {league_id}: {n_target} righe da scrivere (bulk). Esempi:")
        for line in (dry_examples or [])[:20]:
            print(line)
        return n_target, 0
    league_fids: set[int] = set().union(*by_ms.values())
    updated = _flush_staging(sb, league_id, stage, counters, slice_state,
                             league_fids=league_fids)
    return n_target, updated


def _dopo_kickoff_id(q, dopo):
    """Filtro keyset sul cursore composto (kickoff, id): righe DOPO l'ultima letta
    nell'ordine `kickoff, id`. Il timestamp va fra virgolette doppie nel filtro
    `or` di PostgREST (contiene ':' e '+')."""
    if dopo is None:
        return q
    k, i = dopo
    return q.or_(f'kickoff.gt."{k}",and(kickoff.eq."{k}",id.gt.{int(i)})')


def _recent_targets(sb, days: int) -> dict[int, set[int]]:
    """{league_id: {fixture recenti}} per le righe di analytics_signals con
    kickoff negli ultimi `days` giorni. Serve al modo incrementale: enrichisce
    SOLO queste leghe, e tratta i loro fixture non-settlati come stato corrente."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: dict[int, set[int]] = defaultdict(set)
    # ORDER BY kickoff,id: kickoff e' gia' l'ordine dell'indice usato dal filtro
    # (idx_as_kickoff) e id lo rende TOTALE; il piano resta lo stesso con un
    # Incremental Sort (misurato: 26.076 contro 25.031, +4%).
    # KEYSET composto (24/09): cursore (kickoff, id) dell'ultima riga, filtro
    # `kickoff > k OR (kickoff = k AND id > i)` -> niente OFFSET sull'indice kickoff.
    for x in _leggi_pagine(
            lambda dopo, size: _dopo_kickoff_id(
                sb.table("analytics_signals").select("league_id,fixture_id,kickoff,id")
                .gte("kickoff", since), dopo)
            .order("kickoff").order("id").limit(size),
            f"analytics_signals recenti (da {since[:10]})",
            cursore=lambda r: (r["kickoff"], r["id"])):
        if x.get("league_id") is not None:
            out[x["league_id"]].add(x["fixture_id"])
    return out


def _soglia_rinvii_pct() -> float:
    """Soglia % di leghe rinviate oltre la quale la run e' rossa (ENRICH_SOGLIA_RINVII_PCT)."""
    try:
        v = float((os.environ.get("ENRICH_SOGLIA_RINVII_PCT") or "").strip())
    except ValueError:
        return _SOGLIA_RINVII_PCT
    return v if v >= 0 else _SOGLIA_RINVII_PCT


def _storia_rinvii(sb) -> dict[int, int]:
    """{lega: rinvii CONSECUTIVI nelle run precedenti} letti da public.live_alerts
    (righe ENRICH_RINVIO / ENRICH_RINVIO_PERSISTENTE / ENRICH_RIPRESA scritte da questo
    script, messaggio che inizia con "lega N:"). Si contano i rinvii dal piu' recente
    all'indietro fino alla prima ENRICH_RIPRESA della stessa lega. Nessuna tabella
    nuova: lo stato fra run vive negli avvisi che l'utente vede gia' nell'app.
    Lettura non riuscita: {} con avviso (rinvii contati da zero), mai un crash."""
    since = (datetime.now(timezone.utc) - timedelta(days=_GIORNI_STORIA_RINVII)).isoformat()
    try:
        righe = (sb.table("live_alerts").select("id,code,message,created_at")
                 .in_("code", [COD_RINVIO, COD_RINVIO_PERSISTENTE, COD_RIPRESA])
                 .gte("created_at", since)
                 .order("created_at", desc=True).order("id", desc=True)
                 .limit(2000).execute().data or [])
    except Exception as e:  # noqa: BLE001 - canale ausiliario: si dichiara e si prosegue
        print(f"::warning::enrich: storico dei rinvii (live_alerts) non leggibile "
              f"({_descrivi(e)}): rinvii consecutivi contati da zero e leghe rinviate "
              f"nelle run precedenti non aggiunte d'ufficio", flush=True)
        return {}
    out: dict[int, int] = {}
    chiuse: set[int] = set()
    for r in righe:
        m = _RE_LEGA_ALLARME.match(str(r.get("message") or ""))
        if not m:
            continue
        lid = int(m.group(1))
        if lid in chiuse:
            continue
        if r.get("code") == COD_RIPRESA:
            chiuse.add(lid)
            out.setdefault(lid, 0)
            continue
        out[lid] = out.get(lid, 0) + 1
    return out


def _scrivi_allarme(sb, level: str, code: str, message: str) -> bool:
    """Una riga in public.live_alerts (colonne vere: level, code, message). Insert
    puro: UN tentativo (un doppione sarebbe un avviso doppio). Errore -> avviso nel
    log, mai un crash: il rinvio resta dichiarato nel log e nel riepilogo del job."""
    try:
        sb.table("live_alerts").insert(
            {"level": level, "code": code, "message": message[:500]}).execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"::warning::enrich: avviso {code} non scritto in live_alerts "
              f"({_descrivi(e)}): {message}", flush=True)
        return False


def _scrivi_output_job(nome: str, valore: str) -> None:
    percorso = os.environ.get("GITHUB_OUTPUT")
    if percorso:
        try:
            with open(percorso, "a", encoding="utf-8") as fh:
                fh.write(f"{nome}={valore}\n")
        except OSError:
            pass


def _scrivi_riepilogo_job(testo: str) -> None:
    percorso = os.environ.get("GITHUB_STEP_SUMMARY")
    if percorso:
        try:
            with open(percorso, "a", encoding="utf-8") as fh:
                fh.write(testo)
        except OSError:
            pass


def _esito_rinvii(sb, counters: dict, storia: dict[int, int], leghe_ok: set[int],
                  n_leghe: int, scrivi: bool = True) -> None:
    """Chiude il modo incrementale: avvisi in live_alerts, riepilogo del job, exit.
      - nessun rinvio: niente (exit 0 come sempre); le leghe rinviate in passato e
        scritte oggi ricevono la riga ENRICH_RIPRESA;
      - rinvii <= soglia e nessuna lega rinviata per la 3a run di fila: ::warning::,
        exit 0 (la run resta VERDE: il DB era sotto carico, nessun dato perso);
      - rinvii oltre soglia, o una lega rinviata da >= 3 run consecutive:
        ::error:: e SystemExit (exit 1, run ROSSA)."""
    rinviate = counters.get("rinviate", [])
    for lid in sorted(leghe_ok):
        if storia.get(lid, 0) > 0 and scrivi:
            _scrivi_allarme(sb, "INFO", COD_RIPRESA,
                            f"lega {lid}: freq/ritardi RIPRESI e scritti dopo "
                            f"{storia[lid]} run con rinvio")
            print(f"  RIPRESA lega {lid}: scritta dopo {storia[lid]} run con rinvio")
    _scrivi_output_job("rinvii", str(len(rinviate)))
    if not rinviate:
        return
    soglia = _soglia_rinvii_pct()
    pct = 100.0 * len(rinviate) / n_leghe if n_leghe else 100.0
    persistenti = []
    righe_md = []
    print(f"\nRINVIATE ({len(rinviate)} leghe, {pct:.1f}% delle {n_leghe} elaborate, "
          f"soglia {soglia:.0f}%): righe NON scritte oggi, riprese al giro successivo "
          f"(ogni giro riscrive tutte le righe della lega)")
    for r in rinviate:
        consecutivi = storia.get(r["lega"], 0) + 1
        righe_txt = "righe non calcolate (lettura)" if r["righe"] is None else f"{r['righe']} righe"
        testo = (f"lega {r['lega']}: {righe_txt} RINVIATE al prossimo giro, motivo: "
                 f"{r['motivo']}; run consecutive con rinvio: {consecutivi}")
        persistente = consecutivi >= _RUN_RINVIO_PERSISTENTE
        if persistente:
            persistenti.append(r["lega"])
        print(f"  - RINVIATA {testo}")
        righe_md.append(f"- {'**PERSISTENTE** ' if persistente else ''}{testo}")
        if scrivi:
            _scrivi_allarme(sb, "CRITICAL" if persistente else "WARN",
                            COD_RINVIO_PERSISTENTE if persistente else COD_RINVIO, testo)
    oltre = pct > soglia
    if oltre or persistenti:
        motivi = []
        if oltre:
            motivi.append(f"rinvii oltre la soglia ({pct:.1f}% > {soglia:.0f}%)")
        if persistenti:
            motivi.append(f"leghe rinviate da >= {_RUN_RINVIO_PERSISTENTE} run consecutive: "
                          f"{persistenti}")
        esito = "guasto"
        riga = ("ENRICH: " + "; ".join(motivi) + f" - {len(rinviate)} leghe rinviate: "
                f"{[r['lega'] for r in rinviate]}")
        print(f"::error::{riga}", flush=True)
    else:
        esito = "rinviato"
        riga = (f"ENRICH: {len(rinviate)} leghe RINVIATE per DB sotto carico "
                f"({pct:.1f}% <= soglia {soglia:.0f}%), riprese al giro successivo: "
                f"{[r['lega'] for r in rinviate]}")
        print(f"::warning::{riga}", flush=True)
    _scrivi_output_job("esito", esito)
    _scrivi_riepilogo_job(f"### Enrich freq/ritardi: RINVIATE PER DB SOTTO CARICO ({esito})\n\n"
                          f"{riga}\n\n" + "\n".join(righe_md) + "\n")
    if esito == "guasto":
        raise SystemExit(f"ATTENZIONE: {riga}.")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, default=None, help="storico di UNA lega")
    ap.add_argument("--days", type=int, default=None,
                    help="incrementale: solo fixture (per lega) con kickoff negli ultimi N giorni")
    ap.add_argument("--today", action="store_true", help="alias di --days 1")
    ap.add_argument("--leagues", default="",
                    help="RECUPERO (con --days/--today): elabora SOLO queste leghe, "
                         "CSV di id (es. 292,293). Vuoto = tutte (default).")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        solo_leghe = {int(x) for x in args.leagues.replace(" ", "").split(",") if x}
    except ValueError:
        raise SystemExit(f"--leagues non valido: {args.leagues!r} (atteso CSV di interi)")
    if not args.league and not args.days and not args.today:
        raise SystemExit("Specificare --league N | --days N | --today")

    sb = get_supabase_client()
    # failed: righe perse per altri motivi (oggi nessuno: un errore logico risale subito);
    # rinviate: leghe non scritte per DB sotto carico (09/10), vedi _esito_rinvii.
    counters = {"failed": 0, "rinviate": []}
    # dimensione della fetta di flush, condivisa fra le leghe: si dimezza dopo un
    # flush fallito e resta ridotta per le leghe successive (DB sotto pressione).
    slice_state = {"size": _FLUSH_SLICE}

    # ---- MODO STORICO: una lega intera (point-in-time su tutte le settlate) ----
    if args.league:
        n_target, updated = _enrich_league(sb, args.league, args.dry_run, counters,
                                           slice_state=slice_state)
        if n_target == 0:
            print(f"Lega {args.league}: nessuna riga in analytics_signals. Nulla da fare.")
            return
        print(f"\nLega {args.league}: {n_target} righe-target | aggiornate {updated} "
              f"(BULK) | falliti {counters['failed']} | rinviate "
              f"{sum(r['righe'] or 0 for r in counters['rinviate'])}")
        if counters["failed"] or counters["rinviate"]:
            # lancio a mano di UNA lega: chi l'ha chiesto deve vedere che non e' finita
            raise SystemExit(f"ATTENZIONE: lega {args.league} non scritta per intero "
                             f"({counters['failed']} falliti, rinvii: {counters['rinviate']}).")
        return

    # ---- MODO INCREMENTALE: leghe con fixture recenti (point-in-time + stato corrente) ----
    days = args.days if args.days else 1
    storia = {} if args.dry_run else _storia_rinvii(sb)
    recent = _recent_targets(sb, days)
    if solo_leghe:
        # recupero mirato delle leghe fallite in un run precedente
        mancanti = sorted(solo_leghe - set(recent))
        recent = {lid: f for lid, f in recent.items() if lid in solo_leghe}
        print(f"Recupero --leagues: {sorted(solo_leghe)} (senza fixture recenti: {mancanti})")
    # 09/10: le leghe RINVIATE nelle run precedenti (e non ancora riprese) si rifanno
    # anche se oggi non hanno partite nella finestra: senza questo una lega rinviata
    # l'ultimo giorno della sua finestra resterebbe con i valori vecchi fino alla sua
    # prossima partita. Nessun fixture "corrente" (solo snapshot delle settlate).
    da_riprendere = sorted(lid for lid, n in storia.items()
                           if n > 0 and lid not in recent and (not solo_leghe or lid in solo_leghe))
    for lid in da_riprendere:
        recent[lid] = set()
    if da_riprendere:
        print(f"Leghe RINVIATE nelle run precedenti, riprese in questo giro: {da_riprendere}")
    if not recent:
        print(f"Incrementale (--days {days}): nessuna fixture recente in analytics_signals.")
        return
    print(f"Incrementale (--days {days}): {len(recent)} leghe con fixture recenti, "
          f"{sum(len(v) for v in recent.values())} fixture-target.")
    tot_target = tot_upd = 0
    leghe_ok: set[int] = set()
    di_fila = 0
    for league_id, fids in recent.items():
        if di_fila >= _RINVII_DI_FILA_MAX:
            # interruttore: 3 leghe di fila rinviate = il DB non risponde; le altre si
            # dichiarano rinviate senza altri ~20 minuti di tentativi ciascuna
            _registra_rinvio(counters, league_id, None,
                             f"non tentata: {di_fila} leghe rinviate di fila (DB non risponde)")
            continue
        prima = len(counters["rinviate"])
        try:
            n_target, updated = _enrich_league(sb, league_id, args.dry_run, counters,
                                               current_fids=fids, slice_state=slice_state)
        except RuntimeError as e:
            if not _is_retry_esauriti(e):
                raise  # errore LOGICO (colonna inesistente, vincolo, ...): propaga SUBITO
            motivo = f"lettura fallita dopo i tentativi: {e}"
            _registra_rinvio(counters, league_id, None, motivo)
            print(f"\n    RINVIATA lega {league_id}: {motivo}", flush=True)
            di_fila += 1
            continue
        if len(counters["rinviate"]) > prima:
            di_fila += 1
        else:
            di_fila = 0
            leghe_ok.add(league_id)
        tot_target += n_target
        tot_upd += updated
        print(f"  lega {league_id}: target {n_target} | aggiornate {updated}", end="\r")
    print(f"\nIncrementale: target {tot_target} | aggiornate {tot_upd} (BULK) | "
          f"falliti {counters['failed']} | leghe rinviate {len(counters['rinviate'])}")
    if counters["failed"]:
        raise SystemExit(f"ATTENZIONE: {counters['failed']} righe non scritte.")
    _esito_rinvii(sb, counters, storia, leghe_ok, len(recent), scrivi=not args.dry_run)


if __name__ == "__main__":
    # 09/10/2026: resilienza di trasporto PostgREST + riga chiara sul guasto DB persistente
    # (db_client.esegui_main_action, AUDIT_2026-10-09/fallimenti_action)
    from db_client import esegui_main_action
    esegui_main_action(main, "enrich_analytics_snapshots.py")
