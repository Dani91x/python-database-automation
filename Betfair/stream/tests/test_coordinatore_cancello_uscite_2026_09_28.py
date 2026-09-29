"""Verifica INDIPENDENTE del coordinatore sul cantiere N (28/09/2026).

``Betfair/stream/uscite_proposte.CancelloUscite`` e' il cancello delle uscite
dei bot di flusso (4 bot tennis, scalper calcio). Tre cose che la consegna non
provava:

1. una firma data a una proposta che poi DECADE (la condizione non vale piu')
   non deve eseguire l'uscita quando la condizione torna: l'utente ha approvato
   numeri che non esistono piu', la proposta nuova va rimostrata;
2. una firma vale UNA uscita: riletta dalla riga di controllo al battito dopo
   (stesso istante) non ne esegue una seconda;
3. le firme arrivano dal thread del battito mentre il thread del mercato pota
   proposte e firme: nessuna eccezione, mai.

File ASCII-only.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

from Betfair.stream.uscite_proposte import CancelloUscite, proposta_di

T0 = 1_800_000_000.0
PREF = "scalper|1.234|55|ord1|"


def _prop(motivo: str, se_chiudi: float) -> Dict[str, Any]:
    return proposta_di(bot="scalper", motivo=motivo, market_id="1.234", selection_id=55,
                       lato_ingresso="BACK", prezzo=2.40, lato_chiusura="LAY",
                       size_chiusura=23.12, se_chiudi=se_chiudi)


def test_firma_su_proposta_decaduta_non_esegue_quando_la_condizione_torna() -> None:
    eventi: List[str] = []
    c = CancelloUscite(emetti=lambda ev, p: eventi.append(ev))
    chiave = PREF + "stop"
    assert c.lascia_uscire(automatiche=False, chiave=chiave, now_s=T0,
                           proposta=_prop("stop", -1.88)) is False
    c.approva({chiave: T0 + 1})                    # l'utente firma -1,88
    c.conferma_vive(PREF, [])                      # il prezzo rientra: decade
    assert c.vive() == []
    # 30 s dopo la condizione torna, con numeri peggiori
    esce = c.lascia_uscire(automatiche=False, chiave=chiave, now_s=T0 + 31,
                           proposta=_prop("stop", -6.50))
    assert esce is False, ("uscita a -6,50 eseguita con la firma data alla "
                           "proposta a -1,88 che era decaduta")
    assert [p["se_chiudi"] for p in c.vive()] == [-6.5]


def test_una_firma_vale_una_sola_uscita_anche_se_riletta() -> None:
    c = CancelloUscite()
    chiave = PREF + "target"
    c.lascia_uscire(automatiche=False, chiave=chiave, now_s=T0, proposta=_prop("target", 0.4))
    firme = {chiave: T0 + 1}
    c.approva(firme)
    assert c.lascia_uscire(automatiche=False, chiave=chiave, now_s=T0 + 2,
                           proposta=_prop("target", 0.4)) is True
    c.approva(dict(firme))                         # battito dopo: stessa riga riletta
    assert c.lascia_uscire(automatiche=False, chiave=chiave, now_s=T0 + 3,
                           proposta=_prop("target", 0.4)) is False


def test_firme_dal_battito_e_potatura_dal_mercato_insieme_senza_eccezioni() -> None:
    c = CancelloUscite()
    errori: List[BaseException] = []
    fine = threading.Event()

    def battito() -> None:
        n = 0
        try:
            while not fine.is_set():
                n += 1
                c.approva({"scalper|1.234|%d|o%d|stop" % (n % 97, n): T0 + n})
        except BaseException as ex:  # noqa: BLE001 - e' il reperto
            errori.append(ex)

    def mercato() -> None:
        try:
            for i in range(60000):
                c.lascia_uscire(automatiche=False, chiave="scalper|1.234|%d|x|stop" % (i % 50),
                                now_s=T0 + i, proposta=_prop("stop", -1.0))
                c.tieni_solo(["scalper|1.234|%d|" % (i % 7)])
                c.chiudi_posizione("scalper|1.234|%d|" % (i % 11))
                c.conferma_vive("scalper|1.234|", [])
        except BaseException as ex:  # noqa: BLE001 - e' il reperto
            errori.append(ex)
        finally:
            fine.set()

    t1 = threading.Thread(target=battito)
    t2 = threading.Thread(target=mercato)
    t1.start()
    t2.start()
    t2.join(120)
    fine.set()
    t1.join(10)
    assert errori == [], "eccezione con firme e potatura insieme: %r" % errori[:1]
