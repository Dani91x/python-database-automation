"""
cloud_retrain_shard.py — wrapper di sharding per il retrain cloud (GitHub Actions).

Divide le leghe in N shard deterministici (round-robin sugli ID ordinati, così le
leghe grandi e piccole si distribuiscono uniformemente tra i job della matrix) e
delega ogni shard a retrain_all_leagues.py, che gestisce training, gate BSS e
upload su Supabase storage + ai_model_registry.

Uso (dentro il workflow .github/workflows/retrain_models.yml):
    python cloud_retrain_shard.py --shard-index 0 --total-shards 4
    python cloud_retrain_shard.py --shard-index 0 --total-shards 1 --leagues 135,39

Il PC locale scarica automaticamente i modelli nuovi al primo predict_fixture
dopo la scadenza della cache (24h) — nessuna azione manuale richiesta.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import retrain_all_leagues as ral


def main() -> int:
    parser = argparse.ArgumentParser(description="Shard deterministico per il retrain cloud.")
    parser.add_argument("--shard-index", type=int, required=True, help="Indice shard (0-based).")
    parser.add_argument("--total-shards", type=int, required=True, help="Numero totale di shard.")
    parser.add_argument(
        "--leagues",
        default="",
        help="Override: lista esplicita di league_id (csv). Vuoto = tutte le leghe dal DB.",
    )
    parser.add_argument("--last-n-seasons", type=int, default=3)
    parser.add_argument(
        "--skip-existing",
        default="true",
        choices=["true", "false"],
        help="Salta le leghe riaddestrate negli ultimi --max-age-days giorni.",
    )
    parser.add_argument("--max-age-days", type=int, default=7)
    parser.add_argument("--parallel-leagues", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true", help="Mostra cosa verrebbe addestrato senza addestrare.")
    args = parser.parse_args()

    if not (0 <= args.shard_index < args.total_shards):
        print(f"[ERROR] shard-index {args.shard_index} fuori range per total-shards {args.total_shards}")
        return 2

    # Parità di serving: il meta-learner DEVE restare LogReg ovunque. Se qualcuno
    # aggiunge tensorflow all'ambiente cloud, i modelli LARGE userebbero il meta MLP
    # e il PC di serving potrebbe non caricarlo identico — segnala subito.
    try:
        import tensorflow  # noqa: F401
        print("[WARN] tensorflow PRESENTE nell'ambiente di training: il meta-learner "
              "MLP verra' usato sui tier LARGE. Verifica la parita' col PC di serving!")
    except ImportError:
        print("[OK] tensorflow assente: meta-learner LogReg (parita' di serving garantita).")

    if args.leagues.strip():
        tokens = [x.strip() for x in args.leagues.split(",") if x.strip()]
        bad = [t for t in tokens if not t.isdigit()]
        if bad:
            print(f"[ERROR] league_id non numerici nell'input --leagues: {bad}")
            return 2
        all_ids = sorted({int(t) for t in tokens})
        print(f"[SHARD] Override manuale: {len(all_ids)} leghe da input")
    else:
        all_ids = sorted(set(ral._get_all_league_ids_from_db()))
        print(f"[SHARD] Leghe dal DB (season_backfill_state): {len(all_ids)}")

    shard_ids = [lid for i, lid in enumerate(all_ids) if i % args.total_shards == args.shard_index]
    print(f"[SHARD] Shard {args.shard_index + 1}/{args.total_shards}: {len(shard_ids)} leghe -> {shard_ids}")

    if not shard_ids:
        print("[SHARD] Nessuna lega in questo shard, esco con successo.")
        return 0

    cmd = [
        sys.executable,
        os.path.join(ROOT, "retrain_all_leagues.py"),
        "--leagues", ",".join(map(str, shard_ids)),
        "--last-n-seasons", str(args.last_n_seasons),
        "--parallel-leagues", str(args.parallel_leagues),
        "--source", "db",
    ]
    if args.skip_existing == "true":
        cmd += ["--skip-existing", "--max-age-days", str(args.max_age_days)]
    if args.dry_run:
        cmd += ["--dry-run"]

    print(f"[SHARD] Lancio: {' '.join(cmd)}")
    sys.stdout.flush()
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
