"""db.py — scritture Supabase dello scanner Safe Strategy (service_role).

Pattern del repo (Betfair/stream/db.py): upsert IDEMPOTENTI, best-effort con
log; se la migrazione safe_strategy_scan.sql non è applicata il servizio NON
muore — warning una-tantum e si continua (modalità di fatto dry).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

logger = logging.getLogger(__name__)

_MISSING_TABLE_WARNED = False

# event_id per SELECT nella rilettura del pre_ko (URL della query: mai troppo lunga)
_PRE_KO_CHUNK = 40


def _warn_missing_table(exc: Exception) -> None:
    global _MISSING_TABLE_WARNED  # noqa: PLW0603 - log una-tantum
    if not _MISSING_TABLE_WARNED:
        _MISSING_TABLE_WARNED = True
        logger.warning(
            "[safe-scan] tabella safe_strategy_scan non disponibile: migrazione "
            "migrations/safe_strategy_scan.sql non applicata? Lo scanner continua "
            "senza scrivere (il frontend non vedrà nulla finché non la applichi). "
            "Dettaglio: %s",
            str(exc)[:160],
        )


def _is_missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "does not exist" in msg or "42p01" in msg or "pgrst205" in msg or "could not find" in msg


def list_scan_event_ids() -> Optional[List[str]]:
    """event_id presenti in tabella (per la pulizia delle righe orfane di
    istanze precedenti); None se la lettura fallisce."""
    sb = get_supabase_client()
    try:
        res = sb.table("safe_strategy_scan").select("event_id").execute()
        return [str(r["event_id"]) for r in (getattr(res, "data", None) or []) if r.get("event_id")]
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] lettura event_id KO: %s", str(e)[:160])
        return None


def load_scan_pre_ko(event_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Riferimenti 1X2 pre-KO gia' salvati, per gli event_id richiesti.

    Perche' esiste (CERT. 13/09, causa radice di "base e punta non scattano
    mai"): ``pre_ko`` viveva SOLO nella RAM dello scanner. ``freeze_pre_ko`` lo
    cattura solo PRIMA del calcio d'inizio e lo congela al primo tick in-play;
    a ogni riavvio del servizio (chiusura dell'app, crash + watchdog, modifica
    al codice) lo stato si azzerava e, per tutte le partite gia' in corso, il
    riferimento non poteva piu' nascere. Senza ``pre_ko`` non c'e' ``pre_match``,
    senza ``pre_match`` ``favorite_side`` torna None e i check di BASE e PUNTA
    escono ``ok=None`` -> stato "nd" -> scartate in silenzio. ESATTO non usa
    ``pre_ko`` in nessun punto: era l'unica a sopravvivere.

    Il dato era gia' sul DB (``safe_strategy_scan.payload.pre_ko``): era il
    codice stesso a distruggerlo, riscrivendo la riga con None al primo publish
    dopo il riavvio. Qui lo si rilegge.

    Lettura MIRATA (mai tutta la tabella: il payload e' grosso e la SELECT piena
    va in timeout) e a BLOCCHI, con la sola proiezione ``payload->pre_ko``.
    Best-effort come tutto il modulo: su errore torna quello che ha raccolto.
    """
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    ids = [str(e) for e in (event_ids or []) if e]
    if not ids:
        return out
    sb = get_supabase_client()
    for i in range(0, len(ids), _PRE_KO_CHUNK):
        chunk = ids[i:i + _PRE_KO_CHUNK]
        try:
            res = (
                sb.table("safe_strategy_scan")
                .select("event_id,payload->pre_ko")
                .in_("event_id", chunk)
                .execute()
            )
        except Exception as e:  # noqa: BLE001 - mai fatale: si continua senza
            if _is_missing_table(e):
                _warn_missing_table(e)
            else:
                logger.warning("[safe-scan] rilettura pre_ko KO: %s", str(e)[:160])
            # si torna cio' che si e' raccolto: i blocchi NON interrogati non
            # compaiono nel risultato, quindi il chiamante li ritenta (review 13/09)
            return out
        # ogni evento del blocco entra nel risultato, anche quando il
        # riferimento non c'e': "cercato e non trovato" e' un esito, e non va
        # confuso con "non ancora cercato"
        trovati = {str(r.get("event_id") or ""): r.get("pre_ko")
                   for r in (getattr(res, "data", None) or [])}
        for eid in chunk:
            pre = trovati.get(eid)
            # Q12 (25/09): anche la coppia pre-partita del TENNIS si reidrata
            usabile = is_usable_pre_ko(pre) or is_usable_pre_ko_tennis(pre)
            out[eid] = dict(pre) if usabile else None
    return out


def is_usable_pre_ko_tennis(pre: Any) -> bool:
    """Q12 (25/09): coppia pre-partita del tennis {p1, p2} completa e sensata:
    la STESSA condizione di `engine._tennis_pre_match`."""
    if not isinstance(pre, dict):
        return False
    for k in ("p1", "p2"):
        v = pre.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not (v > 1.0):
            return False
    return True


def is_usable_pre_ko(pre: Any) -> bool:
    """Tripla 1X2 completa e numerica: la STESSA condizione che ``engine`` usa
    per costruire ``pre_match``. Un riferimento parziale non serve a nulla e non
    deve essere reidratato (meglio None, cosi' ``freeze_pre_ko`` puo' ancora
    catturarlo se la partita non e' ancora iniziata)."""
    if not isinstance(pre, dict):
        return False
    for k in ("home", "draw", "away"):
        v = pre.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not (v > 1.0):
            return False
    return True


# ---------------------------------------------------------------------------
# D5 (25/09) - SCHEDA DELLA FIXTURE (sola lettura, vedi `selezione.SchedeFixture`)
# ---------------------------------------------------------------------------
# proiezioni JSON: si legge SOLO cio' che serve, mai l'intero raw_json
_SCHEDA_SELECT = (
    "fixture_id,"
    "h2h:raw_json->response->0->h2h,"
    "cmp:raw_json->response->0->comparison,"
    "last5_home:raw_json->response->0->teams->home->last_5,"
    "last5_away:raw_json->response->0->teams->away->last_5"
)


def fixtures_window(start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    """Fixture 'light' della finestra: la STESSA query del matcher di Omega e
    della catena lambda del bot (`omega_db.fixtures_for_window`)."""
    from Betfair.omega import omega_db

    return omega_db.fixtures_for_window(start_iso, end_iso) or []


def load_schede_fixture(fixture_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
    """{fixture_id: scheda} da `fixture_predictions.raw_json` (h2h, confronto
    attacco/difesa, ultime 5): le fonti della Dashboard. UNA SELECT."""
    ids = [int(x) for x in fixture_ids or []]
    if not ids:
        return {}
    res = (get_supabase_client().table("fixture_predictions")
           .select(_SCHEDA_SELECT).in_("fixture_id", ids).execute())
    return {int(r["fixture_id"]): r for r in (getattr(res, "data", None) or [])
            if r.get("fixture_id") is not None}


def load_round_fixture(fixture_ids: List[int]) -> Dict[int, Optional[str]]:
    """{fixture_id: round di API-Football} da `matches.raw_json->league->>round`.
    UNA SELECT, solo la proiezione del round."""
    ids = [int(x) for x in fixture_ids or []]
    if not ids:
        return {}
    res = (get_supabase_client().table("matches")
           .select("fixture_id,round:raw_json->league->>round")
           .in_("fixture_id", ids).execute())
    return {int(r["fixture_id"]): r.get("round") for r in (getattr(res, "data", None) or [])
            if r.get("fixture_id") is not None}


def upsert_scan_rows(rows: List[Dict[str, Any]]) -> bool:
    """Upsert delle righe evento (on_conflict event_id). True se scritte."""
    if not rows:
        return True
    sb = get_supabase_client()
    try:
        sb.table("safe_strategy_scan").upsert(rows, on_conflict="event_id").execute()
        return True
    except Exception as e:  # noqa: BLE001 - best-effort, mai uccidere lo scanner
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] upsert righe KO: %s", str(e)[:160])
        return False


def delete_scan_rows(event_ids: List[str]) -> None:
    if not event_ids:
        return
    sb = get_supabase_client()
    try:
        sb.table("safe_strategy_scan").delete().in_("event_id", event_ids).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] delete righe KO: %s", str(e)[:160])


def upsert_status(payload: Dict[str, Any]) -> None:
    sb = get_supabase_client()
    try:
        # updated_at ESPLICITO (bug visto dal vivo 09/09): il DEFAULT now() vale
        # solo all'INSERT — l'upsert aggiornava il payload ma lasciava la data
        # della prima riga (02/09) → la UI diceva "scanner non attivo, heartbeat
        # 575530s fa" con lo scanner vivo.
        sb.table("safe_strategy_status").upsert(
            {"id": "scanner", "payload": payload, "updated_at": _now_iso()}, on_conflict="id"
        ).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] upsert status KO: %s", str(e)[:160])


_MIKE_TERMINAL_STATES = ("SETTLED", "ERROR", "SKIPPED")


_MIKE_IDLE_STATES = ("WATCH", "IDLE_LIVE")
# stati delle gambe che rappresentano un IMPEGNO reale (ordine vivo o posizione)
_MIKE_LIVE_LEG_STATUS = ("pending", "pending_reconcile", "open")


def _mike_has_exposure(row: dict) -> bool:
    """True se la partita ha DAVVERO qualcosa da proteggere: uno stato operativo
    (non WATCH/IDLE_LIVE) oppure almeno una gamba con un ordine vivo o una
    posizione abbinata. H4 (review): esentare anche le partite in sola
    osservazione regalava le quote di ~10 mercati a testa a partite senza un
    euro sopra."""
    state = str(row.get("state") or "")
    if state in _MIKE_TERMINAL_STATES:
        return False
    for leg in row.get("positions") or []:
        if not isinstance(leg, dict):
            continue
        if str(leg.get("status") or "") in _MIKE_LIVE_LEG_STATUS and not leg.get("archived"):
            return True
        try:
            if float(leg.get("matched") or 0.0) > 0 and not leg.get("archived"):
                return True
        except (TypeError, ValueError):
            continue
    return state not in _MIKE_IDLE_STATES


def _mike_exposure(row: dict) -> float:
    """Quanto denaro Mike ha DAVVERO sopra questa partita.

    Somma le gambe con un ordine vivo o una posizione abbinata, prendendo la
    grandezza piu' grande fra ``liability`` e ``matched``/``size``: serve solo a
    ORDINARE, non a fare conti, quindi si sbaglia per eccesso invece che per
    difetto (una partita non deve mai finire in coda per un campo mancante)."""
    tot = 0.0
    for leg in row.get("positions") or []:
        if not isinstance(leg, dict) or leg.get("archived"):
            continue
        if str(leg.get("status") or "") not in _MIKE_LIVE_LEG_STATUS:
            try:
                if float(leg.get("matched") or 0.0) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
        peso = 0.0
        for campo in ("liability", "matched", "size"):
            try:
                peso = max(peso, abs(float(leg.get(campo) or 0.0)))
            except (TypeError, ValueError):
                continue
        tot += peso
    return tot


def list_mike_followed_event_ids() -> Optional[List[str]]:
    """event_id delle partite di Mike con ESPOSIZIONE (ordini vivi o posizione).

    Servono allo scanner per esentarle dal tetto dei 20 eventi del motore
    opportunità (audit 11/09 C1): una posizione aperta senza le sue linee O/U nel
    feed è senza copertura, senza cash out e senza uscita. Le partite in sola
    osservazione (WATCH/IDLE_LIVE senza gambe) NON sono esenti: non hanno nulla
    da proteggere e peserebbero sul pool stream per niente (H4).
    None se la lettura fallisce (tabella assente = Mike mai installato)."""
    try:
        sb = get_supabase_client()
        res = (
            sb.table("mike_events")
            .select("event_id,state,positions")
            .not_.in_("state", list(_MIKE_TERMINAL_STATES))
            .execute()
        )
        righe = [r for r in (getattr(res, "data", None) or [])
                 if r.get("event_id") and _mike_has_exposure(r)]
        # CERT. 13/09 — ORDINE PER SOLDI A RISCHIO, decrescente.
        # La lista viene TRONCATA a valle (tetto ``MIKE_MAX_FOLLOWED``) e prima
        # il taglio seguiva l'ordine dei candidati dello scanner, cioe' "minuti
        # piu' avanzati per primi": cadevano le partite APPENA INIZIATE, che
        # sono esattamente quelle dove la copertura Over 4.5 serve di piu'.
        # Il tetto non si puo' togliere (pesa sul pool dello stream), ma chi
        # resta fuori dev'essere chi ha MENO denaro sopra, mai il contrario.
        righe.sort(key=lambda r: _mike_exposure(r), reverse=True)
        return [str(r["event_id"]) for r in righe]
    except Exception as e:  # noqa: BLE001 - best effort, mai fatale
        if not _is_missing_table(e):
            logger.warning("[safe-scan] lettura mike_events KO: %s", str(e)[:160])
        return None


# ---------------------------------------------------------------------------
# 02/10 (punto 27, ordine dell'utente: "lo scanner deve sapere le posizioni di
# tutti i bot; SOLO QUANDO I MERCATI SONO CLOSED [...] possiamo liberare lo
# scanner") - ESPOSIZIONI DI TUTTI I BOT, paper E live, in sola lettura.
#
# Fonti = le righe che i bot GIA' scrivono (nessuna tabella nuova, nessuna
# migrazione, nessun processo nuovo; Mike resta su
# ``list_mike_followed_event_ids``, invariata):
#   * ``omega_trades``           - Omega, stati pending/open/hedged;
#   * ``safe_strategy_trades``   - Safe calcio e tennis, stati pending/open/hedged;
#   * ``betfair_live_orders``    - lo SPECCHIO del runner e della sessione scalper
#     (scalper, sniper, theta, ordini via runner di Mike/Omega/Safe, manuali
#     dall'app): ordini in uno stato VIVO;
#   * ``betfair_live_positions`` - posizioni aperte (``esposizione_aperta``) su
#     un mercato non ancora regolato nella stessa modalita';
#   * ``tennis_live_orders`` / ``tennis_live_positions`` - i bot tennis
#     (tennis_scalper, tennis_pro, tennis_flb, tennis_swing, safe_tennis).
# Ogni fonte e' letta da sola: una lettura fallita torna None SOLO per quella
# fonte e il chiamante tiene l'ultima lista buona (mai "nessuna esposizione"
# per un errore di rete).
# ---------------------------------------------------------------------------
#: stati delle righe dei diari dei bot che sono un impegno (ordine vivo,
#: posizione abbinata, posizione coperta ma non ancora regolata)
_STATI_TRADE_ESPOSTI = ("pending", "open", "hedged")
#: stati flumine di un ordine vivo, nelle DUE grafie che lo specchio puo'
#: contenere (nome dell'Enum e valore): ``Betfair/stream/db.py::STATI_ORDINE_VIVO``
_STATI_ORDINE_VIVO_GRAFIE = (
    "PENDING", "EXECUTABLE", "CANCELLING", "UPDATING", "REPLACING",
    "Pending", "Executable", "Cancelling", "Updating", "Replacing",
)
#: le posizioni dello specchio si leggono solo se toccate negli ultimi N giorni:
#: lo specchio non cancella le righe alla regolazione (FIX-A 26/09) e la
#: tabella cresce con la storia. E' un LIMITE DI LETTURA, non una regola di
#: "partita finita": lo scanner guarda eventi da -6 h a +14 h.
_ESPOSIZIONI_FINESTRA_GIORNI = 7
#: colonne lette dalle posizioni (``esposizione_aperta`` + chiavi)
_COLONNE_POSIZIONI_ESPOSTE = ("mode,event_id,market_id,matched_if_win,matched_if_lose,"
                              "unmatched_back_exposure,unmatched_lay_exposure")


def _da_giorni(giorni: int) -> str:
    from datetime import timedelta

    return (datetime.now(timezone.utc) - timedelta(days=giorni)).isoformat()


def _righe_esposte(righe: Any, bot: str, sport: Optional[str]) -> List[Dict[str, Any]]:
    """Righe grezze -> [{event_id, market_id, sport, bot}] (solo con event_id)."""
    out: List[Dict[str, Any]] = []
    for r in righe or []:
        if not isinstance(r, dict) or not r.get("event_id"):
            continue
        out.append({
            "event_id": str(r["event_id"]),
            "market_id": str(r["market_id"]) if r.get("market_id") else None,
            "sport": str(r.get("sport") or sport or "") or None,
            "bot": str(r.get("source") or r.get("bot") or bot),
        })
    return out


def _leggi_fonte(nome: str, leggi: Any) -> Optional[List[Dict[str, Any]]]:
    try:
        return leggi()
    except Exception as e:  # noqa: BLE001 - una fonte giu' non spegne le altre
        if _is_missing_table(e):
            return []          # tabella assente = quel bot non e' installato
        logger.warning("[safe-scan] esposizioni %s: lettura KO: %s", nome, str(e)[:160])
        return None


#: R6 (02/10): UNA chiamata invece di 6-7 SELECT. La RPC e' nella migrazione
#: ``migrations/scanner_list_bot_exposures_2026-10-02.sql`` (la applica
#: l'utente); finche' manca si ripiega sulle letture per fonte e la si
#: riprova ogni ``_RPC_ESPOSIZIONI_RIPROVA_S``.
_RPC_ESPOSIZIONI = "list_bot_exposures"
_RPC_ESPOSIZIONI_RIPROVA_S = 300.0
_RPC_ESPOSIZIONI_STATO: Dict[str, Any] = {"assente_ts": None, "avvisato": False}


def _rpc_assente(exc: Exception) -> bool:
    """La funzione non esiste (migrazione non applicata): PostgREST risponde
    404 con codice PGRST202 «Could not find the function»."""
    msg = str(exc).lower()
    return "pgrst202" in msg or "could not find the function" in msg or "404" in msg


def list_bot_exposures(now_ts: Optional[float] = None) -> Dict[str, Optional[List[Dict[str, Any]]]]:
    """{fonte: [{event_id, market_id, sport, bot}] | None} delle esposizioni
    VIVE (ordini non abbinati + posizioni aperte) di TUTTI i bot, paper e live.

    R6 (02/10): prima la RPC ``list_bot_exposures`` (UNA chiamata), che
    restituisce ``{"rows": [{event_id, market_id, bot, modalita, sport}]}``:
    esito ``{"rpc": righe}``. RPC che risponde con un errore: ``{"rpc": None}``
    (il chiamante tiene l'ultima lista buona). RPC ASSENTE (404, migrazione non
    applicata): WARNING una volta sola e ripiego sulle letture per fonte
    (``_list_bot_exposures_a_fonti``), riprovando la RPC ogni 300 s."""
    import time as _time

    t = _time.time() if now_ts is None else float(now_ts)
    st = _RPC_ESPOSIZIONI_STATO
    if st["assente_ts"] is None or t - float(st["assente_ts"]) >= _RPC_ESPOSIZIONI_RIPROVA_S:
        try:
            res = get_supabase_client().rpc(_RPC_ESPOSIZIONI, {}).execute()
            data = getattr(res, "data", None)
            righe = data.get("rows") if isinstance(data, dict) else None
            if not isinstance(righe, list):
                raise ValueError(f"risposta inattesa: {type(data).__name__}")
            st["assente_ts"] = None
            return {"rpc": _righe_esposte(righe, "?", None)}
        except Exception as e:  # noqa: BLE001 - mai fatale
            if not _rpc_assente(e):
                logger.warning("[safe-scan] esposizioni: RPC %s KO (tengo l'ultima lista "
                               "buona): %s", _RPC_ESPOSIZIONI, str(e)[:160])
                return {"rpc": None}
            st["assente_ts"] = t
            if not st["avvisato"]:
                st["avvisato"] = True
                logger.warning(
                    "[safe-scan] RPC %s non disponibile (migrazione "
                    "scanner_list_bot_exposures_2026-10-02.sql non applicata?): ripiego "
                    "sulle letture per fonte (6-7 SELECT ogni 10 s)", _RPC_ESPOSIZIONI)
    return _list_bot_exposures_a_fonti()


def _list_bot_exposures_a_fonti() -> Dict[str, Optional[List[Dict[str, Any]]]]:
    """Il RIPIEGO senza la RPC: una SELECT filtrata per fonte (piu' una sulle
    regolazioni per le posizioni del calcio). ``None`` = lettura di QUELLA
    fonte fallita (il chiamante tiene l'ultima buona)."""
    sb = get_supabase_client()

    def _omega() -> List[Dict[str, Any]]:
        res = (sb.table("omega_trades").select("event_id,market_id,status")
               .in_("status", list(_STATI_TRADE_ESPOSTI)).execute())
        return _righe_esposte(getattr(res, "data", None), "omega", "calcio")

    def _safe() -> List[Dict[str, Any]]:
        res = (sb.table("safe_strategy_trades").select("event_id,market_id,sport,status")
               .in_("status", list(_STATI_TRADE_ESPOSTI)).execute())
        return _righe_esposte(getattr(res, "data", None), "safe", "calcio")

    def _ordini(tabella: str, sport: str) -> List[Dict[str, Any]]:
        # ``source`` NON si legge: se la sua migrazione mancasse, la SELECT
        # fallirebbe e la fonte resterebbe cieca. Il nome del bot non serve.
        res = (sb.table(tabella).select("event_id,market_id,status")
               .in_("status", list(_STATI_ORDINE_VIVO_GRAFIE)).execute())
        return _righe_esposte(getattr(res, "data", None), "specchio", sport)

    def _posizioni(tabella: str, sport: str, regolate: bool) -> List[Dict[str, Any]]:
        from Betfair.stream import db as _specchio

        res = (sb.table(tabella).select(_COLONNE_POSIZIONI_ESPOSTE)
               .gte("updated_at", _da_giorni(_ESPOSIZIONI_FINESTRA_GIORNI)).execute())
        righe = getattr(res, "data", None) or []
        if regolate:
            # stessa regola della guardia del catalogo vuoto (cantiere A)
            aperte = _specchio._posizioni_aperte_non_regolate(sb, righe)  # noqa: SLF001
        else:
            # il tennis non ha una tabella di regolazione (``tennis_db``)
            aperte = [p for p in righe if _specchio.esposizione_aperta(p)]
        return _righe_esposte(aperte, "specchio", sport)

    return {
        "omega": _leggi_fonte("omega", _omega),
        "safe": _leggi_fonte("safe", _safe),
        "ordini_calcio": _leggi_fonte(
            "ordini_calcio", lambda: _ordini("betfair_live_orders", "calcio")),
        "posizioni_calcio": _leggi_fonte(
            "posizioni_calcio", lambda: _posizioni("betfair_live_positions", "calcio", True)),
        "ordini_tennis": _leggi_fonte(
            "ordini_tennis", lambda: _ordini("tennis_live_orders", "tennis")),
        "posizioni_tennis": _leggi_fonte(
            "posizioni_tennis", lambda: _posizioni("tennis_live_positions", "tennis", False)),
    }
