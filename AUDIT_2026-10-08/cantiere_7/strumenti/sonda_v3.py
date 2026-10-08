"""Sonda (sola lettura): quando la V3 valuta (decisioni_v3 del banco) prima/dopo un istante.
Uso: python3 sonda_v3.py <ev> <sc> <HH:MM:SS> [finestre 0/1]"""
import os, sys
from collections import Counter
sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R
from Betfair.omega import omega_service as S
from Betfair.stream.backtest import certifica as C
ev, sc, soglia = sys.argv[1:4]
if len(sys.argv) > 4:
    R.FINESTRE_DI_PRODUZIONE = sys.argv[4] == "1"
banco = {}
vi = R.FeedReplay.__init__
def init(self, b):
    banco["b"] = b; vi(self, b)
R.FeedReplay.__init__ = init
from datetime import datetime, timezone
vero = S._v3_select
cont = Counter()
def sel(*a, **k):
    h = datetime.fromtimestamp(banco["b"].ora, tz=timezone.utc).strftime("%H:%M:%S")
    cont[("prima" if h < soglia else "dopo")] += 1
    return vero(*a, **k)
S._v3_select = sel
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir=os.path.abspath("_live_raw"), scenario=sc)
print(sc, "finestre", R.FINESTRE_DI_PRODUZIONE, ref.decisioni, ref.azioni, dict(cont))
