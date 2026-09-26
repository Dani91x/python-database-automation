"""R-F2-12 (26/09) - un rifiuto del FRENO non e' un tentativo della gamba.

Reperto E2E fase 2 (sessione B): a freno tirato Omega scriveva
``skip kill_switch attempt 1..3 di max 3`` sulla stessa gamba (evento 36090944):
ogni giro il freno chiudeva la riserva con ``_leg_certain_failure``, che consumava
il budget ``LEG_RETRY_MAX`` come se Betfair avesse ucciso un FOK. Rilasciato il
freno, quella gamba non si riprovava piu' per tutta la partita.

Il freno non e' un esito di mercato: nessun ordine e' partito. La riserva si
chiude lo stesso (nessuna posizione nuda, nessuna riga pending a far credere
che un ordine sia vivo), ma il budget dei tentativi resta intatto, in memoria
E sul DB (``omega_db.failed_legs`` salta le righe marcate
``tentativo_consumato=False``).

Il freno e' quello VERO (``controls.motivo_kill_switch``) pilotato dalle stesse
due sorgenti del test O1: env ``LIVE_KILL_SWITCH`` e ``get_live_settings`` con
la chiave vera ``kill_switch`` (bool). Nessun finto del freno.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.omega import omega_db as DB
from Betfair.omega import omega_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.stream import motore_ordini as MO
from Betfair.omega.test_omega_service import (
    NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot,
)
from Betfair.stream.trading import controls as CTL


@pytest.fixture
def freno(monkeypatch):
    """Freno tirato (True) o rilasciato (False), sorgente DB come in produzione."""
    # il .env del PC (letto dai test) accende il canale ordini di Omega: qui si
    # collaudano i rami REST/paper, quindi l'interruttore si spegne apposta
    monkeypatch.setenv("OMEGA_ORDINI_VIA_CANALE", "false")

    def _imposta(tirato: bool):
        monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
        monkeypatch.setattr(CTL, "get_live_settings",
                            lambda *a, **k: {"kill_switch": bool(tirato)})
    return _imposta


def _giro(db, market, i):
    # giri distanziati oltre LEG_RETRY_MIN_S: il budget e' l'unico limite
    return S.run_once(market=market, db=db, now=NOW + timedelta(seconds=(S.LEG_RETRY_MIN_S + 1) * i))


@pytest.mark.parametrize("modo", ["paper", "live"])
def test_freno_ripetuto_non_brucia_la_gamba(freno, modo):
    db = FakeDB(_control(mode=modo))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    freno(True)
    for i in range(S.LEG_RETRY_MAX + 1):
        assert _giro(db, market, i)["placed"] == 0
    rifiuti = [p for k, p in db.activity if k == "skip" and p.get("reason") == "kill_switch"]
    assert len(rifiuti) >= S.LEG_RETRY_MAX, "il freno ha davvero fermato ogni giro"
    # nessun tentativo consumato: nessuna chiave di tentativo nel log del freno
    assert all(p.get("tentativo_consumato") is False for p in rifiuti)
    assert all("attempt" not in p for p in rifiuti)
    assert all(S._leg_attempts("1.100", ph)[0] == 0 for ph in ("ht_cs", "ft_cs", ""))
    # freno rilasciato: la gamba si apre al giro dopo
    freno(False)
    res = _giro(db, market, S.LEG_RETRY_MAX + 2)
    assert res["placed"] == 1, "rilasciato il freno la gamba deve essere ancora tentabile"


@pytest.mark.parametrize("motivo,consuma", [
    (MO.M_KILL, False),                     # ack del runner: freno tirato
    (MO.M_AGGANCIO, False),                 # runner senza il mercato: mai al mercato
    (f"{MO.M_IN_AGGANCIO}: mercato 1.2 non sottoscritto", False),
    (MO.M_ETA, True),                       # comando scaduto: esito certo, conta
    (MO.M_PARAM, True),                     # parametri invalidi: conta (niente loop)
])
def test_canale_rifiuto_del_freno_non_consuma(monkeypatch, freno, motivo, consuma):
    """Canale ordini ACCESO (produzione dal 26/09): il runner rifiuta l'apertura
    con l'ack ``motivo`` (costanti vere di ``motore_ordini``). L'esito arriva al
    bot come il ``PlaceOutcome`` VERO di ``execution._place_via_canale`` per un
    ack rifiutato (stessi campi: fill_note ``canale_rifiutato:<motivo>``,
    error_code = motivo)."""
    freno(False)
    monkeypatch.setattr(S, "_porta_per", lambda params, mode: object())
    monkeypatch.setattr(S, "_place_via_canale", lambda porta, **kw: X.PlaceOutcome(
        "error", None, 0.0, None, f"canale_rifiutato:{motivo}",
        size_requested=kw.get("size"), size_remaining=0.0, error_code=motivo))
    db = FakeDB(_control(mode="paper"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    for i in range(S.LEG_RETRY_MAX + 1):
        assert _giro(db, market, i)["placed"] == 0
    n = max(S._leg_attempts("1.100", ph)[0] for ph in ("ht_cs", "ft_cs", ""))
    if consuma:
        assert n == S.LEG_RETRY_MAX, "un esito di mercato continua a consumare il budget"
    else:
        assert n == 0, "il rifiuto del freno sul canale non consuma il budget"


class _PortaConMemoria:
    """Porta con la ``MemoriaComandi`` VERA: l'ack entra dalla stessa busta
    che il runner manda (``ricevi_ack``)."""

    def __init__(self):
        self.memoria = SPO.MemoriaComandi()


def _evento_rifiutato(ref):
    # stesse chiavi di motore_ordini.riga_specchio_da_esito + _emetti
    d = {k: None for k in MO.CHIAVI_SPECCHIO}
    d.update({"client_order_ref": "awlq0000000001", "request_id": 1, "mode": "paper",
              "market_id": "m-1.100", "selection_id": 3, "handicap": 0.0, "side": "lay",
              "order_type": "LIMIT", "price": 75.0, "size": 1.0, "size_matched": 0.0,
              "size_remaining": 0.0, "size_cancelled": 0.0, "size_lapsed": 0.0,
              "size_voided": 0.0, "average_price_matched": 0.0,
              "ref": ref, "seq": 7, "fase": "rifiutato", "esito_ms": 1})
    return d


@pytest.mark.parametrize("motivo_ack,consuma", [
    (f"{MO.M_IN_AGGANCIO}: mercato m-1.100 non ancora sottoscritto", False),
    (None, True),                                  # ack normale: il rifiuto conta
])
def test_evento_terminale_aggancio_scaduto_non_consuma(monkeypatch, motivo_ack, consuma):
    """Omega 124 (26/09): il runner PARCHEGGIA l'apertura (ack accettato col
    motivo ``in_aggancio``) e dopo il tempo massimo la chiude ``rifiutato``
    senza mai toccare il mercato. L'evento non porta il motivo: lo porta l'ack."""
    porta = _PortaConMemoria()
    ref = "omega-t41"
    porta.memoria.ricevi_ack({"ref": ref, "seq": 6, "accettato": True,
                              "motivo": motivo_ack, "ricevuto_ms": 1.0})
    monkeypatch.setattr(S._PO, "porta_esistente", lambda: porta)
    db = FakeDB(_control(mode="paper"))
    tid = db.insert_trade({"event_id": "E-ag", "market_id": "m-1.100", "selection_id": 3,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "pending", "price": 75.0, "size": 1.0, "phase": "ft_cs",
                           "liability": 74.0, "pnl": 0.0,
                           "meta": {"phase": "reserved", "canale_ref": ref}})
    tr = next(t for t in db.trades if t["id"] == tid)
    S._chiudi_da_evento(tr, _evento_rifiutato(ref), db=db, mode="paper", min_stake=2.0, now=NOW)
    riga = next(t for t in db.trades if t["id"] == tid)
    assert riga["status"] == "error" and riga["meta"]["leg_failed"] is True
    n = S._leg_attempts("E-ag", "ft_cs")[0]
    if consuma:
        assert n == 1 and "tentativo_consumato" not in riga["meta"]
    else:
        assert n == 0 and riga["meta"]["tentativo_consumato"] is False
        # la cadenza resta: il giro subito dopo NON riprova, dopo 31 s si'
        assert not S._leg_retry_allowed("E-ag", "ft_cs", NOW + timedelta(seconds=5))
        assert S._leg_retry_allowed("E-ag", "ft_cs",
                                    NOW + timedelta(seconds=S.LEG_RETRY_MIN_S + 1))


def test_esito_di_mercato_consuma_ancora_il_budget(freno):
    """Parita': un esito CERTO di mercato (paper senza fill) continua a contare."""
    freno(False)
    db = FakeDB(_control(mode="paper"))
    tid = db.insert_trade({"event_id": "E-nf", "market_id": "m", "selection_id": 9,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "pending", "price": 50.0, "size": 1.0,
                           "liability": 49.0, "pnl": 0.0, "meta": {"phase": "reserved"}})
    S._leg_certain_failure(db, tid, "E-nf", "ft_cs", NOW, "paper_no_fill")
    assert S._leg_attempts("E-nf", "ft_cs")[0] == 1
    skip = [p for k, p in db.activity if k == "skip"]
    assert skip[-1]["attempt"] == 1 and skip[-1]["max_attempts"] == S.LEG_RETRY_MAX


def test_riga_del_freno_rimasta_sul_db_non_conta_nel_budget(monkeypatch):
    """Se il delete della riserva fallisce la riga resta con ``leg_failed``
    (serve al reconcile, M-11): ``failed_legs`` NON deve contarla come tentativo.
    Righe con le colonne e le chiavi del ``_select_all`` vero."""
    righe = [
        {"id": 1, "event_id": "E-db", "phase": "ft_cs", "closes_trade_id": None,
         "placed_at": "2026-09-26T09:10:57+00:00",
         "meta": {"phase": "reserved", "leg_failed": True, "reason": "kill_switch",
                  "error_final": True, "error_at": "2026-09-26T09:10:58+00:00",
                  "tentativo_consumato": False, "motivo": "db_kill_switch_attivo",
                  "percorso": "paper"}},
        {"id": 2, "event_id": "E-db", "phase": "ft_cs", "closes_trade_id": None,
         "placed_at": "2026-09-26T09:12:00+00:00",
         "meta": {"phase": "reserved", "leg_failed": True, "reason": "paper_no_fill",
                  "error_final": True, "error_at": "2026-09-26T09:12:01+00:00"}},
    ]
    monkeypatch.setattr(DB, "_select_all", lambda *a, **k: [dict(r) for r in righe])
    out = DB.failed_legs()
    assert out[("E-db", "ft_cs")][0] == 1, "conta solo l'esito di mercato, non il freno"
