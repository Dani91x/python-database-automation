#!/bin/bash
# I replay del giro 4, UNO alla volta (--worker 1), referti in AUDIT_2026-10-06/replay/giro4/
cd "$(dirname "$0")/../.."
OUT=AUDIT_2026-10-06/replay/giro4
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
# 1. i replay chiesti dall'utente: liquidita' minima 100 (Under 2,5) e 50 (Under 3,5)
corri liquidita_35797769 35797769 media-under-liquidita-100,media-under-35-liquidita-50
corri liquidita_35760084 35760084 media-under-liquidita-100,media-under-35-liquidita-50
# 2. i 12 scenari della modalita' (e gli stessi sulla 35760084)
corri media_35797769 35797769 media-under,media-under-paper,media-under-35
corri varianti_35797769 35797769 media-under-obiettivo-030,media-under-rientri-1,media-under-rischio-30,media-under-tick-1
corri guasti_35797769 35797769 media-under-riavvio,media-under-rifiuti-betfair,media-under-esiti-ignoti,media-under-kill-switch,media-under-bot-fermo
corri media_35760084 35760084 media-under,media-under-paper,media-under-35
# 3. i 15 dello Scalper con la modalita' spenta (+ base,paper sulla 35760084)
corri A1 35797769 base,auto-live,paper,bot-fermo,kill-switch
corri A2 35797769 senza-missione,esiti-ignoti,rifiuti-betfair,riavvio,chiusura-abbinata-in-parte
corri B1 35797769 sniper,sniper-paper
corri B2 35797769 sniper-uscite-auto,uscite-manuali
corri B3 35797769 uscite-manuali-firmate
corri C 35760084 base,paper
echo "== FINE $(date +%H:%M:%S)"
