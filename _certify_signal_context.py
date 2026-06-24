"""
_certify_signal_context.py — certifica la mappatura cruscotto -> RPC frequenze/ritardi.

Replica freqMap/delayMap di signalContext.ts e, per una lega reale, chiama
get_market_frequency / get_market_delays per OGNI mercato+direzione del cruscotto,
stampando lo STATO ATTUALE (frequenza corrente + baseline + z, ritardo attuale + media).
Verifica che le RPC accettino i parametri e tornino dati sensati.

Uso: python _certify_signal_context.py [league_id]
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from db_client import get_supabase_client
sb = get_supabase_client()

SEL3 = {"H": "1", "D": "X", "A": "2"}
MARKETS = [("1x2","H"),("1x2","D"),("1x2","A"),("ht_1x2","H"),
           ("over_1_5","Over"),("over_1_5","Under"),("over_2_5","Over"),("over_2_5","Under"),
           ("over_3_5","Over"),("over_3_5","Under"),("btts","Yes"),("btts","No"),
           ("first_half_over_0_5","Over"),("first_half_over_0_5","Under")]


def freq_map(market, d):
    if market == "1x2": return {"market":"1x2","selection":SEL3[d],"line":None}
    if market == "ht_1x2": return {"market":"1x2_ht","selection":SEL3[d],"line":None}
    if market == "btts": return {"market":"btts","selection":"yes" if d=="Yes" else "no","line":None}
    if market == "over_1_5": return {"market":"ou_ft","selection":d.lower(),"line":1.5}
    if market == "over_2_5": return {"market":"ou_ft","selection":d.lower(),"line":2.5}
    if market == "over_3_5": return {"market":"ou_ft","selection":d.lower(),"line":3.5}
    if market == "first_half_over_0_5": return {"market":"ou_ht","selection":d.lower(),"line":0.5}
    return None


def delay_map(market, d):
    if market in ("over_1_5","over_2_5","over_3_5"):
        return {"market":"over" if d=="Over" else "under","target":".".join(market.split("_")[1:])}
    if market == "first_half_over_0_5" and d == "Over": return {"market":"ovpt","target":"0.5"}
    if market == "1x2" and d == "D": return {"market":"x","target":None}
    return None


def pick_league():
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        return int(sys.argv[1])
    # auto: lega con tante partite settlate (dalla tabella matches)
    for lid in (39,135,140,78,61,2,3,563,425):
        try:
            r = sb.rpc("get_market_frequency", {"p_league_id":lid,"p_market":"1x2","p_selection":"1",
                       "p_line":None,"p_mode":"last_n","p_last_n":300,"p_season_year":None}).execute().data
            if r and r.get("meta",{}).get("n_effective",0) >= 50:
                return lid
        except Exception:
            continue
    return 39


def main():
    lid = pick_league()
    print(f"Lega di test: {lid}\n")
    print(f"{'MERCATO':24}{'FREQ att':>9}{'FREQ med':>9}{'z':>6}  {'RIT att':>8}{'RIT med':>8}  {'mappa':>16}")
    ok_f = ok_d = err = 0
    for market, d in MARKETS:
        fm = freq_map(market, d); dm = delay_map(market, d)
        fa = fmed = z = ra = rmed = None
        try:
            fs = sb.rpc("get_market_frequency", {"p_league_id":lid,"p_market":fm["market"],
                 "p_selection":fm["selection"],"p_line":fm["line"],"p_mode":"last_n","p_last_n":300,
                 "p_season_year":None}).execute().data
            pts = fs.get("points") or []
            if pts: fa = pts[-1].get("mm10"); z = pts[-1].get("z")
            fmed = fs.get("meta",{}).get("baseline")
            if fa is not None or fmed is not None: ok_f += 1
        except Exception as e:
            err += 1; print(f"  ERRORE freq {market}/{d}: {str(e)[:60]}")
        if dm:
            try:
                dr = sb.rpc("get_market_delays", {"p_league_id":lid,"p_market":dm["market"],
                     "p_target":dm["target"],"p_mode":"all","p_last_n":None,"p_season_year":None}).execute().data
                st = dr.get("stats",{})
                ra = st.get("ritardo_attuale"); rmed = st.get("media_ritardi") or st.get("media_storica")
                if ra is not None: ok_d += 1
            except Exception as e:
                err += 1; print(f"  ERRORE rit {market}/{d}: {str(e)[:60]}")
        fstr = f"{fa*100:.0f}%" if fa is not None else "-"
        fmstr = f"{fmed*100:.0f}%" if fmed is not None else "-"
        zstr = f"{z:.1f}" if z is not None else "-"
        rastr = str(ra) if ra is not None else ("-" if dm else "n/a")
        rmstr = f"{rmed:.1f}" if rmed is not None else ("-" if dm else "n/a")
        mp = f"{dm['market']}" if dm else "no-rit"
        print(f"{market+'/'+d:24}{fstr:>9}{fmstr:>9}{zstr:>6}  {rastr:>8}{rmstr:>8}  {mp:>16}")
    print(f"\nFreq OK: {ok_f}/14 mercati · Ritardo OK: {ok_d}/{sum(1 for m,d in MARKETS if delay_map(m,d))} mappati · errori: {err}")
    print("ESITO:", "✅ mappatura valida — RPC rispondono coi dati" if err == 0 and ok_f >= 10 else "⚠️ controllare")


if __name__ == "__main__":
    main()
