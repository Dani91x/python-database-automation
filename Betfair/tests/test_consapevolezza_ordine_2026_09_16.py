"""CONSAPEVOLEZZA DELL'ORDINE — i tre bot REST (C.12a, 16/09/2026).

La domanda dell'utente, il 16/09: «ordine x a prezzo y: il bot sa se e' stato
abbinato? in che quantita'? tutto o parziale? si comporta di conseguenza?».
La matrice del mattino (MATRICE_CONSAPEVOLEZZA_ORDINI_2026-09-16.md) ha
risposto NO su tre punti che valgono soldi:

  1. `PlaceResult` non portava la size CHIESTA ne' il residuo: dopo la conferma
     nessuno sapeva piu' quanto era stato chiesto (`size` viene sovrascritta
     con l'abbinato);
  2. `cancel_order_live` NON ESISTEVA: tutti gli «annulla» dei tre bot erano
     CONTABILI — cambiavano lo stato della riga mentre su Betfair l'ordine
     restava VIVO e si abbinava piu' tardi, senza che nessuno lo
     contabilizzasse (posizione doppia con soldi veri);
  3. `errorCode` non veniva letto da nessuno: INSUFFICIENT_FUNDS e
     INVALID_PROFIT_RATIO erano indistinguibili da un `ok=False` generico.

NESSUN FINTO SCRITTO A MANO SULLE RISPOSTE DI BETFAIR (lezione del 15/09,
`feedback_i_finti_devono_parlare_come_il_vero`): qui si costruiscono i PAYLOAD
REST GREZZI — camelCase, come li manda l'exchange, con i nomi dei campi
verificati su `betfairlightweight/resources/bettingresources.py` — e si fanno
passare dalle FUNZIONI VERE di `omega_market`. Quello che arriva ai bot e'
quindi un `PlaceResult` vero, un `CancelResult` vero e ordini in snake_case
prodotti dal normalizzatore vero.

ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.mike import engine as ME
from Betfair.mike import service as MS
from Betfair.omega import omega_market as OM
from Betfair.omega import omega_service as OS
from Betfair.safe_strategy import execution as X

ORA = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


# ===========================================================================
# 0. I PAYLOAD GREZZI DI BETFAIR (camelCase, come arrivano davvero)
# ===========================================================================
def place_report(*, matched=0.0, prezzo=None, bet_id="B1", stato="SUCCESS",
                 order_status="EXECUTION_COMPLETE", codice=None):
    """PlaceExecutionReport grezzo. Campi da `PlaceOrderInstructionReports`
    (`bettingresources.py:981-1011`): status, orderStatus, betId,
    averagePriceMatched, sizeMatched, placedDate, errorCode."""
    ir = {"status": stato, "orderStatus": order_status, "betId": bet_id,
          "sizeMatched": matched, "averagePriceMatched": prezzo,
          "placedDate": "2026-09-16T12:00:00.000Z"}
    if codice:
        ir["errorCode"] = codice
    return {"status": stato, "marketId": "1.234", "instructionReports": [ir]}


def cancel_report(*, tagliato=0.0, stato="SUCCESS", codice=None):
    """CancelExecutionReport grezzo (`bettingresources.py:1049-1091`)."""
    cir = {"status": stato, "sizeCancelled": tagliato,
           "cancelledDate": "2026-09-16T12:00:05.000Z",
           "instruction": {"betId": "B1"}}
    if codice:
        cir["errorCode"] = codice
    return {"status": stato, "marketId": "1.234", "instructionReports": [cir]}


def current_orders(*, bet_id="B1", matched=0.0, residuo=0.0, prezzo=None,
                   ref="mike-t1", stato="EXECUTABLE", annullato=0.0):
    """Risposta grezza di listCurrentOrders (`CurrentOrder`, :664-711)."""
    return {"currentOrders": [{
        "betId": bet_id, "marketId": "1.234", "selectionId": 55, "side": "LAY",
        "status": stato, "sizeMatched": matched, "averagePriceMatched": prezzo,
        "sizeRemaining": residuo, "sizeCancelled": annullato, "sizeLapsed": 0.0,
        "sizeVoided": 0.0, "customerOrderRef": ref,
        "matchedDate": "2026-09-16T12:00:03.000Z",
        "placedDate": "2026-09-16T12:00:00.000Z",
        "priceSize": {"price": 2.14, "size": 5.0},
    }]}


@pytest.fixture()
def betfair(monkeypatch):
    """Betfair finto A LIVELLO DI RETE: si sostituisce solo il trasporto, tutte
    le funzioni di `omega_market` restano quelle vere."""

    class Rete:
        def __init__(self):
            self.place = place_report(matched=5.0, prezzo=2.14)
            self.cancel = cancel_report(tagliato=5.0)
            self.current = {"currentOrders": []}
            # book vuoto = IGNOTO: il place-and-trim sceglie il percorso
            # conservativo (parcheggio lontano + replace), che e' la sequenza
            # storica di questi test.
            self.book = []
            self.cleared = {"clearedOrders": []}
            self.chiamate = []

        def muta(self, fn):
            # si distingue place da cancel guardando il metodo richiesto
            visto = {}

            class Cli:
                def place_orders(_s, *a, **k):
                    visto["k"] = "place"
                    return self.place

                def betting_rpc(_s, method=None, params=None, **k):
                    m = str(method or (a[0] if (a := ()) else ""))
                    visto["k"] = m
                    if "cancelOrders" in m:
                        return self.cancel
                    if "replaceOrders" in m:
                        return self.place
                    return {}

            out = fn(Cli())
            self.chiamate.append(visto.get("k"))
            return out

        def legge(self, fn):
            class Cli:
                def betting_rpc(_s, method=None, params=None, *a, **k):
                    m = str(method or (a[0] if a else ""))
                    if "listCurrentOrders" in m:
                        return self.current
                    if "listClearedOrders" in m:
                        return self.cleared
                    return {}

                def list_current_orders(_s, **k):
                    return self.current

                def list_cleared_orders(_s, **k):
                    return self.cleared

                def list_market_book(_s, *a, **k):
                    # 17/09: il place-and-trim legge il book per sapere se la
                    # quota target e' abbinabile. Il finto parla come il vero:
                    # stesso nome di metodo, stessa forma (lista di book).
                    return self.book

            return fn(Cli())

    rete = Rete()
    monkeypatch.setattr(OM, "call_mutating", rete.muta)
    monkeypatch.setattr(OM, "call", rete.legge)
    return rete


# ===========================================================================
# 1. IL CONTRATTO DEL DATO — `PlaceResult` sa dire chiesto, residuo e codice
# ===========================================================================
def test_place_result_porta_la_size_chiesta_e_il_residuo(betfair):
    """Il reperto n.1 della matrice: la size CHIESTA spariva."""
    betfair.place = place_report(matched=5.0, prezzo=2.14)
    res = OM.place_order_live(market_id="1.234", selection_id=55, price=2.14,
                              size=5.0, event_id="E1", side="lay")
    assert res.ok is True
    assert res.size_requested == 5.0, "la size CHIESTA deve sopravvivere al place"
    assert res.price_requested == 2.14
    assert res.size_remaining == 0.0, "FILL_OR_KILL: Betfair uccide il non abbinato"
    assert res.betfair_updated_at == "2026-09-16T12:00:00.000Z"


def test_un_parziale_dice_quanto_e_rimasto_fuori(betfair):
    """Parziale subito, z su x: 2,00 abbinati su 5,00 chiesti."""
    betfair.place = place_report(matched=2.0, prezzo=2.14)
    res = OM.place_order_live(market_id="1.234", selection_id=55, price=2.14,
                              size=5.0, event_id="E1", side="lay",
                              fill_or_kill=False)
    assert (res.size_requested, res.size_matched, res.size_remaining) == (5.0, 2.0, 3.0)


def test_il_codice_di_errore_di_betfair_arriva_al_chiamante(betfair):
    """`errorCode` era sepolto in `raw` e nessuno lo leggeva."""
    betfair.place = place_report(stato="FAILURE", order_status=None, bet_id=None,
                                 codice="INVALID_PROFIT_RATIO")
    res = OM.place_order_live(market_id="1.234", selection_id=55, price=2.14,
                              size=5.0, event_id="E1", side="lay")
    assert res.ok is False
    assert res.error_code == "INVALID_PROFIT_RATIO"


def test_gli_ordini_vivi_portano_annullato_scaduto_e_quando(betfair):
    """`sizeCancelled`/`sizeLapsed`/`sizeVoided`/`matchedDate` c'erano gia' nella
    risposta di Betfair e li buttavamo via."""
    betfair.current = current_orders(matched=2.0, residuo=3.0, prezzo=2.12,
                                     annullato=0.5)
    o = OM.list_current_orders("mike")[0]
    # le chiavi STORICHE non cambiano (le legge tutta la riconciliazione)
    assert o["size_matched"] == 2.0 and o["size_remaining"] == 3.0
    assert o["avg_price_matched"] == 2.12
    # le nuove
    assert o["size_cancelled"] == 0.5 and o["size_lapsed"] == 0.0
    assert o["matched_date"] == "2026-09-16T12:00:03.000Z"
    assert o["size_requested"] == 5.0 and o["price_requested"] == 2.14
    assert o["average_price_matched"] == 2.12, "entrambe le grafie, mai una sola"


# ===========================================================================
# 2. L'ANNULLAMENTO ARRIVA A BETFAIR — e si rilegge
# ===========================================================================
def test_cancel_riuscito_l_ordine_non_e_piu_vivo(betfair):
    betfair.cancel = cancel_report(tagliato=5.0)
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": [{"betId": "B1", "sizeSettled": 0.0,
                                          "priceMatched": None}]}
    ann = OM.cancel_order_live("B1", "1.234")
    assert ann.ok is True and ann.size_cancelled == 5.0
    assert ann.riletto is True
    assert ann.size_matched == 0.0 and ann.size_remaining == 0.0


def test_cancel_rifiutato_da_betfair_non_e_un_annullamento(betfair):
    """BET_TAKEN_OR_LAPSED: l'ordine non e' stato annullato da noi."""
    betfair.cancel = cancel_report(stato="FAILURE", codice="BET_TAKEN_OR_LAPSED")
    betfair.current = current_orders(bet_id="B1", matched=5.0, residuo=0.0, prezzo=2.14)
    ann = OM.cancel_order_live("B1", "1.234")
    assert ann.ok is False and ann.error_code == "BET_TAKEN_OR_LAPSED"
    assert ann.size_matched == 5.0, "abbinato mentre provavamo ad annullare"


def test_cancel_con_abbinamento_nel_frattempo(betfair):
    """Annullato il residuo, ma 2,00 si erano gia' abbinati: quella parte e' una
    POSIZIONE e non deve sparire."""
    betfair.cancel = cancel_report(tagliato=3.0)
    betfair.current = current_orders(bet_id="B1", matched=2.0, residuo=0.0, prezzo=2.10)
    ann = OM.cancel_order_live("B1", "1.234")
    assert ann.ok is True and ann.size_cancelled == 3.0
    assert ann.size_matched == 2.0 and ann.avg_price_matched == 2.10


def test_cancel_a_esito_ignoto_solleva(betfair):
    """TIMEOUT: l'ordine puo' essere vivo o morto. Non si decide al buio."""
    betfair.cancel = {"status": "TIMEOUT", "instructionReports": []}
    with pytest.raises(RuntimeError):
        OM.cancel_order_live("B1", "1.234")


# ===========================================================================
# 3. SAFE — rifiuto CERTO del place-and-trim, parziale, codice in attivita'
# ===========================================================================
class DbFinto:
    """Le stesse firme del `db` vero (`update_trade(id, **campi)`, `log(kind, payload)`)."""

    def __init__(self, colonne_nuove=True):
        self.righe = {}
        self.attivita = []
        self.colonne_nuove = colonne_nuove

    def update_trade(self, trade_id, **campi):
        if not self.colonne_nuove:
            for c in X.COLONNE_CONSAPEVOLEZZA:
                if c in campi:
                    raise RuntimeError(
                        "{'code':'PGRST204','message':\"Could not find the "
                        f"'{c}' column of 'safe_strategy_trades' in the schema cache\"}}")
        self.righe.setdefault(int(trade_id), {}).update(campi)

    def log(self, kind, payload=None, *a):
        self.attivita.append((kind, payload or {}))

    def kinds(self):
        return [k for k, _ in self.attivita]

    def payload(self, kind):
        return next(p for k, p in self.attivita if k == kind)


class MercatoVero:
    """Il mercato dei bot: inoltra alle funzioni VERE di `omega_market`, che a
    loro volta parlano con la rete finta della fixture."""

    place_order_live = staticmethod(OM.place_order_live)
    place_submin_live = staticmethod(OM.place_submin_live)
    cancel_order_live = staticmethod(OM.cancel_order_live)
    order_state_by_bet_id = staticmethod(OM.order_state_by_bet_id)
    list_current_orders = staticmethod(OM.list_current_orders)


def _place_safe(db, *, size=5.0, price=2.14, mode="live", side="lay"):
    return X.place(db=db, market=MercatoVero(), mode=mode, event_id="E1",
                   market_id="1.234", selection_id=55, side=side, price=price,
                   size=size, best_size=None, ladder=(), client_ref="safe-t7",
                   trade_id=7, meta={}, now=ORA, params={"execution_mode": "rest"})


def test_safe_parziale_porta_chiesto_abbinato_residuo(betfair, monkeypatch):
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    betfair.place = place_report(matched=2.0, prezzo=2.12)
    db = DbFinto()
    out = _place_safe(db)
    assert out.status == "open"
    assert (out.size_requested, out.size, out.size_remaining) == (5.0, 2.0, 0.0)
    assert out.avg_price_matched == 2.12
    # l'attivita' lo DICE, non lo lascia solo nei numeri
    p = db.payload("place_parziale")
    assert p["size_requested"] == 5.0 and p["size_matched"] == 2.0
    assert "parziale 2.00 su 5.00" in p["nota"]


def test_safe_rifiuto_invalid_profit_ratio_chiude_la_riga_in_error(betfair, monkeypatch):
    """Il reperto n.3 della TOP-15: un place-and-trim rifiutato lasciava la riga
    'pending' IN VERIFICA su un ordine che non esiste, e il segnale bloccato."""
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    # il place-and-trim parcheggia (place), taglia (cancel), riprezza (replace):
    # il riprezzo viene RIFIUTATO con INVALID_PROFIT_RATIO e il residuo ritirato.
    passi = {"n": 0}

    def muta(fn):
        passi["n"] += 1
        if passi["n"] == 1:              # parcheggio
            return place_report(matched=0.0, bet_id="B9")
        if passi["n"] == 2:              # taglio
            return cancel_report(tagliato=1.20)
        if passi["n"] == 3:              # riprezzo RIFIUTATO
            return {"status": "FAILURE", "instructionReports": [
                {"status": "FAILURE", "errorCode": "INVALID_PROFIT_RATIO"}]}
        return cancel_report(tagliato=0.80)   # ritiro del residuo: RIUSCITO
    monkeypatch.setattr(OM, "call_mutating", lambda fn: muta(fn))
    # 17/09 — dopo il taglio il place-and-trim RILEGGE l'ordine da Betfair
    # (`listCurrentOrders` per betId): il finto risponde come il vero, con il
    # residuo al target (2,00 di parcheggio - 1,20 tagliati = 0,80).
    betfair.current = current_orders(bet_id="B9", residuo=0.80, stato="EXECUTABLE")
    db = DbFinto()
    out = _place_safe(db, size=0.80, side="back")
    assert out.status == "error", "rifiuto CERTO: mai 'pending' su un ordine inesistente"
    assert out.error_code == "INVALID_PROFIT_RATIO"
    assert "INVALID_PROFIT_RATIO" in out.fill_note
    assert db.payload("place_rifiutato")["error_code"] == "INVALID_PROFIT_RATIO"
    assert "place_exception" not in db.kinds(), "non e' un esito ignoto"


def test_safe_rifiuto_col_codice_scritto_in_attivita(betfair, monkeypatch):
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    betfair.place = place_report(stato="FAILURE", order_status="EXPIRED",
                                 bet_id=None, codice="INSUFFICIENT_FUNDS")
    db = DbFinto()
    out = _place_safe(db)
    assert out.status == "error" and out.error_code == "INSUFFICIENT_FUNDS"
    assert db.payload("place_rifiutato")["error_code"] == "INSUFFICIENT_FUNDS"


def test_safe_se_il_ritiro_fallisce_l_esito_resta_IGNOTO(betfair, monkeypatch):
    """Se il residuo NON si riesce a ritirare l'ordine puo' essere vivo: quello
    NON e' un rifiuto certo, e la riga deve restare in riconciliazione."""
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    passi = {"n": 0}

    def muta(fn):
        passi["n"] += 1
        if passi["n"] == 1:
            return place_report(matched=0.0, bet_id="B9")
        if passi["n"] == 2:
            return cancel_report(tagliato=1.20)
        if passi["n"] == 3:
            return {"status": "FAILURE", "instructionReports": [
                {"status": "FAILURE", "errorCode": "INVALID_PROFIT_RATIO"}]}
        raise RuntimeError("rete KO sul ritiro")
    monkeypatch.setattr(OM, "call_mutating", lambda fn: muta(fn))
    betfair.current = current_orders(bet_id="B9", residuo=0.80, stato="EXECUTABLE")
    db = DbFinto()
    out = _place_safe(db, size=0.80, side="back")
    assert out.status == "pending", "ordine forse vivo: si riconcilia, non si chiude"
    assert "place_exception" in db.kinds()


# ===========================================================================
# 4. LE COLONNE NUOVE — si scrivono se ci sono, e non rompono se non ci sono
# ===========================================================================
def test_le_colonne_nuove_vengono_scritte_quando_esistono():
    db = DbFinto(colonne_nuove=True)
    X.aggiorna_trade(db, 7, campi={"status": "open", "size": 2.0},
                     consapevolezza={"size_requested": 5.0, "size_matched": 2.0,
                                     "size_remaining": 3.0, "avg_price_matched": 2.12})
    r = db.righe[7]
    assert r["size_requested"] == 5.0 and r["size_remaining"] == 3.0
    assert r["avg_price_matched"] == 2.12


def test_senza_migrazione_non_esplode_niente():
    """Migrazione non applicata: l'aggiornamento passa lo stesso, senza le
    colonne nuove e senza eccezioni (come `live_follow.record`)."""
    db = DbFinto(colonne_nuove=False)
    X.aggiorna_trade(db, 7, campi={"status": "open", "size": 2.0},
                     consapevolezza={"size_requested": 5.0, "size_matched": 2.0})
    assert db.righe[7] == {"status": "open", "size": 2.0}
    # e il rilevamento avviene UNA volta sola: il secondo giro non riprova
    db.righe.clear()
    X.aggiorna_trade(db, 8, campi={"status": "open"},
                     consapevolezza={"size_requested": 5.0})
    assert db.righe[8] == {"status": "open"}


def test_un_errore_di_rete_non_viene_scambiato_per_una_colonna_mancante():
    """C5: un timeout non e' un errore di schema. Se lo fosse, si riscriverebbe
    la riga credendo di aver capito, mentre il database e' muto."""
    class DbMuto(DbFinto):
        def update_trade(self, trade_id, **campi):
            raise RuntimeError("timeout leggendo la risposta")

    with pytest.raises(RuntimeError):
        X.aggiorna_trade(DbMuto(), 7, campi={"status": "open"},
                         consapevolezza={"size_requested": 5.0})


# ===========================================================================
# 5. MIKE — l'annullamento non e' piu' contabile
# ===========================================================================
class DbMike(DbFinto):
    """`mike_trades` con le colonne VERE che il servizio legge."""

    def __init__(self, riga=None, colonne_nuove=True):
        super().__init__(colonne_nuove)
        r = {"id": 1, "signal_key": "under_green-0-2", "role": "under_green",
             "cycle_no": 0, "side": "lay", "status": "pending", "bet_id": "B1",
             "mode": "live", "market_id": "1.234", "selection_id": 55, "meta": {}}
        r.update(riga or {})
        self.riga = r

    def trades_for_event(self, _eid, **_kw):
        return [self.riga]

    def log(self, kind, payload=None, event_id=None):
        self.attivita.append((kind, payload or {}))


def _gamba_mike(**kw):
    base = dict(ref="under_green-0-2", role="under_green", market=ME.MARKET_OU35,
                selection=ME.SEL_UNDER, side="lay", price=1.43, size=5.0,
                matched=0.0, status="pending", cycle_no=0)
    base.update(kw)
    return ME.Leg(**base)


def test_mike_cancel_riuscito_la_riga_si_chiude(betfair):
    betfair.cancel = cancel_report(tagliato=5.0)
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": [{"betId": "B1", "sizeSettled": 0.0}]}
    db, leg = DbMike(), _gamba_mike()
    esito = MS._mark_trade_cancelled(db, "E1", leg, "cancelled_by_user",
                                     market=MercatoVero())
    assert esito == "cancelled" and leg.status == "cancelled"
    assert db.righe[1]["status"] == "error"
    assert "cancel_richiesto" in db.kinds() and "cancel_esito" in db.kinds()
    assert db.payload("cancel_esito")["confermato"] is True


def test_mike_cancel_fallito_la_riga_resta_in_riconciliazione(betfair):
    """FAIL-CLOSED: Betfair non conferma -> mai «annullato» su un ordine che
    puo' abbinarsi cinque minuti dopo."""
    betfair.cancel = cancel_report(stato="FAILURE", codice="ERROR_IN_ORDER")
    betfair.current = current_orders(bet_id="B1", matched=0.0, residuo=5.0)
    db, leg = DbMike(), _gamba_mike()
    esito = MS._mark_trade_cancelled(db, "E1", leg, "cancelled_by_engine",
                                     market=MercatoVero())
    assert esito == ME.STATUS_RECONCILE and leg.status == ME.STATUS_RECONCILE
    assert 1 not in db.righe, "la riga NON viene chiusa"
    assert db.payload("cancel_esito")["confermato"] is False


def test_mike_cancel_con_abbinamento_nel_frattempo_conserva_la_posizione(betfair):
    """L'ordine si e' abbinato mentre lo annullavamo: quella posizione esiste e
    non deve essere dimenticata."""
    betfair.cancel = cancel_report(tagliato=2.0)
    betfair.current = current_orders(bet_id="B1", matched=3.0, residuo=0.0, prezzo=1.42)
    db, leg = DbMike(), _gamba_mike()
    esito = MS._mark_trade_cancelled(db, "E1", leg, "cancelled_manual",
                                     market=MercatoVero())
    assert esito == "open" and leg.status == "open"
    assert leg.matched == 3.0 and leg.avg_price == 1.42
    assert db.righe[1]["status"] == "open" and db.righe[1]["size"] == 3.0
    assert db.righe[1]["size_matched"] == 3.0
    assert "fill_resting" in db.kinds()


def test_mike_senza_ordine_reale_non_si_chiama_betfair(betfair):
    """Riga paper, o senza bet_id: non c'e' niente da annullare e il
    comportamento storico resta identico."""
    db, leg = DbMike(riga={"mode": "paper"}), _gamba_mike()
    esito = MS._mark_trade_cancelled(db, "E1", leg, "cancelled_by_user",
                                     market=MercatoVero())
    assert esito == "cancelled" and db.righe[1]["status"] == "error"
    assert "cancel_richiesto" not in db.kinds()
    assert betfair.chiamate == [], "nessuna chiamata a Betfair per una riga paper"


def test_mike_legge_il_residuo_DA_BETFAIR_non_per_sottrazione(betfair):
    """Il residuo vivo era DEDOTTO da `leg.size - leg.matched`. Qui Betfair dice
    3,00 mentre la sottrazione direbbe 3,00 solo per coincidenza: se Betfair
    riduce l'ordine i due numeri divergono, e vince Betfair."""
    betfair.current = current_orders(bet_id="B1", matched=1.5, residuo=2.0,
                                     prezzo=1.42, ref="mike-t1")
    db, leg = DbMike(), _gamba_mike()

    class Mk:
        @staticmethod
        def list_current_orders():
            return OM.list_current_orders("mike")

    MS._segui_resting_live(db=db, market=Mk(), leg=leg, extra={}, params={},
                           now_ts=ORA.timestamp(), ev={"event_id": "E1"})
    assert leg.matched == 1.5
    # la sottrazione direbbe 3,50: il numero vero e' quello di Betfair
    assert db.righe[1]["size_remaining"] == 2.0
    assert db.righe[1]["size_requested"] == 5.0
    p = db.payload("fill_resting")
    assert "parziale 1.50 su 5.00, residuo 2.00 vivo" in p["nota"]


# ===========================================================================
# 6. OMEGA — non si dichiara morto un ordine che Betfair dice vivo
# ===========================================================================
def test_omega_non_chiude_la_riga_se_l_ordine_e_ancora_vivo(betfair):
    betfair.cancel = cancel_report(stato="FAILURE", codice="ERROR_IN_ORDER")
    betfair.current = current_orders(bet_id="B7", matched=0.0, residuo=4.0,
                                     ref="omega-t3")
    db = DbFinto()
    tr = {"id": 3, "event_id": "E1", "bet_id": "B7", "market_id": "1.234"}
    assert OS._ordine_ancora_vivo(MercatoVero(), tr, db=db, now=ORA) is True
    assert db.payload("cancel_esito")["size_remaining"] == 4.0


def test_omega_senza_residuo_la_riga_puo_essere_chiusa(betfair):
    betfair.cancel = cancel_report(tagliato=4.0)
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": [{"betId": "B7", "sizeSettled": 0.0}]}
    db = DbFinto()
    tr = {"id": 3, "event_id": "E1", "bet_id": "B7", "market_id": "1.234"}
    assert OS._ordine_ancora_vivo(MercatoVero(), tr, db=db, now=ORA) is False


def test_omega_senza_bet_id_il_comportamento_storico_non_cambia(betfair):
    db = DbFinto()
    tr = {"id": 3, "event_id": "E1", "bet_id": None, "market_id": "1.234"}
    assert OS._ordine_ancora_vivo(MercatoVero(), tr, db=db, now=ORA) is False
    assert db.kinds() == [], "nessuna chiamata, nessuna attivita'"


def test_omega_esito_ignoto_dell_annullamento_non_chiude_la_riga(betfair, monkeypatch):
    """Sul percorso a coda «non lo so» non e' «non esiste»: se l'annullamento
    non si riesce nemmeno a tentare, la riga resta in verifica."""
    class SenzaCancel:
        pass

    db = DbFinto()
    tr = {"id": 3, "event_id": "E1", "bet_id": "B7", "market_id": "1.234"}
    # senza ``ignoto_e_vivo`` il comportamento storico non cambia
    assert OS._ordine_ancora_vivo(SenzaCancel(), tr, db=db, now=ORA) is False
    assert OS._ordine_ancora_vivo(SenzaCancel(), tr, db=db, now=ORA,
                                  ignoto_e_vivo=True) is True
    assert db.payload("cancel_esito")["esito_ignoto"] is True


def test_omega_bet_id_esplicito_dallo_specchio(betfair):
    """Sul percorso a coda il bet_id non sta sulla riga: arriva dallo specchio."""
    betfair.cancel = cancel_report(stato="FAILURE", codice="ERROR_IN_ORDER")
    betfair.current = current_orders(bet_id="B9", matched=0.0, residuo=2.5)
    db = DbFinto()
    tr = {"id": 3, "event_id": "E1", "bet_id": None, "market_id": "1.234"}
    assert OS._ordine_ancora_vivo(MercatoVero(), tr, db=db, now=ORA,
                                  bet_id="B9", ignoto_e_vivo=True) is True
    assert db.payload("cancel_richiesto")["bet_id"] == "B9"


def test_omega_oltre_la_deadline_l_ordine_sconosciuto_viene_annullato(betfair, monkeypatch):
    """`live_rest_not_found`: la riga stava per diventare terminale CON un
    bet_id e SENZA che nessuno avesse mai chiesto l'annullamento."""
    betfair.cancel = cancel_report(stato="FAILURE", codice="BET_TAKEN_OR_LAPSED")
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}
    chiusa = {}

    class DbCoda(DbFinto):
        def get_live_order_request(self, rid):
            return {"id": rid, "status": "done", "bet_id": "B7", "result": {}}

        def get_live_order_mirror(self, ref, mode):
            return None

        def list_trades(self, _s):
            return []

    monkeypatch.setattr(OS, "_flumine_no_fill_error",
                        lambda tr, **kw: chiusa.setdefault("reason", kw.get("reason")) and 1 or 1)
    db = DbCoda()
    tr = {"id": 3, "event_id": "E1", "mode": "live", "market_id": "1.234",
          "side": "lay", "price": 2.0, "size": 5.0,
          "meta": {"flumine_request_id": 11,
                   "flumine_enqueued_at": "2026-09-16T11:00:00+00:00"}}
    n = OS._poll_one_flumine_live_trade(tr, db=db, market=MercatoVero(),
                                        params={"live_fill_deadline_s": 20}, now=ORA)
    assert n == 1 and chiusa["reason"] == "live_rest_not_found"
    # l'annullamento e' stato CHIESTO prima di chiudere
    assert "cancel_richiesto" in db.kinds() and "cancel_esito" in db.kinds()


def test_omega_oltre_la_deadline_con_rete_muta_la_riga_resta_viva(betfair, monkeypatch):
    """Stessa deadline, ma il cancel non si riesce a mandare: la riga NON si
    chiude (fail-closed) e si riprova al ciclo dopo."""
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}

    class DbCoda(DbFinto):
        def get_live_order_request(self, rid):
            return {"id": rid, "status": "done", "bet_id": "B7", "result": {}}

        def get_live_order_mirror(self, ref, mode):
            return None

    class MercatoSenzaCancel:
        order_state_by_bet_id = staticmethod(OM.order_state_by_bet_id)

    def mai(*_a, **_k):
        raise AssertionError("la riga non doveva essere chiusa")
    monkeypatch.setattr(OS, "_flumine_no_fill_error", mai)
    db = DbCoda()
    tr = {"id": 3, "event_id": "E1", "mode": "live", "market_id": "1.234",
          "side": "lay", "price": 2.0, "size": 5.0,
          "meta": {"flumine_request_id": 11,
                   "flumine_enqueued_at": "2026-09-16T11:00:00+00:00"}}
    assert OS._poll_one_flumine_live_trade(tr, db=db, market=MercatoSenzaCancel(),
                                           params={"live_fill_deadline_s": 20},
                                           now=ORA) == 0


# ===========================================================================
# 6-bis. `order_state_by_bet_id` sa dire DA QUANDO
# ===========================================================================
def test_lo_stato_per_bet_id_porta_gli_istanti_di_betfair(betfair):
    """E' la SOLA strada quando l'ordine non e' nella lista del giro: senza
    questi campi `betfair_updated_at` resterebbe vuoto proprio li'."""
    betfair.current = current_orders(bet_id="B1", matched=2.0, residuo=3.0, prezzo=2.12)
    st = OM.order_state_by_bet_id("B1")
    assert st["found"] is True and st["size_matched"] == 2.0
    assert st["matched_date"] == "2026-09-16T12:00:03.000Z"
    assert st["placed_date"] == "2026-09-16T12:00:00.000Z"


def test_lo_stato_di_un_ordine_REGOLATO_porta_lastMatchedDate(betfair):
    """Su un ordine regolato l'ultimo abbinamento si chiama `lastMatchedDate`:
    stessa cosa, nome diverso — e va normalizzato lo stesso."""
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": [{
        "betId": "B1", "sizeSettled": 5.0, "priceMatched": 2.14,
        "lastMatchedDate": "2026-09-16T12:00:09.000Z",
        "placedDate": "2026-09-16T12:00:00.000Z",
        "settledDate": "2026-09-16T14:00:00.000Z"}]}
    st = OM.order_state_by_bet_id("B1")
    assert st["found"] is True and st["size_matched"] == 5.0
    assert st["matched_date"] == "2026-09-16T12:00:09.000Z"
    assert st["settled_date"] == "2026-09-16T14:00:00.000Z"


def test_il_cancel_dice_anche_da_quando(betfair):
    betfair.cancel = cancel_report(tagliato=3.0)
    betfair.current = current_orders(bet_id="B1", matched=2.0, residuo=0.0, prezzo=2.10)
    ann = OM.cancel_order_live("B1", "1.234")
    assert ann.betfair_updated_at == "2026-09-16T12:00:03.000Z"


def test_mike_scrive_da_quando_sulla_riga_dopo_un_annullamento(betfair):
    betfair.cancel = cancel_report(tagliato=2.0)
    betfair.current = current_orders(bet_id="B1", matched=3.0, residuo=0.0, prezzo=1.42)
    db, leg = DbMike(), _gamba_mike()
    MS._mark_trade_cancelled(db, "E1", leg, "cancelled_manual", market=MercatoVero())
    assert db.righe[1]["betfair_updated_at"] == "2026-09-16T12:00:03.000Z"


# ===========================================================================
# 7. IL VOID DETTO PER NOME (comportamento invariato)
# ===========================================================================
def test_il_void_dichiarato_da_betfair_si_distingue_da_quello_dedotto():
    assert OM.void_reason("VOIDED", True) == "market_status_void"
    assert OM.void_reason("CLOSED", True) == "closed_senza_winner"
    assert OM.void_reason("CLOSED", False) is None


# ===========================================================================
# 8. SAFE - LA RICONCILIAZIONE RACCONTA IL VERO E ANNULLA DAVVERO (C.12a, 16/09)
#
# Due reperti della matrice, sulla stessa funzione (`bot_service.
# reconcile_pending`):
#   - n.12 - parziale con residuo vivo: `_reconcile_by_bet_id` tornava `keep` e
#     la riga restava 'pending' MUTA finche' il residuo non moriva. Esposizione
#     contata, segnale bloccato, e nessuno sapeva che 2,00 dei 5,00 chiesti
#     erano gia' una posizione.
#   - n.6 - nessun annullamento vero: una riga live con `bet_id` diventava
#     'error' (o spariva con `delete_trade`) mentre l'ordine era VIVO su
#     Betfair e poteva abbinarsi minuti dopo.
#
# Come sopra: nessun finto scritto a mano sulle risposte di Betfair. Gli ordini
# arrivano dai PAYLOAD GREZZI camelCase passati per le funzioni VERE di
# `omega_market` (`order_state_by_bet_id`, `list_current_orders`,
# `cancel_order_live`), e le righe portano le COLONNE VERE della migrazione
# `trades_consapevolezza_ordine_2026-09-16.sql`.
# ===========================================================================
from Betfair.safe_strategy import bot_service as S   # noqa: E402

VECCHIO = "2026-09-16T11:00:00+00:00"   # oltre RECON_GRACE_S (120 s) da ORA


class DbSafe(DbFinto):
    """Il `db` di Safe: le stesse firme di `safe_strategy/bot_db`."""

    def __init__(self, righe=None, colonne_nuove=True):
        super().__init__(colonne_nuove=colonne_nuove)
        self.righe = {int(r["id"]): dict(r) for r in (righe or [])}

    def list_trades(self, status=None):
        return [dict(r) for r in self.righe.values()
                if status is None or r.get("status") == status]

    def get_trade(self, trade_id):
        r = self.righe.get(int(trade_id))
        return dict(r) if r else None

    def delete_trade(self, trade_id):
        # come il vero: cancella SOLO una riserva ancora 'pending'
        r = self.righe.get(int(trade_id))
        if r and r.get("status") == "pending":
            self.righe.pop(int(trade_id))

    def closing_trades_for(self, ids):
        chiavi = {int(i) for i in ids}
        return [dict(r) for r in self.righe.values()
                if r.get("closes_trade_id") in chiavi]


def riga_safe(**kw):
    """Riga di `safe_strategy_trades` con le colonne VERE (migrazioni
    `safe_strategy_bot.sql` + `trades_consapevolezza_ordine_2026-09-16.sql`).
    'pending' + marker di riconciliazione = esito del place IGNOTO."""
    r = {"id": 7, "event_id": "E1", "market_id": "1.234", "market_type": "MATCH_ODDS",
         "selection_id": 55, "selection_name": "Home", "side": "lay", "strategy": "base",
         "mode": "live", "status": "pending", "origin": "auto", "signal_key": "k1",
         "price": 2.14, "size": 5.0, "liability": 5.7, "commission": 0.05,
         "bet_id": "B7", "closes_trade_id": None, "placed_at": VECCHIO,
         "meta": {"phase": "reserved", "reason": "place_exception_reconciling"},
         "size_requested": None, "size_matched": None, "size_remaining": None,
         "avg_price_matched": None, "betfair_updated_at": None}
    r.update(kw)
    return r


class MercatoSafe:
    """Il mercato del bot Safe: le funzioni VERE di `omega_market`."""

    place_order_live = staticmethod(OM.place_order_live)
    cancel_order_live = staticmethod(OM.cancel_order_live)
    order_state_by_bet_id = staticmethod(OM.order_state_by_bet_id)
    list_current_orders = staticmethod(OM.list_current_orders)
    list_cleared_orders = staticmethod(OM.list_cleared_orders)


class MercatoCheRivela(MercatoSafe):
    """Fra la DECISIONE e l'ANNULLAMENTO passa del tempo.

    E' il caso vero, non un trucco del test: `listCurrentOrders` non elencava
    l'ordine (finestra di consistenza, o la paginazione a 100 record della
    matrice) e un istante dopo, quando si chiede l'annullamento, l'ordine c'e'
    - con residuo vivo o gia' abbinato. E' esattamente la situazione in cui
    prima la riga diventava terminale su un ordine reale."""

    def __init__(self, rete, dopo):
        self.rete, self.dopo = rete, dopo

    def cancel_order_live(self, bet_id, market_id, size_reduction=None):
        self.rete.current = self.dopo
        return OM.cancel_order_live(bet_id, market_id, size_reduction)


@pytest.fixture(autouse=True)
def _memoria_pulita():
    """La memoria delle scritture gia' fatte e' di processo: fra un test e
    l'altro si azzera, come dopo un riavvio del servizio."""
    S._CONSAPEVOLEZZA_SCRITTA.clear()
    S._PENDING_CICLO.clear()
    yield
    S._CONSAPEVOLEZZA_SCRITTA.clear()
    S._PENDING_CICLO.clear()


# --- 8a. PARZIALE CON RESIDUO VIVO -----------------------------------------
def test_safe_il_parziale_con_residuo_vivo_finisce_SULLA_RIGA(betfair):
    betfair.current = current_orders(bet_id="B7", matched=2.0, residuo=3.0,
                                     prezzo=2.12, ref="safe-t7")
    db = DbSafe([riga_safe()])
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    r = db.righe[7]
    assert r["status"] == "pending", "la decisione non cambia: il residuo e' vivo"
    assert (r["size_matched"], r["size_remaining"]) == (2.0, 3.0)
    assert r["avg_price_matched"] == 2.12
    # 'quando l'ho saputo DA BETFAIR': il matchedDate dell'ordine, mai l'ora
    # di questo processo (commento della migrazione)
    assert r["betfair_updated_at"] == "2026-09-16T12:00:03.000Z"
    assert r["size_requested"] == 5.0        # priceSize.size, dichiarato da Betfair
    p = db.payload("place_parziale")
    assert p["nota"] == "parziale 2.00 su 5.00, residuo 3.00 vivo"
    assert p["size_matched"] == 2.0 and p["size_remaining"] == 3.0
    assert p["critical"] is True and p["fonte"] == "riconciliazione"


def test_safe_il_parziale_si_riscrive_SOLO_quando_cambia(betfair):
    """La riga porta i numeri VERI a ogni giro; il DB non li riceve due volte
    uguali (respiro del DB, 13/09: un UPDATE identico ogni 2 s per ogni riga
    pending e' il carico che ha messo il database in ginocchio)."""
    betfair.current = current_orders(bet_id="B7", matched=2.0, residuo=3.0,
                                     prezzo=2.12, ref="safe-t7")
    db = DbSafe([riga_safe()])
    for _ in range(3):
        S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    assert db.kinds().count("place_parziale") == 1
    # il residuo si abbina ancora un po': i numeri CAMBIANO -> si riscrive
    betfair.current = current_orders(bet_id="B7", matched=4.0, residuo=1.0,
                                     prezzo=2.13, ref="safe-t7")
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    r = db.righe[7]
    assert (r["size_matched"], r["size_remaining"]) == (4.0, 1.0)
    assert r["avg_price_matched"] == 2.13
    assert db.kinds().count("place_parziale") == 2
    ultimo = [p["nota"] for k, p in db.attivita if k == "place_parziale"][-1]
    assert ultimo == "parziale 4.00 su 5.00, residuo 1.00 vivo"


def test_safe_l_ordine_solo_appoggiato_non_si_annuncia_come_parziale(betfair):
    """Abbinato 0: i numeri vanno sulla riga (residuo vivo), ma 'parziale 0,00
    su 5,00' sarebbe una bugia."""
    betfair.current = current_orders(bet_id="B7", matched=0.0, residuo=5.0,
                                     ref="safe-t7")
    db = DbSafe([riga_safe()])
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    r = db.righe[7]
    assert (r["size_matched"], r["size_remaining"]) == (0.0, 5.0)
    assert "place_parziale" not in db.kinds()
    assert r["status"] == "pending"


def test_safe_senza_migrazione_il_parziale_si_dice_lo_stesso(betfair):
    """Le colonne nuove possono non esserci ancora: l'attivita' non dipende da
    una migrazione applicata (il bot non deve rompersi, e nemmeno tacere)."""
    betfair.current = current_orders(bet_id="B7", matched=2.0, residuo=3.0,
                                     prezzo=2.12, ref="safe-t7")
    db = DbSafe([riga_safe()], colonne_nuove=False)
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    assert db.payload("place_parziale")["size_matched"] == 2.0
    assert db.righe[7]["status"] == "pending"


# --- 8b. ANNULLAMENTO VERO PRIMA DI UN TERMINALE ----------------------------
def test_safe_prima_di_dichiarare_terminale_si_ANNULLA_davvero(betfair):
    """Nessun ordine vivo: la riga diventa terminale come sempre - ma solo
    DOPO aver chiesto l'annullamento a Betfair e averlo riletto."""
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}
    betfair.cancel = cancel_report(tagliato=5.0)
    db = DbSafe([riga_safe()])
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    assert db.kinds().count("cancel_richiesto") == 1
    assert db.payload("cancel_esito")["confermato"] is True
    r = db.righe[7]
    assert r["status"] == "error" and r["meta"]["error_final"] is True
    assert r["meta"]["reason"] == "reconcile_ordine_assente"


def test_safe_con_residuo_vivo_la_riga_NON_diventa_terminale(betfair):
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}
    betfair.cancel = cancel_report(stato="FAILURE", codice="BET_TAKEN_OR_LAPSED")
    vivo = current_orders(bet_id="B7", matched=1.0, residuo=4.0, prezzo=2.14,
                          ref="safe-t7")
    db = DbSafe([riga_safe()])
    S.reconcile_pending(market=MercatoCheRivela(betfair, vivo), db=db, now=ORA)
    r = db.righe[7]
    assert r["status"] == "pending", "ordine VIVO: mai terminale (fail-closed)"
    assert db.payload("cancel_esito")["size_remaining"] == 4.0
    assert db.payload("cancel_esito")["error_code"] == "BET_TAKEN_OR_LAPSED"
    # e la riga lo RACCONTA, invece di restare muta
    assert (r["size_matched"], r["size_remaining"]) == (1.0, 4.0)


def test_safe_cancel_a_esito_IGNOTO_resta_in_riconciliazione(betfair):
    """La rete cade durante l'annullamento: l'ordine puo' essere vivo o morto.
    Non si decide al buio - si riprova al giro dopo."""
    class MercatoCheCade(MercatoSafe):
        def cancel_order_live(self, *a, **k):
            raise RuntimeError("rete KO durante cancelOrders")

    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}
    db = DbSafe([riga_safe()])
    S.reconcile_pending(market=MercatoCheCade(), db=db, now=ORA)
    r = db.righe[7]
    assert r["status"] == "pending"
    assert db.payload("cancel_esito")["riletto"] is False
    assert db.payload("cancel_esito")["confermato"] is False


def test_safe_se_si_e_abbinato_nel_frattempo_la_parte_abbinata_e_POSIZIONE(betfair):
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}
    betfair.cancel = cancel_report(stato="FAILURE", codice="BET_TAKEN_OR_LAPSED")
    preso = current_orders(bet_id="B7", matched=5.0, residuo=0.0, prezzo=2.12,
                           ref="safe-t7")
    db = DbSafe([riga_safe()])
    S.reconcile_pending(market=MercatoCheRivela(betfair, preso), db=db, now=ORA)
    r = db.righe[7]
    assert r["status"] == "open", "abbinato: e' una posizione, non un errore"
    assert r["size"] == 5.0 and r["price"] == 2.12 and r["bet_id"] == "B7"
    assert r["meta"]["reconciled"] == "cancel"
    assert "place_parziale" not in db.kinds(), "abbinato INTERO: nessun parziale"


def test_safe_la_riserva_senza_bet_id_non_chiama_betfair(betfair):
    """Comportamento storico invariato: senza `bet_id` non c'e' niente da
    annullare, e la riserva mai piazzata si libera come sempre."""
    betfair.current = {"currentOrders": []}
    betfair.cleared = {"clearedOrders": []}
    db = DbSafe([riga_safe(bet_id=None, meta={"phase": "reserved"})])
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    assert 7 not in db.righe, "riserva liberata (nessun ordine mai partito)"
    assert "cancel_richiesto" not in db.kinds()


def test_safe_in_paper_non_si_annulla_niente(betfair):
    """In paper non esiste nessun ordine su Betfair da annullare."""
    db = DbSafe([riga_safe(mode="paper")])
    S.reconcile_pending(market=MercatoSafe(), db=db, now=ORA)
    assert "cancel_richiesto" not in db.kinds()
    assert db.righe[7]["status"] == "error"
