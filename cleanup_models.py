"""
cleanup_models.py — Pulizia completa modelli ML.

Cancella:
  1. Tutte le entry dalla tabella ai_model_registry su Supabase
  2. Tutti i file .pkl.gz dai bucket Supabase ai-models-league-*
  3. Tutti i file locali in models_cache/downloaded/
  4. Tutti i file locali in models_cache/league_*/

Dopo questo script, la prossima esecuzione di aggiorna_report.bat
riaddestrerà ogni lega da zero usando il codice aggiornato.
"""
import os
import sys
import shutil
import glob

ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))

from db_client import get_supabase_client

MODELS_CACHE_DIR = os.path.join(ROOT, "Ai Engine", "models_cache")


def delete_registry(sb) -> int:
    """Cancella tutte le righe da ai_model_registry."""
    print("  Cancello ai_model_registry...")
    res = sb.table("ai_model_registry").delete().neq("league_id", -1).execute()
    deleted = len(getattr(res, "data", []) or [])
    print(f"    Rimossi {deleted} record.")
    return deleted


def empty_supabase_buckets(sb) -> int:
    """Svuota i file dai bucket ai-models-league-* su Supabase."""
    print("  Recupero lista bucket Supabase...")
    try:
        buckets = sb.storage.list_buckets()
    except Exception as e:
        print(f"    Impossibile listare i bucket: {e}")
        return 0

    total_deleted = 0
    for bucket in buckets:
        name = bucket.name if hasattr(bucket, "name") else bucket.get("name", "")
        if not name.startswith("ai-models-league-"):
            continue

        try:
            files = sb.storage.from_(name).list()
        except Exception as e:
            print(f"    Impossibile listare i file del bucket {name}: {e}")
            continue

        if not files:
            print(f"    Bucket {name}: già vuoto.")
            continue

        file_names = [f["name"] if isinstance(f, dict) else f.name for f in files]
        try:
            sb.storage.from_(name).remove(file_names)
            print(f"    Bucket {name}: rimossi {len(file_names)} file.")
            total_deleted += len(file_names)
        except Exception as e:
            print(f"    Errore rimozione da {name}: {e}")

    return total_deleted


def clear_local_cache() -> int:
    """Rimuove tutti i file locali in models_cache/."""
    if not os.path.isdir(MODELS_CACHE_DIR):
        print(f"    Cartella {MODELS_CACHE_DIR} non trovata. Salto.")
        return 0

    removed = 0

    # Cancella models_cache/downloaded/ (tutte le sottocartelle)
    downloaded_dir = os.path.join(MODELS_CACHE_DIR, "downloaded")
    if os.path.isdir(downloaded_dir):
        shutil.rmtree(downloaded_dir)
        print(f"    Rimossa cartella: {downloaded_dir}")
        removed += 1

    # Cancella tutte le sottocartelle di models_cache/ (league_*, seriea, ecc.)
    for entry in os.listdir(MODELS_CACHE_DIR):
        entry_path = os.path.join(MODELS_CACHE_DIR, entry)
        if os.path.isdir(entry_path):
            shutil.rmtree(entry_path)
            print(f"    Rimossa cartella: {entry}")
            removed += 1

    return removed


def main():
    print("=" * 60)
    print("  CLEANUP MODELLI ML")
    print("  Questo script resetta TUTTI i modelli addestrati.")
    print("  La prossima esecuzione di aggiorna_report.bat")
    print("  riaddestrerà le leghe necessarie da zero.")
    print("=" * 60)
    print()

    confirm = input("Sei sicuro? Digita 'SI' per continuare: ").strip()
    if confirm != "SI":
        print("Operazione annullata.")
        return

    print()
    sb = get_supabase_client()

    print("[1/3] Supabase — ai_model_registry:")
    delete_registry(sb)

    print()
    print("[2/3] Supabase — bucket ai-models-league-*:")
    n_files = empty_supabase_buckets(sb)
    print(f"    Totale file rimossi dai bucket: {n_files}")

    print()
    print("[3/3] Locale — models_cache/:")
    n_dirs = clear_local_cache()
    print(f"    Totale cartelle rimosse: {n_dirs}")

    print()
    print("=" * 60)
    print("  CLEANUP COMPLETATO.")
    print("  Ora lancia aggiorna_report.bat.")
    print("  Il sistema addestrerà le leghe di oggi automaticamente.")
    print("=" * 60)


if __name__ == "__main__":
    main()
