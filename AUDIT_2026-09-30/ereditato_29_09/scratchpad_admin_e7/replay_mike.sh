#!/bin/bash
# Replay di Mike dal worktree indicato: scenari tutti sul canale, poi coperture sui due trasporti.
# uso: replay_mike.sh <worktree> <cartella di uscita> <etichetta>
SP="/c/Users/Admin/AppData/Local/Temp/claude/C--Users-Admin/718cbcd2-a29d-44dc-b459-c4590da8e624/scratchpad"
M="/c/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation"
PY="$M/.venv/Scripts/python.exe"
W="$1"; OUT="$2"; ET="$3"
mkdir -p "$OUT"
cd "$W" || exit 2
export SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
export LIVE_ORDER_MODE=LIVE LIVE_KILL_SWITCH=false LIVE_RECONCILE_POLL_SEC=5 SAFE_PRE_KO_OU_HOURS=1
export MIKE_LIVE_ENABLED=1 LIVE_MARKET_TYPES=MATCH_ODDS,CORRECT_SCORE,HALF_TIME_SCORE
for v in SAFE_SCAN_CANALE MIKE_CANALE_POSIZIONI OMEGA_CANALE_POSIZIONI SAFE_CANALE_POSIZIONI \
         TENNIS_BOT_CANALE SAFE_BOT_LEGGE_CANALE SAFE_BOT_SVEGLIA_CANALE OMEGA_SVEGLIA_CANALE \
         MIKE_SVEGLIA_CANALE TENNIS_BOT_SVEGLIA_CANALE MIKE_LEGGE_CANALE OMEGA_LEGGE_CANALE \
         PUNTEGGI_CANALE ESITI_ORDINI_CANALE MOTORE_ORDINI_CANALE SCALPER_CANALE \
         SAFE_ORDINI_VIA_CANALE OMEGA_ORDINI_VIA_CANALE MOTORE_ORDINI_CANALE_TENNIS \
         SAFE_TENNIS_ORDINI_VIA_CANALE; do export $v=0; done
for f in Betfair/mike/engine.py Betfair/mike/service.py Betfair/mike/db.py Betfair/mike/config.py \
         Betfair/mike/certificazione.py Betfair/mike/tools/replay_registrazioni.py; do
  echo "$(git hash-object "$f") $f"
done > "$OUT/hash_$ET.txt"
date +"inizio %H:%M:%S"
"$PY" -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti --trasporto canale \
  --worker 0 --data-dir "$M/_live_raw" > "$OUT/mike_tutti_$ET.txt" 2>&1
echo "tutti: uscita $?"
"$PY" -m Betfair.stream.backtest.certifica mike 35760084 --scenari copertura-rifiutata \
  --trasporto entrambi --worker 0 --data-dir "$M/_live_raw" > "$OUT/mike_coperture_$ET.txt" 2>&1
echo "coperture: uscita $?"
date +"fine %H:%M:%S"
grep -aE "^(OK|KO|!!)|ESITO|violazion|TEMPO TOTALE|LENTO" "$OUT/mike_tutti_$ET.txt" "$OUT/mike_coperture_$ET.txt" | cut -c1-200
