#!/bin/bash
# confronto dei referti prima/dopo, tolte le righe dei tempi
S=/tmp/claude-0/-home-user-python-database-automation/b81252ef-134e-5437-9162-d213fe1a02bc/scratchpad/replay_pro
F='secondi|tick/s|LENTO|codice bot| [0-9.]+ s\b|durata|tempi'
for b in "$@"; do
  echo "== $b"
  diff <(grep -Ev "$F" $S/ref_prima_$b.txt | sed -E "s/[0-9]{15,}/ID/g") <(grep -Ev "$F" $S/ref_dopo_$b.txt | sed -E "s/[0-9]{15,}/ID/g") && echo "IDENTICI (tolte le righe dei tempi)"
done
