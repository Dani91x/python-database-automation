"""IL LOOP DEL 15/09 — trentadue green-up identici con soldi veri.

Al primo avvio in live Mike ha piazzato TRENTADUE volte la stessa lay
appoggiata (5,07 @ 1,43) su Beijing Guoan v Pohang Steelers, una ogni tre
secondi, arrivando a 61 EUR impegnati su un budget di 35. La catena:

    piazza la lay appoggiata
        -> `_segui_resting_live` la cerca su Betfair per `customerOrderRef`
           e NON la trova
        -> la marca 'reconciled_not_placed'
        -> il motore non vede piu' nessuna gamba di green-up
        -> ne crea una NUOVA, con un ref nuovo
        -> si ricomincia.

Ogni anello aveva un suo perche'. Quello che mancava era la domanda piu'
semplice: **ne ho gia' una in volo?**

Qui si difendono le due correzioni:
  1. il FRENO — non si piazza una gamba protettiva se una con lo stesso ruolo
     e ciclo e' gia' `pending`. Il confronto NON usa il ref, perche' il ref
     cambiava a ogni giro ed e' esattamente il motivo per cui il duplicato
     passava;
  2. il BET_ID si scrive SEMPRE, non solo quando l'ordine si abbina: senza,
     la riconciliazione puo' cercare l'ordine solo per `customerOrderRef`, e
     se quella ricerca fallisce la riga risulta «mai piazzata» mentre su
     Betfair l'ordine e' vivo.
"""
from __future__ import annotations

from types import SimpleNamespace

from Betfair.mike import service as S
from Betfair.mike import engine as E


class DbFinto:
    """Il minimo per far girare `_piazza_resting_live`: righe, log, update."""

    def __init__(self, righe=None):
        self.righe = list(righe or [])
        self.log_righe = []
        self.update_chiamate = []
        self._id = 1000

    # --- lettura ---
    def trades_for_event(self, event_id, **_kw):
        return list(self.righe)

    # --- scrittura ---
    def insert_trade(self, row, **_kw):
        self._id += 1
        r = {**row, "id": self._id}
        self.righe.append(r)
        return r

    def update_trade(self, trade_id, **campi):
        self.update_chiamate.append((trade_id, campi))
        for r in self.righe:
            if r.get("id") == trade_id:
                r.update(campi)
        return True

    def log(self, kind, payload=None, event_id=None):
        self.log_righe.append((kind, payload or {}))

    def kinds(self):
        return [k for k, _ in self.log_righe]


def gamba(ref="under_green-0-2", ruolo="under_green", ciclo=0):
    return E.Leg(ref=ref, role=ruolo, market=E.MARKET_OU35, selection=E.SEL_UNDER,
                 side="lay", price=1.43, size=5.07, cycle_no=ciclo)


def riga_pending(ruolo="under_green", ciclo=0, lato="lay", rid=4783):
    return {"id": rid, "role": ruolo, "cycle_no": ciclo, "side": lato,
            "status": "pending", "signal_key": f"{ruolo}-{ciclo}-99",
            "meta": {"leg_ref": f"{ruolo}-{ciclo}-99"}}


# ===========================================================================
# 1. IL FRENO
# ===========================================================================

def test_gia_appoggiata_riconosce_il_duplicato_anche_con_un_REF_DIVERSO():
    """E' il cuore del difetto: il ref cambiava a ogni giro."""
    db = DbFinto([riga_pending()])
    trovata = S._gia_appoggiata(db, "36074915", gamba(ref="under_green-0-17"))
    assert trovata is not None
    assert trovata["id"] == 4783


def test_gia_appoggiata_NON_confonde_ruoli_cicli_o_lati_diversi():
    db = DbFinto([riga_pending()])
    assert S._gia_appoggiata(db, "E1", gamba(ruolo="over_cover")) is None
    assert S._gia_appoggiata(db, "E1", gamba(ciclo=1)) is None
    g = gamba()
    g.side = "back"
    assert S._gia_appoggiata(db, "E1", g) is None


def test_gia_appoggiata_ignora_le_righe_NON_pending():
    """Una gamba abbinata o annullata non blocca la successiva: e' la
    riproposizione LEGITTIMA del ciclo dopo."""
    for stato in ("open", "cancelled", "error", "won", "lost"):
        r = riga_pending(); r["status"] = stato
        assert S._gia_appoggiata(DbFinto([r]), "E1", gamba()) is None, stato


def test_NON_SI_PIAZZA_una_seconda_gamba_protettiva(monkeypatch):
    """Il caso del 15/09, riprodotto: con una gia' in volo, NESSUN ordine parte."""
    db = DbFinto([riga_pending()])
    piazzati = []
    market = SimpleNamespace(
        place_order_live=lambda **kw: piazzati.append(kw) or SimpleNamespace(
            bet_id="999", size_matched=0.0, avg_price=None))
    info = SimpleNamespace(event_id="E1", event_name="Beijing v Pohang",
                           market_id=lambda m: "1.1", selection_id=lambda m, s: 1,
                           selection_name=lambda m, s: "Under 3.5 Goals")
    g = gamba(ref="under_green-0-17")

    S._piazza_resting_live(db=db, market=market, info=info, leg=g, mode="live",
                           params=S.C.resolve_params({}) if hasattr(S.C, "resolve_params") else {},
                           minuto=10, score="0-0", chiude=None, motivo=None,
                           ev={"event_id": "E1"})

    assert piazzati == [], "ha piazzato un ordine reale nonostante il duplicato"
    assert g.status == "cancelled"
    assert "place_saltato" in db.kinds()


def test_il_freno_DICHIARA_quale_riga_era_gia_in_volo():
    """Un blocco muto non si puo' diagnosticare: deve dire quale riga."""
    db = DbFinto([riga_pending(rid=4783)])
    market = SimpleNamespace(place_order_live=lambda **kw: None)
    info = SimpleNamespace(event_id="E1", event_name="x", market_id=lambda m: "1.1",
                           selection_id=lambda m, s: 1, selection_name=lambda m, s: "u")
    S._piazza_resting_live(db=db, market=market, info=info, leg=gamba(ref="under_green-0-9"),
                           mode="live", params={}, minuto=None, score=None,
                           chiude=None, motivo=None, ev={"event_id": "E1"})
    kind, payload = next((k, p) for k, p in db.log_righe if k == "place_saltato")
    assert payload.get("gia_in_volo") == 4783
    assert payload.get("critical") is True


# ===========================================================================
# 2. IL BET_ID
# ===========================================================================

def test_il_bet_id_si_scrive_ANCHE_se_l_ordine_non_si_abbina():
    """E' l'anello da cui e' partito il loop: un ordine appoggiato che resta
    sul book e' il caso NORMALE, e senza il suo identificativo la
    riconciliazione lo dichiara «mai piazzato»."""
    db = DbFinto()
    market = SimpleNamespace(place_order_live=lambda **kw: SimpleNamespace(
        bet_id="442889708346", size_matched=0.0, avg_price=None))
    info = SimpleNamespace(event_id="E1", event_name="x", market_id=lambda m: "1.1",
                           selection_id=lambda m, s: 1, selection_name=lambda m, s: "u")

    S._piazza_resting_live(db=db, market=market, info=info, leg=gamba(), mode="live",
                           params={}, minuto=None, score=None, chiude=None,
                           motivo=None, ev={"event_id": "E1"})

    scritti = [c for _, c in db.update_chiamate if "bet_id" in c]
    assert scritti, "il bet_id non e' stato salvato su un ordine appoggiato non abbinato"
    assert scritti[0]["bet_id"] == "442889708346"


def test_senza_bet_id_da_Betfair_lo_si_DICHIARA_invece_di_tacere():
    db = DbFinto()
    market = SimpleNamespace(place_order_live=lambda **kw: SimpleNamespace(
        bet_id=None, size_matched=0.0, avg_price=None))
    info = SimpleNamespace(event_id="E1", event_name="x", market_id=lambda m: "1.1",
                           selection_id=lambda m, s: 1, selection_name=lambda m, s: "u")

    S._piazza_resting_live(db=db, market=market, info=info, leg=gamba(), mode="live",
                           params={}, minuto=None, score=None, chiude=None,
                           motivo=None, ev={"event_id": "E1"})

    motivi = [p.get("reason") for k, p in db.log_righe if k == "error"]
    assert "resting_senza_bet_id" in motivi


def test_RIGHE_ILLEGGIBILI_NON_SI_PIAZZA(monkeypatch):
    """FAIL-CLOSED: se non si riesce a leggere le righe non sappiamo se una
    gamba e' gia' in volo — e nel dubbio non parte nessun ordine reale."""
    class DbRotto(DbFinto):
        def trades_for_event(self, event_id, **_kw):
            raise RuntimeError("503 dal database")

    db = DbRotto()
    piazzati = []
    market = SimpleNamespace(
        place_order_live=lambda **kw: piazzati.append(kw) or SimpleNamespace(
            bet_id="1", size_matched=0.0, avg_price=None))
    info = SimpleNamespace(event_id="E1", event_name="x", market_id=lambda m: "1.1",
                           selection_id=lambda m, s: 1, selection_name=lambda m, s: "u")
    g = gamba()
    S._piazza_resting_live(db=db, market=market, info=info, leg=g, mode="live",
                           params={}, minuto=None, score=None, chiude=None,
                           motivo=None, ev={"event_id": "E1"})
    assert piazzati == [], "ha piazzato un ordine reale senza poter leggere le righe"
    assert "place_saltato" in db.kinds()


# ===========================================================================
# 3. LA RADICE: la chiave con cui si ritrova l'ordine
#
# `omega_market.list_current_orders()` normalizza in snake_case e restituisce
# `customer_order_ref`; Mike cercava `customerOrderRef`, che in quel
# dizionario NON ESISTE. Il confronto falliva SEMPRE, per costruzione.
# ===========================================================================

def test_ritrova_l_ordine_con_la_chiave_VERA_di_list_current_orders():
    """E' la forma che `omega_market` produce davvero."""
    vivi = [{"bet_id": "999", "customer_order_ref": "under_green-0-2",
             "size_matched": 0.0, "size_remaining": 5.07}]
    db = DbFinto([{**riga_pending(), "signal_key": "under_green-0-2", "bet_id": None}])
    trovato = S._ordine_di(vivi, gamba(ref="under_green-0-2"), db, "E1")
    assert trovato is not None and trovato["bet_id"] == "999"


def test_la_vecchia_chiave_camelCase_continua_a_funzionare():
    """Difesa a due strade: se un giorno la normalizzazione cambia, non si
    rompe in silenzio una ricerca da cui dipendono ordini reali."""
    vivi = [{"bet_id": "1", "customerOrderRef": "under_green-0-2"}]
    db = DbFinto([{**riga_pending(), "signal_key": "under_green-0-2", "bet_id": None}])
    assert S._ordine_di(vivi, gamba(ref="under_green-0-2"), db, "E1") is not None


def test_si_ritrova_per_BET_ID_anche_se_il_riferimento_non_torna():
    """Il bet_id e' l'identificativo che Betfair stesso ci ha dato: e' la
    strada piu' solida, e dal 15/09 sta sempre sulla riga."""
    vivi = [{"bet_id": "442891672194", "customer_order_ref": "un-altro-ref"}]
    db = DbFinto([{**riga_pending(), "signal_key": "under_green-0-2",
                   "bet_id": "442891672194"}])
    trovato = S._ordine_di(vivi, gamba(ref="under_green-0-2"), db, "E1")
    assert trovato is not None, "non ritrovato nemmeno per bet_id"


def test_ordine_davvero_assente_resta_assente():
    """Il fix non deve trasformare un'assenza in una presenza: se l'ordine
    non c'e', si continua a dire che non c'e'."""
    vivi = [{"bet_id": "altro", "customer_order_ref": "over_cover-0-9"}]
    db = DbFinto([{**riga_pending(), "signal_key": "under_green-0-2", "bet_id": "mio"}])
    assert S._ordine_di(vivi, gamba(ref="under_green-0-2"), db, "E1") is None


def test_nessun_ordine_vivo_nessuna_confusione():
    db = DbFinto([{**riga_pending(), "signal_key": "under_green-0-2", "bet_id": "x"}])
    assert S._ordine_di([], gamba(ref="under_green-0-2"), db, "E1") is None
