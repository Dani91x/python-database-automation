"""I TRE DIFETTI DEL POMERIGGIO DEL 15/09 — stessa radice, tre punti.

Li ha trovati l'utente guardando gli ORDINI VERI su Betfair, non una review:
alle 14:00 c'erano a mercato cinque ordini reali e il database ne raccontava
una terza versione.

La radice e' sempre la stessa, ed e' quella della mattina: **un identificativo
o un campo scritto in un modo e letto in un altro.** Non da errore. Da `None`,
che diventa `0.0`, che significa «non abbinato» / «mai piazzato». Silenzioso,
e sul percorso dei soldi.

  A) `res.ok` non veniva letto DA NESSUNA PARTE. Se Betfair rifiutava la lay
     appoggiata il codice proseguiva lo stesso, scriveva `place_resting` e
     lasciava la riga 'pending': il bot credeva di avere una copertura che non
     esisteva. Trinec v Mlada Boleslav, 13:43:33 — un back reale da 5 EUR e'
     rimasto scoperto.

  B) `getattr(res, "avg_price", None)` — quel campo non esiste, si chiama
     `avg_price_matched`. Tornava sempre `None` e il prezzo ricadeva su quello
     CHIESTO: un abbinamento immediato contabilizzato al prezzo sbagliato.

  C) la riconciliazione cercava sempre e solo `mike-t<id>`, ma le gambe di
     USCITA venivano piazzate con `customer_ref=leg.ref` (`under_green-0-2`).
     L'ordine VIVO non veniva trovato, la riga finiva in 'error', il freno
     anti-duplicato (che guarda le righe 'pending') smetteva di coprire, e al
     giro dopo partiva un SECONDO green-up. Il loop della mattina, in un terzo
     punto.

Nessun finto scritto a mano: gli esiti si costruiscono con il vero
`PlaceResult` e gli ordini con la grafia che `omega_market` produce davvero.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.omega.omega_market import PlaceResult


NOW = datetime(2026, 9, 15, 14, 0, 0, tzinfo=timezone.utc)
VECCHIO = "2026-09-15T13:43:33+00:00"      # oltre RECON_GRACE_S


# ---------------------------------------------------------------------------
# i doppi: parlano come i veri, o non servono a niente
# ---------------------------------------------------------------------------
def esito(*, ok=True, bet_id="B1", matched=0.0, prezzo=None,
          stato="EXECUTABLE") -> PlaceResult:
    """L'esito di un place, con la CLASSE VERA."""
    return PlaceResult(ok=ok, order_status=stato, bet_id=bet_id,
                       size_matched=matched, avg_price_matched=prezzo, raw={})


def ordine(**kw: Any) -> Dict[str, Any]:
    """Un ordine come lo restituisce `omega_market.list_current_orders()`:
    chiavi in snake_case, mai camelCase."""
    base = {"bet_id": "B1", "customer_order_ref": "mike-t1", "market_id": "1.262445982",
            "selection_id": 1222344, "side": "lay", "status": "EXECUTABLE",
            "size_matched": 0.0, "size_remaining": 5.05, "avg_price_matched": None}
    base.update(kw)
    return base


class DbFinto:
    def __init__(self, righe: Optional[List[dict]] = None) -> None:
        self.righe = list(righe or [])
        self.log_righe: List[tuple] = []
        self.aggiornate: List[tuple] = []
        self._id = 0

    def trades_for_event(self, _event_id, **_kw) -> List[dict]:
        return list(self.righe)

    def insert_trade(self, row, **_kw):
        # il vero torna l'ID (`Optional[int]`), non la riga
        self._id += 1
        self.righe.append({**row, "id": self._id})
        return self._id

    def update_trade(self, trade_id, **campi):
        self.aggiornate.append((trade_id, campi))
        for r in self.righe:
            if r.get("id") == trade_id:
                r.update(campi)

    def log(self, kind, payload=None, event_id=None):
        self.log_righe.append((kind, payload or {}))

    def kinds(self) -> List[str]:
        return [k for k, _ in self.log_righe]

    def motivi(self, kind: str) -> List[str]:
        return [str(p.get("reason") or "") for k, p in self.log_righe if k == kind]


class InfoFinta:
    event_id = "36066505"
    event_name = "Trinec v Mlada Boleslav"
    competition = None
    ko_at = 0.0

    def market_id(self, _m: str) -> str:
        return "1.262445982"

    def selection_id(self, _m: str, _s: str) -> int:
        return 1222344

    def selection_name(self, _m: str, _s: str) -> str:
        return "Under 3.5 Goals"


def gamba(**kw: Any) -> E.Leg:
    base = dict(ref="under_green-0-2", role="under_green", market=E.MARKET_OU35,
                selection=E.SEL_UNDER, side="lay", price=1.43, size=5.05,
                status="pending")
    base.update(kw)
    return E.Leg(**base)


def piazza(db, market, leg, **kw):
    S._piazza_resting_live(db=db, market=market, info=InfoFinta(), leg=leg,
                           mode="live", params={}, minuto=None, score=None,
                           chiude=None, motivo=None, ev={"event_id": InfoFinta.event_id},
                           **kw)


# ===========================================================================
# A. L'ESITO SI LEGGE
# ===========================================================================
def test_un_RIFIUTO_di_betfair_non_diventa_una_copertura():
    """Il caso di Trinec. `ok=False` senza tracce vuol dire una cosa sola:
    l'ordine NON e' a mercato. Dichiararlo piazzato lascia scoperto un back
    reale, ed e' esattamente quello che e' successo."""
    db, leg = DbFinto(), gamba()
    market = SimpleNamespace(
        place_order_live=lambda **kw: esito(ok=False, bet_id=None, stato="EXPIRED"))

    piazza(db, market, leg)

    assert "place_resting" not in db.kinds(), (
        "ha dichiarato appoggiata una lay che Betfair aveva rifiutato")
    assert "place_rifiutato" in db.kinds()
    assert leg.status == "cancelled"


def test_dopo_un_rifiuto_la_riga_NON_resta_pending():
    """Una riga 'pending' eterna terrebbe alzato il freno anti-duplicato su una
    gamba mai nata: la copertura non verrebbe mai piu' riproposta."""
    db, leg = DbFinto(), gamba()
    market = SimpleNamespace(
        place_order_live=lambda **kw: esito(ok=False, bet_id=None, stato="EXPIRED"))

    piazza(db, market, leg)

    assert db.righe, "la riga di riserva deve esistere: si scrive prima di piazzare"
    assert str(db.righe[0].get("status")) == "error"


def test_un_rifiuto_CON_TRACCE_non_si_decide_da_soli():
    """`ok=False` ma un bet_id in mano: i due racconti non tornano. Non si
    sceglie quale credere — si chiede a Betfair."""
    db, leg = DbFinto(), gamba()
    market = SimpleNamespace(
        place_order_live=lambda **kw: esito(ok=False, bet_id="442915404791"))

    piazza(db, market, leg)

    assert leg.status == E.STATUS_RECONCILE
    assert "resting_rifiutata_con_tracce" in db.motivi("reconcile_pending")
    assert "place_resting" not in db.kinds()


def test_un_esito_BUONO_segue_la_strada_di_sempre():
    db, leg = DbFinto(), gamba()
    market = SimpleNamespace(place_order_live=lambda **kw: esito(bet_id="442915404791"))

    piazza(db, market, leg)

    assert "place_resting" in db.kinds()
    assert leg.status == "pending"
    scritti = [c for _, c in db.aggiornate if "bet_id" in c]
    assert scritti and scritti[0]["bet_id"] == "442915404791"


# ===========================================================================
# B. IL PREZZO E' QUELLO ABBINATO, NON QUELLO CHIESTO
# ===========================================================================
def test_un_abbinamento_immediato_vale_il_prezzo_ABBINATO():
    """`avg_price` non esiste su `PlaceResult`: tornava sempre `None` e il
    prezzo ricadeva su quello chiesto. Da li' passano liability, P&L e
    cash-out."""
    db, leg = DbFinto(), gamba(price=1.43, size=5.05)
    market = SimpleNamespace(
        place_order_live=lambda **kw: esito(matched=5.05, prezzo=1.39,
                                            stato="EXECUTION_COMPLETE"))

    piazza(db, market, leg)

    assert leg.avg_price == 1.39, "ha contabilizzato il prezzo CHIESTO, non l'abbinato"
    assert leg.matched == pytest.approx(5.05) and leg.status == "open"


def test_senza_prezzo_abbinato_si_tiene_quello_chiesto():
    """`None` non deve diventare 0.0: una gamba non vale mai quota zero."""
    db, leg = DbFinto(), gamba(price=1.43, size=5.05)
    market = SimpleNamespace(
        place_order_live=lambda **kw: esito(matched=2.0, prezzo=None))

    piazza(db, market, leg)

    assert leg.avg_price == 1.43


def test_PlaceResult_ha_davvero_i_campi_che_il_codice_legge():
    """Il contratto, per iscritto. Se un campo cambia nome il test si rompe
    QUI, e non su un ordine vero: e' l'unico modo per cui questa famiglia di
    difetti si vede prima."""
    r = esito()
    for campo in ("ok", "order_status", "bet_id", "size_matched",
                  "avg_price_matched", "raw"):
        assert hasattr(r, campo), f"PlaceResult non espone piu' '{campo}'"
    assert not hasattr(r, "avg_price"), (
        "'avg_price' non esiste e non deve esistere: e' il campo che il codice "
        "leggeva per sbaglio")


# ===========================================================================
# C. LA RICONCILIAZIONE RITROVA L'ORDINE CHE HA PIAZZATO
# ===========================================================================
def riga_uscita(**kw: Any) -> Dict[str, Any]:
    """La riga #4820: una gamba di USCITA (`closes_trade_id` valorizzato), in
    attesa di conferma, con l'ordine gia' a mercato."""
    base = {"id": 1, "signal_key": "under_green-0-2", "role": "under_green",
            "cycle_no": 0, "side": "lay", "status": "pending", "bet_id": None,
            "market_id": "1.262445982", "selection_id": 1222344,
            "closes_trade_id": 99, "price": 1.43, "size": 5.05,
            "placed_at": VECCHIO, "meta": {}}
    base.update(kw)
    return base


def riconcilia(db, vivi, regolati=None, leg=None):
    market = SimpleNamespace(list_current_orders=lambda: list(vivi),
                             list_cleared_orders=lambda: list(regolati or []))
    l = leg if leg is not None else gamba(status=E.STATUS_RECONCILE)
    ctx = E.MatchCtx(legs=[l])
    n = S._reconcile_unknown(db, market, InfoFinta.event_id, ctx, "live", NOW)
    return n, l


def test_un_ordine_VIVO_col_ref_storico_NON_va_in_error():
    """IL DIFETTO C, nel suo caso esatto: la riga #4820 e' stata marcata «mai
    piazzata» mentre su Betfair l'ordine era vivo. Da li' il freno
    anti-duplicato smetteva di coprire e partiva un secondo green-up."""
    db = DbFinto([riga_uscita()])
    vivi = [ordine(customer_order_ref="under_green-0-2")]   # EXECUTABLE, non abbinato

    _n, leg = riconcilia(db, vivi)

    assert str(db.righe[0]["status"]) == "pending", (
        "un ordine VIVO a mercato e' stato dichiarato «mai piazzato»")
    assert leg.status == E.STATUS_RECONCILE, "si aspetta, non si libera"
    assert "reconciled_not_placed" not in db.motivi("reconcile_fix")


def test_un_ordine_ABBINATO_col_ref_storico_viene_CONFERMATO():
    db = DbFinto([riga_uscita()])
    vivi = [ordine(customer_order_ref="under_green-0-2", size_matched=5.05,
                   size_remaining=0.0, avg_price_matched=1.93,
                   status="EXECUTION_COMPLETE")]

    _n, leg = riconcilia(db, vivi)

    assert str(db.righe[0]["status"]) == "open"
    assert leg.matched == pytest.approx(5.05) and leg.avg_price == 1.93


def test_un_ordine_col_ref_NUOVO_viene_CONFERMATO():
    """Gli ordini nati dal 15/09 in poi portano `mike-t<id>`."""
    db = DbFinto([riga_uscita()])
    vivi = [ordine(customer_order_ref="mike-t1", size_matched=5.05,
                   size_remaining=0.0, avg_price_matched=1.93,
                   status="EXECUTION_COMPLETE")]

    _n, _leg = riconcilia(db, vivi)

    assert str(db.righe[0]["status"]) == "open"


def test_il_BET_ID_basta_da_solo():
    """E' l'identificativo che ha dato Betfair: unico su tutto il conto, e non
    dipende da come abbiamo chiamato l'ordine."""
    db = DbFinto([riga_uscita(bet_id="442915404791")])
    vivi = [ordine(bet_id="442915404791", customer_order_ref="qualunque-cosa",
                   size_matched=5.05, size_remaining=0.0, avg_price_matched=1.93,
                   status="EXECUTION_COMPLETE")]

    _n, _leg = riconcilia(db, vivi)

    assert str(db.righe[0]["status"]) == "open"


def test_lo_STESSO_ref_storico_di_UN_ALTRA_PARTITA_non_conferma_niente():
    """LA GUARDIA, e non e' teorica: alle 14:00 del 15/09 a mercato c'erano
    `under_green-0-116` e `under_green-0-2` su due partite diverse. Il ref
    della gamba vale `{ruolo}-{ciclo}-{seq}` e `seq` conta PER PARTITA: senza
    il confronto sul mercato si confermerebbe questa riga con l'ordine di un
    ALTRO evento, prezzo e size compresi."""
    db = DbFinto([riga_uscita()])
    vivi = [ordine(customer_order_ref="under_green-0-2", market_id="1.262364408",
                   selection_id=1222344, size_matched=5.07, size_remaining=0.0,
                   avg_price_matched=1.53, status="EXECUTION_COMPLETE")]

    _n, _leg = riconcilia(db, vivi)

    assert str(db.righe[0]["status"]) != "open", (
        "ha confermato la riga con l'ordine di un'ALTRA partita")


def test_nessun_ordine_da_nessuna_parte_resta_il_comportamento_di_prima():
    """Il fix non ammorbidisce la regola: un pending vecchio che su Betfair non
    esiste davvero va ancora liberato, o resterebbe per sempre."""
    db = DbFinto([riga_uscita()])

    _n, leg = riconcilia(db, [])

    assert str(db.righe[0]["status"]) == "error"
    assert leg.status == "cancelled"


def test_gli_ordini_arrivano_normalizzati_anche_se_camelCase():
    """`reconcile_decision` legge solo snake_case e non ha modo di difendersi
    da sola: se la lista arriva in camelCase vede `size_matched=None` -> 0.0,
    cioe' «non abbinato». Qui si normalizza prima di consegnargliela."""
    db = DbFinto([riga_uscita()])
    grezzo = {"betId": "B1", "customerOrderRef": "under_green-0-2",
              "marketId": "1.262445982", "selectionId": 1222344, "side": "lay",
              "status": "EXECUTION_COMPLETE", "sizeMatched": 5.05,
              "sizeRemaining": 0.0, "averagePriceMatched": 1.93}

    _n, leg = riconcilia(db, [grezzo])

    assert str(db.righe[0]["status"]) == "open"
    assert leg.matched == pytest.approx(5.05) and leg.avg_price == 1.93
