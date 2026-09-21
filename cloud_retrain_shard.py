"""
cloud_retrain_shard.py — wrapper di sharding per il retrain cloud (GitHub Actions).

Divide le leghe in N shard deterministici (round-robin sugli ID ordinati, così le
leghe grandi e piccole si distribuiscono uniformemente tra i job della matrix) e
delega ogni shard a retrain_all_leagues.py, che gestisce training, gate BSS e
upload su Supabase storage + ai_model_registry.

Uso (dentro il workflow .github/workflows/retrain_models.yml):
    python cloud_retrain_shard.py --shard-index 0 --total-shards 4
    python cloud_retrain_shard.py --shard-index 0 --total-shards 1 --leagues 135,39

Il PC locale scarica automaticamente i modelli nuovi al primo predict_fixture
dopo la scadenza della cache (24h) — nessuna azione manuale richiesta.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import retrain_all_leagues as ral

# -- Ritentativi di fine shard ---------------------------------------------
# Una lega che fallisce (tipicamente per un timeout di lettura sul DB) non deve
# far cadere lo shard senza appello: si riprovano le leghe fallite ALLA FINE,
# quando il resto e' gia' addestrato e il DB ha respirato. L'exit code resta
# !=0 se una lega ritentata non risulta COMPLETATA (per errore o perche' non e'
# stata nemmeno avviata): una lega e' recuperata solo con prova positiva.
_RETRY_ROUNDS_DEFAULT = 2
_RETRY_PAUSE_S = 60.0        # pausa prima di ogni giro di ritentativi
_RETRY_MIN_BUDGET_MIN = 2.0  # sotto questo residuo non si riparte
_RETRY_HARD_CAP_MIN = 300.0  # tetto assoluto (vale anche con --time-budget-min 0)
_PROBE_TIMEOUT_S = 25.0      # come il pre-flight di retrain_models.yml
_PROBE_SOGLIA_S = 12.0

# Marcatori stampati da retrain_all_leagues.py:
#   "  [ERROR] league 71: <errore>"                     (subito, per-lega)
#   "  Leghe con errore (2):" + "    - League 71: ..."  (riepilogo finale)
#   "  BSS comparison - league 71:"                     (PROVA POSITIVA: la lega
#        ha prodotto modelli; stampata solo da print_bss_comparison con status ok)
#   "  Completato in 12.0s | 18 modelli"                (senza league_id: usabile
#        solo quando la passata ha UNA sola lega richiesta)
#   "  Stop budget:    3 (non avviate, ...)"            (leghe mai partite)
#   "  Log salvato in: ..." / "  NOTA:"                 (fine del riepilogo)
_RE_ERR_INLINE = re.compile(r"\[ERROR\]\s+league\s+(\d+)\s*:", re.IGNORECASE)
_RE_ERR_HEADER = re.compile(r"Leghe con errore\s*\(\d+\)", re.IGNORECASE)
_RE_ERR_ROW = re.compile(r"^\s*-\s*League\s+(\d+)\s*:", re.IGNORECASE)
_RE_ERR_FINE_BLOCCO = re.compile(r"(Log salvato in:|NOTA:|BSS FLEET DASHBOARD|RIEPILOGO FINALE)")
_RE_OK_BSS = re.compile(r"BSS comparison.*?league\s+(\d+)", re.IGNORECASE)
_RE_OK_COMPLETATO = re.compile(r"Completato in\s+[\d.]+s\s*\|\s*(\d+)\s+modelli", re.IGNORECASE)
_RE_TIMEBUDGET = re.compile(r"Stop budget:\s*(\d+)")


def _db_probe_lenta(timeout_s: float = _PROBE_TIMEOUT_S,
                    soglia_s: float = _PROBE_SOGLIA_S) -> bool:
    """Pre-flight come quello del workflow: True se il DB e' lento o muto.

    Il ritentativo parte DOPO il pre-flight del job, quindi il DB potrebbe
    essersi degradato nel frattempo: si ricontrolla prima di ogni giro per non
    insistere su un'istanza gia' in affanno. Una sola SELECT da una riga.
    """
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("[SHARD] Probe DB: credenziali assenti, non ritento.")
        return True
    req = urllib.request.Request(
        url + "/rest/v1/ai_model_registry?select=id&limit=1",
        headers={"apikey": key, "Authorization": "Bearer " + key},
    )
    t0 = time.time()
    try:
        urllib.request.urlopen(req, timeout=timeout_s).read()
    except Exception as exc:
        print(f"[SHARD] Probe DB: non reattivo ({exc!r}), non ritento.")
        return True
    dt = time.time() - t0
    print(f"[SHARD] Probe DB: ok in {dt:.1f}s")
    if dt > soglia_s:
        print(f"[SHARD] Probe DB: lento (>{soglia_s:.0f}s), non ritento per non stressarlo.")
        return True
    return False


def _run_training(cmd: list, leghe_richieste: list) -> tuple:
    """Lancia retrain_all_leagues.py mostrando l'output riga per riga.

    Ritorna ``(exit_code, leghe_fallite, leghe_completate, non_avviate_per_budget)``.
    L'output del figlio viene ristampato identico (i log dell'Action non
    cambiano): qui lo si legge solo per sapere quali leghe sono fallite e quali
    hanno PROVA POSITIVA di completamento. Niente prova = non completata: una
    lega saltata o mai avviata non deve passare per "recuperata".
    """
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")

    failed: list = []
    completate: list = []
    timebudget = 0
    in_error_block = False
    lega_unica = leghe_richieste[0] if len(leghe_richieste) == 1 else None

    def _aggiungi(elenco: list, lid: int) -> None:
        if lid not in elenco:
            elenco.append(lid)

    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        print(line)
        sys.stdout.flush()

        m = _RE_ERR_INLINE.search(line)
        if m:
            _aggiungi(failed, int(m.group(1)))
        m = _RE_OK_BSS.search(line)
        if m:
            _aggiungi(completate, int(m.group(1)))
        elif lega_unica is not None:
            m = _RE_OK_COMPLETATO.search(line)
            if m and int(m.group(1)) > 0:
                _aggiungi(completate, lega_unica)
        m = _RE_TIMEBUDGET.search(line)
        if m:
            timebudget = int(m.group(1))

        # Blocco "Leghe con errore": un errore puo' occupare piu' righe, quindi
        # il blocco si chiude solo su un marcatore di fine riepilogo (o a fine
        # output), mai alla prima riga che non e' "- League <id>:".
        if _RE_ERR_HEADER.search(line):
            in_error_block = True
            continue
        if in_error_block:
            m = _RE_ERR_ROW.match(line)
            if m:
                _aggiungi(failed, int(m.group(1)))
            elif _RE_ERR_FINE_BLOCCO.search(line):
                in_error_block = False

    rc = proc.wait()
    # Una lega con errore non e' completata, qualunque cosa sia stato stampato.
    completate = [lid for lid in completate if lid not in failed]
    return rc, failed, completate, timebudget


def main() -> int:
    parser = argparse.ArgumentParser(description="Shard deterministico per il retrain cloud.")
    parser.add_argument("--shard-index", type=int, required=True, help="Indice shard (0-based).")
    parser.add_argument("--total-shards", type=int, required=True, help="Numero totale di shard.")
    parser.add_argument(
        "--leagues",
        default="",
        help="Override: lista esplicita di league_id (csv). Vuoto = tutte le leghe dal DB.",
    )
    parser.add_argument("--last-n-seasons", type=int, default=3)
    parser.add_argument(
        "--skip-existing",
        default="true",
        choices=["true", "false"],
        help="Salta le leghe riaddestrate negli ultimi --max-age-days giorni.",
    )
    parser.add_argument("--max-age-days", type=int, default=7)
    parser.add_argument("--parallel-leagues", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true", help="Mostra cosa verrebbe addestrato senza addestrare.")
    parser.add_argument(
        "--use-planner",
        default="false",
        choices=["true", "false"],
        help=(
            "true = il planner sceglie le leghe (mancanti + stale<cutoff) in 2 query "
            "bulk, gentile sull'I/O; ignora --skip-existing/--max-age-days. "
            "Default false = comportamento storico (tutte le leghe del DB + skip per-lega)."
        ),
    )
    parser.add_argument(
        "--time-budget-min",
        type=float,
        default=0.0,
        help="Minuti dopo i quali non si avviano nuove leghe (stop sotto le 3h). 0 = illimitato.",
    )
    parser.add_argument(
        "--retry-failed-rounds",
        type=int,
        default=_RETRY_ROUNDS_DEFAULT,
        help=(
            "Giri di ritentativo, a fine shard, sulle leghe fallite (dentro il "
            "time-budget residuo). 0 = nessun ritentativo."
        ),
    )
    args = parser.parse_args()

    if not (0 <= args.shard_index < args.total_shards):
        print(f"[ERROR] shard-index {args.shard_index} fuori range per total-shards {args.total_shards}")
        return 2

    # Parità di serving: il meta-learner DEVE restare LogReg ovunque. Se qualcuno
    # aggiunge tensorflow all'ambiente cloud, i modelli LARGE userebbero il meta MLP
    # e il PC di serving potrebbe non caricarlo identico — segnala subito.
    try:
        import tensorflow  # noqa: F401
        print("[WARN] tensorflow PRESENTE nell'ambiente di training: il meta-learner "
              "MLP verra' usato sui tier LARGE. Verifica la parita' col PC di serving!")
    except ImportError:
        print("[OK] tensorflow assente: meta-learner LogReg (parita' di serving garantita).")

    planner_mode = False
    if args.leagues.strip():
        tokens = [x.strip() for x in args.leagues.split(",") if x.strip()]
        bad = [t for t in tokens if not t.isdigit()]
        if bad:
            print(f"[ERROR] league_id non numerici nell'input --leagues: {bad}")
            return 2
        all_ids = sorted({int(t) for t in tokens})
        print(f"[SHARD] Override manuale: {len(all_ids)} leghe da input")
    elif args.use_planner == "true":
        # Selezione gentile: 2 query bulk, niente skip per-lega. Ordine
        # missing-first/oldest-first PRESERVATO (non ri-ordinare).
        import training_planner
        plan = training_planner.select_leagues_to_train()
        all_ids = list(plan["todo"])
        planner_mode = True
        print(
            f"[PLANNER] universe={plan['universe']} | da_fare={len(all_ids)} "
            f"(missing={len(plan['missing'])}, stale={len(plan['stale'])}) | "
            f"gia_fresche={plan['fresh_count']} | cutoff={plan['cutoff']}"
        )
        if not all_ids:
            print("[PLANNER] Niente da fare: tutte le leghe sono fresche. Esco con successo.")
            return 0
    else:
        all_ids = sorted(set(ral._get_all_league_ids_from_db()))
        print(f"[SHARD] Leghe dal DB (season_backfill_state): {len(all_ids)}")

    # Sharding round-robin (preserva l'ordine d'ingresso: in planner_mode tiene
    # la priorita' missing-first/oldest-first).
    shard_ids = [lid for i, lid in enumerate(all_ids) if i % args.total_shards == args.shard_index]
    print(f"[SHARD] Shard {args.shard_index + 1}/{args.total_shards}: {len(shard_ids)} leghe -> {shard_ids[:50]}{' ...' if len(shard_ids) > 50 else ''}")

    if not shard_ids:
        print("[SHARD] Nessuna lega in questo shard, esco con successo.")
        return 0

    base_cmd = [
        sys.executable,
        os.path.join(ROOT, "retrain_all_leagues.py"),
        "--last-n-seasons", str(args.last_n_seasons),
        "--parallel-leagues", str(args.parallel_leagues),
        "--source", "db",
    ]
    if args.dry_run:
        base_cmd += ["--dry-run"]
    # In planner_mode la selezione e' gia' fatta: niente skip per-lega (zero
    # query extra). Fuori dal planner si mantiene lo skip storico.
    primo_cmd = list(base_cmd)
    if not planner_mode and args.skip_existing == "true":
        primo_cmd += ["--skip-existing", "--max-age-days", str(args.max_age_days)]

    # Time-budget: e' dello SHARD, non del singolo lancio. I ritentativi girano
    # dentro il budget residuo, cosi' il tetto (e il timeout del workflow) resta
    # quello di prima.
    started = time.time()
    budget_s = args.time_budget_min * 60.0 if args.time_budget_min and args.time_budget_min > 0 else 0.0

    def _trascorsi_min() -> float:
        return (time.time() - started) / 60.0

    def _remaining_min() -> float:
        if budget_s <= 0:
            return 0.0  # 0 = illimitato, come l'argomento originale
        return (budget_s - (time.time() - started)) / 60.0

    def _cmd_for(leagues: list, base: list) -> list:
        cmd = list(base) + ["--leagues", ",".join(map(str, leagues))]
        if budget_s > 0:
            # Mai sotto la soglia: un figlio con budget ~0 non avvierebbe nulla.
            cmd += ["--time-budget-min", f"{max(_remaining_min(), _RETRY_MIN_BUDGET_MIN):.1f}"]
        return cmd

    cmd = _cmd_for(shard_ids, primo_cmd)
    print(f"[SHARD] Lancio: {' '.join(cmd)}")
    sys.stdout.flush()
    rc, failed, _completate, timebudget = _run_training(cmd, shard_ids)

    if not failed:
        if rc != 0:
            print(f"[SHARD] Uscita {rc} senza leghe in errore riconosciute: "
                  f"fallimento NON di lega (vedi log sopra).")
        return rc

    print(f"\n[SHARD] Leghe fallite al primo giro ({len(failed)}): {failed}")
    if args.dry_run:
        print("[SHARD] --dry-run: nessun ritentativo.")
        return rc

    rounds = max(0, args.retry_failed_rounds)
    remaining = list(failed)
    # Causa per ogni lega ancora da sistemare: serve nell'elenco finale.
    causa = {lid: "errore nel training" for lid in remaining}
    for giro in range(1, rounds + 1):
        if not remaining:
            break
        if budget_s > 0 and _remaining_min() < _RETRY_MIN_BUDGET_MIN:
            print(f"[SHARD] Time-budget esaurito ({_remaining_min():.1f} min): "
                  f"NIENTE ritentativo per {remaining}.")
            break
        if _trascorsi_min() > _RETRY_HARD_CAP_MIN:
            print(f"[SHARD] Tetto assoluto di {_RETRY_HARD_CAP_MIN:.0f} min superato "
                  f"({_trascorsi_min():.0f} min): NIENTE ritentativo per {remaining}.")
            break
        if _db_probe_lenta():
            print(f"[SHARD] Ritentativo {giro} saltato: DB non pronto. "
                  f"Restano {remaining}.")
            break
        print(f"[SHARD] Ritentativo {giro}/{rounds} su {len(remaining)} leghe "
              f"dopo {_RETRY_PAUSE_S:.0f}s di pausa: {remaining}")
        sys.stdout.flush()
        time.sleep(_RETRY_PAUSE_S)
        # Nel ritentativo MAI --skip-existing: la lega da ritentare non e' stata
        # addestrata, e una lega salvata a meta' verrebbe "saltata" e scambiata
        # per recuperata.
        cmd = _cmd_for(remaining, base_cmd)
        print(f"[SHARD] Lancio ritentativo: {' '.join(cmd)}")
        sys.stdout.flush()
        rc, ancora_fallite, completate, timebudget = _run_training(cmd, remaining)
        if timebudget:
            print(f"[SHARD] ATTENZIONE: {timebudget} lega/leghe NON avviate per "
                  f"time-budget durante il ritentativo {giro}.")
        # Recuperata SOLO con prova positiva di completamento.
        recuperate = [lid for lid in remaining if lid in completate]
        if recuperate:
            print(f"[SHARD] Recuperate al ritentativo {giro}: {recuperate}")
        remaining = [lid for lid in remaining if lid not in completate]
        for lid in remaining:
            causa[lid] = ("errore nel training" if lid in ancora_fallite
                          else "non completata (non avviata o senza modelli)")
        if remaining:
            print(f"[SHARD] Ancora da sistemare dopo il ritentativo {giro}: "
                  f"{[(lid, causa[lid]) for lid in remaining]}")

    if remaining:
        print(f"\n[SHARD] ERRORE: {len(remaining)} lega/leghe NON completate dopo "
              f"{rounds} ritentativi:")
        for lid in remaining:
            print(f"    - League {lid}: {causa[lid]}")
        return 1

    print("\n[SHARD] Tutte le leghe fallite sono state completate dai ritentativi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
