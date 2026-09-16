# -*- coding: utf-8 -*-
"""estrai_transizioni — scarica UNA VOLTA le transizioni per minuto e le mette
su disco, perche' il banco dei modelli (``banco_modelli.py``) possa rifittare
cento volte senza toccare il database (§18: il DB deve respirare).

Tabella ``omega_minute_transitions`` (migrazione ``omega_models_v3.sql``):
``(league_id, bucket, score, target, result, n)``, ``league_id = 0`` = globale.
E' stata costruita dai gol con minuto di ``match_events`` su ~1,4 M partite:
«dal punteggio S al minuto del bucket B, quante volte si e' finiti a R»
(``target='ft'`` = risultato finale, ``target='ht'`` = risultato al 45').

ATTENZIONE, DICHIARATO: ``built_at`` = **11/09/2026**. La tabella e' ferma da 5
giorni. E' comunque il campione piu' grande che abbiamo su «minuto + punteggio
-> risultato» e nessun'altra fonte del DB risponde a quella domanda (§2 del
progetto, fonti 4-5).

Uso:
    python -m Betfair.omega.tools.estrai_transizioni                # globale
    python -m Betfair.omega.tools.estrai_transizioni --leghe 60     # + 60 leghe (OOS)

Scrive ``Betfair/omega/data/transizioni_minuto_2026-09-16.json.gz``.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
from typing import Any, Dict, List, Optional

PAGINA = 1000
DEST = os.path.join("Betfair", "omega", "data", "transizioni_minuto_2026-09-16.json.gz")


def _pagina_tabella(sb, **filtri) -> List[dict]:
    fuori: List[dict] = []
    off = 0
    while True:
        q = sb.table("omega_minute_transitions").select("league_id,bucket,score,target,result,n")
        for k, v in filtri.items():
            if isinstance(v, (list, tuple)):
                q = q.in_(k, list(v))
            else:
                q = q.eq(k, v)
        d = (q.order("bucket").order("score").order("result")
             .range(off, off + PAGINA - 1).execute().data)
        if not d:
            break
        fuori.extend(d)
        if len(d) < PAGINA:
            break
        off += PAGINA
    return fuori


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leghe", type=int, default=60,
                    help="quante leghe (fra quelle con abbastanza partite) per lo split OOS")
    ap.add_argument("--min-partite", type=int, default=2000)
    ap.add_argument("--out", default=DEST)
    args = ap.parse_args(argv)

    sys.path.insert(0, os.getcwd())
    from db_client import get_supabase_client

    sb = get_supabase_client()
    print("globale (league_id = 0)...", flush=True)
    globali = _pagina_tabella(sb, league_id=0)
    print(f"  righe: {len(globali)}", flush=True)

    per_lega: Dict[str, List[dict]] = {}
    if args.leghe > 0:
        conteggi = (sb.table("omega_minute_league_counts").select("league_id,n")
                    .gte("n", args.min_partite).execute().data) or []
        conteggi.sort(key=lambda r: -int(r["n"]))
        rng = random.Random(20260916)
        scelte = conteggi if len(conteggi) <= args.leghe else rng.sample(conteggi, args.leghe)
        print(f"leghe scelte: {len(scelte)} (su {len(conteggi)} con n >= {args.min_partite})", flush=True)
        for i, riga in enumerate(scelte, 1):
            lid = int(riga["league_id"])
            righe = _pagina_tabella(sb, league_id=lid)
            per_lega[str(lid)] = righe
            print(f"  [{i}/{len(scelte)}] lega {lid}: {len(righe)} righe "
                  f"({riga['n']} partite)", flush=True)

    fuori: Dict[str, Any] = {
        "built_at_tabella": "2026-09-11",
        "scaricato_il": "2026-09-16",
        "min_partite_lega": args.min_partite,
        "globale": globali,
        "per_lega": per_lega,
        "partite_per_lega": {str(r["league_id"]): int(r["n"])
                             for r in (sb.table("omega_minute_league_counts")
                                       .select("league_id,n").gte("n", args.min_partite)
                                       .execute().data or [])
                             if str(r["league_id"]) in per_lega},
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as fh:
        json.dump(fuori, fh, ensure_ascii=False)
    print(f"scritto {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
