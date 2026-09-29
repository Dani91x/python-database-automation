"""CANTIERE N3 (28/09) - i controlli del banco a USCITE MANUALI (UM1-UM4, UF1-UF3).

L'osservatore (`backtest/uscite_manuali.py`) avvolge il cancello VERO
(`uscite_proposte.CancelloUscite`): qui gli si danno decisioni vere del
cancello e, per provare che ogni controllo sa diventare rosso, cancelli
GUASTI (una firma che vale due volte, una firma che sopravvive alla sua
proposta, un'uscita che parte senza firma).

Finti: una strategia con `cancello_uscite` (l'attributo vero) e ordini con le
chiavi di flumine (`id`, `selection_id`, `side`, `size_matched`,
`size_remaining`, `order_type.size`).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from Betfair.stream import uscite_proposte as UP
from Betfair.stream.backtest import uscite_manuali as UM
from Betfair.stream.scalper.tools import replay_registrazioni as RR
from Betfair.stream.tennis_live.tools import replay_bot as RB

CHIAVE = "scalper|1.9|7|o1|stop"


def _proposta(**over: Any) -> dict:
    p = UP.proposta_di(bot="scalper", motivo="stop", market_id="1.9", selection_id=7,
                       lato_ingresso="BACK", prezzo=2.3, lato_chiusura="LAY",
                       size_chiusura=10.0, se_chiudi=-0.5, se_vince=1.0, se_perde=-2.0)
    p.update(over)
    return p


class _Strategia:
    def __init__(self) -> None:
        self.cancello_uscite = UP.CancelloUscite()
        self.ordini: List[Any] = []


def _ordine(oid: str, *, sel: int = 7, side: str = "LAY", size: float = 10.0,
            matched: float = 10.0, remaining: float = 0.0) -> Any:
    return SimpleNamespace(id=oid, selection_id=sel, side=side, size_matched=matched,
                           size_remaining=remaining,
                           order_type=SimpleNamespace(size=size))


def _oss(scenario: str, s: _Strategia, firme: dict, **k: Any) -> UM.Osservatore:
    def _firma(chiave: str, istante: str) -> None:
        firme[chiave] = istante
        # la via di produzione: la riga riletta passa le firme ai bot vivi
        UP.applica_firme([s], {UP.CHIAVE_FIRME: dict(firme)})

    return UM.Osservatore(scenario, strategie=lambda: [s], ordini_di=lambda st: st.ordini,
                          firma=_firma if scenario == UM.SCENARIO_FIRMATE else None, **k)


def _codici(o: UM.Osservatore) -> List[str]:
    return [v[0] for v in o.violazioni]


# ---------------------------------------------------------------- scenari
def test_scenari_registrati_nei_due_banchi():
    for sc in UM.SCENARI:
        assert sc in RB.SCENARI_DESCRITTI and sc in RR.SCENARI_DESCRITTI
        assert RB.uscite_automatiche_scenario(sc) is False
        assert RR.control_della_ui("1", sc)["params"]["uscite_automatiche"] is False
        assert RR.control_della_ui("1", sc)["params"]["sniper_mode"] is True
        assert RR.sniper_acceso(sc)
        # tennis: i gate di `gate-aperto` (senza, swing e scalper non aprono)
        for bot in ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"):
            assert RB.parametri_scenario(sc, bot) == RB.parametri_scenario("gate-aperto", bot)


# ---------------------------------------------------------------- UM1-UM2
def test_manuale_decisione_diventa_proposta_e_niente_parte():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        c = s.cancello_uscite
        for t in (10.0, 11.0, 12.0):
            assert c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=t,
                                   proposta=_proposta()) is False
        o.giro(12_000, fine=True)
    assert o.violazioni == []
    assert o.sollecitati["UM1"] == 3 and o.sollecitati["UM2"] == 3
    assert o.proposte_nate == 1


def test_um1_interruttore_acceso_in_scenario_manuale_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        s.cancello_uscite.lascia_uscire(automatiche=True, chiave=CHIAVE, now_s=1.0,
                                        proposta=_proposta())
    assert any(v[0] == "UM1" and "AUTOMATICHE" in v[2] for v in o.violazioni)


def test_um1_uscita_eseguita_con_una_firma_non_del_banco_e_violazione():
    """Nello scenario SENZA firme qualcuno firma lo stesso: l'uscita parte ed e'
    un'uscita di trading senza l'utente."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=1.0, proposta=_proposta())
        c.approva({CHIAVE: 2.0})
        assert c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=3.0,
                               proposta=_proposta()) is True
    assert "UM1" in _codici(o)


def test_um2_decisione_senza_proposta_e_violazione(monkeypatch):
    """Un cancello guasto che non registra la proposta."""
    def _guasto(self, *, automatiche, chiave, now_s, proposta):
        return False

    monkeypatch.setattr(UP.CancelloUscite, "lascia_uscire", _guasto)
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        s.cancello_uscite.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=1.0,
                                        proposta=_proposta())
    assert any(v[0] == "UM2" and "senza proposta viva" in v[2] for v in o.violazioni)


def test_um2_proposta_senza_i_numeri_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        s.cancello_uscite.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=1.0,
                                        proposta={"motivo": "stop"})
    assert "UM2" in _codici(o)


# ---------------------------------------------------------------- UM3
def test_um3_una_protezione_che_passa_dal_cancello_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        s.cancello_uscite.lascia_uscire(automatiche=False, chiave="scalper|1.9|7|o1|flatten",
                                        now_s=1.0, proposta=_proposta(motivo="flatten"))
    assert "UM3" in _codici(o)


@pytest.mark.parametrize("difetto,rosso", [(None, False), ("maker con 1 slot aperti", True)])
def test_um3_fine_sessione_non_piatta_e_violazione(difetto, rosso):
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {}, piatto_a_fine=lambda: difetto)
    o.giro(1_000, fine=True)
    assert ("UM3" in _codici(o)) is rosso
    assert o.sollecitati.get("UM3") == 1


def test_um3_senza_fine_finestra_dichiarato_non_giudicato():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    o.giro(1_000, fine=True)
    assert o.violazioni == [] and "UM3" not in o.sollecitati
    assert any(n.startswith("UM3b") for n in o.non_giudicabili)


# ---------------------------------------------------------------- UM4
def test_um4_condizione_caduta_la_proposta_sparisce():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=1.0, proposta=_proposta())
        c.conferma_vive("scalper|1.9|7|o1|", [])
    assert o.violazioni == [] and o.sollecitati["UM4"] == 1 and o.decadute == 1
    assert s.cancello_uscite.vive() == []


def test_um4_proposta_che_resta_dopo_la_decadenza_e_violazione(monkeypatch):
    """Cancello guasto: annuncia la decadenza ma non toglie niente."""
    monkeypatch.setattr(UP.CancelloUscite, "_togli", lambda self, k: None)
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=1.0, proposta=_proposta())
        c.conferma_vive("scalper|1.9|7|o1|", [])
    assert "UM4" in _codici(o)


# ---------------------------------------------------------------- firmate
def _firmata_ed_eseguita(s: _Strategia, o: UM.Osservatore, *, ordini_dopo: List[Any]):
    c = s.cancello_uscite
    c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0, proposta=_proposta())
    o.giro(12_000)                                     # troppo presto: nessuna firma
    assert o.firme_date == 0
    o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))       # dopo N s: firma
    assert o.firme_date == 1 and c.firmata(CHIAVE)
    ok = c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=15.5, proposta=_proposta())
    s.ordini.extend(ordini_dopo)
    return ok


def test_firmata_parte_una_volta_all_importo_esatto():
    s = _Strategia()
    firme: dict = {}
    o = _oss(UM.SCENARIO_FIRMATE, s, firme)
    with o.attivo():
        assert _firmata_ed_eseguita(s, o, ordini_dopo=[_ordine("x1")]) is True
        # la stessa riga riletta: la firma consumata non riparte
        UP.applica_firme([s], {UP.CHIAVE_FIRME: dict(firme)})
        assert s.cancello_uscite.lascia_uscire(automatiche=False, chiave=CHIAVE,
                                               now_s=16.0, proposta=_proposta()) is False
        o.giro(int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1)
        o.giro(30_000, fine=True)
    assert o.violazioni == [], o.violazioni
    assert o.eseguite == 1 and o.sollecitati["UF1"] == 1 and o.sollecitati["UF2"] == 1
    # la firma ha il tipo della RPC (ISO con fuso)
    assert list(firme.values())[0].endswith("+00:00")


def test_uf1_una_firma_che_esegue_due_volte_e_violazione(monkeypatch):
    vero = UP.CancelloUscite.lascia_uscire

    def _guasto(self, *, automatiche, chiave, now_s, proposta):
        firma = self.approvate.get(chiave)
        ok = vero(self, automatiche=automatiche, chiave=chiave, now_s=now_s,
                  proposta=proposta)
        if ok and firma is not None:
            self.approvate[chiave] = firma                  # la firma non si consuma
            self.proposte.setdefault(chiave, {"decided_at": 10.0})
        return ok

    monkeypatch.setattr(UP.CancelloUscite, "lascia_uscire", _guasto)
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _firmata_ed_eseguita(s, o, ordini_dopo=[_ordine("x1")])
        s.cancello_uscite.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=16.0,
                                        proposta=_proposta())
    assert "UF1" in _codici(o)


@pytest.mark.parametrize("ordini,rosso", [
    ([_ordine("x1", size=10.0, matched=10.0)], False),
    ([_ordine("x1", size=10.0, matched=4.0, remaining=6.0)], False),
    ([_ordine("x1", size=7.0, matched=7.0)], True),                 # importo diverso
    ([_ordine("x1", side="BACK")], True),                            # lato sbagliato
    ([_ordine("x1", sel=8)], True),                                  # altra selezione
    ([], True),                                                      # non e' partita
])
def test_uf2_importo_esatto(ordini, rosso):
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _firmata_ed_eseguita(s, o, ordini_dopo=ordini)
        o.giro(int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1)
    assert ("UF2" in _codici(o)) is rosso, o.violazioni
    assert o.sollecitati["UF2"] == 1
    if not ordini:
        assert any("nessun ordine" in v[2] for v in o.violazioni)


# ---------------------------------------------------------------- UF2 e la catena di D2
# 29/09 (replay tennis_pro 35794049, `uscite-manuali-firmate`): lo stop firmato da
# 2,06 BACK parte ESATTO per la via di D2: 2,00 diretti @1,06 (abbinati) +
# parcheggio 2,00 @1000 (gradino 1), ridotto e rimpiazzato da 0,06 @1,06
# (abbinati). A +5 s il parcheggio era ancora vivo: il vecchio UF2 sommava 2,00 +
# 2,00 = 4,00. Qui la stessa catena con le chiavi di flumine.
CHIAVE_BACK = "tennis_pro|1.2|7|1|stop"


def _prop_back(size: float) -> dict:
    return _proposta(lato_chiusura="BACK", size_chiusura=size, motivo="stop")


def _ob(oid: str, price: float, size: float, matched: float, remaining: float,
        cancelled: float = 0.0, trade: Any = None) -> Any:
    o = SimpleNamespace(id=oid, selection_id=7, side="BACK", size_matched=matched,
                        size_remaining=remaining, size_cancelled=cancelled,
                        order_type=SimpleNamespace(price=price, size=size), trade=trade)
    if trade is not None:
        trade.orders.append(o)
    return o


def _eseguita_back(s: _Strategia, o: UM.Osservatore, size: float) -> None:
    c = s.cancello_uscite
    c.lascia_uscire(automatiche=False, chiave=CHIAVE_BACK, now_s=10.0, proposta=_prop_back(size))
    o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))
    assert c.lascia_uscire(automatiche=False, chiave=CHIAVE_BACK, now_s=15.5,
                           proposta=_prop_back(size)) is True


FINE_FINESTRA = int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1


def test_uf2_catena_d2_legittima_2_06_non_e_violazione_e_aspetta_la_fine():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _eseguita_back(s, o, 2.06)
        seq = SimpleNamespace(orders=[])
        s.ordini.append(_ob("d", 1.06, 2.0, 2.0, 0.0))
        park = _ob("p", 1000.0, 2.0, 0.0, 2.0, trade=seq)
        s.ordini.append(park)
        o.giro(FINE_FINESTRA)                      # parcheggio vivo: si aspetta
        assert "UF2" not in o.sollecitati and o.violazioni == []
        # gradino 2-3: ridotto e rimpiazzato alla quota vera (nato DOPO la finestra)
        park.size_remaining, park.size_cancelled = 0.0, 2.0
        s.ordini.append(_ob("r", 1.06, 0.06, 0.06, 0.0, trade=seq))
        o.giro(FINE_FINESTRA + 1_000)
    assert o.violazioni == [], o.violazioni
    assert o.sollecitati["UF2"] == 1


def test_uf2_uscita_gonfiata_4_00_abbinabili_per_2_06_resta_violazione():
    """Il caso (b): due ordini da 2,00 a quota di mercato per una proposta da
    2,06 (doppia chiusura). Nessuna catena, nessuna scusa."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _eseguita_back(s, o, 2.06)
        s.ordini += [_ob("d1", 1.06, 2.0, 2.0, 0.0), _ob("d2", 1.06, 2.0, 0.0, 2.0)]
        o.giro(FINE_FINESTRA)
    assert any(v[0] == "UF2" and "4.00" in v[2] for v in o.violazioni), o.violazioni


def test_uf2_parcheggio_che_ABBINA_a_1000_conta():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _eseguita_back(s, o, 2.06)
        s.ordini += [_ob("d", 1.06, 2.0, 2.0, 0.0), _ob("p", 1000.0, 2.0, 2.0, 0.0)]
        o.giro(FINE_FINESTRA)
    assert any(v[0] == "UF2" and "4.00" in v[2] for v in o.violazioni)


def test_uf2_catena_con_rimpiazzo_gonfiato_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _eseguita_back(s, o, 2.06)
        seq = SimpleNamespace(orders=[])
        s.ordini.append(_ob("d", 1.06, 2.0, 2.0, 0.0))
        s.ordini.append(_ob("p", 1000.0, 2.0, 0.0, 0.0, cancelled=2.0, trade=seq))
        s.ordini.append(_ob("r", 1.06, 2.0, 2.0, 0.0, trade=seq))     # rimpiazzo intero
        o.giro(FINE_FINESTRA)
    assert any(v[0] == "UF2" and "4.00" in v[2] for v in o.violazioni)


def test_uf2_parcheggio_mai_finito_si_giudica_a_fine_replay():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _eseguita_back(s, o, 2.06)
        s.ordini += [_ob("d", 1.06, 2.0, 2.0, 0.0), _ob("p", 1000.0, 2.0, 0.0, 2.0)]
        o.giro(FINE_FINESTRA)
        o.giro(FINE_FINESTRA + 60_000, fine=True)
    # a fine replay il resto 0,06 non e' mai arrivato a quota abbinabile
    assert any(v[0] == "UF2" and "2.00" in v[2] for v in o.violazioni)


# ---------------------------------------------------------------- UF2: ingressi e resto
def test_uf2_la_gamba_d_ingresso_del_ciclo_nuovo_non_e_l_uscita():
    """Replay scalper tennis: a +5 s dal target firmato (LAY 2,02 -> 2,00 @1,08
    abbinati) il maker ha gia' quotato il ciclo nuovo (BACK @1,09 + LAY @1,08):
    la LAY d'ingresso non e' l'uscita (credenza del bot)."""
    s = _Strategia()
    ingresso = _ordine("in", side="LAY", matched=0.0, remaining=2.0)
    ruolo = (lambda x: "ingresso" if x is ingresso else None)
    for con_ruolo, rosso in ((True, False), (False, True)):
        s = _Strategia()
        o = _oss(UM.SCENARIO_FIRMATE, s, {}, ruolo=ruolo if con_ruolo else None)
        with o.attivo():
            _firmata_ed_eseguita(s, o, ordini_dopo=[_ordine("x1"), ingresso])
            o.giro(int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1)
        assert ("UF2" in _codici(o)) is rosso, (con_ruolo, o.violazioni)


@pytest.mark.parametrize("proposta,eseguito,dichiarato,rosso", [
    (10.02, 10.0, True, False),      # resto 0,02 dichiarato dal bot: non giudicato
    (10.02, 10.0, False, True),      # resto non dichiarato: violazione
    (10.06, 10.0, True, True),       # 0,06 >= 0,05: mai scusato
    (9.98, 10.0, True, True),        # uscita PIU' grande: mai scusata
])
def test_uf2_resto_non_piazzabile_solo_se_il_bot_lo_dichiara(proposta, eseguito,
                                                              dichiarato, rosso):
    visti = []

    def _resto(st, sel, lato, resto):
        visti.append((sel, lato, resto))
        return dichiarato

    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {}, resto_non_piazzabile=_resto)
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0,
                        proposta=_proposta(size_chiusura=proposta))
        o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=15.5,
                        proposta=_proposta(size_chiusura=proposta))
        s.ordini.append(_ordine("x1", size=eseguito, matched=eseguito))
        o.giro(int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1)
    assert ("UF2" in _codici(o)) is rosso, o.violazioni
    if not rosso:
        assert visti == [(7, "LAY", 0.02)]
        assert any("NON piazzabile" in n for n in o.non_giudicabili)


def test_uf2_resto_dichiarato_e_nessun_ordine():
    """Proposta 0,01 (scalper tennis): niente parte, il bot dichiara il resto."""
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {}, resto_non_piazzabile=lambda *a: True)
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0,
                        proposta=_proposta(size_chiusura=0.01))
        o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=15.5,
                        proposta=_proposta(size_chiusura=0.01))
        o.giro(int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1)
    assert o.violazioni == []


def test_resto_dichiarato_dal_bot_tennis_legge_la_memoria_del_bot():
    s = SimpleNamespace(_min_bet_detto={(10372252, "LAY", 0.02)})
    assert RB.resto_dichiarato_dal_bot(s, 10372252, "LAY", 0.02) is True
    assert RB.resto_dichiarato_dal_bot(s, 10372252, "BACK", 0.02) is False
    assert RB.resto_dichiarato_dal_bot(s, 10372252, "LAY", 0.03) is False
    assert RB.resto_dichiarato_dal_bot(SimpleNamespace(), 1, "LAY", 0.02) is False


def test_e_parcheggio_le_quote_del_gradino_1():
    assert UM.e_parcheggio(_ob("p", 1000.0, 2.0, 0.0, 2.0))
    lay = SimpleNamespace(side="LAY", order_type=SimpleNamespace(price=1.01))
    assert UM.e_parcheggio(lay)
    assert not UM.e_parcheggio(_ob("d", 1.06, 2.0, 0.0, 2.0))
    assert not UM.e_parcheggio(SimpleNamespace(side="LAY", order_type=SimpleNamespace(price=1000.0)))


def test_uf2_ordini_di_prima_non_contano():
    """L'ordine d'ingresso gia' a mercato (stessa selezione e lato) non e'
    l'uscita: contano solo gli ordini nati dopo la firma."""
    s = _Strategia()
    s.ordini.append(_ordine("vecchio"))
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        _firmata_ed_eseguita(s, o, ordini_dopo=[])
        o.giro(int((15.5 + UM.FINESTRA_ORDINI_S) * 1000) + 1)
    assert "UF2" in _codici(o)


def test_uf3_firma_sopravvissuta_alla_sua_proposta_esegue_la_nuova_e_violazione(monkeypatch):
    """Cancello guasto: la decadenza non porta via la firma. La proposta firmata
    decade, ne nasce una NUOVA con la stessa chiave, e la vecchia firma la
    esegue: e' un'uscita diversa da quella che l'utente ha visto."""
    def _togli_senza_firma(self, k):
        self.proposte.pop(k, None)

    monkeypatch.setattr(UP.CancelloUscite, "_togli", _togli_senza_firma)
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0, proposta=_proposta())
        o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))
        c.conferma_vive("scalper|1.9|7|o1|", [])         # la condizione cade
        assert c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=20.0,
                               proposta=_proposta()) is True
    assert "UF3" in _codici(o) and "UM4" in _codici(o)


def test_uf3_eseguita_senza_firma_del_banco_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0, proposta=_proposta())
        c.approva({CHIAVE: 11.0})                        # non l'ha firmata il banco
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=12.0, proposta=_proposta())
    assert "UF3" in _codici(o)


def test_uf3_motivo_diverso_da_quello_firmato_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_FIRMATE, s, {})
    with o.attivo():
        c = s.cancello_uscite
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=10.0, proposta=_proposta())
        o.giro(int((10.0 + UM.FIRMA_DOPO_S) * 1000))
        c.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=15.5,
                        proposta=_proposta(lato_chiusura="BACK"))
    assert "UF3" in _codici(o)


def test_l_osservatore_rimette_il_cancello_vero():
    vero_l, vero_e = UP.CancelloUscite.lascia_uscire, UP.CancelloUscite._emit
    o = _oss(UM.SCENARIO_MANUALI, _Strategia(), {})
    with pytest.raises(RuntimeError):
        with o.attivo():
            assert UP.CancelloUscite.lascia_uscire is not vero_l
            raise RuntimeError("replay caduto")
    assert UP.CancelloUscite.lascia_uscire is vero_l and UP.CancelloUscite._emit is vero_e


# ---------------------------------------------------------------- il ponte tennis
def test_ponte_tennis_passa_le_firme_con_la_funzione_del_runner(monkeypatch):
    """`_forse_firme` alla cadenza del bot_control_worker chiama
    `tennis_runner._aggiorna_uscite` con la riga (interruttore spento + firme):
    la firma arriva al cancello del bot; nessuna scrittura sul DB."""
    from Betfair.stream.tennis_live import tennis_runner as TR

    chiamate = []
    vera = TR._aggiorna_uscite

    def _spia(flumine, session, key, strat, riga):
        chiamate.append((key, dict(riga)))
        return vera(flumine, session, key, strat, riga)

    monkeypatch.setattr(TR, "_aggiorna_uscite", _spia)
    monkeypatch.setattr(TR.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: pytest.fail("scrittura sul DB dal banco"))
    strat = SimpleNamespace(cancello_uscite=UP.CancelloUscite(), uscite_automatiche=False)
    strat.cancello_uscite.lascia_uscire(automatiche=False, chiave="tennis_swing|1.1|11|1|stop",
                                        now_s=1.0, proposta=_proposta())
    ponte = RB._Ponte.__new__(RB._Ponte)
    ponte.s, ponte.event_id, ponte.bot_key = strat, "35794049", "tennis_swing"
    ponte.quadro = None
    ponte.osservatore = UM.Osservatore(UM.SCENARIO_FIRMATE, strategie=lambda: [strat],
                                       ordini_di=lambda s: [], firma=None)
    ponte.firme, ponte._firme_ms, ponte._sess_firme, ponte.ultimo_ms = {}, 0, None, 0
    ponte.firma("tennis_swing|1.1|11|1|stop", UM.istante_iso(2.0))
    ponte._forse_firme(5_000)
    assert chiamate and chiamate[0][0] == ("35794049", "tennis_swing")
    assert chiamate[0][1]["uscite_automatiche"] is False
    assert strat.cancello_uscite.firmata("tennis_swing|1.1|11|1|stop")
    ponte._forse_firme(6_000)                            # prima della cadenza: niente
    assert len(chiamate) == 1
    ponte._forse_firme(8_100)
    assert len(chiamate) == 2


# ---------------------------------------------------------------- il banco scalper
def _banco_finto(sniper: Any = None, strategia: Any = None, messaggi=()):
    from Betfair.stream.scalper import certificazione as SC

    b = RR._Banco.__new__(RR._Banco)
    b.sniper_ultimo = sniper
    b.sessioni = []
    b.mercati_catalogo = []
    b.ultima_strategia = strategia
    b.sniper_ordini_visti = set()
    b.attivita_sniper = []
    b.ref = SC.Referto(event_id="1", scenario=UM.SCENARIO_FIRMATE)
    b.db = SimpleNamespace(messaggi=lambda: list(messaggi))
    return b


class _SniperManuale:
    uscite_automatiche = False

    def __init__(self, piatto: bool = True) -> None:
        self._piatto = piatto

    def is_flat(self) -> bool:
        return self._piatto


POS_A = "scalper|1.234|1221385|sn-A|"
POS_B = "scalper|1.234|1221385|sn-B|"


def _firma_eseguita(chiave: str) -> tuple:
    # il payload VERO di `CancelloUscite.lascia_uscire` sull'uscita firmata
    return ("uscita_eseguita_su_approvazione",
            {"chiave": chiave, "approvata_at": 10.0,
             "motivo": chiave.rsplit("|", 1)[-1], "decisa_at": 9.0})


def _verde(*prefissi: str) -> tuple:
    return ("sniper_green", {"locked": 0.3, "minute": 20.0,
                             RR.CHIAVE_PREFISSI_GREEN: list(prefissi)})


@pytest.mark.parametrize("eventi,rosso", [
    ([_verde(POS_A)], True),                                            # da solo
    ([_firma_eseguita(POS_A + "target"), _verde(POS_A)], False),        # la SUA firma
    # il reperto: verde non firmato + firma d'ALTRA posizione = non si compensano
    ([_firma_eseguita(POS_B + "target"), _verde(POS_A)], True),
    # firma della stessa posizione ma d'altro motivo (stop): non e' la sua
    ([_firma_eseguita(POS_A + "stop"), _verde(POS_A)], True),
    # la firma arriva DOPO il verde: il verde era partito da solo
    ([_verde(POS_A), _firma_eseguita(POS_A + "target")], True),
    # una firma, due verdi: la firma vale UNA volta
    ([_firma_eseguita(POS_A + "target"), _verde(POS_A), _verde(POS_A)], True),
    # due posizioni, ognuna con la sua firma
    ([_firma_eseguita(POS_A + "target"), _firma_eseguita(POS_B + "target"),
      _verde(POS_B), _verde(POS_A)], False),
    # posizione ignota (il banco non l'ha letta): mai "sano"
    ([_firma_eseguita(POS_A + "target"), ("sniper_green", {"locked": 0.3})], True),
])
def test_z3_ogni_verde_ha_la_sua_firma_per_identita(eventi, rosso):
    b = _banco_finto(_SniperManuale())
    b.attivita_sniper = [(k, p, 0) for k, p in eventi]
    b.controlli_sniper(1_000, "fine", True)
    assert any(v.codice == "Z3" for v in b.ref.violazioni) is rosso, b.ref.violazioni


def test_z3_il_tee_del_banco_legge_la_posizione_del_verde_vera():
    """Lo sniper VERO in posizione con la chiusura abbinata: nell'istante del
    verde il banco legge la sua posizione con `_prefisso_uscite` di produzione."""
    from Betfair.stream.tests.test_sniper_uscite_automatiche_2026_09_28 import _in_posizione
    from Betfair.stream.tests.test_sniper_bot_2026_07_10 import _FakeOrder

    s, _mkt, pos = _in_posizione()
    assert RR.prefissi_del_green(s) == []               # nessuna chiusura: nessun verde
    pos.close = _FakeOrder("LAY", price=3.35, size_matched=10.0, avg=3.35)
    atteso = s._prefisso_uscite(pos)
    assert RR.prefissi_del_green(s) == [atteso] and atteso.startswith("scalper|1.234|")


def test_z3_il_tee_del_banco_scrive_la_posizione_sul_verde():
    """`aggiungi_strategia` monta il tee sull'event_sink dello sniper VERO: il
    `sniper_green` registrato dal banco porta la posizione; il sink di
    produzione riceve il payload intatto."""
    from Betfair.stream.tests.test_sniper_bot_2026_07_10 import _FakeOrder
    from Betfair.stream.tests.test_sniper_uscite_automatiche_2026_09_28 import _in_posizione

    s, _mkt, pos = _in_posizione()
    pos.close = _FakeOrder("LAY", price=3.35, size_matched=10.0, avg=3.35)
    b = RR._Banco.__new__(RR._Banco)
    b.raw, b.attivita_sniper, b.compagne, b.mercati_catalogo = "raw", [], [], []
    b._stream_ids = set()
    b.orologio = SimpleNamespace(ora_ms=lambda: 5)
    b.quadro = SimpleNamespace(add_strategy=lambda st: None)
    b.aggiungi_strategia(SimpleNamespace(strategie=[]), s)
    s._emit("sniper_green", locked=0.3, minute=20.0)
    k, p, _t = b.attivita_sniper[-1]
    assert k == "sniper_green" and p[RR.CHIAVE_PREFISSI_GREEN] == [s._prefisso_uscite(pos)]
    vero = [p for k, p in s._test_events if k == "sniper_green"][-1]
    assert RR.CHIAVE_PREFISSI_GREEN not in vero


@pytest.mark.parametrize("difetto,rosso", [
    (None, False),
    ("togli:size_chiusura", True),        # chiave assente
    ("nulla:size_chiusura", True),        # chiave presente senza numero
    ("nulla:se_chiudi", True),
    ("nulla:lato_chiusura", True),
    ("nulla:prezzo", True),
])
def test_z4_ogni_numero_obbligatorio_presente_e_valorizzato(difetto, rosso):
    p = dict(_proposta(), chiave=CHIAVE, decided_at=1.0)
    if difetto:
        modo, k = difetto.split(":")
        if modo == "togli":
            p.pop(k)
        else:
            p[k] = None
    b = _banco_finto(_SniperManuale())
    b.attivita_sniper = [("uscita_proposta", p, 0)]
    b.controlli_sniper(1_000, "fine", True)
    assert any(v.codice == "Z4" for v in b.ref.violazioni) is rosso


@pytest.mark.parametrize("k", list(UM.CHIAVI_NUMERI_OBBLIGATORI))
def test_difetti_proposta_verifica_una_per_una_ogni_chiave_obbligatoria(k):
    p = dict(_proposta(), chiave=CHIAVE, decided_at=1.0)
    assert UM.difetti_proposta(p) == []
    senza = dict(p)
    senza.pop(k)
    assert UM.difetti_proposta(senza) == ["%s assente" % k]
    vuota = dict(p, **{k: None})
    assert UM.difetti_proposta(vuota) == ["%s senza valore" % k]


def test_um2_proposta_con_un_numero_vuoto_e_violazione():
    s = _Strategia()
    o = _oss(UM.SCENARIO_MANUALI, s, {})
    with o.attivo():
        s.cancello_uscite.lascia_uscire(automatiche=False, chiave=CHIAVE, now_s=1.0,
                                        proposta=_proposta(size_chiusura=None))
    assert any(v[0] == "UM2" and "size_chiusura senza valore" in v[2]
               for v in o.violazioni)


def test_piatto_a_fine_maker_sniper_e_dichiarazione():
    from Betfair.stream.scalper import scalper_bot as SB

    def _maker(stato):
        slot = SimpleNamespace(status=stato, entry=None, entry_back=None, entry_lay=None,
                               next_entry=None, close=None, flatten_orders=[])
        return SimpleNamespace(_slots={("1.9", 7): slot})

    assert _banco_finto(_SniperManuale(), _maker(SB.DONE)).piatto_a_fine() is None
    assert "maker" in _banco_finto(_SniperManuale(), _maker(SB.LOCKING)).piatto_a_fine()
    assert "sniper" in _banco_finto(_SniperManuale(False), _maker(SB.IDLE)).piatto_a_fine()
    # la sessione lo ha DICHIARATO: non e' un difetto del banco
    assert _banco_finto(_SniperManuale(False), _maker(SB.LOCKING),
                        messaggi=["stop: posizione NON flat"]).piatto_a_fine() is None


def test_banco_scalper_resto_dichiarato_e_ruolo():
    b = _banco_finto(_SniperManuale())
    b.attivita = [("min_bet_skip", {"selection_id": 7, "side": "LAY", "size": 0.02}, 0)]
    b.attivita_sniper = []
    assert b.resto_dichiarato(None, 7, "LAY", 0.02) is True
    assert b.resto_dichiarato(None, 7, "BACK", 0.02) is False
    assert b.resto_dichiarato(None, 8, "LAY", 0.02) is False
    ingresso, uscita = object(), object()
    slot = SimpleNamespace(status="LOCKING", entry=ingresso, entry_back=None, entry_lay=None,
                           next_entry=None, close=uscita, flatten_orders=[])
    b.ultima_strategia = SimpleNamespace(_slots={("1.9", 7): slot})
    assert b.ruolo_ordine(ingresso) == "ingresso"
    assert b.ruolo_ordine(uscita) == "uscita"
    assert b.ruolo_ordine(object()) is None
