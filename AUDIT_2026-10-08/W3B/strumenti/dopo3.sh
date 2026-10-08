#!/bin/bash
# replay DOPO sulla cima 1ac69d0 (cantiere 9) + W3b: 5 scenari di riferimento, i 4 del
# cantiere 9 e i 5 di W3b
WT=/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd
OUT=$WT/AUDIT_2026-10-08/W3B/giro2_c9
mkdir -p "$OUT"
cd "$WT" || exit 1
rm -f "$OUT/dopo_exit.txt"
for ev in 35797769 35760084; do
  t0=$(date +%s)
  python3 -m Betfair.stream.backtest.certifica scalper_calcio "$ev" \
    --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper,ingresso-abbinato-in-parte,ingresso-abbinato-in-parte-paper,rifiuti-betfair-codici,rifiuti-betfair-codici-paper,ordine-esterno,ordine-esterno-app,ordine-esterno-di-un-bot,ordine-esterno-db-giu,ordine-esterno-altro-mercato \
    --worker 1 > "$OUT/dopo_$ev.txt" 2> "$OUT/dopo_$ev.err"
  rc=$?
  t1=$(date +%s)
  echo "exit $ev $rc parete_s $((t1 - t0))" >> "$OUT/dopo_exit.txt"
done
