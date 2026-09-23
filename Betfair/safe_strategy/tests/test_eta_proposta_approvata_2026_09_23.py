"""23/09 - PM7 del banco: l'eta' di una PROPOSTA approvata si misura dal CLIC.

Prima: ``_request_age_s`` leggeva solo ``created_at`` (nascita della riga
'proposed'), e ``safe_request_approve`` non lo tocca: una proposta nata 180 s
prima e approvata con un clic fresco veniva rifiutata 'richiesta_scaduta'.
Adesso, se il payload porta ``approved_at`` (scritto SOLO dalla RPC
``safe_request_approve``, migrazioni 2026-09-14 e 2026-09-18), l'eta' parte
dal clic. Il tetto di 120 s resta; le richieste dirette restano come erano.

Le righe finte hanno le chiavi della riga vera di ``safe_strategy_requests``
(``id``, ``kind``, ``status``, ``created_at``, ``payload``) e ``approved_at`` nel
formato esatto della RPC (``YYYY-MM-DDTHH:MM:SSZ``).
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, _place_payload, _run, _skips, _feed_row)


def _iso_rpc(dt):
    # formato di `safe_request_approve`: to_char(... 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_eta_proposta_approvata_parte_dal_clic():
    riga = {"created_at": (NOW - timedelta(seconds=180)).isoformat(),
            "payload": {"approved_at": _iso_rpc(NOW - timedelta(seconds=5))}}
    assert abs(S._request_age_s(riga, NOW) - 5.0) < 1.0


def test_richiesta_diretta_resta_dalla_creazione():
    riga = {"created_at": (NOW - timedelta(seconds=180)).isoformat(),
            "payload": _place_payload()}
    assert abs(S._request_age_s(riga, NOW) - 180.0) < 1.0


def test_approved_at_illeggibile_ricade_su_created_at():
    riga = {"created_at": (NOW - timedelta(seconds=180)).isoformat(),
            "payload": {"approved_at": "non-una-data"}}
    assert abs(S._request_age_s(riga, NOW) - 180.0) < 1.0


def test_proposta_vecchia_con_clic_fresco_non_scade():
    db = FakeDB(status="running", mode="paper")
    db.scan_rows = [_feed_row()]
    db.requests.append({
        "id": 1, "kind": "place", "status": "pending",
        "created_at": (NOW - timedelta(seconds=180)).isoformat(),
        "payload": _place_payload(approved_at=_iso_rpc(NOW - timedelta(seconds=3)))})
    _run(db)
    assert not _skips(db, "richiesta_scaduta")
    assert (db.requests[0].get("result") or {}).get("reason") != "richiesta_scaduta"


def test_clic_vecchio_oltre_il_tetto_scade_ancora():
    db = FakeDB(status="running", mode="paper")
    db.scan_rows = [_feed_row()]
    db.requests.append({
        "id": 1, "kind": "place", "status": "pending",
        "created_at": (NOW - timedelta(seconds=600)).isoformat(),
        "payload": _place_payload(approved_at=_iso_rpc(
            NOW - timedelta(seconds=S._REQUEST_MAX_AGE_S + 30)))})
    _run(db)
    assert db.trades == []
    assert _skips(db, "richiesta_scaduta")
