"""PIANO MIKE 29/09, P5 blocco 4B (richieste del coordinatore dopo le sue 30
mutazioni sul blocco 2, piu' l'impronta del referto).

A. sei test che mancavano: ognuno diventa rosso con la mutazione indicata
   (N3, N13, N14, N15, N17, N21 del coordinatore);
B. contratto dell'impronta: ogni modulo di ``Betfair/mike`` importato dal
   servizio sta nei ``moduli_produzione`` di Mike nel registro del banco, cosi'
   l'impronta del referto cambia quando cambia il motore.

Finti: oggetti veri dell'engine; il registro vero.
"""
from __future__ import annotations

import ast
import os
from typing import Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0
COMM = 0.05


def params(**over):
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    p["cover_form"] = E.COVER_LAY_U45
    p["cover_policy"] = "immediate"
    p.update(over)
    return p


def gamba(role, market, selection, side, prezzo, abbinato, *, ref, status="open",
          size: Optional[float] = None) -> E.Leg:
    return E.Leg(role=role, market=market, selection=selection, side=side, price=prezzo,
                 size=abbinato if size is None else size, matched=abbinato,
                 avg_price=prezzo if abbinato > 0 else None, ref=ref, status=status,
                 placed_at=KO)


def ingresso(stake=10.0):
    return gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, stake,
                 ref="under_entry-0-1")


def libro(bb, bl, status="OPEN"):
    return E.Book(best_back=bb, back_size=500.0, best_lay=bl, lay_size=500.0,
                  status=status, inplay=True)


def foto(*, now=KO + 1200, goals=0, u45=None, o45=None):
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(1.45, 1.46),
             (E.MARKET_OU45, E.SEL_UNDER): u45 or libro(1.17, 1.18),
             (E.MARKET_OU45, E.SEL_OVER): o45 or libro(6.6, 6.8)}
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=20,
                      goals=goals, feed_fresh=True, order_fresh=True)


def _posti(d):
    return [a for a in d.actions if a.kind == "place"]


# ---------------------------------------------------------------------------
# A1 (N3): valore sconosciuto = forma di prima
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("valore", ["qualunque", "", None, "LAY_UNDER45", 3])
def test_cover_form_sconosciuto_e_la_forma_di_prima(valore):
    assert E.cover_form({"cover_form": valore}) == E.COVER_BACK_O45
    assert E.cover_form({}) == E.COVER_BACK_O45
    # i parametri passano da ``merge_params``: un valore non previsto torna al
    # valore di SERIE (dal blocco 5 la banca), mai a un valore inventato
    assert C.merge_params({"cover_form": valore})["cover_form"] == C.DEFAULTS["cover_form"]


# ---------------------------------------------------------------------------
# A2 (N13): mercato Under 4,5 SOSPESO con i prezzi presenti
# ---------------------------------------------------------------------------
def test_banca_con_under45_sospeso_non_parte():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    d = E.decide(ctx, foto(u45=libro(1.17, 1.18, status="SUSPENDED")), params())
    assert _posti(d) == [] and d.state == "LIVE_UNCOVERED"
    assert d.reason == "copertura: mercato Under 4.5 sospeso, si aspetta la riapertura"


# ---------------------------------------------------------------------------
# A3 (N14): troppi gol nella forma banca
# ---------------------------------------------------------------------------
def test_banca_troppi_gol_copertura_saltata():
    p = params()
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    d = E.decide(ctx, foto(goals=int(p["cover_max_goals"]) + 1), p)
    assert _posti(d) == []
    assert d.reason == "copertura saltata: troppi gol"


# ---------------------------------------------------------------------------
# A4 (N15): tranche della banca sotto 0,50 -> in una volta, mai due tranche
# ---------------------------------------------------------------------------
def test_tranche_della_banca_sotto_0_50_si_copre_in_una_volta():
    # liability 0,50 -> banca piena 0,63; la meta' (0,32) sarebbe sotto 0,50
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso(0.5)], cover_stage=1,
                     early_goal_at=KO + 600)
    d = E.decide(ctx, foto(goals=1), params())
    [a] = _posti(d)
    assert (a.side, a.size) == ("lay", 0.63)
    assert d.telemetry["cover"]["split_declassato"] is True
    assert d.updates.get("cover_stage") == 0


# ---------------------------------------------------------------------------
# A5 (N17): riprezzo della banca a mercato Under 4,5 sospeso
# ---------------------------------------------------------------------------
def test_riprezzo_della_banca_a_mercato_sospeso_non_tocca_niente():
    viva = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 0.0,
                 ref="over_cover-0-2", status="pending", size=12.63)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[ingresso(), viva])
    d = E._decide_cover_pending(ctx, foto(now=KO + 5000,
                                          u45=libro(1.20, 1.21, status="SUSPENDED")),
                                params(), COMM)
    assert d.actions == [] and d.state == "LIVE_COVER_PENDING"
    assert "nessun riprezzo" in d.reason


# ---------------------------------------------------------------------------
# A6 (N21): forma di prima, chiusura sotto 0,50 = identica a prima del pacchetto
# ---------------------------------------------------------------------------
def test_forma_di_prima_chiusura_sotto_0_50_identica_a_prima():
    """Punta Over 2,00 a 6,00; banca Over a 30 = 0,40 (sotto 0,50). La puntata
    equivalente sull'Under a 1,20 sarebbe 10,00 (multiplo di 0,50): proprio il
    caso in cui il ripiego scatterebbe. Nella forma di prima NON deve: resta la
    banca Over 0,40, l'ordine di prima."""
    punta = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.0, 2.0,
                  ref="over_cover-0-2")
    books = {(E.MARKET_OU45, E.SEL_OVER): libro(29.0, 30.0),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.20, 1.21)}
    cv = E.cashout_value([punta], books, COMM)
    assert cv.ripieghi == {}
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[punta])
    [a] = [x for x in E._close_actions(ctx, cv, params()) if x.kind == "place"]
    assert (a.role, a.selection, a.side, a.size, a.price) == ("over_close", E.SEL_OVER,
                                                             "lay", 0.4, 30.0)


# ---------------------------------------------------------------------------
# B: contratto dell'impronta del referto
# ---------------------------------------------------------------------------
def _moduli_mike_importati_dal_servizio():
    radice = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(radice, "service.py"), encoding="utf-8") as fh:
        albero = ast.parse(fh.read())
    locali = {n[:-3] for n in os.listdir(radice) if n.endswith(".py")}
    trovati = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.ImportFrom):
            if nodo.level == 1 and nodo.module is None:
                trovati |= {a.name for a in nodo.names if a.name in locali}
            elif nodo.level == 1 and nodo.module:
                trovati.add(nodo.module.split(".")[0])
            elif (nodo.module or "").startswith("Betfair.mike."):
                trovati.add(nodo.module.split(".")[2])
        elif isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name.startswith("Betfair.mike."):
                    trovati.add(a.name.split(".")[2])
    return {f"Betfair.mike.{m}" for m in trovati if m in locali}


def test_impronta_di_mike_contiene_ogni_modulo_importato_dal_servizio():
    from Betfair.stream.backtest import registro_bot as REG

    scheda = REG.bot("mike")
    mancanti = _moduli_mike_importati_dal_servizio() - set(scheda.moduli_produzione)
    assert "Betfair.mike.engine" in _moduli_mike_importati_dal_servizio()
    assert mancanti == set(), f"moduli di Mike fuori dall'impronta del referto: {mancanti}"


def test_l_impronta_cambia_se_cambia_il_motore(monkeypatch, tmp_path):
    """L'impronta legge i file dei moduli di produzione: un motore diverso
    (copia in una cartella temporanea) da' un'impronta diversa."""
    from Betfair.stream.backtest import certifica as CE
    from Betfair.stream.backtest import registro_bot as REG

    radice = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    monkeypatch.chdir(radice)
    scheda = REG.bot("mike")
    prima = CE.impronta(scheda)["codice_bot"]
    copia = tmp_path / "Betfair" / "mike"
    copia.mkdir(parents=True)
    for m in list(scheda.moduli_produzione) + [scheda.controlli]:
        rel = os.path.join(*m.split(".")) + ".py"
        testo = open(os.path.join(radice, rel), "rb").read()
        if m == "Betfair.mike.engine":
            testo += b"\n# motore cambiato\n"
        (tmp_path / rel).write_bytes(testo)
    monkeypatch.chdir(tmp_path)
    dopo = CE.impronta(scheda)["codice_bot"]
    assert prima != dopo and prima.endswith("(8 file)") and dopo.endswith("(8 file)")
