r"""Lancia la sessione del piano di architettura tramite il Claude Agent SDK.

Perche': i crediti promozionali del Console valgono per «Agent SDK, API, Batch API,
Playground e Agenti gestiti», NON per Claude Code da terminale. L'Agent SDK e' lo
stesso motore di Claude Code (strumenti Read/Edit/Bash/Grep/Agent, CLAUDE.md,
regole, delegati) usato da uno script: la fatturazione passa dalla chiave API.

LEZIONE DEL PRIMO LANCIO (08/10, 12:18-12:37, 40,94 USD): con `query()` il processo
termina quando il coordinatore chiude il proprio turno; i delegati lanciati in
sottofondo (`run_in_background=True`, che e' il DEFAULT dello strumento Agent) vengono
uccisi a meta' lavoro. Da qui: il processo resta VIVO con `ClaudeSDKClient`, e quando il
coordinatore chiude un turno gli si manda «continua» finche' non scrive il file
ARCHITETTURA_2026-10/FATTO.txt o finisce il budget.

Uso (PowerShell, nella radice del repo, con la chiave nella stessa finestra):
    python -m pip install claude-agent-sdk
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python ARCHITETTURA_2026-10\strumenti\sessione_sdk.py --prova      # 1 turno, tetto 0,50 USD
    python ARCHITETTURA_2026-10\strumenti\sessione_sdk.py              # sessione nuova, tetto 190 USD
    python ARCHITETTURA_2026-10\strumenti\sessione_sdk.py --riprendi   # riprende l'ultima sessione

Tutto cio' che l'agente scrive finisce anche in
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
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                                  ResultMessage, SystemMessage, TextBlock, ToolUseBlock)
except ImportError:  # pragma: no cover
    print("manca il pacchetto: esegui  python -m pip install claude-agent-sdk")
    sys.exit(2)

RADICE = Path(__file__).resolve().parents[2]
CARTELLA = Path(__file__).resolve().parent
BRIEF = "ARCHITETTURA_2026-10/BRIEF_PIANO_ARCHITETTURA_2026-10-08.md"
FATTO = RADICE / "ARCHITETTURA_2026-10" / "FATTO.txt"
ULTIMA = CARTELLA / "ultima_sessione.txt"
TETTO_USD = 190.0
MAX_CONTINUAZIONI = 400

REGOLE_DI_LAVORO = (
    "REGOLE DI LAVORO DI QUESTA SESSIONE (vincolanti): (1) lavori da solo fino alla fine, "
    "nessuno risponde alle domande: se un punto e' una decisione dell'utente lo scrivi nel "
    "documento 06 e vai avanti; (2) i delegati (strumento Agent) li lanci con "
    "run_in_background=false, cioe' aspetti il loro risultato, al massimo 4 alla volta; se "
    "ne lanci in sottofondo NON chiudere il turno finche' non hai ricevuto tutte le loro "
    "notifiche e integrato i risultati; (3) ogni volta che chiudi un turno senza aver finito "
    "il piano, riceverai «continua»: riprendi dallo stato su disco e in git; (4) quando TUTTE "
    "le consegne del brief sono scritte e committate, crea il file ARCHITETTURA_2026-10/FATTO.txt "
    "con l'elenco delle consegne e chiudi il turno: solo quel file ferma la sessione; "
    "(5) commit per tappa con percorsi espliciti, mai git add -A, mai rebase, mai push forzato; "
    "(6) COSTI.md aggiornato a ogni tappa; tetto 190 USD."
)
PROMPT = (
    "Leggi CLAUDE.md, poi esegui " + BRIEF + " dall'inizio alla fine, compreso il "
    "paragrafo 9 che vale su tutto. Sei il coordinatore di questa sessione: delega le "
    "schede e la ricerca sui competitor a delegati Sonnet (strumento Agent, model sonnet), "
    "fai le sintesi con Opus, verifica ogni scheda contro il codice prima di accettarla e "
    "non fidarti delle ipotesi del brief: fidati solo del codice, dei dati e delle misure. "
    "L'utente da' le indicazioni, voi trovate la soluzione ingegneristica migliore per far "
    "funzionare il software al massimo delle potenzialita' senza rinunciare a nulla di "
    "quello che oggi funziona. Niente codice di produzione: solo documenti dentro "
    "ARCHITETTURA_2026-10/. " + REGOLE_DI_LAVORO
)
PROMPT_RIPRESA = (
    "Riprendi il piano di architettura (" + BRIEF + ", par. 9 compreso) da dove eri. Il "
    "processo precedente e' terminato mentre i tuoi delegati in sottofondo lavoravano: "
    "controlla lo stato su disco (file NON tracciati in ARCHITETTURA_2026-10/, strumenti e "
    "uscite dei delegati) e in git (ultimo commit della tappa 0), integra cio' che e' "
    "utilizzabile, rilancia solo i delegati il cui lavoro manca. " + REGOLE_DI_LAVORO
)
PROMPT_CONTINUA = (
    "Continua: il piano non e' finito (manca ARCHITETTURA_2026-10/FATTO.txt). Guarda lo stato "
    "su disco e in git, scrivi in COSTI.md la spesa cumulativa che ti comunico, e prosegui "
    "con la tappa successiva del brief. Se hai delegati in sottofondo, aspetta e integra. "
    "Spesa cumulativa finora: %.2f USD su 190."
)
PROMPT_PROVA = (
    "Prova di collegamento: leggi la prima riga di CLAUDE.md e rispondi con una frase "
    "in italiano che dica quale ramo e quale cartella di lavoro vedi (usa git). Non "
    "modificare nulla. Poi crea il file ARCHITETTURA_2026-10/FATTO.txt con il testo 'prova'."
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
        max_turns=4 if prova else None,
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
    if FATTO.is_file():
        FATTO.unlink()
    log = CARTELLA / ("registro_sessione_%s.log" % dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    costo = 0.0
    sessione = riprendi
    turni_vuoti = 0
    with log.open("w", encoding="utf-8") as f:
        def scrivi(riga: str) -> None:
            ora = dt.datetime.now().strftime("%H:%M:%S")
            testo = "[%s] %s" % (ora, riga)
            print(testo, flush=True)
            f.write(testo + "\n")
            f.flush()

        scrivi("avvio %s | cwd=%s | tetto=%.2f USD | riprendi=%s" % (
            "PROVA" if prova else "SESSIONE", RADICE, 0.5 if prova else TETTO_USD, riprendi))
        primo = PROMPT_PROVA if prova else (PROMPT_RIPRESA if riprendi else PROMPT)
        try:
            async with ClaudeSDKClient(options=opzioni(prova, riprendi)) as client:
                await client.query(primo)
                for giro in range(MAX_CONTINUAZIONI):
                    strumenti_nel_turno = 0
                    async for m in client.receive_response():
                        if isinstance(m, SystemMessage):
                            dati = m.data if isinstance(m.data, dict) else {}
                            sid = dati.get("session_id")
                            if sid and sid != sessione:
                                sessione = sid
                                ULTIMA.write_text(sessione, encoding="utf-8")
                                scrivi("sessione %s (salvata in %s)" % (sessione, ULTIMA.name))
                        elif isinstance(m, AssistantMessage):
                            for b in m.content:
                                if isinstance(b, TextBlock) and b.text.strip():
                                    scrivi("CLAUDE: " + b.text.strip())
                                elif isinstance(b, ToolUseBlock):
                                    strumenti_nel_turno += 1
                                    scrivi("strumento %s %s" % (b.name, str(b.input)[:200]))
                        elif isinstance(m, ResultMessage):
                            costo = m.total_cost_usd or costo
                            if m.session_id:
                                ULTIMA.write_text(m.session_id, encoding="utf-8")
                            scrivi("TURNO CHIUSO (%d): %s | turni=%s | costo cumulativo=%.2f USD | %.0f s | errore=%s" % (
                                giro + 1, m.subtype, m.num_turns, costo, (m.duration_ms or 0) / 1000.0, m.is_error))
                            for e in (m.errors or []):
                                scrivi("errore: " + str(e))
                    # decisione: fermarsi o continuare
                    if FATTO.is_file():
                        scrivi("FATTO.txt presente: il piano e' consegnato. Spesa cumulativa %.2f USD" % costo)
                        break
                    if prova:
                        scrivi("prova conclusa senza FATTO.txt (va bene lo stesso)")
                        break
                    if costo >= TETTO_USD:
                        scrivi("tetto raggiunto (%.2f USD): stop" % costo)
                        break
                    if m.subtype.startswith("error") and m.subtype != "error_max_turns":
                        scrivi("turno in errore (%s): stop, riprendi con --riprendi" % m.subtype)
                        break
                    turni_vuoti = turni_vuoti + 1 if strumenti_nel_turno == 0 else 0
                    if turni_vuoti >= 3:
                        scrivi("tre turni di fila senza strumenti e senza FATTO.txt: stop (controllare il registro)")
                        break
                    scrivi("-> continua (giro %d)" % (giro + 2))
                    await client.query(PROMPT_CONTINUA % costo)
        except KeyboardInterrupt:
            scrivi("interrotto dall'utente; spesa cumulativa %.2f USD; riprendi con --riprendi" % costo)
            return 130
        scrivi("fine. spesa cumulativa %.2f USD" % costo)
    print("registro:", log)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prova", action="store_true", help="pochi turni, tetto 0,50 USD: verifica chiave e fatturazione")
    p.add_argument("--riprendi", action="store_true", help="riprende l'ultima sessione salvata")
    a = p.parse_args()
    riprendi = ULTIMA.read_text(encoding="utf-8").strip() if a.riprendi and ULTIMA.is_file() else None
    if a.riprendi and not riprendi:
        print("nessuna sessione salvata da riprendere")
        return 2
    return asyncio.run(esegui(a.prova, riprendi))


if __name__ == "__main__":
    sys.exit(main())
