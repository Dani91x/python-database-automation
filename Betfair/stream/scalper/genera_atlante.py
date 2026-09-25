"""genera_atlante.py - GENERATORE dell'Atlante Hazard, incrementale per lega.

Perche' esiste (24/09/2026, ordine dell'utente): l'atlante in uso
(``omega/data/hazard_atlas_v2.json``) era fermo al 15/07 e lo script che lo
aveva prodotto viveva in uno scratchpad di sessione, MAI committato: nessuno
poteva rigenerarlo. "Deve essere uno strumento AUTOMATICO che si aggiorna in
base alle leghe e alle partite come tutto il resto del sistema". Questo
modulo rifa' il METODO scritto nel ``meta.method`` del v1/v2, e lo rende
incrementale:

  * STATO GREZZO per lega (conteggi additivi, mai probabilita'): celle
    (bucket 5' x gol correnti) con n partite-minuto a rischio e successi a
    2'/3', gol per lato per bucket, profili squadra, scontri diretti, id delle
    partite gia' contate (idempotenza: una partita non si conta due volte).
  * ASSEMBLAGGIO: dallo stato grezzo si ricalcolano global, by_league
    (shrinkage K=1500 verso il globale), by_team (K=12 verso la lega) e
    h2h_hint, con ``meta.generated_at`` e i conteggi per lega. Stesso
    formato che ``hazard_atlas.hazard_lookup`` e i consumatori gia' leggono.
  * INCREMENTALE: ogni notte si leggono SOLO gli eventi con id oltre la
    filigrana (``match_events.id``, chiave primaria), si ricavano le partite
    toccate e si aggiornano SOLO le loro leghe.
  * BOOTSTRAP: una tantum per lega/stagione (lo storico che l'incrementale
    non vede).

Il metodo (dal meta del v1, riprodotto qui):
  - solo partite ``status_short == 'FT'``; eventi ``Goal`` escluso
    ``Missed Penalty``; partita scartata se il numero di gol negli eventi e'
    diverso dal punteggio finale;
  - minuto clampato a [1, 90] (il recupero cade in 45/90, minute_extra
    ignorato);
  - per ogni minuto m in 0..87: stato = (bucket 5' di m, gol con minuto<=m);
    n += 1; s3 += 1 se c'e' almeno un gol in (m, m+3]; s2 idem su 2';
  - p_shrunk = (successi + K * p_parent) / (n + K).

SOLA LETTURA del DB in questo modulo (GET su PostgREST); la scrittura dello
stato e dell'atlante su DB e' in ``_Scrittore`` ed e' usata SOLO dalla action
notturna con ``--scrivi-db``. ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("genera_atlante")

BUCKETS: Tuple[str, ...] = tuple(f"{lo}-{lo + 5}" for lo in range(0, 90, 5))
GOAL_KEYS: Tuple[str, ...] = ("0", "1", "2", "3+")

K_LEAGUE = 1500.0            # partite-minuto: shrinkage della cella di lega
K_TEAM = 12.0                # partite: shrinkage del profilo squadra
# 25/09 (ordine dell'utente: "l'atlante deve adattarsi a OGNI lega che
# abbiamo nel DB"): ogni lega con dati ha la SUA griglia, shrinkata verso il
# globale con lo stesso K_LEAGUE (con pochi dati la griglia ~ globale, con
# molti ~ dati della lega). La soglia qui sotto NON esclude piu' nessuna lega:
# serve SOLO a (a) scegliere le leghe su cui si stima il GLOBALE (campione
# affidabile, come nel v1), (b) il livello SQUADRE (i profili si shrinkano
# verso il side_rate di una lega affidabile) e (c) l'etichetta di confidenza.
MIN_FIXTURES_LEAGUE = 300    # lega "affidabile": globale, livello squadre, confidenza alta
MIN_FIXTURES_MEDIA = 100     # confidenza di lega "media" da qui, "bassa" sotto
# confidenza della CELLA dal peso dei dati della lega nella stima shrinkata,
# w = n / (n + K_LEAGUE): alta se w >= 0.5 (n >= K), media se w >= 0.2
# (n >= K/4 = 375 partite-minuto), bassa sotto.
PESO_ALTA = 0.5
PESO_MEDIA = 0.2
# il globale si stima dallo stato solo se le leghe affidabili sommano almeno
# tante partite; sotto si usa il globale del SEME (v3, 53.187 partite) e lo si
# dichiara. 10.000 partite: la cella globale meno popolata (85-90, 3+ gol)
# avrebbe ~4.500 partite-minuto -> errore standard ~0,5 punti su p~0,12.
MIN_FIXTURES_GLOBALE = 10000
MIN_TEAM_MATCHES = 10        # sotto: la squadra non entra in by_team
MIN_H2H = 3                  # scontri diretti minimi per h2h_hint
M_MAX = 87                   # ogni finestra di 3' cade in [1, 90]
COPERTURA_MIN = 0.60         # quota minima di partite con gol che hanno gli eventi (v1)
LOTTO_GOL = 200              # fixture_id per GET dei gol nel bootstrap (indice fixture_id)
VERSIONE = "hazard_atlas_v3"


def _bucket(minute: int) -> str:
    m = max(0, min(89, int(minute)))
    lo = (m // 5) * 5
    return f"{lo}-{lo + 5}"


def _bucket_gol(minute: int) -> str:
    """Bucket di un GOL (minuto 1..90): convenzione del v1, (lo, lo+5]. Il
    gol al 5' sta in '0-5', al 45' (recupero compreso) in '40-45', al 90' in
    '85-90'. Verificato sul v2 (side_rate della Premier identici)."""
    return _bucket(max(1, min(90, int(minute))) - 1)


def _gk(goals: int) -> str:
    return "3+" if goals >= 3 else str(max(0, int(goals)))


def _int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1) la partita: dalle righe del DB alla sequenza dei gol
# ---------------------------------------------------------------------------
def sequenza_partita(match: Dict[str, Any], goal_rows: Iterable[Dict[str, Any]]
                     ) -> Tuple[Optional[Dict[str, Any]], str]:
    """(sequenza, motivo). Sequenza None = partita scartata, motivo dice perche'.

    ``match`` ha le colonne di ``matches``; ``goal_rows`` quelle di
    ``match_events`` con ``event_type == 'Goal'`` della stessa partita.
    Autogol: il lato si prende dal team_id dell'evento; se i gol per lato non
    tornano col punteggio e l'evento e' un autogol, si attribuisce all'altra
    squadra (la fonte non e' uniforme: e' una correzione dichiarata)."""
    if str(match.get("status_short") or "") != "FT":
        return None, "non_ft"
    fid = _int(match.get("fixture_id"))
    hid, aid = _int(match.get("home_team_id")), _int(match.get("away_team_id"))
    gh, ga = _int(match.get("goals_home")), _int(match.get("goals_away"))
    if fid is None or hid is None or aid is None or gh is None or ga is None:
        return None, "dati_mancanti"
    goals: List[List[Any]] = []
    for r in goal_rows:
        if str(r.get("event_type") or "") != "Goal":
            continue
        det = str(r.get("detail") or "")
        if det == "Missed Penalty":
            continue
        mi = _int(r.get("minute"))
        tid = _int(r.get("team_id"))
        if mi is None or tid not in (hid, aid):
            return None, "evento_incoerente"
        side = "h" if tid == hid else "a"
        goals.append([min(90, max(1, mi)), side, det == "Own Goal"])
    if len(goals) != gh + ga:
        return None, "gol_diversi_dal_punteggio"
    nh = sum(1 for g in goals if g[1] == "h")
    if nh != gh:
        # prova l'altra convenzione per gli autogol
        flip = [[g[0], ("a" if g[1] == "h" else "h") if g[2] else g[1], g[2]] for g in goals]
        if sum(1 for g in flip if g[1] == "h") == gh:
            goals = flip
        else:
            return None, "lati_incoerenti"
    goals.sort(key=lambda g: g[0])
    hth, hta = _int(match.get("halftime_home")), _int(match.get("halftime_away"))
    return {
        "fixture_id": fid,
        "league_id": _int(match.get("league_id")),
        "season": _int(match.get("season_year")),
        "date": str(match.get("fixture_date") or "")[:10] or None,
        "home_id": hid, "away_id": aid,
        "home_name": match.get("home_team_name"), "away_name": match.get("away_team_name"),
        "ft": [gh, ga],
        "ht": [hth, hta] if hth is not None and hta is not None else None,
        "goals": [[g[0], g[1]] for g in goals],
    }, "ok"


# ---------------------------------------------------------------------------
# 2) stato grezzo per lega: conteggi ADDITIVI
# ---------------------------------------------------------------------------
def stato_lega_vuoto(league_id: int, league_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "league_id": int(league_id), "league_name": league_name,
        "n_fixtures": 0, "n_goals": 0, "n_discarded": {},
        "cells": {b: {k: [0, 0, 0] for k in GOAL_KEYS} for b in BUCKETS},
        "side_goals": {b: 0 for b in BUCKETS},
        "teams": {}, "h2h": {}, "seasons": [], "fixtures": [],
        "last_fixture_date": None, "updated_at": None,
        # 25/09 sera: lo stato del v4 (atlante_v4) cresce INSIEME al v3, dalle
        # stesse righe. Uno stato di prima (senza "v4") non si completa a
        # pezzi: la lega la ricalcola per intero il motore a domanda.
        "v4": _v4_vuoto(),
    }


def _v4_vuoto() -> Optional[Dict[str, Any]]:
    from . import atlante_v4 as V4          # pigro: numpy solo quando serve
    return V4.stato_v4_vuoto()


def aggiungi_v4(stato: Dict[str, Any], match: Dict[str, Any], goal_rows: List[Dict[str, Any]], *,
                affidabile: Optional[bool] = None) -> bool:
    """Somma la partita al blocco v4 dello stato (SOLO dopo che
    ``aggiungi_partita`` l'ha contata nel v3: l'idempotenza e' la sua).

    ``affidabile`` (la stagione registra il recupero dei gol? reperto 6 del
    25/09): nel bootstrap lo decide la stagione INTERA; None (incrementale) =
    dai conteggi CUMULATI della stagione nello stato, questa partita compresa.
    Stato senza "v4" (di prima del collegamento): niente, e False."""
    v4 = stato.get("v4")
    if not isinstance(v4, dict):
        return False
    from . import atlante_v4 as V4
    p, motivo = V4.partita_v4(match, goal_rows)
    if p is None:
        sc = v4.setdefault("scarti", {})
        sc[motivo] = int(sc.get(motivo, 0)) + 1
        return False
    s = str(p.season)
    if affidabile is None:
        con, tot = V4.quota_gol_con_extra(goal_rows)
        q = v4.setdefault("quota_extra", {}).setdefault(s, [0, 0])
        q[0] += int(con)
        q[1] += int(tot)
        affidabile = V4.affidabile_da_quota(q[0], q[1])
    v4.setdefault("affidabile", {})[s] = bool(affidabile)
    return V4.aggiungi_partita_v4(v4, p, set(), recupero_affidabile=bool(affidabile), registra_fixture=False)


def scarta(stato: Dict[str, Any], motivo: str) -> None:
    d = stato.setdefault("n_discarded", {})
    d[motivo] = int(d.get(motivo, 0)) + 1


def aggiungi_partita(stato: Dict[str, Any], seq: Dict[str, Any],
                     visti: Optional[set] = None) -> bool:
    """Somma una partita allo stato della lega. False se gia' contata."""
    fid = int(seq["fixture_id"])
    if visti is None:
        visti = set(stato.get("fixtures") or [])
    if fid in visti:
        return False
    minuti = [int(g[0]) for g in seq["goals"]]
    cells = stato["cells"]
    for m in range(0, M_MAX + 1):
        b = _bucket(m)
        gk = _gk(sum(1 for x in minuti if x <= m))
        c = cells[b][gk]
        c[0] += 1
        if any(m < x <= m + 3 for x in minuti):
            c[1] += 1
        if any(m < x <= m + 2 for x in minuti):
            c[2] += 1
    for mi, side in seq["goals"]:
        stato["side_goals"][_bucket_gol(mi)] += 1
    # profili squadra (att/def per bucket), nessuna distinzione casa/trasferta
    for tid, nome, lato in ((seq["home_id"], seq["home_name"], "h"),
                            (seq["away_id"], seq["away_name"], "a")):
        t = stato["teams"].setdefault(str(tid), {"name": nome, "n": 0,
                                                  "att": {b: 0 for b in BUCKETS},
                                                  "def": {b: 0 for b in BUCKETS}})
        if nome:
            t["name"] = nome
        t["n"] += 1
        for mi, side in seq["goals"]:
            t["att" if side == lato else "def"][_bucket_gol(mi)] += 1
    # scontri diretti, orientati come id_min - id_max
    a, b_ = sorted((int(seq["home_id"]), int(seq["away_id"])))
    key = f"{a}-{b_}"
    h = stato["h2h"].setdefault(key, {"team_a": {"id": a, "name": None},
                                      "team_b": {"id": b_, "name": None},
                                      "ft": {}, "ht": {}})
    home_is_a = int(seq["home_id"]) == a
    nomi = {int(seq["home_id"]): seq["home_name"], int(seq["away_id"]): seq["away_name"]}
    h["team_a"]["name"] = nomi.get(a) or h["team_a"]["name"]
    h["team_b"]["name"] = nomi.get(b_) or h["team_b"]["name"]
    for chiave, sc in (("ft", seq["ft"]), ("ht", seq["ht"])):
        if not sc:
            continue
        s = f"{sc[0]}-{sc[1]}" if home_is_a else f"{sc[1]}-{sc[0]}"
        h[chiave][s] = int(h[chiave].get(s, 0)) + 1
    stato["n_fixtures"] += 1
    stato["n_goals"] += len(minuti)
    if seq.get("season") is not None and seq["season"] not in stato["seasons"]:
        stato["seasons"] = sorted(stato["seasons"] + [seq["season"]])
    if seq.get("date") and (stato.get("last_fixture_date") or "") < seq["date"]:
        stato["last_fixture_date"] = seq["date"]
    stato.setdefault("fixtures", []).append(fid)
    visti.add(fid)
    return True


# ---------------------------------------------------------------------------
# 3) assemblaggio: dallo stato grezzo all'atlante (formato v1/v2)
# ---------------------------------------------------------------------------
def _r(x: float) -> float:
    return round(float(x), 5)


def confidenza_lega(n_fixtures: int, soglia: int = MIN_FIXTURES_LEAGUE) -> str:
    """'alta' (>= soglia partite: lega affidabile), 'media' (>= MIN_FIXTURES_MEDIA), 'bassa'."""
    n = int(n_fixtures or 0)
    if n >= soglia:
        return "alta"
    return "media" if n >= MIN_FIXTURES_MEDIA else "bassa"


def confidenza_cella(n: int, k: float = K_LEAGUE) -> str:
    """Dal peso dei dati della lega nella cella shrinkata, w = n / (n + K)."""
    n = max(0, int(n or 0))
    w = n / (n + float(k)) if (n + float(k)) > 0 else 0.0
    if w >= PESO_ALTA:
        return "alta"
    return "media" if w >= PESO_MEDIA else "bassa"


def assembla(stati: Dict[str, Dict[str, Any]], *, generated_at: str,
             watermark: Optional[int] = None,
             min_fixtures_league: int = MIN_FIXTURES_LEAGUE,
             seme: Optional[Dict[str, Any]] = None,
             min_fixtures_globale: int = MIN_FIXTURES_GLOBALE) -> Dict[str, Any]:
    """L'atlante completo dagli stati grezzi di TUTTE le leghe.

    25/09: OGNI lega con almeno una partita contata entra in ``by_league``
    (griglia shrinkata verso il globale, stesso K); ``min_fixtures_league``
    decide solo il campione del globale, il livello squadre e la confidenza.
    ``seme`` (un atlante gia' fatto, il v3): se le leghe affidabili dello stato
    non bastano a stimare il globale (< ``min_fixtures_globale`` partite) si
    usa il globale del seme, dichiarato in meta; le leghe/squadre/scontri del
    seme che lo stato non ha ancora restano disponibili (marcate ``da_seme``).
    Senza seme il globale si stima come prima."""
    coperte = {k: s for k, s in stati.items() if int(s.get("n_fixtures") or 0) >= min_fixtures_league}
    base = coperte or stati        # il globale si stima sul campione coperto (come il v1)
    tot_coperte = sum(int(s.get("n_fixtures") or 0) for s in coperte.values())
    usa_seme = (bool(seme) and isinstance((seme or {}).get("global"), dict)
                and tot_coperte < int(min_fixtures_globale))
    # --- globale (non shrinkato)
    glob_raw = {b: {k: [0, 0, 0] for k in GOAL_KEYS} for b in BUCKETS}
    for s in base.values():
        for b in BUCKETS:
            for k in GOAL_KEYS:
                c = s["cells"][b][k]
                g = glob_raw[b][k]
                g[0] += c[0]
                g[1] += c[1]
                g[2] += c[2]
    glob: Dict[str, Any] = {}
    for b in BUCKETS:
        glob[b] = {}
        for k in GOAL_KEYS:
            n, s3, s2 = glob_raw[b][k]
            # cella vuota: None come nel v1 (mai uno 0.0 che sembra un dato)
            glob[b][k] = {"p_goal_next_3min": _r(s3 / n) if n else None,
                          "p_goal_next_2min": _r(s2 / n) if n else None, "n": n}
    if usa_seme:
        # globale del SEME: le leghe affidabili dello stato sono troppo poche
        # per stimarlo. Stesso formato, celle copiate come sono.
        vuota = {"p_goal_next_3min": None, "p_goal_next_2min": None, "n": 0}
        glob = {b: {k: dict(((seme["global"].get(b) or {}).get(k) or vuota))
                    for k in GOAL_KEYS} for b in BUCKETS}
    # --- leghe (shrinkate verso il globale): TUTTE quelle con dati
    by_league: Dict[str, Any] = {}
    side_rate: Dict[str, Dict[str, float]] = {}
    for lid, s in stati.items():
        nf = int(s.get("n_fixtures") or 0)
        if nf <= 0:
            continue                 # nessuna partita contata: nessuna griglia da inventare
        sr = {b: _r(s["side_goals"][b] / (2.0 * nf)) for b in BUCKETS}
        affidabile = lid in coperte
        if affidabile:
            side_rate[lid] = sr      # riferimento dei profili squadra: solo leghe affidabili
        grid: Dict[str, Any] = {}
        for b in BUCKETS:
            grid[b] = {}
            for k in GOAL_KEYS:
                n, s3, s2 = s["cells"][b][k]
                gp = glob[b][k]
                if gp.get("p_goal_next_3min") is None:
                    grid[b][k] = {"p_goal_next_3min": None, "p_goal_next_2min": None, "n": n,
                                  "conf": confidenza_cella(n)}
                    continue
                p3 = (s3 + K_LEAGUE * gp["p_goal_next_3min"]) / (n + K_LEAGUE)
                p2 = (s2 + K_LEAGUE * gp["p_goal_next_2min"]) / (n + K_LEAGUE)
                grid[b][k] = {"p_goal_next_3min": _r(p3), "p_goal_next_2min": _r(p2), "n": n,
                              "conf": confidenza_cella(n)}
        by_league[lid] = {"meta": {
            "league_name": s.get("league_name"), "n_fixtures": nf,
            "n_goals": int(s["n_goals"]),
            "n_discarded_mismatch": int(sum((s.get("n_discarded") or {}).values())),
            "seasons": list(s.get("seasons") or []),
            "side_rate_per_bucket": sr,
            "last_fixture_date": s.get("last_fixture_date"),
            "updated_at": s.get("updated_at"),
            "affidabile": affidabile,
            "confidenza": confidenza_lega(nf, min_fixtures_league),
        }, "grid": grid}
    # --- squadre: somma su tutte le leghe, lega di riferimento = quella con
    # piu' partite (se coperta), shrink verso il suo side_rate
    squadre: Dict[str, Dict[str, Any]] = {}
    for lid, s in stati.items():
        for tid, t in (s.get("teams") or {}).items():
            q = squadre.setdefault(tid, {"name": t.get("name"), "n": 0, "per_lega": {},
                                         "att": {b: 0 for b in BUCKETS},
                                         "def": {b: 0 for b in BUCKETS}})
            q["n"] += int(t["n"])
            q["per_lega"][lid] = q["per_lega"].get(lid, 0) + int(t["n"])
            if t.get("name"):
                q["name"] = t["name"]
            for b in BUCKETS:
                q["att"][b] += int(t["att"].get(b, 0))
                q["def"][b] += int(t["def"].get(b, 0))
    glob_sr = {b: 0.0 for b in BUCKETS}
    tot_f = sum(int(s["n_fixtures"]) for s in base.values())
    if tot_f:
        for b in BUCKETS:
            glob_sr[b] = sum(int(s["side_goals"][b]) for s in base.values()) / (2.0 * tot_f)
    by_team: Dict[str, Any] = {}
    fallback = 0
    for tid, q in squadre.items():
        if q["n"] < MIN_TEAM_MATCHES:
            fallback += 1
            continue
        lega = max(q["per_lega"].items(), key=lambda kv: (kv[1], kv[0]))[0]
        sr = side_rate.get(lega, glob_sr)
        by_team[tid] = {
            "team_name": q["name"], "league_id": int(lega), "n_matches": q["n"],
            "att_goals_per_match_by_bucket": {
                b: _r((q["att"][b] + K_TEAM * sr[b]) / (q["n"] + K_TEAM)) for b in BUCKETS},
            "def_goals_per_match_by_bucket": {
                b: _r((q["def"][b] + K_TEAM * sr[b]) / (q["n"] + K_TEAM)) for b in BUCKETS},
        }
    # --- scontri diretti: somma su tutte le leghe (coppe comprese)
    h2h_raw: Dict[str, Dict[str, Any]] = {}
    for s in stati.values():
        for key, h in (s.get("h2h") or {}).items():
            d = h2h_raw.setdefault(key, {"team_a": dict(h["team_a"]), "team_b": dict(h["team_b"]),
                                         "ft": {}, "ht": {}})
            for ch in ("ft", "ht"):
                for sc, k in (h.get(ch) or {}).items():
                    d[ch][sc] = d[ch].get(sc, 0) + int(k)
    h2h: Dict[str, Any] = {}
    for key, d in h2h_raw.items():
        n = sum(d["ft"].values())
        if n < MIN_H2H:
            continue
        h2h[key] = {"n_meetings": n, "team_a": d["team_a"], "team_b": d["team_b"],
                    "ft_scores_a_b": dict(sorted(d["ft"].items(), key=lambda kv: -kv[1])),
                    "ht_scores_a_b": dict(sorted(d["ht"].items(), key=lambda kv: -kv[1]))}
    # --- SEME: cio' che lo stato non ha ancora resta disponibile, dichiarato
    n_da_seme = 0
    if seme:
        for lid, blk in (seme.get("by_league") or {}).items():
            if lid in by_league or not isinstance(blk, dict):
                continue
            blk = json.loads(json.dumps(blk))          # copia: il seme non si tocca
            meta_s = blk.setdefault("meta", {})
            nf_s = int(meta_s.get("n_fixtures") or 0)
            meta_s["da_seme"] = True
            meta_s.setdefault("affidabile", nf_s >= min_fixtures_league)
            meta_s.setdefault("confidenza", confidenza_lega(nf_s, min_fixtures_league))
            by_league[lid] = blk
            n_da_seme += 1
        for tid, t in (seme.get("by_team") or {}).items():
            if tid not in by_team and str(t.get("league_id")) not in stati:
                by_team[tid] = dict(t, da_seme=True)
        for key, h in (seme.get("h2h_hint") or {}).items():
            h2h.setdefault(key, h)
    n_used = sum(int(s["n_fixtures"]) for s in base.values())
    n_goals = sum(int(s["n_goals"]) for s in base.values())
    per_lega = {lid: {"league_name": s.get("league_name"), "n_fixtures": int(s["n_fixtures"]),
                      "n_goals": int(s["n_goals"]),
                      "coperta": lid in by_league and not (by_league[lid]["meta"] or {}).get("da_seme"),
                      "affidabile": lid in coperte,
                      "confidenza": confidenza_lega(int(s["n_fixtures"]), min_fixtures_league),
                      "seasons": list(s.get("seasons") or []),
                      "last_fixture_date": s.get("last_fixture_date"),
                      "updated_at": s.get("updated_at"),
                      "n_discarded": dict(s.get("n_discarded") or {})}
                for lid, s in sorted(stati.items(), key=lambda kv: int(kv[0]))}
    meta = {
        "name": VERSIONE, "generated_at": generated_at,
        "generator": "Betfair/stream/scalper/genera_atlante.py",
        "purpose": "P(gol imminente) per stato (minuto, gol correnti), gerarchico "
                   "squadra->lega->globale. Rigenerato in automatico, incrementale per lega.",
        "n_fixtures_used": n_used, "n_goals": n_goals,
        "avg_goals_per_match": round(n_goals / n_used, 4) if n_used else None,
        "n_leagues": len(by_league), "n_leagues_in_state": len(stati),
        "n_leagues_affidabili": len(coperte), "n_leagues_da_seme": n_da_seme,
        "globale": ({"fonte": "seme", "seme": (seme.get("meta") or {}).get("name"),
                     "seme_generated_at": (seme.get("meta") or {}).get("generated_at"),
                     "seme_n_fixtures": (seme.get("meta") or {}).get("n_fixtures_used"),
                     "motivo": f"leghe affidabili dello stato: {tot_coperte} partite "
                               f"< {int(min_fixtures_globale)}"}
                    if usa_seme else {"fonte": "stato", "n_fixtures": tot_coperte or
                                      sum(int(s.get("n_fixtures") or 0) for s in base.values())}),
        "confidenza": {"lega": f"alta >= {min_fixtures_league} partite, media >= "
                               f"{MIN_FIXTURES_MEDIA}, bassa sotto",
                       "cella": f"peso della lega w=n/(n+K): alta >= {PESO_ALTA}, "
                                f"media >= {PESO_MEDIA}, bassa sotto"},
        "n_teams": len(by_team), "n_teams_fallback_to_league": fallback,
        "n_h2h_pairs": len(h2h),
        "watermark_event_id": watermark,
        "shrinkage": {"K_league_fixture_minutes": K_LEAGUE, "K_team_matches": K_TEAM,
                      "formula": "p_shrunk = (successi + K * p_parent) / (n + K)"},
        "fallback_min_n_team_matches": MIN_TEAM_MATCHES,
        "min_fixtures_league": min_fixtures_league,
        "method": "Stima empirica diretta (metodo del v1): per ogni partita FT sequenza "
                  "minuti-gol; per ogni minuto m in 0..87 stato=(bucket 5' di m, gol con "
                  "minuto<=m); P_k = quota di partite-minuto dello stato con >=1 gol in (m, m+k].",
        "approximations": [
            "minute_extra ignorato: gol nel recupero clampati a 45/90.",
            "Solo status_short=FT; scartate le partite con n. eventi-gol != punteggio finale.",
            "'Missed Penalty' escluso; autogol: lato dall'evento, corretto se i lati non tornano.",
            "Nessuna distinzione casa/trasferta nei profili squadra.",
            "Il globale e' stimato sulle leghe affidabili (>= min_fixtures_league partite); "
            "ogni lega con dati ha la sua griglia shrinkata verso il globale.",
            "Livello squadre solo su lega affidabile: i profili si shrinkano verso il "
            "side_rate di una lega affidabile, altrimenti verso quello globale.",
        ],
        "per_league": per_lega,
    }
    out = {"meta": meta, "global": glob, "by_league": by_league, "by_team": by_team,
           "h2h_hint": h2h}
    # 25/09 sera - ATLANTE v4 (A*, validato fuori campione): blocco accanto ai
    # v3, dagli stati v4 delle leghe che lo hanno. I blocchi v3 restano (ripiego
    # dichiarato dei consumatori, h2h_hint di Omega, seme del globale v3).
    v4 = assembla_blocco_v4(stati, generated_at=generated_at)
    if v4 is not None:
        out["v4"] = v4
        meta["v4"] = {k: v4["meta"].get(k) for k in ("name", "stagione_rif", "n_leghe",
                                                    "n_leghe_affidabili", "n_partite_affidabili",
                                                    "globale_solido", "recupero_2T_noto")}
    return out


def assembla_blocco_v4(stati: Dict[str, Dict[str, Any]], *, generated_at: str) -> Optional[Dict[str, Any]]:
    """Il blocco ``atlas['v4']`` dagli stati v4 (``stato['v4']``) delle leghe
    che lo hanno e hanno almeno una partita. None se nessuna. La stagione a
    peso 1 e' quella DOPO l'ultima contata (come nel banco: addestra <= S,
    riferimento S + 1), cosi' i pesi per eta' sono quelli validati."""
    vista: Dict[str, Dict[str, Any]] = {}
    for lid, st in stati.items():
        v4 = st.get("v4")
        if not isinstance(v4, dict):
            continue
        stag = v4.get("stagioni") or {}
        if not any(int((b or {}).get("n_fixtures") or 0) > 0 for b in stag.values()):
            continue
        vista[lid] = {"league_name": st.get("league_name"), "stagioni": stag}
    if not vista:
        return None
    from . import atlante_v4 as V4
    rif = max(int(x) for v in vista.values() for x in v["stagioni"]) + 1
    return V4.assembla_v4(vista, generated_at=generated_at, stagione_rif=rif)


# ---------------------------------------------------------------------------
# 4) lettura del DB (SOLO GET) con ritentativi pazienti
# ---------------------------------------------------------------------------
class LettoreDB:
    """Client PostgREST in SOLA LETTURA. Ritenta su 5xx/52x/57014 con attese
    crescenti (il DB puo' essere in manutenzione: un errore non vuol dire che
    il dato manca)."""

    def __init__(self, url: str, key: str, *, attese: Tuple[float, ...] = (5, 30, 120, 300),
                 timeout: float = 120.0, sleep: Callable[[float], None] = time.sleep,
                 pausa: float = 0.1) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.pausa = pausa
        self.attese = attese
        self.timeout = timeout
        self.sleep = sleep
        self.n_richieste = 0
        self.n_righe = 0

    def get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        q = urllib.parse.urlencode(params, safe="(),.*:!")
        for tent in range(len(self.attese) + 1):
            req = urllib.request.Request(f"{self.url}/rest/v1/{table}?{q}", method="GET")
            req.add_header("apikey", self.key)
            req.add_header("Authorization", "Bearer " + self.key)
            try:
                self.n_richieste += 1
                if self.pausa > 0:
                    self.sleep(self.pausa)      # passo gentile: il DB ha un budget di IO
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    rows = json.loads(r.read().decode("utf-8"))
                    self.n_righe += len(rows)
                    return rows
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as ex:
                code = getattr(ex, "code", None)
                if code is not None and code < 500:
                    raise
                if tent >= len(self.attese):
                    raise
                logger.warning("[atlante] %s KO (%s), ritento tra %ss", table, code or ex,
                               self.attese[tent])
                self.sleep(self.attese[tent])
        raise RuntimeError("irraggiungibile")

    def tutte(self, table: str, params: Dict[str, str], *, chiave: str,
              pagina: int = 1000) -> List[Dict[str, Any]]:
        """Paginazione a CHIAVE (``chiave`` > ultimo visto, ordinata): niente
        OFFSET, che sui tavoloni fa scansioni e statement timeout."""
        out: List[Dict[str, Any]] = []
        ultimo: Optional[Any] = None
        while True:
            p = dict(params)
            p["order"] = f"{chiave}.asc"
            p["limit"] = str(pagina)
            if ultimo is not None:
                p[chiave] = f"gt.{ultimo}"
            rows = self.get(table, p)
            out.extend(rows)
            if len(rows) < pagina:
                return out
            ultimo = rows[-1][chiave]


# 25/09 sera (atlante v4 collegato): + la durata del RECUPERO DEL 2T
# (``raw_json.fixture.status.extra`` di API-Football, nel DB dal 2024; nessuna
# colonna vera la porta, ``fixtures_backfill`` salva solo short/long/elapsed).
# Stesse righe, ~10 byte in piu' a riga nella risposta (misura nel referto
# ATLANTE_V4_COLLEGATO). I gol hanno gia' ``minute_extra`` in COLONNE_GOL.
COLONNE_MATCH = ("fixture_id,league_id,season_year,fixture_date,status_short,home_team_id,"
                 "home_team_name,away_team_id,away_team_name,goals_home,goals_away,"
                 "halftime_home,halftime_away,extra:raw_json->fixture->status->extra")
COLONNE_GOL = "id,fixture_id,league_id,season_year,team_id,event_type,detail,minute,minute_extra"


def _sequenze(matches: List[Dict[str, Any]], gol: List[Dict[str, Any]],
              stati: Dict[str, Dict[str, Any]], nomi: Dict[str, Optional[str]],
              adesso: str, *, solo_leghe_in_stato: bool = False,
              affidabile_v4: Optional[bool] = None) -> Dict[str, int]:
    """Aggiunge le partite agli stati delle loro leghe. Ritorna i conteggi.

    ``solo_leghe_in_stato``: le partite di una lega che lo stato non ha si
    IGNORANO (non si crea una lega senza storico: la aggiunge l'atlante a
    domanda, per intero, quando una sua partita e' da osservare).
    25/09 sera: ogni partita contata nel v3 entra anche nel v4
    (``aggiungi_v4``); ``affidabile_v4`` = decisione della stagione intera
    (bootstrap), None = dai conteggi cumulati (incrementale)."""
    per_fixture: Dict[int, List[Dict[str, Any]]] = {}
    for g in gol:
        fid = _int(g.get("fixture_id"))
        if fid is not None:
            per_fixture.setdefault(fid, []).append(g)
    visti: Dict[str, set] = {}
    conti = {"aggiunte": 0, "gia_contate": 0, "scartate": 0, "non_ft": 0}
    for m in matches:
        lid = str(_int(m.get("league_id")))
        if lid == "None":
            continue
        stato = stati.get(lid)
        if stato is None:
            if solo_leghe_in_stato:
                conti["fuori_stato"] = conti.get("fuori_stato", 0) + 1
                continue
            stato = stati[lid] = stato_lega_vuoto(int(lid), nomi.get(lid))
        seq, motivo = sequenza_partita(m, per_fixture.get(int(m["fixture_id"]), []))
        if seq is None:
            if motivo == "non_ft":
                conti["non_ft"] += 1
            else:
                conti["scartate"] += 1
                scarta(stato, motivo)
            continue
        if stato.get("fixtures") is None:
            # fail-closed: senza la lista dei gia' contati si conterebbe due volte
            raise RuntimeError(f"fixture_id gia' contati non caricati per la lega {lid}")
        vs = visti.setdefault(lid, set(stato["fixtures"]))
        if aggiungi_partita(stato, seq, vs):
            conti["aggiunte"] += 1
            stato["updated_at"] = adesso
            aggiungi_v4(stato, m, per_fixture.get(int(m["fixture_id"]), []), affidabile=affidabile_v4)
        else:
            conti["gia_contate"] += 1
    return conti


def bootstrap(lettore: LettoreDB, stati: Dict[str, Dict[str, Any]], leghe: List[int],
              stagioni: List[int], nomi: Dict[str, Optional[str]], adesso: str,
              prepara: Optional[Callable[[List[str]], None]] = None) -> Dict[str, int]:
    """Storico per (lega, stagione): una tantum, o per una lega nuova."""
    tot = {"aggiunte": 0, "gia_contate": 0, "scartate": 0, "non_ft": 0}
    if prepara is not None:
        prepara([str(x) for x in leghe])
    for lid in leghe:
        for anno in stagioni:
            matches = lettore.tutte("matches", {"select": COLONNE_MATCH,
                                                "league_id": f"eq.{lid}",
                                                "season_year": f"eq.{anno}"}, chiave="fixture_id")
            chiave_l = str(lid)
            if chiave_l not in stati:
                stati[chiave_l] = stato_lega_vuoto(int(lid), nomi.get(chiave_l))
            if not matches:
                # stagione dichiarata ma senza partite nel DB: si ricorda, non si conta
                vuote = stati[chiave_l].setdefault("stagioni_vuote", [])
                if anno not in vuote:
                    vuote.append(anno)
                continue
            # 25/09: i gol si leggono PER fixture_id (indice su
            # match_events.fixture_id, misurato 2,6 ms per 200 partite il
            # 21/09 - vedi Ai Engine/ai_engine/db_adapter.py) e non per
            # (league_id, season_year), che su match_events non ha indice e
            # costringe a scorrere la chiave primaria su 10 milioni di righe.
            # Stesse righe (i gol delle partite della stagione), meno IO.
            gol = []
            fids_stagione = sorted({int(m["fixture_id"]) for m in matches
                                    if _int(m.get("fixture_id")) is not None})
            for i in range(0, len(fids_stagione), LOTTO_GOL):
                lista = ",".join(str(f) for f in fids_stagione[i:i + LOTTO_GOL])
                gol.extend(lettore.tutte("match_events", {"select": COLONNE_GOL,
                                                          "fixture_id": f"in.({lista})",
                                                          "event_type": "eq.Goal"}, chiave="id"))
            # COPERTURA della stagione: se gli eventi mancano per la maggior
            # parte delle partite con gol, la stagione NON si usa. Altrimenti
            # resterebbero solo gli 0-0 (che non hanno gol da registrare) e
            # l'hazard verrebbe spinto in basso. Soglia del v1: 60%.
            con_gol = {int(m["fixture_id"]) for m in matches
                       if str(m.get("status_short")) == "FT"
                       and (_int(m.get("goals_home")) or 0) + (_int(m.get("goals_away")) or 0) > 0}
            con_eventi = {_int(g.get("fixture_id")) for g in gol}
            cop = (len(con_gol & con_eventi) / len(con_gol)) if con_gol else 0.0
            if cop < COPERTURA_MIN:
                scartate = stati[chiave_l].setdefault("stagioni_scartate", {})
                if str(anno) not in scartate:      # un nuovo tentativo non si conta due volte
                    scarta(stati[chiave_l], "stagione_senza_eventi")
                scartate[str(anno)] = round(cop, 3)
                logger.info("[atlante] lega %s stagione %s SALTATA: eventi sul %.0f%% delle "
                            "partite con gol", lid, anno, cop * 100)
                continue
            # 25/09 sera - v4: la stagione registra il minuto di recupero dei
            # gol? (reperto 6: 2025 europeo senza minute_extra). Si decide
            # sulla stagione INTERA, gia' letta; i conteggi restano nello stato
            # (l'incrementale continua da li'). Stesse righe, nessuna lettura.
            aff_v4 = None
            v4 = stati[chiave_l].get("v4")
            if isinstance(v4, dict):
                from . import atlante_v4 as V4
                con, tot_e = V4.quota_gol_con_extra(gol)
                v4.setdefault("quota_extra", {})[str(anno)] = [int(con), int(tot_e)]
                aff_v4 = V4.affidabile_da_quota(con, tot_e)
            c = _sequenze(matches, gol, stati, nomi, adesso, affidabile_v4=aff_v4)
            for k in tot:
                tot[k] += c[k]
            # 25/09: stagione ACQUISITA (serve all'atlante a domanda per sapere
            # quali stagioni nuove, comparse in coverage, mancano ancora)
            acq = stati[chiave_l].setdefault("stagioni_acquisite", [])
            if anno not in acq:
                stati[chiave_l]["stagioni_acquisite"] = sorted(acq + [anno])
            (stati[chiave_l].get("stagioni_scartate") or {}).pop(str(anno), None)
            logger.info("[atlante] bootstrap lega %s stagione %s: %s", lid, anno, c)
    return tot


def stagioni_con_eventi(lettore: LettoreDB, leghe: List[int]) -> Dict[str, List[int]]:
    """Stagioni con ``fixtures_events = true`` in ``api_coverage_by_season``,
    per lega. UNA richiesta ogni 150 leghe, due colonne: le stagioni senza
    eventi dichiarati non si scaricano nemmeno (prima si scaricavano e poi si
    scartavano)."""
    out: Dict[str, List[int]] = {str(int(l)): [] for l in leghe}
    ids = sorted({int(l) for l in leghe})
    for i in range(0, len(ids), 150):
        blocco = ",".join(str(x) for x in ids[i:i + 150])
        for r in lettore.get("api_coverage_by_season", {
                "select": "league_id,season_year,fixtures_events",
                "league_id": f"in.({blocco})", "fixtures_events": "eq.true",
                "limit": "5000"}):
            lid, anno = _int(r.get("league_id")), _int(r.get("season_year"))
            if lid is None or anno is None:
                continue
            out.setdefault(str(lid), []).append(anno)
    return {k: sorted(set(v)) for k, v in out.items()}


def incrementale(lettore: LettoreDB, stati: Dict[str, Dict[str, Any]], watermark: int,
                 nomi: Dict[str, Optional[str]], adesso: str, *, lotto: int = 100,
                 prepara: Optional[Callable[[List[str]], None]] = None,
                 solo_leghe_in_stato: bool = False,
                 ) -> Tuple[int, Dict[str, int], List[str]]:
    """Eventi con id > watermark -> partite toccate -> leghe aggiornate.

    Ritorna (nuova filigrana, conteggi, leghe toccate). Le partite toccate si
    rileggono INTERE (tutti i gol, non solo i nuovi): la sequenza e' completa
    e l'idempotenza per fixture_id impedisce doppi conteggi. ``prepara``
    riceve le leghe toccate PRIMA dei conteggi (per caricare dal DB i loro
    fixture_id gia' contati). ``solo_leghe_in_stato`` (25/09, rete di
    sicurezza notturna dell'atlante a domanda): si leggono e si aggiornano
    SOLO le partite delle leghe gia' nello stato; la filigrana avanza lo
    stesso."""
    nuovi = lettore.tutte("match_events", {"select": "id,fixture_id,league_id",
                                           "id": f"gt.{int(watermark)}"}, chiave="id")
    if not nuovi:
        return int(watermark), {"aggiunte": 0, "gia_contate": 0, "scartate": 0, "non_ft": 0}, []
    nuova = max(int(r["id"]) for r in nuovi)
    if solo_leghe_in_stato:
        nuovi = [r for r in nuovi if str(_int(r.get("league_id"))) in stati]
    if prepara is not None:
        prepara(sorted({str(_int(r.get("league_id"))) for r in nuovi} - {"None"}))
    fids = sorted({int(r["fixture_id"]) for r in nuovi if r.get("fixture_id") is not None})
    tot = {"aggiunte": 0, "gia_contate": 0, "scartate": 0, "non_ft": 0}
    toccate: set = set()
    for i in range(0, len(fids), lotto):
        blocco = fids[i:i + lotto]
        lista = ",".join(str(f) for f in blocco)
        matches = lettore.get("matches", {"select": COLONNE_MATCH,
                                          "fixture_id": f"in.({lista})"})
        gol = lettore.get("match_events", {"select": COLONNE_GOL,
                                           "fixture_id": f"in.({lista})",
                                           "event_type": "eq.Goal"})
        c = _sequenze(matches, gol, stati, nomi, adesso, solo_leghe_in_stato=solo_leghe_in_stato)
        for k in tot:
            tot[k] += c[k]
        toccate.update(str(_int(m.get("league_id"))) for m in matches
                       if not solo_leghe_in_stato or str(_int(m.get("league_id"))) in stati)
    return nuova, tot, sorted(t for t in toccate if t != "None")


# ---------------------------------------------------------------------------
# 5) stato: file locale (sviluppo) o DB (action notturna)
# ---------------------------------------------------------------------------
def leggi_stato_file(path: str) -> Tuple[Dict[str, Dict[str, Any]], int]:
    if not os.path.exists(path):
        return {}, 0
    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    return d.get("leghe") or {}, int(d.get("watermark_event_id") or 0)


def scrivi_json_atomico(path: str, obj: Any) -> None:
    """Scrittura ATOMICA (tmp + os.replace): un lettore non vede mai un file a meta'."""
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=True, separators=(",", ":"))
    os.replace(tmp, path)


def leggi_stato_db(lettore: LettoreDB) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """Stati grezzi di TUTTE le leghe (SENZA la lista dei fixture_id, che e'
    la parte pesante e serve solo per le leghe toccate: ``carica_fixtures``)."""
    rows = lettore.tutte("hazard_atlas_leghe", {"select": "league_id,stato"}, chiave="league_id")
    stati = {str(r["league_id"]): r["stato"] for r in rows if isinstance(r.get("stato"), dict)}
    for s in stati.values():
        s["fixtures"] = None            # non ancora caricati: vedi carica_fixtures
    ult = lettore.get("hazard_atlas", {"select": "watermark_event_id",
                                       "order": "generated_at.desc", "limit": "1"})
    wm = int(ult[0]["watermark_event_id"] or 0) if ult else 0
    return stati, wm


def carica_fixtures(lettore: LettoreDB, stati: Dict[str, Dict[str, Any]], leghe: List[str]) -> None:
    """fixture_id gia' contati per le leghe indicate (colonna ``fixtures``)."""
    da = [l for l in leghe if l in stati and stati[l].get("fixtures") is None]
    for i in range(0, len(da), 50):
        blocco = ",".join(da[i:i + 50])
        for r in lettore.get("hazard_atlas_leghe", {"select": "league_id,fixtures",
                                                    "league_id": f"in.({blocco})"}):
            stati[str(r["league_id"])]["fixtures"] = list(r.get("fixtures") or [])
    for l in da:
        if stati[l].get("fixtures") is None:
            stati[l]["fixtures"] = []


class _Scrittore:
    """SCRITTURA su DB: solo la action notturna (``--scrivi-db``). Upsert dello
    stato delle SOLE leghe toccate + una riga nuova in ``hazard_atlas``;
    tiene le ultime ``tieni`` versioni."""

    def __init__(self, url: str, key: str) -> None:
        self.url = url.rstrip("/")
        self.key = key

    def _req(self, metodo: str, path: str, corpo: Any = None, prefer: str = "") -> None:
        data = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", data=data, method=metodo)
        req.add_header("apikey", self.key)
        req.add_header("Authorization", "Bearer " + self.key)
        req.add_header("Content-Type", "application/json")
        if prefer:
            req.add_header("Prefer", prefer)
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()

    def salva(self, stati: Dict[str, Dict[str, Any]], toccate: List[str],
              atlas: Dict[str, Any], tieni: int = 7) -> None:
        self.salva_leghe(stati, toccate)
        self.salva_versione(atlas, tieni)

    def salva_leghe(self, stati: Dict[str, Dict[str, Any]], toccate: List[str]) -> int:
        """Upsert per ``league_id`` dello stato grezzo delle leghe indicate
        (solo quelle con la lista dei contati caricata). Ritorna le righe."""
        righe = []
        for l in toccate:
            s = stati.get(l)
            if s is None or s.get("fixtures") is None:
                continue          # mai scrivere uno stato con la lista non caricata
            righe.append({"league_id": int(l), "league_name": s.get("league_name"),
                          "n_fixtures": int(s["n_fixtures"]),
                          "last_fixture_date": s.get("last_fixture_date"),
                          "updated_at": s.get("updated_at"),
                          "stato": {k: v for k, v in s.items() if k != "fixtures"},
                          "fixtures": s["fixtures"]})
        for i in range(0, len(righe), 20):
            self._req("POST", "hazard_atlas_leghe?on_conflict=league_id", righe[i:i + 20],
                      "resolution=merge-duplicates,return=minimal")
        return len(righe)

    def salva_versione(self, atlas: Dict[str, Any], tieni: int = 7) -> None:
        """Una riga nuova in ``hazard_atlas`` (atlante assemblato + filigrana);
        tiene le ultime ``tieni``."""
        meta = atlas["meta"]
        self._req("POST", "hazard_atlas", {
            "generated_at": meta["generated_at"], "n_leghe": meta["n_leagues"],
            "n_partite": meta["n_fixtures_used"], "watermark_event_id": meta["watermark_event_id"],
            "payload": atlas}, "return=minimal")
        vecchie = LettoreDB(self.url, self.key).get(
            "hazard_atlas", {"select": "id", "order": "generated_at.desc",
                             "offset": str(tieni), "limit": "100"})
        for r in vecchie:
            self._req("DELETE", f"hazard_atlas?id=eq.{int(r['id'])}")


# ---------------------------------------------------------------------------
# 6) confronto fra due atlanti (referto)
# ---------------------------------------------------------------------------
def confronta(vecchio: Dict[str, Any], nuovo: Dict[str, Any], soglia: float = 0.20) -> Dict[str, Any]:
    lv, ln = set((vecchio.get("by_league") or {})), set((nuovo.get("by_league") or {}))
    cambi: List[Dict[str, Any]] = []
    for lid in sorted(lv & ln, key=int):
        gv = vecchio["by_league"][lid]["grid"]
        gn = nuovo["by_league"][lid]["grid"]
        for b in BUCKETS:
            for k in GOAL_KEYS:
                cv = (gv.get(b) or {}).get(k)
                cn = (gn.get(b) or {}).get(k)
                if not cv or not cn or not cv.get("p_goal_next_3min") or cn.get("p_goal_next_3min") is None:
                    continue
                rel = cn["p_goal_next_3min"] / cv["p_goal_next_3min"] - 1.0
                if abs(rel) > soglia:
                    cambi.append({"league_id": lid, "bucket": b, "gol": k,
                                  "v_old": cv["p_goal_next_3min"], "v_new": cn["p_goal_next_3min"],
                                  "rel": round(rel, 4), "n_new": cn.get("n")})
    glob = []
    for b in BUCKETS:
        for k in GOAL_KEYS:
            cv = ((vecchio.get("global") or {}).get(b) or {}).get(k)
            cn = ((nuovo.get("global") or {}).get(b) or {}).get(k)
            if cv and cn and cv.get("p_goal_next_3min") and cn.get("p_goal_next_3min") is not None:
                glob.append(round(cn["p_goal_next_3min"] / cv["p_goal_next_3min"] - 1.0, 4))
    return {"leghe_aggiunte": sorted(ln - lv, key=int), "leghe_tolte": sorted(lv - ln, key=int),
            "celle_lega_cambiate_oltre_soglia": cambi,
            "globale_max_rel": max((abs(x) for x in glob), default=None),
            "soglia": soglia}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _env_db() -> Tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY mancanti")
    return url, key


def _intervallo(s: str) -> List[int]:
    if "-" in s:
        a, b = s.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",") if x.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Genera l'Atlante Hazard (incrementale per lega).")
    ap.add_argument("--bootstrap", action="store_true", help="storico per --leghe x --stagioni")
    ap.add_argument("--leghe", default="", help="id lega separati da virgola (bootstrap)")
    ap.add_argument("--stagioni", default="", help="es. 2017-2026 (bootstrap)")
    ap.add_argument("--incrementale", action="store_true", help="eventi oltre la filigrana")
    ap.add_argument("--bootstrap-nuove", type=int, default=0,
                    help="max leghe NUOVE a cui dare lo storico per notte (incrementale)")
    ap.add_argument("--stagioni-indietro", type=int, default=10,
                    help="stagioni di storico per una lega nuova")
    ap.add_argument("--watermark", type=int, default=None,
                    help="filigrana iniziale se lo stato non ne ha una")
    ap.add_argument("--stato-file", default="", help="stato grezzo su FILE (sviluppo)")
    ap.add_argument("--stato-db", action="store_true", help="stato grezzo dal DB (action)")
    ap.add_argument("--scrivi-db", action="store_true", help="SCRIVE stato e atlante sul DB")
    ap.add_argument("--json", default="", help="scrive l'atlante assemblato in questo file")
    ap.add_argument("--confronta", default="", help="atlante precedente da confrontare")
    ap.add_argument("--nomi-da", default="", help="atlante da cui prendere i nomi di lega")
    ap.add_argument("--solo-leghe-in-stato", action="store_true",
                    help="incrementale SOLO sulle leghe gia' nello stato (rete notturna "
                         "dell'atlante a domanda: nessuna lega nuova senza storico)")
    ap.add_argument("--filigrana-da-ora-se-assente", action="store_true",
                    help="senza filigrana l'incrementale parte da ORA (max id) invece di "
                         "fermarsi: nessun rosso nella catena finche' lo stato e' vuoto")
    ap.add_argument("--seme", default="",
                    help="atlante seme (es. hazard_atlas_v3.json): globale se lo stato "
                         "non basta, leghe non ancora nello stato")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    url, key = _env_db()
    lettore = LettoreDB(url, key)
    t0 = time.time()
    adesso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if args.stato_db:
        stati, wm = leggi_stato_db(lettore)
    elif args.stato_file:
        stati, wm = leggi_stato_file(args.stato_file)
    else:
        stati, wm = {}, 0
    if args.watermark is not None and not wm:
        wm = int(args.watermark)
    nomi: Dict[str, Optional[str]] = {lid: s.get("league_name") for lid, s in stati.items()}
    if args.nomi_da and os.path.exists(args.nomi_da):
        with open(args.nomi_da, encoding="utf-8") as fh:
            for lid, blk in (json.load(fh).get("by_league") or {}).items():
                nomi.setdefault(lid, (blk.get("meta") or {}).get("league_name"))
    toccate: set = set()
    conti: Dict[str, Any] = {}

    def prepara(leghe: List[str]) -> None:
        if args.stato_db:
            carica_fixtures(lettore, stati, leghe)

    def _filigrana_da_ora() -> int:
        ult = lettore.get("match_events", {"select": "id", "order": "id.desc", "limit": "1"})
        return int(ult[0]["id"]) if ult else 0

    if args.bootstrap:
        leghe = [int(x) for x in args.leghe.split(",") if x.strip()]
        if not leghe or not args.stagioni:
            raise SystemExit("--bootstrap vuole --leghe e --stagioni")
        if not wm:
            # la filigrana parte da ORA: l'incrementale vedra' solo il dopo
            wm = _filigrana_da_ora()
        if args.stagioni.strip() == "auto":
            # 25/09: SOLO le stagioni con eventi dichiarati in coverage (le
            # ultime --stagioni-indietro): niente download da scartare dopo
            cov = stagioni_con_eventi(lettore, leghe)
            conti["bootstrap"] = {}
            for x in leghe:
                st_x = cov.get(str(x), [])[-args.stagioni_indietro:]
                c = bootstrap(lettore, stati, [x], st_x, nomi, adesso, prepara)
                conti["bootstrap"][str(x)] = c
                if str(x) in stati:
                    stati[str(x)]["bootstrapped"] = st_x
        else:
            stagioni = _intervallo(args.stagioni)
            conti["bootstrap"] = bootstrap(lettore, stati, leghe, stagioni, nomi, adesso, prepara)
            for x in leghe:
                if str(x) in stati:
                    stati[str(x)]["bootstrapped"] = stagioni
        toccate.update(str(x) for x in leghe)
    if args.incrementale:
        if not wm:
            if not args.filigrana_da_ora_se_assente:
                # senza filigrana l'incrementale leggerebbe TUTTI i 10 milioni
                # di eventi: prima il bootstrap (che fissa la filigrana)
                raise SystemExit("filigrana assente: lanciare prima --bootstrap (vedi referto)")
            # 25/09: atlante a domanda - lo stato lo riempie il PC lega per
            # lega; la rete notturna parte da ORA e non va mai in rosso
            wm = _filigrana_da_ora()
            conti["filigrana_iniziale_da_ora"] = wm
        wm, c, t = incrementale(lettore, stati, wm, nomi, adesso, prepara=prepara,
                                solo_leghe_in_stato=args.solo_leghe_in_stato)
        conti["incrementale"] = c
        toccate.update(t)
        # LEGHE NUOVE: la copertura segue i dati. Una lega che compare negli
        # eventi e non ha ancora il suo storico lo riceve qui, al massimo
        # --bootstrap-nuove leghe per notte (costo della notte limitato).
        if args.bootstrap_nuove > 0:
            anno = dt.date.today().year
            stagioni = list(range(anno - args.stagioni_indietro + 1, anno + 1))
            nuove = [l for l in t if l in stati and not stati[l].get("bootstrapped")]
            nuove.sort(key=lambda l: -int(stati[l].get("n_fixtures") or 0))
            scelte = [int(l) for l in nuove[: args.bootstrap_nuove]]
            if scelte:
                conti["bootstrap_nuove"] = bootstrap(lettore, stati, scelte, stagioni, nomi,
                                                     adesso, prepara)
                for x in scelte:
                    stati[str(x)]["bootstrapped"] = stagioni
            conti["leghe_in_attesa_di_storico"] = len(nuove) - len(scelte)
    for lid, s in stati.items():
        if not s.get("league_name") and nomi.get(lid):
            s["league_name"] = nomi[lid]
    seme = None
    if args.seme and os.path.exists(args.seme):
        with open(args.seme, encoding="utf-8") as fh:
            seme = json.load(fh)
    atlas = assembla(stati, generated_at=adesso, watermark=wm, seme=seme)
    atlas["meta"]["run"] = {"conti": conti, "leghe_toccate": sorted(toccate, key=int),
                            "richieste_db": lettore.n_richieste, "righe_lette": lettore.n_righe,
                            "secondi": round(time.time() - t0, 1)}
    if args.stato_file:
        scrivi_json_atomico(args.stato_file, {"watermark_event_id": wm, "leghe": stati})
    if args.json:
        scrivi_json_atomico(args.json, atlas)
    if args.scrivi_db:
        _Scrittore(url, key).salva(stati, sorted(toccate, key=int), atlas)
    riepilogo = {k: atlas["meta"][k] for k in ("generated_at", "n_leagues", "n_fixtures_used",
                                                 "n_goals", "n_teams", "n_h2h_pairs",
                                                 "watermark_event_id")}
    riepilogo["run"] = atlas["meta"]["run"]
    if args.confronta and os.path.exists(args.confronta):
        with open(args.confronta, encoding="utf-8") as fh:
            riepilogo["confronto"] = confronta(json.load(fh), atlas)
    print(json.dumps(riepilogo, ensure_ascii=True, indent=1, default=str)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
