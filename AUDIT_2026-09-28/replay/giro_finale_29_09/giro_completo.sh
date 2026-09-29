#!/bin/sh
# Giro completo di certificazione sul codice finale di master: un bot dopo
# l'altro, ambiente neutro, referti in scratchpad/replay/giro_finale/.
# Uso: sh giro_completo.sh <worktree> <file di attesa facoltativo>
SP="/c/Users/Admin/AppData/Local/Temp/claude/C--Users-Admin/718cbcd2-a29d-44dc-b459-c4590da8e624/scratchpad"
M="/c/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation"
PY="$M/.venv/Scripts/python.exe"
WT="$1"
ATTESA="$2"
CALCIO="$M/_live_raw"
TENNIS="C:/Users/Admin/Desktop/tennis_rec/20260707"
OUT="$SP/replay/giro_finale"
mkdir -p "$OUT"

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

if [ -n "$ATTESA" ]; then
  until grep -q "^fine" "$ATTESA" 2>/dev/null; do sleep 15; done
fi

cd "$WT" || exit 1
COD=$(git log --oneline -1 | cut -c1-7)

gira() {
  nome="$1"; shift
  f="$OUT/${nome}_${COD}.txt"
  echo "codice $COD  inizio $(date +%H:%M:%S)" > "$f"
  t0=$(date +%s)
  "$PY" -m Betfair.stream.backtest.certifica "$@" --worker 0 >> "$f" 2>&1
  rc=$?
  t1=$(date +%s)
  echo "TEMPO_S $((t1-t0)) RC $rc" >> "$f"
  ok=$(grep -a -c "^OK" "$f"); ko=$(grep -a -c "^KO" "$f")
  az=$(grep -a "^OK\|^KO" "$f" | sed 's/.*azioni= *\([0-9]*\).*/\1/' | sort -n | tail -1)
  par=$(grep -a -i -c "PARITA.*RAGGIUNTA" "$f")
  echo "$(date +%H:%M) $nome: OK=$ok KO=$ko azioni_max=$az parita_raggiunta=$par tempo=$((t1-t0))s rc=$rc"
  grep -a -E "^ +[A-Z]+[0-9]+ x[0-9]+:|LENTO" "$f" | cut -c1-200 | head -6
}

gira omega          omega       35760084 --scenari rapidi --trasporto entrambi --data-dir "$CALCIO"
gira safe_base      safe_base   35760084 --scenari rapidi --trasporto entrambi --data-dir "$CALCIO"
gira safe_esatto    safe_esatto 35760084 --scenari rapidi --trasporto entrambi --data-dir "$CALCIO"
gira safe_punta     safe_punta  35760084 --scenari rapidi --trasporto entrambi --data-dir "$CALCIO"
gira safe_tennis    safe_tennis 35795993 --scenari rapidi --trasporto entrambi --data-dir "$TENNIS"
for ev in 35794049 35795993; do
  for b in tennis_pro tennis_flb tennis_swing tennis_scalper; do
    gira "${b}_${ev}" "$b" "$ev" --scenari base,live,gate-aperto,parziali,uscite-manuali,uscite-manuali-firmate --data-dir "$TENNIS"
  done
done
gira mike_coperture mike 35760084 --scenari copertura-rifiutata --trasporto entrambi --data-dir "$CALCIO"
gira mike_tutti     mike 35760084 --scenari tutti --trasporto canale --data-dir "$CALCIO"
echo "GIRO FINITO $(date +%H:%M)"
