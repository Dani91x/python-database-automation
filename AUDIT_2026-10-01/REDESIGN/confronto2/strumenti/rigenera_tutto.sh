#!/bin/bash
# Rigenera TUTTE le immagini di consegna sullo stato finale e fa la prova pixel
# col guscio spento contro master su tutte le pagine. Dalla radice del repo.
Q=AUDIT_2026-10-01/REDESIGN/confronto2/strumenti
while read -r pag proto env; do
  [ -z "$pag" ] && continue
  env $env bash $Q/consegna_pagina.sh $pag $proto 2>&1 | tail -1
done <<'ELENCO'
control-room control-room CANALE_FINTO=1
board board CANALE_FINTO=1
segui-live segui-live CANALE_FINTO=1
segui-live-terminal segui-live CANALE_FINTO=1
mike mike X=1
safe-strategy safe-strategy X=1
omega omega X=1
tennis-terminal-sinner tennis-terminal X=1
tennis tennis X=1
multi-ladder multi-ladder CANALE_FINTO=1
market-watch market-watch CANALE_FINTO=1
live-pnl live-pnl CANALE_FINTO=1
trade-journal trade-journal X=1
storico-calcio storico-calcio X=1
storico-tennis storico-tennis X=1
report-personale report-personale X=1
watchlist watchlist X=1
match-replay match-replay X=1
analytics analytics X=1
dashboard dashboard X=1
select-sport select-sport ORA_FISSA=0
ELENCO
python3 $Q/affianca.py /tmp/claude-0/proto/sl-terminal.png /tmp/claude-0/consegna_segui-live-terminal/intera/segui-live-terminal.v2.1600.intera.png AUDIT_2026-10-01/REDESIGN/confronto2/segui-live-terminal.affianco.png
CANALE_FINTO=1 bash $Q/prova_off_master.sh control-room,board,segui-live,segui-live-terminal,mike,safe-strategy,omega,tennis-terminal-sinner,tennis,multi-ladder,ladder-popout,market-watch,live-pnl,trade-journal,storico-calcio,storico-tennis,report-personale,watchlist,match-replay,analytics,dashboard 1280,1600
cp -r /tmp/claude-0/off_ramo /tmp/claude-0/off_ramo_finale
