# Prediction/predictions_results_backfill.py

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# ----------------------------------------------------------
# Ensure project root is on sys.path so absolute imports work
# even when running this file from the Prediction/ folder.
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_client import get_supabase_client  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Allineato a daily_yesterday_backfill.py
FINISHED_SHORT_STATUSES = {"FT", "AET", "PEN"}


# =========================================================================
# Resilienza DB (SOLO il MODO di leggere/scrivere: la matematica e' invariata)
# =========================================================================
# Il ruolo PostgREST ha statement_timeout = 8 s: su questa tabella un UPDATE
# costa ~0,2 s per riga (manutenzione indici, fra cui due GIN su JSONB), quindi
# blocchi grandi superano sistematicamente il timeout (SQLSTATE 57014). La cura
# NON e' alzare il timeout (decisione dell'utente) ma: fette piccole e adattive,
# retry con backoff+jitter sui soli errori transitori, e nessun errore ingoiato.

# Tentativi per singola chiamata su errore TRANSITORIO (timeout escluso quando
# la strategia corretta e' rimpicciolire la fetta: vedi retry_timeout=False).
RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 0.8  # secondi (raddoppia a ogni tentativo, con jitter)

# SQLSTATE / codici HTTP considerati transitori (ritentabili).
_TRANSIENT_CODES = {
    "57014",    # statement_timeout
    "57P01",    # admin_shutdown
    "53300",    # too_many_connections
    "40001",    # serialization_failure
    "40P01",    # deadlock_detected
    "08000", "08003", "08006",  # connection_exception
    "PGRST002",  # PostgREST non riesce a leggere lo schema cache (DB sotto stress)
    "502", "503", "504",
}
_TRANSIENT_MARKERS = (
    "statement timeout",
    "pgrst002",
    "server disconnected",
    "connection reset",
    "connection aborted",
    "connection error",
    "read timeout",
    "readtimeout",
    "connecttimeout",
    "connecterror",
    "remotedisconnected",
    "temporarily unavailable",
    "bad gateway",
    "gateway timeout",
    "service unavailable",
    "timed out",
)


def _err_code(exc: BaseException) -> str:
    return str(getattr(exc, "code", "") or "").upper()


def _is_statement_timeout(exc: BaseException) -> bool:
    """True se l'errore e' uno statement_timeout Postgres (SQLSTATE 57014)."""
    if _err_code(exc) == "57014":
        return True
    msg = str(exc).lower()
    return "57014" in msg or "statement timeout" in msg


def _is_transient_error(exc: BaseException) -> bool:
    """True SOLO per errori ritentabili (timeout, rete, DB momentaneamente KO).

    Gli errori LOGICI (vincoli violati, funzione inesistente, 4xx di validazione)
    NON sono transitori: ritentarli e' inutile e maschererebbe un difetto.
    """
    if _is_statement_timeout(exc):
        return True
    if _err_code(exc) in _TRANSIENT_CODES:
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def _sleep_backoff(attempt: int) -> None:
    """Attesa crescente con jitter (50-100% del tetto) fra un tentativo e l'altro.
    Isolata in una funzione per poterla neutralizzare nei test."""
    wait = min(20.0, RETRY_BASE_DELAY * (2 ** max(0, attempt - 1)))
    time.sleep(wait * (0.5 + random.random() * 0.5))


def _exec_with_retry(
    call: Callable[[], Any],
    *,
    what: str,
    attempts: int = RETRY_ATTEMPTS,
    retry_timeout: bool = True,
) -> Any:
    """Esegue `call()` ritentando SOLO gli errori transitori. L'ultima eccezione
    risale SEMPRE al chiamante: niente errori ingoiati.

    retry_timeout=False: lo statement_timeout non viene ritentato "uguale" ma
    rilanciato subito, perche' il chiamante sa fare di meglio (dimezzare la fetta)
    invece di sprecare altri 8 s di DB con la stessa dimensione.
    """
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - riclassificato subito qui sotto
            if not _is_transient_error(exc):
                raise
            if _is_statement_timeout(exc) and not retry_timeout:
                raise
            if attempt >= attempts:
                raise
            logger.warning(
                "[retry %s/%s] %s: errore transitorio (%s) - ritento.",
                attempt, attempts, what, str(exc)[:200],
            )
            _sleep_backoff(attempt)
    raise RuntimeError(f"unreachable: {what}")  # difensivo


# =========================
# Helpers
# =========================

def _outcome(hg: int, ag: int) -> str:
    if hg > ag:
        return "H"
    if hg < ag:
        return "A"
    return "D"


def _parse_under_over(line: Optional[str]) -> Optional[Tuple[str, float]]:
    """
    Converte la notazione dell'endpoint predictions:
      "-3.5" => ("under", 3.5)
      "+2.5" => ("over", 2.5)
    Se non riconosciuta -> None.
    """
    if not line:
        return None
    s = str(line).strip()
    if not s:
        return None

    if s[0] not in {"+", "-"}:
        return None

    try:
        val = float(s[1:])
    except ValueError:
        return None

    return ("over", val) if s[0] == "+" else ("under", val)


def _is_finished(match_row: Dict[str, Any]) -> bool:
    short = match_row.get("status_short")
    return isinstance(short, str) and short.upper() in FINISHED_SHORT_STATUSES


def _real_winner_team_id(match_row: Dict[str, Any]) -> Optional[int]:
    """
    Determina il winner reale dal punteggio (se non è pari).
    """
    home_id = match_row.get("home_team_id")
    away_id = match_row.get("away_team_id")
    hg = match_row.get("goals_home")
    ag = match_row.get("goals_away")

    if home_id is None or away_id is None or hg is None or ag is None:
        return None

    hg, ag = int(hg), int(ag)

    if hg > ag:
        return int(home_id)
    if ag > hg:
        return int(away_id)
    return None  # draw


# =========================
# Fetch
# =========================

# Lettura predictions: pagine KEYSET su fixture_id (chiave primaria) invece di
# una sola select da `limit` righe senza ordinamento. Pagine piccole e adattive
# -> nessuno statement_timeout; ordinamento + keyset -> insieme di righe
# deterministico, senza buchi ne' duplicati (stesso insieme di prima).
FETCH_PAGE = 500
FETCH_MIN_PAGE = 50
# Tentativi concessi quando la pagina e' gia' al minimo e arriva comunque un
# 57014: senza questi, un solo timeout momentaneo abbatterebbe tutto il run.
FETCH_MIN_RETRY = 3

# Lettura matches: blocchi di fixture_id (erano 200, fissi). Sempre ben sotto il
# tetto righe di PostgREST -> la risposta non puo' essere troncata in silenzio.
MATCHES_CHUNK = 100
MATCHES_MIN_CHUNK = 10


def fetch_predictions_ok_for_date(
    sb,
    target_date: str,
    force: bool,
    limit: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Prende tutte le predictions status='ok' per la data UTC richiesta.
    Se force=False prende solo quelle non ancora valutate (evaluated_at is null).

    Stessi filtri di prima; cambia solo il MODO di leggere: pagine keyset
    ordinate per fixture_id, con dimensione che si dimezza sullo
    statement_timeout. `limit` resta il tetto massimo di righe restituite.

    Ritorna (righe, troncata): `troncata` e' True SOLO se il tetto `limit` e'
    stato raggiunto E una sonda di una riga dimostra che ce n'erano altre da
    leggere (righe perse: il chiamante deve uscire con codice != 0).
    """
    def _page(after_id: Optional[int], size: int):
        q = (
            sb.table("fixture_predictions")
            .select(
                "fixture_id, fixture_date, status, winner_team_id, win_or_draw, under_over_line, evaluated_at"
            )
            .eq("status", "ok")
            .gte("fixture_date", f"{target_date}T00:00:00+00:00")
            .lte("fixture_date", f"{target_date}T23:59:59+00:00")
        )
        if not force:
            q = q.is_("evaluated_at", "null")
        if after_id is not None:
            q = q.gt("fixture_id", after_id)
        return q.order("fixture_id", desc=False).limit(size)

    out: List[Dict[str, Any]] = []
    seen: set = set()
    page_size = max(1, min(FETCH_PAGE, limit))
    after_id: Optional[int] = None
    tentativi_al_minimo = 0

    while len(out) < limit:
        want = min(page_size, limit - len(out))
        try:
            resp = _exec_with_retry(
                lambda _a=after_id, _w=want: _page(_a, _w).execute(),
                what=f"fetch predictions {target_date} (pagina da {want}, dopo fixture_id={after_id})",
                retry_timeout=False,
            )
        except Exception as exc:  # noqa: BLE001 - rilanciato se non gestibile
            if _is_statement_timeout(exc):
                if want > FETCH_MIN_PAGE:
                    # ci si dimezza rispetto alla pagina DAVVERO chiesta (`want`):
                    # basarsi su page_size rischierebbe di richiedere la stessa
                    # identica pagina e bruciare altri 8 s di DB.
                    page_size = max(FETCH_MIN_PAGE, want // 2)
                    logger.warning(
                        "[fetch predictions] statement_timeout su pagina da %s -> riprovo con %s.",
                        want, page_size,
                    )
                    continue
                tentativi_al_minimo += 1
                if tentativi_al_minimo <= FETCH_MIN_RETRY:
                    logger.warning(
                        "[fetch predictions] statement_timeout su pagina minima da %s "
                        "(tentativo %s/%s): attendo e riprovo.",
                        want, tentativi_al_minimo, FETCH_MIN_RETRY,
                    )
                    _sleep_backoff(tentativi_al_minimo)
                    continue
            raise
        err = getattr(resp, "error", None)
        if err:
            raise RuntimeError(f"Errore fetch predictions: {err}")

        rows = getattr(resp, "data", None) or []
        tentativi_al_minimo = 0
        nuovi = 0
        for r in rows:
            fx = r.get("fixture_id")
            if fx is None:
                continue
            fx = int(fx)
            if fx in seen:  # difensivo: il keyset non puo' ripetere una riga
                continue
            seen.add(fx)
            out.append(r)
            nuovi += 1
            after_id = fx if after_id is None or fx > after_id else after_id

        if rows and nuovi == 0:
            # La paginazione non avanza (keyset o ordinamento rotti): meglio un
            # errore rumoroso che un ciclo infinito o una lettura parziale.
            raise RuntimeError(
                f"Paginazione predictions bloccata dopo fixture_id={after_id}: "
                f"{len(rows)} righe gia' viste, nessuna nuova."
            )

        # UNICA condizione di uscita: pagina VUOTA (come
        # master_backtest.fetch_completed_fixtures). Fermarsi su
        # "meno righe di quante chieste" darebbe per finita la lettura anche
        # quando e' il server a troncare la pagina (max-rows) -> righe perse.
        if not rows:
            break

    troncata = False
    if limit > 0 and len(out) >= limit:
        # Sonda di UNA riga oltre l'ultimo fixture_id letto: distingue "il tetto
        # coincide esattamente con le righe disponibili" (nessun problema) da
        # "ci sono altre predictions non lette" (dati mancanti, run rosso).
        resp = _exec_with_retry(
            lambda _a=after_id: _page(_a, 1).execute(),
            what=f"sonda oltre il tetto --limit per {target_date}",
        )
        rimaste = getattr(resp, "data", None) or []
        if rimaste:
            troncata = True
            logger.error(
                "[fetch predictions] tetto --limit=%s raggiunto per %s e ci sono ANCORA "
                "predictions da leggere (prima non letta: fixture_id=%s): rilanciare con "
                "--limit piu' alto.",
                limit, target_date, rimaste[0].get("fixture_id"),
            )
        else:
            logger.info(
                "[fetch predictions] tetto --limit=%s raggiunto per %s ma non c'e' altro "
                "da leggere: nessuna riga persa.",
                limit, target_date,
            )

    return out, troncata


def fetch_matches_map(sb, fixture_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Ritorna mappa fixture_id -> match_row per tutti i fixture_ids richiesti.

    ⚠️ IMPORTANTE:
    - Evita .in_() con liste enormi in una sola richiesta (può restituire risultati parziali).
    - Usa chunk piccoli (MATCHES_CHUNK) e unisce i risultati.
    - Blocco dimezzato sullo statement_timeout, retry sui soli errori transitori:
      una lettura persa qui diventerebbe un falso "missing_match" (e un risultato
      che resta NULL per sempre), quindi non puo' fallire in silenzio.
    """
    if not fixture_ids:
        return {}

    out: Dict[int, Dict[str, Any]] = {}
    uniq_ids = sorted({int(x) for x in fixture_ids})

    size = max(1, MATCHES_CHUNK)
    i = 0
    blocco = 0
    while i < len(uniq_ids):
        blocco += 1
        tentativi_al_minimo = 0
        while True:
            chunk_ids = uniq_ids[i:i + size]
            try:
                resp = _exec_with_retry(
                    lambda _ids=chunk_ids: (
                        sb.table("matches")
                        .select(
                            "fixture_id, status_short, goals_home, goals_away, "
                            "home_team_id, away_team_id"
                        )
                        .in_("fixture_id", _ids)
                        .order("fixture_id", desc=False)
                        .execute()
                    ),
                    what=f"fetch matches blocco {blocco} ({len(chunk_ids)} fixture)",
                    retry_timeout=False,
                )
            except Exception as exc:  # noqa: BLE001 - rilanciato se non gestibile
                if _is_statement_timeout(exc):
                    if len(chunk_ids) > MATCHES_MIN_CHUNK:
                        size = max(MATCHES_MIN_CHUNK, len(chunk_ids) // 2)
                        logger.warning(
                            "[fetch matches] statement_timeout su blocco da %s -> riprovo con %s.",
                            len(chunk_ids), size,
                        )
                        continue
                    tentativi_al_minimo += 1
                    if tentativi_al_minimo <= FETCH_MIN_RETRY:
                        logger.warning(
                            "[fetch matches] statement_timeout su blocco minimo da %s "
                            "(tentativo %s/%s): attendo e riprovo.",
                            len(chunk_ids), tentativi_al_minimo, FETCH_MIN_RETRY,
                        )
                        _sleep_backoff(tentativi_al_minimo)
                        continue
                raise RuntimeError(f"Errore fetch matches (chunk {blocco}): {exc}") from exc

            err = getattr(resp, "error", None)
            if err:
                raise RuntimeError(f"Errore fetch matches (chunk {blocco}): {err}")

            rows = getattr(resp, "data", None) or []
            for r in rows:
                fx = r.get("fixture_id")
                if fx is not None:
                    out[int(fx)] = r
            i += len(chunk_ids)
            break

    return out


# =========================
# Evaluate
# =========================

def evaluate(pred: Dict[str, Any], match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Ritorna il payload dei campi risultato da scrivere su fixture_predictions,
    oppure None se il match non è valutabile (non FT/AET/PEN o goal null).
    """
    if not match or not _is_finished(match):
        return None

    hg = match.get("goals_home")
    ag = match.get("goals_away")
    if hg is None or ag is None:
        return None

    hg, ag = int(hg), int(ag)
    total = hg + ag
    out = _outcome(hg, ag)

    pred_winner_id = pred.get("winner_team_id")
    real_winner_id = _real_winner_team_id(match)

    # hit_winner
    hit_winner: Optional[bool] = None
    if pred_winner_id is not None:
        if real_winner_id is None:
            hit_winner = False  # match finito pari -> winner sbagliato
        else:
            hit_winner = int(pred_winner_id) == int(real_winner_id)

    # hit_win_or_draw
    hit_wod: Optional[bool] = None
    if bool(pred.get("win_or_draw")) is True and pred_winner_id is not None:
        if out == "D":
            hit_wod = True
        else:
            hit_wod = (real_winner_id is not None) and (int(pred_winner_id) == int(real_winner_id))

    # hit_under_over
    hit_uo: Optional[bool] = None
    uo = _parse_under_over(pred.get("under_over_line"))
    if uo:
        kind, line = uo
        if kind == "under":
            hit_uo = total < line
        else:
            hit_uo = total > line

    return {
        "fixture_id": int(pred["fixture_id"]),
        "result_status_short": str(match.get("status_short")).upper() if match.get("status_short") else None,
        "result_home_goals": hg,
        "result_away_goals": ag,
        "result_total_goals": total,
        "result_outcome": out,
        "hit_winner": hit_winner,
        "hit_win_or_draw": hit_wod,
        "hit_under_over": hit_uo,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


# =========================
# DB update (SAFE: update only)
# =========================

def update_prediction_row(sb, fixture_id: int, payload: Dict[str, Any]) -> None:
    """
    Update garantito: NON fa insert, quindi non può violare NOT NULL (es. status).
    """
    body = {k: v for k, v in payload.items() if k != "fixture_id"}

    resp = sb.table("fixture_predictions").update(body).eq("fixture_id", fixture_id).execute()
    err = getattr(resp, "error", None)
    if err:
        raise RuntimeError(f"Update failed fixture_id={fixture_id}: {err}")


# =========================
# DB update BULK via RPC (stesso comportamento, meno round-trip)
# =========================

# RPC definita in migrations/predictions_results_bulk_update_rpc.sql:
# UPDATE ... FROM jsonb_to_recordset -> aggiorna SOLO righe esistenti (mai
# insert, come update_prediction_row), stesse colonne/valori/WHERE fixture_id.
RPC_BULK_UPDATE = "bulk_update_prediction_results"
# Misura dai log di produzione: l'UPDATE costa ~0,2 s per riga (manutenzione
# indici, fra cui due GIN su JSONB), quindi con statement_timeout=8 s un blocco
# da 500 payload non passa MAI (ne' uno da 96: 19/09 e 20/09 in timeout subito).
# Si parte piccoli e si scende ancora se serve (dimezzamento adattivo).
RPC_BULK_CHUNK = 25  # payload per chiamata RPC (partenza, poi adattivo)
RPC_MIN_CHUNK = 5    # sotto questa soglia conviene il riga-per-riga (errore per fixture)


class _RpcMissingError(RuntimeError):
    """La RPC non esiste (ancora) sul DB: migration non applicata."""


def _is_rpc_missing_error(err: Any) -> bool:
    """
    Riconosce l'errore 'function not found':
    - PGRST202: PostgREST non trova la funzione nello schema cache
    - 42883:    undefined_function lato Postgres
    """
    code = str(getattr(err, "code", "") or "").upper()
    if code in {"PGRST202", "42883"}:
        return True
    msg = str(err).lower()
    return (
        "pgrst202" in msg
        or "could not find the function" in msg
        or ("function" in msg and "does not exist" in msg)
    )


def update_rows_one_by_one(sb, updates: List[Dict[str, Any]]) -> List[Tuple[int, str]]:
    """
    Percorso storico: 1 UPDATE HTTP per fixture (update_prediction_row), ora con
    retry sui soli errori transitori (timeout/rete): l'UPDATE e' idempotente
    (stessi valori, WHERE fixture_id), quindi ritentarlo e' sempre sicuro.

    Ritorna l'elenco (fixture_id, errore) delle fixture NON aggiornate: niente
    errori ingoiati, il chiamante li riporta nel riepilogo e nell'exit code.
    """
    failures: List[Tuple[int, str]] = []
    for u in updates:
        fx_id = int(u["fixture_id"])
        try:
            _exec_with_retry(
                lambda _fx=fx_id, _u=u: update_prediction_row(sb, _fx, _u),
                what=f"update fixture_id={fx_id}",
            )
        except Exception as e:  # noqa: BLE001 - registrato e riportato, mai ingoiato
            failures.append((fx_id, str(e)))
            logger.error("❌ Update fallito fixture_id=%s: %s", fx_id, e)
    return failures


def _fixture_id_esistenti(sb, fixture_ids: List[int]) -> set:
    """Quali di questi fixture_id esistono ancora in fixture_predictions.

    Serve SOLO quando la RPC dichiara meno righe aggiornate dei payload inviati:
    la RPC e' update-only, quindi il disavanzo sono righe che non esistono piu'
    (o non sono mai esistite) e che nessun UPDATE potra' mai scrivere. Con questa
    lettura si dice ESATTAMENTE quali, invece di tirare a indovinare.
    """
    trovati: set = set()
    ids = sorted({int(x) for x in fixture_ids})
    for k in range(0, len(ids), MATCHES_CHUNK):
        blocco = ids[k:k + MATCHES_CHUNK]
        resp = _exec_with_retry(
            lambda _ids=blocco: (
                sb.table("fixture_predictions")
                .select("fixture_id")
                .in_("fixture_id", _ids)
                .order("fixture_id", desc=False)
                .execute()
            ),
            what=f"verifica esistenza {len(blocco)} fixture_predictions",
        )
        for r in (getattr(resp, "data", None) or []):
            fx = r.get("fixture_id")
            if fx is not None:
                trovati.add(int(fx))
    return trovati


def _recupera_chunk_non_confermato(
    sb,
    chunk: List[Dict[str, Any]],
    chunk_no: int,
    motivo: str,
) -> List[Tuple[int, str]]:
    """La RPC non ha confermato la scrittura di tutti i payload del blocco.

    L'UPDATE e' idempotente: si riscrive il blocco riga-per-riga (che da' l'errore
    per singola fixture). Se nemmeno cosi' emergono errori, si verifica quali
    fixture esistono davvero: quelle assenti NON sono state scritte e finiscono
    nei falliti (run rosso), le altre a quel punto sono scritte per davvero.
    """
    logger.warning(
        "[RPC bulk] chunk %s: %s -> riscrivo il blocco riga-per-riga.",
        chunk_no, motivo,
    )
    failures = update_rows_one_by_one(sb, chunk)
    gia_falliti = {fx for fx, _ in failures}

    ids = [int(u["fixture_id"]) for u in chunk if int(u["fixture_id"]) not in gia_falliti]
    if not ids:
        return failures

    esistenti = _fixture_id_esistenti(sb, ids)
    assenti = [fx for fx in ids if fx not in esistenti]
    for fx in assenti:
        err = f"riga assente da fixture_predictions ({motivo}): risultato NON scritto"
        failures.append((fx, err))
        logger.error("[RPC bulk] fixture_id=%s: %s", fx, err)
    return failures


def bulk_update_predictions(sb, updates: List[Dict[str, Any]]) -> List[Tuple[int, str]]:
    """
    Percorso bulk: 1 chiamata RPC ogni RPC_BULK_CHUNK payload invece di 1
    UPDATE HTTP per fixture. Stessi valori scritti, stesso vincolo SAFE
    (update-only, mai insert). Ritorna l'elenco (fixture_id, errore) dei falliti.

    - statement_timeout (57014) su un blocco -> la dimensione viene DIMEZZATA e
      il blocco ritentato (dimensione ridotta poi mantenuta per il resto del run,
      cosi' non si ripaga il timeout a ogni blocco). Solo sotto RPC_MIN_CHUNK si
      passa al riga-per-riga, che ha la granularita' di errore per fixture.
    - Altri errori transitori (rete, DB momentaneamente KO) -> retry con backoff
      e jitter dentro _exec_with_retry.
    - RPC assente sul PRIMO chunk -> solleva _RpcMissingError: il chiamante fa
      fallback integrale al loop riga-per-riga (il file funziona identico anche
      prima che la migration venga applicata).
    - Chunk fallito per ALTRI motivi -> ritentato riga-per-riga, cosi' la
      granularita' di errore e i conteggi restano quelli di oggi.
    - RISPOSTA che non conferma le scritture (meno righe aggiornate dei payload,
      oppure esito ignoto perche' `data` non e' un intero) -> il blocco NON e'
      riuscito: si riscrive riga-per-riga e le righe che non esistono finiscono
      nei falliti (vedi _recupera_chunk_non_confermato).
    """
    failures: List[Tuple[int, str]] = []
    size = max(1, RPC_BULK_CHUNK)
    i = 0
    chunk_no = 0

    while i < len(updates):
        chunk_no += 1
        while True:
            chunk = updates[i:i + size]

            # Dedup difensivo per fixture_id (vince l'ULTIMO payload, come nel loop
            # sequenziale dove l'ultimo UPDATE sovrascrive). Con fixture_id univoco
            # nel fetch e' un no-op.
            body = list({int(u["fixture_id"]): u for u in chunk}.values())

            try:
                resp = _exec_with_retry(
                    lambda _b=body: sb.rpc(RPC_BULK_UPDATE, {"p_rows": _b}).execute(),
                    what=f"RPC bulk chunk {chunk_no} ({len(body)} payload)",
                    retry_timeout=False,
                )
                err = getattr(resp, "error", None)
                if err:
                    raise RuntimeError(str(err))
            except Exception as e:
                if _is_rpc_missing_error(e):
                    if i == 0:
                        raise _RpcMissingError(str(e)) from e
                    # Non dovrebbe accadere a meta' run (il primo chunk e' passato):
                    # comunque, resto degli update riga-per-riga.
                    logger.warning(
                        "⚠️ RPC %s non piu' disponibile a meta' run: fallback riga-per-riga sul resto.",
                        RPC_BULK_UPDATE,
                    )
                    failures.extend(update_rows_one_by_one(sb, updates[i:]))
                    return failures
                if _is_statement_timeout(e) and len(body) > RPC_MIN_CHUNK:
                    # si dimezza rispetto ai payload DAVVERO inviati (se il blocco
                    # era gia' piu' corto di `size`, ritentarlo uguale sarebbe
                    # solo un altro timeout da 8 s).
                    new_size = max(RPC_MIN_CHUNK, min(size, len(body)) // 2)
                    logger.warning(
                        "[RPC bulk] chunk %s: statement_timeout su %s payload -> "
                        "riprovo lo STESSO blocco con %s payload.",
                        chunk_no, len(body), new_size,
                    )
                    size = new_size
                    continue  # stessa posizione, fetta piu' piccola
                logger.warning(
                    "⚠️ RPC bulk fallita sul chunk %s (%s payload): %s — ritento riga-per-riga il chunk.",
                    chunk_no, len(chunk), e,
                )
                failures.extend(update_rows_one_by_one(sb, chunk))
                i += len(chunk)
                break

            n_rows = resp.data if isinstance(resp.data, int) else None
            logger.info(
                "📦 RPC bulk chunk %s: %s payload → %s righe aggiornate.",
                chunk_no, len(body), n_rows if n_rows is not None else "?",
            )
            # L'unica prova che i payload sono stati scritti e' il numero di righe
            # aggiornate dichiarato dalla RPC. Se manca (esito IGNOTO) o e' minore
            # dei payload inviati, il blocco NON si puo' dare per riuscito.
            if n_rows is None:
                failures.extend(_recupera_chunk_non_confermato(
                    sb, body, chunk_no,
                    f"la RPC non ha restituito il numero di righe (data={resp.data!r})",
                ))
            elif n_rows < len(body):
                failures.extend(_recupera_chunk_non_confermato(
                    sb, body, chunk_no,
                    f"la RPC ha aggiornato {n_rows} righe su {len(body)} payload",
                ))
            i += len(chunk)
            break

    return failures


# =========================
# Runner
# =========================

def _fmt_ids(ids: List[int]) -> str:
    """Elenco COMPLETO di fixture_id (servono tutti per il recupero manuale)."""
    return ", ".join(str(x) for x in ids)


def run(target_date: str, force: bool, limit: int) -> int:
    """Esegue il backfill.

    Ritorna il numero di ANOMALIE che devono rendere rosso il run: fixture non
    aggiornate + eventuale troncamento della lettura (righe mai lette).
    """
    sb = get_supabase_client()

    preds, troncata = fetch_predictions_ok_for_date(sb, target_date, force=force, limit=limit)
    logger.info("📌 Predictions OK trovate per %s: %s", target_date, len(preds))
    if not preds:
        logger.info("✅ Nulla da valutare.")
        return 1 if troncata else 0

    fixture_ids = [int(p["fixture_id"]) for p in preds]
    matches_map = fetch_matches_map(sb, fixture_ids)

    updates: List[Dict[str, Any]] = []
    missing_ids: List[int] = []
    not_finished_ids: List[int] = []

    for p in preds:
        fx_id = int(p["fixture_id"])
        m = matches_map.get(fx_id)
        if not m:
            missing_ids.append(fx_id)
            continue

        payload = evaluate(p, m)
        if payload is None:
            not_finished_ids.append(fx_id)
            continue

        updates.append(payload)

    missing_match = len(missing_ids)
    not_finished = len(not_finished_ids)

    logger.info(
        "🧾 Pre-update: updates=%s missing_match=%s not_finished=%s",
        len(updates), missing_match, not_finished
    )
    # Le predictions senza riga in `matches` restano NULL e nessun run successivo
    # le riprende (questo script guarda solo il giorno richiesto): vanno almeno
    # elencate, non contate e basta.
    if missing_ids:
        logger.warning(
            "[missing_match] %s predictions senza riga in matches (risultato NON "
            "valutabile, resta NULL): %s",
            missing_match, _fmt_ids(missing_ids),
        )
    if not_finished_ids:
        logger.warning(
            "[not_finished] %s predictions con match non FT/AET/PEN o goals null: %s",
            not_finished, _fmt_ids(not_finished_ids),
        )

    if not updates:
        logger.info("✅ Nessun match valutabile (probabile: non FINISHED o goals null).")
        return 1 if troncata else 0

    # Percorso bulk (1 RPC per chunk) con fallback automatico al loop
    # riga-per-riga se la RPC non e' ancora stata applicata sul DB.
    try:
        failures = bulk_update_predictions(sb, updates)
    except _RpcMissingError:
        logger.warning(
            "⚠️ RPC %s non trovata sul DB (migration "
            "migrations/predictions_results_bulk_update_rpc.sql non applicata?): "
            "fallback al loop riga-per-riga.",
            RPC_BULK_UPDATE,
        )
        failures = update_rows_one_by_one(sb, updates)

    failed = len(failures)
    logger.info(
        "🏁 COMPLETATO → updated=%s failed=%s missing_match=%s not_finished=%s "
        "troncata=%s (date=%s)",
        len(updates) - failed, failed, missing_match, not_finished,
        "SI" if troncata else "no", target_date,
    )

    # Nessun dato perso in silenzio: le fixture rimaste indietro sono elencate
    # TUTTE (serve l'elenco completo per il recupero) e il processo esce con
    # codice != 0 (dopo aver comunque provato tutte le altre).
    if failures:
        logger.error(
            "%s fixture NON aggiornate dopo tutti i tentativi (risultato ancora "
            "NULL su fixture_predictions):", failed,
        )
        for fx_id, err in failures:
            logger.error("   - fixture_id=%s errore=%s", fx_id, err)
        logger.error(
            "[non_aggiornate] elenco completo: %s",
            _fmt_ids([fx for fx, _ in failures]),
        )

    return failed + (1 if troncata else 0)


def main() -> None:
    # Console Windows in cp1252: le emoji dei log farebbero UnicodeEncodeError e
    # abortirebbero il run (stesso accorgimento di generate_dc_rho.py).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - stream senza reconfigure
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD (UTC). Se omesso: ieri.")
    parser.add_argument("--force", action="store_true", help="Rivaluta anche se evaluated_at è già valorizzato")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    if args.limit <= 0:
        # Un tetto <= 0 leggeva zero righe e usciva "Nulla da valutare": un run
        # verde che non ha valutato niente. Meglio un errore esplicito.
        parser.error("--limit deve essere > 0")

    if args.date:
        target_date = args.date
    else:
        target_date = (date.today() - timedelta(days=1)).isoformat()

    problemi = run(target_date=target_date, force=args.force, limit=args.limit)
    if problemi:
        # Exit code != 0: il run non deve piu' risultare VERDE con risultati mancanti.
        sys.exit(1)


if __name__ == "__main__":
    main()
