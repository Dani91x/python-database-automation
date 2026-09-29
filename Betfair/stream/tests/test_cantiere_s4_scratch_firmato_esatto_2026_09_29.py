"""CANTIERE S4 (29/09) - scalper calcio: lo SCRATCH firmato parte all'importo
ESATTO della proposta, subito, anche se la close a target (firmata poco prima)
aveva appena avviato una sequenza place-and-trim.

Reperto (sonda S4 sul replay 35797769, `uscite-manuali-firmate`, selezione 22
del mercato 1.259819674, `AUDIT_2026-09-28/cantiere_s/traccia_s4.txt`):
LAY 25 @1,65 abbinata per 2,80; la target firmata parte a 2,78 (2,50 + 0,28 col
place-and-trim); 7 s dopo lo SCRATCH firmato (proposta BACK 2,80 @1,65) ritira
la close e piazza 2,50 diretti, ma il resto 0,30 era `min_bet_skip`: la pausa
anti-cascata di 30 s era stata consumata dalla sequenza della target. I 0,30
restavano scoperti ~20 minuti (poi chiusi dal flatten a 1,64). UF2 del banco:
"proposta 2,80, uscita 2,50".

Bot VERO su Flumine vero (client paper, esecuzione differita di 1 e 4 book),
come i test S: il test passa solo da `process_market_book`.
"""
from __future__ import annotations

from typing import Any

from Betfair.stream.tests import test_cantiere_s_scalper_ko_2026_09_29 as SCT
from Betfair.stream.tests.test_cantiere_s_scalper_ko_2026_09_29 import (  # noqa: F401
    differita,
    esecuzione_differita,
    orologio_mercato,
)

SEL = SCT.SEL


def _importo_a_quota(b: Any, prezzo: float) -> float:
    """BACK a quota abbinabile `prezzo`: abbinato + residuo, parcheggi esclusi
    (la stessa misura del controllo UF2)."""
    tot = 0.0
    for o in b.market.blotter.strategy_orders(b.strat):
        if (int(o.selection_id) == SEL and o.side == "BACK"
                and abs(float(o.order_type.price) - prezzo) < 1e-9):
            tot += float(o.size_matched) + float(o.size_remaining)
    return round(tot, 2)


def test_scratch_firmato_parte_esatto_subito_dopo_la_target(differita, orologio_mercato):
    b = SCT.Banco(uscite_automatiche=False)
    orologio_mercato["banco"] = b
    b.pt = SCT.KO_MS - 3_000_000
    b.ladder[SEL] = (1.64, 1.65)          # il touch e' al prezzo d'ingresso: scratch
    b.senza_scambi.add(SEL)               # niente si abbina: si misura cosa parte
    b.book()
    slot = b.slot()
    slot.entry = b.abbinato("LAY", 1.65, 2.8)
    slot.entry_side = "LAY"
    canc = b.strat.cancello_uscite
    # la target: proposta, firma, esecuzione (BACK 2,78 @1,66 = 2,50 + 0,28)
    b.strat._open_lock(b.market, slot, b.pt, slot.entry, 1.64, 1.65)
    target = [p for p in canc.vive() if p.get("motivo") == "target"][0]
    canc.approvate[target["chiave"]] = b.pt / 1000.0
    for _ in range(3):
        differita()
        b.book()
    assert _importo_a_quota(b, 1.66) >= 2.5, "la target firmata deve essere partita"
    # lo scratch: proposto dal bot (il touch e' al prezzo d'ingresso), firmato
    scratch = [p for p in canc.vive() if p.get("motivo") == "scratch"]
    assert scratch, [p.get("motivo") for p in canc.vive()]
    proposta = float(scratch[0]["size_chiusura"])
    assert abs(proposta - 2.8) < 1e-9
    canc.approvate[scratch[0]["chiave"]] = b.pt / 1000.0
    for _ in range(25):                   # dentro la pausa di 30 s
        differita()
        b.book()
    assert [r for r in b.righe if r[0] == "scratch"], "lo scratch firmato deve partire"
    assert _importo_a_quota(b, 1.65) == proposta, (
        _importo_a_quota(b, 1.65), proposta,
        [r for r in b.righe if r[0] in ("min_bet_skip", "submin_start", "place")])
    assert not [r for r in b.righe if r[0] == "min_bet_skip"
                and abs(float(r[1].get("size") or 0) - 0.30) < 1e-9]
