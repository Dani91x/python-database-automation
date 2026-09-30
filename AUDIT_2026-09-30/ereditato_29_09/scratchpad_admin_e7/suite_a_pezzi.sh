#!/bin/sh
# Suite Python intera, un pezzo alla volta (un processo per cartella: la
# memoria si libera fra un pezzo e l'altro). Alla fine confronta la somma dei
# test eseguiti col totale raccolto su tutta la cartella Betfair/.
M="/c/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation"
PY="$M/.venv/Scripts/python.exe"
SP="/c/Users/Admin/AppData/Local/Temp/claude/C--Users-Admin/718cbcd2-a29d-44dc-b459-c4590da8e624/scratchpad"
OUT="$SP/suite_a_pezzi"
mkdir -p "$OUT"
cd "$M" || exit 1
echo "codice $(git log --oneline -1 | cut -c1-7)  inizio $(date +%H:%M)"

"$PY" -m pytest Betfair/ -q -p no:cacheprovider --collect-only > "$OUT/raccolta.txt" 2>&1
grep -a -E "tests? collected|error" "$OUT/raccolta.txt" | tail -2

# pezzi: ogni sottocartella di Betfair/ e di Betfair/stream/ che contiene test
PEZZI=$(grep -a "::" "$OUT/raccolta.txt" | sed 's/::.*//' | awk -F/ '{ if ($2=="stream") print $1"/"$2"/"$3; else if (NF>2) print $1"/"$2; else print $0 }' | sort -u)
TOT_OK=0; TOT_KO=0
for p in $PEZZI; do
  n=$(echo "$p" | tr '/.' '__')
  "$PY" -m pytest "$p" -q -p no:cacheprovider > "$OUT/$n.txt" 2>&1
  coda=$(grep -a -E "passed|failed|error|no tests ran" "$OUT/$n.txt" | tail -1)
  ok=$(echo "$coda" | sed -n 's/.*[^0-9]\([0-9][0-9]*\) passed.*/\1/p'); [ -z "$ok" ] && ok=$(echo "$coda" | sed -n 's/^\([0-9][0-9]*\) passed.*/\1/p')
  ko=$(echo "$coda" | sed -n 's/.*[^0-9]\([0-9][0-9]*\) failed.*/\1/p'); [ -z "$ko" ] && ko=$(echo "$coda" | sed -n 's/^\([0-9][0-9]*\) failed.*/\1/p')
  TOT_OK=$((TOT_OK + ${ok:-0})); TOT_KO=$((TOT_KO + ${ko:-0}))
  echo "$(date +%H:%M) $p: $coda"
done
echo "TOTALE passati $TOT_OK, falliti $TOT_KO  fine $(date +%H:%M)"
grep -a -h "^FAILED\|^ERROR" "$OUT"/*.txt | head -20
