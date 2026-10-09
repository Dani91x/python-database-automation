"""CPU del ladder (W1-A2, revisione M5b): nuovo a 20 ms contro oggi a 200 ms, con MOLTE partite insieme.

Dalla radice del repository:

    python ARCHITETTURA_2026-10/ondata1/W1-A2/misura_cpu_ladder.py [copie ...]

Prende una finestra della registrazione 35797769 (messaggi ``DA``..``A``, partita in
corso) e la replica in N copie con id di mercato diversi (N partite contemporanee,
stessi istanti): ogni copia passa dal SUO ``StreamListener`` vero. Sugli stessi
``MarketBook`` girano insieme, col tempo della registrazione (``pt``):
* OGGI: ``MarketRecorderStrategy.process_market_book`` vero (serializza OGNI book,
  thread di flumine) + ``runner.ladder_worker`` vero a 200 ms;
* NUOVO: ``LadderEvento`` (``consumatore`` + ``esegui_scaduti``) a 20 ms;
e per entrambi la serializzazione JSON che ``local_channel.publish`` fa a ogni invio.
Misura ``time.thread_time`` (CPU del thread) di ciascuno, separata, e la divide per la
durata della finestra: percentuale di UN core. Una riga JSON per N.
Limite dichiarato: la CPU di oggi qui e' recorder + worker (due thread in esercizio),
quella nuova e' il solo thread del ladder (il recorder di oggi resta nel runner fino al
taglio: in ombra la CPU si SOMMA).
"""
from __future__ import annotations

import json
import os
import queue
import sys
import time

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, RADICE)

DA, A = 30000, 33000
EVENTO = "35797769"


def _righe():
    from Betfair.nucleo.betfair.tests.test_a2_finti import righe_registrazione
    for i, riga in enumerate(righe_registrazione(EVENTO)):
        if i >= A:
            return
        if i >= DA:
            yield riga


def misura(copie: int) -> dict:
    import pytest
    from betfairlightweight.streaming.listener import StreamListener

    from Betfair.nucleo.betfair.tests.test_a2_ladder_parita import Banco

    righe = list(_righe())
    listener = []
    for _k in range(copie):
        q: "queue.Queue" = queue.Queue()
        li = StreamListener(output_queue=q, max_latency=None)
        li.register_stream(0, "marketSubscription")
        listener.append((li, q))
    cpu = {"oggi": 0.0, "nuovo": 0.0}
    pubblicati = {"oggi": 0, "nuovo": 0}
    with pytest.MonkeyPatch.context() as mp:
        banco = Banco("calcio", mp, canale_ms_vecchio=200, intervallo_nuovo_ms=20)
        orig = {"vr": banco._vecchio_riceve, "gv": banco._giro_vecchio,
                "cons": banco.lad.consumatore, "es": banco.lad.esegui_scaduti}

        def pub_oggi(topic, riga):
            json.dumps({"t": topic, "d": riga}, default=str)
            pubblicati["oggi"] += 1

        def pub_nuovo(topic, riga):
            json.dumps({"t": topic, "d": riga}, default=str)
            pubblicati["nuovo"] += 1
        from Betfair.stream import local_channel as LCH
        mp.setattr(LCH, "publish", pub_oggi)
        banco.lad._pubblica = pub_nuovo

        def con_cpu(chi, f):
            def g(*a, **k):
                t0 = time.thread_time()
                try:
                    return f(*a, **k)
                finally:
                    cpu[chi] += time.thread_time() - t0
            return g
        banco._vecchio_riceve = con_cpu("oggi", orig["vr"])
        banco._giro_vecchio = con_cpu("oggi", orig["gv"])
        banco.lad.consumatore = con_cpu("nuovo", orig["cons"])
        banco.lad.esegui_scaduti = con_cpu("nuovo", orig["es"])
        t_primo = t_ultimo = None
        libri_tot = 0
        for i, riga in enumerate(righe):
            d = json.loads(riga)
            pt = d.get("pt")
            t = pt / 1000.0 if isinstance(pt, (int, float)) else (t_ultimo or 0.0)
            t_primo = t if t_primo is None else t_primo
            t_ultimo = max(t, t_ultimo or t)
            libri = []
            for k, (li, q) in enumerate(listener):
                li.on_data(riga.replace('"id":"1.', '"id":"1.%d' % (k + 1)))
                while not q.empty():
                    libri.extend(q.get_nowait())
            libri_tot += len(libri)
            if libri:
                banco.passo(i, t_ultimo, libri, ogni_messaggio=False)
            banco.vecchio.canale.clear(), banco.nuovo.canale.clear()
    durata = max(1e-9, t_ultimo - t_primo)
    return {"copie": copie, "messaggi_per_copia": len(righe), "book": libri_tot,
            "durata_finestra_s": round(durata, 1),
            "cpu_oggi_s": round(cpu["oggi"], 2), "cpu_nuovo_s": round(cpu["nuovo"], 2),
            "cpu_oggi_pct_core": round(100.0 * cpu["oggi"] / durata, 2),
            "cpu_nuovo_pct_core": round(100.0 * cpu["nuovo"] / durata, 2),
            "pubblicati_oggi": pubblicati["oggi"], "pubblicati_nuovo": pubblicati["nuovo"]}


if __name__ == "__main__":
    for n in [int(x) for x in sys.argv[1:]] or [1, 10]:
        print(json.dumps(misura(n), sort_keys=True), flush=True)
