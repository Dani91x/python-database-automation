"""W1-G1 - prove della TERZA revisione (09/10, "PASSA con 4 riserve").

Principio vincolante (coordinatore): IDENTICO A OGGI. Oggi vince l'ultima scrittura fatta
dal bot e nessuna scrittura viene scartata; la versione serve SOLO a impedire che una voce
VECCHIA della STESSA origine (ritento del postino, rientro da dead_letter, voce ripetuta
dopo un crash) sovrascriva una voce piu' nuova della stessa origine.

R1 versione LOCALE (vseq per file, persistita) al posto dell'orologio del bot; R2 rientro
delle dead_letter che non riporta indietro il cloud, archiviazione dopo N rientri,
conservazione; R3 ``errore_di_dato`` ristretto, guasto del codice che non scarta;
R4 disco guasto per 3+ tentativi a processo vivo. Client supabase VERO su MockTransport
(``test_g1_finti``), orologio comandato. Materiale del revisore: scratchpad/rev_w1g1_2
(m3.py, dl_stale.py, disco_guasto.py), asserzioni riportate qui.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import Betfair.nucleo.dati.archivio as mod  # noqa: E402
from Betfair.nucleo.dati.archivio import (RIENTRI_MAX_DATO, ArchivioLocale, errore_di_codice,  # noqa: E402
                                          errore_di_dato)
from Betfair.nucleo.dati.contratto import SpecTabella  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale, StatoPostinoArchivio  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto, riga_ordine  # noqa: E402

T0 = 1_760_004_000_000
ORDINE = {"mode": "paper", "client_order_ref": "r1"}


class Nodo:
    """Un processo: archivio (cartella propria) + postino sullo STESSO cloud finto."""

    def __init__(self, base: Path, server: PostgrestFinto, ora: List[int], spec: Optional[Dict[str, Any]] = None,
                 **kw: Any) -> None:
        self.eventi: List[Tuple[str, Dict[str, Any]]] = []
        self.archivio = ArchivioLocale("prova", spec or SPEC, base=base, orologio_ms=lambda: ora[0],
                                       eventi=lambda n, d: self.eventi.append((n, dict(d)))).apri()
        self.postino = PostinoLocale(self.archivio, CloudProva(server), orologio_ms=lambda: ora[0],
                                     eventi=lambda n, d: self.eventi.append((n, dict(d))), **kw)

    def nomi(self) -> List[str]:
        return [n for n, _ in self.eventi]


@pytest.fixture
def ora() -> List[int]:
    return [T0]


def _cloud(srv: PostgrestFinto) -> List[Tuple[Any, Any]]:
    return [(r["status"], r["updated_at"]) for r in srv.tabelle["betfair_live_orders"].righe]


# ============================================================================ R1
def test_R1_orologio_indietro_115_s_execution_complete_arriva_locale_e_cloud(tmp_path: Path, ora: List[int]) -> None:
    """m3.py scenario 4: dopo un riavvio l'orologio del PC e' 115 s indietro. Prima della
    terza revisione EXECUTION_COMPLETE era scartato (stantio) in locale e nel cloud."""
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    try:
        a, p = n.archivio, n.postino
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:02:00.000000+00:00"))
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T10:00:05.000000+00:00"))
        assert a.conferma() and p.drena().errore is None
        assert a.leggi("betfair_live_orders", ORDINE)["status"] == "EXECUTION_COMPLETE"
        assert _cloud(srv) == [("EXECUTION_COMPLETE", "2026-10-09T10:00:05.000000+00:00")]   # tale e quale
        assert "dati.riga_vecchia" not in n.nomi() and p.contatori["vecchie"] == 0
    finally:
        n.archivio.chiudi()


def test_R1_esito_vecchio_di_3_s_scritto_dopo_vince_con_updated_at_tale_e_quale(tmp_path: Path,
                                                                               ora: List[int]) -> None:
    """m3.py scenario 1: oggi vince l'ultimo upsert; nessun +1 us sulla colonna del bot."""
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    try:
        a, p = n.archivio, n.postino
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T10:00:03.000000+00:00",
                                                    size_matched=2.0))
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00.000000+00:00",
                                                    size_matched=0.0))
        assert a.conferma() and p.drena().errore is None
        locale = a.leggi("betfair_live_orders", ORDINE)
        assert (locale["status"], locale["updated_at"]) == ("EXECUTABLE", "2026-10-09T10:00:00.000000+00:00")
        assert _cloud(srv) == [("EXECUTABLE", "2026-10-09T10:00:00.000000+00:00")]
        assert srv.tabelle["betfair_live_orders"].righe[0]["size_matched"] == 0.0
    finally:
        n.archivio.chiudi()


def test_R1_ritento_di_una_voce_gia_superata_della_stessa_origine_scartato(tmp_path: Path, ora: List[int]) -> None:
    """Voce ripetuta dopo un crash (la stessa voce torna in outbox dopo che una piu' nuova
    della stessa origine e' gia' arrivata): il cloud la scarta, "vecchia", con un evento."""
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    try:
        a, p = n.archivio, n.postino
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        assert a.conferma()
        prima = a.outbox_pronta("stato_denaro", 2 ** 62, 10)[0]
        assert p.drena().consegnate == 1
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T09:59:00+00:00"))
        assert a.conferma() and p.drena().consegnate == 1
        # la prima voce ricompare in outbox con la SUA vseq (come dopo un crash fra cloud e conferma)
        a._esegui_sincrono("stato_denaro", lambda c: c.execute(
            "INSERT INTO outbox (tabella, op, chiave, json, creato_ms, vseq) VALUES (?, ?, ?, ?, ?, ?)",
            (prima.tabella, prima.op, prima.chiave, prima.testo, prima.creato_ms, prima.vseq)))
        e = p.drena()
        assert e.consegnate == 1 and p.contatori["vecchie"] == 1
        assert _cloud(srv) == [("EXECUTION_COMPLETE", "2026-10-09T09:59:00+00:00")]
        assert [d["vseq"] for nm, d in n.eventi if nm == "dati.riga_vecchia"] == [prima.vseq]
        assert p.stato().in_coda == 0
    finally:
        n.archivio.chiudi()


def test_R1_due_processi_vince_l_ultima_arrivata(tmp_path: Path, ora: List[int]) -> None:
    """m3.py scenario 2: due processi (stesso nome, due cartelle = due origini). Fra origini
    diverse vince l'ultima arrivata, come oggi; il ritento vecchio di A resta scartato."""
    srv = PostgrestFinto()
    na, nb = Nodo(tmp_path / "a", srv, ora), Nodo(tmp_path / "b", srv, ora)
    try:
        assert na.archivio.origine("stato_denaro") != nb.archivio.origine("stato_denaro")
        na.archivio.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T10:00:03+00:00"))
        nb.archivio.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        assert na.archivio.conferma() and nb.archivio.conferma()
        voce_a = na.archivio.outbox_pronta("stato_denaro", 2 ** 62, 10)[0]
        assert na.postino.drena().consegnate == 1 and nb.postino.drena().consegnate == 1
        assert _cloud(srv) == [("EXECUTABLE", "2026-10-09T10:00:00+00:00")]        # B arrivata per ultima
        na.archivio.scrivi("betfair_live_orders", riga_ordine("r1", "CANCELLED", "2026-10-09T10:00:01+00:00"))
        assert na.archivio.conferma() and na.postino.drena().consegnate == 1
        assert _cloud(srv) == [("CANCELLED", "2026-10-09T10:00:01+00:00")]         # ora A arrivata per ultima
        # il ritento della prima voce di A (superata dalla stessa A) non riporta indietro il cloud
        na.archivio._esegui_sincrono("stato_denaro", lambda c: c.execute(
            "INSERT INTO outbox (tabella, op, chiave, json, creato_ms, vseq) VALUES (?, ?, ?, ?, ?, ?)",
            (voce_a.tabella, voce_a.op, voce_a.chiave, voce_a.testo, voce_a.creato_ms, voce_a.vseq)))
        assert na.postino.drena().consegnate == 1 and na.postino.contatori["vecchie"] == 1
        assert _cloud(srv) == [("CANCELLED", "2026-10-09T10:00:01+00:00")]
    finally:
        na.archivio.chiudi()
        nb.archivio.chiudi()


def test_R1_vseq_persistita_mai_riusata_anche_dopo_pulizia_e_riapertura(tmp_path: Path, ora: List[int]) -> None:
    """La vseq riparte dall'alto anche se righe e outbox sono vuote (pulite, consegnate):
    una vseq riusata sarebbe "vecchia" per il cloud e una scrittura NUOVA si perderebbe."""
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    a = n.archivio
    for i in range(5):
        a.scrivi("live_follow", {"event_id": f"e{i}", "status": "NEW", "updated_at": "2026-10-09T10:00:00+00:00"})
    assert a.conferma() and n.postino.drena().consegnate == 5
    origine = a.origine("stato_vivo")
    a._esegui_sincrono("stato_vivo", lambda c: c.execute("DELETE FROM righe"))     # come dopo la pulizia
    a.chiudi()
    b = ArchivioLocale("prova", SPEC, base=tmp_path, orologio_ms=lambda: ora[0]).apri()
    try:
        assert b.origine("stato_vivo") == origine
        b.scrivi("live_follow", {"event_id": "e0", "status": "OLD", "updated_at": "2026-10-09T09:00:00+00:00"})
        assert b.conferma()
        assert b.outbox_pronta("stato_vivo", 2 ** 62, 10)[0].vseq == 6
        assert PostinoLocale(b, CloudProva(srv), orologio_ms=lambda: ora[0]).drena().consegnate == 1
        assert {r["event_id"]: r["status"] for r in srv.tabelle["live_follow"].righe}["e0"] == "OLD"
    finally:
        b.chiudi()


# ============================================================================ R2
SPEC_DL = dict(SPEC)
# dl_stale.py del revisore: live_alerts come tabella CMD di STATO senza rev_colonna (FK su live_follow)
SPEC_DL["live_alerts"] = SpecTabella("live_alerts", ("uid",), "CMD", "stato_vivo", 5.0, False, None, ("live_follow",))
UID = "00000000-0000-0000-0000-000000000001"


def _dl_stale(tmp_path: Path, ora: List[int]) -> Tuple[Nodo, PostgrestFinto]:
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora, spec=SPEC_DL, tetto_tentativi_riga=3)
    a, p = n.archivio, n.postino
    a.scrivi("live_alerts", {"uid": UID, "level": "INFO", "code": "c", "message": "VECCHIO", "event_id": "padre"})
    assert a.conferma()
    for _ in range(4):
        p.drena()
        ora[0] += 61_000
    assert [d["motivo"] for d in a.dead_letter()] == ["transitorio"]
    a.scrivi("live_alerts", {"uid": UID, "level": "INFO", "code": "c", "message": "NUOVO", "event_id": None})
    assert a.conferma()
    for _ in range(3):
        p.drena()
        ora[0] += 1000
    assert [(r["message"], r["event_id"]) for r in srv.tabelle["live_alerts"].righe] == [("NUOVO", None)]
    srv.tabelle["live_follow"].righe.append({"event_id": "padre"})                # il padre arriva molto dopo
    ora[0] += 16 * 60_000
    return n, srv


def test_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud(tmp_path: Path, ora: List[int]) -> None:
    """dl_stale.py del revisore (regressione provata: NUOVO -> VECCHIO dopo 15 min)."""
    n, srv = _dl_stale(tmp_path, ora)
    try:
        for _ in range(3):
            n.postino.drena()
            ora[0] += 1000
        assert [(r["message"], r["event_id"]) for r in srv.tabelle["live_alerts"].righe] == [("NUOVO", None)]
        morte = n.archivio.dead_letter()
        assert len(morte) == 1 and morte[0]["archiviata_ms"] is not None and "superata" in morte[0]["nota"]
        assert "dati.dead_letter_superata" in n.nomi()
        st = n.postino.stato()
        assert isinstance(st, StatoPostinoArchivio)
        assert (st.dead_letter, st.archiviate, st.in_coda) == (0, 1, 0)
    finally:
        n.archivio.chiudi()


def test_R2a_anche_senza_la_riga_locale_il_cloud_scarta_la_voce_vecchia(tmp_path: Path, ora: List[int]) -> None:
    """Seconda difesa: la riga locale non c'e' piu' (pulizia del vivo dopo 2 giorni) e il
    controllo locale non vede la scrittura piu' nuova: la voce rientra, ma il cloud (versione
    per origine) la scarta come "vecchia". Il cloud resta NUOVO."""
    n, srv = _dl_stale(tmp_path, ora)
    try:
        n.archivio._esegui_sincrono("stato_vivo", lambda c: c.execute("DELETE FROM righe WHERE tabella = 'live_alerts'"))
        for _ in range(3):
            n.postino.drena()
            ora[0] += 1000
        assert [(r["message"], r["event_id"]) for r in srv.tabelle["live_alerts"].righe] == [("NUOVO", None)]
        assert n.postino.contatori["vecchie"] == 1 and n.archivio.dead_letter() == []
    finally:
        n.archivio.chiudi()


def test_R2b_dato_archiviata_dopo_N_rientri_niente_allarme_niente_chiamate(tmp_path: Path, ora: List[int]) -> None:
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    try:
        a, p = n.archivio, n.postino
        srv.tabelle["live_follow"].righe.append({"event_id": "35760084"})
        a.accoda("betfair_live_order_requests", "upsert", None, {"client_ref": "c1", "status": "pending"})
        assert p.drena().consegnate == 1
        # una richiesta che il cloud rifiuta per sempre (22P02: valore non valido per la colonna)
        a.accoda("betfair_live_order_requests", "upsert", None, {"client_ref": "c2", "status": "x"})
        srv.copione = []
        vero = srv._scrivi_riga

        def rifiuta(t: Any, op: str, conflitto: List[str], chiave: Tuple[Any, ...], r: Dict[str, Any]) -> str:
            if r.get("client_ref") == "c2":
                from Betfair.nucleo.dati.tests.test_g1_finti import ErrorePg
                raise ErrorePg("22P02", "invalid input syntax for type uuid")
            return vero(t, op, conflitto, chiave, r)

        srv._scrivi_riga = rifiuta  # type: ignore[method-assign]
        assert p.drena().dead_letter == 1
        for giro in range(RIENTRI_MAX_DATO):
            assert p.stato().dead_letter == 1 and p.stato().archiviate == 0, giro
            ora[0] += 24 * 3_600_000 + 61_000
            assert p.drena().dead_letter == 1, giro                                 # rientra e rimuore
        st = p.stato()
        assert (st.dead_letter, st.archiviate) == (0, 1)
        morta = a.dead_letter()[0]
        assert morta["rientri"] == RIENTRI_MAX_DATO and morta["nota"] == "rientri esauriti"
        assert n.nomi().count("dati.dead_letter_archiviata") == 1
        chiamate = len(srv.richieste)
        for _ in range(3):                                                           # niente piu' chiamate
            ora[0] += 24 * 3_600_000 + 61_000
            p.drena()
        assert len(srv.richieste) == chiamate and len(a.dead_letter()) == 1
    finally:
        n.archivio.chiudi()


def test_R2c_pulisci_toglie_le_archiviate_oltre_la_conservazione_mai_le_attive(tmp_path: Path,
                                                                              ora: List[int]) -> None:
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    a = n.archivio
    try:
        def morta(nota: Optional[str], arch: Optional[int]) -> None:
            a._esegui_sincrono("stato_denaro", lambda c: c.execute(
                "INSERT INTO dead_letter (fonte, tabella, op, chiave, json, creato_ms, morto_ms, motivo, "
                "prossimo_rientro_ms, archiviata_ms, nota) VALUES ('outbox', 'betfair_live_orders', 'upsert', 'k', "
                "'{}', ?, ?, 'dato', ?, ?, ?)", (ora[0], ora[0], 2 ** 60, arch, nota)))

        morta("rientri esauriti", ora[0])
        morta(None, None)                                                          # attiva: mai tolta
        a.pulisci(adesso_ms=ora[0] + 29 * 86_400_000)
        assert len(a.dead_letter()) == 2
        a.pulisci(adesso_ms=ora[0] + 31 * 86_400_000)
        assert [d["archiviata_ms"] for d in a.dead_letter()] == [None]
        assert a.contatori["archiviate_tolte"] == 1
        a.pulisci(adesso_ms=ora[0] + 400 * 86_400_000)
        assert len(a.dead_letter()) == 1
    finally:
        a.chiudi()


# ============================================================================ R3
def test_R3_errore_di_dato_solo_i_casi_provati() -> None:
    for exc in (UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed"), OverflowError("x"),
                sqlite3.IntegrityError("x"), sqlite3.DataError("x"), json.JSONDecodeError("x", "y", 0)):
        assert errore_di_dato(exc) and not errore_di_codice(exc), exc
    for exc in (TypeError("x"), ValueError("x"), sqlite3.ProgrammingError("x"), sqlite3.InterfaceError("x"),
                AttributeError("x"), KeyError("x")):
        assert not errore_di_dato(exc) and errore_di_codice(exc), exc
    for exc in (sqlite3.OperationalError("disk I/O error"), OSError(28, "No space left")):
        assert not errore_di_dato(exc) and not errore_di_codice(exc), exc


class _ConnRotta:
    """Fa fallire con ``eccezione`` ogni scrittura di righe (``chiave`` None = tutte)."""

    def __init__(self, conn: sqlite3.Connection, eccezione: BaseException, chiave: Optional[str] = None) -> None:
        self._c, self.eccezione, self.chiave, self.rotta = conn, eccezione, chiave, True

    def execute(self, sql: str, *a: Any) -> Any:
        if self.rotta and sql.startswith(("INSERT INTO righe", "UPDATE righe")) and \
                (self.chiave is None or (a and self.chiave in a[0])):
            raise self.eccezione
        return self._c.execute(sql, *a)

    def __getattr__(self, k: str) -> Any:
        return getattr(self._c, k)


def test_R3_errore_di_codice_su_tutte_le_voci_resta_in_coda_critical_una_volta_al_minuto(
        tmp_path: Path, ora: List[int], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(mod, "ATTESA_RITENTO_BASE_S", 0.002)
    srv = PostgrestFinto()
    n = Nodo(tmp_path, srv, ora)
    a = n.archivio
    try:
        rotta = _ConnRotta(a._scrittori["stato_vivo"], TypeError("bug: argomento sbagliato"))
        a._scrittori["stato_vivo"] = rotta  # type: ignore[assignment]
        with caplog.at_level(logging.CRITICAL, logger=mod.__name__):
            for i in range(4):
                a.scrivi("live_follow", {"event_id": f"e{i}", "status": "NEW", "updated_at": "2026-10-09T10:00:00+00:00"})
            fine = time.monotonic() + 30
            while a.contatori["guasti_codice"] < 4 and time.monotonic() < fine:
                time.sleep(0.05)
            assert a.contatori["guasti_codice"] >= 4                       # piu' giri di guasto...
            critici = [r for r in caplog.records if r.levelno == logging.CRITICAL]
            assert len(critici) == 1 and "GUASTO DEL CODICE" in critici[0].getMessage()   # ...un CRITICAL solo
        assert a.scarti_scrittore() == []                                    # MAI scartate
        assert n.nomi().count("dati.archivio_guasto_codice") == 1
        st = n.postino.stato()
        assert st.guasti_codice >= 4 and "TypeError" in (st.guasto_codice or "") and st.dead_letter == 0
        assert not a.conferma(0.2)
        rotta.rotta = False                                                  # il codice e' corretto
        assert a.conferma(30)
        assert sorted(json.loads(v.testo)["event_id"] for v in a.outbox_pronta("stato_vivo", 2 ** 62, 10)) == \
            ["e0", "e1", "e2", "e3"]
        assert a.guasto_codice is None and n.postino.stato().guasto_codice is None
    finally:
        a.chiudi()


def test_R3_errore_di_codice_su_una_sola_voce_e_lo_scarto_le_altre_passano(tmp_path: Path, ora: List[int],
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "ATTESA_RITENTO_BASE_S", 0.002)
    n = Nodo(tmp_path, PostgrestFinto(), ora)
    a = n.archivio
    try:
        a._scrittori["stato_vivo"] = _ConnRotta(a._scrittori["stato_vivo"],  # type: ignore[assignment]
                                                TypeError("solo questa"), '["e1"]')
        for i in range(3):
            a.scrivi("live_follow", {"event_id": f"e{i}", "status": "NEW", "updated_at": "2026-10-09T10:00:00+00:00"})
        a.scrivi("live_follow", {"event_id": "e1", "status": "DOPO", "updated_at": "2026-10-09T10:00:00+00:00"})
        assert a.conferma(30)
        assert [s["chiave"] for s in a.scarti_scrittore()] == ['["e1"]', '["e1"]']
        assert a.leggi("live_follow", {"event_id": "e0"}) is not None and a.leggi("live_follow", {"event_id": "e2"})
        assert a.contatori["guasti_codice"] == 0
    finally:
        a.chiudi()


def test_R3_scarti_nell_allarme_poi_archiviati_poi_tolti_dalla_pulizia(tmp_path: Path, ora: List[int]) -> None:
    n = Nodo(tmp_path, PostgrestFinto(), ora)
    a, p = n.archivio, n.postino
    try:
        a.scrivi("live_follow", {"event_id": "\ud800", "status": "P", "updated_at": "2026-10-09T10:00:00+00:00"})
        assert a.conferma(10) and len(a.scarti_scrittore()) == 1
        assert (p.stato().dead_letter, p.stato().archiviate) == (1, 0)
        ora[0] += 6 * 86_400_000
        assert (p.stato().dead_letter, p.stato().archiviate) == (1, 0)
        ora[0] += 2 * 86_400_000                                              # oltre la finestra d'allarme
        assert (p.stato().dead_letter, p.stato().archiviate) == (0, 1)
        a.pulisci(adesso_ms=T0 + 36 * 86_400_000)
        assert len(a.scarti_scrittore()) == 1
        a.pulisci(adesso_ms=T0 + 38 * 86_400_000)                             # 7 + 30 giorni
        assert a.scarti_scrittore() == [] and a.contatori["scarti_tolti"] == 1
    finally:
        a.chiudi()


# ============================================================================ R4
class _ConnCommitRotto:
    """disco_guasto.py del revisore: il COMMIT fallisce (disk I/O) finche' ``rotto``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._c, self.rotto = conn, True

    def execute(self, sql: str, *a: Any) -> Any:
        if self.rotto and sql.strip().upper() == "COMMIT":
            raise sqlite3.OperationalError("disk I/O error")
        return self._c.execute(sql, *a)

    def __getattr__(self, k: str) -> Any:
        return getattr(self._c, k)


def test_R4_disco_guasto_per_3_o_piu_tentativi_poi_ripristino_a_processo_vivo(tmp_path: Path, ora: List[int],
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutazione V14 del revisore: salvataggio+abbandono anche a processo VIVO. Qui il disco
    torna dopo 3+ tentativi: tutto confermato, il claim torna VERO, nessun file di salvataggio."""
    monkeypatch.setattr(mod, "ATTESA_RITENTO_BASE_S", 0.01)
    n = Nodo(tmp_path, PostgrestFinto(), ora)
    a = n.archivio
    try:
        a.scrivi("betfair_live_orders", riga_ordine("r0", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        assert a.conferma()
        rotto = _ConnCommitRotto(a._scrittori["stato_denaro"])
        a._scrittori["stato_denaro"] = rotto  # type: ignore[assignment]
        esiti: Dict[str, Any] = {}

        def claim() -> None:
            try:
                esiti["claim"] = a.transizione("betfair_live_orders", {"mode": "paper", "client_order_ref": "r0"},
                                               "EXECUTABLE", "EXECUTION_COMPLETE")
            except BaseException as exc:  # l'esito falso sarebbe proprio questo
                esiti["claim"] = exc

        def sincrona() -> None:
            try:
                esiti["accoda"] = a.accoda("betfair_live_orders", "upsert", None,
                                           riga_ordine("r2", "EXECUTABLE", "2026-10-09T10:00:00+00:00"), timeout_s=30)
            except BaseException as exc:
                esiti["accoda"] = exc

        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        fili = [threading.Thread(target=claim), threading.Thread(target=sincrona)]
        for f in fili:
            f.start()
        fine = time.monotonic() + 30
        while a.contatori["guasti_scrittura"] < 5 and time.monotonic() < fine:
            time.sleep(0.01)
        assert a.contatori["guasti_scrittura"] >= 5 and a.guasto is not None
        assert all(f.is_alive() for f in fili)                                # i chiamanti aspettano l'esito vero
        rotto.rotto = False                                                   # il disco torna
        for f in fili:
            f.join(60)
        assert a.conferma(30)
        assert esiti["claim"] is True and isinstance(esiti["accoda"], int) and esiti["accoda"] > 0
        assert list(tmp_path.rglob("salvataggio-*.jsonl")) == []
        assert a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"})["status"] == "EXECUTABLE"
        assert a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r0"})["status"] == \
            "EXECUTION_COMPLETE"
        assert a.guasto is None and "dati.archivio_ripreso" in n.nomi()
    finally:
        a.chiudi()


# ============================================================================ W1-C1: semantica di transizione
def test_C1_semantica_dichiarata_di_transizione(tmp_path: Path, ora: List[int]) -> None:
    """La semantica che W1-C1 (porta ordini) puo' usare, verificata dal revisore
    (transizione.py): riga assente -> falso; UNA colonna (``status``); vede le scritture
    ancora in coda; un secondo claim uguale -> falso; colonna assente -> falso."""
    n = Nodo(tmp_path, PostgrestFinto(), ora)
    a = n.archivio
    try:
        assert a.transizione("betfair_live_orders", ORDINE, "EXECUTABLE", "EXECUTION_COMPLETE") is False
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        assert a.transizione("betfair_live_orders", ORDINE, "EXECUTABLE", "EXECUTION_COMPLETE") is True
        assert a.transizione("betfair_live_orders", ORDINE, "EXECUTABLE", "EXECUTION_COMPLETE") is False
        r = a.leggi("betfair_live_orders", ORDINE)
        assert r == riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T10:00:00+00:00")   # SOLO status cambia
        a.scrivi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r2"})
        assert a.transizione("betfair_live_orders", {"mode": "paper", "client_order_ref": "r2"}, "EXECUTABLE", "X") \
            is False
        with pytest.raises(ValueError):
            a.transizione("mike_activity", {"uid": "x"}, "A", "B")
        with pytest.raises(KeyError):
            a.transizione("non_registrata", {"uid": "x"}, "A", "B")
    finally:
        a.chiudi()
