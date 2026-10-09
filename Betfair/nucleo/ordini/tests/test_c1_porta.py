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
  * archivio (integrazione W1-G1 + W1-C1, 09/10): OGNI test gira DUE volte (fixture
    ``archivio_parametrico``): con ``_ArchivioMemoria``, il finto col protocollo
    ``nucleo/dati/contratto.Archivio`` che sopravvive alla porta (simula il disco al
    riavvio), e con l'``ArchivioLocale`` VERO di W1-G1 su una cartella temporanea
    (``_ArchivioVero``: aperto e chiuso dalla fixture, tabelle della porta dichiarate in
    ``registro.TABELLE_SOLO_LOCALI``; al riavvio si CHIUDE e si RIAPRE sulla stessa
    cartella). Il finto ha la semantica del vero, anche nei guasti (vedi le due classi).

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
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Union

import pytest
from betfairlightweight.resources.bettingresources import (CancelOrders, PlaceOrders,
                                                           ReplaceOrders)

from Betfair.nucleo.dati import archivio as ARCH
from Betfair.nucleo.dati.archivio import ArchivioChiuso, ArchivioLocale
from Betfair.nucleo.dati.registro import TABELLE_SOLO_LOCALI
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
    """Il protocollo ``Archivio`` in memoria con la SEMANTICA VERA di ``ArchivioLocale``
    (W1-G1, ``Betfair/nucleo/dati/archivio.py``): ``scrivi`` = upsert che FONDE le colonne
    per chiave naturale; ``leggi`` = l'ultima versione (anche se non ancora su disco) o None;
    ``transizione`` = la ``colonna_stato`` (di serie ``"status"``) passa da ``da`` ad ``a``
    SOLO su una riga ESISTENTE che vale ``da``: riga assente -> False (provato da
    ``test_contratto_del_finto_transizione_come_il_vero``, che gira anche sul vero).
    ``cartella`` come il vero (una per istanza). Righe in JSON e ritorno (tipi del vero).

    Guasti, con gli effetti del vero (integrazione del 09/10, INTEGRAZIONE.md par. 3):
      * ``guasto_lettura``: il lettore fallisce -> ``leggi`` solleva (il vero:
        ``sqlite3.OperationalError``);
      * ``guasto_scrittura`` (disco che rifiuta i commit): ``scrivi`` NON solleva (il vero
        accoda e il suo thread ritenta finche' il disco torna; ``leggi`` vede la riga in
        coda); ``transizione`` (sincrona) ASPETTA che il disco torni, poi l'esito vero;
      * ``chiudi()``: archivio chiuso -> ``leggi``/``scrivi``/``transizione`` sollevano
        ``ArchivioChiuso`` (l'UNICO modo in cui lo ``scrivi`` del vero solleva, oltre a una
        tabella non registrata: ``KeyError``);
      * ``ritardo_lettura_s`` simula una lettura che viaggia (fotografia, poi latenza)."""

    _N = 0

    def __init__(self, colonna_stato: str = "status") -> None:
        _ArchivioMemoria._N += 1
        self.cartella = f"/finto/archivio-{_ArchivioMemoria._N}"
        self.colonna_stato = colonna_stato
        self._righe: Dict[str, Dict[str, str]] = {}
        self.guasto_lettura = False
        self.guasto_scrittura = False
        self.ritardo_lettura_s = 0.0
        self.letture = 0
        self._aperto = True
        self._lock = threading.Lock()

    @property
    def aperto(self) -> bool:
        return self._aperto

    def chiudi(self) -> None:
        self._aperto = False

    def _controlla(self, tabella: str) -> None:
        if tabella not in TABELLE_SOLO_LOCALI:
            raise KeyError(f"tabella non registrata nell'archivio: {tabella}")
        if not self._aperto:
            raise ArchivioChiuso("archivio finto non aperto")

    @staticmethod
    def _k(tabella: str, valori: Mapping[str, Any]) -> str:
        return json.dumps([valori[c] for c in TABELLE_SOLO_LOCALI[tabella].chiave_naturale])

    @property
    def tabelle(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Le righe per tabella (come le vede il disco a fine coda)."""
        with self._lock:
            return {t: {k: json.loads(j) for k, j in d.items()} for t, d in self._righe.items() if d}

    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        self._controlla(tabella)
        if self.guasto_lettura:
            raise sqlite3.OperationalError("disk I/O error")
        with self._lock:
            self.letture += 1
            testo = self._righe.get(tabella, {}).get(self._k(tabella, chiave))
        if self.ritardo_lettura_s:
            time.sleep(self.ritardo_lettura_s)
        return None if testo is None else json.loads(testo)

    def scrivi(self, tabella: str, riga: Mapping[str, Any]) -> None:
        self._controlla(tabella)
        with self._lock:                               # col disco guasto: in coda, visibile
            t = self._righe.setdefault(tabella, {})
            k = self._k(tabella, riga)
            prima = json.loads(t[k]) if k in t else {}
            t[k] = json.dumps({**prima, **dict(riga)})  # fusione delle colonne (upsert)

    def transizione(self, tabella: str, chiave: Mapping[str, Any], da: str, a: str) -> bool:
        self._controlla(tabella)
        while self.guasto_scrittura:                   # sincrona: aspetta il disco
            time.sleep(0.01)
        with self._lock:
            t = self._righe.setdefault(tabella, {})
            k = self._k(tabella, chiave)
            if k not in t:
                return False
            riga = json.loads(t[k])
            if riga.get(self.colonna_stato) != da:
                return False
            riga[self.colonna_stato] = a
            t[k] = json.dumps(riga)
            return True


class _ArchivioVero(ArchivioLocale):
    """L'``ArchivioLocale`` VERO di W1-G1 con il registro VUOTO: le tabelle della porta le
    legge da ``registro.TABELLE_SOLO_LOCALI`` (regime ``stato_denaro``, FULL, mai il
    cloud). Aggiunge SOLO gli interruttori di guasto del finto, iniettati nel punto in cui
    il vero incontra il guasto (il resto e' il codice vero):
      * ``guasto_lettura``: il lettore SQLite fallisce (``_leggi_uno``);
      * ``guasto_scrittura``: i commit del file ``denaro`` falliscono con l'errore del disco
        pieno (``_unita_sqlite``): il thread di scrittura ritenta finche' torna;
      * ``ritardo_lettura_s``: latenza dopo la lettura; ``letture``: conteggio;
      * ``tabelle``: le righe su disco dopo ``conferma`` (stessa forma del finto)."""

    def __init__(self, processo: str, *, base: Any, colonna_stato: str = "status") -> None:
        super().__init__(processo, {}, base=base, colonna_stato=colonna_stato)
        self.base = base
        self.colonna_stato = colonna_stato
        self.guasto_lettura = False
        self.guasto_scrittura = False
        self.ritardo_lettura_s = 0.0
        self.letture = 0
        self._lock_letture = threading.Lock()

    def _leggi_uno(self, regime: str, sql: str, args: Any) -> Any:
        if self.guasto_lettura:
            raise sqlite3.OperationalError("disk I/O error")
        return super()._leggi_uno(regime, sql, args)

    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        riga = super().leggi(tabella, chiave)
        with self._lock_letture:
            self.letture += 1
        if self.ritardo_lettura_s:
            time.sleep(self.ritardo_lettura_s)
        return riga

    def _unita_sqlite(self, regime: str, voci: List[Any]) -> Any:
        if self.guasto_scrittura and regime == "stato_denaro":
            raise sqlite3.OperationalError("database or disk is full")
        return super()._unita_sqlite(regime, voci)

    @property
    def tabelle(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        assert self.conferma(10.0), "archivio vero: coda non scritta entro 10 s"
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for t in TABELLE_SOLO_LOCALI:
            righe = self.righe_finestra(t, 0, None)
            if righe:
                out[t] = {k: json.loads(j) for k, j in righe}
        return out


ArchivioDiProva = Union[_ArchivioMemoria, _ArchivioVero]

#: quale archivio usano ``_Ambiente`` e ``_nuovo_archivio`` nel test in corso (fixture)
_FABBRICA: Dict[str, Any] = {"tipo": "finto", "base": None, "aperti": [], "n": 0}


def _nuovo_archivio(colonna_stato: str = "status") -> ArchivioDiProva:
    """Un archivio NUOVO (vuoto) del tipo del test in corso; il vero e' gia' aperto."""
    if _FABBRICA["tipo"] == "finto":
        return _ArchivioMemoria(colonna_stato)
    _FABBRICA["n"] += 1
    a = _ArchivioVero(f"porta-{_FABBRICA['n']}", base=_FABBRICA["base"], colonna_stato=colonna_stato)
    _FABBRICA["aperti"].append(a)
    return a.apri()


def _riavviato(archivio: ArchivioDiProva) -> ArchivioDiProva:
    """Il processo riparte con lo STESSO archivio su disco: il finto (che simula il disco)
    resta lo stesso oggetto; il vero si CHIUDE (coda scritta) e si RIAPRE sulla stessa
    cartella: le righe tornano dal file."""
    if isinstance(archivio, _ArchivioMemoria):
        return archivio
    archivio.chiudi()
    nuovo = _ArchivioVero(archivio.processo, base=archivio.base, colonna_stato=archivio.colonna_stato)
    _FABBRICA["aperti"].append(nuovo)
    return nuovo.apri()


def _gemello(archivio: ArchivioDiProva) -> ArchivioDiProva:
    """Un ALTRO oggetto archivio sulla STESSA cartella (non aperto)."""
    if isinstance(archivio, _ArchivioMemoria):
        g = _ArchivioMemoria(archivio.colonna_stato)
        g.cartella = archivio.cartella
        return g
    return _ArchivioVero(archivio.processo, base=archivio.base, colonna_stato=archivio.colonna_stato)


@pytest.fixture(params=["finto", "vero"], autouse=True)
def archivio_parametrico(request: Any, tmp_path_factory: Any,
                         monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """OGNI test della porta con l'archivio finto e con l'``ArchivioLocale`` VERO di W1-G1
    (cartella temporanea, chiuso alla fine). Col vero il ritento dopo un guasto del disco
    parte dopo 10 ms invece di 0,5 s (``ATTESA_RITENTO_BASE_S``): solo la velocita' del test."""
    monkeypatch.setitem(_FABBRICA, "tipo", request.param)
    monkeypatch.setitem(_FABBRICA, "base", tmp_path_factory.mktemp("archivi"))
    monkeypatch.setitem(_FABBRICA, "aperti", [])
    monkeypatch.setattr(ARCH, "ATTESA_RITENTO_BASE_S", 0.01)
    try:
        yield request.param
    finally:
        for a in _FABBRICA["aperti"]:
            a.guasto_scrittura = False
            a.guasto_lettura = False
            a.chiudi(timeout_s=10.0)


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
                 archivio: Optional[ArchivioDiProva] = None, cartella: str = "diario",
                 orologio: Optional[_Orologio] = None) -> None:
        self.orologio = orologio or _Orologio()
        self.betfair = _BetfairFinto(self.orologio)
        self.esecutore = _EsecutoreBetfairFinto(self.betfair)
        self.archivio = archivio if archivio is not None else _nuovo_archivio()
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
    dopo = _Ambiente(tmp_path, cartella="diario_2", archivio=_riavviato(prima.archivio),
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
    # archivio CHIUSO (app in chiusura): leggi e scrivi sollevano ArchivioChiuso -> fail-closed
    amb.archivio.chiudi()
    b = amb.porta.invia(_r(ref="safe-t9"))
    assert not b.accettato and b.motivo.startswith(PT.M_ARCHIVIO) and b.seq is None
    assert amb.betfair.chiamate == []


def test_disco_dell_archivio_guasto_l_ordine_parte_e_il_dedup_regge(tmp_path: Any) -> None:
    """Semantica VERA di W1-G1 (integrazione del 09/10): col disco dell'archivio che rifiuta
    i commit, ``scrivi`` NON solleva (accoda; il thread di scrittura ritenta finche' il disco
    torna) e ``leggi`` vede la riga in coda. Il write-ahead durevole e' il DIARIO: l'ordine
    parte una volta, il ref ripetuto risponde l'ack originale, e quando il disco torna la
    riga del ref e' sul file. (Il finto della consegna di C1 faceva sollevare ``scrivi``:
    differenza col vero, corretta nel finto.)"""
    amb = _Ambiente(tmp_path)
    amb.archivio.guasto_scrittura = True
    a = amb.porta.invia(_r(ref="safe-t9"))
    b = amb.porta.invia(_r(ref="safe-t9"))
    assert a.accettato and a.motivo is None and len(amb.betfair.chiamate) == 1
    assert (b.accettato, b.seq, b.motivo) == (True, a.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert len(amb.betfair.chiamate) == 1
    amb.archivio.guasto_scrittura = False
    riga = amb.archivio.tabelle[PT.TABELLA_REF]
    assert [(x["ref"], x["accettato"], x["seq"]) for x in riga.values()] == [("safe-t9", True, a.seq)]


def test_le_tabelle_della_porta_sono_le_solo_locali_del_registro() -> None:
    """Integrazione W1-G1 + W1-C1: i nomi che la porta usa sono quelli dichiarati SOLO LOCALI
    (regime stato_denaro, mai il cloud) nel registro, con le chiavi che la porta scrive."""
    assert {PT.TABELLA_REF, PT.TABELLA_SEQ} == set(TABELLE_SOLO_LOCALI)
    assert TABELLE_SOLO_LOCALI[PT.TABELLA_REF].chiave_naturale == ("ref",)
    assert TABELLE_SOLO_LOCALI[PT.TABELLA_SEQ].chiave_naturale == ("chiave",)
    assert all(s.regime == "stato_denaro" for s in TABELLE_SOLO_LOCALI.values())


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
    b = amb.porta.invia(_r(creato_ms=T0))       # il bot ripete: nessun nuovo ordine
    # parita' col motore: l'ack ORIGINALE (accettato e seq), motivo ref_gia_visto
    assert (b.accettato, b.seq, b.motivo) == (True, a.seq, MO.MOTIVO_REF_GIA_VISTO)
    assert amb.porta.stato("safe-t1").fase == "ignoto"   # lo stato resta da riconciliare
    assert len(amb.betfair.chiamate) == 1
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
    seq_prima = prima.porta._visti["safe-t1"].seq   # il seq dato col primo invio
    prima.porta.chiudi()                         # il processo e' morto: archivio libero
    dopo = _Ambiente(tmp_path, archivio=_riavviato(prima.archivio), orologio=_Orologio(T0 + 1_000))
    assert dopo.porta.in_volo() == ("safe-t1",)
    assert dopo.porta.stato("safe-t1").fase == "ignoto"
    b = dopo.porta.invia(_r(creato_ms=T0 + 1_000))
    # parita' col motore: l'ack ORIGINALE dal diario (accettato, stesso seq), 0 invii;
    # lo stato resta ignoto finche' la riconciliazione per ref non lo chiude
    assert (b.accettato, b.seq, b.motivo) == (True, seq_prima, MO.MOTIVO_REF_GIA_VISTO)
    assert dopo.porta.stato("safe-t1").fase == "ignoto"
    assert dopo.porta.in_volo() == ("safe-t1",)
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
