import sys, statistics as st
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
r = sb.table("ai_model_registry").select("league_id,target,brier,train_rows,trained_at").eq("target","target_over_2_5").limit(500).execute().data or []
print("righe", len(r))
tr = sorted(x["train_rows"] for x in r if x.get("train_rows"))
print("train_rows n=%d min %s p10 %s med %s mean %.0f p90 %s max %s"%(len(tr),tr[0],tr[len(tr)//10],st.median(tr),st.mean(tr),tr[9*len(tr)//10],tr[-1]))
# holdout = 10% di n ; train = 75% - purge  => holdout in [tr/0.75*0.1 , ...]
ho=[0.1/0.75*t for t in tr]
print("holdout stimato (limite basso, senza purge) p10 %.0f med %.0f mean %.0f p90 %.0f; quota <60: %.0f%%, <100: %.0f%%"%(ho[len(ho)//10],st.median(ho),st.mean(ho),ho[9*len(ho)//10],100*sum(h<60 for h in ho)/len(ho),100*sum(h<100 for h in ho)/len(ho)))
br=[x["brier"] for x in r if x.get("brier") is not None]
print("brier n",len(br),"min %.4f"%min(br),"nulli(brier None):",sum(1 for x in r if x.get("brier") is None), "brier<0.15:",sum(b<0.15 for b in br), "brier==0:",sum(b==0 for b in br))
