"""R3 (25/09 sera) - IL FRENO UNICO: ferma OGNI apertura, live E paper.

Ordine dell'utente: «si', un freno unico che ferma ogni cosa sia live che
paper». Il freno e' uno solo (``controls.motivo_kill_switch``: env
``LIVE_KILL_SWITCH`` oppure ``betfair_live_settings.kill_switch``, la riga che
la RPC ``set_live_kill_switch`` scrive). Prima di oggi:

  * il worker della coda e il motore del canale fermavano gia' live E paper;
  * Omega, Mike e Safe lo applicavano SOLO sulla strada REST LIVE: il fill
    PAPER simulato in casa (gate flumine chiuso) apriva lo stesso;
  * lo scalper si fermava SOLO col file ``STOP_SCALPER``;
  * lo stato del freno non arrivava alla Control Room dal canale.

Qui:
  (a) Mike in PAPER non apre col freno, la chiusura passa;
  (b) lo scalper non apre (e non parte) col freno del DB senza file STOP;
  (c) Omega (automatico e manuale) e Safe in PAPER non aprono;
  (d) freno non valutabile (import fallito) = freno tirato;
  (e) il messaggio ``modo_ordini`` porta il freno e i finti del frontend hanno
      le chiavi dei messaggi veri.

Finti: la riga ``betfair_live_settings`` e' quella della RPC vera
(``get_live_settings`` -> dict con ``kill_switch``); il DB di Mike e' il
``DbMemoria`` del banco comune; quello di Omega e' il ``FakeDB`` di
``test_omega_service``; quello dello scalper e' la classe ``Db`` VERA con un
client supabase finto (stesse chiamate ``table().update().eq().execute()``).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import builtins
import json
import os
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.mike import config as MC
from Betfair.mike import engine as ME
from Betfair.mike import feed as MF
from Betfair.mike import service as MS
from Betfair.omega import omega_service as OS
from Betfair.safe_strategy import execution as X
from Betfair.stream import canale_bot as CB
from Betfair.stream import live_order_worker as W
from Betfair.stream import local_channel as LC
from Betfair.stream import modo_ordini as MO
from Betfair.stream.backtest.banco_comune import DbMemoria
from Betfair.stream.scalper import scalper_service as SVC
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.trading import controls as CTL

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_FINTI_UI = os.path.join(_RADICE, "frontend", "src", "lib", "__fixtures__",
                         "runnerCanaleFinti.json")


# ---------------------------------------------------------------------------
# il freno: 'env', 'db' oppure None (rilasciato)
# ---------------------------------------------------------------------------
def _riga_settings(kill: bool) -> Dict[str, Any]:
    """La riga di ``betfair_live_settings`` come la restituisce la RPC vera."""
    return {"id": 1, "kill_switch": bool(kill), "max_exposure_per_selection": None,
            "max_orders_per_min": None, "order_poll_sec": None, "risk_poll_sec": None,
            "daily_loss_limit": None, "max_exposure_per_event": None,
            "max_exposure_per_league": None, "updated_at": "2026-09-25T20:00:00+00:00",
            "order_mode": "paper", "order_mode_updated_at": "2026-09-25T12:00:00+00:00",
            "order_mode_updated_by": "avvio_app"}


@pytest.fixture
def freno(monkeypatch):
    def _imposta(sorgente):
        monkeypatch.setenv("LIVE_KILL_SWITCH", "true" if sorgente == "env" else "false")
        monkeypatch.setattr(CTL, "get_live_settings",
                            lambda *a, **k: _riga_settings(sorgente == "db"))
    return _imposta


def _motivo(sorgente: str) -> str:
    return "live_kill_switch_attivo" if sorgente == "env" else "db_kill_switch_attivo"


@pytest.fixture
def controls_non_importabile(monkeypatch):
    """Il modulo del freno non si importa: il freno non e' valutabile."""
    vero_import = builtins.__import__

    def _import(nome, globs=None, locs=None, fromlist=(), livello=0):
        if nome.endswith("trading.controls") or (
                nome.endswith("trading") and "controls" in (fromlist or ())):
            raise ImportError("controls assente")
        return vero_import(nome, globs, locs, fromlist, livello)

    monkeypatch.setattr(builtins, "__import__", _import)


# ===========================================================================
# (c) SAFE - execution.place in PAPER (lo stesso place di Mike e delle
#     chiusure di Omega)
# ===========================================================================
def _safe_paper(meta=None):
    return X.place(db=SimpleNamespace(log=lambda *a, **k: None), market=None, mode="paper",
                   event_id="E1", market_id="1.1", selection_id=7, side="back",
                   price=3.0, size=5.0, best_size=100.0, client_ref="safe-t41",
                   trade_id=41, meta=meta, now=None, params={"execution_mode": "rest"})


@pytest.mark.parametrize("sorgente", ["env", "db"])
def test_safe_paper_apertura_ferma_col_freno(freno, sorgente):
    freno(sorgente)
    out = _safe_paper()
    assert out.status == "error"
    assert out.fill_note == _motivo(sorgente)
    assert out.size == 0.0


@pytest.mark.parametrize("meta", [{"closes_trade_id": 40}, {"cashout": True}])
def test_safe_paper_chiusura_passa_col_freno(freno, meta):
    freno("db")
    out = _safe_paper(meta)
    assert out.status == "open", "a freno tirato le chiusure passano sempre"


def test_safe_paper_freno_rilasciato_parita(freno):
    freno(None)
    assert _safe_paper().status == "open"


# ===========================================================================
# (a) MIKE - execute_place in PAPER (DbMemoria del banco, EventInfo vera)
# ===========================================================================
_ORA = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)


def _info() -> MF.EventInfo:
    return MF.EventInfo(
        event_id="35674515", event_name="Shanghai Port v Qingdao West Coast",
        home="Shanghai Port", away="Qingdao West Coast", competition="Chinese Super League",
        ko_at=_ORA.timestamp() + 3600.0, open_date=None,
        markets={ME.MARKET_OU35: "1.245111111", ME.MARKET_OU45: "1.245222222"},
        selections={(ME.MARKET_OU35, ME.SEL_UNDER): 47973,
                    (ME.MARKET_OU35, ME.SEL_OVER): 47972,
                    (ME.MARKET_OU45, ME.SEL_UNDER): 48901,
                    (ME.MARKET_OU45, ME.SEL_OVER): 48900})


def _mike(ruolo: str, side: str, price: float, closes=None) -> Tuple[str, DbMemoria]:
    db = DbMemoria({"status": "running", "mode": "paper", "params": {}})
    leg = ME.Leg(role=ruolo, market=ME.MARKET_OU35, selection=ME.SEL_UNDER,
                 side=side, price=price, size=10.0, ref=f"{ruolo}-0-1")
    book = ME.Book(status="OPEN", best_back=1.76, back_size=500.0,
                   best_lay=1.78, lay_size=500.0, inplay=False)
    esito = MS.execute_place(db=db, market=SimpleNamespace(), info=_info(), leg=leg,
                             book=book, mode="paper", params=dict(MC.merge_params(None)),
                             now=_ORA, dry=False, closes_trade_id=closes,
                             ctx=ME.MatchCtx(state="PRE", cycle_no=0))
    return esito, db


def _righe_aperte(db: DbMemoria) -> List[Dict[str, Any]]:
    return [r for r in db.trades if r.get("status") == "open"]


@pytest.mark.parametrize("sorgente", ["env", "db"])
def test_mike_paper_apertura_ferma_col_freno(freno, sorgente):
    freno(sorgente)
    esito, db = _mike("under_entry", "back", 1.76)
    assert esito == "cancelled"
    assert _righe_aperte(db) == [], "nessuna posizione paper nasce a freno tirato"
    skip = [p for k, p, _e in db.attivita if k == "skip"]
    assert skip and skip[-1]["reason"] == _motivo(sorgente)


def test_mike_paper_chiusura_passa_col_freno(freno):
    freno("db")
    esito, db = _mike("under_green", "lay", 1.78, closes=41)
    assert esito == "open"
    assert len(_righe_aperte(db)) == 1


def test_mike_paper_freno_rilasciato_parita(freno):
    freno(None)
    esito, db = _mike("under_entry", "back", 1.76)
    assert esito == "open" and len(_righe_aperte(db)) == 1


def test_mike_resting_paper_di_apertura_ferma(freno):
    freno("db")
    db = DbMemoria({"status": "running", "mode": "paper", "params": {}})
    leg = ME.Leg(role="under_entry", market=ME.MARKET_OU35, selection=ME.SEL_UNDER,
                 side="lay", price=1.78, size=5.0, ref="under_entry-0-1")
    assert MS._freno_resting_paper(db, leg, "35674515") is True
    assert leg.status == "cancelled"
    salt = [p for k, p, _e in db.attivita if k == "place_saltato"]
    assert salt and salt[0]["reason"] == "kill_switch"
    assert salt[0]["motivo"] == "db_kill_switch_attivo"
    freno(None)
    leg2 = ME.Leg(role="under_entry", market=ME.MARKET_OU35, selection=ME.SEL_UNDER,
                  side="lay", price=1.78, size=5.0, ref="under_entry-0-2")
    assert MS._freno_resting_paper(db, leg2, "35674515") is False


# ===========================================================================
# (c) OMEGA - automatico e manuale in PAPER: in
#     ``Betfair/omega/tests/test_omega_kill_switch_rest_o1_2026_09_24.py`` (serve
#     il conftest di Omega che azzera lo stato di processo fra un test e l'altro)
# ===========================================================================


# ===========================================================================
# (d) FAIL-CLOSED: freno non valutabile = freno tirato
# ===========================================================================
def test_safe_freno_aperture_import_fallito_e_tirato(controls_non_importabile):
    assert X._freno_aperture() == "kill_switch_illeggibile"


def test_safe_live_brake_import_fallito_e_tirato(controls_non_importabile, monkeypatch):
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    assert X._live_brake() == "kill_switch_illeggibile"


def test_safe_live_brake_freni_non_importabili_e_tirato(monkeypatch):
    vero_import = builtins.__import__

    def _import(nome, globs=None, locs=None, fromlist=(), livello=0):
        if nome == "Betfair.stream" and "modo_ordini" in (fromlist or ()):
            raise ImportError("modo_ordini assente")
        return vero_import(nome, globs, locs, fromlist, livello)

    monkeypatch.setattr(builtins, "__import__", _import)
    assert X._live_brake() == "freni_live_non_letti"


def test_safe_paper_col_freno_illeggibile_non_apre(controls_non_importabile):
    out = _safe_paper()
    assert out.status == "error" and out.fill_note == "kill_switch_illeggibile"


def test_omega_e_mike_freno_illeggibile_e_tirato(controls_non_importabile):
    assert OS._freno_rest_aperture() == "kill_switch_illeggibile"
    assert MS._freno_aperture_rest() == "kill_switch_illeggibile"


def test_scalper_freno_illeggibile_e_tirato(controls_non_importabile, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert SS.motivo_freno() == "kill_switch_illeggibile"


# ===========================================================================
# (b) SCALPER: il freno del DB senza file STOP
# ===========================================================================
class _SbFinto:
    """``sb.table(t).update(f).eq(c, v).execute()`` e ``.insert(r).execute()``
    come il client supabase vero: registra cosa scriverebbe."""

    def __init__(self) -> None:
        self.scritte: List[Tuple[str, str, Any]] = []

    def table(self, nome: str) -> Any:
        sb = self

        class _Q:
            def __init__(self) -> None:
                self._op: Tuple[str, Any] = ("", None)

            def update(self, campi):
                self._op = ("update", dict(campi))
                return self

            def insert(self, riga):
                self._op = ("insert", riga)
                return self

            def eq(self, _col, _val):
                return self

            def execute(self):
                sb.scritte.append((nome, self._op[0], self._op[1]))
                return SimpleNamespace(data=[])
        return _Q()


def _db_scalper() -> Tuple[SS.Db, _SbFinto]:
    db = SS.Db.__new__(SS.Db)
    sb = _SbFinto()
    db.sb = sb
    return db, sb


def test_scalper_motivo_freno_dal_db_senza_file(freno, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                 # nessun STOP_SCALPER qui
    assert not os.path.isfile(SS.KILL_FILE)
    freno("db")
    assert SS.motivo_freno() == "db_kill_switch_attivo"
    freno("env")
    assert SS.motivo_freno() == "live_kill_switch_attivo"
    freno(None)
    assert SS.motivo_freno() is None
    (tmp_path / SS.KILL_FILE).write_text("stop")
    assert SS.motivo_freno() == SS.MOTIVO_FILE


def test_scalper_sessione_non_parte_col_freno(freno, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    freno("db")
    db, sb = _db_scalper()
    assert SS.non_partire_col_freno(db, "34567890") == "db_kill_switch_attivo"
    upd = [c for t, op, c in sb.scritte if t == "scalper_control" and op == "update"]
    assert upd and upd[0]["status"] == "stopped"
    assert "freno tirato" in upd[0]["error"] and upd[0]["stopped_at"]
    freno(None)
    db2, sb2 = _db_scalper()
    assert SS.non_partire_col_freno(db2, "34567890") is None
    assert sb2.scritte == [], "a freno rilasciato la sessione parte senza scritture in piu'"


def test_scalper_supervisore_non_avvia_sessioni_col_freno():
    riga = {"event_id": "34567890", "status": "requested"}
    assert SVC.sessione_da_avviare(riga, False, "db_kill_switch_attivo") is False
    assert SVC.sessione_da_avviare(riga, False, None) is True
    assert SVC.sessione_da_avviare(riga, True, None) is False
    assert SVC.sessione_da_avviare({**riga, "status": "running"}, False, None) is False


def test_scalper_supervisore_legge_il_freno_del_db(freno, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    freno("db")
    assert SVC.freno_supervisore() == "db_kill_switch_attivo"
    freno(None)
    assert SVC.freno_supervisore() is None


def test_scalper_sorvegliante_arma_il_force_flat_al_freno(freno, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    freno("db")
    stop, visto, chiamate = threading.Event(), threading.Event(), []
    assert SS.sorveglia_freno(stop, visto, chiamate.append, poll_s=0.01) == "db_kill_switch_attivo"
    assert visto.is_set() and chiamate == ["db_kill_switch_attivo"]


def test_scalper_sorvegliante_esce_a_fine_sessione_senza_freno(freno, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    freno(None)
    stop, visto, chiamate = threading.Event(), threading.Event(), []
    stop.set()
    assert SS.sorveglia_freno(stop, visto, chiamate.append, poll_s=0.01) is None
    assert not visto.is_set() and chiamate == []


# ===========================================================================
# (e) il freno nel messaggio ``modo_ordini`` del runner calcio
# ===========================================================================
class _CanaleRegistrato(LC.LocalChannel):
    """Il canale VERO, non avviato, con ``publish`` che registra."""

    def __init__(self) -> None:
        super().__init__(47331, "calcio")
        self.usciti: List[Tuple[str, Any]] = []

    def publish(self, topic: str, payload: Any) -> None:  # type: ignore[override]
        json.dumps({"t": topic, "d": payload}, default=str)
        self.usciti.append((topic, payload))


class _SbSettings:
    def __init__(self) -> None:
        self.riga = _riga_settings(False)

    def rpc(self, nome, _args):
        assert nome == "get_live_settings"
        sb = self

        class _Q:
            def execute(self_inner):
                return SimpleNamespace(data=dict(sb.riga))
        return _Q()


@pytest.fixture
def canale(monkeypatch):
    ch = _CanaleRegistrato()
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    monkeypatch.setattr(W, "_MODO_CANALE_FIRMA", None)
    # ``_refresh_settings`` riscrive la copia di PROCESSO dei settings del worker
    # (kill_switch compreso): va ripristinata, o i test dopo vedrebbero il freno
    monkeypatch.setattr(W, "_SETTINGS", dict(W._SETTINGS))
    monkeypatch.setattr(W, "_SETTINGS_TS", W._SETTINGS_TS)
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    MO.azzera()
    CB.azzera_statistiche()
    yield ch
    MO.azzera()
    CB.azzera_statistiche()


def _modi(ch: _CanaleRegistrato) -> List[Dict[str, Any]]:
    return [d for t, d in ch.usciti if t == CB.TOPIC["modo_ordini"]]


def test_modo_ordini_porta_il_freno_e_lo_pubblica_al_cambio(canale):
    sb = _SbSettings()
    W._refresh_settings(sb)
    m = _modi(canale)
    assert len(m) == 1 and m[0]["kill_switch"] is False
    assert m[0]["kill_switch_letto"] is True and m[0]["kill_switch_env"] is False
    sb.riga["kill_switch"] = True                 # l'utente tira il freno dalla UI
    W._refresh_settings(sb)
    m = _modi(canale)
    assert len(m) == 2, "tirare il freno e' un cambio: esce subito sul canale"
    assert m[1]["kill_switch"] is True
    assert canale._hello_extra["modo_ordini"]["kill_switch"] is True
    W._refresh_settings(sb)
    assert len(_modi(canale)) == 2
    sb.riga["kill_switch"] = False                # rilasciato
    W._refresh_settings(sb)
    assert _modi(canale)[-1]["kill_switch"] is False


def test_modo_ordini_freno_dal_env(canale, monkeypatch):
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    W._refresh_settings(_SbSettings())
    m = _modi(canale)[-1]
    assert m["kill_switch"] is True and m["kill_switch_env"] is True


def test_i_finti_del_frontend_col_freno_hanno_chiavi_e_tipi_veri(canale):
    with open(_FINTI_UI, encoding="utf-8") as fh:
        finti = json.load(fh)
    sb = _SbSettings()
    sb.riga["kill_switch"] = True
    W._refresh_settings(sb)
    vero = _modi(canale)[-1]
    for nome in ("modo_ordini", "modo_ordini_live", "modo_ordini_freno"):
        assert set(finti[nome].keys()) == set(vero.keys()), nome
        for k in ("kill_switch", "kill_switch_env", "kill_switch_letto", "ts"):
            assert type(finti[nome][k]) is type(vero[k]), (nome, k)
    assert set(finti["hello"]["modo_ordini"].keys()) == set(vero.keys())
    assert finti["modo_ordini_freno"]["kill_switch"] is True is vero["kill_switch"]
