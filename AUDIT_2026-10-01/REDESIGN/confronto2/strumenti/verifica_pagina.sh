#!/bin/bash
# Verifiche obbligatorie a ogni pagina (brief §7), a macchina scarica (nessun Chromium acceso).
# Uso, dalla radice del repo: bash AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/verifica_pagina.sh
cd frontend
echo "== tsc"; npx tsc -p tsconfig.app.json --noEmit && echo "tsc 0 errori"
echo "== suite intera"; npx vitest run > /tmp/claude-0/suite_ultima.log 2>&1; grep -E "Test Files|Tests " /tmp/claude-0/suite_ultima.log; grep -E "FAIL" /tmp/claude-0/suite_ultima.log | head
echo "== fotografie non rigenerate"; git status --short src/fotografia/snapshot
echo "== build"; npm run build > /tmp/claude-0/build_ultima.log 2>&1 && du -sb dist/assets
cd ..; echo "== solo classi"; python3 AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/solo_classi.py | sed -n '1,40p'
