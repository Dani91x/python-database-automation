#!/bin/bash
# uno alla volta: il DOPO parte solo quando il PRIMA (prima3.sh) ha finito
P=/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w3b_prima3/prima_exit.txt
until [ -f "$P" ] && [ "$(wc -l < "$P")" = "2" ]; do sleep 20; done
cat "$P"
bash /home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd/AUDIT_2026-10-08/W3B/strumenti/dopo3.sh
cat /home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd/AUDIT_2026-10-08/W3B/giro2_c9/dopo_exit.txt
