"""F0 (16/09) — il gate della coda legge dal battito le modalita' SERVITE.

Dal 16/09 un runner LIVE serve anche le righe 'paper' (client simulato affiancato
nello stesso processo) e lo dichiara nel battito. La tabella
``betfair_live_heartbeat`` ha una sola colonna ``mode`` TEXT e nessun campo JSON
(``migrations/betfair_live_account_heartbeat.sql:53-61``), quindi le modalita'
servite viaggiano nella STESSA colonna separate da '+': ``LIVE+PAPER``.

Cio' che questo test INCHIODA e' la compatibilita' all'indietro, che e'
money-critical in un verso solo: **una riga vecchia ``mode='LIVE'`` non deve
aprire il gate PAPER** (altrimenti un bot in paper crederebbe di avere un banco
simulato dove c'e' solo il client reale). Il gate e' unico per Omega, Safe e Mike
(``safe_strategy/execution.py:543`` delega a ``omega_service._flumine_gate``),
quindi una sola lettura corretta li copre tutti e tre.

I finti sono quelli gia' in uso per la coda (``FakeQueueDB``), che restituisce la
riga di heartbeat con le chiavi vere ``{ts, mode, pid}`` di ``omega_db.runner_heartbeat``.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB, _params
from Betfair.omega.test_omega_service import NOW, _control


@pytest.mark.parametrize("hb_mode,paper_aperto,live_aperto", [
    # riga VECCHIA (pre-F0): dichiara una sola modalita'
    ("LIVE", False, True),      # <-- il gate paper DEVE restare chiuso
    ("PAPER", True, False),
    ("OFF", False, False),
    (None, False, False),       # nessun battito
    # riga NUOVA (F0): il runner LIVE dichiara di servire entrambe
    ("LIVE+PAPER", True, True),
    ("live+paper", True, True),  # tolleranza di grafia (upper interno)
])
def test_il_gate_apre_solo_le_modalita_dichiarate(hb_mode, paper_aperto, live_aperto):
    db = FakeQueueDB(_control(), hb_mode=hb_mode)
    ok_p, why_p = S._flumine_gate("1.100", db=db, mode="paper",
                                  params=_params(), now=NOW)
    ok_l, why_l = S._flumine_gate("1.100", db=db, mode="live",
                                  params=_params(omega_live_via_flumine=True),
                                  now=NOW)
    assert ok_p is paper_aperto, why_p
    assert ok_l is live_aperto, why_l
    if not paper_aperto:
        assert why_p in ("runner_mode_non_paper",)
    if not live_aperto:
        assert why_l in ("runner_mode_non_live",)


def test_hb_serve_e_fail_closed_su_valori_sporchi():
    """Qualunque valore non leggibile = nessuna modalita' dichiarata (gate chiuso)."""
    assert S._hb_serve("LIVE+PAPER", "PAPER") is True
    assert S._hb_serve("LIVE+PAPER", "LIVE") is True
    assert S._hb_serve("LIVE", "PAPER") is False
    assert S._hb_serve("PAPER", "LIVE") is False
    assert S._hb_serve(None, "PAPER") is False
    assert S._hb_serve("", "PAPER") is False
    assert S._hb_serve(123, "PAPER") is False
    # una modalita' non e' un prefisso dell'altra: nessun match "per contenuto"
    assert S._hb_serve("LIVEPAPER", "PAPER") is False
