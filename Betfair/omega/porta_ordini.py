"""porta_ordini.py (Omega) - la PORTA da cui un ordine di Omega esce verso Betfair.

Decisione dell'utente (24/09): la strada UNICA verso gli ordini e' il runner
dello sport con flumine nello stesso processo; il bot gli parla sul canale di
comando ``/comando/omega`` (47331), il DB resta diario e ripiego.

PERCHE' QUI E NON UN MODULO CONDIVISO IN ``Betfair/stream`` (F6, 24/09).
La porta di Safe (``Betfair/safe_strategy/porta_ordini.py``) ha gia' tutto il
generico: ``Ack``, ``MemoriaComandi`` (seq/dedup/buchi), ``PortaCanale`` (client
persistente, ``da_seq`` alla riconnessione). Spostarla in ``Betfair/stream``
voleva dire toccare Safe: i suoi test sostituiscono variabili del MODULO
(``PO.MAX_ETA_MS``, ``PO._connetti_ws``) che ``PortaCanale`` legge per nome, e
``costruisci_comando`` scrive ``strategy_ref="safe"`` e la tabella
``safe_strategy_trades`` fisse. Qui si RIUSANO quelle classi cosi' come sono
(nessuna riga di Safe cambia) e si aggiunge solo cio' che e' di Omega:

* l'interruttore ``OMEGA_ORDINI_VIA_CANALE`` (SPENTO di serie: spento
  ``porta_omega`` torna ``None`` e ``omega_service`` fa cio' che fa oggi);
* ``VistaOmega``: la porta vista da UNA azione di Omega. I punti di invio di
  ``safe_strategy.execution`` (``_place_via_canale``, ``_annulla_via_canale``,
  gia' usati da Safe) costruiscono il comando col modulo di Safe; la vista lo
  ADATTA prima che esca: ``strategy_ref`` = ``omega`` (il motore del runner
  rifiuta un ``strategy_ref`` diverso dall'attore), ``origine.tabella`` =
  ``omega_trades``, ref dell'annullo ``omega-c<bet_id>``, e le due chiavi
  dell'estensione del protocollo che Omega usa: ``time_in_force``
  (``FILL_OR_KILL`` dove oggi Omega usa il FOK) e ``reduces_liability`` (True
  sulle chiusure). Cambia il TRASPORTO, mai cosa/quanto/quando si piazza.

Regole (ognuna inchiodata da un test in
``tests/test_porta_ordini_omega_f6_2026_09_24.py``): ref deterministico dalla
riga (``omega-t<id>``); ``mode`` sempre quello della riga; un comando che non si
riesce ad adattare NON esce (rifiuto locale col motivo, mai un invio "per
sicurezza"); tutte e sole le chiavi di ``CHIAVI_COMANDO``.

Modulo PURO: nessun import di flumine, betfairlightweight, supabase o database.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from Betfair.safe_strategy import porta_ordini as _SPO

logger = logging.getLogger("omega.porta_ordini")

# ------------------------------------------------------------------ costanti
ENV_CANALE = "OMEGA_ORDINI_VIA_CANALE"
ATTORE = "omega"
STRATEGY_REF = "omega"
TABELLA_ORIGINE = "omega_trades"
PREFISSO_REF = "omega-"
FOK = "FILL_OR_KILL"
REF_MAX = _SPO.REF_MAX
MOTIVO_REF_GIA_VISTO = _SPO.MOTIVO_REF_GIA_VISTO
#: rifiuto LOCALE: il comando non e' adattabile, quindi non e' mai uscito
MOTIVO_NON_VALIDO = "omega_comando_non_valido"
#: le chiavi del comando di Omega: quelle di Safe piu' l'estensione del
#: protocollo (``motore_ordini.valida_comando``), TUTTE e sempre, in quest'ordine
# (24/09 sera) la porta di Safe porta gia' le due chiavi: non si duplicano
CHIAVI_COMANDO = tuple(_SPO.CHIAVI_COMANDO) + tuple(
    k for k in ("time_in_force", "reduces_liability") if k not in _SPO.CHIAVI_COMANDO)

Ack = _SPO.Ack
terminale = _SPO.terminale


def acceso() -> bool:
    """Interruttore acceso SOLO se scritto (``1``/``true``/``si``/``yes``)."""
    return _SPO.acceso(ENV_CANALE)


def ref_ordine(trade_id: Any) -> str:
    """Il ref DETERMINISTICO di una riga di ``omega_trades``: lo stesso
    ``omega-t<id>`` della coda flumine e del customerOrderRef REST
    (``omega_engine.customer_ref_for``)."""
    return ("omega-t%d" % int(trade_id))[:REF_MAX]


def ref_annullo(bet_id: Any, size_reduction: Optional[float] = None) -> str:
    """Il ref di un ``cancel`` di Omega: deterministico dal bet_id."""
    ref = "omega-c%s" % str(bet_id).strip()
    if size_reduction is not None:
        ref += "-%d" % int(round(float(size_reduction) * 100))
    return ref[:REF_MAX]


def adatta_comando(comando: Dict[str, Any], *, time_in_force: Optional[str] = None,
                   riduce: bool = False) -> Dict[str, Any]:
    """Il comando costruito da ``safe_strategy.porta_ordini.costruisci_comando``
    reso comando di OMEGA. Solleva ``ValueError`` su qualunque cosa fuori posto:
    chi chiama NON manda niente."""
    d = dict(comando or {})
    if str(d.get("attore") or "") != ATTORE:
        raise ValueError("attore non di Omega: %r" % d.get("attore"))
    azione = d.get("azione")
    if azione not in _SPO.AZIONI:
        raise ValueError("azione fuori protocollo: %r" % azione)
    if d.get("mode") not in _SPO.MODI:
        raise ValueError("mode fuori protocollo: %r" % d.get("mode"))
    ref = str(d.get("ref") or "")
    if azione == "cancel" and ref.startswith("safe-c"):
        # il ref dell'annullo lo scrive il modulo di Safe: stesso schema, prefisso nostro
        ref = ref_annullo(d.get("bet_id"), d.get("size_reduction"))
    if not ref.startswith(PREFISSO_REF) or len(ref) > REF_MAX:
        raise ValueError("ref non di Omega: %r" % ref)
    if time_in_force not in (None, FOK):
        raise ValueError("time_in_force fuori protocollo: %r" % time_in_force)
    d["ref"] = ref
    d["strategy_ref"] = STRATEGY_REF
    # il runner vuole ``creato_ms`` INTERO (``motore_ordini._intero``): il
    # modulo di Safe lo scrive float (``round(ms, 1)``) e un float in JSON resta
    # float -> rifiuto ``parametri_invalidi``. Si tronca al millisecondo.
    creato = d.get("creato_ms")
    if isinstance(creato, bool) or not isinstance(creato, (int, float)):
        raise ValueError("creato_ms non numerico: %r" % creato)
    d["creato_ms"] = int(creato)
    origine = d.get("origine")
    if origine:
        if not isinstance(origine, dict):
            raise ValueError("origine non valida: %r" % origine)
        d["origine"] = {**origine, "tabella": TABELLA_ORIGINE}
    d["time_in_force"] = time_in_force if azione == "place" else None
    d["reduces_liability"] = bool(riduce) if azione == "place" else False
    return {k: d.get(k) for k in CHIAVI_COMANDO}


# ------------------------------------------------------------------ la vista
class VistaOmega:
    """La porta di Omega vista da UNA azione (apertura, chiusura, annullo).

    Stessa interfaccia della ``PortaCanale`` che ``safe_strategy.execution``
    usa (``via_canale``, ``attore``, ``disponibile``, ``invia``, ``esiti``,
    ``attendi_esito_bet``): passa tutto alla porta vera, tranne ``invia`` che
    prima adatta il comando. Nessuno stato proprio: si crea per azione."""

    via_canale = True
    nome = "canale_omega"

    def __init__(self, base: Any, *, time_in_force: Optional[str] = None,
                 riduce: bool = False) -> None:
        if time_in_force not in (None, FOK):
            raise ValueError("time_in_force fuori protocollo: %r" % time_in_force)
        self.base = base
        self.time_in_force = time_in_force
        self.riduce = bool(riduce)

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
            d = adatta_comando(comando, time_in_force=self.time_in_force, riduce=self.riduce)
        except ValueError as ex:
            ref = str((comando or {}).get("ref") or "")
            logger.error("[omega.porta] comando NON inviato (%s): %s", ref, str(ex)[:160])
            # rifiuto LOCALE: nulla e' uscito, e chi chiama lo tratta come un
            # rifiuto (nessun secondo invio, nessun ripiego)
            return Ack(ref, None, False, MOTIVO_NON_VALIDO, None)
        return self.base.invia(d)

    def esiti(self, ref: str) -> Optional[Dict[str, Any]]:
        return self.base.esiti(ref)

    def attendi_esito_bet(self, bet_id: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        return self.base.attendi_esito_bet(bet_id, timeout_s)


# ------------------------------------------------------------------ la porta
class PortaCanaleOmega(_SPO.PortaCanale):
    """La ``PortaCanale`` di Safe, identica, col nome del thread di Omega."""

    def avvia(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name="omega-porta-%s" % self.attore)
        self._thread.start()


def _crea_porta() -> PortaCanaleOmega:
    """La porta del runner calcio (stessa porta WS del runner di Safe calcio)."""
    return PortaCanaleOmega(
        porta_ws=_SPO._porta_env(_SPO.ENV_PORTA_CALCIO, _SPO.PORTA_CALCIO),
        attore=ATTORE, sport="calcio")


_PORTA: Optional[Any] = None
_LOCK = threading.Lock()


def porta_omega(*, avvia: bool = True) -> Optional[Any]:
    """La porta a comandi di Omega, o ``None`` a interruttore SPENTO (= il
    trasporto di oggi, nessuna chiamata diversa). Crea e avvia il client una
    volta sola per processo."""
    global _PORTA
    if not acceso():
        return None
    with _LOCK:
        p = _PORTA
        if p is None:
            p = _crea_porta()
            _PORTA = p
    if avvia:
        p.avvia()
    return p


def porta_esistente() -> Optional[Any]:
    """La porta gia' creata (anche se l'interruttore e' stato spento dopo), per
    leggere gli esiti delle righe gia' inviate. Mai ne crea una."""
    with _LOCK:
        return _PORTA


def azzera() -> None:
    """Ferma e dimentica la porta. Per i test e per il riavvio."""
    global _PORTA
    with _LOCK:
        p = _PORTA
        _PORTA = None
    if p is not None:
        try:
            p.ferma()
        except Exception:  # noqa: BLE001
            pass
