"""24/09 - LIVE_ORDER_MODE DALLA UI: "devo operare dalla UI, non dal codice".

Cosa certifica:
  (1) LA REGOLA, in tutte le combinazioni env x DB: il modo effettivo e' il PIU'
      RESTRITTIVO (OFF < PAPER < LIVE); riga mancante/illeggibile/vecchia -> OFF;
      la UI non supera mai il tetto del .env e lo dice.
  (2) il worker della coda e il freno di Safe/Mike/Omega (``execution._live_brake``)
      leggono la STESSA regola, per ogni combinazione.
  (3) nel worker: aperture filtrate dal modo effettivo, chiusure sempre servite dal
      modo di processo (il freno ferma le aperture, mai le uscite).
  (4) nessuna lettura DB in piu' per giro: il modo arriva con lo snapshot che il
      worker legge gia' (1 RPC al secondo, come prima); i bot rileggono al massimo
      ogni 5 s e SOLO su apertura live.
  (5) all'avvio dell'app la riga scende a PAPER (mai sale); stesso avvio -> niente;
      finche' la dichiarazione d'avvio non riesce la scelta di ieri non vale.
  (6) il runner pubblica sul ``now`` il modo EFFETTIVO, il tetto e la scelta.

I finti parlano come il vero: la riga di ``get_live_settings`` ha le chiavi della
tabella ``betfair_live_settings`` (``migrations/betfair_live_controls.sql`` +
``betfair_live_risk_limits_v4.sql`` + ``live_order_mode_control_2026-09-24.sql``).
NESSUNA rete, NESSUN DB, NESSUN ordine reale.
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.live_order_worker as wk
from Betfair.stream import modo_ordini as MO
from Betfair.stream.tests.test_paper_live_stesso_processo_2026_09_16 import (
    _STRAT_LIVE,
    _STRAT_PAPER,
    _Sb,
    _by_id,
    _riga,
    _scenario,
)

_REAL_LOM = wk._live_order_mode
_REAL_PROC = wk._modo_processo


def _riga_settings(order_mode: Optional[str] = "paper", **kw: Any) -> Dict[str, Any]:
    """Riga ``betfair_live_settings`` come la restituisce ``to_jsonb(s.*)``."""
    riga: Dict[str, Any] = {
        "id": 1,
        "kill_switch": False,
        "max_exposure_per_selection": None,
        "max_orders_per_min": None,
        "order_poll_sec": None,
        "risk_poll_sec": None,
        "daily_loss_limit": None,
        "max_exposure_per_event": None,
        "max_exposure_per_league": None,
        "updated_at": "2026-09-24T09:00:00+00:00",
        "order_mode": order_mode,
        "order_mode_updated_at": "2026-09-24T09:00:00+00:00",
        "order_mode_updated_by": "daniele.ritrovato@gmail.com",
        "order_mode_boot_id": "boot-1",
        "order_mode_tetto": "live",
        "order_mode_tetto_at": "2026-09-24T08:00:00+00:00",
    }
    riga.update(kw)
    return riga


class _Rpc:
    def __init__(self, data: Any, boom: Optional[Exception] = None) -> None:
        self._data = data
        self._boom = boom

    def execute(self) -> Any:
        if self._boom is not None:
            raise self._boom
        return type("R", (), {"data": self._data})()


class _SbRpc(_Sb):
    """La coda finta del test F0 + le RPC vere che il worker chiama."""

    def __init__(self, rows: List[Dict[str, Any]], settings: Any,
                 boom: Optional[Exception] = None) -> None:
        super().__init__(rows)
        self.settings = settings
        self.boom = boom
        self.chiamate: List[tuple] = []

    def rpc(self, nome: str, params: Dict[str, Any]) -> _Rpc:
        self.chiamate.append((nome, dict(params)))
        if nome == "get_live_settings":
            return _Rpc(self.settings, self.boom)
        if nome == "live_order_mode_avvio":
            if self.boom is not None:
                return _Rpc(None, self.boom)
            nuovo = dict(self.settings or {})
            if params.get("p_modo") is not None:
                nuovo["order_mode"] = params["p_modo"]
            nuovo["order_mode_boot_id"] = params["p_boot_id"]
            nuovo["order_mode_tetto"] = params["p_tetto"]
            return _Rpc(nuovo)
        return _Rpc(None)


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    MO.azzera()
    wk._LAST_CYCLE.clear()
    monkeypatch.setattr(wk, "_live_order_mode", _REAL_LOM)
    monkeypatch.setattr(wk, "_modo_processo", _REAL_PROC)
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_journal_done", lambda *_a, **_k: None)
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    yield
    MO.azzera()
    wk._LAST_CYCLE.clear()


# ===========================================================================
# (1) LA REGOLA
# ===========================================================================
_ATTESO = {
    # (env, db) -> effettivo. None/"boh" = illeggibile -> OFF
    ("OFF", "off"): "OFF", ("OFF", "paper"): "OFF", ("OFF", "live"): "OFF",
    ("PAPER", "off"): "OFF", ("PAPER", "paper"): "PAPER", ("PAPER", "live"): "PAPER",
    ("LIVE", "off"): "OFF", ("LIVE", "paper"): "PAPER", ("LIVE", "live"): "LIVE",
    ("OFF", None): "OFF", ("PAPER", None): "OFF", ("LIVE", None): "OFF",
    ("OFF", "boh"): "OFF", ("PAPER", "boh"): "OFF", ("LIVE", "boh"): "OFF",
    ("boh", "live"): "OFF", (None, "live"): "OFF", ("", "live"): "OFF",
}


@pytest.mark.parametrize("env,db", sorted(_ATTESO, key=str))
def test_regola_piu_restrittiva_in_tutte_le_combinazioni(env, db):
    assert MO.modo_effettivo(env, db) == _ATTESO[(env, db)]


def test_la_ui_non_supera_il_tetto_e_lo_dice():
    info = MO.descrivi("PAPER", "live")
    assert info == {"effettivo": "PAPER", "tetto_ambiente": "PAPER",
                    "scelto_ui": "LIVE", "motivo": MO.MOTIVO_TETTO}
    assert MO.descrivi("LIVE", "paper")["motivo"] == MO.MOTIVO_OK
    assert MO.descrivi("LIVE", None)["motivo"] == MO.MOTIVO_DB_ASSENTE


def test_riga_mai_letta_o_senza_colonna_vale_off(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    assert MO.modo_corrente() == "OFF"                      # mai letta
    MO.registra_settings(_riga_settings(order_mode=None))    # colonna vuota
    assert MO.modo_corrente() == "OFF"
    riga = _riga_settings()
    del riga["order_mode"]                                   # migrazione non applicata
    MO.registra_settings(riga)
    assert MO.modo_corrente() == "OFF"
    MO.registra_settings(_riga_settings(order_mode="live"))
    assert MO.modo_corrente() == "LIVE"


def test_lettura_vecchia_torna_off(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    ora = [1000.0]
    monkeypatch.setattr(MO, "_ora", lambda: ora[0])
    MO.registra_settings(_riga_settings(order_mode="live"))
    assert MO.modo_corrente() == "LIVE"
    ora[0] += MO.VALIDITA_S - 0.1
    assert MO.modo_corrente() == "LIVE"
    ora[0] += 0.2
    assert MO.modo_corrente() == "OFF"
    assert MO.kill_switch_db() is False


# ===========================================================================
# (2) worker e Safe: la STESSA regola, combinazione per combinazione
# ===========================================================================
@pytest.mark.parametrize("env,db", list(itertools.product(
    ["OFF", "PAPER", "LIVE"], ["off", "paper", "live", None])))
def test_worker_e_safe_leggono_la_stessa_regola(monkeypatch, env, db):
    from Betfair.safe_strategy import execution as X

    monkeypatch.setenv("LIVE_ORDER_MODE", env)
    riga = _riga_settings(order_mode=db)
    # worker: la riga arriva dallo snapshot che legge gia' (_refresh_settings)
    wk._refresh_settings(_SbRpc([], riga))
    atteso = MO.modo_effettivo(env, db)
    assert wk._live_order_mode() == atteso
    # Safe/Mike/Omega: stessa riga, letta dal loro processo (qui: stesso finto)
    MO.azzera()
    monkeypatch.setattr("db_client.get_supabase_client", lambda: _SbRpc([], riga))
    freno = X._live_brake()
    # stessa DECISIONE (parte o no); il motivo nomina il tetto quando il tetto
    # basta a dire no (il DB non si legge), altrimenti il modo effettivo
    if atteso == "LIVE":
        assert freno is None
    else:
        assert freno == f"live_order_mode_non_live:{env if env != 'LIVE' else atteso}"


def test_safe_riga_illeggibile_e_kill_da_ui_fermano_il_live(monkeypatch):
    from Betfair.safe_strategy import execution as X

    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setattr("db_client.get_supabase_client",
                        lambda: _SbRpc([], None, boom=RuntimeError("DB giu'")))
    assert X._live_brake() == "live_order_mode_non_live:OFF"
    MO.azzera()
    monkeypatch.setattr("db_client.get_supabase_client",
                        lambda: _SbRpc([], _riga_settings(order_mode="live", kill_switch=True)))
    assert X._live_brake() == "live_kill_switch_attivo"


def test_safe_freni_non_importabili_non_mandano_ordini(monkeypatch):
    """Fail-closed: prima un modulo non importabile lasciava passare il live."""
    import builtins

    from Betfair.safe_strategy import execution as X

    vero = builtins.__import__

    def _finto(nome, *a, **k):
        if nome == "Betfair.stream" and a and a[2] and "modo_ordini" in a[2]:
            raise ImportError("sparito")
        return vero(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _finto)
    assert X._live_brake() == "freni_live_non_letti"


# ===========================================================================
# (3) worker: aperture col modo effettivo, chiusure col modo di processo
# ===========================================================================
def test_env_live_ui_paper_apertura_live_rifiutata_paper_eseguita(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    sb = _SbRpc([_riga(1, "live"), _riga(2, "paper")], _riga_settings(order_mode="paper"))
    fl, market, paper, reale = _scenario("LIVE")

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})

    r1, r2 = _by_id(sb, 1), _by_id(sb, 2)
    assert r1["status"] == "error" and "modo ordini PAPER" in r1["error"]
    assert r2["status"] == "done"
    assert reale.eseguiti == [] and len(paper.eseguiti) == 1


def test_env_paper_ui_live_vale_il_tetto(monkeypatch):
    """La UI chiede LIVE ma il .env dice PAPER: il runner non ha il client reale,
    la riga live e' rifiutata col motivo di sempre (mai eseguita)."""
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    sb = _SbRpc([_riga(3, "live")], _riga_settings(order_mode="live"))
    fl, market, paper, reale = _scenario("PAPER", con_reale=False)

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER})

    riga = _by_id(sb, 3)
    assert riga["status"] == "error" and wk.ERR_LIVE_CLIENT_ASSENTE in riga["error"]
    assert reale.eseguiti == [] and market.calls == []
    assert wk._blocco_apertura_modo("paper", "place", None) is None
    assert MO.stato_corrente()["motivo"] == MO.MOTIVO_TETTO


def test_ui_off_rifiuta_le_aperture_ma_serve_le_chiusure(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    sb = _SbRpc([_riga(4, "paper"),
                 _riga(5, "live", params={"reduces_liability": True})],
                _riga_settings(order_mode="off"))
    fl, market, paper, reale = _scenario("LIVE")

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})

    assert _by_id(sb, 4)["status"] == "error"
    assert "modo ordini OFF" in _by_id(sb, 4)["error"]
    assert _by_id(sb, 5)["status"] == "done"          # l'uscita passa
    assert len(reale.eseguiti) == 1 and paper.eseguiti == []


def test_riga_db_illeggibile_nel_worker_rifiuta_le_aperture(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    sb = _SbRpc([_riga(6, "paper")], None, boom=RuntimeError("DB giu'"))
    fl, market, paper, reale = _scenario("LIVE")

    wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})

    riga = _by_id(sb, 6)
    assert riga["status"] == "error" and "non letta" in riga["error"]
    assert paper.eseguiti == [] and reale.eseguiti == []


# ===========================================================================
# (4) nessuna lettura DB in piu' per giro
# ===========================================================================
def test_worker_una_sola_lettura_al_secondo_come_prima(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    sb = _SbRpc([], _riga_settings(order_mode="live"))
    fl, market, paper, reale = _scenario("LIVE")
    for _ in range(8):
        wk._process_once(sb, fl, strategy={"paper": _STRAT_PAPER, "live": _STRAT_LIVE})
        wk._live_order_mode()
        wk._blocco_apertura_modo("live", "place", None)
    letture = [c for c in sb.chiamate if c[0] == "get_live_settings"]
    assert len(letture) == 1, sb.chiamate


def test_modo_effettivo_non_tocca_mai_il_db(monkeypatch):
    def _vietato():
        raise AssertionError("_live_order_mode non deve leggere il DB")

    monkeypatch.setattr("db_client.get_supabase_client", _vietato)
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    for _ in range(50):
        assert wk._live_order_mode() == "OFF"
        MO.modo_corrente()


def test_bot_rilegge_al_massimo_ogni_5s_e_solo_col_tetto_live(monkeypatch):
    from Betfair.safe_strategy import execution as X

    ora = [500.0]
    monkeypatch.setattr(MO, "_ora", lambda: ora[0])
    sb = _SbRpc([], _riga_settings(order_mode="live"))
    monkeypatch.setattr("db_client.get_supabase_client", lambda: sb)
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    for _ in range(5):
        X._live_brake()
    assert sb.chiamate == []                  # tetto PAPER: il DB non serve
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    for _ in range(10):
        assert X._live_brake() is None
        ora[0] += 0.4                          # 10 aperture in 4 s
    assert len(sb.chiamate) == 1
    ora[0] += MO.ETA_RILETTURA_BOT_S
    X._live_brake()
    assert len(sb.chiamate) == 2


# ===========================================================================
# (5) avvio dell'app: la scelta scende a PAPER, mai sale
# ===========================================================================
@pytest.mark.parametrize("prima,atteso", [
    ("live", "PAPER"), ("paper", "PAPER"), ("off", "OFF"), (None, "PAPER"),
])
def test_avvio_nuovo_scende_a_paper_mai_sale(prima, atteso):
    assert MO.modo_all_avvio(_riga_settings(order_mode=prima), "boot-2") == atteso


def test_stesso_avvio_non_tocca_niente_e_id_vuoto_vale_avvio_nuovo():
    riga = _riga_settings(order_mode="live", order_mode_boot_id="boot-7")
    assert MO.modo_all_avvio(riga, "boot-7") is None
    assert MO.modo_all_avvio(riga, "") == "PAPER"
    assert MO.modo_all_avvio(_riga_settings(order_mode="live", order_mode_boot_id=None),
                             "") == "PAPER"


def test_runner_all_avvio_riporta_a_paper_e_intanto_non_eredita(monkeypatch):
    from Betfair.stream import runner as R

    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("APP_BOOT_ID", "boot-oggi")
    sb = _SbRpc([], _riga_settings(order_mode="live", order_mode_boot_id="boot-ieri"),
                boom=RuntimeError("DB giu'"))
    monkeypatch.setattr("db_client.get_supabase_client", lambda: sb)
    R._MODO_AVVIO_STATO["ultimo"] = -1e9
    MO.richiedi_avvio()
    # la lettura di ieri arriva dallo snapshot, ma non vale finche' non si dichiara
    MO.registra_settings(_riga_settings(order_mode="live"))
    assert MO.modo_corrente() == "OFF"
    assert R._dichiara_modo_ordini_all_avvio(forza=True) is False
    assert MO.modo_corrente() == "OFF" and MO.avvio_in_attesa()
    sb.boom = None
    assert R._dichiara_modo_ordini_all_avvio(forza=True) is True
    avvio = [c for c in sb.chiamate if c[0] == "live_order_mode_avvio"][-1][1]
    assert avvio == {"p_boot_id": "boot-oggi", "p_modo": "paper", "p_tetto": "live"}
    assert MO.modo_corrente() == "PAPER" and not MO.avvio_in_attesa()


def test_runner_riavvio_da_watchdog_non_tocca_la_scelta(monkeypatch):
    from Betfair.stream import runner as R

    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("APP_BOOT_ID", "boot-oggi")
    sb = _SbRpc([], _riga_settings(order_mode="live", order_mode_boot_id="boot-oggi"))
    monkeypatch.setattr("db_client.get_supabase_client", lambda: sb)
    MO.richiedi_avvio()
    assert R._dichiara_modo_ordini_all_avvio(forza=True) is True
    avvio = [c for c in sb.chiamate if c[0] == "live_order_mode_avvio"][-1][1]
    assert avvio["p_modo"] is None and avvio["p_tetto"] == "live"
    assert MO.modo_corrente() == "LIVE"


# ===========================================================================
# (6) il runner pubblica il modo effettivo (il badge legge questo)
# ===========================================================================
def test_now_pubblica_effettivo_tetto_e_scelta(monkeypatch):
    from Betfair.stream import runner as R

    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    MO.registra_settings(_riga_settings(order_mode="paper"))
    stato = R.LiveSession().build_live_state("E-nessuno")
    assert stato["order_mode"] == "PAPER"
    assert stato["order_mode_tetto"] == "LIVE"
    assert stato["order_mode_scelto"] == "PAPER"
