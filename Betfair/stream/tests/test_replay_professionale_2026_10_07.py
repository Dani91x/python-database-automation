"""07/10 sera - REPLAY PROFESSIONALE: cio' che il banco restituisce alla UI.

Ordine dell'utente: <<per qualsiasi bot e qualsiasi strategia devo vedere dal
ladder esattamente come avrebbe operato il bot nella realta', con importi, P&L,
abbinamenti>>. Il banco (``applica_bot.esegui``, la funzione del worker) ora
restituisce, oltre alla cronologia degli ordini:

* sulle righe i campi ``_`` letti dall'ordine VERO di flumine
  (``varianti_bot.campi_ordine``): identita' ``_ordine`` (un ``replace_order``
  crea un ordine nuovo con lo STESSO ref), trade, strategia, ``_sostituisce``;
  sull'ultima riga ``_profitto_flumine`` (regolamento di flumine);
* ``esiti_mercati`` dal raw, ``conto_banco`` (P&L a regolamento dalle righe, le
  STESSE regole della UI ``replayOperazioni.contoRegolato``), ``conto_flumine``,
  ``conto_dichiarato`` (referto del bot), ``cicli_bot``/``clic_bot`` come dati,
  ``richiesta``/``conferme``/``versione`` per l'avviso di onesta' della UI.

Le fixture sono ESITI VERI del banco (stessi file dei test della UI:
``frontend/src/lib/__fixtures__/replay_pro``). ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from unittest import mock

import pytest

from Betfair.stream.backtest import applica_bot as AB
from Betfair.stream.backtest import varianti_bot as VB

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FIXTURE = os.path.join(RADICE, "frontend", "src", "lib", "__fixtures__", "replay_pro")
ESITI = sorted(f for f in os.listdir(FIXTURE) if f.startswith("esito_") and f.endswith(".json"))
TENNIS_DIR = os.environ.get("APPLICA_BOT_TENNIS_DIR",
                            "/home/user/python-database-automation/_live_raw_tennis")
CALCIO_DIR = "/home/user/python-database-automation/_live_raw"


def _esito(nome: str):
    with open(os.path.join(FIXTURE, nome), encoding="utf-8") as fh:
        return json.load(fh)


def test_ci_sono_le_fixture_vere():
    assert len(ESITI) >= 9


@pytest.mark.parametrize("nome", ESITI)
def test_conto_regolato_uguale_al_banco_e_a_flumine(nome):
    """Il P&L a regolamento ricalcolato dalle righe e' quello che il banco ha
    scritto nell'esito e, quando il mercato e' stato regolato da flumine, e'
    il regolamento di FLUMINE (``order.simulated.profit``) al centesimo."""
    e = _esito(nome)
    c = AB.conto_regolato(e["righe"], e["esiti_mercati"])
    assert {k: c[k] for k in ("lordo", "commissione", "netto", "mercati")} == {
        k: e["conto_banco"][k] for k in ("lordo", "commissione", "netto", "mercati")}
    if e.get("conto_flumine"):
        assert c["lordo"] == e["conto_flumine"]["lordo"]
        assert c["mercati"] == e["conto_flumine"]["mercati"]
    d = e.get("conto_dichiarato")
    if d and d["metodo"] == "regolamento":
        assert (c["lordo"], c["commissione"], c["netto"]) == (d["lordo"], d["commissione"], d["netto"])


def _riga(**k):
    base = {"bet_id": "1", "client_order_ref": "r", "market_id": "1.1", "selection_id": 5,
            "side": "back", "price": 1.1, "size": 0.15, "size_matched": 0.15,
            "average_price_matched": 1.1, "status": "EXECUTION_COMPLETE", "_ms": 1}
    base.update(k)
    return base


def test_arrotondamento_per_ordine_come_flumine():
    es = {"1.1": {"runners": {"5": "WINNER", "6": "LOSER"}, "aliquota": 0.05}}
    righe = [_riga(_ordine=str(i)) for i in range(3)]
    assert AB.conto_regolato(righe, es)["lordo"] == 0.06          # 3 x round(0.015.., 2)
    assert AB.conto_regolato([_riga(_ordine="z", price=1.5, size=0.25, size_matched=0.25,
                                    average_price_matched=1.5)], es)["lordo"] == 0.12
    # mercato senza risultato: fuori dal conto e dichiarato
    c = AB.conto_regolato(righe, {})
    assert c["lordo"] == 0 and c["mercati_non_regolati"] == ["1.1"]


def test_identita_dell_ordine_e_non_del_ref():
    """Due bet id con lo stesso ref (replace di flumine) restano due ordini."""
    r1 = _riga(_ordine="a", client_order_ref="sc1", bet_id="27")
    r2 = _riga(_ordine="b", client_order_ref="sc1", bet_id="28")
    assert len({AB._chiave(r) for r in (r1, r2)}) == 2
    assert AB.cronologia([r1, r2]) == [r1, r2]


def test_campi_ordine_dal_replace_vero_di_flumine():
    """``campi_ordine`` sugli oggetti VERI di flumine: il nuovo ordine creato da
    ``Trade.create_order_replacement`` si lega al vecchio anche dopo che flumine
    ha svuotato ``update_data`` (vecchio chiuso)."""
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    strat = mock.Mock()
    strat.name = "s1"
    tr = Trade(market_id="1.1", selection_id=5, handicap=0, strategy=strat)
    vecchio = tr.create_order(side="LAY", order_type=LimitOrder(1.01, 1.0),
                              context={"customer_order_ref": "sc1"})
    vecchio.update_client(mock.Mock(paper_trade=False))
    vecchio.executable()
    vecchio.bet_id = "27"
    vecchio.replace(1.69)
    assert vecchio.status.name == "REPLACING"
    nuovo = tr.create_order_replacement(vecchio, 1.69, 0.79, datetime.now(timezone.utc))
    campi = VB.campi_ordine(nuovo)
    assert campi["_ordine"] == str(nuovo.id) and campi["_sostituisce"] == str(vecchio.id)
    assert campi["_trade_id"] == str(tr.id) and campi["_strategia"] == "s1"
    assert VB.campi_ordine(vecchio)["_sostituisce"] is None
    # un altro ordine dello stesso trade, NON nato da un replace: nessun legame
    altro = tr.create_order(side="LAY", order_type=LimitOrder(1.69, 1.0))
    assert VB.campi_ordine(altro)["_sostituisce"] is None


def test_conferme_e_conto_dichiarato_dal_referto():
    note = ["ACCENSIONE dell'utente a 18:30 (ms 1783708200000, primo giro ...)",
            "ATTIVA ADESSO clic clic-2-1783711500000 (in gioco al 24'25\"): letto ...",
            "P&L del replay: lordo +5.26 | commissione 0.26 (5.0%) | NETTO +5.00 EUR (...)"]
    c = AB.conferme(note, 1783708200000, [1783711500000, 1783712000000])
    assert c == {"dal_ms": True, "clic_ms": [{"ms": 1783711500000, "ricevuto": True},
                                             {"ms": 1783712000000, "ricevuto": False}]}
    assert AB.conferme(note[2:], 1783708200000, None)["dal_ms"] is False
    assert AB.conferme(note, None, None) == {"dal_ms": None, "clic_ms": []}
    ref = mock.Mock(stats_finali={}, note=note)
    d = AB.conto_dichiarato(ref)
    assert (d["metodo"], d["lordo"], d["commissione"], d["netto"]) == ("regolamento", 5.26, 0.26, 5.0)
    ref2 = mock.Mock(stats_finali={"media_conto": {"lordo": 0.48, "commissione": 0.02, "netto": 0.46,
                                                   "aliquota": 0.05, "cicli_esito_ignoto": 0}}, note=note)
    assert AB.conto_dichiarato(ref2)["metodo"] == "cicli"
    assert AB.conto_dichiarato(mock.Mock(stats_finali={}, note=[])) is None


def test_esito_vero_media_under_clic_strutturati():
    """Il caso dei 4 clic (uno rifiutato perche' il ciclo era aperto): i clic e
    i cicli arrivano come DATI, non solo note."""
    e = _esito("esito_media_clic_multi_69.json")
    assert e["versione"] == AB.VERSIONE_ESITO
    assert [c["esito"] for c in e["clic_bot"]] == ["eseguito", "rifiutato", "eseguito", "eseguito"]
    assert e["clic_bot"][1]["motivo"] == "posizione aperta o ordine vivo"
    assert [c["origine"] for c in e["cicli_bot"]] == ["clic", "clic", "clic"]
    assert [c["lordo"] for c in e["cicli_bot"]] == [0.02, 0.11, 0.35]
    assert all(c["inizio_ms"] and c["fine_ms"] for c in e["cicli_bot"])
    assert e["conferme"]["dal_ms"] is True
    assert e["richiesta"]["clic_ms"] == e["clic_ms"]


@pytest.mark.skipif(not os.path.isfile(os.path.join(TENNIS_DIR, "20260707", "35790089",
                                                    "35790089.raw.jsonl")),
                    reason="registrazione tennis 35790089 assente")
def test_banco_vero_tennis_scalper_riprezzo_e_regolamento():
    """Il banco VERO (``applica_bot.esegui``, ~12 s): l'ordine nato dal replace di
    flumine si lega al vecchio; il P&L dalle righe e' quello di flumine."""
    e = AB.esegui({"bot": "tennis_scalper", "scenario": "gate-aperto", "event_id": "35790089"},
                  data_dir=TENNIS_DIR)
    assert e["ordini"] == 72
    legati = [r for r in e["righe"] if r.get("_sostituisce")]
    assert legati and all(r["_ordine"] != r["_sostituisce"] for r in legati)
    assert e["conto_flumine"]["lordo"] == e["conto_banco"]["lordo"] == -10.08
    assert e["esiti_mercati"]["1.259745327"]["vincitori"] == [35635727]


@pytest.mark.skipif(not os.path.isfile(os.path.join(CALCIO_DIR, "35797769", "35797769.raw.jsonl")),
                    reason="registrazione 35797769 assente")
def test_esiti_dal_raw_calcio():
    es = AB.esiti_dal_raw(os.path.join(CALCIO_DIR, "35797769", "35797769.raw.jsonl"))
    ou = es["1.259819682"]
    assert ou["market_type"] == "OVER_UNDER_25"
    assert ou["runners"] == {"47972": "LOSER", "47973": "WINNER"} and ou["vincitori"] == [47973]
    assert ou["aliquota"] == 0.05 and ou["chiuso_ms"] > ou["in_gioco_ms"] > 0
