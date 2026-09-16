# -*- coding: utf-8 -*-
"""«SE CHIUDO IO, IL BOT DEVE SAPERLO» — ordine dell'utente del 16/09/2026 sera.

Quattro cose, e ognuna e' costata un reperto misurato:
  1. CASH-OUT GLOBALE di partita: il bot lo capisce e NON FA ALTRO (T14 era
     violato x282 su 35797769: dopo il cash-out del trader il servizio ha
     aggiunto una gamba automatica da 0,04 EUR e ha continuato le uscite);
  2. `cashout` per singola riga: la riga diventa ORFANA, niente gambe figlie;
  3. CHIUSURA FUORI DALL'APP (lay dell'utente direttamente su Betfair): la si
     scopre leggendo la POSIZIONE DI CONTO sul mercato, senza filtro di
     strategia — e l'utente puo' avere ANCHE altre operazioni sue sulla stessa
     selezione, che non vanno ne' scambiate per le nostre ne' ignorate;
  4. i CAP del bot contano solo il BOT (32,80 EUR di responsabilita' manuale
     stavano dentro i cap).

I finti qui parlano la lingua del vero: gli ordini hanno le chiavi che
`omega_market._riga_corrente`/`_riga_regolata` producono (snake_case,
`customer_order_ref`, `size_matched`, `bet_outcome`, `profit`), non una grafia
inventata — e' il difetto 27 del catalogo, e il 15/09 e' costato 32 ordini veri.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.safe_strategy import bot_db as DB
from Betfair.safe_strategy import bot_service as S

from test_bot_service import (NOW, FakeDB, FakeEngine, FakeMarket, _feed_row,
                              _signal)

PIU_TARDI = NOW.replace(minute=30)


@pytest.fixture(autouse=True)
def _indice_pulito():
    """L'indice degli eventi chiusi e' una CACHE di processo: ogni test parte
    da zero, come un servizio appena avviato."""
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()
    yield
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()


# ---------------------------------------------------------------------------
# aiutanti: righe vere della tabella, ordini veri del conto
# ---------------------------------------------------------------------------
def _riga(db: FakeDB, **kw) -> dict:
    riga = {"event_id": "1.1", "event_name": "Home v Away", "sport": "calcio",
            "strategy": "esatto", "market_id": "1.1", "market_type": "MATCH_ODDS",
            "selection_id": 7, "selection_name": "Home",
            "side": "lay", "mode": "live", "price": 32.0, "size": 2.0,
            "liability": 62.0, "commission": 0.05, "status": "open", "pnl": 0.0,
            "origin": "auto", "signal_key": "1.1:esatto:home:1-1",
            "meta": {}, "placed_at": NOW.isoformat()}
    riga.update(kw)
    tid = db.insert_trade(riga)
    return db.get_trade(tid)


def _ordine(ref: str, side: str, size: float, *, market_id: str = "1.1",
            selection_id: int = 7, **kw) -> dict:
    """UN ordine come lo normalizza `omega_market`: stesse chiavi, nessuna in piu'."""
    o = {"bet_id": f"b-{ref}", "market_id": market_id, "selection_id": selection_id,
         "side": side, "status": "EXECUTION_COMPLETE", "size_matched": size,
         "size_remaining": 0.0, "avg_price_matched": 32.0,
         "customer_order_ref": ref}
    o.update(kw)
    return o


class MercatoConConto(FakeMarket):
    """Un mercato che espone la POSIZIONE DI CONTO come il banco comune
    (`MercatoFlumine.list_account_orders` / `list_account_cleared_orders`) e
    come la produzione (`omega_market.list_current_orders_account` /
    `list_cleared_orders_account`)."""

    def __init__(self, vivi=None, regolati=None):
        super().__init__()
        self.vivi = list(vivi or [])
        self.regolati = list(regolati or [])
        self.letture: list[str] = []
        self.annullati: list[str] = []

    def list_account_orders(self, market_id):
        self.letture.append(str(market_id))
        return [o for o in self.vivi if str(o["market_id"]) == str(market_id)]

    def list_account_cleared_orders(self, market_id):
        return [o for o in self.regolati if str(o["market_id"]) == str(market_id)]

    def cancel_order_live(self, bet_id, market_id, size_reduction=None):
        self.annullati.append(str(bet_id))
        return {"ok": True}

    def order_state_by_bet_id(self, bet_id):
        return {"found": True, "size_matched": 0.0, "size_remaining": 0.0,
                "avg_price_matched": None}


# ===========================================================================
# 1. CASH-OUT GLOBALE DI PARTITA
# ===========================================================================
def test_cashout_event_chiude_tutte_le_righe_e_scrive_il_marcatore():
    db = FakeDB(mode="live")
    a = _riga(db)
    b = _riga(db, signal_key="1.1:esatto:away:1-1", selection_name="Away")
    mercato = MercatoConConto()
    mercato.book = {"status": "OPEN", "runners": {}}
    res = S._request_cashout_event(
        db=db, market=mercato, rows_by_event={"1.1": _feed_row()},
        payload={"event_id": "1.1"}, params={}, now=NOW)
    assert res.get("ok") is True
    assert res.get("chiuso_dall_utente") is True
    # CHIUSE DAVVERO, non solo dichiarate: due gambe di chiusura a mercato con
    # `exit_kind='manual'`, e le due aperture passate a 'hedged'
    assert res["chiuse"] == [a["id"], b["id"]] and res["non_chiuse"] == []
    figlie = [t for t in db.trades if t.get("closes_trade_id")]
    assert {t["closes_trade_id"] for t in figlie} == {a["id"], b["id"]}
    assert all(t["origin"] == "manual" for t in figlie)
    # il marcatore c'e' sulle righe (nel `meta`, cioe' sopravvive al riavvio)
    for riga in (db.get_trade(a["id"]), db.get_trade(b["id"])):
        mk = S.marcatore_utente(riga)
        assert mk is not None and mk["come"] == "cashout_event"
    # ...e sull'indice di partita, con un'attivita' leggibile dal trader
    assert S.evento_chiuso_dall_utente("1.1") is not None
    assert "chiuso_dall_utente" in db.kinds()


def test_dopo_il_cashout_globale_nessuna_apertura_nuova():
    """T14, primo corno: «non apre»."""
    db = FakeDB(mode="live")
    _riga(db)
    S.segna_chiuso_dall_utente(db, event_id="1.1", righe=db.trades,
                              come="cashout_event", now=NOW)
    riga = {"event_id": "1.1", "market_id": "1.1", "selection_id": 7,
            "side": "lay", "mode": "live", "price": 32.0, "size": 2.0,
            "origin": "auto"}
    out = S._execute(db=db, market=MercatoConConto(), trade_id=99, row=riga,
                     params={}, now=PIU_TARDI, best_size=100.0, ladder=((32.0, 100.0),))
    assert out.status == "error"
    assert out.fill_note == "partita_chiusa_dall_utente"


def test_nessuna_RISERVA_nuova_dal_ciclo_vero():
    """Il controllo sta PRIMA della riserva, e lo si prova dal ciclo intero
    (`run_once` -> `scan_and_place`): non deve nascere nemmeno la riga
    'pending', che occupa l'idempotenza del segnale e conta nell'esposizione."""
    db = FakeDB(mode="live")
    db.scan_rows = [_feed_row()]
    riga = _riga(db)
    S.segna_chiuso_dall_utente(db, event_id="1.1", righe=db.trades,
                               come="cashout_event", now=NOW)
    prima = len(db.trades)
    res = S.run_once(db=db, market=MercatoConConto(), engine=FakeEngine([_signal()]),
                     now=PIU_TARDI)
    assert res["placed"] == 0
    assert len(db.trades) == prima, "non deve nascere nemmeno una riserva"
    motivi = [p.get("reason") for k, p in db.activity if k == "skip"]
    assert "partita_chiusa_dall_utente" in motivi


def test_dopo_il_cashout_globale_nessuna_uscita_automatica():
    """T14, secondo corno: «non esce». Erano 282 `exit_hold` su 35797769."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    assert S._exit_candidates([riga]) == [riga]        # prima: e' un candidato
    S.segna_chiuso_dall_utente(db, event_id="1.1", righe=db.trades,
                               come="cashout_event", now=NOW)
    assert S._exit_candidates([db.get_trade(riga["id"])]) == []


def test_il_manuale_dell_utente_passa_lo_stesso():
    """Il freno e' sul BOT, non sul trader: le SUE operazioni restano libere."""
    db = FakeDB(mode="live")
    _riga(db)
    S.segna_chiuso_dall_utente(db, event_id="1.1", righe=db.trades,
                               come="cashout_event", now=NOW)
    riga = {"event_id": "1.1", "market_id": "1.1", "selection_id": 7,
            "side": "lay", "mode": "live", "price": 32.0, "size": 2.0,
            "origin": "manual"}
    out = S._execute(db=db, market=MercatoConConto(), trade_id=99, row=riga,
                     params={}, now=PIU_TARDI, best_size=100.0, ladder=((32.0, 100.0),))
    assert out.fill_note != "partita_chiusa_dall_utente"


def test_le_gambe_di_COMBO_non_si_chiudono_su_una_partita_gia_chiusa():
    """`X.close_trade` piazza per conto suo e NON passa da `_execute`: la
    guardia va ripetuta dove nasce la gamba, cioe' qui. Altrimenti una combo
    rotta continuerebbe a svolgersi su posizioni che non esistono piu'."""
    db = FakeDB(mode="live")
    gamba = _riga(db, strategy="model")
    prezzi = {int(gamba["id"]): {"back": 32.0, "back_size": 500.0,
                                 "lay": 34.0, "lay_size": 500.0}}
    S.segna_chiuso_dall_utente(db, event_id="1.1", righe=db.trades,
                               come="cashout_event", now=NOW)
    prima = len(db.trades)
    n = S._close_combo_siblings(db=db, market=MercatoConConto(), legs=[gamba],
                                prices_by_id=prezzi, params={}, now=PIU_TARDI,
                                reason="combo rotta")
    assert n == 0
    assert len(db.trades) == prima, "nessuna gamba figlia"
    motivi = [p.get("reason") for k, p in db.activity if k == "skip"]
    assert "partita_chiusa_dall_utente" in motivi


def test_riprendi_e_l_unico_modo_di_riaccendere():
    db = FakeDB(mode="live")
    _riga(db)
    S.segna_chiuso_dall_utente(db, event_id="1.1", righe=db.trades,
                               come="cashout_event", now=NOW)
    res = S._request_riprendi_evento(db=db, payload={"event_id": "1.1"}, now=PIU_TARDI)
    assert res["ok"] is True and res["righe_ripulite"] == 1
    assert S.evento_chiuso_dall_utente("1.1") is None
    assert S.marcatore_utente(db.trades[0]) is None
    # e su una partita mai chiusa il «Riprendi» si rifiuta, non finge
    assert S._request_riprendi_evento(db=db, payload={"event_id": "1.9"},
                                      now=PIU_TARDI).get("rejected")


def test_la_riserva_in_volo_si_annulla_su_betfair_e_si_rilegge():
    """Il cancel e' quello VERO (`execution.annulla_su_betfair`), e l'esito si
    RILEGGE: mai «annullato» per fiducia."""
    db = FakeDB(mode="live")
    riserva = _riga(db, status="pending", bet_id="bf-1")
    mercato = MercatoConConto()
    esito = S._annulla_riserva(db, market=mercato, trade=riserva, now=NOW)
    assert esito["ok"] is True
    assert mercato.annullati == ["bf-1"]
    assert "cancel_richiesto" in db.kinds() and "cancel_esito" in db.kinds()


def test_cancel_a_esito_ignoto_non_dichiara_annullato():
    class SenzaRilettura(MercatoConConto):
        def order_state_by_bet_id(self, bet_id):
            return {"found": False}

    db = FakeDB(mode="live")
    riserva = _riga(db, status="pending", bet_id="bf-1")
    esito = S._annulla_riserva(db, market=SenzaRilettura(), trade=riserva, now=NOW)
    assert esito["ok"] is False and "ignoto" in esito["motivo"]


# ===========================================================================
# 2. CASH-OUT PER SINGOLA RIGA -> RIGA ORFANA
# ===========================================================================
def test_la_riga_chiusa_a_mano_non_riceve_piu_gambe_figlie():
    """Il PERCORSO VERO: `_request_cashout`, quello che gira quando il trader
    clicca «Cash out» sulla scheda. La riga resta orfana: il bot non ci
    aggiunge la gamba da 0,04 EUR sul residuo e non la fa piu' girare nella
    macchina delle uscite."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    prima = S._exit_candidates([riga])
    assert prima == [riga]
    res = S._request_cashout(db=db, market=MercatoConConto(),
                             rows_by_event={"1.1": _feed_row()},
                             payload={"trade_id": riga["id"], "fraction": 1.0},
                             params={}, now=NOW)
    assert res.get("ok") is True
    dopo = db.get_trade(riga["id"])
    assert S.marcatore_utente(dopo)["come"] == "cashout"
    assert S._exit_candidates([dopo]) == []


def test_un_uscita_del_BOT_approvata_dall_utente_non_e_una_sua_chiusura():
    """Il cancelletto del TENNIS manda una richiesta `cashout` identica a
    quella del bottone «Cash out»: la differenza e' che quella chiusura l'ha
    DECISA IL BOT (`_proponi_chiusura` scrive `exit_kind` nel payload) e
    l'utente ha solo dato l'ok. Marcarla come chiusura dell'utente spegnerebbe
    il bot su una partita che sta gestendo lui — il replay tennis
    `approvata-subito` lo ha fatto vedere al primo giro."""
    db = FakeDB(mode="live")
    riga = _riga(db, sport="tennis", strategy="tennis")
    res = S._request_cashout(
        db=db, market=MercatoConConto(), rows_by_event={"1.1": _feed_row()},
        payload={"trade_id": riga["id"], "fraction": 1.0,
                 "exit_kind": "take_profit", "exit_reason": "obiettivo raggiunto"},
        params={}, now=NOW)
    assert res.get("ok") is True
    assert S.marcatore_utente(db.get_trade(riga["id"])) is None
    assert S.evento_chiuso_dall_utente("1.1") is None
    assert "chiuso_dall_utente" not in db.kinds()


@pytest.mark.parametrize("firma", [
    {"approved_at": "2026-09-16T20:00:00Z"},     # la RPC safe_request_approve
    {"exit_kind": "take_profit"},                # il payload della proposta
    {"approvata_da": "replay: il trader firma"},  # la firma nel replay
])
def test_le_tre_firme_dell_approvazione_valgono_tutte(firma):
    """La RPC vera CONSERVA il payload della proposta e ci aggiunge
    ``approved_at``; il doppio del replay tennis lo RIFA' da zero e ci mette
    ``approvata_da`` (difetto 27: un doppio che parla una lingua diversa dal
    vero). Se ne riconoscono tutte e tre, cosi' nessuno dei due percorsi puo'
    far passare un'uscita del bot per una chiusura dell'utente."""
    assert S._uscita_del_bot_approvata({"trade_id": 1, "fraction": 1.0, **firma})
    assert not S._uscita_del_bot_approvata({"trade_id": 1, "fraction": 1.0})


def test_una_sola_riga_viva_chiusa_a_mano_e_un_cashout_globale():
    """L'utente non deve premere due bottoni: se chiude a mano l'ULTIMA
    posizione viva del bot su quella partita, quello E' il cash-out globale —
    e solo su QUELLA partita (le altre restano in carico al bot)."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    altra = _riga(db, event_id="1.2", market_id="1.2",
                  signal_key="1.2:esatto:home:1-1")
    res = S._request_cashout(db=db, market=MercatoConConto(),
                             rows_by_event={"1.1": _feed_row()},
                             payload={"trade_id": riga["id"], "fraction": 1.0},
                             params={}, now=NOW)
    assert res.get("ok") is True and res.get("evento_chiuso_dall_utente") is True
    assert S.evento_chiuso_dall_utente("1.1") is not None
    assert S.evento_chiuso_dall_utente("1.2") is None
    assert S._righe_vive_del_bot(db.trades, "1.1") == []
    assert [t["id"] for t in S._righe_vive_del_bot(db.trades, "1.2")] == [altra["id"]]


# ===========================================================================
# 3. CHIUSURA FUORI DALL'APP — la posizione di conto
# ===========================================================================
def _sorveglia(db, mercato, riga, closings=None, params=None):
    return S._sorveglia_posizione_di_conto(
        db=db, market=mercato, parents=[riga],
        closings={int(riga["id"]): list(closings or [])},
        now=NOW, params=params or {})


def test_posizione_sparita_dal_conto_e_chiusura_dell_utente():
    db = FakeDB(mode="live")
    riga = _riga(db)                      # LAY 2,00 del bot
    mercato = MercatoConConto(
        regolati=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                  _ordine("utente-1", "back", 2.0)])     # la SUA chiusura
    assert _sorveglia(db, mercato, riga) == 1
    assert S.evento_chiuso_dall_utente("1.1")["come"] == "fuori_app"
    assert "posizione_di_conto" in db.kinds()


def test_l_utente_puo_avere_operazioni_SUE_sulla_stessa_selezione():
    """Il caso che fa sbagliare: sulla selezione c'e' ANCHE roba sua.

    Il bot ha una LAY da 2,00 ancora viva; l'utente ha una sua LAY da 5,00 e una
    sua BACK da 5,00 (che si annullano fra loro). Il netto di conto contiene
    ancora la posizione del bot: NON e' «tutto chiuso», e nemmeno «tutto mio».
    """
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[
        _ordine(f"safe-t{riga['id']}", "lay", 2.0),
        _ordine("utente-1", "lay", 5.0),
        _ordine("utente-2", "back", 5.0),
    ])
    assert _sorveglia(db, mercato, riga) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None
    verdetti = [p.get("verdetto") for k, p in db.activity if k == "posizione_di_conto"]
    assert verdetti == []          # niente da dire: la posizione c'e' ancora


def test_copertura_solo_parziale_dell_utente_si_dichiara_e_basta():
    db = FakeDB(mode="live")
    riga = _riga(db, size=4.0, liability=124.0)
    mercato = MercatoConConto(vivi=[
        _ordine(f"safe-t{riga['id']}", "lay", 4.0),
        _ordine("utente-1", "back", 3.0),      # ne copre 3 su 4
    ])
    assert _sorveglia(db, mercato, riga) == 0
    verdetti = [p.get("verdetto") for k, p in db.activity if k == "posizione_di_conto"]
    assert verdetti == ["ridotta_dall_utente"]
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_gambe_non_ritrovate_e_riconciliazione_non_chiusura():
    """Se gli ordini del BOT non si ritrovano sul conto il caso e' una
    riconciliazione: non si spegne niente su un dubbio."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine("utente-1", "back", 9.0)])
    assert _sorveglia(db, mercato, riga) == 0
    verdetti = [p.get("verdetto") for k, p in db.activity if k == "posizione_di_conto"]
    assert verdetti == ["gambe_non_ritrovate"]
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_il_paper_non_ha_nessun_conto_da_leggere():
    db = FakeDB(mode="paper")
    riga = _riga(db, mode="paper")
    mercato = MercatoConConto(regolati=[_ordine(f"safe-t{riga['id']}", "lay", 2.0)])
    assert _sorveglia(db, mercato, riga) == 0
    assert mercato.letture == []


def test_la_lettura_di_conto_rispetta_il_respiro_del_db():
    """Due giri di fila: la seconda lettura NON si fa (cadenza 30 s/mercato)."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0)])
    _sorveglia(db, mercato, riga)
    _sorveglia(db, mercato, riga)
    assert mercato.letture == ["1.1"]
    assert S.CONTO_EVERY_S == 30.0


def test_il_pnl_viene_dal_settlement_vero_non_dedotto():
    db = FakeDB(mode="live")
    riga = _riga(db)
    ref = f"safe-t{riga['id']}"
    mercato = MercatoConConto(regolati=[
        {**_ordine(ref, "lay", 2.0), "bet_outcome": "WON", "profit": 2.0},
        _ordine("utente-1", "back", 2.0),
    ])
    assert _sorveglia(db, mercato, riga) == 1
    finale = db.get_trade(riga["id"])
    assert finale["status"] == "won"
    assert finale["pnl"] == pytest.approx(1.9)       # 2,00 meno il 5% di commissione


def test_mercato_non_ancora_regolato_non_inventa_nessun_pnl():
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(regolati=[
        _ordine(f"safe-t{riga['id']}", "lay", 2.0),      # senza bet_outcome
        _ordine("utente-1", "back", 2.0),
    ])
    assert _sorveglia(db, mercato, riga) == 1
    finale = db.get_trade(riga["id"])
    assert finale["status"] == "open" and finale["pnl"] == 0.0
    assert S.marcatore_utente(finale)["come"] == "fuori_app"


# ===========================================================================
# 4. I CAP DEL BOT CONTANO SOLO IL BOT
# ===========================================================================
def _manuale(db: FakeDB, liability: float) -> dict:
    return _riga(db, origin="manual", strategy="manual", signal_key=None,
                 event_id="1.9", market_id="1.9", liability=liability,
                 selection_id=111)


def test_32_80_di_responsabilita_manuale_non_toccano_i_cap_del_bot():
    """Il numero e' quello misurato il 16/09 nello scenario `manuale-e-bot`."""
    db = FakeDB(mode="live")
    _riga(db)                                  # 62,00 del bot
    _manuale(db, 32.80)                        # 32,80 del trader
    ctx = S.build_risk_ctx(db, NOW, {}, mode="live")
    assert [t["id"] for t in ctx["open"]] == [1], "i cap contano SOLO il bot"
    assert [t["id"] for t in ctx["open_tutte"]] == [1, 2], "la pagina vede tutto"
    assert [t["id"] for t in ctx["open_all"]] == [1, 2], "la protezione vede tutto"
    assert ctx["day_liability"] == pytest.approx(62.0)


def test_i_totali_di_pagina_restano_completi():
    db = FakeDB(mode="live")
    _riga(db)
    _manuale(db, 32.80)
    agg = DB.aggregate_rows(db.trades, mode="live")
    assert agg["day_liability"] == pytest.approx(94.8)      # 62,00 + 32,80: pagina
    assert agg["day_liability_auto"] == pytest.approx(62.0)  # cap del bot
    assert agg["open_count"] == 2 and agg["open_count_auto"] == 1


def test_il_cashout_manuale_di_una_posizione_del_bot_resta_pnl_del_bot():
    """Una gamba di chiusura MANUALE su una posizione AUTOMATICA e' del bot:
    escluderla darebbe un realizzato falso."""
    righe = [
        {"id": 1, "event_id": "1.1", "origin": "auto", "status": "won", "pnl": 3.0,
         "liability": 10.0, "mode": "live", "strategy": "esatto",
         "placed_at": NOW.isoformat()},
        {"id": 2, "event_id": "1.1", "origin": "manual", "closes_trade_id": 1,
         "status": "lost", "pnl": -1.0, "liability": 0.0, "mode": "live",
         "strategy": "manual", "placed_at": NOW.isoformat()},
    ]
    solo_bot = DB.righe_del_bot(righe)
    assert [r["id"] for r in solo_bot] == [1, 2]
    agg = DB.aggregate_rows(righe, mode="live")
    assert agg["realized_total_auto"] == pytest.approx(2.0)


def test_una_riga_senza_origine_conta_come_del_bot():
    """`origin` e' NOT NULL DEFAULT 'auto' nel database: in dubbio si CONTA nei
    cap, non si nasconde (difetto 21 del catalogo)."""
    assert S.e_del_bot({"origin": None}) is True
    assert S.e_del_bot({}) is True
    assert S.e_del_bot({"origin": "manual"}) is False


def test_la_riserva_manuale_non_entra_nei_cap_del_ciclo():
    ctx = {"open": [], "open_tutte": [], "day_liability": 0.0}
    S._risk_commit(ctx, {"id": 1, "event_id": "1.1", "origin": "manual",
                         "liability": 32.80, "strategy": "manual"})
    assert ctx["open"] == [] and len(ctx["open_tutte"]) == 1
    assert ctx["day_liability"] == pytest.approx(0.0)
    S._risk_commit(ctx, {"id": 2, "event_id": "1.1", "origin": "auto",
                         "liability": 62.0, "strategy": "esatto"})
    assert [t["id"] for t in ctx["open"]] == [2]
    assert ctx["day_liability"] == pytest.approx(62.0)
