"""Caricamento del Replay Tennis su Supabase (service_role), IDEMPOTENTE.

Regola: una partita si puo' caricare quante volte si vuole, mai righe doppie.
  * evento e mercati: upsert sulle chiavi (``event_id``; ``event_id,market_id``);
  * snapshot: per OGNI mercato portato dal caricamento, delete di quel mercato
    dell'evento + insert (un import che porta il SET_BETTING non cancella il
    MATCH_ODDS caricato prima da un'altra cartella);
  * punteggio: delete+insert dell'evento SOLO se il caricamento porta un
    punteggio (una cartella senza sidecar non cancella quello gia' caricato);
  * conteggi dell'evento ricalcolati dai mercati che stanno DAVVERO nel DB.
Le funzioni di scrittura a blocchi sono quelle del calcio (``db.delete_event_rows``,
``db.insert_rows_resilient``: delete per PK a blocchi, insert che si riduce sul
57014), sulle tabelle del TENNIS: nessuna riga tennis nelle tabelle del calcio.

Lock per evento nello stesso processo (come ``uploader._event_lock``): import a
mano e caricamento a fine partita del runner non si sovrappongono sulla stessa
partita nello stesso processo.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client

from .. import db
from .convertitore import ReplayTennis

logger = logging.getLogger(__name__)

T_EVENTI = "tennis_replay_eventi"
T_MERCATI = "tennis_replay_mercati"
T_SNAPSHOT = "tennis_replay_snapshots"
T_PUNTEGGIO = "tennis_replay_punteggio"

_GUARDIA = threading.Lock()
_LOCKS: Dict[str, threading.Lock] = {}


def _lock(event_id: str) -> threading.Lock:
    with _GUARDIA:
        lk = _LOCKS.get(event_id)
        if lk is None:
            lk = threading.Lock()
            _LOCKS[event_id] = lk
        return lk


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def carica_replay(rt: ReplayTennis, *, fonte: str = "import",
                  raw_files: Optional[List[str]] = None, raw_bytes: Optional[int] = None) -> Dict[str, Any]:
    """Scrive una partita convertita. Ritorna il riepilogo (conteggi nel DB)."""
    if fonte not in ("import", "runner"):
        raise ValueError(f"fonte non valida: {fonte}")
    ev = str(rt.evento["event_id"])
    with _lock(ev):
        return _carica(rt, ev, fonte, raw_files or [], raw_bytes)


def _nomi_migliori(sb: Any, rt: ReplayTennis, ev: str) -> Dict[str, Any]:
    """I nomi da scrivere per un evento, a confronto con quelli gia' nel DB.

    08/10 (cantiere 14): al reimport un nome gia' nel DB si SOSTITUISCE solo se la nuova
    fonte e' migliore (catalogo > marketDefinition/evento > IPS troncato > ``#id``); a
    parita' o con fonte peggiore resta quello nel DB (un reimport da un PC senza
    ``_names.json`` non fa tornare «Marcelo Tomas Barrios V» al posto del nome intero).
    Con gli stessi dati in ingresso l'esito e' identico a prima (idempotente).

    Ritorna ``{"mercati": righe da scrivere (selezioni col nome migliore),
    "giocatori": {player1_name/player2_name da scrivere}, "fonti": nomi_fonte finale,
    "diagnostica_db": diagnostica gia' nel DB}``. Sola lettura."""
    from .convertitore import RANGO_NOME_FONTE, RANGO_NOME_SENZA_FONTE, migliora_selezioni

    # mercati: selezioni gia' nel DB per questo evento
    gia = {str(r["market_id"]): r.get("selections")
           for r in (sb.table(T_MERCATI).select("market_id,selections").eq("event_id", ev).execute().data or [])}
    mercati = [dict(m, event_id=ev, selections=migliora_selezioni(gia.get(m["market_id"]), m["selections"]))
               for m in rt.mercati]
    # evento: nomi dei due giocatori e loro fonte
    riga = (sb.table(T_EVENTI).select("player1_name,player2_name,diagnostica").eq("event_id", ev)
            .limit(1).execute().data or [{}])[0]
    diag_db = riga.get("diagnostica") if isinstance(riga.get("diagnostica"), dict) else {}
    fonti_db = (diag_db or {}).get("nomi_fonte") or {}
    fonti_nuove = (rt.diagnostica or {}).get("nomi_fonte") or {}
    giocatori: Dict[str, str] = {}
    fonti: Dict[str, str] = {}
    for k in ("player1_name", "player2_name"):
        nuovo, vecchio = rt.evento.get(k), riga.get(k)
        r_nuovo = RANGO_NOME_FONTE.get(fonti_nuove.get(k, ""), RANGO_NOME_SENZA_FONTE) if nuovo else -1
        r_vecchio = RANGO_NOME_FONTE.get(fonti_db.get(k, ""), RANGO_NOME_SENZA_FONTE) if vecchio else -1
        if nuovo and r_nuovo >= r_vecchio:
            giocatori[k] = nuovo
            if fonti_nuove.get(k):
                fonti[k] = fonti_nuove[k]
        elif vecchio and fonti_db.get(k):   # resta il nome gia' nel DB, con la sua fonte
            fonti[k] = fonti_db[k]
    return {"mercati": mercati, "giocatori": giocatori, "fonti": fonti, "diagnostica_db": diag_db or {}}


def aggiorna_nomi(rt: ReplayTennis) -> Dict[str, Any]:
    """Aggiorna SOLO i nomi di una partita gia' caricata (08/10, cantiere 14).

    Reimport «leggero» per quando compare una fonte migliore dei nomi (``_names.json``,
    catalogo nel DB): UPDATE delle sole ``selections`` dei mercati GIA' nel DB e dei due
    nomi dei giocatori (+ ``diagnostica.nomi_fonte``). Snapshot, punteggio, conteggi e
    mercati mai toccati; un mercato non ancora nel DB non viene creato. Regola del
    nome migliore come in ``_nomi_migliori``. Partita non caricata = non fa nulla."""
    ev = str(rt.evento["event_id"])
    with _lock(ev):
        sb = get_supabase_client()
        if not (sb.table(T_EVENTI).select("event_id").eq("event_id", ev).limit(1).execute().data or []):
            return {"event_id": ev, "aggiornato": False,
                    "motivo": "partita non caricata: serve l'import completo"}
        n = _nomi_migliori(sb, rt, ev)
        nel_db = {str(r["market_id"]) for r in
                  (sb.table(T_MERCATI).select("market_id").eq("event_id", ev).execute().data or [])}
        scritti = 0
        for m in n["mercati"]:
            if m["market_id"] in nel_db:
                db._exec_retry(sb.table(T_MERCATI).update({"selections": m["selections"]})
                               .eq("event_id", ev).eq("market_id", m["market_id"]))
                scritti += 1
        campi: Dict[str, Any] = dict(n["giocatori"])
        campi["diagnostica"] = dict(n["diagnostica_db"], nomi_fonte=n["fonti"])
        campi["updated_at"] = _ora()
        db._exec_retry(sb.table(T_EVENTI).update(campi).eq("event_id", ev))
        riepilogo = {"event_id": ev, "aggiornato": True, "mercati_aggiornati": scritti,
                     "giocatori": n["giocatori"], "nomi_fonte": n["fonti"]}
        logger.info("[replay-tennis] %s nomi aggiornati: %s", ev, riepilogo)
        return riepilogo


def _carica(rt: ReplayTennis, ev: str, fonte: str, raw_files: List[str],
            raw_bytes: Optional[int]) -> Dict[str, Any]:
    sb = get_supabase_client()
    nomi = _nomi_migliori(sb, rt, ev)
    # 1) evento PRIMA dei figli (chiavi esterne); anagrafica vuota non sovrascrive
    riga_ev: Dict[str, Any] = {"event_id": ev, "fonte": fonte, "valuta": "GBP",
                               "raw_files": raw_files, "raw_bytes": raw_bytes,
                               "diagnostica": dict(rt.diagnostica or {}, nomi_fonte=nomi["fonti"]),
                               "updated_at": _ora()}
    for k in ("competition_name", "open_date"):
        if rt.evento.get(k):
            riga_ev[k] = rt.evento[k]
    riga_ev.update(nomi["giocatori"])   # solo se la fonte nuova non e' peggiore di quella nel DB
    db._exec_retry(sb.table(T_EVENTI).upsert(riga_ev, on_conflict="event_id"))
    righe_mercati = nomi["mercati"]

    # 2) catalogo dei mercati portati da questo caricamento
    if righe_mercati:
        db._exec_retry(sb.table(T_MERCATI).upsert(righe_mercati, on_conflict="event_id,market_id"))

    # 3) snapshot, mercato per mercato
    n_snap = 0
    for m in rt.mercati:
        mid = m["market_id"]
        righe = [r for r in rt.snapshot if r["market_id"] == mid]
        db.delete_event_rows(T_SNAPSHOT, ev, market_id=mid)
        n_snap += db.insert_rows_resilient(T_SNAPSHOT, righe)

    # 4) punteggio (solo se portato)
    n_score: Optional[int] = None
    if rt.punteggio:
        db.delete_event_rows(T_PUNTEGGIO, ev)
        n_score = db.insert_rows_resilient(T_PUNTEGGIO, rt.punteggio)

    # 5) conteggi dell'evento dai mercati nel DB (anche quelli di import precedenti)
    nel_db = (sb.table(T_MERCATI).select("market_id,n_updates,ts_min,ts_max")
              .eq("event_id", ev).execute().data or [])
    agg: Dict[str, Any] = {
        "n_markets": len(nel_db),
        "n_snapshots": sum(int(r.get("n_updates") or 0) for r in nel_db),
        "ts_min": min((r["ts_min"] for r in nel_db if r.get("ts_min")), default=None),
        "ts_max": max((r["ts_max"] for r in nel_db if r.get("ts_max")), default=None),
        "updated_at": _ora(),
    }
    if n_score is not None:
        agg["n_score"] = n_score
    db._exec_retry(sb.table(T_EVENTI).update(agg).eq("event_id", ev))
    riepilogo = {"event_id": ev, "fonte": fonte, "snapshot_scritti": n_snap,
                 "punteggi_scritti": n_score or 0, **{k: agg[k] for k in ("n_markets", "n_snapshots")}}
    logger.info("[replay-tennis] %s caricato: %s", ev, riepilogo)
    return riepilogo
