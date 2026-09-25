"""season_gaps.py - "Cosa manca" per (lega, stagione), DERIVATO DAI DATI (25/09/2026).

Mattoni condivisi da league_orchestrator.py (a mano), seasons_catchup.py (action
giornaliera) e daily_yesterday_backfill.py (fixture di ieri):

- quali partite FT (status_short FT/AET/PEN in `matches`) NON hanno righe in
  ciascuna tabella di dettaglio (nomi veri, da per_fixture_backfill.py):
      events       -> match_events        (flag fixtures_events,              /fixtures/events)
      lineups      -> match_lineups       (flag fixtures_lineups,             /fixtures/lineups)
      player_stats -> match_player_stats  (flag fixtures_statistics_players,  /fixtures/players)
      team_stats   -> match_team_stats    (flag fixtures_statistics_fixtures, /fixtures/statistics)
      odds         -> match_odds          (flag odds,                         /odds)
- tenendo conto delle fixture GIA' interrogate con risposta VUOTA
  (tabella `fixture_detail_checks`, migrazione season_gaps_2026-09-25.sql):
      da_chiamare     mai interrogata                      -> si chiama
      errore          ultimo tentativo in errore           -> si chiama
      da_richiamare   1 risposta vuota, attesa scaduta     -> si chiama (2o e ultimo tentativo)
      in_attesa       1 risposta vuota da < 2 giorni       -> NON si chiama ora (buco aperto)
      vuoto_definitivo 2 risposte vuote, oppure vuota chiesta >= 7 gg dopo la
                      partita -> l'API non ha il dato: NON e' un buco, si dichiara.
      non_disponibile solo match_odds, partita di oltre 7 giorni fa: API-Football
                      tiene lo storico quote solo 7 giorni (prova reale 25/09:
                      /odds?fixture=1223598, Serie A 2024 -> results 0) -> NON si
                      chiama, NON e' un buco recuperabile, si dichiara a parte.
  Una partita scritta a meta' (insert fallito) e' registrata 'parziale' e torna
  'errore' anche se ha righe. Per match_odds conta solo snapshot_type
  'api_football': le quote 'football_data_csv' sono un'altra fonte.
- lo stato di season_backfill_state deriva da qui: `completed` SOLO a stagione
  finita (season_end < oggi) e senza buchi aperti; altrimenti `in_progress`.

Tutto il calcolo pesante e' nella RPC `season_detail_gaps` (una query per
lega-stagione, NOT EXISTS su indice fixture_id) e `season_gaps_summary` (a
blocchi di lega-stagioni): nessuna lettura riga-per-riga delle tabelle enormi
(match_odds ~82M righe).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

MIGRAZIONE = "migrations/season_gaps_2026-09-25.sql"
FT_STATUSES = ("FT", "AET", "PEN")

# chiave coverage -> (tabella, colonna flag in api_coverage_by_season, endpoint API)
ENDPOINTS: Dict[str, Tuple[str, str, str]] = {
    "events": ("match_events", "fixtures_events", "/fixtures/events"),
    "lineups": ("match_lineups", "fixtures_lineups", "/fixtures/lineups"),
    "player_stats": ("match_player_stats", "fixtures_statistics_players", "/fixtures/players"),
    "team_stats": ("match_team_stats", "fixtures_statistics_fixtures", "/fixtures/statistics"),
    "odds": ("match_odds", "odds", "/odds"),
}
TABELLA_A_CHIAVE = {v[0]: k for k, v in ENDPOINTS.items()}
AGGREGATI = ("standings", "top_scorers", "top_assists", "top_cards", "injuries")
STATI_DA_CHIAMARE = ("da_chiamare", "errore", "da_richiamare")
STATI_APERTI = STATI_DA_CHIAMARE + ("in_attesa",)
FINESTRA_RECENTE_GIORNI = 30

COLONNE_COVERAGE = ("league_id,league_name,country_name,season_year,season_start,season_end,current,"
                    "fixtures_events,fixtures_lineups,fixtures_statistics_fixtures,"
                    "fixtures_statistics_players,standings,players,top_scorers,top_assists,"
                    "top_cards,injuries,predictions,odds")


class MigrazioneMancante(RuntimeError):
    """La migrazione season_gaps_2026-09-25.sql non e' applicata."""


def _e_funzione_mancante(err: Exception) -> bool:
    msg = str(err)
    return ("PGRST202" in msg or "Could not find the function" in msg
            or "PGRST205" in msg or "fixture_detail_checks" in msg and "does not exist" in msg
            or "42883" in msg or "42P01" in msg)


def _oggi() -> date:
    return datetime.now(timezone.utc).date()


def _data(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------
def flag_per_fixture(coverage_row: Dict[str, Any]) -> Dict[str, bool]:
    """{events, lineups, player_stats, team_stats, odds} -> bool dal record coverage."""
    return {k: bool(coverage_row.get(col)) for k, (_, col, _) in ENDPOINTS.items()}


def flag_aggregati(coverage_row: Dict[str, Any]) -> Dict[str, bool]:
    return {k: bool(coverage_row.get(k)) for k in AGGREGATI}


def e_corrente_o_recente(row: Dict[str, Any], oggi: Optional[date] = None) -> bool:
    oggi = oggi or _oggi()
    fine = _data(row.get("season_end"))
    return bool(row.get("current")) or (fine is not None and fine >= oggi - timedelta(days=FINESTRA_RECENTE_GIORNI))


def stagione_finita(row: Dict[str, Any], oggi: Optional[date] = None) -> bool:
    oggi = oggi or _oggi()
    fine = _data(row.get("season_end"))
    return fine is not None and fine < oggi and not bool(row.get("current"))


def stagione_iniziata(row: Dict[str, Any], oggi: Optional[date] = None) -> bool:
    oggi = oggi or _oggi()
    inizio = _data(row.get("season_start"))
    return inizio is None or inizio <= oggi


# ---------------------------------------------------------------------------
# Lacune
# ---------------------------------------------------------------------------
@dataclass
class Lacune:
    league_id: int
    season_year: int
    partite_totali: int = 0
    ft_totali: int = 0
    # tabella -> stato -> set(fixture_id)   (stati: vedi docstring del modulo)
    per_tabella: Dict[str, Dict[str, Set[int]]] = field(default_factory=dict)
    # tabella -> stato -> n (quando si hanno solo i conteggi: season_gaps_summary)
    conteggi: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # 25/09 (seguito): aggregati per lega-stagione, nome -> {stato, n, ultimo, costo}
    # (season_aggregates.calcola); vuoto = non ancora calcolati
    aggregati: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def agg_da_fare(self) -> List[str]:
        return [nome for nome, a in self.aggregati.items() if a.get("stato") in ("mancante", "da_aggiornare", "errore")]

    def chiamate_aggregati(self) -> int:
        return sum(int(a.get("costo") or 0) for a in self.aggregati.values())

    def n(self, tabella: str, stati: Sequence[str]) -> int:
        if self.per_tabella:
            return sum(len(self.per_tabella.get(tabella, {}).get(s, ())) for s in stati)
        return sum(int(self.conteggi.get(tabella, {}).get(s, 0)) for s in stati)

    def tabelle_attive(self, flags: Dict[str, bool]) -> List[str]:
        return [ENDPOINTS[k][0] for k, on in flags.items() if on]

    def da_chiamare_per_fixture(self, flags: Dict[str, bool]) -> Dict[int, List[str]]:
        """fixture_id -> [chiavi endpoint da chiamare], SOLO endpoint con flag True."""
        out: Dict[int, List[str]] = {}
        for chiave, on in flags.items():
            if not on:
                continue
            tabella = ENDPOINTS[chiave][0]
            for stato in STATI_DA_CHIAMARE:
                for fid in self.per_tabella.get(tabella, {}).get(stato, ()):
                    out.setdefault(int(fid), []).append(chiave)
        return {fid: sorted(v, key=list(ENDPOINTS).index) for fid, v in sorted(out.items())}

    def chiamate_per_fixture(self, flags: Dict[str, bool]) -> int:
        return sum(self.n(t, STATI_DA_CHIAMARE) for t in self.tabelle_attive(flags))

    def aperti(self, flags: Dict[str, bool]) -> int:
        """Buchi aperti: partite-tabella + aggregati da fare (mancanti/da aggiornare/in errore)."""
        return sum(self.n(t, STATI_APERTI) for t in self.tabelle_attive(flags)) + len(self.agg_da_fare())

    def in_attesa(self, flags: Dict[str, bool]) -> int:
        return sum(self.n(t, ("in_attesa",)) for t in self.tabelle_attive(flags))

    def errori(self, flags: Dict[str, bool]) -> int:
        return sum(self.n(t, ("errore",)) for t in self.tabelle_attive(flags))

    def per_tabella_conteggi(self, flags: Dict[str, bool]) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for chiave, (tabella, _, _) in ENDPOINTS.items():
            out[tabella] = {
                "flag": bool(flags.get(chiave)),
                "da_chiamare": self.n(tabella, STATI_DA_CHIAMARE),
                "errore": self.n(tabella, ("errore",)),
                "in_attesa": self.n(tabella, ("in_attesa",)),
                "vuoti_definitivi": self.n(tabella, ("vuoto_definitivo",)),
                "non_disponibili": self.n(tabella, ("non_disponibile",)),
            }
        return out

    def non_disponibili(self, flags: Dict[str, bool]) -> int:
        return sum(self.n(t, ("non_disponibile",)) for t in self.tabelle_attive(flags))


def _righe_rpc(resp: Any) -> List[Dict[str, Any]]:
    return list(getattr(resp, "data", None) or [])


def _applica_righe(l: Lacune, righe: Iterable[Dict[str, Any]], con_id: bool) -> None:
    for r in righe:
        tab, stato, n = r.get("tabella"), r.get("stato"), int(r.get("n") or 0)
        if tab == "_partite":
            if stato == "ft":
                l.ft_totali = n
            elif stato == "tutte":
                l.partite_totali = n
            continue
        l.conteggi.setdefault(tab, {})[stato] = n
        if con_id:
            l.per_tabella.setdefault(tab, {})[stato] = {int(x) for x in (r.get("fixture_ids") or [])}


def lacune_stagione(sb: Any, league_id: int, season_year: int,
                    fixture_ids: Optional[List[int]] = None) -> Lacune:
    """Una RPC: tutte le lacune (con gli id) di una lega-stagione (o di alcune fixture)."""
    try:
        resp = sb.rpc("season_detail_gaps", {"p_league_id": int(league_id),
                                             "p_season_year": int(season_year),
                                             "p_fixture_ids": fixture_ids}).execute()
    except Exception as e:
        if _e_funzione_mancante(e):
            raise MigrazioneMancante(
                f"RPC season_detail_gaps assente: applica {MIGRAZIONE} (errore: {e})") from e
        raise
    l = Lacune(int(league_id), int(season_year))
    _applica_righe(l, _righe_rpc(resp), con_id=True)
    return l


def riepilogo_lacune(sb: Any, coppie: Sequence[Tuple[int, int]], blocco: int = 20) -> Dict[Tuple[int, int], Lacune]:
    """Solo conteggi, a blocchi di `blocco` lega-stagioni per RPC."""
    out: Dict[Tuple[int, int], Lacune] = {(int(a), int(b)): Lacune(int(a), int(b)) for a, b in coppie}
    lista = list(out)
    for i in range(0, len(lista), blocco):
        pezzo = lista[i:i + blocco]
        try:
            resp = sb.rpc("season_gaps_summary", {"p_league_ids": [p[0] for p in pezzo],
                                                  "p_season_years": [p[1] for p in pezzo]}).execute()
        except Exception as e:
            if _e_funzione_mancante(e):
                raise MigrazioneMancante(
                    f"RPC season_gaps_summary assente: applica {MIGRAZIONE} (errore: {e})") from e
            raise
        per_coppia: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for r in _righe_rpc(resp):
            per_coppia.setdefault((int(r["league_id"]), int(r["season_year"])), []).append(r)
        for k, righe in per_coppia.items():
            if k in out:
                _applica_righe(out[k], righe, con_id=False)
    return out


def verifica_migrazione(sb: Any) -> None:
    """Fail-loud se la migrazione non e' applicata (chiamate innocue: lega 0, lista vuota)."""
    lacune_stagione(sb, 0, 0)
    registra_esiti(sb, [{"fixture_id": 0, "tabella": "match_events", "league_id": 0,
                         "season_year": 0, "esito": "sonda"}], obbligatorio=True)


# ---------------------------------------------------------------------------
# Esiti delle chiamate (risposte vuote / errori) -> fixture_detail_checks
# ---------------------------------------------------------------------------
_avviso_registro_dato = False


def registra_esiti(sb: Any, righe: List[Dict[str, Any]], obbligatorio: bool = False) -> bool:
    """righe: [{fixture_id, tabella, league_id, season_year, esito: 'vuoto'|'errore'}].
    obbligatorio=False (Daily): se la migrazione manca avvisa FORTE una volta e
    continua; obbligatorio=True (catchup/orchestratore): solleva."""
    global _avviso_registro_dato
    if not righe:
        return True
    try:
        sb.rpc("record_fixture_detail_checks", {"p_rows": righe}).execute()
        return True
    except Exception as e:
        if obbligatorio:
            if _e_funzione_mancante(e):
                raise MigrazioneMancante(f"RPC record_fixture_detail_checks assente: applica {MIGRAZIONE}") from e
            raise
        if not _avviso_registro_dato:
            print(f"[LACUNE] ATTENZIONE: risposte vuote/errori NON registrate ({e}). "
                  f"Se la RPC manca applica {MIGRAZIONE}: senza, le fixture vuote verranno "
                  f"richiamate a ogni recupero.")
            _avviso_registro_dato = True
        return False


# ---------------------------------------------------------------------------
# Stato per stagione (derivato dai dati)
# ---------------------------------------------------------------------------
def calcola_stato(coverage_row: Dict[str, Any], lacune: Lacune, oggi: Optional[date] = None) -> str:
    oggi = oggi or _oggi()
    flags = flag_per_fixture(coverage_row)
    if stagione_finita(coverage_row, oggi) and lacune.aperti(flags) == 0 and lacune.ft_totali > 0:
        return "completed"
    return "in_progress"


def costruisci_stats_json(coverage_row: Dict[str, Any], lacune: Lacune, stato_precedente: Optional[Dict[str, Any]],
                          fonte: str, esito: Optional[Dict[str, Any]] = None,
                          oggi: Optional[date] = None,
                          tentativi_aggregati: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """stats_json v2. `fixtures.matches_count` resta (lo legge training_planner nel fallback)."""
    oggi = oggi or _oggi()
    flags = flag_per_fixture(coverage_row)
    aperti = lacune.aperti(flags)
    prec = (stato_precedente or {}).get("stats_json") or {}
    aperto_dal = None
    if aperti > 0:
        aperto_dal = prec.get("buco_aperto_dal") if (prec.get("meta") or {}).get("version") == "v2" else None
        aperto_dal = aperto_dal or oggi.isoformat()
    return {
        "meta": {"version": "v2", "fonte": fonte,
                 "aggiornato_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "coverage": {**flags, **flag_aggregati(coverage_row)},
        "fixtures": {"matches_count": lacune.partite_totali, "ft_count": lacune.ft_totali},
        "lacune": lacune.per_tabella_conteggi(flags),
        "buchi_aperti": aperti,
        "chiamate_stimate": lacune.chiamate_per_fixture(flags),
        "buco_aperto_dal": aperto_dal,
        "ultimo_esito": esito or {},
        "aggregati": {n: a.get("stato") for n, a in lacune.aggregati.items()},
        # ultimo tentativo per aggregato {at, esito}: serve a non richiamare un aggregato vuoto
        "aggregati_tentativi": {**(prec.get("aggregati_tentativi") or {}), **(tentativi_aggregati or {})},
    }


def giorni_aperto(stats_json: Dict[str, Any], oggi: Optional[date] = None) -> int:
    oggi = oggi or _oggi()
    d = _data((stats_json or {}).get("buco_aperto_dal"))
    return (oggi - d).days if d else 0


def scrivi_stato(sb: Any, league_id: int, season_year: int, status: str, stats_json: Dict[str, Any]) -> None:
    sb.table("season_backfill_state").upsert({
        "league_id": int(league_id), "season_year": int(season_year), "status": status,
        "last_run_at": datetime.now(timezone.utc).isoformat(), "stats_json": stats_json,
    }, on_conflict="league_id,season_year").execute()


def scrivi_stati(sb: Any, righe: List[Dict[str, Any]], blocco: int = 200) -> None:
    """Upsert a blocchi di stati gia' calcolati: [{league_id, season_year, status, stats_json}]."""
    adesso = datetime.now(timezone.utc).isoformat()
    for i in range(0, len(righe), blocco):
        pezzo = [{**r, "last_run_at": adesso} for r in righe[i:i + blocco]]
        sb.table("season_backfill_state").upsert(pezzo, on_conflict="league_id,season_year").execute()


def leggi_stati(sb: Any, league_id: Optional[int] = None, pagina: int = 1000) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """season_backfill_state paginato (una lega o tutte).
    Tutte le leghe (recupero giornaliero, ~7.000 righe): si leggono SOLO i
    campi JSON che servono (versione, buco_aperto_dal, ft_count) e si ricompone
    uno stats_json minimo, per non scaricare MB di stats_json."""
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    inizio = 0
    leggero = league_id is None
    colonne = ("league_id,season_year,status,last_run_at,versione:stats_json->meta->>version,"
               "buco_aperto_dal:stats_json->>buco_aperto_dal,ft_count:stats_json->fixtures->>ft_count,"
               "aggregati_tentativi:stats_json->aggregati_tentativi"
               if leggero else "league_id,season_year,status,last_run_at,stats_json")
    while True:
        q = sb.table("season_backfill_state").select(colonne)
        if league_id is not None:
            q = q.eq("league_id", int(league_id))
        resp = q.order("league_id").order("season_year").range(inizio, inizio + pagina - 1).execute()
        righe = list(getattr(resp, "data", None) or [])
        for r in righe:
            try:
                if leggero:
                    r = {"league_id": r["league_id"], "season_year": r["season_year"],
                         "status": r.get("status"), "last_run_at": r.get("last_run_at"),
                         "stats_json": {"meta": {"version": r.get("versione")},
                                        "buco_aperto_dal": r.get("buco_aperto_dal"),
                                        "fixtures": {"ft_count": r.get("ft_count")},
                                        "aggregati_tentativi": r.get("aggregati_tentativi") or {}}}
                out[(int(r["league_id"]), int(r["season_year"]))] = r
            except (KeyError, TypeError, ValueError):
                continue
        if len(righe) < pagina:
            return out
        inizio += pagina


def leggi_coverage(sb: Any, league_id: Optional[int] = None, pagina: int = 1000) -> List[Dict[str, Any]]:
    """api_coverage_by_season paginato (una lega o tutte), ordinato per lega/stagione."""
    out: List[Dict[str, Any]] = []
    inizio = 0
    while True:
        q = sb.table("api_coverage_by_season").select(COLONNE_COVERAGE)
        if league_id is not None:
            q = q.eq("league_id", int(league_id))
        resp = q.order("league_id").order("season_year").range(inizio, inizio + pagina - 1).execute()
        righe = list(getattr(resp, "data", None) or [])
        out.extend(righe)
        if len(righe) < pagina:
            return out
        inizio += pagina
