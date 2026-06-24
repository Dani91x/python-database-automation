"""_certify_betfair_full.py — get_betfair_full_odds/direction_odds vs tabella grezza."""
import sys, json; sys.stdout.reconfigure(encoding="utf-8")
from db_client import get_supabase_client
sb = get_supabase_client()
MAP = {("1x2","H"):("Match Odds",1),("1x2","A"):("Match Odds",2),("1x2","D"):("Match Odds",3),
       ("ht_1x2","H"):("Half Time",1),("ht_1x2","A"):("Half Time",2),("ht_1x2","D"):("Half Time",3),
       ("over_1_5","Over"):("Over/Under 1.5 Goals","Over 1.5 Goals"),("over_1_5","Under"):("Over/Under 1.5 Goals","Under 1.5 Goals"),
       ("over_2_5","Over"):("Over/Under 2.5 Goals","Over 2.5 Goals"),("over_2_5","Under"):("Over/Under 2.5 Goals","Under 2.5 Goals"),
       ("over_3_5","Over"):("Over/Under 3.5 Goals","Over 3.5 Goals"),("over_3_5","Under"):("Over/Under 3.5 Goals","Under 3.5 Goals"),
       ("btts","Yes"):("Both teams to Score?","Yes"),("btts","No"):("Both teams to Score?","No"),
       ("first_half_over_0_5","Over"):("First Half Goals 0.5","Over 0.5 Goals"),("first_half_over_0_5","Under"):("First Half Goals 0.5","Under 0.5 Goals")}
fid=1489408
raw=sb.table("betfair_market_odds").select("*").eq("fixture_id",fid).execute().data
by=( {}, {} )  # (market,selection)->row ; (market,sort)->row
rk, rks = {}, {}
for r in raw:
    rk[(r["market_name"], r["selection"])]=r
    if r["sort_priority"] is not None: rks[(r["market_name"], r["sort_priority"])]=r
mism=0
# full: tutti i mercati presenti
full=sb.rpc("get_betfair_full_odds",{"p_fixture_id":fid}).execute().data
raw_markets=set(r["market_name"] for r in raw)
rpc_markets=set(m["market"] for m in full)
if raw_markets!=rpc_markets: print("MISMATCH mercati:",raw_markets^rpc_markets); mism+=1
nrun_raw=len(raw); nrun_rpc=sum(len(m["runners"]) for m in full)
if nrun_raw!=nrun_rpc: print("MISMATCH n runners:",nrun_raw,nrun_rpc); mism+=1
# direction: ogni cella canonica == riga grezza
d=sb.rpc("get_betfair_direction_odds",{"p_fixture_id":fid}).execute().data
for (cm,cs),(bfm,key) in MAP.items():
    row = rks.get((bfm,key)) if isinstance(key,int) else rk.get((bfm,key))
    rpcv = d.get(cm,{}).get(cs)
    if row is None and rpcv is None: continue
    if (row is None)!=(rpcv is None): print("MISMATCH presenza",cm,cs); mism+=1; continue
    if json.dumps(row["back"],sort_keys=True)!=json.dumps(rpcv["back"],sort_keys=True) or json.dumps(row["lay"],sort_keys=True)!=json.dumps(rpcv["lay"],sort_keys=True):
        print("MISMATCH valori",cm,cs); mism+=1
print(f"\nfull: {len(rpc_markets)} mercati / {nrun_rpc} runners | direction: {sum(len(v) for v in d.values())} celle")
print("ESITO:", "OK CERTIFICATO" if mism==0 else f"{mism} mismatch")
