"""Certificazione della LETTURA DB della calibrazione settimanale Poisson.

Contesto (21/09/2026): lo step 3 della action `weekly_poisson_calibration`
(`generate_dc_rho.py` -> `master_backtest.fetch_completed_fixtures`) falliva con
57014 ("canceling statement due to statement timeout") sull'ultima pagina
(OFFSET 77000 LIMIT 1000) circa 5 lunedi' su 8: `dc_rho_by_league.json` non
veniva rigenerato e il motore ripiegava sul rho globale con il run VERDE.

Cosa certifica questo file:
  1) la nuova lettura KEYSET restituisce lo STESSO IDENTICO insieme di righe
     della vecchia lettura a OFFSET (nessun buco, nessun duplicato);
  2) su timeout la pagina si dimezza e si riprende dallo STESSO cursore;
  3) un errore NON transitorio non viene mai ritentato;
  4) se i tentativi finiscono l'errore resta VISIBILE (eccezione propagata);
  5) `dc_rho_by_league.json` non viene mai sovrascritto con dati parziali;
  6) a parita' di dati finti il JSON prodotto da vecchio e nuovo codice e'
     identico BYTE PER BYTE;
  7) il 57014 MASCHERATO da 500 non-JSON (il codice porta lo status HTTP e il
     motivo vero sta in "details") viene riconosciuto, ritentato e dimezzato,
     mentre un 500 con causa logica NON viene ritentato;
  8) lo Step 1 dello stesso workflow (`generate_dynamic_cal.py`) ha la stessa
     meccanica: niente uscita su pagina troncata, retry sui blocchi HT, e
     nessun `dynamic_cal.json` scritto su lettura vuota.

NESSUN test tocca il database: il client e' un finto in memoria iniettato in
sys.modules, e le funzioni che SCRIVONO (upsert poisson_calibration) sono
neutralizzate esplicitamente.

I finti hanno le IDENTICHE chiavi e tipi del vero: postgrest.APIError costruito
dal dict reale {'message','code','hint','details'}, righe con le colonne reali
(fixture_id int, league_id int, fixture_date ISO string, db_json_analisi dict).
"""
from __future__ import annotations

import json
import os
import random
import sys
import types
from datetime import datetime as _datetime_reale, timezone
from typing import Any, Callable, Dict, List, Optional

import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import master_backtest  # noqa: E402


# =============================================================================
# FINTI - stessa superficie del client supabase-py 2.28 / postgrest 2.28
# =============================================================================
def errore_timeout() -> APIError:
    """L'APIError REALE vista in produzione (run 35581846524, step 3)."""
    return APIError({
        "message": "canceling statement due to statement timeout",
        "code": "57014",
        "hint": None,
        "details": None,
    })


def errore_logico() -> APIError:
    """Errore NON ritentabile: colonna inesistente (42703)."""
    return APIError({
        "message": 'column fixture_predictions.pippo does not exist',
        "code": "42703",
        "hint": None,
        "details": None,
    })


def errore_gateway() -> APIError:
    """Risposta non-JSON del gateway: postgrest mette lo status HTTP in code (int)."""
    return APIError({
        "message": "JSON could not be generated",
        "code": 503,
        "hint": "Refer to full message for details",
        "details": "b''",
    })


def errore_timeout_mascherato() -> APIError:
    """Il 57014 come arriva quando la risposta NON e' JSON.

    postgrest.generate_default_error_message mette lo status HTTP in "code" e il
    corpo vero in "details": il codice dice solo 500, il motivo ("canceling
    statement due to statement timeout") sta nel testo. E' la forma piu'
    probabile sotto carico e la vecchia classificazione per solo codice la
    lasciava passare come errore definitivo.
    """
    return APIError({
        "message": "JSON could not be generated",
        "code": 500,
        "hint": "Refer to full message for details",
        "details": "canceling statement due to statement timeout",
    })


def errore_500_logico() -> APIError:
    """500 non-JSON con causa LOGICA: non si ritenta, deve restare visibile."""
    return APIError({
        "message": "JSON could not be generated",
        "code": 500,
        "hint": "Refer to full message for details",
        "details": 'function public.calcola_roi(integer) does not exist',
    })


class RispostaFinta:
    """Ha l'unico attributo usato dal codice di produzione: .data"""

    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class QueryFinta:
    """Builder con la stessa catena usata dal codice: select/in_/not_.is_/gte/gt/order/limit/range."""

    def __init__(self, db: "DbFinto", tabella: str) -> None:
        self._db = db
        self.tabella = tabella
        self.colonne: List[str] = []
        self.filtri: List[tuple] = []
        self.ordine: Optional[str] = None
        self.limite: Optional[int] = None
        self.intervallo: Optional[tuple] = None
        self._negato = False

    def _consuma_negazione(self) -> bool:
        negato, self._negato = self._negato, False
        return negato

    def select(self, colonne: str) -> "QueryFinta":
        self.colonne = [c.strip() for c in colonne.split(",")]
        return self

    def in_(self, colonna: str, valori) -> "QueryFinta":
        self.filtri.append(("in", colonna, list(valori), self._consuma_negazione()))
        return self

    @property
    def not_(self) -> "QueryFinta":
        self._negato = True
        return self

    def is_(self, colonna: str, valore) -> "QueryFinta":
        self.filtri.append(("is", colonna, valore, self._consuma_negazione()))
        return self

    def gt(self, colonna: str, valore) -> "QueryFinta":
        self.filtri.append(("gt", colonna, valore, self._consuma_negazione()))
        return self

    def gte(self, colonna: str, valore) -> "QueryFinta":
        self.filtri.append(("gte", colonna, valore, self._consuma_negazione()))
        return self

    def order(self, colonna: str) -> "QueryFinta":
        self.ordine = colonna
        return self

    def limit(self, n: int) -> "QueryFinta":
        self.limite = n
        return self

    def range(self, da: int, a: int) -> "QueryFinta":
        self.intervallo = (da, a)
        return self

    def execute(self) -> RispostaFinta:
        return self._db.esegui(self)


class DbFinto:
    """Emula PostgREST: filtri, ordinamento, limit/range, ordine fisico senza ORDER BY."""

    def __init__(self, tabelle: Dict[str, List[Dict[str, Any]]]) -> None:
        self.tabelle = tabelle
        self.richieste: List[QueryFinta] = []
        # guasto(indice_richiesta_1based, query) -> Exception | None
        self.guasto: Optional[Callable[[int, QueryFinta], Optional[BaseException]]] = None
        self.max_rows: Optional[int] = None  # troncamento lato server (PostgREST)

    def table(self, nome: str) -> QueryFinta:
        return QueryFinta(self, nome)

    def esegui(self, q: QueryFinta) -> RispostaFinta:
        self.richieste.append(q)
        if self.guasto is not None:
            exc = self.guasto(len(self.richieste), q)
            if exc is not None:
                raise exc

        righe = list(self.tabelle.get(q.tabella, []))
        for tipo, colonna, valore, negato in q.filtri:
            if tipo == "in":
                tieni = lambda r, c=colonna, v=valore: r.get(c) in v
            elif tipo == "gt":
                tieni = lambda r, c=colonna, v=valore: r.get(c) is not None and r[c] > v
            elif tipo == "gte":
                tieni = lambda r, c=colonna, v=valore: r.get(c) is not None and r[c] >= v
            elif tipo == "is" and valore == "null":
                tieni = lambda r, c=colonna: r.get(c) is None
            else:  # pragma: no cover - filtro non usato dal codice di produzione
                raise AssertionError(f"filtro finto non gestito: {tipo}")
            if negato:
                righe = [r for r in righe if not tieni(r)]
            else:
                righe = [r for r in righe if tieni(r)]

        if q.ordine:
            righe.sort(key=lambda r: r[q.ordine])
        if q.intervallo is not None:
            da, a = q.intervallo
            righe = righe[da : a + 1]
        if q.limite is not None:
            righe = righe[: q.limite]
        if self.max_rows is not None:
            righe = righe[: self.max_rows]

        if q.colonne:
            righe = [{c: r.get(c) for c in q.colonne} for r in righe]
        return RispostaFinta(righe)


def fixture_finta(fixture_id: int, league_id: int, *, status: str = "FT",
                  con_analisi: bool = True, gh: int = 1, ga: int = 0,
                  lh: float = 1.45, la: float = 1.12) -> Dict[str, Any]:
    """Riga di fixture_predictions con chiavi e tipi IDENTICI al vero."""
    analisi = None
    if con_analisi:
        analisi = {
            "model": "poisson_xg_hybrid_dc",
            "inputs": {"lambda_home": lh, "lambda_away": la},
            "markets": {"1x2": {"H": 0.48, "D": 0.27, "A": 0.25},
                        "over_2_5": {"True": 0.52, "False": 0.48}},
        }
    return {
        "fixture_id": fixture_id,
        "league_id": league_id,
        "league_name": f"Lega {league_id}",
        "fixture_date": "2025-08-16T18:30:00+00:00",
        "home_team_name": "Casa",
        "away_team_name": "Ospite",
        "result_status_short": status,
        "result_home_goals": gh,
        "result_away_goals": ga,
        "db_json_analisi": analisi,
        "raw_json_odds": {"bookmakers": [{"name": "Betfair", "bets": []}]},
        "model_predictions_json": {"target_1x2": {"H": 0.5, "D": 0.3, "A": 0.2}},
        "season_year": 2025,
    }


def costruisci_tabella(n_ft: int = 2500, semi: int = 7) -> List[Dict[str, Any]]:
    """Righe in ordine FISICO mescolato (il Seq Scan non e' ordinato per fixture_id)."""
    righe: List[Dict[str, Any]] = []
    fid = 135761
    for i in range(n_ft):
        status = ["FT", "FT", "FT", "AET", "PEN"][i % 5]
        righe.append(fixture_finta(fid, 39 + (i % 4), status=status))
        fid += 3
    # righe che i filtri devono ESCLUDERE
    for i in range(120):
        righe.append(fixture_finta(fid, 39, status="NS"))
        fid += 3
    for i in range(80):
        righe.append(fixture_finta(fid, 61, status="FT", con_analisi=False))
        fid += 3
    random.Random(semi).shuffle(righe)
    return righe


def lettura_vecchia_offset(sb, select_cols: str, *, con_analisi_non_null: bool,
                           page_size: int = 1000) -> List[Dict[str, Any]]:
    """RIPRODUZIONE FEDELE della vecchia lettura a OFFSET (riferimento di equivalenza)."""
    righe: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = (sb.table("fixture_predictions")
             .select(select_cols)
             .in_("result_status_short", ["FT", "AET", "PEN"]))
        if con_analisi_non_null:
            q = q.not_.is_("db_json_analisi", "null")
        resp = q.range(offset, offset + page_size - 1).execute()
        batch = resp.data or []
        righe.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return righe


COLONNE_BACKTEST = (
    "fixture_id,league_id,league_name,fixture_date,"
    "home_team_name,away_team_name,"
    "result_status_short,result_home_goals,result_away_goals,"
    "db_json_analisi,raw_json_odds,model_predictions_json"
)
COLONNE_CALIBRAZIONE = (
    "fixture_id,result_home_goals,result_away_goals,db_json_analisi,league_id"
)


@pytest.fixture(autouse=True)
def niente_attese(monkeypatch):
    """Azzera il backoff: i test verificano la MECCANICA, non l'orologio."""
    monkeypatch.setattr(master_backtest, "DB_ATTESA_BASE", 0.0)


@pytest.fixture
def db_iniettato(monkeypatch):
    """Inietta un modulo db_client finto: nessun .env, nessuna connessione vera."""
    def _inietta(db: DbFinto) -> DbFinto:
        modulo = types.ModuleType("db_client")
        modulo.get_supabase_client = lambda: db
        monkeypatch.setitem(sys.modules, "db_client", modulo)
        return db
    return _inietta


# =============================================================================
# 1 - EQUIVALENZA: stesso identico insieme di righe del metodo vecchio
# =============================================================================
def test_keyset_stesso_insieme_di_righe_del_vecchio_offset(db_iniettato):
    tabella = costruisci_tabella()
    db = db_iniettato(DbFinto({"fixture_predictions": tabella}))

    attese = lettura_vecchia_offset(db, COLONNE_BACKTEST, con_analisi_non_null=False)
    db.richieste.clear()
    ottenute = master_backtest.fetch_completed_fixtures()

    assert [r["fixture_id"] for r in ottenute] == sorted(r["fixture_id"] for r in attese)
    assert len(ottenute) == len(set(r["fixture_id"] for r in ottenute))  # zero duplicati
    per_id = {r["fixture_id"]: r for r in attese}
    assert all(r == per_id[r["fixture_id"]] for r in ottenute)  # stesse colonne, stessi valori


def test_keyset_usa_ordine_e_cursore_mai_offset(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=1200)}))
    master_backtest.fetch_completed_fixtures()

    assert all(q.ordine == "fixture_id" for q in db.richieste)
    assert all(q.intervallo is None for q in db.richieste)  # niente .range/OFFSET
    cursori = [v for q in db.richieste for (t, c, v, _n) in q.filtri
               if t == "gt" and c == "fixture_id"]
    assert cursori == sorted(cursori) and len(cursori) == len(set(cursori))


def test_filtri_data_e_leghe_restano_identici(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=300)}))
    master_backtest.fetch_completed_fixtures(date_from="2025-01-01", league_ids=[39, 61])
    prima = db.richieste[0]
    assert ("gte", "fixture_date", "2025-01-01", False) in prima.filtri
    assert ("in", "league_id", [39, 61], False) in prima.filtri
    assert ("in", "result_status_short", ["FT", "AET", "PEN"], False) in prima.filtri


def test_pagina_troncata_dal_server_non_ferma_la_scansione(db_iniettato):
    """max-rows lato server: la vecchia uscita su len(batch)<page_size perdeva righe."""
    tabella = costruisci_tabella(n_ft=900)
    db = db_iniettato(DbFinto({"fixture_predictions": tabella}))
    db.max_rows = 137  # il server tronca ogni pagina
    ottenute = master_backtest.fetch_completed_fixtures()
    attese = [r for r in tabella if r["result_status_short"] in ("FT", "AET", "PEN")]
    assert len(ottenute) == len(attese)


# =============================================================================
# 2 - TIMEOUT: dimezzamento, ripresa dallo stesso cursore, nessuna riga persa
# =============================================================================
def test_timeout_dimezza_la_pagina_e_riprende_dallo_stesso_cursore(db_iniettato):
    tabella = costruisci_tabella(n_ft=2500)
    db_pulito = DbFinto({"fixture_predictions": tabella})
    db_iniettato(db_pulito)
    attese = master_backtest.fetch_completed_fixtures()

    db = db_iniettato(DbFinto({"fixture_predictions": tabella}))
    db.guasto = lambda i, q: errore_timeout() if i == 3 else None
    ottenute = master_backtest.fetch_completed_fixtures()

    assert ottenute == attese  # stesse righe, stesso ordine, nessun buco
    fallita, ripresa = db.richieste[2], db.richieste[3]
    cursore = lambda q: [v for (t, c, v, _n) in q.filtri if t == "gt" and c == "fixture_id"]
    assert cursore(ripresa) == cursore(fallita)          # stesso cursore, non da capo
    assert fallita.limite == 1000 and ripresa.limite == 500  # pagina dimezzata


def test_timeout_ripetuti_nessuna_riga_persa_ne_duplicata(db_iniettato):
    tabella = costruisci_tabella(n_ft=2500)
    db_iniettato(DbFinto({"fixture_predictions": tabella}))
    attese = master_backtest.fetch_completed_fixtures()

    db = db_iniettato(DbFinto({"fixture_predictions": tabella}))
    db.guasto = lambda i, q: errore_timeout() if i in (1, 2, 4, 7, 11) else None
    ottenute = master_backtest.fetch_completed_fixtures()

    assert [r["fixture_id"] for r in ottenute] == [r["fixture_id"] for r in attese]
    assert len(ottenute) == len(set(r["fixture_id"] for r in ottenute))


def test_pagina_risale_dopo_letture_riuscite(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=6000)}))
    db.guasto = lambda i, q: errore_timeout() if i == 1 else None
    master_backtest.fetch_completed_fixtures()
    limiti = [q.limite for q in db.richieste]
    assert limiti[0] == 1000 and limiti[1] == 500
    assert max(limiti[2:]) == 1000  # riallarga invece di restare a pagine minuscole


def test_errore_di_gateway_e_ritentato_senza_dimezzare(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=1200)}))
    db.guasto = lambda i, q: errore_gateway() if i == 2 else None
    master_backtest.fetch_completed_fixtures()
    assert db.richieste[1].limite == 1000 and db.richieste[2].limite == 1000


# =============================================================================
# 3 - ERRORI VISIBILI: niente retry sugli errori logici, niente dati parziali
# =============================================================================
def test_errore_logico_non_viene_mai_ritentato(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=1200)}))
    db.guasto = lambda i, q: errore_logico() if i == 2 else None
    with pytest.raises(APIError) as info:
        master_backtest.fetch_completed_fixtures()
    assert info.value.code == "42703"
    assert len(db.richieste) == 2  # nessun tentativo in piu'


def test_timeout_persistente_propaga_errore_e_dimezza_fino_al_minimo(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=1200)}))
    db.guasto = lambda i, q: errore_timeout()
    with pytest.raises(APIError) as info:
        master_backtest.fetch_completed_fixtures()
    assert info.value.code == "57014"
    assert len(db.richieste) == master_backtest.DB_MAX_TENTATIVI
    assert [q.limite for q in db.richieste] == [1000, 500, 250, 125, 62, 50]


def test_classificazione_errori_transitori():
    assert master_backtest._errore_db_transitorio(errore_timeout())
    assert master_backtest._errore_db_transitorio(errore_gateway())
    assert not master_backtest._errore_db_transitorio(errore_logico())
    assert not master_backtest._errore_db_transitorio(ValueError("boom"))
    assert master_backtest._errore_db_timeout(errore_timeout())
    assert not master_backtest._errore_db_timeout(errore_gateway())

    class ReadTimeout(Exception):
        pass

    assert master_backtest._errore_db_transitorio(ReadTimeout("read timeout"))
    assert master_backtest._errore_db_timeout(ReadTimeout("read timeout"))


def test_backoff_cresce_e_ha_jitter(monkeypatch):
    monkeypatch.setattr(master_backtest, "DB_ATTESA_BASE", 1.5)
    attese = [master_backtest._attesa_retry(t) for t in range(1, 6)]
    assert all(1.5 * 2 ** (t - 1) <= a <= 1.5 * 2 ** (t - 1) + 1.5
               for t, a in enumerate(attese, start=1))
    campioni = {round(master_backtest._attesa_retry(1), 6) for _ in range(20)}
    assert len(campioni) > 1  # jitter presente


# =============================================================================
# 4 - HALFTIME: blocchi che avanzano anche quando matches non ha righe
# =============================================================================
def test_halftime_copre_tutti_gli_id_anche_con_timeout(db_iniettato):
    fids = list(range(200000, 200000 + 1000))
    # solo una fixture su tre ha la riga in matches: i blocchi devono avanzare lo stesso
    matches = [{"fixture_id": f, "halftime_home": 1, "halftime_away": 0}
               for f in fids if f % 3 == 0]
    db = db_iniettato(DbFinto({"matches": matches}))
    db.guasto = lambda i, q: errore_timeout() if i in (2, 5) else None

    ht = master_backtest.fetch_halftime_results(fids)

    assert set(ht) == {f for f in fids if f % 3 == 0}
    assert all(v == (1, 0) for v in ht.values())
    chiesti: List[int] = []
    for idx, q in enumerate(db.richieste, start=1):
        if db.guasto(idx, q) is None:
            chiesti.extend([v for (t, c, v, _n) in q.filtri if t == "in"][0])
    assert chiesti == fids  # partizione esatta: nessun id saltato, nessuno ripetuto


# =============================================================================
# 5 - update_poisson_calibration: stessa equivalenza
# =============================================================================
def test_update_poisson_fetch_all_data_equivalente_al_vecchio(db_iniettato):
    import update_poisson_calibration as upc

    tabella = costruisci_tabella(n_ft=2300)
    fids_ft = [r["fixture_id"] for r in tabella
               if r["result_status_short"] in ("FT", "AET", "PEN")
               and r["db_json_analisi"] is not None]
    matches = [{"fixture_id": f, "halftime_home": 0, "halftime_away": 1}
               for f in fids_ft[::2]]
    db = db_iniettato(DbFinto({"fixture_predictions": tabella, "matches": matches}))

    attese = lettura_vecchia_offset(db, COLONNE_CALIBRAZIONE, con_analisi_non_null=True)
    db.richieste.clear()
    db.guasto = lambda i, q: errore_timeout() if i == 2 else None
    righe, ht = upc.fetch_all_data()

    assert [r["fixture_id"] for r in righe] == sorted(r["fixture_id"] for r in attese)
    per_id = {r["fixture_id"]: r for r in attese}
    assert all(r == per_id[r["fixture_id"]] for r in righe)
    assert set(ht) == {f for f in fids_ft[::2]}
    # il filtro "db_json_analisi non null" resta applicato
    assert all(r["db_json_analisi"] is not None for r in righe)


def test_update_poisson_si_ferma_se_la_lettura_torna_vuota(monkeypatch, db_iniettato):
    """Senza righe la tabella sarebbe tutta 1.0: --apply non deve mai partire."""
    import update_poisson_calibration as upc

    db_iniettato(DbFinto({"fixture_predictions": [], "matches": []}))
    monkeypatch.setattr(sys, "argv", ["update_poisson_calibration.py", "--apply"])
    applicata = []
    monkeypatch.setattr(upc, "apply_to_money_management",
                        lambda *a, **k: applicata.append(True))

    with pytest.raises(SystemExit) as info:
        upc.main()

    assert info.value.code == 1
    assert applicata == []  # money_management.py mai toccato


# =============================================================================
# 6 - generate_dc_rho: mai un file parziale, e JSON identico vecchio/nuovo
# =============================================================================
def _prepara_dc_rho(monkeypatch, tmp_path, *, leghe_preesistenti: int = 3):
    import generate_dc_rho as gdr

    monkeypatch.setattr(gdr, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(gdr, "MIN_MATCHES_RHO", 20)

    class DataFissa(_datetime_reale):
        @classmethod
        def now(cls, tz=None):
            return _datetime_reale(2026, 9, 21, 3, 27, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(gdr, "datetime", DataFissa)

    percorso = tmp_path / "dc_rho_by_league.json"
    if leghe_preesistenti:
        percorso.write_text(json.dumps({
            "rho_by_league": {str(39 + i): -0.12 for i in range(leghe_preesistenti)},
            "global_fallback": -0.13,
            "leagues_estimated": leghe_preesistenti,
        }, indent=2), encoding="utf-8")
    return gdr, percorso


def test_dc_rho_non_sovrascrive_se_la_lettura_torna_vuota(monkeypatch, tmp_path):
    gdr, percorso = _prepara_dc_rho(monkeypatch, tmp_path)
    prima = percorso.read_bytes()
    monkeypatch.setattr(master_backtest, "fetch_completed_fixtures", lambda: [])

    with pytest.raises(SystemExit) as info:
        gdr.main()

    assert info.value.code == 1
    assert percorso.read_bytes() == prima  # file buono intatto


def test_dc_rho_lettura_vuota_non_crea_un_file_vuoto(monkeypatch, tmp_path):
    """Senza file precedente la lettura vuota deve fermarsi, non scrivere 0 leghe."""
    gdr, percorso = _prepara_dc_rho(monkeypatch, tmp_path, leghe_preesistenti=0)
    monkeypatch.setattr(master_backtest, "fetch_completed_fixtures", lambda: [])

    with pytest.raises(SystemExit) as info:
        gdr.main()

    assert info.value.code == 1
    assert not percorso.exists()
    assert not list(tmp_path.glob("*.tmp"))  # nessun temporaneo lasciato in giro


def test_dc_rho_non_sovrascrive_se_nessuna_lega_raggiunge_il_minimo(monkeypatch, tmp_path):
    gdr, percorso = _prepara_dc_rho(monkeypatch, tmp_path)
    prima = percorso.read_bytes()
    poche = [fixture_finta(200000 + i, 39, gh=i % 3, ga=(i + 1) % 2) for i in range(5)]
    monkeypatch.setattr(master_backtest, "fetch_completed_fixtures", lambda: poche)

    with pytest.raises(SystemExit) as info:
        gdr.main()

    assert info.value.code == 1
    assert percorso.read_bytes() == prima


def _campione_due_leghe() -> List[Dict[str, Any]]:
    """40 fixture per lega con lambda e risultati variati (>= MIN_MATCHES_RHO=20)."""
    righe: List[Dict[str, Any]] = []
    fid = 300001
    for lega, base in ((39, 1.35), (135, 1.05)):
        for i in range(40):
            righe.append(fixture_finta(
                fid, lega,
                gh=i % 4, ga=(i * 3) % 3,
                lh=base + 0.03 * (i % 7), la=0.9 + 0.05 * (i % 5),
            ))
            fid += 7
    random.Random(11).shuffle(righe)  # ordine FISICO mescolato, come un Seq Scan
    return righe


def test_dc_rho_json_identico_byte_per_byte_vecchio_e_nuovo(monkeypatch, tmp_path,
                                                            db_iniettato):
    gdr, percorso = _prepara_dc_rho(monkeypatch, tmp_path, leghe_preesistenti=0)
    tabella = _campione_due_leghe()
    lettura_nuova = master_backtest.fetch_completed_fixtures

    # --- vecchio codice: lettura a OFFSET, ordine fisico del Seq Scan ---
    db_vecchio = DbFinto({"fixture_predictions": tabella})
    monkeypatch.setattr(
        master_backtest, "fetch_completed_fixtures",
        lambda: lettura_vecchia_offset(db_vecchio, COLONNE_BACKTEST,
                                       con_analisi_non_null=False, page_size=25),
    )
    gdr.main()
    json_vecchio = percorso.read_bytes()

    # --- nuovo codice: lettura KEYSET con un timeout iniettato a meta' ---
    percorso.unlink()
    db_nuovo = db_iniettato(DbFinto({"fixture_predictions": tabella}))
    db_nuovo.guasto = lambda i, q: errore_timeout() if i == 2 else None
    monkeypatch.setattr(master_backtest, "fetch_completed_fixtures", lettura_nuova)
    monkeypatch.setattr(master_backtest, "DB_PAGE_SIZE", 25)
    monkeypatch.setattr(master_backtest, "DB_PAGE_SIZE_MIN", 5)
    gdr.main()
    json_nuovo = percorso.read_bytes()

    assert len(db_nuovo.richieste) > 3  # la lettura keyset e' passata da piu' pagine
    assert json_nuovo == json_vecchio
    payload = json.loads(json_nuovo)
    assert payload["leagues_estimated"] == 2
    assert set(payload["rho_by_league"]) == {"39", "135"}


# ============================================================================
# 7 - 57014 MASCHERATO da 500 non-JSON (la forma piu' probabile sotto carico)
# ============================================================================
def test_timeout_mascherato_da_500_e_riconosciuto_come_timeout():
    exc = errore_timeout_mascherato()
    assert master_backtest._codice_errore_db(exc) == "500"  # il codice non basta
    assert master_backtest._errore_db_timeout(exc)          # il testo lo svela
    assert master_backtest._errore_db_transitorio(exc)


def test_500_con_causa_logica_non_e_transitorio():
    exc = errore_500_logico()
    assert master_backtest._codice_errore_db(exc) == "500"
    assert not master_backtest._errore_db_timeout(exc)
    assert not master_backtest._errore_db_transitorio(exc)


def test_timeout_mascherato_dimezza_la_pagina_e_ritenta(db_iniettato):
    tabella = costruisci_tabella(n_ft=2500)
    db_iniettato(DbFinto({"fixture_predictions": tabella}))
    attese = master_backtest.fetch_completed_fixtures()

    db = db_iniettato(DbFinto({"fixture_predictions": tabella}))
    db.guasto = lambda i, q: errore_timeout_mascherato() if i == 3 else None
    ottenute = master_backtest.fetch_completed_fixtures()

    assert ottenute == attese
    fallita, ripresa = db.richieste[2], db.richieste[3]
    cursore = lambda q: [v for (t, c, v, _n) in q.filtri if t == "gt" and c == "fixture_id"]
    assert cursore(ripresa) == cursore(fallita)
    assert fallita.limite == 1000 and ripresa.limite == 500


def test_500_logico_non_viene_ritentato(db_iniettato):
    db = db_iniettato(DbFinto({"fixture_predictions": costruisci_tabella(n_ft=1200)}))
    db.guasto = lambda i, q: errore_500_logico() if i == 2 else None
    with pytest.raises(APIError):
        master_backtest.fetch_completed_fixtures()
    assert len(db.richieste) == 2  # nessun tentativo in piu'


def test_errori_di_connessione_sono_transitori(db_iniettato):
    """ConnectionError/reset/abort: rete, non logica -> si ritenta."""
    assert master_backtest._errore_db_transitorio(
        ConnectionResetError("[WinError 10054] connection reset by peer"))
    assert master_backtest._errore_db_transitorio(
        ConnectionAbortedError("connection aborted"))
    assert master_backtest._errore_db_transitorio(TimeoutError("timed out"))
    assert master_backtest._errore_db_timeout(TimeoutError("timed out"))
    # Senza marcatori nel testo restano riconoscibili solo dal TIPO: e' il caso
    # dei socket Windows, che si presentano con il solo numero di errore.
    assert master_backtest._errore_db_transitorio(ConnectionResetError("[WinError 10054]"))
    assert master_backtest._errore_db_timeout(TimeoutError())
    assert master_backtest._errore_db_transitorio(TimeoutError())

    class ProtocolError(Exception):
        pass

    assert master_backtest._errore_db_transitorio(ProtocolError("server disconnected"))

    tabella = costruisci_tabella(n_ft=1200)
    complete = [r for r in tabella if r["result_status_short"] in ("FT", "AET", "PEN")]
    db = db_iniettato(DbFinto({"fixture_predictions": tabella}))
    db.guasto = lambda i, q: (ConnectionResetError("connection reset by peer")
                              if i == 2 else None)
    righe = master_backtest.fetch_completed_fixtures()
    assert len(righe) == len(complete)
    assert db.richieste[2].limite == 1000  # rete: si riprova, non si dimezza


def test_57014_in_forma_di_stringa_senza_codice():
    """Alcuni client rilanciano l'errore come eccezione generica con il testo."""
    exc = RuntimeError("{'message': 'canceling statement due to statement timeout', "
                       "'code': '57014', 'hint': None, 'details': None}")
    assert master_backtest._errore_db_timeout(exc)
    assert master_backtest._errore_db_transitorio(exc)
    assert not master_backtest._errore_db_transitorio(RuntimeError("boom logico"))


# ============================================================================
# 8 - generate_dynamic_cal.py (Step 1 dello STESSO workflow settimanale)
# ============================================================================
COLONNE_DYNAMIC_CAL = (
    "fixture_id,result_home_goals,result_away_goals,db_json_analisi,league_id,raw_json_odds"
)


def lettura_vecchia_dynamic_cal(sb, page_size: int = 1000) -> List[Dict[str, Any]]:
    """RIPRODUZIONE FEDELE del fetch_data di HEAD (git show HEAD:generate_dynamic_cal.py).

    Keyset gia' presente, ma: uscita su `len(batch) < page_size` (perde righe se
    il server tronca la pagina) e retry debole (3 tentativi, solo "57014" nel
    testo, nessun dimezzamento). L'unica differenza rispetto a HEAD e' il
    `time.sleep(2 * attempt)`, qui omesso: non influisce sull'insieme letto.
    """
    rows: List[Dict[str, Any]] = []
    last_fid = 0
    while True:
        batch = None
        for attempt in range(1, 4):
            try:
                resp = (sb.table("fixture_predictions")
                        .select(COLONNE_DYNAMIC_CAL)
                        .in_("result_status_short", ["FT", "AET", "PEN"])
                        .not_.is_("db_json_analisi", "null")
                        .gt("fixture_id", last_fid)
                        .order("fixture_id")
                        .limit(page_size)
                        .execute())
                batch = resp.data or []
                break
            except Exception as ex:  # noqa: BLE001 - copia fedele di HEAD
                if "57014" in str(ex) and attempt < 3:
                    continue
                raise
        if not batch:
            break
        rows.extend(batch)
        last_fid = batch[-1]["fixture_id"]
        if len(batch) < page_size:
            break
    return rows


def _prepara_dynamic_cal(monkeypatch, tmp_path):
    """Isola generate_dynamic_cal: scrive in tmp, data fissa, NIENTE scritture DB."""
    import generate_dynamic_cal as gdc

    monkeypatch.setattr(gdc, "__file__", str(tmp_path / "generate_dynamic_cal.py"))

    class DataFissa(_datetime_reale):
        @classmethod
        def now(cls, tz=None):
            return _datetime_reale(2026, 9, 21, 3, 27, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(gdc, "datetime", DataFissa)
    scritture_db: List[Any] = []
    monkeypatch.setattr(gdc, "_upsert_poisson_calibration_db",
                        lambda payload: scritture_db.append(payload))
    monkeypatch.setattr(sys, "argv",
                        ["generate_dynamic_cal.py", "--min-n", "5", "--min-global", "5"])
    return gdc, tmp_path / "dynamic_cal.json", scritture_db


def test_dynamic_cal_stesso_insieme_di_righe_del_codice_di_head(db_iniettato):
    import generate_dynamic_cal as gdc

    tabella = costruisci_tabella(n_ft=2500)
    db = db_iniettato(DbFinto({"fixture_predictions": tabella, "matches": []}))
    attese = lettura_vecchia_dynamic_cal(db)
    db.richieste.clear()

    righe, _ht = gdc.fetch_data()

    assert [r["fixture_id"] for r in righe] == [r["fixture_id"] for r in attese]
    per_id = {r["fixture_id"]: r for r in attese}
    assert all(r == per_id[r["fixture_id"]] for r in righe)


def test_dynamic_cal_pagina_troncata_dal_server_perdeva_righe(db_iniettato):
    """Il difetto di HEAD: il server tronca la pagina e la scansione si ferma."""
    import generate_dynamic_cal as gdc

    tabella = costruisci_tabella(n_ft=2000)
    complete = [r for r in tabella
                if r["result_status_short"] in ("FT", "AET", "PEN")
                and r["db_json_analisi"] is not None]

    db = db_iniettato(DbFinto({"fixture_predictions": tabella, "matches": []}))
    db.max_rows = 137
    vecchie = lettura_vecchia_dynamic_cal(db)
    db.richieste.clear()
    nuove, _ht = gdc.fetch_data()

    assert len(vecchie) == 137                 # HEAD si fermava alla prima pagina
    assert len(nuove) == len(complete)         # la nuova le legge tutte
    assert {r["fixture_id"] for r in nuove} == {r["fixture_id"] for r in complete}


def test_dynamic_cal_blocchi_ht_ritentano_e_coprono_tutti_gli_id(db_iniettato):
    import generate_dynamic_cal as gdc

    tabella = costruisci_tabella(n_ft=700)
    fids = sorted(r["fixture_id"] for r in tabella
                  if r["result_status_short"] in ("FT", "AET", "PEN")
                  and r["db_json_analisi"] is not None)
    matches = [{"fixture_id": f, "halftime_home": 1, "halftime_away": 1}
               for f in fids if f % 2 == 0]
    db = db_iniettato(DbFinto({"fixture_predictions": tabella, "matches": matches}))
    # timeout sul primo blocco HT (le pagine fixture sono le richieste 1-2)
    db.guasto = lambda i, q: errore_timeout() if (i == 3 or i == 6) else None

    _righe, ht = gdc.fetch_data()

    assert set(ht) == {f for f in fids if f % 2 == 0}
    chiesti: List[int] = []
    for idx, q in enumerate(db.richieste, start=1):
        if q.tabella == "matches" and db.guasto(idx, q) is None:
            chiesti.extend([v for (t, c, v, _n) in q.filtri if t == "in"][0])
    assert chiesti == fids  # partizione esatta dei blocchi HT


def test_dynamic_cal_non_scrive_il_file_su_lettura_vuota(monkeypatch, tmp_path,
                                                         db_iniettato):
    gdc, percorso, scritture_db = _prepara_dynamic_cal(monkeypatch, tmp_path)
    db_iniettato(DbFinto({"fixture_predictions": [], "matches": []}))

    with pytest.raises(SystemExit) as info:
        gdc.main()

    assert info.value.code == 1
    assert not percorso.exists()   # dynamic_cal.json mai riscritto
    assert scritture_db == []      # nessuna scrittura sul DB


def test_dynamic_cal_json_identico_byte_per_byte_vecchio_e_nuovo(monkeypatch, tmp_path,
                                                                 db_iniettato):
    gdc, percorso, scritture_db = _prepara_dynamic_cal(monkeypatch, tmp_path)
    tabella = costruisci_tabella(n_ft=900)
    fids = sorted(r["fixture_id"] for r in tabella
                  if r["result_status_short"] in ("FT", "AET", "PEN")
                  and r["db_json_analisi"] is not None)
    matches = [{"fixture_id": f, "halftime_home": 1, "halftime_away": 0} for f in fids]
    lettura_nuova = gdc.fetch_data

    # --- codice di HEAD: keyset debole, nessun dimezzamento ---
    db_vecchio = db_iniettato(DbFinto({"fixture_predictions": tabella,
                                       "matches": matches}))

    def fetch_head():
        righe = lettura_vecchia_dynamic_cal(db_vecchio, page_size=200)
        ht = {}
        for i in range(0, len(righe), 300):
            blocco = [r["fixture_id"] for r in righe[i:i + 300]]
            resp = (db_vecchio.table("matches")
                    .select("fixture_id,halftime_home,halftime_away")
                    .in_("fixture_id", blocco).execute())
            for row in resp.data or []:
                ht[row["fixture_id"]] = (int(row["halftime_home"]),
                                         int(row["halftime_away"]))
        return righe, ht

    monkeypatch.setattr(gdc, "fetch_data", fetch_head)
    gdc.main()
    json_vecchio = percorso.read_bytes()

    # --- codice nuovo, con un timeout iniettato a meta' lettura ---
    percorso.unlink()
    db_nuovo = db_iniettato(DbFinto({"fixture_predictions": tabella,
                                     "matches": matches}))
    db_nuovo.guasto = lambda i, q: errore_timeout_mascherato() if i == 2 else None
    monkeypatch.setattr(gdc, "fetch_data", lettura_nuova)
    monkeypatch.setattr(master_backtest, "DB_PAGE_SIZE", 200)
    monkeypatch.setattr(master_backtest, "DB_PAGE_SIZE_MIN", 25)
    gdc.main()
    json_nuovo = percorso.read_bytes()

    assert json_nuovo == json_vecchio
    payload = json.loads(json_nuovo)
    assert payload["total_fixtures"] == len(fids)
    assert payload["leagues_covered"] > 0
    assert len(scritture_db) == 2  # l'upsert e' stato intercettato, mai eseguito
