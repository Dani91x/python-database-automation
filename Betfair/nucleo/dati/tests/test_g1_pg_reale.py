"""W1-G1 - le stesse prove del postino contro un PostgreSQL VERO con la migrazione applicata.

Si accende SOLO con ``G1_PG_PSQL`` (es. ``"-h /tmp -p 54329 -U postgres"``) che punta a un
PostgreSQL USA-E-GETTA locale (socket in ``/tmp`` o ``127.0.0.1``), con le migrazioni di base
del repo e ``migrations/architettura_uid_ombra_2026-10-09.sql`` applicate e i ruoli finti di
Supabase (anon, authenticated, service_role BYPASSRLS). MAI un DB vero: il test rifiuta un
host che non sia locale, e svuota (TRUNCATE) solo le tabelle che usa.
Client supabase VERO -> ``httpx.MockTransport`` -> ``PgPonte`` -> ``psql`` come ``service_role``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

from Betfair.nucleo.dati.archivio import ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.riconcilia import confronta_ombra  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import (SPEC, CloudProva, PgPonte, psql, psql_argomenti,  # noqa: E402
                                                     riga_attivita, riga_ordine)

ARGS = psql_argomenti()
pytestmark = pytest.mark.skipif(ARGS is None, reason="G1_PG_PSQL non impostata: PostgreSQL usa-e-getta assente")

TABELLE = ["mike_activity", "mike_activity_ombra", "live_alerts", "live_follow", "betfair_live_orders",
           "betfair_live_orders_ombra", "betfair_live_order_requests", "postino_versioni"]


def _solo_locale() -> None:
    assert ARGS is not None
    host = ARGS[ARGS.index("-h") + 1] if "-h" in ARGS else ""
    assert host.startswith("/tmp") or host in ("127.0.0.1", "localhost"), f"host non locale: {host}"


def sql(testo: str) -> str:
    r = psql(testo)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def righe(tabella: str) -> List[Dict[str, Any]]:
    out = sql(f"SELECT coalesce(json_agg(t ORDER BY 1), '[]') FROM public.{tabella} AS t;")
    return json.loads(out)


@pytest.fixture
def pg(tmp_path: Path):
    _solo_locale()
    sql("TRUNCATE " + ", ".join(f"public.{t}" for t in TABELLE) + " RESTART IDENTITY CASCADE;")
    ora = [1_760_004_000_000]
    eventi: List[str] = []
    srv = PgPonte()
    a = ArchivioLocale("prova", SPEC, base=tmp_path, orologio_ms=lambda: ora[0]).apri()
    p = PostinoLocale(a, CloudProva(srv), orologio_ms=lambda: ora[0], eventi=lambda n, d: eventi.append(n))
    yield a, p, srv, ora, eventi
    a.chiudi()


def test_pg_consegna_idempotente_e_colonne_vere(pg) -> None:
    a, p, srv, ora, _ = pg
    for i in range(5):
        a.scrivi("mike_activity", riga_attivita(i))
    assert a.conferma()
    srv.copione = ["applica_poi_perdi"]
    assert p.drena().errore.startswith("offline")
    assert len(righe("mike_activity")) == 5
    ora[0] += 2000
    assert p.drena().consegnate == 5
    r = righe("mike_activity")
    assert len(r) == 5 and len({x["uid"] for x in r}) == 5
    assert r[0]["ts"].startswith("2025-10-09T10:00:00")                   # istante dell'evento
    assert p.contatori["ignorate"] == 5


def test_pg_check_dead_letter_e_23503_poi_padre(pg) -> None:
    a, p, srv, ora, eventi = pg
    a.scrivi("live_alerts", {"level": "GRAVE", "code": "a", "message": "m"})
    a.scrivi("live_alerts", {"level": "INFO", "code": "b", "message": "m", "event_id": "35760084"})
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.ritentate, e.dead_letter) == (0, 1, 1)
    assert a.dead_letter()[0]["codice"] == "23514" and "dati.dead_letter" in eventi
    sql("INSERT INTO public.live_follow (event_id, home_name, away_name, open_date) "
        "VALUES ('35760084', 'A', 'B', now());")
    ora[0] += 2000
    assert p.drena().consegnate == 1
    assert [x["code"] for x in righe("live_alerts")] == ["b"]


def test_pg_versione_per_origine_mai_dall_orologio(pg) -> None:
    """Terza revisione R1 sul PostgreSQL vero: l'orologio indietro di 115 s non fa perdere
    EXECUTION_COMPLETE (updated_at tale e quale); la versione decide SOLO fra voci della
    stessa origine; fra origini diverse vince l'ultima arrivata."""
    a, p, srv, ora, eventi = pg
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:02:00+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2025-10-09T10:00:05+00:00"))
    assert a.conferma() and p.drena().consegnate == 2
    r = righe("betfair_live_orders")[0]
    assert r["status"] == "EXECUTION_COMPLETE" and r["updated_at"].startswith("2025-10-09T10:00:05")
    assert "dati.riga_vecchia" not in eventi
    base = {"p_tabella": "betfair_live_orders", "p_op": "upsert", "p_conflitto": ["mode", "client_order_ref"]}
    origine = a.origine("stato_denaro")
    vecchia = srv.rpc("postino_consegna", {**base, "p_origine": origine, "p_versioni": [1], "p_righe": [
        riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:09:00+00:00")]})
    stessa = srv.rpc("postino_consegna", {**base, "p_origine": origine, "p_versioni": [2], "p_righe": [
        riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:09:00+00:00")]})
    assert (vecchia, stessa) == ([{"esito": "vecchia"}], [{"esito": "ignorata"}])
    assert righe("betfair_live_orders")[0]["status"] == "EXECUTION_COMPLETE"
    altra = srv.rpc("postino_consegna", {**base, "p_origine": "altro/stato_denaro/x", "p_versioni": [1], "p_righe": [
        riga_ordine("r1", "CANCELLED", "2025-10-09T09:00:00+00:00")]})
    assert altra == [{"esito": "ok"}] and righe("betfair_live_orders")[0]["status"] == "CANCELLED"
    senza = srv.rpc("postino_consegna", {**base, "p_righe": [riga_ordine("r1", "LAPSED", "2025-10-09T08:00:00+00:00")]})
    assert senza == [{"esito": "ok"}] and righe("betfair_live_orders")[0]["status"] == "LAPSED"
    assert sql("SELECT count(*) FROM public.postino_versioni;") == "2"


def test_pg_ombra_e_confronto(tmp_path: Path, pg) -> None:
    a, _, srv, ora, _ = pg
    p = PostinoLocale(a, CloudProva(srv), ombra=True, orologio_ms=lambda: ora[0])
    a.scrivi("mike_activity", riga_attivita(1))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma() and p.drena().consegnate == 2
    assert righe("mike_activity") == [] and righe("betfair_live_orders") == []
    assert len(righe("mike_activity_ombra")) == 1 and len(righe("betfair_live_orders_ombra")) == 1
    sql("INSERT INTO public.mike_activity (ts, event_id, kind, payload) "
        "VALUES ('2025-10-09T10:00:00Z', '35760084', 'giro', '{}');")              # il vecchio scrittore
    da = datetime(2025, 10, 9, tzinfo=timezone.utc)
    assert confronta_ombra(p.cloud, "mike_activity", ["kind", "event_id"], "ts", da) == []
    sql("INSERT INTO public.mike_activity (ts, event_id, kind, payload) "
        "VALUES ('2025-10-09T11:00:00Z', '35760084', 'giro', '{}');")
    assert confronta_ombra(p.cloud, "mike_activity", ["kind", "event_id"], "ts", da) == [
        {"giorno": "2025-10-09", "gruppo": ["giro", "35760084"], "vera": 2, "ombra": 1}]


def test_pg_riconcilia(pg) -> None:
    a, p, srv, ora, _ = pg
    for i in range(3):
        a.scrivi("mike_activity", riga_attivita(i))
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:00+00:00"))
    assert a.conferma() and p.drena().consegnate == 4
    da = datetime(2025, 10, 9, tzinfo=timezone.utc)
    r = p.riconcilia("mike_activity", da)
    assert (r.righe_locali, r.righe_cloud, r.mancanti_nel_cloud, r.in_piu_nel_cloud, r.diverse) == (3, 3, (), (), ())
    r2 = p.riconcilia("betfair_live_orders", da)
    assert r2.diverse == () and r2.mancanti_nel_cloud == ()                  # timestamptz del cloud == ISO locale
    sql("DELETE FROM public.mike_activity WHERE id = 2;")
    sql("UPDATE public.betfair_live_orders SET updated_at = '2025-10-09T09:00:00Z';")
    assert len(p.riconcilia("mike_activity", da).mancanti_nel_cloud) == 1
    assert p.riconcilia("betfair_live_orders", da).diverse == ('["paper", "r1"]',)



# ---------------------------------------------------------------- correzioni dopo la revisione (09/10)
def test_pg_R12_patch_con_versione_piu_vecchia_della_stessa_origine_non_tocca_il_cloud(pg) -> None:
    a, p, srv, ora, _ = pg
    a.accoda("betfair_live_orders", "upsert", None, riga_ordine("r1", "EXECUTION_COMPLETE", "2025-10-09T10:00:09+00:00"))
    assert p.drena().consegnate == 1
    base = {"p_tabella": "betfair_live_orders", "p_op": "patch", "p_conflitto": ["mode", "client_order_ref"],
            "p_origine": a.origine("stato_denaro")}
    vecchia = srv.rpc("postino_consegna", {**base, "p_versioni": [0], "p_righe": [
        {"mode": "paper", "client_order_ref": "r1", "status": "EXECUTABLE", "updated_at": "2025-10-09T10:00:01+00:00"}]})
    assert vecchia == [{"esito": "vecchia"}]
    assert righe("betfair_live_orders")[0]["status"] == "EXECUTION_COMPLETE"
    nuova = srv.rpc("postino_consegna", {**base, "p_versioni": [10], "p_righe": [
        {"mode": "paper", "client_order_ref": "r1", "status": "CANCELLED", "updated_at": "2025-10-09T10:00:01+00:00"}]})
    assert nuova == [{"esito": "ok"}] and righe("betfair_live_orders")[0]["status"] == "CANCELLED"
    # una riga rifiutata (CHECK) non lascia la sua versione: il ritento corretto passa
    rifiutata = srv.rpc("postino_consegna", {**base, "p_versioni": [11], "p_righe": [
        {"mode": "paper", "client_order_ref": "r1", "side": "BACK"}]})
    assert rifiutata[0]["esito"] == "errore" and rifiutata[0]["codice"] == "23514"
    assert srv.rpc("postino_consegna", {**base, "p_versioni": [11], "p_righe": [
        {"mode": "paper", "client_order_ref": "r1", "side": "lay"}]}) == [{"esito": "ok"}]


def test_pg_R2a_dl_stale_il_rientro_non_riporta_indietro_il_cloud(tmp_path: Path, pg) -> None:
    """dl_stale.py del revisore sul PostgreSQL vero (live_alerts come stato senza versione)."""
    from Betfair.nucleo.dati.contratto import SpecTabella
    _, _, srv, ora, _ = pg
    spec = dict(SPEC)
    spec["live_alerts"] = SpecTabella("live_alerts", ("uid",), "CMD", "stato_vivo", 5.0, False, None, ("live_follow",))
    a = ArchivioLocale("dl", spec, base=tmp_path / "dl", orologio_ms=lambda: ora[0]).apri()
    try:
        p = PostinoLocale(a, CloudProva(srv), orologio_ms=lambda: ora[0], eventi=lambda n, d: None,
                          tetto_tentativi_riga=3)
        uid = "00000000-0000-0000-0000-000000000001"
        a.scrivi("live_alerts", {"uid": uid, "level": "INFO", "code": "c", "message": "VECCHIO", "event_id": "padre"})
        assert a.conferma()
        for _ in range(4):
            p.drena()
            ora[0] += 61_000
        assert [d["motivo"] for d in a.dead_letter()] == ["transitorio"]
        a.scrivi("live_alerts", {"uid": uid, "level": "INFO", "code": "c", "message": "NUOVO", "event_id": None})
        assert a.conferma() and p.drena().consegnate == 1
        sql("INSERT INTO public.live_follow (event_id, home_name, away_name, open_date) VALUES ('padre', 'A', 'B', now());")
        ora[0] += 16 * 60_000
        a._esegui_sincrono("stato_vivo", lambda c: c.execute("DELETE FROM righe"))   # anche senza la difesa locale
        for _ in range(3):
            p.drena()
            ora[0] += 1000
        assert [(x["message"], x["event_id"]) for x in righe("live_alerts")] == [("NUOVO", None)]
        assert p.contatori["vecchie"] == 1 and p.stato().in_coda == 0
    finally:
        a.chiudi()


def test_pg_A1_carattere_nullo_rifiutato_dal_jsonb_bisezione(pg) -> None:
    a, p, srv, ora, _ = pg
    for i in range(8):
        a.scrivi("mike_activity", riga_attivita(i, kind="a\x00b" if i == 5 else "giro"))
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.dead_letter) == (7, 1)
    assert sorted(r["payload"]["i"] for r in righe("mike_activity")) == [0, 1, 2, 3, 4, 6, 7]
    assert a.dead_letter()[0]["codice"] == "22P05"


def test_pg_A1_nan_mai_inviato_le_altre_passano(pg) -> None:
    a, p, srv, ora, _ = pg
    a.scrivi("mike_activity", riga_attivita(0, payload={"x": float("nan")}))
    a.scrivi("mike_activity", riga_attivita(1))
    assert a.conferma()
    e = p.drena()
    assert (e.consegnate, e.dead_letter) == (1, 1) and a.dead_letter()[0]["codice"] == "valore_non_json"


def test_pg_A4_colonna_sconosciuta_blocca_la_tabella_niente_dead_letter(pg) -> None:
    a, p, srv, ora, eventi = pg
    for i in range(5):
        a.scrivi("mike_activity", riga_attivita(i, colonna_nuova=1))
    assert a.conferma()
    e = p.drena()
    assert e.dead_letter == 0 and p.stato().in_coda == 5 and eventi.count("dati.postino_bloccato") == 1


def test_pg_intestazione_ha_il_suo_sqlstate(pg) -> None:
    from Betfair.nucleo.dati.postino import classe_riga
    from Betfair.nucleo.dati.tests.test_g1_finti import ErrorePg
    a, p, srv, ora, _ = pg
    with pytest.raises(ErrorePg) as e:
        srv.rpc("postino_consegna", {"p_tabella": "mike_activity", "p_op": "fondi", "p_conflitto": ["uid"],
                                     "p_righe": []})
    assert e.value.codice == "GP001" and classe_riga("GP001") == "schema"
    with pytest.raises(ErrorePg) as e2:
        srv.rpc("postino_consegna", {"p_tabella": "mike_activity", "p_op": "upsert", "p_conflitto": ["uid"],
                                     "p_righe": [{"uid": "00000000-0000-0000-0000-000000000009"}],
                                     "p_origine": "o", "p_versioni": [1, 2]})
    assert e2.value.codice == "GP001"



def test_pg_R11_riga_senza_chiave_naturale_rifiutata(pg) -> None:
    a, p, srv, ora, _ = pg
    esiti = srv.rpc("postino_consegna", {"p_tabella": "mike_activity", "p_op": "insert", "p_conflitto": ["uid"],
                                         "p_righe": [{"kind": "senza_uid", "payload": {}}]})
    assert esiti[0]["esito"] == "errore" and esiti[0]["codice"] == "22023"
    assert righe("mike_activity") == []


# ---------------------------------------------------------------- quarta revisione (09/10): riserva D, nota b
def test_pg_D_perdita_di_corrente_sul_vivo_la_scrittura_nuova_arriva(tmp_path: Path, pg) -> None:
    """origine_2d.py del revisore sul PostgreSQL vero: dopo il blackout la vseq si riusa, ma con
    un'origine NUOVA (una per apertura): la scrittura CLOSED arriva, come oggi."""
    import shutil
    _, _, srv, ora, _ = pg
    base = tmp_path / "d"

    def apri() -> Any:
        a = ArchivioLocale("x", SPEC, base=base, orologio_ms=lambda: ora[0]).apri()
        return a, PostinoLocale(a, CloudProva(srv), orologio_ms=lambda: ora[0], eventi=lambda n, d: None)

    def segui(stato: str, i: int) -> Dict[str, Any]:
        return {"event_id": "E1", "home_name": "A", "away_name": "B", "open_date": "2026-10-09T12:00:00+00:00",
                "status": stato, "updated_at": f"2026-10-09T10:00:0{i}+00:00"}

    a, _ = apri()
    a.chiudi()
    shutil.copytree(a.cartella, tmp_path / "durevole")
    a, p = apri()
    for i in range(3):
        a.scrivi("live_follow", segui("STREAMING", i))
    assert a.conferma() and p.drena().consegnate == 1                      # live_follow coalesce: una voce, vseq 3
    assert sql("SELECT max(versione) FROM public.postino_versioni WHERE tabella = 'live_follow';") == "3"
    a.chiudi()
    shutil.rmtree(a.cartella)
    shutil.copytree(tmp_path / "durevole", a.cartella)            # il SO ha perso la coda del WAL
    a, p = apri()
    try:
        a.scrivi("live_follow", segui("CLOSED", 5))
        assert a.conferma() and p.drena().consegnate == 1
        assert sql("SELECT status FROM public.live_follow WHERE event_id = 'E1';") == "CLOSED"
        assert p.contatori["vecchie"] == 0
    finally:
        a.chiudi()


def test_pg_b_due_postini_lotti_in_ordine_opposto_niente_deadlock(pg) -> None:
    """Nota b: le due sessioni psql del revisore (conc_a.sql / conc_b.sql): 300 chiamate da 10
    righe, chiavi k0..k9 in una sessione e k9..k0 nell'altra, in parallelo. Prima della
    correzione ~1.000 esiti 40P01 per sessione su 3.000; ora la RPC scrive in ordine di chiave."""
    import subprocess
    assert ARGS is not None

    def copione(nome: str, chiavi: List[str], origine: str) -> str:
        # deadlock_timeout corto: un deadlock costa 20 ms invece di 1 s (la mutazione S09 resta veloce)
        righe_sql = ["SET deadlock_timeout = '20ms';", "SET ROLE service_role;", "CREATE TEMP TABLE esiti(c text);"]
        for giro in range(1, 301):
            lotto = [{"mode": "paper", "client_order_ref": k, "market_id": "1.2", "selection_id": 1, "side": "back",
                      "status": f"{nome}{giro}"} for k in chiavi]
            righe_sql.append(
                "INSERT INTO esiti SELECT coalesce(e->>'codice', e->>'esito') FROM jsonb_array_elements("
                "public.postino_consegna('betfair_live_orders', 'upsert', ARRAY['mode','client_order_ref'], "
                f"$j${json.dumps(lotto)}$j$::jsonb, '{origine}', '{json.dumps([giro] * len(chiavi))}'::jsonb)) e;")
        righe_sql.append("SELECT c || '|' || count(*) FROM esiti GROUP BY c ORDER BY 1;")
        return "\n".join(righe_sql) + "\n"

    chiavi = [f"k{i}" for i in range(10)]
    sessioni = [subprocess.Popen(["psql", *ARGS, "-X", "-q", "-A", "-t"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    copioni = [copione("A", chiavi, "A/x/1"), copione("B", chiavi[::-1], "B/x/1")]
    fili = []
    uscite: List[Any] = [None, None]
    import threading

    for i, (s, c) in enumerate(zip(sessioni, copioni)):
        def parla(i: int = i, s: Any = s, c: str = c) -> None:
            uscite[i] = s.communicate(c, timeout=600)
        fili.append(threading.Thread(target=parla))
    for f in fili:
        f.start()
    for f in fili:
        f.join(620)
    conteggi = []
    for (out, err), s in zip(uscite, sessioni):
        assert s.returncode == 0, err[-500:]
        conteggi.append(dict(x.split("|") for x in out.split() if "|" in x))
    assert conteggi == [{"ok": "3000"}, {"ok": "3000"}], conteggi
