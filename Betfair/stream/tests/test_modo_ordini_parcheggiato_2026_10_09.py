"""09/10/2026 - correzione "modo ordini da parcheggiato" (revisione del coordinatore).

DIFETTO: il tabellone abilita il box quota solo se conosce il modo ordini
EFFETTIVO dal canale (topic ``modo_ordini`` o ``hello.modo_ordini``; l'``hello.mode``
e' il solo tetto del .env). Ma i due runner rileggevano i settings e pubblicavano
il modo SOLO dentro i worker di flumine (calcio ``live_order_worker._process_once``
-> ``_refresh_settings`` -> ``_pubblica_modo_ordini_se_cambiato``; tennis
``tennis_live_order_worker`` -> ``guardie_tennis.aggiorna_impostazioni``). Col
runner PARCHEGGIATO (ciclo d'attesa, il caso normale del tennis) nessuno li
leggeva: "ORDINI: NON NOTA", conferma spenta, e i percorsi d'aggancio da
parcheggiato decidevano con kill-switch e modo vecchi o di default.

Cosa certifica (codice di produzione, ``setup_and_run`` VERO fermato al primo
sonno del ciclo d'attesa come nei test del 09/10):
  * calcio e tennis parcheggiati: dopo un giro d'attesa ``modo_ordini`` esce sul
    canale e nell'hello col modo ``effettivo`` LETTO (non il default);
  * il tennis pubblica il SUO stato (``sport: tennis``), mai quello del calcio;
  * kill-switch e modo usati da parcheggiato sono quelli dei settings (tennis:
    ``servi_comandi_da_parcheggiato`` rifiuta col freno / con OFF; calcio: la
    copia in RAM che il motore ordini controlla e' fresca e porta il freno);
  * nessuna lettura in piu': stesso orologio di cadenza del worker (nel passaggio
    parcheggiato -> framework il primo giro del worker non rilegge); tetto OFF ->
    nessuna lettura (come il worker, inerte);
  * il ciclo d'attesa non cade (DB giu', errore inatteso).

Finti: la riga di ``get_live_settings`` con le chiavi del vero
(``migrations/live_order_mode_control_2026-09-24.sql``), la RPC
``live_order_mode_avvio`` come in ``test_modo_ordini_ui_2026_09_24``; canale =
``LocalChannel`` VERO col publish registrato (``test_board_programma_2026_10_09``).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream import avvio_app as AA
from Betfair.stream import live_order_worker as LOW
from Betfair.stream import local_channel as LC
from Betfair.stream import modo_ordini as MO
from Betfair.stream.tests.test_board_programma_2026_10_09 import (  # noqa: F401 - fixture
    E1, T1, _api, _book, _cat, _Canale, _feed, _Fermo, _payload_calcio, _payload_tennis,
    _sonno_che_ferma, _stato_pulito)

BOOT = "boot-di-oggi-0910"


def _riga(modo: str = "paper", boot: Any = BOOT, kill: bool = False) -> Dict[str, Any]:
    """La riga di ``get_live_settings`` con le chiavi del vero."""
    return {"id": 1, "kill_switch": kill, "order_mode": modo,
            "order_mode_updated_at": "2026-10-09T08:00:00+00:00",
            "order_mode_updated_by": "utente@esempio.it", "order_mode_boot_id": boot,
            "order_mode_tetto": "live", "order_mode_tetto_at": "2026-10-09T07:59:00+00:00",
            "max_exposure_per_selection": None, "max_orders_per_min": None,
            "order_poll_sec": None, "risk_poll_sec": None}


class _Esito:
    def __init__(self, data: Any, boom: Optional[Exception]) -> None:
        self._data, self._boom = data, boom

    def execute(self) -> Any:
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(data=self._data)


class _Sb:
    """``sb.rpc(nome, params).execute().data`` come PostgREST, con le chiamate contate."""

    def __init__(self, riga: Dict[str, Any], boom: Optional[Exception] = None) -> None:
        self.riga = dict(riga)
        self.boom = boom
        self.chiamate: List[str] = []

    def letture(self) -> int:
        return self.chiamate.count("get_live_settings")

    def rpc(self, nome: str, params: Dict[str, Any]) -> _Esito:
        self.chiamate.append(nome)
        if nome == "get_live_settings":
            return _Esito(dict(self.riga), self.boom)
        if nome == "live_order_mode_avvio":
            if params.get("p_modo") is not None:
                self.riga["order_mode"] = params["p_modo"]
            self.riga["order_mode_boot_id"] = params["p_boot_id"]
            self.riga["order_mode_tetto"] = params["p_tetto"]
            return _Esito(dict(self.riga), None)
        raise AssertionError(f"RPC inattesa: {nome}")


def _modi(ch: _Canale) -> List[Dict[str, Any]]:
    return [d for t, d in ch.usciti if t == "modo_ordini"]


@pytest.fixture(autouse=True)
def _processo_pulito(monkeypatch):
    """Stato di PROCESSO dei settings e del modo a nuovo (elenco esplicito)."""
    from Betfair.stream.tennis_live import guardie_tennis as GT

    MO.azzera()
    GT.azzera_per_i_test()
    monkeypatch.setenv(AA.ENV_BOOT_ID, BOOT)
    monkeypatch.delenv("LIVE_KILL_SWITCH", raising=False)
    monkeypatch.setattr(LOW, "_SETTINGS", {})
    monkeypatch.setattr(LOW, "_SETTINGS_TS", None)
    monkeypatch.setattr(LOW, "_LAST_CYCLE", {})
    monkeypatch.setattr(LOW, "_MODO_CANALE_FIRMA", None)
    yield
    MO.azzera()
    GT.azzera_per_i_test()


# ===========================================================================
# CALCIO
# ===========================================================================
def _calcio_pronto(monkeypatch, sb: _Sb, tetto: str = "PAPER") -> _Canale:
    """Runner calcio parcheggiato senza motore, guardia d'avvio disarmata, DB finto."""
    import db_client
    from Betfair.stream import runner as R

    ch = _Canale("calcio", 47331)
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    monkeypatch.setenv("LIVE_ORDER_MODE", tetto)
    monkeypatch.setenv("MOTORE_ORDINI_CANALE", "0")
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(R, "_GUARDIA_AVVIO", AA.Guardia("runner_calcio"))
    monkeypatch.setattr(R, "_MODO_AVVIO_STATO", {"ultimo": -1e9})
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    monkeypatch.setattr(R, "_board_da_parcheggiato", lambda *a, **k: False)
    return ch


def test_runner_calcio_parcheggiato_pubblica_modo_ordini(monkeypatch, tmp_path):
    """``setup_and_run`` VERO in PAPER, nessuna partita: dopo il primo giro
    d'attesa il 47331 porta ``modo_ordini`` (topic e hello) col modo LETTO."""
    from Betfair.stream import runner as R

    sb = _Sb(_riga("live", boot="boot-di-ieri"))   # avvio nuovo: la riga scende a PAPER
    api = _api()
    _feed(monkeypatch, {E1: ("calcio", _payload_calcio())})
    ch = _Canale("calcio", 47331)

    def _start(port, sport, solo_lettura=False):
        assert (port, sport) == (47331, "calcio")
        monkeypatch.setattr(LC, "_CHANNEL", ch)
        return ch

    class _Rest:
        def login_cert(self):
            return None

    import db_client

    monkeypatch.setattr(db_client, "get_supabase_client", lambda: sb)
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    monkeypatch.setenv("MOTORE_ORDINI_CANALE", "0")
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    monkeypatch.setattr(R, "_GUARDIA_AVVIO", AA.Guardia("runner_calcio"))
    monkeypatch.setattr(R, "_MODO_AVVIO_STATO", {"ultimo": -1e9})

    def _ripresa_riuscita() -> bool:                 # la ripresa d'avvio (DB) riuscita
        R._GUARDIA_AVVIO.fatto = True
        return True
    monkeypatch.setattr(R, "_ripresa_all_avvio", _ripresa_riuscita)
    monkeypatch.setattr(R, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(R, "uploader", SimpleNamespace(sweep_pending=lambda **k: None))
    monkeypatch.setattr(R, "BetfairClient", _Rest)
    monkeypatch.setattr(R, "build_client", lambda login=True: api)
    monkeypatch.setattr(R._valuta.CAMBIO, "avvia", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "_chiudi_live_now_orfani_all_avvio", lambda: None)
    monkeypatch.setattr(R, "_announce_order_mode", lambda *a, **k: None)
    monkeypatch.setattr(R._AO, "richiesto", lambda: False)
    monkeypatch.setattr(R, "resolve_and_register", lambda rest: None)
    monkeypatch.setattr(R.db, "list_pending_follows", lambda: [])
    monkeypatch.setattr(R, "_sync_record_events", lambda s, f: None)
    monkeypatch.setattr(R, "_battito_in_attesa", lambda s, t: None)
    monkeypatch.setattr(R, "run_account_sync_if_due", lambda s: None)
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    monkeypatch.setattr(LC, "start_channel", _start)
    sonni: List[float] = []
    monkeypatch.setattr(R.time, "sleep", _sonno_che_ferma(sonni))
    with pytest.raises(_Fermo):
        R.setup_and_run()
    assert sonni, "ciclo d'attesa non raggiunto"
    assert ch.ultimo("board") is not None                  # il lavoro del 09/10 resta
    m = _modi(ch)
    assert m, "runner calcio parcheggiato: modo_ordini mai pubblicato (NON NOTA)"
    assert len(m) == 1                                     # solo al cambio
    assert m[0]["effettivo"] == "PAPER" and m[0]["tetto_ambiente"] == "PAPER"
    assert m[0]["scelto_ui"] == "PAPER" and m[0]["motivo"] == MO.MOTIVO_OK
    assert m[0]["kill_switch"] is False and m[0]["kill_switch_letto"] is True
    assert ch._hello_extra["modo_ordini"] == m[0]          # chi si collega dopo
    assert ch._hello_extra["mode"] == "PAPER"              # il tetto resta il tetto
    # la sola dichiarazione d'avvio + UNA lettura nel giro d'attesa
    assert sb.chiamate == ["get_live_settings", "live_order_mode_avvio", "get_live_settings"]


def test_calcio_parcheggiato_kill_switch_e_modo_freschi(monkeypatch):
    """Da parcheggiato la copia dei settings che il motore ordini controlla
    all'aggancio (kill-switch, eta', modo) e' quella LETTA adesso."""
    from Betfair.stream import runner as R

    sb = _Sb(_riga("paper", kill=True))
    ch = _calcio_pronto(monkeypatch, sb)
    assert LOW._db_kill_switch() is False and LOW.eta_settings_s() == float("inf")
    R._attesa_board_e_canale(object())
    assert sb.letture() == 1
    assert LOW._db_kill_switch() is True                   # il freno della UI letto
    assert LOW.eta_settings_s() < 1.0                      # copia fresca (motore: <= 10 s)
    assert LOW._live_order_mode() == "PAPER"               # modo effettivo letto
    m = _modi(ch)
    assert len(m) == 1 and m[0]["kill_switch"] is True and m[0]["effettivo"] == "PAPER"
    # la UI rilascia il freno e sceglie OFF: al giro dopo (cadenza 1 s) lo si vede
    sb.riga.update({"kill_switch": False, "order_mode": "off"})
    LOW._LAST_CYCLE["settings_refresh"] -= 5.0
    R._attesa_board_e_canale(object())
    assert LOW._db_kill_switch() is False and LOW._live_order_mode() == "OFF"
    assert [x["effettivo"] for x in _modi(ch)] == ["PAPER", "OFF"]


def test_calcio_nessuna_doppia_lettura_nel_passaggio_al_framework(monkeypatch):
    """Il giro d'attesa usa l'orologio di cadenza del worker della coda: il primo
    giro del worker subito dopo NON rilegge (e viceversa)."""
    from Betfair.stream import runner as R

    sb = _Sb(_riga("paper"))
    _calcio_pronto(monkeypatch, sb)
    R._attesa_board_e_canale(object())
    R._attesa_board_e_canale(object())                     # stesso secondo: niente
    assert sb.letture() == 1
    # il framework nasce: il giro VERO del worker della coda (``_process_once``),
    # col ciclo DB appena fatto (si ferma dopo i settings e il drenaggio locale)
    LOW._LAST_CYCLE["order_cycle"] = LOW._now_epoch()
    assert LOW._process_once(sb, flumine=None, session=None, strategy=None) == 0
    assert sb.letture() == 1, "passaggio parcheggiato -> framework: settings riletti due volte"
    # dopo la cadenza il worker rilegge lui (una volta)
    LOW._LAST_CYCLE["settings_refresh"] -= 5.0
    LOW._LAST_CYCLE["order_cycle"] = LOW._now_epoch()
    LOW._process_once(sb, flumine=None, session=None, strategy=None)
    assert sb.letture() == 2


def test_calcio_dichiarazione_d_avvio_riprovata_da_parcheggiato(monkeypatch):
    """Dichiarazione d'avvio fallita all'avvio (DB giu'): il worker guardato la
    riprova prima del worker della coda (``_live_order_worker_guardato``); da
    parcheggiato lo stesso, con lo stesso orologio, e solo a guardia disarmata.
    Senza, il modo restava OFF (scelta dalla UI non valida) per tutta l'attesa."""
    from Betfair.stream import runner as R

    sb = _Sb(_riga("live", boot="boot-di-ieri"))
    ch = _calcio_pronto(monkeypatch, sb)
    MO.richiedi_avvio()                                    # la forzata d'avvio non e' riuscita
    R._GUARDIA_AVVIO.attiva = True                         # guardia ARMATA: non si dichiara
    R._attesa_board_e_canale(object())
    assert sb.chiamate == ["get_live_settings"]
    assert _modi(ch)[-1]["effettivo"] == "OFF"             # scelta dalla UI non ancora valida
    R._GUARDIA_AVVIO.fatto = True                          # ripresa riuscita
    LOW._LAST_CYCLE["settings_refresh"] -= 5.0
    R._attesa_board_e_canale(object())
    # la dichiarazione (sua lettura + scrittura), poi la lettura del giro
    assert sb.chiamate == ["get_live_settings", "get_live_settings", "live_order_mode_avvio",
                           "get_live_settings"]
    assert MO.avvio_in_attesa() is False
    assert _modi(ch)[-1]["effettivo"] == "PAPER"           # avvio nuovo: scesa a PAPER


def test_calcio_tetto_off_nessuna_lettura(monkeypatch):
    """Tetto OFF: il worker della coda e' inerte e non legge; da parcheggiato idem."""
    from Betfair.stream import runner as R

    sb = _Sb(_riga("paper"))
    ch = _calcio_pronto(monkeypatch, sb, tetto="OFF")
    R._attesa_board_e_canale(object())
    assert sb.chiamate == [] and _modi(ch) == []


def test_calcio_ciclo_d_attesa_non_cade(monkeypatch):
    import db_client
    from Betfair.stream import runner as R

    giri: List[int] = []
    _calcio_pronto(monkeypatch, _Sb(_riga()))
    monkeypatch.setattr(R, "_board_da_parcheggiato", lambda *a, **k: giri.append(1))

    def _giu():
        raise RuntimeError("supabase giu'")
    monkeypatch.setattr(db_client, "get_supabase_client", _giu)
    R._attesa_board_e_canale(object())                     # non solleva
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: _Sb(_riga()))

    def _rotto(_sb):
        raise ValueError("errore inatteso")
    monkeypatch.setattr(LOW, "_refresh_settings", _rotto)
    R._attesa_board_e_canale(object())                     # non solleva
    assert giri == [1, 1]                                  # il board gira comunque


# ===========================================================================
# TENNIS
# ===========================================================================
def _tennis_pronto(monkeypatch, sb: _Sb, tetto: str = "PAPER") -> _Canale:
    from Betfair.stream.tennis_live import tennis_db as TD
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    ch = _Canale("tennis", 47332)
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", tetto)
    monkeypatch.setattr(TD, "get_tennis_client", lambda: sb)
    monkeypatch.setattr(TW, "_LOCAL_IN_AGGANCIO", type(TW._LOCAL_IN_AGGANCIO)())
    monkeypatch.setattr(TW, "_LOCAL_SEEN", {})
    return ch


def test_runner_tennis_parcheggiato_pubblica_modo_ordini(monkeypatch):
    """``setup_and_run`` VERO col tetto LIVE, nessuna partita: dopo il primo giro
    d'attesa il 47332 porta il modo del TENNIS letto (LIVE scelto in questo
    avvio: senza lettura sarebbe PAPER di default)."""
    from Betfair.stream.tennis_live import guardie_tennis as GT
    from Betfair.stream.tennis_live import tennis_bot_service as TBS
    from Betfair.stream.tennis_live import tennis_runner as TR

    sb = _Sb(_riga("live"))
    cat = {"MATCH_ODDS": [_cat("1.401", T1, "Barrios Vera v Simakin", "Match Odds",
                               [(9633138, "Barrios Vera", 0.0, 1),
                                (35635727, "Simakin", 0.0, 2)])]}
    books = {"1.401": _book("1.401", inplay=True, tm=43210.0, bet_delay=3,
                            runners=[(9633138, 0.0, 1.8, 1.82, 1.0, 1.0),
                                     (35635727, 0.0, 2.2, 2.24, 1.0, 1.0)])}
    api = _api(cat, books, [("MATCH_ODDS", 1)])
    _feed(monkeypatch, {T1: ("tennis", _payload_tennis())})
    ch = _tennis_pronto(monkeypatch, sb, tetto="LIVE")
    monkeypatch.setattr(LC, "_CHANNEL", None)

    def _start(port, sport, solo_lettura=False):
        assert (port, sport) == (47332, "tennis")
        monkeypatch.setattr(LC, "_CHANNEL", ch)
        return ch
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    monkeypatch.setenv("MOTORE_ORDINI_CANALE_TENNIS", "0")
    # ripresa d'avvio (DB) riuscita: la guardia si arma e si disarma
    monkeypatch.setattr(GT, "ripresa_all_avvio",
                        lambda db=None: setattr(GT.GUARDIA_RUNNER, "fatto", True) or True)
    monkeypatch.setattr(TR, "build_client", lambda login=True: api)
    monkeypatch.setattr(TR._valuta.CAMBIO, "avvia", lambda *_a, **_k: None)
    monkeypatch.setattr(TBS, "ferma_bot_al_nuovo_avvio", lambda *a, **k: None)
    monkeypatch.setattr(TR, "_cleanup_orphan_bot_controls", lambda: None)
    monkeypatch.setattr(TR.tennis_db, "chiudi_tennis_now_orfani", lambda: 0)
    monkeypatch.setattr(TR, "_avvia_sveglia_armamento", lambda s: None)
    monkeypatch.setattr(TR, "_announce_order_mode", lambda m: None)
    monkeypatch.setattr(TR, "safe_logout", lambda t: None)
    monkeypatch.setattr(TR.tennis_db, "list_pending_tennis_follows", lambda: [])
    monkeypatch.setattr(LC, "start_channel", _start)
    sonni: List[float] = []
    monkeypatch.setattr(TR.time, "sleep", _sonno_che_ferma(sonni))
    with pytest.raises(_Fermo):
        TR.setup_and_run()
    assert sonni, "ciclo d'attesa non raggiunto"
    assert ch.ultimo("board") is not None                  # il lavoro del 09/10 resta
    m = _modi(ch)
    assert m, "runner tennis parcheggiato: modo_ordini mai pubblicato (NON NOTA)"
    assert len(m) == 1
    assert m[0]["sport"] == "tennis"                       # il SUO stato, mai il calcio
    assert m[0]["effettivo"] == "LIVE" and m[0]["tetto_ambiente"] == "LIVE"
    assert m[0]["scelto_ui"] == "LIVE" and m[0]["motivo"] == MO.MOTIVO_OK
    assert ch._hello_extra["modo_ordini"] == m[0]
    assert ch._hello_extra["mode"] == "LIVE"
    assert sb.letture() == 1


@pytest.mark.parametrize("riga,motivo", [
    (_riga("paper", kill=True), "kill-switch ATTIVO"),     # freno tirato dalla UI
    (_riga("off"), "OFF"),                                 # "Ordini reali" OFF in questo avvio
])
def test_tennis_parcheggiato_kill_switch_e_modo_dai_settings(monkeypatch, riga, motivo):
    """``servi_comandi_da_parcheggiato`` decide col kill-switch e il modo LETTI
    nello stesso giro d'attesa: il place e' rifiutato e nessun aggancio parte."""
    from Betfair.stream import board_worker as bw
    from Betfair.stream.tennis_live import esecutore_tennis as ET
    from Betfair.stream.tennis_live import tennis_runner as TR

    sb = _Sb(riga)
    ch = _tennis_pronto(monkeypatch, sb)
    monkeypatch.setattr(bw, "giro_da_parcheggiato", lambda *a, **k: False)
    sess = TR.TennisLiveSession(trading=None)
    sess.aggancio_desktop = ET.AgganciaTennis(sess, risolvi=lambda m: None,
                                              allinea=lambda: None)
    ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=1, method="order", params={
        "action": "place", "mode": "paper", "client_ref": "crt-1", "market_id": "1.303",
        "selection_id": 11, "side": "BACK", "price": 2.0, "size": 2.0,
        "persistence": "LAPSE", "order_type": "LIMIT"}))
    TR._attesa_board_e_canale(sess)
    assert sb.letture() == 1
    risposte = {mid: (ok, e) for mid, ok, _d, e in ch.risposte}
    assert 1 in risposte, "place accettato in attesa d'aggancio con settings non letti"
    ok, e = risposte[1]
    assert ok is False and motivo in e
    assert not sess.aggancio_desktop.richieste             # nessuna partita agganciata


def test_tennis_nessuna_doppia_lettura_nel_passaggio_al_framework(monkeypatch):
    """Stesso orologio del worker ordini tennis (``_IMPOSTAZIONI_RILETTE``): la
    sua prima lettura subito dopo il giro d'attesa non rilegge."""
    from Betfair.stream import board_worker as bw
    from Betfair.stream.tennis_live import guardie_tennis as GT
    from Betfair.stream.tennis_live import tennis_db as TD
    from Betfair.stream.tennis_live import tennis_runner as TR

    sb = _Sb(_riga("paper"))
    _tennis_pronto(monkeypatch, sb)
    monkeypatch.setattr(bw, "giro_da_parcheggiato", lambda *a, **k: False)
    sess = TR.TennisLiveSession(trading=None)
    TR._attesa_board_e_canale(sess)
    TR._attesa_board_e_canale(sess)                        # stesso secondo: niente
    assert sb.letture() == 1
    GT.aggiorna_impostazioni(TD.get_tennis_client())       # la riga del worker ordini
    assert sb.letture() == 1, "passaggio parcheggiato -> framework: settings riletti due volte"
    GT._IMPOSTAZIONI_RILETTE["ts"] -= 5.0
    GT.aggiorna_impostazioni(TD.get_tennis_client())
    assert sb.letture() == 2


def test_tennis_tetto_off_nessuna_lettura(monkeypatch):
    from Betfair.stream import board_worker as bw
    from Betfair.stream.tennis_live import tennis_runner as TR

    sb = _Sb(_riga("paper"))
    ch = _tennis_pronto(monkeypatch, sb, tetto="OFF")
    monkeypatch.setattr(bw, "giro_da_parcheggiato", lambda *a, **k: False)
    TR._attesa_board_e_canale(TR.TennisLiveSession(trading=None))
    assert sb.chiamate == [] and _modi(ch) == []


def test_tennis_ciclo_d_attesa_non_cade(monkeypatch):
    from Betfair.stream import board_worker as bw
    from Betfair.stream.tennis_live import tennis_db as TD
    from Betfair.stream.tennis_live import tennis_runner as TR

    giri: List[int] = []
    _tennis_pronto(monkeypatch, _Sb(_riga()))
    monkeypatch.setattr(bw, "giro_da_parcheggiato", lambda *a, **k: giri.append(1))

    def _giu():
        raise RuntimeError("supabase giu'")
    monkeypatch.setattr(TD, "get_tennis_client", _giu)
    TR._attesa_board_e_canale(TR.TennisLiveSession(trading=None))   # non solleva
    assert giri == [1]


def test_calcio_e_tennis_non_si_mischiano(monkeypatch):
    """Sul 47332 esce solo il modo del tennis (tetto ``TENNIS_LIVE_ORDER_MODE``),
    sul 47331 solo quello del calcio (tetto ``LIVE_ORDER_MODE``)."""
    from Betfair.stream import board_worker as bw
    from Betfair.stream import runner as R
    from Betfair.stream.tennis_live import tennis_runner as TR

    monkeypatch.setattr(bw, "giro_da_parcheggiato", lambda *a, **k: False)
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")          # tetto del calcio diverso
    ch_t = _tennis_pronto(monkeypatch, _Sb(_riga("live")), tetto="PAPER")
    TR._attesa_board_e_canale(TR.TennisLiveSession(trading=None))
    m = _modi(ch_t)
    assert len(m) == 1 and m[0]["sport"] == "tennis" and m[0]["tetto_ambiente"] == "PAPER"
    ch_c = _calcio_pronto(monkeypatch, _Sb(_riga("live")), tetto="LIVE")
    MO.azzera()
    R._attesa_board_e_canale(object())
    mc = _modi(ch_c)
    assert len(mc) == 1 and "sport" not in mc[0] and mc[0]["tetto_ambiente"] == "LIVE"
    assert _modi(ch_t) == m                                # il 47332 non ha visto il calcio
