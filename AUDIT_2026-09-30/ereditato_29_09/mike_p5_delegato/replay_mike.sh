#!/bin/sh
# Replay di Mike per P5 (ambiente neutro di giro_completo.sh, par. 6.9).
# Uso: sh replay_mike.sh <worktree> <nome> <scenari> <trasporto>
M="/c/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation"
PY="$M/.venv/Scripts/python.exe"
WT="$1"; NOME="$2"; SCEN="$3"; TRA="$4"; EVENTO="${5:-35760084}"
OUT="$WT/AUDIT_2026-09-29/mike_p5"
export SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
export LIVE_ORDER_MODE=LIVE LIVE_KILL_SWITCH=false LIVE_RECONCILE_POLL_SEC=5
export SAFE_PRE_KO_OU_HOURS=1 MIKE_LIVE_ENABLED=1
export LIVE_MARKET_TYPES=MATCH_ODDS,CORRECT_SCORE,HALF_TIME_SCORE
for v in SAFE_SCAN_CANALE MIKE_CANALE_POSIZIONI OMEGA_CANALE_POSIZIONI SAFE_CANALE_POSIZIONI \
  TENNIS_BOT_CANALE SAFE_BOT_LEGGE_CANALE SAFE_BOT_SVEGLIA_CANALE OMEGA_SVEGLIA_CANALE \
  MIKE_SVEGLIA_CANALE TENNIS_BOT_SVEGLIA_CANALE MIKE_LEGGE_CANALE OMEGA_LEGGE_CANALE \
  PUNTEGGI_CANALE ESITI_ORDINI_CANALE MOTORE_ORDINI_CANALE SCALPER_CANALE \
  SAFE_ORDINI_VIA_CANALE OMEGA_ORDINI_VIA_CANALE MOTORE_ORDINI_CANALE_TENNIS \
  SAFE_TENNIS_ORDINI_VIA_CANALE; do export $v=0; done
cd "$WT" || exit 1
f="$OUT/replay_${NOME}.txt"
echo "codice $(git log --oneline -1 | cut -c1-7) + P5 blocco (non committato)  inizio $(date +%H:%M:%S)" > "$f"
t0=$(date +%s)
"$PY" -m Betfair.stream.backtest.certifica mike $EVENTO --scenari "$SCEN" --trasporto "$TRA" --worker 0 --data-dir "$M/_live_raw" >> "$f" 2>&1
rc=$?
echo "TEMPO_S $(( $(date +%s) - t0 )) RC $rc" >> "$f"
echo "fine" >> "$f"
