"""Falsificazione W3b A LIVELLO DI REPLAY (famiglia OE del banco): ogni mutazione
reintroduce un difetto, il replay `certifica` DEVE diventare rosso sui controlli
attesi. Ripristino dal contenuto salvato, sha verificato."""
import hashlib
import re
import subprocess
import sys

WT = "/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd"
OUT = "/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w3b_prove"
OE = "Betfair/stream/tennis_scalper/ordini_esterni.py"
SS = "Betfair/stream/scalper/scalper_session.py"

MUT = [
    ("RM1 ordine dal sito preso per un bot", OE,
     "    if motivo_bot_da_riferimenti(vista, tuple(prefissi)) is not None:\n        return BOT\n    return UTENTE",
     "    if motivo_bot_da_riferimenti(vista, tuple(prefissi)) is not None:\n        return BOT\n    if not csr:  # MUTAZIONE\n        return BOT\n    return UTENTE",
     "ordine-esterno"),
    ("RM2 mercato ignorato (ogni mercato e' del bot)", OE,
     "                if mid in mercati:\n",
     "                if True:  # MUTAZIONE\n",
     "ordine-esterno-altro-mercato"),
    ("RM3 gli ordini del bot presi per ordini dell'utente", OE,
     "    bid = _testo(o.get(\"betId\"))\n    if bid and bid in bet_ids_propri:\n        return PROPRIO\n    cor = _testo(o.get(\"customerOrderRef\"))\n    if cor and any(cor.startswith(h) for h in identita.hash):\n        return PROPRIO\n",
     "    pass  # MUTAZIONE\n",
     "ordine-esterno-altro-mercato"),
    ("RM4 all'intervento nessun annullo dei vivi", SS,
     "            evento[\"annullo\"] = OE.annulla_vivi(_ordini_della_sessione(framework, attive))\n",
     "            evento[\"annullo\"] = {}  # MUTAZIONE\n",
     "ordine-esterno"),
    ("RM5 il bot continua a decidere dopo l'intervento", OE,
     "        if _s.controlla() is not None:\n            return False\n        return bool(_orig(market, market_book))",
     "        _s.controlla()  # MUTAZIONE\n        return bool(_orig(market, market_book))",
     "ordine-esterno"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def replay(scenario, nome):
    out = "%s/mut_%s.txt" % (OUT, nome.split()[0])
    with open(out, "w") as fh:
        r = subprocess.run([sys.executable, "-m", "Betfair.stream.backtest.certifica",
                            "scalper_calcio", "35797769", "--scenari", scenario,
                            "--worker", "1"], cwd=WT, stdout=fh, stderr=subprocess.DEVNULL,
                           timeout=2400)
    testo = open(out).read()
    esito = re.findall(r"^(OK|KO|NE)\s+35797769", testo, re.M)
    codici = sorted(set(re.findall(r"^\s+([A-Z]+[0-9]+[a-z]?) x\d+: ", testo, re.M)))
    return r.returncode, esito, codici, out


def main():
    sel = set(sys.argv[1:])
    righe = []
    for nome, f, old, new, scenario in MUT:
        if sel and nome.split()[0] not in sel:
            continue
        p = WT + "/" + f
        orig = open(p, encoding="utf-8").read()
        h0 = sha(p)
        if orig.count(old) != 1:
            righe.append("%s -> NON APPLICABILE (%d)" % (nome, orig.count(old)))
            continue
        try:
            open(p, "w", encoding="utf-8").write(orig.replace(old, new))
            rc, esito, codici, out = replay(scenario, nome)
        finally:
            open(p, "w", encoding="utf-8").write(orig)
        h1 = sha(p)
        righe.append("%s [%s] -> rc=%s esito=%s violazioni=%s | %s | sha %s %s" % (
            nome, scenario, rc, esito, codici, out, h0[:12],
            "ripristinato" if h0 == h1 else "DIVERSO!"))
        print(righe[-1], flush=True)


main()
