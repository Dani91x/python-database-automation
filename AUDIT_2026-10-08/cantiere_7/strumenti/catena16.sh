#!/bin/bash
# PRIMA sulla cima 16d6c67 (albero estratto) e DOPO (worktree su 16d6c67 + modifiche),
# uno alla volta: Omega 35760084 apertura (+ tutti del PRIMA), Mike e Safe di controllo.
S=/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/c7
W=/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d
bash "$S/lancia2.sh" "$S/prima16" PRIMA16 35760084:apertura
bash "$S/lancia2.sh" "$W" FINALE16 35760084:apertura
bash "$S/lancia3.sh" "$S/prima16" mike PRIMA16 35760084:base,cap-stretto
bash "$S/lancia3.sh" "$W" mike FINALE16 35760084:base,cap-stretto
bash "$S/lancia3.sh" "$S/prima16" safe_base PRIMA16 35760084:base,riavvio
bash "$S/lancia3.sh" "$W" safe_base FINALE16 35760084:base,riavvio
bash "$S/lancia2.sh" "$S/prima16" PRIMA16 35760084:tutti
