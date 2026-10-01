#!/bin/bash
# Prova di parita' col guscio SPENTO: l'app di master e il ramo, con la STESSA
# anteprima popolata, scattati uno dopo l'altro; poi confronto pixel per pixel.
# Uso, dalla radice del repo: bash AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/prova_off_master.sh <pagine> [larghezze]
set -e
RADICE=$(pwd); QUI=$RADICE/AUDIT_2026-10-01/REDESIGN/confronto2/strumenti
M=${MASTER_DIR:-/tmp/claude-0/master_fe}
PAG=$1; LARG=${2:-1280,1600}
if [ ! -d $M/frontend/src ]; then
  mkdir -p $M; git archive origin/master frontend | tar -x -C $M
  ln -s $RADICE/frontend/node_modules $M/frontend/node_modules
fi
# l'anteprima (finti e strumenti) e' la stessa del ramo: si copia, non si tocca master
rm -rf $M/frontend/src/anteprima; cp -r $RADICE/frontend/src/anteprima $M/frontend/src/anteprima
mkdir -p $M/AUDIT_2026-10-01/REDESIGN/confronto2; rm -rf $M/AUDIT_2026-10-01/REDESIGN/confronto2/strumenti
cp -r $QUI $M/AUDIT_2026-10-01/REDESIGN/confronto2/strumenti
avvia() { (cd $1 && PORTA=$2 node AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/server.mjs > /tmp/claude-0/server_$2.log 2>&1 &); until curl -s -o /dev/null http://127.0.0.1:$2/; do sleep 1; done; }
curl -s -o /dev/null http://127.0.0.1:5197/ || avvia $M 5197
curl -s -o /dev/null http://127.0.0.1:5198/ || avvia $RADICE 5198
rm -rf /tmp/claude-0/off_master /tmp/claude-0/off_ramo
PORTA=5197 node $QUI/scatta.mjs /tmp/claude-0/off_master $PAG $LARG off 1 > /dev/null
PORTA=5198 node $QUI/scatta.mjs /tmp/claude-0/off_ramo $PAG $LARG off 1 > /dev/null
python3 $QUI/confronta_png.py /tmp/claude-0/off_master /tmp/claude-0/off_ramo 2>/dev/null
