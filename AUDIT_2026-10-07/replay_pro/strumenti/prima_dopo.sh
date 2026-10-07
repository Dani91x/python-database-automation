#!/bin/bash
# Referto del banco PRIMA (778189ec) e DOPO (worktree) sugli stessi scenari:
# le modifiche alla cronologia degli ordini non devono cambiare nulla.
S=/tmp/claude-0/-home-user-python-database-automation/b81252ef-134e-5437-9162-d213fe1a02bc/scratchpad/replay_pro
W=/home/user/python-database-automation/.claude/worktrees/agent-ab7777449749e7976
for lato in ${LATI:-prima dopo}; do
  if [ "$lato" = prima ]; then R=$S/base_778; else R=$W; fi
  cd "$R" || exit 1
  python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --data-dir /home/user/python-database-automation/_live_raw --scenari base,media-under,media-clic-due-clic --worker 1 > $S/ref_${lato}_scalper.txt 2>&1
  python -m Betfair.stream.backtest.certifica tennis_scalper 35790089 --data-dir /home/user/python-database-automation/_live_raw_tennis/20260707 --scenari base,gate-aperto,parziali --worker 1 > $S/ref_${lato}_tennis.txt 2>&1
  python -m Betfair.stream.backtest.certifica mike 35797769 --data-dir /home/user/python-database-automation/_live_raw --scenari base --worker 1 > $S/ref_${lato}_mike.txt 2>&1
done
echo FINITO
