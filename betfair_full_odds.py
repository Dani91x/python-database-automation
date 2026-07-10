"""
betfair_full_odds.py — fetch ADDITIVO delle quote Betfair COMPLETE (tutti i mercati,
back + lay) per le partite di OGGI, in tabella betfair_market_odds.

NON e' il report .bat: NON tocca Google Sheets ne' il Money Management. Fa solo:
login Betfair -> abbina ogni evento Betfair a UNA fixture del DB (matching
affidabile, 1:1) -> scarica TUTTI i mercati + back/lay (EX_BEST_OFFERS, 3 livelli)
-> upsert in betfair_market_odds.

MONEY-CRITICAL: le quote DEVONO essere abbinate alla partita giusta. Vedi
Betfair/betfair_match.py per le garanzie (fuzzy come il foglio + gate temporale +
assegnazione 1:1, niente collisioni/sovrascritture).

FINESTRA: SOLO eventi di OGGI (to_date = fine giornata UTC), identica al report.
NON include il giorno successivo.

Uso:
  python betfair_full_odds.py                 # tutti gli eventi calcio di oggi
  python betfair_full_odds.py --filter kuwait # solo eventi che contengono "kuwait" (test)

NOTA: le quote di OGGI vengono SEMPRE cancellate e riscritte da zero (idempotente).
La run riparte sempre pulita: niente resume parziale (evita mix stale+fresh).
"""
import sys
import time
import argparse
import datetime as dt
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

# --- RISPETTO LIMITI BETFAIR (tassativo: niente ban) ---
# listMarketBook: peso max 200/chiamata, EX_BEST_OFFERS = 5/mercato -> batch 39 = peso 39*5 = 195 (< 200).
# Delay 0.6s tra OGNI chiamata (best-practice anti-throttling). Stop immediato sui limiti.
BATCH = 39            # mercati per listMarketBook (peso 39*5 = 195 < 200)
REQ_DELAY = 0.6       # secondi tra chiamate
# EVENT_DELAY ridotto 0.4 -> 0.2: col catalogo a chunk (CAT_CHUNK eventi/chiamata) e i book
# a batch 39 le richieste per evento calano di ~2-3x, quindi il ritmo complessivo resta
# uguale o piu' lento di prima. REQ_DELAY 0.6 tra le chiamate resta INVARIATO.
EVENT_DELAY = 0.2     # secondi extra tra eventi
# listMarketCatalogue: tetto 1000 risultati/chiamata; con ~30-60 mercati/evento,
# 12 eventi = max ~720 risultati (largo sotto il tetto). Se una risposta tocca il
# tetto (possibile troncamento) -> fallback per-evento, identico al comportamento storico.
# Peso projection: RUNNER_DESCRIPTION ed EVENT pesano 0 -> nessun problema di peso.
CAT_CHUNK = 12        # eventi per chiamata listMarketCatalogue
LIMIT_MARKERS = ("TOO_MANY_REQUESTS", "TOO_MUCH_DATA")


class BetfairLimitHit(RuntimeError):
    pass


def _is_limit(ex) -> bool:
    return any(m in str(ex) for m in LIMIT_MARKERS)


def _is_stmt_timeout(ex) -> bool:
    """Statement timeout Postgres (57014): quasi sempre ATTESA DI LOCK su
    betfair_market_odds (worker quote / stream / run appesa) piu' che scansione
    lenta — la tabella e' piccola. Ritentabile con backoff."""
    s = str(ex)
    return "57014" in s or "statement timeout" in s.lower()


def _delete_with_retry(sb, filters, *, what, retries=6, base_delay=1.5):
    """DELETE su betfair_market_odds resiliente a lock/timeout (57014).
    Ritenta con backoff lineare: se un altro processo tiene il lock, di norma
    lo rilascia entro pochi secondi. Sui limiti Betfair NON c'entra (e' solo DB).
    Rilancia l'ultima eccezione se non e' un timeout o se esauriamo i tentativi."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            q = sb.table("betfair_market_odds").delete()
            for col, val in filters:
                q = q.eq(col, val)
            return q.execute()
        except Exception as ex:  # noqa: BLE001
            last = ex
            if not _is_stmt_timeout(ex) or attempt == retries:
                raise
            wait = base_delay * attempt
            print(f"  [retry {attempt}/{retries}] DELETE {what}: timeout/lock DB, "
                  f"ritento tra {wait:.1f}s...")
            time.sleep(wait)
    raise last  # difensivo: non dovrebbe mai arrivarci


def _insert_with_retry(sb, rows, *, what, retries=6, base_delay=1.5):
    """INSERT su betfair_market_odds resiliente a lock/timeout (57014).
    Stessa logica di _delete_with_retry: ritenta con backoff lineare."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            return sb.table("betfair_market_odds").insert(rows).execute()
        except Exception as ex:  # noqa: BLE001
            last = ex
            if not _is_stmt_timeout(ex) or attempt == retries:
                raise
            wait = base_delay * attempt
            print(f"  [retry {attempt}/{retries}] INSERT {what}: timeout/lock DB, "
                  f"ritento tra {wait:.1f}s...")
            time.sleep(wait)
    raise last  # difensivo


def best_levels(arr, n=3):
    return [{"price": x.get("price"), "size": x.get("size")} for x in (arr or [])[:n]]


def _list_catalogue(c, event_ids):
    """listMarketCatalogue per una lista di eventIds (stessi parametri della vecchia
    chiamata per-evento: nessun filtro marketTypeCodes, maxResults 1000). La projection
    EVENT (peso 0) serve SOLO al mapping evento->mercati; i dati per mercato
    (marketId, marketName, runners) sono identici a prima. Stop sui limiti + REQ_DELAY."""
    try:
        cats = c.betting_rpc("SportsAPING/v1.0/listMarketCatalogue",
                             {"filter": {"eventIds": event_ids}, "maxResults": 1000,
                              "marketProjection": ["RUNNER_DESCRIPTION", "EVENT"]}) or []
    except Exception as ex:
        if _is_limit(ex):
            raise BetfairLimitHit(str(ex))
        raise
    time.sleep(REQ_DELAY)
    return cats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", default="", help="processa solo eventi il cui nome contiene questa stringa")
    args = ap.parse_args()

    from db_client import get_supabase_client
    from Betfair.client import BetfairClient
    from Betfair.betfair_match import resolve_matches, load_name_map

    sb = get_supabase_client()
    today = dt.date.today().isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    # Fixture di OGGI (stessa finestra del report: [today 00:00, tomorrow 00:00) UTC)
    fx = sb.table("fixture_predictions").select(
        "fixture_id,home_team_name,away_team_name,fixture_date"
    ).gte("fixture_date", today + "T00:00:00").lt("fixture_date", tomorrow + "T00:00:00").execute().data
    print(f"Fixture DB di oggi ({today}): {len(fx)}")

    c = BetfairClient()
    c.login_cert()

    # SOLO eventi di OGGI: to_date = fine giornata UTC (identico a betfair_report_manager).
    # NIENTE giorno successivo.
    now_utc = datetime.now(timezone.utc)
    end_today = now_utc.replace(hour=23, minute=59, second=59, microsecond=0)
    to_date_str = end_today.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_evs = c.list_events(["1"], to_date=to_date_str) or []

    events = []
    for e in raw_evs:
        ev = e.get("event", {})
        events.append({
            "id": ev.get("id"),
            "name": ev.get("name", "") or "",
            "openDate": ev.get("openDate"),
        })
    if args.filter:
        events = [e for e in events if args.filter.lower() in e["name"].lower()]
    print(f"Eventi Betfair di OGGI (fino a {to_date_str}): {len(events)}")

    # MATCH 1:1 affidabile (fuzzy come il foglio + gate temporale + assegnazione unica)
    matched, unmatched = resolve_matches(events, fx, name_map=load_name_map())
    print(f"Match trovati: {len(matched)} | non matchati: {len(unmatched)}")

    # SICUREZZA anti-collisione: invariante garantito da resolve_matches (used_fx),
    # qui come tripwire money-critical: se mai saltasse, STOP prima di scrivere.
    fids = [m["fixture"]["fixture_id"] for m in matched]
    if len(fids) != len(set(fids)):
        raise RuntimeError("COLLISIONE fatale: stesso fixture_id assegnato a piu' eventi. STOP.")

    # PURGE quote di oggi: SEMPRE. La run riparte pulita (la precedente aveva
    # abbinamenti errati). Niente resume parziale -> niente mix stale+fresh.
    # NON deve MAI bloccare la run: se la purge globale va in lock/timeout DB, si
    # prosegue lo stesso -> ogni fixture viene ripulita per-fixture PRIMA di scrivere
    # (piu' sotto). Eventuali righe stale di fixture non piu' matchate oggi verranno
    # rimosse alla prossima run riuscita.
    try:
        _delete_with_retry(sb, [("run_date", today)], what=f"purge run_date={today}")
        print(f"[purge] cancellate tutte le quote run_date={today}")
    except Exception as ex:  # noqa: BLE001
        print(f"[purge] NON riuscita ({str(ex)[:120]}) -> proseguo con purge per-fixture.")

    written = 0
    written_fids = set()
    # Catalogo a CHUNK di eventi: 1 chiamata listMarketCatalogue ogni CAT_CHUNK eventi
    # (prima: 1 per evento). La selezione dei mercati e' IDENTICA (stessi parametri);
    # cambia solo il raggruppamento. L'elaborazione/scrittura resta per-evento come prima.
    for ci in range(0, len(matched), CAT_CHUNK):
        chunk_matches = matched[ci:ci + CAT_CHUNK]
        chunk_eids = [m["event"]["id"] for m in chunk_matches]

        cats_chunk = _list_catalogue(c, chunk_eids)
        cats_by_event = {}
        if len(cats_chunk) >= 1000:
            # Tetto maxResults toccato: la risposta puo' essere troncata.
            # Fallback per-evento (comportamento storico): nessun mercato perso.
            print(f"  [WARN] catalogo chunk {ci // CAT_CHUNK + 1}: tetto 1000 risultati -> fallback per-evento")
            for eid_fb in chunk_eids:
                cats_by_event[eid_fb] = _list_catalogue(c, [eid_fb])
        else:
            for mk in cats_chunk:
                eid_mk = (mk.get("event") or {}).get("id")
                if eid_mk:
                    cats_by_event.setdefault(eid_mk, []).append(mk)

        for m in chunk_matches:
            ev = m["event"]
            fixture = m["fixture"]
            eid = ev["id"]
            fid = fixture["fixture_id"]
            name = ev["name"]

            # difensivo: mai riscrivere due volte la stessa fixture nella stessa run
            if fid in written_fids:
                print(f"  [WARN] fixture {fid} gia' scritto in questa run: salto (anti-sovrascrittura).")
                continue

            # Ogni fixture e' ISOLATA: un errore qui (rete, dati, DB) NON deve mai
            # fermare la run -> log e passa alla prossima. UNICA eccezione: il limite
            # Betfair, che propaga per fermarsi PULITI (niente ban, niente retry-storm).
            try:
                cats = cats_by_event.get(eid, [])

                meta = {}
                mids = []
                for mk in cats:
                    mid = mk["marketId"]
                    mids.append(mid)
                    meta[mid] = {"name": mk["marketName"],
                                 "runners": {r["selectionId"]: (r.get("runnerName", "?"), r.get("sortPriority"))
                                             for r in mk.get("runners", [])}}

                books = []
                for i in range(0, len(mids), BATCH):  # peso = BATCH*5 = 195 < 200
                    try:
                        books += c.list_market_book(mids[i:i + BATCH]) or []
                    except Exception as ex:
                        if _is_limit(ex):
                            raise BetfairLimitHit(str(ex))
                        raise
                    time.sleep(REQ_DELAY)

                rows = []
                for b in books:
                    mm = meta.get(b["marketId"])
                    if not mm:
                        continue
                    for r in b.get("runners", []):
                        rn, sp = mm["runners"].get(r["selectionId"], ("?", None))
                        ex = r.get("ex", {})
                        rows.append({
                            "fixture_id": fid, "market_name": mm["name"], "selection": rn,
                            "sort_priority": sp, "market_id": b["marketId"], "run_date": today,
                            "back": best_levels(ex.get("availableToBack")),
                            "lay": best_levels(ex.get("availableToLay")),
                        })
                if not rows:
                    print(f"  [skip] '{name}' (fid {fid}): nessuna quota")
                    continue

                # Idempotenza: sostituisci SOLO le righe di QUESTO fixture per OGGI.
                _delete_with_retry(sb, [("fixture_id", fid), ("run_date", today)],
                                   what=f"fixture {fid} run_date={today}")
                for i in range(0, len(rows), 500):
                    _insert_with_retry(sb, rows[i:i + 500], what=f"fixture {fid}")
                written_fids.add(fid)
                written += 1

                tag = "strong" if m["strong"] else f"weak/{m['score']}"
                dtm = f"Δt={m['dt_min']}m" if m["dt_min"] is not None else "Δt=?"
                print(f"  [ok] {name} -> fid {fid} [{tag},{dtm}]: {len(rows)} righe "
                      f"({len(set(x['market_name'] for x in rows))} mercati) | DB: "
                      f"{fixture.get('home_team_name')} v {fixture.get('away_team_name')}")
                time.sleep(EVENT_DELAY)
            except BetfairLimitHit:
                raise  # propaga: stop pulito sui limiti Betfair
            except Exception as ex:  # noqa: BLE001
                print(f"  [ERRORE fixture {fid} '{name}']: {str(ex)[:160]} -> salto, continuo.")
                continue

    print(f"\nFatto. Eventi oggi: {len(events)} | match: {len(matched)} | fixture scritte: {written}")
    if unmatched:
        print(f"\nEventi NON matchati ({len(unmatched)}):")
        for u in unmatched:
            print(f"  [skip] '{u['event']['name']}'  ({u['reason']}, best={u['best_score']})")


if __name__ == "__main__":
    try:
        main()
    except BetfairLimitHit as ex:
        # mai retry-storm sui limiti: stop pulito (le fixture gia' scritte restano).
        print(f"\n[STOP LIMITE BETFAIR] interrotto per sicurezza (niente ban): {str(ex)[:140]}")
