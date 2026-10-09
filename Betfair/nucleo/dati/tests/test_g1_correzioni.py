"""W1-G1 - prove delle correzioni dopo la revisione del 09/10 che il revisore non aveva scritto.

A2 (voce velenosa nello scrittore: intero oltre 2^63 nella versione, chiave con un surrogato),
A1 (\\u0000 rifiutato dal jsonb su TUTTA la chiamata: bisezione), A4 (rientro automatico delle
dead_letter, transitorie e di dato), R8 (unita' di log fallita dopo il flush; commit del vivo
fallito dopo il log: nessun doppione nel file), B7 (conteggio incrementale della coda dei log).
Client supabase VERO su MockTransport (``test_g1_finti``), orologio comandato.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import Betfair.nucleo.dati.archivio as mod  # noqa: E402
from Betfair.nucleo.dati.archivio import ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.contratto import SpecTabella  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, riga_attivita  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_postino import Banco  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_revisione import _ConnFallisceCommit  # noqa: E402

CONTATORI = SpecTabella("contatori_prova", ("k",), "SV", "stato_vivo", 5.0, False, "rev", ())


@pytest.fixture
def banco(tmp_path: Path):
    b = Banco(tmp_path)
    yield b
    b.chiudi()


# ---------------------------------------------------------------- A2 scrittore: voce velenosa isolata
def test_A2_versione_oltre_2_alla_63_isolata_negli_scarti_il_resto_prosegue(tmp_path: Path) -> None:
    eventi: List[Tuple[str, Dict[str, Any]]] = []
    a = ArchivioLocale("prova", {**SPEC, CONTATORI.nome: CONTATORI}, base=tmp_path,
                       eventi=lambda n, d: eventi.append((n, dict(d)))).apri()
    try:
        a.scrivi("contatori_prova", {"k": 1, "rev": 2 ** 64, "v": "veleno"})       # OverflowError in SQLite
        a.scrivi("contatori_prova", {"k": 2, "rev": 1, "v": "buona"})
        a.scrivi("mike_activity", riga_attivita(1))
        assert a.conferma(10), "una voce impossibile da salvare ferma lo scrittore"
        assert a.leggi("contatori_prova", {"k": 2})["v"] == "buona"
        scarti = a.scarti_scrittore()
        assert len(scarti) == 1 and scarti[0]["tabella"] == "contatori_prova" and "Overflow" in scarti[0]["errore"]
        assert [d["fonte"] for n, d in eventi if n == "dati.dead_letter"] == ["scrittore"]
        assert any(m["fonte"] == "scrittore" for m in a.dead_letter())
    finally:
        a.chiudi()


def test_A2_chiave_con_surrogato_isolata_denaro_e_vivo_non_si_fermano(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("live_follow", {"event_id": "\ud800", "home_name": "A", "away_name": "B", "status": "P",
                                 "open_date": "x", "updated_at": "2026-10-09T10:00:00+00:00"})
        a.scrivi("live_follow", {"event_id": "e1", "home_name": "A", "away_name": "B", "status": "P",
                                 "open_date": "x", "updated_at": "2026-10-09T10:00:00+00:00"})
        a.accoda("betfair_live_order_requests", "upsert", None, {"client_ref": "c1", "status": "pending"})
        assert a.conferma(10)
        assert a.leggi("live_follow", {"event_id": "e1"}) is not None
        assert len(a.scarti_scrittore()) == 1
    finally:
        a.chiudi()


# ---------------------------------------------------------------- A1 \u0000: tutta la chiamata, bisezione
def test_A1_carattere_nullo_bisezione_isola_la_riga_sola(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(8):
        a.scrivi("mike_activity", riga_attivita(i, kind="a\x00b" if i == 5 else "giro"))
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.dead_letter) == (7, 1)
    assert sorted(r["payload"]["i"] for r in banco.righe("mike_activity")) == [0, 1, 2, 3, 4, 6, 7]
    morta = a.dead_letter()[0]
    assert morta["codice"] == "22P05" and morta["motivo"] == "dato" and p.contatori["bisezioni"] >= 1


# ---------------------------------------------------------------- A4 rientro automatico
def test_A4_dead_letter_transitoria_rientra_da_sola_dopo_15_minuti(tmp_path: Path) -> None:
    b = Banco(tmp_path, tetto_tentativi_riga=2)
    try:
        b.archivio.scrivi("live_alerts", {"level": "INFO", "code": "a", "message": "m", "event_id": "tardi"})
        assert b.archivio.conferma()
        for _ in range(3):
            b.postino.drena()
            b.avanza(61)
        morte = b.archivio.dead_letter()
        assert len(morte) == 1 and morte[0]["motivo"] == "transitorio"
        b.server.tabelle["live_follow"].righe.append({"event_id": "tardi"})       # il padre arriva molto dopo
        b.avanza(10 * 60)
        b.postino.drena()
        assert len(b.righe("live_alerts")) == 0                                  # non ancora: 15 min
        b.avanza(6 * 60)
        b.postino.drena()
        b.postino.drena()
        assert len(b.righe("live_alerts")) == 1 and b.archivio.dead_letter() == []
        assert "dati.dead_letter_rientro" in b.nomi()
    finally:
        b.chiudi()


def test_A4_dead_letter_di_dato_rientra_dopo_24_ore_e_passa_se_il_vincolo_e_cambiato(banco: Banco) -> None:
    """Il caso PSB par. 7 n.18: un CHECK che non ammetteva uno stato, corretto da una migrazione:
    la riga torna nel cloud senza che nessuno faccia nulla."""
    a, p = banco.archivio, banco.postino
    banco.server.tabelle["live_follow"].righe.append({"event_id": "35760084"})
    a.scrivi("live_alerts", {"level": "GRAVE", "code": "x", "message": "m", "event_id": "35760084"})
    assert a.conferma() and p.drena().dead_letter == 1
    banco.avanza(23 * 3600)
    p.drena()
    assert len(a.dead_letter()) == 1                                            # prima delle 24 h resta
    banco.server.tabelle["live_alerts"].check = []                              # "migrazione" che allarga il CHECK
    banco.avanza(3600 + 1)
    p.drena()
    p.drena()
    assert a.dead_letter() == [] and [r["level"] for r in banco.righe("live_alerts")] == ["GRAVE"]


def test_A4_dato_ancora_non_valido_torna_in_dead_letter_contando_i_rientri(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    banco.server.tabelle["live_follow"].righe.append({"event_id": "35760084"})
    a.scrivi("live_alerts", {"level": "GRAVE", "code": "x", "message": "m", "event_id": "35760084"})
    assert a.conferma() and p.drena().dead_letter == 1
    banco.avanza(24 * 3600 + 1)
    p.drena()
    p.drena()
    morte = a.dead_letter()
    assert len(morte) == 1 and morte[0]["rientri"] == 1 and banco.righe("live_alerts") == []


# ---------------------------------------------------------------- R8 nessun doppione nel file di log
class _FileCheFallisce:
    """Il flush scrive DAVVERO e poi fallisce (il disco ha preso i byte, l'esito si perde)."""

    def __init__(self, vero: Any) -> None:
        self.vero, self.volte = vero, 1

    def write(self, b: bytes) -> int:
        return self.vero.write(b)

    def tell(self) -> int:
        return self.vero.tell()

    def flush(self) -> None:
        self.vero.flush()
        if self.volte:
            self.volte -= 1
            raise OSError("I/O error (prova)")

    def close(self) -> None:
        self.vero.close()


def _uid_nel_file(a: ArchivioLocale) -> List[str]:
    return [json.loads(x)["r"]["uid"] for f in a.file_log() for x in f.read_bytes().split(b"\n") if x.strip()]


def test_R8_unita_di_log_fallita_dopo_il_flush_riavvolta_nessun_doppione(tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("mike_activity", riga_attivita(0))
        assert a.conferma()
        nome = next(iter(a._file_log))
        a._file_log[nome] = _FileCheFallisce(a._file_log[nome])
        for i in range(1, 30):
            a.scrivi("mike_activity", riga_attivita(i))
        assert a.conferma(10)
        uid = _uid_nel_file(a)
        assert len(uid) == 30 and len(set(uid)) == 30, f"doppioni nel file: {len(uid)} righe, {len(set(uid))} uid"
        assert a.contatori["guasti_scrittura"] >= 1
    finally:
        a.chiudi()


def test_R8_commit_del_vivo_fallito_dopo_il_log_nessun_doppione(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a._scrittori["stato_vivo"] = _ConnFallisceCommit(a._scrittori["stato_vivo"], 1)
        for i in range(20):
            a.scrivi("mike_activity", riga_attivita(i))
            a.scrivi("live_follow", {"event_id": f"e{i}", "home_name": "A", "away_name": "B", "status": "P",
                                     "open_date": "x", "updated_at": "2026-10-09T10:00:00+00:00"})
        assert a.conferma(10)
        uid = _uid_nel_file(a)
        assert len(uid) == 20 and len(set(uid)) == 20
        assert sqlite3.connect(a.cartella / "vivo.sqlite3").execute(
            "SELECT count(*) FROM outbox WHERE tabella = 'live_follow'").fetchone()[0] == 20
    finally:
        a.chiudi()


# ---------------------------------------------------------------- B7 conteggio incrementale
def test_B7_stato_conta_la_coda_dei_log_in_modo_incrementale(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(10):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    assert p.stato().per_tabella == {"mike_activity": 10}
    p.drena(4)
    assert p.stato().per_tabella == {"mike_activity": 6}
    for i in range(3):
        a.scrivi("scalper_activity", {"kind": "k", "payload": {}, "event_id": "1"})
    assert a.conferma()
    st = p.stato()
    assert st.per_tabella == {"mike_activity": 6, "scalper_activity": 3} and st.eta_max_s is not None
    for _ in range(20):
        if not p.drena().consegnate:
            break
    assert p.stato().in_coda == 0 and p.stato().eta_max_s is None



# ---------------------------------------------------------------- M4 FIFO per chiave fra un giro e l'altro
def test_M4_voce_successiva_non_supera_quella_in_attesa_nei_giri_dopo(tmp_path: Path) -> None:
    from Betfair.nucleo.dati.postino import PostinoLocale
    from Betfair.nucleo.dati.tests.test_g1_revisione import CloudScript
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "status": "pending"})
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "status": "done"})
        assert a.conferma()
        cloud: Dict[str, str] = {}
        n = {"chiamate": 0}

        def fn(args: Dict[str, Any]) -> List[Dict[str, Any]]:
            out = []
            for r in args["p_righe"]:
                n["chiamate"] += 1
                if n["chiamate"] == 1:
                    out.append({"esito": "errore", "codice": "40P01", "messaggio": "deadlock"})
                else:
                    cloud[r["client_ref"]] = r["status"]
                    out.append({"esito": "ok"})
            return out
        ora = [1_760_004_000_000]
        p = PostinoLocale(a, CloudScript(fn), orologio_ms=lambda: ora[0])
        p.drena()                                    # pending fallisce (ritento fra 2 s), done rimandata
        ora[0] += 1_000
        p.drena()                                    # done e' pronta, ma pending (piu' vecchia) aspetta ancora
        assert cloud == {}, "la voce successiva e' partita prima di quella della stessa chiave in attesa"
        ora[0] += 2_000
        p.drena()
        p.drena()
        assert cloud == {"c1": "done"}
    finally:
        a.chiudi()



# ---------------------------------------------------------------- M3 con versione INTERA
def test_M3_versione_intera_uguale_vince_l_ultima_minore_e_stantia(tmp_path: Path) -> None:
    eventi: List[str] = []
    a = ArchivioLocale("prova", {**SPEC, CONTATORI.nome: CONTATORI}, base=tmp_path,
                       eventi=lambda n, d: eventi.append(n)).apri()
    try:
        a.scrivi("contatori_prova", {"k": 1, "rev": 5, "v": "a"})
        a.scrivi("contatori_prova", {"k": 1, "rev": 5, "v": "b"})        # stessa versione: vince l'ultima, rev 6
        assert a.conferma()
        assert a.leggi("contatori_prova", {"k": 1}) == {"k": 1, "rev": 6, "v": "b"}
        a.scrivi("contatori_prova", {"k": 1, "rev": 4, "v": "c"})        # intero piu' basso: stantio, scartato
        assert a.conferma()
        assert a.leggi("contatori_prova", {"k": 1})["v"] == "b" and eventi.count("dati.riga_vecchia") == 1
    finally:
        a.chiudi()
