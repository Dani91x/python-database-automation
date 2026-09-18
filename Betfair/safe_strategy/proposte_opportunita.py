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

import math
from typing import Any, Optional

from Betfair.safe_strategy import exits as _XE

# kind della riga nella coda: una proposta di opportunita' e' un PIAZZAMENTO in
# attesa di firma, non un cash out (le proposte di chiusura usano 'cashout').
KIND_RICHIESTA = "place"

# i tipi di opportunita' che passano da qui.
# 18/09 — ORDINE DELL'UTENTE: «si, convertili a proposte e falli finire come
# proposte sia tennis che calcio»: 'anomaly' e 'combo' sono comprese da oggi
# (vedi CHECKPOINT_COMBOS_ANOMALIE_PROPOSTE_2026-09-18.md). 'anomaly' passa da
# ``_proponi_opps`` (una gamba sola, stessa forma del modello); 'combo' ha un
# corpo diverso (``corpo_proposta_combo``, N gambe) perche' non esiste un solo
# market_id/selection_id/side da mettere in cima al payload.
KINDS_PROPOSTI = ("model", "tennis", "anomaly", "combo")


def signal_key(kind: str, market_type: str, selection_id: Any, side: str) -> str:
    """La chiave del SEGNALE dentro la partita: identica a quella che
    ``_auto_trade_opps`` usava per non piazzare due volte la stessa cosa."""
    return f"{kind}:{market_type}:{selection_id}:{side}"


def opp_key(event_id: str, kind: str, market_type: str, selection_id: Any,
            side: str) -> str:
    """La chiave STABILE della proposta: partita + segnale.

    Stabile vuol dire che non cambia mentre il prezzo si muove: se cambiasse,
    un rifiuto durerebbe un ciclo e la scheda tornerebbe su da sola.

    18/09 — usata anche per le ANOMALIE (kind='anomaly'): a differenza della
    chiave interna del cecchino di ieri (``anomaly:{mt}:{sid}:{side}:{epoch}``,
    col timestamp per il dedupe di un piazzamento immediato), qui NON c'e' il
    tempo. E' la stessa scelta del modello: senza tempo nella chiave, RIFIUTA
    tiene finche' la stessa selezione/lato non genera un'altra anomalia; CON
    il tempo, il rifiuto durerebbe un tick (stesso reperto del test di
    falsificazione qui sotto)."""
    return f"{event_id}|{signal_key(kind, market_type, selection_id, side)}"


def combo_key(event_id: str, cid: str) -> str:
    """La chiave STABILE di una proposta COMBO: partita + identificativo della
    combinazione. ``cid`` e' lo stesso hash stabile che l'automatico di ieri
    usava per non ripiazzare due volte la stessa combo (hash di
    (market_id, selection_id, side) di ogni gamba, MAI del prezzo): una combo
    e' definita dalle sue gambe, non dal prezzo del momento."""
    return f"{event_id}|combo:{cid}"


def e_proposta_di_opportunita(riga: Optional[dict[str, Any]]) -> bool:
    """Una riga della coda e' una proposta di OPPORTUNITA' (non di chiusura)?"""
    if not isinstance(riga, dict):
        return False
    corpo = riga.get("payload")
    return isinstance(corpo, dict) and bool(corpo.get("opp_key"))


def e_proposta_combo(riga: Optional[dict[str, Any]]) -> bool:
    """Una proposta di opportunita' che e' una COMBO (N gambe), non una gamba
    sola. La card ne ha bisogno per decidere se mostrare la lista delle gambe
    o i campi singoli di sempre."""
    if not e_proposta_di_opportunita(riga):
        return False
    corpo = (riga or {}).get("payload") or {}
    legs = corpo.get("legs")
    return str(corpo.get("kind") or "") == "combo" and isinstance(legs, list) and len(legs) >= 2


# Campi che, cambiando, rendono la proposta una cosa DIVERSA da guardare.
# Il prezzo ci sta: e' il numero su cui l'utente decide. La size abbinabile no
# (si muove a ogni tick e non cambia la decisione): quella la scheda la legge
# viva dal feed, come fa la scheda della chiusura.
# 18/09 — ``legs`` per le COMBO: il confronto per uguaglianza fra liste di
# dict funziona (Python confronta elemento per elemento), quindi la stessa
# funzione serve sia per una gamba sola (``legs`` assente, None == None) sia
# per N gambe (basta che UNA sola cambi prezzo/size perche' la proposta si
# riscriva).
_SOSTANZA = ("opp_key", "market_id", "side", "price", "size", "liability",
             "mode", "p_model", "edge", "ev", "confidence", "rationale", "legs")


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


def corpo_proposta_combo(*, event_id: str, event_name: Any, sport: str, cid: str,
                         combo: dict[str, Any], legs: list[dict[str, Any]],
                         mode: str, minute: Any, score: Any, now_iso: str,
                         decided_at: str, feed_updated_at: Any = None) -> dict[str, Any]:
    """Il payload di una proposta COMBO (18/09): stessa coda, stesso 'place',
    ma il COMANDO non e' una gamba sola: e' un elenco. ``legs`` e' gia'
    calcolato dal chiamante (stake per gamba scalati sul totale voluto, come
    faceva ``_auto_trade_combos``) — qui si scrive soltanto il corpo.

    Ogni elemento di ``legs`` porta le chiavi che ``_request_place`` rilegge
    all'approvazione: market_id, market_type, selection_id, selection_name,
    side, price, size, liability. NESSUN market_id/selection_id/side in cima
    al payload (a differenza di una proposta a una gamba): non esiste un solo
    valore da mettere li', e mettercene uno a caso (es. della prima gamba)
    farebbe leggere una card che approva mezza combo."""
    liability_totale = round(sum(float(l.get("liability") or 0.0) for l in legs), 2)
    size_totale = round(sum(float(l.get("size") or 0.0) for l in legs), 2)
    corpo: dict[str, Any] = {
        "opp_key": combo_key(event_id, cid),
        "strategy": "model",
        "kind": "combo",
        "event_id": str(event_id),
        "event_name": event_name,
        "sport": sport,
        "combo_id": cid,
        "legs": [dict(l) for l in legs],
        "size": size_totale,
        "liability": liability_totale,
        "mode": mode,
        "minute": minute,
        "score": score,
        "signal_key": f"combo:{cid}",
        "decided_at": decided_at,
        "proposed_at": now_iso,
        "p_model": combo.get("p_model"),
        "p_implied": combo.get("p_implied"),
        "edge": combo.get("edge"),
        "ev": combo.get("ev"),
        "confidence": combo.get("confidence"),
        "rationale": combo.get("rationale"),
        "feed_updated_at": feed_updated_at,
    }
    return corpo


# Scostamento massimo del prezzo dalla fotografia oltre il quale una proposta
# NON si approva piu': stessa idea (e la stessa soglia di default, 2%) usata
# dalla scheda della CHIUSURA (frontend, ``controlRoomProposte.SLIPPAGE_PCT_
# DEFAULT``). Per COMBO e ANOMALIE serve anche qui, lato server, perche'
# all'approvazione non c'e' piu' un motore che rivaluta la condizione: si
# ricontrolla solo che il prezzo non si sia mosso troppo dal momento della
# proposta. Per MODELLO e TENNIS non si tocca (nessuna soglia nuova su cio'
# che era gia' convertito ieri: cambia solo chi preme il grilletto).
SLIPPAGE_PCT_DEFAULT = 2.0


def prezzo_fuori_tolleranza(prezzo_decisione: Optional[float], prezzo_attuale: Optional[float],
                            side: str, soglia_pct: float = SLIPPAGE_PCT_DEFAULT) -> bool:
    """Il prezzo si e' mosso oltre la tolleranza dalla fotografia su cui il
    bot ha deciso? Prezzi mancanti o non validi -> SEMPRE fuori tolleranza
    (fail-closed: non si approva al buio). Il verso conta: un BACK che sale di
    prezzo (quota migliore per chi punta) e' contro chi ha proposto un back a
    un prezzo piu' basso; un LAY che scende (quota migliore per chi banca) e'
    contro chi ha proposto un lay a un prezzo piu' alto — qui pero' e'
    un'APERTURA (non una chiusura): peggiora chi acquista, quindi la direzione
    "contro" e' l'opposto di quella della chiusura in ``controlRoomProposte``.
    Si giudica solo l'AMPIEZZA dello scostamento in percentuale, non il verso:
    un prezzo aperto oltre soglia in qualunque direzione non e' piu' quello su
    cui l'utente ha deciso.

    ORDINE DEL COORDINATORE (18/09, 3o giro) — FAIL-CLOSED anche su valori NON
    FINITI. Reperto: ``nan`` supera ``isinstance``+``<=1.0`` perche' per IEEE
    754 OGNI confronto con ``nan`` e' falso (compreso ``nan<=1.0``), quindi
    passava indenne e la funzione tornava ``False`` (approvabile) su un
    prezzo nan — riprodotto dal coordinatore con
    ``prezzo_fuori_tolleranza(3.0, nan, 'back')``. Anche ``+inf`` come
    DECISIONE sfuggiva (``+inf<=1.0`` e' falso, e poi ``abs(x-inf)/inf`` da'
    ``nan``, mai ``> soglia``). ``math.isfinite()`` esclude nan e i due
    infiniti in un colpo solo, senza distinguere quale forma di "non finito"
    sia: e' una guardia di sicurezza nella direzione sicura (rifiuta di piu',
    mai di meno), non una soglia di strategia."""
    if not isinstance(prezzo_decisione, (int, float)) or isinstance(prezzo_decisione, bool) \
            or not math.isfinite(prezzo_decisione) or prezzo_decisione <= 1.0:
        return True
    if not isinstance(prezzo_attuale, (int, float)) or isinstance(prezzo_attuale, bool) \
            or not math.isfinite(prezzo_attuale) or prezzo_attuale <= 1.0:
        return True
    if side not in ("back", "lay"):
        return True
    scostamento_pct = abs(prezzo_attuale - prezzo_decisione) / prezzo_decisione * 100.0
    return scostamento_pct > soglia_pct


# ===========================================================================
# IL PREZZO CHE L'UTENTE VEDE (18/09/2026) — ORDINE DELL'UTENTE:
# «il prezzo può muoversi, io devo vedere la tab aggiornata e quando clicco
# prendiamo QUEL NUMERO CHE VEDO.»
#
# Non e' piu' la fotografia congelata al momento della proposta a decidere il
# prezzo dell'ordine: e' il numero che la scheda mostrava nell'istante del
# clic (``price_visto``/``legs_prices_visti``, scritti da
# ``safe_request_approve`` nel payload della richiesta approvata — vedi
# ``migrations/safe_request_approve_prezzo_visto_2026-09-18.sql``). Qui vive
# SOLO la parte pura: validare che il prezzo visto sia un numero vero, e che
# il clic non sia troppo vecchio per fidarsene.
# ===========================================================================

# Eta' massima del clic (secondi) oltre la quale il prezzo visto non e' piu'
# affidabile: STESSA soglia di freschezza gia' in uso su tutta la piattaforma
# per le quote (``exits.FEED_FRESH_S`` lato server, ``FEED_ROW_STALE_MS``
# lato frontend, `20_000` ms — vedi ``frontend/src/lib/safeBot.ts``): non e'
# un numero nuovo, e' lo stesso limite gia' certificato altrove.
CLICK_MAX_AGE_S = _XE.FEED_FRESH_S


def prezzo_visto_valido(v: Any) -> Optional[float]:
    """Il valore che la scheda dichiara di aver mostrato all'utente, se e'
    un numero VERO (finito, non bool, > 1.0). ``None`` se non lo e' —
    fail-closed: un ``price_visto`` illeggibile non diventa MAI il prezzo
    dell'ordine."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    fv = float(v)
    if not math.isfinite(fv) or fv <= 1.0:
        return None
    return fv


def clic_troppo_vecchio(price_visto_at: Any, now_ts: float,
                        max_age_s: float = CLICK_MAX_AGE_S) -> bool:
    """Il clic su PIAZZA e' troppo vecchio per fidarsi del prezzo che porta?

    Fail-closed: un istante assente o illeggibile (``exits.parse_ts`` non lo
    capisce) conta come "troppo vecchio", non come "sconosciuto quindi via
    libera". Un istante nel FUTURO oltre un piccolo margine (orologi non
    perfettamente sincronizzati fra client e server) e' trattato allo stesso
    modo: non e' un clic di cui fidarsi."""
    ts = _XE.parse_ts(price_visto_at)
    if ts is None:
        return True
    eta = now_ts - ts
    if eta > max_age_s:
        return True
    if eta < -5.0:
        return True
    return False


def slippage_pct_effettivo(payload: dict[str, Any]) -> float:
    """Lo slippage da usare per QUESTA approvazione: quello che l'utente ha
    impostato a video (``payload.slippage_pct``, salvato da
    ``safe_request_approve`` se il client lo manda) se e' un numero valido,
    altrimenti ``SLIPPAGE_PCT_DEFAULT``. Un valore sporco non azzera la
    guardia: ripiega sul default, non su "nessun limite"."""
    raw = payload.get("slippage_pct") if isinstance(payload, dict) else None
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return SLIPPAGE_PCT_DEFAULT
    fv = float(raw)
    if not math.isfinite(fv) or fv <= 0:
        return SLIPPAGE_PCT_DEFAULT
    return fv
