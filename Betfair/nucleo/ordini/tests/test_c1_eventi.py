"""W1-C1 - ``nucleo/ordini/eventi.py``: parita' con il consumatore di OGGI.

Il consumatore di oggi e' ``safe_strategy/porta_ordini.py`` ``MemoriaComandi`` (arbitro,
mai modificato). Su flussi casuali di ack ed eventi con seq per attore (base ~1,7e12 come
il motore), con messaggi PERSI, DUPLICATI e fuori ordine e con risposte ``da_seq``
complete e non, i due devono dare lo stesso ``seq_visto``, gli stessi contatori di buchi
e lo stesso ultimo evento per ref.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.nucleo.ordini.contratto import Ack, EventoOrdine
from Betfair.nucleo.ordini.eventi import ConsumatoreEventi, RispostaDaSeq
from Betfair.safe_strategy import porta_ordini as PO

BASE = 1_760_000_000_000
#: fasi del contratto -> fasi del motore (le stesse terminali; ``ignoto`` escluso: per
#: Safe ``errore`` e' terminale, per il contratto ``ignoto`` no - vedi il referto)
FASI = {"accettato": "accettato_betfair", "parziale": "abbinato_parziale",
        "abbinato": "abbinato", "annullato": "annullato", "scaduto": "scaduto",
        "rifiutato": "rifiutato", "parcheggiato": "parcheggiato", "ridotto": "ridotto"}


def _flusso(rnd: random.Random, n: int) -> List[Tuple[str, Any]]:
    """Messaggi di UN attore in ordine di seq: per ogni ref un ciclo di vita VERO (ack,
    accettato, parziali con l'abbinato che cresce, UN terminale), cicli intercalati."""
    out: List[Tuple[str, Any]] = []
    seq = BASE
    vivi: Dict[str, Tuple[float, int]] = {}      # ref -> (abbinato, eventi fatti)
    i = 0
    while len(out) < n:
        seq += 1
        if not vivi or rnd.random() < 0.25:
            i += 1
            ref = f"safe-t{i}"
            vivi[ref] = (0.0, 0)
            out.append(("ack", Ack(ref=ref, accettato=rnd.random() < 0.9, seq=seq, motivo=None)))
            continue
        ref = rnd.choice(list(vivi))
        abbinato, fatti = vivi[ref]
        if fatti == 0:
            fase = rnd.choice(["accettato", "parcheggiato"])
        elif fatti < 3 and rnd.random() < 0.6:
            fase = rnd.choice(["parziale", "ridotto"])
            abbinato = round(abbinato + rnd.choice([0.0, 0.5, 1.0]), 2)
        else:
            fase = rnd.choice(["abbinato", "annullato", "scaduto", "rifiutato"])
            abbinato = round(abbinato + (1.0 if fase == "abbinato" else 0.0), 2)
            del vivi[ref]
        if ref in vivi:
            vivi[ref] = (abbinato, fatti + 1)
        out.append(("evento", EventoOrdine(ref=ref, seq=seq, fase=fase, bet_id="1",
                                           abbinato=abbinato, residuo=0.0, prezzo_medio=None,
                                           codice_errore=None, esito_ms=None)))
    return out


def _come_safe(m: Any) -> Dict[str, Any]:
    if isinstance(m, Ack):
        return {"ref": m.ref, "seq": m.seq, "accettato": m.accettato, "motivo": m.motivo}
    return {"ref": m.ref, "seq": m.seq, "fase": FASI[m.fase], "bet_id": m.bet_id}


@pytest.mark.parametrize("seme", range(12))
def test_parita_con_memoria_comandi(seme: int) -> None:
    rnd = random.Random(seme)
    flusso = _flusso(rnd, 400)
    # disturbi del canale: persi, duplicati, scambiati
    consegnati: List[Tuple[str, Any]] = []
    for item in flusso:
        x = rnd.random()
        if x < 0.08:
            continue
        consegnati.append(item)
        if x > 0.95:
            consegnati.append(item)
    for i in range(0, len(consegnati) - 1, 17):
        consegnati[i], consegnati[i + 1] = consegnati[i + 1], consegnati[i]
    vecchio = PO.MemoriaComandi()
    nuovo = ConsumatoreEventi("safe")          # senza sorgente: solo la contiguita'
    for k, (tipo, m) in enumerate(consegnati):
        if tipo == "ack":
            vecchio.ricevi_ack(_come_safe(m))
        else:
            vecchio.ricevi_evento(_come_safe(m))
        nuovo.ricevi(m)
        if k % 50 == 49:                       # una risposta da_seq ogni tanto
            fino = max(x.seq for _t, x in consegnati[:k + 1])
            completo = rnd.random() < 0.5
            vecchio.chiudi_da_seq({"dal": vecchio.seq_visto, "fino_a": fino,
                                   "inviati": 0, "completo": completo})
            nuovo.chiudi_da_seq(fino, completo)
        assert (nuovo.seq_visto, nuovo.buchi, nuovo.buchi_non_colmati) == (
            vecchio.seq_visto, vecchio.buchi, vecchio.buchi_non_colmati), k
    assert nuovo.buchi > 0
    for ref, ev in vecchio._eventi.items():
        mio = nuovo.ultimo(ref)
        assert mio is not None and (mio.seq, FASI[mio.fase]) == (ev["seq"], ev["fase"]), ref


def _ev(ref: str, seq: int, fase: str, abbinato: float) -> EventoOrdine:
    return EventoOrdine(ref=ref, seq=seq, fase=fase, bet_id="1", abbinato=abbinato,
                        residuo=0.0, prezzo_medio=None, codice_errore=None, esito_ms=None)


def test_stato_non_regredisce_piu_severo_di_oggi() -> None:
    """DIVERGENZA dichiarata: ``MemoriaComandi`` accetta (seq piu' alto) un terminale dopo
    un terminale e un abbinato che cala; il consumatore nuovo no."""
    vecchio = PO.MemoriaComandi()
    nuovo = ConsumatoreEventi("safe")
    for ev in (_ev("safe-t1", BASE + 1, "parziale", 3.0), _ev("safe-t1", BASE + 2, "parziale", 1.0),
               _ev("safe-t2", BASE + 3, "abbinato", 4.0), _ev("safe-t2", BASE + 4, "rifiutato", 0.0),
               _ev("safe-t3", BASE + 5, "scaduto", 0.0), _ev("safe-t3", BASE + 6, "annullato", 0.0)):
        vecchio.ricevi_evento(_come_safe(ev))
        nuovo.ricevi(ev)
    assert nuovo.ultimo("safe-t1").abbinato == 3.0
    assert nuovo.ultimo("safe-t2").fase == "abbinato"
    assert nuovo.ultimo("safe-t3").fase == "scaduto"            # terminale dopo terminale
    assert vecchio._eventi["safe-t3"]["fase"] == "annullato"
    assert vecchio._eventi["safe-t2"]["fase"] == "rifiutato"      # oggi: regredisce


def test_memoria_del_consumatore_limitata() -> None:
    from Betfair.nucleo.ordini import eventi as EV

    cons = ConsumatoreEventi("safe")
    for k in range(EV.MAX_REF_IN_MEMORIA + 50):
        cons.ricevi(Ack(ref=f"safe-t{k}", accettato=True, seq=BASE + 2 * k + 1, motivo=None))
        cons.ricevi(_ev(f"safe-t{k}", BASE + 2 * k + 2, "accettato", 0.0))
    assert len(cons.ack) == EV.MAX_REF_IN_MEMORIA == len(cons.eventi)
    assert "safe-t0" not in cons.eventi and cons.buchi == 0


class _Sorgente:
    """Risponde con i messaggi GIA' emessi (``emessi`` = quanti, lo avanza il test)."""

    def __init__(self, messaggi: List[Any], completo: bool = True) -> None:
        self.messaggi = messaggi
        self.completo = completo
        self.emessi = 0
        self.chieste: List[int] = []

    def da_seq(self, attore: str, dal: int) -> RispostaDaSeq:
        self.chieste.append(dal)
        fatti = self.messaggi[:self.emessi]
        return RispostaDaSeq(dal=dal, fino_a=max(m.seq for m in fatti),
                             messaggi=tuple(m for m in fatti if m.seq > dal),
                             completo=self.completo)


def test_buco_chiede_da_seq_e_ripara() -> None:
    msgs = [m for _t, m in _flusso(random.Random(5), 30)]
    sorgente = _Sorgente(msgs)
    cons = ConsumatoreEventi("safe", sorgente=sorgente)
    for i, m in enumerate(msgs):
        sorgente.emessi = i + 1
        if i in (3, 4, 11):                     # persi dal push
            continue
        cons.ricevi(m)
    assert sorgente.chieste == [msgs[2].seq, msgs[10].seq]
    assert cons.seq_visto == msgs[-1].seq and cons.buchi_non_colmati == 0


def test_sorgente_ko_lascia_il_buco_aperto() -> None:
    class _Rotta:
        def da_seq(self, attore: str, dal: int) -> RispostaDaSeq:
            raise ConnectionError("canale giu'")

    msgs = [m for _t, m in _flusso(random.Random(9), 6)]
    cons = ConsumatoreEventi("safe", sorgente=_Rotta())
    cons.ricevi(msgs[0])
    cons.ricevi(msgs[2])
    assert cons.seq_visto == msgs[0].seq and cons.richieste_da_seq == 1
