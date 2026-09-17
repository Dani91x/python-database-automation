# -*- coding: utf-8 -*-
"""LE OPPORTUNITA' DI MODELLO DIVENTANO PROPOSTE (17/09/2026).

Ordine dell'utente: «Le opportunita' modello (SIA CALCIO CHE TENNIS) devono
apparirmi come la card della chiusura, con tutte le informazioni e i due tasti:
PIAZZA parte l'ordine, RIFIUTA la scheda viene rifiutata.»

Qui vive SOLO la parte pura: la chiave stabile di una proposta, il corpo che
viene scritto nella coda e la "sostanza" che decide se una proposta gia' viva
va riscritta. L'orchestrazione (lettura del feed, scrittura, decadenza) sta in
``bot_service.process_opportunities``; le porte del DB in ``bot_db``.

PERCHE' UNA CODA SOLA. Non nasce nessuna tabella nuova: una proposta e' una
riga di ``safe_strategy_requests`` con ``kind='place'`` e ``status='proposed'``,
esattamente come la proposta di CHIUSURA del 14/09
(``migrations/safe_strategy_proposed_2026-09-14.sql``) e come le proposte di
uscita di Omega del 17/09 (``omega_proposte_coda_unica_2026-09-17.sql``). Il
perno e' sempre lo stesso: **il servizio drena SOLO ``status='pending'``**
(``bot_db.pending_requests``), quindi una riga 'proposed' resta ferma finche'
un essere umano non la promuove con ``safe_request_approve``. Da li' in poi il
percorso e' quello di sempre: ``_request_place`` con ``strategy='model'`` e il
``kind`` dell'opportunita'. Nessuna seconda strada verso Betfair.

LA CHIAVE. ``event_id`` + ``kind:market_type:selection_id:side``: e' la stessa
``signal_key`` che l'automatico usava per non ripetersi, quindi una proposta e
un piazzamento parlano della stessa cosa. Finche' la chiave resta uguale, una
proposta RIFIUTATA non torna: e' esattamente cosa vuol dire "rifiutare".

ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Optional

# kind della riga nella coda: una proposta di opportunita' e' un PIAZZAMENTO in
# attesa di firma, non un cash out (le proposte di chiusura usano 'cashout').
KIND_RICHIESTA = "place"

# i tipi di opportunita' che passano da qui. 'anomaly' e 'combo' NON sono
# compresi in questo giro (cecchino e combinazioni hanno un motore proprio):
# vedi CHECKPOINT_PROPOSTE_OPPORTUNITA_2026-09-17.md, divergenza dichiarata.
KINDS_PROPOSTI = ("model", "tennis")


def signal_key(kind: str, market_type: str, selection_id: Any, side: str) -> str:
    """La chiave del SEGNALE dentro la partita: identica a quella che
    ``_auto_trade_opps`` usava per non piazzare due volte la stessa cosa."""
    return f"{kind}:{market_type}:{selection_id}:{side}"


def opp_key(event_id: str, kind: str, market_type: str, selection_id: Any,
            side: str) -> str:
    """La chiave STABILE della proposta: partita + segnale.

    Stabile vuol dire che non cambia mentre il prezzo si muove: se cambiasse,
    un rifiuto durerebbe un ciclo e la scheda tornerebbe su da sola."""
    return f"{event_id}|{signal_key(kind, market_type, selection_id, side)}"


def e_proposta_di_opportunita(riga: Optional[dict[str, Any]]) -> bool:
    """Una riga della coda e' una proposta di OPPORTUNITA' (non di chiusura)?"""
    if not isinstance(riga, dict):
        return False
    corpo = riga.get("payload")
    return isinstance(corpo, dict) and bool(corpo.get("opp_key"))


# Campi che, cambiando, rendono la proposta una cosa DIVERSA da guardare.
# Il prezzo ci sta: e' il numero su cui l'utente decide. La size abbinabile no
# (si muove a ogni tick e non cambia la decisione): quella la scheda la legge
# viva dal feed, come fa la scheda della chiusura.
_SOSTANZA = ("opp_key", "market_id", "side", "price", "size", "liability",
             "mode", "p_model", "edge", "ev", "confidence", "rationale")


def sostanza(corpo: Optional[dict[str, Any]]) -> tuple:
    """Impronta della proposta: se non cambia, non si riscrive la riga.

    Write-on-change come per il feed: il DB ha un budget di IO e una proposta
    riscritta a ogni ciclo e' rumore che nessuno legge (13/09, il giorno in cui
    il database e' andato giu')."""
    c = corpo if isinstance(corpo, dict) else {}
    return tuple(c.get(k) for k in _SOSTANZA)


def corpo_proposta(*, event_id: str, event_name: Any, sport: str, kind: str,
                   opp: dict[str, Any], stake: float, liability: float,
                   mode: str, minute: Any, score: Any, now_iso: str,
                   decided_at: str, feed_updated_at: Any = None,
                   odds_ts_ms: Any = None,
                   idempotency_key: Optional[str] = None) -> dict[str, Any]:
    """Il payload della riga 'proposed'.

    Contiene DUE cose diverse e non vanno confuse:
      * il COMANDO che partira' se l'utente firma (event_id, market_id,
        market_type, selection_id, side, price, size, mode, strategy, kind):
        sono le stesse chiavi che ``_request_place`` legge da una richiesta
        manuale della UI, ne' una di piu' ne' una di meno;
      * la FOTOGRAFIA su cui il bot ha deciso (p_model, edge, ev, confidence,
        rationale, size_available, prezzo e istante della decisione), che serve
        a chi firma per capire perche', e a noi per misurare lo scostamento.

    ``price`` e' la fotografia E il prezzo del comando: come per il manuale
    della UI, l'utente guarda il prezzo VIVO un istante prima di premere e la
    scheda spegne il bottone se si e' mosso oltre la tolleranza.
    """
    corpo: dict[str, Any] = {
        # --- il comando ---
        "opp_key": opp_key(event_id, kind, str(opp.get("market_type") or ""),
                           opp.get("selection_id"), str(opp.get("side") or "").lower()),
        "strategy": "model",
        "kind": kind,
        "event_id": str(event_id),
        "event_name": event_name,
        "sport": sport,
        "market_id": opp.get("market_id"),
        "market_type": str(opp.get("market_type") or ""),
        "selection_id": opp.get("selection_id"),
        "selection_name": opp.get("selection_name"),
        "side": str(opp.get("side") or "").lower(),
        "price": opp.get("price"),
        "size": stake,
        "liability": liability,
        "mode": mode,
        "minute": minute,
        "score": score,
        # --- la fotografia su cui il bot ha deciso ---
        "signal_key": signal_key(kind, str(opp.get("market_type") or ""),
                                 opp.get("selection_id"),
                                 str(opp.get("side") or "").lower()),
        "price_at_decision": opp.get("price"),
        "size_available_at_decision": opp.get("size_available"),
        "size_available": opp.get("size_available"),
        "p_model": opp.get("p_model"),
        "p_implied": opp.get("p_implied"),
        "edge": opp.get("edge"),
        "ev": opp.get("ev"),
        "confidence": opp.get("confidence"),
        "rationale": opp.get("rationale"),
        "line": opp.get("line"),
        # eta' del PREZZO su cui si operera' (non dello scritto sul feed)
        "odds_ts_ms": odds_ts_ms,
        "feed_updated_at": feed_updated_at,
        # i due istanti che rendono misurabile la latenza vera (cert. 14/09):
        # `decided_at` NON si rinfresca, `proposed_at` e' l'ultimo aggiornamento.
        "decided_at": decided_at,
        "proposed_at": now_iso,
    }
    if opp.get("rule") is not None:
        corpo["rule"] = opp.get("rule")
    if idempotency_key:
        corpo["idempotency_key"] = idempotency_key
    return corpo
