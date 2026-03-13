"""
reset_ai_models.py
==================
Svuota completamente:
  1. La tabella ai_model_registry (tutti i record)
  2. Tutti i file nei bucket Supabase Storage ai-models-league-XXX

Eseguire PRIMA di aggiorna_modelli.bat per ripartire da zero.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from db_client import get_supabase_client

def reset_ai_models():
    sb = get_supabase_client()

    # ── 1. Svuota ai_model_registry ────────────────────────────────────────
    print("=" * 60)
    print("STEP 1: Svuoto ai_model_registry...")
    try:
        # Legge tutti i record per contarli prima
        resp = sb.table("ai_model_registry").select("league_id, target").execute()
        records = getattr(resp, "data", None) or []
        print(f"  Trovati {len(records)} record nel registry.")

        if records:
            # Cancella tutto con filtro always-true (id > 0 o simile non serve,
            # supabase-py richiede almeno un filtro — usiamo neq su campo che non esiste mai)
            sb.table("ai_model_registry").delete().neq("league_id", -999999).execute()
            print(f"  ✅ ai_model_registry svuotato ({len(records)} record rimossi).")
        else:
            print("  ℹ️  Tabella già vuota.")
    except Exception as e:
        print(f"  ❌ Errore su ai_model_registry: {e}")
        sys.exit(1)

    # ── 2. Trova tutti i bucket ai-models-league-XXX ───────────────────────
    print()
    print("STEP 2: Ricerca bucket ai-models-league-*...")
    try:
        buckets_resp = sb.storage.list_buckets()
        all_buckets = buckets_resp if isinstance(buckets_resp, list) else []
        target_buckets = [b for b in all_buckets if str(getattr(b, "name", b.get("name", "") if isinstance(b, dict) else "")).startswith("ai-models-league-")]
        print(f"  Trovati {len(target_buckets)} bucket da svuotare.")
    except Exception as e:
        print(f"  ❌ Errore nel listare i bucket: {e}")
        sys.exit(1)

    # ── 3. Svuota ogni bucket ──────────────────────────────────────────────
    total_deleted = 0
    total_errors = 0

    for bucket_obj in target_buckets:
        bucket_name = bucket_obj.name if hasattr(bucket_obj, "name") else bucket_obj.get("name", "")
        if not bucket_name:
            continue

        print(f"\n  Bucket: {bucket_name}")
        try:
            # Lista tutti i file nel bucket (root)
            files_resp = sb.storage.from_(bucket_name).list()
            files = files_resp if isinstance(files_resp, list) else []

            if not files:
                print(f"    ℹ️  Già vuoto.")
                continue

            file_names = [f.get("name") if isinstance(f, dict) else f.name for f in files if f]
            file_names = [n for n in file_names if n]

            print(f"    Trovati {len(file_names)} file → eliminazione...")

            # Cancella in batch (max 100 per chiamata)
            batch_size = 100
            for i in range(0, len(file_names), batch_size):
                batch = file_names[i:i + batch_size]
                try:
                    sb.storage.from_(bucket_name).remove(batch)
                    total_deleted += len(batch)
                    print(f"    ✅ Eliminati {len(batch)} file (batch {i//batch_size + 1}).")
                except Exception as e:
                    print(f"    ❌ Errore batch {i//batch_size + 1}: {e}")
                    total_errors += len(batch)

        except Exception as e:
            print(f"    ❌ Errore nel listare il bucket {bucket_name}: {e}")
            total_errors += 1

    # ── 4. Riepilogo ───────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"✅ COMPLETATO")
    print(f"   File Storage eliminati : {total_deleted}")
    print(f"   Errori                 : {total_errors}")
    print()
    print("Prossimi step:")
    print("  1. aggiorna_modelli.bat   ← retraining completo")
    print("  2. aggiorna_report.bat    ← report con nuovi modelli")
    print("=" * 60)


if __name__ == "__main__":
    print()
    print("⚠️  Questo script elimina TUTTI i modelli AI da Supabase.")
    print("   Dovrai eseguire aggiorna_modelli.bat per riaddestrarli.")
    print()
    confirm = input("Confermi? (scrivi 'SI' per procedere): ").strip().upper()
    if confirm != "SI":
        print("Operazione annullata.")
        sys.exit(0)
    print()
    reset_ai_models()
