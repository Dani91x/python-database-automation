"""26/09 (F-10, test e2e FASE 3) - ``set_summary`` omette l'ultimo set.

Reperto: Bondar v Birrell (36118619), ``tennis_live_now.score``: status
'Finished', sets 1-2, games 1-6, set_summary '5-7 6-2' (manca il 1-6 del terzo
set). ``gameSequence`` IPS porta i set chiusi PRIMA di quello corrente; il set
in corso (o l'ultimo, a partita finita) sta in ``games``.

Payload IPS con le chiavi vere (``_payload`` di ``test_tennis_score_state``).

FALSIFICAZIONE (26/09): rimettendo la vecchia ``_set_summary`` (solo la
sequenza) i primi due test diventano rossi; togliendo il controllo sulla
lunghezza il terzo (nessun doppione) diventa rosso.
"""

from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores
from Betfair.stream.tennis_live.tennis_runner import tennis_score_state


def _payload(*, status, sh, sa, gh, ga, seq_h, seq_a):
    return [{
        "eventId": "36118619", "status": status, "matchStatus": status,
        "currentSet": sh + sa + 1, "currentGame": 1,
        "score": {
            "home": {"score": "0", "games": gh, "sets": sh, "isServing": True,
                     "serviceBreaks": 0, "gameSequence": seq_h},
            "away": {"score": "0", "games": ga, "sets": sa, "isServing": False,
                     "serviceBreaks": 0, "gameSequence": seq_a},
        },
    }]


def _summary(**kw):
    return tennis_score_state(parse_tennis_scores(_payload(**kw), "36118619"))["set_summary"]


def test_partita_finita_mostra_anche_l_ultimo_set():
    assert _summary(status="Finished", sh=1, sa=2, gh=1, ga=6,
                    seq_h=["5", "6"], seq_a=["7", "2"]) == "5-7 6-2 1-6"


def test_in_gioco_mostra_il_set_in_corso():
    assert _summary(status="InPlay", sh=1, sa=1, gh=2, ga=1,
                    seq_h=["6", "3"], seq_a=["4", "6"]) == "6-4 3-6 2-1"


def test_nessun_doppione_se_la_sequenza_contiene_gia_l_ultimo_set():
    assert _summary(status="Finished", sh=1, sa=2, gh=1, ga=6,
                    seq_h=["5", "6", "1"], seq_a=["7", "2", "6"]) == "5-7 6-2 1-6"


def test_inizio_set_a_zero_non_aggiunge_0_0():
    assert _summary(status="InPlay", sh=1, sa=0, gh=0, ga=0,
                    seq_h=["6"], seq_a=["4"]) == "6-4"
