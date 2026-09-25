"""produzione.py - il candidato A0: l'atlante DI PRODUZIONE, col codice di produzione.

Niente riscritture: si chiama ``genera_atlante.bootstrap`` (coverage 60%,
``sequenza_partita``, ``aggiungi_partita``) e ``genera_atlante.assembla``
servendo le righe dalla CACHE con un lettore finto che parla come il vero
(``tutte``/``get`` con gli stessi parametri PostgREST). Le probabilita' si
leggono con ``hazard_atlas.consulta_atlante``, la funzione che Safe e Mike
chiamano in live, una volta per chiave unica (lega, minuto, gol[, squadre]).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper.hazard_atlas import consulta_atlante


class LettoreCache:
    """Lettore PostgREST FINTO sulle righe della cache: stessi metodi e stessi
    parametri del ``LettoreDB`` (solo i filtri che ``bootstrap`` usa: eq su
    league_id/season_year/event_type, in su fixture_id). Un filtro che non
    conosce lo fa esplodere: mai risposte inventate."""

    FILTRI_NOTI = {"select", "league_id", "season_year", "fixture_id", "event_type", "order", "limit"}

    def __init__(self, matches: Iterable[Dict[str, Any]], eventi: Iterable[Dict[str, Any]]) -> None:
        self.matches: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for m in matches:
            self.matches.setdefault((int(m["league_id"]), int(m["season_year"])), []).append(m)
        self.eventi: Dict[int, List[Dict[str, Any]]] = {}
        for e in eventi:
            self.eventi.setdefault(int(e["fixture_id"]), []).append(e)
        self.n_richieste = 0
        self.n_righe = 0

    def _filtra(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        ignoti = set(params) - self.FILTRI_NOTI
        if ignoti:
            raise ValueError(f"filtro non supportato dal lettore finto: {sorted(ignoti)}")
        if table == "matches":
            lid = int(params["league_id"].split(".", 1)[1])
            anno = int(params["season_year"].split(".", 1)[1])
            rows = sorted(self.matches.get((lid, anno), []), key=lambda r: int(r["fixture_id"]))
        elif table == "match_events":
            lista = params["fixture_id"]
            assert lista.startswith("in.(") and lista.endswith(")")
            fids = [int(x) for x in lista[4:-1].split(",") if x]
            rows = [e for f in fids for e in self.eventi.get(f, [])]
            if "event_type" in params:
                tipo = params["event_type"].split(".", 1)[1]
                rows = [e for e in rows if str(e.get("event_type")) == tipo]
            rows.sort(key=lambda r: int(r["id"]))
        else:
            raise ValueError(f"tabella non servita dal lettore finto: {table}")
        return rows

    def get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        self.n_richieste += 1
        rows = self._filtra(table, params)
        self.n_righe += len(rows)
        return rows

    def tutte(self, table: str, params: Dict[str, str], *, chiave: str,
              pagina: int = 1000) -> List[Dict[str, Any]]:
        p = {k: v for k, v in params.items() if k not in ("order", "limit")}
        return self.get(table, p)


def atlante_a0(lettore: LettoreCache, stagioni_per_lega: Dict[int, List[int]],
               nomi: Optional[Dict[str, Optional[str]]] = None,
               generated_at: str = "2026-09-25T00:00:00+00:00") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(atlante, stati grezzi) di produzione sulle leghe/stagioni indicate."""
    stati: Dict[str, Dict[str, Any]] = {}
    nomi = nomi or {}
    for lid in sorted(stagioni_per_lega):
        G.bootstrap(lettore, stati, [int(lid)], list(stagioni_per_lega[lid]), nomi, generated_at)
    atlas = G.assembla(stati, generated_at=generated_at)
    return atlas, stati


def minuto_a0(tempo: int, stop: int, j: int, m_live: int, convenzione_1t: str) -> int:
    """Il minuto che il consumatore passa a ``consulta_atlante``. Recupero del
    2T: 90+j (``hazard_bucket`` lo porta a '85-90'). Recupero del 1T: il feed
    Betfair NON e' verificato; 'regolare' = 45 (cella '40-45'), 'cumulato' =
    45+j (cella '45-50', quella di inizio ripresa)."""
    if stop and tempo == 1:
        return 44 if convenzione_1t == "regolare" else 45 + j
    return int(m_live)


def predici_a0(atlas: Dict[str, Any], S: Dict[str, np.ndarray], idx: np.ndarray,
               partite: List[Any], *, squadre: bool = False,
               convenzione_1t: str = "regolare") -> Dict[str, np.ndarray]:
    """P2/P3 di A0 sugli stati ``idx`` (una consulta per chiave unica)."""
    cache: Dict[Tuple[Any, ...], Tuple[Optional[float], Optional[float], str]] = {}
    p2 = np.empty(idx.size)
    p3 = np.empty(idx.size)
    fonte = np.empty(idx.size, dtype=object)
    for n, i in enumerate(idx):
        m = minuto_a0(int(S["tempo"][i]), int(S["stop"][i]), int(S["j"][i]), int(S["m_live"][i]),
                      convenzione_1t)
        g = int(S["gh"][i] + S["ga"][i])
        lid = int(S["lega"][i])
        mm = min(89, max(0, m))
        chiave: Tuple[Any, ...] = (lid, mm // 5, min(g, 3))
        if squadre:
            p = partite[int(S["mi"][i])]
            chiave = chiave + (p.home_id, p.away_id)
        v = cache.get(chiave)
        if v is None:
            kw: Dict[str, Any] = {}
            if squadre:
                kw = {"home_id": chiave[3], "away_id": chiave[4]}
            c3 = consulta_atlante(atlas, m, g, lid, horizon="p_goal_next_3min", **kw)
            c2 = consulta_atlante(atlas, m, g, lid, horizon="p_goal_next_2min", **kw)
            v = (c2["p"], c3["p"], c3["fonte"])
            cache[chiave] = v
        p2[n] = np.nan if v[0] is None else v[0]
        p3[n] = np.nan if v[1] is None else v[1]
        fonte[n] = v[2]
    return {"p2": p2, "p3": p3, "fonte": fonte}
