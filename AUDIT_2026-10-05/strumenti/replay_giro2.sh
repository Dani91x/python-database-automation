#!/bin/bash
# I replay del giro 2, UNO alla volta (--worker 1), referti in AUDIT_2026-10-05/replay/giro2/
cd "$(dirname "$0")/../.."
OUT=AUDIT_2026-10-05/replay/giro2
mkdir -p $OUT
corri() {  # nome evento scenari
  local nome=$1 ev=$2 sc=$3
  echo "== $(date +%H:%M:%S) $nome $ev $sc"
  local t0=$SECONDS
  python -m Betfair.stream.backtest.certifica scalper_calcio $ev --scenari $sc --worker 1 > $OUT/$nome.txt 2>&1
  echo "tempo totale $((SECONDS - t0)) s" >> $OUT/$nome.txt
  grep -E "^(OK|KO|NE) " $OUT/$nome.txt
  tail -1 $OUT/$nome.txt
}
# 1. non regressione (stessi gruppi del revisore)
corri nr_A1 35797769 base,auto-live,paper,bot-fermo,kill-switch
corri nr_A2 35797769 senza-missione,esiti-ignoti,rifiuti-betfair,riavvio,chiusura-abbinata-in-parte
corri nr_B1 35797769 sniper,sniper-paper
corri nr_B2 35797769 sniper-uscite-auto,uscite-manuali
corri nr_B3 35797769 uscite-manuali-firmate
corri nr_C 35760084 base,paper
# 2. i tre scenari della modalita' su entrambe le registrazioni
corri media_35797769 35797769 media-under,media-under-paper,media-under-35
corri media_35760084 35760084 media-under,media-under-paper,media-under-35
# 3. parametri diversi
corri varianti_35797769 35797769 media-under-obiettivo-030,media-under-rientri-1,media-under-rischio-30,media-under-tick-1
corri varianti_35760084 35760084 media-under-obiettivo-030,media-under-rientri-1,media-under-rischio-30,media-under-tick-1
# 4. guasti con la modalita' accesa
corri guasti_35797769 35797769 media-under-riavvio,media-under-rifiuti-betfair,media-under-esiti-ignoti,media-under-kill-switch,media-under-bot-fermo
corri guasti_35760084 35760084 media-under-riavvio,media-under-rifiuti-betfair,media-under-esiti-ignoti,media-under-kill-switch,media-under-bot-fermo
echo "== FINE $(date +%H:%M:%S)"
