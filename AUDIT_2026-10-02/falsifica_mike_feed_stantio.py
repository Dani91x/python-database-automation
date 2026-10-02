"""Falsificazione della correzione «feed stantio: la stessa gamba respinta non si
ripropone» (02/10). Ogni mutazione rimette un pezzo del difetto nel codice di
produzione; i test nuovi DEVONO diventare rossi. Il file originale si rimette
SEMPRE (finally) e alla fine si verifica che il sorgente sia identico a prima.
Uso (dalla radice del worktree):
    python AUDIT_2026-10-02/falsifica_mike_feed_stantio.py > AUDIT_2026-10-02/falsifica_mike_feed_stantio_out.txt
"""
import hashlib
import subprocess
import sys

TEST = "Betfair/mike/tests/test_mike_feed_stantio_loop_2026_10_02.py"
ENG = "Betfair/mike/engine.py"
SRV = "Betfair/mike/service.py"

MUTAZIONI = [
    ("M1 execute_place non scrive il rifiuto per feed stantio (ramo taker)", SRV,
     "        _rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)\n        db.log(\"no_fill\", {\"leg\": leg.ref, \"role\": leg.role, \"reason\": \"feed_stantio\",\n                           \"wanted\": leg.price, \"side\": leg.side, \"mode\": mode}, info.event_id)",
     "        db.log(\"no_fill\", {\"leg\": leg.ref, \"role\": leg.role, \"reason\": \"feed_stantio\",\n                           \"wanted\": leg.price, \"side\": leg.side, \"mode\": mode}, info.event_id)"),
    ("M2 la lay appoggiata respinta non scrive il rifiuto (ramo resting)", SRV,
     "                    _rifiutata(ctx, leg, E.MOTIVO_FEED_STANTIO)\n",
     "                    pass\n"),
    ("M3 il motore non tiene mai (filtro spento)", ENG,
     "    if snap.feed_fresh:\n        return d\n    tolte = ",
     "    return d\n    tolte = "),
    ("M4 il filtro vale anche a feed FRESCO (non riparte al ritorno)", ENG,
     "    if snap.feed_fresh:\n        return d\n    tolte = ",
     "    tolte = "),
    ("M5 tentativo_gia_rifiutato conta anche il feed stantio (blocca per sempre)", ENG,
     "    if r is None or r.get(\"motivo\") == MOTIVO_FEED_STANTIO:\n        return None\n    return r",
     "    if r is None:\n        return None\n    return r"),
    ("M6 tenendo, lo stato avanza e gli aggiornamenti si applicano", ENG,
     "    stato = d.state if restano_place else ctx.state",
     "    stato = d.state"),
    ("M7 aggiornamenti applicati anche senza ordine (attempts consumati)", ENG,
     "                    updates=dict(d.updates) if restano_place else {},",
     "                    updates=dict(d.updates),"),
    ("M8 il filtro non e' chiamato dalle ultime guardie", ENG,
     "    d = _tieni_a_feed_stantio(ctx, d, snap)\n    d = _guardia_minimo_listino",
     "    d = _guardia_minimo_listino"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pytest():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ultima = [l for l in r.stdout.splitlines() if " passed" in l or " failed" in l or "error" in l]
    falliti = [l.split("::")[-1] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    return r.returncode, (ultima[-1] if ultima else r.stdout[-200:]), falliti


impronte = {p: sha(p) for p in (ENG, SRV)}
rc, riga, _ = pytest()
print(f"BASE (codice corretto): rc={rc} {riga}")
assert rc == 0, "la base deve essere verde"
rossi = 0
for nome, path, vecchio, nuovo in MUTAZIONI:
    orig = open(path, encoding="utf-8", newline="").read()
    if "\r\n" in orig:  # i sorgenti sono CRLF: le mutazioni si scrivono uguali
        vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
    n = orig.count(vecchio)
    if n != 1:
        print(f"{nome}: ANCORA NON APPLICABILE (occorrenze {n})")
        continue
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig.replace(vecchio, nuovo))
        rc, riga, falliti = pytest()
    finally:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig)
    esito = "ROSSO (atteso)" if rc != 0 else "VERDE  <-- il test NON vede la mutazione"
    rossi += rc != 0
    print(f"{nome}: {esito} | {riga}")
    for t in falliti:
        print(f"      rosso: {t}")
for p, h in impronte.items():
    assert sha(p) == h, f"{p} NON ripristinato"
rc, riga, _ = pytest()
print(f"RIPRISTINO: sorgenti identici (sha256) | test di nuovo: rc={rc} {riga}")
print(f"TOTALE: {rossi}/{len(MUTAZIONI)} mutazioni viste dai test")
