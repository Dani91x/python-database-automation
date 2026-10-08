#!/bin/bash
# replay DOPO (worktree con le modifiche W3b): 5 scenari di riferimento + 2 nuovi
WT=/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd
OUT=$WT/AUDIT_2026-10-08/W3B
cd "$WT" || exit 1
rm -f "$OUT/dopo_exit.txt"
for ev in 35797769 35760084; do
  t0=$(date +%s)
  python3 -m Betfair.stream.backtest.certifica scalper_calcio "$ev" \
    --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper,ordine-esterno,ordine-esterno-altro-mercato \
    --worker 1 > "$OUT/dopo_$ev.txt" 2> /tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w3b_prove/dopo_$ev.err
  rc=$?
  t1=$(date +%s)
  echo "exit $ev $rc parete_s $((t1 - t0))" >> "$OUT/dopo_exit.txt"
done
