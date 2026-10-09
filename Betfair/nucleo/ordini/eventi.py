"""eventi.py - il consumatore di ``EventoOrdine`` con controllo della contiguita' di ``seq`` (W1-C1).

Scopo
-----
``EventoOrdine`` e' un flusso DIFFERENZIALE (revisione critica R07, 04 par. 3.11): un
evento perso e' una fase dell'ordine che il bot non vede mai. Il canale locale per
costruzione "salta il giro" verso un client lento (``local_channel.py`` ~630-672), quindi
OGNI consumatore deve controllare che i ``seq`` del SUO attore siano contigui e, al primo
buco, chiedere ``da_seq`` (oggi servito dal motore: ``motore_ordini.py``
``_prossimo_seq`` ~939, ``_rispondi_da_seq`` ~2280, memoria di 500 messaggi per attore).

La logica e' quella del consumatore di oggi, ``safe_strategy/porta_ordini.py``
``MemoriaComandi`` (``_avanza_seq``, ``ricevi_ack``, ``ricevi_evento``,
``chiudi_da_seq``), riscritta qui perche' un comparto non importa un bot (04 par. 2.3):
la parita' e' provata dal test ``tests/test_c1_eventi.py`` contro la classe di oggi.
In piu' rispetto a oggi: il consumatore CHIEDE da solo il ``da_seq`` alla sorgente
iniettata (in Safe lo fa il client WebSocket ``_chiedi_da_seq``).

Entrate: ``Ack`` ed ``EventoOrdine`` (con ``seq`` per attore, UN contatore per ack ed
eventi come nel motore); una ``SorgenteDaSeq`` (la porta). Uscite: l'ultimo evento per
``ref``, ``seq_visto`` (il piu' alto seq contiguo), contatori di buchi.

Cosa NON fa: non apre socket ne' thread; non riconcilia con Betfair un buco non colmabile
(``completo`` False): lo CONTA e riparte, come oggi (la riconciliazione per ref e' del
comparto C2).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Set, Tuple, Union

from Betfair.nucleo.ordini.contratto import Ack, EventoOrdine

logger = logging.getLogger(__name__)

Messaggio = Union[Ack, EventoOrdine]
#: fasi dopo cui l'ordine non cambia piu' (``ignoto`` NON e' terminale: si riconcilia)
FASI_TERMINALI = frozenset({"abbinato", "scaduto", "annullato", "rifiutato"})


@dataclass(frozen=True)
class RispostaDaSeq:
    """La risposta a ``da_seq``: i messaggi con ``seq > dal`` ancora in memoria, il seq
    piu' alto assegnato (``fino_a``) e se la memoria copriva tutto (``completo``)."""

    dal: int
    fino_a: int
    messaggi: Tuple[Messaggio, ...]
    completo: bool


class SorgenteDaSeq(Protocol):
    def da_seq(self, attore: str, dal: int) -> RispostaDaSeq: ...


def terminale(ev: Optional[EventoOrdine]) -> bool:
    return ev is not None and ev.fase in FASI_TERMINALI


class ConsumatoreEventi:
    """Gli ack e gli eventi di UN attore, con il controllo della contiguita'. Thread-safe."""

    def __init__(self, attore: str, sorgente: Optional[SorgenteDaSeq] = None) -> None:
        self.attore = attore
        self._sorgente = sorgente
        self._lock = threading.RLock()
        self.seq_visto = 0
        self._sopra: Set[int] = set()
        self.buchi = 0
        self.buchi_non_colmati = 0
        self.richieste_da_seq = 0
        self._riparazione_in_corso = False
        self.ack: Dict[str, Ack] = {}
        self.eventi: Dict[str, EventoOrdine] = {}
        self.conti: Dict[str, int] = {"ack": 0, "eventi": 0, "vecchi": 0}

    # ------------------------------------------------------------ contiguita'
    def _avanza_seq(self, seq: Optional[int]) -> bool:
        """Registra ``seq``; True se c'e' un BUCO aperto. Il primo seq visto e' la BASE
        (il motore numera dall'istante del suo avvio, ~1,7e12)."""
        if seq is None:
            return False
        if self.seq_visto == 0 and not self._sopra:
            self.seq_visto = seq - 1
        if seq <= self.seq_visto:
            return False
        self._sopra.add(seq)
        while (self.seq_visto + 1) in self._sopra:
            self.seq_visto += 1
            self._sopra.discard(self.seq_visto)
        if self._sopra:
            self.buchi += 1
            return True
        return False

    def chiudi_da_seq(self, fino_a: int, completo: bool) -> None:
        """Dopo i messaggi rimandati: fino a ``fino_a`` non c'e' piu' niente da chiedere;
        un buco non colmabile (``completo`` False) si conta e si riparte da ``fino_a``."""
        with self._lock:
            if completo is False and fino_a > self.seq_visto:
                self.buchi_non_colmati += 1
                logger.warning("[porta.eventi] %s: buco NON colmabile fino a %d (memoria "
                               "superata): riallineare per ref", self.attore, fino_a)
            if fino_a > self.seq_visto:
                self.seq_visto = fino_a
            self._sopra = {s for s in self._sopra if s > self.seq_visto}
            while (self.seq_visto + 1) in self._sopra:
                self.seq_visto += 1
                self._sopra.discard(self.seq_visto)

    # -------------------------------------------------------------- ricezione
    def _registra_ack(self, a: Ack) -> bool:
        if not a.ref:
            return False
        self.ack[a.ref] = a
        self.conti["ack"] += 1
        return self._avanza_seq(a.seq)

    def _registra_evento(self, ev: EventoOrdine) -> Tuple[bool, bool]:
        """(entrato, buco)."""
        buco = self._avanza_seq(ev.seq)
        prima = self.eventi.get(ev.ref)
        if prima is not None and (ev.seq <= prima.seq or (terminale(prima)
                                                         and not terminale(ev))):
            self.conti["vecchi"] += 1
            return False, buco
        self.eventi[ev.ref] = ev
        self.conti["eventi"] += 1
        return True, buco

    def ricevi(self, m: Messaggio) -> bool:
        """Un messaggio dal flusso. Al buco chiede ``da_seq`` alla sorgente (una richiesta
        alla volta, mai ricorsiva). Ritorna True se il messaggio e' entrato."""
        with self._lock:
            if isinstance(m, Ack):
                if not m.ref:
                    return False
                entrato, buco = True, self._registra_ack(m)
            else:
                entrato, buco = self._registra_evento(m)
        if buco:
            self._ripara()
        return entrato

    def _ripara(self) -> None:
        if self._sorgente is None or self._riparazione_in_corso:
            return
        self._riparazione_in_corso = True
        try:
            with self._lock:
                dal = self.seq_visto
            self.richieste_da_seq += 1
            risposta = self._sorgente.da_seq(self.attore, dal)
            with self._lock:
                for m in risposta.messaggi:
                    if isinstance(m, Ack):
                        self._registra_ack(m)
                    else:
                        self._registra_evento(m)
            self.chiudi_da_seq(risposta.fino_a, risposta.completo)
        except Exception as ex:  # noqa: BLE001 - il buco resta aperto e si dice
            logger.error("[porta.eventi] %s: da_seq KO, buco aperto: %s", self.attore,
                         str(ex)[:200])
        finally:
            self._riparazione_in_corso = False

    def ultimo(self, ref: str) -> Optional[EventoOrdine]:
        with self._lock:
            return self.eventi.get(ref)
