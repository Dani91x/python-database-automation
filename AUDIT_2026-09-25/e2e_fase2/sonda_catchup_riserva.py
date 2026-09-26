"""sonda_catchup_riserva.py - Verifica indipendente 7.9.4.B (b): riserva dinamica.

Importa la funzione di PRODUZIONE seasons_catchup.ControlloConcorrenza.action_completate_oggi
(nessuna scrittura: fa solo GET verso l'API di GitHub, mai verso API-Football) e la confronta
con quanto dichiarato nel log del run seasons_catchup.yml del 26/09 alle 06:20 UTC.

Uso:  .venv\\Scripts\\python.exe AUDIT_2026-09-25\\e2e_fase2\\sonda_catchup_riserva.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from seasons_catchup import ControlloConcorrenza, ACTION_GIORNALIERE  # noqa: E402

cc = ControlloConcorrenza()
print("GITHUB_TOKEN presente:", bool(cc.token), " repo:", cc.repo)
print("Azioni giornaliere considerate:", ACTION_GIORNALIERE)

for wf in ACTION_GIORNALIERE:
    print(f"  cron di {wf}:", cc.orario_cron(wf), "UTC")

adesso = datetime.now(timezone.utc)
print("\nAdesso UTC:", adesso.isoformat())
esito_ora = cc.action_completate_oggi(adesso)
print("action_completate_oggi() ADESSO ->", esito_ora)

# Ricostruzione dello stato al momento del run delle 06:20:02Z del 26/09 (log catchup):
# i tempi delle run sono letti SOLO con gh run list (nessuna chiamata qui): vedi
# ADMIN26_CATCHUP_QUOTA.md per la tabella con i createdAt esatti.
print("\n(la ricostruzione dello stato ALLE 06:20 e' fatta a mano nel referto con `gh run list`, "
      "perche' questa funzione guarda sempre l'ora corrente reale, non un'ora passata)")
