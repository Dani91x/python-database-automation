"""league_orchestrator.py - Orchestratore A MANO di una lega (tutte le stagioni).

25/09/2026 - riscritto sugli stessi mattoni del recupero giornaliero:
  - "cosa manca" DERIVATO DAI DATI (season_gaps: partite FT senza righe per
    tabella di dettaglio, vuoti API gia' registrati esclusi);
  - quota: controllo PRIMA di ogni stagione, ricalcolo DOPO (api_quota);
  - stato di season_backfill_state DERIVATO (completed solo a stagione finita
    e senza buchi; un `completed` vecchio con buchi viene riaperto): lo stato
    non e' piu' una barriera, i dati si.
  - rilancio sulla stessa lega senza mancanze = ZERO chiamate API.

Uso:
  python league_orchestrator.py --league 135 --dry-run          (nessuna chiamata, nessuna scrittura)
  python league_orchestrator.py --league 135 --season 2026
  python league_orchestrator.py                                 (prompt interattivo come prima)

Prima (fino al 25/09): saltava le stagioni `completed` (anche in corso e con
buchi), rifaceva TUTTE le partite con 5 chiamate ciascuna e chiudeva sempre
`completed`, anche con i flag di coverage False (135/2026: 15 chiamate, 0 eventi).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import season_aggregates as sa
import season_backfill as sb_mod
import season_gaps as sg
from api_quota import GestoreQuota, QuotaNonLeggibile

logger = logging.getLogger("league_orchestrator")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

_supabase = None


def get_supabase():
    global _supabase
    if _supabase is None:
        from db_client import get_supabase_client
        _supabase = get_supabase_client()
    return _supabase


def refresh_coverage_mv() -> None:
    """Refresh della MV di reporting (dashboard). Non blocca: logga e continua."""
    try:
        get_supabase().rpc("refresh_api_coverage_by_season_v2_mv", {}).execute()
        logger.info("Refresh MV api_coverage_by_season_v2_mv completato.")
    except Exception as e:
        logger.error("Refresh MV fallito (non blocco l'orchestratore): %s", e)


def _flag_str(flags: Dict[str, bool]) -> str:
    return " ".join("S" if flags[k] else "-" for k in sg.ENDPOINTS)


def _mancanti_str(piano: sb_mod.Piano) -> str:
    """5 colonne larghe 6: n = da chiamare (flag True); (n) = senza righe ma flag False."""
    parti = []
    for chiave, (tab, _, _) in sg.ENDPOINTS.items():
        n = piano.lacune.n(tab, sg.STATI_DA_CHIAMARE)
        if piano.flags[chiave]:
            parti.append(f"{n:>6}")
        else:
            parti.append(f"{'(' + str(n) + ')' if n else '-':>6}")
    return "".join(parti)


def backfill_full_league(league_id: int, season: Optional[int] = None, dry_run: bool = False,
                         sb: Any = None, quota: Any = None, client: Any = None,
                         stampa=print, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Elabora tutte le stagioni (o una sola) di una lega. Ritorna il riepilogo."""
    sb = sb or get_supabase()
    oggi = oggi or datetime.now(timezone.utc).date()
    if not dry_run:
        sg.verifica_migrazione(sb)
    else:
        # anche il dry-run ha bisogno della RPC per contare le mancanze
        sg.lacune_stagione(sb, 0, 0)
    sa.verifica_migrazione(sb)      # aggregati: migrations/season_aggregates_2026-09-25.sql

    coperture = sg.leggi_coverage(sb, league_id)
    if season is not None:
        coperture = [r for r in coperture if int(r["season_year"]) == int(season)]
    if not coperture:
        stampa(f"Nessuna stagione in api_coverage_by_season per lega {league_id}"
               + (f" stagione {season}" if season is not None else "") + ". Nulla da fare.")
        return {"stagioni": 0, "chiamate": 0, "fermato": None}
    stati = sg.leggi_stati(sb, league_id)

    if quota is None:
        from config import API_FOOTBALL_KEY
        if client is None and not dry_run:
            from api_client import APIFootballClient
            client = APIFootballClient()
        quota = GestoreQuota(sb=sb, api_key=API_FOOTBALL_KEY, client=client)
    st = quota.aggiorna()           # fail-loud se nessuna fonte (QuotaNonLeggibile)

    nome = coperture[0].get("league_name") or "?"
    paese = coperture[0].get("country_name") or "?"
    stampa("=" * 118)
    stampa(f"ORCHESTRATORE {'- DRY-RUN (nessuna chiamata API, nessuna scrittura)' if dry_run else ''}"
           f"  lega {league_id} ({nome}, {paese})  oggi {oggi.isoformat()} UTC")
    stampa(f"Quota API-Football: {st.riga()}")
    stampa("Flag = coverage per-partita ev/fo/sg/ss/qu = eventi/formazioni/stat. giocatori/stat. squadra/quote "
           "(S=True). Mancano = partite FT da chiamare;")
    stampa("(n) = partite senza righe ma flag False: NON si chiamano (se l'API ha acceso il flag, lo aggiorna il "
           "mapper). Att. = vuote in attesa del 2o tentativo; Vuoti = vuote definitive dell'API;"
           " N.disp = quote di partite oltre 7 gg (storico API 7 gg: non recuperabili, non si chiamano).")
    stampa("Riga 'aggregati' per stagione: nome=stato(ultimo aggiornamento) ~chiamate. Stati: ok, mancante, "
           "da_aggiornare (cadenza: standings dopo ogni giornata, injuries ogni giorno, top_* settimanale), errore,"
           " vuoto_api (l'API non ha dati), flag_false (coverage False: non si chiama). Chiam.~ li include.")
    stampa("-" * 118)
    stampa(f"{'':<6}{'':<33}{'':<11}{'':<11}{'':>8} {'--- mancano (partite FT) ---':^30}")
    stampa(f"{'Stag.':<6}{'Stato DB -> calcolato':<33}{'Fine':<11}{'Flag':<11}{'FT':>8} "
           f"{'ev':>6}{'fo':>6}{'sg':>6}{'ss':>6}{'qu':>6}{'Att.':>6}{'Vuoti':>6}{'N.disp':>7}{'Chiam.~':>9}  Decisione")

    margine_sim = quota.margine()
    riepilogo: Dict[str, Any] = {"stagioni": len(coperture), "chiamate": 0, "fermato": None,
                                 "per_stagione": []}
    fermo = False
    for row in coperture:
        sy = int(row["season_year"])
        prec = stati.get((league_id, sy))
        piano = sb_mod.pianifica(sb, row, prec, includi_mai_caricate=True, oggi=oggi)
        vuoti = sum(piano.lacune.n(t, ("vuoto_definitivo",)) for t in piano.lacune.tabelle_attive(piano.flags))
        stato_str = f"{piano.stato_attuale or '(nessuno)'} -> {piano.stato_calcolato}"
        if piano.stato_attuale == "completed" and piano.stato_calcolato != "completed":
            stato_str += " RIAP"

        if fermo:
            decisione = "in coda (dopo lo stop)"
        elif not piano.c_e_lavoro:
            decisione = "niente da fare (0 chiamate)"
        elif dry_run:
            if margine_sim >= piano.costo:
                decisione = "procederei"
                margine_sim -= piano.costo
            elif piano.costo > quota.capacita_giornaliera() and margine_sim >= piano.chiamate_fisse + 5:
                decisione = f"procederei a spezzoni (~{margine_sim} oggi)"
                margine_sim = 0
            else:
                decisione = f"MI FERMEREI qui (margine {margine_sim} < {piano.costo})"
                fermo = True
        else:
            decisione = sb_mod.decidi(piano, quota)
            if decisione == "mi_fermo":
                fermo = True
                decisione = f"MI FERMO (margine {quota.margine()} < {piano.costo}): riprendo domani"
        ft = "mai car." if piano.serve_fixtures else str(piano.lacune.ft_totali)
        stampa(f"{sy:<6}{stato_str:<33}{str(row.get('season_end') or '?')[:10]:<11}{_flag_str(piano.flags):<11}"
               f"{ft:>8} {_mancanti_str(piano)}{piano.lacune.in_attesa(piano.flags):>6}"
               f"{vuoti:>6}{piano.lacune.non_disponibili(piano.flags):>7}{piano.costo:>9}  {decisione}")
        stampa("      " + sa.riga_dry_run(piano.lacune.aggregati))
        spenti_con_buchi = [c for c, on in piano.flags.items()
                            if not on and piano.lacune.n(sg.ENDPOINTS[c][0], sg.STATI_DA_CHIAMARE)]
        if spenti_con_buchi and sg.e_corrente_o_recente(row, oggi):
            stampa(f"      ATTENZIONE {sy}: stagione viva con partite FT senza dati e flag False "
                   f"({', '.join(spenti_con_buchi)}): se API-Football li ha accesi, `python leagues_mapper.py` "
                   f"(1 chiamata) li aggiorna e il rilancio li recupera.")

        voce = {"season_year": sy, "costo": piano.costo, "decisione": decisione,
                "stato_attuale": piano.stato_attuale, "stato_calcolato": piano.stato_calcolato}
        riepilogo["per_stagione"].append(voce)
        if dry_run:
            continue
        if not piano.c_e_lavoro:
            sb_mod.scrivi_stato_senza_lavoro(sb, piano, prec, "orchestratore", oggi)
            continue
        if fermo:
            riepilogo["fermato"] = "quota"
            continue
        es = sb_mod.esegui(sb, client, quota, piano, prec, "orchestratore", oggi=oggi)
        riepilogo["chiamate"] += es.chiamate
        voce.update({"chiamate": es.chiamate, "stato": es.stato, "buchi_aperti": es.buchi_aperti,
                     "errore": es.errore, "fermato_per": es.fermato_per})
        quota.aggiorna()            # RICALCOLO dopo ogni lega-stagione (ordine utente punto 4)
        stampa("   " + sb_mod.riga_log_dopo(es, quota, None))
        if es.fermato_per:
            fermo = True
            riepilogo["fermato"] = es.fermato_per

    stampa("-" * 118)
    if dry_run:
        tot = sum(v["costo"] for v in riepilogo["per_stagione"])
        stampa(f"Totale chiamate stimate per chiudere tutti i buchi della lega: ~{tot}. "
               f"Margine di oggi: {quota.margine()}. Nulla e' stato chiamato ne' scritto.")
    else:
        stampa(f"Chiamate fatte: {riepilogo['chiamate']}. {quota.stato.riga() if quota.stato else ''}")
        refresh_coverage_mv()
    return riepilogo


def ask_and_run_cli() -> None:
    print("==============================================")
    print("  Orchestratore backfill lega + stagioni")
    print("==============================================")
    while True:
        league_input = input("Inserisci league_id (oppure premi INVIO per uscire): ").strip()
        if not league_input:
            print("Uscita dall'orchestratore.")
            break
        try:
            league_id = int(league_input)
        except ValueError:
            print("Inserisci un intero valido per league_id.")
            continue
        backfill_full_league(league_id)


def _stdout_robusto() -> None:
    """Console Windows cp1252: gli script vecchi stampano emoji -> UnicodeEncodeError
    dentro il lavoro (visto nella prova). Si sostituisce il carattere, non si muore."""
    for flusso in (sys.stdout, sys.stderr):
        try:
            flusso.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _stdout_robusto()
    ap = argparse.ArgumentParser(description="Backfill di una lega: SOLO cio' che manca, dentro la quota.")
    ap.add_argument("--league", type=int, help="league_id (senza: prompt interattivo)")
    ap.add_argument("--season", type=int, help="una sola stagione (default: tutte)")
    ap.add_argument("--dry-run", action="store_true",
                    help="mostra cosa farebbe: NESSUNA chiamata API (salvo /status, gratuita) e NESSUNA scrittura")
    args = ap.parse_args(argv)
    if args.league is None:
        if args.dry_run or args.season is not None:
            ap.error("--season/--dry-run richiedono --league")
        ask_and_run_cli()
        return 0
    try:
        backfill_full_league(args.league, args.season, args.dry_run)
    except QuotaNonLeggibile as e:
        print(f"NON PARTO: {e}")
        return 2
    except sg.MigrazioneMancante as e:
        print(f"NON PARTO: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
