"""W1-G1 - le prove della revisione indipendente del 09/10 (D1-D11, E1-E10, R1/R7/R13), incorporate.

Fonte: ``scratchpad/rev-w1g1/test_rev_{a,b,d,e}.py`` del revisore. Gli ASSERT sono quelli del
revisore, invariati; ogni test porta un nome che dice il comportamento GIUSTO (il revisore li
aveva chiamati col difetto che cercavano). Cambiati solo i meccanismi di prova, dichiarati:
  * D8: ``time.sleep`` del modulo spento con ``monkeypatch`` (il revisore lo sovrascriveva per
    tutto il processo senza ripristino);
  * E5: la parte col collegamento simbolico si salta dove il sistema non li permette;
  * E8 (limite di dimensione dei file con ``resource``): solo Linux/macOS;
  * radice del repo calcolata dal file (il revisore usava la sua copia ``/tmp/rev-w1g1``).
Le correzioni corrispondenti: referto W1-G1, sezione "Correzioni dopo la revisione".
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
from typing import Any, Dict

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import Betfair.nucleo.dati.archivio as mod  # noqa: E402
from Betfair.nucleo.dati.archivio import ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.percorso import ArchivioOccupato, PercorsoNonAmmesso, cartella_base  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import (SPEC, CloudProva, PostgrestFinto, riga_attivita,  # noqa: E402
                                                     riga_ordine)
from Betfair.nucleo.dati.tests.test_g1_postino import Banco  # noqa: E402

RADICE = Path(__file__).resolve().parents[4]


@pytest.fixture
def banco(tmp_path: Path):
    b = Banco(tmp_path)
    yield b
    try:
        b.chiudi()
    except Exception:
        pass


def _drena_n(b: Banco, n: int = 5):
    esiti = []
    for _ in range(n):
        b.avanza(61)
        esiti.append(b.postino.drena())
    return esiti


# ---------------------------------------------------------------- A1 riga velenosa: isolata, le altre passano
def test_rev_D1_riga_con_nan_isolata_le_altre_passano(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("mike_activity", riga_attivita(0, payload={"x": float("nan")}))     # riga velenosa
    for i in range(1, 20):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    _drena_n(banco, 6)
    consegnate = len(banco.righe("mike_activity"))
    assert consegnate == 19, "una riga con NaN ferma per sempre le 19 righe buone della stessa tabella"
    morte = a.dead_letter()
    assert len(morte) == 1 and morte[0]["motivo"] == "dato" and morte[0]["codice"] == "valore_non_json"


def test_rev_D1b_surrogato_isolato_nei_log_isolato_le_altre_passano(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("mike_activity", riga_attivita(0, kind="\ud800"))
    for i in range(1, 20):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    _drena_n(banco, 6)
    assert len(banco.righe("mike_activity")) == 19, "surrogato isolato: tabella bloccata"
    assert [m["fonte"] for m in a.dead_letter()] == ["log"]


def test_rev_D2_surrogato_in_riga_di_stato_lo_scrittore_prosegue(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("live_follow", {"event_id": "e0", "home_name": "\ud800", "away_name": "B", "status": "PENDING",
                                 "open_date": "2026-10-09T18:00:00+00:00", "updated_at": "2026-10-09T10:00:00+00:00"})
        a.scrivi("live_follow", {"event_id": "e1", "home_name": "A", "away_name": "B", "status": "PENDING",
                                 "open_date": "2026-10-09T18:00:00+00:00", "updated_at": "2026-10-09T10:00:00+00:00"})
        a.conferma(4.0)
        a.scrivi("mike_activity", riga_attivita(1))
        assert a.conferma(4.0), "UNA riga con un surrogato isolato blocca lo scrittore per sempre (tutti i regimi)"
    finally:
        a.chiudi()


# ---------------------------------------------------------------- M1 tabella non piu' registrata
def test_rev_D3_log_di_tabella_non_registrata_va_in_dead_letter(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    a.scrivi("mike_activity", riga_attivita(1))
    a.scrivi("omega_activity", {"kind": "k", "payload": {}})
    assert a.conferma()
    a.chiudi()
    ridotto = {k: v for k, v in SPEC.items() if k != "omega_activity"}      # app piu' vecchia / registro cambiato
    srv = PostgrestFinto()
    b = ArchivioLocale("prova", ridotto, base=tmp_path).apri()
    try:
        p = PostinoLocale(b, CloudProva(srv))
        p.drena()
        in_cloud = len(srv.tabelle["omega_activity"].righe)
        assert in_cloud == 1 or len(b.dead_letter()) == 1, \
            "riga di log scartata: ne' nel cloud ne' in dead_letter (solo una segnalazione)"
        assert b.dead_letter()[0]["motivo"] == "registro"
    finally:
        b.chiudi()


def test_rev_D3b_voce_outbox_di_tabella_non_registrata_non_ferma_le_altre(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    a.scrivi("live_follow", {"event_id": "e0", "home_name": "A", "away_name": "B", "status": "PENDING",
                             "open_date": "2026-10-09T18:00:00+00:00", "updated_at": "2026-10-09T10:00:00+00:00"})
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma()
    a.chiudi()
    ridotto = {k: v for k, v in SPEC.items() if k != "live_follow"}
    srv = PostgrestFinto()
    b = ArchivioLocale("prova", ridotto, base=tmp_path).apri()
    try:
        p = PostinoLocale(b, CloudProva(srv))
        try:
            p.drena()
        except KeyError as exc:
            pytest.fail(f"drena solleva {exc!r}: una voce sconosciuta ferma TUTTE le altre tabelle")
        assert len(srv.tabelle["betfair_live_orders"].righe) == 1
        assert [m["motivo"] for m in b.dead_letter()] == ["registro"]
    finally:
        b.chiudi()


# ---------------------------------------------------------------- A3 riparazione dei log troncati
def test_rev_D4_riga_troncata_oltre_1MiB_le_righe_buone_restano(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    for i in range(200):
        a.scrivi("mike_activity", riga_attivita(i, payload={"pad": "x" * 10_000}))
    assert a.conferma()
    a.chiudi()
    f = next((tmp_path / "prova" / "log").glob("*.jsonl"))
    dim_buona = f.stat().st_size
    frammento = b'{"t":"mike_activity","op":"insert","ms":1,"v":1,"r":{"pad":"' + b"y" * 1_300_000
    with open(f, "ab") as fh:                        # un crash lascia una riga enorme a meta'
        fh.write(frammento)
    b = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        dopo = f.stat().st_size
        assert dopo == dim_buona, f"la riparazione ha buttato {dim_buona - dopo} byte di righe BUONE non consegnate"
        seg = b.segnalazioni()
        assert seg[0]["dettagli"]["byte"] == len(frammento) and seg[0]["dettagli"]["offset"] == dim_buona
    finally:
        b.chiudi()


def test_rev_D4b_file_tutto_frammento_si_taglia_a_zero(tmp_path: Path) -> None:
    """Nessun \\n in tutto il file: SOLO in questo caso il taglio e' a 0, con i byte veri."""
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    a.chiudi()
    f = tmp_path / "prova" / "log" / "2026-10-09.jsonl"
    f.write_bytes(b'{"t":"mike_activity"' + b"z" * 2_500_000)
    b = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        assert f.stat().st_size == 0
        assert b.segnalazioni()[0]["dettagli"]["byte"] == 2_500_020
    finally:
        b.chiudi()


# ---------------------------------------------------------------- M2 marcatore oltre la fine
def test_rev_D5_marcatore_oltre_la_fine_torna_a_zero(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(10):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma() and p.drena().consegnate == 10
    f = next((a.cartella / "log").glob("*.jsonl"))
    a.chiudi()
    f.write_bytes(b"")                              # file perso/troncato (spegnimento, antivirus, utente)
    banco.archivio = ArchivioLocale("prova", SPEC, base=a.cartella.parent, orologio_ms=banco.adesso).apri()
    banco.postino = PostinoLocale(banco.archivio, banco.cloud, orologio_ms=banco.adesso)
    for i in range(100, 103):
        banco.archivio.scrivi("mike_activity", riga_attivita(i))
    assert banco.archivio.conferma()
    p2 = banco.postino
    p2.drena()
    assert len(banco.righe("mike_activity")) == 13, "le 3 righe scritte dopo non vengono mai consegnate ne' contate"
    assert any(s["tipo"] == "marcatore_log_azzerato" for s in banco.archivio.segnalazioni())


def test_rev_D5b_file_sostituito_piu_lungo_del_marcatore(banco: Banco) -> None:
    """Il file sostituito e GIA' piu' lungo del vecchio marcatore: lo dice la firma della prima riga."""
    a, p = banco.archivio, banco.postino
    for i in range(3):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma() and p.drena().consegnate == 3
    f = next((a.cartella / "log").glob("*.jsonl"))
    a.chiudi()
    f.write_bytes(b"")
    banco.archivio = ArchivioLocale("prova", SPEC, base=a.cartella.parent, orologio_ms=banco.adesso).apri()
    banco.postino = PostinoLocale(banco.archivio, banco.cloud, orologio_ms=banco.adesso)
    for i in range(100, 120):
        banco.archivio.scrivi("mike_activity", riga_attivita(i))
    assert banco.archivio.conferma()
    for _ in range(5):
        if not banco.postino.drena().consegnate:
            break
    assert len(banco.righe("mike_activity")) == 23


# ---------------------------------------------------------------- M3 versione uguale / orologio indietro
def test_rev_D6_stessa_versione_vince_l_ultima_scritta(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2025-10-09T10:00:00+00:00", size_matched=2.0))
    assert a.conferma() and p.drena().errore is None
    stato = banco.righe("betfair_live_orders")[0]["status"]
    assert stato == "EXECUTION_COMPLETE", "stesso updated_at, contenuto diverso: l'aggiornamento e' perso in silenzio"


def test_rev_D6b_orologio_indietro_di_3_s_vince_l_ultima_scritta(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:10+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2025-10-09T10:00:07+00:00"))   # NTP: -3 s
    assert a.conferma() and p.drena().errore is None
    assert banco.righe("betfair_live_orders")[0]["status"] == "EXECUTION_COMPLETE"
    # terza revisione R1: updated_at TALE E QUALE (prima: spostato a "precedente + 1 us")
    assert banco.righe("betfair_live_orders")[0]["updated_at"] == "2025-10-09T10:00:07+00:00"


def test_rev_M3_orologio_indietro_di_9_s_vince_l_ultima_scritta(banco: Banco) -> None:
    """Terza revisione R1 (principio "identico a oggi"): prima della terza revisione la
    scrittura con updated_at 9 s piu' vecchio era scartata come stantia; ora VINCE, come
    oggi vince l'ultimo upsert, e nessun evento di riga vecchia."""
    a, p = banco.archivio, banco.postino
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:10+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "PENDING", "2025-10-09T10:00:01+00:00"))       # -9 s
    assert a.conferma() and p.drena().errore is None
    assert banco.righe("betfair_live_orders")[0]["status"] == "PENDING"
    assert banco.righe("betfair_live_orders")[0]["updated_at"] == "2025-10-09T10:00:01+00:00"
    assert banco.nomi().count("dati.riga_vecchia") == 0


# ---------------------------------------------------------------- B2 coalescenza che fonde
def test_rev_D7_coalescenza_fonde_le_colonne_degli_upsert_parziali(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    base = {"event_id": "e9", "home_name": "A", "away_name": "B", "open_date": "2026-10-09T18:00:00+00:00"}
    a.scrivi("live_follow", {**base, "status": "ERROR", "error_detail": "boom", "updated_at": "2026-10-09T10:00:00+00:00"})
    a.scrivi("live_follow", {"event_id": "e9", "status": "RUNNING", "updated_at": "2026-10-09T10:00:05+00:00"})   # parziale
    assert a.conferma() and p.drena().errore is None
    righe = banco.righe("live_follow")
    assert righe and righe[0]["home_name"] == "A" and righe[0]["error_detail"] == "boom"
    assert a.leggi("live_follow", {"event_id": "e9"})["home_name"] == "A"             # anche in locale


# ---------------------------------------------------------------- M5 claim con due commit
class _ConnFallisceCommit:
    def __init__(self, conn, falli=1):
        self._c, self.falli = conn, falli

    def execute(self, sql, *a):
        if sql.strip().upper() == "COMMIT" and self.falli > 0:
            self.falli -= 1
            raise sqlite3.OperationalError("disk I/O error (prova)")
        return self._c.execute(sql, *a)

    def __getattr__(self, k):
        return getattr(self._c, k)


def test_rev_D8_claim_riuscito_riferito_vero_anche_se_il_secondo_commit_fallisce(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "action": "place", "mode": "paper",
                                                 "status": "pending", "side": "back"})
        assert a.conferma()
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
        a._scrittori["stato_vivo"] = _ConnFallisceCommit(a._scrittori["stato_vivo"], 1)
        res: Dict[str, Any] = {}
        # meccanismo (dichiarato): lo scrittore e' trattenuto finche' il claim (denaro) e la riga del vivo
        # sono entrambi in coda, cosi' finiscono nello STESSO lotto in modo deterministico
        trattieni = threading.Event()
        from concurrent.futures import Future
        a._coda.put(mod._Lavoro(a._prossimo_n(), "stato_denaro", lambda c: trattieni.wait(10), Future()))
        t = threading.Thread(target=lambda: res.setdefault("claim", a.transizione(
            "betfair_live_order_requests", {"client_ref": "c1"}, "pending", "processing")))
        t.start()
        time.sleep(0.2)
        a.scrivi("live_follow", {"event_id": "e1", "home_name": "A", "away_name": "B", "status": "PENDING",
                                 "open_date": "2026-10-09T18:00:00+00:00", "updated_at": "2026-10-09T10:00:00+00:00"})
        trattieni.set()
        t.join(20)
        riga = a.leggi("betfair_live_order_requests", {"client_ref": "c1"})
        assert not (riga["status"] == "processing" and res.get("claim") is False), \
            "il claim e' avvenuto (status=processing) ma il chiamante ha ricevuto False"
        assert res.get("claim") is True
    finally:
        a.chiudi()


def test_rev_M5_claim_scaduto_prima_di_partire_non_avviene(tmp_path: Path) -> None:
    """Attesa scaduta mentre lo scrittore e' occupato: il lavoro si ANNULLA (esito vero:
    non avvenuto) e non parte piu' dopo."""
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "status": "pending"})
        assert a.conferma()
        sblocca = threading.Event()
        a._coda.put(mod._Lavoro(a._prossimo_n(), "stato_denaro", lambda c: sblocca.wait(10), __import__(
            "concurrent.futures").futures.Future()))                     # scrittore occupato
        with pytest.raises(TimeoutError):
            a._esegui_sincrono("stato_denaro", lambda c: c.execute(
                "UPDATE righe SET json = '{\"status\":\"processing\"}' WHERE tabella = 'betfair_live_order_requests'"),
                timeout_s=0.3)
        sblocca.set()
        assert a.conferma(10)
        assert a.leggi("betfair_live_order_requests", {"client_ref": "c1"})["status"] == "pending"
    finally:
        a.chiudi()


# ---------------------------------------------------------------- A4 classi di errore per riga
class CloudScript:
    """Cloud a copione: usa la stessa forma di risposta di postino_consegna."""
    def __init__(self, fn):
        self.fn, self.chiamate = fn, []

    def leggi(self, *a, **k):
        return []

    def rpc(self, nome, args, **k):
        self.chiamate.append((nome, args))
        return self.fn(args)


@pytest.mark.parametrize("codice", ["25006", "53100", "08006", "57P02"])
def test_rev_D9_sqlstate_transitorio_per_riga_non_va_in_dead_letter(tmp_path: Path, codice: str) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        for i in range(5):
            a.scrivi("mike_activity", riga_attivita(i))
        assert a.conferma()
        cloud = CloudScript(lambda args: [{"esito": "errore", "codice": codice, "messaggio": "x"} for _ in args["p_righe"]])
        p = PostinoLocale(a, cloud)
        e = p.drena()
        assert e.dead_letter == 0, f"{codice} (cloud in failover/disco pieno/connessione) manda 5 righe in dead_letter alla prima prova"
    finally:
        a.chiudi()


def test_rev_D9b_colonna_sconosciuta_blocca_la_tabella_niente_dead_letter(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(30):
        a.scrivi("mike_activity", riga_attivita(i, colonna_nuova=1))
    assert a.conferma()
    e = p.drena()
    assert e.dead_letter == 0
    assert banco.nomi().count("dati.postino_bloccato") == 1                   # segnalata UNA volta
    banco.avanza(61)
    p.drena()
    assert banco.nomi().count("dati.postino_bloccato") == 1 and p.stato().in_coda == 30


def test_rev_D10_padre_di_altro_processo_in_ritardo_il_figlio_aspetta(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("live_alerts", {"level": "INFO", "code": "b", "message": "m", "event_id": "35760084"})
    assert a.conferma()
    secondi = 0
    for _ in range(40):
        e = p.drena()
        if e.dead_letter:
            break
        banco.avanza(60)
        secondi += 60
    assert not a.dead_letter(), f"figlio in dead_letter dopo {secondi} s, il padre (altro processo) puo' arrivare piu' tardi"


# ---------------------------------------------------------------- M4 ordine per chiave
def test_rev_D11_patch_aspetta_l_upsert_fallito(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        riga = {"mode": "paper", "client_order_ref": "r1", "market_id": "1.2", "selection_id": 1, "side": "back",
                "price": 2.0, "size": 2.0, "status": "EXECUTABLE", "updated_at": "2026-10-09T10:00:00+00:00"}
        a.accoda("betfair_live_orders", "upsert", None, riga)
        a.accoda("betfair_live_orders", "patch", '["paper", "r1"]',
                 {"mode": "paper", "client_order_ref": "r1", "status": "CANCELLED", "updated_at": "2026-10-09T10:00:05+00:00"})
        stato = {"righe": {}}

        def fn(args):
            out = []
            for r in args["p_righe"]:
                if args["p_op"] == "upsert":
                    out.append({"esito": "errore", "codice": "40001", "messaggio": "serialization"})
                else:
                    out.append({"esito": "ok" if r["client_order_ref"] in stato["righe"] else "ignorata"})
            return out
        p = PostinoLocale(a, CloudScript(fn))
        p.drena()
        in_coda = a.conteggi_outbox("stato_denaro")[0]
        assert in_coda.get("betfair_live_orders", 0) == 2, "la patch e' stata data per consegnata ('ignorata') mentre la riga non esisteva ancora"
    finally:
        a.chiudi()


def test_rev_D11b_upsert_vecchio_ritentato_non_supera_il_nuovo(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "action": "place", "mode": "paper", "status": "pending"})
        a.scrivi("betfair_live_order_requests", {"client_ref": "c1", "action": "place", "mode": "paper", "status": "done"})
        assert a.conferma()
        cloud_righe: Dict[str, Any] = {}
        prima = {"n": 0}

        def fn(args):
            out = []
            for r in args["p_righe"]:
                prima["n"] += 1
                if prima["n"] == 1:                       # solo la PRIMA riga fallisce in modo transitorio
                    out.append({"esito": "errore", "codice": "40P01", "messaggio": "deadlock"})
                else:
                    cloud_righe[r["client_ref"]] = r["status"]
                    out.append({"esito": "ok"})
            return out
        now = [1_760_004_000_000]
        p = PostinoLocale(a, CloudScript(fn), orologio_ms=lambda: now[0])
        p.drena()
        now[0] += 10_000
        p.drena()
        assert cloud_righe["c1"] == "done", "lo stato vecchio 'pending' ha sovrascritto 'done' nel cloud"
    finally:
        a.chiudi()


# ---------------------------------------------------------------- E: lucchetto, auto_vacuum, import, disco
def test_rev_E1_lucchetto_rimasto_da_processo_morto(tmp_path: Path) -> None:
    c = tmp_path / "prova"
    c.mkdir()
    (c / ".lucchetto").write_text("99999")
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()      # un file di lucchetto vecchio non blocca
    a.chiudi()


FIGLIO_TIENE = r'''
import sys, time
from pathlib import Path
from Betfair.nucleo.dati.archivio import ArchivioLocale
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC
a = ArchivioLocale("prova", SPEC, base=Path(sys.argv[1])).apri()
print("pronto", flush=True)
time.sleep(60)
'''


def test_rev_E2_due_processi_stessa_cartella_e_morte_del_primo(tmp_path: Path) -> None:
    p = subprocess.Popen([sys.executable, "-c", FIGLIO_TIENE, str(tmp_path)], cwd=RADICE, stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "pronto"
        with pytest.raises(ArchivioOccupato):
            ArchivioLocale("prova", SPEC, base=tmp_path).apri()
        p.kill()                                                  # SIGKILL: niente chiudi(), niente rilascio manuale
        p.wait()
        a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
        a.chiudi()
    finally:
        p.kill()


def test_rev_E3_auto_vacuum_effettivo_e_il_file_si_restringe(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path, conserva_giorni={"stato_denaro": 0, "stato_vivo": 0, "log": 0}).apri()
    try:
        for regime in ("denaro", "vivo"):
            c = sqlite3.connect(a.cartella / f"{regime}.sqlite3")
            av = c.execute("PRAGMA auto_vacuum").fetchone()[0]
            assert av == 2, f"{regime}: auto_vacuum={av} (2=INCREMENTAL): il file non si restringe mai"
        for i in range(3000):
            a.scrivi("live_follow", {"event_id": f"e{i}", "home_name": "x" * 400, "away_name": "B", "status": "P",
                                     "open_date": "x", "updated_at": "2026-10-09T10:00:00+00:00"})
        assert a.conferma(60)
        voci = [v.seq for v in a.outbox_pronta("stato_vivo", 2 ** 62, 5000)]
        a.chiudi_voci("stato_vivo", voci, [], [])
        assert a.conferma()
        sqlite3.connect(a.cartella / "vivo.sqlite3").execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        pagine = lambda: a._leggi_uno("stato_vivo", "PRAGMA page_count", ())[0]  # noqa: E731
        prima = pagine()
        from Betfair.nucleo.dati.schema_locale import giorno_utc
        a.scrivi_riconciliazione("live_follow", giorno_utc(a._ora_ms()), "ok", {})
        assert a.pulisci(adesso_ms=a._ora_ms() + 86_400_000)["stato_vivo"] == 3000
        assert pagine() < prima / 2, (prima, pagine())
    finally:
        a.chiudi()


def test_rev_E4_import_senza_effetti(tmp_path: Path) -> None:
    codice = ("import threading, sys\nn0 = threading.active_count()\nimport Betfair.nucleo.dati.archivio, "
              "Betfair.nucleo.dati.postino, Betfair.nucleo.dati.riconcilia, Betfair.nucleo.dati.percorso, "
              "Betfair.nucleo.dati.schema_locale\nassert threading.active_count() == n0\n"
              "assert 'supabase' not in sys.modules and 'httpx' not in sys.modules, [m for m in ('supabase','httpx') if m in sys.modules]\n"
              "assert 'config' not in sys.modules and 'db_client' not in sys.modules\nprint('ok')")
    env = {**os.environ, "HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "x"), "LOCALAPPDATA": str(tmp_path / "y")}
    r = subprocess.run([sys.executable, "-c", codice], cwd=RADICE, capture_output=True, text=True, env=env)
    assert r.stdout.strip() == "ok", r.stderr[-1500:]
    assert not (tmp_path / "x").exists() and not (tmp_path / "y").exists()


def test_rev_E5_percorso_mai_nel_repo(tmp_path: Path) -> None:
    with pytest.raises(PercorsoNonAmmesso):
        cartella_base({"ARCH_ARCHIVIO_DIR": str(RADICE / "dati_locali")})
    with pytest.raises(PercorsoNonAmmesso):
        cartella_base({"ARCH_ARCHIVIO_DIR": str(RADICE / "a" / ".." / "b")})
    link = tmp_path / "ln"
    try:
        link.symlink_to(RADICE)                                     # symlink verso il repo
    except OSError:
        pytest.skip("collegamenti simbolici non permessi su questo sistema")
    with pytest.raises(PercorsoNonAmmesso):
        cartella_base({"ARCH_ARCHIVIO_DIR": str(link / "dati")})


def test_rev_E6_cartella_non_creabile_solleva_oserror_documentato(tmp_path: Path) -> None:
    """B3 (documenta): ``apri()`` solleva ``OSError``; l'aggancio resta su "vecchio"."""
    (tmp_path / "file").write_text("x")
    with pytest.raises(OSError) as e:
        ArchivioLocale("prova", SPEC, base=tmp_path / "file").apri()
    assert not isinstance(e.value, ArchivioOccupato)
    assert "OSError" in (ArchivioLocale.apri.__doc__ or "")


DISCO_PIENO = r'''
import os, resource, signal, sys, time
from pathlib import Path
from Betfair.nucleo.dati.archivio import ArchivioLocale
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, riga_attivita, riga_ordine
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
base = Path(sys.argv[1])
eventi = []
a = ArchivioLocale("prova", SPEC, base=base, eventi=lambda n, d: eventi.append(n)).apri()
for i in range(50):
    a.scrivi("mike_activity", riga_attivita(i))
a.conferma()
resource.setrlimit(resource.RLIMIT_FSIZE, (200_000, resource.getrlimit(resource.RLIMIT_FSIZE)[1]))   # "disco pieno"
for i in range(50, 3050):
    a.scrivi("mike_activity", riga_attivita(i, payload={"i": i, "pad": "z" * 400}))
    a.scrivi("betfair_live_orders", riga_ordine("r%d" % i, "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
time.sleep(3)
print("guasto", a.guasto, "eventi", sorted(set(eventi)), flush=True)
resource.setrlimit(resource.RLIMIT_FSIZE, (resource.RLIM_INFINITY, resource.getrlimit(resource.RLIMIT_FSIZE)[1]))
ok = a.conferma(120)
print("conferma_dopo_sblocco", ok, flush=True)
a.chiudi()
'''


@pytest.mark.skipif(not sys.platform.startswith(("linux", "darwin")), reason="RLIMIT_FSIZE solo su POSIX")
def test_rev_E8_disco_pieno_poi_libero_nessuna_perdita(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, "-c", DISCO_PIENO, str(tmp_path)], cwd=RADICE, capture_output=True, text=True, timeout=240)
    assert "conferma_dopo_sblocco True" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    cart = tmp_path / "prova"
    righe = []
    for f in sorted((cart / "log").glob("*.jsonl")):
        for x in f.read_bytes().split(b"\n"):
            if x.strip():
                righe.append(json.loads(x))             # una riga corrotta a meta' file fa fallire qui
    interi = {x["r"]["payload"]["i"] for x in righe}
    assert interi == set(range(3050)), f"mancano {sorted(set(range(3050)) - interi)[:10]}"
    ordini = sqlite3.connect(cart / "denaro.sqlite3").execute("SELECT count(*) FROM righe").fetchone()[0]
    assert ordini == 3000
    out = sqlite3.connect(cart / "denaro.sqlite3").execute("SELECT count(*) FROM outbox").fetchone()[0]
    assert out == 3000


def test_rev_E9_conferma_non_aspetta_una_pulizia_grossa(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path, pulizia_ogni_s=1e9,
                       conserva_giorni={"stato_denaro": 0, "stato_vivo": 0, "log": 0}).apri()
    try:
        c = sqlite3.connect(a.cartella / "denaro.sqlite3", timeout=60)
        c.execute("BEGIN")
        c.executemany("INSERT INTO righe (tabella, chiave, json, rev, aggiornato_ms) VALUES (?,?,?,?,?)",
                      [("betfair_live_orders", '["paper", "r%d"]' % i, '{"x":%d,"pad":"%s"}' % (i, "p" * 200), None, 1000 + i)
                       for i in range(600_000)])
        c.execute("INSERT INTO riconciliazioni (tabella, giorno, esito, dettagli, ts_ms) VALUES ('betfair_live_orders','1970-01-01','ok','{}',0)")
        c.execute("COMMIT")
        c.close()
        lat = []
        stop = threading.Event()

        def pulisce():
            a.pulisci()
            stop.set()

        th = threading.Thread(target=pulisce)
        th.start()
        time.sleep(0.05)
        while not stop.is_set():
            t0 = time.perf_counter()
            a.scrivi("mike_activity", riga_attivita(1))
            a.conferma(60)
            lat.append(time.perf_counter() - t0)
            time.sleep(0.05)
        th.join()
        assert max(lat) < 1.0, f"conferma() bloccata {max(lat):.2f} s dalla pulizia nello stesso thread di scrittura"
    finally:
        a.chiudi()


def test_rev_E10_chiusura_con_disco_guasto_le_righe_accettate_rientrano(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    a._scrittori["stato_denaro"] = _ConnFallisceCommit(a._scrittori["stato_denaro"], 10**6)   # il disco non scrive piu'
    for i in range(20):
        a.scrivi("betfair_live_orders", riga_ordine(f"r{i}", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))   # accettate
    time.sleep(0.2)
    a.chiudi(5)
    a2 = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        n = a2.conteggi_outbox("stato_denaro")[0].get("betfair_live_orders", 0)
        assert n == 20 or a2.dead_letter(), "20 righe accettate da scrivi() sparite alla chiusura, senza traccia"
        assert n == 20 and not list(a2.cartella.glob("salvataggio-*.jsonl"))
    finally:
        a2.chiudi()


# ---------------------------------------------------------------- R1, R7, R13 (test_rev_d del revisore)
def test_rev_R7_riga_di_log_a_meta_scrittura_non_si_salta_ne_si_perde(banco: Banco) -> None:
    """R7: l'ultima riga senza \\n (lo scrittore sta ancora scrivendo) non e' ne' consegnata ne' scartata."""
    a, p = banco.archivio, banco.postino
    a.scrivi("mike_activity", riga_attivita(0))
    assert a.conferma()
    f = next((a.cartella / "log").glob("*.jsonl"))
    intera = f.read_bytes()
    uid = json.loads(intera)["r"]["uid"].encode()
    seconda = intera.replace(uid, b"00000000-0000-4000-8000-000000000001").replace(b'"i":0', b'"i":1')
    with open(f, "ab") as fh:                                   # una seconda riga scritta a meta'
        fh.write(seconda[: len(seconda) // 2])
    assert p.drena().consegnate == 1                            # solo la riga completa
    assert not a.segnalazioni(), "la riga a meta' scrittura e' stata scambiata per una riga guasta"
    with open(f, "ab") as fh:                                   # lo scrittore finisce la riga
        fh.write(seconda[len(seconda) // 2:])
    assert p.drena().consegnate == 1
    assert [r["payload"]["i"] for r in banco.righe("mike_activity")] == [0, 1]


def test_rev_R1_pulizia_non_toglie_un_file_di_log_non_consegnato(banco: Banco) -> None:
    """R1: un file vecchio, riconciliato 'ok' per errore ma con righe NON ancora consegnate, resta."""
    a = banco.archivio
    for i in range(3):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    a.scrivi_riconciliazione("mike_activity", "2025-10-09", "ok", {})
    assert a.pulisci(adesso_ms=banco.adesso() + 10 * 86_400_000)["file_log"] == 0
    assert len(list((a.cartella / "log").glob("*.jsonl"))) == 1
    assert banco.postino.drena().consegnate == 3


def test_rev_R13_leggi_vede_l_ultima_scritta_prima_e_dopo_il_commit(banco: Banco) -> None:
    """R13 (riletto con la terza revisione R1): leggi() vede SEMPRE l'ultima scrittura
    accodata, prima e dopo il commit, qualunque sia il suo updated_at (stessa regola dello
    scrittore: nessuna regressione fra vista in attesa e disco)."""
    a = banco.archivio
    a.scrivi("betfair_live_orders", riga_ordine("r1", "PRIMA", "2025-10-09T10:00:10+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "ULTIMA", "2025-10-09T10:00:01+00:00"))
    assert a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"})["status"] == "ULTIMA"
    assert a.conferma()
    assert a.leggi("betfair_live_orders", {"mode": "paper", "client_order_ref": "r1"})["status"] == "ULTIMA"
