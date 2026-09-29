"""Il RUNNER PAPER finto per i test di Safe (cantiere P, 28/09).

Dal 28/09 (ordine dell'utente: «deve essere lo specchio per tutti i bot») un
ordine PAPER di Safe esiste solo sul runner: coda ``betfair_live_order_requests``
(o canale di comando), specchio ``betfair_live_orders``, esito letto dal poll
VERO (``omega_service.poll_flumine_pending`` via ``bot_service.poll_flumine``).
Senza runner l'ordine e' dichiarato non eseguito (``paper_senza_runner``).

I finti di prima (``follow="NONE"`` = gate chiuso) facevano passare OGNI test
dal simulatore «di casa» di ``execution.place``, che non c'e' piu'. Qui si
RIUSA il runner finto di Omega (``Betfair/omega/tests/runner_paper_finto``,
cantiere C: stesse chiavi di ``omega_db``/``bot_db`` per coda, specchio e
battito) con tre adattamenti per il contratto dei finti di Safe:
  * ``db.follow`` / ``db.heartbeat`` restano i comandi dei test (un test che
    mette ``follow="NONE"`` o un battito vecchio spegne il runner come prima);
  * ogni payload accodato finisce anche in ``db.queue`` (i test storici lo
    ispezionano);
  * ``place_submin`` (place-and-trim sotto il minimo) viene eseguito come il
    runner lo esegue (stessa macchina in paper e in live, ``motore_ordini`` /
    ``live_order_worker``): qui l'esito finto e' l'abbinamento della
    ``params.target_size`` al prezzo, o nulla se il test lo dice.

COSA E' FINTO, dichiarato: l'ESITO del runner (abbinato per intero al prezzo
chiesto, oppure ucciso). Il matching VERO (coda, bet delay, FOK, parziali) e'
di flumine ed e' certificato dal banco, non da questi test.
ASCII-only.
"""
from __future__ import annotations

from typing import Any

from Betfair.omega.tests.runner_paper_finto import attiva_runner_paper


def monta_runner_paper(db: Any, *, esito: str = "abbinato") -> Any:
    """Monta su ``db`` (istanza) il runner PAPER finto. Idempotente.

    ``esito``: 'abbinato' (FOK coperto: tutto al prezzo chiesto) o 'ucciso'
    (FOK non coperto: nessun abbinato)."""
    gia = isinstance(getattr(db, "coda_runner", None), dict)
    attiva_runner_paper(db, esito=esito)
    if gia:
        return db
    # 1) gate: i comandi dei test (follow / heartbeat) restano quelli di sempre
    if not hasattr(db, "follow"):
        db.follow = "STREAMING"
    if hasattr(db, "heartbeat"):
        def runner_heartbeat() -> dict:
            return db.heartbeat
        db.runner_heartbeat = runner_heartbeat

    def live_follow_status(event_id: str) -> str:
        return db.follow

    db.live_follow_status = live_follow_status

    # 2) coda: payload registrati + place-and-trim paper
    accoda = db.enqueue_live_order

    def enqueue_live_order(payload: dict) -> int:
        rid = accoda(payload)
        if isinstance(getattr(db, "queue", None), list):
            db.queue.append(payload)
        if payload.get("action") == "place_submin" and payload.get("mode") == "paper":
            chiave = "awlq%d" % rid
            if chiave not in db.specchi_runner:
                target = float((payload.get("params") or {}).get("target_size")
                               or payload["size"])
                abbinato = target if db.esito_runner == "abbinato" else 0.0
                db.specchi_runner[chiave] = {
                    "mode": "paper", "bet_id": "sim%d" % rid,
                    "status": "EXECUTION_COMPLETE",
                    "size_matched": abbinato, "size_remaining": 0.0,
                    "average_price_matched": float(payload["price"]) if abbinato else 0.0,
                    "matched_at": None}
        return rid

    db.enqueue_live_order = enqueue_live_order
    return db


def esito_del_runner(db: Any, *, now: Any, params: Any = None, market: Any = None) -> int:
    """Le prime fasi del giro DOPO, per chi collauda ``execution.close_trade``
    / ``place`` fuori dal ciclo del servizio: il poll VERO della coda
    (``omega_service.poll_flumine_pending``, lo stesso che usano Safe e Omega)
    e il riallineamento delle aperture con le chiusure appena confermate
    (``execution.apply_hedge_state``, cio' che fanno ``sync_hedges`` di Safe e
    il settlement di Omega al giro dopo)."""
    from Betfair.omega import omega_service as OS
    from Betfair.safe_strategy import execution as X

    n = OS.poll_flumine_pending(db=db, params=params or {}, now=now, market=market)
    for tr in [t for t in list(getattr(db, "trades", []) or [])
               if t.get("status") == "open" and not t.get("closes_trade_id")]:
        legs = [c for c in db.trades if c.get("closes_trade_id") == tr.get("id")]
        if legs:
            X.apply_hedge_state(db, tr, legs, now)
    return n


def spegni_runner(db: Any) -> Any:
    """Il runner NON raggiungibile (evento non seguito in streaming)."""
    db.follow = "NONE"
    return db
