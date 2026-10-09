"""W1-C1 - test di CONTRATTO della porta degli ordini (scheda C par. 5, punti 1-4).

Finti con le chiavi e i tipi del vero:
  * Betfair: ``_BetfairFinto`` risponde con le RISPOSTE VERE di betfairlightweight
    (``PlaceOrders``/``CancelOrders``/``ReplaceOrders`` costruite dal JSON camelCase
    dell'API, come ``betting.place_orders``); l'esecutore di prova legge gli attributi
    VERI (``place_instruction_reports[0].status``, ``bet_id``, ``size_matched``,
    ``average_price_matched``, ``order_status``, ``error_code``) e traduce la fase con
    ``motore_ordini.fase_da_riga`` sulla riga dello specchio, come il motore
    (modello: ``banco_comune.py`` ~1024-1028, ordini e stati VERI, mai stringhe inventate);
  * diario: la classe VERA ``motore_ordini.Diario`` su una cartella temporanea (fsync);
  * archivio: ``_ArchivioMemoria`` col protocollo ``nucleo/dati/contratto.Archivio``,
    che sopravvive alla porta (simula il disco al riavvio).

Coperti: (1) dedup per ref dopo il riavvio (dall'archivio, dal diario) e nella finestra;
(2) ciclo di vita con le risposte vere: accettato, parziale, abbinato, FOK scaduto,
rifiuto di Betfair, taglia rifiutata non ritentata, bet delay sull'orologio; (3) esito
IGNOTO mai ok e mai ritentato; (4) ``da_seq``: push scartato di proposito e riparato;
piu' modo della riga, kill-switch solo sulle aperture, diario write-ahead, minimi,
tetto delle transazioni per conto su piu' attori, ordini in volo al riavvio.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Mapping, Optional

import pytest
from betfairlightweight.resources.bettingresources import (CancelOrders, PlaceOrders,
                                                           ReplaceOrders)

from Betfair.nucleo.ordini import adattatore_comando as AC
from Betfair.nucleo.ordini import controlli as CT
from Betfair.nucleo.ordini import porta as PT
from Betfair.nucleo.ordini.contratto import (Ack, EventoOrdine, PortaOrdini,
                                             RichiestaOrdine)
from Betfair.nucleo.ordini.eventi import ConsumatoreEventi
from Betfair.stream import motore_ordini as MO

T0 = 1_760_000_000_000
GIORNO = "2025-10-09"


class _Orologio:
    def __init__(self, ms: int = T0) -> None:
        self.ms = ms

    def __call__(self) -> int:
        return self.ms


class _ArchivioMemoria:
    """Il protocollo ``Archivio`` in memoria, con le chiavi naturali delle due tabelle
    della porta e ``transizione(t, chiave, "", a)`` = inserisci-se-assente ATOMICO (la
    semantica che la porta chiede a G1). ``guasto_*`` fa sollevare; ``ritardo_lettura_s``
    simula una lettura che viaggia (fotografia, poi latenza)."""

    CHIAVI = {PT.TABELLA_REF: ("ref",), getattr(PT, "TABELLA_SEQ", "ordini_seq"): ("chiave",)}

    def __init__(self) -> None:
        import threading

        self.tabelle: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.guasto_lettura = False
        self.guasto_scrittura = False
        self.ritardo_lettura_s = 0.0
        self._lock = threading.Lock()

    def _k(self, tabella: str, valori: Mapping[str, Any]) -> str:
        return json.dumps({c: valori[c] for c in self.CHIAVI[tabella]}, sort_keys=True)

    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        if self.guasto_lettura:
            raise OSError("archivio illeggibile")
        with self._lock:
            riga = self.tabelle.get(tabella, {}).get(self._k(tabella, chiave))
            riga = dict(riga) if riga is not None else None
        if self.ritardo_lettura_s:
            # la risposta viaggia: chi scrive nel frattempo non e' in questa lettura
            import time
            time.sleep(self.ritardo_lettura_s)
        return riga

    def scrivi(self, tabella: str, riga: Mapping[str, Any]) -> None:
        if self.guasto_scrittura:
            raise OSError("disco pieno")
        with self._lock:
            self.tabelle.setdefault(tabella, {})[self._k(tabella, riga)] = dict(riga)

    def transizione(self, tabella: str, chiave: Mapping[str, Any], da: str, a: str) -> bool:
        if self.guasto_scrittura:
            raise OSError("disco pieno")
        with self._lock:
            t = self.tabelle.setdefault(tabella, {})
            k = self._k(tabella, chiave)
            attuale = t.get(k)
            if (attuale is None and da == "") or (attuale is not None
                                                  and attuale.get("stato") == da):
                t[k] = {**dict(chiave), **(attuale or {}), "stato": a}
                return True
            return False


class _Freni:
    def __init__(self, proc: str = "LIVE", kill: bool = False) -> None:
        self.proc, self.kill = proc, kill

    def kill_switch(self) -> bool:
        return self.kill

    def modo_processo(self) -> str:
        return self.proc

    def blocco_apertura(self, modo_riga: str, azione: str, params: Any) -> Optional[str]:
        return None

    def eta_settings_s(self) -> float:
        return 0.5


# ---------------------------------------------------------------------------
# il finto Betfair: risposte VERE di betfairlightweight
# ---------------------------------------------------------------------------
class _BetfairFinto:
    """Risponde come ``betting.place_orders/cancel_orders/replace_orders``: un oggetto
    VERO della libreria costruito dal JSON dell'API. ``piano`` = cosa rispondere al
    prossimo place (o un'eccezione = timeout di rete: esito ignoto)."""

    def __init__(self, orologio: _Orologio, bet_delay_ms: int = 0) -> None:
        self.orologio = orologio
        self.bet_delay_ms = bet_delay_ms
        self.piano: List[Any] = []
        self.chiamate: List[Dict[str, Any]] = []
        self._n = 0

    def place_orders(self, market_id: str, instructions: List[Dict[str, Any]],
                     customer_ref: str, customer_strategy_ref: str) -> PlaceOrders:
        self.chiamate.append({"metodo": "place_orders", "market_id": market_id,
                              "instructions": instructions, "customer_ref": customer_ref,
                              "customer_strategy_ref": customer_strategy_ref})
        self.orologio.ms += self.bet_delay_ms
        cosa = self.piano.pop(0) if self.piano else "EXECUTABLE"
        if isinstance(cosa, Exception):
            raise cosa
        self._n += 1
        ins = instructions[0]
        size = ins["limitOrder"]["size"]
        rep: Dict[str, Any] = {"status": "SUCCESS", "instruction": ins}
        if cosa == "FAILURE":
            rep = {"status": "FAILURE", "instruction": ins, "errorCode": "INVALID_BET_SIZE"}
        else:
            matched = {"EXECUTABLE": 0.0, "PARZIALE": 1.0,
                       "EXECUTION_COMPLETE": size, "EXPIRED": 0.0}[cosa]
            rep.update({"betId": f"31242600{self._n:04d}", "placedDate": "2026-10-09T10:00:00.000Z",
                        "averagePriceMatched": ins["limitOrder"]["price"] if matched else 0.0,
                        "sizeMatched": matched,
                        "orderStatus": "EXECUTABLE" if cosa == "PARZIALE" else cosa})
        return PlaceOrders(status=rep["status"], marketId=market_id, customerRef=customer_ref,
                           instructionReports=[rep],
                           **({"errorCode": "BET_ACTION_ERROR"} if cosa == "FAILURE" else {}))

    def cancel_orders(self, market_id: str, instructions: List[Dict[str, Any]],
                      customer_ref: str) -> CancelOrders:
        self.chiamate.append({"metodo": "cancel_orders", "instructions": instructions})
        ins = instructions[0]
        return CancelOrders(status="SUCCESS", marketId=market_id, customerRef=customer_ref,
                            instructionReports=[{"status": "SUCCESS", "instruction": ins,
                                                 "sizeCancelled": ins.get("sizeReduction") or 2.0,
                                                 "cancelledDate": "2026-10-09T10:00:01.000Z"}])

    def replace_orders(self, market_id: str, instructions: List[Dict[str, Any]],
                       customer_ref: str) -> ReplaceOrders:
        self.chiamate.append({"metodo": "replace_orders", "instructions": instructions})
        ins = instructions[0]
        return ReplaceOrders(status="SUCCESS", marketId=market_id, customerRef=customer_ref,
                             instructionReports=[{
                                 "status": "SUCCESS",
                                 "cancelInstructionReport": {
                                     "status": "SUCCESS", "instruction": {"betId": ins["betId"]},
                                     "sizeCancelled": 2.0,
                                     "cancelledDate": "2026-10-09T10:00:01.000Z"},
                                 "placeInstructionReport": {
                                     "status": "SUCCESS", "betId": "999", "orderStatus": "EXECUTABLE",
                                     "sizeMatched": 0.0, "averagePriceMatched": 0.0,
                                     "placedDate": "2026-10-09T10:00:01.000Z",
                                     "instruction": {"selectionId": 1, "handicap": 0,
                                                     "side": "BACK", "orderType": "LIMIT",
                                                     "limitOrder": {"size": 2.0,
                                                                    "price": ins["newPrice"],
                                                                    "persistenceType": "LAPSE"}}}}])


class _EsecutoreBetfairFinto:
    """Un ``Esecutore`` che parla al finto Betfair con le istruzioni dell'API e legge le
    risposte VERE. La fase viene da ``motore_ordini.fase_da_riga`` (stessa regola del
    motore) sulla riga dello specchio costruita dagli attributi della libreria."""

    def __init__(self, betfair: _BetfairFinto) -> None:
        self.betfair = betfair
        self.ricevute: List[RichiestaOrdine] = []
        self.prima_della_chiamata: Optional[Callable[[RichiestaOrdine], None]] = None

    def _evento(self, r: RichiestaOrdine, rep: Any, size: float) -> EventoOrdine:
        if rep.status != "SUCCESS":
            return EventoOrdine(ref=r.ref, seq=0, fase="rifiutato", bet_id=None, abbinato=0.0,
                                residuo=0.0, prezzo_medio=None, codice_errore=rep.error_code,
                                esito_ms=self.betfair.orologio.ms)
        matched = float(rep.size_matched or 0.0)
        riga = {"status": rep.order_status, "size": size, "size_matched": matched,
                "bet_id": str(rep.bet_id) if rep.bet_id is not None else None,
                "size_lapsed": size - matched if rep.order_status == "EXPIRED" else 0.0}
        fase_motore = MO.fase_da_riga(riga)
        fase = {"accettato_betfair": "accettato", "abbinato_parziale": "parziale",
                "inviato": "accettato"}.get(fase_motore, fase_motore)
        return EventoOrdine(ref=r.ref, seq=0, fase=fase, bet_id=riga["bet_id"],
                            abbinato=matched,
                            residuo=round(size - matched, 2) if rep.order_status == "EXECUTABLE"
                            else 0.0,
                            prezzo_medio=float(rep.average_price_matched) if matched else None,
                            codice_errore=None, esito_ms=self.betfair.orologio.ms)

    def place(self, r: RichiestaOrdine) -> EventoOrdine:
        self.ricevute.append(r)
        if self.prima_della_chiamata is not None:
            self.prima_della_chiamata(r)
        lo = {"size": r.importo, "price": r.prezzo, "persistenceType": r.persistenza}
        if r.time_in_force:
            lo["timeInForce"] = r.time_in_force
        risp = self.betfair.place_orders(
            r.market_id, [{"selectionId": r.selection_id, "handicap": r.handicap,
                           "side": str(r.lato).upper(), "orderType": "LIMIT",
                           "limitOrder": lo}],
            customer_ref=r.ref, customer_strategy_ref=r.attore[:15])
        return self._evento(r, risp.place_instruction_reports[0], float(r.importo or 0.0))

    def cancel(self, r: RichiestaOrdine) -> EventoOrdine:
        self.ricevute.append(r)
        ins: Dict[str, Any] = {"betId": r.bet_id}
        if r.riduzione is not None:
            ins["sizeReduction"] = r.riduzione
        risp = self.betfair.cancel_orders(r.market_id, [ins], customer_ref=r.ref)
        rep = risp.cancel_instruction_reports[0]
        return EventoOrdine(ref=r.ref, seq=0, fase="annullato" if rep.status == "SUCCESS"
                            else "rifiutato", bet_id=r.bet_id, abbinato=0.0, residuo=0.0,
                            prezzo_medio=None, codice_errore=rep.error_code,
                            esito_ms=self.betfair.orologio.ms)

    def replace(self, r: RichiestaOrdine) -> EventoOrdine:
        self.ricevute.append(r)
        risp = self.betfair.replace_orders(r.market_id, [{"betId": r.bet_id,
                                                          "newPrice": r.nuovo_prezzo}],
                                           customer_ref=r.ref)
        rep = risp.replace_instruction_reports[0].place_instruction_reports
        return self._evento(r, rep, 2.0)


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------
class _Ambiente:
    def __init__(self, tmp: Any, *, proc: str = "LIVE", tetto: Optional[int] = None,
                 archivio: Optional[_ArchivioMemoria] = None, cartella: str = "diario",
                 orologio: Optional[_Orologio] = None) -> None:
        self.orologio = orologio or _Orologio()
        self.betfair = _BetfairFinto(self.orologio)
        self.esecutore = _EsecutoreBetfairFinto(self.betfair)
        self.archivio = archivio or _ArchivioMemoria()
        self.freni = _Freni(proc)
        self.cartella = str(tmp / cartella)
        self.diario = MO.Diario(self.cartella, giorno=lambda: GIORNO)
        self.contatore = CT.ContatoreTransazioni(tetto, self.orologio) if tetto is not None \
            else None
        self.porta = PT.PortaLocale(self.esecutore, freni=self.freni, archivio=self.archivio,
                                    diario=self.diario, contatore=self.contatore,
                                    orologio_ms=self.orologio)
        self.porta._giorni = lambda: [GIORNO]  # type: ignore[method-assign]
        self.porta.apri()

    def righe_diario(self) -> List[Dict[str, Any]]:
        return self.diario.leggi([GIORNO])


def _r(**k: Any) -> RichiestaOrdine:
    base: Dict[str, Any] = dict(ref="safe-t1", attore="safe", sport="calcio", modo="live",
                                azione="place", market_id="1.234", selection_id=47972,
                                lato="back", prezzo=2.5, importo=4.0, creato_ms=T0,
                                time_in_force="FILL_OR_KILL")
    base.update(k)
    return RichiestaOrdine(**base)


def test_la_porta_rispetta_il_protocollo(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    porta: PortaOrdini = amb.porta
    assert isinstance(porta.invia(_r()), Ack)


# ---------------------------------------------------------------------------
# (1) dedup per ref
# ---------------------------------------------------------------------------
def test_dedup_nella_stessa_vita(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a1 = amb.porta.invia(_r())
    amb.orologio.ms += 40_000                  # dentro la finestra di 60 s di Betfair
    a2 = amb.porta.invia(_r(creato_ms=amb.orologio.ms))
    amb.orologio.ms += 600_000                 # e ben oltre
    a3 = amb.porta.invia(_r(creato_ms=amb.orologio.ms, importo=9.0))
    assert a1.accettato and a1.motivo is None
    assert (a2.accettato, a2.seq, a2.motivo) == (True, a1.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert (a3.accettato, a3.seq, a3.motivo) == (True, a1.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert len(amb.betfair.chiamate) == 1      # MAI un secondo ordine


def test_dedup_dopo_il_riavvio_dall_archivio(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path, cartella="diario_1")
    a1 = prima.porta.invia(_r())
    rif = prima.porta.invia(_r(ref="safe-t2", importo=0.3))       # rifiuto registrato
    assert a1.accettato and not rif.accettato
    prima.porta.chiudi()
    # riavvio: RAM vuota, DIARIO NUOVO (cartella diversa), stesso archivio su disco
    dopo = _Ambiente(tmp_path, cartella="diario_2", archivio=prima.archivio,
                     orologio=_Orologio(T0 + 3_600_000))
    b1 = dopo.porta.invia(_r(creato_ms=dopo.orologio.ms))
    b2 = dopo.porta.invia(_r(ref="safe-t2", importo=4.0, creato_ms=dopo.orologio.ms))
    assert (b1.accettato, b1.seq, b1.motivo) == (True, a1.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert (b2.accettato, b2.seq, b2.motivo) == (False, rif.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert dopo.betfair.chiamate == []         # nessun ordine dopo il riavvio


def test_dedup_dopo_il_riavvio_dal_diario(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)
    a1 = prima.porta.invia(_r())
    prima.porta.chiudi()
    dopo = _Ambiente(tmp_path, orologio=_Orologio(T0 + 5_000))    # archivio NUOVO, stesso diario
    b1 = dopo.porta.invia(_r(creato_ms=dopo.orologio.ms))
    assert (b1.seq, b1.motivo) == (a1.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert dopo.betfair.chiamate == []


def test_archivio_illeggibile_fail_closed(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.archivio.guasto_lettura = True
    a = amb.porta.invia(_r())
    assert not a.accettato and a.motivo.startswith(PT.M_ARCHIVIO) and a.seq is None
    amb.archivio.guasto_lettura = False
    amb.archivio.guasto_scrittura = True
    b = amb.porta.invia(_r(ref="safe-t9"))
    assert not b.accettato and b.motivo.startswith(PT.M_ARCHIVIO)
    assert amb.betfair.chiamate == []


def test_ref_non_valido_non_registrato(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    for r in (_r(ref="omega-t1"), _r(ref="safe-"), _r(ref="safe-" + "x" * 30),
              _r(attore="sconosciuto", ref="sconosciuto-t1")):
        a = amb.porta.invia(r)
        assert not a.accettato and a.seq is None
    assert amb.betfair.chiamate == [] and not amb.archivio.tabelle.get(PT.TABELLA_REF)


# ---------------------------------------------------------------------------
# (2) ciclo di vita con le risposte vere
# ---------------------------------------------------------------------------
def test_ciclo_di_vita_con_le_risposte_vere(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.bet_delay_ms = 5_000          # in gioco: la risposta arriva dopo il delay
    amb.betfair.piano = ["PARZIALE", "EXPIRED", "FAILURE", "EXECUTION_COMPLETE"]
    a = amb.porta.invia(_r(ref="safe-t1", time_in_force=None, persistenza="PERSIST"))
    ev = list(amb.porta.eventi("safe", a.seq))
    assert [e.fase for e in ev] == ["parziale"]
    assert ev[0].bet_id == "312426000001" and (ev[0].abbinato, ev[0].residuo) == (1.0, 3.0)
    assert ev[0].esito_ms == T0 + 5_000 and ev[0].seq == a.seq + 1
    # il resto si abbina dopo: lo porta il flusso degli ordini
    fine = amb.porta.notifica(EventoOrdine(ref="safe-t1", seq=0, fase="abbinato",
                                           bet_id="312426000001", abbinato=4.0, residuo=0.0,
                                           prezzo_medio=2.5, codice_errore=None, esito_ms=None))
    assert fine is not None and fine.seq == a.seq + 2
    assert amb.porta.stato("safe-t1").fase == "abbinato"
    # un evento vecchio non terminale dopo il terminale: ignorato
    assert amb.porta.notifica(EventoOrdine(ref="safe-t1", seq=0, fase="parziale", bet_id=None,
                                           abbinato=1.0, residuo=3.0, prezzo_medio=None,
                                           codice_errore=None, esito_ms=None)) is None
    # FOK non abbinato: Betfair risponde orderStatus EXPIRED -> scaduto
    amb.orologio.ms += 1
    b = amb.porta.invia(_r(ref="safe-t2", creato_ms=amb.orologio.ms))
    assert amb.porta.stato("safe-t2").fase == "scaduto" and b.accettato
    assert amb.betfair.chiamate[-1]["instructions"][0]["limitOrder"]["timeInForce"] == \
        "FILL_OR_KILL"
    assert amb.betfair.chiamate[-1]["customer_strategy_ref"] == "safe"
    # rifiuto di Betfair: rifiutato col codice vero; la stessa taglia non si ritenta
    c = amb.porta.invia(_r(ref="safe-t3", creato_ms=amb.orologio.ms))
    st = amb.porta.stato("safe-t3")
    assert c.accettato and st.fase == "rifiutato"
    assert list(amb.porta.eventi("safe", c.seq))[0].codice_errore == "INVALID_BET_SIZE"
    d = amb.porta.invia(_r(ref="safe-t4", creato_ms=amb.orologio.ms))
    assert not d.accettato and d.motivo.startswith(MO.M_SOTTO_MINIMO)
    n = len(amb.betfair.chiamate)
    e = amb.porta.invia(_r(ref="safe-t5", importo=6.0, creato_ms=amb.orologio.ms))
    assert e.accettato and len(amb.betfair.chiamate) == n + 1
    assert amb.porta.stato("safe-t5").fase == "abbinato"


def test_cancel_e_replace(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    c = amb.porta.invia(_r(ref="safe-c31-50", azione="cancel", bet_id="31", riduzione=0.5,
                           lato=None, prezzo=None, importo=None, time_in_force=None,
                           selection_id=0))
    assert c.accettato and amb.porta.stato("safe-c31-50").fase == "annullato"
    assert amb.betfair.chiamate[-1]["instructions"] == [{"betId": "31", "sizeReduction": 0.5}]
    r = amb.porta.invia(_r(ref="safe-r31", azione="replace", bet_id="31", nuovo_prezzo=2.62,
                           lato=None, prezzo=None, importo=None, time_in_force=None))
    assert r.accettato and amb.porta.stato("safe-r31").bet_id == "999"


def test_minimi_punta_050_e_sotto_minimo(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    a = amb.porta.invia(_r(ref="safe-t1", importo=7.27))
    assert a.accettato and amb.esecutore.ricevute[-1].importo == 7.0
    ev = list(amb.porta.eventi("safe", a.seq))[0]
    assert ev.punta_050 == {"chiesto": 7.27, "piazzato": 7.0, "residuo": 0.27,
                            "motivo": "punta .it diretta solo a multipli di 0,50: "
                                      "arrotondata per difetto, residuo NON piazzato"}
    for ref, imp in (("safe-t2", 0.7), ("safe-t3", 0.3)):
        b = amb.porta.invia(_r(ref=ref, importo=imp, lato="lay"))
        assert not b.accettato and b.motivo.startswith(MO.M_SOTTO_MINIMO + ": ")
    assert len(amb.esecutore.ricevute) == 1


# ---------------------------------------------------------------------------
# (3) esito ignoto: mai ok, mai ritentato
# ---------------------------------------------------------------------------
def test_esito_ignoto_mai_ok_mai_ritentato(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.betfair.piano = [TimeoutError("read timeout dopo placeOrders")]
    a = amb.porta.invia(_r())
    assert a.accettato                          # il comando e' partito: esito da riconciliare
    st = amb.porta.stato("safe-t1")
    assert st.fase == "ignoto" and st.bet_id is None
    ev = list(amb.porta.eventi("safe", a.seq))
    assert [(e.fase, e.codice_errore) for e in ev] == [("ignoto", PT.CODICE_ESITO_IGNOTO)]
    assert len(amb.betfair.chiamate) == 1       # UNA chiamata: nessun ritento
    b = amb.porta.invia(_r(creato_ms=T0))       # il bot ripete: dedup, nessun ordine
    assert b.motivo == MO.MOTIVO_REF_GIA_VISTO and len(amb.betfair.chiamate) == 1
    assert amb.porta.conti["ignoti"] == 1


# ---------------------------------------------------------------------------
# (4) da_seq: un push perso si ripara
# ---------------------------------------------------------------------------
def test_push_scartato_di_proposito_riparato_con_da_seq(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    cons = ConsumatoreEventi("safe", sorgente=amb.porta)
    ricevuti: List[int] = []

    def _push(m: Any) -> None:
        ricevuti.append(m.seq)
        if len(ricevuti) == 2:                 # il canale "salta il giro": perso
            return
        cons.ricevi(m)

    amb.porta.aggiungi_consumatore("safe", _push)
    amb.betfair.piano = ["PARZIALE", "EXECUTABLE"]
    a = amb.porta.invia(_r(ref="safe-t1"))     # ack (seq n), evento parziale (n+1) PERSO
    assert cons.ultimo("safe-t1") is None      # il consumatore non l'ha visto
    amb.porta.invia(_r(ref="safe-t2"))         # ack (n+2): buco -> da_seq
    assert cons.richieste_da_seq == 1
    ev = cons.ultimo("safe-t1")
    assert ev is not None and ev.fase == "parziale" and ev.seq == a.seq + 1
    assert cons.seq_visto == amb.porta._seq["safe"] and cons.buchi_non_colmati == 0


def test_da_seq_memoria_superata_non_colmabile(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.porta._memoria_max = 3
    amb.porta._memoria.clear()
    for i in range(4):
        amb.porta.invia(_r(ref=f"safe-t{i}"))
    risposta = amb.porta.da_seq("safe", amb.porta._base_seq)
    assert not risposta.completo and len(risposta.messaggi) == 3
    cons = ConsumatoreEventi("safe", sorgente=amb.porta)
    cons.ricevi(Ack(ref="safe-t0", accettato=True, seq=amb.porta._base_seq + 1, motivo=None))
    cons.ricevi(risposta.messaggi[-1])          # salto: buco oltre la memoria
    assert cons.buchi_non_colmati == 1 and cons.seq_visto == amb.porta._seq["safe"]


# ---------------------------------------------------------------------------
# modo della riga, freni, diario, tetto, riavvio con ordine in volo
# ---------------------------------------------------------------------------
def test_modo_della_riga_mai_del_servizio(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path, proc="PAPER")
    live = amb.porta.invia(_r(ref="safe-t1", modo="live"))
    paper = amb.porta.invia(_r(ref="safe-t2", modo="paper"))
    assert not live.accettato and live.motivo.startswith(MO.M_MODE)
    assert paper.accettato and [r.modo for r in amb.esecutore.ricevute] == ["paper"]


def test_kill_switch_ferma_le_aperture_non_le_chiusure(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    amb.freni.kill = True
    a = amb.porta.invia(_r(ref="safe-t1"))
    c = amb.porta.invia(_r(ref="safe-c31", azione="cancel", bet_id="31", lato=None,
                           prezzo=None, importo=None, time_in_force=None))
    assert not a.accettato and a.motivo.startswith(MO.M_KILL)
    assert c.accettato and [r.azione for r in amb.esecutore.ricevute] == ["cancel"]
    # una riduzione DICHIARATA non verificata non scavalca il kill-switch
    d = amb.porta.invia(_r(ref="safe-t2", riduce_esposizione=True))
    assert not d.accettato and d.motivo.startswith(MO.M_RIDUZIONE)


def test_diario_write_ahead_prima_dell_esecutore(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    visto: List[bool] = []

    def _controlla_disco(r: RichiestaOrdine) -> None:
        # dentro l'esecutore: la riga ``inviato`` e' GIA' sul disco (rilettura dal file)
        with open(os.path.join(amb.cartella, f"{GIORNO}.jsonl"), encoding="ascii") as fh:
            righe = [json.loads(x) for x in fh if x.strip()]
        visto.append(any(x.get("tipo") == "inviato" and x.get("ref") == r.ref for x in righe))

    amb.esecutore.prima_della_chiamata = _controlla_disco
    amb.porta.invia(_r())
    assert visto == [True]
    tipi = [x["tipo"] for x in amb.righe_diario()]
    assert tipi == ["inviato", "esito"]


def test_diario_non_scrivibile_niente_ordine(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    amb = _Ambiente(tmp_path)

    def _rotto(record: Dict[str, Any], *, durevole: bool = True) -> None:
        raise OSError("disco pieno")

    monkeypatch.setattr(amb.diario, "scrivi", _rotto)
    a = amb.porta.invia(_r())
    assert not a.accettato and a.motivo.startswith(MO.M_DIARIO)
    assert amb.betfair.chiamate == []
    assert amb.porta.invia(_r()).motivo == MO.MOTIVO_REF_GIA_VISTO


def test_tetto_transazioni_uno_per_conto_su_piu_attori(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path, tetto=2)
    esiti = [amb.porta.invia(_r(ref=f"{a}-t1", attore=a)) for a in ("safe", "omega", "mike")]
    assert all(x.accettato for x in esiti)       # 3 piazzati: totale 3 > tetto 2
    quarto = amb.porta.invia(_r(ref="safe_tennis-t1", attore="safe_tennis", sport="tennis"))
    assert not quarto.accettato and quarto.motivo.startswith(CT.CODICE_TETTO)
    assert amb.contatore.stato()["per_attore"] == {"safe": 1, "omega": 1, "mike": 1}


def test_riavvio_con_ordine_in_volo(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)

    class _Crollo(BaseException):
        """Il processo muore DENTRO la chiamata a Betfair (non e' un'eccezione gestita)."""

    def _muore(_r: RichiestaOrdine) -> None:
        raise _Crollo()

    prima.esecutore.prima_della_chiamata = _muore
    with pytest.raises(_Crollo):
        prima.porta.invia(_r())
    dopo = _Ambiente(tmp_path, archivio=prima.archivio, orologio=_Orologio(T0 + 1_000))
    assert dopo.porta.in_volo() == ("safe-t1",)
    assert dopo.porta.stato("safe-t1").fase == "ignoto"
    assert dopo.porta.invia(_r(creato_ms=T0 + 1_000)).motivo == MO.MOTIVO_REF_GIA_VISTO
    assert dopo.betfair.chiamate == []


def test_seq_mai_indietro_dopo_il_riavvio(tmp_path: Any) -> None:
    prima = _Ambiente(tmp_path)
    a = prima.porta.invia(_r(ref="safe-t1"))
    dopo = _Ambiente(tmp_path, cartella="d2", orologio=_Orologio(T0 + 10))
    b = dopo.porta.invia(_r(ref="safe-t2", creato_ms=T0 + 10))
    assert b.seq > a.seq + 1


def test_azione_composta_sopra_la_porta(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    g = AC.RichiestaComposta(ref="safe-g1", attore="safe", sport="calcio", modo="live",
                             azione="greenup", market_id="1.234", selection_id=1, creato_ms=T0)
    a = amb.porta.invia(g)
    assert not a.accettato and a.motivo.startswith(PT.M_COMPOSTA) and a.seq is not None
    assert amb.esecutore.ricevute == []


def test_posizione_delegata_a_c2(tmp_path: Any) -> None:
    amb = _Ambiente(tmp_path)
    with pytest.raises(NotImplementedError):
        amb.porta.posizione("1.234")


def test_seq_per_attore_contiguo_con_traffico_di_altri(tmp_path: Any) -> None:
    """UN contatore per attore (motore ``_prossimo_seq``): il traffico di omega non apre
    buchi nel flusso di safe."""
    amb = _Ambiente(tmp_path)
    cons = ConsumatoreEventi("safe", sorgente=None)
    amb.porta.aggiungi_consumatore("safe", cons.ricevi)
    for i in range(5):
        amb.porta.invia(_r(ref=f"safe-t{i}"))
        amb.porta.invia(_r(ref=f"omega-t{i}", attore="omega"))
    assert cons.buchi == 0 and cons.conti["ack"] == 5 and cons.conti["eventi"] == 5


def test_stesso_ref_da_piu_thread_un_solo_ordine(tmp_path: Any) -> None:
    """Concorrenza (PSB 6.6): 8 thread mandano lo stesso ref insieme -> UN ordine."""
    import threading

    amb = _Ambiente(tmp_path)
    amb.archivio.ritardo_lettura_s = 0.02     # la finestra fra controllo e registrazione
    via = threading.Barrier(8)
    acks: List[Ack] = []

    def _manda() -> None:
        via.wait()
        acks.append(amb.porta.invia(_r()))

    th = [threading.Thread(target=_manda) for _ in range(8)]
    for t in th:
        t.start()
    for t in th:
        t.join(10)
    assert len(acks) == 8 and len(amb.betfair.chiamate) == 1
    assert len({a.seq for a in acks}) == 1 and all(a.accettato for a in acks)
    assert sum(a.motivo == MO.MOTIVO_REF_GIA_VISTO for a in acks) == 7
