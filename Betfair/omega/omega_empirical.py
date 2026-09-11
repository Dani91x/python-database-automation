"""omega_empirical — SECONDA OPINIONE DAI DATI STORICI per la gamba 2T (§14, 11/09).

Il modello live (``omega_model``) stima P(risultato finale) da λ pre-match e
stato della partita. Il backtest del 10/09 ha mostrato che dal 60′ in poi il
modello è OTTIMISTA proprio sui risultati "impossibili" — la famiglia di lay
che Omega banca. Qui la stessa domanda è posta AI DATI: su ~1,4 M partite
storiche (tabella ``matches``: punteggio al 45′ e finale), quante volte da un
dato risultato del 1T si è arrivati a quel risultato finale?

Tabella ``omega_ht_ft_transitions`` (migrazione ``omega_daily_v2.sql``):
``(league_id, ht, ft, n)`` con ``league_id = 0`` = tutte le leghe. La stima
per lega è SHRINKATA verso il globale (prior Bayesiano con peso ``K``): una
lega con pochi casi pesa poco, una lega con migliaia di partite pesa molto.

Uso nella selezione (``select_by_model`` con ``p_data``): quando il punteggio
corrente al momento dell'ingresso 2T È ANCORA quello del 45′, la P usata per
filtro e ordinamento è max(P_modello, P_empirica) — un risultato va bancato
solo se è raro per ENTRAMBE le viste. Con gol già segnati nel 2T la tabella
non è condizionabile e resta solo il modello. Tutto puro: nessun I/O.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

GLOBAL_LEAGUE = 0
SHRINK_K = 200.0          # peso del prior globale (in "partite equivalenti")
MIN_GLOBAL_N = 30         # sotto: il risultato del 1T è troppo raro per dire qualcosa


def score_key(h: int, a: int) -> str:
    return f"{int(h)}-{int(a)}"


class EmpiricalTable:
    """Conteggi HT→FT per lega (0 = globale). Costruita da righe
    ``{league_id, ht, ft, n}`` (RPC ``get_omega_ht_ft``)."""

    def __init__(self, rows: Iterable[dict]) -> None:
        # league → ht → ft → n ; league → ht → totale
        self._n: Dict[int, Dict[str, Dict[str, int]]] = {}
        self._tot: Dict[int, Dict[str, int]] = {}
        for r in rows or ():
            try:
                lg = int(r.get("league_id") if r.get("league_id") is not None else GLOBAL_LEAGUE)
                ht, ft, n = str(r["ht"]), str(r["ft"]), int(r.get("n") or 0)
            except (TypeError, ValueError, KeyError):
                continue
            if n <= 0:
                continue
            bucket = self._n.setdefault(lg, {}).setdefault(ht, {})
            bucket[ft] = bucket.get(ft, 0) + n
            totals = self._tot.setdefault(lg, {})
            totals[ht] = totals.get(ht, 0) + n

    @property
    def empty(self) -> bool:
        return not self._tot.get(GLOBAL_LEAGUE)

    def counts(self, league_id: Optional[int], ht: Tuple[int, int]) -> Tuple[Dict[str, int], int]:
        lg = int(league_id) if league_id is not None else GLOBAL_LEAGUE
        key = score_key(*ht)
        return self._n.get(lg, {}).get(key, {}), self._tot.get(lg, {}).get(key, 0)

    def p_ft_given_ht(self, ht: Tuple[int, int], ft: Tuple[int, int],
                      league_id: Optional[int] = None) -> Optional[Tuple[float, int]]:
        """(P empirica che dal 1T ``ht`` si finisca ``ft``, n casi globali del 1T).
        None se il 1T è troppo raro nei dati (``MIN_GLOBAL_N``)."""
        g_counts, g_tot = self.counts(GLOBAL_LEAGUE, ht)
        if g_tot < MIN_GLOBAL_N:
            return None
        key = score_key(*ft)
        p_global = g_counts.get(key, 0) / g_tot
        if league_id is None or int(league_id) == GLOBAL_LEAGUE:
            return p_global, g_tot
        l_counts, l_tot = self.counts(league_id, ht)
        if l_tot <= 0:
            return p_global, g_tot
        # shrinkage: (n_lega_ft + K·p_globale) / (n_lega_ht + K)
        p = (l_counts.get(key, 0) + SHRINK_K * p_global) / (l_tot + SHRINK_K)
        return p, g_tot


def empirical_lookup(table: Optional[EmpiricalTable], *, ht: Optional[Tuple[int, int]],
                     current: Tuple[int, int], league_id: Optional[int]):
    """Funzione ``p_data(h, a) → P | None`` per ``select_by_model``, oppure None
    quando la tabella non può parlare: assente/vuota, 1T ignoto, o punteggio
    corrente diverso da quello del 45′ (gol già nel 2T: dati non condizionabili)."""
    if table is None or table.empty or ht is None:
        return None
    if (int(current[0]), int(current[1])) != (int(ht[0]), int(ht[1])):
        return None

    def _p(h: int, a: int) -> Optional[float]:
        got = table.p_ft_given_ht(ht, (h, a), league_id)
        return None if got is None else float(got[0])

    return _p


def audit_empirical(table: Optional[EmpiricalTable], *, ht: Optional[Tuple[int, int]],
                    current: Tuple[int, int], league_id: Optional[int],
                    ft: Tuple[int, int]) -> Dict[str, Any]:
    """Blocco di audit (numeri, mai decisioni) per ``trade.meta.model``."""
    out: Dict[str, Any] = {"empirical": None, "ht_score": None if ht is None else score_key(*ht)}
    if table is None or table.empty or ht is None:
        out["empirical_note"] = "tabella_assente" if (table is None or table.empty) else "1t_ignoto"
        return out
    if (int(current[0]), int(current[1])) != (int(ht[0]), int(ht[1])):
        out["empirical_note"] = "gol_nel_2t"
        return out
    got = table.p_ft_given_ht(ht, ft, league_id)
    if got is None:
        out["empirical_note"] = "1t_raro"
        return out
    out["empirical"] = round(got[0], 6)
    out["empirical_n"] = int(got[1])
    return out
