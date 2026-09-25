# -*- coding: utf-8 -*-
"""verifica_transizioni_2026_09_25 -- verifica in SOLA LETTURA delle tabelle di
transizione di Omega dopo la migrazione
``migrations/omega_transitions_catchup_2026-09-25.sql``.

Stampa NUMERI, non giudizi. Nessuna scrittura: solo SELECT via PostgREST e le tre
RPC di lettura della migrazione (``omega_transitions_status``,
``omega_transitions_ledger_counts``, ``omega_transitions_compare``).

Invarianti misurati (il valore atteso e' scritto accanto, il giudizio a chi legge):
  A. per lega: somma di n a bucket 0 target 'ft' = partite nel registro con
     minute_at (grezzo: tutte le leghe; pubblicato: leghe presenti + globale 0);
     per lega: somma di n HT->FT = partite nel registro con ht_ft_at;
  B. celle con n <= 0 nelle quattro tabelle (atteso 0);
  C. built_at massimo delle tabelle (atteso >= oggi dopo un giro con partite);
  D. leghe pubblicate contro leghe ammesse (registro n_minute >= soglia);
  E. contatori per lega (omega_transitions_league_counts e
     omega_minute_league_counts) contro il registro;
  F. ultimi giri (omega_transitions_runs): un secondo giro subito dopo conta 0.

Uso:
    python -m Betfair.omega.tools.verifica_transizioni_2026_09_25
    python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --confronto pre
    python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --salva-impronta imp1.json
    python -m Betfair.omega.tools.verifica_transizioni_2026_09_25 --confronta-impronta imp1.json

Carico: ~15 pagine (bucket 0 pubblicato), ~50 (bucket 0 grezzo), ~2 x 140 (HT->FT),
una GROUP BY sul registro (RPC), 4 conteggi n <= 0, 4 massimi di built_at;
``--confronto`` aggiunge due join complete lato DB (una volta).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

PAGINA = 1000   # max-rows di PostgREST su Supabase

T_MIN = "omega_minute_transitions"
T_MIN_RAW = "omega_minute_transitions_raw"
T_HT = "omega_ht_ft_transitions"
T_HT_RAW = "omega_ht_ft_transitions_raw"
T_CONTATORI = "omega_transitions_league_counts"
T_LEGHE_PUB = "omega_minute_league_counts"

# chiavi delle RPC e colonne delle tabelle della migrazione (il test di contratto
# le confronta con il file SQL: una chiave rinominata la' fa diventare rosso il test)
CHIAVI_STATUS = ("state", "runs", "pg_cron", "cron_jobs", "cron_last_runs",
                 "index_matches_fixture_date", "index_match_events_goal",
                 "backup_pre_ledger", "league_counts_global", "now")
COLONNE_STATE = ("id_cursor", "sweep_cursor", "sweep_cycles", "bootstrap_started_at",
                 "bootstrap_done_at", "published_at", "min_league_matches", "updated_at")
COLONNE_RUN = ("id", "started_at", "elapsed_s", "dry_run", "status", "published", "steps",
               "scanned", "ht_ft_counted", "minute_counted", "minute_rejected",
               "hot_candidates", "hot_skipped_no_index", "id_cursor_from", "id_cursor_to",
               "max_id", "sweep_from", "sweep_to", "live_minute_upserts",
               "live_ht_ft_upserts", "new_leagues", "error")
CHIAVI_REGISTRO = ("league_id", "n_minute", "n_ht_ft", "n_rejected_open")
CHIAVI_CONFRONTO = ("cells_old", "cells_new", "cells_equal", "cells_grown", "cells_lower",
                    "deficit_sum", "cells_missing", "cells_added", "matches_global_old",
                    "matches_global_new", "leagues_old", "leagues_new")


# ---------------------------------------------------------------------------
# lettura
# ---------------------------------------------------------------------------
def _pagine(sb, tabella: str, colonne: str, ordine: Iterable[str],
            filtri: Iterable[Tuple[str, str, Any]] = ()) -> List[dict]:
    """Tutte le righe, a pagine da ``PAGINA`` (PostgREST non ne da' di piu')."""
    fuori: List[dict] = []
    off = 0
    filtri = list(filtri)
    ordine = list(ordine)
    while True:
        q = sb.table(tabella).select(colonne)
        for op, col, val in filtri:
            q = getattr(q, op)(col, val)
        for col in ordine:
            q = q.order(col)
        d = q.range(off, off + PAGINA - 1).execute().data or []
        fuori.extend(d)
        if len(d) < PAGINA:
            break
        off += PAGINA
    return fuori


def _conta(sb, tabella: str, filtri: Iterable[Tuple[str, str, Any]]) -> int:
    q = sb.table(tabella).select("league_id", count="exact")
    for op, col, val in filtri:
        q = getattr(q, op)(col, val)
    res = q.limit(1).execute()
    return int(res.count or 0)


def _massimo(sb, tabella: str, colonna: str) -> Optional[str]:
    d = (sb.table(tabella).select(colonna).order(colonna, desc=True).limit(1).execute().data or [])
    return d[0][colonna] if d else None


def _rpc(sb, nome: str, params: Optional[dict] = None) -> Any:
    return sb.rpc(nome, params or {}).execute().data


def _somme_per_lega(righe: List[dict]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for r in righe:
        lg = int(r["league_id"])
        out[lg] = out.get(lg, 0) + int(r["n"])
    return out


def _diff(atteso: Dict[int, int], visto: Dict[int, int], chiavi: Iterable[int]) -> List[Tuple[int, int, int]]:
    """[(lega, atteso, visto)] dove differiscono, sulle chiavi date."""
    fuori = []
    for lg in sorted(set(chiavi)):
        a, v = int(atteso.get(lg, 0)), int(visto.get(lg, 0))
        if a != v:
            fuori.append((lg, a, v))
    return fuori


# ---------------------------------------------------------------------------
# raccolta dei numeri
# ---------------------------------------------------------------------------
def raccogli(sb, soglia: Optional[int] = None, confronto: Optional[str] = None) -> Dict[str, Any]:
    stato = _rpc(sb, "omega_transitions_status") or {}
    st = stato.get("state") or {}
    pubblicata = st.get("published_at") is not None
    soglia_usata = int(soglia if soglia is not None else (st.get("min_league_matches") or 1000))

    registro_righe = _rpc(sb, "omega_transitions_ledger_counts") or []
    reg_min = {int(r["league_id"]): int(r["n_minute"]) for r in registro_righe}
    reg_ht = {int(r["league_id"]): int(r["n_ht_ft"]) for r in registro_righe}
    reg_rej = {int(r["league_id"]): int(r["n_rejected_open"]) for r in registro_righe}

    b0 = [("eq", "bucket", 0), ("eq", "target", "ft")]
    ord_min = ("league_id", "score", "result")
    raw_min = _somme_per_lega(_pagine(sb, T_MIN_RAW, "league_id,n", ord_min, b0))
    pub_min = _somme_per_lega(_pagine(sb, T_MIN, "league_id,n", ord_min, b0))
    ord_ht = ("league_id", "ht", "ft")
    raw_ht = _somme_per_lega(_pagine(sb, T_HT_RAW, "league_id,n", ord_ht))
    pub_ht = _somme_per_lega(_pagine(sb, T_HT, "league_id,n", ord_ht))

    contatori = _pagine(sb, T_CONTATORI, "league_id,n_minute,n_ht_ft", ("league_id",))
    cont_min = {int(r["league_id"]): int(r["n_minute"]) for r in contatori}
    cont_ht = {int(r["league_id"]): int(r["n_ht_ft"]) for r in contatori}
    leghe_pub = {int(r["league_id"]): int(r["n"])
                 for r in _pagine(sb, T_LEGHE_PUB, "league_id,n", ("league_id",))}

    leghe_reg = [lg for lg, n in reg_min.items() if n > 0]
    leghe_reg_ht = [lg for lg, n in reg_ht.items() if n > 0]
    ammesse = {lg for lg, n in reg_min.items() if lg != 0 and n >= soglia_usata}
    pubblicate = {lg for lg in pub_min if lg != 0}

    n: Dict[str, Any] = {
        "letto_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pubblicata": pubblicata,
        "soglia_leghe": soglia_usata,
        "stato": {k: st.get(k) for k in COLONNE_STATE},
        "pg_cron": stato.get("pg_cron"),
        "cron_jobs": stato.get("cron_jobs"),
        "cron_last_runs": stato.get("cron_last_runs"),
        "indice_matches_fixture_date": stato.get("index_matches_fixture_date"),
        "indice_match_events_goal": stato.get("index_match_events_goal"),
        "copia_11_09": stato.get("backup_pre_ledger"),
        "registro": {
            "partite_minuto": reg_min.get(0, 0),
            "partite_ht_ft": reg_ht.get(0, 0),
            "scartate_aperte": reg_rej.get(0, 0),
            "leghe_con_partite": len([lg for lg in leghe_reg if lg != 0]),
        },
        # A
        "A_grezzo_minuto": {
            "leghe_confrontate": len(set(leghe_reg) | set(raw_min)),
            "leghe_diverse": _diff(reg_min, raw_min, set(leghe_reg) | set(raw_min)),
            "globale_somma_b0": raw_min.get(0, 0), "globale_registro": reg_min.get(0, 0),
        },
        "A_grezzo_ht_ft": {
            "leghe_confrontate": len(set(leghe_reg_ht) | set(raw_ht)),
            "leghe_diverse": _diff(reg_ht, raw_ht, set(leghe_reg_ht) | set(raw_ht)),
            "globale_somma": raw_ht.get(0, 0), "globale_registro": reg_ht.get(0, 0),
        },
        "A_pubblicato_minuto": {
            "leghe_confrontate": len(pub_min),
            "leghe_diverse": _diff(reg_min, pub_min, pub_min.keys()) if pubblicata else None,
            "globale_somma_b0": pub_min.get(0, 0), "globale_registro": reg_min.get(0, 0),
        },
        "A_pubblicato_ht_ft": {
            "leghe_confrontate": len(pub_ht),
            "leghe_diverse": _diff(reg_ht, pub_ht, set(pub_ht) | set(leghe_reg_ht)) if pubblicata else None,
            "globale_somma": pub_ht.get(0, 0), "globale_registro": reg_ht.get(0, 0),
        },
        # B
        "B_celle_n_non_positivo": {t: _conta(sb, t, [("lte", "n", 0)])
                                   for t in (T_MIN, T_MIN_RAW, T_HT, T_HT_RAW)},
        # C
        "C_built_at_max": {t: _massimo(sb, t, "built_at") for t in (T_MIN, T_MIN_RAW, T_HT, T_HT_RAW)},
        # D
        "D_leghe": {
            "pubblicate": len(pubblicate),
            "ammesse_dal_registro": len(ammesse),
            "pubblicate_non_ammesse": sorted(pubblicate - ammesse),
            "ammesse_non_pubblicate": sorted(ammesse - pubblicate),
            "min_partite_fra_pubblicate": min((reg_min.get(lg, 0) for lg in pubblicate), default=None),
            "max_partite_fra_escluse": max((v for lg, v in reg_min.items()
                                            if lg != 0 and lg not in pubblicate), default=None),
        },
        # E
        "E_contatori": {
            "minuto_leghe_diverse": _diff(reg_min, cont_min, set(reg_min) | set(cont_min)),
            "ht_ft_leghe_diverse": _diff(reg_ht, cont_ht, set(reg_ht) | set(cont_ht)),
            "pubblicati_leghe_diverse": (_diff({k: v for k, v in reg_min.items() if k != 0 and v > 0},
                                               leghe_pub, set(k for k, v in reg_min.items() if k != 0 and v > 0)
                                               | set(leghe_pub)) if pubblicata else None),
        },
        # F
        "F_giri": [{k: r.get(k) for k in COLONNE_RUN} for r in (stato.get("runs") or [])],
        # per l'impronta
        "_somme": {"raw_min_b0": raw_min, "pub_min_b0": pub_min, "raw_ht": raw_ht,
                   "pub_ht": pub_ht, "registro_min": reg_min, "registro_ht": reg_ht},
    }
    if confronto:
        cmp = _rpc(sb, "omega_transitions_compare", {"p_mode": confronto}) or {}
        n["confronto"] = {
            "modo": cmp.get("mode"),
            "soglia": cmp.get("min_league_matches"),
            "minute": {k: (cmp.get("minute") or {}).get(k) for k in CHIAVI_CONFRONTO},
            "ht_ft": {k: (cmp.get("ht_ft") or {}).get(k) for k in CHIAVI_CONFRONTO},
        }
    return n


# ---------------------------------------------------------------------------
# impronta (per "secondo giro => zero variazioni" e per il prima/dopo)
# ---------------------------------------------------------------------------
def impronta(numeri: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    return {nome: {str(k): int(v) for k, v in sorted(d.items())}
            for nome, d in numeri["_somme"].items()}


def confronta_impronte(prima: Dict[str, Dict[str, int]], dopo: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, int]]:
    fuori: Dict[str, Dict[str, int]] = {}
    for nome in sorted(set(prima) | set(dopo)):
        a, b = prima.get(nome, {}), dopo.get(nome, {})
        chiavi = set(a) | set(b)
        cambiate = [k for k in chiavi if int(a.get(k, 0)) != int(b.get(k, 0))]
        fuori[nome] = {
            "leghe_prima": len(a), "leghe_dopo": len(b), "leghe_cambiate": len(cambiate),
            "delta_totale": sum(int(b.get(k, 0)) - int(a.get(k, 0)) for k in chiavi),
            "delta_negativi": sum(1 for k in cambiate if int(b.get(k, 0)) < int(a.get(k, 0))),
        }
    return fuori


# ---------------------------------------------------------------------------
# stampa
# ---------------------------------------------------------------------------
def _fmt_diff(d: Optional[List[Tuple[int, int, int]]], quante: int = 20) -> str:
    if d is None:
        return "non misurato (tabella non pubblicata)"
    if not d:
        return "0"
    corpo = ", ".join(f"lega {lg}: atteso {a} visto {v}" for lg, a, v in d[:quante])
    return f"{len(d)}  [{corpo}{' ...' if len(d) > quante else ''}]"


def stampa(n: Dict[str, Any], out=None) -> None:
    out = out or sys.stdout
    p = lambda s="": print(s, file=out)  # noqa: E731
    p(f"letto il: {n['letto_il']}")
    p(f"pubblicata: {n['pubblicata']}   soglia leghe: {n['soglia_leghe']}")
    p("stato: " + ", ".join(f"{k}={v}" for k, v in n["stato"].items()))
    p(f"pg_cron: {n['pg_cron']}   job: {json.dumps(n['cron_jobs'], ensure_ascii=True)}")
    p(f"ultimi giri pg_cron: {json.dumps(n['cron_last_runs'], ensure_ascii=True, default=str)}")
    p(f"indice matches(fixture_date): {n['indice_matches_fixture_date']}   "
      f"indice gol match_events: {n['indice_match_events_goal']}   copia 11/09: {n['copia_11_09']}")
    r = n["registro"]
    p(f"registro: partite minuto {r['partite_minuto']}, partite HT-FT {r['partite_ht_ft']}, "
      f"scartate aperte {r['scartate_aperte']}, leghe {r['leghe_con_partite']}")
    p()
    for chiave, titolo in (("A_grezzo_minuto", "A grezzo minuto (somma b0 ft = registro)"),
                           ("A_pubblicato_minuto", "A pubblicato minuto (somma b0 ft = registro)")):
        a = n[chiave]
        p(f"{titolo}: leghe confrontate {a['leghe_confrontate']}, leghe diverse {_fmt_diff(a['leghe_diverse'])}, "
          f"globale {a['globale_somma_b0']} / registro {a['globale_registro']}")
    for chiave, titolo in (("A_grezzo_ht_ft", "A grezzo HT-FT (somma = registro)"),
                           ("A_pubblicato_ht_ft", "A pubblicato HT-FT (somma = registro)")):
        a = n[chiave]
        p(f"{titolo}: leghe confrontate {a['leghe_confrontate']}, leghe diverse {_fmt_diff(a['leghe_diverse'])}, "
          f"globale {a['globale_somma']} / registro {a['globale_registro']}")
    p("B celle con n <= 0 (atteso 0): " + ", ".join(f"{t}={v}" for t, v in n["B_celle_n_non_positivo"].items()))
    p("C built_at massimo: " + ", ".join(f"{t}={v}" for t, v in n["C_built_at_max"].items()))
    d = n["D_leghe"]
    p(f"D leghe: pubblicate {d['pubblicate']}, ammesse dal registro {d['ammesse_dal_registro']}, "
      f"pubblicate non ammesse {len(d['pubblicate_non_ammesse'])} {d['pubblicate_non_ammesse'][:20]}, "
      f"ammesse non pubblicate {len(d['ammesse_non_pubblicate'])} {d['ammesse_non_pubblicate'][:20]}, "
      f"min partite fra pubblicate {d['min_partite_fra_pubblicate']}, "
      f"max partite fra escluse {d['max_partite_fra_escluse']}")
    e = n["E_contatori"]
    p(f"E contatori: minuto leghe diverse {_fmt_diff(e['minuto_leghe_diverse'])}, "
      f"HT-FT leghe diverse {_fmt_diff(e['ht_ft_leghe_diverse'])}, "
      f"omega_minute_league_counts leghe diverse {_fmt_diff(e['pubblicati_leghe_diverse'])}")
    p("F ultimi giri (piu' recente prima):")
    for g in n["F_giri"]:
        p("   " + ", ".join(f"{k}={g.get(k)}" for k in COLONNE_RUN))
    if "confronto" in n:
        c = n["confronto"]
        p(f"confronto {c['modo']} (soglia {c['soglia']}):")
        for t in ("minute", "ht_ft"):
            p(f"   {t}: " + ", ".join(f"{k}={v}" for k, v in c[t].items()))


def stampa_confronto_impronte(delta: Dict[str, Dict[str, int]], out=None) -> None:
    out = out or sys.stdout
    for nome, d in delta.items():
        print(f"impronta {nome}: " + ", ".join(f"{k}={v}" for k, v in d.items()), file=out)


# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None, sb=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--soglia", type=int, default=None,
                    help="soglia partite per lega (default: quella pubblicata nello stato)")
    ap.add_argument("--confronto", choices=("pre", "post"), default=None,
                    help="confronto cella per cella lato DB (pre = 11/09 contro grezzo, post = copia 11/09 contro pubblicato)")
    ap.add_argument("--salva-impronta", default=None, help="scrive le somme per lega in un file JSON")
    ap.add_argument("--confronta-impronta", default=None, help="confronta con un'impronta salvata prima")
    args = ap.parse_args(argv)

    if sb is None:
        sys.path.insert(0, os.getcwd())
        from db_client import get_supabase_client
        sb = get_supabase_client()
    numeri = raccogli(sb, soglia=args.soglia, confronto=args.confronto)
    stampa(numeri, out=out)
    imp = impronta(numeri)
    if args.confronta_impronta:
        with open(args.confronta_impronta, "r", encoding="utf-8") as fh:
            prima = json.load(fh)
        stampa_confronto_impronte(confronta_impronte(prima, imp), out=out)
    if args.salva_impronta:
        with open(args.salva_impronta, "w", encoding="utf-8") as fh:
            json.dump(imp, fh, ensure_ascii=True, indent=1)
        print(f"impronta scritta: {args.salva_impronta}", file=out or sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
