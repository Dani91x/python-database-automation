"""Il RUNNER PAPER finto per i test di Omega che hanno bisogno di una posizione
paper APERTA (cantiere C, 28/09).

Dal 28/09 (ordine dell'utente, D1) Omega in paper NON ha piu' un simulatore
"di casa": l'apertura paper passa dal runner (canale o coda) oppure e'
dichiarata non eseguita. I test storici che collaudano altro (settlement,
target, missioni, V3...) aprivano la posizione col fill istantaneo del
vecchio simulatore; qui ricevono invece la STRADA VERA del paper: la coda del
runner (``betfair_live_order_requests``) e lo specchio (``betfair_live_orders``)
col contratto e le chiavi di ``omega_db`` (stesse dei finti di
``test_omega_flumine_paper.FakeQueueDB``), piu' il poll VERO del servizio
(``poll_flumine_pending``) che conferma la riga.

COSA E' FINTO, dichiarato: l'ESITO del runner. Qui un FOK che il book copre
viene abbinato per intero al prezzo chiesto (``esito='abbinato'``) oppure
ucciso (``esito='ucciso'``). Il matching VERO (coda al prezzo, bet delay, FOK)
e' di flumine ed e' certificato dal banco (``trasporto_rapido`` R1/R3 sulla
registrazione 35760084), non da questi test.
ASCII-only.
"""
from __future__ import annotations

from typing import Any, Optional

from Betfair.omega import omega_config
from Betfair.omega import omega_service as S

#: battito del runner: un istante lontano nel futuro, cosi' il gate lo trova
#: fresco a qualunque ``now`` dei test (il vero e' un ISO di Betfair UTC)
_BATTITO_TS = "2100-01-01T00:00:00+00:00"


def attiva_runner_paper(db: Any, *, esito: str = "abbinato") -> Any:
    """Aggiunge a ``db`` (istanza) il contratto coda/specchio/battito di un
    runner in modalita' PAPER che esegue subito i ``place`` paper. Idempotente."""
    if isinstance(getattr(db, "coda_runner", None), dict):
        db.esito_runner = esito
        return db
    db.coda_runner = {}
    db.specchi_runner = {}
    db.esito_runner = esito

    def live_follow_status(event_id: str) -> str:
        return "STREAMING"

    def runner_heartbeat() -> dict:
        return {"ts": _BATTITO_TS, "mode": "PAPER", "pid": 4242}

    def enqueue_live_order(payload: dict) -> int:
        for rid, riga in db.coda_runner.items():
            if riga["payload"]["client_ref"] == payload["client_ref"]:
                return rid                     # idempotenza su client_ref (RPC vera)
        rid = len(db.coda_runner) + 1
        db.coda_runner[rid] = {"id": rid, "status": "done", "result": None, "error": None,
                               "bet_id": None, "payload": dict(payload)}
        if payload.get("action") == "place" and payload.get("mode") == "paper":
            abbinato = float(payload["size"]) if db.esito_runner == "abbinato" else 0.0
            db.specchi_runner["awlq%d" % rid] = {
                "mode": "paper", "bet_id": "sim%d" % rid, "status": "EXECUTION_COMPLETE",
                "size_matched": abbinato, "size_remaining": 0.0,
                "average_price_matched": float(payload["price"]) if abbinato else 0.0,
                "matched_at": None}
        return rid

    def get_live_order_request(request_id: int) -> Optional[dict]:
        riga = db.coda_runner.get(int(request_id))
        if riga is None:
            return None
        return {k: riga.get(k) for k in ("id", "status", "result", "error", "bet_id")}

    def get_live_order_request_by_ref(client_ref: str) -> Optional[dict]:
        for riga in db.coda_runner.values():
            if riga["payload"]["client_ref"] == str(client_ref):
                return {k: riga.get(k) for k in ("id", "status", "result", "error", "bet_id")}
        return None

    def get_live_order_mirror(client_order_ref: str, mode: str = "paper") -> Optional[dict]:
        riga = db.specchi_runner.get(str(client_order_ref))
        if riga is not None and str(riga.get("mode")) != str(mode):
            return None
        return riga

    def revoke_live_order_request(request_id: int) -> bool:
        riga = db.coda_runner.get(int(request_id))
        if riga is None or riga.get("status") != "pending":
            return False
        riga["status"] = "error"
        return True

    if not callable(getattr(db, "list_trades", None)):
        # i finti piu' vecchi (test v2) non avevano la lettura dei 'pending' che
        # il poll della coda usa: stessa firma di ``omega_db.list_trades``
        def list_trades(status: Optional[str] = None) -> list:
            return [t for t in db.trades if status is None or t.get("status") == status]

        db.list_trades = list_trades

    for f in (live_follow_status, runner_heartbeat, enqueue_live_order,
              get_live_order_request, get_live_order_request_by_ref,
              get_live_order_mirror, revoke_live_order_request):
        setattr(db, f.__name__, f)
    return db


def conferma(db: Any, market: Any, params: dict, now: Any) -> int:
    """Il poll VERO della coda (prima fase del giro dopo) per chi chiama lo scan
    direttamente senza ``run_once``."""
    return S.poll_flumine_pending(db=db, params=params, now=now, market=market)


def gira(*, market: Any, db: Any, now: Any, **kw: Any) -> dict:
    """Un giro VERO di ``run_once`` seguito dal poll VERO della coda (quello
    che il giro successivo farebbe per primo): la riga paper accodata in
    questo giro esce confermata o chiusa, come nel servizio."""
    res = S.run_once(market=market, db=db, now=now, **kw)
    params = omega_config.resolve_params((db.read_control() or {}).get("params"))
    S.poll_flumine_pending(db=db, params=params, now=now, market=market)
    return res
