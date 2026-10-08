"""CANTIERE 9 (08/10) - reperto 7.2 del cantiere 5: `uscite_manuali.e_parcheggio`.

Dal 07/10 (calcio, `scalper_bot.stato_parcheggio`) e dall'08/10 (tennis,
`condotta_ordini.stato_parcheggio`) il parcheggio LAY del place-and-trim sta alla
quota di `trading.submin.quota_parcheggio_lontano(lato, resto)`: 1,02 per i resti
0,50-0,62, 1,03 per 0,63-0,79, 1,01 per 0,80-0,99. L'osservatore delle uscite
firmate (UF2) lo riconosceva SOLO a 1,01: con un parcheggio a 1,02/1,03
  (a) contava il residuo VIVO del parcheggio come importo d'uscita e giudicava
      subito invece di aspettare la fine della catena;
  (b) non agganciava i rimpiazzi della catena nati dopo la finestra.

Finti: la strategia con `cancello_uscite` (l'attributo vero, `CancelloUscite` di
produzione) e ordini con le chiavi di flumine (`id`, `selection_id`, `side`,
`size_matched`, `size_remaining`, `size_cancelled`, `order_type.price`,
`order_type.size`, `trade.orders`), come i test N3 del 28/09.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from Betfair.stream import uscite_proposte as UP
from Betfair.stream.backtest import uscite_manuali as UM
from Betfair.stream.tennis_scalper.condotta_ordini import QUOTE_PARCHEGGIO_LAY
from Betfair.stream.trading.submin import initial_place_price, quota_parcheggio_lontano

CHIAVE = "scalper|1.9|7|o1|stop"


class _Strategia:
    def __init__(self) -> None:
        self.cancello_uscite = UP.CancelloUscite()
        self.ordini: List[Any] = []


def _proposta(size: float) -> dict:
    # posizione BACK in perdita: la chiusura e' una BANCA (lato LAY)
    return UP.proposta_di(bot="scalper", motivo="stop", market_id="1.9", selection_id=7,
                          lato_ingresso="BACK", prezzo=2.0, lato_chiusura="LAY",
                          size_chiusura=size, se_chiudi=-0.5, se_vince=1.0, se_perde=-2.0)


def _ol(oid: str, price: float, size: float, matched: float, remaining: float,
        cancelled: float = 0.0, trade: Any = None) -> Any:
    o = SimpleNamespace(id=oid, selection_id=7, side="LAY", size_matched=matched,
                        size_remaining=remaining, size_cancelled=cancelled,
                        order_type=SimpleNamespace(price=price, size=size), trade=trade)
    if trade is not None:
        trade.orders.append(o)
    return o


def _oss(s: _Strategia) -> UM.Osservatore:
    firme: dict = {}

    def _firma(chiave: str, istante: str) -> None:
        firme[chiave] = istante
        UP.applica_firme([s], {UP.CHIAVE_FIRME: dict(firme)})

    return UM.Osservatore(UM.SCENARIO_FIRMATE, strategie=lambda: [s],
                          ordini_di=lambda st: st.ordini, firma=_firma)


def _eseguita(s: _Strategia, o: UM.Osservatore, size: float) -> None:
    c = s.cancello_uscite
    c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0, proposta=_proposta(size))
    o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))
    assert c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=15.5,
                           proposta=_proposta(size)) is True


FINE_FINESTRA = int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1


# ---------------------------------------------------------------- la quota
def test_le_quote_lay_della_fonte_unica_sono_quelle_del_resto():
    """La tupla non e' scritta a mano: e' l'insieme delle quote che la fonte
    unica da' ai resti 0,50-0,99 (e contiene la 1,01 di sempre)."""
    attese = {quota_parcheggio_lontano("lay", c / 100.0) for c in range(50, 100)}
    assert set(QUOTE_PARCHEGGIO_LAY) == attese
    assert initial_place_price("lay") in QUOTE_PARCHEGGIO_LAY
    assert len(QUOTE_PARCHEGGIO_LAY) >= 2


@pytest.mark.parametrize("centesimi", list(range(50, 100)))
def test_e_parcheggio_riconosce_il_parcheggio_lay_di_ogni_resto(centesimi):
    q = quota_parcheggio_lontano("lay", centesimi / 100.0)
    assert UM.e_parcheggio(_ol("p", q, 1.0, 0.0, centesimi / 100.0)), q


def test_e_parcheggio_non_scambia_per_parcheggio_le_quote_vere():
    assert not UM.e_parcheggio(_ol("d", 1.04, 1.0, 0.0, 1.0))
    assert not UM.e_parcheggio(_ol("d", 2.0, 1.0, 0.0, 1.0))
    # BACK: invariato, solo 1000
    back = SimpleNamespace(side="BACK", order_type=SimpleNamespace(price=1.02))
    assert not UM.e_parcheggio(back)
    assert UM.e_parcheggio(SimpleNamespace(side="BACK",
                                           order_type=SimpleNamespace(price=1000.0)))


# ---------------------------------------------------------------- UF2 sulla catena
@pytest.mark.parametrize("resto", [0.55, 0.70])
def test_uf2_catena_lay_a_quota_in_banda_aspetta_e_aggancia_il_rimpiazzo(resto):
    """Uscita firmata LAY 2,00 + resto: diretta 2,00 abbinata e parcheggio LAY
    1,00 alla quota della fonte unica (1,02 per 0,55, 1,03 per 0,70), ancora
    INTERO alla fine della finestra. UF2 deve aspettare la catena (non contare
    1,00 di parcheggio vivo come uscita) e poi agganciare il rimpiazzo nato
    DOPO la finestra."""
    q = quota_parcheggio_lontano("lay", resto)
    assert q in (1.02, 1.03)
    size = round(2.0 + resto, 2)
    s = _Strategia()
    o = _oss(s)
    with o.attivo():
        _eseguita(s, o, size)
        seq = SimpleNamespace(orders=[])
        s.ordini.append(_ol("d", 2.0, 2.0, 2.0, 0.0))
        park = _ol("p", q, 1.0, 0.0, 1.0, trade=seq)
        s.ordini.append(park)
        o.giro(FINE_FINESTRA)                   # parcheggio vivo: si aspetta
        assert "UF2" not in o.sollecitati and o.violazioni == [], o.violazioni
        # gradini 2-3: tagliato al resto e rimpiazzato alla quota vera, DOPO la finestra
        park.size_remaining, park.size_cancelled = 0.0, 1.0
        s.ordini.append(_ol("r", 2.0, resto, resto, 0.0, trade=seq))
        o.giro(FINE_FINESTRA + 1_000)
    assert o.violazioni == [], o.violazioni
    assert o.sollecitati["UF2"] == 1


def test_uf2_catena_lay_1_03_con_rimpiazzo_gonfiato_resta_violazione():
    """La correzione non scusa niente: un rimpiazzo piu' grande del resto e' un
    importo d'uscita sbagliato anche con il parcheggio riconosciuto."""
    s = _Strategia()
    o = _oss(s)
    with o.attivo():
        _eseguita(s, o, 2.70)
        seq = SimpleNamespace(orders=[])
        s.ordini.append(_ol("d", 2.0, 2.0, 2.0, 0.0))
        s.ordini.append(_ol("p", 1.03, 1.0, 0.0, 0.0, cancelled=1.0, trade=seq))
        s.ordini.append(_ol("r", 2.0, 1.0, 1.0, 0.0, trade=seq))
        o.giro(FINE_FINESTRA)
    assert any(v[0] == "UF2" and "3.00" in v[2] for v in o.violazioni), o.violazioni


def test_uf2_parcheggio_lay_1_02_che_abbina_conta():
    """Un parcheggio che ABBINA sposta davvero la posizione: conta come uscita."""
    s = _Strategia()
    o = _oss(s)
    with o.attivo():
        _eseguita(s, o, 2.55)
        s.ordini += [_ol("d", 2.0, 2.0, 2.0, 0.0), _ol("p", 1.02, 1.0, 1.0, 0.0)]
        o.giro(FINE_FINESTRA)
    assert any(v[0] == "UF2" and "3.00" in v[2] for v in o.violazioni), o.violazioni
