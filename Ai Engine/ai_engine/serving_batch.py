"""serving_batch.py — runner ML giornaliero (gemello di tactical_engine/serving.py).

Popola `fixture_predictions.model_predictions_json` per le partite del giorno,
chiamando `predict_fixture(fixture_id, store=True)` su ciascuna. NON usa quote
Betfair (live_odds resta None): le previsioni ML dipendono solo dalle feature del
modello, quindi gira interamente in cloud (action giornaliera) come gli altri motori.

ADDITIVO E NON-FATALE: un errore su una partita NON ferma le altre; un errore
globale viene loggato e ritornato, mai sollevato (lo chiama un blocco try/except).

Uso standalone:
  python -m ai_engine.serving_batch --date 2026-06-22
  python -m ai_engine.serving_batch --date 2026-06-22 --max 2   # smoke test
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_AIENG = os.path.dirname(_HERE)          # cartella "Ai Engine" (per `import ai_engine`)
_ROOT = os.path.dirname(_AIENG)          # repo root (per `import db_client`)
for _p in (_ROOT, _AIENG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db_client import get_supabase_client  # noqa: E402
from ai_engine.predict_fixture import predict_fixture  # noqa: E402

log = logging.getLogger("ml_engine.serving_batch")

# Eccezioni "attese" (partita non predicibile, non un bug): lega senza modelli nel
# registry o feature non producibili. Le contiamo come `skipped`, non `errors`.
# Marker SPECIFICI ai messaggi di predict_fixture (evita di mascherare errori DB
# generici che contengono parole come "not found").
_SKIP_MARKERS = ("no models found in ai_model_registry", "no features produced")


def run_for_date(target_date: Optional[str] = None, max_fixtures: int = 0) -> dict:
    """Predice (ML) le partite della data e fa upsert di model_predictions_json.

    Ritorna un riepilogo {fixtures, stored, skipped, errors}. Non solleva mai:
    logga e ritorna anche in caso di errore globale (es. DB irraggiungibile).
    """
    try:
        day = (datetime.fromisoformat(target_date).date() if target_date
               else datetime.now(timezone.utc).date())
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        sb = get_supabase_client()
        # Sorgente = fixture_predictions (NON `matches`): predict_fixture richiede che
        # la riga esista già qui (la scrive il loop Poisson che gira prima). Iterando
        # direttamente questa tabella evitiamo i "not found" sulle partite che il loop
        # principale ha saltato (no_coverage) e non sprechiamo lavoro su fixture impredicibili.
        rows = sb.table("fixture_predictions").select(
            "fixture_id,league_id,fixture_date"
        ).gte("fixture_date", start.isoformat()).lt("fixture_date", end.isoformat()).execute().data
        fixtures = [r for r in (rows or []) if r.get("fixture_id")]
        if max_fixtures:
            fixtures = fixtures[:max_fixtures]

        log.info("[ml_engine] partite del %s da predire: %d", day.isoformat(), len(fixtures))
        summary = {"fixtures": len(fixtures), "stored": 0, "skipped": 0, "errors": 0}

        for r in fixtures:
            fid = r["fixture_id"]
            try:
                predict_fixture(fid, store=True)  # live_odds=None: nessuna quota Betfair
                summary["stored"] += 1
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if any(m in msg.lower() for m in _SKIP_MARKERS):
                    summary["skipped"] += 1
                    log.info("[ml_engine] fixture %s saltata: %s", fid, msg[:140])
                else:
                    summary["errors"] += 1
                    log.warning("[ml_engine] fixture %s ERRORE: %s", fid, msg[:140])

        log.info("[ml_engine] %s → %s", day.isoformat(), summary)
        return summary
    except Exception as e:  # noqa: BLE001  — errore globale: logga e ritorna, non sollevare
        log.warning("[ml_engine] run_for_date fallito per %s: %s", target_date, e)
        return {"fixtures": 0, "stored": 0, "skipped": 0, "errors": 0, "fatal": str(e)[:200]}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: oggi UTC)")
    ap.add_argument("--max", type=int, default=0, help="limita N partite (smoke test)")
    args = ap.parse_args()
    res = run_for_date(args.date, max_fixtures=args.max)
    print(res)


if __name__ == "__main__":
    main()
