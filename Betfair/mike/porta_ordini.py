"""porta_ordini.py (Mike) - la porta da cui un ordine PAPER di Mike esce verso il runner.

D1 (29/09, ordine dell'utente): «il paper deve essere lo specchio del live per
TUTTI i bot». Fino al 28/09 Mike in paper riempiva IN CASA (``execution.place``
col fill simulato sul libro del feed, lay appoggiata «abbinata» quando il best
back scendeva sotto il prezzo, bet delay contato da Mike): nessuna coda, nessun
parziale, nessun LAPSE. Da qui in poi l'ordine paper di Mike lo esegue il RUNNER
(flumine, matching simulato con bet delay, coda, parziali, LAPSE/PERSIST) sul
canale di comando ``/comando/mike`` (47331): la STESSA strada di Safe e Omega.
Cambia solo CHI esegue in paper: cosa, quanto e quando piazzare restano quelli
della Costituzione di Mike. Il live NON cambia (REST, ``omega_market``).

Come Omega (``Betfair/omega/porta_ordini.py``) si RIUSA la porta di Safe
(``safe_strategy.porta_ordini.PortaCanale``: client persistente, ack, eventi
``order`` con seq, ``da_seq``) e si aggiunge solo cio' che e' di Mike:
  * ``VistaMike``: adatta il comando costruito da ``execution._place_via_canale``
    / ``_annulla_via_canale`` (``strategy_ref``=``mike``, ``origine.tabella``=
    ``mike_trades``, ref dell'annullo ``mike-c<bet_id>``) e fissa il TIPO
    d'ordine uguale al live: FOK sui taker (``place_order_live`` di default),
    nessun FOK e ``LAPSE`` sulla lay appoggiata (``omega_market.py:735``);
  * nessun interruttore: in paper Mike passa SEMPRE dal runner. Runner giu' =
    ordine dichiarato NON eseguito (``paper_senza_runner``), mai un fill in casa.

Modulo PURO: nessun import di flumine, betfairlightweight, supabase o database.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from Betfair.safe_strategy import porta_ordini as _SPO

logger = logging.getLogger("mike.porta_ordini")

ATTORE = "mike"
STRATEGY_REF = "mike"
TABELLA_ORIGINE = "mike_trades"
PREFISSO_REF = "mike-"
FOK = _SPO.FOK
REF_MAX = _SPO.REF_MAX
MOTIVO_NON_VALIDO = "mike_comando_non_valido"
CHIAVI_COMANDO = tuple(_SPO.CHIAVI_COMANDO)

Ack = _SPO.Ack
terminale = _SPO.terminale
FASI_TERMINALI = _SPO.FASI_TERMINALI


def ref_ordine(trade_id: Any) -> str:
    """Il ref DETERMINISTICO di una riga di ``mike_trades``: lo stesso
    ``mike-t<id>`` del customerOrderRef del live (``service.execute_place``)."""
    return ("mike-t%d" % int(trade_id))[:REF_MAX]


def ref_annullo(bet_id: Any, size_reduction: Optional[float] = None) -> str:
    ref = "mike-c%s" % str(bet_id).strip()
    if size_reduction is not None:
        ref += "-%d" % int(round(float(size_reduction) * 100))
    return ref[:REF_MAX]


def adatta_comando(comando: Dict[str, Any], *, appoggiata: bool = False) -> Dict[str, Any]:
    """Il comando del modulo di Safe reso comando di MIKE. Solleva ``ValueError``
    su qualunque cosa fuori posto: chi chiama NON manda niente.

    Tipo d'ordine = quello del LIVE di Mike:
      * taker (``appoggiata`` False): si tiene cio' che ``execution`` ha gia'
        scelto: ``FILL_OR_KILL`` come ``place_order_live`` (FOK di default),
        oppure nessun FOK sotto il minimo di piazzamento, dove il motore del
        runner fa il place-and-trim come il live (``place_submin_live``);
        ``reduces_liability`` sulle chiusure;
      * lay appoggiata (``appoggiata`` True): NESSUN FOK e ``LAPSE``, come
        ``_piazza_resting_live`` -> ``place_order_live(fill_or_kill=False)``
        (``omega_market.py:735``)."""
    d = dict(comando or {})
    time_in_force = None if appoggiata else d.get("time_in_force")
    persistence = "LAPSE" if appoggiata else (d.get("persistence") or "LAPSE")
    azione = d.get("azione")
    if azione not in _SPO.AZIONI:
        raise ValueError("azione fuori protocollo: %r" % azione)
    if d.get("mode") not in _SPO.MODI:
        raise ValueError("mode fuori protocollo: %r" % d.get("mode"))
    ref = str(d.get("ref") or "")
    if azione == "cancel" and not ref.startswith(PREFISSO_REF):
        ref = ref_annullo(d.get("bet_id"), d.get("size_reduction"))
    if not ref.startswith(PREFISSO_REF) or len(ref) > REF_MAX:
        raise ValueError("ref non di Mike: %r" % ref)
    if time_in_force not in (None, FOK):
        raise ValueError("time_in_force fuori protocollo: %r" % time_in_force)
    if persistence is not None and persistence not in _SPO.PERSISTENZE:
        raise ValueError("persistence fuori protocollo: %r" % persistence)
    creato = d.get("creato_ms")
    if isinstance(creato, bool) or not isinstance(creato, (int, float)):
        raise ValueError("creato_ms non numerico: %r" % creato)
    d["ref"] = ref
    d["attore"] = ATTORE
    d["strategy_ref"] = STRATEGY_REF
    d["creato_ms"] = int(creato)
    origine = d.get("origine")
    if origine:
        if not isinstance(origine, dict):
            raise ValueError("origine non valida: %r" % origine)
        d["origine"] = {**origine, "tabella": TABELLA_ORIGINE}
    if azione == "place":
        d["time_in_force"] = time_in_force
        d["reduces_liability"] = bool(d.get("reduces_liability"))
        d["persistence"] = persistence
    else:
        d["time_in_force"] = None
        d["reduces_liability"] = False
    return {k: d.get(k) for k in CHIAVI_COMANDO}


class VistaMike:
    """La porta di Mike vista da UNA azione (stessa interfaccia della
    ``PortaCanale`` che ``safe_strategy.execution`` usa)."""

    via_canale = True
    nome = "canale_mike"

    def __init__(self, base: Any, *, appoggiata: bool = False) -> None:
        self.base = base
        self.appoggiata = bool(appoggiata)
        # D1-ter (28/09): il taker di Mike in LIVE e' un FOK anche sotto il
        # minimo (``place_submin_live(fill_or_kill=True)``): ``execution`` deve
        # decidere il piano come il live prima di mandare il comando. La lay
        # appoggiata no (``fill_or_kill=False`` in live).
        self.submin_fill_or_kill = not self.appoggiata

    @property
    def attore(self) -> str:
        return ATTORE

    @property
    def memoria(self) -> Any:
        return getattr(self.base, "memoria", None)

    def disponibile(self) -> bool:
        try:
            return bool(self.base.disponibile())
        except Exception:  # noqa: BLE001 - porta illeggibile = giu'
            return False

    def invia(self, comando: Dict[str, Any]) -> Any:
        try:
            d = adatta_comando(comando, appoggiata=self.appoggiata)
        except ValueError as ex:
            ref = str((comando or {}).get("ref") or "")
            logger.error("[mike.porta] comando NON inviato (%s): %s", ref, str(ex)[:160])
            return Ack(ref, None, False, MOTIVO_NON_VALIDO, None)
        return self.base.invia(d)

    def esiti(self, ref: str) -> Optional[Dict[str, Any]]:
        return self.base.esiti(ref)

    def attendi_esito_bet(self, bet_id: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        return self.base.attendi_esito_bet(bet_id, timeout_s)


class PortaCanaleMike(_SPO.PortaCanale):
    """La ``PortaCanale`` di Safe, identica, col nome del thread di Mike."""

    def avvia(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name="mike-porta-%s" % self.attore)
        self._thread.start()


def _crea_porta() -> PortaCanaleMike:
    return PortaCanaleMike(
        porta_ws=_SPO._porta_env(_SPO.ENV_PORTA_CALCIO, _SPO.PORTA_CALCIO),
        attore=ATTORE, sport="calcio")


_PORTA: Optional[Any] = None
_LOCK = threading.Lock()


def porta_mike(*, avvia: bool = True) -> Any:
    """La porta a comandi di Mike (una per processo). Nessun interruttore: in
    paper Mike passa sempre dal runner."""
    global _PORTA
    with _LOCK:
        p = _PORTA
        if p is None:
            p = _crea_porta()
            _PORTA = p
    if avvia and hasattr(p, "avvia"):
        p.avvia()
    return p


def porta_esistente() -> Optional[Any]:
    with _LOCK:
        return _PORTA


def installa(porta: Any) -> None:
    """Sostituisce la porta del processo (banco e test: un runner finto che
    parla il protocollo vero)."""
    global _PORTA
    with _LOCK:
        _PORTA = porta


def azzera() -> None:
    global _PORTA
    with _LOCK:
        p = _PORTA
        _PORTA = None
    if p is not None and hasattr(p, "ferma"):
        try:
            p.ferma()
        except Exception:  # noqa: BLE001
            pass


def vista(*, appoggiata: bool = False) -> VistaMike:
    """La vista per un ordine paper: taker (tipo scelto da ``execution``) o lay
    appoggiata (nessun FOK, ``LAPSE``)."""
    return VistaMike(porta_mike(), appoggiata=appoggiata)
