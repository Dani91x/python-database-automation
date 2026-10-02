"""02/10/2026 - Mike: PUNTO 25 (riga assente, mercato aperto) e REPERTO R1 (arresto).

PUNTO 25 (decisione dell'utente): quando lo scanner toglie la riga della partita
Mike annullava i suoi ordini vivi credendo il mercato finito (riga assente oltre
la grazia, o in gioco da KO + 100'). Ora prima di annullare rilegge lo stato del
mercato via REST (``market.read_book``, la lettura del regolamento): CLOSED ->
annulla e regola come prima; OPEN/SUSPENDED -> TIENE e lo scrive nel diario
(«riga assente, mercato aperto: tengo»); illeggibile -> i tetti di sempre. Al piu'
una lettura ogni ``_RIGA_ASSENTE_REST_S``.

REPERTO R1 (``AUDIT_2026-10-02/SCANNER_MAI_CIECO.md`` par. 9): all'arresto (stop
dall'app, segnale, eccezione) Mike annulla gli ordini vivi NON abbinati (tetto
10 s, ``_ARRESTO_TETTO_S``) con la via di sempre (``_mark_trade_cancelled``,
runner in paper, Betfair in live), dichiara le posizioni abbinate (diario +
CRITICAL «posizione lasciata a mercato per arresto»), poi esce.

Finti: ``FakeDB``/``FakeMarket`` di ``test_mike_service`` (le firme di
``mike/db.py`` e di ``read_book``), runner finto sul protocollo vero,
``CancelResult`` vero di ``omega_market``. ASCII-only.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_indagine_mercato_deciso_2026_09_29 import OU35, OU45
from Betfair.mike.tests.test_mike_ondata2_2026_09_30 import (_annulli_al_runner,
                                                             _copertura_in_volo, _gamba)
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, run, state
from Betfair.omega.omega_market import CancelResult


class MercatoContato(FakeMarket):
    """``FakeMarket`` (stessa firma di ``read_book``) che conta le letture REST."""

    def __init__(self) -> None:
        super().__init__()
        self.letture: List[str] = []

    def read_book(self, market_id, names):
        self.letture.append(str(market_id))
        return super().read_book(market_id, names)


def _stato(mk: FakeMarket, s35: str, s45: str) -> None:
    mk.books[OU35] = {"market_id": OU35, "status": s35, "inplay": True, "runners": []}
    mk.books[OU45] = {"market_id": OU45, "status": s45, "inplay": True, "runners": []}


def _riga_assente_oltre_la_grazia(db: FakeDB) -> None:
    db.events["E1"]["ctx"]["row_missing_since"] = NOW.timestamp() - S._ROW_MISSING_GRACE_S - 1


def _tengo(db: FakeDB) -> List[Dict[str, Any]]:
    return [p for k, p, _e in db.activity if k == "riga_assente_mercato_aperto"]


# ===========================================================================
# PUNTO 25
# ===========================================================================
@pytest.mark.parametrize("s35,s45", [("OPEN", "OPEN"), ("SUSPENDED", "SUSPENDED"),
                                     ("CLOSED", "OPEN")],
                         ids=["aperto", "sospeso", "3_5_chiuso_4_5_aperto"])
def test_25_riga_assente_mercato_aperto_tengo_gli_ordini(runner, s35, s45):
    """Il caso del punto 25: la riga sparisce, i tetti di sempre direbbero
    «partita finita», ma Betfair dice che il mercato e' aperto (o sospeso, o il
    3,5 deciso e il 4,5 vivo): nessun annullo, nessun regolamento, una riga di
    diario."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    _riga_assente_oltre_la_grazia(db)
    mk = MercatoContato()
    _stato(mk, s35, s45)
    run(db, mk, NOW, [])
    assert _annulli_al_runner(runner) == [], runner.comandi
    assert _gamba(db, "over_cover-0-7")["status"] == "pending"
    assert state(db) not in ("SETTLING", "SETTLED")
    [riga] = _tengo(db)
    assert riga["nota"] == "riga assente, mercato aperto: tengo"
    assert riga["ordini_vivi"] == ["over_cover-0-7"]
    assert sorted(mk.letture) == sorted([OU35, OU45])


def test_25_rilettura_col_suo_ritmo_e_alla_chiusura_si_annulla(runner):
    """Fra due letture passano almeno ``_RIGA_ASSENTE_REST_S`` (mai un poll
    stretto), il diario lo dice UNA volta; quando Betfair dice CLOSED gli ordini
    si annullano e la partita va al regolamento come prima."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    _riga_assente_oltre_la_grazia(db)
    mk = MercatoContato()
    _stato(mk, "OPEN", "OPEN")
    run(db, mk, NOW, [])
    for dt in (2, 10, 29):
        run(db, mk, NOW + timedelta(seconds=dt), [])
    assert len(mk.letture) == 2, mk.letture                # una sola rilettura (2 linee)
    assert len(_tengo(db)) == 1 and _annulli_al_runner(runner) == []
    _stato(mk, "CLOSED", "CLOSED")
    run(db, mk, NOW + timedelta(seconds=S._RIGA_ASSENTE_REST_S + 1), [])
    # 2 della rilettura del punto 25 + 2 del regolamento (lettura di sempre)
    assert len(mk.letture) == 6
    assert len(_annulli_al_runner(runner)) == 1
    assert _gamba(db, "over_cover-0-7")["status"] == "cancelled"
    assert state(db) == "SETTLING"


def test_25_rest_illeggibile_valgono_i_tetti_di_sempre(runner):
    """Betfair non risponde (nessun libro): si torna alla regola di prima, la
    riga assente oltre la grazia vale «partita chiusa» (annullo e regolamento)."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    _riga_assente_oltre_la_grazia(db)
    mk = MercatoContato()
    run(db, mk, NOW, [])
    assert len(mk.letture) == 4          # 2 della rilettura + 2 del regolamento
    assert len(_annulli_al_runner(runner)) == 1 and state(db) == "SETTLING"
    assert _tengo(db) == []


def test_25_dentro_la_grazia_nessuna_rilettura_e_nessun_annullo(runner):
    """Riga assente da poco: nessun tetto superato, nessuna lettura REST in piu'."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    db.events["E1"]["ctx"]["seen_inplay"] = False
    db.events["E1"]["ctx"]["row_missing_since"] = NOW.timestamp() - 30.0
    mk = MercatoContato()
    _stato(mk, "CLOSED", "CLOSED")
    run(db, mk, NOW, [])
    assert mk.letture == [] and _annulli_al_runner(runner) == []


def test_25_la_riga_torna_e_l_episodio_si_chiude():
    ctx = {"row_missing_since": 1.0, "riga_assente_tengo": 2.0, "riga_assente_rest_ts": 3.0,
           "riga_assente_rest_esito": S._REST_APERTO}
    # il giro di produzione: con la riga presente le chiavi dell'episodio cadono
    db = FakeDB(params={"stake": 10})
    from Betfair.mike.tests.test_mike_indagine_mercato_deciso_2026_09_29 import (
        _evento_coperto, _payload)
    from Betfair.mike.tests.test_mike_feed import row
    _evento_coperto(db)
    db.events["E1"]["ctx"].update(ctx)
    run(db, FakeMarket(), NOW, [row(_payload([]))])
    resto = db.events["E1"]["ctx"]
    assert not any(k in resto for k in ("row_missing_since", "riga_assente_tengo",
                                        "riga_assente_rest_ts", "riga_assente_rest_esito"))


# ===========================================================================
# REPERTO R1 - l'arresto
# ===========================================================================
def test_R1_arresto_annulla_gli_ordini_vivi_e_dichiara_le_posizioni(runner, caplog):
    db = FakeDB(params={"stake": 10})
    ref = _copertura_in_volo(db, runner)
    with caplog.at_level(logging.CRITICAL, logger="mike.service"):
        esito = S.arresto_con_ordini(motivo="stop dall'app", db=db, market=FakeMarket())
    [annullo] = _annulli_al_runner(runner)
    assert str(annullo["bet_id"]) == str(runner.ordine(ref)["bet_id"])
    assert [a["leg"] for a in esito["annullati"]] == ["over_cover-0-7"]
    assert _gamba(db, "over_cover-0-7")["status"] == "cancelled"
    # le gambe ABBINATE non si toccano: si dichiarano
    assert _gamba(db, "under_entry-0-1")["status"] == "open"
    [pos] = esito["posizioni"]
    assert pos["event_id"] == "E1" and pos["esposizioni"]
    [riga] = [p for k, p, _e in db.activity if k == "posizione_lasciata_per_arresto"]
    assert riga["critical"] is True and riga["motivo_arresto"] == "stop dall'app"
    assert any(r.levelno == logging.CRITICAL and "lasciata a mercato per arresto" in r.getMessage()
               for r in caplog.records)
    assert esito["non_annullati"] == []


def test_R1_oltre_il_tetto_nessun_altro_annullo_e_un_critical(runner, caplog):
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    tempi = iter([0.0, S._ARRESTO_TETTO_S + 0.5, S._ARRESTO_TETTO_S + 1.0])
    with caplog.at_level(logging.CRITICAL, logger="mike.service"):
        esito = S.arresto_con_ordini(motivo="segnale (SIGTERM)", db=db, market=FakeMarket(),
                                     orologio=lambda: next(tempi))
    assert _annulli_al_runner(runner) == []
    assert [x["leg"] for x in esito["non_annullati"]] == ["over_cover-0-7"]
    [riga] = [p for k, p, _e in db.activity if k == "arresto_ordini_non_annullati"]
    assert riga["critical"] is True and riga["tetto_s"] == S._ARRESTO_TETTO_S


def test_R1_live_stessa_via_con_betfair(monkeypatch):
    """LIVE: stessa funzione, l'annullo va a Betfair (``cancel_order_live``) e il
    suo esito confermato chiude la gamba."""
    from Betfair.mike.tests.test_mike_indagine_mercato_deciso_2026_09_29 import _evento_coperto
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    db.events["E1"]["mode"] = "live"
    db.events["E1"]["positions"].append(
        {"role": "over_cover", "market": "OU45", "selection": "UNDER", "side": "lay",
         "price": 4.9, "size": 3.0, "matched": 0.0, "avg_price": None, "ref": "over_cover-0-9",
         "status": "pending", "placed_at": 0.0, "persistence": "LAPSE", "cycle_no": 0,
         "final": False, "archived": False})
    db.trades.append({"id": 9, "event_id": "E1", "signal_key": "over_cover-0-9",
                      "status": "pending", "mode": "live", "bet_id": "B-9",
                      "market_id": OU45, "meta": {"leg_ref": "over_cover-0-9"}, "pnl": 0})
    chiamate: List[tuple] = []

    class MercatoLive(FakeMarket):
        def cancel_order_live(self, bet_id, market_id, size_reduction=None):
            chiamate.append((bet_id, market_id))
            return CancelResult(ok=True, status="SUCCESS", bet_id=str(bet_id),
                                size_cancelled=3.0, riletto=True, size_matched=0.0,
                                size_remaining=0.0)
    esito = S.arresto_con_ordini(motivo="eccezione RuntimeError: x", db=db, market=MercatoLive())
    assert chiamate == [("B-9", OU45)]
    assert [a["esito"] for a in esito["annullati"]] == ["cancelled"]


def test_R1_main_all_arresto_chiama_l_arresto_degli_ordini(monkeypatch):
    """Il servizio vero (``main``): un segnale (KeyboardInterrupt nel giro) e lo
    stop dall'app passano dall'arresto degli ordini, col loro motivo."""
    import copy

    chiamate: List[str] = []
    # ``main`` accende la guardia d'avvio del MODULO: copia, rimessa a posto a fine test
    monkeypatch.setattr(S, "_GUARDIA_AVVIO", copy.copy(S._GUARDIA_AVVIO))
    monkeypatch.setattr(S, "arresto_con_ordini", lambda *, motivo, **_k: chiamate.append(motivo))
    import Betfair.stream.single_instance as SI
    monkeypatch.setattr(SI, "acquire_single_instance_lock", lambda *a, **k: None)
    for nome in ("_avvia_canale", "_avvia_sveglia", "avvia_client_scan",
                 "avvia_conto_dal_canale", "ferma_al_nuovo_avvio", "_installa_segnali_di_arresto"):
        monkeypatch.setattr(S, nome, lambda *a, **k: None)
    from Betfair.omega import omega_market as OM
    monkeypatch.setattr(OM, "attiva_saldo_su_evento", lambda *a, **k: None)
    monkeypatch.setattr(S.D, "load_atlas", lambda *a, **k: {})
    monkeypatch.setattr("sys.argv", ["mike"])

    def giro_col_segnale(**_k):
        raise KeyboardInterrupt("segnale 15")
    monkeypatch.setattr(S, "run_once", giro_col_segnale)
    monkeypatch.setattr(S._AO, "richiesto", lambda *a, **k: False)
    S.main()
    assert chiamate == ["segnale (segnale 15)"]
    # stop dall'app: il guscio esce prima del giro
    monkeypatch.setattr(S._AO, "richiesto", lambda *a, **k: True)
    S.main()
    assert chiamate[-1] == "stop dall'app"
