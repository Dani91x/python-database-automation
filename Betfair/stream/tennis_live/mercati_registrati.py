"""mercati_registrati.py - TUTTI i mercati dell'evento per le partite con REC acceso (07/10).

Decisione dell'utente del 07/10 ("1) SI"): le partite tennis con la registrazione
accesa (``tennis_live_follow.record = true``) registrano TUTTI i mercati che
Betfair offre per l'evento (Set Betting, Set Winner, Total Games, Handicap, ...),
non solo il Match Odds, nello stesso ``<id>.raw.jsonl``.

COME, senza toccare cio' che ricevono i bot (vincolo del coordinatore):
  * STESSA connessione e STESSA sottoscrizione del runner tennis: lo stream
    unico ha il filtro ``market_ids`` = i Match Odds seguiti; qui si AGGIUNGONO
    gli altri mercati dei soli eventi registrati. Nessuna sottoscrizione ne'
    connessione in piu' (flumine riusa la MarketStream solo a filtro identico:
    capture, bot e stream ricevono lo STESSO elenco, calcolato UNA volta qui);
  * i bot sono gia' limitati al LORO mercato (``tennis_runner._scope_to_market``)
    e i consumer (ladder, now, ordini) leggono solo il proprio mercato
    (``capture.latest_for``): i mercati in piu' non arrivano mai alla loro logica;
  * PRIORITA': i Match Odds non escono MAI per far posto ai mercati registrati;
    se l'elenco supererebbe il tetto (``iscrizione_a_caldo.tetto_mercati``,
    sotto il limite Betfair di 200 mercati per connessione) i mercati
    registrati in eccesso restano FUORI (registrazione incompleta, dichiarata
    nel log), mai un mercato di un bot.
Il catalogo (nomi dei mercati e dei runner, che lo stream non porta) si legge
con ``listMarketCatalogue`` per evento, la stessa chiamata REST che il runner
fa gia' per il Match Odds (``tennis_runner._resolve_market``).

ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping

logger = logging.getLogger(__name__)

#: chiave in ``session.market_meta[event_id]``: lista dei mercati in piu' dell'evento
#: ([{market_id, market_type, market_name, selection_names}]). ASSENTE = mai letto
#: (o REC spento); lista VUOTA = letto, l'evento non ha altri mercati.
CHIAVE = "mercati_registrati"
TENNIS_EVENT_TYPE_ID = "2"


def catalogo_mercati_evento(trading: Any, event_id: str, escludi: str) -> List[Dict[str, Any]]:
    """Gli altri mercati dell'evento (REST ``listMarketCatalogue``), senza ``escludi``
    (il Match Odds gia' sottoscritto). Solleva in caso di errore: decide il chiamante."""
    from betfairlightweight import filters

    cat = trading.betting.list_market_catalogue(
        filter=filters.market_filter(event_ids=[str(event_id)], event_type_ids=[TENNIS_EVENT_TYPE_ID]),
        market_projection=["RUNNER_DESCRIPTION", "MARKET_DESCRIPTION"],
        sort="FIRST_TO_START", max_results=200,
    ) or []
    out: List[Dict[str, Any]] = []
    for m in cat:
        mid = str(getattr(m, "market_id", "") or "")
        if not mid or mid == str(escludi):
            continue
        desc = getattr(m, "description", None)
        out.append({
            "market_id": mid,
            "market_type": getattr(desc, "market_type", None),
            "market_name": getattr(m, "market_name", None),
            "selection_names": {str(r.selection_id): r.runner_name for r in (getattr(m, "runners", None) or [])},
        })
    out.sort(key=lambda x: x["market_id"])
    return out


def mercati_extra(meta: Mapping[str, Any]) -> List[str]:
    """I market_id in piu' di UN evento (vuoto se REC spento o catalogo non letto)."""
    return [str(x["market_id"]) for x in (meta.get(CHIAVE) or []) if x.get("market_id")]


def mercati_da_sottoscrivere(metas: Mapping[str, Mapping[str, Any]], tetto: int) -> List[str]:
    """L'elenco CANONICO (ordinato) dei mercati dello stream unico del tennis.

    Sempre TUTTI i mercati principali (Match Odds) degli eventi; poi i mercati
    registrati, evento per evento (ordine di event_id), finche' c'e' posto sotto
    ``tetto``. Un mercato registrato non toglie mai il posto a un principale."""
    principali = sorted({str(m["market_id"]) for m in metas.values() if m.get("market_id")})
    scelti = list(principali)
    visti = set(scelti)
    fuori = 0
    for ev in sorted(metas):
        for mid in mercati_extra(metas[ev]):
            if mid in visti:
                continue
            if len(scelti) >= tetto:
                fuori += 1
                continue
            scelti.append(mid)
            visti.add(mid)
    if fuori:
        logger.warning("[tennis-rec] %d mercati registrati FUORI dallo stream: tetto di %d mercati "
                       "(i Match Odds dei bot hanno la precedenza).", fuori, tetto)
    return sorted(scelti)
