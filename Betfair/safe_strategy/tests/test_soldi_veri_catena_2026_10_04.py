"""04/10/2026 - SOLDI VERI COERENTI: il bot in live con una catena che non serve il live.

Incidente del 04/10: Safe tennis acceso in «soldi veri», runner tennis in PAPER.
Ogni apertura respinta dal motore del runner (``mode_non_servibile: mode 'live'
non servibile dal runner in PAPER``): 15 tentativi su 5 partite, ``place_retry``
e ``place_exhausted`` a raffica, ``stats.motivo_blocco`` = null. La pagina diceva
«acceso in soldi veri» e taceva.

Regola (ordine dell'utente «ogni cosa deve essere coerente per il trader»): un
rifiuto di CATENA (runner senza il live, «Ordini reali» sotto LIVE, freno) NON
e' un esito di mercato:
  * nessun tentativo consumato (i segnali restano quelli della strategia);
  * il blocco si DICHIARA su ``stats.motivo_blocco`` con parole da trader;
  * UN CRITICAL per episodio (non uno per tentativo);
  * nessun comando a vuoto: una sola apertura-sonda ogni ``CATENA_PROVA_S``;
  * la prima apertura accettata chiude l'episodio.

I rifiuti arrivano col TESTO VERO del motore (``motore_ordini.Rifiuto`` con i
codici veri) attraverso la ``PortaCanale`` VERA e il finto motore che valida
ogni comando con ``motore_ordini.valida_comando`` (test F5).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as PO
from Betfair.safe_strategy.tests.test_porta_ordini_f5_2026_09_24 import (
    NOW, TOKEN, FakeDB, FakeMarket, FintoMotore, _attendi, _place, _riserva,
)
from Betfair.stream import motore_ordini as MO

#: il motivo ESATTO che l'ack del motore porta (``str(Rifiuto)``, motore_ordini:1076)
MOTIVO_RUNNER_PAPER = str(MO.Rifiuto(MO.M_MODE, "mode 'live' non servibile dal runner in PAPER"))
#: blocco del modo EFFETTIVO (calcio: «Ordini reali» su PAPER, live_order_worker:204)
MOTIVO_MODO_EFFETTIVO = str(MO.Rifiuto(
    MO.M_MODE, "modo ordini PAPER (scelta dalla Control Room): apertura 'live' RIFIUTATA "
               "- si cambia da Control Room, Ordini reali"))
MOTIVO_FRENO = str(MO.Rifiuto(MO.M_KILL, "kill-switch ATTIVO: solo chiusure permesse"))


@pytest.fixture(autouse=True)
def _pulito():
    S._CATENA.clear()
    S._PLACE_ATTEMPTS.clear()
    S._SKIP_LOG_STATE.clear()
    X._EPISODI_CATENA.clear()
    yield
    S._CATENA.clear()
    S._PLACE_ATTEMPTS.clear()
    S._SKIP_LOG_STATE.clear()
    X._EPISODI_CATENA.clear()


@pytest.fixture
def porta_tennis(monkeypatch):
    monkeypatch.setattr(PO, "MAX_ETA_MS", 400)
    motore = FintoMotore(attore="safe_tennis", comportamento="rifiuta",
                         motivo=MOTIVO_RUNNER_PAPER)
    porta = PO.PortaCanale(porta_ws=47332, attore="safe_tennis", connetti=motore.connetti,
                           token_fn=lambda: TOKEN)
    porta.avvia()
    assert _attendi(porta.disponibile)
    yield porta, motore
    porta.ferma()


def _rifiuti(db):
    return [p for k, p in db.activity if k == "canale_rifiutato"]


# ---------------------------------------------------------------------------
# 1. classificazione: che cosa e' un rifiuto di CATENA (e che cosa no)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nota,catena", [
    (f"canale_rifiutato:{MOTIVO_RUNNER_PAPER}", True),
    (f"canale_rifiutato:{MOTIVO_MODO_EFFETTIVO}", True),
    (f"canale_rifiutato:{MOTIVO_FRENO}", True),
    ("live_order_mode_non_live:PAPER", True),          # execution._live_brake
    ("live_kill_switch_attivo", True),                 # controls.motivo_kill_switch
    ("db_kill_switch_attivo", True),
    ("freni_live_non_letti", True),
    # esiti di mercato o del comando: CONTINUANO a consumare il budget
    (f"canale_rifiutato:{MO.M_ETA}: eta' 5000 ms > max_eta_ms 3000", False),
    (f"canale_rifiutato:{MO.M_PARAM}: price", False),
    ("canale_rifiutato:SOTTO_MINIMO_NON_PIAZZABILE: 0.30", False),
    ("paper_senza_runner:gate", False),                # ha la sua regola (cantiere P)
    ("INSUFFICIENT_FUNDS", False),
    ("", False), (None, False),
])
def test_classificazione_rifiuti_di_catena(nota, catena):
    assert X.blocco_di_catena(nota) is catena


# ---------------------------------------------------------------------------
# 2. canale: CRITICAL una volta per episodio, l'episodio finisce all'accettazione
# ---------------------------------------------------------------------------
def test_mode_non_servibile_critical_una_volta_per_episodio(porta_tennis):
    porta, motore = porta_tennis
    db, market = FakeDB(), FakeMarket()
    for _ in range(3):
        out = _place(db, market, porta, _riserva(db, mode="live", sport="tennis"))
        assert out.status == "error"
        assert out.fill_note == f"canale_rifiutato:{MOTIVO_RUNNER_PAPER}"
    r = _rifiuti(db)
    assert [p["critical"] for p in r] == [True, False, False]
    assert [p["tentativo_nell_episodio"] for p in r] == [1, 2, 3]
    # la catena torna: un'apertura ACCETTATA chiude l'episodio
    motore.comportamento = "accetta"
    out = _place(db, market, porta, _riserva(db, mode="live", sport="tennis"))
    assert out.status == "pending"
    motore.comportamento = "rifiuta"
    _place(db, market, porta, _riserva(db, mode="live", sport="tennis"))
    assert _rifiuti(db)[-1]["critical"] is True, "episodio nuovo: di nuovo CRITICAL"


def test_paper_rifiutata_dal_freno_mai_critical(porta_tennis):
    porta, motore = porta_tennis
    motore.motivo = MOTIVO_FRENO
    db, market = FakeDB(), FakeMarket()
    _place(db, market, porta, _riserva(db, mode="paper", sport="tennis"))
    assert _rifiuti(db)[-1]["critical"] is False


# ---------------------------------------------------------------------------
# 3. il servizio: niente tentativi consumati, blocco dichiarato, sonda unica
# ---------------------------------------------------------------------------
def _riga(db, mode="live", sport="tennis", key="ev1:tennis:back"):
    tid = db.insert_trade({"event_id": "35795993", "sport": sport, "market_id": "1.250",
                           "selection_id": 101, "side": "back", "mode": mode,
                           "price": 1.05, "size": 2.0, "status": "pending",
                           "strategy": "tennis" if sport == "tennis" else "base",
                           "origin": "auto", "signal_key": key,
                           "meta": {"phase": "reserved"}})
    return tid, db.get_trade(tid)


def test_rifiuto_di_catena_non_brucia_i_tentativi_e_dichiara_il_blocco():
    db = FakeDB()
    params = {"place_max_attempts": 3}
    err = f"canale_rifiutato:{MOTIVO_RUNNER_PAPER}"
    for i in range(5):
        tid, row = _riga(db)
        S._place_fail(db, tid, row, err, NOW + timedelta(seconds=i), params)
        assert db.get_trade(tid)["status"] == "error"
        assert db.get_trade(tid)["meta"]["place"]["blocco_catena"] is True
    st = S._PLACE_ATTEMPTS[S._place_key("35795993", "ev1:tennis:back")]
    assert st["attempts"] == 0 and st["final"] is False
    kinds = [k for k, _ in db.activity]
    assert "place_exhausted" not in kinds and "place_retry" not in kinds
    # il blocco si dice in pagina, con parole da trader
    motivo = S._motivo_catena()
    assert motivo is not None
    assert "tennis live" in motivo and "runner tennis gira solo in PAPER" in motivo
    assert "chiusure non si fermano" in motivo
    # UNA riga 'skip' che apre il blocco (non una per tentativo)
    aperture = [p for k, p in db.activity if k == "skip" and p.get("reason") == "blocco_di_catena"]
    assert len(aperture) == 1


def test_esito_di_mercato_consuma_ancora_il_budget():
    """Parita' col prima: un esito di mercato (FOK ucciso) brucia ancora."""
    db = FakeDB()
    for i in range(3):
        tid, row = _riga(db)
        S._place_fail(db, tid, row, "canale_rifiutato:comando_scaduto: eta'",
                      NOW + timedelta(seconds=i), {"place_max_attempts": 3})
    st = S._PLACE_ATTEMPTS[S._place_key("35795993", "ev1:tennis:back")]
    assert st["attempts"] == 3 and st["final"] is True
    assert S._CATENA == {}


def test_sonda_unica_ogni_attesa_e_niente_raffica():
    db = FakeDB()
    tid, row = _riga(db)
    t0 = NOW.timestamp()
    S._place_fail(db, tid, row, "live_order_mode_non_live:PAPER", NOW, {})
    # durante l'attesa: bloccata (nessuna riserva, nessun comando)
    assert S._catena_bloccata("tennis", "live", t0 + 1) is not None
    assert S._catena_bloccata("tennis", "live", t0 + X.CATENA_PROVA_S - 1) is not None
    # scaduta l'attesa passa UNA sola apertura, poi di nuovo ferma
    assert S._catena_bloccata("tennis", "live", t0 + X.CATENA_PROVA_S) is None
    assert S._catena_bloccata("tennis", "live", t0 + X.CATENA_PROVA_S + 1) is not None
    # le altre modalita' e l'altro sport non sono toccati (bot indipendenti)
    assert S._catena_bloccata("tennis", "paper", t0 + 1) is None
    assert S._catena_bloccata("calcio", "live", t0 + 1) is None


def test_motivo_blocco_pubblicato_a_ogni_giro_anche_senza_segnali():
    db = FakeDB()
    tid, row = _riga(db)
    S._place_fail(db, tid, row, f"canale_rifiutato:{MOTIVO_MODO_EFFETTIVO}", NOW, {})
    assert S.scan_and_place(db=db, market=None, engine=None, rows=[], params={},
                            mode="live", now=NOW) == (0, 0)
    assert "Ordini reali" in str(S._BLOCCO["motivo"])


def test_apertura_partita_chiude_il_blocco(monkeypatch):
    db = FakeDB()
    tid, row = _riga(db)
    S._place_fail(db, tid, row, "live_kill_switch_attivo", NOW, {})
    assert S._motivo_catena() is not None
    # 04/10 (revisione del coordinatore): un 'pending' QUALUNQUE (es. ack
    # in_aggancio) NON e' una prova; lo e' l'ack senza motivo (catena_servita)
    monkeypatch.setattr(X, "place", lambda **kw: X.PlaceOutcome(
        "pending", 1.05, 2.0, None, "canale_live:safe_tennis-t1", size_requested=2.0))
    tid2, row2 = _riga(db, key="ev1:tennis:back2")
    out = S._execute(db=db, market=FakeMarket(), trade_id=tid2, row=row2, params={},
                     now=NOW, best_size=10.0, ladder=())
    assert out.status == "pending"
    assert S._motivo_catena() is not None, "un pending qualunque non ripristina"
    monkeypatch.setattr(X, "place", lambda **kw: X.PlaceOutcome(
        "pending", 1.05, 2.0, None, "canale_live:safe_tennis-t2", size_requested=2.0,
        catena_servita=True))
    tid3, row3 = _riga(db, key="ev1:tennis:back3")
    S._execute(db=db, market=FakeMarket(), trade_id=tid3, row=row3, params={},
               now=NOW, best_size=10.0, ladder=())
    assert S._motivo_catena() is None
    assert S._catena_bloccata("tennis", "live", NOW.timestamp() + 1) is None


@pytest.mark.parametrize("tennis,attesa", [("1", "runner_tennis"), ("0", "diretta"),
                                           (None, "diretta")])
def test_il_servizio_dichiara_la_strada_degli_ordini(monkeypatch, tennis, attesa):
    """04/10 (B): la strada la DICHIARA il servizio in ``stats.strade_ordini``
    (la UI non la deduce). Interruttore ``SAFE_TENNIS_ORDINI_VIA_CANALE``: 1 =
    runner tennis (canale 47332), 0/assente = strada diretta («Ordini reali»)."""
    from Betfair.safe_strategy.tests.test_bot_service import FakeDB as DbServizio
    from Betfair.safe_strategy.tests.test_bot_service import FakeMarket as MercatoServizio
    from Betfair.safe_strategy.tests.test_bot_service import _reset_module_state

    monkeypatch.setenv("SAFE_ORDINI_VIA_CANALE", "1")
    if tennis is None:
        monkeypatch.setenv("SAFE_TENNIS_ORDINI_VIA_CANALE", "")
    else:
        monkeypatch.setenv("SAFE_TENNIS_ORDINI_VIA_CANALE", tennis)
    assert S.strade_ordini() == {"calcio": "runner_calcio", "tennis": attesa}
    # e arriva davvero nella riga di controllo (stats del giro)
    monkeypatch.setattr(PO, "porta_per_sport", lambda *a, **k: None)
    _reset_module_state()
    db = DbServizio(status="stopped")
    S.run_once(db=db, market=MercatoServizio(), now=NOW)
    assert db.control["stats"]["strade_ordini"] == {"calcio": "runner_calcio", "tennis": attesa}


@pytest.mark.parametrize("sport", ["tennis", "calcio"])
def test_strada_diretta_catena_armata_parte_un_ordine_vero(monkeypatch, sport):
    """04/10 (matrice, «soldi veri scelto + catena armata -> parte un ordine VERO»):
    Safe sulla strada DIRETTA (interruttore del canale a 0, come i live del 14-22/09
    e da oggi per il tennis): tetto LIVE + «Ordini reali» LIVE (conftest, dichiarati)
    -> ``market.place_order_live`` (REST di Betfair) chiamato con la riga live.
    Con «Ordini reali» su PAPER, nessuna chiamata e blocco di catena dichiarato."""
    from Betfair.stream import modo_ordini as MOD

    monkeypatch.setenv("SAFE_ORDINI_VIA_CANALE", "0")
    monkeypatch.setenv("SAFE_TENNIS_ORDINI_VIA_CANALE", "0")
    db, market = FakeDB(), FakeMarket()
    tid, row = _riga(db, key="ev1:%s:back" % sport, sport=sport)
    out = S._execute(db=db, market=market, trade_id=tid, row=row,
                     params={"execution_mode": "rest"},
                     now=NOW, best_size=10.0, ladder=())
    assert len(market.placed) == 1, (out, market.placed)
    assert out.status == "open" and S._motivo_catena() is None
    db2, market2 = FakeDB(), FakeMarket()
    with MOD.dichiara_per_banco("PAPER"):
        tid2, row2 = _riga(db2, key="ev2:%s:back" % sport, sport=sport)
        out2 = S._execute(db=db2, market=market2, trade_id=tid2, row=row2,
                          params={"execution_mode": "rest"},
                          now=NOW, best_size=10.0, ladder=())
    assert market2.placed == [] and out2.fill_note.startswith("live_order_mode_non_live")
    assert "Ordini reali" in str(S._motivo_catena())


@pytest.mark.parametrize("nota,parola", [
    (f"canale_rifiutato:{MOTIVO_RUNNER_PAPER}", "abilita il runner tennis ai soldi veri"),
    (f"canale_rifiutato:{MOTIVO_MODO_EFFETTIVO}", "«Ordini reali» a LIVE"),
    (f"canale_rifiutato:{MOTIVO_FRENO}", "rilasciando il freno"),
    ("live_order_mode_non_live:PAPER", "«Ordini reali» a LIVE"),
])
def test_testo_dice_che_cosa_manca_e_come_si_risolve(nota, parola):
    t = X.testo_blocco_catena(nota, sport="tennis", mode="live")
    assert parola in t and t.startswith("aperture in soldi veri FERME")
