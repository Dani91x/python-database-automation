"""02/10/2026 - R1: ARRESTO ORDINATO di Safe e Omega («niente resta in coda»).

All'arresto (stop dall'app, segnale, eccezione fatale): annullo dei SOLI propri ordini vivi
non abbinati (righe ``pending`` col bet_id) con la via della riga (canale, coda paper,
REST per bet_id solo live), tetto 10 s; posizioni abbinate MAI chiuse ma dichiarate con UN
CRITICAL «posizione lasciata a mercato per arresto»; stato nel diario; poi l'uscita.
``desktop/main.js`` concede a Safe e Omega almeno il tempo massimo dell'arresto + 10 s.

Finti: DB storici di Safe (``test_bot_service.FakeDB`` col runner paper finto) e di Omega,
``CancelResult`` vero di ``omega_market``. Nessuna rete. ASCII-only.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import pytest

from Betfair.omega import omega_market as OM
from Betfair.safe_strategy import arresto_bot as AB
from Betfair.safe_strategy.tests.test_bot_service import FakeDB

NOW = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


class _Mercato:
    """Solo l'annullo per bet_id (la firma vera di ``omega_market.cancel_order_live``);
    qualunque altra chiamata (annulli di mercato, place) fa fallire il test."""

    def __init__(self, residuo: float = 0.0) -> None:
        self.annulli: list = []
        self.residuo = residuo

    def cancel_order_live(self, bet_id: str, market_id: str, size_reduction: Any = None):
        self.annulli.append((bet_id, market_id, size_reduction))
        return OM.CancelResult(ok=self.residuo <= 0, status="SUCCESS", bet_id=bet_id,
                               size_cancelled=2.0, riletto=True, size_matched=0.0,
                               size_remaining=self.residuo)

    def __getattr__(self, nome: str) -> Any:
        raise AssertionError(f"chiamata vietata all'arresto: {nome}")


def _riga(db: FakeDB, **kw: Any) -> dict:
    base = {"event_id": "E1", "market_id": "1.5", "selection_id": 7, "side": "lay",
            "mode": "live", "origin": "manual", "status": "pending", "price": 3.0,
            "size": 2.0, "meta": {}}
    base.update(kw)
    return db.get_trade(db.insert_trade(base))


def _chiudi(db: FakeDB, mercato: Any, *, porta_kw=lambda tr: {}, ora=None, causa="stop_app"):
    return AB.chiudi_bot_all_arresto(bot="safe", db=db, market=mercato, causa=causa,
                                     porta_kw_di=porta_kw, ora=ora or (lambda: 0.0),
                                     adesso=lambda: NOW)


def _arresti(db: FakeDB) -> list:
    return [p for k, p in db.activity if k == "arresto"]


def test_annulla_solo_i_propri_bet_id_live_e_dichiara_le_posizioni():
    db = FakeDB(mode="live")
    viva = _riga(db, bet_id="B1")
    _riga(db, bet_id=None)                                  # mai piazzata: nessun bet_id
    aperta = _riga(db, status="open", bet_id="B2", size=5.0)
    m = _Mercato()
    esito = _chiudi(db, m)
    assert m.annulli == [("B1", "1.5", None)]               # solo il suo bet_id
    assert [v["esito"] for v in esito["annulli"]] == ["annullato", "senza_bet_id"]
    assert [p["trade_id"] for p in esito["posizioni"]] == [aperta["id"]]
    # la posizione NON si tocca
    assert db.get_trade(aperta["id"])["status"] == "open"
    assert db.get_trade(viva["id"])["status"] == "pending"   # la riconciliazione la chiude dopo
    log = _arresti(db)
    assert len(log) == 1 and log[0]["critical"] is True
    assert AB.CRITICO_POSIZIONE in log[0]["nota"]


def test_arresto_pulito_nessun_critical():
    db = FakeDB(mode="live")
    _riga(db, bet_id="B1")
    esito = _chiudi(db, _Mercato())
    assert esito["critical"] is False and _arresti(db)[0]["critical"] is False


def test_ordine_ancora_vivo_dopo_l_annullo_e_critical():
    db = FakeDB(mode="live")
    _riga(db, bet_id="B1")
    esito = _chiudi(db, _Mercato(residuo=1.0))
    assert esito["annulli"][0]["esito"] == "vivo" and esito["critical"] is True


def test_paper_senza_runner_mai_un_rest_sul_conto_vero():
    db = FakeDB(mode="paper")
    _riga(db, mode="paper", bet_id="SIM1")
    esito = _chiudi(db, _Mercato())                         # qualunque chiamata = rosso
    assert esito["annulli"][0]["esito"] == "nessun_ordine"


def test_paper_in_coda_annullo_accodato_al_runner():
    db = FakeDB(mode="paper")
    tr = _riga(db, mode="paper", bet_id="SIM1",
               meta={"flumine_request_id": 3, "flumine_client_ref": "safe-t1"})
    esito = _chiudi(db, _Mercato())
    assert esito["annulli"][0]["esito"] == "accodato"
    assert db.queue[-1]["action"] == "cancel" and db.queue[-1]["bet_id"] == "SIM1"
    assert db.queue[-1]["client_ref"] == "safe-t1-cancel"
    assert tr["id"]


def test_canale_paper_e_live_passano_dalla_porta():
    visti = []

    class _Porta:
        via_canale = True

    def _annulla(market, *, bet_id, market_id, size_reduction=None, porta=None, mode=None):
        visti.append((market, bet_id, mode, porta is not None))
        return OM.CancelResult(ok=True, status="EXECUTION_COMPLETE", bet_id=bet_id,
                               size_cancelled=2.0, riletto=True, size_remaining=0.0)

    from Betfair.safe_strategy import execution as X

    orig = X.annulla_su_betfair
    X.annulla_su_betfair = _annulla
    try:
        for mode in ("paper", "live"):
            db = FakeDB(mode=mode)
            _riga(db, mode=mode, bet_id="C1", meta={"canale_ref": "safe-t1"})
            _chiudi(db, _Mercato(), porta_kw=lambda tr: {"porta": _Porta(),
                                                         "mode": tr["mode"]})
    finally:
        X.annulla_su_betfair = orig
    # paper: mai il mercato REST (None); live: il mercato c'e' per il ripiego del canale
    assert visti[0][0] is None and visti[0][1:] == ("C1", "paper", True)
    assert visti[1][1:] == ("C1", "live", True) and visti[1][0] is not None


def test_tetto_di_10_secondi_le_righe_oltre_si_dichiarano():
    db = FakeDB(mode="live")
    for i in range(3):
        _riga(db, bet_id=f"B{i}")
    t = {"v": 0.0}

    def ora():
        t["v"] += 6.0                                       # ogni annullo costa 6 s
        return t["v"]

    m = _Mercato()
    esito = _chiudi(db, m, ora=ora)
    assert len(m.annulli) < 3 and esito["non_tentati"]
    assert esito["critical"] is True
    assert AB.ARRESTO_ANNULLO_TIMEOUT_S == 10.0


@pytest.mark.parametrize("comportamento,causa", [
    ("stop", AB.CAUSA_STOP_APP), ("ctrl_c", AB.CAUSA_SEGNALE), ("fatale", AB.CAUSA_ERRORE_FATALE),
])
def test_ogni_uscita_passa_dall_arresto_ordinato(comportamento, causa):
    visti = []

    def ciclo():
        if comportamento == "ctrl_c":
            raise KeyboardInterrupt()
        if comportamento == "fatale":
            raise RuntimeError("bug")

    if comportamento == "fatale":
        with pytest.raises(RuntimeError):
            AB.esegui_ciclo_con_arresto(ciclo, visti.append, stop_app=lambda: False)
    else:
        AB.esegui_ciclo_con_arresto(ciclo, visti.append,
                                    stop_app=lambda: comportamento == "stop")
    assert visti == [causa]


def test_i_segnali_diventano_keyboardinterrupt():
    import signal

    prima = {n: signal.getsignal(getattr(signal, n)) for n in ("SIGTERM", "SIGBREAK")
             if hasattr(signal, n)}
    try:
        fatti = AB.installa_segnali()
        assert "SIGTERM" in fatti
        with pytest.raises(KeyboardInterrupt):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    finally:
        for n, h in prima.items():
            signal.signal(getattr(signal, n), h)


def test_la_dormita_si_accorge_dell_arresto():
    dormite = []
    stop = {"si": False}
    assert AB.dormi_finche_arresto(5.5, richiesto=lambda: stop["si"],
                                   dormi=dormite.append) is False
    assert sum(dormite) == pytest.approx(5.5) and max(dormite) <= 1.0
    dormite.clear()

    def dormi_e_ferma(s):
        dormite.append(s)
        stop["si"] = True

    assert AB.dormi_finche_arresto(60.0, richiesto=lambda: stop["si"],
                                   dormi=dormi_e_ferma) is True
    assert sum(dormite) <= 1.0


# ---------------------------------------------------------------------------
# collegamento nei due servizi e in main.js
# ---------------------------------------------------------------------------
def test_main_di_safe_e_omega_passano_dall_arresto_ordinato():
    """Il ``main`` di entrambi i servizi esegue il ciclo dentro
    ``esegui_ciclo_con_arresto`` con la chiusura del proprio bot, e installa i segnali."""
    import inspect

    from Betfair.omega import omega_service as OS
    from Betfair.safe_strategy import bot_service as BS

    for mod, nome in ((BS, "safe"), (OS, "omega")):
        src = inspect.getsource(mod.main)
        assert "esegui_ciclo_con_arresto" in src, nome
        assert "installa_segnali()" in src, nome
        assert callable(getattr(mod, "_chiudi_all_arresto", None)), nome


@pytest.mark.parametrize("modulo", ["safe", "omega"])
def test_chiusura_del_servizio_usa_db_mercato_e_porta_veri(monkeypatch, modulo):
    from Betfair.omega import omega_service as OS
    from Betfair.safe_strategy import bot_service as BS

    mod = BS if modulo == "safe" else OS
    visti = {}
    monkeypatch.setattr(AB, "chiudi_bot_all_arresto", lambda **kw: visti.update(kw) or {})
    mod._chiudi_all_arresto("segnale")
    assert visti["bot"] == modulo and visti["causa"] == "segnale"
    assert visti["db"] is mod._real_db and visti["market"] is mod._real_market
    assert visti["porta_kw_di"] is mod._porta_kw_annullo


def test_omega_la_dormita_del_ciclo_si_accorge_dell_arresto(monkeypatch):
    from Betfair.omega import omega_service as OS

    monkeypatch.setattr(OS, "_ASCOLTO_SCAN", None)
    monkeypatch.setattr(OS, "_sveglia_dal_client_scan", lambda: False)
    monkeypatch.setattr(OS._AO, "richiesto", lambda *a, **k: True)
    dormite = []
    monkeypatch.setattr(OS.time, "sleep", lambda s: dormite.append(s))
    OS._dormi_o_sveglia(60, {})
    assert sum(dormite) <= 1.0


@pytest.mark.parametrize("label", ["omega-service", "safe-strategy-bot"])
def test_main_js_concede_a_safe_e_omega_il_tempo_dell_arresto(label):
    radice = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    with open(os.path.join(radice, "desktop", "main.js"), encoding="utf-8") as f:
        js = f.read()
    corpo = js[js.index("function shutdownGraceMs(label)"):]
    corpo = corpo[:corpo.index("\n}\n")]
    m = re.search(r"'" + re.escape(label) + r"'[^\n]*?return ([0-9_]+);", corpo) or \
        re.search(r"\n    return ([0-9_]+);", corpo)
    grazia_s = int(m.group(1).replace("_", "")) / 1000.0
    assert grazia_s >= AB.TEMPO_MASSIMO_ARRESTO_S + 10.0, (label, grazia_s)
