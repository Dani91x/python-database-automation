"""08/10/2026 sera - 57014 su season_detail_gaps DENTRO il ciclo per lega-stagione.

Run rossa reale 37743110569 (rilancio delle 15:07 UTC, log in
AUDIT_2026-10-08/action_catchup/REFERTO.md, sezione 2.x):
  - 14:30:00 UTC  POST /rest/v1/rpc/season_detail_gaps -> HTTP/2 500 (unico 500 della run);
    4 s dopo la stessa RPC risponde 200;
  - referto: "ERRORE: lega 667 stagione 2026: APIError: {'message': 'canceling statement due
    to statement timeout', 'code': '57014', ...}" -> exit 1. Nessuna riga "[CATCHUP] P.. lega
    667 stagione 2026: costo ...": l'eccezione e' nata in season_backfill.pianifica.

Finti:
  - livello RPC: client supabase/postgrest/httpx VERO con trasporto finto (fixture `server` di
    test_catchup_rete_2026_10_08): la APIError nasce dal codice vero di postgrest sul corpo
    JSON vero del 57014 (HTTP 500);
  - catena intera (esegui_catchup): il mondo finto di test_backfill_automatico_2026_09_25
    (FintoDB con il modello Python di season_detail_gaps, stessa forma di righe
    {tabella, stato, n, fixture_ids}); l'errore e' APIError(dict(corpo)), la stessa
    costruzione di postgrest (_sync/request_builder.py: `raise APIError(dict(json_obj))`).
"""
from __future__ import annotations

import os
import sys
import time as _time_vero
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")
os.environ.setdefault("API_FOOTBALL_KEY", "x")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from postgrest.exceptions import APIError  # noqa: E402

import db_client  # noqa: E402
import season_backfill as sbk  # noqa: E402
import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402
import test_backfill_automatico_2026_09_25 as tba  # noqa: E402
from test_backfill_automatico_2026_09_25 import mondo  # noqa: E402,F401  (fixture)
from test_catchup_p4_2026_09_25 import P4_ANNO, P4_LEGA, mondo_p4  # noqa: E402,F401  (fixture)
from test_catchup_rete_2026_10_08 import CORPO_42501, CORPO_57014, json_errore, server  # noqa: E402,F401

# corpo VERO di PostgREST per una funzione assente con firma diversa (42883)
CORPO_42883 = {"code": "42883", "details": None,
               "hint": "No function matches the given name and argument types. You might need to add "
                       "explicit type casts.",
               "message": "function public.season_detail_gaps(integer, integer, integer[]) does not exist"}
# errore applicativo 500 che NON e' un 57014 (internal error di Postgres)
CORPO_XX000 = {"code": "XX000", "details": None, "hint": None, "message": "cache lookup failed for relation 1"}

LEGA = (667, 2026)                     # la lega-stagione della run 37743110569


@pytest.fixture(autouse=True)
def pulito(monkeypatch):
    """Attese di season_gaps registrate (nessuna attesa vera), statistiche 57014 e stato di
    rete di db_client puliti prima e dopo ogni test."""
    sonni: List[float] = []
    monkeypatch.setattr(sg, "time", SimpleNamespace(sleep=sonni.append, time=_time_vero.time))
    monkeypatch.setattr(db_client._time, "sleep", lambda s: None)
    sg.STATISTICHE_57014.update({"ritentativi": 0, "riusciti_dopo_ritentativo": 0, "persistenti": 0})
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0})
    db_client.STATISTICHE_RETE.update({"ritentativi": 0, "riusciti_dopo_ritentativo": 0,
                                       "guasti_persistenti": 0, "rinnovi_client": 0})
    db_client.STATISTICHE_RETE["per_classe"].clear()
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    yield sonni
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0})
    db_client._TLS.client = None


# ---------------------------------------------------------------------------
# 1. lacune_stagione con il client VERO (APIError costruita da postgrest)
# ---------------------------------------------------------------------------
def _rpc_detail(srv: Any) -> int:
    return len([r for r in srv.richieste if r[2] == "/rpc/season_detail_gaps"])


def test_a_un_57014_poi_200_un_ritentativo_nessun_errore(server, pulito):
    """Il caso vero: 500 + 57014, la chiamata dopo risponde 200."""
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(500, CORPO_57014)]
    lac = sg.lacune_stagione(db_client.ClientResiliente(), *LEGA)
    assert lac.ft_totali == 3 and lac.da_chiamare_per_fixture({"events": True}) == {11: ["events"]}
    assert _rpc_detail(server) == 2
    assert pulito == [5.0]
    assert sg.STATISTICHE_57014 == {"ritentativi": 1, "riusciti_dopo_ritentativo": 1, "persistenti": 0}
    assert db_client.STATISTICHE_RETE["ritentativi"] == 0       # non e' un guasto di rete: niente doppi giri


def test_b_tre_57014_eccezione_dedicata_con_la_causa_vera(server, pulito):
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(500, CORPO_57014)] * 3
    with pytest.raises(sg.Timeout57014Persistente) as info:
        sg.lacune_stagione(db_client.ClientResiliente(), *LEGA)
    e = info.value
    assert (e.league_id, e.season_year, e.tentativi) == (667, 2026, 3)
    assert isinstance(e.__cause__, APIError) and e.__cause__.code == "57014"
    assert e.__cause__.message == "canceling statement due to statement timeout"
    assert sg._e_statement_timeout(e)                            # riconoscibile come 57014
    assert _rpc_detail(server) == 3 and pulito == [5.0, 10.0]
    assert sg.STATISTICHE_57014["persistenti"] == 1


def test_d_errori_applicativi_mai_ritentati(server, pulito):
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(404, CORPO_42883)]
    with pytest.raises(sg.MigrazioneMancante):
        sg.lacune_stagione(db_client.ClientResiliente(), *LEGA)
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(500, CORPO_XX000)]
    with pytest.raises(APIError) as info:
        sg.lacune_stagione(db_client.ClientResiliente(), *LEGA)
    assert info.value.code == "XX000"
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(403, CORPO_42501)]
    with pytest.raises(APIError, match="42501"):
        sg.lacune_stagione(db_client.ClientResiliente(), *LEGA)
    assert _rpc_detail(server) == 3                              # 1 + 1 + 1: nessun ritentativo
    assert pulito == [] and sg.STATISTICHE_57014["ritentativi"] == 0


# ---------------------------------------------------------------------------
# 2. Catena intera (esegui_catchup) sul mondo finto
# ---------------------------------------------------------------------------
def _errore(corpo: Dict[str, Any]) -> Callable[[], APIError]:
    return lambda: APIError(dict(corpo))                         # = postgrest: APIError(dict(json_obj))


def _inietta(db: Any, lega: int, fallite: Set[int], corpo: Dict[str, Any] = CORPO_57014) -> Dict[str, int]:
    """La n-esima esecuzione (1, 2, ...) di season_detail_gaps per `lega` in `fallite` solleva
    l'errore; le altre vanno al modello vero del FintoDB."""
    conta = {"n": 0}
    originale = db.rpc

    class _RpcInErrore:
        def execute(self) -> None:
            raise _errore(corpo)()

    def rpc(nome: str, params: Dict[str, Any]) -> Any:
        if nome == "season_detail_gaps" and int(params["p_league_id"]) == lega:
            conta["n"] += 1
            if conta["n"] in fallite:
                return _RpcInErrore()
        return originale(nome, params)
    db.rpc = rpc
    return conta


def _mondo_667(db: Any, prec_consecutivi: Optional[int] = None, aperto_dal: str = "2026-09-10") -> None:
    """135/2026 (P1, atlante) e 667/2026 (P2) vive, entrambe con partite FT senza dettagli.
    Con prec_consecutivi: 667 era gia' degradata per 57014 da tanti giorni, buco aperto da
    `aperto_dal` (oltre BACKFILL_BUCHI_MAX_GIORNI: senza la correzione sarebbe BUCO VECCHIO)."""
    db.t["api_coverage_by_season"] += [tba.coverage(135, 2026), tba.coverage(*LEGA)]
    for fid in (1, 2):
        db.partita(fid, 135, 2026)
    for fid in (6671, 6672):
        db.partita(fid, *LEGA)
    if prec_consecutivi is not None:
        db.t["season_backfill_state"].append(
            {"id": 66, "league_id": LEGA[0], "season_year": LEGA[1], "status": "in_progress",
             "stats_json": {"meta": {"version": "v2"}, "buco_aperto_dal": aperto_dal,
                            "degradato_57014": {"consecutivi": prec_consecutivi, "primo_at": "2026-09-20",
                                                "ultimo_at": "2026-09-24"}}})


def _catchup(db: Any, server: Any) -> Tuple[Any, List[str]]:
    client = tba.FintoClient(server)
    righe: List[str] = []
    ris = sc.esegui_catchup(db, client, tba.quota_per(db, server, client), None,
                            env={"CATCHUP_LEGHE_PRIORITARIE": "135"}, oggi=tba.OGGI, stampa=righe.append)
    return ris, righe


def _stato(db: Any, k: Tuple[int, int]) -> Dict[str, Any]:
    return [r for r in db.t["season_backfill_state"] if (r["league_id"], r["season_year"]) == k][0]


def _chiamate_fixture(server: Any, fids: Tuple[int, ...]) -> List[Any]:
    return [p.get("fixture") for e, p in server.chiamate if p.get("fixture") in fids]


def test_a_catena_run_37743110569_con_il_codice_nuovo_exit_0(mondo, pulito):
    """La run rossa: un 57014 su season_detail_gaps in pianifica di 667/2026, poi 200.
    Prima: ERRORE + exit 1. Ora: 1 ritentativo dopo 5 s, lega-stagione lavorata, exit 0."""
    db, server = mondo
    _mondo_667(db)
    conta = _inietta(db, LEGA[0], {1})
    ris, righe = _catchup(db, server)
    testo = "\n".join(righe)
    assert ris.errori == [] and ris.codice == 0
    assert "ERRORE:" not in testo
    assert any(r.startswith("[CATCHUP] P2 lega 667 stagione 2026: costo ~") for r in righe)   # la riga mancante
    assert LEGA in ris.fatte and ris.degradate_timeout == [] and ris.degradate_ciclo == {}
    assert pulito == [5.0] and conta["n"] == 4                   # pianifica 2 + esegui 1 + dopo 1
    assert sorted(set(_chiamate_fixture(server, (6671, 6672)))) == [6671, 6672]
    assert "57014 su season_detail_gaps: 1 ritentativi, 1 riusciti dopo ritentativo, 0 persistenti" in testo
    assert righe[-1] == "DB SENZA BUCHI"


def test_b_catena_57014_persistente_degradata_exit_0_contatore_e_fuori_dalla_p4(mondo, pulito, monkeypatch):
    db, server = mondo
    _mondo_667(db, prec_consecutivi=1)
    conta = _inietta(db, LEGA[0], {1, 2, 3})
    viste: List[Set[Tuple[int, int]]] = []
    vera_p4 = sc.seleziona_p4

    def spia(coperture: Any, stati: Any, lacune_note: Any, *a: Any, **k: Any) -> Any:
        viste.append(set(lacune_note))
        return vera_p4(coperture, stati, lacune_note, *a, **k)
    monkeypatch.setattr(sc, "seleziona_p4", spia)
    ris, righe = _catchup(db, server)
    testo = "\n".join(righe)
    assert ris.errori == [] and ris.codice == 0
    assert ris.degradate_timeout == [LEGA]
    assert ris.degradate_ciclo[LEGA].startswith("pianifica: 57014 persistente su rpc season_detail_gaps")
    assert ris.degradate_consecutivi[LEGA] == 2                  # 1 di ieri + oggi, NON azzerato da scrivi_stati
    st = _stato(db, LEGA)
    assert st["stats_json"]["degradato_57014"]["consecutivi"] == 2
    assert st["stats_json"]["degradato_57014"]["primo_at"] == "2026-09-20"
    assert st["stats_json"]["buco_aperto_dal"] == "2026-09-10" and st["status"] == "in_progress"
    assert conta["n"] == 3 and pulito == [5.0, 10.0]              # 3 esecuzioni, nessuna oltre
    assert _chiamate_fixture(server, (6671, 6672)) == []          # niente lavoro oggi sulla degradata
    assert LEGA in ris.rimaste and LEGA not in ris.fatte and (135, 2026) in ris.fatte
    assert viste and LEGA not in viste[0] and (135, 2026) in viste[0]   # esclusa dalla P4
    assert "DEGRADATA per 57014 nel ciclo: lega 667 stagione 2026 (pianifica: " in testo
    assert "giorni consecutivi: 2" in testo
    assert "BUCO VECCHIO" not in testo and "ERRORE:" not in testo
    assert "RINVIATO (quota/tempo/action concorrente)" not in testo   # e' una degradata, non un rinvio
    assert "DEGRADATA PERSISTENTE" not in testo


def test_c_catena_degradata_oltre_max_giorni_exit_1(mondo, pulito):
    """Regola esistente R-CATCHUP-3: non muta per sempre."""
    db, server = mondo
    _mondo_667(db, prec_consecutivi=3)                            # BACKFILL_BUCHI_MAX_GIORNI = 3
    _inietta(db, LEGA[0], {1, 2, 3})
    ris, righe = _catchup(db, server)
    testo = "\n".join(righe)
    assert ris.errori == [] and ris.degradate_consecutivi[LEGA] == 4
    assert ris.codice == 1
    assert ("DEGRADATA PERSISTENTE (> 3 giorni consecutivi, non piu' muta): lega 667 stagione 2026: degradata "
            "per 57014 da 4 giorni CONSECUTIVI (> 3)") in testo


def test_d_catena_errore_applicativo_resta_errore_senza_ritentativi(mondo, pulito):
    db, server = mondo
    _mondo_667(db)
    conta = _inietta(db, LEGA[0], {1}, CORPO_42501)
    ris, righe = _catchup(db, server)
    assert ris.codice == 1 and ris.degradate_timeout == [] and ris.degradate_ciclo == {}
    assert any(r.startswith("ERRORE: lega 667 stagione 2026: APIError") and "42501" in r for r in righe)
    assert conta["n"] == 1 and pulito == []


def test_d_catena_42883_fail_loud_migrazione_senza_ritentativi(mondo, pulito):
    db, server = mondo
    _mondo_667(db)
    conta = _inietta(db, LEGA[0], {1}, CORPO_42883)
    with pytest.raises(sg.MigrazioneMancante):
        _catchup(db, server)
    assert conta["n"] == 1 and pulito == []


# ---------------------------------------------------------------------------
# 3. Le altre vie del ciclo P1-P3: dentro esegui, dopo esegui, chiamata diretta
# ---------------------------------------------------------------------------
def test_via_esegui_lacune_prima_del_lavoro_degradata(mondo, pulito):
    """season_backfill.esegui: lacune_stagione dopo /fixtures (es.errore, inghiottita).
    Buco aperto da 15 giorni e lega-stagione in `fatte`: senza la correzione del referto
    sarebbe BUCO VECCHIO "partite da chiamare NON tentate nonostante il budget" -> exit 1."""
    db, server = mondo
    _mondo_667(db, prec_consecutivi=1)
    conta = _inietta(db, LEGA[0], {2, 3, 4})                      # 1 = pianifica ok, 5 = lacune dopo ok
    ris, righe = _catchup(db, server)
    testo = "\n".join(righe)
    assert ris.errori == [] and ris.codice == 0 and conta["n"] == 5
    assert ris.degradate_ciclo[LEGA].startswith("lavoro: Timeout57014Persistente: 57014 persistente")
    assert LEGA in ris.fatte and _chiamate_fixture(server, (6671, 6672)) == []
    assert ris.degradate_consecutivi[LEGA] == 2
    assert "BUCO VECCHIO" not in testo and "DEGRADATA per 57014 nel ciclo: lega 667 stagione 2026 (lavoro: " in testo


def test_via_esegui_lacune_dopo_il_lavoro_degradata(mondo, pulito):
    """season_backfill.esegui: lacune_stagione DOPO il lavoro (fuori dal suo try: risale)."""
    db, server = mondo
    _mondo_667(db)
    conta = _inietta(db, LEGA[0], {3, 4, 5})
    ris, righe = _catchup(db, server)
    assert ris.errori == [] and ris.codice == 0 and conta["n"] == 5
    assert ris.degradate_ciclo[LEGA].startswith("lavoro: 57014 persistente")
    assert sorted(set(_chiamate_fixture(server, (6671, 6672)))) == [6671, 6672]   # lavoro fatto
    assert "BUCO VECCHIO" not in "\n".join(righe)


def test_via_chiamata_diretta_dopo_il_lavoro_degradata(mondo, pulito, monkeypatch):
    """seasons_catchup: `es.lacune_dopo or sg.lacune_stagione(...)` (chiamata diretta)."""
    db, server = mondo
    _mondo_667(db)
    vera = sbk.esegui

    def esegui_senza_lacune_dopo(*a: Any, **k: Any) -> Any:
        es = vera(*a, **k)
        es.lacune_dopo = None
        return es
    monkeypatch.setattr(sbk, "esegui", esegui_senza_lacune_dopo)
    conta = _inietta(db, LEGA[0], {4, 5, 6})                      # 1 pianifica, 2-3 esegui, 4-6 diretta
    ris, righe = _catchup(db, server)
    assert ris.errori == [] and ris.codice == 0 and conta["n"] == 6
    assert ris.degradate_ciclo[LEGA].startswith("lacune dopo il lavoro: 57014 persistente")


# ---------------------------------------------------------------------------
# 4. P4 (stagioni mai caricate): pianifica e lavoro
# ---------------------------------------------------------------------------
def test_p4_pianifica_57014_persistente_degradata_nessuna_chiamata(mondo_p4, pulito):
    db, server = mondo_p4
    conta = _inietta(db, P4_LEGA, {1, 2, 3})
    ris, righe = _catchup(db, server)
    k = (P4_LEGA, P4_ANNO)
    assert ris.errori == [] and ris.codice == 0 and conta["n"] == 3
    assert ris.degradate_ciclo[k].startswith("P4 pianifica: 57014 persistente")
    assert ris.degradate_consecutivi[k] == 1
    assert [p for e, p in server.chiamate if e == "/fixtures" and p.get("league") == P4_LEGA] == []
    assert k not in ris.p4_caricate and k not in ris.p4_spezzoni
    assert "DEGRADATA per 57014 nel ciclo: lega 777 stagione 2023 (P4 pianifica: " in "\n".join(righe)


def test_p4_lavoro_57014_persistente_degradata_non_dichiarata_caricata(mondo_p4, pulito):
    db, server = mondo_p4
    conta = _inietta(db, P4_LEGA, {2, 3, 4})                       # 1 = pianifica ok, 5 = lacune dopo ok
    ris, righe = _catchup(db, server)
    k = (P4_LEGA, P4_ANNO)
    assert ris.errori == [] and ris.codice == 0 and conta["n"] == 5
    assert ris.degradate_ciclo[k].startswith("P4 lavoro: Timeout57014Persistente: 57014 persistente")
    assert [p for e, p in server.chiamate if e == "/fixtures" and p.get("league") == P4_LEGA]   # /fixtures fatta
    assert k not in ris.p4_caricate and k not in ris.p4_spezzoni and k not in ris.p4_senza_partite
