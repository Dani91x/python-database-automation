#!/bin/bash
# Replay degli altri bot del calcio che usano il motore degli ordini condiviso
# (Omega e le tre Safe), scenari rapidi sui due trasporti, uno dopo l'altro.
# uso: replay_altri_bot.sh <worktree> <cartella di uscita> <etichetta>
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
echo "$(git hash-object Betfair/stream/motore_ordini.py) Betfair/stream/motore_ordini.py" > "$OUT/hash_motore_$ET.txt"
for b in omega safe_base safe_esatto safe_punta; do
  f="$OUT/${b}_$ET.txt"
  date +"$b inizio %H:%M:%S"
  "$PY" -m Betfair.stream.backtest.certifica "$b" 35760084 --scenari rapidi --trasporto entrambi \
    --worker 0 --data-dir "$M/_live_raw" > "$f" 2>&1
  echo "$b: uscita $? | OK=$(grep -a -c '^OK' "$f") KO=$(grep -a -c '^KO' "$f")"
  grep -aE "ESITO|violazioni totali|TEMPO TOTALE|PARITA" "$f" | cut -c1-170
done
date +"fine %H:%M:%S"
