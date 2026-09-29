"""CANTIERE S3 (29/09) - UF2: ogni uscita firmata conta SOLO i propri ordini.

Reperto (sonda del cantiere S2 sul replay 35797769, `uscite-manuali-firmate`,
`AUDIT_2026-09-28/cantiere_s/traccia_uf2.txt` righe 9-26): sulla stessa
posizione (LAY 25 @4,2) il banco firma la TARGET (BACK 24,42 @4,3) e lo SCRATCH
(BACK 25,00 @4,2). La target parte esatta (24,00 diretti + parcheggio 2,00 @1000
ridotto a 0,42 e rimpiazzato); 9 s dopo lo scratch firmato ritira la close a
target (condotta di sempre, anche in automatico) e piazza BACK 25,00, abbinata.
Il vecchio UF2 attribuiva alla target TUTTI gli ordini BACK nati dopo la sua
firma, scratch compreso: "proposta 24,42, uscita 25,00".

Finti con le chiavi di flumine (`id`, `selection_id`, `side`, `size_matched`,
`size_remaining`, `order_type.price/size`, `trade.orders`) come nei test N3; il
cancello e' quello VERO (`uscite_proposte.CancelloUscite`).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from Betfair.stream import uscite_proposte as UP
from Betfair.stream.backtest import uscite_manuali as UM
from Betfair.stream.tests.test_banco_uscite_manuali_n3_2026_09_28 import (
    _Strategia,
    _codici,
    _oss,
)

MID, SEL = "1.259819674", 58805
POS = "scalper|%s|%d|140099680546292522|" % (MID, SEL)
TARGET, SCRATCH = POS + "target", POS + "scratch"


def _prop(motivo: str, size: float, prezzo: float, sel: int = SEL) -> dict:
    return UP.proposta_di(bot="scalper", motivo=motivo, market_id=MID, selection_id=sel,
                          lato_ingresso="LAY", prezzo=prezzo, lato_chiusura="BACK",
                          size_chiusura=size, se_chiudi=0.58, se_vince=-80.0, se_perde=25.0)


def _o(oid: str, price: float, size: float, matched: float, remaining: float,
       trade: Any = None, sel: int = SEL, side: str = "BACK") -> Any:
    o = SimpleNamespace(id=oid, selection_id=sel, side=side, size_matched=matched,
                        size_remaining=remaining, size_cancelled=0.0,
                        order_type=SimpleNamespace(price=price, size=size), trade=trade)
    if trade is not None:
        trade.orders.append(o)
    return o


def _firma_le_due(s: _Strategia, o: UM.Osservatore, size_target: float = 24.42,
                  size_scratch: float = 25.0) -> None:
    c = s.cancello_uscite
    assert c.lascia_uscire(automatiche=False, chiave=TARGET, now_s=10.0,
                           proposta=_prop("target", size_target, 4.3)) is False
    assert c.lascia_uscire(automatiche=False, chiave=SCRATCH, now_s=10.4,
                           proposta=_prop("scratch", size_scratch, 4.2)) is False
    o.giro(15_500)                               # il banco firma le due proposte
    assert o.firme_date == 2


def _esegui(s: _Strategia, o: UM.Osservatore, chiave: str, t_s: float, prop: dict) -> None:
    o.giro(int(t_s * 1000))
    assert s.cancello_uscite.lascia_uscire(automatiche=False, chiave=chiave, now_s=t_s,
                                           proposta=prop) is True


def _traccia(s: _Strategia, o: UM.Osservatore, *, target_diretto: float = 24.0,
             sost: float = 0.42, sost_abbinato: bool = False, scratch: float = 25.0,
             extra_dopo: List[Any] = ()) -> None:
    """Il reperto: target eseguita a 18,6 s, scratch eseguito a 27,2 s."""
    _firma_le_due(s, o)
    _esegui(s, o, TARGET, 18.6, _prop("target", 24.42, 4.3))
    seq = SimpleNamespace(orders=[])
    diretto = _o("d24", 4.3, target_diretto, 0.0, target_diretto)
    park = _o("park", 1000.0, 2.0, 0.0, 2.0, trade=seq)
    s.ordini += [diretto, park]
    o.giro(20_000)
    _esegui(s, o, SCRATCH, 27.2, _prop("scratch", 25.0, 4.2))
    # lo scratch ritira la close a target; la catena finisce col rimpiazzo
    diretto.size_remaining = 0.0
    park.size_remaining = 0.0
    sostituto = _o("sost", 4.3, sost, sost if sost_abbinato else 0.0, 0.0, trade=seq)
    s.ordini += [sostituto, _o("scr25", 4.2, scratch, scratch, 0.0)]
    s.ordini += list(extra_dopo)
    o.giro(40_000)
    o.giro(60_000, fine=True)


def test_reperto_target_poi_scratch_firmati_nessuna_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _traccia(s, o)
    assert o.violazioni == [], o.violazioni
    assert o.eseguite == 2 and o.sollecitati["UF2"] == 2


def test_sostituto_della_target_abbinato_dopo_lo_scratch_resta_della_target():
    """Il rimpiazzo della catena della target nasce (e si abbina) DOPO
    l'esecuzione dello scratch: e' della target, non dello scratch."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _traccia(s, o, sost_abbinato=True)
    assert o.violazioni == [], o.violazioni


# ------------------------------------------------------ i casi che restano ROSSI
def test_firmata_a_importo_diverso_senza_seconda_firma_resta_rossa():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _firma_le_due(s, o)
        _esegui(s, o, TARGET, 18.6, _prop("target", 24.42, 4.3))
        s.ordini.append(_o("d25", 4.3, 25.0, 25.0, 0.0))        # 25,00 per 24,42
        o.giro(40_000)
        o.giro(60_000, fine=True)
    assert any(v[0] == "UF2" and TARGET in v[2] and "25.00" in v[2]
               for v in o.violazioni), o.violazioni


def test_seconda_firma_a_importo_diverso_dalla_sua_proposta_resta_rossa():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _traccia(s, o, scratch=24.0)                          # scratch 24,00 per 25,00
    assert any(v[0] == "UF2" and SCRATCH in v[2] for v in o.violazioni), o.violazioni
    assert not any(v[0] == "UF2" and TARGET in v[2] for v in o.violazioni), o.violazioni


def test_ordine_dopo_la_seconda_firma_non_giustificato_resta_rosso():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _traccia(s, o, extra_dopo=[_o("x3", 4.2, 3.0, 3.0, 0.0)])
    assert any(v[0] == "UF2" and SCRATCH in v[2] and "28.00" in v[2]
               for v in o.violazioni), o.violazioni


def test_target_superata_che_aveva_piazzato_un_importo_sbagliato_resta_rossa():
    """Superata dallo scratch, la target si giudica su quanto ha PIAZZATO:
    23,00 + 0,42 per una proposta da 24,42 e' sbagliato."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _traccia(s, o, target_diretto=23.0)
    assert any(v[0] == "UF2" and TARGET in v[2] and "23.42" in v[2]
               for v in o.violazioni), o.violazioni


def test_la_firma_di_un_altra_selezione_non_chiude_la_finestra():
    """Target sulla 58805 eseguita; poi si esegue una firma sulla selezione 22
    dello stesso mercato; gli ordini della target nascono DOPO: restano suoi."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    altra = "scalper|%s|22|e2|target" % MID
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=TARGET, now_s=10.0,
                        proposta=_prop("target", 24.42, 4.3))
        c.lascia_uscire(automatiche=False, chiave=altra, now_s=10.2,
                        proposta=_prop("target", 3.0, 1.66, sel=22))
        o.giro(15_500)
        _esegui(s, o, TARGET, 16.0, _prop("target", 24.42, 4.3))
        _esegui(s, o, altra, 16.5, _prop("target", 3.0, 1.66, sel=22))
        s.ordini += [_o("a3", 1.66, 3.0, 3.0, 0.0, sel=22),
                     _o("d24", 4.3, 24.0, 24.0, 0.0), _o("d042", 4.3, 0.42, 0.42, 0.0)]
        o.giro(40_000)
        o.giro(60_000, fine=True)
    assert o.violazioni == [], o.violazioni
    assert o.sollecitati["UF2"] == 2


def test_seconda_firma_dentro_la_finestra_della_prima():
    """Lo scratch firmato si esegue 3 s dopo la target (dentro la finestra di 5 s
    della target): gli ordini dello scratch non sono della target."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _firma_le_due(s, o)
        _esegui(s, o, TARGET, 18.6, _prop("target", 24.42, 4.3))
        seq = SimpleNamespace(orders=[])
        diretto = _o("d24", 4.3, 24.0, 0.0, 24.0)
        park = _o("park", 1000.0, 2.0, 0.0, 2.0, trade=seq)
        s.ordini += [diretto, park]
        _esegui(s, o, SCRATCH, 21.6, _prop("scratch", 25.0, 4.2))
        diretto.size_remaining = 0.0
        park.size_remaining = 0.0
        s.ordini += [_o("sost", 4.3, 0.42, 0.0, 0.0, trade=seq),
                     _o("scr25", 4.2, 25.0, 25.0, 0.0)]
        o.giro(40_000)
        o.giro(60_000, fine=True)
    assert o.violazioni == [], o.violazioni
    assert o.sollecitati["UF2"] == 2
