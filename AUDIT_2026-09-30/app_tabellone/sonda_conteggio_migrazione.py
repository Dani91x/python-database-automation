# Sonda SOLA LETTURA (30/09): quante righe toccherebbe la migrazione
# tennis_paper_voided_residuo_zero_2026-09-30.sql (stesso WHERE), e quante
# righe bot tennis con residuo > 0 non regolate NON sono in quel perimetro.
import sys, os, collections
sys.path.insert(0, os.getcwd())
from db_client import get_supabase_client

sb = get_supabase_client()
BOT = ["tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"]
tutte = (sb.table("tennis_live_orders")
         .select("id,source,mode,status,size_matched,size_remaining,settled_at,updated_at")
         .in_("source", BOT).is_("settled_at", "null").gt("size_remaining", 0).execute()).data
dentro = [o for o in tutte if o["mode"] == "paper" and o["status"] == "VOIDED"
          and float(o["size_matched"] or 0) == 0]
print("non regolate con residuo > 0:", len(tutte), "| nel perimetro della migrazione:", len(dentro))
print("fuori perimetro:", [(o["id"], o["mode"], o["status"], o["size_matched"]) for o in tutte if o not in dentro])
print("per giorno di updated_at:", collections.Counter(o["updated_at"][:10] for o in dentro))
