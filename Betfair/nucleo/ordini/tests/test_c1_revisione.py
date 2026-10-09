"""W1-C1 - correzioni dopo la revisione indipendente del 09/10 (R01-R17 del revisore e
mutazioni sopravvissute V08, V11, V43, V59, V60), con nomi miei.

Ogni test e' stato visto ROSSO sul commit consegnato ``0b4f2b59`` (prima delle correzioni)
o con la mutazione corrispondente di ``falsifica_c1.py``; il referto (sezione "Correzioni
dopo la revisione") dice quale.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

import pytest

from Betfair.nucleo.ordini import porta as PT
from Betfair.nucleo.ordini.adattatore_comando import ExtraComando
from Betfair.nucleo.ordini.contratto import Ack, EventoOrdine
from Betfair.nucleo.ordini.eventi import ConsumatoreEventi
from Betfair.nucleo.dati.archivio import ArchivioChiuso
from Betfair.nucleo.ordini.tests.test_c1_porta import (GIORNO, T0, _Ambiente, _gemello,  # noqa: F401
                                                       _nuovo_archivio, _Orologio, _r, _riavviato,
                                                       archivio_parametrico)
from Betfair.stream import motore_ordini as MO


class _Crollo(BaseException):
    """Il processo muore (non e' un'eccezione gestita)."""


def _parz(ab: float, fase: str = "parziale", ref: str = "safe-t1") -> EventoOrdine:
    return EventoOrdine(ref=ref, seq=0, fase=fase, bet_id="1", abbinato=ab, residuo=4.0 - ab,
                        prezzo_medio=2.5, codice_errore=None, esito_ms=None)


# ---------------------------------------------------------------- bloccante 1: paper/live
def test_paper_non_consuma_il_tetto_del_live(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path, tetto=2)
    assert amb.porta.invia(_r(ref="safe-l0", modo="live")).accettato   # l'ora e' aperta
    for i in range(3):
        assert amb.porta.invia(_r(ref=f"safe-p{i}", modo="paper")).accettato
    live = amb.porta.invia(_r(ref="safe-l1", modo="live"))
    assert live.accettato, live.motivo
    assert amb.contatore.stato()["ora_corrente"] == 2         # solo il live conta


def test_il_tetto_del_live_non_ferma_il_paper(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path, tetto=0)
    assert amb.porta.invia(_r(ref="safe-l0", modo="live")).accettato
    assert not amb.porta.invia(_r(ref="safe-l1", modo="live")).accettato   # live pieno
    assert amb.porta.invia(_r(ref="safe-p1", modo="paper")).accettato


def test_contatore_proprio_del_paper(tmp_path: Any) -> None:
    """Oggi il client simulato ha il SUO tetto (``runner.py``): si riproduce passando un
    contatore del paper; i due non si sommano."""
    from Betfair.nucleo.ordini import controlli as CT

    amb = _Ambiente(tmp_path, tetto=5)
    paper = CT.ContatoreTransazioni(0, amb.orologio)
    amb.porta._contatori["paper"] = paper
    assert amb.porta.invia(_r(ref="safe-p0", modo="paper")).accettato
    assert not amb.porta.invia(_r(ref="safe-p1", modo="paper")).accettato  # paper pieno
    assert amb.porta.invia(_r(ref="safe-l0", modo="live")).accettato
    assert (paper.totale_ora, amb.contatore.totale_ora) == (1, 1)


def test_il_paper_non_impedisce_al_live_di_chiudere(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path, tetto=0)
    assert amb.porta.invia(_r(ref="safe-p1", modo="paper")).accettato
    c = amb.porta.invia(_r(ref="safe-c9", modo="live", azione="cancel", bet_id="9",
                           lato=None, prezzo=None, importo=None, time_in_force=None))
    assert c.accettato, c.motivo


def test_taglia_rifiutata_in_paper_non_blocca_il_live(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["FAILURE"]
    amb.porta.invia(_r(modo="paper", time_in_force=None))
    d = amb.porta.invia(_r(ref="safe-t2", modo="live", time_in_force=None))
    assert d.accettato, d.motivo


# ---------------------------------------------------------------- bloccante 2: params
def test_params_arrivano_al_dispatch_vero(tmp_path: Any, monkeypatch: Any) -> None:
    """Catena VERA: PortaLocale -> EsecutoreRunner -> live_order_worker._dispatch."""
    from Betfair.nucleo.ordini.esecutori.runner import EsecutoreRunner
    from Betfair.nucleo.ordini.tests import test_c1_esecutore_runner as TR
    from Betfair.stream import live_order_worker as LOW

    for nome, valore in (("_modo_processo", "LIVE"), ("_live_order_mode", "LIVE"),
                         ("_kill_switch", False), ("_jurisdiction", "it"),
                         ("_max_stake", None)):
        monkeypatch.setattr(LOW, nome, lambda v=valore: v)
    fl, market = TR._framework()
    es = EsecutoreRunner(fl, {"live": TR._STRAT_LIVE, "paper": TR._STRAT_PAPER})
    amb = _Ambiente(tmp_path)
    amb.porta.chiudi()                     # questa prova usa la porta sopra l'esecutore vero
    porta = PT.PortaLocale(es, freni=amb.freni, archivio=amb.archivio, diario=amb.diario,
                           orologio_ms=amb.orologio)
    porta._giorni = lambda: [GIORNO]  # type: ignore[method-assign]
    viste: List[Dict[str, Any]] = []
    orig = LOW._dispatch

    def _spia(sb: Any, flumine: Any, riga: Dict[str, Any], mode: str, strat: Any) -> None:
        viste.append(dict(riga))
        return orig(sb, flumine, riga, mode, strat)

    monkeypatch.setattr(LOW, "_dispatch", _spia)
    a = porta.invia(_r(modo="paper", importo=3.0, time_in_force=None),
                    ExtraComando(params={"max_stake": 1.0, "fok_ttl_sec": 5}))
    assert a.accettato and len(viste) == 1
    assert viste[0]["params"]["max_stake"] == 1.0 and viste[0]["params"]["fok_ttl_sec"] == 5
    # il cap di stake ha FERMATO l'ordine (3,00 > 1,00): nessun place_order
    assert porta.stato("safe-t1").fase == "rifiutato" and market.chiamate == []
    diario = [x for x in amb.righe_diario() if x.get("tipo") == "inviato"][0]
    assert diario["parametri"]["params"] == {"max_stake": 1.0, "fok_ttl_sec": 5}


def test_params_rifiutati_se_l_esecutore_non_li_serve(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = amb.porta.invia(_r(), ExtraComando(params={"max_stake": 1.0}))
    assert not a.accettato and a.motivo.startswith(PT.M_PARAMS)
    assert amb.betfair.chiamate == []
    assert [x["tipo"] for x in amb.righe_diario()] == ["rifiuto"]   # nessun 'inviato'


# ---------------------------------------------------------------- bloccante 3: deadlock
def test_consumatore_che_invia_dentro_la_callback_non_blocca(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    fatto = threading.Event()
    ricevuti: List[Any] = []

    def _cb(m: Any) -> None:
        ricevuti.append(m)
        if isinstance(m, Ack) and not fatto.is_set():
            fatto.set()
            amb.porta.invia(_r(ref="safe-t2", creato_ms=amb.orologio.ms))

    amb.porta.aggiungi_consumatore("safe", _cb)
    t = threading.Thread(target=lambda: amb.porta.invia(_r()), daemon=True)
    t.start()
    t.join(3)
    assert not t.is_alive(), "DEADLOCK: invia() dentro un consumatore chiamato da invia()"
    assert len(amb.betfair.chiamate) == 2
    seqs = [m.seq for m in ricevuti]
    assert seqs == sorted(seqs) and len(seqs) == 4            # 2 ack + 2 esiti, in ordine


# ---------------------------------------------------------------- 4. ack fantasma
def test_crash_fra_diario_e_archivio_nessun_ack_fantasma(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)

    def _muore(*_a: Any, **_k: Any) -> None:
        raise _Crollo()

    prima.diario.scrivi = _muore  # type: ignore[method-assign]
    with pytest.raises(_Crollo):
        prima.porta.invia(_r())
    assert prima.betfair.chiamate == []
    prima.porta.chiudi()
    dopo = _Ambiente(tmp_path, archivio=_riavviato(prima.archivio), orologio=_Orologio(T0 + 1_000))
    b = dopo.porta.invia(_r(creato_ms=T0 + 1_000))
    fantasma = b.accettato and dopo.porta.in_volo() == () and dopo.porta.stato("safe-t1") is None
    assert not fantasma


def test_archivio_ko_dopo_inviato_chiude_il_ref_nel_diario(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)
    orig = prima.archivio.scrivi

    def _ko_sul_ref(tabella: str, riga: Any) -> None:
        if tabella == PT.TABELLA_REF and riga.get("accettato"):
            # l'eccezione VERA dello scrivi di W1-G1 (archivio in chiusura): un disco guasto
            # invece NON fa sollevare scrivi (test_disco_dell_archivio_guasto_*)
            raise ArchivioChiuso("archivio in chiusura")
        orig(tabella, riga)

    prima.archivio.scrivi = _ko_sul_ref  # type: ignore[method-assign]
    a = prima.porta.invia(_r())
    assert not a.accettato and a.motivo.startswith(PT.M_ARCHIVIO)
    assert prima.betfair.chiamate == []
    dopo = _Ambiente(tmp_path, archivio=_nuovo_archivio(), orologio=_Orologio(T0 + 1_000))
    assert dopo.porta.in_volo() == () and dopo.porta.stato("safe-t1").fase == "rifiutato"


# ---------------------------------------------------------------- 5. ignoto dopo il riavvio
def test_ignoto_resta_da_riconciliare_dopo_il_riavvio(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)
    prima.betfair.piano = [TimeoutError("timeout dopo placeOrders")]
    prima.porta.invia(_r())
    prima.porta.chiudi()
    dopo = _Ambiente(tmp_path, archivio=_riavviato(prima.archivio), orologio=_Orologio(T0 + 1_000))
    assert dopo.porta.stato("safe-t1").fase == "ignoto"
    assert dopo.porta.in_volo() == ("safe-t1",)
    # un evento vero lo risolve e lo toglie dagli ordini in volo
    assert dopo.porta.notifica(_parz(4.0, "abbinato")) is not None
    assert dopo.porta.in_volo() == () and dopo.porta.stato("safe-t1").fase == "abbinato"


# ---------------------------------------------------------------- 6. stato monotono
def test_un_terminale_tardivo_non_cancella_un_abbinato(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXECUTION_COMPLETE"]
    amb.porta.invia(_r(time_in_force=None))
    assert amb.porta.notifica(EventoOrdine(ref="safe-t1", seq=0, fase="rifiutato",
                                           bet_id=None, abbinato=0.0, residuo=0.0,
                                           prezzo_medio=None, codice_errore="X",
                                           esito_ms=None)) is None
    st = amb.porta.stato("safe-t1")
    assert (st.fase, st.abbinato) == ("abbinato", 4.0)


def test_un_terminale_non_si_sovrascrive_con_un_altro_terminale(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXPIRED"]                     # FOK non abbinato: scaduto, 0 abbinato
    amb.porta.invia(_r())
    assert amb.porta.stato("safe-t1").fase == "scaduto"
    assert amb.porta.notifica(EventoOrdine(ref="safe-t1", seq=0, fase="annullato",
                                           bet_id="1", abbinato=0.0, residuo=0.0,
                                           prezzo_medio=None, codice_errore=None,
                                           esito_ms=None)) is None
    assert amb.porta.stato("safe-t1").fase == "scaduto"


def test_un_evento_vecchio_non_fa_regredire_l_abbinato(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXECUTABLE"]
    a = amb.porta.invia(_r(time_in_force=None))
    amb.porta.notifica(_parz(3.0))
    assert amb.porta.notifica(_parz(1.0)) is None          # in ritardo: scartato
    st = amb.porta.stato("safe-t1")
    assert (st.abbinato, st.residuo, st.prezzo_medio) == (3.0, 1.0, 2.5)
    assert [e.abbinato for e in amb.porta.eventi("safe", a.seq)] == [0.0, 3.0]
    assert amb.porta.conti["stantii"] == 1


# ---------------------------------------------------------------- 7. seq atomico
def test_memoria_in_ordine_di_seq_sotto_stress(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXECUTABLE"] * 400
    amb.porta.invia(_r(ref="safe-b0", time_in_force=None))
    stop = threading.Event()

    def _noti() -> None:
        i = 0
        while not stop.is_set():
            amb.porta.notifica(_parz(1.0 + i * 0.001, ref="safe-b0"))
            i += 1

    t = threading.Thread(target=_noti, daemon=True)
    t.start()
    for i in range(1, 150):
        amb.orologio.ms += 1
        amb.porta.invia(_r(ref=f"safe-b{i}", time_in_force=None, creato_ms=amb.orologio.ms))
    stop.set()
    t.join(5)
    seqs = [m.seq for m in amb.porta._memoria["safe"]]
    assert seqs == sorted(seqs)


def test_da_seq_non_dichiara_visto_un_seq_non_ancora_in_memoria(tmp_path: Any) -> None:
    """Un evento si ferma DENTRO la sezione che assegna il seq (scrittura del diario): un
    ``da_seq`` concorrente aspetta e poi vede tutto fino a ``fino_a``."""
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXECUTABLE"]
    amb.porta.invia(_r(time_in_force=None))
    base = amb.porta._seq["safe"]
    dentro, via = threading.Event(), threading.Event()
    orig = amb.diario.scrivi

    def _lenta(rec: Dict[str, Any], **k: Any) -> None:
        if rec.get("tipo") == "evento" and not dentro.is_set():
            dentro.set()
            via.wait(5)
        orig(rec, **k)

    amb.diario.scrivi = _lenta  # type: ignore[method-assign]
    t1 = threading.Thread(target=lambda: amb.porta.notifica(_parz(1.0)), daemon=True)
    t1.start()
    assert dentro.wait(5)
    risposte: List[Any] = []
    t2 = threading.Thread(target=lambda: risposte.append(amb.porta.da_seq("safe", base)),
                          daemon=True)
    t2.start()
    t2.join(0.3)
    assert t2.is_alive()                     # aspetta: il seq non e' ancora in memoria
    via.set()
    t1.join(5)
    t2.join(5)
    r = risposte[0]
    assert {m.seq for m in r.messaggi} == set(range(base + 1, r.fino_a + 1)) and r.fino_a > base


# ---------------------------------------------------------------- 8. due porte, un archivio
def test_seconda_porta_sullo_stesso_archivio_rifiutata(tmp_path: Any) -> None:
    """Decisione del coordinatore: una porta per archivio. Fra processi c'e' il lucchetto
    esclusivo della cartella (W1-G1); nello stesso processo la seconda e' una
    misconfigurazione, rifiutata alla costruzione."""
    arc = _nuovo_archivio()
    a1 = _Ambiente(tmp_path, archivio=arc, cartella="d1")
    with pytest.raises(PT.ArchivioGiaInUso):
        _Ambiente(tmp_path, archivio=arc, cartella="d2")
    a1.porta.invia(_r())
    a1.porta.chiudi()                                    # liberato: si puo' riaprire
    a3 = _Ambiente(tmp_path, archivio=arc, cartella="d3", orologio=_Orologio(T0 + 10))
    b = a3.porta.invia(_r(creato_ms=T0 + 10))
    assert b.motivo == MO.MOTIVO_REF_GIA_VISTO and b.accettato and a3.betfair.chiamate == []
    # lo stesso archivio vero ha la stessa cartella anche se e' un altro oggetto
    gemello = _gemello(arc)
    with pytest.raises(PT.ArchivioGiaInUso):
        _Ambiente(tmp_path, archivio=gemello, cartella="d4")


# ---------------------------------------------------------------- 9. tennis (implementato)
def test_tennis_apertura_sotto_minimo_portata_al_minimo(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = amb.porta.invia(_r(ref="safe_tennis-t1", attore="safe_tennis", sport="tennis",
                           lato="lay", importo=0.8, time_in_force=None))
    assert a.accettato, a.motivo
    assert amb.esecutore.ricevute[-1].importo == 1.0
    ev = list(amb.porta.eventi("safe_tennis", a.seq))[0]
    assert ev.portata_al_minimo == {"chiesto": 0.8, "piazzato": 1.0}
    # una CHIUSURA tennis non si gonfia mai: sotto il minimo e' rifiutata
    c = amb.porta.invia(_r(ref="safe_tennis-t2", attore="safe_tennis", sport="tennis",
                           lato="lay", importo=0.8, time_in_force=None,
                           riduce_esposizione=True))
    amb.porta._riduzione_verificata = None
    assert not c.accettato and c.motivo.startswith(MO.M_SOTTO_MINIMO)
    # il calcio NON porta al minimo
    d = amb.porta.invia(_r(ref="safe-t3", lato="lay", importo=0.8, time_in_force=None))
    assert not d.accettato and d.motivo.startswith(MO.M_SOTTO_MINIMO)


def test_place_and_trim_mai_dalla_porta(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.esecutore.submin_disponibile = True            # type: ignore[attr-defined]
    a = amb.porta.invia(_r(importo=0.6, time_in_force=None))
    assert not a.accettato and a.motivo.startswith(MO.M_SOTTO_MINIMO)
    assert amb.esecutore.ricevute == []


# ---------------------------------------------------------------- bassi
def test_contatore_che_solleva_dopo_l_invio_lascia_l_esito(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path, tetto=100)

    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("contatore KO")

    amb.contatore.registra = _boom  # type: ignore[method-assign]
    a = amb.porta.invia(_r())
    assert a.accettato and len(amb.betfair.chiamate) == 1
    assert amb.porta.stato("safe-t1").fase == "accettato"


def test_taglia_rifiutata_anche_con_lato_maiuscolo(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["FAILURE"]
    amb.porta.invia(_r(lato="BACK", time_in_force=None))
    n = len(amb.betfair.chiamate)
    d = amb.porta.invia(_r(ref="safe-t2", lato="BACK", time_in_force=None))
    assert not d.accettato and len(amb.betfair.chiamate) == n


def test_replace_con_riduce_non_scavalca_il_kill_switch(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.freni.kill = True
    amb.porta._riduzione_verificata = lambda r: True
    a = amb.porta.invia(_r(ref="safe-t1", azione="replace", lato=None, prezzo=None,
                           importo=None, time_in_force=None, bet_id="1", nuovo_prezzo=2.6,
                           riduce_esposizione=True))
    assert not a.accettato and a.motivo.startswith(MO.M_KILL)
    c = amb.porta.invia(_r(ref="safe-t2", azione="cancel", lato=None, prezzo=None,
                           importo=None, time_in_force=None, bet_id="1"))
    assert c.accettato


def test_seq_dopo_il_riavvio_con_orologio_indietro(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)
    a = prima.porta.invia(_r(ref="safe-t1"))
    prima.porta.chiudi()
    dopo = _Ambiente(tmp_path, cartella="d2", archivio=_riavviato(prima.archivio),
                     orologio=_Orologio(T0 - 5_000))
    b = dopo.porta.invia(_r(ref="safe-t2", creato_ms=T0 - 5_000))
    assert b.seq > a.seq


def test_memoria_della_porta_limitata(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PT, "MAX_IN_MEMORIA", 10)
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXECUTION_COMPLETE"] * 30         # ordini CHIUSI: si possono dimenticare
    for i in range(30):
        amb.porta.invia(_r(ref=f"safe-t{i}"))
    p = amb.porta
    assert max(len(p._visti), len(p._richieste), len(p._stati), len(p._attore_di_ref)) <= 10
    # il dedup dei ref usciti dalla RAM resta nell'archivio
    assert p.invia(_r(ref="safe-t0")).motivo == MO.MOTIVO_REF_GIA_VISTO
    assert len(amb.betfair.chiamate) == 30


# ---------------------------------------------------------------- mutazioni sopravvissute
def test_stato_porta_i_valori_veri(tmp_path: Any) -> None:
    """V60: abbinato e residuo NON scambiati, prezzo medio dal report."""
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["PARZIALE"]
    amb.porta.invia(_r(importo=6.0, time_in_force=None))
    st = amb.porta.stato("safe-t1")
    assert (st.fase, st.abbinato, st.residuo, st.prezzo_medio) == ("parziale", 1.0, 5.0, 2.5)
    assert st.bet_id == "312426000001"


def test_write_ahead_e_durevole(tmp_path: Any) -> None:
    """V08: la riga ``inviato`` si scrive con fsync (``durevole=True``), come il motore."""
    amb = _Ambiente(tmp_path)
    chiamate: List[tuple] = []
    orig = amb.diario.scrivi

    def _spia(rec: Dict[str, Any], *, durevole: bool = True) -> None:
        chiamate.append((rec.get("tipo"), durevole))
        orig(rec, durevole=durevole)

    amb.diario.scrivi = _spia  # type: ignore[method-assign]
    amb.porta.invia(_r())
    assert ("inviato", True) in chiamate and ("esito", True) in chiamate


def test_ignoto_e_rifiuto_locale_non_contano_come_transazioni(tmp_path: Any) -> None:
    """V11, V43: un esito ignoto e un rifiuto locale (nessuna richiesta a Betfair) non
    contano; un rifiuto DI BETFAIR conta come fallita."""
    amb = _Ambiente(tmp_path, tetto=100)
    amb.betfair.piano = [TimeoutError("timeout")]
    amb.porta.invia(_r(ref="safe-t1"))
    assert amb.contatore.totale_ora == 0

    class _RifiutoLocale:
        def place(self, r: Any) -> EventoOrdine:
            return EventoOrdine(ref=r.ref, seq=0, fase="rifiutato", bet_id=None,
                                abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                codice_errore="SOTTO_MINIMO_NON_PIAZZABILE", esito_ms=None)

    amb.porta._esecutore = _RifiutoLocale()          # type: ignore[assignment]
    amb.porta.invia(_r(ref="safe-t2"))
    assert amb.contatore.totale_ora == 0
    amb.porta._esecutore = amb.esecutore             # type: ignore[assignment]
    amb.betfair.piano = ["FAILURE"]
    amb.porta.invia(_r(ref="safe-t3", importo=5.0))
    # un place rifiutato DA BETFAIR conta (flumine: +1 a ogni risposta del place)
    assert (amb.contatore.correnti, amb.contatore.correnti_fallite) == (1, 0)


def test_notifica_di_un_ref_sconosciuto_ignorata(tmp_path: Any) -> None:
    """V59."""
    amb = _Ambiente(tmp_path)
    cons = ConsumatoreEventi("safe")
    amb.porta.aggiungi_consumatore("safe", cons.ricevi)
    assert amb.porta.notifica(_parz(1.0, ref="safe-t99")) is None
    assert amb.porta.stato("safe-t99") is None and amb.porta._memoria == {}


# ---------------------------------------------------------------- seconda revisione (41ea9dcb)
def test_contratto_del_finto_transizione_come_il_vero() -> None:
    """Il finto fa ESATTAMENTE cio' che fa ``ArchivioLocale.transizione`` di W1-G1: riga
    assente -> False; colonna di stato configurabile (di serie ``status``); scrivi fonde.
    Gira sul finto E sul vero (fixture ``archivio_parametrico``): stesse risposte."""
    a = _nuovo_archivio()
    assert a.transizione(PT.TABELLA_REF, {"ref": "safe-x"}, "", "qualsiasi") is False
    assert a.leggi(PT.TABELLA_REF, {"ref": "safe-x"}) is None
    a.scrivi(PT.TABELLA_REF, {"ref": "safe-x", "status": "aperto", "seq": 1})
    a.scrivi(PT.TABELLA_REF, {"ref": "safe-x", "motivo": "m"})
    assert a.leggi(PT.TABELLA_REF, {"ref": "safe-x"}) == {"ref": "safe-x", "status": "aperto",
                                                          "seq": 1, "motivo": "m"}
    assert a.transizione(PT.TABELLA_REF, {"ref": "safe-x"}, "altro", "chiuso") is False
    assert a.transizione(PT.TABELLA_REF, {"ref": "safe-x"}, "aperto", "chiuso") is True
    b = _nuovo_archivio(colonna_stato="stato")
    b.scrivi(PT.TABELLA_REF, {"ref": "r", "stato": "x", "status": "y"})
    assert b.transizione(PT.TABELLA_REF, {"ref": "r"}, "y", "z") is False
    assert b.transizione(PT.TABELLA_REF, {"ref": "r"}, "x", "z") is True


def test_ogni_ordine_nuovo_parte_con_la_semantica_vera(tmp_path: Any) -> None:
    """Il difetto bloccante della seconda revisione: con l'archivio vero ogni ordine nuovo
    usciva 'in carico a un'altra porta' con 0 chiamate. Ora: 20 ordini nuovi, 20 invii."""
    amb = _Ambiente(tmp_path)
    for i in range(20):
        a = amb.porta.invia(_r(ref=f"safe-n{i}"))
        assert a.accettato and a.seq is not None and a.motivo is None
    assert len(amb.betfair.chiamate) == 20


def test_ref_gia_visto_risponde_l_ack_originale(tmp_path: Any) -> None:
    """Parita' col motore (``motore_ordini.py:997-1005``): stesso ref = stessa richiesta,
    mai un secondo invio, ack con ``accettato`` e ``seq`` della PRIMA risposta, in ogni
    fase. Un ``accettato=False`` sul ref in volo farebbe rimandare il bot con un ref
    NUOVO: un secondo ordine."""
    amb = _Ambiente(tmp_path)
    # 1. in volo dopo il riavvio: lo stesso ack del diario
    amb.esecutore.prima_della_chiamata = lambda _r: (_ for _ in ()).throw(_Crollo())
    with pytest.raises(_Crollo):
        amb.porta.invia(_r(ref="safe-v1"))
    seq_v1 = amb.porta._visti["safe-v1"].seq
    amb.porta.chiudi()
    dopo = _Ambiente(tmp_path, archivio=_riavviato(amb.archivio), orologio=_Orologio(T0 + 1_000))
    a = dopo.porta.invia(_r(ref="safe-v1", creato_ms=T0 + 1_000))
    assert (a.accettato, a.seq, a.motivo) == (True, seq_v1, MO.MOTIVO_REF_GIA_VISTO)
    assert dopo.porta.stato("safe-v1").fase == "ignoto"        # resta da riconciliare
    # 2. esito ignoto nella stessa vita: lo stesso ack del primo invio
    dopo.betfair.piano = [TimeoutError("timeout")]
    b1 = dopo.porta.invia(_r(ref="safe-v2", creato_ms=T0 + 1_000))
    b = dopo.porta.invia(_r(ref="safe-v2", creato_ms=T0 + 1_000))
    assert (b.accettato, b.seq, b.motivo) == (True, b1.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert dopo.porta.stato("safe-v2").fase == "ignoto"
    assert len(dopo.betfair.chiamate) == 1                     # solo il primo safe-v2
    # 3. idempotenza: un ref ACCETTATO da questa porta risponde lo stesso ack
    c1 = dopo.porta.invia(_r(ref="safe-v3", creato_ms=T0 + 1_000))
    c2 = dopo.porta.invia(_r(ref="safe-v3", creato_ms=T0 + 1_000))
    assert (c2.accettato, c2.seq, c2.motivo) == (True, c1.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert len(dopo.betfair.chiamate) == 2


def test_esito_del_place_non_sovrascrive_il_flusso_arrivato_prima(tmp_path: Any) -> None:
    """P2 del revisore: lo stream degli ordini (abbinato 4,0) arriva PRIMA della risposta
    REST del place (parziale 1,0): lo stato resta abbinato 4,0."""
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["PARZIALE"]

    def _prima(r: Any) -> None:
        amb.porta.notifica(EventoOrdine(ref=r.ref, seq=0, fase="abbinato", bet_id="b1",
                                        abbinato=4.0, residuo=0.0, prezzo_medio=2.5,
                                        codice_errore=None, esito_ms=None))

    amb.esecutore.prima_della_chiamata = _prima
    a = amb.porta.invia(_r(ref="safe-p2", time_in_force=None, persistenza="PERSIST"))
    st = amb.porta.stato("safe-p2")
    assert (st.fase, st.abbinato, st.residuo) == ("abbinato", 4.0, 0.0)
    assert [(e.fase, e.abbinato) for e in amb.porta.eventi("safe", a.seq)] == [("abbinato", 4.0)]


def test_un_ordine_aperto_non_si_dimentica(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """P1 del revisore (tetto 20): un PERSIST ancora aperto resta in memoria oltre il tetto
    e i suoi aggiornamenti arrivano; si dimenticano solo gli ordini chiusi."""
    monkeypatch.setattr(PT, "MAX_IN_MEMORIA", 20)
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["PARZIALE"] + ["EXECUTION_COMPLETE"] * 40
    amb.porta.invia(_r(ref="safe-0", time_in_force=None, persistenza="PERSIST"))
    for i in range(1, 41):
        amb.orologio.ms += 1
        amb.porta.invia(_r(ref=f"safe-{i}", creato_ms=amb.orologio.ms))
    assert amb.porta.stato("safe-0").fase == "parziale"
    fine = amb.porta.notifica(EventoOrdine(ref="safe-0", seq=0, fase="abbinato", bet_id="x",
                                           abbinato=4.0, residuo=0.0, prezzo_medio=2.5,
                                           codice_errore=None, esito_ms=None))
    assert fine is not None and amb.porta.stato("safe-0").fase == "abbinato"
    assert len(amb.porta._stati) <= 21 and len(amb.porta._attore_di_ref) <= 21


def test_tetto_pieno_di_ordini_aperti_cresce(tmp_path: Any, monkeypatch: pytest.MonkeyPatch,
                                            caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(PT, "MAX_IN_MEMORIA", 5)
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = ["EXECUTABLE"] * 12
    for i in range(12):
        amb.porta.invia(_r(ref=f"safe-a{i}", time_in_force=None, persistenza="PERSIST"))
    assert len(amb.porta._stati) == 12                         # nessun aperto dimenticato
    assert any("APERTI oltre il tetto" in r.getMessage() for r in caplog.records)


def test_riavvio_con_righe_stantie_nel_diario(tmp_path: Any) -> None:
    """R9: al riavvio un evento piu' vecchio (abbinato che cala) scritto nel diario dopo
    quello buono non fa regredire lo stato."""
    prima = _Ambiente(tmp_path)
    prima.betfair.piano = ["EXECUTABLE"]
    prima.porta.invia(_r(time_in_force=None))
    prima.porta.notifica(_parz(3.0))
    stantio = _parz(1.0)
    prima.diario.scrivi({"tipo": "evento", "ref": "safe-t1", "ts_ms": T0,
                         "evento": dict(stantio.__dict__, seq=prima.porta._seq["safe"] + 1)})
    prima.porta.chiudi()
    dopo = _Ambiente(tmp_path, archivio=_riavviato(prima.archivio), orologio=_Orologio(T0 + 1_000))
    st = dopo.porta.stato("safe-t1")
    assert (st.fase, st.abbinato) == ("parziale", 3.0)


# ---------------------------------------------------------------- terza revisione (cc5286cb)
def _riavvia(amb: Any, tmp_path: Any) -> Any:
    """Il processo muore e riparte: stesso diario (stessa cartella), stesso archivio."""
    amb.porta.chiudi()
    return _Ambiente(tmp_path, archivio=_riavviato(amb.archivio), orologio=_Orologio(T0 + 1_000))


def test_riavvio_con_un_ref_rifiutato_stesso_rifiuto(tmp_path: Any) -> None:
    """L'unico accettato=False su un ref noto: la prima risposta era gia' un rifiuto."""
    amb = _Ambiente(tmp_path)
    amb.freni.kill = True
    a = amb.porta.invia(_r(ref="safe-k1"))
    assert not a.accettato and a.seq is not None and a.motivo.startswith(MO.M_KILL)
    dopo = _riavvia(amb, tmp_path)
    b = dopo.porta.invia(_r(ref="safe-k1", creato_ms=T0 + 1_000))   # kill-switch ora spento
    assert (b.accettato, b.seq, b.motivo) == (False, a.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert dopo.betfair.chiamate == []


def test_ref_gia_visto_parita_col_motore_di_oggi(tmp_path: Any) -> None:
    """Parita' DIRETTA sugli stessi ingressi: il diario scritto dalla porta (lo stesso
    ``motore_ordini.Diario``) caricato dal ``MotoreOrdini`` di oggi (``_carica_visti``) e
    il ramo di dedup del motore (``_gestisci``, ``motore_ordini.py:997-1005``) rispondono
    come la porta riavviata: ref chiuso, ignoto, rifiutato, in volo."""
    from types import SimpleNamespace

    amb = _Ambiente(tmp_path)
    amb.porta.invia(_r(ref="safe-q1"))                                # chiuso
    amb.betfair.piano = [TimeoutError("timeout")]
    amb.porta.invia(_r(ref="safe-q2"))                                # ignoto
    amb.freni.kill = True
    amb.porta.invia(_r(ref="safe-q3"))                                # rifiutato
    amb.freni.kill = False
    amb.esecutore.prima_della_chiamata = lambda _r: (_ for _ in ()).throw(_Crollo())
    with pytest.raises(_Crollo):
        amb.porta.invia(_r(ref="safe-q4"))                            # in volo (crash)
    refs = ("safe-q1", "safe-q2", "safe-q3", "safe-q4")
    prime = {ref: amb.porta._visti[ref] for ref in refs}
    dopo = _riavvia(amb, tmp_path)
    assert set(dopo.porta.in_volo()) == {"safe-q2", "safe-q4"}

    class _Canale:
        def __init__(self) -> None:
            self.acks: List[Dict[str, Any]] = []

        def invia(self, _ws: Any, payload: Dict[str, Any]) -> None:
            self.acks.append(payload["d"])

    canale = _Canale()
    motore = MO.MotoreOrdini("calcio", canale=canale,
                             diario=MO.Diario(amb.cartella, giorno=lambda: GIORNO),
                             scrittore=None)  # type: ignore[arg-type]
    motore._giorni_diario = lambda: [GIORNO]  # type: ignore[method-assign]
    motore._carica_visti()
    for ref in refs:
        motore._gestisci(SimpleNamespace(token_ok=True, attore="safe", tipo="comando",
                                         d={"ref": ref}, ws="ws", ricevuto_ms=0))
        oggi = canale.acks[-1]
        mia = dopo.porta.invia(_r(ref=ref, creato_ms=T0 + 1_000))
        assert (mia.accettato, mia.seq, mia.motivo) == \
            (oggi["accettato"], oggi["seq"], oggi["motivo"]), ref
        assert (mia.accettato, mia.seq) == (prime[ref].accettato, prime[ref].seq), ref
    assert [a["accettato"] for a in canale.acks] == [True, True, False, True]
    assert dopo.betfair.chiamate == []                 # nessun invio dopo il riavvio
