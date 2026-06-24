"""
_certify_delay_context.py — certifica il RITARDO del cruscotto Direzione.

Il cruscotto calcola il ritardo dalla SERIE binaria di get_market_frequency
(che esclude correttamente le partite senza HT). Qui verifico due cose:
  1) il calcolo del ritardo dalla serie == calcolo INDIPENDENTE dalla tabella matches
     (verita' a terra), per mercati FT e HT;
  2) sul caso-bug (lega 256, over 0.5 1°T) il ritardo NON e' piu' 547 ma un valore sano.

Uso: python _certify_delay_context.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from db_client import get_supabase_client
sb = get_supabase_client()


def compute_delay(outs):
    """Mirror ESATTO di computeDelay() in signalContext.ts."""
    gaps, run = [], 0
    for o in outs:
        if o == 1:
            gaps.append(run); run = 0
        else:
            run += 1
    current = run
    record = max([current] + gaps + [0])
    media = (sum(gaps) / len(gaps)) if gaps else None
    return current, media, record


def freq_series(league, market, selection, line):
    f = sb.rpc("get_market_frequency", {"p_league_id": league, "p_market": market,
        "p_selection": selection, "p_line": line, "p_mode": "all",
        "p_last_n": None, "p_season_year": None}).execute().data
    pts = sorted(f.get("points") or [], key=lambda p: p["idx"])
    return [int(p["out"]) for p in pts], f.get("meta", {}).get("baseline")


def matches_truth(league, kind, line=None):
    """Serie out 0/1 DIRETTA da matches (FT primario, fallback goals; HT esclude NULL)."""
    cols = "fixture_id,fixture_date,fulltime_home,fulltime_away,goals_home,goals_away,halftime_home,halftime_away,status_short"
    rows, start = [], 0
    while True:
        d = (sb.table("matches").select(cols).eq("league_id", league)
             .in_("status_short", ["FT", "AET", "PEN"])
             .order("fixture_date").order("fixture_id").range(start, start + 999).execute().data)
        rows += d
        if len(d) < 1000:
            break
        start += 1000
    def fnum(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    outs = []
    for r in rows:
        # FT 90': fulltime_* primario, fallback goals_* solo su FT
        fh, fa = fnum(r.get("fulltime_home")), fnum(r.get("fulltime_away"))
        if fh is None or fa is None:
            if str(r.get("status_short")).upper() == "FT":
                fh, fa = fnum(r.get("goals_home")), fnum(r.get("goals_away"))
        hh, ha = fnum(r.get("halftime_home")), fnum(r.get("halftime_away"))
        if kind == "ou_ht":           # esclude righe senza HT
            if hh is None or ha is None:
                continue
            outs.append(1 if (hh + ha) > line else 0)
        elif kind == "ou_ft":
            if fh is None or fa is None:
                continue
            outs.append(1 if (fh + fa) > line else 0)
        elif kind == "1x2_home":
            if fh is None or fa is None:
                continue
            outs.append(1 if fh > fa else 0)
    return outs


def main():
    cases = [
        ("256 over0.5 1T (CASO BUG)", 256, "ou_ht", "over", 0.5, "ou_ht", 0.5),
        ("256 over2.5 FT",            256, "ou_ft", "over", 2.5, "ou_ft", 2.5),
        ("256 esito 1 (Casa)",        256, "1x2",   "1",    None, "1x2_home", None),
        ("39  over0.5 1T",            39,  "ou_ht", "over", 0.5, "ou_ht", 0.5),
    ]
    mism = 0
    print(f"{'CASO':28}{'fonte':9}{'attuale':>8}{'media':>8}{'record':>8}{'baseline':>10}")
    for name, lg, fmkt, fsel, fline, tkind, tline in cases:
        outs_s, base = freq_series(lg, fmkt, fsel, fline)
        cs, ms, rs = compute_delay(outs_s)
        outs_t = matches_truth(lg, tkind, tline)
        ct, mt, rt = compute_delay(outs_t)
        impl = sum(outs_s) / len(outs_s) if outs_s else None
        ok = (cs == ct and rs == rt and abs((ms or 0) - (mt or 0)) < 1e-9 and len(outs_s) == len(outs_t))
        if not ok: mism += 1
        print(f"{name:28}{'serie':9}{cs:>8}{(round(ms,2) if ms is not None else '-'):>8}{rs:>8}{(round(base,3) if base else '-'):>10}")
        print(f"{'':28}{'matches':9}{ct:>8}{(round(mt,2) if mt is not None else '-'):>8}{rt:>8}{(round(impl,3) if impl else '-'):>10}  {'OK' if ok else 'MISMATCH n_serie='+str(len(outs_s))+' n_matches='+str(len(outs_t))}")
    print(f"\nESITO: {'✅ RITARDO CERTIFICATO — serie == verita matches' if mism == 0 else '❌ '+str(mism)+' mismatch'}")
    print("(NB il caso-bug: record deve essere piccolo, non 547)")


if __name__ == "__main__":
    main()
