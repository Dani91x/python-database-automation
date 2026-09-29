"""riserva_prezzi.py - i PREZZI DI RISERVA dei runner quando il loro stream e' muto (cantiere J2, 28/09/2026).

Ordine dell'utente (28/09): «se cade lo stream ci dovrebbe essere il pool di
backup, per le chiamate, funziona? c'e'?». Lo scanner ha il ripiego REST per
mercato (``safe_strategy/service.py::poll_books``); i runner no: a stream muto il
ladder e le protezioni (stop, bracket, green-up, chiusure di sicurezza) leggevano
l'ultimo book in memoria SENZA saperlo.

LA RISERVA (nessuna chiamata Betfair in piu', nessun processo nuovo): il feed
dello scanner che il runner GIA' legge per i punteggi (``scan_feed.shared_cache``,
canale 47336 o DB), e SOLO se lo scanner dichiara vivi i prezzi di QUEL mercato
(``flusso_prezzi.valuta``: giro dello scanner non bloccato, mercato non fra
quelli fermi). Il feed porta il MIGLIOR livello (back/lay e size) dei mercati
che lo scanner segue: MATCH_ODDS (``odds``), Correct Score (``cs``), Half Time
Score (``ht``), BTTS, Half Time result, le linee O/U seguite (``ou``). Un
mercato che non c'e' (handicap asiatico, linee non seguite...) o un handicap
diverso da 0: NESSUN prezzo (mai un prezzo inventato): chi chiama non agisce e
lo si DICE (``ultimo_esito``).

Chi usa la riserva decide cosa farne; la regola (brief J2): con i prezzi di
riserva restano attive le PROTEZIONI, nessuna posizione nuova. Al rientro dello
stream si torna ai prezzi dello stream (``stream_vivo`` torna vero al primo
battito vivo del runner).

Stato del processo: ``imposta_stato`` lo chiama il battito del runner con la
dichiarazione di ``stream_muto.SorvegliaStream`` (``interrotto``,
``mercati_fermi``). Nessun I/O qui tranne la lettura della cache del feed.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from . import flusso_prezzi as _FP

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_STATO: Dict[str, Any] = {}
#: ultimo esito della riserva per mercato (per lo stato del runner e i log)
ULTIMO_ESITO: Dict[str, str] = {}

FONTE_STREAM = "stream"
FONTE_FEED = "feed"
FONTE_NESSUNA = "nessuna"

_BLOCCO_PER_TIPO = {"CORRECT_SCORE": "cs", "HALF_TIME_SCORE": "ht", "BOTH_TEAMS_TO_SCORE": "btts",
                    "HALF_TIME": "ht_result"}
_CHIAVI_BLOCCHI = ("cs", "ht", "btts", "ht_result")


def imposta_stato(dichiarazione: Optional[Dict[str, Any]]) -> None:
    """La dichiarazione del sorvegliante dello stream del runner (battito)."""
    with _lock:
        _STATO.clear()
        if isinstance(dichiarazione, dict):
            _STATO.update(dichiarazione)


def azzera() -> None:
    with _lock:
        _STATO.clear()
        ULTIMO_ESITO.clear()


def stream_vivo(market_id: Any) -> bool:
    """Lo stream del runner serve prezzi vivi per questo mercato? Falso SOLO
    con un episodio dichiarato (``interrotto``) che riguarda il mercato (o
    tutti, se l'elenco dei mercati fermi e' vuoto). Nessuna dichiarazione =
    vivo (comportamento di prima: il segnale non si inventa)."""
    with _lock:
        if not _STATO.get("interrotto"):
            return True
        fermi = [str(m) for m in (_STATO.get("mercati_fermi") or [])]
    return bool(fermi) and str(market_id) not in fermi


def _v(obj: Any, nome: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(nome)
    try:
        return getattr(obj, nome, None)
    except Exception:  # noqa: BLE001 - property di flumine che solleva: dato assente
        return None


def _evento_e_tipo(market: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    mid = _v(market, "market_id")
    ev = _v(market, "event_id")
    mt = _v(market, "market_type")
    if ev is None or mt is None:
        md = _v(_v(market, "market_book"), "market_definition")
        ev = ev if ev is not None else _v(md, "event_id")
        mt = mt if mt is not None else _v(md, "market_type")
    return (None if mid is None else str(mid), None if ev is None else str(ev),
            None if mt is None else str(mt).upper())


def prezzi_dalla_riga(payload: Dict[str, Any], market_id: str, market_type: Optional[str],
                      selection_id: int) -> Optional[Dict[str, Any]]:
    """Il miglior livello della selezione nella riga del feed. Stessa ricerca di
    ``safe_strategy.bot_service.prices_from_row`` (MATCH_ODDS nel blocco ``odds``
    per selection_id; gli altri mercati nei blocchi col loro ``market_id``). PURA."""
    if str(payload.get("mo_market_id") or "") == str(market_id) or market_type == "MATCH_ODDS":
        for blk in (payload.get("odds") or {}).values():
            if isinstance(blk, dict) and blk.get("selection_id") is not None \
                    and int(blk["selection_id"]) == int(selection_id):
                return blk
        return None
    blocchi = [payload.get(k) for k in _CHIAVI_BLOCCHI] + list(payload.get("ou") or [])
    for blk in blocchi:
        if not isinstance(blk, dict) or str(blk.get("market_id") or "") != str(market_id):
            continue
        for sel in blk.get("selections") or []:
            if isinstance(sel, dict) and sel.get("selection_id") is not None \
                    and int(sel["selection_id"]) == int(selection_id):
                return sel
    return None


def _esito(mid: str, testo: str) -> None:
    if ULTIMO_ESITO.get(mid) != testo:
        ULTIMO_ESITO[mid] = testo
        if len(ULTIMO_ESITO) > 2000:
            ULTIMO_ESITO.clear()
        logger.warning("[riserva] mercato %s: %s", mid, testo)


def prezzi_di_riserva(market: Any, selection_id: int, handicap: float = 0.0,
                      cache: Any = None) -> Tuple[Optional[float], Optional[float]]:
    """(best back, best lay) dal feed dello scanner, SOLO con i prezzi vivi per
    lo scanner su QUEL mercato. (None, None) altrimenti, col motivo in
    ``ULTIMO_ESITO`` (e nel log al cambio)."""
    mid, ev, mt = _evento_e_tipo(market)
    if not mid:
        return None, None
    if abs(float(handicap or 0.0)) > 1e-9:
        _esito(mid, "nessuna riserva: mercato con handicap (il feed non lo porta)")
        return None, None
    if not ev:
        _esito(mid, "nessuna riserva: evento del mercato ignoto")
        return None, None
    try:
        if cache is None:
            from .scores import scan_feed as _scan_feed
            cache = _scan_feed.shared_cache()
        riga = (cache.rows_for([ev]) or {}).get(ev)
        stato_fn = getattr(cache, "scanner_stato", None)
        stato = stato_fn() if callable(stato_fn) else None
    except Exception as ex:  # noqa: BLE001 - la riserva non rompe mai il chiamante
        _esito(mid, f"nessuna riserva: feed illeggibile ({str(ex)[:80]})")
        return None, None
    payload = riga.get("payload") if isinstance(riga, dict) else None
    if not isinstance(payload, dict):
        _esito(mid, "nessuna riserva: la partita non e' nel feed dello scanner")
        return None, None
    esito = _FP.valuta(payload, stato, None, [mid])
    if not esito.vivo:
        _esito(mid, f"nessuna riserva: anche il feed dello scanner e' fermo ({esito.motivo})")
        return None, None
    if not esito.noto:
        _esito(mid, "nessuna riserva: la riga non dichiara il flusso (scanner vecchio)")
        return None, None
    blk = prezzi_dalla_riga(payload, mid, mt, int(selection_id))
    if blk is None:
        _esito(mid, "nessuna riserva: il feed non segue questo mercato/selezione "
                    f"({mt or 'tipo ignoto'})")
        return None, None
    back, lay = blk.get("back"), blk.get("lay")
    back = float(back) if isinstance(back, (int, float)) and back > 1.0 else None
    lay = float(lay) if isinstance(lay, (int, float)) and lay > 1.0 else None
    _esito(mid, "riserva attiva: prezzi dal feed dello scanner" if (back or lay)
           else "nessuna riserva: il feed non ha prezzi per la selezione")
    return back, lay


def prezzi_protezione(market: Any, selection_id: int, handicap: float,
                      dallo_stream: Callable[[Any, int, float], Tuple[Optional[float], Optional[float]]],
                      cache: Any = None) -> Tuple[Optional[float], Optional[float], str]:
    """(back, lay, fonte): lo stream del runner se vivo per il mercato,
    altrimenti la riserva dal feed (``FONTE_FEED``) o niente (``FONTE_NESSUNA``)."""
    mid = _v(market, "market_id")
    if mid is None or stream_vivo(mid):
        b, l = dallo_stream(market, selection_id, handicap)
        return b, l, FONTE_STREAM
    b, l = prezzi_di_riserva(market, selection_id, handicap, cache)
    return b, l, (FONTE_FEED if (b is not None or l is not None) else FONTE_NESSUNA)
