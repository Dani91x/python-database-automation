#!/bin/bash
# Immagini di consegna di UNA pagina (server.mjs acceso sulla 5198):
#   confronto2/<pagina>.<off|v2>.<1280|1600>.png   (schermata, tavolozza 256)
#   confronto2/<pagina>.affianco.png                (prototipo | v2, pagina intera)
# Uso, dalla radice del repo: bash .../consegna_pagina.sh <pagina> <id-prototipo>
set -e
QUI=$(cd "$(dirname "$0")" && pwd); C2=$(dirname $QUI); T=/tmp/claude-0/consegna_$1
rm -rf $T; mkdir -p $T
node $QUI/scatta.mjs $T $1 1280,1600 off,v2 0 > /dev/null
node $QUI/scatta.mjs $T/intera $1 1600 v2 1 > /dev/null
mkdir -p $T/proto; node $QUI/scatta_prototipo.mjs $T/proto $2 1600 1
python3 - $T $C2 $1 <<'PY'
import sys, glob, os
from PIL import Image
T, C2, p = sys.argv[1:]
for f in sorted(glob.glob(f'{T}/{p}.*.png')):
    Image.open(f).convert('RGB').quantize(256).save(os.path.join(C2, os.path.basename(f)), optimize=True)
    print(os.path.join(C2, os.path.basename(f)))
PY
python3 $QUI/affianca.py $T/proto/$2.1600.png $(ls $T/intera/$1.v2.1600*.png | head -1) $C2/$1.affianco.png
grep -o '"errori":\[[^]]*\]' $T/misure.json | sort | uniq -c
