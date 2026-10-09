"""W1-G1 - postino: consegna, idempotenza, versione, offline, dead_letter, padre/figlio, ombra, riconcilia.

Client supabase VERO (supabase-py + postgrest + httpx) su ``httpx.MockTransport``; dietro, il
PostgREST finto di ``test_g1_finti`` con le forme vere delle tabelle e la semantica delle RPC
della migrazione (la stessa sequenza gira sul PostgreSQL vero in ``test_g1_pg_reale.py``).
Orologio comandato: le attese (2-4-8-16-32 s, tetto 60) si provano senza dormire.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

from Betfair.nucleo.dati.archivio import ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.contratto import Postino  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.riconcilia import confronta_ombra, normalizza_chiave  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_archivio import conforme  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import (SPEC, CloudProva, PostgrestFinto, riga_attivita,  # noqa: E402
                                                     riga_ordine)

T0 = 1_760_004_000_000          # 2025-10-09T10:00:00Z


class Banco:
    """Archivio + postino + cloud finto con un orologio comune."""

    def __init__(self, tmp: Path, server: PostgrestFinto | None = None, **kw: Any) -> None:
        self.ora = [T0]
        self.eventi: List[Tuple[str, Dict[str, Any]]] = []
        self.server = server or PostgrestFinto()
        self.cloud = CloudProva(self.server)
        self.archivio = ArchivioLocale("prova", SPEC, base=tmp, orologio_ms=self.adesso,
                                       eventi=self.registra).apri()
        self.postino = PostinoLocale(self.archivio, self.cloud, orologio_ms=self.adesso, eventi=self.registra, **kw)

    def adesso(self) -> int:
        return self.ora[0]

    def avanza(self, s: float) -> None:
        self.ora[0] += int(s * 1000)

    def registra(self, nome: str, dati: Any) -> None:
        self.eventi.append((nome, dict(dati)))

    def nomi(self) -> List[str]:
        return [n for n, _ in self.eventi]

    def righe(self, tabella: str) -> List[Dict[str, Any]]:
        return self.server.tabelle[tabella].righe

    def chiudi(self) -> None:
        self.archivio.chiudi()


@pytest.fixture
def banco(tmp_path: Path):
    b = Banco(tmp_path)
    yield b
    b.chiudi()


def test_protocollo_postino(banco: Banco) -> None:
    assert conforme(PostinoLocale, Postino)


def test_consegna_log_e_stato_stesse_colonne(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(5):
        a.scrivi("mike_activity", riga_attivita(i))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma()
    assert p.stato().in_coda == 6
    esito = p.drena()
    assert (esito.consegnate, esito.ritentate, esito.dead_letter, esito.errore) == (6, 0, 0, None)
    st = p.stato()
    assert st.in_coda == 0 and st.dead_letter == 0 and st.eta_max_s is None
    righe = banco.righe("mike_activity")
    assert [r["payload"]["i"] for r in righe] == [0, 1, 2, 3, 4]
    assert set(righe[0]) == {"id", "ts", "event_id", "kind", "payload", "uid"}   # le colonne vere, niente di piu'
    assert righe[0]["ts"] == "2025-10-09T10:00:00.000+00:00"                     # istante dell'evento, non della consegna
    assert banco.righe("betfair_live_orders")[0]["status"] == "EXECUTABLE"
    assert p.drena().consegnate == 0                                             # niente due volte


def test_ritento_dopo_risposta_persa_zero_duplicati(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(10):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    banco.server.copione = ["applica_poi_perdi"]       # il DB applica, la risposta si perde (GOAWAY)
    e1 = p.drena()
    assert e1.consegnate == 0 and "offline" in (e1.errore or "")
    assert len(banco.righe("mike_activity")) == 10      # gia' nel cloud...
    banco.avanza(2.0)
    e2 = p.drena()
    assert e2.consegnate == 10                          # ...ritentate: ON CONFLICT (uid) DO NOTHING
    assert len(banco.righe("mike_activity")) == 10      # 0 duplicati
    assert banco.postino.contatori["ignorate"] == 10
    assert p.stato().in_coda == 0


def test_cloud_fermo_coda_cresce_allarme_e_ripresa(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    banco.server.offline = True
    attese = []
    for giro in range(7):
        a.scrivi("mike_activity", riga_attivita(giro))
        a.scrivi("betfair_live_orders", riga_ordine(f"r{giro}", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
        assert a.conferma()
        e = p.drena()
        assert e.consegnate == 0 and e.errore and e.errore.startswith("offline")
        attese.append((p._prossimo_giro_ms - banco.adesso()) / 1000.0)
        assert p.drena().errore.startswith("in attesa")                         # niente martellamento
        banco.avanza(61)
    assert attese == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]                    # G par. 4.2, tetto 60 s
    st = p.stato()
    assert st.in_coda == 14 and st.offline_da is not None and st.eta_max_s >= 6 * 61
    assert st.per_tabella == {"mike_activity": 7, "betfair_live_orders": 7}
    assert banco.nomi().count("dati.postino_offline") == 1                      # allarme una volta
    assert banco.righe("mike_activity") == []
    banco.server.offline = False
    assert p.drena().consegnate == 14
    assert p.stato().in_coda == 0 and p.offline_da is None
    assert "dati.postino_online" in banco.nomi()
    assert len(banco.righe("mike_activity")) == 7 and len(banco.righe("betfair_live_orders")) == 7


@pytest.mark.parametrize("guasto", ["connect", "goaway", "html520"])
def test_guasti_di_rete_veri_sono_offline_mai_dead_letter(banco: Banco, guasto: str) -> None:
    banco.archivio.scrivi("mike_activity", riga_attivita(1))
    assert banco.archivio.conferma()
    banco.server.copione = [guasto]
    e = banco.postino.drena()
    assert e.errore.startswith("offline") and e.dead_letter == 0
    banco.avanza(2)
    assert banco.postino.drena().consegnate == 1


def test_check_rifiutato_va_in_dead_letter_visibile_le_altre_passano(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("betfair_live_orders", riga_ordine("buona1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("cattiva", "EXECUTABLE", "2025-10-09T10:00:00+00:00", side="BACK"))
    a.scrivi("betfair_live_orders", riga_ordine("buona2", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.dead_letter) == (2, 1)
    morte = a.dead_letter()
    assert len(morte) == 1 and morte[0]["codice"] == "23514" and morte[0]["riga"]["client_order_ref"] == "cattiva"
    assert p.stato().dead_letter == 1 and p.stato().in_coda == 0
    ev = [d for n, d in banco.eventi if n == "dati.dead_letter"]
    assert len(ev) == 1 and ev[0]["riga"]["side"] == "BACK" and "23514" in ev[0]["errore"]
    assert p.drena().consegnate == 0                                             # mai ritentata in eterno
    # dopo la correzione si rimette in coda e passa
    rid = a.rimetti_in_coda("stato_denaro", morte[0]["id"])
    assert rid > 0 and a.dead_letter() == []


def test_check_rifiutato_sui_log_dead_letter_senza_bloccare_il_file(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    banco.server.tabelle["live_follow"].righe.append({"event_id": "35760084"})
    a.scrivi("live_alerts", {"level": "INFO", "code": "a", "message": "m", "event_id": "35760084"})
    a.scrivi("live_alerts", {"level": "GRAVE", "code": "b", "message": "m", "event_id": "35760084"})
    a.scrivi("live_alerts", {"level": "WARN", "code": "c", "message": "m", "event_id": "35760084"})
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.dead_letter) == (2, 1)
    assert [r["code"] for r in banco.righe("live_alerts")] == ["a", "c"]
    assert [m["fonte"] for m in a.dead_letter()] == ["log"]
    assert p.stato().in_coda == 0


def test_23503_transitorio_poi_consegnato_quando_arriva_il_padre(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("live_alerts", {"level": "INFO", "code": "a", "message": "m", "event_id": "padre_altrove"})
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.ritentate, e.dead_letter) == (0, 1, 0)
    assert p.stato().in_coda == 1                                                # promossa in outbox, non persa
    banco.server.tabelle["live_follow"].righe.append({"event_id": "padre_altrove"})   # il padre lo scrive un altro processo
    assert p.drena().consegnate == 0                                             # attende il suo turno (2 s)
    banco.avanza(2)
    assert p.drena().consegnate == 1
    assert len(banco.righe("live_alerts")) == 1


def test_23503_oltre_il_tetto_va_in_dead_letter_con_allarme(tmp_path: Path) -> None:
    b = Banco(tmp_path, tetto_tentativi_riga=3)
    try:
        b.archivio.scrivi("live_alerts", {"level": "INFO", "code": "a", "message": "m", "event_id": "mai"})
        assert b.archivio.conferma()
        esiti = []
        for _ in range(5):
            esiti.append(b.postino.drena())
            b.avanza(61)
        assert [x.ritentate for x in esiti[:2]] == [1, 1] and esiti[2].dead_letter == 1
        assert b.archivio.dead_letter()[0]["codice"] == "23503"
        assert "dati.dead_letter" in b.nomi() and b.postino.stato().in_coda == 0
    finally:
        b.chiudi()


def test_padre_prima_del_figlio_nello_stesso_giro(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("live_alerts", {"level": "INFO", "code": "a", "message": "m", "event_id": "35999999"})   # figlio prima
    a.scrivi("live_follow", {"event_id": "35999999", "home_name": "A", "away_name": "B", "status": "PENDING",
                             "open_date": "2025-10-09T18:00:00+00:00", "updated_at": "2025-10-09T10:00:00+00:00"})
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.ritentate) == (2, 0)
    ordine = [c["p_tabella"] for rotta, c in banco.server.richieste if rotta == "/rpc/postino_consegna"]
    assert ordine == ["live_follow", "live_alerts"]


def test_figlio_aspetta_se_il_padre_non_passa(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("live_follow", {"event_id": "e1", "home_name": "A", "away_name": "B", "status": "STATO_NON_AMMESSO",
                             "open_date": "x", "updated_at": "2025-10-09T10:00:00+00:00"})
    a.scrivi("live_alerts", {"level": "INFO", "code": "a", "message": "m", "event_id": "e1"})
    assert a.conferma()
    banco.server.tabelle["live_follow"].check = [("live_follow_status_check", lambda r: r.get("status") != "STATO_NON_AMMESSO")]
    e = p.drena()
    assert e.dead_letter == 1 and e.consegnate == 0
    richieste = [c["p_tabella"] for rotta, c in banco.server.richieste]
    assert richieste == ["live_follow"]                                          # il figlio non e' partito
    assert p.stato().in_coda == 1


def test_riga_vecchia_tardiva_non_riporta_indietro_il_cloud(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    # il cloud ha gia' la versione nuova (scritta da un altro giro); arriva tardi la vecchia
    banco.server.consegna("betfair_live_orders", "upsert", ["mode", "client_order_ref"], "updated_at",
                          [riga_ordine("r1", "EXECUTION_COMPLETE", "2025-10-09T10:00:09+00:00")])
    a.accoda("betfair_live_orders", "upsert", None, riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:01+00:00"))
    e = p.drena()
    assert e.consegnate == 1 and p.contatori["ignorate"] == 1
    assert banco.righe("betfair_live_orders")[0]["status"] == "EXECUTION_COMPLETE"
    # e la nuova invece passa
    a.scrivi("betfair_live_orders", riga_ordine("r1", "CANCELLED", "2025-10-09T10:00:10+00:00"))
    assert a.conferma() and p.drena().consegnate == 1
    assert banco.righe("betfair_live_orders")[0]["status"] == "CANCELLED"


def test_57014_dimezza_il_blocco(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(8):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    banco.server.copione = ["57014"]
    e = p.drena()
    assert e.consegnate == 0 and "57014" in e.errore
    assert p._blocco_tabella["mike_activity"] == 4
    assert p.drena().consegnate == 8
    dimensioni = [len(c["p_righe"]) for rotta, c in banco.server.richieste if c.get("p_righe")]
    assert dimensioni[-2:] == [4, 4]


def test_rpc_assente_tabella_bloccata_mai_dead_letter(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("mike_activity", riga_attivita(1))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma()
    banco.server.senza_rpc = True                                                # migrazione non applicata
    e = p.drena()
    assert e.dead_letter == 0 and e.consegnate == 0 and "PGRST202" in e.errore
    assert "dati.postino_bloccato" in banco.nomi()
    assert p.stato().in_coda == 2 and a.dead_letter() == []
    banco.server.senza_rpc = False
    banco.avanza(2)
    assert p.drena().consegnate == 2


def test_permesso_negato_per_riga_blocca_non_uccide(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("mike_activity", riga_attivita(1))
    assert a.conferma()
    orig = banco.server.consegna
    banco.server.consegna = lambda *x: [{"esito": "errore", "codice": "42501",  # type: ignore[method-assign]
                                         "messaggio": "permission denied for table mike_activity"}]
    e = p.drena()
    assert e.dead_letter == 0 and a.dead_letter() == [] and p.stato().in_coda == 1
    banco.server.consegna = orig  # type: ignore[method-assign]
    banco.avanza(2)
    assert p.drena().consegnate == 1


def test_ombra_scrive_solo_sulle_tabelle_ombra(tmp_path: Path) -> None:
    b = Banco(tmp_path, ombra=True)
    try:
        b.archivio.scrivi("mike_activity", riga_attivita(1))
        b.archivio.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
        assert b.archivio.conferma()
        assert b.postino.drena().consegnate == 2
        assert b.righe("mike_activity") == [] and b.righe("betfair_live_orders") == []
        assert len(b.righe("mike_activity_ombra")) == 1 and len(b.righe("betfair_live_orders_ombra")) == 1
        # criterio di T8: il vecchio scrittore ha scritto la sua riga nella vera (senza uid)
        b.server.tabelle["mike_activity"].righe.append({"id": 1, "kind": "giro", "event_id": "35760084",
                                                        "ts": "2025-10-09T10:00:00.000+00:00", "uid": None})
        da = datetime(2025, 10, 9, tzinfo=timezone.utc)
        assert confronta_ombra(b.cloud, "mike_activity", ["kind", "event_id"], "ts", da) == []
        b.server.tabelle["mike_activity"].righe.append({"id": 2, "kind": "giro", "event_id": "35760084",
                                                        "ts": "2025-10-09T11:00:00.000+00:00", "uid": None})
        diff = confronta_ombra(b.cloud, "mike_activity", ["kind", "event_id"], "ts", da)
        assert diff == [{"giorno": "2025-10-09", "gruppo": ["giro", "35760084"], "vera": 2, "ombra": 1}]
    finally:
        b.chiudi()


def test_tetto_di_disco_segnale_di_ripiego_mai_perdita(tmp_path: Path) -> None:
    b = Banco(tmp_path, tetto_disco_mb=0.05)
    try:
        b.server.offline = True
        for i in range(400):
            b.archivio.scrivi("mike_activity", riga_attivita(i, payload={"i": i, "pad": "x" * 200}))
        assert b.archivio.conferma()
        b.postino.drena()
        st = b.postino.stato()
        assert b.postino.ripiego_diretto is True and "dati.tetto_disco" in b.nomi()
        assert st.in_coda == 400                                                 # niente scartato
        b.server.offline = False
        b.avanza(61)
        while b.postino.drena().consegnate:
            pass
        assert len(b.righe("mike_activity")) == 400
    finally:
        b.chiudi()


def test_riconcilia_mancanti_in_piu_diverse(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    for i in range(4):
        a.scrivi("mike_activity", riga_attivita(i))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r2", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma() and p.drena().consegnate == 6
    da = datetime(2025, 10, 9, tzinfo=timezone.utc)
    vuoto = p.riconcilia("mike_activity", da)
    assert (vuoto.righe_locali, vuoto.righe_cloud, vuoto.mancanti_nel_cloud, vuoto.in_piu_nel_cloud) == (4, 4, (), ())
    persa = banco.righe("mike_activity").pop(1)                                 # il cloud perde una riga
    banco.righe("mike_activity").append({"id": 99, "kind": "x", "uid": "estranea", "ts": "2025-10-09T12:00:00+00:00"})
    r = p.riconcilia("mike_activity", da)
    assert r.mancanti_nel_cloud == (normalizza_chiave([persa["uid"]]),)
    assert r.in_piu_nel_cloud == (normalizza_chiave(["estranea"]),)
    banco.righe("betfair_live_orders")[1]["updated_at"] = "2025-10-09T09:00:00+00:00"   # versione diversa
    r2 = p.riconcilia("betfair_live_orders", da)
    assert r2.diverse == (normalizza_chiave(["paper", "r2"]),) and r2.mancanti_nel_cloud == ()
    assert "dati.riconciliazione" in banco.nomi()


def test_riconcilia_non_conta_come_mancante_cio_che_e_in_coda(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma()
    r = p.riconcilia("betfair_live_orders", datetime(2025, 10, 9, tzinfo=timezone.utc))
    assert r.righe_locali == 1 and r.mancanti_nel_cloud == ()


def test_riconcilia_giorno_scrive_il_marcatore_della_pulizia(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.scrivi("mike_activity", riga_attivita(1))
    assert a.conferma() and p.drena().consegnate == 1
    rapporti = p.riconcilia_giorno("2025-10-09", ["mike_activity"])
    assert rapporti[0].righe_cloud == 1
    assert a.riconciliazione("mike_activity", "2025-10-09") == "ok"
    banco.righe("mike_activity").clear()
    p.riconcilia_giorno("2025-10-09", ["mike_activity"])
    assert a.riconciliazione("mike_activity", "2025-10-09") == "differenze"


def test_ordine_delle_operazioni_sulla_stessa_chiave(banco: Banco) -> None:
    a, p = banco.archivio, banco.postino
    a.accoda("betfair_live_order_requests", "upsert", None, {"client_ref": "c1", "status": "pending"})
    a.accoda("betfair_live_order_requests", "patch", None, {"client_ref": "c1", "status": "processing"})
    a.accoda("betfair_live_order_requests", "upsert", None, {"client_ref": "c1", "status": "done"})
    assert p.drena().consegnate == 3
    assert banco.righe("betfair_live_order_requests")[0]["status"] == "done"
    ops = [c["p_op"] for rotta, c in banco.server.richieste]
    assert ops == ["upsert", "patch", "upsert"]


def test_thread_del_postino_drena_da_solo(tmp_path: Path) -> None:
    srv = PostgrestFinto()
    archivio = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    postino = PostinoLocale(archivio, CloudProva(srv))
    try:
        postino.avvia(intervallo_s=0.02)
        for i in range(30):
            archivio.scrivi("mike_activity", riga_attivita(i))
        import time
        fine = time.monotonic() + 10
        while len(srv.tabelle["mike_activity"].righe) < 30 and time.monotonic() < fine:
            time.sleep(0.02)
        assert len(srv.tabelle["mike_activity"].righe) == 30
        time.sleep(0.1)                                                     # qualche giro a vuoto
        assert postino.ultimo_errore is None                                # nessun giro fallito
        assert postino._thread is not None and postino._thread.is_alive()
    finally:
        postino.ferma()
        archivio.chiudi()
