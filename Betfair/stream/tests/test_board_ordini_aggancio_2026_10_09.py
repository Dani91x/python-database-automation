"""09/10/2026 - PROGRAMMA DEL GIORNO, contratto par. 4: gli ordini dal tabellone.

Il box quota del tabellone usa il ``/order`` di sempre (canale 47331/47332 col
token). Un ``place`` su una partita NON ancora seguita dal runner prima era
rifiutato "market ... non sottoscritto nel runner" (calcio e tennis), e a runner
PARCHEGGIATO restava senza risposta. Cosa certifica, con le classi VERE:

CALCIO (``MotoreOrdini._servi_order`` + ``AutoFollow`` vero):
  * place su mercato non seguito -> aggancio al volo (stesso ``richiedi`` dei
    comandi dei bot, stessa connessione, stesso tetto), richiesta in ATTESA,
    piazzata al primo book NUOVO, risposta ``ok`` al desktop;
  * tetto pieno -> rifiuto SUBITO ``tetto_mercati_pieno`` col motivo;
  * attesa oltre ``aggancio_order_max_ms`` -> rifiuto ``in_aggancio``, e il
    mercato arrivato DOPO non piazza niente (la pagina ha gia' smesso di
    aspettare: l'attesa resta sotto i 10 s di ``LOCAL_REQUEST_TIMEOUT_MS``);
  * runner senza framework -> l'aggancio fa partire il runner, poi si piazza;
  * FIFO per mercato, guardia d'avvio rifatta all'uscita dall'attesa, cancel
    mai agganciato, senza auto-follow tutto come prima;
  * runner parcheggiato SENZA motore: ogni comando riceve subito il rifiuto.
TENNIS (``tennis_live_order_worker`` + ``AgganciaTennis`` vero, framework e
stream VERI del banco dell'iscrizione a caldo):
  * place su partita non seguita -> aggancio a caldo sulla STESSA connessione,
    piazzato al primo book nuovo; senza aggancio il rifiuto di sempre;
  * runner parcheggiato: snapshot vuoto, place con aggancio -> attesa (il runner
    parte con la partita), senza aggancio / guardia / OFF -> rifiuto dichiarato,
    scadenza -> rifiuto ``in_aggancio``.

Finti: quelli dei test del motore (``test_motore_ordini_2026_09_24``: canale VERO
con le risposte registrate, flumine con clients veri) e del banco tennis
(``test_tennis_iscrizione_a_caldo_2026_09_25``). Nessuna rete, nessun DB.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import local_channel as LC
from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.test_auto_follow_2026_09_25 import (
    _BlotterConOrdini, _auto, _monta, _nuovo_mercato)
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _STRAT_LIVE, _STRAT_PAPER, amb)

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _req(msg_id: Any, **p: Any) -> LC.LocalRequest:
    """La richiesta del box quota del tabellone (``localOrderApi`` -> ``order``)."""
    base = {"action": "place", "mode": "paper", "client_ref": f"cr-{msg_id}",
            "market_id": "1.555", "selection_id": 47972, "side": "BACK", "price": 2.5,
            "size": 3.0, "persistence": "LAPSE", "order_type": "LIMIT", "handicap": 0}
    base.update(p)
    return LC.LocalRequest(ws=None, msg_id=msg_id, method="order", params=base)


def _manda(amb: Any, *reqs: LC.LocalRequest) -> None:
    for r in reqs:
        amb.ch._requests.put_nowait(r)
    amb.motore.drena()


def _risposte(amb: Any) -> Dict[Any, Tuple[bool, Any, Optional[str]]]:
    return {m: (ok, d, e) for m, ok, d, e in amb.ch.risposte}


# ===========================================================================
# CALCIO
# ===========================================================================
def test_place_su_mercato_non_seguito_aggancia_e_piazza(amb):
    auto = _auto()
    _monta(amb, auto)
    _manda(amb, _req(1))
    # prima del 09/10: risposta immediata ok=False "non sottoscritto nel runner"
    assert amb.ch.risposte == [], amb.ch.risposte
    assert "1.555" in auto.piano.mercati()
    auto.giro()
    assert auto.sottoscrittore.chiamate[-1] == ["1.234", "1.555"]     # STESSA connessione
    assert amb.motore.avanza_aggancio() == 0 and amb.ch.risposte == []  # book non arrivato
    m = _nuovo_mercato(amb, "1.555")
    assert amb.motore.avanza_aggancio() == 1
    ok, d, e = _risposte(amb)[1]
    assert ok is True and e is None and d["ok"] is True and d["market_id"] == "1.555"
    assert len(m.calls) == 1 and m.calls[0][2] is amb.paper           # client della modalita'
    assert m.calls[0][0].trade.strategy is _STRAT_PAPER
    assert not amb.motore._order_in_aggancio


def test_mercato_gia_servibile_nessuna_attesa(amb):
    auto = _auto()
    _monta(amb, auto)
    _manda(amb, _req(1, market_id="1.234"))
    assert _risposte(amb)[1][0] is True and len(amb.market.calls) == 1
    assert not amb.motore._order_in_aggancio


def test_tetto_pieno_rifiuto_subito_col_motivo(amb):
    auto = _auto(tetto=2)
    _monta(amb, auto)                                          # 1.234 a mano
    m_pos = _nuovo_mercato(amb, "1.600")
    auto.piano.richiedi("E-pos", {"1.600"}, priorita=0, protetti=set(),
                        puo_espellere=False, ora=1.0)
    m_pos.blotter = _BlotterConOrdini(1)                       # con ordini: mai espulso
    _manda(amb, _req(1, market_id="1.601"))
    ok, _d, e = _risposte(amb)[1]
    assert ok is False and e.startswith(MO.M_TETTO) and "NON piazzato" in e
    assert auto.piano.mercati() == {"1.234", "1.600"}
    assert not amb.motore._order_in_aggancio and amb.paper.eseguiti == []


def test_scadenza_rifiuto_in_aggancio_e_mai_un_ordine_dopo(amb, monkeypatch):
    auto = _auto()
    _monta(amb, auto)
    ora = [int(time.time() * 1000)]
    monkeypatch.setattr(amb.motore, "_ora_ms", lambda: ora[0])
    _manda(amb, _req(1))
    auto.giro()
    ora[0] += amb.motore.aggancio_order_max_ms - 10
    assert amb.motore.avanza_aggancio() == 0 and amb.ch.risposte == []
    ora[0] += 20
    assert amb.motore.avanza_aggancio() == 1
    ok, _d, e = _risposte(amb)[1]
    assert ok is False and e.startswith(MO.M_IN_AGGANCIO) and "NON piazzato" in e
    m = _nuovo_mercato(amb, "1.555")                           # arriva DOPO: niente
    assert amb.motore.avanza_aggancio() == 0
    assert m.calls == [] and amb.paper.eseguiti == [] and amb.reale.eseguiti == []


def test_runner_senza_framework_l_aggancio_lo_fa_partire(amb):
    auto = _auto()
    _monta(amb, auto)
    amb.motore.sgancia()
    _manda(amb, _req(1))
    # prima: "runner senza framework attivo ... NON eseguito" subito
    assert amb.ch.risposte == [] and "1.555" in auto.piano.mercati()
    assert auto.mercati_da_sottoscrivere() and "1.555" in auto.mercati_da_sottoscrivere()
    # il runner parte (setup_and_run: framework nuovo + motore riagganciato)
    amb.motore.aggancia(amb.fl, {"live": _STRAT_LIVE, "paper": _STRAT_PAPER})
    auto.giro()
    m = _nuovo_mercato(amb, "1.555")
    assert amb.motore.avanza_aggancio() == 1
    assert _risposte(amb)[1][0] is True and len(m.calls) == 1


def test_fifo_per_mercato_e_ordini_paper_live_separati(amb):
    auto = _auto()
    _monta(amb, auto)
    _manda(amb, _req(1, price=2.5), _req(2, price=2.6, mode="live"))
    auto.giro()
    m = _nuovo_mercato(amb, "1.555")
    # arrivato quando il mercato e' gia' servibile ma i primi sono in fila: in fila
    _manda(amb, _req(3, price=2.7))
    assert 3 not in _risposte(amb) and len(amb.motore._order_in_aggancio) == 3
    assert amb.motore.avanza_aggancio() == 3
    assert [c[0].order_type.price for c in m.calls] == [2.5, 2.6, 2.7]
    assert [c[2] for c in m.calls] == [amb.paper, amb.reale, amb.paper]
    assert all(_risposte(amb)[i][0] is True for i in (1, 2, 3))


def test_guardia_d_avvio_rifatta_all_uscita_dall_attesa(amb):
    auto = _auto()
    _monta(amb, auto)
    _manda(amb, _req(1))
    auto.giro()
    amb.guardia["armata"] = True                               # ripresa riarmata nel frattempo
    m = _nuovo_mercato(amb, "1.555")
    assert amb.motore.avanza_aggancio() == 1
    assert _risposte(amb)[1] == (False, None, amb.motore._motivo_guardia_order)
    assert m.calls == []


def test_errore_nel_giro_non_tocca_le_richieste_in_attesa(amb, monkeypatch):
    """Un errore servendo le richieste PRONTE non deve dare "NON eseguito" a
    quella parcheggiata nello stesso giro (partirebbe poi, a rifiuto gia' letto)."""
    auto = _auto()
    _monta(amb, auto)

    def _rotto(_reqs):
        raise RuntimeError("guasto")
    monkeypatch.setattr(amb.motore, "_servi_order_pronti", _rotto)
    _manda(amb, _req(1), _req(2, market_id="1.234"))
    r = _risposte(amb)
    assert 1 not in r and 1 in [o["req"].msg_id for o in amb.motore._order_in_aggancio.values()]
    assert r[2][0] is False and "guasto" in r[2][2]


def test_cancel_mai_agganciato_e_senza_auto_follow_come_prima(amb):
    auto = _auto()
    _monta(amb, auto)
    _manda(amb, _req(1, action="cancel", bet_id="B-X", market_id="1.888"))
    assert 1 in _risposte(amb) and "1.888" not in auto.piano.mercati()
    amb.motore._aggancio = None
    _manda(amb, _req(2, market_id="1.777"))
    ok, _d, e = _risposte(amb)[2]
    assert ok is False and "non sottoscritto" in e               # il rifiuto di sempre


def test_attesa_sempre_sotto_il_timeout_della_pagina(amb, monkeypatch):
    with open(os.path.join(_RADICE, "frontend", "src", "lib", "localChannel.ts"),
              encoding="utf-8") as fh:
        m = re.search(r"LOCAL_REQUEST_TIMEOUT_MS\s*=\s*([\d_]+)", fh.read())
    assert m, "costante del frontend non trovata"
    timeout_pagina = int(m.group(1).replace("_", ""))
    assert MO.AGGANCIO_ORDER_MAX_MS_TETTO <= timeout_pagina - 2000
    assert amb.motore.aggancio_order_max_ms == MO.AGGANCIO_ORDER_MAX_MS_DEFAULT
    monkeypatch.setenv("MOTORE_AGGANCIO_ORDER_MAX_MS", "60000")
    mo = MO.MotoreOrdini("calcio", canale=amb.ch, diario=amb.diario, scrittore=amb.scrittore)
    assert mo.aggancio_order_max_ms == MO.AGGANCIO_ORDER_MAX_MS_TETTO


def test_runner_parcheggiato_senza_motore_risponde_subito(monkeypatch, amb):
    from Betfair.stream import runner as R

    for i in (1, 2):
        amb.ch._requests.put_nowait(_req(i))
    amb.ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=3, method="snapshot",
                                                params={"market_id": "1.555"}))
    # col motore acceso NON si tocca la coda: la serve lui (con l'aggancio)
    monkeypatch.setattr(R, "_MOTORE", {"motore": amb.motore, "api": None, "auto": None})
    monkeypatch.setattr(R, "_board_da_parcheggiato", lambda *a, **k: False)
    R._attesa_board_e_canale(object())
    assert amb.ch._requests.qsize() == 3 and amb.ch.risposte == []
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    R._attesa_board_e_canale(object())
    assert amb.ch._requests.qsize() == 0
    assert amb.ch.risposte == [(i, False, None, R._MOTIVO_PARCHEGGIATO_SENZA_MOTORE)
                               for i in (1, 2, 3)]


# ===========================================================================
# TENNIS
# ===========================================================================
from Betfair.stream.tennis_live import esecutore_tennis as ET  # noqa: E402
from Betfair.stream.tennis_live import guardie_tennis as GT  # noqa: E402
from Betfair.stream.tennis_live import tennis_live_order_worker as TW  # noqa: E402
from Betfair.stream.tennis_live import tennis_runner as TR  # noqa: E402
from Betfair.stream.tennis_live.tests.test_motore_ordini_tennis_2026_09_25 import (  # noqa: E402,F401
    _DbTennisNullo, _latenza_flumine_rimessa, ambiente)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: E402,F401
    _banco, _follow, _meta, banchi, db)


class _CanaleT(LC.LocalChannel):
    def __init__(self) -> None:
        super().__init__(59983, "tennis", token="t" * 64)
        self.risposte: List[Tuple[Any, bool, Any, Optional[str]]] = []

    def respond(self, req: Any, ok: bool, data: Any = None,  # type: ignore[override]
                error: Optional[str] = None) -> None:
        self.risposte.append((req.msg_id, ok, data, error))

    def per_id(self) -> Dict[Any, Tuple[bool, Any, Optional[str]]]:
        return {m: (ok, d, e) for m, ok, d, e in self.risposte}


@pytest.fixture
def canale_t(monkeypatch):
    ch = _CanaleT()
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    monkeypatch.setattr(TW, "_LOCAL_IN_AGGANCIO", type(TW._LOCAL_IN_AGGANCIO)())
    monkeypatch.setattr(TW, "_LOCAL_SEEN", {})
    return ch


def _req_t(msg_id: Any, ev: str = "303", **p: Any) -> LC.LocalRequest:
    base = {"action": "place", "mode": "paper", "client_ref": f"crt-{msg_id}",
            "market_id": f"1.{ev}", "selection_id": 11, "side": "BACK", "price": 2.0,
            "size": 2.0, "persistence": "LAPSE", "order_type": "LIMIT"}
    base.update(p)
    return LC.LocalRequest(ws=None, msg_id=msg_id, method="order", params=base)


def _aggancio_del_runner(b: Any) -> Any:
    """L'``AgganciaTennis`` come lo monta ``_monta_motore_tennis``: catalogo
    risolto, allineamento a caldo VERO sulla connessione del banco."""
    ag = ET.AgganciaTennis(
        b.session, risolvi=lambda mid: _meta(mid.split(".", 1)[1]),
        allinea=lambda: TR._allinea_follow_a_caldo(
            b.fw, b.session, b.session.caldo,
            ET.follows_con_comandi(b.session, b.session.ultimi_follows)))
    ag.aggancia(b.fw)
    b.session.aggancio_desktop = ag
    return ag


def test_tennis_place_su_partita_non_seguita_aggancia_a_caldo_e_piazza(
        db, banchi, ambiente, canale_t):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    b.session.ultimi_follows = list(db.list_pending_tennis_follows())
    ag = _aggancio_del_runner(b)
    canale_t._requests.put_nowait(_req_t(1))
    TW._process_local_requests(b.fw, b.session, "paper")
    # prima del 09/10: ok=False "market 1.303 non sottoscritto nel runner tennis"
    assert canale_t.risposte == [], canale_t.risposte
    assert "1.303" in ag.richieste
    assert ag.giro() is True                                  # catalogo + allineamento
    assert b.mercati_sottoscritti() == ["1.101", "1.303"]     # STESSA connessione
    assert TW._avanza_locali_in_aggancio(b.fw, b.session, "paper") == 0
    b.book("303")                                             # primo book NUOVO
    assert TW._avanza_locali_in_aggancio(b.fw, b.session, "paper") == 1
    ok, d, e = canale_t.per_id()[1]
    assert ok is True and e is None and d["ok"] is True
    ordini = list(b.fw.markets.markets["1.303"].blotter)
    assert len(ordini) == 1 and ordini[0].order_type.price == 2.0
    assert ordini[0].client.paper_trade is True


def test_tennis_senza_aggancio_il_rifiuto_di_sempre(db, banchi, ambiente, canale_t):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    canale_t._requests.put_nowait(_req_t(1))
    TW._process_local_requests(b.fw, b.session, "paper")
    ok, _d, e = canale_t.per_id()[1]
    assert ok is False and "non sottoscritto" in e


def test_tennis_parcheggiato_risponde_sempre(monkeypatch, canale_t):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    monkeypatch.delenv("LIVE_KILL_SWITCH", raising=False)
    monkeypatch.setattr(LOW, "_SETTINGS_TS", time.monotonic())
    GT.azzera_per_i_test()
    sess = TR.TennisLiveSession(trading=None)
    # senza aggancio (motore tennis spento): rifiuto dichiarato; snapshot vuoto
    canale_t._requests.put_nowait(_req_t(1))
    canale_t._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=2, method="snapshot",
                                                  params={"market_id": "1.303"}))
    assert TW.servi_comandi_da_parcheggiato(sess) == 2
    r = canale_t.per_id()
    assert r[1][0] is False and "parcheggiato" in r[1][2] and "spento" in r[1][2]
    assert r[2] == (True, {"orders": [], "positions": []}, None)
    # con l'aggancio: il place lo CHIEDE (il runner partira' con la partita) e aspetta
    allineati: List[Any] = []
    ag = ET.AgganciaTennis(sess, risolvi=lambda mid: _meta("303"),
                           allinea=lambda: allineati.append(1))
    sess.aggancio_desktop = ag
    canale_t._requests.put_nowait(_req_t(3))
    canale_t._requests.put_nowait(_req_t(4, action="cancel", bet_id="9"))
    canale_t._requests.put_nowait(_req_t(5, mode="live"))     # runner PAPER: mai live
    TW.servi_comandi_da_parcheggiato(sess)
    r = canale_t.per_id()
    assert 3 not in r and "1.303" in ag.richieste
    assert r[4][0] is False and "parcheggiato" in r[4][2]
    assert r[5][0] is False and "non servibile" in r[5][2]
    ag.giro()
    assert "303" in sess.comandi                              # entra nella prossima build
    assert [f["event_id"] for f in ET.follows_con_comandi(sess, [])] == ["303"]
    # scaduta l'attesa (framework mai nato): rifiuto in_aggancio, mai in silenzio
    for o in TW._LOCAL_IN_AGGANCIO.values():
        o["scadenza_ms"] = 0
    TW.servi_comandi_da_parcheggiato(sess)
    ok, _d, e = canale_t.per_id()[3]
    assert ok is False and e.startswith(MO.M_IN_AGGANCIO)
    assert not TW._LOCAL_IN_AGGANCIO


def test_tennis_parcheggiato_guardia_e_off(monkeypatch, canale_t):
    monkeypatch.setattr(LOW, "_SETTINGS_TS", time.monotonic())
    GT.azzera_per_i_test()
    sess = TR.TennisLiveSession(trading=None)
    sess.aggancio_desktop = ET.AgganciaTennis(sess, risolvi=lambda m: None,
                                              allinea=lambda: None)
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "OFF")
    canale_t._requests.put_nowait(_req_t(1))
    TW.servi_comandi_da_parcheggiato(sess)
    assert canale_t.per_id()[1] == (False, None, "modalita' ordini OFF: comando NON eseguito")
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    monkeypatch.setattr(GT, "guardia_blocca", lambda: True)
    canale_t._requests.put_nowait(_req_t(2))
    TW.servi_comandi_da_parcheggiato(sess)
    assert canale_t.per_id()[2] == (False, None, GT.MOTIVO_GUARDIA_LOCALE)
    assert not sess.aggancio_desktop.richieste                # nessun aggancio chiesto
    GT.azzera_per_i_test()
