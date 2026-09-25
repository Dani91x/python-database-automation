"""Catchup P4 - stagioni MAI CARICATE (25/09/2026).

Ordine dell'utente: "Il backfill deve occuparsi di tenere PERFETTO il DB: ad esempio ad
oggi ci sono ancora il 40 % di crediti API da utilizzare, potrebbe popolare qualche lega".
Le (lega, stagione) con 0 partite in `matches` entrano nel recupero automatico con la
priorita' piu' bassa (P4): solo dopo P1-P3, solo con il margine sopra il pavimento
CATCHUP_P4_MARGINE_MINIMO, a spezzoni ripartibili, mai oltre la quota.

Stessi finti di test_backfill_automatico_2026_09_25.py (client supabase-py e API-Football
con chiavi e strutture reali); in piu' /fixtures di una stagione passata (date vecchie:
quote fuori dalla finestra API di 7 giorni) e righe di api_call_log con le colonne vere
(id, endpoint, created_at).
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api_quota  # noqa: E402
import league_orchestrator as lo  # noqa: E402
import season_backfill as sbk  # noqa: E402
import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402
from test_backfill_automatico_2026_09_25 import (  # noqa: E402,F401  (mondo e' una fixture)
    OGGI, FintoClient, FintoDB, FintoServer, coverage, fixture_api, mondo, quota_per,
)

P4_LEGA, P4_ANNO = 777, 2023
ENDPOINT_PARTITA = ("/fixtures/events", "/fixtures/lineups", "/fixtures/players", "/fixtures/statistics", "/odds")


def coverage_passata(lid: int, sy: int, **kw: Any) -> Dict[str, Any]:
    return coverage(lid, sy, current=kw.pop("current", False), fine=kw.pop("fine", f"{sy + 1}-05-30"),
                    inizio=kw.pop("inizio", f"{sy}-08-20"), **kw)


def fixture_vecchia(fid: int, lid: int, sy: int) -> Dict[str, Any]:
    """/fixtures con struttura reale, partita giocata a stagione passata (data vecchia)."""
    f = fixture_api(fid, lid, sy)
    f["fixture"]["date"] = f"{sy + 1}-01-10T15:00:00+00:00"
    return f


def _catchup(db: FintoDB, server: FintoServer, env: Optional[Dict[str, str]] = None, oggi: date = OGGI,
             concorrenza: Any = None):
    client = FintoClient(server)
    q = quota_per(db, server, client)
    righe: List[str] = []
    env = {"CATCHUP_LEGHE_PRIORITARIE": "135", **(env or {})}
    ris = sc.esegui_catchup(db, client, q, concorrenza, env=env, oggi=oggi, stampa=righe.append)
    return ris, righe, q


@pytest.fixture
def mondo_p4(mondo, monkeypatch):
    """P1: 135/2026 con 2 partite senza dettagli (10 chiamate). P4: 777/2023 mai caricata,
    l'API ha 3 partite (4 endpoint ciascuna: le quote sono fuori finestra)."""
    db, server = mondo
    monkeypatch.setattr(sc, "leghe_modelli_ml", lambda: set())
    db.t["api_coverage_by_season"] += [coverage(135, 2026), coverage_passata(P4_LEGA, P4_ANNO)]
    for fid in (1, 2):
        db.partita(fid, 135, 2026)
    server.fixtures_stagione[(P4_LEGA, P4_ANNO)] = [fixture_vecchia(f, P4_LEGA, P4_ANNO) for f in (901, 902, 903)]
    return db, server


def _chiamate_p4(server: FintoServer) -> List[Any]:
    return [(e, p) for e, p in server.chiamate
            if (e == "/fixtures" and p.get("league") == P4_LEGA) or p.get("fixture") in range(900, 1000)]


# ===========================================================================
# 1. P4 dopo P1-P3, sopra il pavimento, per intero
# ===========================================================================
def test_p4_parte_dopo_p1_p3_carica_la_stagione_e_il_db_resta_senza_buchi(mondo_p4):
    db, server = mondo_p4
    ris, righe, q = _catchup(db, server)
    fatte = [(e, p.get("fixture") or p.get("league")) for e, p in server.chiamate]
    i_fixtures = fatte.index(("/fixtures", P4_LEGA))
    assert all(p in (1, 2) for _, p in fatte[:i_fixtures])            # prima TUTTA la P1
    assert i_fixtures == 10
    dopo = [p for e, p in fatte[i_fixtures + 1:]]
    assert sorted(set(dopo)) == [901, 902, 903] and len(dopo) == 12      # 3 partite x 4 endpoint, quote no
    assert "/odds" not in [e for e, p in server.chiamate if p.get("fixture") in (901, 902, 903)]
    assert ris.p4_caricate == [(P4_LEGA, P4_ANNO)] and ris.codice == 0
    assert sorted(m["fixture_id"] for m in db.t["matches"] if m["league_id"] == P4_LEGA) == [901, 902, 903]
    testo = "\n".join(righe)
    assert "STAGIONI MAI CARICATE" in testo
    assert "in coda P4: 1 (leghe bot 0, leghe ML 0, altre 1), ~1521 chiamate stimate" in testo
    assert "caricate oggi: 1 per intero, 0 interrotte" in testo and "restano: 0 stagioni, ~0 chiamate" in testo
    assert righe[-1] == "DB SENZA BUCHI"
    # il margine non e' mai sceso sotto il pavimento
    assert 7500 - server.current - 3000 >= 500


def test_p4_non_parte_se_p1_p3_si_sono_fermate(mondo_p4):
    db, server = mondo_p4
    server.current = 7500 - 3000 - 9                    # margine 9: la P1 (10) non entra -> stop per quota
    ris, righe, _ = _catchup(db, server)
    assert ris.fermato_per == "quota"
    assert _chiamate_p4(server) == []                    # P4: zero chiamate
    assert ris.p4_non_partita and "P1-P3 non finite" in ris.p4_non_partita
    assert any("P4 ferma: P1-P3 non finite (fermate per quota)" in r for r in righe)


def test_p4_non_parte_sotto_il_pavimento_e_il_pavimento_viene_da_env(mondo_p4):
    db, server = mondo_p4
    server.current = 7500 - 3000 - 10 - 499              # dopo la P1 (10) resta 499 < 500
    ris, righe, _ = _catchup(db, server)
    assert [p.get("fixture") for e, p in server.chiamate] == [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]
    assert _chiamate_p4(server) == [] and ris.p4_caricate == []
    assert any("P4 ferma: margine 499 sotto il pavimento 500" in r for r in righe)


def test_p4_pavimento_da_env(mondo_p4):
    db, server = mondo_p4
    server.current = 7500 - 3000 - 10 - 400 - 1521       # dopo la P1: margine 1921; col pavimento 400 = 1521
    ris, righe, _ = _catchup(db, server, env={"CATCHUP_P4_MARGINE_MINIMO": "400"})
    assert ris.p4_pavimento == 400
    assert any("margine 1921 - pavimento 400 = 1521 -> procedo" in r for r in righe)
    assert ris.p4_caricate == [(P4_LEGA, P4_ANNO)]
    assert 7500 - server.current - 3000 == 1921 - 13     # /fixtures + 3 partite x 4


def test_p4_col_pavimento_di_default_la_stessa_stagione_non_entra_per_intero(mondo_p4):
    db, server = mondo_p4
    server.current = 7500 - 3000 - 10 - 400 - 1521      # margine P4 = 1921 - 500 = 1421 < 1521
    ris, righe, _ = _catchup(db, server)
    assert _chiamate_p4(server) == [] and ris.p4_non_entrate == [(P4_LEGA, P4_ANNO)]
    assert any("-> non_entra" in r for r in righe)


def test_p4_non_parte_se_un_action_concorrente_e_in_corso(mondo, monkeypatch):
    db, server = mondo
    monkeypatch.setattr(sc, "leghe_modelli_ml", lambda: set())
    db.t["api_coverage_by_season"].append(coverage_passata(P4_LEGA, P4_ANNO))
    server.fixtures_stagione[(P4_LEGA, P4_ANNO)] = [fixture_vecchia(901, P4_LEGA, P4_ANNO)]

    class Conc:
        def in_corso(self, forza=False):
            return "action concorrente in_progress: daily_yesterday_backfill.yml"
    ris, righe, _ = _catchup(db, server, concorrenza=Conc())
    assert server.chiamate == [] and ris.p4_caricate == [] and ris.codice == 0
    assert any("P4 ferma: action concorrente in_progress: daily_yesterday_backfill.yml" in r for r in righe)


# ===========================================================================
# 2. Solo PER INTERO (decisione utente: "NON DOBBIAMO LASCIARE LEGHE A META'")
# ===========================================================================
def test_p4_solo_per_intero_se_non_entra_nessuna_chiamata(mondo_p4):
    db, server = mondo_p4
    server.fixtures_stagione[(P4_LEGA, P4_ANNO)] = [fixture_vecchia(f, P4_LEGA, P4_ANNO) for f in range(901, 921)]
    server.current = 7500 - 3000 - 10 - 500 - 60         # dopo la P1: margine P4 = 60 (costo ~1521)
    ris, righe, _ = _catchup(db, server)
    assert _chiamate_p4(server) == []                     # niente /fixtures, niente partite: nessuna meta'
    assert [m for m in db.t["matches"] if m["league_id"] == P4_LEGA] == []
    assert ris.p4_caricate == [] and ris.p4_spezzoni == [] and ris.p4_non_entrate == [(P4_LEGA, P4_ANNO)]
    assert any("P4 ferma: 1 stagioni non entrano PER INTERO nel margine di oggi" in r for r in righe)


def test_p4_salta_quella_che_non_entra_e_carica_intera_la_successiva(mondo_p4):
    db, server = mondo_p4
    db.t["api_coverage_by_season"].append(coverage_passata(P4_LEGA, 2022, fo=False, sgio=False, ss=False, qu=False))
    server.fixtures_stagione[(P4_LEGA, 2022)] = [fixture_vecchia(f, P4_LEGA, 2022) for f in (951, 952)]
    server.current = 7500 - 3000 - 10 - 500 - 500        # margine P4 = 500: 2023 (~1521) no, 2022 (~381) si'
    ris, righe, _ = _catchup(db, server)
    assert ris.p4_non_entrate == [(P4_LEGA, P4_ANNO)] and ris.p4_caricate == [(P4_LEGA, 2022)]
    assert ("/fixtures", {"league": P4_LEGA, "season": P4_ANNO}) not in server.chiamate
    assert sorted(m["fixture_id"] for m in db.t["matches"] if m["league_id"] == P4_LEGA) == [951, 952]


def test_p4_stima_superata_si_ferma_sopra_il_pavimento_e_la_p3_chiude_senza_doppioni(mondo_p4):
    """Unico caso residuo di stagione a meta': l'API ha piu' partite della stima. Il lavoro si
    ferma a fine partita sopra il pavimento; il giorno dopo la P3 (precedenza) chiude il resto."""
    db, server = mondo_p4
    db.t["api_coverage_by_season"][-1] = coverage_passata(P4_LEGA, P4_ANNO, fo=False, sgio=False, ss=False,
                                                            qu=False)          # solo eventi: stima 1 + 380
    server.fixtures_stagione[(P4_LEGA, P4_ANNO)] = [fixture_vecchia(f, P4_LEGA, P4_ANNO) for f in range(1000, 1400)]
    server.current = 7500 - 3000 - 10 - 500 - 390         # margine P4 = 390 >= 381: parte
    ris, righe, _ = _catchup(db, server)
    fatte = [p["fixture"] for e, p in server.chiamate if p.get("fixture") in range(1000, 1400)]
    assert ris.p4_spezzoni == [(P4_LEGA, P4_ANNO)] and ris.p4_caricate == []
    assert len(fatte) == 389 and len(set(fatte)) == 389   # 390 - 1 /fixtures, una chiamata per partita
    assert 7500 - server.current - 3000 == 500             # pavimento intatto, mai sotto
    assert any("P4 ferma: fermata a fine partita: quota" in r for r in righe)
    # GIORNO DOPO: la stagione ha partite -> P3; nessuna partita gia' fatta si richiama
    server.current = 1076
    n_prima = len(server.chiamate)
    ris2, righe2, _ = _catchup(db, server)
    nuove = [p["fixture"] for e, p in server.chiamate[n_prima:] if p.get("fixture") in range(1000, 1400)]
    assert sorted(nuove) == sorted(set(range(1000, 1400)) - set(fatte))
    fids = [m["fixture_id"] for m in db.t["matches"]]
    assert len(fids) == len(set(fids)) == 2 + 400          # /fixtures rifatta con upsert: nessun doppione
    assert (P4_LEGA, P4_ANNO) in ris2.fatte and ris2.p4_candidati == []
    assert righe2[-1] == "DB SENZA BUCHI"


def test_p4_stima_con_le_partite_reali_della_lega():
    righe = [coverage_passata(40, 2019), coverage_passata(40, 2020)]
    stati = {(40, 2019): _stato_mc("0"), (40, 2020): _stato_mc("552")}      # Championship: 552 partite
    cand, _ = sc.seleziona_p4(righe, stati, {}, OGGI, set(), set())
    assert [c.costo for c in cand] == [1 + 552 * 4]


# ===========================================================================
# 3. Ordine di priorita' e criteri di ingresso (funzione pura)
# ===========================================================================
def _lac(lid: int, sy: int, partite: int) -> sg.Lacune:
    return sg.Lacune(lid, sy, partite_totali=partite, ft_totali=partite)


def _stato_mc(n: Any, **extra: Any) -> Dict[str, Any]:
    return {"status": "completed", "stats_json": {"meta": {"version": "v1"}, "fixtures": {"matches_count": n},
                                                  **extra}}


def test_p4_ordine_bot_poi_ml_poi_importanza_poi_stagione_piu_recente():
    righe = [coverage_passata(500, 2019), coverage_passata(500, 2021),             # altra, importanza 3
             coverage_passata(500, 2015),
             coverage_passata(600, 2020),                                          # altra, importanza 1
             coverage_passata(39, 2012),                                           # bot
             coverage_passata(71, 2014),                                           # ML
             coverage_passata(71, 2016, ev=False),                                 # ML ma senza eventi
             coverage_passata(135, 2024)]                                          # bot, ha partite
    stati = {(500, 2019): _stato_mc("0"), (500, 2021): _stato_mc("0"), (500, 2015): _stato_mc("0"),
             (600, 2020): _stato_mc("0"), (39, 2012): _stato_mc(0), (71, 2014): _stato_mc("0"),
             (71, 2016): _stato_mc("0"), (135, 2024): _stato_mc("380")}
    cand, conti = sc.seleziona_p4(righe, stati, {}, OGGI, {39, 135}, {71})
    assert [c.chiave for c in cand] == [(39, 2012), (71, 2014), (500, 2021), (500, 2019), (500, 2015),
                                        (600, 2020)]
    assert [c.fascia for c in cand] == [0, 1, 2, 2, 2, 2]
    assert conti["senza_eventi"] == 1
    # costo: 1 /fixtures + 380 x 4 (quote fuori finestra) + aggregati con flag True (qui False)
    assert cand[0].costo == 1 + 380 * 4 == sbk.stima_costo_mai_caricata(righe[4], OGGI)


def test_p4_criteri_di_ingresso():
    viva = coverage(800, 2026)                                                     # viva: mai P4
    recente = coverage_passata(801, 2025, fine="2026-09-10")                        # finita da 15 gg
    futura = coverage_passata(802, 2027, inizio="2027-08-01", fine="2028-05-30")   # non iniziata
    zombie = coverage_passata(880, 2021, current=True, fine="2022-10-11")          # current: si fida dell'API
    ignota = coverage_passata(803, 2020)                                           # nessuno stato, non verificata
    verificata = coverage_passata(804, 2020)                                       # verificata stanotte: 0 partite
    verificata_piena = coverage_passata(805, 2020)                                 # stato vecchio 0, DB pieno
    senza_flag = coverage_passata(806, 2020, ev=False, fo=False, sgio=False, ss=False, qu=False)
    righe = [viva, recente, futura, zombie, ignota, verificata, verificata_piena, senza_flag]
    stati = {(k["league_id"], k["season_year"]): _stato_mc("0") for k in righe if k["league_id"] != 803}
    lacune = {(804, 2020): _lac(804, 2020, 0), (805, 2020): _lac(805, 2020, 12), (880, 2021): _lac(880, 2021, 0)}
    cand, _ = sc.seleziona_p4(righe, stati, lacune, OGGI, set(), set())
    assert sorted(c.chiave for c in cand) == [(804, 2020)]    # la 'current' entra solo se l'API la chiude
    zombie["current"] = False                                  # come fa verifica_current_sospette
    cand, _ = sc.seleziona_p4(righe, stati, lacune, OGGI, set(), set())
    assert sorted(c.chiave for c in cand) == [(804, 2020), (880, 2021)]


def test_p4_stagione_senza_eventi_esclusa_salvo_richiesta_esplicita(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage_passata(P4_LEGA, P4_ANNO, ev=False))
    server.fixtures_stagione[(P4_LEGA, P4_ANNO)] = [fixture_vecchia(901, P4_LEGA, P4_ANNO)]
    ris, righe, _ = _catchup(db, server)
    ris, righe, _ = _catchup(db, server)                  # 2o giro: stato noto (0 partite)
    assert server.chiamate == [] and ris.p4_candidati == [] and ris.p4_conti["senza_eventi"] == 1
    assert any("escluse: 1 senza fixtures_events (non caricabili: API senza eventi" in r for r in righe)
    ris, righe, _ = _catchup(db, server, env={"CATCHUP_P4_ANCHE_SENZA_EVENTI": "1"})
    assert ris.p4_caricate == [(P4_LEGA, P4_ANNO)]
    assert ("/fixtures", {"league": P4_LEGA, "season": P4_ANNO}) in server.chiamate


def test_p4_fixtures_senza_partite_ricordata_ritentata_dopo_7_giorni_poi_dichiarata(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage_passata(P4_LEGA, P4_ANNO))
    # l'API non ha partite per la stagione: /fixtures risponde response []
    ris, righe, _ = _catchup(db, server)
    assert server.chiamate == [("/fixtures", {"league": P4_LEGA, "season": P4_ANNO})]
    assert ris.p4_senza_partite == [(P4_LEGA, P4_ANNO)]
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == P4_LEGA)
    assert stato["stats_json"]["mai_caricata"]["tentativi"] == 1
    _catchup(db, server)                                                            # stesso giorno
    _catchup(db, server, oggi=OGGI + timedelta(days=6))                             # < 7 gg
    assert len(server.chiamate) == 1                                                # non richiamata
    _catchup(db, server, oggi=OGGI + timedelta(days=7))                             # ritentativo
    assert len(server.chiamate) == 2
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == P4_LEGA)
    assert stato["stats_json"]["mai_caricata"]["tentativi"] == 2
    ris, righe, _ = _catchup(db, server, oggi=OGGI + timedelta(days=30))
    assert len(server.chiamate) == 2 and ris.p4_conti["api_senza_partite"] == 1    # dichiarata, mai piu'
    assert any("1 API senza partite (/fixtures vuota 2 volte)" in r for r in righe)
    # la memoria sopravvive a ogni riscrittura dello stato (orchestratore a mano, verifica notturna)
    riscritto = sg.costruisci_stats_json(coverage_passata(P4_LEGA, P4_ANNO), sg.Lacune(P4_LEGA, P4_ANNO),
                                         stato, "orchestratore", None, OGGI)
    assert riscritto["mai_caricata"] == stato["stats_json"]["mai_caricata"]


def test_p4_stagione_mai_caricata_non_e_un_buco_p3_aggregati_solo_dopo_le_partite(mondo, monkeypatch):
    db, server = mondo
    monkeypatch.setattr(sc, "leghe_modelli_ml", lambda: set())
    db.t["api_coverage_by_season"].append(coverage_passata(P4_LEGA, P4_ANNO, aggregati=True))
    server.fixtures_stagione[(P4_LEGA, P4_ANNO)] = [fixture_vecchia(901, P4_LEGA, P4_ANNO)]
    ris, righe, _ = _catchup(db, server)
    endpoint = [e for e, p in server.chiamate]
    assert endpoint[0] == "/fixtures"                      # nessun aggregato prima delle partite (P3)
    # costo stimato: 1 /fixtures + 380 x 4 + aggregati 1+1+1+1+2 (top_cards = 2 chiamate)
    assert endpoint.count("/standings") == 1 and endpoint.count("/players/topredcards") == 1
    assert ris.fatte == [] and ris.p4_caricate == [(P4_LEGA, P4_ANNO)]
    assert "in coda P4: 1 (leghe bot 0, leghe ML 0, altre 1), ~1527 chiamate stimate" in "\n".join(righe)
    assert not any(r.lstrip().startswith(f"{P4_LEGA} ") for r in righe)   # non e' una riga del REFERTO BUCHI


def test_p4_stato_vecchio_a_zero_ma_partite_in_db_zero_chiamate_e_passa_alla_p3(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage_passata(P4_LEGA, P4_ANNO))
    db.t["season_backfill_state"].append({"id": 9, "league_id": P4_LEGA, "season_year": P4_ANNO,
                                          "status": "completed",
                                          "stats_json": {"meta": {"version": "v1"},
                                                         "fixtures": {"matches_count": 0}}})
    db.partita(950, P4_LEGA, P4_ANNO, giorni_fa=600)       # in DB c'e' (es. scritta dal Daily)
    ris, righe, _ = _catchup(db, server)
    assert server.chiamate == [] and ris.p4_caricate == []
    assert any("partite gia' in DB (1), stato aggiornato, passa alla P3" in r for r in righe)
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == P4_LEGA)
    assert stato["stats_json"]["fixtures"]["matches_count"] == 1 and stato["stats_json"]["meta"]["version"] == "v2"


# ===========================================================================
# 4. Referto: stima dei giorni con il margine medio degli ultimi 7 giorni
# ===========================================================================
def _log_giorni(db: FintoDB, per_giorno: List[int], adesso: datetime) -> None:
    """api_call_log con le colonne vere (id, endpoint, created_at): per_giorno[0] = 7 gg fa."""
    i = 0
    oggi0 = adesso.replace(hour=0, minute=0, second=0, microsecond=0)
    for g, n in enumerate(per_giorno):
        giorno = oggi0 - timedelta(days=len(per_giorno) - g)
        for j in range(n):
            i += 1
            db.t["api_call_log"].append({"id": i, "endpoint": "/fixtures/events",
                                         "created_at": (giorno + timedelta(seconds=j)).isoformat()})


def test_consumo_giorni_log_e_margine_medio():
    db = FintoDB()
    adesso = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    _log_giorni(db, [100, 200, 300, 400, 500, 600, 700], adesso)
    db.t["api_call_log"].append({"id": 99999, "endpoint": "/odds", "created_at": adesso.isoformat()})  # oggi: fuori
    giorni = api_quota.consumo_giorni_log(db, 7, adesso)
    assert giorni == [("2026-09-18", 100), ("2026-09-19", 200), ("2026-09-20", 300), ("2026-09-21", 400),
                      ("2026-09-22", 500), ("2026-09-23", 600), ("2026-09-24", 700)]
    # margine avanzato = max(0, 7500 - 3000 - n): media di 4400..3800 = 4100
    assert api_quota.margine_medio_log(db, 7500, 3000, 7, adesso) == 4100


def test_referto_p4_quante_restano_e_stima_giorni(mondo, monkeypatch):
    db, server = mondo
    monkeypatch.setattr(sc, "leghe_modelli_ml", lambda: {778})
    db.t["api_coverage_by_season"] += [coverage_passata(P4_LEGA, 2023), coverage_passata(778, 2022),
                                       coverage_passata(779, 2021, ev=False)]
    server.fixtures_stagione[(778, 2022)] = [fixture_vecchia(f, 778, 2022) for f in (931, 932)]
    _log_giorni(db, [3500] * 7, datetime.now(timezone.utc))     # margine avanzato 1000/giorno
    server.current = 7500 - 3000 - 500 - 1521                     # margine P4 = 1521: solo la prima (ML)
    ris, righe, _ = _catchup(db, server)
    assert ris.p4_caricate == [(778, 2022)]
    testo = "\n".join(righe)
    assert "in coda P4: 2 (leghe bot 0, leghe ML 1, altre 1), ~3042 chiamate stimate" in testo
    assert "caricate oggi: 1 per intero, 0 interrotte" in testo
    assert "restano: 1 stagioni, ~1521 chiamate" in testo
    assert "escluse: 1 senza fixtures_events" in testo
    # (1000 - pavimento 500) = 500/giorno -> ceil(1521 / 500) = 4 giorni
    assert ("stima giorni al completamento: ~4 giorni (margine medio ultimi 7 gg da api_call_log 1000 - "
            "pavimento 500 = 500 chiamate/giorno per la P4)") in testo
    assert f"prossime: lega {P4_LEGA} stagione 2023 ~1521" in testo
    assert righe[-1] == "DB SENZA BUCHI"                        # le mai caricate non sono "buchi"


def test_referto_p4_log_illeggibile_stima_non_disponibile_senza_errore(mondo_p4):
    db, server = mondo_p4
    server.current = 7500 - 3000 - 10 - 499
    db.errori_tabella["api_call_log"] = {"select": "{'code': '57014'}"}
    ris, righe, _ = _catchup(db, server)
    assert ris.codice == 0
    assert any(r.startswith("  stima giorni al completamento: non disponibile") for r in righe)


def test_quota_con_pavimento():
    db, server = FintoDB(), FintoServer(current=1000)
    q = quota_per(db, server, FintoClient(server))
    q4 = api_quota.QuotaConPavimento(q, 500)
    q.aggiorna()
    assert q.margine() == 3500 and q4.margine() == 3000
    assert q4.copre(3000) and not q4.copre(3001)
    q4.aggiungi_chiamate_esterne(10)
    assert q.margine() == 3490 and q4.margine() == 2990
    assert q4.capacita_giornaliera() == 4000


# ===========================================================================
# 5. Dry-run dell'orchestratore
# ===========================================================================
def test_dry_run_mostra_mai_caricata_con_il_costo(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"] += [coverage_passata(P4_LEGA, 2023), coverage_passata(P4_LEGA, 2022, ev=False)]
    out = io.StringIO()
    with redirect_stdout(out):
        lo.backfill_full_league(P4_LEGA, dry_run=True, sb=db, quota=quota_per(db, server, None), oggi=OGGI)
    testo = out.getvalue()
    assert server.chiamate == []
    riga23 = next(r for r in testo.splitlines() if r.startswith("2023"))
    riga22 = next(r for r in testo.splitlines() if r.startswith("2022"))
    assert "MAI CARICATA ~1521 chiamate (recupero automatico: coda P4): procederei" in riga23
    assert "MAI CARICATA ~1141 chiamate (fuori dal recupero automatico: API senza eventi" in riga22


# ===========================================================================
# 6. Stagioni 'current' con fine passata: verifica mirata all'API (decisione utente)
# ===========================================================================
def _leghe_api(server: FintoServer, monkeypatch, correnti: Dict[Any, Any]) -> None:
    """/leagues?id=&season= con la struttura reale; correnti[(lega, anno)] = True/False/'errore'."""
    vero = server.rispondi

    def rispondi(endpoint: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if endpoint != "/leagues":
            return vero(endpoint, params)
        server.current += 1
        server.chiamate.append((endpoint, dict(params or {})))
        k = (params["id"], params["season"])
        if correnti.get(k) == "errore":
            return {"get": "leagues", "parameters": params, "errors": {"requests": "limit"}, "results": 0,
                    "paging": {"current": 1, "total": 1}, "response": []}
        stag = {"year": k[1], "start": f"{k[1]}-09-16", "end": "2022-10-11", "current": bool(correnti.get(k)),
                "coverage": {"fixtures": {"events": True, "lineups": True, "statistics_fixtures": True,
                                          "statistics_players": True}, "odds": True}}
        return {"get": "leagues", "parameters": params, "errors": [], "results": 1,
                "paging": {"current": 1, "total": 1},
                "response": [{"league": {"id": k[0], "name": f"Lega {k[0]}", "type": "League", "logo": ""},
                              "country": {"name": "World", "code": None, "flag": None}, "seasons": [stag]}]}
    monkeypatch.setattr(server, "rispondi", rispondi)


def _zombie(db: FintoDB, lid: int = 880, sy: int = 2021) -> None:
    db.t["api_coverage_by_season"].append(coverage_passata(lid, sy, current=True, fine="2022-10-11"))
    db.t["season_backfill_state"].append({"id": db.nuovo_id(), "league_id": lid, "season_year": sy,
                                          "status": "completed",
                                          "stats_json": {"meta": {"version": "v1"},
                                                         "fixtures": {"matches_count": 0}}})


def test_current_sospetta_verificata_e_trattata_come_dice_l_api(mondo, monkeypatch):
    db, server = mondo
    monkeypatch.setattr(sc, "leghe_modelli_ml", lambda: set())
    _zombie(db)
    _leghe_api(server, monkeypatch, {(880, 2021): False})
    server.fixtures_stagione[(880, 2021)] = [fixture_vecchia(f, 880, 2021) for f in (961, 962)]
    ris, righe, _ = _catchup(db, server)
    assert server.chiamate[0] == ("/leagues", {"id": 880, "season": 2021})
    assert ris.verifiche_current["chiamate"] == 1 and ris.verifiche_current["chiuse"] == 1
    assert any("API current=False -> trattata come passata" in r for r in righe)
    assert ris.p4_caricate == [(880, 2021)]                      # chiusa dall'API: P4 per intero
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == 880)
    assert stato["stats_json"]["verifica_current"] == {"at": OGGI.isoformat(), "current": False}
    n = len([c for c in server.chiamate if c[0] == "/leagues"])
    _catchup(db, server, oggi=OGGI + timedelta(days=3))          # stessa settimana: nessuna richiamata
    assert len([c for c in server.chiamate if c[0] == "/leagues"]) == n


def test_current_confermata_dall_api_resta_viva_e_si_riverifica_dopo_7_giorni(mondo, monkeypatch):
    db, server = mondo
    _zombie(db)
    _leghe_api(server, monkeypatch, {(880, 2021): True})
    ris, righe, _ = _catchup(db, server)
    assert [c for c in server.chiamate if c[0] != "/leagues"] == []      # viva, 0 FT: niente P4
    assert ris.verifiche_current["confermate_current"] == 1 and ris.p4_candidati == []
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == 880)
    assert stato["stats_json"]["verifica_current"] == {"at": OGGI.isoformat(), "current": True}
    assert stato["stats_json"]["fixtures"] == {"matches_count": 0}     # il resto dello stato intatto
    _catchup(db, server, oggi=OGGI + timedelta(days=6))
    assert len(server.chiamate) == 1
    _catchup(db, server, oggi=OGGI + timedelta(days=7))
    assert len(server.chiamate) == 2                                       # una volta a settimana


def test_verifica_current_nel_budget_e_col_tetto(mondo, monkeypatch):
    db, server = mondo
    _zombie(db, 880, 2021)
    _zombie(db, 888, 2022)
    _leghe_api(server, monkeypatch, {(880, 2021): True, (888, 2022): True})
    ris, _, _ = _catchup(db, server, env={"CATCHUP_MAX_VERIFICHE_CURRENT": "1"})
    assert len(server.chiamate) == 1 and ris.verifiche_current["rinviate"] == 1
    server.current = 7500 - 3000                                           # margine 0: nessuna verifica
    ris, _, _ = _catchup(db, server, oggi=OGGI + timedelta(days=1))
    assert len(server.chiamate) == 1 and ris.verifiche_current["rinviate"] == 1   # l'altra ha la nota


def test_verifica_current_errore_api_resta_come_nel_db(mondo, monkeypatch):
    db, server = mondo
    _zombie(db)
    _leghe_api(server, monkeypatch, {(880, 2021): "errore"})
    ris, righe, _ = _catchup(db, server)
    assert ris.p4_candidati == [] and ris.verifiche_current["chiamate"] == 1
    stato = next(r for r in db.t["season_backfill_state"] if r["league_id"] == 880)
    assert "verifica_current" not in stato["stats_json"]
    assert any("API senza risposta valida, resta come nel DB" in r for r in righe)
