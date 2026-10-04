# -*- coding: utf-8 -*-
"""IL TENNIS SEGUE «ORDINI REALI» (cantiere tetto tennis, passo 3, 04/10/2026).

Decisione dell'utente: i soldi veri del tennis li governa lo STESSO interruttore
«Ordini reali» del calcio (``betfair_live_settings.order_mode``). Regola:

  effettivo tennis = il piu' restrittivo fra il tetto del runner tennis e la scelta
  dalla UI valida per QUESTO avvio dell'app (``order_mode_boot_id == APP_BOOT_ID``);
  scelta non valida (non letta, scaduta, di un altro avvio) -> PAPER.

Le APERTURE seguono l'effettivo su ogni strada (canale ``/order``, coda DB, motore,
terza rete dentro flumine); le CHIUSURE passano sempre. Nessuna lettura in piu': la
riga arriva gia' ~1/s (``guardie_tennis.aggiorna_impostazioni``).

Finti che parlano come il vero: la riga e' quella di ``get_live_settings``
(``to_jsonb(s.*)``: chiavi ``order_mode`` minuscolo, ``order_mode_boot_id``,
``kill_switch``); framework, client, ``Market``, trading control VERI (dal modulo
``test_modalita_e_guardie_tennis_2026_09_24``: ``process_order_package`` registra il
pacchetto, nessuna chiamata a Betfair); canale ``LocalChannel``/``LocalRequest`` VERI.
"""
from __future__ import annotations

import types
from typing import Any, Dict

import pytest
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import modo_ordini as MO
from Betfair.stream.tennis_live import esecutore_tennis as ET
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import tennis_live_order_worker as W
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_modalita_e_guardie_tennis_2026_09_24 import (  # noqa: F401
    MID,
    SEL,
    _arma,
    _DbCoda,
    _gira,
    _quadro,
    _richiesta,
    _riga_coda,
    _stato_pulito,
    bot_che_entra,
    worker_finto,
)

BOOT = "boot-di-oggi"


def _riga(modo: str = "live", boot: Any = BOOT, kill: bool = False) -> Dict[str, Any]:
    """La riga di ``get_live_settings`` con le chiavi del vero."""
    return {"id": 1, "kill_switch": kill, "order_mode": modo,
            "order_mode_updated_at": "2026-10-04T10:00:00+00:00",
            "order_mode_updated_by": "utente@esempio.it", "order_mode_boot_id": boot,
            "order_mode_tetto": "live", "order_mode_tetto_at": "2026-10-04T09:00:00+00:00"}


@pytest.fixture(autouse=True)
def _modo_pulito(monkeypatch):
    MO.azzera()
    monkeypatch.setenv("APP_BOOT_ID", BOOT)
    yield
    MO.azzera()


# --------------------------------------------------------------------------- la regola
@pytest.mark.parametrize("tetto,riga,atteso", [
    ("LIVE", _riga("live"), "LIVE"),                       # gesto in questo avvio
    ("LIVE", _riga("paper"), "PAPER"),
    ("LIVE", _riga("off"), "OFF"),                         # OFF esplicito vale OFF
    ("LIVE", _riga("live", boot="boot-di-ieri"), "PAPER"),  # scelta di ieri: non vale
    ("LIVE", _riga("live", boot=None), "PAPER"),           # riga mai dichiarata
    ("LIVE", None, "PAPER"),                               # riga mai letta
    ("PAPER", _riga("live"), "PAPER"),                     # mai sopra il tetto
    ("OFF", _riga("live"), "OFF"),
])
def test_regola_del_modo_effettivo_tennis(tetto, riga, atteso):
    if riga is not None:
        MO.registra_settings(riga)
    assert MO.modo_effettivo_tennis(tetto) == atteso


def test_lettura_scaduta_torna_paper(monkeypatch):
    MO.registra_settings(_riga("live"))
    assert MO.modo_effettivo_tennis("LIVE") == "LIVE"
    ora = MO._ora() + MO.VALIDITA_S + 1.0
    monkeypatch.setattr(MO, "_ora", lambda: ora)
    assert MO.modo_effettivo_tennis("LIVE") == "PAPER"


def test_processo_senza_app_boot_id_mai_live(monkeypatch):
    """Un runner lanciato fuori dall'app (APP_BOOT_ID assente) non sa da quale
    avvio viene: la scelta non vale mai."""
    monkeypatch.delenv("APP_BOOT_ID", raising=False)
    MO.registra_settings(_riga("live", boot=""))
    assert MO.modo_effettivo_tennis("LIVE") == "PAPER"


def test_avvio_nuovo_dell_app_tutto_in_prova(monkeypatch):
    """La riga e' rimasta LIVE dall'avvio di prima; l'app si riapre (id nuovo):
    prima che il runner calcio la riporti a PAPER il tennis e' gia' in prova;
    dopo (``dichiara_avvio`` -> paper + boot nuovo) resta in prova finche'
    l'utente non sceglie di nuovo LIVE."""
    monkeypatch.setenv("APP_BOOT_ID", "boot-nuovo")
    MO.registra_settings(_riga("live", boot=BOOT))
    assert MO.modo_effettivo_tennis("LIVE") == "PAPER"
    assert MO.modo_all_avvio(_riga("live", boot=BOOT), "boot-nuovo") == "PAPER"
    MO.registra_settings(_riga("paper", boot="boot-nuovo"))
    assert MO.modo_effettivo_tennis("LIVE") == "PAPER"
    MO.registra_settings(_riga("live", boot="boot-nuovo"))     # il gesto di oggi
    assert MO.modo_effettivo_tennis("LIVE") == "LIVE"


def test_stato_tennis_dice_il_perche():
    s = MO.stato_tennis("LIVE")
    assert (s["effettivo"], s["motivo"], s["scelto_ui"]) == ("PAPER", MO.MOTIVO_DB_ASSENTE, None)
    MO.registra_settings(_riga("live", boot="boot-di-ieri"))
    s = MO.stato_tennis("LIVE")
    assert (s["effettivo"], s["motivo"]) == ("PAPER", MO.MOTIVO_AVVIO_DIVERSO)
    MO.registra_settings(_riga("live"))
    s = MO.stato_tennis("PAPER")
    assert (s["effettivo"], s["motivo"], s["tetto_ambiente"]) == ("PAPER", MO.MOTIVO_TETTO, "PAPER")
    s = MO.stato_tennis("LIVE")
    assert (s["effettivo"], s["motivo"], s["scelto_ui"]) == ("LIVE", MO.MOTIVO_OK, "LIVE")


def test_il_calcio_non_cambia():
    """Il modo del calcio resta quello di prima (nessun controllo d'avvio qui:
    il calcio ha ``richiedi_avvio``/``dichiara_avvio``)."""
    MO.registra_settings(_riga("live", boot="boot-di-ieri"))
    assert MO.modo_effettivo("LIVE", MO.valore_db()) == "LIVE"


# --------------------------------------------------------------------------- aperture / chiusure
@pytest.fixture
def tetto_live(monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")


@pytest.mark.parametrize("action,params,bloccata", [
    ("place", {}, True),
    ("replace", {}, True),
    ("place", {"reduces_liability": True}, False),
    ("greenup", {}, False),
    ("cancel", {}, False),
])
def test_aperture_live_ferme_chiusure_servite(tetto_live, action, params, bloccata):
    MO.registra_settings(_riga("paper"))
    motivo = W._blocco_apertura_modo("live", action, params)
    assert (motivo is not None) is bloccata
    if bloccata:
        assert "Ordini reali" in motivo
    # la prova non si ferma
    assert W._blocco_apertura_modo("paper", action, params) is None


def test_motore_tennis_usa_la_stessa_regola(tetto_live):
    MO.registra_settings(_riga("paper"))
    assert ET._blocco_apertura_modo("live", "place", {}) is not None
    MO.registra_settings(_riga("live"))
    assert ET._blocco_apertura_modo("live", "place", {}) is None


def test_canale_locale_paper_e_live_per_riga(worker_finto, monkeypatch):
    """Tetto LIVE, «Ordini reali» in PROVA: il clic in prova parte (client paper),
    il clic reale e' rifiutato col motivo, il green-up reale passa (chiusura)."""
    MO.registra_settings(_riga("paper"))
    monkeypatch.setattr(W, "tennis_db", _DbCoda([]))
    ch = worker_finto["ch"]
    ch._requests.put_nowait(_richiesta(1, "place", mode="paper", side="BACK", price=2.0, size=2.0))
    ch._requests.put_nowait(_richiesta(2, "place", mode="live", side="BACK", price=2.0, size=2.0))
    ch._requests.put_nowait(_richiesta(3, "greenup", mode="live"))
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    per_id = {m: (ok, err) for m, ok, err in worker_finto["risposte"]}
    assert per_id[1][0] is True and per_id[3][0] is True
    assert per_id[2][0] is False and "Ordini reali" in per_id[2][1]
    assert [a for a, _ in worker_finto["eseguiti"]] == ["place", "greenup"]


def test_canale_locale_live_con_ordini_reali_live(worker_finto, monkeypatch):
    MO.registra_settings(_riga("live"))
    monkeypatch.setattr(W, "tennis_db", _DbCoda([]))
    ch = worker_finto["ch"]
    ch._requests.put_nowait(_richiesta(1, "place", mode="live", side="BACK", price=2.0, size=2.0))
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    assert worker_finto["risposte"][0][1] is True
    assert [a for a, _ in worker_finto["eseguiti"]] == ["place"]


def test_canale_locale_runner_paper_rifiuta_il_live(worker_finto, monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    MO.registra_settings(_riga("live"))
    monkeypatch.setattr(W, "tennis_db", _DbCoda([]))
    ch = worker_finto["ch"]
    ch._requests.put_nowait(_richiesta(1, "place", mode="live", side="BACK", price=2.0, size=2.0))
    ch._requests.put_nowait(_richiesta(2, "place", mode="paper", side="BACK", price=2.0, size=2.0))
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    per_id = {m: (ok, err) for m, ok, err in worker_finto["risposte"]}
    assert per_id[1][0] is False and "non servibile" in per_id[1][1]
    assert per_id[2][0] is True


def test_coda_db_aperture_reali_ferme_col_motivo(worker_finto, monkeypatch):
    MO.registra_settings(_riga("live", boot="boot-di-ieri"))
    db = _DbCoda([_riga_coda(1, "place", mode="live", side="BACK", price=2.0, size=2.0),
                  _riga_coda(2, "place", mode="paper", side="BACK", price=2.0, size=2.0),
                  _riga_coda(3, "greenup", mode="live"),
                  _riga_coda(4, "cancel", mode="live", bet_id="B-1")])
    monkeypatch.setattr(W, "tennis_db", db)
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    assert [a for a, _ in worker_finto["eseguiti"]] == ["place", "greenup", "cancel"]
    rifiutate = {rid: res["error"] for rid, res in db.errori}
    assert set(rifiutate) == {1}
    assert "questo avvio" in rifiutate[1]


def test_specchio_del_canale_sotto_la_modalita_dell_ordine(worker_finto, monkeypatch):
    """Prima lo specchio di un clic dal canale usava la modalita' del RUNNER."""
    MO.registra_settings(_riga("paper"))
    monkeypatch.setattr(W, "tennis_db", _DbCoda([]))
    specchi = []
    monkeypatch.setattr(W, "_mirror_order", lambda mode, *a, **k: specchi.append(mode))
    worker_finto["ch"]._requests.put_nowait(
        _richiesta(1, "place", mode="paper", side="BACK", price=2.0, size=2.0))
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace(tracked_orders={}))
    assert specchi == ["paper"]


# --------------------------------------------------------------------------- terza rete
def _q_con_terza_rete() -> Dict[str, Any]:
    q = _quadro("LIVE")
    q["fw"].add_trading_control(GT.ControlloModoOrdiniTennis)
    return q


def _ordine(q: Dict[str, Any], client: Any, context: Any = None) -> Any:
    # la capture VERA del runner (BaseStrategy di flumine), come per gli ordini a mano
    strat = TR._make_capture(MID, "*", market_ids=[MID])
    o = Trade(market_id=MID, selection_id=SEL, handicap=0.0, strategy=strat).create_order(
        side="BACK", order_type=LimitOrder(price=2.0, size=2.0))
    if context:
        o.context.update(context)
    return o


def test_terza_rete_ordine_reale_fermo_senza_ordini_reali_live(tetto_live):
    q = _q_con_terza_rete()
    MO.registra_settings(_riga("paper"))
    o = _ordine(q, q["client"])
    assert q["mercato"].place_order(o, client=q["client"]) is False
    assert q["pacchi"] == []
    assert "TENNIS_MODO_ORDINI" in str(o.violation_msg)


def test_terza_rete_ordine_reale_parte_con_ordini_reali_live(tetto_live):
    q = _q_con_terza_rete()
    MO.registra_settings(_riga("live"))
    o = _ordine(q, q["client"])
    assert q["mercato"].place_order(o, client=q["client"]) is True


def test_terza_rete_paper_mai_fermato_e_chiusura_reale_passa(tetto_live):
    q = _q_con_terza_rete()
    MO.registra_settings(_riga("paper"))
    o = _ordine(q, q["paper"])
    assert q["mercato"].place_order(o, client=q["paper"]) is True
    chiusura = _ordine(q, q["client"], context={"reduces_liability": True})
    assert q["mercato"].place_order(chiusura, client=q["client"]) is True


def test_terza_rete_tetto_riletto_paper_ferma_il_reale(monkeypatch):
    """Il client reale esiste (runner nato LIVE) ma il tetto riletto non e' LIVE:
    nessuna apertura reale (fail-closed), anche con «Ordini reali» LIVE."""
    q = _q_con_terza_rete()
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    MO.registra_settings(_riga("live"))
    o = _ordine(q, q["client"])
    assert q["mercato"].place_order(o, client=q["client"]) is False


def test_terza_rete_ferma_il_bot_live(tetto_live, bot_che_entra):
    """Bot armato in soldi veri (riga live, dry_run False) e poi «Ordini reali»
    riportato in prova: le sue aperture si fermano DENTRO flumine."""
    q = _q_con_terza_rete()
    MO.registra_settings(_riga("paper"))
    bot = _arma({"mode": "live", "dry_run": False}, "LIVE", paper=q["paper"])
    _gira(q, bot)
    assert bot._esito_place is False and q["pacchi"] == []
    MO.registra_settings(_riga("live"))
    _gira(q, bot)
    assert bot._esito_place is True and len(q["pacchi"]) == 1
    assert q["pacchi"][0].client is q["client"]


# --------------------------------------------------------------------------- canale (passo 6)
@pytest.fixture
def canale_tennis(monkeypatch):
    """``LocalChannel`` VERO del tennis (non avviato): ``publish`` registra."""
    from Betfair.stream import local_channel as LC

    ch = LC.LocalChannel(59996, "tennis")
    usciti = []
    monkeypatch.setattr(ch, "publish", lambda topic, msg: usciti.append((topic, dict(msg))))
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    GT._MODO_CANALE["firma"] = None
    yield {"ch": ch, "usciti": usciti}
    GT._MODO_CANALE["firma"] = None


def test_il_canale_tennis_dichiara_il_modo_del_tennis(tetto_live, canale_tennis):
    MO.registra_settings(_riga("live", boot="boot-di-ieri"))
    assert GT.pubblica_modo_ordini_se_cambiato() is True
    topic, msg = canale_tennis["usciti"][-1]
    assert topic == "modo_ordini"
    assert (msg["effettivo"], msg["tetto_ambiente"], msg["motivo"], msg["sport"]) == \
        ("PAPER", "LIVE", MO.MOTIVO_AVVIO_DIVERSO, "tennis")
    assert canale_tennis["ch"]._hello_extra["modo_ordini"]["effettivo"] == "PAPER"
    # nessun cambio: nessun messaggio
    assert GT.pubblica_modo_ordini_se_cambiato() is False
    # il gesto di oggi: esce LIVE
    MO.registra_settings(_riga("live"))
    assert GT.pubblica_modo_ordini_se_cambiato() is True
    assert canale_tennis["usciti"][-1][1]["effettivo"] == "LIVE"


def test_il_canale_tennis_non_dice_il_tetto_del_calcio(canale_tennis, monkeypatch):
    """Reperto 5 del delegato precedente: col tetto CALCIO LIVE e il tennis in
    PAPER il canale tennis non deve dire LIVE."""
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    MO.registra_settings(_riga("live"))
    GT.pubblica_modo_ordini_se_cambiato()
    msg = canale_tennis["usciti"][-1][1]
    assert (msg["effettivo"], msg["tetto_ambiente"]) == ("PAPER", "PAPER")
    # e la funzione del calcio resta muta sul 47332
    assert LOW._pubblica_modo_ordini_se_cambiato() is False


def test_la_rilettura_dei_settings_pubblica_il_modo(tetto_live, canale_tennis, monkeypatch):
    righe = iter([_riga("paper"), _riga("live")])

    class _Sb:
        def rpc(self, nome, _args):
            assert nome == "get_live_settings"
            return types.SimpleNamespace(execute=lambda: types.SimpleNamespace(data=next(righe)))
    GT.aggiorna_impostazioni(_Sb(), forza=True)
    GT.aggiorna_impostazioni(_Sb(), forza=True)
    effettivi = [m["effettivo"] for t, m in canale_tennis["usciti"] if t == "modo_ordini"]
    assert effettivi == ["PAPER", "LIVE"]


def test_il_runner_monta_la_terza_rete():
    """``setup_and_run`` monta i trading control con ``aggiungi_controlli_ordini``:
    la terza rete c'e' insieme alle due di prima."""
    nomi = []
    fw = types.SimpleNamespace(add_trading_control=lambda c, **k: nomi.append(c.NAME))
    TR.aggiungi_controlli_ordini(fw)
    assert nomi == ["TENNIS_MODALITA_BOT", "TENNIS_KILL_SWITCH", "TENNIS_MODO_ORDINI"]
    import inspect
    assert "aggiungi_controlli_ordini(framework)" in inspect.getsource(TR.setup_and_run)


def test_nessuna_lettura_db_in_piu(worker_finto, monkeypatch):
    """Il modo effettivo non legge niente: un giro del worker = le stesse letture
    di prima (la coda una volta al secondo, i settings dalla funzione di sempre)."""
    chiamate = {"settings": 0}
    monkeypatch.setattr(GT, "aggiorna_impostazioni",
                        lambda sb, forza=False: chiamate.__setitem__(
                            "settings", chiamate["settings"] + 1))
    MO.registra_settings(_riga("paper"))
    db = _DbCoda([_riga_coda(1, "place", mode="live", side="BACK", price=2.0, size=2.0)])
    monkeypatch.setattr(W, "tennis_db", db)
    W.tennis_live_order_worker({}, object(), types.SimpleNamespace())
    assert chiamate["settings"] == 1 and db.letture == 1
    assert LOW._SETTINGS is not None
