"""TESTI DEI MOTIVI DI MIKE: «copertura sulla linea 4,5», non «copertura Over 4.5» (30/09).

Di serie la copertura e' una BANCA sull'Under 4,5 (``cover_form='lay_under45'``):
scrivere «copertura Over 4.5» nel diario e nella proposta confondeva il trader
(audit UI, reperto A4). I motivi sono solo testo: nessun codice li confronta per
decidere (verificato con grep), quindi qui si fissano le parole nuove.

File ASCII-only.
"""
from __future__ import annotations

import ast
import pathlib

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_700_000_000.0
PAR = C.merge_params(None)
FINESTRA = float(PAR["ko_green_window_s"])


def _book(bb, status="OPEN"):
    return E.Book(best_back=bb, back_size=200.0, best_lay=round(bb + 0.02, 2), lay_size=200.0,
                  status=status, inplay=True)


def _snap(now, *, o45=None):
    books = {(E.MARKET_OU35, E.SEL_UNDER): _book(2.10),
             (E.MARKET_OU45, E.SEL_UNDER): _book(1.18),
             (E.MARKET_OU45, E.SEL_OVER): o45 or _book(6.0)}
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=20,
                      goals=0, feed_fresh=True, order_fresh=True)


def _ingresso():
    return E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                 side="back", price=2.12, size=5.0, matched=5.0, avg_price=2.12,
                 ref="under_entry-0-1", status="open", placed_at=KO - 600)


def test_uscita_non_abbinata_allo_scadere_dice_copertura_sulla_linea_45():
    banca = E.Leg(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=2.08, size=5.10, ref="ko_green-0-3", status="pending",
                  placed_at=KO + 1.0)
    ctx = E.MatchCtx(state="LIVE_KO_GREEN", legs=[_ingresso(), banca], live_since=KO, ko_goals=0)
    d = E.decide(ctx, _snap(KO + FINESTRA + 1.0), PAR)
    assert d.state == "LIVE_UNCOVERED"
    assert d.reason == "uscita non abbinata in %d': copertura sulla linea 4,5" % int(FINESTRA // 60)


def test_forma_punta_over_con_mercato_sospeso_dice_mercato_della_linea_45():
    p = dict(PAR)
    p["cover_form"] = E.COVER_BACK_O45
    p["uscite_automatiche"] = True
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[_ingresso()])
    d = E.decide(ctx, _snap(KO + 1200, o45=_book(6.0, status="SUSPENDED")), p)
    assert d.reason == "copertura: mercato della linea 4,5 sospeso, si aspetta la riapertura"


def test_nessun_testo_di_motivo_dice_ancora_copertura_over_45():
    """Guardia sul sorgente: nessuna STRINGA (docstring e commenti esclusi) del
    motore dice «copertura Over 4.5» o «mercato Over 4.5»."""
    src = pathlib.Path(E.__file__).read_text(encoding="utf-8")
    albero = ast.parse(src)
    docstring = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            corpo = getattr(nodo, "body", [])
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(
                    getattr(corpo[0], "value", None), ast.Constant):
                docstring.add(id(corpo[0].value))
    cattivi = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) \
                and id(nodo) not in docstring:
            if "copertura Over 4.5" in nodo.value or "mercato Over 4.5" in nodo.value:
                cattivi.append((nodo.lineno, nodo.value))
    assert cattivi == [], cattivi
    # e le parole nuove ci sono (gol precoce, tranche)
    assert "gol precoce: copertura sulla linea 4,5" in src
    assert "copertura sulla linea 4,5: prima tranche" in src
