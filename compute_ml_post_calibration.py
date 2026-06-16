"""
compute_ml_post_calibration.py  —  ASSEMBLATORE calibrazione post-hoc per-lega
------------------------------------------------------------------------------
Costruisce la tabella public.ml_post_calibration a partire dalle CELLE DI
CALIBRAZIONE out-of-sample emesse dal training (col. ai_model_registry.calibration_cells).

PERCHE' OUT-OF-SAMPLE / NO LEAK:
  Le celle vengono dall'HOLDOUT di ogni modello (la fetta che il training NON usa
  per imparare), gia' calcolata in seriea_model_export._train_one_target. Qui si
  SOLO AGGREGANO numeri — nessuna ri-predizione dello storico (che sarebbe
  in-sample = leak), nessun modello caricato.

STRUTTURA CELLA (per riga registry = una coppia lega/target):
  calibration_cells = { classe: { bin("0".."9"): {n, pred_sum, out_sum} } }
    n        = #righe holdout la cui P(classe) cade nel bin
    pred_sum = somma delle P(classe) previste nel bin
    out_sum  = #righe del bin il cui esito reale == classe

CORREZIONE per cella (con abbastanza campioni):
    hit_rate = out_sum / n ;  avg_pred = pred_sum / n
    cf = hit_rate / avg_pred = out_sum / pred_sum        (clamp [0.3, 3.0])
  Sotto la soglia min-n la cella e' OMESSA => il consumer cade sul fallback.

OUTPUT (tutto su DB, tabella public.ml_post_calibration):
  una riga per lega   -> {league_id, corrections={target:{classe:{bin:cf}}}, min_n, generated_at}
  una riga league_id=0 -> il FALLBACK GLOBALE (somma su TUTTE le leghe)

Il consumer (predict_fixture.py) legge 2 righe: quella della lega + quella globale
(league_id IN (<lega>, 0)) e cerca: lega → bin; se assente → global → bin; se
assente → cf=1.0. Copre TUTTI i mercati che hanno celle.

Uso:
    python compute_ml_post_calibration.py                  # scrive la tabella DB
    python compute_ml_post_calibration.py --min-n 30       # soglia campioni per bin
    python compute_ml_post_calibration.py --out prova.json # SOLO test: scrive su file, NON tocca il DB
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Optional

MIN_N_DEFAULT = 20   # campioni minimi per bin per fidarsi della correzione
CF_FLOOR = 0.3       # clamp conservativo (coerente col valore storico ML)
CF_CEIL = 3.0


def _norm_ts(s: str) -> str:
    """Normalizza un timestamp ISO per il confronto lessicografico: 'Z' -> '+00:00'
    (cosi' due timestamp dello stesso istante con suffissi diversi si confrontano
    correttamente). Stringhe vuote restano vuote (< di qualsiasi timestamp)."""
    s = (s or "").strip()
    return s[:-1] + "+00:00" if s.endswith("Z") else s


def _new_cell() -> dict:
    return {"n": 0, "pred_sum": 0.0, "out_sum": 0}


def _add_cell(dst: dict, src: dict) -> None:
    """Somma una cella sorgente (da DB) in un accumulatore."""
    try:
        dst["n"] += int(src.get("n", 0) or 0)
        dst["pred_sum"] += float(src.get("pred_sum", 0.0) or 0.0)
        dst["out_sum"] += int(src.get("out_sum", 0) or 0)
    except (TypeError, ValueError):
        pass


def _cf_from_cell(cell: dict, min_n: int) -> Optional[float]:
    """Correzione per una cella aggregata. None se campioni insufficienti."""
    n = int(cell.get("n", 0) or 0)
    if n < min_n:
        return None
    ps = float(cell.get("pred_sum", 0.0) or 0.0)
    if ps <= 0:
        return 1.0
    cf = round(float(cell.get("out_sum", 0) or 0) / ps, 3)
    return max(CF_FLOOR, min(cf, CF_CEIL))


def _fetch_registry_cells() -> list:
    """Scarica (league_id, target, calibration_cells, trained_at) dal registry,
    solo righe con celle non-null. trained_at serve a capire quali leghe sono
    state riaddestrate dall'ultima calibrazione."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_client import get_supabase_client
    sb = get_supabase_client()
    rows = []
    page = 1000
    off = 0
    print("Fetching calibration_cells dal registry...")
    while True:
        resp = (
            sb.table("ai_model_registry")
            .select("league_id,target,calibration_cells,trained_at")
            .not_.is_("calibration_cells", "null")
            .range(off, off + page - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        print(f"  {len(rows)} righe con celle...", end="\r")
        if len(batch) < page:
            break
        off += page
    print(f"\n  Totale righe con celle: {len(rows)}")
    return rows


def _fetch_cal_timestamps() -> dict:
    """{league_id(str): generated_at} dalla tabella ml_post_calibration. Serve a
    capire quali leghe hanno la calibrazione PIU' VECCHIA del loro ultimo
    trained_at (= sono state riaddestrate dall'ultima calibrazione)."""
    from db_client import get_supabase_client
    sb = get_supabase_client()
    out: Dict[str, str] = {}
    try:
        data = sb.table("ml_post_calibration").select("league_id,generated_at").execute().data or []
        for r in data:
            out[str(r.get("league_id"))] = str(r.get("generated_at") or "")
    except Exception as e:
        print(f"  [WARN] lettura timestamp calibrazione saltata: {e}")
    return out


def assemble(rows: list, min_n: int) -> dict:
    """Aggrega le celle del registry in calibrazione per-lega + globale."""
    # accumulatori raw: leghe[lid][target][cls][bin] e global[target][cls][bin]
    leagues_raw: Dict[str, dict] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(_new_cell)))
    )
    global_raw: Dict[str, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(_new_cell)))
    trained_at_map: Dict[str, str] = {}   # lid -> max(trained_at) tra i suoi modelli

    n_cells = 0
    for r in rows:
        lid = str(r.get("league_id"))
        if lid == "None":          # difesa: league_id NULL (non dovrebbe accadere, PK NOT NULL)
            continue
        ta = str(r.get("trained_at") or "")
        if ta and ta > trained_at_map.get(lid, ""):
            trained_at_map[lid] = ta
        tgt = r.get("target")
        cells = r.get("calibration_cells")
        if not tgt or not isinstance(cells, dict):
            continue
        for cls, bins in cells.items():
            if not isinstance(bins, dict):
                continue
            for b, cell in bins.items():
                if not isinstance(cell, dict):
                    continue
                b = str(b)
                _add_cell(leagues_raw[lid][tgt][cls][b], cell)
                _add_cell(global_raw[tgt][cls][b], cell)
                n_cells += 1

    # calcola correction factor; OMETTE le celle sotto soglia (=> fallback)
    def _finalize(raw: dict) -> dict:
        out: Dict[str, dict] = {}
        for tgt, cls_map in raw.items():
            for cls, bin_map in cls_map.items():
                for b, cell in bin_map.items():
                    cf = _cf_from_cell(cell, min_n)
                    if cf is None or cf == 1.0:
                        continue  # niente correzione utile => non scrivere (fallback/identity)
                    out.setdefault(tgt, {}).setdefault(cls, {})[b] = cf
        return out

    leagues_out = {lid: _finalize(cls_map) for lid, cls_map in leagues_raw.items()}
    leagues_out = {lid: v for lid, v in leagues_out.items() if v}  # scarta leghe senza correzioni
    global_out = _finalize(global_raw)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_n": min_n,
        "n_leagues_total": len(leagues_raw),
        "n_leagues_with_corrections": len(leagues_out),
        "n_cells_aggregated": n_cells,
        "leagues": leagues_out,
        "global": global_out,
        "trained_at": trained_at_map,
    }


def _report(result: dict) -> None:
    print("\n" + "=" * 72)
    print("  ASSEMBLATORE CALIBRAZIONE POST-HOC (per-lega + globale)")
    print("=" * 72)
    print(f"  Leghe con celle: {result['n_leagues_total']}")
    print(f"  Leghe con correzioni utili (>= min_n): {result['n_leagues_with_corrections']}")
    print(f"  Celle aggregate: {result['n_cells_aggregated']}")
    g = result["global"]
    n_global = sum(len(b) for t in g.values() for b in t.values())
    print(f"  Correzioni GLOBALI attive: {n_global} (target globali: {sorted(g.keys())})")


def _write_to_db(result: dict, only_leagues=None) -> int:
    """Upsert delle correzioni nella tabella public.ml_post_calibration.
    Sempre la riga globale (league_id=0). Per le righe-lega:
      - only_leagues=None  => TUTTE (modalita' full / rete di sicurezza) + pulizia obsolete;
      - only_leagues={...}  => SOLO quelle leghe (modalita' incrementale: le riaddestrate),
                               nessuna pulizia (non tocchiamo righe di leghe non coinvolte).
    Usa service_role (RLS bypassato). Idempotente (upsert su PK league_id)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_client import get_supabase_client
    sb = get_supabase_client()
    ga = result["generated_at"]
    mn = result["min_n"]
    _only = None if only_leagues is None else {str(x) for x in only_leagues}
    if _only is None:
        # FULL: tutte le leghe con correzioni utili.
        src = list(result["leagues"].items())
    else:
        # INCREMENTALE: una riga per OGNI lega stale (riaddestrata), ANCHE con
        # correzioni vuote {} se ora non ne ha di utili (holdout troppo piccolo):
        # cosi' la calibrazione vecchia viene INVALIDATA e il generated_at
        # aggiornato (stop al re-processing infinito), e il serving ricade sul
        # fallback globale per quella lega.
        src = [(lid, result["leagues"].get(lid, {})) for lid in _only]
    league_rows = []
    for lid, corr in src:
        if str(lid) == "None":
            continue
        try:
            league_rows.append(
                {"league_id": int(lid), "corrections": corr, "min_n": mn, "generated_at": ga}
            )
        except (TypeError, ValueError):
            continue
    # La riga GLOBALE (league_id=0) va scritta PER PRIMA: il fallback deve esistere
    # sempre, anche se l'upsert delle righe-lega fallisse a meta' (le leghe non
    # ancora scritte ricadono sul globale, gia' presente).
    rows = [{"league_id": 0, "corrections": result["global"], "min_n": mn, "generated_at": ga}] + league_rows
    written = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        try:
            sb.table("ml_post_calibration").upsert(batch).execute()
        except Exception as e:
            # Fallire RUMOROSAMENTE (il workflow deve accorgersene), non lasciare
            # un upsert parziale silenzioso.
            raise RuntimeError(f"Upsert ml_post_calibration fallito al batch offset {i}: {e}") from e
        written += len(batch)
    # Pulizia righe-lega obsolete: SOLO in modalita' full (only_leagues=None). In
    # incrementale non tocchiamo le leghe non coinvolte, quindi non si puo' dedurre
    # l'obsolescenza dal solo result.
    if only_leagues is None:
        try:
            keep = {int(lid) for lid in result["leagues"].keys()} | {0}
            existing = sb.table("ml_post_calibration").select("league_id").execute().data or []
            obsolete = [r["league_id"] for r in existing if r["league_id"] not in keep]
            for lid in obsolete:
                sb.table("ml_post_calibration").delete().eq("league_id", lid).execute()
            if obsolete:
                print(f"  Righe obsolete rimosse: {len(obsolete)}")
        except Exception as e:
            print(f"  [WARN] pulizia righe obsolete saltata: {e}")
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-n", type=int, default=MIN_N_DEFAULT)
    parser.add_argument("--full", action="store_true",
                        help="Riscrive TUTTE le leghe + pulizia obsolete (rete di sicurezza "
                             "giornaliera). Default: INCREMENTALE = solo le leghe riaddestrate "
                             "dall'ultima calibrazione.")
    parser.add_argument("--out", type=str, default=None,
                        help="SOLO test: scrive il risultato su questo file JSON invece che sul DB.")
    args = parser.parse_args()

    rows = _fetch_registry_cells()
    if not rows:
        print("  Nessuna cella nel registry: nulla da assemblare. Esco senza scrivere.")
        return
    result = assemble(rows, min_n=args.min_n)

    # INCREMENTALE (default): aggiorna SOLO le leghe il cui modello e' piu' nuovo
    # della loro calibrazione attuale (= riaddestrate dall'ultima volta). Se nessuna
    # e' cambiata => non fa nulla. --full forza tutte (rete di sicurezza).
    only = None
    if not args.full and not args.out:
        cal_ts = _fetch_cal_timestamps()
        ta_map = result.get("trained_at", {})
        stale = {
            lid for lid, ta in ta_map.items()
            if ta and _norm_ts(ta) > _norm_ts(cal_ts.get(lid, ""))
        }
        if not stale:
            print("\n  Nessuna lega riaddestrata dall'ultima calibrazione: niente da fare.")
            return
        only = stale
        print(f"\n  Modalita' INCREMENTALE: {len(stale)} leghe riaddestrate da ricalibrare.")

    _report(result)

    if args.out:
        out_path = (
            args.out if os.path.isabs(args.out)
            else os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
        )
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        os.replace(tmp, out_path)
        print(f"\n  [TEST] Salvato su file (DB NON toccato): {out_path}")
    else:
        n = _write_to_db(result, only_leagues=only)
        scope = "TUTTE (full)" if only is None else f"{len(only)} riaddestrate (incrementale)"
        print(f"\n  Scritto su DB public.ml_post_calibration: {n} righe (globale + {scope}).")


if __name__ == "__main__":
    main()
