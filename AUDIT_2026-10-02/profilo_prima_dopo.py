"""I punti caldi del replay di Mike base, PRIMA e DOPO, per nome di funzione
(il numero di riga di banco_comune cambia fra le due versioni).
Uso: python AUDIT_2026-10-02/profilo_prima_dopo.py"""
import pstats

VOLUTI = [
    ("replay_registrazioni.py", "process_market_book"),
    ("banco_comune.py", "_a_flumine"),
    ("service.py", "_run_event"),
    ("baseflumine.py", "_process_close_market"),
    ("banco_comune.py", "_process_close_market"),
    ("utils.py", "call_middleware_error_handling"),
    ("banco_comune.py", "applica_book"),
    ("banco_comune.py", "pubblica"),
    ("banco_comune.py", "veloce"),
    ("replay_registrazioni.py", "process_closed_market"),
    ("banco_comune.py", "registra_libro_chiuso"),
    ("banco_comune.py", "_lapse_al_fischio"),
    ("banco_comune.py", "_lapse_alla_sospensione"),
    ("bettingresources.py", "__init__"),
    ("market.py", "cleared"),
    ("scanner.py", "payload_signature"),
    ("dossier.py", "live_frame"),
    ("service.py", "_sorveglia_posizione_di_conto"),
    ("banco_comune.py", "consuma_tempo"),
]

for nome in ("PRIMA", "DOPO"):
    st = pstats.Stats("AUDIT_2026-10-02/replay/mike_base_%s.prof" % nome)
    print("== %s: totale con profilo %.1f s" % (nome, st.total_tt))
    righe = {}
    for (f, l, fn), (cc, nc, tt, ct, _c) in st.stats.items():
        corto = f.replace("\\", "/").split("/")[-1]
        for v in VOLUTI:
            if corto == v[0] and fn == v[1]:
                k = "%s:%s" % v
                a = righe.get(k, (0.0, 0.0, 0))
                righe[k] = (a[0] + ct, a[1] + tt, a[2] + nc)
    for k in ["%s:%s" % v for v in VOLUTI]:
        ct, tt, nc = righe.get(k, (0.0, 0.0, 0))
        print("  cumulato %6.1f  proprio %5.1f  chiamate %8d  %s" % (ct, tt, nc, k))
