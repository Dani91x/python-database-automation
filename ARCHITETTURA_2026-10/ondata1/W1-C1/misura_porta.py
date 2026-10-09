"""Misura del costo di PortaLocale.invia (porta + diario fsync) con un esecutore istantaneo."""
import pathlib
import statistics
import sys
import tempfile
import time

sys.path.insert(0, sys.argv[1])
from Betfair.nucleo.ordini.tests import test_c1_porta as T  # noqa: E402
from Betfair.nucleo.ordini.contratto import EventoOrdine  # noqa: E402


class _Istantaneo:
    def place(self, r):
        return EventoOrdine(ref=r.ref, seq=0, fase="accettato", bet_id="1", abbinato=0.0,
                            residuo=float(r.importo), prezzo_medio=None, codice_errore=None,
                            esito_ms=None)

    cancel = replace = place


for durevole in (True, False):
    tmp = pathlib.Path(tempfile.mkdtemp())
    amb = T._Ambiente(tmp)
    amb.porta._esecutore = _Istantaneo()
    if not durevole:
        orig = amb.diario.scrivi
        amb.diario.scrivi = lambda rec, durevole=True, _o=orig: _o(rec, durevole=False)
    tempi = []
    for i in range(2000):
        r = T._r(ref=f"safe-t{i}", creato_ms=amb.orologio.ms)
        t0 = time.perf_counter()
        a = amb.porta.invia(r)
        tempi.append((time.perf_counter() - t0) * 1000)
        assert a.accettato
    tempi.sort()
    print(f"fsync={durevole}: n=2000 p50={statistics.median(tempi):.3f} ms "
          f"p95={tempi[1899]:.3f} ms p99={tempi[1979]:.3f} ms max={tempi[-1]:.3f} ms")
