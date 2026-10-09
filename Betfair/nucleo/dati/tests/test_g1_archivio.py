"""W1-G1 - archivio locale: percorso, schema, tre regimi, claim, coalescenza, ripresa, pulizia.

Ogni prova usa l'archivio VERO su una cartella temporanea (mai dentro il repo) e le
forme vere delle tabelle (``test_g1_finti.SPEC``). Le prove di crash con processo
figlio vero sono in ``test_g1_crash.py``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.nucleo.dati import percorso as P
from Betfair.nucleo.dati import schema_locale as S
from Betfair.nucleo.dati.archivio import ArchivioChiuso, ArchivioLocale
from Betfair.nucleo.dati.contratto import Archivio, SpecTabella
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, riga_attivita, riga_ordine

RADICE = Path(__file__).resolve().parents[4]


def conforme(cls: type, proto: type) -> bool:
    """Ogni metodo del protocollo esiste con gli STESSI parametri (nome, tipo di passaggio)."""
    import inspect

    for nome, fn in vars(proto).items():
        if nome.startswith("_") or not callable(fn):
            continue
        atteso = [(p.name, p.kind) for p in inspect.signature(fn).parameters.values()]
        vero = [(p.name, p.kind) for p in inspect.signature(getattr(cls, nome)).parameters.values()]
        assert vero[:len(atteso)] == atteso, (nome, vero, atteso)
        assert all(p.default is not inspect.Parameter.empty for p in
                   list(inspect.signature(getattr(cls, nome)).parameters.values())[len(atteso):]), nome
    return True


def apri(tmp_path: Path, **kw: Any) -> ArchivioLocale:
    eventi: List[Tuple[str, Dict[str, Any]]] = kw.pop("raccolta", [])
    a = ArchivioLocale("prova", SPEC, base=tmp_path, eventi=lambda n, d: eventi.append((n, dict(d))), **kw)
    return a.apri()


# ---------------------------------------------------------------------------
# percorso: invisibile, mai nel repo, lucchetto per processo
# ---------------------------------------------------------------------------
def test_percorso_windows_posix_e_aggancio() -> None:
    w = P.cartella_base({"LOCALAPPDATA": r"/tmp/Locale"}, "win32")
    assert w.parts[-3:] == ("Locale", "AlphaScore Trading", "archivio")
    x = P.cartella_base({"XDG_DATA_HOME": "/tmp/xdg"}, "linux")
    assert x.parts[-3:] == ("xdg", "alphascore-trading", "archivio")
    e = P.cartella_base({"ARCH_ARCHIVIO_DIR": "/tmp/da_electron", "LOCALAPPDATA": "/tmp/no"}, "win32")
    assert e == Path("/tmp/da_electron").resolve()


def test_percorso_mai_dentro_il_repo() -> None:
    with pytest.raises(P.PercorsoNonAmmesso):
        P.cartella_base({"ARCH_ARCHIVIO_DIR": str(RADICE / "_archivio")}, "linux")
    with pytest.raises(P.PercorsoNonAmmesso):
        P.cartella_processo("mike", RADICE / "dentro")
    with pytest.raises(P.PercorsoNonAmmesso):
        P.cartella_processo("../fuga", Path("/tmp"))


def test_lucchetto_esclusivo_fra_processi_e_liberato_dal_crash(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        figlio = ("import sys; from pathlib import Path; from Betfair.nucleo.dati.archivio import ArchivioLocale;"
                  "from Betfair.nucleo.dati.percorso import ArchivioOccupato;"
                  "from Betfair.nucleo.dati.tests.test_g1_finti import SPEC\n"
                  "try:\n ArchivioLocale('prova', SPEC, base=Path(sys.argv[1])).apri(); print('APERTO')\n"
                  "except ArchivioOccupato: print('OCCUPATO')")
        out = subprocess.run([sys.executable, "-c", figlio, str(tmp_path)], capture_output=True, text=True,
                             cwd=RADICE, timeout=60)
        assert out.stdout.strip() == "OCCUPATO", out.stderr
    finally:
        a.chiudi()
    # un figlio che prende il lucchetto e muore con os._exit: il SO lo rilascia
    figlio2 = ("import os, sys; from pathlib import Path; from Betfair.nucleo.dati.archivio import ArchivioLocale;"
               "from Betfair.nucleo.dati.tests.test_g1_finti import SPEC\n"
               "ArchivioLocale('prova', SPEC, base=Path(sys.argv[1])).apri(); os._exit(3)")
    r = subprocess.run([sys.executable, "-c", figlio2, str(tmp_path)], cwd=RADICE, timeout=60)
    assert r.returncode == 3
    b = apri(tmp_path)
    b.chiudi()


def test_import_non_apre_file_ne_thread(tmp_path: Path) -> None:
    codice = ("import threading, os, sys\nprima = set(os.listdir(sys.argv[1]))\n"
              "import Betfair.nucleo.dati.archivio, Betfair.nucleo.dati.postino, Betfair.nucleo.dati.riconcilia\n"
              "import Betfair.nucleo.dati.percorso, Betfair.nucleo.dati.schema_locale\n"
              "print(threading.active_count(), set(os.listdir(sys.argv[1])) == prima)")
    out = subprocess.run([sys.executable, "-c", codice, str(tmp_path)], capture_output=True, text=True, cwd=RADICE,
                         timeout=60, env={**os.environ, "XDG_DATA_HOME": str(tmp_path)})
    assert out.stdout.split() == ["1", "True"], out.stderr


# ---------------------------------------------------------------------------
# schema generico e versionato
# ---------------------------------------------------------------------------
def test_schema_creato_versionato_e_rifiuto_del_piu_nuovo(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "x.sqlite3", isolation_level=None)
    assert S.applica_schema(conn) == 0
    assert S.versione(conn) == S.VERSIONE_SCHEMA
    assert S.applica_schema(conn) == S.VERSIONE_SCHEMA                     # idempotente
    assert int(conn.execute("PRAGMA auto_vacuum").fetchone()[0]) == 2     # INCREMENTAL
    assert {"righe", "outbox", "dead_letter", "consegna", "riconciliazioni", "segnalazioni"} <= {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.execute(f"PRAGMA user_version = {S.VERSIONE_SCHEMA + 1}")
    with pytest.raises(S.SchemaPiuNuovo):
        S.applica_schema(conn)


def test_schema_generico_nessuna_tabella_del_cloud(tmp_path: Path) -> None:
    """Aggiungere una tabella = una riga di registro: lo schema non nomina nessuna tabella del cloud."""
    testo = " ".join(" ".join(m) for m in S.MIGRAZIONI)
    for nome in ("mike", "omega", "betfair", "live_", "scalper", "tennis", "safe"):
        assert nome not in testo
    spec = SpecTabella("tabella_nuova_di_un_bot", ("k",), "SV", "stato_vivo", 5.0, False, None, ())
    a = ArchivioLocale("prova", {**SPEC, spec.nome: spec}, base=tmp_path).apri()
    try:
        a.scrivi("tabella_nuova_di_un_bot", {"k": 1, "v": "x"})
        assert a.conferma()
        assert a.leggi("tabella_nuova_di_un_bot", {"k": 1}) == {"k": 1, "v": "x"}
    finally:
        a.chiudi()


def test_chiave_canonica_come_jsonb_e_versione() -> None:
    s = SPEC["betfair_live_orders"]
    assert S.chiave_canonica(s, {"mode": "paper", "client_order_ref": "r1"}) == '["paper", "r1"]'
    with pytest.raises(KeyError):
        S.chiave_canonica(s, {"mode": "paper"})
    assert S.rev_ordinabile(7) == 7
    assert S.rev_ordinabile("2026-10-09T10:00:00Z") == S.rev_ordinabile("2026-10-09T12:00:00+02:00")
    assert S.rev_ordinabile("2026-10-09T10:00:00.000001+00:00") > S.rev_ordinabile("2026-10-09T10:00:00+00:00")
    with pytest.raises(ValueError):
        S.rev_ordinabile(1.5)


# ---------------------------------------------------------------------------
# i tre regimi
# ---------------------------------------------------------------------------
def test_tre_regimi_due_file_e_sincronia(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        assert conforme(ArchivioLocale, Archivio)                         # protocollo del contratto
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        a.scrivi("live_follow", {"event_id": "35760084", "home_name": "A", "away_name": "B",
                                 "open_date": "2026-10-09T18:00:00+00:00", "status": "STREAMING",
                                 "updated_at": "2026-10-09T10:00:00+00:00"})
        a.scrivi("mike_activity", riga_attivita(1))
        assert a.conferma(10)
        cart = a.cartella
        assert (cart / "denaro.sqlite3").exists() and (cart / "vivo.sqlite3").exists()
        log = list((cart / "log").glob("*.jsonl"))
        assert len(log) == 1
        riga = json.loads(log[0].read_text(encoding="ascii"))
        assert riga["t"] == "mike_activity" and riga["op"] == "insert"
        assert len(riga["r"]["uid"]) == 36 and riga["r"]["ts"].endswith("+00:00")   # uid e timbro nel punto di scrittura
        d = sqlite3.connect(cart / "denaro.sqlite3")
        v = sqlite3.connect(cart / "vivo.sqlite3")
        assert d.execute("SELECT count(*) FROM righe").fetchone()[0] == 1
        assert d.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1
        assert v.execute("SELECT count(*) FROM righe").fetchone()[0] == 1
        assert d.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert a._scrittori["stato_denaro"].execute("PRAGMA synchronous").fetchone()[0] == 2   # FULL
        assert a._scrittori["stato_vivo"].execute("PRAGMA synchronous").fetchone()[0] == 1     # NORMAL
        assert a._scrittori["stato_vivo"].execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 0
    finally:
        a.chiudi()


def test_leggi_vede_subito_e_versione_mai_indietro(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T10:00:05+00:00"))
        assert a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"})["status"] == \
            "EXECUTION_COMPLETE"                                          # prima del commit
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:01+00:00"))
        assert a.conferma()
        assert a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"})["status"] == \
            "EXECUTION_COMPLETE"
        assert a.contatori["righe_vecchie_ignorate"] == 1
        assert len(a.outbox_pronta("stato_denaro", 2 ** 62, 10)) == 1     # la vecchia non va in coda
        with pytest.raises(ValueError):
            a.scrivi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r2", "status": "X"})
        with pytest.raises(KeyError):
            a.scrivi("tabella_mai_registrata", {"x": 1})
        with pytest.raises(ValueError):
            a.leggi("mike_activity", {"uid": "x"})
    finally:
        a.chiudi()
    with pytest.raises(ArchivioChiuso):
        a.scrivi("mike_activity", riga_attivita(2))


def test_transizione_claim_atomico_una_volta_sola(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "action": "place", "mode": "paper",
                                                 "status": "pending"})
        vinti: List[bool] = []
        barriera = threading.Barrier(8)

        def prova() -> None:
            barriera.wait()
            vinti.append(a.transizione("betfair_live_order_requests", {"client_ref": "c1"}, "pending", "processing"))

        th = [threading.Thread(target=prova) for _ in range(8)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        assert sorted(vinti) == [False] * 7 + [True]
        assert a.leggi("betfair_live_order_requests", {"client_ref": "c1"})["status"] == "processing"
        assert not a.transizione("betfair_live_order_requests", {"client_ref": "assente"}, "pending", "x")
        voci = a.outbox_pronta("stato_denaro", 2 ** 62, 10)
        assert [json.loads(v.testo)["status"] for v in voci] == ["pending", "processing"]
    finally:
        a.chiudi()


def test_transizione_alza_la_versione(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2099-01-01T00:00:00+00:00"))
        assert a.transizione("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"},
                             "EXECUTABLE", "EXECUTION_COMPLETE")
        r = a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"})
        assert S.rev_ordinabile(r["updated_at"]) > S.rev_ordinabile("2099-01-01T00:00:00+00:00")
    finally:
        a.chiudi()


def test_riga_e_outbox_nella_stessa_transazione(tmp_path: Path) -> None:
    """Se la outbox non si scrive, la riga non c'e' (e viceversa): mai una senza l'altra."""
    a = apri(tmp_path)
    try:
        a.scrivi("betfair_live_orders", riga_ordine("ok", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        assert a.conferma()
        orig = a._in_outbox
        chiamate: List[int] = []

        def guasto(*args: Any) -> int:
            chiamate.append(1)
            if len(chiamate) <= 2:
                raise sqlite3.OperationalError("disk I/O error (simulato)")
            return orig(*args)

        a._in_outbox = guasto  # type: ignore[method-assign]
        a.scrivi("betfair_live_orders", riga_ordine("r9", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
        time.sleep(0.3)
        conn = sqlite3.connect(a.cartella / "denaro.sqlite3")
        # durante il guasto: ne' riga ne' outbox per r9
        assert conn.execute("SELECT count(*) FROM righe WHERE chiave LIKE '%r9%'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM outbox WHERE chiave LIKE '%r9%'").fetchone()[0] == 0
        assert a.guasto is not None
        assert a.conferma(15)                                             # poi riprova e scrive entrambe
        assert conn.execute("SELECT count(*) FROM righe WHERE chiave LIKE '%r9%'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM outbox WHERE chiave LIKE '%r9%'").fetchone()[0] == 1
        assert a.guasto is None and a.contatori["guasti_scrittura"] == 2
    finally:
        a.chiudi()


def test_coalescenza_tiene_solo_l_ultima_versione(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        for i in range(50):
            a.scrivi("betfair_live_heartbeat", {"id": 1, "runner": "calcio", "ts": f"2026-10-09T10:00:{i:02d}+00:00"})
        a.scrivi("betfair_live_heartbeat", {"id": 2, "runner": "tennis", "ts": "x"})
        assert a.conferma()
        voci = a.outbox_pronta("stato_vivo", 2 ** 62, 100)
        assert len(voci) == 2
        assert json.loads(voci[0].testo)["ts"] == "2026-10-09T10:00:49+00:00"
    finally:
        a.chiudi()


def test_accoda_sincrona_patch_e_delete(tmp_path: Path) -> None:
    a = apri(tmp_path)
    try:
        s1 = a.accoda("betfair_live_order_requests", "upsert", None, {"client_ref": "c1", "status": "pending"})
        s2 = a.accoda("betfair_live_order_requests", "patch", None, {"client_ref": "c1", "status": "done"})
        assert s2 > s1 > 0
        assert a.leggi("betfair_live_order_requests", {"client_ref": "c1"}) == {"client_ref": "c1", "status": "done"}
        a.accoda("betfair_live_order_requests", "delete", None, {"client_ref": "c1"})
        assert a.leggi("betfair_live_order_requests", {"client_ref": "c1"}) is None
        assert [v.op for v in a.outbox_pronta("stato_denaro", 2 ** 62, 10)] == ["upsert", "patch", "delete"]
        off1 = a.accoda("mike_activity", "insert", None, riga_attivita(1))
        off2 = a.accoda("mike_activity", "insert", None, riga_attivita(2))
        assert off1 == 0 and off2 > off1                                  # offset in byte nel file del giorno
    finally:
        a.chiudi()


# ---------------------------------------------------------------------------
# ripresa: riga JSONL troncata
# ---------------------------------------------------------------------------
def test_riga_jsonl_troncata_scartata_e_segnalata(tmp_path: Path) -> None:
    eventi: List[Tuple[str, Dict[str, Any]]] = []
    a = apri(tmp_path, raccolta=eventi)
    a.scrivi("mike_activity", riga_attivita(1))
    a.scrivi("mike_activity", riga_attivita(2))
    assert a.conferma()
    a.chiudi()
    f = next((a.cartella / "log").glob("*.jsonl"))
    with open(f, "ab") as h:
        h.write(b'{"t":"mike_activity","op":"insert","ms":1,"v":1,"r":{"kind":"meta')   # crash a meta' riga
    b = apri(tmp_path, raccolta=eventi)
    try:
        assert f.read_bytes().endswith(b"\n") and len(f.read_bytes().splitlines()) == 2
        seg = b.segnalazioni()
        assert [s["tipo"] for s in seg] == ["riga_log_troncata"]
        assert seg[0]["dettagli"]["anteprima"].startswith('{"t":"mike_activity"')
        assert any(n == "dati.riga_troncata" for n, _ in eventi)
        assert b.dead_letter() == []                                        # NON e' una dead_letter
        b.scrivi("mike_activity", riga_attivita(3))
        assert b.conferma()
        assert all(json.loads(x) for x in f.read_text(encoding="ascii").splitlines())
    finally:
        b.chiudi()


# ---------------------------------------------------------------------------
# checkpoint fuori dal percorso e pulizia
# ---------------------------------------------------------------------------
def test_checkpoint_lo_fa_la_manutenzione(tmp_path: Path) -> None:
    a = apri(tmp_path, checkpoint_ogni_s=0.05)
    try:
        for i in range(300):
            a.scrivi("live_follow", {"event_id": str(i), "home_name": "A", "away_name": "B", "status": "PENDING",
                                     "open_date": "2026-10-09T18:00:00+00:00", "updated_at": f"2026-10-09T10:00:00+00:00"})
        assert a.conferma()
        fine = time.monotonic() + 5
        while not a.misure()["checkpoint_us"].get("n") and time.monotonic() < fine:
            time.sleep(0.05)
        assert a.misure()["checkpoint_us"]["n"] > 0
        m = a.misure()
        assert m["accodamento_us"]["n"] == 300 and m["commit_us"]["stato_vivo"]["n"] >= 1
    finally:
        a.chiudi()
    wal = a.cartella / "vivo.sqlite3-wal"
    assert not wal.exists() or wal.stat().st_size == 0                         # TRUNCATE alla chiusura


def test_pulizia_solo_consegnato_e_riconciliato(tmp_path: Path) -> None:
    ora = [1_760_000_000_000]
    a = apri(tmp_path, orologio_ms=lambda: ora[0])
    try:
        a.scrivi("live_follow", {"event_id": "vecchio", "home_name": "A", "away_name": "B", "status": "CLOSED",
                                 "open_date": "x", "updated_at": "2025-10-09T10:00:00+00:00"})
        a.scrivi("live_follow", {"event_id": "in_coda", "home_name": "A", "away_name": "B", "status": "CLOSED",
                                 "open_date": "x", "updated_at": "2025-10-09T10:00:00+00:00"})
        a.scrivi("mike_activity", riga_attivita(1))
        assert a.conferma()
        voci = {json.loads(v.testo)["event_id"]: v.seq for v in a.outbox_pronta("stato_vivo", 2 ** 62, 10)}
        a.chiudi_voci("stato_vivo", [voci["vecchio"]], [], [])           # consegnato solo «vecchio»
        giorno = S.giorno_utc(ora[0])
        ora[0] += 10 * 86_400_000                                           # dieci giorni dopo
        assert a.pulisci() == {"stato_denaro": 0, "stato_vivo": 0, "file_log": 0}   # niente riconciliato: niente tolto
        a.scrivi_riconciliazione("live_follow", giorno, "ok", {})
        f = a.file_log()[0]
        a.chiudi_log(f.name, f.stat().st_size, [], [])
        assert a.pulisci() == {"stato_denaro": 0, "stato_vivo": 1, "file_log": 0}   # log non riconciliato: resta
        a.scrivi_riconciliazione("mike_activity", giorno, "ok", {})
        assert a.pulisci() == {"stato_denaro": 0, "stato_vivo": 0, "file_log": 1}
        assert a.leggi("live_follow", {"event_id": "in_coda"}) is not None  # ancora in coda: resta
        assert a.leggi("live_follow", {"event_id": "vecchio"}) is None
        assert a.file_log() == []
    finally:
        a.chiudi()
