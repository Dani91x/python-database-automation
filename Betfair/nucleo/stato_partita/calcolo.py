"""calcolo.py - lo stato della partita calcolato UNA volta (comparto B, ondata 1).

SCOPO
  Trasformare cio' che una fonte ha letto (stato IPS grezzo, riga dello
  scanner, risposta di API-Football, record del sidecar) in UN
  ``StatoPartita`` (``contratto.py``), con gli STESSI valori che oggi calcolano
  le funzioni sparse nel codice (scheda B par. 3.3). Nessun valore nuovo: ogni
  campo e' il risultato di una funzione di oggi, IMPORTATA (riuso, mai copia).

ENTRATE / USCITE
  * ``stato_calcio_da_grezzo``: stato IPS grezzo (dict) -> ``StatoPartita``.
    Minuto, gol, rossi, corner, gialli = ``parse_score_dict``
    (``Betfair/stream/scores/betfair_inplay.py:50``); tempo =
    ``tempo_da_stato_ips`` (``Betfair/stream/scalper/atlante_v4.py:550``);
    fase = ``mission_phase`` di Omega (``Betfair/omega/omega_engine.py:866``)
    chiamata come la chiama ``_ht_ancora_in_gioco``
    (``Betfair/omega/omega_service.py:945``: ``matchStatus``, ``kickoff=None``).
  * ``stato_calcio_da_riga``: riga dello scanner (``safe_strategy_scan``) ->
    ``StatoPartita``. Minuto, gol e rossi sono quelli che i bot LEGGONO dalla
    riga (``payload.minute``, ``payload.score_*``, ``payload.red_*``, scritti da
    ``apply_score_state`` con ``parse_score_dict`` sul record NON spogliato);
    corner e gialli da ``parse_score_dict(score_raw)`` come fa il runner.
  * ``stato_calcio_da_api_football``: entry di ``/fixtures`` ->
    ``StatoPartita`` via ``parse_fixture_response``
    (``Betfair/stream/scores/api_football.py:34``).
  * ``stato_tennis_da_grezzo``: lista di record IPS tennis -> ``StatoPartita``
    via ``parse_tennis_scores`` (``tennis_scalper/tennis_score.py:131``);
    ``chiave_tennis`` riproduce ``TennisScore.key()``.
  * ``ko_epoch_ms`` + ``KoPerMercato`` / ``KoUnico``: l'orario del calcio
    d'inizio dalla ``market_definition`` di un ``MarketBook`` vero, con la
    STESSA politica di cache di ciascuna delle 4 copie di produzione di
    ``_ko_epoch_ms`` (vedi sotto: le copie DIVERGONO nella cache, non si sceglie).
  * ``minuto_da_orologio``: il ripiego a orologio di Omega
    (``omega_engine.minute_from_clock``), importato.

LE 4 COPIE DI ``_ko_epoch_ms`` (produzione, lette riga per riga il 09/10)
  1. ``Betfair/stream/scalper/scalper_bot.py:788``  cache PER MERCATO, None non in cache
  2. ``Betfair/stream/tennis_scalper/tennis_scalper_bot.py:804`` identica alla 1
  3. ``Betfair/stream/scalper/sniper_bot.py:295``   cache PER MERCATO, None non in cache
  4. ``Betfair/stream/scalper/media_under_bot.py:1020`` cache UNICA per istanza:
     il primo valore non None vale per TUTTI i mercati dell'istanza.
  Il corpo (duck-typing su ``timestamp()``, naive -> UTC, eccezioni -> None,
  float in ms) e' lo stesso nelle 4; la politica di cache no (divergenza per
  l'utente nel referto). ``ko_epoch_ms`` e' il corpo SENZA cache (riscritto:
  e' un metodo, non si puo' importare) e il test di parita' lo confronta con
  le 4 copie vere; ``KoPerMercato`` riproduce 1-3, ``KoUnico`` riproduce 4.

COSA NON FA
  * nessuna soglia di freschezza (restano nei file di strategia, U-08);
  * nessuna rete, nessun file, nessun thread: e' puro;
  * non sceglie fra copie divergenti di oggi: le espone tutte.

Import: i moduli di oggi che tirano dentro ``betfairlightweight`` (che apre un
socket di prova IPv6 all'import, ``urllib3``) o ``config``/``.env``
(``api_client``) o ``numpy`` (``atlante_v4``) si importano DENTRO le funzioni:
importare questo modulo non apre file, socket o thread.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from Betfair.nucleo.comuni import Sport
from Betfair.nucleo.stato_partita.contratto import (Eta, FasePartita, FonteStatoPartita,
                                                    StatoPartita, TennisSet)
from Betfair.omega import omega_engine as _omega_engine
from Betfair.stream.tennis_scalper.tennis_score import TennisScore, parse_tennis_scores

logger = logging.getLogger(__name__)

#: ``mission_phase`` -> ``FasePartita``. Omega chiama l'intervallo "ht".
_FASE_DA_OMEGA: Dict[str, FasePartita] = {
    "pre": "pre", "1t": "1t", "ht": "intervallo", "2t": "2t", "finita": "finita",
}
#: Omega classifica supplementari e rigori come "2t" (``_PHASE_ET``); lo stato li
#: distingue con "supplementari" (sotto-caso di "2t": ``fase_omega`` torna indietro).
_STATI_SUPPLEMENTARI = ("extratime", "penalt")
#: ``mission_phase`` con ``kickoff=None`` non legge mai l'orologio: un istante
#: fisso evita di toccare l'ora del PC (stesso valore per costruzione).
_ORA_IRRILEVANTE = _dt.datetime(2000, 1, 1, tzinfo=_dt.timezone.utc)

Coppia = Optional[Tuple[Optional[int], Optional[int]]]


@dataclass(frozen=True)
class StatoPartitaEsteso(StatoPartita):
    """ESTENSIONE proposta del contratto (``contratto.StatoPartita`` e' fisso):
    ``fase_dedotta`` = la fase NON e' letta da uno stato del fornitore ma dedotta
    dal solo minuto con la regola di oggi (``mission_phase(status=None, ...)``),
    come fa Omega quando il punteggio arriva dal ripiego (``omega_service.py:1129-1139``
    e ``:1980``). Gli eventi ``FaseCambiata`` si emettono solo fra fasi LETTE."""

    fase_dedotta: bool = False


def fase_dedotta(stato: StatoPartita) -> bool:
    """True se la fase dello stato e' dedotta dal minuto (``StatoPartitaEsteso``)."""
    return bool(getattr(stato, "fase_dedotta", False))


def _da_ms(ms: Optional[float]) -> Optional[_dt.datetime]:
    return None if ms is None else _dt.datetime.fromtimestamp(float(ms) / 1000.0, tz=_dt.timezone.utc)


# ---------------------------------------------------------------------------
# moduli di oggi importati al primo uso (vedi docstring: import innocuo)
# ---------------------------------------------------------------------------
def _betfair_inplay() -> Any:
    from Betfair.stream.scores import betfair_inplay

    return betfair_inplay


def _api_football() -> Any:
    from Betfair.stream.scores import api_football

    return api_football


def _atlante_v4() -> Any:
    from Betfair.stream.scalper import atlante_v4

    return atlante_v4


# ---------------------------------------------------------------------------
# pezzi elementari
# ---------------------------------------------------------------------------
def coppia(casa: Optional[int], ospite: Optional[int]) -> Coppia:
    """``(casa, ospite)``; None solo se ENTRAMBI mancano (dato assente non e'
    zero). Un lato solo presente resta com'e' (nessun valore inventato)."""
    if casa is None and ospite is None:
        return None
    return (casa, ospite)


def tempo_partita(grezzo: Optional[Mapping[str, Any]], minuto: Optional[float]) -> Optional[int]:
    """1/2/None: ``atlante_v4.tempo_da_stato_ips`` invariata (Safe, Mike)."""
    return _atlante_v4().tempo_da_stato_ips(dict(grezzo) if isinstance(grezzo, Mapping) else None,
                                           minuto)


def stato_ips(grezzo: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Lo stato IPS come lo legge Omega (``_ht_ancora_in_gioco``): SOLO
    ``matchStatus`` (``parse_score_dict`` e ``tempo_da_stato_ips`` ripiegano
    anche su ``status``: divergenza dichiarata nel referto)."""
    return grezzo.get("matchStatus") if isinstance(grezzo, Mapping) else None


def fase_omega(status: Optional[str], minuto: Optional[int], *,
               ko: Optional[_dt.datetime] = None,
               adesso: Optional[_dt.datetime] = None,
               precedente: str = "pre") -> str:
    """``omega_engine.mission_phase`` invariata ('pre'|'1t'|'ht'|'2t'|'finita')."""
    return _omega_engine.mission_phase(status=status, minute=minuto, kickoff=ko,
                                       now=adesso if adesso is not None else _ORA_IRRILEVANTE,
                                       prev=precedente)


def fase_partita(status: Optional[str], minuto: Optional[int], *,
                 ko: Optional[_dt.datetime] = None,
                 adesso: Optional[_dt.datetime] = None,
                 precedente: str = "pre") -> FasePartita:
    """``FasePartita`` da ``mission_phase``: 'ht' -> 'intervallo'; un '2t' con
    stato di supplementari/rigori -> 'supplementari' (Omega lo chiama '2t')."""
    grezza = fase_omega(status, minuto, ko=ko, adesso=adesso, precedente=precedente)
    if grezza == "2t":
        norm = re.sub(r"[^a-z]", "", str(status or "").lower())
        if any(k in norm for k in _STATI_SUPPLEMENTARI):
            return "supplementari"
    return _FASE_DA_OMEGA.get(grezza, "sconosciuta")


def fase_come_omega(fase: FasePartita) -> Optional[str]:
    """Il ritorno: la fase dello stato nella lingua di ``mission_phase``."""
    inverso = {"pre": "pre", "1t": "1t", "intervallo": "ht", "2t": "2t",
               "supplementari": "2t", "finita": "finita"}
    return inverso.get(fase)


def minuto_da_orologio(ko: _dt.datetime, adesso: _dt.datetime) -> int:
    """Ripiego a orologio di Omega (``omega_engine.minute_from_clock``), invariato."""
    return _omega_engine.minute_from_clock(ko, adesso)


# ---------------------------------------------------------------------------
# calcio
# ---------------------------------------------------------------------------
def _intero_o_none(v: Any) -> Optional[int]:
    """Come i bot leggono il minuto della riga (``int(...)`` o None)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def stato_calcio_da_grezzo(event_id: str, grezzo: Optional[Mapping[str, Any]], *,
                           fonte: FonteStatoPartita, eta: Eta, prezzi_vivi: Any,
                           in_gioco: bool = False, ko_ms: Optional[int] = None) -> StatoPartita:
    """Stato calcio da uno stato IPS grezzo (fonte diretta, registrazione).

    Senza stato grezzo: tutti i campi assenti e fase 'sconosciuta'."""
    if not isinstance(grezzo, Mapping):
        return _stato_vuoto(event_id, "calcio", fonte, eta, prezzi_vivi, in_gioco, ko_ms)
    snap = _betfair_inplay().parse_score_dict(str(event_id), dict(grezzo))
    return StatoPartita(
        event_id=str(event_id), sport="calcio", in_gioco=bool(in_gioco),
        fase=fase_partita(stato_ips(grezzo), snap.minute),
        minuto=snap.minute, tempo=tempo_partita(grezzo, snap.minute),
        gol=coppia(snap.score_home, snap.score_away),
        rossi=coppia(snap.red_home, snap.red_away),
        corner=coppia(snap.corners_home, snap.corners_away),
        gialli=coppia(snap.yellow_home, snap.yellow_away),
        set_game=None, ko_ms=ko_ms, fonte=fonte, eta=eta,
        prezzi_vivi=prezzi_vivi, grezzo=grezzo,
    )


def stato_calcio_da_riga(riga: Mapping[str, Any], *, eta: Eta, prezzi_vivi: Any,
                         fonte: FonteStatoPartita = "ips_scanner",
                         ko_ms: Optional[int] = None) -> StatoPartita:
    """Stato calcio dalla riga dello scanner, con i numeri che i bot leggono.

    ``minuto``/``gol``/``rossi`` = campi del payload (``apply_score_state``);
    ``tempo`` = ``atlante_v4.tempo_da_payload`` (score_raw + minute);
    ``in_gioco`` = ``payload.inplay``; corner e gialli dallo ``score_raw``."""
    payload = riga.get("payload") if isinstance(riga.get("payload"), Mapping) else {}
    event_id = str(riga.get("event_id") or "")
    grezzo = payload.get("score_raw") if isinstance(payload.get("score_raw"), Mapping) else None
    minuto = _intero_o_none(payload.get("minute"))
    corner: Coppia = None
    gialli: Coppia = None
    if grezzo is not None:
        snap = _betfair_inplay().parse_score_dict(event_id, dict(grezzo))
        corner = coppia(snap.corners_home, snap.corners_away)
        gialli = coppia(snap.yellow_home, snap.yellow_away)
    return StatoPartita(
        event_id=event_id, sport="calcio", in_gioco=payload.get("inplay") is True,
        # come ``_ht_ancora_in_gioco``: riga senza stato ne' minuto = 'pre'
        fase=fase_partita(stato_ips(grezzo), minuto),
        minuto=minuto, tempo=_atlante_v4().tempo_da_payload(dict(payload)),
        gol=coppia(payload.get("score_home"), payload.get("score_away")),
        rossi=coppia(payload.get("red_home"), payload.get("red_away")),
        corner=corner, gialli=gialli, set_game=None, ko_ms=ko_ms, fonte=fonte, eta=eta,
        prezzi_vivi=prezzi_vivi, grezzo=grezzo if grezzo is not None else {},
    )


def stato_calcio_da_api_football(event_id: str, entry: Optional[Mapping[str, Any]], *,
                                 eta: Eta, prezzi_vivi: Any, in_gioco: bool = False,
                                 ko_ms: Optional[int] = None,
                                 adesso_s: Optional[float] = None) -> StatoPartita:
    """Stato calcio dal ripiego API-Football (``parse_fixture_response``).

    Minuto e gol = ``parse_fixture_response`` (quelli che il runner scrive in
    ``live_now``). FASE: quella che Omega calcola OGGI quando il punteggio arriva
    dal ripiego, cioe' da ``live_now`` senza stato IPS: ``mission_phase(status=None,
    minute, kickoff, now)`` (``omega_service.py:1129-1139``, il ripiego
    ``score_lookup`` torna ``status=None``; ``:1980`` chiama ``mission_phase`` con
    ``kickoff=ev.open_date`` e ``now``). Qui ``kickoff`` = ``ko_ms`` e ``now`` =
    ``adesso_s`` (contano solo senza minuto). La fase e' DEDOTTA, non letta:
    ``StatoPartitaEsteso.fase_dedotta = True``; ``status.short`` di API-Football
    (HT, FT, ...) non e' letto da nessuna regola di oggi e qui nemmeno.
    Tempo: None (nessuno lo calcola dal ripiego: Safe e Mike leggono solo la riga
    dello scanner). Rossi, corner, gialli: assenti (il ripiego non li porta)."""
    snap = None
    if isinstance(entry, Mapping):
        snap = _api_football().parse_fixture_response(str(event_id), {"response": [dict(entry)]})
    if snap is None:
        return _stato_vuoto(event_id, "calcio", "api_football", eta, prezzi_vivi, in_gioco, ko_ms)
    return StatoPartitaEsteso(
        event_id=str(event_id), sport="calcio", in_gioco=bool(in_gioco),
        fase=fase_partita(None, snap.minute, ko=_da_ms(ko_ms),
                          adesso=_da_ms(None if adesso_s is None else float(adesso_s) * 1000.0)),
        minuto=snap.minute, tempo=None,
        gol=coppia(snap.score_home, snap.score_away), rossi=None, corner=None, gialli=None,
        set_game=None, ko_ms=ko_ms, fonte="api_football", eta=eta,
        prezzi_vivi=prezzi_vivi, grezzo=entry or {}, fase_dedotta=True,
    )


def _stato_vuoto(event_id: str, sport: Sport, fonte: FonteStatoPartita, eta: Eta,
                 prezzi_vivi: Any, in_gioco: bool, ko_ms: Optional[int]) -> StatoPartita:
    return StatoPartita(
        event_id=str(event_id), sport=sport, in_gioco=bool(in_gioco), fase="sconosciuta",
        minuto=None, tempo=None, gol=None, rossi=None, corner=None, gialli=None,
        set_game=None, ko_ms=ko_ms, fonte=fonte, eta=eta, prezzi_vivi=prezzi_vivi, grezzo={},
    )


# ---------------------------------------------------------------------------
# tennis
# ---------------------------------------------------------------------------
def set_game_da_punteggio(ts: TennisScore) -> TennisSet:
    """``TennisSet`` con i valori di ``TennisScore`` TALI E QUALI (anche None:
    il contratto dichiara ``int``, ma un lato assente resta assente).
    ``pressione`` = ``TennisScore.point_pressure`` (la regola resta in
    ``tennis_score.pressures``, strategia)."""
    return TennisSet(
        sets=(ts.sets_home, ts.sets_away),
        games=(ts.games_home, ts.games_away),
        punto=(ts.point_home, ts.point_away),
        servizio=ts.server,
        pressione=bool(ts.point_pressure),
    )


def chiave_tennis(set_game: Optional[TennisSet]) -> Optional[tuple]:
    """``TennisScore.key()`` ricostruita dallo stato (rileva i cambi punto)."""
    if set_game is None:
        return None
    return (set_game.sets[0], set_game.sets[1], set_game.games[0], set_game.games[1],
            set_game.punto[0], set_game.punto[1], set_game.servizio)


def punteggio_tennis(grezzi: Optional[Sequence[Mapping[str, Any]]],
                     event_id: str) -> Optional[TennisScore]:
    """``parse_tennis_scores`` con la guardia del worker del runner tennis:
    qualunque eccezione del parser = None (registrata nel log, mai muta)."""
    try:
        return parse_tennis_scores(list(grezzi) if grezzi else None, event_id)
    except Exception as ex:  # noqa: BLE001 - come tennis_runner.py:1652: record rotto = nessun punteggio
        logger.debug("[stato-partita] punteggio tennis illeggibile %s: %s", event_id, str(ex)[:120])
        return None


def stato_tennis_da_grezzo(event_id: str, grezzi: Optional[Sequence[Mapping[str, Any]]], *,
                           fonte: FonteStatoPartita, eta: Eta, prezzi_vivi: Any,
                           in_gioco: bool = False, ko_ms: Optional[int] = None) -> StatoPartita:
    """Stato tennis: ``parse_tennis_scores(grezzi, event_id)`` invariata.

    La fase resta 'sconosciuta': ``FasePartita`` e' del calcio (estensione
    proposta nel referto); lo stato del tennis e' in ``grezzo``.

    Un record malformato (es. ``score`` stringa o lista: il parser di oggi
    solleva ``AttributeError``) vale "nessun punteggio", come nel worker del
    runner tennis, che chiama lo stesso parser dentro un try/except e lascia
    ``ts=None`` (``tennis_runner.py:1641-1653``); il motivo va nel log."""
    ts = punteggio_tennis(grezzi, event_id)
    if ts is None:
        return _stato_vuoto(event_id, "tennis", fonte, eta, prezzi_vivi, in_gioco, ko_ms)
    return StatoPartita(
        event_id=str(event_id), sport="tennis", in_gioco=bool(in_gioco), fase="sconosciuta",
        minuto=None, tempo=None, gol=None, rossi=None, corner=None, gialli=None,
        set_game=set_game_da_punteggio(ts), ko_ms=ko_ms, fonte=fonte, eta=eta,
        prezzi_vivi=prezzi_vivi, grezzo=ts.raw,
    )


def stato_tennis_da_riga(riga: Mapping[str, Any], *, eta: Eta, prezzi_vivi: Any,
                         fonte: FonteStatoPartita = "ips_scanner",
                         ko_ms: Optional[int] = None) -> StatoPartita:
    """Stato tennis dalla riga dello scanner: ``parse_tennis_scores([score_raw])``,
    come Safe tennis (``tennis_opportunity.py:45``) e il runner tennis."""
    payload = riga.get("payload") if isinstance(riga.get("payload"), Mapping) else {}
    grezzo = payload.get("score_raw")
    return stato_tennis_da_grezzo(
        str(riga.get("event_id") or ""), [grezzo] if isinstance(grezzo, Mapping) else None,
        fonte=fonte, eta=eta, prezzi_vivi=prezzi_vivi,
        in_gioco=payload.get("inplay") is True, ko_ms=ko_ms)


# ---------------------------------------------------------------------------
# calcio d'inizio (``_ko_epoch_ms``)
# ---------------------------------------------------------------------------
def ko_epoch_ms(market_book: Any) -> Optional[float]:
    """Kickoff in ms epoch (float) dalla ``market_definition`` del book, SENZA
    cache: il corpo comune delle 4 copie di produzione (vedi docstring).

    Duck-typing su ``timestamp()`` (nel processo convivono due classi datetime:
    l'isinstance fallirebbe, ``scalper_bot.py:791-795``); naive = UTC; errori -> None."""
    md = getattr(market_book, "market_definition", None)
    mt = getattr(md, "market_time", None) if md is not None else None
    if not callable(getattr(mt, "timestamp", None)):
        return None
    try:
        if getattr(mt, "tzinfo", None) is None:
            mt = mt.replace(tzinfo=_dt.timezone.utc)
        return float(mt.timestamp()) * 1000.0
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def ko_ms_intero(ko: Optional[float]) -> Optional[int]:
    """Il ``ko_ms`` del contratto (int). Arrotondato: su ``market_time`` al
    millisecondo intero e' lo stesso numero del float delle copie (test sulle
    registrazioni: 100%)."""
    return None if ko is None else int(round(ko))


class KoPerMercato:
    """Cache PER MERCATO, il None non si mette in cache (al prossimo book si
    riprova): ``scalper_bot.py:788``, ``tennis_scalper_bot.py:804``,
    ``sniper_bot.py:295``. Il primo valore di un mercato resta per sempre."""

    def __init__(self) -> None:
        self._ko_ms: Dict[str, float] = {}

    def dimentica(self, market_ids: Iterable[str]) -> None:
        """Toglie dalla cache i mercati di una partita non piu' seguita (le 4
        copie di oggi non lo fanno: la cache cresce per tutta la vita del bot;
        qui chi la usa per piu' partite la pota, vedi ``servizio.segui``)."""
        for mid in market_ids:
            self._ko_ms.pop(str(mid), None)

    def __len__(self) -> int:
        return len(self._ko_ms)

    def __call__(self, market_book: Any) -> Optional[float]:
        mid = market_book.market_id
        cached = self._ko_ms.get(mid)
        if cached is not None:
            return cached
        ko = ko_epoch_ms(market_book)
        if ko is not None:
            self._ko_ms[mid] = ko
        return ko


class KoUnico:
    """Cache UNICA per istanza (``media_under_bot.py:1020``): il primo valore
    non None vale per ogni mercato successivo, qualunque sia."""

    def __init__(self) -> None:
        self._ko_ms: Optional[float] = None

    def __call__(self, market_book: Any) -> Optional[float]:
        if self._ko_ms is not None:
            return self._ko_ms
        self._ko_ms = ko_epoch_ms(market_book)
        return self._ko_ms
