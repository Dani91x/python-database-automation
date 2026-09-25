"""25/09 - la SUPERFICIE di tennis_pro passa dal runner al bot, per partita.

Catena vera (nessuna classe di laboratorio):
  tennis_markets.competition_name --(ponte: ensure_follows_for_bots)-->
  tennis_live_follow.competition_name --(runner: _risolvi_follow)-->
  meta['competition_name'] --(runner: _instantiate_bot)--> bot.surface
e, a video, `_scrivi_superficie` -> params della riga `tennis_bot_control` +
attivita' `superficie`.

I finti hanno le chiavi e i tipi del vero: la riga di `tennis_markets` come la
seleziona `tennis_bot_service._market_row_for`, la riga di `tennis_live_follow`
come la scrive `tennis_db.register_tennis_follow`, la riga per partita come la
scrive il ponte (`tennis_bot_service._riga_armatura`, funzione vera), il
catalogo con la classe VERA di betfairlightweight (`MarketCatalogue`).

ATTENZIONE: i setup su terra/cemento NON sono certificati sul banco.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from betfairlightweight.filters import streaming_market_data_filter
from betfairlightweight.resources.bettingresources import MarketCatalogue

from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db
from Betfair.stream.tennis_live import tennis_runner as R


# ---------------------------------------------------------------------------
# finti con le chiavi del vero
# ---------------------------------------------------------------------------
def _riga_markets(ev: str = "35800001", comp: Any = "Roland Garros 2026") -> Dict[str, Any]:
    """Riga di `tennis_markets` con le colonne di `_market_row_for`."""
    return {"event_id": ev, "market_id": "1.250000001",
            "player1": {"name": "Jannik Sinner", "selection_id": 111},
            "player2": {"name": "Carlos Alcaraz", "selection_id": 222},
            "competition_name": comp, "open_date": "2026-06-01T12:00:00+00:00"}


def _catalogo(comp: Any = "Roland Garros 2026") -> MarketCatalogue:
    """listMarketCatalogue come lo rende Betfair (classe vera)."""
    dati: Dict[str, Any] = {
        "marketId": "1.250000001", "marketName": "Match Odds", "totalMatched": 1000.0,
        "runners": [
            {"selectionId": 111, "runnerName": "Jannik Sinner", "handicap": 0.0,
             "sortPriority": 1},
            {"selectionId": 222, "runnerName": "Carlos Alcaraz", "handicap": 0.0,
             "sortPriority": 2}],
        "event": {"id": "35800001", "name": "Sinner v Alcaraz", "countryCode": "FR",
                  "timezone": "GMT", "openDate": "2026-06-01T12:00:00.000Z"},
    }
    if comp is not None:
        dati["competition"] = {"id": "2536", "name": comp}
    return MarketCatalogue(**dati)


class _Betting:
    def __init__(self, cat: MarketCatalogue) -> None:
        self.cat = cat
        self.chiamate: List[Dict[str, Any]] = []

    def list_market_catalogue(self, filter=None, market_projection=None, sort=None,  # noqa: A002
                              max_results=None, **kw):
        self.chiamate.append({"market_projection": list(market_projection or [])})
        return [self.cat]


class _Trading:
    def __init__(self, cat: MarketCatalogue) -> None:
        self.betting = _Betting(cat)

    def login(self) -> None:  # pragma: no cover - non serve qui
        pass


def _servizio_pro(params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Riga VERA di `tennis_bot_service_control` (come nei test del ponte)."""
    return {"bot_key": "tennis_pro", "status": "running", "mode": "paper", "stake": 2,
            "params": params if params is not None else {}, "stats": None, "error": None,
            "started_at": None, "stopped_at": None, "heartbeat_at": None,
            "updated_at": None}


def _riga_control(ev: str = "35800001", params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """La riga per partita come la scrive il PONTE (`_riga_armatura`, vera),
    completata con le colonne che la tabella aggiunge (stats, error, ...)."""
    d = S.stato_desiderato([_servizio_pro(params)])["tennis_pro"]
    riga = S._riga_armatura(ev, "tennis_pro", d, dict(d["params"]))
    riga.update({"stats": None, "error": None, "requested_at": None, "started_at": None,
                 "stopped_at": None, "heartbeat_at": None})
    return riga


def _arma(control: Dict[str, Any], comp: Any, sink=None):
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    return R._instantiate_bot(
        "tennis_pro", control, "1.250000001", {"Jannik Sinner": 111, "Carlos Alcaraz": 222},
        sink or (lambda *a, **k: None), df, "PAPER", competition_name=comp)


# ===========================================================================
# 1. il catalogo chiede la COMPETIZIONE (stessa chiamata) e la meta la porta
# ===========================================================================
def test_resolve_market_chiede_e_porta_la_competizione():
    tr = _Trading(_catalogo("Roland Garros 2026"))
    meta = R._resolve_market(tr, "1.250000001", "35800001")
    assert "COMPETITION" in tr.betting.chiamate[0]["market_projection"]
    assert len(tr.betting.chiamate) == 1                 # nessuna chiamata in piu'
    assert meta["competition_name"] == "Roland Garros 2026"


def test_risolvi_follow_ripiega_sulla_riga_di_follow():
    """Catalogo senza competizione -> vale quella della riga di follow."""
    sess = R.TennisLiveSession(_Trading(_catalogo(None)))
    follow = {"event_id": "35800001", "market_id": "1.250000001",
              "player1_name": "Jannik Sinner", "player2_name": "Carlos Alcaraz",
              "open_date": "2026-06-01T12:00:00+00:00", "competition_name": "ATP Hamburg 2026",
              "status": "PENDING", "updated_at": "2026-06-01T11:00:00+00:00",
              "origine": "manuale", "error_detail": None}
    meta = R._risolvi_follow(sess, follow)
    assert meta["competition_name"] == "ATP Hamburg 2026"


def test_catalogo_vince_sulla_riga_di_follow():
    sess = R.TennisLiveSession(_Trading(_catalogo("Wimbledon 2026")))
    follow = {"event_id": "35800001", "market_id": "1.250000001",
              "competition_name": "qualcos'altro", "status": "PENDING"}
    assert R._risolvi_follow(sess, follow)["competition_name"] == "Wimbledon 2026"


# ===========================================================================
# 2. il runner passa la superficie al bot
# ===========================================================================
@pytest.mark.parametrize("comp,sup,fonte", [
    ("Roland Garros 2026", "clay", "mappa"),
    ("Wimbledon 2026", "grass", "mappa"),
    ("US Open 2026", "hard", "mappa"),
    ("Challenger Genova (Clay)", "clay", "nome"),
    ("ITF M15 Xyz", "hard", "default"),
    (None, "hard", "default"),
])
def test_instantiate_bot_passa_superficie_e_fonte(comp, sup, fonte):
    bot = _arma(_riga_control(), comp)
    assert bot.surface == sup
    assert bot.surface_fonte == fonte
    assert bot._tennis_superficie.superficie == sup


def test_vecchio_grass_della_ui_non_vince_sulla_partita():
    """La vecchia UI salvava surface='grass' su OGNI partita: ora decide il torneo."""
    bot = _arma(_riga_control(params={"surface": "grass"}), "Roland Garros 2026")
    assert bot.surface == "clay" and bot.surface_fonte == "mappa"
    # i 3 setup di reversione: accesi (terra)
    assert bot.enable_serving_set and bot.enable_double_break and bot.enable_compressed_fav


def test_senza_competizione_vale_il_torneo_gia_scritto_sulla_riga():
    ctrl = _riga_control(params={"surface_torneo": "ATP Madrid 2026"})
    bot = _arma(ctrl, None)
    assert (bot.surface, bot.surface_fonte) == ("clay", "mappa")


def test_varianti_accese_arrivano_dalla_riga_del_ponte():
    bot = _arma(_riga_control(), "Wimbledon 2026")
    assert (bot.trend, bot.adapt, bot.maker) == (True, True, True)
    spenti = _arma(_riga_control(params={"trend": False, "adapt": False, "maker": False}),
                   "Wimbledon 2026")
    assert (spenti.trend, spenti.adapt, spenti.maker) == (False, False, False)


def test_gli_altri_bot_non_ricevono_la_superficie():
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    flb = R._instantiate_bot("tennis_flb", {"stake": 2.0, "params": {}, "mode": "paper"},
                             "1.250000001", {}, lambda *a, **k: None, df, "PAPER",
                             competition_name="Roland Garros 2026")
    assert getattr(flb, "_tennis_superficie", "assente") is None


def test_catena_intera_tennis_markets_ponte_runner_bot(monkeypatch):
    """tennis_markets -> follow (ponte) -> meta (runner) -> bot.surface."""
    registrati: List[Dict[str, Any]] = []

    class _Q:
        def __init__(self, rows): self.rows = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self):
            class _R: pass
            r = _R(); r.data = self.rows
            return r

    class _Sb:
        def table(self, nome):
            assert nome == "tennis_markets"
            return _Q([_riga_markets(comp="ATP Kitzbuhel 2026")])

    monkeypatch.setattr(tennis_db, "list_tennis_bot_controls",
                        lambda *a, **k: [_riga_control()])
    monkeypatch.setattr(tennis_db, "list_pending_tennis_follows", lambda: [])
    monkeypatch.setattr(tennis_db, "get_tennis_client", lambda: _Sb())
    monkeypatch.setattr(tennis_db, "register_tennis_follow",
                        lambda **kw: registrati.append(dict(kw)))
    assert S.ensure_follows_for_bots() == ["35800001"]
    follow = {**registrati[0], "updated_at": None, "origine": "manuale", "error_detail": None}
    assert follow["competition_name"] == "ATP Kitzbuhel 2026"
    sess = R.TennisLiveSession(_Trading(_catalogo(None)))   # catalogo muto
    meta = R._risolvi_follow(sess, follow)
    bot = _arma(_riga_control(), meta["competition_name"])
    assert (bot.surface, bot.surface_fonte, bot._tennis_superficie.voce) == \
        ("clay", "mappa", "Kitzbuhel")


# ===========================================================================
# 3. a video: params della riga + attivita'
# ===========================================================================
@pytest.fixture
def scritture(monkeypatch):
    out: Dict[str, List[Any]] = {"params": [], "attivita": []}
    monkeypatch.setattr(tennis_db, "set_tennis_bot_params",
                        lambda ev, bk, p: out["params"].append((ev, bk, dict(p))))
    monkeypatch.setattr(tennis_db, "write_tennis_bot_activity",
                        lambda ev, bk, kind, payload: out["attivita"].append(
                            (ev, bk, kind, dict(payload))))
    return out


def test_scrivi_superficie_mette_superficie_e_fonte_nella_riga(scritture):
    ctrl = _riga_control(params={"bp_target_ticks": 5, "surface": "grass"})
    bot = _arma(ctrl, "Roland Garros 2026")
    R._scrivi_superficie("35800001", "tennis_pro", bot, ctrl)
    (ev, bk, p), = scritture["params"]
    assert (ev, bk) == ("35800001", "tennis_pro")
    assert p["bp_target_ticks"] == 5                     # i params della riga restano
    assert p["surface"] == "clay" and p["surface_fonte"] == "mappa"
    assert p["surface_voce"] == "Roland Garros"
    assert p["surface_torneo"] == "Roland Garros 2026"
    (_, _, kind, payload), = scritture["attivita"]
    assert kind == "superficie"
    assert payload["testo"] == "terra (mappa: Roland Garros)"
    assert payload["fonte"] == "mappa"
    assert payload["richiesta_ignorata"] == "grass"


def test_scrivi_superficie_default_dichiarato(scritture):
    ctrl = _riga_control()
    bot = _arma(ctrl, "Torneo Mai Visto")
    R._scrivi_superficie("35800001", "tennis_pro", bot, ctrl)
    p = scritture["params"][0][2]
    assert (p["surface"], p["surface_fonte"]) == ("hard", "default")
    assert scritture["attivita"][0][3]["testo"] == "cemento (default: torneo sconosciuto)"


def test_scrivi_superficie_non_riscrive_se_gia_uguale(scritture):
    ctrl = _riga_control()
    bot = _arma(ctrl, "Wimbledon 2026")
    ctrl2 = dict(ctrl)
    ctrl2["params"] = {**ctrl["params"], **bot._tennis_superficie.come_params()}
    R._scrivi_superficie("35800001", "tennis_pro", bot, ctrl2)
    assert scritture["params"] == [] and scritture["attivita"] == []


def test_scrivi_superficie_non_solleva_se_il_db_cade(monkeypatch):
    def _giu(*a, **k):
        raise RuntimeError("503")
    monkeypatch.setattr(tennis_db, "set_tennis_bot_params", _giu)
    monkeypatch.setattr(tennis_db, "write_tennis_bot_activity", _giu)
    ctrl = _riga_control()
    R._scrivi_superficie("35800001", "tennis_pro", _arma(ctrl, "Wimbledon"), ctrl)


def test_set_tennis_bot_params_aggiorna_solo_la_colonna_params(monkeypatch):
    fatti: List[Any] = []

    class _Q:
        def update(self, upd):
            fatti.append(("update", upd)); return self
        def eq(self, col, val):
            fatti.append(("eq", col, val)); return self
        def execute(self):
            class _R: data = []
            return _R()

    class _Sb:
        def table(self, nome):
            fatti.append(("table", nome)); return _Q()

    monkeypatch.setattr(tennis_db, "get_tennis_client", lambda: _Sb())
    monkeypatch.setattr(tennis_db, "_CANALE_ACCESO", False)
    tennis_db.set_tennis_bot_params("35800001", "tennis_pro", {"surface": "clay"})
    assert fatti == [("table", "tennis_bot_control"),
                     ("update", {"params": {"surface": "clay"}}),
                     ("eq", "event_id", "35800001"), ("eq", "bot_key", "tennis_pro")]
