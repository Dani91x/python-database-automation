"""Falsificazione W3b: ogni mutazione reintroduce un difetto, i test DEVONO diventare
rossi; il file si ripristina dal contenuto salvato (sha verificato)."""
import hashlib
import subprocess
import sys

WT = "/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd"
OE = "Betfair/stream/tennis_scalper/ordini_esterni.py"
SS = "Betfair/stream/scalper/scalper_session.py"
OET = "Betfair/stream/tennis_live/ordini_esterni_tennis.py"
TR = "Betfair/stream/tennis_live/tennis_runner.py"
T_SC = "Betfair/stream/tests/test_w3b_ordini_esterni_scalper_2026_10_08.py"
T_TE = "Betfair/stream/tennis_live/tests/test_w3b_ordini_esterni_tennis_2026_10_08.py"

MUT = [
    ("M1 ordine dal sito preso per un bot", OE,
     "    if motivo_bot_da_riferimenti(vista, tuple(prefissi)) is not None:\n        return BOT\n    return UTENTE",
     "    if motivo_bot_da_riferimenti(vista, tuple(prefissi)) is not None:\n        return BOT\n    if not csr:  # MUTAZIONE\n        return BOT\n    return UTENTE",
     [T_SC, T_TE]),
    ("M2 mercato ignorato (ogni mercato e' del bot)", OE,
     "                if mid not in mercati:\n",
     "                if False:  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M3 gli ordini del bot non riconosciuti come suoi", OE,
     "    bid = _testo(o.get(\"betId\"))\n    if bid and bid in bet_ids_propri:\n        return PROPRIO\n    cor = _testo(o.get(\"customerOrderRef\"))\n    if cor and any(cor.startswith(h) for h in identita.hash):\n        return PROPRIO\n    csr = _testo(o.get(\"customerStrategyRef\"))\n    if csr and csr[:15].lower() in identita.nomi:\n        return PROPRIO\n",
     "    csr = _testo(o.get(\"customerStrategyRef\"))\n    if csr and csr[:15].lower() in identita.nomi and False:  # MUTAZIONE\n        return PROPRIO\n    csr = None if csr and csr[:15].lower() in identita.nomi else csr  # MUTAZIONE\n    csr = csr or \"\"\n",
     [T_SC, T_TE]),
    ("M4 il registro manda lo stream anche alle sorveglianze paper", OE,
     "                if s.modo != \"live\" or s.intervento is not None:\n",
     "                if s.intervento is not None:  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M5 la fonte paper prende anche ordini live", OET,
     "            if str(rec.get(\"mode\") or \"\").lower() != \"paper\":\n                continue\n",
     "            pass  # MUTAZIONE\n",
     [T_TE]),
    ("M6 la sessione monta la sorveglianza anche in prova / a interruttore spento", SS,
     "        if not OE.acceso() or session_paper:\n            return None\n",
     "        pass  # MUTAZIONE\n",
     [T_SC]),
    ("M7 all'intervento nessun annullo dei vivi", SS,
     "            evento[\"annullo\"] = OE.annulla_vivi(_ordini_della_sessione(framework, attive))\n",
     "            evento[\"annullo\"] = {}  # MUTAZIONE\n",
     [T_SC]),
    ("M8 all'intervento le strategie non si fermano", SS,
     "            for s in attive:\n                OE.ferma_strategia(s)\n",
     "            pass  # MUTAZIONE\n",
     [T_SC]),
    ("M9 linea di base tolta (ordini vecchi = intervento)", OE,
     "            self._base[bid] = sm if vecchio else 0.0\n",
     "            self._base[bid] = 0.0  # MUTAZIONE\n",
     [T_SC]),
    ("M10 dopo l'intervento la sessione fa force-flat (copre)", SS,
     "            if esterni is not None and esterni.intervento is not None:\n                stopped_by_ui = True\n",
     "            if esterni is not None and esterni.intervento is not None:\n                _force_flat_all()  # MUTAZIONE\n                stopped_by_ui = True\n",
     [T_SC]),
    ("M11 tennis: riga senza il marcatore che il ponte legge", OET,
     "        stats[CM.CHIAVE_STATS] = {",
     "        stats[\"MUTAZIONE\"] = {",
     [T_TE]),
    ("M12 tennis: il ladder manuale ('tennis') preso per un bot", OET,
     "            rif_manuali=(OE.RIF_MANUALE_TENNIS,),\n",
     "            rif_manuali=(),  # MUTAZIONE\n",
     [T_TE]),
    ("M13 tennis: all'intervento il bot non si disabilita", OET,
     "            disabilita(bot)\n",
     "            pass  # MUTAZIONE\n",
     [T_TE]),
    ("M14 tennis: conclusione dopo l'heartbeat (riga riscritta running)", TR,
     "    try:\n        _OET.concludi_interventi(session, flumine, e_flat=_strategy_is_flat)\n",
     "    try:\n        pass  # MUTAZIONE\n",
     [T_TE]),
    # --- SECONDO GIRO: la verifica "del bot / fuori bot" ---
    ("M16 la verifica ignora il DB (tutto fuori bot)", OE,
     "                    self._esiti[b] = (\"bot:%s\" % motivo) if motivo else FUORI_BOT\n",
     "                    self._esiti[b] = FUORI_BOT  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M17 esito 'di un bot' trattato come fuori bot", OE,
     "                if esito is not None:\n                    self._attesa.pop(bid, None)\n                    self._rilascia(bid)\n",
     "                if esito is not None:\n                    return self._scatta(o, nuovo, fonte, ric, pub)  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M18 DB illeggibile = fuori bot (stop al buio)", OE,
     "                    self._errori[b] = (str(ex)[:200] or type(ex).__name__, ora)\n",
     "                    self._esiti[b] = FUORI_BOT  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M19 il controllo non rifiuta sulla selezione sospesa", OE,
     "            if s.sospesa(getattr(order, \"market_id\", None), getattr(order, \"selection_id\", None)):\n",
     "            if False:  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M20 nessuna sospensione durante la verifica", OE,
     "        self._sospese.setdefault(chiave, set()).add(bid)\n",
     "        pass  # MUTAZIONE\n",
     [T_SC, T_TE]),
    ("M21 decisione dai soli riferimenti (verifica saltata)", OE,
     "                if self._conferma is None:\n                    if scatto is None:\n",
     "                if True:  # MUTAZIONE\n                    if scatto is None:\n",
     [T_SC, T_TE]),
    ("M22 tennis: riga di coda del runner ignorata (solo DB)", OET,
     "        return motivo_bot_da_coda(coda) if isinstance(coda, dict) else None\n",
     "        return None  # MUTAZIONE\n",
     [T_TE]),
    ("M23 nessuna cache: l'esito letto si butta (il DB si rilegge)", OE,
     "            return self._esiti.get(str(bet_id))\n",
     "            return self._esiti.pop(str(bet_id), None)  # MUTAZIONE\n",
     [T_SC]),
    ("M15 una sola volta: l'intervento si ripete", OE,
     "        if self.intervento is not None:\n            return None\n        with self._lock:\n            if self.intervento is not None:\n                return None\n",
     "        with self._lock:  # MUTAZIONE\n",
     [T_SC]),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pytest(files):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *files],
                       cwd=WT, capture_output=True, text=True, timeout=900)
    righe = [x for x in r.stdout.strip().splitlines() if x.strip()]
    return r.returncode, (righe[-1] if righe else r.stderr[-300:])


def main():
    sel = set(sys.argv[1:])
    esiti = []
    for nome, f, old, new, tests in MUT:
        if sel and nome.split()[0] not in sel:
            continue
        p = WT + "/" + f
        orig = open(p, encoding="utf-8").read()
        h0 = sha(p)
        if orig.count(old) != 1:
            esiti.append((nome, "NON APPLICABILE (testo trovato %d volte)" % orig.count(old), h0, h0))
            continue
        try:
            open(p, "w", encoding="utf-8").write(orig.replace(old, new))
            rc, riga = pytest(tests)
        finally:
            open(p, "w", encoding="utf-8").write(orig)
        h1 = sha(p)
        esito = ("ROSSO" if rc != 0 else "VERDE (mutazione NON catturata)") + " | " + riga
        esiti.append((nome, esito, h0, h1))
    for nome, esito, h0, h1 in esiti:
        print("%s -> %s | sha %s %s" % (nome, esito, h0[:12], "ripristinato" if h0 == h1 else "DIVERSO!"))


main()
