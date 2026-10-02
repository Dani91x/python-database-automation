"""FALSIFICAZIONE dei test nuovi dei punti 26-29 (02/10/2026).

Per ogni mutazione: si rimette il difetto nel codice (sostituzione testuale
esatta, che DEVE trovare il testo una volta sola), si lanciano i test nuovi,
si conta quanti diventano rossi, si ripristina il file BYTE PER BYTE (finally).
F0 = il codice di master (i test nuovi devono essere rossi PRIMA della
correzione: e' il "rosso" del TDD). Esito in ``falsifica_scanner_out.txt``.

Uso (dalla radice del worktree):
    <python> AUDIT_2026-10-02/falsifica_scanner.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVICE = "Betfair/safe_strategy/service.py"
DB = "Betfair/safe_strategy/db.py"
SESS = "Betfair/stream/scalper/scalper_session.py"
SUPERV = "Betfair/stream/scalper/scalper_service.py"
MAINJS = "desktop/main.js"
T_SCAN = "Betfair/safe_strategy/tests/test_scanner_mai_cieco_2026_10_02.py"
T_SESS = "Betfair/stream/tests/test_scalper_arresto_ordinato_2026_10_02.py"
OUT = os.path.join(RADICE, "AUDIT_2026-10-02", "falsifica_scanner_out.txt")

MUTAZIONI = [
    # ---------------------------------------------------------- punto 27
    ("F1 build_rows: esposizione solo di Mike (aa5749a)", SERVICE,
     "esposti = set(self._eventi_esposti(None, esp))",
     "esposti = {str(e) for e in self._mike_followed()}", T_SCAN),
    ("F2 _tieni_eventi_vivi: solo Mike e solo calcio (aa5749a)", SERVICE,
     "esposti = set(self._eventi_esposti(sport, esp))",
     "esposti = {str(e) for e in self._mike_followed()} if sport == \"calcio\" else set()", T_SCAN),
    ("F3 MO CLOSED = fine anche con un mercato esposto aperto", SERVICE,
     "            if stato is not None and stato != \"CLOSED\":\n                out.append(mid)",
     "            if False:\n                out.append(mid)", T_SCAN),
    ("F4 mercato esposto MAI visto trattato come aperto", SERVICE,
     "            if stato is not None and stato != \"CLOSED\":\n                out.append(mid)",
     "            if stato != \"CLOSED\":\n                out.append(mid)", T_SCAN),
    ("F10 fonte caduta = nessuna esposizione (non tiene l'ultima buona)", SERVICE,
     "                        if righe is not None:\n                            self._esposizioni_fonti[str(nome)] = list(righe)",
     "                        self._esposizioni_fonti[str(nome)] = list(righe or [])", T_SCAN),
    ("F19 db: posizioni gia' regolate contate come esposte", DB,
     "aperte = _specchio._posizioni_aperte_non_regolate(sb, righe)  # noqa: SLF001",
     "aperte = [p for p in righe if _specchio.esposizione_aperta(p)]", T_SCAN),
    ("F20 db: Omega/Safe solo 'open' (pending/hedged dimenticati)", DB,
     "_STATI_TRADE_ESPOSTI = (\"pending\", \"open\", \"hedged\")",
     "_STATI_TRADE_ESPOSTI = (\"open\",)", T_SCAN),
    ("F21 db: fonte caduta letta come lista vuota", DB,
     "        logger.warning(\"[safe-scan] esposizioni %s: lettura KO: %s\", nome, str(e)[:160])\n        return None",
     "        logger.warning(\"[safe-scan] esposizioni %s: lettura KO: %s\", nome, str(e)[:160])\n        return []", T_SCAN),
    ("F22 db: ordini vivi solo nella grafia dell'Enum", DB,
     "    \"Pending\", \"Executable\", \"Cancelling\", \"Updating\", \"Replacing\",\n", "", T_SCAN),
    # ---------------------------------------------------------- punto 28
    ("F5 ranked: nessun mercato esposto oltre i tetti di candidatura", SERVICE,
     "        if esposti:\n            presenti = {mid for _, mid in out}",
     "        if False:\n            presenti = {mid for _, mid in out}", T_SCAN),
    ("F6 ranked: niente tier -1 per gli esposti", SERVICE,
     "out = [((-1,) + tuple(k) if mid in esposti else k, mid) for k, mid in out]",
     "out = [(k, mid) for k, mid in out]", T_SCAN),
    ("F7 ranked: mercato esposto CLOSED tenuto sotto quote", SERVICE,
     "                    if self._stato_blocco(ev, mid) == \"CLOSED\":\n                        continue",
     "                    if False:\n                        continue", T_SCAN),
    ("F8 riga: blocco esposto potato dai tetti", SERVICE,
     "            or (str(mid) in esposti and isinstance(blk, dict) and blk.get(\"status\") != \"CLOSED\")",
     "            or False", T_SCAN),
    ("F9 riga: blocco esposto CLOSED tenuto", SERVICE,
     "            or (str(mid) in esposti and isinstance(blk, dict) and blk.get(\"status\") != \"CLOSED\")",
     "            or (str(mid) in esposti and isinstance(blk, dict))", T_SCAN),
    ("F15 mercati esposti ignoti mai chiesti a catalogo", SERVICE,
     "                ignoti.append(mid)\n", "                pass\n", T_SCAN),
    ("F16 tipo non pubblicato: CRITICAL anche per lo specchio", SERVICE,
     "                if bots & self._BOT_SUL_FEED:", "                if True:", T_SCAN),
    ("F17 pool: esposto fuori dal pool solo WARN", SERVICE,
     "\"pool_esposti\", tuple(fuori_esposti), \"CRITICAL\",",
     "\"pool_esposti\", tuple(fuori_esposti), \"WARN\",", T_SCAN),
    ("F18 avvisi a raffica (nessun episodio)", SERVICE,
     "        if self._episodi_avviso.get(chiave) == firma:\n            return False\n",
     "", T_SCAN),
    # ---------------------------------------------------------- punto 29
    ("F11 catalogo: esposti fuori tetto mai aggiunti", SERVICE,
     "aggiunti = self._aggiungi_esposti_mancanti(sport, metas)", "aggiunti = 0", T_SCAN),
    ("F12 catalogo troncato: solo log, nessun WARN in live_alerts", SERVICE,
     "self._avviso_episodio(f\"catalogo_troncato:{sport}\", True, \"WARN\",",
     "(lambda *a: None)(f\"catalogo_troncato:{sport}\", True, \"WARN\",", T_SCAN),
    ("F13 catalogo mirato fallito: nessun CRITICAL", SERVICE,
     "f\"esposti_senza_catalogo:{sport}\", tuple(sorted(mancanti)), \"CRITICAL\",",
     "f\"esposti_senza_catalogo:{sport}\", tuple(sorted(mancanti)), \"INFO\",", T_SCAN),
    ("F14 esposto non a catalogo richiesto a raffica", SERVICE,
     "                self._esposti_non_a_catalogo[eid] = t\n", "                pass\n", T_SCAN),
    # ---------------------------------------------------------- punto 26
    ("G1 except esterno: sys.exit senza annullo (difetto originale)", SESS,
     "    if framework is not None:\n        chiudi_all_arresto(",
     "    if False:\n        chiudi_all_arresto(", T_SESS),
    ("G1b except esterno: lo stato e sys.exit senza passare dall'uscita ordinata", SESS,
     "        _uscita_su_eccezione(db, ev, exc, framework, trading, session_paper, runner, flush)",
     "        flush()\n        sys.exit(1)", T_SESS),
    ("G2 stop app/freno: flumine spento senza annullo", SESS,
     "        elif causa_arresto in CAUSE_ARRESTO:", "        elif False:", T_SESS),
    ("G3 annullo non chiesto a flumine", SESS,
     "                market.cancel_order(order)\n", "", T_SESS),
    ("G4 cancel REST anche in PAPER (conto vero)", SESS,
     "    if rimasti and not session_paper and trading is not None:",
     "    if rimasti and trading is not None:", T_SESS),
    ("G5 ripiego REST market-wide", SESS,
     "            esito[\"rest\"] = _sweep_cancel(trading, [m for m in mids if m], bets)",
     "            esito[\"rest\"] = _sweep_cancel(trading, [m for m in mids if m], [])", T_SESS),
    ("G6 tempo massimo ignorato (attesa 10x)", SESS,
     "scadenza = ora() + max(0.0, float(timeout_s))",
     "scadenza = ora() + 10 * max(0.0, float(timeout_s))", T_SESS),
    ("G7 posizione lasciata a mercato senza CRITICAL", SESS,
     "    if non_flat and causa in CAUSE_ARRESTO:", "    if False:", T_SESS),
    ("G9 Ctrl+C/segnale non gestito", SESS,
     "    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001",
     "    except Exception as exc:  # noqa: BLE001", T_SESS),
    ("G10 segnali di arresto non installati", SESS,
     "            signal.signal(num, _al_segnale)\n", "", T_SESS),
    ("G11 annullati anche gli ordini abbinati", SESS,
     "                if str(nome or \"\").upper() in _STATI_VIVI:\n                    out.append((m, o))",
     "                out.append((m, o))", T_SESS),
    # ------------------------------------------- correzioni del pomeriggio
    ("H1 R2 supervisore: attesa di 60 s (il vecchio tetto)", SUPERV,
     "        deadline_s = _tempo_massimo_arresto_s()", "        deadline_s = 60.0", T_SESS),
    ("H2 R2 supervisore: nessun segnale prima del terminate", SUPERV,
     "            _segnale_di_arresto(p)", "            pass", T_SESS),
    ("H3 R2 supervisore: terminate subito dopo il segnale", SUPERV,
     "        _attendi(now() + _attesa_dopo_segnale_s())", "        pass", T_SESS),
    ("H4 R2 tetto calcolato con UNA sola strategia", SESS,
     "TEMPO_MASSIMO_ARRESTO_S = (HEARTBEAT_S + STRATEGIE_MAX * FLAT_ATTESA_S",
     "TEMPO_MASSIMO_ARRESTO_S = (HEARTBEAT_S + FLAT_ATTESA_S", T_SESS),
    ("H5 R2 main.js torna a 70 s", MAINJS,
     "    if (label === 'scalper-service') return 150_000;",
     "    if (label === 'scalper-service') return 70_000;", T_SESS),
    ("H6 R2 sessione senza gruppo di processi (CTRL_BREAK non le arriva)", SUPERV,
     "        creationflags=getattr(subprocess, \"CREATE_NEW_PROCESS_GROUP\", 0),\n", "", T_SESS),
    ("H7 R3 fine vita senza annullo", SESS,
     "                causa_arresto = \"fine_vita\"\n", "", T_SESS),
    ("H8 R3 partita finita trattata come arresto", SESS,
     "\"errore_fatale\", \"fine_vita\"})", "\"errore_fatale\", \"fine_vita\", \"partita_finita\"})",
     T_SESS),
    ("H9 R3 fine vita fuori dalle cause", SESS,
     "\"errore_fatale\", \"fine_vita\"})", "\"errore_fatale\"})", T_SESS),
    ("I1 R6 RPC mai usata (sempre 6-7 SELECT)", DB,
     "    if st[\"assente_ts\"] is None or t - float(st[\"assente_ts\"]) >= _RPC_ESPOSIZIONI_RIPROVA_S:",
     "    if False:", T_SCAN),
    ("I2 R6 errore della RPC trattato come assente (ripiego)", DB,
     "            if not _rpc_assente(e):", "            if False:", T_SCAN),
    ("I3 R6 RPC assente trattata come errore (nessun ripiego)", DB,
     "            if not _rpc_assente(e):", "            if True:", T_SCAN),
    ("I4 R6 WARNING a ogni giro", DB,
     "            if not st[\"avvisato\"]:", "            if True:", T_SCAN),
    ("I5 R6 RPC assente richiesta a ogni giro", DB,
     "            st[\"assente_ts\"] = t\n", "            st[\"assente_ts\"] = None\n", T_SCAN),
    ("I6 R6 lettura completa che non sostituisce (righe vecchie)", SERVICE,
     "                if all(righe is not None for righe in fonti.values()):",
     "                if False:", T_SCAN),
    ("J1 R9 esposto tolto dalla cache senza book", SERVICE,
     "                    and str(store[e].get(\"market_id\")) not in esposti]:", "]:", T_SCAN),
]


def _pytest(*files: str) -> "tuple[int, int, str]":
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider"],
                       cwd=RADICE, capture_output=True, text=True)
    coda = (r.stdout or "").strip().splitlines()[-1:] or [""]
    riga = coda[0]
    rossi = int((re.search(r"(\d+) failed", riga) or [0, 0])[1])
    verdi = int((re.search(r"(\d+) passed", riga) or [0, 0])[1])
    return rossi, verdi, f"{riga} ({time.time() - t0:.1f}s)"


def _leggi(path: str) -> bytes:
    with open(os.path.join(RADICE, path), "rb") as f:
        return f.read()


def _scrivi(path: str, dati: bytes) -> None:
    with open(os.path.join(RADICE, path), "wb") as f:
        f.write(dati)


def main() -> int:
    righe = []
    base = _pytest(T_SCAN, T_SESS)
    righe.append(f"BASE (codice corretto): {base[2]}")
    esiti = []
    # F0: il codice di MASTER con i test nuovi -> rosso (TDD)
    originali = {p: _leggi(p) for p in (SERVICE, DB, SESS, SUPERV, MAINJS)}
    try:
        for p in (SERVICE, DB, SESS, SUPERV, MAINJS):
            master = subprocess.run(["git", "show", f"master:{p}"], cwd=RADICE,
                                    capture_output=True).stdout
            _scrivi(p, master)
        r_scan = _pytest(T_SCAN)
        r_sess = _pytest(T_SESS)
    finally:
        for p, dati in originali.items():
            _scrivi(p, dati)
    righe.append(f"F0 codice di master, test scanner: {r_scan[2]}")
    righe.append(f"F0 codice di master, test scalper: {r_sess[2]}")
    esiti.append(("F0", (r_scan[0] + r_sess[0]) > 0 or "error" in (r_scan[2] + r_sess[2])))
    for nome, path, vecchio, nuovo, test in MUTAZIONI:
        originale = _leggi(path)
        testo = originale.decode("utf-8")
        # i file del repo possono avere fine riga CRLF: si confronta sul testo
        crlf = "\r\n" in testo
        t = testo.replace("\r\n", "\n")
        n = t.count(vecchio)
        if n != 1:
            righe.append(f"{nome}: TESTO NON TROVATO UNA VOLTA SOLA ({n}) -> mutazione NON eseguita")
            esiti.append((nome, False))
            continue
        mutato = t.replace(vecchio, nuovo)
        if crlf:
            mutato = mutato.replace("\n", "\r\n")
        try:
            _scrivi(path, mutato.encode("utf-8"))
            rossi, _, riga = _pytest(test)
        finally:
            _scrivi(path, originale)
        assert _leggi(path) == originale, f"ripristino fallito: {path}"
        esito = rossi > 0 or " error" in riga
        esiti.append((nome, esito))
        righe.append(f"{nome}: {'ROSSO' if esito else 'VERDE (SOPRAVVISSUTA)'} - {riga}")
    finale = _pytest(T_SCAN, T_SESS)
    righe.append(f"FINALE (dopo i ripristini): {finale[2]}")
    stato = subprocess.run(["git", "status", "--short", "--", SERVICE, DB, SESS, SUPERV, MAINJS],
                           cwd=RADICE,
                           capture_output=True, text=True).stdout.strip()
    righe.append(f"git status dei file mutati dopo i ripristini: {stato or 'pulito'}")
    rosse = sum(1 for _, e in esiti if e)
    righe.append(f"TOTALE: {rosse}/{len(esiti)} mutazioni rosse")
    testo = "\n".join(righe) + "\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(testo)
    print(testo)
    return 0 if rosse == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
