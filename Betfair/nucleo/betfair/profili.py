"""profili.py - i quattro profili di sottoscrizione dei prezzi, con i valori di OGGI.

Scopo: dare a ``flusso.GestoreFlussi`` (e a chi apre uno stream di mercato) UNA
descrizione per ogni politica di sottoscrizione che oggi e' sparsa in quattro
posti: runner calcio, runner tennis, scanner, sessione scalper. Ogni valore porta
il ``file:riga`` del codice di oggi da cui e' preso e lo stesso nome di variabile
d'ambiente con lo stesso parsing (stessi default, stessi limiti): con lo stesso
ambiente il profilo vale ESATTAMENTE quanto vale oggi la costante (provato in
``tests/test_a2_profili.py``, anche con l'ambiente cambiato, in un processo a parte).

Entrate: il nome del profilo e, facoltativo, un ambiente (``Mapping``; di serie
``os.environ`` letto AL MOMENTO della chiamata: nessuno stato di modulo).
Uscite: ``ProfiloFlusso`` (tipo del contratto, ``contratto.py``).

Cosa NON fa: non apre connessioni, non legge file, non importa il codice di oggi
(i valori sono riscritti qui con il riferimento e confrontati nei test). Non
cambia nessun valore: ``conflateMs`` e ``heartbeatMs`` restano quelli di oggi
(decisioni U-01, U-02, U-03 dell'utente: nessun cambio senza replay).

Due interpretazioni dichiarate (referto W1-A2, par. 2):
* ``ladder_levels = 0`` vuol dire «non inviato» (oggi la sessione scalper usa il
  filtro di serie di flumine, senza ``ladderLevels``): il contratto lo tipizza
  ``int``; ``filtro_dati`` qui sotto lo traduce in ``None``.
* ``riserva_connessioni = 0`` per tennis, scanner e scalper: oggi solo il calcio
  legge ``connectionsAvailable`` e tiene una riserva (A par. 1.3).
"""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional, Tuple

from .contratto import NomeProfilo, ProfiloFlusso

#: limite Betfair per sottoscrizione (``Betfair/stream/sottoscrizione_a_caldo.py:40``)
LIMITE_BETFAIR_MERCATI = 200
#: connessioni di serie per app key (``Betfair/stream/frammenti_mercato.py:86``)
LIMITE_BETFAIR_CONNESSIONI = 10

#: campi del runner calcio (``Betfair/stream/config_stream.py:90-98``)
CAMPI_CALCIO: Tuple[str, ...] = (
    "EX_ALL_OFFERS", "EX_TRADED", "EX_TRADED_VOL", "EX_LTP", "EX_MARKET_DEF",
    "SP_TRADED", "SP_PROJECTED",
)
#: campi del runner tennis (``Betfair/stream/tennis_live/tennis_runner.py:120``)
CAMPI_TENNIS: Tuple[str, ...] = (
    "EX_BEST_OFFERS", "EX_LTP", "EX_TRADED", "EX_TRADED_VOL", "EX_MARKET_DEF",
)
#: campi dello scanner (``Betfair/safe_strategy/stream.py:275``)
CAMPI_SCANSIONE: Tuple[str, ...] = ("EX_BEST_OFFERS", "EX_MARKET_DEF")
#: campi della sessione scalper = filtro di serie di flumine
#: (``flumine/strategy/strategy.py:13-23``; le strategie dello scalper non passano
#: ``market_data_filter``: ``Betfair/stream/scalper/scalper_session.py:1649-1658``)
CAMPI_SCALPER: Tuple[str, ...] = (
    "EX_ALL_OFFERS", "EX_TRADED", "EX_TRADED_VOL", "EX_LTP", "EX_MARKET_DEF",
    "SP_TRADED", "SP_PROJECTED",
)

NOMI_PROFILI: Tuple[NomeProfilo, ...] = (
    "runner_calcio", "runner_tennis", "scansione", "scalper_partita",
)


def _testo(amb: Mapping[str, str], nome: str) -> str:
    return str(amb.get(nome, "") or "").strip()


def _int_come_getenv(amb: Mapping[str, str], nome: str, default: str) -> int:
    """``int(os.getenv(nome, default))`` come le costanti di oggi: un valore
    illeggibile solleva ``ValueError`` (oggi fa cadere l'import del modulo)."""
    valore = amb.get(nome)
    return int(default if valore is None else valore)


def _env_int_limitato(amb: Mapping[str, str], nome: str, default: int,
                      lo: int, hi: int) -> int:
    """Il parsing di ``frammenti_mercato._env_int`` (``:108-115``) e di
    ``safe_strategy/stream._env_int`` (``:86-93``): vuoto/illeggibile = default,
    poi limitato a [lo, hi]."""
    raw = _testo(amb, nome)
    try:
        val = int(raw) if raw else default
    except ValueError:
        val = default
    return max(lo, min(hi, val))


def _tetto_calcio(amb: Mapping[str, str]) -> int:
    """``auto_follow.tetto_mercati`` (``Betfair/stream/auto_follow.py:124-141``):
    ``LIVE_HARD_MARKET_CAP`` (``config_stream.py:164``, di serie 180),
    sovrascritto da ``AUTO_FOLLOW_TETTO_MERCATI`` se intero, mai oltre 200."""
    base = _int_come_getenv(amb, "LIVE_HARD_MARKET_CAP", "180")
    raw = _testo(amb, "AUTO_FOLLOW_TETTO_MERCATI")
    if raw:
        try:
            base = int(raw)
        except ValueError:
            pass
    return max(1, min(base, LIMITE_BETFAIR_MERCATI))


def _tetto_tennis(amb: Mapping[str, str]) -> int:
    """``iscrizione_a_caldo.tetto_mercati`` (``tennis_live/iscrizione_a_caldo.py:88-102``):
    ``TENNIS_TETTO_MERCATI`` (anche decimale) altrimenti 180, fra 1 e 200."""
    raw = _testo(amb, "TENNIS_TETTO_MERCATI")
    base = 180
    if raw:
        try:
            base = int(float(raw))
        except ValueError:
            base = 180
    return max(1, min(base, LIMITE_BETFAIR_MERCATI))


def _calcio(amb: Mapping[str, str]) -> ProfiloFlusso:
    conflate = _int_come_getenv(amb, "LIVE_STREAM_CONFLATE_MS", "0")   # config_stream.py:87
    return ProfiloFlusso(
        nome="runner_calcio",
        campi=CAMPI_CALCIO,
        ladder_levels=_int_come_getenv(amb, "LIVE_LADDER_DEPTH", "10"),  # config_stream.py:47
        conflate_ms=conflate or None,                                    # runner.py:2960
        heartbeat_ms=None,              # non passato: flumine marketstream.py:36-42
        mercati_per_connessione=_tetto_calcio(amb),
        connessioni_max=_env_int_limitato(amb, "RUNNER_CALCIO_STREAM_CONNS", 3, 1,
                                          LIMITE_BETFAIR_CONNESSIONI),   # frammenti_mercato.py:89,412
        riserva_connessioni=_env_int_limitato(amb, "RUNNER_CALCIO_STREAM_RISERVA", 1, 0,
                                              LIMITE_BETFAIR_CONNESSIONI - 1),  # :91,414
        registra_raw=True,              # tee raw opt-in: runner.py:2963 (FrammentoMarketStream)
    )


def _tennis(amb: Mapping[str, str]) -> ProfiloFlusso:
    return ProfiloFlusso(
        nome="runner_tennis",
        campi=CAMPI_TENNIS,
        ladder_levels=_int_come_getenv(amb, "TENNIS_LADDER_DEPTH", "10"),  # tennis_runner.py:104
        # ``TENNIS_STREAM_CONFLATE_MS`` (tennis_runner.py:117) e' codice morto: la
        # capture non passa conflate_ms (tennis_runner.py:483-492). Oggi = None.
        conflate_ms=None,
        heartbeat_ms=None,
        mercati_per_connessione=_tetto_tennis(amb),
        connessioni_max=1,              # UNO stream cross-evento (tennis_runner.py:476-492)
        riserva_connessioni=0,          # il tennis non legge connectionsAvailable
        registra_raw=True,              # TennisRecMarketStream (tennis_runner.py:485)
    )


def _scansione(amb: Mapping[str, str]) -> ProfiloFlusso:
    return ProfiloFlusso(
        nome="scansione",
        campi=CAMPI_SCANSIONE,
        ladder_levels=1,                # safe_strategy/stream.py:276
        conflate_ms=1000,               # safe_strategy/stream.py:67 (_CONFLATE_MS)
        heartbeat_ms=5000,              # safe_strategy/stream.py:66 (_HEARTBEAT_MS)
        mercati_per_connessione=_env_int_limitato(
            amb, "SAFE_STRATEGY_STREAM_MARKETS_PER_CONN", 180, 1, 1000),  # :83,479-484
        connessioni_max=_env_int_limitato(amb, "SAFE_STRATEGY_STREAM_CONNS", 4, 1,
                                          LIMITE_BETFAIR_CONNESSIONI),       # :82,476
        riserva_connessioni=0,          # lo scanner non legge connectionsAvailable
        registra_raw=False,
    )


def _scalper(amb: Mapping[str, str]) -> ProfiloFlusso:  # noqa: ARG001 - nessuna env oggi
    return ProfiloFlusso(
        nome="scalper_partita",
        campi=CAMPI_SCALPER,
        ladder_levels=0,                # non inviato (filtro di serie di flumine)
        conflate_ms=None,               # default flumine (BaseStrategy conflate_ms=None)
        heartbeat_ms=None,
        mercati_per_connessione=LIMITE_BETFAIR_MERCATI,  # nessun tetto proprio: il limite Betfair
        connessioni_max=1,              # un Flumine per partita (scalper_session.py:1926)
        riserva_connessioni=0,
        registra_raw=False,             # nessun tee nella sessione scalper
    )


_COSTRUTTORI = {
    "runner_calcio": _calcio,
    "runner_tennis": _tennis,
    "scansione": _scansione,
    "scalper_partita": _scalper,
}


def profilo(nome: NomeProfilo, ambiente: Optional[Mapping[str, str]] = None) -> ProfiloFlusso:
    """Il profilo ``nome`` con l'ambiente dato (di serie ``os.environ`` adesso)."""
    try:
        costruttore = _COSTRUTTORI[nome]
    except KeyError:
        raise ValueError("profilo sconosciuto: %r (ammessi: %s)"
                         % (nome, ", ".join(NOMI_PROFILI))) from None
    return costruttore(os.environ if ambiente is None else ambiente)


def tutti(ambiente: Optional[Mapping[str, str]] = None) -> Dict[str, ProfiloFlusso]:
    """I quattro profili, per nome."""
    return {n: profilo(n, ambiente) for n in NOMI_PROFILI}


def filtro_dati(p: ProfiloFlusso) -> Dict[str, object]:
    """Il ``marketDataFilter`` del profilo, nella forma di betfairlightweight
    (``filters.streaming_market_data_filter``): lo stesso dizionario che oggi
    costruisce ogni chiamante. ``ladder_levels`` 0 = chiave assente."""
    from betfairlightweight.filters import streaming_market_data_filter

    return streaming_market_data_filter(fields=list(p.campi),
                                        ladder_levels=p.ladder_levels or None)
