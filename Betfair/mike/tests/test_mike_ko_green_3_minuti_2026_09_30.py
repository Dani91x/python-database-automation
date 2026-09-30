"""LA BANCA AL FISCHIO RESTA A MERCATO PER TUTTA LA FINESTRA (ordine dell'utente, 30/09 15:40).

Testuale: «quell'ordine deve restare a mercato per 3 minuti come da
progettazione, SOLO DOPO I 3 minuti, controlla quando e' stato abbinato (se
parziale come in questo caso) RITIRA IL RESTO, e si copre sulla selezione 4.5
PER L'IMPORTO RIMANENTE SU UNDER 3.5».

Il caso vero (live, partita 36130526 Vsetin-Bohemians): fischio 15:30:03, banca
``ko_green`` 5,10 @ 2,08 appoggiata alle 15:30:04; alle 15:30:32 abbinata IN
PARTE 1,00 (residuo 4,10 vivo) e nello stesso secondo Mike ha ANNULLATO il
residuo («cancelled_by_engine»), perche' il riallineo di ``_decide_ko_green``
confrontava la size VIVA (5,10) con il piano ricalcolato sulla posizione che
comprendeva gia' l'abbinato della stessa banca (4,10): «la posizione e'
cambiata» -> annullo; al giro dopo la gamba non viva con abbinato > 0 cadeva in
«uscita al fischio parziale: copro il residuo». Dopo 29 secondi invece di 180.

La regola nuova, provata qui sulla classe VERA del motore (``E.decide``) e sul
ciclo vero del servizio (``S.run_once`` con ``FakeDB``/``FakeMarket`` di
``test_mike_service`` e il runner finto che parla il protocollo vero):

  1. dal fischio la banca resta a mercato per TUTTA ``ko_green_window_s``, anche
     abbinata in parte: nessun annullo, nessuna copertura;
  2. allo scadere: tutta abbinata -> FLAT (ma quella arriva appena si abbina);
     in parte -> annullo del residuo e copertura banca Under 4,5 sul rischio
     RESIDUO (5,00 puntati, 1,00 chiuso -> 4,00 x 1,2 / 0,95 = 5,05);
     non abbinata -> annullo e copertura intera (5,00 x 1,2 / 0,95 = 6,32);
  3. banca fatta scadere da Betfair dentro la finestra con un parziale: si
     riappoggia per il RESIDUO finche' la finestra e' aperta;
  4. gol precoce nella finestra: la strada C di oggi.

File ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run, state


KO = 1_700_000_000.0
PAR = C.merge_params(None)
FINESTRA = float(PAR["ko_green_window_s"])

# i numeri del caso vero: punta Under 3,5 5,00 @ 2,12 -> banca 2 tick sotto = 2,08
STAKE, PE, P_BANCA, S_BANCA = 5.00, 2.12, 2.08, 5.10


def book(bb: float, *, status: str = "OPEN", inplay: bool = True) -> E.Book:
    return E.Book(best_back=bb, back_size=200.0, best_lay=round(bb + 0.02, 2), lay_size=200.0,
                  status=status, inplay=inplay)


def snap(now: float, *, goals: int = 0, minute: int = 1) -> E.Snapshot:
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(2.10),
             (E.MARKET_OU45, E.SEL_UNDER): book(1.18),
             (E.MARKET_OU45, E.SEL_OVER): book(6.0)}
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=minute,
                      goals=goals, feed_fresh=True, order_fresh=True)


def banca(**kw) -> E.Leg:
    base = dict(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                price=P_BANCA, size=S_BANCA, ref="ko_green-0-3", status="pending",
                placed_at=KO + 1.0)
    base.update(kw)
    return E.Leg(**base)


def ctx_al_fischio(gambe: Optional[List[E.Leg]] = None) -> E.MatchCtx:
    ingresso = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                     side="back", price=PE, size=STAKE, matched=STAKE, avg_price=PE,
                     ref="under_entry-0-1", status="open", placed_at=KO - 600)
    return E.MatchCtx(state="LIVE_KO_GREEN", legs=[ingresso] + list(gambe or []),
                      live_since=KO, ko_goals=0)


def _annulli(d: E.Decision) -> List[str]:
    return [a.ref for a in d.actions if a.kind == "cancel"]


def _posati(d: E.Decision, ruolo: Optional[str] = None) -> List[E.Action]:
    return [a for a in d.actions if a.kind == "place" and (ruolo is None or a.role == ruolo)]


# ---------------------------------------------------------------------------
def test_precondizione_la_banca_al_fischio_e_quella_del_caso_vero():
    d = E.decide(ctx_al_fischio(), snap(KO + 1.0), PAR)
    p = _posati(d, "ko_green")
    assert len(p) == 1 and p[0].side == "lay"
    assert p[0].price == pytest.approx(P_BANCA) and p[0].size == pytest.approx(S_BANCA)


def test_parziale_a_30_secondi_resta_a_mercato():
    """IL CASO VERO: 1,00 abbinato su 5,10, 29 s dopo il fischio. Nessun annullo,
    nessuna copertura, nessuna banca nuova: la stessa resta sul book."""
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA)])
    d = E.decide(ctx, snap(KO + 30.0), PAR)
    assert _annulli(d) == [], d.reason
    assert _posati(d) == [], d.reason
    assert d.state == "LIVE_KO_GREEN", d.reason
    assert not d.updates.get("cover_forced")


def test_parziale_abbinato_a_prezzo_migliore_resta_a_mercato():
    """Un limite si abbina anche MEGLIO (banca a 2,06 invece di 2,08): il residuo
    resta lo stesso ordine, non si riallinea."""
    ctx = ctx_al_fischio([banca(matched=2.0, avg_price=2.06)])
    d = E.decide(ctx, snap(KO + 90.0), PAR)
    assert _annulli(d) == [] and _posati(d) == [], d.reason
    assert d.state == "LIVE_KO_GREEN"


def test_parziale_allo_scadere_annulla_il_residuo_e_copre_il_rischio_residuo():
    """Allo scadere dei 180 s: annullo del residuo, poi (annullo confermato)
    banca Under 4,5 = 4,00 x 1,2 / 0,95 = 5,05."""
    viva = banca(matched=1.0, avg_price=P_BANCA)
    ctx = ctx_al_fischio([viva])
    fine = KO + FINESTRA + 1.0
    d = E.decide(ctx, snap(fine), PAR)
    assert _annulli(d) == ["ko_green-0-3"], d.reason
    assert _posati(d) == []
    assert d.state == "LIVE_UNCOVERED" and d.updates.get("cover_forced") is True
    E.apply_decision(ctx, d, fine)
    # annullo confermato da Betfair: la gamba resta con l'abbinato vero
    viva.status = "open"
    assert E.under_liability(ctx.legs) == pytest.approx(4.00)
    d2 = E.decide(ctx, snap(fine + 2.0), PAR)
    cop = _posati(d2, "over_cover")
    assert len(cop) == 1, d2.reason
    assert cop[0].market == E.MARKET_OU45 and cop[0].selection == E.SEL_UNDER
    assert cop[0].side == "lay"
    assert cop[0].size == pytest.approx(5.05)


def test_non_abbinata_allo_scadere_annullo_e_copertura_intera():
    viva = banca()
    ctx = ctx_al_fischio([viva])
    fine = KO + FINESTRA + 1.0
    d = E.decide(ctx, snap(fine), PAR)
    assert _annulli(d) == ["ko_green-0-3"] and d.state == "LIVE_UNCOVERED"
    E.apply_decision(ctx, d, fine)
    viva.status = "cancelled"
    d2 = E.decide(ctx, snap(fine + 2.0), PAR)
    cop = _posati(d2, "over_cover")
    assert len(cop) == 1 and cop[0].size == pytest.approx(6.32), d2.reason


def test_tutta_abbinata_a_60_secondi_e_flat_subito():
    ctx = ctx_al_fischio([banca(matched=S_BANCA, avg_price=P_BANCA, status="open")])
    d = E.decide(ctx, snap(KO + 60.0), PAR)
    assert d.state == "FLAT", d.reason
    assert _posati(d) == [] and _annulli(d) == []


def test_parziale_scaduto_da_betfair_nella_finestra_si_riappoggia_il_residuo():
    """Betfair ha fatto scadere il residuo (sospensione) con 1,00 gia' abbinato:
    finestra aperta -> si riappoggia la banca per il RESIDUO, niente copertura."""
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA, status="open")])
    d = E.decide(ctx, snap(KO + 60.0), PAR)
    assert d.state == "LIVE_KO_GREEN", d.reason
    p = _posati(d, "ko_green")
    assert len(p) == 1, d.reason
    assert p[0].price == pytest.approx(P_BANCA) and p[0].size == pytest.approx(4.10)


def test_parziale_scaduto_da_betfair_a_finestra_chiusa_si_copre():
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA, status="open")])
    d = E.decide(ctx, snap(KO + FINESTRA + 5.0), PAR)
    assert d.state == "LIVE_UNCOVERED" and d.updates.get("cover_forced") is True
    assert _posati(d) == [] and _annulli(d) == []


def test_gol_nella_finestra_con_parziale_strada_c():
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA)])
    d = E.decide(ctx, snap(KO + 40.0, goals=1), PAR)
    assert _annulli(d) == ["ko_green-0-3"]
    assert d.state == "LIVE_SECOND_ENTRY", d.reason


def test_se_cambia_la_posizione_d_ingresso_la_banca_si_riallinea():
    """Il riallineo resta per cio' per cui era nato: un fill del residuo PERSIST
    (l'Under e' cresciuto) cambia la banca giusta, e quella viva si annulla."""
    persist = E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                    side="back", price=PE, size=3.0, matched=3.0, avg_price=PE,
                    ref="under_last-0-2", status="open", placed_at=KO - 60)
    ctx = ctx_al_fischio([persist, banca(matched=1.0, avg_price=P_BANCA)])
    d = E.decide(ctx, snap(KO + 30.0), PAR)
    assert _annulli(d) == ["ko_green-0-3"], d.reason
    assert d.state == "LIVE_KO_GREEN"


# ---------------------------------------------------------------------------
# il ciclo vero del servizio (paper sul runner finto, protocollo vero)
# ---------------------------------------------------------------------------
def _evento_al_fischio() -> dict:
    return {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": "LIVE_KO_GREEN", "cycle_no": 0,
        "entry_price_initial": PE,
        "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": [{"role": "under_entry", "market": "OU35", "selection": "UNDER",
                       "side": "back", "price": PE, "size": STAKE, "matched": STAKE,
                       "avg_price": PE, "ref": "under_entry-0-1", "status": "open",
                       "placed_at": 0.0, "persistence": "LAPSE", "cycle_no": 0,
                       "final": False, "archived": False}],
        "dossier": {}, "live": {}, "ctx": {"ko_goals": 0}, "mode": "paper",
        "ko_at": (NOW - timedelta(seconds=5)).isoformat(),
    }


def _p():
    return payload(inplay=True, minute=1, sh=0, sa=0, ko=NOW - timedelta(seconds=5),
                   u35=(2.10, 2.12, 200.0, 200.0), u45=(1.18, 1.19, 200.0, 200.0))


def _gamba(db, ruolo):
    return [g for g in legs(db) if g["role"] == ruolo]


def test_servizio_parziale_al_fischio_resta_fino_allo_scadere(runner):
    db = FakeDB(params={"stake": STAKE})
    mk = FakeMarket()
    db.events["E1"] = _evento_al_fischio()
    run(db, mk, NOW, [row(_p(), updated=NOW)])
    assert state(db) == "LIVE_KO_GREEN"
    uscita = _gamba(db, "ko_green")
    assert len(uscita) == 1, db.kinds()
    ref = [c for c in runner.comandi if c["azione"] == "place"][-1]["ref"]
    assert uscita[0]["price"] == pytest.approx(P_BANCA)
    assert uscita[0]["size"] == pytest.approx(S_BANCA)
    # 29 s dopo: il runner abbina IN PARTE 1,00
    runner.abbina(ref, size=1.0)
    for dt in (29, 31, 60, 120, 170):
        t = NOW + timedelta(seconds=dt)
        run(db, mk, t, [row(_p(), updated=t)])
        assert state(db) == "LIVE_KO_GREEN", (dt, db.kinds()[-5:])
        g = _gamba(db, "ko_green")
        assert len(g) == 1 and g[0]["status"] == "pending", (dt, g)
        assert g[0]["matched"] == pytest.approx(1.0)
    assert [c for c in runner.comandi if c["azione"] == "cancel"] == [], \
        "annullo del residuo prima dello scadere della finestra"
    assert _gamba(db, "over_cover") == []
    # allo scadere: annullo del residuo (confermato dal runner) ...
    t = NOW + timedelta(seconds=FINESTRA + 2)
    run(db, mk, t, [row(_p(), updated=t)])
    assert len([c for c in runner.comandi if c["azione"] == "cancel"]) == 1
    g = _gamba(db, "ko_green")[0]
    assert g["status"] == "open" and g["matched"] == pytest.approx(1.0)
    # ... e la copertura banca Under 4,5 sul rischio residuo 4,00
    for k in range(1, 4):
        t2 = t + timedelta(seconds=2 * k)
        run(db, mk, t2, [row(_p(), updated=t2)])
    cop = _gamba(db, "over_cover")
    assert len(cop) == 1, (state(db), db.kinds()[-6:])
    assert cop[0]["market"] == "OU45" and cop[0]["selection"] == "UNDER"
    assert cop[0]["side"] == "lay" and cop[0]["size"] == pytest.approx(5.05)


# ---------------------------------------------------------------------------
# il controllo di condotta del banco: KG1 (certificazione.py)
# ---------------------------------------------------------------------------
def _kg1(ctx: E.MatchCtx, s: E.Snapshot, d: E.Decision) -> List[str]:
    soll: dict = {}
    out = [v.dettaglio for v in CERT.verifica(ctx, s, d, PAR, soll)
           if v.codice.startswith("KG1")]
    assert soll.get("KG1"), "KG1 non ha avuto il caso"
    return out


def _annullo(ref: str = "ko_green-0-3") -> E.Action:
    return E.Action(kind="cancel", ref=ref, role="ko_green", market=E.MARKET_OU35,
                    selection=E.SEL_UNDER)


def test_kg1_rosso_sull_annullo_del_parziale_a_29_secondi():
    """Il caso vero: annullo del residuo 29 s dopo il fischio."""
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA)])
    d = E.Decision("LIVE_KO_GREEN", [_annullo()], "uscita appoggiata a 2.08")
    viol = _kg1(ctx, snap(KO + 29.0), d)
    assert len(viol) == 1 and "29 s dal fischio" in viol[0]


def test_kg1_rosso_sulla_copertura_dentro_la_finestra():
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA, status="open")])
    d = E.Decision("LIVE_UNCOVERED", [], "uscita al fischio parziale: copro il residuo")
    viol = _kg1(ctx, snap(KO + 31.0), d)
    assert len(viol) == 1 and "copertura a 31 s" in viol[0]


def test_kg1_tace_allo_scadere_col_gol_e_sul_riallineo():
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA)])
    d = E.Decision("LIVE_UNCOVERED", [_annullo()], "scaduta")
    assert _kg1(ctx, snap(KO + FINESTRA + 1.0), d) == []
    assert _kg1(ctx, snap(KO + 40.0, goals=1),
                E.Decision("LIVE_SECOND_ENTRY", [_annullo()], "gol")) == []
    persist = E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                    side="back", price=PE, size=3.0, matched=3.0, avg_price=PE,
                    ref="under_last-0-2", status="open", placed_at=KO - 60)
    ctx2 = ctx_al_fischio([persist, banca(matched=1.0, avg_price=P_BANCA)])
    assert _kg1(ctx2, snap(KO + 30.0), E.Decision("LIVE_KO_GREEN", [_annullo()], "r")) == []


def test_kg1_rosso_sulla_copertura_dimensionata_sullo_stake_lordo():
    """Allo scadere la copertura vale il rischio RESIDUO (4,00 -> 5,05), mai lo
    stake lordo (5,00 -> 6,32)."""
    ctx = ctx_al_fischio([banca(matched=1.0, avg_price=P_BANCA, status="open")])
    ctx.state = "LIVE_UNCOVERED"
    giusta = E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                      selection=E.SEL_UNDER, side="lay", price=1.20, size=5.05)
    lorda = E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                     selection=E.SEL_UNDER, side="lay", price=1.20, size=6.32)
    s = snap(KO + FINESTRA + 5.0)
    assert _kg1(ctx, s, E.Decision("LIVE_COVER_PENDING", [giusta], "cop")) == []
    viol = _kg1(ctx, s, E.Decision("LIVE_COVER_PENDING", [lorda], "cop"))
    assert len(viol) == 1 and "6.32" in viol[0]


# ---------------------------------------------------------------------------
# lo scenario del banco: il guasto colpisce SOLO la banca al fischio
# ---------------------------------------------------------------------------
def _ordine_flumine(*, ref: str, side: str = "LAY", price: float = P_BANCA,
                    size: float = S_BANCA):
    """Le sole cose che il banco legge di un ordine di flumine: ``notes`` (il
    ``bot_ref`` sulla coda, il ``customer_order_ref`` del runner sul canale),
    ``order_type.price/size``, ``side``, ``market_id``, ``selection_id``."""
    from types import SimpleNamespace
    note = {"bot_ref": ref} if ref.startswith("mike-") else {"customer_order_ref": ref}
    return SimpleNamespace(notes=note, side=side, market_id="1.35", selection_id=1222344,
                           order_type=SimpleNamespace(price=price, size=size))


def test_scenario_ko_green_parziale_riconosce_solo_la_banca_al_fischio():
    from Betfair.mike.tools import replay_registrazioni as R
    righe = [
        {"id": 2, "strategy": "under_green", "role": "under_green", "market_id": "1.35",
         "selection_id": 1222344, "side": "lay", "price": P_BANCA, "size": S_BANCA},
        {"id": 3, "strategy": "ko_green", "role": "ko_green", "market_id": "1.35",
         "selection_id": 1222344, "side": "lay", "price": P_BANCA, "size": 4.10},
    ]
    e = R.e_banca_al_fischio(lambda: righe)
    # coda: dal ref della riga
    assert e(_ordine_flumine(ref="mike-t3")) is True
    assert e(_ordine_flumine(ref="mike-t2")) is False
    # canale: dalla STESSA domanda (la banca pre-partita ha un altro importo)
    assert e(_ordine_flumine(ref="awlq17907", size=4.10)) is True
    assert e(_ordine_flumine(ref="awlq17906", size=S_BANCA)) is False
    assert "ko-green-parziale" in R.SCENARI and "ko-green-parziale" in R.SCENARI_DESCRITTI
