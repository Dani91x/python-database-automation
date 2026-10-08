"""Falsificazione del SECONDO GIRO a livello di REPLAY (scalper calcio 35797769):
ogni mutazione reintroduce un difetto della verifica "del bot / fuori bot"; il replay
DEVE diventare rosso sui controlli OE attesi. Ripristino dal contenuto salvato."""
import hashlib
import re
import subprocess
import sys

WT = "/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd"
OUT = WT + "/AUDIT_2026-10-08/W3B/giro2/falsificazioni"
OE = "Betfair/stream/tennis_scalper/ordini_esterni.py"

MUT = [
    ("RM7 esito 'di un bot' trattato come fuori bot", OE,
     "                if esito is not None:\n                    self._attesa.pop(bid, None)\n                    self._rilascia(bid)\n",
     "                if esito is not None:\n                    return self._scatta(o, nuovo, fonte, ric, pub)  # MUTAZIONE\n",
     "ordine-esterno-di-un-bot"),
    ("RM8 DB illeggibile = fuori bot (stop al buio)", OE,
     "                    self._errori[b] = (str(ex)[:200] or type(ex).__name__, ora)\n",
     "                    self._esiti[b] = FUORI_BOT  # MUTAZIONE\n",
     "ordine-esterno-db-giu"),
    ("RM9 il controllo non rifiuta sulla selezione sospesa", OE,
     "            if s.sospesa(getattr(order, \"market_id\", None), getattr(order, \"selection_id\", None)):\n",
     "            if False:  # MUTAZIONE\n",
     "ordine-esterno-db-giu"),
    ("RM10 decisione dai soli riferimenti (verifica saltata)", OE,
     "                if self._conferma is None:\n                    if scatto is None:\n",
     "                if True:  # MUTAZIONE\n                    if scatto is None:\n",
     "ordine-esterno-di-un-bot"),
    # RM8 muta ConfermaBot._gira, che il banco sostituisce con ConfermaBanco (lettura
    # a tempo di mercato): resta verde per costruzione (coperta dal test unitario
    # M18). RM11 porta lo STESSO difetto nel percorso di decisione di produzione.
    ("RM11 DB illeggibile = fuori bot nella decisione (Sorveglianza.rivedi)", OE,
     "                errore = self._conferma.errore(bid)\n                if errore is not None:\n",
     "                errore = self._conferma.errore(bid)\n                if errore is not None:  # MUTAZIONE\n                    self._attesa.pop(bid, None)\n                    return self._scatta(o, nuovo, fonte, ric, pub)\n                if errore is not None:\n",
     "ordine-esterno-db-giu"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    import os

    os.makedirs(OUT, exist_ok=True)
    sel = set(sys.argv[1:])
    for nome, f, old, new, scenario in MUT:
        if sel and nome.split()[0] not in sel:
            continue
        p = WT + "/" + f
        orig = open(p, encoding="utf-8").read()
        h0 = sha(p)
        if orig.count(old) != 1:
            print("%s -> NON APPLICABILE (%d)" % (nome, orig.count(old)), flush=True)
            continue
        out = "%s/mut_%s.txt" % (OUT, nome.split()[0])
        try:
            open(p, "w", encoding="utf-8").write(orig.replace(old, new))
            with open(out, "w") as fh:
                r = subprocess.run([sys.executable, "-m", "Betfair.stream.backtest.certifica",
                                    "scalper_calcio", "35797769", "--scenari", scenario,
                                    "--worker", "1"], cwd=WT, stdout=fh,
                                   stderr=subprocess.DEVNULL, timeout=2400)
        finally:
            open(p, "w", encoding="utf-8").write(orig)
        testo = open(out).read()
        print("%s [%s] -> rc=%s esito=%s violazioni=%s | sha %s %s" % (
            nome, scenario, r.returncode, re.findall(r"^(OK|KO|NE)\s+35797769", testo, re.M),
            sorted(set(re.findall(r"^\s+([A-Z]+[0-9]+[a-z]?) x\d+: ", testo, re.M))),
            h0[:12], "ripristinato" if sha(p) == h0 else "DIVERSO!"), flush=True)


main()
