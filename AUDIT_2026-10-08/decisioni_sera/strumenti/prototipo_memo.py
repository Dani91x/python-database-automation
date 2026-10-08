# Prototipo D-14d (NON nel repo): memoria per identita' con verifica completa
# (C-level) e misura del tempo contro la conversione di oggi.
import os, sys, time
sys.path.insert(0, os.getcwd())
import flumine  # noqa: F401
from betfairlightweight import APIClient
from betfairlightweight.streaming import StreamListener
from Betfair.stream import valuta as V

MEMO = {}
stat = {"hit": 0, "miss": 0}
_copia = dict.copy


def livelli_memo(chiave, orig, r):
    if orig is None or isinstance(orig, V._LivelliEur):
        return orig
    e = MEMO.get(chiave)
    if (e is not None and e[0] is orig and e[1] == r and len(orig) == len(e[2])
            and orig == e[2] and e[3] == e[4]):
        stat["hit"] += 1
        return e[3]
    stat["miss"] += 1
    conv = V._livelli(orig, r)
    if all(type(x) is dict for x in orig):
        MEMO[chiave] = (orig, r, list(map(_copia, orig)), conv, list(map(_copia, conv)))
    else:
        MEMO.pop(chiave, None)
    return conv


def converti(mb, cambio):
    if getattr(mb, "size_gbp_convertite", False):
        return mb
    r = cambio.per_mercato(mb.market_id)
    for rb in mb.runners:
        if getattr(rb, "_k1_eur", False) is True:
            continue
        ex = rb.ex
        k = (mb.market_id, rb.selection_id, rb.handicap)
        ex.available_to_back = livelli_memo(k + ("b",), ex.available_to_back, r)
        ex.available_to_lay = livelli_memo(k + ("l",), ex.available_to_lay, r)
        ex.traded_volume = livelli_memo(k + ("t",), ex.traded_volume, r)
        rb.total_matched = V._importo(rb.total_matched, r)
        rb._k1_eur = True
    mb.total_matched = V._importo(mb.total_matched, r)
    mb.valuta = V.VALUTA_CONTO
    mb.cambio_gbp_eur = r
    mb.size_gbp_convertite = True
    return mb


modo = sys.argv[2]
trading = APIClient("u", "p", app_key="x", lightweight=False)
listener = StreamListener(max_latency=None, lightweight=False)
gen = trading.streaming.create_historical_generator_stream(file_path=sys.argv[1], listener=listener)
cambio = V.cambio_banco()
f = V.converti_libro if modo == "oggi" else converti
t = 0.0
pc = time.perf_counter
for lista in gen.get_generator()():
    for mb in lista:
        t0 = pc()
        f(mb, cambio)
        t += pc() - t0
print(modo, "tempo conversione %.2f s" % t, stat)
