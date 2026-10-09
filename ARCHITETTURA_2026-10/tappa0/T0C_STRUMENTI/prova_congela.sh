#!/bin/bash
# T0C - PROVA DEL CONGELAMENTO su un manifesto DI PROVA (mai il manifesto vero).
# Uso (dalla radice del repository; DURATA ~2 min, due replay di Omega base):
#   bash ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/prova_congela.sh <CARTELLA_TEMP> <CAS_GIRO1> <CAS_GIRO2>
# CAS_GIRO1/CAS_GIRO2 = due cassette di `certifica omega 35760084 --scenari base --cassetta ...`.
# ASCII-only.
C=$1; G1=$2; G2=$3
[ -n "$C" ] && [ -f "$G1" ] && [ -f "$G2" ] || { echo "uso: $0 CARTELLA_TEMP CAS_GIRO1 CAS_GIRO2"; exit 2; }
case "$C" in ARCHITETTURA_2026-10/riferimenti_congelati*|*/ARCHITETTURA_2026-10/riferimenti_congelati*) echo "NON sul manifesto vero"; exit 2;; esac
rm -rf "$C"
echo "--- 1. congela SENZA prova di determinismo (atteso: rifiuto, rc 2)"
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari base --congela --congelati "$C" | tail -1; echo "rc=${PIPESTATUS[0]}"
echo "--- 2. congela con --ombra del primo giro (atteso: 0 divergenze, due voci congelate)"
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari base --ombra "$G1" --congela --congelati "$C" | grep "^OMBRA: \|^CONGELATO\|RIFIUTATO"; echo "rc=${PIPESTATUS[0]}"
echo "--- 3. registrazioni e software (solo aggiunta)"
python -m Betfair.stream.backtest.congela aggiungi --tipo registrazione --congelati "$C" _live_raw/35760084/35760084.raw.jsonl _live_raw/35760084/35760084.scores.jsonl registrazioni_banco/35760084/35760084.raw.jsonl.gz; echo "rc=$?"
python -m Betfair.stream.backtest.congela aggiungi --tipo software --congelati "$C" requirements.txt Betfair/stream/backtest/banco_comune.py; echo "rc=$?"
echo "--- 4. la stessa voce di nuovo: niente si ripete"
python -m Betfair.stream.backtest.congela aggiungi --tipo software --congelati "$C" requirements.txt; echo "rc=$?"
echo "--- 5. verifica: tutto integro (atteso rc 0)"
python -m Betfair.stream.backtest.certifica --verifica-congelati --congelati "$C" | tail -1; echo "rc=${PIPESTATUS[0]}"
echo "--- 6. secondo congelamento dello stesso comando (atteso: rifiuto, solo aggiunta)"
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari base --ombra "$G1" --congela --congelati "$C" | grep -c "CONGELAMENTO RIFIUTATO"; echo "rc=${PIPESTATUS[0]}"
CAS=$(ls "$C"/cassette/*.jsonl.gz)
cp "$CAS" "$C/salva.gz"
python - "$CAS" <<'PY'
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read()); b[100] ^= 1; open(p, "wb").write(bytes(b))
PY
echo "--- 7. un byte della cassetta congelata cambiato: verifica rossa (atteso rc 1)"
python -m Betfair.stream.backtest.certifica --verifica-congelati --congelati "$C" | grep "KO\|^ESITO"; echo "rc=${PIPESTATUS[0]}"
echo "--- 8. ombra contro la cassetta ritoccata (atteso: sigillo rotto, rc 1)"
python -m Betfair.stream.backtest.ombra "$CAS" "$G2" | grep "SIGILLO\|^OMBRA: [DS0]"; echo "rc=${PIPESTATUS[0]}"
cp "$C/salva.gz" "$CAS"; rm -f "$C/salva.gz"
echo "--- 8b. ripristinata: ombra contro il giro 2 (atteso rc 0)"
python -m Betfair.stream.backtest.ombra "$CAS" "$G2" | tail -1; echo "rc=${PIPESTATUS[0]}"
cp "$C/MANIFEST.json" "$C/salva.json"
python - "$C/MANIFEST.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p)); m["voci"][2]["comando"] = "ritoccato"; json.dump(m, open(p, "w"), indent=1)
PY
echo "--- 9. voce del manifesto ritoccata a mano: catena rotta (atteso rc 1)"
python -m Betfair.stream.backtest.certifica --verifica-congelati --congelati "$C" | grep "KO\|^ESITO"; echo "rc=${PIPESTATUS[0]}"
cp "$C/salva.json" "$C/MANIFEST.json"; rm -f "$C/salva.json"
echo "--- 10. ripristinato: verifica di nuovo verde (atteso rc 0)"
python -m Betfair.stream.backtest.certifica --verifica-congelati --congelati "$C" | tail -1; echo "rc=${PIPESTATUS[0]}"
