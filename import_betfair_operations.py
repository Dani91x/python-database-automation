# -*- coding: utf-8 -*-
"""
import_betfair_operations.py — Importa le operazioni Betfair regolate nel Report
Personale (tabella personal_trades), raggruppate PER MERCATO, con P&L reale +
commissione reale + pronostici API-Football + direzioni motori congelati.

Default: giorno PRECEDENTE a oggi (le operazioni di ieri, viste stamattina).

Flusso:
  1) listClearedOrders SETTLED del giorno (livello BET per side/quota/stake/betId +
     livello MARKET per la commissione reale, che esiste solo a quel livello).
  2) Riconcilia ogni evento Betfair -> fixture del DB (resolve_matches, lo stesso
     matcher del report/quote, fuzzy + gate temporale + 1:1).
  3) Per ogni MERCATO ricostruisce: lato d'ingresso, quota media, stake, copertura
     (stake sul lato opposto/hedge), P&L netto reale (profit - commissione).
  4) Congela in `context`: pronostici API-Football (advice, under/over, gol attesi)
     + direzioni motori (get_direction) + risultato reale + "hit" (azzeccato o no).
  5) upsert_imported_trade (idempotente su market+giorno): ri-eseguibile.

Uso:
  python import_betfair_operations.py                 # ieri
  python import_betfair_operations.py --date 2026-07-05
  python import_betfair_operations.py --dry-run       # non scrive: stampa le righe

MONEY-CRITICAL: il P&L netto usa il profit + la commissione REALI di Betfair; i
campi descrittivi (quota d'ingresso, copertura) sono ricostruiti dal dettaglio BET.
"""
from __future__ import annotations
import sys, time, json, re, argparse, datetime as dt
from collections import defaultdict

sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
sys.stdout.reconfigure(encoding="utf-8")

from db_client import get_supabase_client
from Betfair.client import BetfairClient
from Betfair.betfair_match import resolve_matches, load_name_map

# colonne fixture_predictions necessarie (riconciliazione + pronostici + risultato)
FP_COLS = (
    "fixture_id,home_team_name,away_team_name,fixture_date,league_id,league_name,"
    "season_year,result_home_goals,result_away_goals,result_outcome,"
    "result_status_short,result_total_goals,advice,under_over_line,goals_home_line,"
    "goals_away_line,percent_home,percent_draw,percent_away,winner_name,raw_json"
)


def _line_from_market_type(mt: str):
    """OVER_UNDER_35 -> 3.5 ; OVER_UNDER_05 -> 0.5 (cifre finali /10).
    None per mercati senza linea (MATCH_ODDS, CORRECT_SCORE, ...)."""
    if not mt:
        return None
    import re
    m = re.search(r"(\d{2,3})$", mt)
    if m and ("OVER_UNDER" in mt or "GOALS" in mt or "TOTAL" in mt):
        return int(m.group(1)) / 10.0
    return None


def _country_from_fp(fp: dict):
    """Nazione lega da API-Football: raw_json.response[0].league.country."""
    rj = fp.get("raw_json")
    if isinstance(rj, dict):
        resp = rj.get("response") or []
        if resp and isinstance(resp[0], dict):
            c = ((resp[0].get("league") or {}).get("country"))
            if c:
                return c
    return None


def _fetch_cleared(c: BetfairClient, group: str, frm: str, to: str):
    out, rec = [], 0
    while True:
        res = c.betting_rpc("SportsAPING/v1.0/listClearedOrders", {
            "betStatus": "SETTLED",
            "settledDateRange": {"from": frm, "to": to},
            "groupBy": group,
            "includeItemDescription": True,
            "fromRecord": rec, "recordCount": 1000,
        }) or {}
        chunk = res.get("clearedOrders") or []
        out.extend(chunk)
        if not res.get("moreAvailable") or not chunk:
            break
        rec += len(chunk)
    return out


def _wavg(pairs):
    """media pesata di (valore, peso); None se peso totale 0."""
    num = sum(v * w for v, w in pairs if v is not None and w)
    den = sum(w for _, w in pairs if w)
    return (num / den) if den else None


def _mins_between(a_iso: str, b_iso: str):
    try:
        a = dt.datetime.fromisoformat(a_iso.replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(b_iso.replace("Z", "+00:00"))
        return round(abs((b - a).total_seconds()) / 60.0, 1)
    except Exception:
        return None


def _dir_hit(market: str, direction, rh, ra):
    """La direzione del motore era azzeccata sul risultato REALE?
    True/False se calcolabile dal risultato finale, None se serve il parziale (HT)."""
    if rh is None or ra is None or not direction:
        return None
    tot = rh + ra
    if market == "1x2":
        out = "H" if rh > ra else ("A" if ra > rh else "D")
        return direction == out
    if market == "btts":
        return direction == ("Yes" if (rh > 0 and ra > 0) else "No")
    if market.startswith("over_"):
        m = re.search(r"(\d)_(\d)", market)
        if not m:
            return None
        line = float(f"{m.group(1)}.{m.group(2)}")
        return direction == ("Over" if tot > line else "Under")
    # ht_1x2 / first_half_*: serve il risultato PRIMO TEMPO, non disponibile -> None
    return None


def build_context(fp: dict, direction, result_ft):
    """Snapshot congelato: pronostici API-Football + direzioni motori + risultato + hit.
    Gli hit sono calcolati PER OGNI mercato-motore sul risultato reale (quando derivabile
    dal finale). I mercati di primo tempo restano None (serve il parziale)."""
    rh, ra = fp.get("result_home_goals"), fp.get("result_away_goals")
    tot = fp.get("result_total_goals")
    predictions = {
        "advice": fp.get("advice"),                 # "pronostico" (es. Combo Double chance...)
        "under_over_line": fp.get("under_over_line"),
        "goals_home_line": fp.get("goals_home_line"),  # possibili gol casa
        "goals_away_line": fp.get("goals_away_line"),  # possibili gol ospite
        "percent_home": fp.get("percent_home"),
        "percent_draw": fp.get("percent_draw"),
        "percent_away": fp.get("percent_away"),
        "winner_name": fp.get("winner_name"),
    }
    result = {
        "home_goals": rh, "away_goals": ra, "total_goals": tot,
        "outcome": fp.get("result_outcome"), "status": fp.get("result_status_short"),
        "ft": result_ft,
    }
    # hit per OGNI mercato presente nelle direzioni motori
    hits = {}
    for mk in ((direction or {}).get("markets") or []):
        h = _dir_hit(mk.get("market"), mk.get("direction"), rh, ra)
        if h is not None:
            hits[mk.get("market")] = h
    return {"predictions": predictions, "directions": direction, "result": result, "hits": hits}


def import_cash_movements(sb, c, from_date, to_date, dry_run):
    """Importa depositi/prelievi dal conto Betfair (Account API getAccountStatement)
    nel periodo. Movimenti di CASSA: NON entrano nell'equity curve. Idempotente su
    transaction_id. Ritorna (n_movimenti, depositi, prelievi)."""
    frm = from_date.strftime("%Y-%m-%dT00:00:00Z")
    to = (to_date + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    try:
        res = c.account_rpc("AccountAPING/v1.0/getAccountStatement", {
            "itemDateRange": {"from": frm, "to": to},
            "includeItem": "DEPOSITS_WITHDRAWALS",
        }) or {}
    except Exception as ex:  # noqa: BLE001 — la cassa non deve bloccare l'import trade
        print(f"[cassa] getAccountStatement fallito: {str(ex)[:120]}")
        return 0, 0.0, 0.0

    items = res.get("accountStatement") or []
    n, dep, wdr = 0, 0.0, 0.0
    for it in items:
        leg = it.get("legacyData") or {}
        mkt = (leg.get("marketName") or "").upper()
        mtype = "DEPOSIT" if mkt == "DEPOSIT" else "WITHDRAWAL" if mkt == "WITHDRAWAL" else None
        if not mtype:
            continue
        amount = it.get("amount")
        txid = str(leg.get("transactionId") or it.get("refId") or "")
        if not txid or amount is None:
            continue
        payload = {
            "transaction_id": txid,
            "ts": it.get("itemDate"),
            "type": mtype,
            "amount": amount,
            "balance": it.get("balance"),
            "description": leg.get("fullMarketName"),
        }
        if not dry_run:
            try:
                sb.rpc("upsert_cash_movement", {"p": payload}).execute()
            except Exception as ex:  # noqa: BLE001
                print(f"[cassa] upsert fallito ({txid}): {str(ex)[:100]}")
                continue
        n += 1
        if mtype == "DEPOSIT":
            dep += amount
        else:
            wdr += amount
    print(f"[cassa] movimenti: {n} | depositi {dep:+.2f} | prelievi {wdr:+.2f}"
          f"{'  [DRY-RUN]' if dry_run else ''}")
    return n, dep, wdr


def import_day(sb, c, day, dry_run):
    """Importa le operazioni Betfair regolate di UN giorno operativo.
    Ritorna (written, skipped, rows_preview). Un giorno vuoto non e' un errore."""
    nxt = day + dt.timedelta(days=1)
    FROM = day.strftime("%Y-%m-%dT00:00:00Z")
    TO = nxt.strftime("%Y-%m-%dT00:00:00Z")
    print(f"\n=== Giorno {day} (settled {FROM} -> {TO}) ===")

    bets = _fetch_cleared(c, "BET", FROM, TO)
    markets = _fetch_cleared(c, "MARKET", FROM, TO)
    print(f"  Cleared orders: {len(bets)} giocate (BET) | {len(markets)} mercati (MARKET)")
    if not bets:
        print("  Nessuna operazione regolata in questa data.")
        return 0, [], []

    comm_by_market = {m["marketId"]: (m.get("commission") or 0.0) for m in markets}
    outcome_by_market = {m["marketId"]: m.get("betOutcome") for m in markets}

    # eventi distinti (nome 'Home v Away' per resolve_matches; eventDesc usa ' - ')
    ev_by_id = {}
    for r in bets:
        eid = r.get("eventId")
        it = r.get("itemDescription") or {}
        if eid and eid not in ev_by_id:
            ev_by_id[eid] = {
                "id": eid,
                "name": (it.get("eventDesc") or "").replace(" - ", " v "),
                "openDate": it.get("marketStartTime"),
            }
    events = list(ev_by_id.values())

    # fixture: finestra ALLARGATA a +-1 giorno. I match a cavallo della mezzanotte
    # (kickoff sera, settle dopo le 00:00) hanno fixture_date sul giorno del match
    # ma cadono nella finestra "settled" del giorno dopo: senza allargare non si
    # riconciliano. Il gate temporale di resolve_matches (openDate vs fixture_date)
    # garantisce comunque l'abbinamento corretto, non forza match a orari diversi.
    prev = day - dt.timedelta(days=1)
    fx = sb.table("fixture_predictions").select(FP_COLS) \
        .gte("fixture_date", prev.isoformat() + "T00:00:00") \
        .lt("fixture_date", (nxt + dt.timedelta(days=1)).isoformat() + "T00:00:00").execute().data
    matched, unmatched = resolve_matches(events, fx, load_name_map())
    fp_by_eid = {m["event"]["id"]: m["fixture"] for m in matched}
    print(f"  Fixture giorno: {len(fx)} | eventi Betfair: {len(events)} | "
          f"riconciliati: {len(matched)} | non riconciliati: {len(unmatched)}")

    # giocate per mercato
    by_market = defaultdict(list)
    for r in bets:
        by_market[r["marketId"]].append(r)

    dir_cache = {}
    def get_dir(fid):
        if fid not in dir_cache:
            try:
                dir_cache[fid] = sb.rpc("get_direction", {"p_fixture_id": fid}).execute().data
            except Exception:
                dir_cache[fid] = None
        return dir_cache[fid]

    written, skipped, rows_preview = 0, [], []
    for market_id, rows in by_market.items():
        try:
            eid = rows[0].get("eventId")
            it0 = rows[0].get("itemDescription") or {}
            ev_desc = it0.get("eventDesc") or "?"
            fp = fp_by_eid.get(eid)
            if not fp:
                skipped.append((ev_desc, market_id, "fixture non riconciliata"))
                continue

            matched_rows = [r for r in rows if (r.get("sizeSettled") or 0) > 0]
            if not matched_rows:
                skipped.append((ev_desc, market_id, "solo frammenti cancellati"))
                continue

            # lato d'ingresso = quello della giocata abbinata piu' vecchia
            matched_rows.sort(key=lambda r: r.get("placedDate") or "")
            entry_side = (matched_rows[0].get("side") or "").lower()
            entry_rows = [r for r in matched_rows if (r.get("side") or "").lower() == entry_side]
            cov_rows = [r for r in matched_rows if (r.get("side") or "").lower() != entry_side]

            entry_stake = sum(r.get("sizeSettled") or 0 for r in entry_rows)
            entry_odds = _wavg([(r.get("priceMatched"), r.get("sizeSettled") or 0) for r in entry_rows])
            # LAY: responsabilita' esatta = Σ size*(price-1) (quanto si rischia/perde).
            # BACK: nessuna liability (si rischia lo stake). E' cio' che va nella colonna
            # "Stake Utilizzato" per il lato lay (richiesta utente).
            liability = (sum((r.get("sizeSettled") or 0) * ((r.get("priceMatched") or 1) - 1)
                             for r in entry_rows) if entry_side == "lay" else None)
            coverage = sum(r.get("sizeSettled") or 0 for r in cov_rows) or None

            gross = sum(r.get("profit") or 0 for r in matched_rows)
            commission = comm_by_market.get(market_id, 0.0)
            net = round(gross - commission, 2)

            # STATO dall'esito REALE dell'operazione (segno del netto): il betOutcome
            # di mercato Betfair non e' affidabile (risultava sempre WON).
            status = "WON" if net > 0 else "LOST" if net < 0 else "VOID"

            placed_min = min((r.get("placedDate") or "" for r in matched_rows), default="")
            start = it0.get("marketStartTime")
            # trade_date = GIORNO DEL MATCH (marketStartTime), non del regolamento: i
            # match notturni (settle dopo le 00:00) cadono cosi' nel giorno giusto.
            trade_date = (start or "")[:10] or day.isoformat()
            # Tempo operativo: NON calcolato dall'import — lo inserisce l'utente a mano
            # dalla dashboard (poi la €/h si ricalcola). Il re-import lo preserva.
            timing = "live" if (start and placed_min and placed_min >= start) else "prematch"

            rh, ra = fp.get("result_home_goals"), fp.get("result_away_goals")
            result_ft = f"{rh}-{ra}" if rh is not None and ra is not None else None
            # Strategia = "{Back/Lay} {selezione}" (es. "Lay Under 3,5 goal"), colorata
            # lato-Betfair nel frontend. Il customerStrategyRef originale va in nota.
            sel = it0.get("runnerDesc") or it0.get("marketType") or "?"
            strategia = f"{'Back' if entry_side == 'back' else 'Lay'} {sel}"
            ref = (entry_rows[0].get("customerStrategyRef") or "").strip()
            comment = f"ref: {ref}" if ref else None

            payload = {
                "fixture_id": fp["fixture_id"],
                "betfair_event_id": eid,
                "betfair_market_id": market_id,
                "league_id": fp.get("league_id"),
                "league_name": fp.get("league_name"),
                "country": _country_from_fp(fp),
                "season_year": fp.get("season_year"),
                "home_team": fp.get("home_team_name"),
                "away_team": fp.get("away_team_name"),
                "kickoff": start,
                "result_ft": result_ft,
                "strategia": strategia,
                "side": entry_side,
                "market": it0.get("marketType"),
                "selection": it0.get("runnerDesc"),
                "line": _line_from_market_type(it0.get("marketType")),
                "entry_odds": round(entry_odds, 3) if entry_odds else None,
                "stake": round(entry_stake, 2),
                "liability": round(liability, 2) if liability is not None else None,
                "coverage": round(coverage, 2) if coverage else None,
                "commission_amount": round(commission, 2),
                "gross_pnl": round(gross, 2),
                "net_pnl": net,
                "timing": timing,
                "trade_date": trade_date,
                "comment": comment,
                "context": build_context(fp, get_dir(fp["fixture_id"]), result_ft),
                "tags": ["import"],
            }

            if dry_run:
                rows_preview.append(payload)
            else:
                sb.rpc("upsert_imported_trade", {"p": payload}).execute()
            written += 1
        except Exception as ex:  # noqa: BLE001 — una riga non deve fermare l'import
            skipped.append((rows[0].get("itemDescription", {}).get("eventDesc", "?"),
                            market_id, f"errore: {str(ex)[:100]}"))
            continue

    print(f"  {'Pronte (dry-run)' if dry_run else 'Scritte'}: {written} | saltate: {len(skipped)}")
    for ev, mid, why in skipped:
        print(f"    [skip] {ev} · {mid}: {why}")
    return written, skipped, rows_preview


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="giorno operativo YYYY-MM-DD (default: ieri)")
    ap.add_argument("--days", type=int, default=0,
                    help="UNA TANTUM: importa gli ultimi N giorni (fino a ieri incluso). "
                         "Es. --days 15 per il backfill iniziale.")
    ap.add_argument("--dry-run", action="store_true", help="non scrive: stampa le righe")
    args = ap.parse_args()

    today = dt.date.today()
    if args.days and args.days > 0:
        # ultimi N giorni: da (oggi - N) fino a IERI incluso (oggi non e' regolato)
        days = [today - dt.timedelta(days=k) for k in range(args.days, 0, -1)]
    elif args.date:
        days = [dt.date.fromisoformat(args.date)]
    else:
        days = [today - dt.timedelta(days=1)]

    print(f"Import operazioni Betfair — {len(days)} giorno/i "
          f"({days[0]} -> {days[-1]}){'  [DRY-RUN]' if args.dry_run else ''}")

    sb = get_supabase_client()
    c = BetfairClient()
    c.login_cert()

    # Movimenti di cassa (depositi/prelievi) sul periodo — fuori dall'equity curve.
    import_cash_movements(sb, c, days[0], days[-1], args.dry_run)

    tot_written, tot_skipped, all_preview = 0, 0, []
    for day in days:
        try:
            w, sk, pv = import_day(sb, c, day, args.dry_run)
        except Exception as ex:  # noqa: BLE001 — un giorno non deve bloccare gli altri
            print(f"  [ERRORE giorno {day}]: {str(ex)[:160]} -> continuo.")
            continue
        tot_written += w
        tot_skipped += len(sk)
        all_preview.extend(pv)

    print(f"\n{'=' * 70}\nTOTALE: {tot_written} righe "
          f"{'pronte (dry-run)' if args.dry_run else 'scritte'} | "
          f"{tot_skipped} saltate | {len(days)} giorni")

    if args.dry_run and all_preview:
        print("\nTABELLA (campi base — T.Op/€/h li inserisci a mano; Stake=responsabilità sul lay):")
        print("Data | Evento | Lega | Naz | Stag | Home-Away | Ris | Strat | Q.ing | Stake | Cop | Net")
        for p in all_preview:
            stake_disp = (p.get("liability") if p.get("side") == "lay" and p.get("liability") is not None
                          else p.get("stake"))
            print(f"  {p['trade_date']} | {p['betfair_event_id']} | {p['league_name']} | "
                  f"{p.get('country') or '—'} | {p.get('season_year') or '—'} | "
                  f"{p['home_team']}-{p['away_team']} | {p.get('result_ft') or '—'} | "
                  f"{p['strategia']} | {p.get('entry_odds')} | {stake_disp} | "
                  f"{p.get('coverage') or '—'} | {p['net_pnl']}")


if __name__ == "__main__":
    main()
