"""
update_poisson_calibration.py — Ricalcola CALIBRATION_TABLE da tutti i dati reali.

Usa TUTTI i fixture completati (FT/AET/PEN) con db_json_analisi per calcolare,
per ogni mercato Poisson e per ogni bin di probabilità (0-9), il fattore correttivo:

    correction_factor[bin] = actual_hit_rate / avg_model_prob_in_bin

Questo fattore, applicato alla probabilità grezza del modello, la porta più
vicina alla realtà storica.

Output:
  1. Stampa la nuova CALIBRATION_TABLE pronta da incollare in money_management.py
  2. Confronto con la tabella attuale (delta)
  3. Salva calibration_update_YYYYMMDD.json con statistiche complete

Uso:
  python update_poisson_calibration.py
  python update_poisson_calibration.py --min-n 50   # bin con N < 50 restano a 1.0
  python update_poisson_calibration.py --apply       # aggiorna money_management.py automaticamente
"""
from __future__ import annotations

import ast
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# TABELLA ATTUALE — letta dinamicamente da money_management.py
# Nessuna copia hardcodata: ogni run usa sempre i valori reali in produzione.
# ─────────────────────────────────────────────────────────────────────────────
def load_current_calibration_table() -> Dict[str, Dict[int, float]]:
    """Legge CALIBRATION_TABLE direttamente da money_management.py a runtime.
    Ritorna {} se il file non esiste o il pattern non viene trovato:
    in quel caso il confronto delta verrà saltato senza crash."""
    mm_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "Betfair", "money_management.py"
    )
    if not os.path.exists(mm_path):
        return {}
    try:
        with open(mm_path, encoding="utf-8") as f:
            content = f.read()
        # Trova il blocco: CALIBRATION_TABLE = { ... }
        # I valori interni sono dict a singolo livello {0: x, 1: y, ...}
        pattern = re.compile(
            r"^CALIBRATION_TABLE\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\})",
            re.MULTILINE | re.DOTALL,
        )
        m = pattern.search(content)
        if not m:
            return {}
        return ast.literal_eval(m.group(1))
    except Exception as e:
        print(f"  Warning: impossibile parsare CALIBRATION_TABLE da money_management.py — {type(e).__name__}: {e}")
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# MAPPA MERCATI POISSON
# (json_market, json_class, cal_key)
# ─────────────────────────────────────────────────────────────────────────────
MARKET_CONFIG = {
    "H":       ("1x2",                  "H",     "Victoria casa"),
    "D":       ("1x2",                  "D",     "Pareggio"),
    "A":       ("1x2",                  "A",     "Victoria trasferta"),
    "O25":     ("over_2_5",             "True",  "Over 2.5"),
    "U25":     ("over_2_5",             "False", "Under 2.5"),
    "BTTS":    ("btts",                 "True",  "BTTS Si"),
    "BTTS_NO": ("btts",                 "False", "BTTS No"),
    "HT05":    ("first_half_over_0_5",  "True",  "1T Over 0.5"),
    # Mercati estesi aggiunti in produzione 2026-03-30
    "O15":    ("over_1_5",           "True",  "Over 1.5"),
    "U15":    ("over_1_5",           "False", "Under 1.5"),
    "O35":    ("over_3_5",           "True",  "Over 3.5"),
    "U35":    ("over_3_5",           "False", "Under 3.5"),
    "HT_H":   ("ht_1x2",            "H",     "HT Casa"),
    "HT_D":   ("ht_1x2",            "D",     "HT Pareggio"),
    "HT_A":   ("ht_1x2",            "A",     "HT Trasferta"),
    # HT Under 0.5 — calibration entry e usato in _resolve_result; classe "False" di first_half_over_0_5
    "HT_U05": ("first_half_over_0_5", "False", "1H Under 0.5"),
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNZIONE RISULTATO (stessa di master_backtest.py)
# ─────────────────────────────────────────────────────────────────────────────
def check_result(cal_key: str, h: int, a: int, hh: Optional[int], ha: Optional[int]) -> Optional[bool]:
    if cal_key == "H":       return h > a
    if cal_key == "D":       return h == a
    if cal_key == "A":       return h < a
    if cal_key == "O25":     return h + a > 2
    if cal_key == "U25":     return h + a <= 2
    if cal_key == "BTTS":    return h > 0 and a > 0
    if cal_key == "BTTS_NO": return not (h > 0 and a > 0)
    if cal_key == "HT05":
        if hh is None or ha is None: return None
        return hh + ha > 0
    if cal_key == "O15":     return h + a > 1
    if cal_key == "U15":     return h + a <= 1
    if cal_key == "O35":     return h + a > 3
    if cal_key == "U35":     return h + a <= 3
    if cal_key == "HT_H":
        if hh is None or ha is None: return None
        return hh > ha
    if cal_key == "HT_D":
        if hh is None or ha is None: return None
        return hh == ha
    if cal_key == "HT_A":
        if hh is None or ha is None: return None
        return hh < ha
    if cal_key == "HT_U05":
        if hh is None or ha is None: return None
        return hh + ha == 0
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FETCH DATI
# ─────────────────────────────────────────────────────────────────────────────
def fetch_all_data() -> Tuple[List[dict], Dict[int, Tuple[int, int]]]:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_client import get_supabase_client
    sb = get_supabase_client()

    rows: List[dict] = []
    page_size = 1000
    offset = 0

    print("Fetching fixture_predictions con db_json_analisi...")
    while True:
        resp = (
            sb.table("fixture_predictions")
            .select("fixture_id,result_home_goals,result_away_goals,db_json_analisi,league_id")
            .in_("result_status_short", ["FT", "AET", "PEN"])
            .not_.is_("db_json_analisi", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        print(f"  {len(rows)} righe...", end="\r")
        if len(batch) < page_size:
            break
        offset += page_size
    print(f"\n  Totale: {len(rows)}")

    # HT data (per HT05 market)
    print("Fetching halftime data...")
    fids = [r["fixture_id"] for r in rows if r.get("fixture_id")]
    ht_map: Dict[int, Tuple[int, int]] = {}
    for i in range(0, len(fids), 300):
        resp2 = sb.table("matches").select("fixture_id,halftime_home,halftime_away").in_(
            "fixture_id", fids[i:i+300]
        ).execute()
        for row in (resp2.data or []):
            hh = row.get("halftime_home")
            ha = row.get("halftime_away")
            if hh is not None and ha is not None:
                try:
                    ht_map[row["fixture_id"]] = (int(hh), int(ha))
                except (ValueError, TypeError):
                    pass
    print(f"  HT data: {len(ht_map)} fixture\n")
    return rows, ht_map


# ─────────────────────────────────────────────────────────────────────────────
# CALCOLO CALIBRAZIONE
# ─────────────────────────────────────────────────────────────────────────────
def compute_calibration(
    rows: List[dict],
    ht_map: Dict[int, Tuple[int, int]],
    min_n: int = 30,
) -> Dict[str, Dict[int, dict]]:
    """
    Ritorna per ogni (cal_key, bin_idx) le statistiche:
      n, sum_prob, hits, avg_prob, hit_rate, correction_factor
    """
    # {cal_key: {bin_idx: {"n": int, "sum_prob": float, "hits": int}}}
    stats: Dict[str, Dict[int, dict]] = {
        cal_key: {b: {"n": 0, "sum_prob": 0.0, "hits": 0} for b in range(10)}
        for cal_key in MARKET_CONFIG
    }

    skipped = 0
    for row in rows:
        analisi = row.get("db_json_analisi")
        h = row.get("result_home_goals")
        a = row.get("result_away_goals")
        if not analisi or not isinstance(analisi, dict) or h is None or a is None:
            skipped += 1
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            skipped += 1
            continue

        # Escludi record scritti dal modello pre-DC: le probabilità nelle 4 celle
        # basse (0-0, 1-0, 0-1, 1-1) differiscono sistematicamente. Usare record
        # misti produrrebbe fattori di calibrazione contaminati.
        if analisi.get("model") != "poisson_xg_hybrid_dc":
            skipped += 1
            continue

        fid = row.get("fixture_id")
        hh, ha = ht_map.get(fid, (None, None))
        markets = analisi.get("markets", {})

        for cal_key, (json_market, json_class, _label) in MARKET_CONFIG.items():
            market_data = markets.get(json_market)
            if not isinstance(market_data, dict):
                continue
            raw_prob = market_data.get(json_class)
            if raw_prob is None:
                continue
            try:
                prob = float(raw_prob)
            except (ValueError, TypeError):
                continue
            if not (0.0 < prob < 1.0):
                continue

            outcome = check_result(cal_key, h, a, hh, ha)
            if outcome is None:
                continue

            bin_idx = min(int(prob * 10), 9)
            s = stats[cal_key][bin_idx]
            s["n"] += 1
            s["sum_prob"] += prob
            if outcome:
                s["hits"] += 1

    print(f"  Skipped (dati mancanti): {skipped}")
    return stats


def build_calibration_table(
    stats: Dict[str, Dict[int, dict]],
    min_n: int = 30,
) -> Dict[str, Dict[int, float]]:
    """Costruisce la nuova CALIBRATION_TABLE. Bin con N < min_n restano a 1.0."""
    new_table: Dict[str, Dict[int, float]] = {}
    for cal_key, bins in stats.items():
        new_table[cal_key] = {}
        for bin_idx, s in bins.items():
            n = s["n"]
            if n < min_n:
                # Campione insufficiente: usa 1.0 (nessuna correzione)
                new_table[cal_key][bin_idx] = 1.0
            else:
                avg_prob = s["sum_prob"] / n
                hit_rate = s["hits"] / n
                if avg_prob > 0:
                    correction = round(hit_rate / avg_prob, 3)
                    # Cap conservativo [0.2, 3.0]: valori estremi indicano overfitting
                    # su bin rari. Allineato al cap di generate_dynamic_cal.py per
                    # coerenza tra le due tabelle di calibrazione.
                    correction = max(0.2, min(correction, 3.0))
                else:
                    correction = 1.0
                new_table[cal_key][bin_idx] = correction
    return new_table


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────────────────────
def print_comparison(
    stats: Dict[str, Dict[int, dict]],
    new_table: Dict[str, Dict[int, float]],
    min_n: int,
    current_table: Dict[str, Dict[int, float]],
) -> None:
    print("\n" + "=" * 90)
    print("  NUOVA CALIBRATION TABLE — confronto con attuale")
    print("  Bin: 0=[0-10%]  1=[10-20%] ... 9=[90-100%]")
    if not current_table:
        print("  AVVISO: colonna 'Old CF' non disponibile (money_management.py non leggibile)")
    print("=" * 90)

    for cal_key, (_, _, label) in MARKET_CONFIG.items():
        print(f"\n  {cal_key} — {label}")
        print(f"  {'Bin':>4} {'N':>6} {'Avg Prob':>9} {'Hit Rate':>9} {'Bias':>8} {'New CF':>8} {'Old CF':>8} {'Delta':>8} {'Note'}")
        print(f"  {'─'*4} {'─'*6} {'─'*9} {'─'*9} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for bin_idx in range(10):
            s = stats[cal_key][bin_idx]
            n = s["n"]
            if n == 0:
                print(f"  {bin_idx:>4}   [vuoto]")
                continue
            avg_prob = s["sum_prob"] / n
            hit_rate = s["hits"] / n
            bias = hit_rate - avg_prob
            new_cf = new_table[cal_key][bin_idx]
            old_cf = current_table.get(cal_key, {}).get(bin_idx, 1.0)
            delta = new_cf - old_cf
            note = ""
            if n < min_n:
                note = f"N<{min_n} → cf=1.0 (mantenuto)"
            elif abs(delta) > 0.20:
                note = "*** CAMBIO SIGNIFICATIVO ***"
            elif abs(bias) > 0.10:
                note = "forte bias"
            print(f"  {bin_idx:>4} {n:>6} {avg_prob*100:>8.1f}% {hit_rate*100:>8.1f}% "
                  f"{bias*100:>+7.1f}% {new_cf:>8.3f} {old_cf:>8.3f} {delta:>+8.3f}  {note}")


def print_python_table(new_table: Dict[str, Dict[int, float]]) -> None:
    """Stampa la CALIBRATION_TABLE pronta da incollare in money_management.py."""
    print("\n" + "=" * 90)
    print("  CODICE PRONTO — incolla in money_management.py come CALIBRATION_TABLE")
    print("=" * 90)
    print("CALIBRATION_TABLE = {")
    descriptions = {
        "H":       "1X2 Home",
        "D":       "1X2 Draw",
        "A":       "1X2 Away",
        "O25":     "Over 2.5",
        "U25":     "Under 2.5",
        "BTTS":    "BTTS Si",
        "BTTS_NO": "BTTS No",
        "HT05":    "1H Over 0.5",
        "O15":     "Over 1.5",
        "U15":     "Under 1.5",
        "O35":     "Over 3.5",
        "U35":     "Under 3.5",
        "HT_H":    "HT Casa",
        "HT_D":    "HT Pareggio",
        "HT_A":    "HT Trasferta",
        "HT_U05":  "1H Under 0.5",
    }
    for cal_key, bins in new_table.items():
        desc = descriptions.get(cal_key, cal_key)
        values = ", ".join(f"{b}: {v}" for b, v in sorted(bins.items()))
        print(f"    # {desc}")
        print(f"    \"{cal_key}\": {{{values}}},")
    print("}")


# ─────────────────────────────────────────────────────────────────────────────
# APPLY (aggiorna money_management.py automaticamente)
# ─────────────────────────────────────────────────────────────────────────────
def apply_to_money_management(new_table: Dict[str, Dict[int, float]], total_rows: int = 0) -> None:
    """Sostituisce CALIBRATION_TABLE in money_management.py."""
    mm_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "Betfair", "money_management.py"
    )
    if not os.path.exists(mm_path):
        print(f"  ERRORE: non trovo {mm_path}")
        return

    with open(mm_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Costruisce il nuovo blocco
    descriptions = {
        "H":       "1X2 Home — aggiornato da update_poisson_calibration.py",
        "D":       "1X2 Draw",
        "A":       "1X2 Away",
        "O25":     "Over 2.5",
        "U25":     "Under 2.5",
        "BTTS":    "BTTS Si",
        "BTTS_NO": "BTTS No",
        "HT05":    "1H Over 0.5",
        "O15":     "Over 1.5",
        "U15":     "Under 1.5",
        "O35":     "Over 3.5",
        "U35":     "Under 3.5",
        "HT_H":    "HT Casa",
        "HT_D":    "HT Pareggio",
        "HT_A":    "HT Trasferta",
        "HT_U05":  "1H Under 0.5",
    }
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# ---------------------------------------------------------------------------",
        f"#  TABELLA DI CALIBRAZIONE — Aggiornata il {ts} da update_poisson_calibration.py",
        f"#  Derivata da {total_rows} match storici",
        "#  Per ogni mercato e fascia di probabilità: fattore correttivo = WR_reale / Prob_stimata",
        "#  Applicato PRIMA del calcolo dell'edge per usare probabilità realistiche.",
        "# ---------------------------------------------------------------------------",
        "CALIBRATION_TABLE = {",
    ]
    for cal_key, bins in new_table.items():
        desc = descriptions.get(cal_key, cal_key)
        values = ", ".join(f"{b}: {v}" for b, v in sorted(bins.items()))
        lines.append(f"    # {desc}")
        lines.append(f"    \"{cal_key}\": {{{values}}},")
    lines.append("}")
    new_block = "\n".join(lines)

    # Regex per trovare il blocco CALIBRATION_TABLE esistente.
    # La chiusura ^\} deve stare a colonna 0: corrisponde sempre all'outer dict close,
    # mai agli inner dict (che sono indentati e terminano con "},").
    pattern = re.compile(
        r"# -{10,}.*?TABELLA DI CALIBRAZIONE.*?^CALIBRATION_TABLE\s*=\s*\{.*?^\}",
        re.DOTALL | re.MULTILINE
    )
    match = pattern.search(content)
    if not match:
        print("  ATTENZIONE: pattern CALIBRATION_TABLE non trovato in money_management.py")
        print("  Incolla manualmente il codice stampato sopra.")
        return

    new_content = content[:match.start()] + new_block + content[match.end():]

    # Backup
    backup_path = mm_path + ".cal_backup"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Backup salvato: {backup_path}")

    # Validazione sintattica prima di scrivere — evita di corrompere il file live
    try:
        compile(new_content, mm_path, "exec")
    except SyntaxError as syn_err:
        print(f"  ERRORE CRITICO: il nuovo contenuto ha errori di sintassi Python — scrittura annullata!")
        print(f"  Dettaglio: {syn_err}")
        print(f"  Il file originale NON è stato modificato. Backup disponibile in: {backup_path}")
        return

    with open(mm_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  money_management.py aggiornato con la nuova CALIBRATION_TABLE")


# ─────────────────────────────────────────────────────────────────────────────
# SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────
def save_json(
    stats: Dict[str, Dict[int, dict]],
    new_table: Dict[str, Dict[int, float]],
    output_path: str,
    total_rows: int,
) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": total_rows,
        "new_calibration_table": new_table,
        "per_market_stats": {
            cal_key: {
                str(bin_idx): {
                    "n": s["n"],
                    "avg_prob": round(s["sum_prob"] / s["n"], 4) if s["n"] > 0 else 0,
                    "hit_rate": round(s["hits"] / s["n"], 4) if s["n"] > 0 else 0,
                    "correction_factor": new_table.get(cal_key, {}).get(bin_idx, 1.0),
                }
                for bin_idx, s in bins.items()
                if s["n"] > 0
            }
            for cal_key, bins in stats.items()
        },
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON salvato: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Ricalcola CALIBRATION_TABLE Poisson")
    parser.add_argument("--min-n", type=int, default=30,
                        help="Bin con N < min_n restano a 1.0 (default: 30)")
    parser.add_argument("--apply", action="store_true",
                        help="Aggiorna money_management.py automaticamente (crea backup)")
    args = parser.parse_args()

    # 0. Carica tabella corrente da money_management.py (sempre aggiornata, mai hardcodata)
    current_table = load_current_calibration_table()
    if not current_table:
        print("  AVVISO: impossibile leggere CALIBRATION_TABLE da money_management.py")
        print("  Il confronto delta mostrerà 'Old CF' = 1.0 per tutti i bin.\n")

    # 1. Fetch
    rows, ht_map = fetch_all_data()

    # 2. Calcola calibrazione
    print("Calcolando statistiche per bin...")
    stats = compute_calibration(rows, ht_map, min_n=args.min_n)

    # 3. Costruisce nuova tabella
    new_table = build_calibration_table(stats, min_n=args.min_n)

    # 4. Mostra confronto
    print_comparison(stats, new_table, min_n=args.min_n, current_table=current_table)

    # 5. Mostra codice pronto
    print_python_table(new_table)

    # 6. Salva JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"calibration_update_{ts}.json"
    )
    save_json(stats, new_table, json_path, len(rows))

    # 7. Applica (opzionale)
    if args.apply:
        print("\nApplico a money_management.py...")
        apply_to_money_management(new_table, total_rows=len(rows))
    else:
        print("\n  Aggiungi --apply per aggiornare money_management.py automaticamente.")
        print("  Oppure incolla il codice CALIBRATION_TABLE stampato sopra.")

    # 8. Summary
    print("\n" + "=" * 90)
    print("  RIEPILOGO CALIBRAZIONE")
    print("=" * 90)
    total_samples = sum(
        s["n"] for bins in stats.values() for s in bins.values()
    )
    print(f"  Fixture analizzate   : {len(rows)}")
    print(f"  Campioni totali      : {total_samples} (fixture × mercati con dato)")
    print(f"  Bin con N >= {args.min_n}     : {sum(1 for bins in stats.values() for s in bins.values() if s['n'] >= args.min_n)}")
    print(f"  Bin a 1.0 (N < {args.min_n}) : {sum(1 for bins in stats.values() for s in bins.values() if 0 < s['n'] < args.min_n)}")
    print(f"  Bin vuoti            : {sum(1 for bins in stats.values() for s in bins.values() if s['n'] == 0)}")
    print()

    # Mercati con bias sistematico significativo
    print("  Mercati con bias significativo (|bias| > 5pp su almeno un bin con N>=50):")
    for cal_key, bins in stats.items():
        _, _, label = MARKET_CONFIG[cal_key]
        bad_bins = []
        for bin_idx, s in bins.items():
            if s["n"] >= 50:
                avg_p = s["sum_prob"] / s["n"]
                hr = s["hits"] / s["n"]
                if abs(hr - avg_p) > 0.05:
                    bad_bins.append((bin_idx, avg_p, hr, hr - avg_p))
        if bad_bins:
            print(f"\n  {cal_key} ({label}):")
            for bin_idx, ap, hr, bias in bad_bins:
                direction = "SOVRASTIMA" if bias < 0 else "SOTTOSTIMA"
                print(f"    bin {bin_idx} [{bin_idx*10}-{(bin_idx+1)*10}%]: "
                      f"model={ap*100:.1f}% reale={hr*100:.1f}% bias={bias*100:+.1f}pp {direction}")


if __name__ == "__main__":
    main()
