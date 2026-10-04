# -*- coding: utf-8 -*-
"""CERTIFICAZIONE TENNIS PRO e TENNIS SCALPER (04/10/2026) - il banco dei bot tennis.

Tre pezzi del banco (`certificazione_bot` + `tools/replay_bot`), nessuno della strategia:

* B8 legge i minimi .it dalla FONTE UNICA `trading/minimi_it.py` (prima: 2,00 / 0,50
  scritti a mano, catalogo §7 punto 33). Il VALORE non lo sceglie il banco.
* B10 (nuovo): un ordine che l'exchange del banco ha RIFIUTATO per taglia
  (`backtest.minimi_banco`, INVALID_BET_SIZE) non si rimanda IDENTICO (regola
  dell'utente del 01/10, punto 3). E' cio' che rendeva «verde» un pro che dal 02/10
  rimanda ogni 30 s un place-and-trim da 0,02-0,06 EUR che Betfair rifiuta per legge.
* SV1 (nuovo) e gli scenari `soldi-veri`, `soldi-veri-prova`, `soldi-veri-paper`:
  la catena «soldi veri» del runner (trading control veri, «Ordini reali» di questo
  avvio) sul replay del bot vero.

I finti: ordini VERI di flumine (`Trade.create_order`), client VERI (il simulato del
banco e la sua vista `ClienteLiveBanco`), la regola VERA dell'exchange del banco
(`minimi_banco.sotto_minimo`). ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest
from flumine.markets.blotter import Blotter  # noqa: F401 - import di controllo
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade
from flumine.strategy.strategy import BaseStrategy

from Betfair.stream.backtest import banco_comune as BC
from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.backtest.porta_banco import ClienteLiveBanco
from Betfair.stream.tennis_live import certificazione_bot as CERT
from Betfair.stream.tennis_live.tools import replay_bot as RB
from Betfair.stream.trading import minimi_it as MIN

MID = "1.259781331"
SEL = 10372252


class _Bot(BaseStrategy):
    def check_market_book(self, market: Any, market_book: Any) -> bool:  # pragma: no cover
        return False

    def process_market_book(self, market: Any, market_book: Any) -> None:  # pragma: no cover
        return None


def _bot() -> _Bot:
    return _Bot(market_filter={"markets": []})


def _ordine(strat: Any, side: str, size: float, price: float = 1.5, sel: int = SEL) -> Any:
    return Trade(market_id=MID, selection_id=sel, handicap=0.0, strategy=strat).create_order(
        side=side, order_type=LimitOrder(price=price, size=size, persistence_type="LAPSE"))


def _rifiuto_del_banco(size: Any, tipo: str, side: Any) -> bool:
    """La regola VERA dell'exchange del banco."""
    return MB.sotto_minimo(size, tipo, side)


# --------------------------------------------------------------------------- B8
def test_b8_legge_i_minimi_dalla_fonte_unica():
    assert CERT.MINIMO_IT == {"BACK": float(MIN.IT_MIN_BACK), "LAY": float(MIN.IT_MIN_LAY)}


def test_b8_parcheggio_al_minimo_del_listino_non_e_violazione():
    """Il parcheggio del place-and-trim nasce a `IT_MIN_BACK`: B8 non lo accusa."""
    oss = CERT.Osservazione(bot="tennis_pro", modalita="live", ordini=[
        {"order_id": "p", "side": "BACK", "size": float(MIN.IT_MIN_BACK), "sostituto": False}])
    assert CERT._b8(oss) is None
    sotto = round(float(MIN.IT_MIN_BACK) - 0.05, 2)     # oltre la tolleranza EPS
    oss.ordini = [{"order_id": "q", "side": "BACK", "size": sotto, "sostituto": False}]
    assert "sotto il minimo" in str(CERT._b8(oss))


def test_b8_passo_della_punta_solo_se_la_fonte_unica_lo_dichiara(monkeypatch):
    """Ipotesi aperta (punte a multipli di 0,50): B8 la applica SOLO se
    `minimi_it.IT_PASSO_PUNTA_DIRETTA` esiste; oggi non c'e' (centesimo)."""
    oss = CERT.Osservazione(bot="tennis_pro", modalita="live", ordini=[
        {"order_id": "e", "side": "BACK", "size": 2.37, "sostituto": False}])
    monkeypatch.delattr(MIN, "IT_PASSO_PUNTA_DIRETTA", raising=False)
    assert CERT.passo_punta_diretta() is None and CERT._b8(oss) is None
    monkeypatch.setattr(MIN, "IT_PASSO_PUNTA_DIRETTA", 0.5, raising=False)
    assert "non multiplo" in str(CERT._b8(oss))
    oss.ordini[0]["size"] = 2.5
    assert CERT._b8(oss) is None
    # la banca non ha passo
    oss.ordini = [{"order_id": "l", "side": "LAY", "size": 1.37, "sostituto": False}]
    assert CERT._b8(oss) is None


# --------------------------------------------------------------------------- B10
def test_rifiuti_taglia_letti_dal_registro_dell_exchange_ripetuto_al_secondo():
    s = _bot()
    altro = _bot()
    piazzati: List[tuple] = []
    # sostituto del place-and-trim da 0,02 (sotto il floor 0,50): rifiutato
    piazzati.append((_ordine(s, "LAY", 0.02), MB.SOSTITUZIONE, 0.02))
    # parcheggio legale: nessun rifiuto
    piazzati.append((_ordine(s, "LAY", float(MIN.IT_MIN_LAY)), MB.DIRETTO,
                     float(MIN.IT_MIN_LAY)))
    # stesso rifiuto di un ALTRO bot: non e' affar suo
    piazzati.append((_ordine(altro, "LAY", 0.02), MB.SOSTITUZIONE, 0.02))
    cont: Dict[tuple, int] = {}
    nuovi, idx = CERT.rifiuti_taglia_nuovi(piazzati, 0, s, _rifiuto_del_banco, cont)
    assert idx == 3
    assert [(r["side"], r["size"], r["tipo"], r["ripetuto"]) for r in nuovi] == [
        ("LAY", 0.02, MB.SOSTITUZIONE, False)]
    # nessun nuovo ordine: niente di nuovo (incrementale)
    assert CERT.rifiuti_taglia_nuovi(piazzati, idx, s, _rifiuto_del_banco, cont)[0] == []
    # lo STESSO ordine rimandato: ripetuto
    piazzati.append((_ordine(s, "LAY", 0.02), MB.SOSTITUZIONE, 0.02))
    # un importo DIVERSO non e' «identico»
    piazzati.append((_ordine(s, "LAY", 0.03), MB.SOSTITUZIONE, 0.03))
    nuovi, idx = CERT.rifiuti_taglia_nuovi(piazzati, idx, s, _rifiuto_del_banco, cont)
    assert [(r["size"], r["ripetuto"], r["volte"]) for r in nuovi] == [
        (0.02, True, 2), (0.03, False, 1)]


def test_b10_rosso_solo_sul_rifiuto_ripetuto():
    oss = CERT.Osservazione(bot="tennis_pro")
    assert not CERT._q_rifiuti_taglia(oss)
    oss.rifiuti_taglia = [{"selection_id": SEL, "side": "BACK", "size": 0.06,
                           "tipo": MB.SOSTITUZIONE, "volte": 1, "ripetuto": False}]
    assert CERT._q_rifiuti_taglia(oss) and CERT._b10(oss) is None
    oss.rifiuti_taglia.append({"selection_id": SEL, "side": "BACK", "size": 0.06,
                               "tipo": MB.SOSTITUZIONE, "volte": 2, "ripetuto": True})
    assert "rimandato identico" in str(CERT._b10(oss))
    soll: Dict[str, int] = {}
    codici = [v.codice for v in CERT.verifica(oss, soll)]
    assert "B10" in codici and soll.get("B10") == 1


# --------------------------------------------------------------------------- SV1
def test_client_reale_con_la_definizione_del_runner():
    sim = BC.cliente_simulato()
    assert CERT.client_reale(sim) is False
    assert CERT.client_reale(ClienteLiveBanco(sim)) is True
    assert CERT.client_reale(None) is None


def _riga(reale: Any) -> Dict[str, Any]:
    return {"order_id": "o1", "side": "BACK", "size": 2.0, "client_reale": reale}


@pytest.mark.parametrize("catena,reale,rosso", [
    ("reale", True, False),
    ("reale", False, True),
    ("reale", None, True),
    ("nessuno_reale", True, True),
    ("nessuno_reale", False, False),
    ("simulato", False, False),
    ("simulato", True, True),
])
def test_sv1_il_client_e_quello_della_catena(catena, reale, rosso):
    oss = CERT.Osservazione(bot="tennis_pro", catena_soldi_veri=catena, ordini=[_riga(reale)])
    assert CERT._q_soldi_veri(oss)
    assert (CERT._sv1(oss) is not None) is rosso


def test_sv1_nessun_ordine_reale_si_giudica_a_ogni_giro_gli_altri_con_un_ordine():
    assert CERT._q_soldi_veri(CERT.Osservazione(catena_soldi_veri="nessuno_reale"))
    assert not CERT._q_soldi_veri(CERT.Osservazione(catena_soldi_veri="reale"))
    assert not CERT._q_soldi_veri(CERT.Osservazione())


def test_riga_ordine_porta_il_client():
    sim = BC.cliente_simulato()
    o = _ordine(_bot(), "BACK", 2.0)
    o.update_client(ClienteLiveBanco(sim))
    assert CERT.riga_ordine(o)["client_reale"] is True
    o2 = _ordine(_bot(), "BACK", 2.0)
    o2.update_client(sim)
    assert CERT.riga_ordine(o2)["client_reale"] is False


# --------------------------------------------------------------------------- scenari
def test_scenari_soldi_veri_dichiarati_coi_gate_e_la_catena():
    for sc, (mode, scelta) in RB.SCENARI_SOLDI_VERI.items():
        assert sc in RB.SCENARI_DESCRITTI
        assert RB.modalita_scenario(sc) == "LIVE"            # tetto del runner
        assert RB.modalita_bot_scenario(sc) == mode
        assert RB.dry_run_scenario(sc) is False              # come il ponte del 04/10
        assert RB.parametri_scenario(sc, "tennis_pro") == RB.parametri_scenario(
            "gate-aperto", "tennis_pro")
        assert scelta in ("live", "paper")
    # gli scenari di prima non cambiano modalita'
    assert RB.modalita_bot_scenario("live") == "live"
    assert RB.modalita_bot_scenario("base") == "paper"


# --------------------------------------------------------------------------- replay vero
_DATI = os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec", "20260707")


@pytest.mark.skipif(not os.path.exists(os.path.join(_DATI, "35794049")),
                    reason="registrazione 35794049 assente")
@pytest.mark.parametrize("scenario,reali_attesi,fermati_attesi", [
    ("soldi-veri", True, False),
    ("soldi-veri-prova", False, True),
    ("soldi-veri-paper", False, False),
])
def test_replay_scalper_soldi_veri_sulla_registrazione(scenario, reali_attesi, fermati_attesi):
    """Il bot VERO sul replay VERO: con soldi veri + «Ordini reali» LIVE gli ordini
    partono sul client reale; con «Ordini reali» in prova la terza rete ferma le
    aperture; in prova il client e' il simulato. SV1 sollecitato e verde."""
    ref = RB.certifica_scenario("35794049", data_dir=_DATI, scenario=scenario,
                                bot="tennis_scalper")
    nota = next(n for n in ref.note if n.startswith("SOLDI VERI ("))
    assert ref.sollecitati.get("SV1", 0) > 0
    assert not [v for v in ref.violazioni if v.codice == "SV1"], nota
    reali = int(nota.split("client REALE ")[1].split(",")[0])
    simulati = int(nota.split("client SIMULATO ")[1].split(";")[0])
    fermati = int(nota.split("(TENNIS_MODO_ORDINI) ")[1])
    assert (reali > 0) is reali_attesi, nota
    assert (fermati > 0) is fermati_attesi, nota
    if scenario == "soldi-veri-paper":
        assert simulati > 0, nota
