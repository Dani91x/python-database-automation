r"""Lancia la sessione del piano di architettura tramite il Claude Agent SDK.

Perche': i crediti promozionali del Console valgono per «Agent SDK, API, Batch API,
Playground e Agenti gestiti», NON per Claude Code da terminale. L'Agent SDK e' lo
stesso motore di Claude Code (strumenti Read/Edit/Bash/Grep/Agent, CLAUDE.md,
regole, delegati) usato da uno script: la fatturazione passa dalla chiave API.

Uso (PowerShell, nella radice del repo, con la chiave nella stessa finestra):
    python -m pip install claude-agent-sdk
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python ARCHITETTURA_2026-10\strumenti\sessione_sdk.py --prova      # 1 turno, tetto 0,50 USD
    python ARCHITETTURA_2026-10\strumenti\sessione_sdk.py              # la sessione vera, tetto 190 USD
    python ARCHITETTURA_2026-10\strumenti\sessione_sdk.py --riprendi   # riprende l'ultima sessione

Tutto cio' che l'agente scrive a schermo finisce anche in
ARCHITETTURA_2026-10/strumenti/registro_sessione_<data>.log; l'id della sessione
in ARCHITETTURA_2026-10/strumenti/ultima_sessione.txt (per --riprendi).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
from pathlib import Path

try:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage,
                                  SystemMessage, TextBlock, ToolUseBlock, query)
except ImportError:  # pragma: no cover
    print("manca il pacchetto: esegui  python -m pip install claude-agent-sdk")
    sys.exit(2)

RADICE = Path(__file__).resolve().parents[2]
CARTELLA = Path(__file__).resolve().parent
BRIEF = "ARCHITETTURA_2026-10/BRIEF_PIANO_ARCHITETTURA_2026-10-08.md"
ULTIMA = CARTELLA / "ultima_sessione.txt"
TETTO_USD = 190.0

PROMPT = (
    "Leggi CLAUDE.md, poi esegui " + BRIEF + " dall'inizio alla fine, compreso il "
    "paragrafo 9 che vale su tutto. Sei il coordinatore di questa sessione: delega le "
    "schede e la ricerca sui competitor a delegati Sonnet in parallelo (strumento Agent, "
    "model sonnet), fai le sintesi con Opus, verifica ogni scheda contro il codice prima "
    "di accettarla e non fidarti delle ipotesi del brief: fidati solo del codice, dei dati "
    "e delle misure. L'utente da' le indicazioni, voi trovate la soluzione ingegneristica "
    "migliore per far funzionare il software al massimo delle potenzialita' senza "
    "rinunciare a nulla di quello che oggi funziona. Niente codice di produzione: solo "
    "documenti dentro ARCHITETTURA_2026-10/. Scrivi i costi in "
    "ARCHITETTURA_2026-10/COSTI.md a ogni tappa e usa tutto il budget: fermati a 190 "
    "dollari con il punto di ripresa in CRONOSTORIA.md. Commit per tappa sul ramo "
    "claude/eloquent-franklin-g2nyk5 con percorsi espliciti, mai git add -A, mai rebase, "
    "mai push forzato. Lavora da solo fino alla fine senza chiedere conferme: non c'e' "
    "nessuno a rispondere; se un punto e' davvero una decisione dell'utente, scrivilo nel "
    "documento 06 e vai avanti."
)
PROMPT_PROVA = (
    "Prova di collegamento: leggi la prima riga di CLAUDE.md e rispondi con una frase "
    "in italiano che dica quale ramo e quale cartella di lavoro vedi (usa git). Non "
    "modificare nulla."
)

# comandi che l'agente NON puo' eseguire (il resto e' approvato in automatico)
VIETATI = [
    "Bash(git push --force*)", "Bash(git push -f*)", "Bash(git add -A*)", "Bash(git add .*)",
    "Bash(git reset --hard*)", "Bash(git checkout -- *)", "Bash(git rebase*)",
    "Bash(git worktree remove --force*)", "Bash(rm -rf*)", "Bash(Remove-Item*)",
    "Bash(npm install*)", "Bash(npm ci*)", "Bash(pip install*)", "Bash(npm run build*)",
]


def opzioni(prova: bool, riprendi: str | None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(RADICE),
        system_prompt={"type": "preset", "preset": "claude_code"},
        tools={"type": "preset", "preset": "claude_code"},
        setting_sources=["user", "project"],       # CLAUDE.md, regole, agenti del repo
        permission_mode="bypassPermissions",       # nessuno risponde ai prompt: va da solo
        disallowed_tools=VIETATI,
        model="opus",
        effort="high",
        max_budget_usd=0.5 if prova else TETTO_USD,
        max_turns=3 if prova else None,
        resume=riprendi,
        env={"CLAUDE_AGENT_SDK_CLIENT_APP": "piano-architettura-2026-10"},
    )


async def esegui(prova: bool, riprendi: str | None) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY non impostata in questa finestra: $env:ANTHROPIC_API_KEY = \"sk-ant-...\"")
        return 2
    if not (RADICE / BRIEF).is_file():
        print("brief assente:", RADICE / BRIEF)
        return 2
    log = CARTELLA / ("registro_sessione_%s.log" % dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    costo = 0.0
    sessione = riprendi
    with log.open("w", encoding="utf-8") as f:
        def scrivi(riga: str) -> None:
            ora = dt.datetime.now().strftime("%H:%M:%S")
            testo = "[%s] %s" % (ora, riga)
            print(testo, flush=True)
            f.write(testo + "\n")
            f.flush()

        scrivi("avvio %s | cwd=%s | tetto=%.2f USD | riprendi=%s" % (
            "PROVA" if prova else "SESSIONE", RADICE, 0.5 if prova else TETTO_USD, riprendi))
        try:
            async for m in query(prompt=PROMPT_PROVA if prova else PROMPT,
                                 options=opzioni(prova, riprendi)):
                if isinstance(m, SystemMessage):
                    sid = getattr(m, "data", {}).get("session_id") if isinstance(getattr(m, "data", None), dict) else None
                    if sid and not sessione:
                        sessione = sid
                        ULTIMA.write_text(sessione, encoding="utf-8")
                        scrivi("sessione %s (salvata in %s)" % (sessione, ULTIMA.name))
                elif isinstance(m, AssistantMessage):
                    for b in m.content:
                        if isinstance(b, TextBlock) and b.text.strip():
                            scrivi("CLAUDE: " + b.text.strip())
                        elif isinstance(b, ToolUseBlock):
                            scrivi("strumento %s %s" % (b.name, str(b.input)[:200]))
                elif isinstance(m, ResultMessage):
                    costo = m.total_cost_usd or 0.0
                    if m.session_id:
                        ULTIMA.write_text(m.session_id, encoding="utf-8")
                    scrivi("FINE: %s | turni=%s | costo stimato=%.2f USD | durata=%.0f s | errore=%s" % (
                        m.subtype, m.num_turns, costo, (m.duration_ms or 0) / 1000.0, m.is_error))
                    if m.errors:
                        for e in m.errors:
                            scrivi("errore: " + str(e))
                    if m.usage:
                        scrivi("token: " + str(m.usage))
        except KeyboardInterrupt:
            scrivi("interrotto dall'utente; costo stimato finora %.2f USD; riprendi con --riprendi" % costo)
            return 130
    print("registro:", log)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prova", action="store_true", help="1 turno, tetto 0,50 USD: verifica chiave e fatturazione")
    p.add_argument("--riprendi", action="store_true", help="riprende l'ultima sessione salvata")
    a = p.parse_args()
    riprendi = ULTIMA.read_text(encoding="utf-8").strip() if a.riprendi and ULTIMA.is_file() else None
    if a.riprendi and not riprendi:
        print("nessuna sessione salvata da riprendere")
        return 2
    return asyncio.run(esegui(a.prova, riprendi))


if __name__ == "__main__":
    sys.exit(main())
