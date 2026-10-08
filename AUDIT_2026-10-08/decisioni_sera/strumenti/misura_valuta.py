# Misura D-14d: quanti livelli convertiti da `valuta.converti_libro` arrivano
# in una lista ORIGINALE identica (stesso oggetto) a quella del book precedente
# per la stessa (mercato, selezione, lato), e quanto costa la conversione.
# In streaming (nessun book trattenuto). Uso: python misura_valuta.py RAW.jsonl
import os, sys, time
sys.path.insert(0, os.getcwd())
import flumine  # noqa: F401 - patch di EX (livelli dict) come nel banco
from betfairlightweight import APIClient
from betfairlightweight.streaming import StreamListener
from Betfair.stream import valuta as V

raw = sys.argv[1]
trading = APIClient("u", "p", app_key="x", lightweight=False)
listener = StreamListener(max_latency=None, lightweight=False)
gen = trading.streaming.create_historical_generator_stream(file_path=raw, listener=listener)
cambio = V.cambio_banco()
ultimo = {}
nbook = liste = stesse = livelli = livelli_stessi = 0
t_conv = 0.0
pc = time.perf_counter
for lista in gen.get_generator()():
    for mb in lista:
        nbook += 1
        if getattr(mb, "size_gbp_convertite", False):
            continue
        for rb in mb.runners:
            if getattr(rb, "_k1_eur", False) is True:
                continue
            for lato in ("available_to_back", "available_to_lay", "traded_volume"):
                l = getattr(rb.ex, lato)
                if l is None:
                    continue
                k = (mb.market_id, rb.selection_id, lato)
                liste += 1
                livelli += len(l)
                if ultimo.get(k) is l:
                    stesse += 1
                    livelli_stessi += len(l)
                ultimo[k] = l
        t0 = pc()
        V.converti_libro(mb, cambio)
        t_conv += pc() - t0
print("book: %d" % nbook)
print("liste convertite: %d, stesso oggetto della precedente: %d (%.1f%%)" % (liste, stesse, 100.0 * stesse / max(1, liste)))
print("livelli convertiti: %d, in liste identiche: %d (%.1f%%)" % (livelli, livelli_stessi, 100.0 * livelli_stessi / max(1, livelli)))
print("tempo dentro converti_libro: %.2f s" % t_conv)
