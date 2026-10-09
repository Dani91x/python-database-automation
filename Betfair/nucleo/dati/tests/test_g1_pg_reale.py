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
           "betfair_live_orders_ombra", "betfair_live_order_requests"]


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


def test_pg_versione_mai_indietro(pg) -> None:
    a, p, srv, ora, _ = pg
    a.accoda("betfair_live_orders", "upsert", None, riga_ordine("r1", "EXECUTION_COMPLETE", "2025-10-09T10:00:09+00:00"))
    assert p.drena().consegnate == 1
    a.accoda("betfair_live_orders", "upsert", None, riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:01+00:00"))
    # l'archivio locale la ignora gia' (versione piu' vecchia): la mando io a mano al cloud
    esiti = srv.rpc("postino_consegna", {"p_tabella": "betfair_live_orders", "p_op": "upsert",
                                         "p_conflitto": ["mode", "client_order_ref"], "p_rev": "updated_at",
                                         "p_righe": [riga_ordine("r1", "EXECUTABLE", "2025-10-09T10:00:01+00:00")]})
    assert esiti == [{"esito": "ignorata"}]
    assert righe("betfair_live_orders")[0]["status"] == "EXECUTION_COMPLETE"
    a.scrivi("betfair_live_orders", riga_ordine("r1", "CANCELLED", "2025-10-09T10:00:10+00:00"))
    assert a.conferma() and p.drena().consegnate == 1
    assert righe("betfair_live_orders")[0]["status"] == "CANCELLED"


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
