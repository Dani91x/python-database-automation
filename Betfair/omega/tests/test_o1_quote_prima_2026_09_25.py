"""O1 (25/09) -- le quote 1X2 pre-KO PRIMA della fixture nella catena dei lambda.

Interruttore ``lambda_quote_prima`` DEFAULT ACCESO (ordine dell'utente del
25/09 sera: "per TUTTI i bot i valori statistici e gli aiuti di default accesi").
SPENTO ESPLICITO la catena di ``omega_service._prematch_lambdas`` resta IDENTICA a
quella di sempre (fixture -> lambda salvati -> pre-KO -> ...): i test del ramo
spento lo passano sempre per esteso.

I finti parlano come il vero:
- ``get_event`` restituisce una riga di ``omega_events`` (``event_id``,
  ``fixture_id``, ``league_id``, ``model``);
- la fixture passa dalla funzione VERA ``Betfair.stream.db.get_fixture_prematch_lambdas``,
  con un client finto che risponde alla stessa query PostgREST
  (``table/select/eq/limit/execute``) con una riga di ``fixture_predictions``
  che porta i JSONB ``tactical_engine_json`` e ``db_json_analisi.inputs``;
- il ``pre_ko`` lo costruisce il produttore VERO dello scanner
  (``safe_strategy.scanner.freeze_pre_ko``) dai prezzi BACK del Match Odds.

Misura: AUDIT_2026-09-25/MISURA_PUNTO8_2026-09-25.md sez. 1.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.omega import omega_config as C
from Betfair.omega import omega_model as M
from Betfair.omega import omega_service as S
from Betfair.safe_strategy.scanner import freeze_pre_ko


# ---------------------------------------------------------------- finti
class _Risposta:
    def __init__(self, data: List[dict]) -> None:
        self.data = data


class _Query:
    """Stessa catena PostgREST di ``get_fixture_prematch_lambdas``."""

    def __init__(self, client: "_Client", tabella: str) -> None:
        self.client = client
        self.tabella = tabella
        self.filtri: Dict[str, Any] = {}

    def select(self, colonne: str) -> "_Query":
        assert colonne == "league_id,tactical_engine_json,db_json_analisi"
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self.filtri[col] = val
        return self

    def limit(self, _n: int) -> "_Query":
        return self

    def execute(self) -> _Risposta:
        assert self.tabella == "fixture_predictions"
        self.client.letture += 1
        riga = self.client.righe.get(int(self.filtri["fixture_id"]))
        return _Risposta([riga] if riga else [])


class _Client:
    def __init__(self, righe: Dict[int, dict]) -> None:
        self.righe = righe
        self.letture = 0

    def table(self, nome: str) -> _Query:
        return _Query(self, nome)


class _DB:
    """Le tre porte che ``_prematch_lambdas`` usa di ``omega_db``."""

    def __init__(self, eventi: Dict[str, dict]) -> None:
        self.eventi = eventi
        self.salvati: List[tuple] = []

    def get_event(self, event_id: str) -> Optional[dict]:
        return self.eventi.get(event_id)

    def save_event_model(self, event_id: str, model: dict) -> None:
        self.salvati.append((event_id, model))

    def event_lambda_hint(self, _event_id: str) -> Optional[dict]:
        return None

    def log(self, *_a: Any, **_k: Any) -> None:
        return None


FID = 1_208_021
LEGA = 135


def _riga_fixture(tattico: Optional[dict], inputs: Optional[dict]) -> dict:
    """Riga di ``fixture_predictions`` come la restituisce PostgREST (JSONB = dict)."""
    return {"league_id": LEGA,
            "tactical_engine_json": tattico,
            "db_json_analisi": ({"inputs": inputs, "markets": {}} if inputs is not None else None)}


def _evento(eid: str, fixture: bool = True) -> dict:
    return {"event_id": eid, "fixture_id": FID if fixture else None,
            "league_id": LEGA, "model": None}


def _pre_ko() -> dict:
    # prezzi BACK del Match Odds pre-KO, congelati dal produttore vero
    odds = {"home": {"back": 1.80, "lay": 1.82}, "draw": {"back": 3.70, "lay": 3.75},
            "away": {"back": 5.20, "lay": 5.30}}
    pk = freeze_pre_ko(None, False, odds, adesso_iso="2026-09-25T17:00:00+00:00")
    assert pk is not None and set(pk) == {"home", "draw", "away", "captured_at"}
    return pk


@pytest.fixture
def client(monkeypatch):
    import Betfair.stream.db as sdb

    c = _Client({FID: _riga_fixture({"lambda_home": 1.9, "lambda_away": 0.7}, None)})
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: c)
    yield c


@pytest.fixture(autouse=True)
def _cache_pulita():
    S._LAMBDA_CACHE.clear()
    yield
    S._LAMBDA_CACHE.clear()


# ---------------------------------------------------------------- whitelist
def test_parametro_esiste_acceso_di_default_e_passa_dalla_whitelist():
    assert C._SPEC["lambda_quote_prima"] == (True, bool, None, None)
    assert C.resolve_params({})["lambda_quote_prima"] is True
    assert C.resolve_params({"lambda_quote_prima": "off"})["lambda_quote_prima"] is False
    assert C.resolve_params({"lambda_quote_prima": False})["lambda_quote_prima"] is False
    assert C.resolve_params({"lambda_quote_prima": "on"})["lambda_quote_prima"] is True
    assert C.resolve_params({"lambda_quote_prima": True})["lambda_quote_prima"] is True


# ---------------------------------------------------------------- catena
def test_spento_quote_e_fixture_presenti_vince_la_fixture_come_oggi(client):
    db = _DB({"e1": _evento("e1")})
    payload = {"pre_ko": _pre_ko()}
    # interruttore spento ESPLICITO, grezzo e passato dalla whitelist: STESSO numero
    out_grezzo = S._prematch_lambdas(db, "e1", payload, params={"lambda_quote_prima": False})
    S._LAMBDA_CACHE.clear()
    out_spento = S._prematch_lambdas(db, "e1", payload,
                                     params=C.resolve_params({"lambda_quote_prima": False}))
    assert out_grezzo == (1.9, 0.7, LEGA, "fixture")
    assert out_spento == out_grezzo
    assert db.salvati == []              # la fixture non si persiste (come oggi)


def test_default_senza_params_e_whitelist_vuota_quote_in_testa(client):
    """25/09 sera: il DEFAULT e' acceso anche quando il chiamante non passa la
    chiave (``params`` assente) o passa la whitelist risolta da vuoto."""
    pk = _pre_ko()
    atteso = M.lambdas_from_pre_ko(pk)
    db = _DB({"e1b": _evento("e1b")})
    assert S._prematch_lambdas(db, "e1b", {"pre_ko": pk}) == (atteso[0], atteso[1], LEGA,
                                                              "pre_ko_odds")
    S._LAMBDA_CACHE.clear()
    assert S._prematch_lambdas(db, "e1b", {"pre_ko": pk}, params=C.resolve_params({}))[3] \
        == "pre_ko_odds"


def test_acceso_quote_e_fixture_presenti_vince_pre_ko(client):
    db = _DB({"e2": _evento("e2")})
    pk = _pre_ko()
    out = S._prematch_lambdas(db, "e2", {"pre_ko": pk},
                              params=C.resolve_params({"lambda_quote_prima": True}))
    atteso = M.lambdas_from_pre_ko(pk)
    assert atteso is not None
    assert out == (atteso[0], atteso[1], LEGA, "pre_ko_odds")
    # la fonte dice la verita' ed e' persistita come il ramo pre-KO di sempre
    assert db.salvati and db.salvati[-1][1]["lambda_source"] == "pre_ko_odds"
    # con le quote in testa la fixture NON si legge (letture DB in meno)
    assert client.letture == 0


@pytest.mark.parametrize("acceso", [False, True])
def test_senza_quote_fixture_in_entrambi_i_casi(client, acceso):
    db = _DB({"e3": _evento("e3")})
    out = S._prematch_lambdas(db, "e3", {"pre_ko": None},
                              params=C.resolve_params({"lambda_quote_prima": acceso}))
    assert out == (1.9, 0.7, LEGA, "fixture")


@pytest.mark.parametrize("acceso", [False, True])
def test_fixture_dal_db_json_analisi_inputs_quando_manca_il_tattico(monkeypatch, acceso):
    import Betfair.stream.db as sdb

    c = _Client({FID: _riga_fixture(None, {"lambda_home": 1.4, "lambda_away": 1.2, "dc_rho": -0.1})})
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: c)
    db = _DB({"e4": _evento("e4")})
    out = S._prematch_lambdas(db, "e4", {}, params={"lambda_quote_prima": acceso})
    assert out == (1.4, 1.2, LEGA, "fixture")


def test_acceso_quote_incomplete_ricade_sulla_fixture(client):
    """Un 1X2 senza il pareggio non e' una quota: si torna alla fixture."""
    db = _DB({"e5": _evento("e5")})
    rotto = {"home": 1.8, "away": 5.2, "captured_at": "2026-09-25T17:00:00+00:00"}
    out = S._prematch_lambdas(db, "e5", {"pre_ko": rotto}, params={"lambda_quote_prima": True})
    assert out == (1.9, 0.7, LEGA, "fixture")


def test_acceso_il_salvato_resta_dopo_le_quote(client):
    """Il ripiego ``saved`` (omega_events.model) resta DOPO il pre-KO: con le
    quote presenti vincono le quote anche se l'evento ha lambda salvati."""
    db = _DB({"e6": {"event_id": "e6", "fixture_id": None, "league_id": LEGA,
                     "model": {"lambda_pre": [2.2, 0.4], "lambda_source": "market_grid",
                               "saved_at": "2099-01-01T00:00:00+00:00"}}})
    pk = _pre_ko()
    acceso = S._prematch_lambdas(db, "e6", {"pre_ko": pk}, params={"lambda_quote_prima": True})
    assert acceso[3] == "pre_ko_odds"
    S._LAMBDA_CACHE.clear()
    spento = S._prematch_lambdas(db, "e6", {"pre_ko": pk}, params={"lambda_quote_prima": False})
    assert spento == (2.2, 0.4, LEGA, "market_grid")      # oggi: saved prima del pre-KO


def test_acceso_la_fixture_in_cache_scade_e_le_quote_arrivate_dopo_la_sostituiscono(client):
    db = _DB({"e7": _evento("e7")})
    p_on = {"lambda_quote_prima": True}
    # primo giro: quote non ancora congelate -> fixture
    assert S._prematch_lambdas(db, "e7", {}, params=p_on)[3] == "fixture"
    # dentro il TTL resta la cache
    assert S._prematch_lambdas(db, "e7", {"pre_ko": _pre_ko()}, params=p_on)[3] == "fixture"
    # oltre il TTL: a interruttore acceso anche la fixture scade -> quote
    val, ts = S._LAMBDA_CACHE["e7"]
    S._LAMBDA_CACHE["e7"] = (val, ts - S.LAMBDA_CACHE_TTL_S - 1)
    assert S._prematch_lambdas(db, "e7", {"pre_ko": _pre_ko()}, params=p_on)[3] == "pre_ko_odds"


def test_spento_la_fixture_in_cache_non_scade_mai_come_oggi(client):
    db = _DB({"e8": _evento("e8")})
    p_off = {"lambda_quote_prima": False}
    assert S._prematch_lambdas(db, "e8", {}, params=p_off)[3] == "fixture"
    val, ts = S._LAMBDA_CACHE["e8"]
    S._LAMBDA_CACHE["e8"] = (val, ts - S.LAMBDA_CACHE_TTL_S - 1)
    assert S._prematch_lambdas(db, "e8", {"pre_ko": _pre_ko()}, params=p_off)[3] == "fixture"
