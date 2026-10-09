r"""Lancia un AUDIT generico tramite il Claude Agent SDK (crediti API), come la sessione
del piano di architettura dell'08/10 (`sessione_sdk.py`, che resta intatta per il suo
--riprendi), ma con brief, cartella di uscita e tetto passati da riga di comando.

Lezioni dell'08/10 e difese:
- con `query()` il processo moriva a fine turno e uccideva i delegati in sottofondo
  (40,94 USD persi): qui `ClaudeSDKClient` resta vivo e a ogni turno chiuso senza
  `<uscita>/FATTO.txt` riceve «continua»; i delegati vanno lanciati in primo piano;
- errore di rete (ENOTFOUND) a meta' turno: qui l'errore si riconosce, si ASPETTA che la
  rete torni (sonda DNS/TCP verso l'API, senza spendere) e poi si continua; se cade il
  processo intero, si riapre da solo riprendendo la stessa sessione (fino a 50 volte);
- errori che non passano da soli (credito finito, chiave non valida): stop subito, con
  il motivo scritto, invece di bruciare tentativi;
- spesa: il contatore dell'SDK e' cumulativo sulla sessione anche dopo una ripresa
  (08/10: la ripresa e' partita da 40,94); la spesa massima vista e' salvata in
  `<uscita>/costo.txt` e il tetto e' controllato su quella;
- il PC non va in sospensione finche' lo script gira (SetThreadExecutionState).

Uso (PowerShell, nella radice del repo, con la chiave nella stessa finestra):
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python ARCHITETTURA_2026-10\strumenti\sessione_audit_sdk.py --brief X\BRIEF.md --uscita X --prova
    python ARCHITETTURA_2026-10\strumenti\sessione_audit_sdk.py --brief X\BRIEF.md --uscita X --tetto 78
    python ARCHITETTURA_2026-10\strumenti\sessione_audit_sdk.py --brief X\BRIEF.md --uscita X --tetto 78 --riprendi

Registro: <uscita>/registro_sessione_<data>.log; id sessione: <uscita>/ultima_sessione.txt.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import socket
import sys
from pathlib import Path

try:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                                  ResultMessage, SystemMessage, TextBlock, ToolUseBlock)
except ImportError:  # pragma: no cover
    print("manca il pacchetto: esegui  python -m pip install claude-agent-sdk")
    sys.exit(2)

RADICE = Path(__file__).resolve().parents[2]
MAX_CONTINUAZIONI = 400
MAX_RIAPERTURE = 50            # processi riaperti dopo un crollo
ATTESA_RETE_MAX_S = 6 * 3600   # oltre: stop (si riprende a mano con --riprendi)
API_HOST = "api.anthropic.com"

VIETATI = [
    "Bash(git push*)", "Bash(git add -A*)", "Bash(git add .*)", "Bash(git commit*)",
    "Bash(git reset --hard*)", "Bash(git checkout*)", "Bash(git switch*)", "Bash(git rebase*)",
    "Bash(git stash*)", "Bash(git worktree remove --force*)", "Bash(rm -rf*)", "Bash(Remove-Item*)",
    "Bash(npm install*)", "Bash(npm ci*)", "Bash(pip install*)", "Bash(npm run build*)",
]

# testi d'errore dell'API che passano da soli (si aspetta e si continua)
TRANSITORI = ("enotfound", "can't reach the api", "econnreset", "etimedout", "econnrefused",
              "socket hang up", "network", "overloaded", "529", "500", "502", "503", "504",
              "internal server error", "rate limit", "429", "timed out", "timeout",
              "connection error", "fetch failed")
# testi d'errore che NON passano da soli: stop immediato
FATALI = ("credit balance", "billing", "invalid x-api-key", "invalid api key",
          "authentication_error", "permission_error", "401", "403")


def classifica_errore(testo: str) -> str | None:
    """'fatale', 'transitorio' o None (non e' un errore dell'API)."""
    # solo i messaggi d'errore della CLI («API Error: ...») e le eccezioni: mai la prosa
    # dell'agente che parla di errori nel codice analizzato
    t = testo.strip().lower()
    if not t.startswith("api error"):
        return None
    if any(k in t for k in FATALI):
        return "fatale"
    if any(k in t for k in TRANSITORI):
        return "transitorio"
    return "transitorio"


def rete_ok() -> bool:
    try:
        with socket.create_connection((API_HOST, 443), timeout=10):
            return True
    except OSError:
        return False


async def aspetta_rete(scrivi) -> bool:
    if rete_ok():
        await asyncio.sleep(20)   # errore lato server: piccola pausa prima di ripartire
        return True
    scrivi("rete assente verso %s: aspetto che torni (nessuna spesa durante l'attesa)" % API_HOST)
    attesa = 0
    passo = 30
    while attesa < ATTESA_RETE_MAX_S:
        await asyncio.sleep(passo)
        attesa += passo
        if rete_ok():
            scrivi("rete tornata dopo %d s: riprendo" % attesa)
            await asyncio.sleep(10)
            return True
        passo = min(passo * 2, 300)
    scrivi("rete assente da %d s: stop (riprendi con --riprendi)" % attesa)
    return False


def tieni_sveglio() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:  # pragma: no cover
        pass


def regola_scrittura(uscita: str, perimetro: list[str]) -> str:
    if not perimetro:
        return ("(2) AUDIT IN SOLA LETTURA: niente modifiche al codice di produzione, ai test, al DB o "
                f"all'app; scrivi SOLO dentro {uscita}/ (script di sonda compresi); ")
    return ("(2) PERIMETRO DI SCRITTURA: puoi modificare SOLO questi percorsi: "
            + ", ".join(perimetro) + f", e scrivere dentro {uscita}/; tutto il resto (altro codice, "
            "DB, migrazioni, workflow, app, build) e' in sola lettura; se una correzione richiede di "
            f"uscire dal perimetro, NON farla: scrivila in {uscita}/DECISIONI_PER_L_UTENTE.md; ")


def regole(uscita: str, tetto: float, perimetro: list[str] | None = None) -> str:
    return (
        "REGOLE DI LAVORO DI QUESTA SESSIONE (vincolanti): (1) lavori da solo fino alla fine, "
        "nessuno risponde alle domande: cio' che e' una decisione dell'utente lo scrivi in "
        f"{uscita}/DECISIONI_PER_L_UTENTE.md e vai avanti; " + regola_scrittura(uscita, perimetro or [])
        + "mai ordini Betfair, mai processi lasciati accesi, MAI terminare processi (niente "
        "taskkill/Stop-Process/kill: il PC e' condiviso con altre sessioni); niente "
        "commit, niente checkout/stash/switch: il checkout e' condiviso con altre sessioni; "
        "(3) i delegati (strumento Agent) li lanci SEMPRE con run_in_background=false, al massimo "
        "4 alla volta, e chiedi a ciascuno di scrivere il proprio risultato su un file dentro "
        f"{uscita}/lavori/ PRIMA di risponderti (cosi' un'interruzione non perde il lavoro); "
        "(4) a ogni turno chiuso senza aver finito riceverai «continua»; dopo un errore di rete o "
        "un riavvio riprendi dallo stato su disco, senza rifare cio' che e' gia' scritto; "
        f"(5) quando TUTTE le consegne del brief sono scritte crea {uscita}/FATTO.txt con l'elenco "
        "delle consegne e chiudi il turno: solo quel file ferma la sessione; non chiudere mai un "
        "turno senza aver fatto lavoro e senza FATTO.txt; "
        f"(6) {uscita}/COSTI.md aggiornato a ogni tappa con la spesa che ti comunico; tetto "
        f"{tetto:.0f} USD: con meno del 15% residuo chiudi il lavoro in corso, completa in forma "
        "sintetica TUTTE le consegne mancanti, scrivi cio' che resta da approfondire e crea FATTO.txt."
    )


def prompt_inizio(brief: str, uscita: str, tetto: float, perimetro: list[str] | None = None) -> str:
    return (
        f"Leggi CLAUDE.md, poi esegui {brief} dall'inizio alla fine. Sei il coordinatore: "
        "delega le parti a delegati Sonnet (strumento Agent, model sonnet), fai le sintesi con "
        "Opus, verifica ogni reperto contro il codice prima di accettarlo (file:riga), non "
        "fidarti delle ipotesi del brief: fidati solo del codice, dei dati e delle misure; per "
        "ogni reperto scrivi gravita', prova e cio' che non hai potuto verificare. "
        + regole(uscita, tetto, perimetro)
    )


def prompt_ripresa(brief: str, uscita: str, tetto: float, spesa: float,
                   perimetro: list[str] | None = None) -> str:
    return (
        f"Il processo e' stato riaperto dopo un'interruzione (rete o crollo). Riprendi l'audit "
        f"({brief}) da dove eri: controlla lo stato su disco in {uscita}/ (consegne, lavori/, "
        "COSTI.md), integra cio' che e' utilizzabile, rilancia solo le parti mancanti. Spesa "
        f"cumulativa finora: {spesa:.2f} USD su {tetto:.0f}. " + regole(uscita, tetto, perimetro)
    )


def prompt_continua(uscita: str, tetto: float, spesa: float, dopo_errore: bool) -> str:
    inizio = ("Continua dopo un errore di rete o del server: alcuni delegati potrebbero essere "
              "stati interrotti; controlla su disco cosa hanno scritto e rilancia solo il "
              "mancante. " if dopo_errore else "Continua: ")
    return (inizio + f"l'audit non e' finito (manca {uscita}/FATTO.txt). Guarda lo stato su "
            "disco, aggiorna COSTI.md e prosegui con la tappa successiva. Se in realta' hai "
            "consegnato tutto, verifica i file del brief e crea FATTO.txt. Spesa cumulativa "
            f"finora: {spesa:.2f} USD su {tetto:.0f}.")


PROMPT_PROVA = (
    "Prova di collegamento: leggi la prima riga di CLAUDE.md e rispondi con una frase "
    "in italiano che dica quale ramo e quale cartella di lavoro vedi (usa git). Non "
    "modificare nulla. Poi crea il file %s/FATTO.txt con il testo 'prova'."
)


def opzioni(prova: bool, riprendi: str | None, tetto: float) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(RADICE),
        system_prompt={"type": "preset", "preset": "claude_code"},
        tools={"type": "preset", "preset": "claude_code"},
        setting_sources=["user", "project"],
        permission_mode="bypassPermissions",
        disallowed_tools=VIETATI,
        model="opus",
        effort="high",
        max_budget_usd=0.5 if prova else tetto,
        max_turns=4 if prova else None,
        resume=riprendi,
        env={"CLAUDE_AGENT_SDK_CLIENT_APP": "audit-sdk"},
    )


class Stato:
    def __init__(self, cartella: Path) -> None:
        self.fatto = cartella / "FATTO.txt"
        self.ultima = cartella / "ultima_sessione.txt"
        self.file_costo = cartella / "costo.txt"
        self.sessione: str | None = None
        self.costo = 0.0
        if self.file_costo.is_file():
            try:
                self.costo = float(self.file_costo.read_text(encoding="utf-8").strip() or 0)
            except ValueError:
                self.costo = 0.0

    def salva_sessione(self, sid: str) -> None:
        self.sessione = sid
        self.ultima.write_text(sid, encoding="utf-8")

    def aggiorna_costo(self, valore: float | None) -> None:
        if valore is not None and valore > self.costo:
            self.costo = valore
            self.file_costo.write_text("%.4f" % valore, encoding="utf-8")


async def un_processo(brief: str, uscita: str, tetto: float, prova: bool, stato: Stato,
                      primo: str, scrivi) -> str:
    """Esito: 'fatto', 'tetto', 'fatale', 'vuoti', 'rete', 'prova', 'limite'."""
    turni_vuoti = 0
    async with ClaudeSDKClient(options=opzioni(prova, stato.sessione, tetto)) as client:
        await client.query(primo)
        for giro in range(MAX_CONTINUAZIONI):
            strumenti = 0
            errore: str | None = None
            subtype = ""
            async for m in client.receive_response():
                if isinstance(m, SystemMessage):
                    dati = m.data if isinstance(m.data, dict) else {}
                    sid = dati.get("session_id")
                    if sid and sid != stato.sessione:
                        stato.salva_sessione(sid)
                        scrivi("sessione %s (salvata in %s)" % (sid, stato.ultima.name))
                elif isinstance(m, AssistantMessage):
                    for b in m.content:
                        if isinstance(b, TextBlock) and b.text.strip():
                            scrivi("CLAUDE: " + b.text.strip())
                            c = classifica_errore(b.text)
                            if c == "fatale" or (c and errore is None):
                                errore = c
                        elif isinstance(b, ToolUseBlock):
                            strumenti += 1
                            scrivi("strumento %s %s" % (b.name, str(b.input)[:200]))
                elif isinstance(m, ResultMessage):
                    subtype = m.subtype or ""
                    stato.aggiorna_costo(m.total_cost_usd)
                    if m.session_id:
                        stato.salva_sessione(m.session_id)
                    scrivi("TURNO CHIUSO (%d): %s | turni=%s | costo cumulativo=%.2f USD | %.0f s | errore=%s" % (
                        giro + 1, subtype, m.num_turns, stato.costo, (m.duration_ms or 0) / 1000.0, m.is_error))
                    for e in (m.errors or []):
                        scrivi("errore: " + str(e))
                        c = classifica_errore("api error " + str(e))
                        if c == "fatale" or (c and errore is None):
                            errore = c
                    if m.is_error and errore is None and subtype != "error_max_budget_usd":
                        errore = "transitorio"
            if stato.fatto.is_file():
                return "fatto"
            if prova:
                return "prova"
            if stato.costo >= tetto or subtype == "error_max_budget_usd":
                return "tetto"
            if errore == "fatale":
                return "fatale"
            if errore == "transitorio":
                if not await aspetta_rete(scrivi):
                    return "rete"
                scrivi("-> continua dopo errore (giro %d)" % (giro + 2))
                await client.query(prompt_continua(uscita, tetto, stato.costo, True))
                continue
            turni_vuoti = turni_vuoti + 1 if strumenti == 0 else 0
            if turni_vuoti >= 3:
                return "vuoti"
            scrivi("-> continua (giro %d)" % (giro + 2))
            await client.query(prompt_continua(uscita, tetto, stato.costo, False))
    return "limite"


async def esegui(brief: str, uscita: str, tetto: float, prova: bool, riprendi: bool,
                 perimetro: list[str] | None = None, nuovo_compito: bool = False) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY non impostata in questa finestra: $env:ANTHROPIC_API_KEY = \"sk-ant-...\"")
        return 2
    if not prova and not (RADICE / brief).is_file():
        print("brief assente:", RADICE / brief)
        return 2
    cartella = RADICE / uscita
    (cartella / "lavori").mkdir(parents=True, exist_ok=True)
    stato = Stato(cartella)
    if riprendi:
        sid = stato.ultima.read_text(encoding="utf-8").strip() if stato.ultima.is_file() else ""
        if not sid:
            print("nessuna sessione salvata da riprendere in", stato.ultima)
            return 2
        stato.sessione = sid
    else:
        stato.costo = 0.0
        if stato.file_costo.is_file():
            stato.file_costo.unlink()
    if stato.fatto.is_file():
        stato.fatto.unlink()
    tieni_sveglio()
    log = cartella / ("registro_sessione_%s.log" % dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    with log.open("w", encoding="utf-8") as f:
        def scrivi(riga: str) -> None:
            testo = "[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), riga)
            print(testo, flush=True)
            f.write(testo + "\n")
            f.flush()

        scrivi("avvio %s | brief=%s | uscita=%s | tetto=%.2f USD | riprendi=%s | spesa nota=%.2f" % (
            "PROVA" if prova else "AUDIT", brief, uscita, 0.5 if prova else tetto, stato.sessione, stato.costo))
        if prova:
            primo = PROMPT_PROVA % uscita
        elif stato.sessione and nuovo_compito:
            primo = ("NUOVO COMPITO nella stessa sessione (conosci gia' il lavoro fatto): "
                     + prompt_inizio(brief, uscita, tetto, perimetro))
        elif stato.sessione:
            primo = prompt_ripresa(brief, uscita, tetto, stato.costo, perimetro)
        else:
            primo = prompt_inizio(brief, uscita, tetto, perimetro)
        esito = "limite"
        try:
            for apertura in range(MAX_RIAPERTURE):
                try:
                    esito = await un_processo(brief, uscita, tetto, prova, stato, primo, scrivi)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    raise
                except Exception as exc:  # crollo del processo dell'agente o della connessione
                    scrivi("CROLLO del processo (%s: %s)" % (type(exc).__name__, str(exc)[:300]))
                    c = classifica_errore("api error " + str(exc))
                    if c == "fatale":
                        esito = "fatale"
                        break
                    if stato.fatto.is_file():
                        esito = "fatto"
                        break
                    if stato.costo >= tetto:
                        esito = "tetto"
                        break
                    if not stato.sessione:
                        scrivi("nessuna sessione ancora salvata: riparto da capo")
                    if not await aspetta_rete(scrivi):
                        esito = "rete"
                        break
                    scrivi("riapro il processo (%d/%d) riprendendo la sessione %s" % (
                        apertura + 2, MAX_RIAPERTURE, stato.sessione))
                    primo = (prompt_ripresa(brief, uscita, tetto, stato.costo, perimetro) if stato.sessione
                             else prompt_inizio(brief, uscita, tetto, perimetro))
                    continue
                break
        except (KeyboardInterrupt, asyncio.CancelledError):
            scrivi("interrotto dall'utente; spesa cumulativa %.2f USD; riprendi con --riprendi" % stato.costo)
            return 130
        motivi = {
            "fatto": "FATTO.txt presente: audit consegnato",
            "prova": "prova conclusa",
            "tetto": "tetto di spesa raggiunto: stop",
            "fatale": "errore che non passa da solo (credito finito o chiave non valida): stop, leggi il registro",
            "vuoti": "tre turni di fila senza lavoro e senza FATTO.txt: stop, leggi il registro",
            "rete": "rete assente troppo a lungo: stop, riprendi con --riprendi",
            "limite": "limite di continuazioni o riaperture raggiunto: stop",
        }
        scrivi("fine: %s. Spesa cumulativa %.2f USD" % (motivi.get(esito, esito), stato.costo))
    print("registro:", log)
    return 0 if esito in ("fatto", "prova") else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(errors="replace")  # caratteri non stampabili: mai un crollo
    except Exception:  # pragma: no cover
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--brief", default="", help="percorso del brief, relativo alla radice del repo")
    p.add_argument("--uscita", required=True, help="cartella dei referti, relativa alla radice")
    p.add_argument("--tetto", type=float, default=45.0, help="tetto di spesa in USD (default 45)")
    p.add_argument("--prova", action="store_true", help="pochi turni, tetto 0,50 USD")
    p.add_argument("--riprendi", action="store_true", help="riprende l'ultima sessione salvata in <uscita>")
    p.add_argument("--nuovo-compito", action="store_true",
                   help="con --riprendi: stessa sessione, ma parte il brief come compito nuovo")
    p.add_argument("--perimetro", default="",
                   help="percorsi scrivibili separati da virgola (senza: sola lettura)")
    a = p.parse_args()
    uscita = a.uscita.replace("\\", "/").rstrip("/")
    brief = a.brief.replace("\\", "/")
    if not a.prova and not brief:
        print("serve --brief (anche con --riprendi)")
        return 2
    perimetro = [x.strip().replace("\\", "/") for x in a.perimetro.split(",") if x.strip()]
    if a.nuovo_compito and not a.riprendi:
        print("--nuovo-compito vale solo con --riprendi")
        return 2
    return asyncio.run(esegui(brief, uscita, a.tetto, a.prova, a.riprendi, perimetro, a.nuovo_compito))


if __name__ == "__main__":
    sys.exit(main())
