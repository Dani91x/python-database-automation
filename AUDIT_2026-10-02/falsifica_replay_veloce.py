"""FALSIFICAZIONE delle memorie del REPLAY VELOCE (02/10).

Per ogni mutazione: si altera il sorgente del banco (una memoria che restituisce
un dato STANTIO), si lancia il file di test, si pretende ROSSO, e si RIPRISTINA
il sorgente dal contenuto letto prima (anche se il test esplode). Alla fine si
verifica che il file sia identico byte per byte all'originale.
Uso (dalla radice del worktree): python AUDIT_2026-10-02/falsifica_replay_veloce.py
"""
import hashlib
import io
import os
import subprocess
import sys

BANCO = os.path.join("Betfair", "stream", "backtest", "banco_comune.py")
TEST = os.path.join("Betfair", "stream", "tests", "test_banco_replay_veloce_2026_10_02.py")

# (nome, file, testo da trovare UNA volta, sostituto). Niente fine riga nei
# testi: i sorgenti sono in CRLF.
MUTAZIONI = [
    ("M1 libro chiuso: memoria per market_id, non per oggetto",
     BANCO, "and prec is not None and prec[0] is market_book",
     "and prec is not None"),
    ("M2 libro chiuso: ignora la conversione in EUR",
     BANCO, "and prec[1] == convertito", "and True"),
    ("M3 libro chiuso: ignora chi ha sostituito il libro",
     BANCO, "and self.libri_chiusi.get(mid_libro) is prec[2]):", "and True):"),
    ("M4 lapse: memoria per market_id, non per oggetto",
     BANCO, "self._ultimo_book_lapse.get(market_id) is market_book):",
     "market_id in self._ultimo_book_lapse):"),
    ("M5 lapse: la memoria non si aggiorna (resta il primo book del mercato)",
     BANCO, "self._ultimo_book_lapse[market_id] = market_book",
     "self._ultimo_book_lapse.setdefault(market_id, market_book)"),
    ("M6 chiusura: muta anche con un logging control montato",
     BANCO, "or self._logging_controls", "or False"),
    ("M7 chiusura: muta anche con il log INFO di flumine acceso",
     BANCO, "or log_flumine.isEnabledFor(logging.INFO)):", "or False):"),
    ("M8 chiusura: la copia non consegna la chiusura alla strategia",
     BANCO, "            strategy.process_closed_market(market, event.event)",
     "            pass"),
    ("M9 chiusura: la copia non regola gli ordini del blotter",
     BANCO, "        market.blotter.process_closed_market(market, event.event)",
     "        pass"),
]


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    esiti = []
    for nome, percorso, da, a in MUTAZIONI:
        originale = io.open(percorso, "rb").read()
        h0 = md5(percorso)
        testo = originale.decode("utf-8")
        if testo.count(da) != 1:
            esiti.append((nome, "NON APPLICABILE (testo non trovato una sola volta)"))
            continue
        try:
            io.open(percorso, "wb").write(testo.replace(da, a).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q",
                                "-p", "no:cacheprovider"],
                               capture_output=True, text=True)
            ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
            rossi = [l.split(" ")[1] for l in r.stdout.splitlines() if l.startswith("FAILED ")]
            esiti.append((nome, ("ROSSO " if r.returncode != 0 else "VERDE (!!) ") + ultima
                          + "".join("\n      " + x for x in rossi)))
        finally:
            io.open(percorso, "wb").write(originale)
        assert md5(percorso) == h0, "RIPRISTINO FALLITO " + percorso
    for nome, e in esiti:
        print(f"{nome}: {e}")
    print("sorgenti ripristinati, md5 identici")
    return 0 if all(e.startswith("ROSSO") for _n, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
