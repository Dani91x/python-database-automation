"""Latenza di PortaLocale.invia sopra l'ArchivioLocale VERO di W1-G1 (SQLite su file), con
il diario VERO (fsync) e un esecutore istantaneo; 1000 ordini nuovi + 1000 doppioni.

Uso: python latenza_archivio_vero.py <radice del repo> <cartella temporanea> <cartella nucleo/dati del ramo di G1>"""
import importlib.util
import pathlib
import statistics
import sys
import tempfile
import time

# cartella `Betfair/nucleo/dati` del ramo di W1-G1 (argomento 3), finche' G1 non e' integrato
G1 = sys.argv[3]
C1 = sys.argv[1]
sys.path.insert(0, C1)
import Betfair.nucleo.dati  # noqa: E402,F401


def carica(nome):
    spec = importlib.util.spec_from_file_location(f"Betfair.nucleo.dati.{nome}", f"{G1}/{nome}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


carica("percorso")
carica("schema_locale")
arch = carica("archivio")
from Betfair.nucleo.dati.contratto import SpecTabella  # noqa: E402
from Betfair.nucleo.ordini.contratto import EventoOrdine  # noqa: E402
from Betfair.nucleo.ordini.tests import test_c1_porta as T  # noqa: E402

SPEC = {n: SpecTabella(n, (c,), "STA", "stato_denaro", 5.0, False, None, ())
        for n, c in (("ordini_ref_visti", "ref"), ("ordini_seq", "chiave"))}


class _Istantaneo:
    def place(self, r):
        return EventoOrdine(ref=r.ref, seq=0, fase="accettato", bet_id="1", abbinato=0.0,
                            residuo=float(r.importo), prezzo_medio=None, codice_errore=None,
                            esito_ms=None)


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


tmp = pathlib.Path(tempfile.mkdtemp(dir=sys.argv[2]))
a = arch.ArchivioLocale("latenza", SPEC, base=tmp / "arch").apri()
amb = T._Ambiente(tmp, archivio=a)
amb.porta._esecutore = _Istantaneo()
for nome, prefisso in (("nuovi", "safe-n"), ("doppioni (RAM)", "safe-n")):
    tempi, letture = [], []
    for i in range(1000):
        amb.orologio.ms += 1
        r = T._r(ref=f"{prefisso}{i}", creato_ms=amb.orologio.ms)
        t0 = time.perf_counter()
        ack = amb.porta.invia(r)
        tempi.append((time.perf_counter() - t0) * 1000)
        assert ack.accettato, ack
    print(f"invia {nome}: n=1000 p50={statistics.median(tempi):.3f} ms "
          f"p95={pct(tempi, .95):.3f} p99={pct(tempi, .99):.3f} max={max(tempi):.3f}")
# la sola lettura dell'archivio di un ref nuovo (cio' che la porta aggiunge al motore)
lt = []
for i in range(1000):
    t0 = time.perf_counter()
    a.leggi("ordini_ref_visti", {"ref": f"safe-assente{i}"})
    lt.append((time.perf_counter() - t0) * 1000)
print(f"Archivio.leggi (ref assente): p50={statistics.median(lt):.3f} ms p95={pct(lt, .95):.3f} "
      f"p99={pct(lt, .99):.3f}")
amb.porta.chiudi()
a.chiudi()
