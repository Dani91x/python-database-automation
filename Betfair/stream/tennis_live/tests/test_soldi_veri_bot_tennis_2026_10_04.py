# -*- coding: utf-8 -*-
"""«SOLDI VERI» SU OGNI BOT TENNIS (cantiere tetto tennis, passo 7, 04/10/2026).

Ordine dell'utente (testuale): «PER TUTTI I BOT QUEL PULSANTE DEVE FUNZIONARE:
QUANDO SCELGO SOLDI VERI DEVONO PARTIRE ORDINI VERI. PER TUTTI I BOT» e «SOLDI VERI
-> AVVIO IO -> BOT CHE SCELGO -> PARTONO GLI ORDINI. PAPER -> STESSA COSA MA SENZA
ORDINI VERI».

Prima: il ponte armava il live con ``dry_run=True`` (doppio gesto per partita): il
bot «acceso in soldi veri» non piazzava niente. Il runner tennis era forzato in
PAPER (``main.js``) e «Ordini reali» non contava.

Qui, per ciascuno dei 4 bot e per Safe tennis, con la catena del runner VERA:
riga per partita scritta dal ponte VERO (``tennis_bot_service._riga_armatura``),
bot istanziato da ``tennis_runner._instantiate_bot``, framework ``Flumine`` con i
client di ``build_order_client`` (reale + paper affiancato) e i trading control
del runner (``aggiungi_controlli_ordini``). ``process_order_package`` REGISTRA il
pacchetto col suo client: nessuna chiamata a Betfair. Il gesto d'ingresso dei bot
e' quello del modulo ``test_modalita_e_guardie_tennis_2026_09_24`` (gate su
``dry_run``, ``market.place_order(order)`` senza client, come i 4 bot).
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream import modo_ordini as MO
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_modalita_e_guardie_tennis_2026_09_24 import (  # noqa: F401
    EV,
    MID,
    _entra,
    _stato_pulito,
)
from Betfair.stream.tennis_live.tests.test_modalita_e_guardie_tennis_2026_09_24 import (
    _quadro as _quadro_base,
)

BOOT = "boot-di-oggi"
BOT = sorted(TR._BOT_REGISTRY)


def _riga_settings(modo: str) -> Dict[str, Any]:
    return {"id": 1, "kill_switch": False, "order_mode": modo, "order_mode_boot_id": BOOT,
            "order_mode_updated_at": None, "order_mode_updated_by": None}


@pytest.fixture(autouse=True)
def _catena(monkeypatch):
    MO.azzera()
    monkeypatch.setenv("APP_BOOT_ID", BOOT)
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    for cls, _kw, _n in TR._BOT_REGISTRY.values():
        monkeypatch.setattr(cls, "process_market_book", _entra)
    yield
    MO.azzera()


def _quadro() -> Dict[str, Any]:
    """Il framework del runner LIVE con i trading control del runner VERO."""
    q = _quadro_base("LIVE")
    q["fw"].trading_controls = []
    TR.aggiungi_controlli_ordini(q["fw"])
    return q


def _bot_dal_ponte(q: Dict[str, Any], bot_key: str, modo: str) -> Any:
    """La riga per partita come la scrive il PONTE dall'interruttore del bot,
    poi il bot come lo istanzia il runner."""
    d = {"mode": modo, "stake": 2, "uscite_automatiche": None}
    riga = S._riga_armatura(EV, bot_key, d, {})
    riga.update({"status": "running", "stats": None})
    df = None
    from betfairlightweight.filters import streaming_market_data_filter
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    return TR._instantiate_bot(bot_key, riga, MID, {"A": 1, "B": 2}, lambda *a, **k: None,
                               df, "LIVE", market_ids=[MID], client_paper=q["paper"])


@pytest.mark.parametrize("bot_key", BOT)
def test_soldi_veri_con_ordini_reali_live_partono_ordini_reali(bot_key):
    q = _quadro()
    MO.registra_settings(_riga_settings("live"))
    bot = _bot_dal_ponte(q, bot_key, "live")
    assert bot.dry_run is False and bot._tennis_modalita_esecuzione == "LIVE"
    bot.process_market_book(q["mercato"], q["mercato"].market_book)
    assert bot._esito_place is True
    assert len(q["pacchi"]) == 1 and q["pacchi"][0].client is q["client"]   # REALE


@pytest.mark.parametrize("bot_key", BOT)
def test_soldi_veri_con_ordini_reali_in_prova_nessun_ordine_reale(bot_key):
    q = _quadro()
    MO.registra_settings(_riga_settings("paper"))
    bot = _bot_dal_ponte(q, bot_key, "live")
    bot.process_market_book(q["mercato"], q["mercato"].market_book)
    assert bot._esito_place is False and q["pacchi"] == []
    assert "TENNIS_MODO_ORDINI" in str(bot._ordine.violation_msg)


@pytest.mark.parametrize("bot_key", BOT)
@pytest.mark.parametrize("ordini_reali", ["paper", "live"])
def test_prova_resta_prova_stessa_cosa_senza_ordini_veri(bot_key, ordini_reali):
    q = _quadro()
    MO.registra_settings(_riga_settings(ordini_reali))
    bot = _bot_dal_ponte(q, bot_key, "paper")
    assert bot.dry_run is False and bot._tennis_modalita_esecuzione == "PAPER"
    bot.process_market_book(q["mercato"], q["mercato"].market_book)
    assert bot._esito_place is True
    assert len(q["pacchi"]) == 1 and GT.is_client_paper(q["pacchi"][0].client)


@pytest.mark.parametrize("bot_key", BOT)
def test_all_avvio_dell_app_tutto_in_prova(bot_key, monkeypatch):
    """«Ordini reali» LIVE di ieri (boot diverso): il bot live di una riga
    rimasta (che il ponte comunque ferma all'avvio) non apre in reale."""
    q = _quadro()
    MO.registra_settings({**_riga_settings("live"), "order_mode_boot_id": "boot-di-ieri"})
    bot = _bot_dal_ponte(q, bot_key, "live")
    bot.process_market_book(q["mercato"], q["mercato"].market_book)
    assert bot._esito_place is False and q["pacchi"] == []


# --------------------------------------------------------------------------- Safe tennis
from Betfair.stream.tennis_live.tests.test_motore_ordini_tennis_2026_09_25 import (  # noqa: E402,F401
    Motore,
    _latenza_flumine_rimessa,
    ambiente,
)
from Betfair.stream.tennis_live.tests.test_paper_live_separati_tennis_2026_10_04 import (  # noqa: E402
    _runner_live,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: E402,F401
    banchi,
    db,
)


@pytest.fixture
def spia_reale(monkeypatch):
    """Il ``place_order`` del Market: il client REALE non arriva mai a Betfair (si
    registra e si dice «preso»), il paper fa il suo corso vero."""
    visti: List[Dict[str, Any]] = []

    def _installa(b: Any) -> List[Dict[str, Any]]:
        Mercato = type(b.fw.markets.markets["1.101"])
        vero = Mercato.place_order

        def _spia(self, order, *a, **k):
            cl = k.get("client")
            visti.append({"client": cl, "strategia": order.trade.strategy})
            if cl is b.client:
                return True
            return vero(self, order, *a, **k)
        monkeypatch.setattr(Mercato, "place_order", _spia)
        return visti
    return _installa


def test_safe_tennis_soldi_veri_parte_con_ordini_reali_live(db, banchi, ambiente, spia_reale,
                                                            monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    b = _runner_live(db, banchi)
    visti = spia_reale(b)
    m = Motore(b, ambiente)
    MO.registra_settings(_riga_settings("live"))
    c = m.manda(mode="live", side="BACK", price=2.0, size=2.0, time_in_force="FILL_OR_KILL")
    assert m.ack(c["ref"])["accettato"] is True
    assert visti and visti[-1]["client"] is b.client                     # REALE
    assert visti[-1]["strategia"] is b.session.capture_ordini["live"]     # mai sommato al paper
    assert visti[-1]["strategia"] is not b.cap                            # non la capture paper
    assert visti[-1]["strategia"].name == TR.NOME_CAPTURE_LIVE


def test_safe_tennis_soldi_veri_rifiutato_con_ordini_reali_in_prova(db, banchi, ambiente,
                                                                    spia_reale, monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    b = _runner_live(db, banchi)
    visti = spia_reale(b)
    m = Motore(b, ambiente)
    MO.registra_settings(_riga_settings("paper"))
    c = m.manda(mode="live", side="BACK", price=2.0, size=2.0, time_in_force="FILL_OR_KILL")
    ack = m.ack(c["ref"])
    assert ack["accettato"] is False and "Ordini reali" in str(ack["motivo"])
    assert visti == []
    # la prova di Safe tennis nello stesso momento parte (client paper)
    p = m.manda(mode="paper", side="BACK", price=2.0, size=2.0, time_in_force="FILL_OR_KILL")
    assert m.ack(p["ref"])["accettato"] is True
    assert visti and GT.is_client_paper(visti[-1]["client"])
    assert visti[-1]["strategia"] is b.session.capture_ordini["paper"]
