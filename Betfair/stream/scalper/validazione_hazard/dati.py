"""dati.py - dalla cache del DB alle PARTITE del banco (PURO, nessuna rete).

Una partita entra nel banco con le STESSE regole della produzione
(``genera_atlante``): stagione con ``fixtures_events=true`` in coverage (tutte
quelle dell'intervallo, come il bootstrap del v3), copertura eventi >= 60% delle partite con gol (``COPERTURA_MIN``),
``sequenza_partita`` che la accetta (FT, gol degli eventi = punteggio, lati
coerenti). In piu' il banco conserva cio' che la produzione butta via:

  gol     (tempo, posizione nel tempo, lato): posizione 1..45 = minuto regolare
          del tempo, 45+e = e-esimo minuto di RECUPERO (minute_extra); la
          produzione invece clampa tutto a [1, 90].
  rossi   (tempo, posizione, lato) da 'Red Card' / 'Second Yellow card'.
  d2      minuti di recupero del 2T GIOCATI, noti: max(status.extra, ultimo
          evento in recupero). None se status.extra manca (stagioni < 2024).
  s1_vivo minuti di recupero del 1T in cui la partita era certamente VIVA
          (ultimo evento NON-gol in recupero, solo stagioni con gli eventi in
          recupero): il DB non ha la durata del recupero del 1T.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Betfair.stream.scalper.genera_atlante import COPERTURA_MIN, sequenza_partita

EXTRA_MAX_VALIDO = 30          # status.extra oltre = dato sporco (misurato: un 86)
DETTAGLI_ROSSO = ("Red Card", "Second Yellow card")


def _int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def posizione(minute: Any, extra: Any) -> Optional[Tuple[int, int]]:
    """(tempo, posizione nel tempo) di un evento API-Football.

    45+2 -> (1, 47); 45 -> (1, 45); 46 -> (2, 1); 90 -> (2, 45); 90+3 -> (2, 48).
    Un minuto > 90 senza extra (2 casi nel campione) vale come recupero del 2T.
    None se il minuto manca."""
    mi = _int(minute)
    if mi is None:
        return None
    ex = _int(extra) or 0
    ex = max(0, ex)
    mi = max(1, mi)
    if mi <= 45:
        return (1, mi + (ex if mi == 45 else 0))
    if mi <= 90:
        return (2, mi - 45 + (ex if mi == 90 else 0))
    return (2, 45 + (mi - 90) + ex)


@dataclass
class Partita:
    fixture_id: int
    league_id: int
    season: int
    date: str
    home_id: int
    away_id: int
    home_name: Optional[str]
    away_name: Optional[str]
    ft: Tuple[int, int]
    gol: List[Tuple[int, int, str]] = field(default_factory=list)     # (tempo, pos, 'h'|'a')
    rossi: List[Tuple[int, int, str]] = field(default_factory=list)
    d2: Optional[int] = None
    s1_vivo: int = 0
    eventi_recupero: bool = False     # stagione con gli eventi in recupero letti
    seq: Optional[Dict[str, Any]] = None   # la sequenza della produzione (per A0)


def lati_gol(match: Dict[str, Any], goal_rows: List[Dict[str, Any]]) -> Optional[List[Tuple[Dict[str, Any], str]]]:
    """(riga, lato) dei gol con la STESSA regola di ``sequenza_partita``
    (lato dal team_id, autogol girati se i lati non tornano). None = scartata."""
    hid, aid = _int(match.get("home_team_id")), _int(match.get("away_team_id"))
    gh = _int(match.get("goals_home"))
    out = []
    for r in goal_rows:
        if str(r.get("event_type") or "") != "Goal" or str(r.get("detail") or "") == "Missed Penalty":
            continue
        tid = _int(r.get("team_id"))
        if _int(r.get("minute")) is None or tid not in (hid, aid):
            return None
        out.append([r, "h" if tid == hid else "a", str(r.get("detail") or "") == "Own Goal"])
    if sum(1 for x in out if x[1] == "h") != gh:
        flip = [[x[0], ("a" if x[1] == "h" else "h") if x[2] else x[1], x[2]] for x in out]
        if sum(1 for x in flip if x[1] == "h") != gh:
            return None
        out = flip
    return [(x[0], x[1]) for x in out]


SOGLIA_RECUPERO_REGISTRATO = 0.6    # 2016-2024: 0,73-0,96 per lega-stagione; 2025 grandi leghe: 0,00-0,28
MIN_GOL_BLOCCO = 5


def quota_gol_con_extra(goal_rows: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    """(gol al 45'/90' con minute_extra > 0, gol al 45'/90' totali). Un gol di
    fine tempo senza extra puo' essere un vero 45'/90'; ma se QUASI TUTTI ne sono
    privi, il recupero non e' stato registrato (misurato 25/09: stagione 2025
    delle leghe europee, ago 2025 - mag 2026, anche ``raw_json.time.extra`` NULL)."""
    con = tot = 0
    for r in goal_rows:
        if str(r.get("event_type")) != "Goal" or _int(r.get("minute")) not in (45, 90):
            continue
        tot += 1
        con += int((_int(r.get("minute_extra")) or 0) > 0)
    return con, tot


def recupero_registrato(match_rows: Iterable[Dict[str, Any]], eventi: Iterable[Dict[str, Any]], *,
                        soglia: float = SOGLIA_RECUPERO_REGISTRATO, min_gol: int = MIN_GOL_BLOCCO
                        ) -> Dict[int, bool]:
    """{fixture_id: il blocco (lega, mese) della partita registra il recupero dei gol?}.
    Blocco (lega, AAAA-MM); se ha meno di ``min_gol`` gol di fine tempo si giudica
    sulla (lega, stagione); se anche quella ne ha meno, si presume registrato."""
    info: Dict[int, Tuple[int, int, str]] = {}
    for m in match_rows:
        f = _int(m.get("fixture_id"))
        if f is not None:
            info[f] = (int(m["league_id"]), int(m["season_year"]), str(m.get("fixture_date") or "")[:7])
    blocco: Dict[Tuple[int, str], List[int]] = {}
    stag: Dict[Tuple[int, int], List[int]] = {}
    for e in eventi:
        i = info.get(_int(e.get("fixture_id")))
        if i is None:
            continue
        c, t = quota_gol_con_extra([e])
        if t:
            for d, k in ((blocco, (i[0], i[2])), (stag, (i[0], i[1]))):
                v = d.setdefault(k, [0, 0])
                v[0] += c
                v[1] += t
    out: Dict[int, bool] = {}
    for f, (lid, s, mese) in info.items():
        c, t = blocco.get((lid, mese), [0, 0])
        if t < min_gol:
            c, t = stag.get((lid, s), [0, 0])
        out[f] = True if t < min_gol else (c / t) >= soglia
    return out


def stagioni_valide(coverage: Iterable[Dict[str, Any]], ultime: Optional[int] = None) -> Dict[int, List[int]]:
    """Stagioni con fixtures_events=true per lega (tutte, o le ultime ``ultime``
    come ``--stagioni auto``). Il banco le usa TUTTE nel suo intervallo
    2016-2025: e' cio' che ha fatto il bootstrap del v3 (``--stagioni 2016-...``)."""
    per: Dict[int, set] = {}
    for r in coverage:
        if r.get("fixtures_events") is True:
            lid, anno = _int(r.get("league_id")), _int(r.get("season_year"))
            if lid is not None and anno is not None:
                per.setdefault(lid, set()).add(anno)
    return {l: (sorted(s)[-ultime:] if ultime else sorted(s)) for l, s in per.items()}


def costruisci_partite(matches: List[Dict[str, Any]], eventi: List[Dict[str, Any]],
                       coverage: List[Dict[str, Any]], *, stagione_max: int = 2025,
                       stagione_eventi_recupero: int = 2024) -> Tuple[List[Partita], Dict[str, Any]]:
    """Le partite del banco + un resoconto (scarti per motivo, stagioni saltate)."""
    valide = stagioni_valide(coverage)
    per_fx: Dict[int, List[Dict[str, Any]]] = {}
    for e in eventi:
        f = _int(e.get("fixture_id"))
        if f is not None:
            per_fx.setdefault(f, []).append(e)
    per_ls: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for m in matches:
        lid, s = _int(m.get("league_id")), _int(m.get("season_year"))
        if lid is None or s is None or s > stagione_max:
            continue
        per_ls.setdefault((lid, s), []).append(m)
    res: Dict[str, Any] = {"scarti": {}, "stagioni_senza_eventi_coverage": [],
                           "stagioni_saltate_copertura": {}, "non_ft": 0}
    out: List[Partita] = []
    for (lid, s), ms in sorted(per_ls.items()):
        if s not in valide.get(lid, []):
            res["stagioni_senza_eventi_coverage"].append([lid, s])
            continue
        gol_fx = {f for m in ms for f in [int(m["fixture_id"])]
                  if any(str(e.get("event_type")) == "Goal" for e in per_fx.get(f, []))}
        con_gol = {int(m["fixture_id"]) for m in ms if str(m.get("status_short")) == "FT"
                   and (_int(m.get("goals_home")) or 0) + (_int(m.get("goals_away")) or 0) > 0}
        cop = len(con_gol & gol_fx) / len(con_gol) if con_gol else 0.0
        if cop < COPERTURA_MIN:
            res["stagioni_saltate_copertura"][f"{lid}-{s}"] = round(cop, 3)
            continue
        for m in ms:
            fid = int(m["fixture_id"])
            evs = per_fx.get(fid, [])
            gol_rows = [e for e in evs if str(e.get("event_type")) == "Goal"]
            seq, motivo = sequenza_partita(m, gol_rows)
            if seq is None:
                if motivo == "non_ft":
                    res["non_ft"] += 1
                else:
                    res["scarti"][motivo] = res["scarti"].get(motivo, 0) + 1
                continue
            lati = lati_gol(m, gol_rows)
            if lati is None:            # impossibile se sequenza_partita l'ha accettata
                res["scarti"]["lati_banco"] = res["scarti"].get("lati_banco", 0) + 1
                continue
            p = Partita(fixture_id=fid, league_id=lid, season=s,
                        date=str(m.get("fixture_date") or "")[:10],
                        home_id=int(m["home_team_id"]), away_id=int(m["away_team_id"]),
                        home_name=m.get("home_team_name"), away_name=m.get("away_team_name"),
                        ft=(int(m["goals_home"]), int(m["goals_away"])), seq=seq)
            for r, lato in lati:
                pos = posizione(r.get("minute"), r.get("minute_extra"))
                p.gol.append((pos[0], pos[1], lato))
            p.gol.sort(key=lambda g: (g[0], g[1]))
            hid = p.home_id
            for e in evs:
                if str(e.get("event_type")) == "Card" and str(e.get("detail")) in DETTAGLI_ROSSO:
                    pos = posizione(e.get("minute"), e.get("minute_extra"))
                    tid = _int(e.get("team_id"))
                    if pos is None or tid not in (p.home_id, p.away_id):
                        continue
                    p.rossi.append((pos[0], pos[1], "h" if tid == hid else "a"))
            p.rossi.sort(key=lambda g: (g[0], g[1]))
            p.eventi_recupero = s >= stagione_eventi_recupero
            lb2 = 0
            lb1_ng = 0
            for e in evs:
                pos = posizione(e.get("minute"), e.get("minute_extra"))
                if pos is None or pos[1] <= 45:
                    continue
                if pos[0] == 2:
                    lb2 = max(lb2, pos[1] - 45)
                elif str(e.get("event_type")) != "Goal":
                    lb1_ng = max(lb1_ng, pos[1] - 45)
            ex = _int(m.get("extra"))
            if ex is not None and 0 <= ex <= EXTRA_MAX_VALIDO:
                p.d2 = max(ex, lb2)
            p.s1_vivo = lb1_ng if p.eventi_recupero else 0
            out.append(p)
    res["n_partite"] = len(out)
    return out, res
