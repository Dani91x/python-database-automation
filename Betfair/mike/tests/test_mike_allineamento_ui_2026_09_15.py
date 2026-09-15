"""IL BACKEND DEVE DIRE QUELLO CHE DECIDE (15/09/2026).

Il 15/09 il trader ha visto Mike «fermo» senza nessun motivo scritto da nessuna
parte. Le ragioni erano due, e nessuna delle due arrivava in pagina:

1. **il tetto delle partite sommava paper e live.** Il ``mode`` si congela sulla
   partita quando viene armata, quindi nel ``tracked`` convivono le due
   modalita'. Col tetto a 1, una vecchia posizione PAPER rimasta viva occupava
   il posto REALE e il bot in live non apriva piu' niente. I soldi finti non
   possono occupare il posto dei soldi veri.

2. **la vitalita' del bot si giudicava con una costante scritta nel frontend.**
   Era una seconda verita': il 13/09 la cadenza delle scritture era stata
   allargata per far respirare il database, e il frontend non lo sapeva.
   La cadenza la dichiara CHI BATTE.

La regola che questi test fissano:

    se il servizio prende una decisione che cambia quello che il trader vede,
    quella decisione la PUBBLICA. Dedurla non e' compito suo.
"""
from __future__ import annotations

from Betfair.mike import config as C
from Betfair.mike import service as S


def _ev(mode: str, state: str = "PRE_OPEN") -> dict:
    return {"event_id": "x", "mode": mode, "state": state, "positions": []}


# ---------------------------------------------------------------------------
# 1. il tetto vale DENTRO una modalita'
# ---------------------------------------------------------------------------
def test_una_partita_paper_non_occupa_il_posto_di_una_live():
    """IL DIFETTO DEL 15/09, in una riga.

    Due partite esposte, una per modalita'. Prima davano «2 posti occupati» e
    con un tetto a 1 il live restava fuori; ora sono due conti separati, e
    ciascuna modalita' ha il suo posto libero... cioe' occupato dal proprio.
    """
    tracked = {"paper1": _ev("paper"), "live1": _ev("live")}
    posti = S.posti_occupati_per_modo(tracked, "live")
    assert posti["paper"] == {"paper1"}
    assert posti["live"] == {"live1"}
    # il conto che decide per il LIVE non vede la partita paper
    assert len(posti.get("live", ())) == 1


def test_le_partite_paper_non_si_contano_mai_insieme_alle_live():
    """Tre paper e una live: per il live il tetto e' occupato da UNA sola."""
    tracked = {f"p{i}": _ev("paper") for i in range(3)}
    tracked["l1"] = _ev("live")
    posti = S.posti_occupati_per_modo(tracked, "live")
    assert len(posti["paper"]) == 3
    assert len(posti["live"]) == 1


def test_chi_non_ha_esposizione_non_occupa_nessun_posto():
    """Osservare non costa: vale per tutte e due le modalita'."""
    tracked = {"a": _ev("live", state="WATCH"), "b": _ev("paper", state="WATCH")}
    assert S.posti_occupati_per_modo(tracked, "live") == {}


def test_una_partita_regolata_libera_il_suo_posto():
    tracked = {"a": _ev("live", state=sorted(S.E.TERMINAL_STATES)[0])}
    assert S.posti_occupati_per_modo(tracked, "live") == {}


def test_chi_non_dichiara_la_modalita_eredita_quella_del_servizio():
    """Una riga senza `mode` non deve finire in un terzo secchio invisibile:
    finirebbe fuori da ogni tetto e non la fermerebbe piu' nessuno."""
    tracked = {"a": {"event_id": "a", "state": "PRE_OPEN", "positions": []}}
    assert S.posti_occupati_per_modo(tracked, "live") == {"live": {"a"}}


def test_nessuna_partita_nessun_posto():
    assert S.posti_occupati_per_modo({}, "live") == {}


# ---------------------------------------------------------------------------
# 2. la cadenza del battito la dichiara chi batte
# ---------------------------------------------------------------------------
def test_la_cadenza_e_quella_del_freno_sulle_scritture():
    """Coi valori di serie vince ``heartbeat_min_s`` (20 s), non il passo del
    ciclo a riposo (5 s): fra due battiti passano fino a 20 secondi."""
    assert S._cadenza_battito(C.merge_params(None)) == 20.0


def test_allargare_il_freno_allarga_la_cadenza_dichiarata():
    """E' IL PUNTO: il 13/09 questo valore e' stato allargato per far respirare
    il database. Se la pagina continuasse a misurare col metro vecchio
    chiamerebbe morto un bot vivo."""
    p = dict(C.merge_params(None), heartbeat_min_s=90.0)
    assert S._cadenza_battito(p) == 90.0


def test_un_ciclo_lento_conta_piu_del_freno():
    """Se il ciclo a riposo e' piu' lento del freno, e' lui a dettare il passo:
    vince sempre il piu' lento dei due, perche' il battito non puo' arrivare
    prima del giro che lo scrive."""
    p = dict(C.merge_params(None), heartbeat_min_s=5.0, idle_cycle_s=45.0)
    assert S._cadenza_battito(p) == 45.0


def test_una_cadenza_assurda_non_diventa_zero():
    """Zero o negativo significherebbe «battito istantaneo» e farebbe dichiarare
    vecchio qualunque bot. Si ricade sul valore di serie."""
    p = dict(C.merge_params(None), heartbeat_min_s=0.0, idle_cycle_s=0.0,
             decide_min_interval_ms=0)
    assert S._cadenza_battito(p) == 20.0


def test_parametri_illeggibili_non_fanno_saltare_il_battito():
    p = {"heartbeat_min_s": "boh", "idle_cycle_s": None, "decide_min_interval_ms": "x"}
    assert S._cadenza_battito(p) > 0.0


def test_senza_parametri_si_usano_quelli_di_serie():
    assert S._cadenza_battito(None) == 20.0
