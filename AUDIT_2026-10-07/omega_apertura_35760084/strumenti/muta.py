"""Mutazioni della correzione del 07/10 (una per lancio). uso: muta.py M1..M7"""
import sys
p = "Betfair/omega/omega_service.py"
s = open(p).read()
m = sys.argv[1]
RIGA = '        blocchi = ("cs", "ht") if con_ht and _ht_ancora_in_gioco(payload) else ("cs",)\n'
if m == "M1":   # il difetto del 29/09: HT sempre, per ogni decisione e in ogni fase
    old, new = RIGA, '        blocchi = ("cs", "ht")  # MUTAZIONE M1\n'
elif m == "M2":  # HT per le decisioni sull'HT anche nel 2T (fase ignorata)
    old, new = RIGA, '        blocchi = ("cs", "ht") if con_ht else ("cs",)  # MUTAZIONE M2\n'
elif m == "M3":  # la prima correzione: HT anche per la V3 nel 1T
    old, new = '    return _flusso_della_riga(event_id, con_ht=False)\n', '    return _flusso_della_riga(event_id, con_ht=True)  # MUTAZIONE M3\n'
elif m == "M4":  # la gamba v2 1T non guarda piu' l'HT
    old, new = 'if market is _real_market and not v3_on and mtype == "HALF_TIME_SCORE":', 'if False:  # MUTAZIONE M4'
elif m == "M5":  # la chiusura di una gamba HT non guarda l'HT
    old, new = '    if half and market is _real_market and not _flusso_feed_ht(str(event_id)).vivo:\n', '    if False:  # MUTAZIONE M5\n'
elif m == "M6":  # la fase dal solo minuto, non dallo stato IPS
    old, new = '    fase = E.mission_phase(status=status,', '    fase = E.mission_phase(status=None,  # MUTAZIONE M6\n                           '
elif m == "M7":  # la fase dipende dall'orologio di sistema (kickoff fisso)
    old, new = 'kickoff=None,\n', 'kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),  # MUTAZIONE M7\n'
else:
    raise SystemExit("mutazione ignota")
assert s.count(old) == 1, m
open(p, "w").write(s.replace(old, new))
print("applicata", m)
