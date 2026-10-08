#!/bin/bash
# replay DOPO del SECONDO giro (cima 7633e20 + W3b): 5 scenari di riferimento + 5 nuovi
WT=/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd
OUT=$WT/AUDIT_2026-10-08/W3B/giro2
mkdir -p "$OUT"
cd "$WT" || exit 1
rm -f "$OUT/dopo_exit.txt"
for ev in 35797769 35760084; do
  t0=$(date +%s)
  python3 -m Betfair.stream.backtest.certifica scalper_calcio "$ev" \
    --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper,ordine-esterno,ordine-esterno-app,ordine-esterno-di-un-bot,ordine-esterno-db-giu,ordine-esterno-altro-mercato \
    --worker 1 > "$OUT/dopo_$ev.txt" 2> /dev/null
  rc=$?
  t1=$(date +%s)
  echo "exit $ev $rc parete_s $((t1 - t0))" >> "$OUT/dopo_exit.txt"
done
