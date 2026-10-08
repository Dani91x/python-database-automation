#!/bin/bash
# uso: lancia.sh <albero> <etichetta> <evento:scenari> [<evento:scenari> ...]
# Replay di Omega uno alla volta, --worker 1, tempo misurato.
ALBERO="$1"; shift
ETI="$1"; shift
S=/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/c7
DATI=/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw
mkdir -p "$S/out"
cd "$ALBERO" || exit 1
for coppia in "$@"; do
  ev="${coppia%%:*}"; sc="${coppia#*:}"
  nome="${ETI}_${ev}_${sc//,/+}"
  inizio=$(date +%s)
  python3 -m Betfair.stream.backtest.certifica omega "$ev" --data-dir "$DATI" \
      --scenari "$sc" --worker 1 > "$S/out/$nome.txt" 2> "$S/out/$nome.err"
  rc=$?
  fine=$(date +%s)
  echo "$nome rc=$rc secondi=$((fine-inizio)) carico=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$S/out/tempi.log"
done
