"""04/10/2026 - SAFE e OMEGA: la PUNTA da 1,00 in su parte SOLO a multiplo di 0,50, per
DIFETTO, su OGNI strada (canale, coda, REST diretta), e il residuo non piazzabile si
DICHIARA una volta e non si ritenta (decisioni dell'utente, testuali: "SOTTO 1 EURO si usa
place and trim (0.50 il minimo), SOPRA 1 EURO i MULTIPLI DI 0.50 FUNZIONANO, IN BACK";
"IL RESIDUO RESTA RICORDATO E LO CHIUDO IO").

Il difetto: sulla strada REST (``omega_market.place_order_live``) una chiusura in punta
da 2,39 partiva com'era, Betfair la rifiutava ``INVALID_BET_SIZE`` e la posizione
restava scoperta (stesso difetto di Mike a Umea, punta 7,27).

Finti: Betfair a livello di RETE (``tradotti_comuni.monta_rete``: ``OM.call`` /
``OM.call_mutating`` con i dizionari grezzi di ``PlaceExecutionReport``), funzioni VERE
di ``omega_market``, ``execution``, ``bot_service``, ``omega_service``; DB storico di Safe
(``test_bot_service.FakeDB`` col runner paper finto). Nessun ordine vero. ASCII-only.
"""
from __future__ import annotations

from typing import Any

import pytest

from Betfair import order_exec as OE
from Betfair.omega import omega_market as OM
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.safe_strategy.tests.test_bot_service import FakeDB
from Betfair.stream.tests.tradotti_comuni import MID, NOW, OVER, UNDER, monta_rete

#: le chiavi della dichiarazione del motore del canale (``motore_ordini._applica_minimi``)
CHIAVI_PUNTA_050 = {"chiesto", "piazzato", "residuo", "motivo"}


def _db(mode: str = "live", *, rest: bool = True) -> FakeDB:
    db = FakeDB(status="stopped", mode=mode)
    db.heartbeat = {"ts": NOW.isoformat(), "mode": "LIVE" if mode == "live" else "PAPER"}
    if rest:
        db.follow = "NONE"                   # gate della coda chiuso: si va in REST
    return db


def _apertura_lay(db: FakeDB, *, size: float = 2.0, price: float = 11.0,
                  mode: str = "live") -> dict:
    """Banca Over 2,00 @11: la chiusura in punta a 9,2 e' 2 x 11 / 9,2 = 2,39."""
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "selection_name": "Over 2.5 Goals",
                           "market_type": "OVER_UNDER_25", "side": "lay", "mode": mode,
                           "origin": "auto", "status": "open", "price": price,
                           "size": size, "liability": X.liability_of("lay", size, price),
                           "pnl": 0.0, "commission": 0.05, "bet_id": "APERTURA1",
                           "strategy": "base", "meta": {}})
    return db.get_trade(tid)


PREZZI = {"back": 9.2, "back_size": 500.0, "lay": 9.4, "lay_size": 500.0}


def _chiudi(db: FakeDB, parent: dict, *, mode: str = "live", porta: Any = None) -> dict:
    return X.close_trade(db=db, market=S._MercatoSafe(OM), trade=parent, prices=dict(PREZZI),
                         mode=mode, now=NOW, params={}, origin="auto", table_prefix="safe",
                         **({"porta": porta} if porta is not None else {}))


def _critici_residuo(db: FakeDB) -> list:
    return [p for k, p in db.activity
            if k == "place_parziale" and p.get("reason") == X.ERR_RESIDUO]


# ---------------------------------------------------------------------------
# 1. REST diretta: omega_market.place_order_live
# ---------------------------------------------------------------------------
def test_rest_punta_239_parte_200_col_residuo_dichiarato(monkeypatch):
    rete = monta_rete(monkeypatch)
    res = OM.place_order_live(market_id=MID, selection_id=OVER, price=9.2, size=2.39,
                              event_id="E1", side="back", customer_ref="safe-t9")
    assert len(rete.piazzati) == 1
    _mid, ins, _kw = rete.piazzati[0]
    assert (ins["side"], ins["limitOrder"]["size"]) == ("BACK", 2.0)
    assert res.ok is True and res.size_matched == 2.0
    # ``size_requested`` = l'importo MANDATO (come la riga di coda e canale)
    assert res.size_requested == 2.0
    assert set(res.punta_050) == CHIAVI_PUNTA_050
    assert (res.punta_050["chiesto"], res.punta_050["piazzato"],
            res.punta_050["residuo"]) == (2.39, 2.0, 0.39)


@pytest.mark.parametrize("lato,importo,mandato,residuo", [
    ("back", 7.27, 7.0, 0.27),       # Umea v Hammarby, 04/10
    ("back", 1.49, 1.0, 0.49),
    ("back", 2.50, 2.5, None),       # gia' multipla: nessuna dichiarazione
    ("back", 1.00, 1.0, None),
    ("lay", 2.39, 2.39, None),       # banca al centesimo, invariata
])
def test_rest_tabella_della_regola(monkeypatch, lato, importo, mandato, residuo):
    rete = monta_rete(monkeypatch)
    res = OM.place_order_live(market_id=MID, selection_id=OVER, price=3.0, size=importo,
                              event_id="E1", side=lato, customer_ref="safe-t9")
    assert rete.piazzati[0][1]["limitOrder"]["size"] == mandato
    if residuo is None:
        assert res.punta_050 is None
    else:
        assert res.punta_050["residuo"] == residuo and res.punta_050["piazzato"] == mandato


def test_rest_place_submin_sopra_il_minimo_passa_dalla_stessa_regola(monkeypatch):
    rete = monta_rete(monkeypatch)
    res = OM.place_submin_live(market_id=MID, selection_id=OVER, price=9.2, size=2.39,
                               event_id="E1", side="back", customer_ref="safe-t9")
    assert rete.piazzati[0][1]["limitOrder"]["size"] == 2.0
    assert res.punta_050["residuo"] == 0.39


# ---------------------------------------------------------------------------
# 2. Safe: la chiusura REST (il 16esimo rosso del cantiere dei minimi)
# ---------------------------------------------------------------------------
def test_safe_chiusura_rest_239_parte_200_e_il_residuo_e_ricordato_una_volta(monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db("live")
    parent = _apertura_lay(db)
    out = _chiudi(db, parent)
    assert out.get("ok") is True, out
    assert len(rete.piazzati) == 1
    assert rete.piazzati[0][1]["limitOrder"]["size"] == 2.0
    gamba = db.get_trade(out["closing_trade_id"])
    assert gamba["status"] == "open" and gamba["size"] == 2.0
    assert gamba["meta"]["punta_050"]["residuo"] == 0.39
    assert out["punta_050"]["chiesto"] == 2.39
    # il residuo e' RICORDATO sull'apertura e DICHIARATO una volta con la proposta
    apri = db.get_trade(parent["id"])
    assert apri["status"] == "open", "0,39 restano scoperti: mai dichiarata coperta"
    assert X.residuo_ricordato(apri)
    assert apri["meta"][X.RESIDUO_KEY]["size"] == 0.39
    crit = _critici_residuo(db)
    assert len(crit) == 1 and crit[0]["critical"] is True
    assert "chiudi tu il residuo" in crit[0]["proposta"]
    # un secondo tentativo: nessun ordine, nessuna riga, nessun secondo CRITICAL
    righe = len(db.trades)
    out2 = _chiudi(db, db.get_trade(parent["id"]))
    assert out2["error"] == X.ERR_RESIDUO
    assert len(rete.piazzati) == 1 and len(db.trades) == righe
    assert len(_critici_residuo(db)) == 1


def test_safe_residuo_di_chiusura_mai_ritentato_a_ogni_giro(monkeypatch):
    """Il resto (0,39 punta) di una chiusura gia' abbinata, scoperto al giro dopo: la
    pre-verifica di ``close_trade`` non riserva nessuna riga e non manda nulla; il
    CRITICAL e' UNO anche dopo 10 giri (prima: ``_rifiuto_sotto_050`` a ogni giro)."""
    rete = monta_rete(monkeypatch)
    db = _db("live")
    parent = _apertura_lay(db)
    # chiusura gia' abbinata per 2,00 a 9,2 (scritta come la scrive close_trade)
    db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                     "side": "back", "mode": "live", "origin": "auto", "status": "open",
                     "price": 9.2, "size": 2.0, "liability": 2.0, "pnl": 0.0,
                     "closes_trade_id": parent["id"],
                     "meta": {"cashout": True, "closes_trade_id": parent["id"]}})
    righe = len(db.trades)
    for _ in range(10):
        out = _chiudi(db, db.get_trade(parent["id"]))
        assert out["error"] == X.ERR_RESIDUO
    assert rete.piazzati == [] and len(db.trades) == righe
    assert len(_critici_residuo(db)) == 1
    assert [k for k, p in db.activity if k == "place_rifiutato"] == []
    assert X.residuo_ricordato(db.get_trade(parent["id"]))


def test_safe_prima_chiusura_sotto_050_resta_com_era(monkeypatch):
    """Perimetro: la PRIMA chiusura di una posizione (nessuna gamba abbinata) sotto 0,50
    non passa dalla pre-verifica: resta il rifiuto certo di sempre."""
    monta_rete(monkeypatch)
    db = _db("live")
    parent = _apertura_lay(db, size=0.30, price=11.0)          # chiusura 0,36
    out = _chiudi(db, parent)
    assert out["error"] == "chiusura_non_eseguita"
    assert not X.residuo_ricordato(db.get_trade(parent["id"]))


# ---------------------------------------------------------------------------
# 3. le altre due strade: coda e canale, stesso importo e stessa dichiarazione
# ---------------------------------------------------------------------------
def test_safe_coda_manda_200_e_l_esito_dichiara_il_residuo(monkeypatch):
    monta_rete(monkeypatch)
    db = _db("live", rest=False)
    db.follow = "STREAMING"
    out = X.place(db=db, market=S._MercatoSafe(OM), mode="live", event_id="E1",
                  market_id=MID, selection_id=OVER, side="back", price=9.2, size=2.39,
                  client_ref="safe-t5", trade_id=5,
                  meta={"cashout": True, "closes_trade_id": 1}, now=NOW, params={})
    assert out.status == "pending", out.fill_note
    assert db.queue and float(db.queue[-1]["size"]) == 2.0
    assert out.punta_050["residuo"] == 0.39 and set(out.punta_050) == CHIAVI_PUNTA_050


class _PortaFinta:
    """Porta a comandi di Safe: ``invia`` registra il comando VERO
    (``porta_ordini.costruisci_comando``) e risponde con un ``Ack`` vero accettato."""

    via_canale = True
    attore = "safe"
    submin_fill_or_kill = False

    def __init__(self) -> None:
        self.comandi: list = []

    def disponibile(self) -> bool:
        return True

    def invia(self, comando: Any) -> SPO.Ack:
        self.comandi.append(comando)
        return SPO.Ack(str(comando.get("ref")), 1, True, None, 1.0)


def test_safe_canale_manda_200_e_l_esito_dichiara_il_residuo(monkeypatch):
    monta_rete(monkeypatch)
    db = _db("live", rest=False)
    porta = _PortaFinta()
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "back", "mode": "live", "status": "pending",
                           "price": 9.2, "size": 2.39, "meta": {}})
    out = X.place(db=db, market=S._MercatoSafe(OM), mode="live", event_id="E1",
                  market_id=MID, selection_id=OVER, side="back", price=9.2, size=2.39,
                  client_ref="safe-t%d" % tid, trade_id=tid,
                  meta={"cashout": True, "closes_trade_id": 1}, now=NOW, params={},
                  porta=porta)
    assert out.status == "pending", out.fill_note
    assert len(porta.comandi) == 1 and float(porta.comandi[0]["size"]) == 2.0
    assert out.punta_050["residuo"] == 0.39
    # la riga lo dice dal primo istante (write-ahead del canale)
    assert db.get_trade(tid)["meta"]["punta_050"]["piazzato"] == 2.0


# ---------------------------------------------------------------------------
# 4. la macchina delle uscite di Safe e di Omega salta il residuo ricordato
# ---------------------------------------------------------------------------
def test_safe_exit_candidates_saltano_il_residuo_ricordato():
    base = {"status": "open", "origin": "auto", "strategy": "base", "event_id": "E1"}
    libero = {**base, "id": 1, "meta": {}}
    ricordato = {**base, "id": 2, "meta": {X.RESIDUO_KEY: {"size": 0.39}}}
    ids = [t["id"] for t in S._exit_candidates([libero, ricordato])]
    assert ids == [1]


def test_omega_greenup_candidates_saltano_il_residuo_ricordato():
    from Betfair.omega import omega_service as OS

    class _Db:
        def open_trades(self):
            return [{"id": 1, "status": "open", "side": "lay", "origin": "auto",
                     "event_id": "E1", "meta": {}},
                    {"id": 2, "status": "open", "side": "lay", "origin": "auto",
                     "event_id": "E1", "meta": {X.RESIDUO_KEY: {"size": 0.39}}}]

        def log(self, *a, **k):
            pass

    assert [t["id"] for t in OS._greenup_candidates(_Db())] == [1]


# ---------------------------------------------------------------------------
# 5. terminale manuale: l'importo dell'utente NON si cambia, si rifiuta prima
# ---------------------------------------------------------------------------
class _Arrivato(Exception):
    pass


def _ferma_dopo_i_controlli(monkeypatch):
    def _stop(*a, **k):
        raise _Arrivato()
    monkeypatch.setattr(OE, "_resolve_target", _stop)
    monkeypatch.setattr(OE, "_call", _stop)


def test_terminale_punta_727_rifiutata_prima_dell_invio_coi_due_importi(monkeypatch):
    _ferma_dopo_i_controlli(monkeypatch)
    with pytest.raises(ValueError) as e:
        OE.place_order(1, "btts", "Yes", "back", 3.0, size=7.27, sb=object())
    assert str(e.value) == "7,27: la punta va a multipli di 0,50, usa 7,00 o 7,50."


@pytest.mark.parametrize("lato,importo", [("back", 7.5), ("back", 1.0), ("lay", 7.27)])
def test_terminale_importi_validi_passano_i_controlli(monkeypatch, lato, importo):
    _ferma_dopo_i_controlli(monkeypatch)
    with pytest.raises(_Arrivato):
        OE.place_order(1, "btts", "Yes", lato, 3.0, size=importo, sb=object())


def test_safe_combo_con_punta_a_multiplo_lo_dice_forte_una_volta(monkeypatch):
    """Combo approvata (``_esegui_combo_riservata``): una gamba in punta 2,39 parte 2,00
    (``X.place`` VERO sulla coda del runner finto). Il profitto bloccato della combo non e'
    piu' quello proposto: UN CRITICAL con le gambe arrotondate; gli importi della
    strategia NON si ricalcolano (la gamba in banca resta quella proposta)."""
    db = _db("paper", rest=False)
    db.follow = "STREAMING"
    legs = [{"market_id": MID, "market_type": "OVER_UNDER_25", "selection_id": OVER,
             "selection_name": "Over 2.5 Goals", "side": "back", "price": 2.1, "size": 2.39,
             "liability": 2.39},
            {"market_id": MID, "market_type": "OVER_UNDER_25", "selection_id": UNDER,
             "selection_name": "Under 2.5 Goals", "side": "lay", "price": 2.0, "size": 2.43,
             "liability": 2.43}]
    out = S._esegui_combo_riservata(db=db, market=S._MercatoSafe(OM), event_id="E1",
                                    event_name="Nord v Sud", cid="c1", legs_esecuzione=legs,
                                    sport="calcio", mode="paper", commission=0.05,
                                    minute=60, score="1-0", rationale="test",
                                    params=S.resolve_params({}), now=NOW,
                                    rows_by_event=None, risk_ctx=None)
    assert out["total"] == 2
    mandati = [(q["side"], float(q["size"])) for q in db.queue]
    assert ("back", 2.0) in mandati and ("lay", 2.43) in mandati
    crit = [p for k, p in db.activity
            if k == "place_parziale" and p.get("reason") == "combo_punta_050"]
    assert len(crit) == 1 and crit[0]["critical"] is True
    assert crit[0]["gambe"][0]["punta_050"]["residuo"] == 0.39


# ---------------------------------------------------------------------------
# 6. i due bot, giro VERO: il residuo si dichiara una volta e non si ritenta
# ---------------------------------------------------------------------------
def test_safe_bot_uscita_con_residuo_un_avviso_e_nessun_ritento():
    """Safe base: banca 10@8,5, chiusura integrale a 9,0 = 9,44 -> parte 9,00 (paper, sul
    runner finto). Al giro dopo il resto (0,44 punta) non ha via: UN CRITICAL con la
    proposta, stato d'uscita 'failed' col codice, nessuna riga nuova nei giri seguenti."""
    from datetime import timedelta

    from Betfair.safe_strategy.tests.test_bot_service import NOW as NOW_S
    from Betfair.safe_strategy.tests.test_bot_service import (
        _auto_trade,
        _cycle,
        _exit_feed_row,
    )

    NOW = NOW_S  # noqa: N806 - l'orologio del finto di Safe

    db = FakeDB(status="running")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    t_goal = NOW + timedelta(seconds=2)
    _cycle(db, _exit_feed_row(66, 2, 0, updated_at=t_goal), at=t_goal)
    t_ok = t_goal + timedelta(seconds=31)
    _cycle(db, _exit_feed_row(66, 2, 0, updated_at=t_ok), at=t_ok)
    gambe = [t for t in db.trades if t.get("closes_trade_id") == tid]
    assert len(gambe) == 1 and gambe[0]["size"] == 9.0
    assert gambe[0]["meta"]["punta_050"]["residuo"] == 0.44
    for s in range(1, 8):
        at = t_ok + timedelta(seconds=30 * s)
        _cycle(db, _exit_feed_row(67, 2, 0, updated_at=at), at=at)
    gambe = [t for t in db.trades if t.get("closes_trade_id") == tid]
    assert len(gambe) == 1, "nessun ritento del residuo, nessuna riga 'error' per giro"
    apri = db.get_trade(tid)
    assert apri["status"] == "open" and X.residuo_ricordato(apri)
    assert apri["meta"]["exit"]["last_error"] == X.ERR_RESIDUO
    assert apri["meta"]["exit"]["state"] == "failed"
    assert apri["meta"]["exit"].get("next_retry_at") is None
    # nessun "ritento" dichiarato: il residuo non e' un fallimento da ritentare
    assert [p for k, p in db.activity
            if k in ("exit_retry", "exit_failed") and p.get("err") == X.ERR_RESIDUO] == []
    assert apri["meta"]["exit_requested"].get("residual_attempts", 0) == 0
    assert len(_critici_residuo(db)) == 1
    assert [p for k, p in db.activity if k == "place_rifiutato"] == []

