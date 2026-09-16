"""«SE CHIUDO IO, IL BOT DEVE SAPERLO» — 16/09/2026 sera (R6, R7, R8, R9).

Ordine dell'utente, testuale:
    «se chiudo io (anche fuori dall'app, direttamente su Betfair) il bot deve
     saperlo e NON gestire posizioni che non esistono piu'; cash-out globale ->
     al controllo dopo non fa altro; il bot gestisce le SUE operazioni e ignora
     le mie manuali».

I FINTI PARLANO COME IL VERO. Le righe della posizione di conto hanno le chiavi
di ``omega_market._riga_corrente`` / ``_riga_regolata`` (snake_case), quelle di
``omega_trades`` le colonne vere. Il 15/09 un finto in camelCase ha certificato
un bug e sono usciti 32 ordini reali: qui i payload REST li costruisce
``_riga_rest``, dalla forma grezza di Betfair, e li fa normalizzare alla
FUNZIONE DI PRODUZIONE.

Ogni test porta la sua FALSIFICAZIONE: si rimette il difetto e il test deve
diventare rosso (le falsificazioni sono i test che finiscono con
``_falsificazione``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.omega import omega_config as C
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as OM
from Betfair.omega import omega_service as S

ADESSO = datetime(2026, 9, 16, 20, 30, tzinfo=timezone.utc)
MKT = "1.259475532"
SEL = 13


def _params(**kw: Any) -> Dict[str, Any]:
    p = dict(C.DEFAULTS)
    p["conto_every_s"] = 0.0          # nei test la lettura e' a ogni giro
    p.update(kw)
    return p


# ---------------------------------------------------------------------------
# I FINTI: payload REST grezzi -> funzioni di normalizzazione VERE
# ---------------------------------------------------------------------------
def _riga_rest(*, bet_id: str, side: str, size: float, ref: str,
               price: float = 300.0, status: str = "EXECUTION_COMPLETE") -> dict:
    """UN ordine come lo manda Betfair (``listCurrentOrders``), grezzo e
    camelCase, passato dalla normalizzazione VERA di produzione."""
    return OM._riga_corrente({
        "betId": bet_id,
        "marketId": MKT,
        "selectionId": SEL,
        "side": side.upper(),
        "status": status,
        "sizeMatched": float(size),
        "averagePriceMatched": float(price),
        "sizeRemaining": 0.0,
        "customerOrderRef": ref,
        "priceSize": {"price": float(price), "size": float(size)},
    })


def _riga_regolata_rest(*, bet_id: str, side: str, size: float, ref: str,
                        price: float = 300.0) -> dict:
    return OM._riga_regolata({
        "betId": bet_id, "marketId": MKT, "selectionId": SEL,
        "side": side.upper(), "sizeSettled": float(size),
        "priceMatched": float(price), "profit": 0.0,
        "betOutcome": "WON", "customerOrderRef": ref,
    })


class DbFinto:
    """Le chiavi sono quelle vere di ``omega_trades`` e le firme quelle di
    ``omega_db``: un finto che sa fare meno del vero certifica un'altra cosa."""

    def __init__(self, trades: List[dict]) -> None:
        self.trades = [dict(t) for t in trades]
        self.attivita: List[tuple] = []
        self.eventi: Dict[str, dict] = {}

    # --- lettura
    def open_trades(self) -> List[dict]:
        return [t for t in self.trades if str(t.get("status")) == "open"]

    def list_trades(self, status: Optional[str] = None) -> List[dict]:
        return [t for t in self.trades
                if status is None or str(t.get("status")) == status]

    def trades_for_event(self, event_id: str, **_kw: Any) -> List[dict]:
        return [t for t in self.trades if str(t.get("event_id")) == str(event_id)]

    def get_trade(self, trade_id: int) -> Optional[dict]:
        return next((t for t in self.trades if int(t.get("id") or 0) == int(trade_id)), None)

    # --- scrittura
    def update_trade(self, trade_id: int, **campi: Any) -> None:
        riga = self.get_trade(trade_id)
        if riga is not None:
            riga.update(campi)

    def log(self, kind: str, payload: Optional[dict] = None, **_kw: Any) -> None:
        self.attivita.append((kind, dict(payload or {})))

    def kinds(self) -> List[str]:
        return [k for k, _p in self.attivita]

    def payload(self, kind: str) -> Optional[dict]:
        return next((p for k, p in self.attivita if k == kind), None)

    # --- stato dell'evento (colonna omega_events.stato_utente)
    def event_user_state(self, event_id: str) -> Optional[dict]:
        st = (self.eventi.get(str(event_id)) or {}).get("stato_utente")
        return dict(st) if isinstance(st, dict) else None

    def set_event_user_state(self, event_id: str, stato: Optional[dict]) -> bool:
        self.eventi.setdefault(str(event_id), {})["stato_utente"] = stato
        return True

    def user_closed_event_ids(self, since_iso: Optional[str] = None) -> set:
        return {e for e, r in self.eventi.items()
                if isinstance(r.get("stato_utente"), dict)
                and r["stato_utente"].get("chiuso_dall_utente")}

    def resume_event(self, event_id: str) -> bool:
        return self.set_event_user_state(event_id, None)


class MercatoFinto:
    """Espone ``posizione_di_conto`` con LA STESSA FIRMA della produzione
    (``omega_market.posizione_di_conto(market_id, selection_id=None)``) e le
    stesse chiavi."""

    def __init__(self, righe: List[dict], *, solleva: bool = False) -> None:
        self.righe = list(righe)
        self.solleva = bool(solleva)
        self.letture = 0

    def posizione_di_conto(self, market_id: str,
                           selection_id: Optional[int] = None) -> List[dict]:
        self.letture += 1
        if self.solleva:
            raise RuntimeError("rete caduta")
        if selection_id is None:
            return list(self.righe)
        return [r for r in self.righe
                if int(r.get("selection_id") or -1) == int(selection_id)]


def _lay_del_bot(**kw: Any) -> dict:
    riga = {"id": 1, "event_id": "35760084", "market_id": MKT, "selection_id": SEL,
            "side": "lay", "size": 5.26, "price": 300.0, "status": "open",
            "mode": "live", "origin": "auto", "bet_id": "100000000001",
            "liability": 1572.74, "closes_trade_id": None, "meta": {}}
    riga.update(kw)
    return riga


REF_BOT = E.customer_ref_for(1)


@pytest.fixture(autouse=True)
def _pulisci_lo_stato_di_processo():
    S.svuota_le_cache()
    yield
    S.svuota_le_cache()


# ===========================================================================
# R9 — la posizione di conto: «se chiudo io su Betfair, il bot deve saperlo»
# ===========================================================================
def test_la_posizione_chiusa_dall_utente_su_betfair_viene_vista():
    db = DbFinto([_lay_del_bot()])
    # sul conto: la lay del BOT (5,26) e la back dell'UTENTE (5,26, ref suo).
    # Netto = 0: la posizione non esiste piu'.
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref="utente-1"),
    ])
    n = S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db, now=ADESSO)
    assert n == 1
    assert "chiuso_dall_utente" in db.kinds()
    assert db.trades[0]["meta"].get("chiuso_dall_utente"), "la riga non e' marcata"
    assert db.user_closed_event_ids() == {"35760084"}


def test_una_posizione_ancora_viva_non_viene_toccata():
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()
    assert not db.trades[0]["meta"].get("chiuso_dall_utente")


def test_una_chiusura_PARZIALE_dell_utente_non_spegne_la_protezione():
    """R10: sul book sottile la chiusura si abbina a meta'. La posizione e'
    ancora aperta, e il bot deve continuare a proteggere quel che resta."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000002", side="BACK", size=2.00, ref="utente-1"),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()
    d = db.payload("diagnosi")
    assert d and d["verdetto"] == "ridotta_dall_utente"
    assert d["ancora_viva"] == pytest.approx(-3.26, abs=0.01)


def test_operazioni_SUE_sulla_stessa_selezione_non_sono_una_chiusura():
    """L'utente ha una posizione tutta sua sulla stessa selezione: il netto di
    conto e' diverso, ma la posizione del BOT c'e' ancora."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000003", side="LAY", size=20.0, ref="utente-2"),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()


def test_se_le_gambe_del_bot_non_si_ritrovano_NON_si_conclude_niente():
    """Conservativo: se sul conto non ci sono gli ordini del bot il problema e'
    la riconciliazione, non una chiusura dell'utente. Si dichiara e basta."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="900000000009", side="BACK", size=5.26, ref="utente-1"),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    d = db.payload("diagnosi")
    assert d and d["verdetto"] == "gambe_non_ritrovate"
    assert not db.trades[0]["meta"].get("chiuso_dall_utente")


def test_in_paper_non_si_legge_nessun_conto():
    db = DbFinto([_lay_del_bot(mode="paper")])
    market = MercatoFinto([])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert market.letture == 0


def test_una_posizione_gia_coperta_dal_bot_non_e_una_chiusura_dell_utente():
    """Lay 5,26 del bot + back 5,26 DEL BOT (green-up): il netto e' zero perche'
    l'ha fatto lui. Non si deve dichiarare niente."""
    chiusura = _lay_del_bot(id=2, side="back", closes_trade_id=1,
                            bet_id="100000000002")
    db = DbFinto([_lay_del_bot(), chiusura])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="100000000002", side="BACK", size=5.26,
                   ref=E.customer_ref_for(2)),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()


def test_la_rete_caduta_non_decide_al_buio():
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([], solleva=True)
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()
    err = db.payload("error")
    assert err and err["reason"] == "posizione_di_conto_non_letta"


def test_la_cadenza_dichiarata_vale_davvero():
    """`conto_every_s` e' un respiro, non un modo di dire: a 120 s la seconda
    lettura nello stesso minuto non parte."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
    ])
    p = _params(conto_every_s=120.0)
    S.sorveglia_posizione_di_conto(params=p, market=market, db=db, now=ADESSO)
    S.sorveglia_posizione_di_conto(params=p, market=market, db=db, now=ADESSO)
    assert market.letture == 1


def test_non_si_ripete_una_volta_saputo():
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref="utente-1"),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 1
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert db.kinds().count("chiuso_dall_utente") == 2   # scoperta + stato evento


def test_i_regolati_contano_come_i_correnti():
    """La back dell'utente puo' essere gia' REGOLATA: la posizione e' chiusa
    lo stesso. Le due liste hanno nomi diversi per la stessa cosa e il codice
    non deve conoscerne due (difetto 1 del catalogo)."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_regolata_rest(bet_id="900000000002", side="BACK", size=5.26,
                            ref="utente-1"),
    ])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 1


def test_lo_stesso_ordine_in_due_liste_non_conta_due_volte():
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_regolata_rest(bet_id="100000000001", side="LAY", size=5.26,
                            ref=REF_BOT),
        _riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref="utente-1"),
    ])
    # la lay del bot conta UNA volta: netto 0 -> chiusa
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 1


def test_un_mercato_senza_posizione_di_conto_non_fa_cadere_il_giro():
    class SenzaConto:
        pass

    db = DbFinto([_lay_del_bot()])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=SenzaConto(),
                                          db=db, now=ADESSO) == 0


def test_r9_falsificazione_senza_la_lettura_del_conto_il_bot_non_vede_niente():
    """IL DIFETTO RIMESSO: il bot legge SOLO i propri ordini
    (``list_current_orders``, filtrato per strategia) invece della posizione di
    CONTO. La back dell'utente non compare, e la chiusura resta invisibile."""
    db = DbFinto([_lay_del_bot()])
    conto = [
        _riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref="utente-1"),
    ]

    class SoloIMieiOrdini(MercatoFinto):
        def posizione_di_conto(self, market_id, selection_id=None):
            return [r for r in conto
                    if str(r.get("customer_order_ref") or "").startswith("omega-")]

    assert S.sorveglia_posizione_di_conto(params=_params(),
                                          market=SoloIMieiOrdini([]), db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()


# ===========================================================================
# R7/R8 — il green-up non decide sulle righe che non sono sue
# ===========================================================================
def test_il_greenup_ignora_le_righe_manuali():
    db = DbFinto([_lay_del_bot(id=7, origin="manual", meta={"manual": True})])
    assert S._greenup_candidates(db) == []
    p = db.payload("skip")
    assert p and p["reason"] == "riga_manuale"


def test_il_greenup_ignora_una_posizione_chiusa_fuori_dall_app():
    db = DbFinto([_lay_del_bot(meta={"chiuso_dall_utente": {"dove": "fuori dall'app"}})])
    assert S._greenup_candidates(db) == []
    p = db.payload("skip")
    assert p and p["reason"] == "chiuso_dall_utente_fuori_app"


def test_il_greenup_ignora_una_partita_chiusa_dall_utente():
    db = DbFinto([_lay_del_bot()])
    assert S._greenup_candidates(db, {"35760084"}) == []
    p = db.payload("skip")
    assert p and p["reason"] == "evento_chiuso_dall_utente"


def test_il_greenup_resta_acceso_su_una_gamba_normale_del_bot():
    db = DbFinto([_lay_del_bot()])
    assert [t["id"] for t in S._greenup_candidates(db)] == [1]


def test_r7_falsificazione_il_greenup_che_decide_sulle_manuali():
    """IL DIFETTO RIMESSO (§12 prima del 16/09): «ogni gamba lay aperta,
    automatica o manuale». Con il filtro tolto la riga dell'utente torna
    candidata."""
    db = DbFinto([_lay_del_bot(id=7, origin="manual", meta={"manual": True})])
    righe = [t for t in db.open_trades()
             if str(t.get("side")) == "lay" and not t.get("closes_trade_id")]
    assert righe, "senza filtro la riga manuale e' candidata: e' il difetto"
    assert S._greenup_candidates(db) == [], "col filtro NON deve esserlo"


# ===========================================================================
# R8 — lo stato dell'evento: scritto, letto, tolto solo a mano
# ===========================================================================
def test_lo_stato_si_scrive_e_si_legge():
    db = DbFinto([])
    assert S._chiudi_evento(db=db, event_id="35760084", now=ADESSO,
                            dove="cash-out nell'app") is True
    st = db.event_user_state("35760084")
    assert st and st["chiuso_dall_utente"] is True and st["dove"] == "cash-out nell'app"
    assert db.user_closed_event_ids() == {"35760084"}


def test_lo_stato_si_toglie_SOLO_con_il_gesto_esplicito():
    db = DbFinto([])
    S._chiudi_evento(db=db, event_id="35760084", now=ADESSO, dove="fuori dall'app")
    assert db.user_closed_event_ids() == {"35760084"}
    assert db.resume_event("35760084") is True
    assert db.user_closed_event_ids() == set()


def test_se_la_colonna_manca_lo_dice_forte():
    """Migrazione non applicata: il marker non si scrive. Non si tace: si scrive
    `schema_warn`, che nella UI e' «MIGRAZIONE MANCANTE»."""
    class SenzaColonna(DbFinto):
        def set_event_user_state(self, event_id, stato):
            return False

    db = SenzaColonna([])
    assert S._chiudi_evento(db=db, event_id="35760084", now=ADESSO,
                            dove="fuori dall'app") is False
    p = db.payload("schema_warn")
    assert p and p["scritto"] is False and "NON SCRITTO" in p["nota"]


def test_chiudere_UNA_gamba_di_due_non_spegne_l_altra_in_silenzio():
    """Il reperto R8: prima succedeva, e non lo diceva nessuno. Adesso: l'altra
    gamba resta gestita, e lo si DICHIARA."""
    db = DbFinto([_lay_del_bot(id=1, phase="ht_cs", status="hedged"),
                  _lay_del_bot(id=2, phase="ft_cs", status="open")])
    S._dopo_il_cashout(db=db, tr=db.get_trade(1), now=ADESSO, partial=False)
    assert db.user_closed_event_ids() == set(), "l'evento NON deve essere chiuso"
    d = db.payload("diagnosi")
    assert d and d["verdetto"] == "resta_aperto_del_bot" and d["restano"] == [2]


def test_chiuse_tutte_le_gambe_l_evento_e_chiuso():
    db = DbFinto([_lay_del_bot(id=1, status="hedged")])
    S._dopo_il_cashout(db=db, tr=db.get_trade(1), now=ADESSO, partial=False)
    assert db.user_closed_event_ids() == {"35760084"}


def test_una_chiusura_ancora_in_volo_si_riguarda_al_giro_dopo():
    """Al momento del clic la gamba e' ancora 'open' (bet delay): lo stato non
    si scrive. Quando la chiusura si abbina, il giro dopo lo scrive."""
    db = DbFinto([_lay_del_bot(id=1, status="open")])
    S._dopo_il_cashout(db=db, tr=db.get_trade(1), now=ADESSO, partial=False)
    assert db.user_closed_event_ids() == set()
    db.trades[0]["status"] = "hedged"
    assert S.chiudi_eventi_in_attesa(db=db, now=ADESSO) == 1
    assert db.user_closed_event_ids() == {"35760084"}


def test_una_chiusura_su_una_riga_SUA_non_prende_lo_stato():
    db = DbFinto([_lay_del_bot(id=1, origin="manual", status="hedged")])
    S._dopo_il_cashout(db=db, tr=db.get_trade(1), now=ADESSO, partial=False)
    assert db.user_closed_event_ids() == set()
    d = db.payload("diagnosi")
    assert d and d["verdetto"] == "riga_sua"


def test_l_apertura_salta_le_partite_chiuse_dall_utente():
    db = DbFinto([])
    ev = type("Ev", (), {"event_id": "35760084", "open_date": None})()
    n = S.scan_and_place_legs(
        control={"daily_goal": 250.0, "mode": "live"}, params=_params(),
        events=[ev], traded_ids=set(), traded_legs=set(),
        aggregates={"realized_profit": 0.0}, market=object(), db=db, now=ADESSO,
        chiusi_dall_utente={"35760084"})
    assert n == 0
    p = db.payload("skip")
    assert p and p["reason"] == "evento_chiuso_dall_utente"


def test_r8_falsificazione_senza_lo_stato_la_partita_torna_aperta():
    """IL DIFETTO RIMESSO: nessuno stato sull'evento. L'apertura non ha niente
    da guardare e la partita che l'utente ha chiuso torna disponibile."""
    db = DbFinto([])
    ev = type("Ev", (), {"event_id": "35760084", "open_date": None})()
    chiamato: List[str] = []

    def _finto_scan(**kw):
        chiamato.append(str(kw["ev"].event_id))
        return 0, 0

    import Betfair.omega.omega_service as mod
    vero = mod._scan_event_legs
    mod._scan_event_legs = _finto_scan
    try:
        mod.scan_and_place_legs(
            control={"daily_goal": 250.0, "mode": "live"}, params=_params(),
            events=[ev], traded_ids=set(), traded_legs=set(),
            aggregates={"realized_profit": 0.0}, market=object(), db=db,
            now=ADESSO, chiusi_dall_utente=set())
        assert chiamato == ["35760084"], "senza stato la partita e' operabile"
        chiamato.clear()
        mod.scan_and_place_legs(
            control={"daily_goal": 250.0, "mode": "live"}, params=_params(),
            events=[ev], traded_ids=set(), traded_legs=set(),
            aggregates={"realized_profit": 0.0}, market=object(), db=db,
            now=ADESSO, chiusi_dall_utente={"35760084"})
        assert chiamato == [], "con lo stato NON deve esserlo"
    finally:
        mod._scan_event_legs = vero


# ===========================================================================
# ORDINE DEL COORDINATORE (16/09 sera): su una partita chiusa dall'utente gli
# ordini del BOT ancora VIVI e NON ABBINATI si ANNULLANO. La parte abbinata no:
# quella e' posizione, e la regola il settlement.
# ===========================================================================
class MercatoConAnnullo(MercatoFinto):
    """Espone ``cancel_order_live`` con la firma e il RISULTATO veri
    (``omega_market.CancelResult``): un finto che torna un dizionario, o un
    booleano, certificherebbe un'altra cosa."""

    def __init__(self, righe: List[dict], *, residuo_dopo: float = 0.0,
                 solleva_cancel: bool = False) -> None:
        super().__init__(righe)
        self.residuo_dopo = float(residuo_dopo)
        self.solleva_cancel = bool(solleva_cancel)
        self.annullati: List[tuple] = []

    def cancel_order_live(self, bet_id: str, market_id: str,
                          size_reduction: Optional[float] = None) -> Any:
        self.annullati.append((str(bet_id), str(market_id), size_reduction))
        if self.solleva_cancel:
            raise RuntimeError("rete caduta durante l'annullo")
        return OM.CancelResult(ok=True, status="SUCCESS", bet_id=str(bet_id),
                               size_cancelled=1.0, size_matched=0.0,
                               size_remaining=self.residuo_dopo, riletto=True)


def _conto_chiuso() -> List[dict]:
    return [_riga_rest(bet_id="100000000001", side="LAY", size=5.26, ref=REF_BOT),
            _riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref="utente-1")]


def test_un_ordine_appoggiato_del_bot_viene_annullato():
    """La riga abbinata (id 1) chiude la partita; la riga 2 ha un ordine ancora
    VIVO e non abbinato: quello si annulla."""
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={"size_remaining": 3.0})
    db = DbFinto([_lay_del_bot(), appoggiato])
    market = MercatoConAnnullo(_conto_chiuso())
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 1
    assert [b for b, _m, _r in market.annullati] == ["100000000002"]
    assert market.annullati[0][1] == MKT, "il mercato dell'annullo non e' quello vero"
    assert "cancel_richiesto" in db.kinds() and "cancel_esito" in db.kinds()
    assert db.get_trade(2)["meta"].get("annullato_per_chiusura_utente")


def test_un_pending_senza_residuo_dichiarato_si_annulla_lo_stesso():
    """Un ordine reale a esito ancora aperto ('pending' con `bet_id`) puo'
    essere vivo anche senza che nessuno abbia scritto un `size_remaining`:
    e' il caso dell'esito IGNOTO, ed e' il piu' pericoloso di tutti."""
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={})
    db = DbFinto([_lay_del_bot(), appoggiato])
    market = MercatoConAnnullo(_conto_chiuso())
    S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db, now=ADESSO)
    assert [b for b, _m, _r in market.annullati] == ["100000000002"]


def test_il_RESIDUO_di_un_parziale_si_annulla():
    """La gamba e' abbinata in parte e il resto e' ancora appoggiato
    (`meta.size_remaining` > 0, scritto da Betfair al piazzamento): la parte
    abbinata resta (e' posizione), il residuo si toglie dal mercato."""
    db = DbFinto([_lay_del_bot(meta={"size_remaining": 2.0})])
    market = MercatoConAnnullo(_conto_chiuso())
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 1
    assert [b for b, _m, _r in market.annullati] == ["100000000001"]


def test_la_parte_ABBINATA_non_si_annulla_mai():
    """La lay del bot e' abbinata al 100%: e' una POSIZIONE. Annullarla non
    vuol dire niente, e chiederlo a Betfair sarebbe un ordine sbagliato."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoConAnnullo(_conto_chiuso())
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 1
    assert market.annullati == []


def test_un_ordine_dell_utente_non_lo_annulla_il_bot():
    manuale = _lay_del_bot(id=3, status="pending", origin="manual",
                           bet_id="900000000777", meta={"size_remaining": 4.0})
    db = DbFinto([_lay_del_bot(), manuale])
    market = MercatoConAnnullo(_conto_chiuso())
    S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db, now=ADESSO)
    assert market.annullati == [], "il bot ha annullato un ordine dell'utente"


def test_un_annullo_a_esito_IGNOTO_non_diventa_mai_annullato():
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={"size_remaining": 3.0})
    db = DbFinto([_lay_del_bot(), appoggiato])
    market = MercatoConAnnullo(_conto_chiuso(), solleva_cancel=True)
    S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db, now=ADESSO)
    assert not db.get_trade(2)["meta"].get("annullato_per_chiusura_utente")
    assert "35760084" in S._DA_ANNULLARE, "l'evento non e' in coda per il ritento"
    p = [pp for k, pp in db.attivita
         if k == "chiuso_dall_utente" and pp.get("verdetto") == "ordini_ancora_vivi"]
    assert p and p[0]["quanti"] == 1


def test_l_annullo_non_confermato_si_ritenta_al_giro_dopo():
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={"size_remaining": 3.0})
    db = DbFinto([_lay_del_bot(), appoggiato])
    rotto = MercatoConAnnullo(_conto_chiuso(), solleva_cancel=True)
    S.sorveglia_posizione_di_conto(params=_params(), market=rotto, db=db, now=ADESSO)
    assert S._DA_ANNULLARE == {"35760084"}
    buono = MercatoConAnnullo(_conto_chiuso())
    assert S.ritenta_annulli(market=buono, db=db, now=ADESSO) == 1
    assert S._DA_ANNULLARE == set()
    assert db.get_trade(2)["meta"].get("annullato_per_chiusura_utente")


def test_un_residuo_ancora_vivo_dopo_l_annullo_resta_in_coda():
    """Betfair dice che il residuo e' ancora li': la riga NON si dichiara
    annullata e l'evento resta in coda (fail-closed)."""
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={"size_remaining": 3.0})
    db = DbFinto([_lay_del_bot(), appoggiato])
    market = MercatoConAnnullo(_conto_chiuso(), residuo_dopo=3.0)
    S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db, now=ADESSO)
    assert S._DA_ANNULLARE == {"35760084"}
    assert not db.get_trade(2)["meta"].get("annullato_per_chiusura_utente")


def test_anche_il_cashout_nell_app_annulla_cio_che_resta_vivo():
    """Con una gamba ancora IN VOLO l'evento non prende subito lo stato (una
    riga 'pending' potrebbe diventare una posizione), ma l'ordine vivo e non
    abbinato si annulla SUBITO. Quando la riga si chiude davvero, il giro dopo
    scrive lo stato."""
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={"size_remaining": 3.0})
    db = DbFinto([_lay_del_bot(id=1, status="hedged"), appoggiato])
    market = MercatoConAnnullo([])
    S._dopo_il_cashout(db=db, tr=db.get_trade(1), now=ADESSO, partial=False,
                       market=market)
    assert [b for b, _m, _r in market.annullati] == ["100000000002"]
    assert db.user_closed_event_ids() == set()
    db.trades[1]["status"] = "error"          # la riconciliazione l'ha chiusa
    assert S.chiudi_eventi_in_attesa(db=db, now=ADESSO, market=market) == 1
    assert db.user_closed_event_ids() == {"35760084"}


def test_annullo_falsificazione_senza_di_esso_l_ordine_resta_a_mercato():
    """IL DIFETTO RIMESSO: si scrive lo stato e basta. L'ordine appoggiato del
    bot resta vivo su una partita che non e' piu' sua: se si abbina, il bot
    riapre una posizione da solo."""
    appoggiato = _lay_del_bot(id=2, status="pending", bet_id="100000000002",
                              meta={"size_remaining": 3.0})
    db = DbFinto([_lay_del_bot(), appoggiato])
    market = MercatoConAnnullo(_conto_chiuso())
    # senza il mercato, `_chiudi_evento` non puo' annullare niente
    S._chiudi_evento(db=db, event_id="35760084", now=ADESSO, dove="fuori dall'app")
    assert market.annullati == [], "il difetto: nessun annullo"
    S._chiudi_evento(db=db, event_id="35760084", now=ADESSO, dove="fuori dall'app",
                     market=market)
    assert [b for b, _m, _r in market.annullati] == ["100000000002"]


# ===========================================================================
# R6 — i numeri con cui il bot decide
# ===========================================================================
def _righe_miste() -> List[dict]:
    return [
        # posizione DEL BOT: lay aperta, 50 EUR di liability
        {"id": 1, "event_id": "A", "status": "open", "liability": 50.0,
         "pnl": 0.0, "origin": "auto", "closes_trade_id": None,
         "placed_at": ADESSO.isoformat(), "bet_id": "b1", "meta": {}},
        # posizione DELL'UTENTE: lay aperta, 100 EUR
        {"id": 2, "event_id": "B", "status": "open", "liability": 100.0,
         "pnl": 0.0, "origin": "manual", "closes_trade_id": None,
         "placed_at": ADESSO.isoformat(), "bet_id": "b2", "meta": {}},
    ]


def test_gli_aggregati_del_bot_non_contengono_le_manuali():
    giorno = E.day_start_utc(ADESSO)
    tutto = E.aggregate_trades(_righe_miste(), giorno)
    solo_bot = E.aggregate_trades(_righe_miste(), giorno, solo_auto=True)
    assert tutto["open_liability"] == pytest.approx(150.0)
    assert solo_bot["open_liability"] == pytest.approx(50.0)
    assert tutto["events_today"] == 2 and solo_bot["events_today"] == 1


def test_il_default_di_aggregate_trades_e_invariato():
    giorno = E.day_start_utc(ADESSO)
    assert (E.aggregate_trades(_righe_miste(), giorno)
            == E.aggregate_trades(_righe_miste(), giorno, solo_auto=False))


def test_un_cashout_MANUALE_su_una_gamba_del_BOT_resta_nei_numeri_del_bot():
    """Il caso che rende cieco il cap di perdita se si sbaglia: l'utente chiude
    a mano una gamba DEL BOT. La riga di chiusura porta `origin='manual'` ma il
    suo P&L e' il risultato di una posizione del bot."""
    righe = [
        {"id": 1, "event_id": "A", "status": "lost", "liability": 50.0,
         "pnl": -20.0, "origin": "auto", "closes_trade_id": None,
         "placed_at": ADESSO.isoformat(), "bet_id": "b1", "meta": {}},
        {"id": 2, "event_id": "A", "status": "won", "liability": 0.0,
         "pnl": 8.0, "origin": "manual", "closes_trade_id": 1,
         "placed_at": ADESSO.isoformat(), "bet_id": "b2", "meta": {}},
    ]
    giorno = E.day_start_utc(ADESSO)
    solo_bot = E.aggregate_trades(righe, giorno, solo_auto=True)
    assert solo_bot["realized_today"] == pytest.approx(-12.0)


def test_una_chiusura_di_una_posizione_DELL_UTENTE_resta_fuori():
    righe = [
        {"id": 1, "event_id": "B", "status": "lost", "liability": 100.0,
         "pnl": -40.0, "origin": "manual", "closes_trade_id": None,
         "placed_at": ADESSO.isoformat(), "bet_id": "b1", "meta": {}},
        {"id": 2, "event_id": "B", "status": "won", "liability": 0.0,
         "pnl": 15.0, "origin": "auto", "closes_trade_id": 1,
         "placed_at": ADESSO.isoformat(), "bet_id": "b2", "meta": {}},
    ]
    giorno = E.day_start_utc(ADESSO)
    assert E.aggregate_trades(righe, giorno, solo_auto=True)["realized_today"] == 0.0
    assert E.aggregate_trades(righe, giorno)["realized_today"] == pytest.approx(-25.0)


def test_r6_falsificazione_senza_il_filtro_il_bot_decide_sui_soldi_dell_utente():
    """IL DIFETTO RIMESSO: `aggregate_trades` senza `solo_auto`. La liability
    con cui il bot decide diventa 150 invece di 50 — misurato il 16/09 sul
    banco: 70 EUR «del bot» contro 0 delle sue gambe."""
    giorno = E.day_start_utc(ADESSO)
    rotto = E.aggregate_trades(_righe_miste(), giorno)          # il difetto
    sano = E.aggregate_trades(_righe_miste(), giorno, solo_auto=True)
    assert rotto["open_liability"] == pytest.approx(150.0)
    assert sano["open_liability"] == pytest.approx(50.0)


def test_la_coppia_di_aggregati_arriva_al_servizio_senza_letture_in_piu():
    """`_aggregati_cached` torna (pagina, bot) e la cache serve entrambe con UNA
    lettura sola (§18: il database respira)."""
    letture: List[int] = []

    class DbCoppia(DbFinto):
        def aggregates_coppia(self, day_start=None):
            letture.append(1)
            righe = _righe_miste()
            return (E.aggregate_trades(righe, day_start),
                    E.aggregate_trades(righe, day_start, solo_auto=True))

    db = DbCoppia([])
    # il conftest spegne le cadenze: qui la cache va ACCESA apposta, perche' e'
    # proprio lei l'oggetto della misura
    C.DEFAULTS["aggregates_cache_s"] = 20.0
    pagina, bot = S._aggregati_cached(db, E.day_start_utc(ADESSO), 1000.0)
    assert pagina["open_liability"] == pytest.approx(150.0)
    assert bot["open_liability"] == pytest.approx(50.0)
    S._aggregati_cached(db, E.day_start_utc(ADESSO), 1001.0)
    assert len(letture) == 1, "la cache non ha retto: due letture per un giro"


def test_un_db_che_non_sa_fare_la_coppia_degrada_in_modo_dichiarato():
    class DbVecchio(DbFinto):
        def aggregates(self, day_start=None):
            return E.aggregate_trades(_righe_miste(), day_start)

    pagina, bot = S._aggregati_cached(DbVecchio([]), E.day_start_utc(ADESSO), 5.0)
    assert pagina == bot, "senza la coppia il comportamento e' quello di prima"


# ===========================================================================
# LA FUNZIONE CONDIVISA — nome e firma concordati fra i delegati (16/09)
# ===========================================================================
def test_posizione_di_conto_ha_la_firma_concordata():
    import inspect

    firma = inspect.signature(OM.posizione_di_conto)
    assert list(firma.parameters) == ["market_id", "selection_id"]
    assert firma.parameters["selection_id"].default is None


def test_il_banco_espone_la_stessa_funzione_con_la_stessa_firma():
    import inspect

    from Betfair.stream.backtest import banco_comune as B

    firma = inspect.signature(B.MercatoFlumine.posizione_di_conto)
    assert list(firma.parameters) == ["self", "market_id", "selection_id"]
    assert firma.parameters["selection_id"].default is None


def test_posizione_di_conto_unisce_vivi_e_regolati_e_filtra_la_selezione(monkeypatch):
    vivi = [_riga_rest(bet_id="1", side="LAY", size=1.0, ref="a")]
    morti = [_riga_regolata_rest(bet_id="2", side="BACK", size=1.0, ref="b")]
    altra = dict(vivi[0]); altra["selection_id"] = 999
    monkeypatch.setattr(OM, "list_current_orders_account",
                        lambda ids, sel=None: list(vivi) + [altra])
    monkeypatch.setattr(OM, "list_cleared_orders_account",
                        lambda ids, lookback_hours=72: list(morti))
    righe = OM.posizione_di_conto(MKT, SEL)
    assert {r["bet_id"] for r in righe} == {"1", "2"}
