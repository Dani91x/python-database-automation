# Prediction/predictions_results_backfill.py

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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

def fetch_predictions_ok_for_date(
    sb,
    target_date: str,
    force: bool,
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Prende tutte le predictions status='ok' per la data UTC richiesta.
    Se force=False prende solo quelle non ancora valutate (evaluated_at is null).
    """
    q = (
        sb.table("fixture_predictions")
        .select(
            "fixture_id, fixture_date, status, winner_team_id, win_or_draw, under_over_line, evaluated_at"
        )
        .eq("status", "ok")
        .gte("fixture_date", f"{target_date}T00:00:00+00:00")
        .lte("fixture_date", f"{target_date}T23:59:59+00:00")
        .limit(limit)
    )

    if not force:
        q = q.is_("evaluated_at", "null")

    resp = q.execute()
    err = getattr(resp, "error", None)
    if err:
        raise RuntimeError(f"Errore fetch predictions: {err}")

    return getattr(resp, "data", None) or []


def fetch_matches_map(sb, fixture_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Ritorna mappa fixture_id -> match_row per tutti i fixture_ids richiesti.

    ⚠️ IMPORTANTE:
    - Evita .in_() con liste enormi in una sola richiesta (può restituire risultati parziali).
    - Usa chunk da 200 e unisce i risultati.
    """
    if not fixture_ids:
        return {}

    CHUNK = 200
    out: Dict[int, Dict[str, Any]] = {}

    uniq_ids = sorted({int(x) for x in fixture_ids})

    for i in range(0, len(uniq_ids), CHUNK):
        chunk_ids = uniq_ids[i:i + CHUNK]

        resp = (
            sb.table("matches")
            .select("fixture_id, status_short, goals_home, goals_away, home_team_id, away_team_id")
            .in_("fixture_id", chunk_ids)
            .execute()
        )
        err = getattr(resp, "error", None)
        if err:
            raise RuntimeError(f"Errore fetch matches (chunk {i // CHUNK + 1}): {err}")

        rows = getattr(resp, "data", None) or []
        for r in rows:
            fx = r.get("fixture_id")
            if fx is not None:
                out[int(fx)] = r

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
RPC_BULK_CHUNK = 500  # payload per chiamata RPC


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


def update_rows_one_by_one(sb, updates: List[Dict[str, Any]]) -> int:
    """
    Percorso storico: 1 UPDATE HTTP per fixture (update_prediction_row).
    Ritorna il numero di failed. Log identici a prima.
    """
    failed = 0
    for u in updates:
        fx_id = int(u["fixture_id"])
        try:
            update_prediction_row(sb, fx_id, u)
        except Exception as e:
            failed += 1
            logger.error("❌ Update fallito fixture_id=%s: %s", fx_id, e)
    return failed


def bulk_update_predictions(sb, updates: List[Dict[str, Any]]) -> int:
    """
    Percorso bulk: 1 chiamata RPC ogni RPC_BULK_CHUNK payload invece di 1
    UPDATE HTTP per fixture. Stessi valori scritti, stesso vincolo SAFE
    (update-only, mai insert). Ritorna il numero di failed.

    - RPC assente sul PRIMO chunk -> solleva _RpcMissingError: il chiamante fa
      fallback integrale al loop riga-per-riga (il file funziona identico anche
      prima che la migration venga applicata).
    - Chunk fallito per ALTRI motivi -> ritentato riga-per-riga, cosi' la
      granularita' di errore e i conteggi restano quelli di oggi.
    """
    failed = 0
    for i in range(0, len(updates), RPC_BULK_CHUNK):
        chunk = updates[i:i + RPC_BULK_CHUNK]
        chunk_no = i // RPC_BULK_CHUNK + 1

        # Dedup difensivo per fixture_id (vince l'ULTIMO payload, come nel loop
        # sequenziale dove l'ultimo UPDATE sovrascrive). Con fixture_id univoco
        # nel fetch e' un no-op.
        body = list({int(u["fixture_id"]): u for u in chunk}.values())

        try:
            resp = sb.rpc(RPC_BULK_UPDATE, {"p_rows": body}).execute()
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
                return failed + update_rows_one_by_one(sb, updates[i:])
            logger.warning(
                "⚠️ RPC bulk fallita sul chunk %s (%s payload): %s — ritento riga-per-riga il chunk.",
                chunk_no, len(chunk), e,
            )
            failed += update_rows_one_by_one(sb, chunk)
            continue

        n_rows = resp.data if isinstance(resp.data, int) else None
        logger.info(
            "📦 RPC bulk chunk %s: %s payload → %s righe aggiornate.",
            chunk_no, len(body), n_rows if n_rows is not None else "?",
        )
        if n_rows is not None and n_rows < len(body):
            # update-only: payload senza riga esistente non scrivono nulla.
            # (Il vecchio loop in questo caso non falliva e non se ne accorgeva:
            # qui almeno lo segnaliamo, senza cambiare i conteggi finali.)
            logger.warning(
                "⚠️ RPC bulk chunk %s: %s payload ma %s righe aggiornate "
                "(fixture_id assenti da fixture_predictions?).",
                chunk_no, len(body), n_rows,
            )
    return failed


# =========================
# Runner
# =========================

def run(target_date: str, force: bool, limit: int) -> None:
    sb = get_supabase_client()

    preds = fetch_predictions_ok_for_date(sb, target_date, force=force, limit=limit)
    logger.info("📌 Predictions OK trovate per %s: %s", target_date, len(preds))
    if not preds:
        logger.info("✅ Nulla da valutare.")
        return

    fixture_ids = [int(p["fixture_id"]) for p in preds]
    matches_map = fetch_matches_map(sb, fixture_ids)

    updates: List[Dict[str, Any]] = []
    missing_match = 0
    not_finished = 0

    for p in preds:
        fx_id = int(p["fixture_id"])
        m = matches_map.get(fx_id)
        if not m:
            missing_match += 1
            continue

        payload = evaluate(p, m)
        if payload is None:
            not_finished += 1
            continue

        updates.append(payload)

    logger.info(
        "🧾 Pre-update: updates=%s missing_match=%s not_finished=%s",
        len(updates), missing_match, not_finished
    )

    if not updates:
        logger.info("✅ Nessun match valutabile (probabile: non FINISHED o goals null).")
        return

    # Percorso bulk (1 RPC per chunk) con fallback automatico al loop
    # riga-per-riga se la RPC non e' ancora stata applicata sul DB.
    try:
        failed = bulk_update_predictions(sb, updates)
    except _RpcMissingError:
        logger.warning(
            "⚠️ RPC %s non trovata sul DB (migration "
            "migrations/predictions_results_bulk_update_rpc.sql non applicata?): "
            "fallback al loop riga-per-riga.",
            RPC_BULK_UPDATE,
        )
        failed = update_rows_one_by_one(sb, updates)

    logger.info(
        "🏁 COMPLETATO → updated=%s failed=%s missing_match=%s (date=%s)",
        len(updates) - failed, failed, missing_match, target_date
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD (UTC). Se omesso: ieri.")
    parser.add_argument("--force", action="store_true", help="Rivaluta anche se evaluated_at è già valorizzato")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        target_date = (date.today() - timedelta(days=1)).isoformat()

    run(target_date=target_date, force=args.force, limit=args.limit)


if __name__ == "__main__":
    main()
