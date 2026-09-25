"""sottoscrizione_a_caldo.py - LA risottoscrizione a caldo, UNA per calcio e tennis (25/09).

Prima c'erano due copie dello stesso meccanismo:
  * ``auto_follow.SottoscrittoreStream.applica`` (runner calcio, edc5540);
  * ``tennis_live.iscrizione_a_caldo.sottoscrivi`` (runner tennis, 72019a6),
    scritta "1:1" sulla prima quando la prima non era ancora su master.
Da qui in poi il meccanismo e' uno solo e i due runner lo chiamano; restano
diversi (per progetto) i PIANI: tetto, priorita' e chi entra/esce
(``auto_follow.PianoFollow`` per il calcio, ``iscrizione_a_caldo.pianifica``
per il tennis).

Il meccanismo (Betfair Stream API + betfairlightweight, gli stessi che flumine
usa all'avvio in ``MarketStream.run``):

* un NUOVO ``marketSubscription`` sulla STESSA connessione sostituisce il
  precedente (``BetfairStream.subscribe_to_markets``): nessuna connessione in
  piu', nessun restart del framework, blotter/posizioni/ordini vivi intatti;
* lo ``stream_id`` nuovo e' prevedibile (``new_unique_id`` = +1) ed e'
  assegnato alla MarketStream PRIMA dell'invio: i primi book della nuova
  sottoscrizione trovano gia' l'id giusto nelle strategie (``stream_ids``);
  se l'invio fallisce si rimette quello vecchio;
* i book della sottoscrizione VECCHIA sono scartati dal listener di
  betfairlightweight (``stream_unique_id`` diverso dall'id del messaggio);
  Betfair risponde alla nuova con l'immagine piena (``initialClk`` nullo);
* il filtro e' CANONICO (mercati ordinati, ``streaming_market_filter``) ed e'
  scritto sulla MarketStream (la riconnessione di flumine lo riusa) e sulle
  strategie di quello stream: capture, bot e stream hanno lo stesso
  dizionario, o flumine aprirebbe una seconda sottoscrizione;
* mai un filtro vuoto (Betfair lo leggerebbe come «tutto»), mai oltre 200
  mercati (limite Betfair per connessione); stream assente o non connesso ->
  ``NonPronto`` (si riprova al giro dopo, niente e' cambiato).

Nessun I/O verso il database. ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

#: limite Betfair: 200 mercati per connessione (accertato 09/09, config_stream)
LIMITE_BETFAIR_MERCATI = 200


class NonPronto(RuntimeError):
    """Lo stream di mercato non e' (ancora) connesso: si riprova al giro dopo."""


def stream_di_mercato(framework: Any, capture: Any = None) -> Any:
    """LA MarketStream del runner: quella della ``capture`` se data (tennis:
    la capture condivisa), altrimenti la prima MarketStream NON storica del
    framework (calcio: recorder e strategie la condividono). None se non c'e'."""
    try:
        from flumine.streams.historicalstream import HistoricalStream
        from flumine.streams.marketstream import MarketStream
    except Exception:  # noqa: BLE001
        return None
    for s in list(getattr(capture, "streams", []) or []):
        if isinstance(s, MarketStream) and not isinstance(s, HistoricalStream):
            return s
    for s in list(getattr(framework, "streams", []) or []):
        if isinstance(s, MarketStream) and not isinstance(s, HistoricalStream):
            return s
    return None


def filtro_mercati(market_ids: Iterable[str]) -> Dict[str, Any]:
    """Il filtro CANONICO (mercati ordinati, senza doppioni)."""
    from betfairlightweight.filters import streaming_market_filter

    return streaming_market_filter(market_ids=sorted({str(m) for m in market_ids}))


def mercati_dello_stream(stream: Any) -> List[str]:
    """I mercati della sottoscrizione corrente della MarketStream (ordinati)."""
    filtro = getattr(stream, "market_filter", None) or {}
    return sorted(str(m) for m in (filtro.get("marketIds") or []))


def sottoscrivi(framework: Any, stream: Any, market_ids: Iterable[str]) -> int:
    """Sostituisce la sottoscrizione della MarketStream ``stream`` con
    ``market_ids`` sulla STESSA connessione. Ritorna il nuovo ``stream_id``.

    Solleva ``ValueError`` (vuota / oltre 200) o ``NonPronto`` (stream assente
    o non connesso) SENZA aver cambiato niente."""
    ids = [str(m) for m in market_ids if m]     # l'ordine canonico lo da' filtro_mercati
    if not ids:
        raise ValueError("sottoscrizione vuota rifiutata")
    if len(set(ids)) > LIMITE_BETFAIR_MERCATI:
        raise ValueError("oltre il limite Betfair: %d mercati" % len(ids))
    if stream is None:
        raise NonPronto("nessuna MarketStream nel framework")
    bs = getattr(stream, "_stream", None)
    if bs is None or not getattr(bs, "running", False):
        raise NonPronto("stream di mercato non ancora connesso")
    filtro = filtro_mercati(ids)
    # l'id nuovo e' prevedibile (``new_unique_id`` = +1): assegnato PRIMA
    # dell'invio, cosi' i primi book della nuova sottoscrizione trovano gia' lo
    # stream_id giusto nelle strategie (``strategy.stream_ids``)
    previsto = int(getattr(bs, "_unique_id", 0) or 0) + 1
    vecchio = stream.stream_id
    stream.stream_id = previsto
    try:
        nuovo = bs.subscribe_to_markets(
            market_filter=filtro, market_data_filter=stream.market_data_filter,
            conflate_ms=stream.conflate_ms)
    except Exception:
        stream.stream_id = vecchio
        raise
    stream.stream_id = nuovo
    stream.market_filter = filtro            # la riconnessione di flumine lo riusa
    for strat in list(getattr(framework, "strategies", []) or []):
        if stream in list(getattr(strat, "streams", []) or []):
            strat.market_filter = filtro
    return int(nuovo)
