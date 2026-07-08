"""Modello win-probability tennis (Markov a livello game) — fair value dal punteggio.

Da hold-di-servizio -> set -> match, calcola P(giocatore vince il match) dato lo
stato di gioco. Serve a stimare il PREZZO GIUSTO in-play e fare fade quando il
mercato SOVRA-reagisce a un punto/break (Klaassen-Magnus: il mercato over-reagisce;
il modello aggiorna la probabilita' del "giusto").

Livello game (non punto): lo score feed da' games/sets, e i punti pesano poco sulla
win-prob complessiva. Hold: probabilita' che chi serve tenga il turno (parametro).
"""
from __future__ import annotations

from functools import lru_cache

# ⚠️ cache BOUNDED (fix review): le chiavi includono float (ha/hb) che nel runner
# always-on cambiano quasi a ogni poll → maxsize=None crescerebbe SENZA LIMITE per
# giorni (OOM di un servizio money-critical). 4096 stati coprono ampiamente un match.


@lru_cache(maxsize=4096)
def p_set(ga: int, gb: int, a_serves: bool, ha: float, hb: float,
          p_tb: float = 0.5) -> float:
    """P(A vince il SET) da games ga-gb, con 'a_serves' = tocca ad A servire.

    ha/hb = prob che A/B TENGA il proprio servizio. Ricorsione sul game a venire.
    """
    # set gia' deciso (6+ con 2 di margine, o 7-x dopo 5-5/6-6 via tiebreak)
    if ga >= 6 and ga - gb >= 2:
        return 1.0
    if gb >= 6 and gb - ga >= 2:
        return 0.0
    if ga == 7:
        return 1.0
    if gb == 7:
        return 0.0
    if ga == 6 and gb == 6:
        return p_tb  # tiebreak
    # gioca il prossimo game: chi serve tiene con prob h; poi si alterna il servizio
    if a_serves:
        win_if_hold = p_set(ga + 1, gb, False, ha, hb, p_tb)   # A tiene
        win_if_break = p_set(ga, gb + 1, False, ha, hb, p_tb)  # A perde il servizio
        return ha * win_if_hold + (1 - ha) * win_if_break
    else:
        # serve B: B tiene con prob hb (allora gb+1), altrimenti A brekka (ga+1)
        win_if_bhold = p_set(ga, gb + 1, True, ha, hb, p_tb)
        win_if_abreak = p_set(ga + 1, gb, True, ha, hb, p_tb)
        return hb * win_if_bhold + (1 - hb) * win_if_abreak


@lru_cache(maxsize=4096)
def p_match(sa: int, sb: int, ga: int, gb: int, a_serves: bool,
            ha: float, hb: float, best_of: int = 3) -> float:
    """P(A vince il MATCH) dallo stato completo. best_of=3 (ATP/WTA std) o 5."""
    need = best_of // 2 + 1
    if sa >= need:
        return 1.0
    if sb >= need:
        return 0.0
    # prob A vince il set corrente
    ps = p_set(ga, gb, a_serves, ha, hb)
    # chi serve per primo il set successivo: alterna col totale game del set corrente
    # (approssimazione: chi ha servito per primo il set successivo). Usiamo a_serves
    # di default a inizio set = alterna dal precedente; qui semplifichiamo a True.
    win_if_win_set = p_match(sa + 1, sb, 0, 0, True, ha, hb, best_of)
    win_if_lose_set = p_match(sa, sb + 1, 0, 0, True, ha, hb, best_of)
    return ps * win_if_win_set + (1 - ps) * win_if_lose_set


def estimate_holds(breaks_a: int, breaks_b: int, games_a: int, games_b: int,
                   prior: float = 0.75) -> tuple:
    """Stima (ha, hb) dai break subiti finora, con shrink verso un prior.

    ha = prob che A tenga il servizio. breaks_b = volte che A ha brekkato B
    (= B ha subito). Usa i game totali come proxy dei turni di servizio.
    """
    serves_each = max(1, (games_a + games_b) // 2)
    # A ha subito breaks_a break sul proprio servizio
    obs_ha = max(0.0, 1.0 - breaks_a / serves_each)
    obs_hb = max(0.0, 1.0 - breaks_b / serves_each)
    # shrink verso il prior (pochi dati -> piu' prior)
    w = min(1.0, serves_each / 6.0)
    ha = w * obs_ha + (1 - w) * prior
    hb = w * obs_hb + (1 - w) * prior
    return (min(0.95, max(0.5, ha)), min(0.95, max(0.5, hb)))


if __name__ == "__main__":  # self-test rapido
    # 0-0, hold uguali 0.75 -> ~0.5
    print("0-0 h=0.75:", round(p_match(0, 0, 0, 0, True, 0.75, 0.75), 3))
    # A avanti di un break 3-1 al servizio -> >0.5 ma non enorme
    print("set 3-1 A serve:", round(p_set(3, 1, True, 0.8, 0.8), 3))
    # A servito, 5-3 -> vicino a chiudere il set
    print("set 5-3 A serve:", round(p_set(5, 3, True, 0.8, 0.8), 3))
    # A con un set di vantaggio best-of-3
    print("match 1-0 set:", round(p_match(1, 0, 0, 0, True, 0.75, 0.75), 3))
    # hold molto alti (servizio domina) -> break vale di piu'
    print("set 3-2 A serve h=0.9:", round(p_set(3, 2, True, 0.9, 0.9), 3))
