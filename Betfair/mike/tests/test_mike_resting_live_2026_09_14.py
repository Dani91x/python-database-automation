"""L'USCITA APPOGGIATA ESISTE ANCHE IN LIVE (14/09/2026).

Regola dell'utente, testuale: «LE STRATEGIE CHE STIAMO TESTANDO IN DEMO DEVONO
ESSERE LE STESSE IDENTICHE CHE ANDRANNO IN LIVE. NON MODIFICARE LE STRATEGIE.
L'UNICA DIFFERENZA È LIVE O PAPER.»

Fino al 13/09 non era così, e la deviazione stava nel LIVE, non nel paper:
`_live_exit_override` forzava `pre_exit_mode='taker'` su ogni partita in
modalità live perché l'ordine appoggiato non era cablato. In paper il bot
appoggiava la lay a −2 tick e il ciclo chiudeva in profitto; in live avrebbe
attraversato lo spread e lo stesso ciclo poteva chiudere in perdita.

Questi test difendono due cose insieme, e servono entrambe:

  1. **la strategia in live è la stessa del paper** — stesso ordine, stesso
     prezzo, stessa size, stesso tipo di esecuzione;
  2. **in live non si SIMULA mai un abbinamento.** È l'invariante dell'11/09 e
     non è negoziabile: un fill inventato su soldi veri è un profitto che non
     esiste. In paper l'abbinamento si deduce dal book; in live si LEGGE dal
     book ordini di Betfair.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S


# ---------------------------------------------------------------------------
# doppi minimi: qui si misura il PERCORSO, non il motore
# ---------------------------------------------------------------------------
class MercatoFinto:
    """Registra cosa gli viene chiesto di piazzare e cosa risponde."""

    def __init__(self, ordini_vivi: Optional[List[dict]] = None, esplode: bool = False) -> None:
        self.piazzati: List[dict] = []
        self.ordini_vivi = ordini_vivi if ordini_vivi is not None else []
        self.esplode = esplode

    def place_order_live(self, **kw: Any) -> Any:
        self.piazzati.append(dict(kw))
        if self.esplode:
            raise RuntimeError("rete giù")
        return type("Res", (), {"size_matched": 0.0, "avg_price": None})()

    def list_current_orders(self) -> List[dict]:
        if self.esplode:
            raise RuntimeError("rete giù")
        return list(self.ordini_vivi)


class DbFinto:
    def __init__(self) -> None:
        self.righe: List[dict] = []
        self.log_scritti: List[tuple] = []
        self.aggiornate: List[dict] = []

    def log(self, kind: str, payload: dict, event_id: Optional[str] = None) -> None:
        self.log_scritti.append((kind, payload))

    def kinds(self) -> List[str]:
        return [k for k, _ in self.log_scritti]

    def insert_trade(self, row: dict) -> dict:
        r = dict(row, id=len(self.righe) + 1)
        self.righe.append(r)
        return r

    def update_trade(self, tid: int, **kw: Any) -> None:
        self.aggiornate.append(dict(kw, id=tid))


class InfoFinta:
    event_id = "E1"
    event_name = "Tizio v Caio"
    competition = None
    ko_at = 0.0

    def market_id(self, m: str) -> str:
        return "1.234"

    def selection_id(self, m: str, s: str) -> int:
        return 47999


def _gamba(**kw: Any) -> E.Leg:
    base = dict(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                side="lay", price=1.48, size=10.14, ref="under_green-1-2", status="pending")
    base.update(kw)
    return E.Leg(**base)


@pytest.fixture(autouse=True)
def _senza_scritture_vere(monkeypatch):
    """Le due funzioni che toccano il database sono sostituite: qui si misura il
    percorso di esecuzione, non la persistenza."""
    monkeypatch.setattr(S, "_insert_trade_row", lambda db, row, eid: db.insert_trade(row))
    monkeypatch.setattr(S, "_trade_row", lambda *a, **k: {"ref": "x"})
    monkeypatch.setattr(S, "_trade_row_for_leg", lambda db, eid, leg: {"id": 1, "meta": {}})


# ===========================================================================
# 1. LA STRATEGIA È LA STESSA
# ===========================================================================
def test_in_live_e_in_paper_i_parametri_di_uscita_coincidono():
    p = C.merge_params({"pre_exit_mode": "resting"})
    assert (S._params_for(p, True, "live")["pre_exit_mode"]
            == S._params_for(p, True, "paper")["pre_exit_mode"] == "resting")


def test_la_valvola_e_accesa_per_difetto():
    """Spenta cambierebbe la strategia in live: deve nascere accesa."""
    assert C.DEFAULTS["live_resting_enabled"] is True


def test_la_valvola_spenta_riporta_al_dirottamento():
    p = C.merge_params({"pre_exit_mode": "resting", "live_resting_enabled": False})
    assert S._params_for(p, True, "live")["pre_exit_mode"] == "taker"
    assert S._params_for(p, True, "paper")["pre_exit_mode"] == "resting"


# ===========================================================================
# 2. IN LIVE SI PIAZZA DAVVERO, E SENZA FILL_OR_KILL
# ===========================================================================
def test_l_ordine_live_viene_piazzato_SENZA_fill_or_kill():
    """È il cuore del cablaggio: un FILL_OR_KILL per definizione non può restare
    sul book. Senza questo flag l'ordine resta appoggiato, che è ciò che la
    strategia chiede."""
    db, mk, leg = DbFinto(), MercatoFinto(), _gamba()
    S._piazza_resting_live(db=db, market=mk, info=InfoFinta(), leg=leg, mode="live",
                           params=C.merge_params(None), minuto=None, score=None,
                           chiude=None, motivo=None, ev={"event_id": "E1"})
    assert len(mk.piazzati) == 1
    o = mk.piazzati[0]
    assert o["fill_or_kill"] is False
    assert o["side"] == "lay" and o["price"] == 1.48 and o["size"] == 10.14
    assert o["customer_ref"] == "under_green-1-2"
    assert "place_resting" in db.kinds()


def test_la_riga_si_scrive_PRIMA_di_piazzare():
    """Se il processo muore in mezzo deve restare una riga 'pending' che la
    riconciliazione ritrova. L'ordine contrario lascerebbe su Betfair un ordine
    VIVO che nessuno sa di avere: più tardi si abbina, il bot nel frattempo è
    rientrato, e sono soldi veri due volte."""
    ordine: List[str] = []
    db, mk = DbFinto(), MercatoFinto()
    db.insert_trade = lambda row: ordine.append("riga") or {"id": 1}   # type: ignore[assignment]
    mk.place_order_live = lambda **kw: ordine.append("ordine") or type("R", (), {"size_matched": 0.0})()  # type: ignore[assignment]
    S._piazza_resting_live(db=db, market=mk, info=InfoFinta(), leg=_gamba(), mode="live",
                           params=C.merge_params(None), minuto=None, score=None,
                           chiude=None, motivo=None, ev={"event_id": "E1"})
    assert ordine == ["riga", "ordine"]


def test_se_la_riserva_fallisce_NON_si_piazza_niente():
    db, mk, leg = DbFinto(), MercatoFinto(), _gamba()

    def boom(row):
        raise RuntimeError("database giù")

    db.insert_trade = boom              # type: ignore[assignment]
    S._piazza_resting_live(db=db, market=mk, info=InfoFinta(), leg=leg, mode="live",
                           params=C.merge_params(None), minuto=None, score=None,
                           chiude=None, motivo=None, ev={"event_id": "E1"})
    assert mk.piazzati == [], "nessun ordine reale senza la riga che lo segue"
    assert leg.status == "cancelled"


def test_esito_IGNOTO_va_in_riconciliazione_non_annullato():
    """L'ordine POTREBBE esistere. Annullare la riga vorrebbe dire dimenticarlo;
    rientrare vorrebbe dire scommettere due volte. Si dichiara di non sapere."""
    db, mk, leg = DbFinto(), MercatoFinto(esplode=True), _gamba()
    S._piazza_resting_live(db=db, market=mk, info=InfoFinta(), leg=leg, mode="live",
                           params=C.merge_params(None), minuto=None, score=None,
                           chiude=None, motivo=None, ev={"event_id": "E1"})
    assert leg.status == E.STATUS_RECONCILE
    assert "reconcile_pending" in db.kinds()


# ===========================================================================
# 3. L'ABBINAMENTO IN LIVE SI LEGGE, NON SI SIMULA
# ===========================================================================
def _segui(db, mk, leg):
    S._segui_resting_live(db=db, market=mk, leg=leg, extra={},
                          params=C.merge_params(None), now_ts=1000.0, ev={"event_id": "E1"})


def test_nessun_progresso_nessun_fill():
    leg = _gamba()
    _segui(DbFinto(), MercatoFinto([{"customerOrderRef": leg.ref, "sizeMatched": 0.0}]), leg)
    assert leg.matched == 0.0 and leg.status == "pending"


def test_abbinamento_PARZIALE_letto_da_betfair():
    leg = _gamba()
    db = DbFinto()
    _segui(db, MercatoFinto([{"customerOrderRef": leg.ref, "sizeMatched": 4.0,
                              "averagePriceMatched": 1.47}]), leg)
    assert leg.matched == 4.0 and leg.avg_price == 1.47
    assert leg.status == "pending", "parziale: la gamba resta viva"
    assert "fill_resting" in db.kinds()


def test_abbinamento_COMPLETO_apre_la_gamba():
    leg = _gamba()
    _segui(DbFinto(), MercatoFinto([{"customerOrderRef": leg.ref, "sizeMatched": 10.14,
                                     "averagePriceMatched": 1.48}]), leg)
    assert leg.matched == pytest.approx(10.14) and leg.status == "open"


def test_ordine_SPARITO_dai_vivi_va_in_riconciliazione():
    """Abbinato del tutto? Annullato? Mai arrivato? Tre casi con conseguenze
    opposte: non si indovina."""
    leg = _gamba()
    db = DbFinto()
    _segui(db, MercatoFinto([]), leg)
    assert leg.status == E.STATUS_RECONCILE
    assert "reconcile_pending" in db.kinds()


def test_rete_GIU_non_inventa_niente():
    """Se non si riesce a chiedere, non si risponde: si riprova al giro dopo."""
    leg = _gamba()
    _segui(DbFinto(), MercatoFinto(esplode=True), leg)
    assert leg.matched == 0.0 and leg.status == "pending"


def test_un_ordine_di_un_ALTRA_gamba_non_viene_scambiato_per_il_nostro():
    leg = _gamba()
    _segui(DbFinto(), MercatoFinto([{"customerOrderRef": "un-altro-ref", "sizeMatched": 10.14}]), leg)
    assert leg.matched == 0.0, "si riconosce dal customerOrderRef, non dal primo che capita"
    assert leg.status == E.STATUS_RECONCILE


# ===========================================================================
# 4. LA CHIUSURA MANUALE NON SI APPOGGIA MAI
# ===========================================================================
def test_una_chiusura_manuale_non_resta_mai_sul_book():
    """«Si esce subito e si accetta»: se l'utente chiede di chiudere, si chiude
    ORA. Garantito dal RUOLO, non dal parametro — così resta vero anche se
    domani qualcuno cambia ``pre_exit_mode``."""
    manuale = _gamba(role="manual_close", ref="m1")
    for modo in ("resting", "taker"):
        assert S._is_resting_leg(manuale, {"pre_exit_mode": modo}) is False, modo
