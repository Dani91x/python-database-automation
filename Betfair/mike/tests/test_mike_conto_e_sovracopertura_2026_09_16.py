"""GLI ORDINI DELL'UTENTE DEL 16/09/2026 SERA, difesi uno per uno.

1. **MAI SOVRACOPERTURA** — `over_cover` si riprezzava con `cancel` + `place`
   nello STESSO giro: due back di copertura potevano stare a mercato insieme e
   comprare Over gia' comprato. Stessa regola delle lay (§15.7), applicata al
   back di copertura: `engine._mai_sovracopertura`, controllo **J6**.

2. **SE CHIUDO IO, IL BOT DEVE SAPERLO, ANCHE FUORI DALL'APP** — Mike leggeva
   solo gli ordini col SUO `customerStrategyRef`: una lay che l'utente piazza
   dal sito Betfair per chiudere la posizione non la vedeva. Adesso legge la
   POSIZIONE DI CONTO sul mercato (`service._sorveglia_posizione_di_conto`,
   cadenza `reconcile_every_s`) e, se quella non contiene piu' la sua posizione,
   accende `ctx.chiuso_dall_utente` e non gestisce piu' la partita. Controllo
   **R3**.

3. **DA UNO STATO TERMINALE NON ESCE NESSUNA AZIONE** (A2) — il controllo non
   ha un caso nel replay perche' `service._run_event` esce PRIMA di chiamare
   `decide`; la seconda linea di difesa e' la guardia dentro `decide`, e qui la
   si mette alla prova direttamente (togliendo quella guardia questi test sono
   rossi).

4. **LA FAMIGLIA K** — i controlli che guardano il rapporto fra cio' che il bot
   CREDE delle sue gambe e cio' che il MERCATO dice dei suoi ordini. Esistono
   perche' la falsificazione indipendente dei cinque difetti del 15/09 ha
   dimostrato che i controlli A-J non li vedono: il referto del replay restava
   identico cifra per cifra. Vedi la sezione 8.

I finti parlano con le chiavi del vero: gli ordini hanno la forma che
`omega_market.list_current_orders`/`list_cleared_orders` producono (snake_case,
`size_matched`, `size_remaining`, `customer_order_ref`), `Book`/`Snapshot`/`Leg`
sono quelli dell'engine.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S

KO = 1_700_000_000.0
MERCATO_35 = "1.35"
SEL_UNDER_35 = 47999
PAR = C.merge_params(None)


# ---------------------------------------------------------------------------
# i finti, con le chiavi del vero
# ---------------------------------------------------------------------------
def ordine_conto(*, ref: str, side: str, abbinato: float, bet_id: str = "B",
                 market_id: str = MERCATO_35, selection_id: int = SEL_UNDER_35,
                 stato: str = "EXECUTION_COMPLETE", residuo: float = 0.0,
                 prezzo: float = 1.50) -> Dict[str, Any]:
    """UN ordine come lo restituisce `omega_market` (snake_case, mai camelCase)."""
    return {
        "bet_id": bet_id, "market_id": market_id, "selection_id": selection_id,
        "side": side, "status": stato, "size_matched": abbinato,
        "avg_price_matched": prezzo, "size_remaining": residuo,
        "customer_order_ref": ref, "size_cancelled": 0.0, "size_lapsed": 0.0,
        "size_voided": 0.0, "matched_date": "2026-09-16T19:00:00Z",
        "placed_date": "2026-09-16T18:59:00Z", "price_requested": prezzo,
        "size_requested": abbinato, "average_price_matched": prezzo,
    }


class DbFinto:
    def __init__(self) -> None:
        self.righe: List[dict] = []
        self.log_scritti: List[tuple] = []
        self.aggiornate: List[dict] = []

    def trades_for_event(self, event_id: str, **_kw) -> List[dict]:
        return list(self.righe)

    def log(self, kind: str, payload: dict, event_id: Optional[str] = None) -> None:
        self.log_scritti.append((kind, dict(payload)))

    def kinds(self) -> List[str]:
        return [k for k, _ in self.log_scritti]

    def payload(self, kind: str) -> Dict[str, Any]:
        for k, p in self.log_scritti:
            if k == kind:
                return p
        raise AssertionError(f"nessuna attivita' '{kind}' fra {self.kinds()}")

    def insert_trade(self, row: dict) -> int:
        r = dict(row, id=len(self.righe) + 1)
        self.righe.append(r)
        return int(r["id"])

    def update_trade(self, tid: int, **kw: Any) -> None:
        self.aggiornate.append(dict(kw, id=tid))


class MercatoConto:
    """Espone la POSIZIONE DI CONTO come `_RealMarket`: `list_account_orders` e
    `list_account_cleared_orders`, SENZA filtro di strategia."""

    def __init__(self, vivi: Optional[List[dict]] = None,
                 morti: Optional[List[dict]] = None,
                 esplode: bool = False) -> None:
        self.vivi = list(vivi or [])
        self.morti = list(morti or [])
        self.esplode = esplode
        self.letture: List[str] = []
        self.annullati: List[str] = []

    def list_account_orders(self, market_id: str) -> List[dict]:
        if self.esplode:
            raise RuntimeError("rete giu'")
        self.letture.append(f"vivi:{market_id}")
        return [o for o in self.vivi if str(o["market_id"]) == str(market_id)]

    def list_account_cleared_orders(self, market_id: str) -> List[dict]:
        if self.esplode:
            raise RuntimeError("rete giu'")
        self.letture.append(f"morti:{market_id}")
        return [o for o in self.morti if str(o["market_id"]) == str(market_id)]

    def cancel_order_live(self, bet_id: str, market_id: str, size_reduction=None):
        from Betfair.omega.omega_market import CancelResult

        self.annullati.append(str(bet_id))
        return CancelResult(ok=True, status="SUCCESS", bet_id=str(bet_id),
                            size_cancelled=1.0, error_code=None, riletto=True,
                            size_matched=0.0, avg_price_matched=None,
                            size_remaining=0.0, raw={})


def gamba_ingresso(matched: float = 10.0) -> E.Leg:
    return E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                 side="back", price=1.50, size=10.0, matched=matched, avg_price=1.50,
                 ref="under_entry-0-1", status="open", placed_at=KO - 600)


def evento() -> Dict[str, Any]:
    return {"event_id": "E1", "event_name": "A v B", "state": "LIVE_COVERED",
            "markets": {E.MARKET_OU35: {"market_id": MERCATO_35},
                        E.MARKET_OU45: {"market_id": "1.45"}},
            "ctx": {"selections": {f"{E.MARKET_OU35}|{E.SEL_UNDER}": SEL_UNDER_35}}}


@pytest.fixture(autouse=True)
def _riga_e_orologio(monkeypatch):
    """La riga di `mike_trades` della gamba (il ref di piazzamento e' `mike-t1`)
    e la memoria della cadenza azzerata fra un test e l'altro."""
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "open", "bet_id": "B1", "mode": "live",
            "signal_key": leg.ref, "market_id": MERCATO_35,
            "selection_id": SEL_UNDER_35})
    S._CONTO_LETTO_A.clear()
    yield
    S._CONTO_LETTO_A.clear()


# ===========================================================================
# 1. MAI SOVRACOPERTURA — la guardia (`engine._mai_sovracopertura`)
# ===========================================================================
def copertura(**kw: Any) -> E.Leg:
    base = dict(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                side="back", price=8.0, size=3.0, ref="over_cover-0-5",
                status="pending", placed_at=KO + 100)
    base.update(kw)
    return E.Leg(**base)


def azione_copertura(size: float = 3.0) -> E.Action:
    return E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                    selection=E.SEL_OVER, side="back", price=8.0, size=size)


@pytest.mark.parametrize("stato", ["pending", E.STATUS_RECONCILE])
def test_una_copertura_in_volo_ferma_la_copertura_nuova(stato):
    """VIVA o a ESITO IGNOTO: in tutti e due i casi la copertura puo' essere a
    mercato, quindi una seconda non si emette."""
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[gamba_ingresso(), copertura(status=stato)])
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura()], "copertura: riprezzo")
    fuori = E._mai_sovracopertura(ctx, d)
    assert [a for a in fuori.actions if a.kind == "place"] == []
    assert "mai sovracopertura" in fuori.reason


@pytest.mark.parametrize("stato", ["pending", E.STATUS_RECONCILE])
def test_lannullamento_della_copertura_passa_sempre(stato):
    """Si toglie la copertura NUOVA, mai l'annullamento: quello e' il modo in cui
    al giro dopo la vecchia non sara' piu' viva."""
    vecchia = copertura(status=stato)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[gamba_ingresso(), vecchia])
    d = E.Decision("LIVE_COVER_PENDING",
                   [E.Action(kind="cancel", ref=vecchia.ref, role="over_cover"),
                    azione_copertura()], "copertura: riprezzo")
    fuori = E._mai_sovracopertura(ctx, d)
    assert [a.kind for a in fuori.actions] == ["cancel"]


def test_senza_ordini_da_piazzare_lo_stato_NON_avanza():
    """Stessa regola di `_strip_openings`: se non resta niente da piazzare il
    ramo deve poter riprovare IDENTICO al giro dopo."""
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso(), copertura()])
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura()], "copertura",
                   updates={"cover_stage": 3})
    fuori = E._mai_sovracopertura(ctx, d)
    assert fuori.state == "LIVE_COVERED"
    assert fuori.updates == {}


def test_senza_copertura_in_volo_la_copertura_passa():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[gamba_ingresso()])
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura()], "copertura")
    assert E._mai_sovracopertura(ctx, d).actions == d.actions


def test_una_copertura_gia_MORTA_non_ferma_niente():
    """`cancelled`/`open` non sono «in volo»: la gamba non e' piu' sul book."""
    for stato in ("cancelled", "open"):
        ctx = E.MatchCtx(state="LIVE_UNCOVERED",
                         legs=[gamba_ingresso(), copertura(status=stato, matched=3.0)])
        d = E.Decision("LIVE_COVER_PENDING", [azione_copertura()], "copertura")
        assert len(E._mai_sovracopertura(ctx, d).actions) == 1, stato


def test_la_guardia_non_tocca_le_lay_ne_le_altre_selezioni():
    """Una copertura in volo non deve impedire un'uscita: sono cose diverse."""
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso(), copertura()])
    lay = E.Action(kind="place", role="under_green", market=E.MARKET_OU35,
                   selection=E.SEL_UNDER, side="lay", price=1.48, size=10.0)
    d = E.Decision("LIVE_CLOSING", [lay], "uscita")
    assert E._mai_sovracopertura(ctx, d).actions == [lay]


def test_copertura_in_volo_su_UNALTRA_selezione_non_conta():
    ctx = E.MatchCtx(state="LIVE_COVERED",
                     legs=[gamba_ingresso(), copertura(selection=E.SEL_UNDER)])
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura()], "copertura")
    assert len(E._mai_sovracopertura(ctx, d).actions) == 1


def test_copertura_in_volo_la_trova_la_funzione_dedicata():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso(), copertura()])
    trovata = E.copertura_in_volo(ctx, E.MARKET_OU45, E.SEL_OVER)
    assert trovata is not None and trovata.ref == "over_cover-0-5"
    assert E.copertura_in_volo(ctx, E.MARKET_OU45, E.SEL_OVER,
                              escludi="over_cover-0-5") is None


def test_il_riprezzo_della_copertura_emette_SOLO_lannullamento():
    """IL COMPORTAMENTO NUOVO, dal ramo VERO (`_decide_cover_pending`): finche'
    la vecchia copertura e' viva esce l'annullamento e basta; la copertura nuova
    arriva al giro dopo, dimensionata sulla copertura REALE gia' abbinata."""
    vecchia = copertura(size=3.0, matched=0.0, placed_at=KO)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING",
                     legs=[gamba_ingresso(), vecchia], cover_stage=0)
    books = {
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.50, back_size=200.0,
                                             best_lay=1.52, lay_size=200.0),
        (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=9.0, back_size=200.0,
                                            best_lay=9.4, lay_size=200.0),
    }
    snap = E.Snapshot(now=KO + 600, ko_at=KO, books=books, inplay=True, minute=30,
                      goals=1, feed_fresh=True, order_fresh=True)
    d = E.decide(ctx, snap, PAR)
    piazzati = [a for a in d.actions if a.kind == "place" and a.role == "over_cover"]
    assert piazzati == [], "la copertura nuova non deve uscire nello stesso giro"
    assert any(a.kind == "cancel" for a in d.actions)


# ===========================================================================
# 2. IL CONTROLLO J6
# ===========================================================================
def snap_cover(prezzo_over: float = 8.0) -> E.Snapshot:
    books = {
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.50, back_size=200.0,
                                             best_lay=1.52, lay_size=200.0),
        (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=prezzo_over, back_size=200.0,
                                            best_lay=prezzo_over + 0.4, lay_size=200.0),
    }
    return E.Snapshot(now=KO + 600, ko_at=KO, books=books, inplay=True, minute=30,
                      goals=1, feed_fresh=True, order_fresh=True)


def _viola(ctx, d, codice="J6"):
    sollecitati: Dict[str, int] = {}
    v = CERT.verifica(ctx, snap_cover(), d, PAR, sollecitati)
    return sollecitati.get(codice, 0), [x for x in v if x.codice == codice]


def test_J6_vede_due_coperture_in_volo_insieme():
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING",
                     legs=[gamba_ingresso(), copertura(ref="over_cover-0-5"),
                           copertura(ref="over_cover-0-6")])
    quante, viol = _viola(ctx, E.Decision("LIVE_COVERED", [], "attesa"))
    assert quante == 1 and len(viol) == 1
    assert "due coperture in volo" in viol[0].dettaglio


def test_J6_vede_la_copertura_nuova_annullata_nello_stesso_giro():
    """L'annullamento EMESSO non e' un annullamento CONFERMATO: J6 lo dice."""
    vecchia = copertura()
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[gamba_ingresso(), vecchia])
    d = E.Decision("LIVE_COVER_PENDING",
                   [E.Action(kind="cancel", ref=vecchia.ref, role="over_cover"),
                    azione_copertura()], "riprezzo")
    quante, viol = _viola(ctx, d)
    assert quante == 1 and len(viol) == 1
    assert "annullamento emesso non e' un annullamento confermato" in viol[0].dettaglio


def test_J6_vede_la_SOVRACOPERTURA_in_quantita():
    """Nessuna copertura in volo, ma la size proposta supera di gran lunga il
    residuo previsto: e' Over comprato due volte."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[gamba_ingresso()])
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura(size=50.0)], "copertura")
    quante, viol = _viola(ctx, d)
    assert quante == 1 and len(viol) == 1
    assert "sovracopertura" in viol[0].dettaglio


def test_J6_tace_sulla_copertura_giusta():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[gamba_ingresso()])
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura(size=2.0)], "copertura")
    quante, viol = _viola(ctx, d)
    assert quante == 1 and viol == []


def test_J6_non_ha_un_caso_quando_di_copertura_non_si_parla():
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[gamba_ingresso()])
    quante, viol = _viola(ctx, E.Decision("PRE_OPEN", [], "tengo"))
    assert quante == 0 and viol == []


# ===========================================================================
# 3. LA POSIZIONE DI CONTO — le funzioni pure
# ===========================================================================
def test_netto_su_selezione_somma_back_meno_lay():
    righe = [ordine_conto(ref="mike-t1", side="back", abbinato=10.0),
             ordine_conto(ref="utente-1", side="lay", abbinato=4.0)]
    assert S._netto_su_selezione(righe, MERCATO_35, SEL_UNDER_35) == 6.0


def test_netto_su_selezione_sa_isolare_gli_ordini_DEL_BOT():
    """Il punto dell'ordine dell'utente: nella posizione di conto ci sono ANCHE
    le sue operazioni, e Mike deve riconoscere LA SUA parte, per riferimento."""
    righe = [ordine_conto(ref="mike-t1", side="back", abbinato=10.0),
             ordine_conto(ref="utente-suo-back", side="back", abbinato=3.0),
             ordine_conto(ref="utente-chiusura", side="lay", abbinato=13.0)]
    assert S._netto_su_selezione(righe, MERCATO_35, SEL_UNDER_35) == 0.0
    assert S._netto_su_selezione(righe, MERCATO_35, SEL_UNDER_35,
                                 solo_refs={"mike-t1"}) == 10.0


def test_netto_su_selezione_ignora_altri_mercati_e_altre_selezioni():
    righe = [ordine_conto(ref="mike-t1", side="back", abbinato=10.0),
             ordine_conto(ref="x", side="back", abbinato=99.0, market_id="1.99"),
             ordine_conto(ref="y", side="back", abbinato=99.0, selection_id=12345)]
    assert S._netto_su_selezione(righe, MERCATO_35, SEL_UNDER_35) == 10.0


def test_posizione_attesa_e_il_netto_delle_gambe_abbinate():
    lay = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                side="lay", price=1.48, size=4.0, matched=4.0, avg_price=1.48,
                ref="under_green-0-2", status="open", placed_at=KO)
    ctx = E.MatchCtx(legs=[gamba_ingresso(), lay])
    assert S._posizione_attesa(ctx, E.MARKET_OU35, E.SEL_UNDER) == 6.0


def test_refs_di_mike_prende_ENTRAMBE_le_grafie():
    """Il ref della gamba (usato dalle uscite) E `mike-t<id>` (usato dalle
    aperture): cercarne una sola e' il difetto 4 del 15/09."""
    db = DbFinto()
    ctx = E.MatchCtx(legs=[gamba_ingresso()])
    refs = S._refs_di_mike(ctx, E.MARKET_OU35, E.SEL_UNDER, db, "E1")
    assert "under_entry-0-1" in refs and "mike-t1" in refs


# ===========================================================================
# 4. LA POSIZIONE DI CONTO — la sorveglianza
# ===========================================================================
def _sorveglia(mercato, ctx, *, mode="live", now=KO + 1000.0, db=None, extra=None):
    return S._sorveglia_posizione_di_conto(
        db=db or DbFinto(), market=mercato, ctx=ctx, ev=evento(),
        extra=extra if extra is not None else dict(evento()["ctx"]),
        params=PAR, mode=mode, now_ts=now)


def test_in_PAPER_non_si_legge_nessun_conto():
    mercato = MercatoConto()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx, mode="paper") is False
    assert mercato.letture == []


def test_la_posizione_INTATTA_non_fa_scattare_niente():
    mercato = MercatoConto(morti=[ordine_conto(ref="mike-t1", side="back", abbinato=10.0)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx) is False
    assert ctx.chiuso_dall_utente is False


def test_la_lay_DELLUTENTE_chiude_la_posizione_e_il_bot_lo_capisce():
    """L'utente chiude dal sito Betfair: il suo ordine non ha il ref di Mike,
    ma sul CONTO la posizione non c'e' piu'."""
    db = DbFinto()
    mercato = MercatoConto(morti=[
        ordine_conto(ref="mike-t1", side="back", abbinato=10.0),
        ordine_conto(ref="utente-chiusura", side="lay", abbinato=10.0, bet_id="U1"),
    ])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx, db=db) is True
    assert ctx.chiuso_dall_utente is True
    assert ctx.no_reentry is True and ctx.reentry_done is True
    p = db.payload("chiuso_dall_utente")
    assert p["dove"] == "fuori dall'app"
    assert p["selezioni"][0]["atteso"] == 10.0
    assert p["selezioni"][0]["netto_di_conto"] == 0.0


def test_lutente_ha_ANCHE_operazioni_sue_e_Mike_riconosce_la_PROPRIA():
    """Sulla stessa partita l'utente ha un back suo da 3 e poi chiude tutto con
    una lay da 13: il netto di conto va a zero, ma le gambe di Mike ci sono
    ancora (per ref e size), quindi e' una chiusura dell'utente, non una
    riconciliazione."""
    db = DbFinto()
    mercato = MercatoConto(morti=[
        ordine_conto(ref="mike-t1", side="back", abbinato=10.0),
        ordine_conto(ref="utente-suo-back", side="back", abbinato=3.0, bet_id="U0"),
        ordine_conto(ref="utente-chiusura", side="lay", abbinato=13.0, bet_id="U1"),
    ])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx, db=db) is True
    p = db.payload("chiuso_dall_utente")["selezioni"][0]
    assert p["mio_sul_conto"] == 10.0 and p["altrui"] == -10.0


def test_le_gambe_di_Mike_che_NON_si_ritrovano_NON_spengono_il_bot():
    """Se gli ordini di Mike non ci sono sul conto il caso e' una
    RICONCILIAZIONE: non si spegne un bot su un dubbio."""
    db = DbFinto()
    mercato = MercatoConto(morti=[])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx, db=db) is False
    assert ctx.chiuso_dall_utente is False
    assert db.payload("posizione_di_conto")["verdetto"] == "gambe_non_ritrovate"


def test_la_chiusura_PARZIALE_dellutente_si_dichiara_e_basta():
    """Una lay da 4 su 10: il bot continua a proteggere quello che resta."""
    db = DbFinto()
    mercato = MercatoConto(morti=[
        ordine_conto(ref="mike-t1", side="back", abbinato=10.0),
        ordine_conto(ref="utente-chiusura", side="lay", abbinato=4.0, bet_id="U1"),
    ])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx, db=db) is False
    assert ctx.chiuso_dall_utente is False
    assert db.payload("posizione_di_conto")["verdetto"] == "ridotta_dall_utente"


def test_la_rete_giu_non_decide_niente_e_si_riprova_al_giro_dopo():
    db = DbFinto()
    mercato = MercatoConto(esplode=True)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(mercato, ctx, db=db) is False
    assert ctx.chiuso_dall_utente is False
    assert S._CONTO_LETTO_A.get("E1") == 0.0     # la cadenza NON consuma il turno


def test_un_mercato_senza_posizione_di_conto_lo_DICHIARA():
    """Un `market` che non espone la lettura (percorso vecchio) non deve fingere:
    lo scrive nelle attivita'."""
    class SenzaConto:
        pass

    db = DbFinto()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _sorveglia(SenzaConto(), ctx, db=db) is False
    assert "posizione_di_conto_non_letta" in db.kinds()


def test_la_cadenza_e_quella_del_respiro_del_database():
    """Due giri ravvicinati = UNA lettura sola (`reconcile_every_s`, 30 s)."""
    mercato = MercatoConto(morti=[ordine_conto(ref="mike-t1", side="back", abbinato=10.0)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    _sorveglia(mercato, ctx, now=KO + 1000.0)
    prime = len(mercato.letture)
    _sorveglia(mercato, ctx, now=KO + 1005.0)
    assert len(mercato.letture) == prime, "una seconda lettura entro 30 s non si fa"
    _sorveglia(mercato, ctx, now=KO + 1000.0 + float(PAR["reconcile_every_s"]) + 1.0)
    assert len(mercato.letture) > prime


def test_senza_posizione_aperta_non_si_legge_nessun_conto():
    mercato = MercatoConto()
    ctx = E.MatchCtx(state="WATCH", legs=[])
    assert _sorveglia(mercato, ctx) is False
    assert mercato.letture == []


# ===========================================================================
# 5. DOPO LA CHIUSURA DELL'UTENTE IL MOTORE NON FA PIU' NIENTE
# ===========================================================================
def test_decide_non_emette_nulla_dopo_chiuso_dall_utente():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()],
                     chiuso_dall_utente=True)
    d = E.decide(ctx, snap_cover(), PAR)
    assert d.actions == []
    assert d.state == "LIVE_COVERED"
    assert "fuori dall'app" in d.reason


def test_il_regolamento_avviene_lo_stesso_a_mercato_CHIUSO():
    """La partita NON diventa terminale: altrimenti il P&L vero delle gambe
    davvero abbinate non verrebbe mai contabilizzato."""
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()],
                     chiuso_dall_utente=True)
    snap = E.Snapshot(now=KO + 9000, ko_at=KO, books={}, inplay=True,
                      market_status="CLOSED", final_total=2)
    d = E.decide(ctx, snap, PAR)
    assert d.state == "SETTLING"


def test_R3_diventa_rosso_se_il_bot_agisce_lo_stesso():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()],
                     chiuso_dall_utente=True)
    sollecitati: Dict[str, int] = {}
    d = E.Decision("LIVE_COVER_PENDING", [azione_copertura()], "copertura")
    v = CERT.verifica(ctx, snap_cover(), d, PAR, sollecitati)
    assert sollecitati.get("R3") == 1
    assert [x.codice for x in v if x.codice == "R3"] == ["R3"]


def test_R3_e_verde_quando_il_bot_sta_fermo():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()],
                     chiuso_dall_utente=True)
    sollecitati: Dict[str, int] = {}
    v = CERT.verifica(ctx, snap_cover(), E.Decision("LIVE_COVERED", [], "fermo"),
                      PAR, sollecitati)
    assert sollecitati.get("R3") == 1
    assert [x for x in v if x.codice == "R3"] == []


def test_lo_stato_chiuso_dall_utente_e_PERSISTITO():
    """Un riavvio a meta' partita non deve far ricominciare Mike a gestire una
    posizione che non c'e' piu' (difetto 19 del catalogo)."""
    assert "chiuso_dall_utente" in S._CTX_FIELDS


# ===========================================================================
# 6. A2 — DA UNO STATO TERMINALE NON ESCE NESSUNA AZIONE
# ===========================================================================
@pytest.mark.parametrize("stato", list(E.TERMINAL_STATES))
def test_decide_su_uno_stato_terminale_non_produce_azioni(stato):
    """LA SECONDA LINEA DI DIFESA. Nel replay A2 non ha mai un caso perche'
    `service._run_event` esce prima di chiamare `decide`; la guardia dentro
    `decide` e' quella che conta se qualcuno togliesse quel return. Togliendo
    `if st in TERMINAL_STATES` da `engine.decide` questo test e' ROSSO."""
    ctx = E.MatchCtx(state=stato, legs=[gamba_ingresso()])
    d = E.decide(ctx, snap_cover(), PAR)
    assert d.actions == []
    assert d.state == stato


@pytest.mark.parametrize("stato", list(E.TERMINAL_STATES))
def test_A2_e_sollecitato_e_verde_su_ogni_stato_terminale(stato):
    ctx = E.MatchCtx(state=stato, legs=[gamba_ingresso()])
    sollecitati: Dict[str, int] = {}
    d = E.decide(ctx, snap_cover(), PAR)
    v = CERT.verifica(ctx, snap_cover(), d, PAR, sollecitati)
    assert sollecitati.get("A2") == 1
    assert [x for x in v if x.codice == "A2"] == []


@pytest.mark.parametrize("stato", list(E.TERMINAL_STATES))
def test_A2_diventa_rosso_se_da_un_terminale_esce_unazione(stato):
    ctx = E.MatchCtx(state=stato, legs=[gamba_ingresso()])
    sollecitati: Dict[str, int] = {}
    d = E.Decision(stato, [azione_copertura()], "azione da uno stato terminale")
    v = CERT.verifica(ctx, snap_cover(), d, PAR, sollecitati)
    assert [x.codice for x in v if x.codice == "A2"] == ["A2"]


def test_il_servizio_non_chiama_nemmeno_decide_su_uno_stato_terminale():
    """LA PRIMA linea di difesa, misurata: `_run_event` esce subito. E' per
    questo che A2 resta a zero casi nel replay, e va detto ad alta voce."""
    chiamate: List[int] = []
    vero = E.decide
    try:
        E.decide = lambda *a, **k: chiamate.append(1) or vero(*a, **k)  # type: ignore
        ev = dict(evento(), state="SETTLED")
        azioni, settled = S._run_event(
            db=DbFinto(), market=MercatoConto(), ev=ev, row=None, params=PAR,
            mode="live", now=S._now(), scanner_age=0.0, atlas=None, dry=True)
    finally:
        E.decide = vero  # type: ignore
    assert (azioni, settled) == (0, 0)
    assert chiamate == []


# ===========================================================================
# 7. IL BANCO parla come Betfair (`order_state_by_bet_id`)
# ===========================================================================
def test_il_banco_espone_order_state_by_bet_id_con_le_chiavi_del_vero():
    """Senza questo metodo il ramo (b) della riapertura («l'ordine appoggiato e'
    SCADUTO alla sospensione») non poteva capitare nel replay: il servizio
    tornava «ignoto/mercato_senza_lettura»."""
    from Betfair.stream.backtest.banco_comune import MercatoFlumine

    class StrategiaFinta:
        mercati: Dict[str, Any] = {}

    class OrdineFinto:
        """Un ordine flumine: `simulated.size_matched`, `size_remaining`, `bet_id`."""

        class simulated:            # noqa: N801 - e' il nome di flumine
            size_matched = 0.0
            average_price_matched = None

        bet_id = "B7"
        size_remaining = 0.0
        status = None

    m = MercatoFlumine(StrategiaFinta())
    assert m.order_state_by_bet_id("mai-visto") == {"found": False}
    m.ordini["ko_green-0-3"] = OrdineFinto()
    st = m.order_state_by_bet_id("B7")
    # LE STESSE CHIAVI di `omega_market.order_state_by_bet_id`, nemmeno una in piu'
    assert set(st) == {"found", "size_matched", "avg_price_matched",
                       "size_remaining", "matched_date", "placed_date"}
    assert st["found"] is True and st["size_remaining"] == 0.0


# ===========================================================================
# 8. LA FAMIGLIA K — la memoria del bot contro il MERCATO
#
# ⚠️ PERCHE' ESISTE. Il 16/09 sera la falsificazione indipendente dei cinque
# difetti del 15/09 ha dato questo risultato: reintrodotti uno a uno sul codice
# di oggi, il replay su 35760084 NON diventava rosso — il referto era identico
# cifra per cifra. I controlli A-J guardano la DECISIONE; quei difetti stanno
# nel rapporto fra cio' che il bot CREDE e cio' che il MERCATO dice. Qui si
# prova che i controlli K sanno diventare rossi: un controllo che non sa
# diventare rosso non certifica (PROCESSO_STANDARD_BOT §6.7).
# ===========================================================================
def _k(ctx, ordini, rifiutati=None, righe=None):
    sollecitati: Dict[str, int] = {}
    v = CERT.verifica_consapevolezza(ctx, ordini, rifiutati, righe, sollecitati)
    return sollecitati, {x.codice for x in v}, v


def test_K_sono_nellelenco_dei_controlli_e_quindi_nella_copertura():
    codici = [c for c, _ in CERT.elenco_controlli()]
    assert {"K1", "K2", "K3", "K4"} <= set(codici)
    # e un controllo K mai sollecitato compare fra i «non lo so»
    assert {"K1", "K2", "K3", "K4"} <= {c for c, _ in CERT.mai_sollecitati({})}


def test_K1_e_verde_quando_il_bot_crede_quello_che_il_mercato_dice():
    leg = gamba_ingresso(matched=10.0)
    ordini = {leg.ref: ordine_conto(ref=leg.ref, side="back", abbinato=10.0, prezzo=1.50)}
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[leg])
    sollecitati, codici, _ = _k(ctx, ordini)
    assert sollecitati["K1"] == 1 and "K1" not in codici


def test_K1_diventa_rosso_sul_PREZZO_MEDIO_sbagliato():
    """E' il difetto 3 del 15/09: `avg_price` al posto di `avg_price_matched`,
    cioe' il prezzo CHIESTO contabilizzato al posto di quello ABBINATO."""
    leg = gamba_ingresso(matched=10.0)
    leg.avg_price = 1.50                      # quello chiesto
    ordini = {leg.ref: ordine_conto(ref=leg.ref, side="back", abbinato=10.0, prezzo=1.42)}
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[leg])
    _s, codici, v = _k(ctx, ordini)
    assert "K1" in codici
    assert "prezzo medio" in v[0].dettaglio


def test_K1_diventa_rosso_sullABBINATO_sbagliato():
    leg = gamba_ingresso(matched=0.0)          # il bot crede che non sia abbinata
    ordini = {leg.ref: ordine_conto(ref=leg.ref, side="back", abbinato=10.0)}
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[leg])
    _s, codici, _v = _k(ctx, ordini)
    assert "K1" in codici


def test_K1_tace_su_un_ordine_ANCORA_VIVO():
    """Il bot legge Betfair alla SUA cadenza: una divergenza su un ordine ancora
    sul book e' normale, non e' un difetto. Il controllo e' conservativo."""
    leg = gamba_ingresso(matched=0.0)
    ordini = {leg.ref: ordine_conto(ref=leg.ref, side="back", abbinato=4.0,
                                    stato="EXECUTABLE", residuo=6.0)}
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[leg])
    _s, codici, _v = _k(ctx, ordini)
    assert "K1" not in codici


def test_K1_tace_su_una_gamba_a_esito_IGNOTO():
    leg = gamba_ingresso(matched=0.0)
    leg.status = E.STATUS_RECONCILE
    ordini = {leg.ref: ordine_conto(ref=leg.ref, side="back", abbinato=10.0)}
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[leg])
    _s, codici, _v = _k(ctx, ordini)
    assert "K1" not in codici


def test_K2_diventa_rosso_se_una_gamba_RIFIUTATA_resta_viva():
    """Difetto 2 del 15/09: `res.ok` mai letto. Betfair ha detto NO, nessun
    ordine esiste, e il bot continua a credere di avere una copertura."""
    leg = copertura(status="pending")
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[gamba_ingresso(), leg])
    _s, codici, v = _k(ctx, {}, rifiutati={leg.ref})
    assert "K2" in codici and "RIFIUTATO" in v[0].dettaglio


def test_K2_e_verde_se_la_gamba_rifiutata_e_stata_chiusa():
    leg = copertura(status="cancelled")
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[gamba_ingresso(), leg])
    sollecitati, codici, _v = _k(ctx, {}, rifiutati={leg.ref})
    assert sollecitati["K2"] == 1 and "K2" not in codici


def test_K3_diventa_rosso_se_il_ref_si_scrive_in_una_grafia_e_si_legge_in_unaltra():
    """Difetto 1 del 15/09: `customerOrderRef` scritto, `customer_order_ref`
    letto. Qui l'ordine porta SOLO la grafia camelCase, come la risposta grezza
    di Betfair: il lettore di produzione deve trovarlo lo stesso."""
    leg = gamba_ingresso()
    grezzo = {"marketId": MERCATO_35, "selectionId": SEL_UNDER_35, "side": "back",
              "status": "EXECUTION_COMPLETE", "sizeMatched": 10.0,
              "customerOrderRef": leg.ref}
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[leg])
    _s, codici, _v = _k(ctx, {leg.ref: grezzo})
    assert "K3" not in codici, "il lettore di produzione accetta ENTRAMBE le grafie"
    # e se l'ordine non porta NESSUNA delle due, il controllo lo dice
    senza = {k: v for k, v in grezzo.items() if k != "customerOrderRef"}
    _s2, codici2, _v2 = _k(ctx, {leg.ref: senza})
    assert "K3" in codici2


def test_K4_diventa_rosso_se_una_chiusura_non_dice_che_cosa_chiude():
    """Difetto 5 del 15/09: `closes_trade_id` in colonna ma letto nel meta —
    nessuna chiusura riconosciuta, place-and-trim rifiutato in loop."""
    righe = [{"id": 7, "role": "under_green", "meta": {}}]
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=[gamba_ingresso()])
    _s, codici, _v = _k(ctx, {}, righe=righe)
    assert "K4" in codici
    righe_ok = [{"id": 7, "role": "under_green", "closes_trade_id": 1, "meta": {}}]
    _s2, codici2, _v2 = _k(ctx, {}, righe=righe_ok)
    assert "K4" not in codici2


def test_il_banco_sa_provocare_il_RIFIUTO_di_betfair():
    """Lo scenario `rifiuti-betfair`: senza, `res.ok` non vale MAI False nel
    replay e il difetto 2 non ha un caso da nessuna parte."""
    from Betfair.mike.tools import replay_registrazioni as R

    assert R.SCENARIO_RIFIUTI in R.SCENARI_DESCRITTI
    from Betfair.stream.backtest.banco_comune import MercatoFlumine

    class StrategiaFinta:
        mercati: Dict[str, Any] = {}

    m = MercatoFlumine(StrategiaFinta())
    m.guasti["place_rifiuto"] = 1
    res = m.place_order_live(market_id="1.1", selection_id=1, price=2.0, size=2.0,
                             event_id="E1", side="lay", customer_ref="r1")
    assert res.ok is False and res.bet_id is None
    assert m.rifiutati and m.rifiutati[0]["ref"] == "r1"
