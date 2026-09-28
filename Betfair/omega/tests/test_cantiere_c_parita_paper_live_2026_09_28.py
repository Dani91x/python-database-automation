"""CANTIERE C (28/09/2026) - OMEGA: IL PAPER E' LO SPECCHIO DEL LIVE.

Ordine dell'utente (28/09): "deve essere lo specchio per tutti i bot, gia'
ripetuto infinite volte". Ogni ramo paper che si comporta diversamente dal
live e' un difetto. Qui i quattro difetti noti e il quinto trovato
nell'audit, ciascuno con un test che ERA ROSSO sul codice di prima:

1. R8 - FOK: il paper piazzava senza ``time_in_force`` (canale e coda), il
   live col FOK. Ora stesso comando in entrambe le modalita'.
2. Ripiego paper legacy: il parziale veniva ACCETTATO (automatico e
   manuale), il live FOK lo uccide. Ora ucciso anche in paper.
3. Riserva con risposta persa: in paper la riga orfana veniva confermata coi
   dati della riserva (fill inventato). Ora la stessa decisione del live
   sulla fonte vera del paper (il simulatore): mai un fill che non c'e'.
4. ``read_control`` KO: il giro saltava INTERO (niente riconciliazione, coda,
   settlement, uscite). Ora giro di sola gestione con l'ultimo controllo
   valido, mai aperture.
5. (audit) la chiusura automatica delle proposte (``uscite_protezione=
   'automatico'``) non passava dalla porta degli ordini: aggirava la strada
   unica a interruttore acceso.

I FINTI PARLANO COME IL VERO: i DB e i mercati sono quelli storici della suite
di Omega (``FakeDB``/``FakeQueueDB``/``FintoMotore`` che valida ogni comando
col validatore VERO del runner); le eccezioni di rete sono quelle vere
(``httpx.ReadTimeout``); l'ordine simulato del paper ha la forma normalizzata
da ``omega_market._riga_corrente`` (lo stesso normalizzatore del live).
ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, List

import httpx
import pytest

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_proposte as PR
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB
from Betfair.omega.test_omega_service import (
    NOW,
    FakeDB,
    FakeMarket,
    _control,
    _cs,
    _event,
    _manual_req,
    _open_snapshot,
)
from Betfair.omega.tests.test_porta_ordini_omega_f6_2026_09_24 import (  # noqa: F401
    _mercato,
    motore,
)
from Betfair.safe_strategy import execution as X

GRAZIA = E.RECON_GRACE_S

#: gli interruttori dei canali: il ``.env`` VERO (letto da ``load_dotenv``) li
#: accende dal 26/09; qui ogni test parte SPENTO e chi vuole il canale lo
#: accende apposta (fixture ``motore``), altrimenti il percorso provato non e'
#: quello che il test dichiara.
_INTERRUTTORI = (
    "OMEGA_ORDINI_VIA_CANALE", "ESITI_ORDINI_CANALE", "OMEGA_LEGGE_CANALE",
    "OMEGA_SVEGLIA_CANALE", "OMEGA_CANALE_POSIZIONI", "MOTORE_ORDINI_CANALE",
    "PUNTEGGI_CANALE", "SAFE_ORDINI_VIA_CANALE")


@pytest.fixture(autouse=True)
def _canali_spenti(monkeypatch):
    from Betfair.omega import porta_ordini as PO

    for nome in _INTERRUTTORI:
        monkeypatch.setenv(nome, "0")
    PO.azzera()
    yield
    PO.azzera()


# ===========================================================================
# 1. R8 - lo STESSO ordine in paper e in live (FOK compreso)
# ===========================================================================
_CHIAVI_DI_MODALITA = {"ref", "mode", "creato_ms", "origine"}


def test_canale_paper_e_live_mandano_lo_stesso_comando(motore):  # noqa: F811
    """Sul canale di comando (strada unica) il comando paper e quello live
    differiscono SOLO per la modalita' (e per cio' che ne dipende per
    costruzione: ref, istante, riga d'origine). Prima: FOK solo in live."""
    comandi = {}
    for modo, hb in (("paper", "PAPER"), ("live", "LIVE")):
        motore.visti.clear()
        db = FakeQueueDB(_control(mode=modo), hb_mode=hb)
        S.run_once(market=_mercato(), db=db, now=NOW)
        comandi[modo] = dict(motore.comandi[-1])
    assert comandi["paper"]["mode"] == "paper" and comandi["live"]["mode"] == "live"
    assert comandi["paper"]["time_in_force"] == "FILL_OR_KILL"
    resto = {m: {k: v for k, v in c.items() if k not in _CHIAVI_DI_MODALITA}
             for m, c in comandi.items()}
    assert resto["paper"] == resto["live"]


def test_coda_paper_e_live_stesso_payload():
    """Sulla coda del runner (ripiego a porta spenta): stesso payload, FOK
    compreso; cambia solo ``mode``."""
    payload = {}
    for modo, hb in (("paper", "PAPER"), ("live", "LIVE")):
        db = FakeQueueDB(_control(mode=modo), hb_mode=hb)
        S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
        payload[modo] = dict(db.queue[1]["payload"])
    assert payload["paper"]["time_in_force"] == "FILL_OR_KILL"
    assert {k: v for k, v in payload["paper"].items() if k != "mode"} == \
        {k: v for k, v in payload["live"].items() if k != "mode"}


# ===========================================================================
# 2. ripiego paper legacy: il parziale e' ucciso come dal FOK live
# ===========================================================================
def test_manuale_paper_senza_runner_non_eseguito():
    """CANTIERE C (28/09, D1): il manuale paper senza runner NON riempie piu'
    in casa (prima: fill istantaneo, poi parziale ucciso). Ordine dichiarato
    non eseguito col motivo leggibile, riga terminale come il live rifiutato."""
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "size": 5})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.manual_reqs[0]["result"].get("error") == "paper_runner_non_disponibile"
    t = db.trades[0]
    assert t["status"] == "error" and t["meta"]["reason"] == "paper_runner_non_disponibile"
    assert t["meta"]["motivo_runner"] == "db_senza_coda" and t["meta"]["leg_failed"] is True
    assert not any(k == "paper_fill_fallback" for k, _ in db.activity)


def test_manuale_paper_e_live_mandano_lo_stesso_ordine_al_runner():
    """Col runner: il manuale paper manda al runner lo STESSO ordine del
    manuale live (prezzo, size, FOK); cambia solo la modalita'."""
    payload = {}
    for modo, hb in (("paper", "PAPER"), ("live", "LIVE")):
        db = FakeQueueDB(_control(status="idle", mode=modo), hb_mode=hb)
        db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                      "selection_id": 4, "side": "lay", "mode": modo,
                                      "price": 110, "size": 5})
        S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
        payload[modo] = dict(db.queue[1]["payload"])
    assert payload["paper"]["time_in_force"] == "FILL_OR_KILL"
    assert {k: v for k, v in payload["paper"].items() if k != "mode"} == \
        {k: v for k, v in payload["live"].items() if k != "mode"}


# ===========================================================================
# 3. riserva con risposta persa: mai un fill inventato, paper = live
# ===========================================================================
class _RispostaPersa(FakeDB):
    """La PRIMA riserva arriva sul server (la riga esiste) ma la risposta si
    perde: l'eccezione e' quella vera del client HTTP."""

    perdi = True

    def insert_trade(self, trade):
        tid = super().insert_trade(trade)
        if self.perdi:
            self.perdi = False
            raise httpx.ReadTimeout("The read operation timed out")
        return tid


def _storia_riserva_persa(modo: str) -> List[Any]:
    db = _RispostaPersa(_control(mode=modo))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.current_orders, market.cleared_orders = [], []   # Betfair: nessun ordine
    storia: List[Any] = []

    def _riga1():
        r = next((t for t in db.trades if t["id"] == 1), None)
        return None if r is None else r["status"]

    S.run_once(market=market, db=db, now=NOW)                     # riserva persa
    storia.append(_riga1())
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))   # dentro la grazia
    storia.append(_riga1())
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=GRAZIA + 5))
    storia.append(_riga1())
    assert any(k == "error" and p.get("reason") == "reserve_failed" for k, p in db.activity)
    return storia


def test_riserva_con_risposta_persa_mai_un_fill_inventato_paper_come_live():
    paper = _storia_riserva_persa("paper")
    live = _storia_riserva_persa("live")
    # nessun ordine e' mai partito: la riga resta in attesa per la grazia e poi
    # si libera; MAI 'open' (prima: 'open' in paper al primo giro utile)
    assert paper == ["pending", "pending", None]
    assert paper == live


# ===========================================================================
# 3-bis. la fonte vera del paper legacy ritrova un fill la cui conferma e' fallita
# ===========================================================================
def test_riavvio_perde_la_fonte_paper_e_la_riga_non_diventa_un_fill():
    """Limite DICHIARATO: la fonte dell'ordine paper registrato dal simulatore
    delle chiusure e' memoria di processo. Dopo un riavvio la riga orfana si
    chiude come NON eseguita (grazia, poi liberata): mai inventata."""
    tr_riga = {"id": 7, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
               "side": "back", "mode": "paper", "status": "pending", "price": 8.0,
               "size": 5.0, "closes_trade_id": 3, "placed_at": NOW.isoformat(),
               "meta": {"phase": "reserved", "cashout": True, "closes_trade_id": 3}}
    S.ricorda_chiusura_paper({"id": 3, "mode": "paper", "market_id": "m1", "selection_id": 4},
                             {"ok": True, "closing_trade_id": 7, "side": "back",
                              "price": 8.0, "size": 5.0, "pending_fill": False}, NOW)
    S.svuota_le_cache()                                          # = riavvio
    db = FakeDB(_control())
    db.trades = [tr_riga]
    market = FakeMarket([], None, None)
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert db.trades and db.trades[0]["status"] == "pending"
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=GRAZIA + 5))
    assert db.trades == []


@pytest.mark.parametrize("mercato,selezione", [("m-ALTRO", 4), ("m1", 99)])
def test_ordine_registrato_di_un_altra_riga_non_conferma(mercato, selezione):
    """Stesso id ma mercato o selezione diversi (id riusato dopo un riavvio del
    DB, riga di un'altra partita): l'ordine NON e' di questa riga. La riga
    segue la regola del 'non trovato': grazia, poi liberata. Mai 'open'."""
    S._ricorda_ordine_paper(1, market_id=mercato, selection_id=selezione, side="lay",
                            size=5.0, price=110.0, now=NOW)
    db = FakeDB(_control())
    db.trades = [{"id": 1, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
                  "side": "lay", "mode": "paper", "price": 110, "size": 5,
                  "liability": 545, "status": "pending", "placed_at": NOW.isoformat(),
                  "meta": {"phase": "reserved"}}]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "pending"
    S.reconcile_pending(market=market, db=db, now=NOW + timedelta(seconds=GRAZIA + 5))
    assert db.trades == []


def test_chiusura_paper_registrata_e_ritrovata():
    tr = {"id": 3, "mode": "paper", "market_id": "m1", "selection_id": 4}
    S.ricorda_chiusura_paper(tr, {"ok": True, "closing_trade_id": 7, "side": "back",
                                  "price": 8.0, "size": 5.0, "pending_fill": False}, NOW)
    riga = {"id": 7, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
            "side": "back", "mode": "paper", "status": "pending", "price": 8.0,
            "size": 5.0, "closes_trade_id": 3, "placed_at": NOW.isoformat(),
            "meta": {"phase": "reserved", "cashout": True, "closes_trade_id": 3}}
    db = FakeDB(_control())
    db.trades = [riga]
    S.reconcile_pending(market=FakeMarket([], None, None), db=db, now=NOW)
    assert db.trades[0]["status"] == "open" and db.trades[0]["size"] == 5.0


@pytest.mark.parametrize("res,modo", [
    ({"ok": True, "closing_trade_id": 7, "side": "back", "price": 8.0, "size": 5.0,
      "pending_fill": True}, "paper"),                       # in volo: esito dal poll
    ({"error": "chiusura_non_eseguita", "closing_trade_id": 7}, "paper"),
    ({"ok": True, "closing_trade_id": 7, "side": "back", "price": 8.0, "size": 5.0,
      "pending_fill": False}, "live"),                       # il live ha Betfair
])
def test_chiusura_non_registrata_se_non_eseguita_dal_simulatore(res, modo):
    S.ricorda_chiusura_paper({"id": 3, "mode": modo, "market_id": "m1",
                              "selection_id": 4}, res, NOW)
    assert 7 not in S._ORDINI_PAPER_SIMULATI


def test_le_tre_chiusure_registrano_la_fonte_paper(monkeypatch):
    """Il cash-out manuale chiama la registrazione con l'esito di
    ``close_trade`` (green-up e proposte: stesso punto, vedi codice)."""
    from Betfair.omega.test_omega_cashout_manuale_fallito_2026_09_23 import _MercatoOK
    from Betfair.omega.test_omega_greenup_2026_09_10 import _DB, _trade

    visti: list = []
    monkeypatch.setattr(S, "ricorda_chiusura_paper",
                        lambda tr, res, now: visti.append((tr.get("id"), dict(res))))
    db = _DB({"status": "idle", "params": {}})
    tr = _trade(db, price=55.0, size=5.0)
    out = S._manual_cashout(market=_MercatoOK([], None, None), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)
    assert out.get("ok") is True, out
    assert visti and visti[0][0] == tr["id"] and visti[0][1].get("closing_trade_id")


# ===========================================================================
# 3-ter. (coordinatore, D3) mercato sparito da 48 h: risultato vero, mai 0 inventato
# ===========================================================================
def _orfano(modo: str, **meta):
    gone = (NOW - timedelta(hours=S.ORPHAN_GONE_MAX_H + 1)).isoformat()
    return {"id": 1, "event_id": "1.100", "market_id": "m-x", "selection_id": 4,
            "runner_name": "3 - 2", "side": "lay", "mode": modo, "price": 110.0,
            "size": 10.0, "liability": 1090.0, "commission": 0.05, "status": "open",
            "phase": "ft_cs", "placed_at": NOW.isoformat(),
            "meta": {"market_gone_since": gone,
                     "runners": {"1": "0 - 0", "4": "3 - 2"}, **meta}}


@pytest.mark.parametrize("risultato,stato,pnl", [("1-0", "won", 9.5), ("3-2", "lost", -1090.0)])
def test_orfano_paper_regolato_col_risultato_vero(risultato, stato, pnl):
    db = FakeDB(_control())
    db.trades = [_orfano("paper", result_ft=risultato)]
    n = S.settle_open(params=S.omega_config.resolve_params({}),
                      market=FakeMarket([_event()], _cs(), None), db=db, now=NOW)
    t = db.trades[0]
    assert n == 1 and t["status"] == stato and t["pnl"] == pytest.approx(pnl)
    assert any(k == "settle_orphan" and p.get("risultato") == risultato
               for k, p in db.activity)


@pytest.mark.parametrize("modo,meta", [("paper", {}),                  # risultato assente
                                        ("live", {"result_ft": "1-0"})])  # live: mai dedotto
def test_orfano_senza_risultato_o_live_resta_aperto_con_allarme(modo, meta):
    db = FakeDB(_control(mode=modo))
    db.trades = [_orfano(modo, **meta)]
    S.settle_open(params=S.omega_config.resolve_params({}),
                  market=FakeMarket([_event()], _cs(), None), db=db, now=NOW)
    assert db.trades[0]["status"] == "open"
    assert any(k == "orphan_live_alert" for k, _ in db.activity)
    assert not any(k == "settle_orphan" for k, _ in db.activity)


@pytest.mark.parametrize("nome,risultato,atteso", [
    ("2 - 1", "2-1", True), ("2 - 1", "1-2", False),
    ("Any Other Home Win", "4-0", True), ("Any Other Home Win", "1-0", False),
    ("Any Other Home Win", "0-4", False), ("Any Other Away Win", "0-4", True),
    ("Any Other Draw", "4-4", True), ("Any Unquoted", "4-3", True),
    ("Any Unquoted", "1-0", False), ("Boh", "1-0", None), ("2 - 1", None, None),
])
def test_vince_col_risultato(nome, risultato, atteso):
    runners = {"1": "0 - 0", "2": "1 - 0", "3": "2 - 1", "5": "1 - 2"}
    assert E.vince_col_risultato(nome, risultato, runners) is atteso


# ===========================================================================
# 4. read_control KO: si gestisce l'esistente, mai si apre
# ===========================================================================
class _ControlloKO(FakeDB):
    guasti = 0            # quante letture consecutive falliscono (-1 = sempre)

    def read_control(self):
        if self.guasti:
            self.guasti -= 1 if self.guasti > 0 else 0
            raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
        return self.control


@pytest.fixture
def spie(monkeypatch):
    chiamate: dict = {k: 0 for k in ("reconcile", "poll", "settle", "greenup", "proposte",
                                      "manual", "scan", "missioni")}

    def _spia(nome, ritorno=0):
        def f(**_kw):
            chiamate[nome] += 1
            return ritorno
        return f

    monkeypatch.setattr(S, "reconcile_pending", _spia("reconcile"))
    monkeypatch.setattr(S, "poll_flumine_pending", _spia("poll"))
    monkeypatch.setattr(S, "settle_open", _spia("settle"))
    monkeypatch.setattr(S, "process_auto_greenup", _spia("greenup"))
    monkeypatch.setattr(PR, "process_proposte_uscita", _spia("proposte"))
    monkeypatch.setattr(S, "process_manual", _spia("manual"))
    monkeypatch.setattr(S, "scan_and_place", _spia("scan"))
    monkeypatch.setattr(S, "scan_and_place_legs", _spia("scan"))
    monkeypatch.setattr(S, "process_missions", _spia("missioni"))
    monkeypatch.setattr(S, "_PAUSE_LETTURA_CONTROLLO_S", (0.0, 0.0))
    return chiamate


def test_read_control_ko_giro_di_sola_gestione_con_l_ultimo_controllo(spie):
    db = _ControlloKO(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)                  # giro buono: controllo in memoria
    assert spie["scan"] == 1
    prima = dict(spie)
    db.guasti = -1                                             # rete giu'
    res = S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))
    assert res["skipped"] == "read_control_failed" and res["degradato"] is True
    assert res["controllo"] == "ultimo_valido" and res["controllo_eta_s"] == 20.0
    # la gestione gira
    for fase in ("reconcile", "poll", "settle"):
        assert spie[fase] == prima[fase] + 1, fase
    assert spie["greenup"] + spie["proposte"] == prima["greenup"] + prima["proposte"] + 1
    # nessuna apertura, nessuna richiesta manuale, nessuna missione
    assert (spie["scan"], spie["manual"], spie["missioni"]) == \
        (prima["scan"], prima["manual"], prima["missioni"])
    assert any(k == "error" and p.get("reason") == "read_control_failed"
               for k, p in db.activity)


def test_read_control_ko_senza_controllo_valido_solo_riconciliazione(spie):
    db = _ControlloKO(_control())
    db.guasti = -1
    res = S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
    assert res["skipped"] == "read_control_failed" and res["controllo"] == "assente"
    assert spie["reconcile"] == 1
    assert spie["settle"] == spie["poll"] == spie["scan"] == spie["manual"] == 0


def test_read_control_ko_una_volta_si_ritenta_e_il_giro_e_normale(spie):
    db = _ControlloKO(_control())
    db.guasti = 1
    res = S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
    assert "skipped" not in res
    assert spie["scan"] == 1 and spie["reconcile"] == 1


def test_controllo_troppo_vecchio_solo_riconciliazione(spie):
    """Coordinatore (28/09): oltre ``_ULTIMO_CONTROLLO_MAX_ETA_S`` l'ultimo
    controllo non guida piu' la gestione (l'utente puo' aver fermato il bot o
    cambiato le uscite): sola riconciliazione."""
    db = _ControlloKO(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    prima = dict(spie)
    db.guasti = -1
    dentro = NOW + timedelta(seconds=S._ULTIMO_CONTROLLO_MAX_ETA_S - 1)
    res = S.run_once(market=market, db=db, now=dentro)
    assert res["controllo"] == "ultimo_valido" and spie["settle"] == prima["settle"] + 1
    fuori = NOW + timedelta(seconds=S._ULTIMO_CONTROLLO_MAX_ETA_S + 1)
    res = S.run_once(market=market, db=db, now=fuori)
    assert res["controllo"] == "scaduto"
    assert spie["reconcile"] == prima["reconcile"] + 2
    assert spie["settle"] == prima["settle"] + 1              # nessuna gestione nuova
    assert spie["greenup"] + spie["proposte"] == prima["greenup"] + prima["proposte"] + 1


def test_bot_fermato_durante_il_buco_non_riparte_con_il_controllo_vecchio(spie):
    """Il controllo vecchio NON autorizza aperture: anche se diceva 'running'."""
    db = _ControlloKO(_control(status="running"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    db.guasti = -1
    for i in range(1, 4):
        S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20 * i))
    assert spie["scan"] == 1


# ===========================================================================
# 4-bis. (audit) la missione non si chiude con un ordine paper ancora in volo
# ===========================================================================
@pytest.mark.parametrize("modo", ["paper", "live"])
def test_missione_non_si_chiude_con_un_pending_senza_bet_id(modo):
    """Un 'pending' senza bet_id (ordine in volo sul canale/coda o riga in
    riconciliazione) tiene aperta la missione in live (review 15/07): ora
    anche in paper. Prima in paper la missione si chiudeva e riapriva
    l'evento all'automatico con l'ordine simulato ancora in corso."""
    from Betfair.omega.test_omega_missions import _mission, _Snap

    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="2t")]
    db.trades.append({"id": 11, "event_id": "1.100", "phase": "ft_cs",
                      "status": "pending", "mode": modo, "bet_id": None,
                      "pnl": 0, "liability": 100, "selection_id": 4, "price": 110,
                      "size": 1, "side": "lay",
                      "meta": {"phase": "flumine_wait", "flumine_client_ref": "omega-t11"}})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=95, home=1, away=0, status="Finished")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["status"] == "active"


# ===========================================================================
# 4-ter. (audit) richiesta paper mai presa in carico: revocata come in live
# ===========================================================================
def _richiesta_mai_presa(modo: str):
    hb = "PAPER" if modo == "paper" else "LIVE"
    db = FakeQueueDB(_control(mode=modo), hb_mode=hb)
    S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
    t = db.trades[0]
    assert db.queue[t["meta"]["flumine_request_id"]]["status"] == "pending"
    return db, t


@pytest.mark.parametrize("modo", ["paper", "live"])
def test_richiesta_mai_presa_in_carico_revocata_alla_scadenza(modo):
    db, t = _richiesta_mai_presa(modo)
    oltre = NOW + timedelta(seconds=3600)                    # oltre ogni scadenza
    S.poll_flumine_pending(db=db, params=S.omega_config.resolve_params({}), now=oltre,
                           market=FakeMarket([_event()], _cs(), _open_snapshot()))
    riga = db.trades[0]
    assert riga["status"] == "error"
    assert db.queue[t["meta"]["flumine_request_id"]]["status"] == "error", \
        "richiesta non revocata: un runner tornato vivo eseguirebbe un ordine stantio"


def test_revoca_paper_persa_la_riga_resta_in_attesa():
    db, t = _richiesta_mai_presa("paper")
    db.revoke_live_order_request = lambda rid: False         # il worker l'ha appena presa
    S.poll_flumine_pending(db=db, params=S.omega_config.resolve_params({}),
                           now=NOW + timedelta(seconds=3600),
                           market=FakeMarket([_event()], _cs(), _open_snapshot()))
    assert db.trades[0]["status"] == "pending"


# ===========================================================================
# 5. la chiusura automatica delle proposte passa dalla porta degli ordini
# ===========================================================================
def test_uscita_automatica_passa_dalla_porta_come_le_altre_chiusure(monkeypatch):
    from Betfair.omega.tests.test_omega_uscite_protezione_2026_09_24 import (
        _db, _gira, _params, _trade)

    SENTINELLA = object()
    porte_chieste: list = []
    visti: list = []

    def _porta(params, mode):
        porte_chieste.append(mode)
        return {"porta": SENTINELLA}

    def _close(**kw):
        visti.append(kw)
        return {"error": "chiusura_non_eseguita", "detail": "finto", "closing_trade_id": 9}

    monkeypatch.setattr(S, "_porta_kw_chiusura", _porta)
    monkeypatch.setattr(X, "close_trade", _close)
    db = _db()
    _trade(db)
    _gira(db, _params(uscite_protezione="automatico"))
    assert len(visti) == 1
    assert visti[0].get("porta") is SENTINELLA
    assert porte_chieste == ["paper"]                          # la modalita' della riga


# ===========================================================================
# 6. (coordinatore, D4) paper e live non si sommano MAI nelle decisioni
# ===========================================================================
def _perdita_di_oggi(modo: str) -> dict:
    return {"id": 90, "event_id": "9.999", "market_id": "m-9", "selection_id": 1,
            "side": "lay", "mode": modo, "origin": "auto", "price": 50.0, "size": 1.0,
            "liability": 49.0, "status": "lost", "pnl": -50.0,
            "placed_at": (NOW - timedelta(hours=1)).isoformat(),
            "settled_at": (NOW - timedelta(minutes=10)).isoformat(), "meta": {}}


@pytest.mark.parametrize("perdita,opera,apre", [
    ("paper", "live", True),      # una perdita in paper non ferma il live
    ("live", "paper", True),      # una perdita in live non ferma il paper
    ("paper", "paper", False),    # nella stessa modalita' il tetto scatta
    ("live", "live", False),
])
def test_perdita_di_una_modalita_non_ferma_l_altra(perdita, opera, apre):
    from Betfair.omega.tests.runner_paper_finto import attiva_runner_paper, gira

    db = attiva_runner_paper(FakeDB(_control(mode=opera, params={"daily_loss_cap": 10})))
    db.trades = [_perdita_di_oggi(perdita)]
    db._id = 90
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = gira(market=market, db=db, now=NOW)
    assert (res["placed"] == 1) is apre, (res, db.activity[-3:])
    assert any(k == "loss_stop" for k, _ in db.activity) is (not apre)


class _ClienteFinto:
    """Il client supabase come lo usa ``omega_db``: ``rpc(...).execute()`` e
    ``table(...).select(...).order(...).range(...).execute().data``."""

    def __init__(self, righe, rpc=None):
        self.righe, self._rpc, self.chiamate = righe, rpc, []

    def rpc(self, nome, parametri):
        self.chiamate.append((nome, dict(parametri)))
        cliente = self

        class _R:
            def execute(self_inner):
                if cliente._rpc is None:
                    from postgrest.exceptions import APIError
                    raise APIError({"code": "PGRST202", "message": "Could not find the function"})
                return type("Res", (), {"data": cliente._rpc})()
        return _R()

    def table(self, _nome):
        cliente = self

        class _T:
            def select(self_i, *_a):
                return self_i

            def order(self_i, *_a, **_k):
                return self_i

            def range(self_i, a, b):
                self_i.pezzo = cliente.righe[a:b + 1]
                return self_i

            def execute(self_i):
                return type("Res", (), {"data": self_i.pezzo})()
        return _T()


def test_db_aggregati_per_modalita_senza_migrazione_in_casa(monkeypatch):
    """PRIMA della migrazione (RPC assente): gli aggregati per modalita' si
    calcolano in casa dalle righe filtrate, e lo si dichiara nel log."""
    from Betfair.omega import omega_db as DB

    righe = [_perdita_di_oggi("paper"), {**_perdita_di_oggi("live"), "id": 91, "pnl": -7.0}]
    cliente = _ClienteFinto(righe)
    monkeypatch.setattr(DB, "_sb", lambda: cliente)
    monkeypatch.setitem(DB._AVVISO_MIGRAZIONE_MODALITA, "dato", False)
    ds = E.day_start_utc(NOW)
    pagina_p, bot_p = DB.aggregates_coppia(ds, mode="paper")
    pagina_l, bot_l = DB.aggregates_coppia(ds, mode="live")
    assert pagina_p["realized_today"] == -50.0 and bot_p["realized_today"] == -50.0
    assert pagina_l["realized_today"] == -7.0 and bot_l["realized_today"] == -7.0
    assert ("get_omega_aggregates_modalita", {"p_mode": "paper"}) in cliente.chiamate
    assert DB._AVVISO_MIGRAZIONE_MODALITA["dato"] is True


def test_db_aggregati_per_modalita_con_la_migrazione(monkeypatch):
    """DOPO la migrazione: la RPC per modalita' e' la fonte; nessuna lettura
    delle righe. Una modalita' senza righe (oggetti vuoti) vale zero."""
    from Betfair.omega import omega_db as DB

    cliente = _ClienteFinto([], rpc={"realized_today": -3.5, "matches_traded_today": 2,
                                     "mode": "live", "auto": {"realized_today": -1.0,
                                                              "mode": "live"}})
    monkeypatch.setattr(DB, "_sb", lambda: cliente)
    pagina, bot = DB.aggregates_coppia(E.day_start_utc(NOW), mode="live")
    assert pagina["realized_today"] == -3.5 and bot["realized_today"] == -1.0
    assert "mode" not in pagina
    vuoto = _ClienteFinto([], rpc={"auto": {}})
    monkeypatch.setattr(DB, "_sb", lambda: vuoto)
    pagina, bot = DB.aggregates_coppia(E.day_start_utc(NOW), mode="paper")
    assert pagina["realized_today"] == 0.0 and bot["realized_today"] == 0.0
