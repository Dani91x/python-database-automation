"""Limiti ufficiali dell'Exchange API di Betfair come DATI, con le funzioni pure di calcolo.

Comparto A, tappa T5 (``ARCHITETTURA_2026-10/05_PIANO_DI_MIGRAZIONE.md``), agente W1-A1.

Scopo: UN posto per i numeri che Betfair impone alle richieste REST e alla
sessione (``ARCHITETTURA_2026-10/02_COMPETITOR.md`` par. 3.2 e 3.3, fonti B-WEIGHT,
S-LIMITS, B-EXC, S-TMR, B-PLACE, B-IT, B-LOGIN) e le funzioni che li applicano:
peso di una richiesta, numero massimo di mercati per richiesta, suddivisione di
un elenco di mercati in blocchi che non superano 200 punti, metodi che si
contendono il tetto delle 3 richieste concorrenti per conto.

Entrate: nomi dei metodi Betfair (``listMarketBook``...) e i loro parametri come
li accetta betfairlightweight (``price_projection`` = dict di
``betfairlightweight.filters.price_projection``, ``order_projection``...).
Uscite: numeri (``Fraction`` per i pesi, int per i conteggi) e liste di blocchi.

Cosa NON fa: nessuna chiamata, nessuno stato, nessun I/O. Non applica i limiti
(lo fa ``rest.py``); i limiti delle istruzioni di ``placeOrders`` (50 sul .it,
back e lay insieme rifiutati) sono qui come dati per la porta degli ordini
(comparto C): ``rest.py`` NON blocca una mutazione per questi motivi (oggi le
rifiuta Betfair, e il piano li assegna alla porta).

Regole lette dalla documentazione ufficiale e tenute come tali:
  * peso di ``listMarketBook``: somma dei pesi della proiezione x numero di
    mercati <= 200 (``TOO_MUCH_DATA`` oltre); le due combinazioni con
    ``EX_TRADED`` hanno un peso PROPRIO (20 e 32, non 22 e 34);
  * ``EX_ALL_OFFERS`` prevale su ``EX_BEST_OFFERS`` se ci sono entrambi (doc
    PriceProjection: "EX_ALL_OFFERS trumps EX_BEST_OFFERS");
  * con ``exBestOffersOverrides.bestPricesDepth`` il peso va moltiplicato per
    (profondita' / 3) (02 par. 3.2, fonte B-WEIGHT: la riga non dice come si
    tratta la combinazione con ``EX_TRADED`` ne' le profondita' sotto 3). Scelte
    PRUDENTI dichiarate nel referto par. 9: il fattore si applica all'intero peso
    della proiezione che contiene le migliori offerte (anche alla combinazione con
    ``EX_TRADED``) e non scende MAI sotto 1 (profondita' 1-2 = peso base):
    sovrastimare il peso fa solo blocchi piu' piccoli, mai un ``TOO_MUCH_DATA``.
    La profondita' deve essere un intero >= 1 (non bool, non 2.5).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# DATI (02_COMPETITOR.md par. 3.2 / 3.3)
# ---------------------------------------------------------------------------

#: punti massimi di una richiesta di dati di mercato (TOO_MUCH_DATA oltre)
PESO_MASSIMO_RICHIESTA = 200

#: pesi di listMarketBook per proiezione (B-WEIGHT); "" = nessuna proiezione
PESI_LIST_MARKET_BOOK: Mapping[str, int] = {
    "": 2,
    "SP_AVAILABLE": 3,
    "SP_TRADED": 7,
    "EX_BEST_OFFERS": 5,
    "EX_ALL_OFFERS": 17,
    "EX_TRADED": 17,
    "EX_BEST_OFFERS+EX_TRADED": 20,
    "EX_ALL_OFFERS+EX_TRADED": 32,
}

#: pesi di listMarketCatalogue per marketProjection (le altre valgono 0)
PESI_LIST_MARKET_CATALOGUE: Mapping[str, int] = {
    "MARKET_DESCRIPTION": 1,
    "RUNNER_METADATA": 1,
}

#: peso per mercato di listMarketProfitAndLoss
PESO_LIST_MARKET_PROFIT_AND_LOSS = 4

#: richieste in coda per CONTO oltre cui Betfair risponde TOO_MANY_REQUESTS
#: (vale per i metodi di ``e_metodo_conteso``; listClearedOrders ha un meccanismo suo)
RICHIESTE_CONCORRENTI_PER_CONTO = 3

#: istruzioni (place/cancel/update/replace) al secondo oltre cui c'e' errore
ISTRUZIONI_AL_SECONDO = 1000

#: istruzioni per singola placeOrders: exchange globale / exchange italiano
ISTRUZIONI_PER_PLACE_GLOBALE = 200
ISTRUZIONI_PER_PLACE_ITALIA = 50

#: login riusciti al minuto per conto; oltre: ban dei NUOVI login per 20 minuti
LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO = 100
DURATA_BAN_LOGIN_S = 20 * 60
CODICE_BAN_LOGIN = "TEMPORARY_BAN_TOO_MANY_REQUESTS"

#: vita della sessione sull'exchange italiano (e spagnolo): 20 minuti, la
#: allunga SOLO keepAlive/login (non l'attivita' API)
VITA_SESSIONE_ITALIA_S = 20 * 60

#: endpoint di sessione dell'exchange italiano (B-LOGIN, B-IT)
URL_KEEPALIVE_ITALIA = "https://identitysso.betfair.it/api/keepAlive"
URL_LOGOUT_ITALIA = "https://identitysso.betfair.it/api/logout"
URL_CERTLOGIN_ITALIA = "https://identitysso-cert.betfair.it/api/certlogin"
#: le chiamate di betting del .it vanno all'endpoint globale (come oggi client.py:44)
URL_BETTING_JSONRPC = "https://api.betfair.com/exchange/betting/json-rpc/v1"

#: chiusura dei keep-alive HTTP inattivi lato server (B-BEST)
KEEPALIVE_HTTP_INATTIVO_S = 3 * 60

#: metodi che CAMBIANO STATO sul conto (i soldi non si ritentano)
METODI_MUTAZIONE: Tuple[str, ...] = ("placeOrders", "cancelOrders", "replaceOrders", "updateOrders")

#: metodi che si contendono il tetto delle 3 richieste concorrenti per conto
#: (listMarketBook SOLO se chiede ordini o abbinamenti)
METODI_CONTESI: Tuple[str, ...] = ("listCurrentOrders", "listMarketProfitAndLoss")


# ---------------------------------------------------------------------------
# FUNZIONI PURE
# ---------------------------------------------------------------------------
def _chiave_proiezione(price_data: Iterable[str]) -> Tuple[str, ...]:
    """Le voci della proiezione che pesano, secondo le regole ufficiali:
    ``EX_ALL_OFFERS`` prevale su ``EX_BEST_OFFERS``; le combinazioni con
    ``EX_TRADED`` hanno il loro peso. Restituisce le chiavi di
    ``PESI_LIST_MARKET_BOOK`` da sommare (vuota -> ("",))."""
    voci = {str(v).upper() for v in (price_data or ()) if v}
    chiavi: List[str] = []
    traded = "EX_TRADED" in voci
    # l'ordine dei rami E' la regola: EX_ALL_OFFERS prima, quindi prevale su EX_BEST_OFFERS
    if "EX_ALL_OFFERS" in voci:
        chiavi.append("EX_ALL_OFFERS+EX_TRADED" if traded else "EX_ALL_OFFERS")
    elif "EX_BEST_OFFERS" in voci:
        chiavi.append("EX_BEST_OFFERS+EX_TRADED" if traded else "EX_BEST_OFFERS")
    elif traded:
        chiavi.append("EX_TRADED")
    for sp in ("SP_AVAILABLE", "SP_TRADED"):
        if sp in voci:
            chiavi.append(sp)
    sconosciute = voci - {"EX_ALL_OFFERS", "EX_BEST_OFFERS", "EX_TRADED", "SP_AVAILABLE", "SP_TRADED"}
    if sconosciute:
        raise ValueError(f"proiezione di prezzo sconosciuta: {sorted(sconosciute)}")
    return tuple(chiavi) or ("",)


def peso_list_market_book(price_projection: Optional[Mapping[str, Any]] = None) -> Fraction:
    """Peso PER MERCATO di una ``listMarketBook`` con questa proiezione.

    ``price_projection`` e' il dict di ``betfairlightweight.filters.price_projection``
    (chiavi camelCase ``priceData``, ``exBestOffersOverrides``); None = nessuna
    proiezione (peso 2). Frazione esatta: con ``bestPricesDepth`` il peso puo'
    non essere intero."""
    pp = dict(price_projection or {})
    chiavi = _chiave_proiezione(pp.get("priceData") or ())
    peso = Fraction(0)
    for k in chiavi:
        base = Fraction(PESI_LIST_MARKET_BOOK[k])
        if "BEST_OFFERS" in k and "ALL_OFFERS" not in k:
            profondita = (pp.get("exBestOffersOverrides") or {}).get("bestPricesDepth")
            if profondita is not None:
                if isinstance(profondita, bool) or not isinstance(profondita, int) or profondita < 1:
                    raise ValueError(f"bestPricesDepth non valido: {profondita!r}")
                base = base * max(Fraction(1), Fraction(profondita, 3))
        peso += base
    return peso


def peso_list_market_catalogue(market_projection: Optional[Iterable[str]] = None) -> int:
    """Peso PER MERCATO di una ``listMarketCatalogue`` (solo MARKET_DESCRIPTION e
    RUNNER_METADATA pesano 1). Dato informativo: ``rest.py`` non suddivide il
    catalogo (vedi il referto: il runner chiede maxResults 1000 con
    MARKET_DESCRIPTION e Betfair lo accetta)."""
    return sum(PESI_LIST_MARKET_CATALOGUE.get(str(p).upper(), 0) for p in (market_projection or ()))


def mercati_massimi_per_richiesta(peso_per_mercato: Fraction | int) -> int:
    """Quanti mercati entrano in UNA richiesta: floor(200 / peso).

    :raises ValueError: se il peso e' <= 0 o se nemmeno UN mercato entra (>200)."""
    p = Fraction(peso_per_mercato)
    if p <= 0:
        raise ValueError(f"peso per mercato non valido: {peso_per_mercato!r}")
    n = math.floor(Fraction(PESO_MASSIMO_RICHIESTA) / p)
    if n < 1:
        raise ValueError(f"peso per mercato {p} oltre il massimo di {PESO_MASSIMO_RICHIESTA}")
    return int(n)


def blocchi_per_peso(market_ids: Sequence[str], peso_per_mercato: Fraction | int,
                     blocco_massimo: Optional[int] = None) -> List[List[str]]:
    """Divide ``market_ids`` (ordine conservato) in blocchi che non superano 200
    punti. ``blocco_massimo`` (facoltativo) stringe ancora il blocco: serve a
    riprodurre i blocchi di oggi (scanner 25, ``odds_refresh`` 20) nell'ombra."""
    n = mercati_massimi_per_richiesta(peso_per_mercato)
    if blocco_massimo is not None:
        if int(blocco_massimo) < 1:
            raise ValueError(f"blocco_massimo non valido: {blocco_massimo!r}")
        n = min(n, int(blocco_massimo))
    ids = list(market_ids)
    return [ids[i:i + n] for i in range(0, len(ids), n)]


def peso_richiesta(metodo: str, parametri: Mapping[str, Any]) -> Optional[Fraction]:
    """Peso PER MERCATO di una richiesta suddivisibile per ``market_ids``; None se il
    metodo non ha un peso per mercato (non si suddivide)."""
    if metodo == "listMarketBook":
        return peso_list_market_book(parametri.get("price_projection"))
    if metodo == "listMarketProfitAndLoss":
        return Fraction(PESO_LIST_MARKET_PROFIT_AND_LOSS)
    return None


def e_metodo_conteso(metodo: str, parametri: Mapping[str, Any]) -> bool:
    """True se la richiesta si contende il tetto delle 3 concorrenti per conto:
    listCurrentOrders, listMarketProfitAndLoss, listMarketBook CON proiezione di
    ordini o di abbinamenti (B-EXC, S-TMR)."""
    if metodo in METODI_CONTESI:
        return True
    if metodo == "listMarketBook":
        return parametri.get("order_projection") is not None or parametri.get("match_projection") is not None
    return False


def istruzioni_oltre_tetto(n_istruzioni: int, *, italia: bool = True) -> bool:
    """True se una placeOrders con ``n_istruzioni`` supera il tetto per richiesta
    (50 sul .it, 200 sul globale). Dato per la porta degli ordini (comparto C)."""
    tetto = ISTRUZIONI_PER_PLACE_ITALIA if italia else ISTRUZIONI_PER_PLACE_GLOBALE
    return int(n_istruzioni) > tetto


def tetto_login_per_processo(processi_attesi: int) -> int:
    """Quota dei 100 login al minuto del conto per UN processo se i processi che
    fanno login sono ``processi_attesi`` (divisione intera, almeno 1)."""
    p = max(1, int(processi_attesi))
    return max(1, LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO // p)
