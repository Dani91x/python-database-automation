"""
direzione.py — CLI del cruscotto DIREZIONE (thin client sulla RPC get_direction).

Tutto il calcolo vive nel DB (RPC get_direction + tabella direction_pagella): qui si
chiama la RPC e si stampa la tabella. Nessun file locale, nessuna calibrazione su disco.

Per ogni partita, per ogni mercato calibrato:
  direzione migliore + affidabilita' storica reale (banda Wilson) + lift + concordanza + quota.

Uso:
  python direzione.py <fixture_id>     # una partita
  python direzione.py                  # AUTO: tutte le partite di oggi non ancora giocate
  python direzione.py --giorni 2       # AUTO: prossimi 2 giorni
"""
import sys, datetime as dt
sys.stdout.reconfigure(encoding="utf-8")


def fixtures_in_programma(sb, giorni: int) -> list[int]:
    oggi = dt.date.today().isoformat()
    fine = (dt.date.today() + dt.timedelta(days=giorni)).isoformat()
    rows, start = [], 0
    while True:
        d = (sb.table("bet_features").select("fixture_id")
             .eq("settled", False).not_.is_("poisson_prob", "null")
             .gte("kickoff", oggi + "T00:00:00").lt("kickoff", fine + "T00:00:00")
             .order("kickoff").range(start, start + 999).execute().data)
        rows.extend(d)
        if len(d) < 1000:
            break
        start += 1000
    return list(dict.fromkeys(r["fixture_id"] for r in rows))


def stampa(d: dict):
    print(f"\n=== fixture {d['fixture_id']}  (lega {d.get('league_id')}) — {len(d['markets'])} mercati ===")
    print(f"{'MERCATO':22}{'DIR':6}{'AFFID':>7}{'BANDA':>12}{'BASE':>6}{'LIFT':>6}{'QUOTA':>7}{'SCOPE':>9}  CONCORDI")
    for m in d["markets"]:
        band = f"{m['wilson_low']*100:.0f}-{m['wilson_high']*100:.0f}%"
        odds = f"{m['odds']:.2f}" if m.get("odds") else "-"
        lift = f"{m['lift']*100:+.0f}"
        print(f"{m['market']:22}{m['direction']:6}{m['affidabilita']*100:6.0f}%{band:>12}"
              f"{m['base']*100:5.0f}%{lift:>6}{odds:>7}{m['scope']:>9}  "
              f"{len(m['concordi'])}/{m['motori_totali']} ({','.join(m['concordi'])})")


def main():
    from db_client import get_supabase_client
    sb = get_supabase_client()
    args = sys.argv[1:]
    if args and args[0].isdigit():
        fids = [int(args[0])]
    else:
        giorni = 1
        if "--giorni" in args:
            i = args.index("--giorni")
            if i + 1 >= len(args) or not args[i + 1].isdigit():
                print("Errore: --giorni richiede un numero (es. --giorni 2).", file=sys.stderr)
                sys.exit(1)
            giorni = int(args[i + 1])
        fids = fixtures_in_programma(sb, giorni)
    if not fids:
        print("Nessuna partita trovata.")
        return
    print(f"Partite: {len(fids)}")
    for fid in fids:
        d = sb.rpc("get_direction", {"p_fixture_id": fid}).execute().data
        if not d or d.get("error"):
            print(f"  fixture {fid}: {d.get('error') if d else 'nessun dato dalla RPC'}.")
        elif not d.get("markets"):
            print(f"  fixture {fid}: 0 mercati calibrati (dati insufficienti).")
        else:
            stampa(d)


if __name__ == "__main__":
    main()
