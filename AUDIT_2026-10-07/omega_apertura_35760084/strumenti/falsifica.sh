#!/bin/bash
# falsificazione della correzione del 07/10: ogni mutazione, test, ripristino dalla copia
W=/home/user/python-database-automation/.claude/worktrees/agent-aadcd5199a17dae8b
SP=/tmp/claude-0/-home-user-python-database-automation/b81252ef-134e-5437-9162-d213fe1a02bc/scratchpad
cd $W || exit 1
for m in M1 M2 M3 M4 M5 M6 M7; do
  python3 $SP/muta.py $m
  timeout 300 python3 -m pytest Betfair/omega/tests/test_flusso_ht_secondo_tempo_2026_10_07.py -q -p no:cacheprovider 2>&1 | tail -1
  cp $SP/omega_service_corretto.py Betfair/omega/omega_service.py
done
echo "MUTAZIONE rimaste: $(grep -c MUTAZIONE Betfair/omega/omega_service.py)"
cmp $SP/omega_service_corretto.py Betfair/omega/omega_service.py && echo RIPRISTINATO
