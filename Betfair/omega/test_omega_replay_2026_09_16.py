# -*- coding: utf-8 -*-
"""I CONTROLLI DI OMEGA SANNO DIVENTARE ROSSI (C.2, 16/09).

Un controllo che non si e' mai visto diventare rosso non certifica niente
(PROCESSO_STANDARD_BOT, difetto 35). Qui ogni controllo di
`Betfair/omega/certificazione.py` viene messo davanti a DUE casi costruiti con
le funzioni VERE di Omega (`omega_model.ModelSelection`, `omega_model.LiveState`,
`omega_config.DEFAULTS`, `omega_engine.customer_ref_for`, il `DbMemoriaOmega`
del replay): una violazione CERTA — e deve scattare — e un caso sano — e deve
tacere.

In piu':
  * il `DbMemoriaOmega` ha le FIRME di `Betfair/omega/omega_db.py`, verificate
    per introspezione una funzione alla volta (un doppio che risponde a domande
    a cui il vero non risponde e' vietato);
  * la formula dei nomi delle scoreline e' verificata CONTRO LA REGISTRAZIONE:
    a ogni gol i runner diventati impossibili smettono di avere prezzi, e i
    blocchi che si spengono devono essere esattamente quelli che la formula
    predice.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone

import pytest

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_config as C
from Betfair.omega import omega_db as DBVERO
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega.tools import replay_registrazioni as R

ADESSO = datetime(2026, 6, 30, 17, 0, tzinfo=timezone.utc)
RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EVENTO = "35760084"


def _params(**extra):
    p = dict(C.DEFAULTS)
    p.update(extra)
    return p


def _db(trades=None, control=None):
    db = R.DbMemoriaOmega(control or {"id": 1, "status": "running", "mode": "live",
                                      "params": {}, "daily_goal": 250.0, "stats": {}})
    for t in trades or []:
        db.trades.append(dict(t))
        db._id = max(db._id, int(t.get("id") or 0))
    return db


def _scatta(codice, m):
    """I codici delle violazioni che questo momento produce."""
    return [v.codice for v in CERT.verifica(m)]


# ===========================================================================
# A. selezione
# ===========================================================================
def _sel(nome="3 - 3", price=300.0, p_model=0.003, p_implied=0.0032, size=50.0,
         p_data=None):
    return M.ModelSelection(selection_id=13, name=nome, price=price,
                            lay_size_available=size, p_model=p_model,
                            p_implied=p_implied, p_data=p_data)


def _momento_selezione(**kw):
    base = dict(tipo="selezione", now=ADESSO, params=_params(price_max=500.0),
                event_id=EVENTO, leg="ft_cs", half=False,
                state=M.LiveState(52, 3, 0), sel=_sel(),
                audit={"lambda_source": "pre_ko_odds", "lambda_pre": [1.4, 1.0],
                       "p_selected": 0.003, "p_data": None},
                motivo=None, size_needed=5.26, db=_db())
    base.update(kw)
    return CERT.Momento(**base)


def test_a1_scatta_su_una_gamba_saltata_senza_motivo():
    m = _momento_selezione(sel=None, audit=None, motivo="")
    assert "A1" in _scatta("A1", m)
    assert "A1" not in _scatta("A1", _momento_selezione(sel=None, audit=None,
                                                        motivo="no_model_lambdas"))


def test_a2_scatta_sul_punteggio_corrente():
    """E' il difetto del v1: il 09/09 Omega ha bancato 0-3 sullo 0-3."""
    m = _momento_selezione(sel=_sel(nome="3 - 0"), state=M.LiveState(52, 3, 0))
    assert "A2" in _scatta("A2", m)
    assert "A2" not in _scatta("A2", _momento_selezione())


def test_a3_scatta_quando_il_mercato_non_sovrapprezza():
    m = _momento_selezione(sel=_sel(p_model=0.02, p_implied=0.0032))
    codici = _scatta("A3", m)
    assert "A3" in codici
    assert "A3" not in _scatta("A3", _momento_selezione())


def test_a4_scatta_fuori_dalla_banda_di_quota():
    m = _momento_selezione(params=_params())          # price_max torna a 120
    assert "A4" in _scatta("A4", m)
    assert "A4" not in _scatta("A4", _momento_selezione())


def test_a5_scatta_su_una_fonte_lambda_non_dichiarata():
    m = _momento_selezione(audit={"lambda_source": "inventata",
                                  "lambda_pre": [1.4, 1.0]})
    assert "A5" in _scatta("A5", m)
    # le fonti VERE del servizio, compresa la forma `saved_stale:`
    for fonte in ("fixture", "pre_ko_odds", "market_grid", "live_ou", "saved",
                  "saved_stale:live_ou"):
        sano = _momento_selezione(audit={"lambda_source": fonte,
                                         "lambda_pre": [1.4, 1.0]})
        assert "A5" not in _scatta("A5", sano), fonte


def test_a6_scatta_quando_il_veto_empirico_non_e_applicato():
    m = _momento_selezione(audit={"lambda_source": "fixture", "lambda_pre": [1.4, 1.0],
                                  "p_data": 0.01, "p_selected": 0.003})
    assert "A6" in _scatta("A6", m)
    sano = _momento_selezione(audit={"lambda_source": "fixture", "lambda_pre": [1.4, 1.0],
                                     "p_data": 0.001, "p_selected": 0.003})
    assert "A6" not in _scatta("A6", sano)


def test_a7_scatta_su_un_aggregato():
    m = _momento_selezione(sel=_sel(nome="Any Unquoted Home"))
    assert "A7" in _scatta("A7", m)


# ===========================================================================
# B. obiettivo e target
# ===========================================================================
def _momento_sizing(**kw):
    base = dict(tipo="sizing", now=ADESSO, params=_params(), event_id=EVENTO,
                leg="ft_cs", target=2.5, goal=5.0, realized=0.0, legs_left=2,
                size=5.26, price=300.0, aggregati={}, db=_db())
    base.update(kw)
    return CERT.Momento(**base)


def test_b1_scatta_su_un_target_che_non_e_quello_della_formula():
    assert "B1" in _scatta("B1", _momento_sizing(target=9.99))
    # il caso sano usa la FUNZIONE VERA, non un numero scritto a mano
    atteso = E.dynamic_target(5.0, 0.0, 2)
    assert "B1" not in _scatta("B1", _momento_sizing(target=atteso))


def test_b2_scatta_se_la_barra_non_torna():
    rotta = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                         stats={"target_leg": 2.5, "target_match": 9.0,
                                "goal": 5.0, "goal_pct": 10.0})
    assert "B2" in _scatta("B2", rotta)
    sana = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                        stats={"target_leg": 2.5, "target_match": 5.0,
                               "goal": 5.0, "goal_pct": 10.0})
    assert "B2" not in _scatta("B2", sana)


def test_b3_scatta_se_apre_a_obiettivo_gia_raggiunto():
    """Il freno di `stop_on_goal` sta a monte del dimensionamento: il caso si
    osserva sul GIRO (obiettivo raggiunto e zero aperture)."""
    stats = {"goal": 5.0, "realized_effective": 6.0, "realized_today": 6.0}
    rotto = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                         stats=stats, esito_giro={"placed": 1})
    assert "B3" in _scatta("B3", rotto)
    sano = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                        stats=stats, esito_giro={"placed": 0})
    assert "B3" not in _scatta("B3", sano)


def test_b4_scatta_se_apre_col_feed_stantio():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     feed_eta=200.0, status_control="running",
                     esito_giro={"placed": 1, "settled": 0, "greenup": 0})
    assert "B4" in _scatta("B4", m)
    sano = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                        feed_eta=200.0, status_control="running",
                        esito_giro={"placed": 0, "settled": 0, "greenup": 0})
    assert "B4" not in _scatta("B4", sano)


# ===========================================================================
# C. cap di rischio
# ===========================================================================
def test_c1_scatta_sopra_il_tetto_di_liability():
    m = CERT.Momento(tipo="ordine", now=ADESSO,
                     params=_params(max_liability_per_match=12.0), db=_db(),
                     richiesta={"market_id": "1.2", "selection_id": 13, "side": "lay",
                                "price": 300.0, "size": 5.0, "customer_ref": "omega-t1"})
    assert "C1" in _scatta("C1", m)
    sotto = CERT.Momento(tipo="ordine", now=ADESSO,
                         params=_params(max_liability_per_match=12.0), db=_db(),
                         richiesta={"market_id": "1.2", "selection_id": 13, "side": "lay",
                                    "price": 3.0, "size": 5.0, "customer_ref": "omega-t1"})
    assert "C1" not in _scatta("C1", sotto)


def test_c2_scatta_sopra_il_tetto_di_esposizione():
    m = _momento_sizing(params=_params(max_open_liability=25.0),
                        aggregati={"open_liability": 20.0})
    assert "C2" in _scatta("C2", m)


def test_c3_scatta_sotto_il_cap_di_perdita():
    m = _momento_sizing(params=_params(daily_loss_cap=15.0), realized=-20.0)
    assert "C3" in _scatta("C3", m)


def test_c4_scatta_se_apre_a_bot_fermo():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     status_control="stopped",
                     esito_giro={"placed": 1, "settled": 0, "greenup": 0})
    assert "C4" in _scatta("C4", m)
    sano = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                        status_control="stopped",
                        esito_giro={"idle": True, "settled": 0, "greenup": 0})
    assert "C4" not in _scatta("C4", sano)


def test_c4_scatta_se_le_protezioni_non_girano_a_bot_fermo():
    """Fermare il bot toglie le APERTURE, non la sorveglianza delle posizioni."""
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     status_control="stopped", esito_giro={"idle": True})
    assert "C4" in _scatta("C4", m)


# ===========================================================================
# D. uscite
# ===========================================================================
def _momento_uscita(**kw):
    base = dict(tipo="uscita", now=ADESSO, params=_params(), event_id=EVENTO,
                trigger="goal", p_lose=0.12, locked=-22.08, hold_profit=2.16,
                loss_if_lose=116.64, distance=1, minute=28, half=False,
                azione="hold", perche="", db=_db())
    base.update(kw)
    return CERT.Momento(**base)


def test_d1_scatta_su_una_valutazione_a_distanza_troppo_grande():
    assert "D1" in _scatta("D1", _momento_uscita(distance=3))
    assert "D1" not in _scatta("D1", _momento_uscita(distance=1))


def test_d2_il_caso_vero_del_10_09_trade_70():
    """Il trade 70 del 10/09 (p 0,12 · bloccato -22,08 · EV(tengo) -12,1 al 28'):
    uscire buttava 10 EUR di valore atteso. Se il bot esce, D2 deve essere rosso."""
    assert "D2" in _scatta("D2", _momento_uscita(azione="exit"))
    assert "D2" not in _scatta("D2", _momento_uscita(azione="hold"))


def test_d2_tace_quando_il_prezzo_vale_davvero():
    """P(perdita) sopra il tetto e bloccato migliore dell'EV: uscire e' giusto."""
    m = _momento_uscita(azione="exit", p_lose=0.5, locked=-5.0, hold_profit=2.0,
                        loss_if_lose=100.0, minute=85)
    assert "D2" not in _scatta("D2", m)


def test_d3_scatta_se_tiene_un_profitto_certo():
    assert "D3" in _scatta("D3", _momento_uscita(locked=3.0, azione="hold"))
    assert "D3" not in _scatta("D3", _momento_uscita(locked=3.0, azione="exit"))


def test_d4_scatta_se_cristallizza_al_buio():
    m = _momento_uscita(p_lose=None, locked=-10.0, azione="exit")
    assert "D4" in _scatta("D4", m)
    assert "D4" not in _scatta("D4", _momento_uscita(p_lose=None, locked=-10.0,
                                                     azione="hold"))


def test_d5_scatta_quando_la_quota_rotta_alza_il_rischio():
    m = CERT.Momento(tipo="riserva", now=ADESSO, params=_params(), db=_db(),
                     p_lose=0.671, p_modello=0.085, p_mercato=0.671,
                     p_source="model_floor_market", distance=2, minute=91)
    assert "D5" in _scatta("D5", m)
    sano = CERT.Momento(tipo="riserva", now=ADESSO, params=_params(), db=_db(),
                        p_lose=0.20, p_modello=0.085, p_mercato=0.20,
                        p_source="model_floor_market", distance=2, minute=91)
    assert "D5" not in _scatta("D5", sano)


def test_d6_scatta_con_una_chiusura_ancora_pending():
    m = _momento_uscita(azione="exit", locked=1.0,
                        chiusure=[{"id": 9, "status": "pending"}])
    assert "D6" in _scatta("D6", m)


# ===========================================================================
# E. MAI DUE LAY SULLA STESSA SELEZIONE (regola di piattaforma, 16/09)
# ===========================================================================
def _ordine_vivo(ref, mid="1.259475532", sid=13):
    """Una riga ordine nella forma VERA di `omega_market.list_current_orders`
    (snake_case: e' la grafia che il 15/09 era sbagliata)."""
    return {"bet_id": ref, "market_id": mid, "selection_id": sid, "side": "lay",
            "status": "EXECUTABLE", "size_matched": 0.0, "avg_price_matched": None,
            "size_remaining": 5.0, "customer_order_ref": ref}


def test_e1_scatta_con_due_lay_vive_sulla_stessa_selezione():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     righe_ordine=[_ordine_vivo("omega-t1"), _ordine_vivo("omega-t2")])
    assert "E1" in _scatta("E1", m)


def test_e1_scatta_anche_se_la_seconda_e_solo_in_volo():
    """Una riga 'pending' e una a esito IGNOTO possono essere ordini VIVI su
    Betfair: §4.11 le conta nel caso peggiore, e questo controllo pure."""
    db = _db([{ "id": 7, "market_id": "1.259475532", "selection_id": 13,
                "side": "lay", "status": "pending", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     righe_ordine=[_ordine_vivo("omega-t1")])
    assert "E1" in _scatta("E1", m)


def test_e1_scatta_con_una_lay_gia_abbinata_e_una_ancora_viva():
    """Il caso della falsificazione del 16/09: la prima lay e' ABBINATA (riga
    'open') e una seconda resta APPOGGIATA sulla stessa selezione. Se si abbina
    anche quella la posizione e' il doppio di quella voluta."""
    db = _db([{"id": 1, "market_id": "1.259475532", "selection_id": 13,
               "side": "lay", "status": "open", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     righe_ordine=[_ordine_vivo("omega-t1-bis")])
    assert "E1" in _scatta("E1", m)


def test_e1_non_conta_due_volte_lo_stesso_ordine():
    """Lo stesso ordine e' VIVO sul book e APERTO sulla riga: e' uno solo."""
    db = _db([{"id": 1, "market_id": "1.259475532", "selection_id": 13,
               "side": "lay", "status": "open", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     righe_ordine=[_ordine_vivo(E.customer_ref_for(1))])
    assert "E1" not in _scatta("E1", m)


def test_e1_tace_con_una_lay_sola_e_con_selezioni_diverse():
    db = _db()
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     righe_ordine=[_ordine_vivo("omega-t1"),
                                   _ordine_vivo("omega-t2", sid=12)])
    assert "E1" not in _scatta("E1", m)
    # una lay gia' abbinata (EXECUTION_COMPLETE) non e' piu' a mercato
    completa = dict(_ordine_vivo("omega-t2"), status="EXECUTION_COMPLETE")
    m2 = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                      righe_ordine=[_ordine_vivo("omega-t1"), completa])
    assert "E1" not in _scatta("E1", m2)


def test_e1_ignora_le_lay_manuali_dell_utente():
    """Ordine dell'utente 16/09 h18: il bot gestisce SOLO le sue operazioni.
    Una lay che l'utente ha piazzato a mano non e' un duplicato del bot."""
    db = _db([{"id": 1, "market_id": "1.259475532", "selection_id": 13,
               "side": "lay", "status": "open", "origin": "manual", "meta": {}},
              {"id": 2, "market_id": "1.259475532", "selection_id": 13,
               "side": "lay", "status": "open", "origin": "auto", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db)
    assert "E1" not in _scatta("E1", m)
    # due righe AUTOMATICHE sulla stessa selezione restano una violazione
    db2 = _db([{"id": 1, "market_id": "1.259475532", "selection_id": 13,
                "side": "lay", "status": "open", "origin": "auto", "meta": {}},
               {"id": 2, "market_id": "1.259475532", "selection_id": 13,
                "side": "lay", "status": "pending", "origin": "auto", "meta": {}}])
    assert "E1" in _scatta("E1", CERT.Momento(tipo="giro", now=ADESSO,
                                              params=_params(), db=db2))


def test_e1_ignora_anche_l_ordine_vivo_di_una_riga_manuale():
    db = _db([{"id": 1, "market_id": "1.259475532", "selection_id": 13,
               "side": "lay", "status": "open", "origin": "manual", "meta": {}},
              {"id": 2, "market_id": "1.259475532", "selection_id": 13,
               "side": "lay", "status": "open", "origin": "auto", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     righe_ordine=[_ordine_vivo(E.customer_ref_for(1))])
    assert "E1" not in _scatta("E1", m)


# --- E3: le operazioni manuali non muovono il bot -------------------------
def _db_manuale():
    return _db([{"id": 1, "market_id": "1.2", "selection_id": 13, "side": "lay",
                 "status": "open", "origin": "manual", "liability": 100.0,
                 "meta": {"manual": True}},
                {"id": 2, "market_id": "1.3", "selection_id": 7, "side": "lay",
                 "status": "open", "origin": "auto", "liability": 50.0, "meta": {}}])


# Dal 16/09 (patch R6) le stats portano DUE numeri: `open_liability` sono i
# TOTALI DI PAGINA (100 EUR dell'utente + 50 del bot = 150) e
# `open_liability_bot` e' quello con cui il bot DECIDE (50).
_SANE = {"open_liability": 150.0, "open_liability_bot": 50.0}


def test_e3_scatta_se_la_liability_manuale_entra_nei_numeri_del_bot():
    db = _db_manuale()
    rotto = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                         stats={"open_liability": 150.0, "open_liability_bot": 150.0})
    assert "E3" in _scatta("E3", rotto)
    sano = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                        stats=dict(_SANE))
    assert "E3" not in _scatta("E3", sano)


def test_e3_scatta_se_le_stats_non_dicono_su_che_cosa_il_bot_ha_deciso():
    """Il contratto vuole ENTRAMBI i numeri: senza `open_liability_bot` nessuno
    puo' sapere se il bot ha deciso sui suoi soldi o su quelli dell'utente."""
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db_manuale(),
                     stats={"open_liability": 150.0})
    assert "E3" in _scatta("E3", m)


def test_e3_scatta_se_la_pagina_nasconde_al_trader_la_sua_liability():
    """L'altro modo di sbagliare: filtrare le manuali ANCHE dai totali di
    pagina. Il trader ha 100 EUR esposti e la pagina gliene mostra 50."""
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db_manuale(),
                     stats={"open_liability": 50.0, "open_liability_bot": 50.0})
    assert "E3" in _scatta("E3", m)


def test_e3_scatta_se_il_bot_decide_su_una_riga_manuale():
    db = _db_manuale()
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     stats=dict(_SANE),
                     attivita=[("greenup", {"trade_id": 1}, None)])
    assert "E3" in _scatta("E3", m)
    # il SETTLEMENT su una riga manuale e' dovuto (I3): non e' una violazione
    ok = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                      stats=dict(_SANE),
                      attivita=[("settle", {"trade_id": 1}, None)])
    assert "E3" not in _scatta("E3", ok)


# --- E5: chiusura fatta dall'UTENTE FUORI DALL'APP (R9, 16/09 sera) -------
def _db_chiusa_fuori():
    return _db([{"id": 1, "market_id": "1.2", "selection_id": 13, "side": "lay",
                 "status": "open", "origin": "auto", "liability": 100.0,
                 "meta": {"chiuso_dall_utente": {"dove": "fuori dall'app"}}}])


def test_e5_scatta_se_il_bot_non_se_ne_accorge():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     chiuso_fuori_app=True, giri_da_fuori_app=9,
                     esito_giro={"placed": 0, "greenup": 0})
    assert "E5" in _scatta("E5", m)


def test_e5_da_qualche_giro_di_tempo_per_accorgersene():
    """La posizione di conto si rilegge alla sua cadenza: accusare il bot al
    primo giro sarebbe accusare il controllo, non il bot."""
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     chiuso_fuori_app=True, giri_da_fuori_app=1,
                     esito_giro={"placed": 0, "greenup": 0})
    assert "E5" not in _scatta("E5", m)


def test_e5_scatta_se_apre_dopo_la_chiusura_dell_utente():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(),
                     db=_db_chiusa_fuori(), chiuso_fuori_app=True,
                     giri_da_fuori_app=2, esito_giro={"placed": 1, "greenup": 0})
    assert "E5" in _scatta("E5", m)


def test_e5_scatta_se_copre_una_posizione_che_non_esiste_piu():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(),
                     db=_db_chiusa_fuori(), chiuso_fuori_app=True,
                     giri_da_fuori_app=2, esito_giro={"placed": 0, "greenup": 1})
    assert "E5" in _scatta("E5", m)


def test_e5_e_verde_quando_il_bot_lo_sa_e_sta_fermo():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(),
                     db=_db_chiusa_fuori(), chiuso_fuori_app=True,
                     giri_da_fuori_app=50, esito_giro={"placed": 0, "greenup": 0})
    assert "E5" not in _scatta("E5", m)


def test_e5_non_accusa_il_bot_per_un_PLACE_DI_PRIMA():
    """Il falso positivo del controllo (difetto 16 del catalogo): `m.attivita`
    e' CUMULATIVA, e dentro c'e' il `place` che ha APERTO la posizione, mezz'ora
    prima che l'utente la chiudesse. E5 deve guardare i contatori DEL GIRO."""
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(),
                     db=_db_chiusa_fuori(), chiuso_fuori_app=True,
                     giri_da_fuori_app=30, esito_giro={"placed": 0, "greenup": 0},
                     attivita=[("place", {"trade_id": 1}, None)])
    assert "E5" not in _scatta("E5", m)


def test_e5_non_ha_un_caso_finche_l_utente_non_ha_chiuso():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     esito_giro={"placed": 1, "greenup": 1})
    assert "E5" not in _scatta("E5", m)


# --- E4: dopo il cash-out globale il bot non fa piu' niente ---------------
def test_e4_scatta_se_il_bot_riapre_dopo_il_cashout_globale():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     cashout_globale=True, esito_giro={"placed": 1, "greenup": 0})
    assert "E4" in _scatta("E4", m)


def test_e4_scatta_se_il_bot_chiude_una_posizione_gia_chiusa_dall_utente():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     cashout_globale=True, posizioni_aperte=0,
                     esito_giro={"placed": 0, "greenup": 1})
    assert "E4" in _scatta("E4", m)


def test_e4_lascia_proteggere_il_residuo_del_cashout_parziale():
    """Se la liquidita' ha cappato il fill dell'utente la posizione e' ancora
    aperta: coprirla NON e' una violazione, e' la protezione."""
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     cashout_globale=True, posizioni_aperte=1,
                     esito_giro={"placed": 0, "greenup": 1})
    assert "E4" not in _scatta("E4", m)


def test_e4_scatta_se_resta_una_lay_del_bot_a_mercato():
    db = _db([{"id": 1, "market_id": "1.2", "selection_id": 13, "side": "lay",
               "status": "pending", "origin": "auto", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     cashout_globale=True, posizioni_aperte=0,
                     esito_giro={"placed": 0, "greenup": 0})
    assert "E4" in _scatta("E4", m)


def test_e4_tace_a_partita_chiusa_dall_utente_e_bot_fermo():
    db = _db([{"id": 1, "market_id": "1.2", "selection_id": 13, "side": "lay",
               "status": "hedged", "origin": "auto", "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     cashout_globale=True, esito_giro={"placed": 0, "greenup": 0})
    assert "E4" not in _scatta("E4", m)


def test_e2_scatta_su_cancel_piu_place_nello_stesso_giro():
    db = _db([{"id": 4, "market_id": "1.2", "selection_id": 13, "side": "lay",
               "status": "open", "meta": {}}])
    attivita = [("cancel_richiesto", {"trade_id": 4, "bet_id": "b1"}, None),
                ("place", {"trade_id": 4, "event_id": EVENTO}, None)]
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                     attivita=attivita)
    assert "E2" in _scatta("E2", m)
    solo_cancel = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db,
                               attivita=[attivita[0],
                                         ("cancel_esito", {"trade_id": 4}, None)])
    assert "E2" not in _scatta("E2", solo_cancel)


# ===========================================================================
# J. il ciclo di vita dell'ordine — i difetti del 15/09
# ===========================================================================
class _Esito:
    """Un `PlaceResult` con le chiavi VERE (`omega_market.PlaceResult`)."""

    def __init__(self, ok, size_matched=0.0, avg_price_matched=None,
                 size_requested=None):
        self.ok = ok
        self.order_status = "EXECUTION_COMPLETE" if ok else "EXPIRED"
        self.bet_id = "1" if ok else None
        self.size_matched = size_matched
        self.avg_price_matched = avg_price_matched
        self.size_requested = size_requested
        self.size_remaining = None
        self.error_code = None


def test_j1_scatta_se_un_place_rifiutato_diventa_una_posizione():
    db = _db([{"id": 1, "event_id": EVENTO, "status": "open", "side": "lay",
               "price": 300.0, "meta": {}}])
    m = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                     db=db, esito=_Esito(False),
                     richiesta={"customer_ref": E.customer_ref_for(1),
                                "price": 300.0, "size": 5.0, "side": "lay",
                                "market_id": "1.2", "selection_id": 13})
    assert "J1" in _scatta("J1", m)


def test_j2_scatta_se_il_prezzo_scritto_e_quello_chiesto():
    db = _db([{"id": 1, "event_id": EVENTO, "status": "open", "side": "lay",
               "price": 300.0, "meta": {}}])
    m = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                     db=db, esito=_Esito(True, 5.0, avg_price_matched=290.0),
                     richiesta={"customer_ref": E.customer_ref_for(1),
                                "price": 300.0, "size": 5.0, "side": "lay",
                                "market_id": "1.2", "selection_id": 13})
    assert "J2" in _scatta("J2", m)
    db2 = _db([{"id": 1, "event_id": EVENTO, "status": "open", "side": "lay",
                "price": 290.0, "meta": {}}])
    sano = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                        db=db2, esito=_Esito(True, 5.0, avg_price_matched=290.0),
                        richiesta={"customer_ref": E.customer_ref_for(1),
                                   "price": 300.0, "size": 5.0, "side": "lay",
                                   "market_id": "1.2", "selection_id": 13})
    assert "J2" not in _scatta("J2", sano)


def test_j3_scatta_su_un_ref_per_evento_invece_che_per_gamba():
    """Difetto 4/6 del 15/09: il ref di piazzamento non e' quello per GAMBA.
    Il controllo lo prende ANCHE se cambiasse `customer_ref_for`, perche' il
    secondo metro e' il formato scritto nella Costituzione (§6/§16)."""
    db = _db([{"id": 1, "event_id": EVENTO, "status": "pending", "side": "lay",
               "market_id": "1.2", "selection_id": 13, "price": 300.0, "meta": {}}])
    m = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                     db=db, esito=_Esito(True, 5.0, 300.0),
                     richiesta={"customer_ref": "omega-" + EVENTO, "price": 300.0,
                                "size": 5.0, "side": "lay", "market_id": "1.2",
                                "selection_id": 13})
    assert "J3" in _scatta("J3", m)
    sano = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                        db=db, esito=_Esito(True, 5.0, 300.0),
                        richiesta={"customer_ref": E.customer_ref_for(1),
                                   "price": 300.0, "size": 5.0, "side": "lay",
                                   "market_id": "1.2", "selection_id": 13})
    assert "J3" not in _scatta("J3", sano)


def test_j3_scatta_su_un_ref_ripetuto():
    db = _db([{"id": 1, "event_id": EVENTO, "status": "open", "side": "lay",
               "price": 300.0, "meta": {}}])
    ref = E.customer_ref_for(1)
    m = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                     db=db, esito=_Esito(True, 5.0, 300.0),
                     richiesta={"customer_ref": ref, "price": 300.0, "size": 5.0,
                                "side": "lay", "market_id": "1.2",
                                "selection_id": 13, "refs_gia_usati": [ref]})
    assert "J3" in _scatta("J3", m)


def test_j4_scatta_se_closes_trade_id_e_solo_nel_meta():
    db = _db([{"id": 2, "status": "pending", "side": "back",
               "meta": {"cashout": True, "closes_trade_id": 1}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db)
    assert "J4" in _scatta("J4", m)
    db2 = _db([{"id": 2, "status": "pending", "side": "back", "closes_trade_id": 1,
                "meta": {"cashout": True, "closes_trade_id": 1}}])
    assert "J4" not in _scatta("J4", CERT.Momento(tipo="giro", now=ADESSO,
                                                  params=_params(), db=db2))


def test_j5_scatta_sulla_grafia_camelcase():
    db = _db([{"id": 1, "status": "open", "sizeMatched": 5.0, "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db)
    assert "J5" in _scatta("J5", m)
    assert "J5" not in _scatta("J5", CERT.Momento(tipo="giro", now=ADESSO,
                                                  params=_params(), db=_db()))


def test_j6_scatta_su_un_parziale_non_dichiarato():
    m = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(), event_id=EVENTO,
                     db=_db(), esito=_Esito(True, 2.0, 300.0),
                     richiesta={"customer_ref": "omega-t1", "price": 300.0,
                                "size": 5.0, "side": "lay", "market_id": "1.2",
                                "selection_id": 13},
                     attivita=[("place", {}, None)])
    assert "J6" in _scatta("J6", m)
    con_nota = CERT.Momento(tipo="ordine", now=ADESSO, params=_params(),
                            event_id=EVENTO, db=_db(), esito=_Esito(True, 2.0, 300.0),
                            richiesta={"customer_ref": "omega-t1", "price": 300.0,
                                       "size": 5.0, "side": "lay",
                                       "market_id": "1.2", "selection_id": 13},
                            attivita=[("place_parziale", {}, None)])
    assert "J6" not in _scatta("J6", con_nota)


def test_j7_scatta_su_un_annullo_senza_esito_riletto():
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                     attivita=[("cancel_richiesto", {"trade_id": 1}, None)])
    assert "J7" in _scatta("J7", m)
    sano = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=_db(),
                        attivita=[("cancel_richiesto", {"trade_id": 1}, None),
                                  ("cancel_esito", {"trade_id": 1,
                                                    "esito_ignoto": False,
                                                    "confermato": True}, None)])
    assert "J7" not in _scatta("J7", sano)


# ===========================================================================
# F. settlement e riconciliazione
# ===========================================================================
def test_f1_scatta_sulla_commissione_contata_due_volte():
    db = _db([{"id": 1, "status": "won", "size": 10.0, "price": 300.0,
               "commission": 0.05, "pnl": round(10.0 * 0.95 * 0.95, 2), "meta": {}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db)
    assert "F1" in _scatta("F1", m)
    db2 = _db([{"id": 1, "status": "won", "size": 10.0, "price": 300.0,
                "commission": 0.05, "pnl": round(10.0 * 0.95, 2), "meta": {}}])
    assert "F1" not in _scatta("F1", CERT.Momento(tipo="giro", now=ADESSO,
                                                  params=_params(), db=db2))


def test_f2_scatta_se_un_esito_ignoto_viene_dato_per_non_piazzato():
    db = _db([{"id": 1, "status": "error", "side": "lay",
               "meta": {"reconciling": True}}])
    m = CERT.Momento(tipo="giro", now=ADESSO, params=_params(), db=db)
    assert "F2" in _scatta("F2", m)
    db2 = _db([{"id": 1, "status": "pending", "side": "lay",
                "meta": {"reconciling": True}}])
    assert "F2" not in _scatta("F2", CERT.Momento(tipo="giro", now=ADESSO,
                                                  params=_params(), db=db2))


# ===========================================================================
# P. difetti di progettazione
# ===========================================================================
def test_p1_scatta_sulla_stessa_richiesta_ripetuta():
    and_ = CERT.Andamento()
    for _ in range(6):
        CERT.osserva(and_, CERT.Momento(
            tipo="ordine", now=ADESSO, params=_params(),
            richiesta={"ruolo": "apertura", "market_id": "1.2", "selection_id": 13,
                       "side": "lay", "price": 300.0, "size": 5.0}))
    v = CERT.difetti_di_progettazione(and_, ordini_piazzati=6, righe_scritte=6)
    assert [x.codice for x in v] == ["P1"]


def test_p2_scatta_su_centinaia_di_skip_uguali():
    """Il 10/09: 746 skip `ft_cs no_model_lambdas` e la 2T mai partita (§14.2)."""
    and_ = CERT.Andamento()
    for _ in range(CERT.SKIP_SOSPETTI):
        CERT.osserva(and_, CERT.Momento(tipo="selezione", now=ADESSO,
                                        params=_params(), leg="ft_cs", sel=None,
                                        motivo="no_model_lambdas"))
    v = CERT.difetti_di_progettazione(and_, ordini_piazzati=0, righe_scritte=0)
    assert "P2" in [x.codice for x in v]


# ===========================================================================
# IL DOPPIO DEL DATABASE PARLA COME IL VERO
# ===========================================================================
# le funzioni di `omega_db` che il SERVIZIO chiama (grep su omega_service.py):
# un doppio che ne dimentica una risponderebbe `None` da `__getattr__` e il
# referto lo direbbe solo a posteriori.
FUNZIONI_USATE = (
    "read_control", "set_control", "log", "insert_trade", "update_trade",
    "delete_trade", "list_trades", "open_trades", "get_trade", "hedged_trades",
    "closing_trades_for", "trades_for_event", "traded_event_ids",
    "manual_event_ids", "traded_legs", "failed_legs", "positions_for_results",
    "upsert_events", "replace_events", "update_event_markets",
    "upsert_market_snapshot", "get_event", "save_event_model",
    "event_lambda_hint", "read_live_now", "pending_manual_requests",
    "set_manual_status", "fail_stale_processing", "active_missions",
    "mission_event_ids", "update_mission", "runner_heartbeat",
    "live_follow_status", "enqueue_live_order", "get_live_order_request",
    "get_live_order_request_by_ref", "revoke_live_order_request",
    "get_live_order_mirror", "aggregates", "upsert_daily_goal",
    "ht_ft_transitions", "minute_transitions", "fixtures_for_window",
    "fixture_analysis", "market_frequency",
)


@pytest.mark.parametrize("nome", FUNZIONI_USATE)
def test_il_db_in_memoria_ha_la_firma_del_vero(nome):
    vero = getattr(DBVERO, nome)
    doppio = getattr(R.DbMemoriaOmega, nome, None)
    assert doppio is not None and callable(doppio), (
        f"`{nome}` esiste in omega_db ma non in DbMemoriaOmega: il doppio "
        f"risponderebbe None dal __getattr__ del banco")
    p_vero = [p for p in inspect.signature(vero).parameters.values()]
    p_doppio = [p for n, p in inspect.signature(doppio).parameters.items()
                if n != "self"]
    obbligatori_veri = [p.name for p in p_vero
                        if p.default is inspect.Parameter.empty
                        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    accettati = {p.name for p in p_doppio}
    ha_var = any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in p_doppio)
    assert ha_var or set(obbligatori_veri) <= accettati, (
        f"`{nome}`: il vero chiede {obbligatori_veri}, il doppio accetta "
        f"{sorted(accettati)}")


def test_insert_trade_torna_l_id_come_il_vero():
    """Il vero torna `Optional[int]`, non la riga (difetto 27 del catalogo)."""
    db = _db()
    tid = db.insert_trade({"event_id": EVENTO, "origin": "auto", "phase": "ft_cs",
                           "market_id": "1.2", "selection_id": 13, "side": "lay",
                           "status": "pending", "meta": {}})
    assert isinstance(tid, int) and tid > 0


def test_l_unique_del_database_impedisce_la_seconda_gamba_uguale():
    """`uq_omega_trades_auto_leg` (migrations/omega_models_v5.sql:222): il
    pattern RESERVE-FIRST di Omega (I1) si regge su questo indice."""
    db = _db()
    riga = {"event_id": EVENTO, "origin": "auto", "phase": "ft_cs",
            "market_id": "1.2", "selection_id": 13, "side": "lay",
            "status": "pending", "meta": {}}
    assert db.insert_trade(dict(riga))
    with pytest.raises(RuntimeError):
        db.insert_trade(dict(riga))
    # una gamba BRUCIATA (meta.leg_failed) e' esclusa dall'unique (H-13)
    db2 = _db()
    assert db2.insert_trade(dict(riga, meta={"leg_failed": True}))
    assert db2.insert_trade(dict(riga))


def test_gli_aggregati_passano_dalla_funzione_pura_vera():
    db = _db([{"id": 1, "event_id": EVENTO, "status": "won", "pnl": 2.5,
               "liability": 100.0, "placed_at": ADESSO.isoformat(),
               "settled_at": ADESSO.isoformat(), "meta": {}, "mode": "live"}])
    agg = db.aggregates(E.day_start_utc(ADESSO))
    atteso = E.aggregate_trades(
        [{"id": 1, "event_id": EVENTO, "status": "won", "pnl": 2.5,
          "liability": 100.0, "bet_id": None, "placed_at": ADESSO.isoformat(),
          "settled_at": ADESSO.isoformat(), "meta": {}, "mode": "live",
          "closes_trade_id": None, "size": None, "price": None,
          "commission": None, "phase": None, "side": None}],
        E.day_start_utc(ADESSO))
    assert agg == atteso


# ===========================================================================
# I NOMI DELLE SCORELINE, VERIFICATI SULLA REGISTRAZIONE
# ===========================================================================
def test_la_formula_delle_scoreline_e_quella_di_betfair():
    """I `selectionId` globali di Betfair per il Correct Score."""
    attesi = {1: "0 - 0", 2: "1 - 0", 3: "1 - 1", 4: "0 - 1", 5: "2 - 0",
              6: "2 - 1", 7: "2 - 2", 8: "1 - 2", 9: "0 - 2", 10: "3 - 0",
              11: "3 - 1", 12: "3 - 2", 13: "3 - 3", 14: "2 - 3", 15: "1 - 3",
              16: "0 - 3"}
    for sid, nome in attesi.items():
        assert R.nome_scoreline(sid) == nome, sid
    assert R.nome_runner_punteggio(9063254) == "Any Unquoted Home"
    assert R.nome_scoreline(9063254) is None      # non e' una scoreline


def _sidecar(event_id):
    return os.path.join(RADICE, "_live_raw", str(event_id), f"{event_id}.jsonl")


@pytest.mark.skipif(not os.path.isfile(_sidecar(EVENTO)),
                    reason="registrazione non su questa macchina")
def test_la_formula_regge_contro_la_registrazione():
    """LA PROVA SUI DATI: quando il punteggio diventa 1-0, i runner del Correct
    Score che diventano IMPOSSIBILI sono tutti e soli quelli con casa=0 — e
    Betfair smette di quotarli. Se la formula sbagliasse l'associazione
    id->punteggio, l'insieme che si spegne non tornerebbe.
    """
    cs_market = None
    snapshot = None
    # 1-0 dal 7' (gol a ts 1782835704258), prima del 2-0 (1782836907518)
    quando = 1782836000000
    with open(os.path.join(RADICE, "_live_raw", EVENTO, f"{EVENTO}.raw.jsonl"),
              "r", encoding="utf-8") as fh:
        for riga in fh:
            if '"CORRECT_SCORE"' not in riga:
                continue
            d = json.loads(riga)
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition") or {}
                if md.get("marketType") == "CORRECT_SCORE":
                    cs_market = str(mc.get("id"))
            if cs_market:
                break
    assert cs_market, "mercato CORRECT_SCORE non trovato nella registrazione"
    with open(_sidecar(EVENTO), "r", encoding="utf-8") as fh:
        for riga in fh:
            d = json.loads(riga)
            if d.get("market_id") == cs_market and d.get("pt") <= quando:
                snapshot = d
    assert snapshot is not None
    spenti = {int(sid) for sid, v in snapshot["runners"].items()
              if not v.get("b") and not v.get("l")}
    attesi = {sid for sid in spenti | set()
              if True}
    # i runner senza NESSUN prezzo sul 1-0 devono essere esattamente i "0 - x"
    nomi_spenti = sorted(R.nome_scoreline(s) for s in spenti)
    assert nomi_spenti == ["0 - 0", "0 - 1", "0 - 2", "0 - 3"], (
        f"sul 1-0 si sono spenti {nomi_spenti}: la formula id->punteggio non "
        f"corrisponde a quella di Betfair")
    assert attesi == spenti


# ===========================================================================
# GLI SCENARI SONO DICHIARATI
# ===========================================================================
def test_ogni_scenario_ha_una_descrizione():
    assert set(R.SCENARI) == set(R.SCENARI_DESCRITTI)
    for nome, testo in R.SCENARI_DESCRITTI.items():
        assert testo and len(testo) > 20, nome


def test_gli_scenari_toccano_solo_parametri_della_whitelist():
    """Uno scenario che cambiasse una chiave sconosciuta cambierebbe il bot, non
    la sua configurazione."""
    for nome, par in R.SCENARI.items():
        for chiave in par:
            if chiave.startswith("__"):
                continue
            assert chiave in C.DEFAULTS, f"scenario {nome}: '{chiave}' non e' un parametro"


def test_il_controllo_e1_e_registrato_con_il_suo_quando():
    codici = dict(CERT.elenco_controlli())
    assert "E1" in codici and "lay" in codici["E1"].lower()
    assert "E2" in codici
