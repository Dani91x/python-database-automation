"""raccogli.py - letture del DB VERO in SOLA LETTURA, UNA volta, in cache locale.

Tetto dichiarato: ~400 richieste. Si legge con il ``LettoreDB`` del generatore
(solo GET, ritentativi pazienti, pausa gentile) e con le stesse colonne del
generatore (``COLONNE_MATCH``, ``COLONNE_GOL``) piu' quelle che servono al banco:
  matches       + raw_json->fixture->status->extra (recupero del 2T, API-Football)
                + raw_json->fixture->periods->first/second (inizio dei tempi, unix)
  match_events  gol, rossi (Red Card / Second Yellow card) e, per le stagioni
                >= STAGIONE_EVENTI_RECUPERO, ogni evento con minute_extra (limite
                inferiore del recupero giocato)
  api_coverage_by_season  stagioni con fixtures_events (stesso filtro della produzione)
  fixture_predictions     lambda pre-partita del motore Poisson (db_json_analisi.inputs),
                          la fonte che Safe usa in live (``resolve_lambdas``)
Le credenziali si passano con ``--env`` (file .env letto A MANO: mai load_dotenv).
Se la cache esiste gia' non si rilegge nulla (``--forza`` per rifare, dichiarato).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from typing import Any, Dict, List

from Betfair.stream.scalper.genera_atlante import COLONNE_GOL, COLONNE_MATCH, LettoreDB

LEGHE_GRANDI = (40, 71, 140, 39, 135, 62, 61, 78, 88, 94, 144, 179)
LEGHE_PICCOLE = (395, 833, 834)       # eventi solo dal 2024: < 300 partite di storico
# 25/09: la 395 ha gli eventi sull'1,7% delle partite 2024/2025 (misurato dalla
# regola di copertura della produzione): esce da sola. Supplemento dichiarato
# con due leghe piccole in piu' (--supplemento): 306 (56 partite/stagione,
# eventi dal 2022) e 835 (240 partite/stagione, eventi dal 2024).
LEGHE_SUPPLEMENTO = (306, 835)
STAGIONI = tuple(range(2016, 2026))   # 2026: nessun evento europeo nel DB (flag fermi)
STAGIONE_EVENTI_RECUPERO = 2024       # validazione + test: anche gli eventi in recupero
LOTTO_EVENTI = 250
LOTTO_PRED = 200
CACHE_DEFAULT = os.path.join("AUDIT_2026-09-25", "validazione_hazard", "cache")

# 25/09 sera: ``extra`` (raw_json->fixture->status->extra) e' ora in COLONNE_MATCH
# (atlante v4 collegato): qui non si ripete, stessa lista di colonne di prima.
COLONNE_MATCH_BANCO = (COLONNE_MATCH + ",status_elapsed,"
                       "p1:raw_json->fixture->periods->first,"
                       "p2:raw_json->fixture->periods->second")
FILTRO_EVENTI = 'or=(event_type.eq.Goal,detail.eq."Red Card",detail.eq."Second Yellow card")'
FILTRO_EVENTI_RECUPERO = ('or=(event_type.eq.Goal,detail.eq."Red Card",'
                          'detail.eq."Second Yellow card",minute_extra.not.is.null)')


def leggi_env(path: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for riga in fh:
            if "=" in riga and not riga.strip().startswith("#"):
                k, v = riga.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def salva(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=True, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def carica(path: str) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _filtro(params: Dict[str, str], filtro: str) -> Dict[str, str]:
    k, v = filtro.split("=", 1)
    out = dict(params)
    out[k] = v
    return out


def raccogli(lettore: LettoreDB, cache: str, leghe: Any = None, suffisso: str = "") -> Dict[str, Any]:
    t0 = time.time()
    leghe = list(leghe) if leghe else list(LEGHE_GRANDI) + list(LEGHE_PICCOLE)
    passi: List[Dict[str, Any]] = []

    def passo(nome: str, r0: int, n0: int, s0: float) -> None:
        passi.append({"passo": nome, "richieste": lettore.n_richieste - r0,
                      "righe": lettore.n_righe - n0, "secondi": round(time.time() - s0, 1)})
        print(passi[-1], file=sys.stderr)

    # 1) coverage: stagioni con eventi dichiarati (stesso filtro della produzione)
    r0, n0, s0 = lettore.n_richieste, lettore.n_righe, time.time()
    cov = lettore.get("api_coverage_by_season", {
        "select": "league_id,season_year,fixtures_events",
        "league_id": "in.(" + ",".join(map(str, leghe)) + ")", "limit": "5000"})
    salva(os.path.join(cache, f"coverage{suffisso}.json.gz"), cov)
    passo("coverage", r0, n0, s0)

    # 2) partite: tutte le leghe e stagioni del campione, a chiave fixture_id
    r0, n0, s0 = lettore.n_richieste, lettore.n_righe, time.time()
    matches = lettore.tutte("matches", {
        "select": COLONNE_MATCH_BANCO,
        "league_id": "in.(" + ",".join(map(str, leghe)) + ")",
        "season_year": "in.(" + ",".join(map(str, STAGIONI)) + ")"}, chiave="fixture_id")
    salva(os.path.join(cache, f"matches{suffisso}.json.gz"), matches)
    passo("matches", r0, n0, s0)

    # 3) eventi: gol + rossi (+ eventi in recupero per le stagioni recenti)
    r0, n0, s0 = lettore.n_richieste, lettore.n_righe, time.time()
    ft = [m for m in matches if str(m.get("status_short")) == "FT"]
    vecchie = sorted(int(m["fixture_id"]) for m in ft if int(m["season_year"]) < STAGIONE_EVENTI_RECUPERO)
    recenti = sorted(int(m["fixture_id"]) for m in ft if int(m["season_year"]) >= STAGIONE_EVENTI_RECUPERO)
    eventi: List[Dict[str, Any]] = []
    for fids, filtro in ((vecchie, FILTRO_EVENTI), (recenti, FILTRO_EVENTI_RECUPERO)):
        for i in range(0, len(fids), LOTTO_EVENTI):
            lista = ",".join(str(f) for f in fids[i:i + LOTTO_EVENTI])
            eventi.extend(lettore.tutte("match_events", _filtro(
                {"select": COLONNE_GOL + ",player_id", "fixture_id": f"in.({lista})"}, filtro),
                chiave="id"))
    salva(os.path.join(cache, f"eventi{suffisso}.json.gz"), eventi)
    passo("eventi", r0, n0, s0)

    # 4) lambda pre-partita (fixture_predictions) sulle stagioni di validazione e test
    r0, n0, s0 = lettore.n_richieste, lettore.n_righe, time.time()
    pred: List[Dict[str, Any]] = []
    for i in range(0, len(recenti), LOTTO_PRED):
        lista = ",".join(str(f) for f in recenti[i:i + LOTTO_PRED])
        pred.extend(lettore.get("fixture_predictions", {
            "select": "fixture_id,lh:db_json_analisi->inputs->lambda_home,"
                      "la:db_json_analisi->inputs->lambda_away,"
                      "gen:db_json_analisi->generated_at",
            "fixture_id": f"in.({lista})"}))
    salva(os.path.join(cache, f"predizioni{suffisso}.json.gz"), pred)
    passo("predizioni", r0, n0, s0)

    meta = {"creata": time.strftime("%Y-%m-%dT%H:%M:%S"), "leghe": leghe,
            "stagioni": list(STAGIONI), "passi": passi,
            "richieste_totali": lettore.n_richieste, "righe_totali": lettore.n_righe,
            "secondi_totali": round(time.time() - t0, 1),
            "n_matches": len(matches), "n_eventi": len(eventi), "n_predizioni": len(pred)}
    with open(os.path.join(cache, f"meta{suffisso}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Letture in SOLA LETTURA per il banco hazard.")
    ap.add_argument("--env", required=True, help=".env del repo principale (letto a mano)")
    ap.add_argument("--cache", default=CACHE_DEFAULT)
    ap.add_argument("--forza", action="store_true", help="rilegge anche se la cache c'e'")
    ap.add_argument("--supplemento", action="store_true",
                    help="solo LEGHE_SUPPLEMENTO, in file *_supp (la cache principale non si tocca)")
    a = ap.parse_args(argv)
    os.makedirs(a.cache, exist_ok=True)
    suff = "_supp" if a.supplemento else ""
    if os.path.exists(os.path.join(a.cache, f"meta{suff}.json")) and not a.forza:
        print("cache gia' presente: nessuna lettura (usa --forza per rifarla)")
        return 0
    env = leggi_env(a.env)
    lettore = LettoreDB(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"], pausa=0.1)
    leghe = LEGHE_SUPPLEMENTO if a.supplemento else None
    print(json.dumps(raccogli(lettore, a.cache, leghe, suff), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
