# -*- coding: utf-8 -*-
"""STATO DEL MERCATO - la guardia unica prima di ogni invio (decisione D2 del 24/09).

Decisione dell'utente (24/09/2026, D2): "i bot devono leggere lo STATO DEL
MERCATO che Betfair comunica (sospeso/aperto) invece di ritentare alla cieca;
vale per tutti i bot; dove non basta, freno crescente".

Qui c'e' UNA regola sola, scritta una volta (catalogo par.7 difetto 33: una
scelta duplicata in piu' posti diverge):

* ``mercato_operabile(stato) -> (bool, motivo)``
    - ``OPEN`` (e definizione completa)        -> (True, "OPEN"): si piazza;
    - ``SUSPENDED`` / ``CLOSED`` / ``INACTIVE`` -> (False, <stato>): NON si
      piazza; su SUSPENDED si ASPETTA la riapertura (l'intento resta al bot e
      si rivaluta alla riapertura con le condizioni della strategia di quel
      momento: mai un ordine "in ritardo" piazzato alla cieca); su CLOSED o
      INACTIVE non c'e' niente da aspettare (catalogo par.7 difetto 17:
      sospeso trattato come chiuso o chiuso come sospeso);
    - ``complete`` falso                        -> (False, "INCOMPLETO"):
      la ``marketDefinition`` dice che la definizione del mercato non e'
      completa. Scelta PRUDENTE chiesta dal coordinatore: nelle 53
      registrazioni calcio e 99 tennis del 24/09 non c'e' nessun
      ``"complete":false``, quindi sui replay non cambia niente;
    - stato NON NOTO (il bot non ha la fonte)   -> (True, "IGNOTO"): la guardia
      non puo' dire niente e NON blocca (bloccare vorrebbe dire spegnere la
      strategia, che e' intoccabile); il chiamante lo DICHIARA e vale il freno
      crescente sui rifiuti (``freno_rifiuti.FrenoRifiuti``).

Le FONTI dello stato, con le chiavi del VERO (catalogo par.7 difetto 1 e 27):
  * flumine / betfairlightweight ``MarketBook``: ``status``, ``inplay``,
    ``bet_delay``, ``complete`` (``stato_da_market_book``);
  * ``marketDefinition`` dello stream Betfair (dict): ``status``, ``inPlay``,
    ``betDelay``, ``complete`` (``stato_da_definizione``);
  * riga del feed dello scanner ``safe_strategy_scan``: ``market_status``,
    ``in_play``, ``bet_delay`` (``stato_da_riga_scan``, se la riga li porta).

``AttesaRiapertura`` tiene il "l'ho gia' detto" per chiave: il bot scrive
l'attivita' ``attesa_riapertura`` UNA volta per sospensione, non a ogni tick o
giro (lezione del freno tennis: 20.494 righe per 40 rifiuti veri).

ASCII-only nel codice; i commenti sono in italiano. Nessun IO, nessuna rete.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Hashable, Mapping, Optional, Tuple

# i codici del motivo (stabili: li leggono test, referti e UI)
OPERABILE = "OPEN"
SOSPESO = "SUSPENDED"
CHIUSO = "CLOSED"
INATTIVO = "INACTIVE"
INCOMPLETO = "INCOMPLETO"
IGNOTO = "IGNOTO"

# il tipo di attivita' che i bot scrivono (una volta per sospensione)
KIND_ATTESA = "attesa_riapertura"
# e quella della riapertura (una volta, per chiudere la finestra nel diario)
KIND_RIAPERTO = "mercato_riaperto"


@dataclass(frozen=True)
class StatoMercato:
    """Lo stato del mercato come Betfair lo comunica. ``None`` = non noto."""

    status: Optional[str] = None
    inplay: Optional[bool] = None
    bet_delay: Optional[int] = None
    complete: Optional[bool] = None
    fonte: str = "ignota"

    @property
    def noto(self) -> bool:
        return self.status is not None


STATO_IGNOTO = StatoMercato()


def _bool_o_none(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "t", "yes", "si"):
            return True
        if s in ("false", "0", "f", "no"):
            return False
        return None
    return bool(v)


def _int_o_none(v: Any) -> Optional[int]:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _status_o_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    # un Enum (es. MarketStatus) si legge dal .value, mai con str() (difetto 10)
    v = getattr(v, "value", v)
    # uno stato che non e' una stringa (un finto generico, un oggetto ignoto)
    # NON e' uno stato: e' IGNOTO. Mai inventare un OPEN, mai un SUSPENDED.
    if not isinstance(v, str):
        return None
    s = v.strip().upper()
    return s or None


def stato_da_market_book(market_book: Any) -> StatoMercato:
    """Dal ``MarketBook`` di flumine/betfairlightweight (attributi snake_case)."""
    if market_book is None:
        return STATO_IGNOTO
    return StatoMercato(
        status=_status_o_none(getattr(market_book, "status", None)),
        inplay=_bool_o_none(getattr(market_book, "inplay", None)),
        bet_delay=_int_o_none(getattr(market_book, "bet_delay", None)),
        complete=_bool_o_none(getattr(market_book, "complete", None)),
        fonte="market_book",
    )


def stato_da_mercato_flumine(market: Any) -> StatoMercato:
    """Dal ``Market`` di flumine: l'ultimo ``market_book`` che ha in memoria."""
    return stato_da_market_book(getattr(market, "market_book", None)) \
        if market is not None else STATO_IGNOTO


def stato_da_definizione(md: Optional[Mapping[str, Any]]) -> StatoMercato:
    """Dalla ``marketDefinition`` dello stream Betfair (chiavi camelCase)."""
    if not md:
        return STATO_IGNOTO
    return StatoMercato(
        status=_status_o_none(md.get("status")),
        inplay=_bool_o_none(md.get("inPlay")),
        bet_delay=_int_o_none(md.get("betDelay")),
        complete=_bool_o_none(md.get("complete")),
        fonte="market_definition",
    )


def stato_da_riga_scan(row: Optional[Mapping[str, Any]],
                       *, chiave_status: str = "market_status",
                       chiave_inplay: str = "in_play",
                       chiave_delay: str = "bet_delay") -> StatoMercato:
    """Da una riga del feed dello scanner, SE la porta. Senza la chiave dello
    stato torna ``STATO_IGNOTO`` (mai un OPEN inventato)."""
    if not row or row.get(chiave_status) is None:
        return STATO_IGNOTO
    return StatoMercato(
        status=_status_o_none(row.get(chiave_status)),
        inplay=_bool_o_none(row.get(chiave_inplay)),
        bet_delay=_int_o_none(row.get(chiave_delay)),
        complete=None,
        fonte="riga_scan",
    )


def mercato_operabile(stato: Optional[StatoMercato]) -> Tuple[bool, str]:
    """(si puo' piazzare?, motivo). Vedi la docstring del modulo per le regole."""
    if stato is None or not stato.noto:
        return True, IGNOTO
    st = stato.status
    if st == OPERABILE:
        if stato.complete is False:
            return False, INCOMPLETO
        return True, OPERABILE
    if st in (SOSPESO, CHIUSO, INATTIVO):
        return False, st
    # uno stato che Betfair non documenta: prudenza, non si piazza
    return False, str(st)


def da_aspettare(motivo: str) -> bool:
    """True se il motivo e' una sospensione (si aspetta la riapertura); False
    se il mercato e' chiuso/inattivo (non c'e' niente da aspettare)."""
    return motivo in (SOSPESO, INCOMPLETO)


class AttesaRiapertura:
    """Il diario delle attese: una riga ``attesa_riapertura`` per sospensione.

    ``annota(chiave, motivo)`` -> True solo la PRIMA volta che la chiave si
    ferma per quel motivo (il chiamante scrive allora l'attivita'); le volte
    dopo False. ``riaperto(chiave)`` -> True se la chiave era in attesa (il
    chiamante puo' scrivere ``mercato_riaperto``) e chiude la finestra, cosi'
    la sospensione successiva si annuncia di nuovo.
    """

    def __init__(self) -> None:
        self._in_attesa: Dict[Hashable, str] = {}
        self.annunci = 0

    def annota(self, chiave: Hashable, motivo: str) -> bool:
        if self._in_attesa.get(chiave) == motivo:
            return False
        self._in_attesa[chiave] = motivo
        self.annunci += 1
        return True

    def riaperto(self, chiave: Hashable) -> bool:
        return self._in_attesa.pop(chiave, None) is not None

    def in_attesa(self, chiave: Hashable) -> bool:
        return chiave in self._in_attesa

    def svuota(self) -> None:
        """Dimentica tutto (riavvio, test, scenario nuovo del banco: una
        memoria di modulo sopravvissuta fra scenari e' il difetto 37)."""
        self._in_attesa.clear()
        self.annunci = 0


def guardia(stato: Optional[StatoMercato], attese: Optional[AttesaRiapertura],
            chiave: Hashable) -> Tuple[bool, str, bool]:
    """La guardia con il suo diario, in una chiamata sola.

    Torna ``(piazza, motivo, da_annunciare)``:
      * ``piazza`` True  -> si piazza (OPEN o stato IGNOTO);
      * ``piazza`` False -> NON si piazza; ``da_annunciare`` True una volta sola
        per sospensione (scrivere ``attesa_riapertura``).
    Alla riapertura la chiave esce dall'attesa da sola.
    """
    ok, motivo = mercato_operabile(stato)
    if ok:
        if attese is not None:
            attese.riaperto(chiave)
        return True, motivo, False
    annuncia = attese.annota(chiave, motivo) if attese is not None else True
    return False, motivo, annuncia


def guardia_flumine(market: Any, attese: Optional[AttesaRiapertura],
                    emit: Any = None, **extra: Any) -> Optional[str]:
    """La guardia per i bot che vivono dentro flumine (scalper, tennis, worker).

    Lo stato si legge dal ``market.market_book`` che il bot ha GIA' in memoria
    (nessuna lettura in piu'). ``None`` = si piazza; altrimenti il motivo, e
    l'attivita' ``attesa_riapertura`` e' stata scritta con ``emit(kind, **p)``
    una volta sola per sospensione. L'ordine NON parte: al book dopo la
    strategia rivaluta da capo con le condizioni di quel momento.

    Nota: flumine ha gia' il suo controllo (``MarketValidation``: "Market is
    not open"), che boccia l'ordine DOPO che il bot l'ha costruito. Questa
    guardia lo anticipa, lo dice col motivo di Betfair e non lo conta come
    rifiuto nel freno (una sospensione non e' un rifiuto).
    """
    stato = stato_da_mercato_flumine(market)
    chiave = str(getattr(market, "market_id", "") or "")
    ok, motivo, annuncia = guardia(stato, attese, chiave)
    if ok:
        return None
    if annuncia and emit is not None:
        try:
            emit(KIND_ATTESA, market_id=chiave, motivo=motivo,
                 status=stato.status, inplay=stato.inplay,
                 bet_delay=stato.bet_delay, aspetta=da_aspettare(motivo),
                 note=("mercato non operabile: nessun ordine inviato; la "
                       "strategia rivaluta alla riapertura"), **extra)
        except Exception:  # noqa: BLE001 - la telemetria non rompe la guardia
            pass
    return motivo
