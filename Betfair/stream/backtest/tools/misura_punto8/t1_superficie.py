# -*- coding: utf-8 -*-
"""T1 - tennis_pro e la SUPERFICIE. SOLO CONTEGGIO, NIENTE SI ACCENDE.

ATTUALE: `TennisProStrategy` legge ``surface`` dal contesto, con default
"grass" (`tennis_pro_bot.py:116`), e nessun runner la passa. Su "grass"/"fast"
tre setup su sei restano spenti (`_lay_rev` falso): SERVING FOR THE SET,
DOUBLE BREAK, COMPRESSED FAVOURITE (`tennis_pro_bot.py:119,132,171,174,184`), e il
BREAK POINT banca il servitore invece del ricevitore (`:510`).

Qui si CONTA, sulle registrazioni tennis:
  1. la superficie di ogni partita. Lo stream non la porta: porta ``countryCode``
     nella marketDefinition. La superficie vera viene da
     `tennis_markets.competition_name` (serve l'estrazione dal DB,
     `estrai_db.py t1`); senza, si riporta solo il paese (dichiarato);
  2. quante volte, in ogni partita, le CONDIZIONI dei tre setup spenti si
     sarebbero verificate (stesse soglie di default del bot:
     serving_for_set = servitore a >= 5 game e avanti di >= 1; double_break =
     scarto >= 3 game (`db_lead_games`); compressed_fav = ltp del favorito
     <= 1,20 (`cf_max_price`)). NON e' un ingresso: dice solo quante occasioni
     il setup avrebbe esaminato. Nessuna strategia viene istanziata.

Uso:
  python -m Betfair.stream.backtest.tools.misura_punto8.t1_superficie --out <f.json> \
      [--tennis-rec <dir>] [--competizioni <estrazione t1 .json.gz>]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.stream.backtest.tools.misura_punto8 import comune as C
from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P

C.blinda_db()

# soglie di default del bot (`tennis_pro_bot.py:172-186`), riportate qui SOLO per
# contare; si verifica nei test che coincidano con quelle del codice vero.
SFS_GAME_MIN = 5
DB_LEAD_GAMES = 3
CF_MAX_PRICE = 1.20

# parole chiave -> superficie (solo per la misura; "sconosciuta" se nessuna)
_SUPERFICI: Tuple[Tuple[str, str], ...] = (
    (r"wimbledon|queen'?s|halle|hertogenbosch|eastbourne|mallorca|newport|\bgrass\b|erba|nottingham|ilkley|surbiton|bad homburg|birmingham", "grass"),
    (r"roland|french open|hamburg|bastad|gstaad|umag|kitzb|monte ?carlo|madrid|rome|roma|barcelona|\bclay\b|terra|bucharest|estoril|marrakech|houston|lyon|geneva|munich|palermo|iasi|braunschweig|prague|contrexeville|biella|trieste|todi|san marino|cordenons|perugia|poznan|bogota|santiago|buenos aires|rio de janeiro|parma|budapest|warsaw|varsavia", "clay"),
    (r"us open|australian open|cincinnati|toronto|montreal|washington|indian wells|miami|\bhard\b|atlanta|los cabos|winston|shanghai|beijing|tokyo|vienna|basel|paris masters|doha|dubai|acapulco|chengdu|hangzhou", "hard"),
)


def superficie_da_nome(nome: Optional[str]) -> str:
    s = str(nome or "").lower()
    for pat, sup in _SUPERFICI:
        if re.search(pat, s):
            return sup
    return "sconosciuta"


def _eventi(radice: str) -> List[Tuple[str, str, str]]:
    """[(giorno, event_id, cartella)] per ogni registrazione con raw."""
    out = []
    for giorno in sorted(os.listdir(radice)):
        g = os.path.join(radice, giorno)
        if not os.path.isdir(g):
            continue
        for eid in sorted(os.listdir(g)):
            d = os.path.join(g, eid)
            if os.path.isfile(os.path.join(d, f"{eid}.raw.jsonl")):
                out.append((giorno, eid, d))
    return out


def leggi_raw(path: str) -> Dict[str, Any]:
    """countryCode, openDate e l'ltp minimo del favorito per ogni tick in cui
    entrambe le ltp sono note (MATCH_ODDS)."""
    paese, apertura, tipo = None, None, None
    ltp: Dict[int, float] = {}
    tick_cf, min_fav = 0, None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            for mc in rec.get("mc") or []:
                md = mc.get("marketDefinition")
                if md:
                    paese = md.get("countryCode") or paese
                    apertura = md.get("openDate") or apertura
                    tipo = md.get("marketType") or tipo
                cambiato = False
                for rc in mc.get("rc") or []:
                    if rc.get("ltp") is not None and rc.get("id") is not None:
                        ltp[int(rc["id"])] = float(rc["ltp"])
                        cambiato = True
                if cambiato and len(ltp) >= 2 and tipo in (None, "MATCH_ODDS"):
                    fav = min(ltp.values())
                    min_fav = fav if min_fav is None else min(min_fav, fav)
                    if fav <= CF_MAX_PRICE:
                        tick_cf += 1
    return {"paese": paese, "apertura": apertura, "tipo": tipo,
            "tick_compressed_fav": tick_cf, "ltp_min_favorito": min_fav}


def _int(x: Any) -> int:
    try:
        return int(str(x).strip() or 0)
    except ValueError:
        return 0


def leggi_punteggi(path: str) -> Dict[str, Any]:
    """Stati di punteggio DISTINTI (set, game, servizio) che soddisfano le
    condizioni di serving_for_set e double_break."""
    sfs, dbk, stati = set(), set(), set()
    if not os.path.isfile(path):
        return {"stati": 0, "stati_serving_for_set": 0, "stati_double_break": 0}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            sc = ((rec.get("score") or {}).get("score") or {})
            h, a = sc.get("home") or {}, sc.get("away") or {}
            gh, ga = _int(h.get("games")), _int(a.get("games"))
            sh, sa = _int(h.get("sets")), _int(a.get("sets"))
            srv = "home" if h.get("isServing") else "away" if a.get("isServing") else None
            chiave = (sh, sa, gh, ga, srv)
            stati.add(chiave)
            if srv is not None:
                gs, go = (gh, ga) if srv == "home" else (ga, gh)
                if gs >= SFS_GAME_MIN and gs - go >= 1:
                    sfs.add(chiave)
            if abs(gh - ga) >= DB_LEAD_GAMES:
                dbk.add(chiave)
    return {"stati": len(stati), "stati_serving_for_set": len(sfs), "stati_double_break": len(dbk)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tennis-rec", default=None)
    ap.add_argument("--competizioni", default=None,
                    help="estrai_db.py t1: [{event_id, competition_name}] (json.gz)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    radice = P.tennis_rec(a.tennis_rec)
    comp: Dict[str, str] = {}
    if a.competizioni:
        with gzip.open(a.competizioni, "rt", encoding="utf-8") as fh:
            for r in json.load(fh).get("tennis_markets") or []:
                comp[str(r.get("event_id"))] = r.get("competition_name")
    per: List[dict] = []
    for giorno, eid, d in _eventi(radice):
        raw = leggi_raw(os.path.join(d, f"{eid}.raw.jsonl"))
        pun = leggi_punteggi(os.path.join(d, f"{eid}.score.jsonl"))
        cn = comp.get(eid)
        per.append({"giorno": giorno, "event_id": eid, **raw, **pun,
                    "competition_name": cn,
                    "superficie": superficie_da_nome(cn) if cn else "ignota_senza_DB"})
    uniche = {}
    for x in per:                                   # un evento puo' stare in due cartelle
        uniche.setdefault(x["event_id"], x)
    ev = list(uniche.values())
    per_paese: Dict[str, int] = {}
    per_sup: Dict[str, int] = {}
    for x in ev:
        per_paese[str(x["paese"])] = per_paese.get(str(x["paese"]), 0) + 1
        per_sup[x["superficie"]] = per_sup.get(x["superficie"], 0) + 1
    non_erba = [x for x in ev if x["superficie"] not in ("grass", "ignota_senza_DB")]
    sintesi = {
        "registrazioni": len(per), "eventi_unici": len(ev),
        "giorni": sorted({x["giorno"] for x in per}),
        "per_paese": per_paese, "per_superficie": per_sup,
        "eventi_non_erba_noti": len(non_erba),
        "eventi_con_occasione": {
            "serving_for_set": sum(1 for x in ev if x["stati_serving_for_set"] > 0),
            "double_break": sum(1 for x in ev if x["stati_double_break"] > 0),
            "compressed_fav": sum(1 for x in ev if x["tick_compressed_fav"] > 0)},
        "stati_totali": {
            "serving_for_set": sum(x["stati_serving_for_set"] for x in ev),
            "double_break": sum(x["stati_double_break"] for x in ev),
            "compressed_fav_tick": sum(x["tick_compressed_fav"] for x in ev)},
        "setup_che_si_accenderebbero_per_partita_non_erba": 3,
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"sintesi": sintesi, "per_evento": per}, fh, indent=1)
    print(json.dumps(sintesi, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
