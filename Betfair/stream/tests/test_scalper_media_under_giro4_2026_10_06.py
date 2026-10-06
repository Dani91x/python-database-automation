"""MEDIA UNDER, quarto giro (06/10/2026): decisioni dell'utente su P1 e P13.

* P1 (a): lo STOP della sessione lascia appoggiata la banca PERSIST della
  modalita' (la posizione resta protetta e si chiude da sola).
* P13: dopo un crash / una caduta di rete la modalita' in SOLDI VERI riprende
  ESATTAMENTE da dove era, senza errori e senza operazioni doppie, leggendo il
  conto (in prova niente: la persistenza serve in soldi veri).
* In piu' (scelta dell'utente): ogni strategia della sessione ha un nome legato
  alla PARTITA (prima la classe: una sessione in soldi veri riadottava, e
  all'arresto annullava, gli ordini delle sessioni delle altre partite).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import EVENTO, KO_MS, BancoMedia, giri


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


@pytest.fixture
def soldi_veri_dichiarati():
    from Betfair.stream.backtest.certifica import _freni_da_banco

    with _freni_da_banco():
        yield


def _catalogo():
    defs = {
        "1.300000001": {"market_type": "MATCH_ODDS", "runners": [(11, 1), (12, 2), (58805, 3)]},
        "1.300000025": {"market_type": "OVER_UNDER_25", "runners": [(47972, 1), (47973, 2)]},
        "1.300000035": {"market_type": "OVER_UNDER_35", "runners": [(1222344, 1), (1222345, 2)]},
    }
    follow = {"event_id": EVENTO, "fixture_id": None, "league_id": None,
              "home_name": "A", "away_name": "B", "open_date": "2025-09-29T10:00:00.000Z"}
    return R.catalogo_dal_raw(defs), follow


# ===========================================================================
# A. il nome di ogni strategia e' legato alla partita
# ===========================================================================
def test_nome_strategia_per_partita_e_ruolo():
    assert SS.nome_strategia("maker", "35797769") == "scm35797769"
    assert SS.nome_strategia("sniper", "35797769") == "scn35797769"
    assert SS.nome_strategia("theta", "35797769") == "sct35797769"
    assert SS.nome_strategia("media", "35797769") == "mu35797769"
    # e' anche il customerStrategyRef: al piu' 15 caratteri, diverso per partita
    assert len(SS.nome_strategia("maker", "123456789012345")) == 15
    nomi = {SS.nome_strategia(r, e) for r in SS.PREFISSI_STRATEGIA
            for e in ("35797769", "35760084")}
    assert len(nomi) == 8


@pytest.mark.usefixtures("soldi_veri_dichiarati")
@pytest.mark.parametrize("scenario, ruolo", [("base", "maker"), (R.SCENARIO_MEDIA, "media")])
def test_la_sessione_arma_le_strategie_col_nome_della_partita(scenario, ruolo):
    import hashlib

    cat, follow = _catalogo()
    par, _cli = R.arma_e_cattura(EVENTO, R.control_della_ui(EVENTO, scenario), follow, cat)
    nome = SS.nome_strategia(ruolo, EVENTO)
    assert par["_name"] == nome
    # l'hash con cui flumine riadotta gli ordini dal conto e' quello del nome
    assert par["name_hash"] == hashlib.sha1(nome.encode("utf-8")).hexdigest()[:13]


# ===========================================================================
# B. P1: lo STOP lascia appoggiata la banca PERSIST della modalita'
# ===========================================================================
def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


class _Tempo:
    """L'orologio e il sonno dell'annullo all'arresto sul banco di prova: ogni
    <<sonno>> fa passare un book (il simulatore esegue gli annulli)."""

    def __init__(self, b: BancoMedia, svuota: Any) -> None:
        self.b, self.svuota, self.t = b, svuota, 0.0

    def ora(self) -> float:
        return self.t

    def dormi(self, s: float) -> None:
        self.t += float(s)
        giri(self.b, self.svuota, 1)


def _db() -> Any:
    ctl = {"event_id": EVENTO, "status": "running", "params": {}}
    return R._DbFinto(R._Orologio(), ctl, {"event_id": EVENTO})


def test_stop_con_la_banca_viva_la_banca_resta(differita, exchange_it):
    b = BancoMedia()
    viol = giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    b.strat.force_flat = True
    viol += giri(b, differita, 3)
    assert viol == [], viol[:3]
    assert b.strat.pronta_allo_stop() is True
    assert b.strat.banca_da_lasciare(banca) is True
    t = _Tempo(b, differita)
    db = _db()
    esito = SS.chiudi_all_arresto(db, EVENTO, b.fw, None, True, "stop_app", flumine_vivo=True,
                                  timeout_s=5.0, ora=t.ora, dormi=t.dormi,
                                  da_lasciare=b.strat.banca_da_lasciare)
    # (il banco di prova lascia EXECUTABLE la punta gia' abbinata per intero: lo
    # stream simulato degli ordini non gira; il suo annullo non tocca niente)
    assert esito["lasciati"] == 1
    assert esito["vivi_dopo"] == 0
    giri(b, differita, 6)
    assert b.vivi("LAY") == [banca] and MU.vivo_o_in_volo(banca)
    avvisi = db.tabelle.get("live_alerts", [])
    assert any("banca PERSIST di chiusura lasciata appoggiata" in a["message"]
               for a in avvisi), avvisi


def test_stop_senza_la_regola_la_banca_si_annulla(differita, exchange_it):
    """La regola di prima (nessun ``da_lasciare``): la banca viene annullata."""
    b = BancoMedia()
    giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    b.strat.force_flat = True
    giri(b, differita, 3)
    t = _Tempo(b, differita)
    esito = SS.chiudi_all_arresto(_db(), EVENTO, b.fw, None, True, "stop_app",
                                  flumine_vivo=True, timeout_s=5.0, ora=t.ora,
                                  dormi=t.dormi)
    assert esito["lasciati"] == 0 and esito["annullo_chiesto"] >= 1
    giri(b, differita, 6)
    assert not MU.vivo_o_in_volo(banca)


def test_stop_durante_un_rientro_la_punta_si_ritira_e_la_banca_copre_tutto(differita,
                                                                            exchange_it):
    """Stop con la punta di rientro abbinata in parte (4 su 10): la punta si
    ritira, la banca copre l'INTERA posizione (14 puntati), poi resta."""
    b = BancoMedia()
    giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(30):
        giri(b, differita, 1, flusso=0.0)
        if len(_punte(b)) == 2 and MU.vivo_o_in_volo(_punte(b)[1]):
            break
    b.strat.force_flat = True
    viol = giri(b, differita, 15, flusso=0.0)
    assert viol == [], viol[:3]
    punta = _punte(b)[1]
    assert not MU.vivo_o_in_volo(punta)
    pos = b.posizione()
    vive = b.vivi("LAY")
    assert len(vive) == 1
    c = MU.quota_della_banca(b.strat._ultimo_ingresso, pos, 2)
    assert (float(vive[0].order_type.price), float(vive[0].size_remaining)) == (
        c, MU.al_centesimo(MU.banca_esatta(pos, c)))
    assert b.strat.pronta_allo_stop() is True
    # nessuna punta nuova dopo lo stop
    assert len(_punte(b)) == 2


def test_stop_non_pronto_finche_la_punta_e_viva(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(30):
        giri(b, differita, 1, flusso=0.0)
        if len(_punte(b)) == 2 and MU.vivo_o_in_volo(_punte(b)[1]):
            break
    assert b.strat.pronta_allo_stop() is False


class _BettingCrash:
    """``trading.betting`` con le firme vere usate dallo sweep: risponde a
    ``list_current_orders`` con gli ordini VERI del banco come ``CurrentOrder``
    di betfairlightweight e registra ogni ``cancel_orders``."""

    def __init__(self, b: BancoMedia) -> None:
        self.b = b
        self.annulli: List[Dict[str, Any]] = []

    def list_current_orders(self, market_ids=None, **_kw):
        from betfairlightweight.resources.bettingresources import CurrentOrders

        righe = [_ordine_corrente(o) for o in self.b.ordini()]
        return CurrentOrders(currentOrders=righe, moreAvailable=False)

    def cancel_orders(self, market_id=None, instructions=None, **_kw):
        self.annulli.append({"market_id": market_id, "instructions": instructions})


class _TradingCrash:
    def __init__(self, b: BancoMedia) -> None:
        self.betting = _BettingCrash(b)


def _ordine_corrente(o: Any) -> Dict[str, Any]:
    """Un ordine flumine come riga di ``listCurrentOrders`` (chiavi della API
    Betfair, quelle che betfairlightweight legge)."""
    m = float(o.size_matched or 0.0)
    resto = float(o.size_remaining or 0.0)
    return {
        "betId": str(o.bet_id), "marketId": o.market_id, "selectionId": o.selection_id,
        "handicap": 0.0, "priceSize": {"price": float(o.order_type.price),
                                       "size": float(o.order_type.size)},
        "bspLiability": 0.0, "side": o.side, "orderType": "LIMIT",
        "status": "EXECUTABLE" if MU.vivo_o_in_volo(o) else "EXECUTION_COMPLETE",
        "persistenceType": str(o.order_type.persistence_type),
        "placedDate": "2025-09-29T09:00:00.000Z",
        "averagePriceMatched": float(o.average_price_matched or 0.0),
        "sizeMatched": m, "sizeRemaining": resto, "sizeLapsed": 0.0,
        "sizeCancelled": float(getattr(o, "size_cancelled", 0.0) or 0.0),
        "sizeVoided": 0.0, "regulatorCode": "MR_INT",
        "customerOrderRef": o.customer_order_ref,
        "customerStrategyRef": str(o.trade.strategy)[:15],
    }


def test_crash_di_flumine_in_soldi_veri_lo_sweep_non_tocca_la_banca(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    tr = _TradingCrash(b)
    db = _db()
    SS._handle_flumine_crash(db, EVENTO, tr, [b.mid], False, framework=b.fw,
                             da_lasciare=b.strat.banca_da_lasciare)
    tolti = [i["betId"] for a in tr.betting.annulli for i in (a["instructions"] or [])]
    assert str(banca.bet_id) not in tolti
    # mai il ripiego market-wide (che toglierebbe anche la banca)
    assert all(a["instructions"] for a in tr.betting.annulli)
    righe = db.attivita("error")
    assert righe and righe[-1]["payload"]["sweep"].get("lasciati") == [str(banca.bet_id)]


def test_crash_senza_la_regola_lo_sweep_toglie_la_banca(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    tr = _TradingCrash(b)
    SS._handle_flumine_crash(_db(), EVENTO, tr, [b.mid], False, framework=b.fw)
    tolti = [i["betId"] for a in tr.betting.annulli for i in (a["instructions"] or [])]
    assert str(banca.bet_id) in tolti
