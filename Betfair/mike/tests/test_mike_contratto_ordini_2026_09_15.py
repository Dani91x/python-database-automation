"""IL CONTRATTO FRA BETFAIR E MIKE, VERIFICATO DAL NORMALIZZATORE VERO (15/09).

Il 15/09 lo stesso identico difetto e' comparso DUE VOLTE, e la seconda dentro
la funzione che aveva causato la prima:

  * `_ordine_di` cercava ``customerOrderRef`` in un dizionario che espone
    ``customer_order_ref`` → «questo ordine non l'ho mai piazzato» → il motore
    ne piazzava un altro. Trentadue ordini reali.
  * `_segui_resting_live` leggeva ``sizeMatched`` dove c'e' ``size_matched`` →
    «la lay appoggiata non si e' abbinata» → un green-up gia' eseguito a
    mercato restava `pending` nel database. Visto dal vivo sulla riga #4817.

Nessun test lo prendeva perche' i finti di mercato erano scritti a mano **con
la grafia sbagliata, la stessa del difetto**: il finto rispondeva a una domanda
a cui il vero non rispondeva.

Questi test non scrivono nessun finto. Prendono una risposta Betfair GREZZA —
camelCase, come la manda l'exchange — la fanno passare dal normalizzatore VERO
(`omega_market.list_current_orders`) e danno il risultato a Mike. Se qualcuno
cambia la normalizzazione, o se qualcuno rilegge una chiave con la grafia
sbagliata, qui diventa rosso.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.omega import omega_market as OM


# --------------------------------------------------------------------------
# la risposta GREZZA di Betfair: le chiavi sono quelle dell'exchange
# --------------------------------------------------------------------------
def _risposta_betfair_grezza(*, bet_id="999", ref="mike-t1", matched=0.0,
                             prezzo=None, residuo=5.0, stato="EXECUTABLE"):
    return {"currentOrders": [{
        "betId": bet_id,
        "marketId": "1.234",
        "selectionId": 1222344,
        "side": "LAY",
        "status": stato,
        "sizeMatched": matched,
        "averagePriceMatched": prezzo,
        "sizeRemaining": residuo,
        "customerOrderRef": ref,
    }]}


@pytest.fixture()
def vivi(monkeypatch):
    """Gli ordini vivi COME LI VEDE MIKE: passati dal normalizzatore vero."""
    def _fai(**kw):
        monkeypatch.setattr(OM, "call", lambda _f, **_k: _risposta_betfair_grezza(**kw))
        return OM.list_current_orders("mike")
    return _fai


def _gamba(**kw):
    base = dict(ref="mike-t1", role="under_green", market=E.MARKET_OU35,
                selection=E.SEL_UNDER, side="lay", price=1.43, size=5.07,
                matched=0.0, status="pending")
    base.update(kw)
    return E.Leg(**base)


class _DbSenzaRighe:
    """Il DB non conosce nessun bet_id: costringe la ricerca a passare dal
    riferimento del cliente, che e' la strada che falliva."""

    def trades_for_event(self, _eid):
        return []

    def log(self, *_a, **_k):
        pass


# ===========================================================================
# 1. IL NORMALIZZATORE: che nomi hanno davvero i campi
# ===========================================================================
def test_il_normalizzatore_espone_snake_case_e_NON_camelCase(vivi):
    o = vivi()[0]
    for atteso in ("bet_id", "customer_order_ref", "size_matched",
                   "avg_price_matched", "size_remaining", "market_id",
                   "selection_id", "side", "status"):
        assert atteso in o, f"il normalizzatore non espone piu' '{atteso}'"
    for sbagliato in ("betId", "customerOrderRef", "sizeMatched",
                      "averagePriceMatched", "sizeRemaining"):
        assert sbagliato not in o, (
            f"'{sbagliato}' NON esiste in questo dizionario: chi la legge "
            f"prende None, che diventa zero, che vuol dire «non abbinato»")


def test_ogni_campo_che_mike_sa_leggere_esiste_davvero(vivi):
    """La tabella degli alias non deve promettere campi che non arrivano mai."""
    o = vivi(matched=2.0, prezzo=1.42)[0]
    for campo in ("bet_id", "customer_order_ref", "size_matched",
                  "avg_price_matched", "size_remaining", "market_id",
                  "selection_id", "side", "status"):
        assert S.campo_ordine(o, campo, "MANCA") != "MANCA", campo


# ===========================================================================
# 2. RITROVARE L'ORDINE — il difetto che ha prodotto 32 ordini veri
# ===========================================================================
def test_l_ordine_appoggiato_si_ritrova_dal_riferimento(vivi):
    trovato = S._ordine_di(vivi(ref="mike-t1"), _gamba(), _DbSenzaRighe(), "E1")
    assert trovato is not None, (
        "l'ordine c'e' ed e' suo: non ritrovarlo significa ripiazzarlo")


def test_un_riferimento_diverso_non_e_il_nostro_ordine(vivi):
    assert S._ordine_di(vivi(ref="mike-t999"), _gamba(), _DbSenzaRighe(), "E1") is None


def test_si_ritrova_anche_per_bet_id_quando_il_riferimento_non_combacia(vivi):
    class _Db(_DbSenzaRighe):
        def trades_for_event(self, _eid):
            # la riga si lega alla gamba dal `signal_key`, che E' il ref
            return [{"id": 1, "signal_key": "mike-t1", "role": "under_green",
                     "cycle_no": 0, "side": "lay", "status": "pending",
                     "bet_id": "777", "meta": {}}]

    trovato = S._ordine_di(vivi(bet_id="777", ref="tutt-altro"), _gamba(),
                           _Db(), "E1")
    assert trovato is not None and trovato["bet_id"] == "777"


# ===========================================================================
# 3. ACCORGERSI CHE LA LAY APPOGGIATA SI E' ABBINATA — il secondo caso
# ===========================================================================
def _segui(vivi_lista, leg):
    class _Mercato:
        @staticmethod
        def list_current_orders():
            return vivi_lista

    registro = []

    class _Db(_DbSenzaRighe):
        def trades_for_event(self, _eid):
            return []

        def log(self, kind, payload, *_a):
            registro.append((kind, payload))

        def update_trade(self, *_a, **_k):
            pass

    S._segui_resting_live(db=_Db(), market=_Mercato(), leg=leg, extra={},
                          params={}, now_ts=1000.0,
                          ev={"event_id": "E1", "markets": {}})
    return registro


def test_un_abbinamento_PARZIALE_viene_visto(vivi):
    leg = _gamba(size=5.07, matched=0.0)
    _segui(vivi(matched=2.5, prezzo=1.42, residuo=2.57), leg)
    assert leg.matched == 2.5, (
        "leggeva 'sizeMatched' e vedeva sempre zero: un abbinamento parziale "
        "restava invisibile")
    assert leg.avg_price == 1.42
    assert leg.status == "pending", "meta' abbinata non e' aperta"


def test_un_abbinamento_TOTALE_apre_la_gamba(vivi):
    leg = _gamba(size=5.07, matched=0.0)
    registro = _segui(vivi(matched=5.07, prezzo=1.43, residuo=0.0), leg)
    assert leg.matched == 5.07 and leg.status == "open"
    assert any(k == "fill_resting" for k, _ in registro), (
        "un abbinamento reale deve lasciare traccia")


def test_senza_progresso_non_succede_niente(vivi):
    leg = _gamba(matched=2.5)
    registro = _segui(vivi(matched=2.5, prezzo=1.42, residuo=2.57), leg)
    assert leg.matched == 2.5 and leg.status == "pending"
    assert not registro, "nessun progresso non e' una notizia"


def test_senza_prezzo_medio_si_tiene_quello_chiesto(vivi):
    """Betfair non manda il prezzo medio finche' non c'e' abbinato: `None` non
    deve diventare 0.0, o la gamba varrebbe un prezzo impossibile."""
    leg = _gamba(price=1.43, matched=0.0)
    _segui(vivi(matched=1.0, prezzo=None, residuo=4.07), leg)
    assert leg.avg_price == 1.43


def test_l_ordine_sparito_dai_vivi_va_in_riconciliazione(vivi):
    """Tre casi opposti (abbinato tutto / annullato / mai arrivato) non si
    indovinano: si riconcilia."""
    leg = _gamba(ref="mike-t1")
    _segui(vivi(ref="un-altro"), leg)
    assert leg.status == E.STATUS_RECONCILE


# ===========================================================================
# 4. IL LETTORE DEI CAMPI — «assente» e «zero» non sono la stessa cosa
# ===========================================================================
def test_un_campo_presente_ma_nullo_resta_nullo():
    assert S.campo_ordine({"avg_price_matched": None}, "avg_price_matched", 9.9) is None


def test_un_campo_assente_vale_il_difetto():
    assert S.campo_ordine({}, "avg_price_matched", 9.9) == 9.9


def test_si_accettano_tutte_e_due_le_grafie():
    """Non per usarle, ma perche' un cambio di normalizzazione a monte non
    possa piu' rompere in SILENZIO una lettura da cui dipendono ordini veri."""
    assert S.campo_ordine({"sizeMatched": 3.0}, "size_matched") == 3.0
    assert S.campo_ordine({"size_matched": 3.0}, "size_matched") == 3.0


def test_un_numero_illeggibile_non_fa_esplodere_il_ciclo():
    assert S._num_ordine({"size_matched": "boh"}, "size_matched", 0.0) == 0.0
    assert S._num_ordine(None, "size_matched", 0.0) == 0.0
