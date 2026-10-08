#!/bin/bash
# replay PRIMA del secondo giro: copia `git archive` della cima 7633e20
S=/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w3b_prima2
cd "$S" || exit 1
rm -f "$S/prima_exit.txt"
for ev in 35797769 35760084; do
  t0=$(date +%s)
  python3 -m Betfair.stream.backtest.certifica scalper_calcio "$ev" \
    --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper \
    --worker 1 > "$S/prima_$ev.txt" 2> "$S/prima_$ev.err"
  rc=$?
  t1=$(date +%s)
  echo "exit $ev $rc parete_s $((t1 - t0))" >> "$S/prima_exit.txt"
done
