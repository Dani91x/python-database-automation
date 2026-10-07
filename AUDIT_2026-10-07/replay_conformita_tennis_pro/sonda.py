# Sonda di SOLA LETTURA: gira il replay del banco (codice di produzione) e registra
# ogni evento emesso dal bot con l'ora di mercato e il punteggio corrente.
# Uso: python3 sonda.py <bot> <scenario> [params_json] [nomi]
#   params_json: se dato, SOSTITUISCE i parametri dello scenario (sonda di conformita')
import sys, os, json, datetime, logging

WT = "/home/user/python-database-automation/.claude/worktrees/agent-a3b99e75233c89de6"
sys.path.insert(0, WT)
os.chdir(WT)
logging.basicConfig(level=logging.ERROR)

from Betfair.stream.tennis_live.tools import replay_bot as RB  # noqa: E402

bot = sys.argv[1]
scenario = sys.argv[2]
params = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] not in ("", "-") else None
nomi = sys.argv[4] if len(sys.argv) > 4 else None
DATA = "/home/user/python-database-automation/_live_raw_tennis/20260707"

if params is not None:
    _orig = RB.parametri_scenario

    def _p(sc, b):
        return dict(params)
    RB.parametri_scenario = _p

CLS = {
    "tennis_pro": ("Betfair.stream.tennis_scalper.tennis_pro_bot", "TennisProStrategy"),
    "tennis_flb": ("Betfair.stream.tennis_scalper.tennis_flb_bot", "TennisFLBStrategy"),
    "tennis_swing": ("Betfair.stream.tennis_scalper.tennis_swing_bot", "TennisSwingStrategy"),
    "tennis_scalper": ("Betfair.stream.tennis_scalper.tennis_scalper_bot", "TennisScalperStrategy"),
}
import importlib  # noqa: E402
mod = importlib.import_module(CLS[bot][0])
K = getattr(mod, CLS[bot][1])
EV = []
_emit0 = K._emit


def _emit(self, ev, **p):
    pt = getattr(self, "_now_pt", None) or getattr(self, "_now_ms", None)
    s = getattr(self, "score", None)
    sk = None
    if s is not None:
        sk = "S%s-%s G%s-%s P%s-%s srv=%s" % (s.sets_home, s.sets_away, s.games_home,
                                            s.games_away, s.point_home, s.point_away, s.server)
    EV.append((pt, ev, p, sk))
    return _emit0(self, ev, **p)


K._emit = _emit
ref = RB.certifica_scenario("35790089", data_dir=DATA, scenario=scenario, bot=bot, nomi=nomi)
print("ESITO", "OK" if ref.pulita else "KO", "tick", ref.tick, "azioni", ref.azioni,
      "ordini", ref.ordini_piazzati, "abbinati", ref.ordini_abbinati, "stati", ref.stati_visti,
      "violazioni", ref.per_codice())
print("STATS", json.dumps(ref.stats_finali, default=str)[:600])
for n in ref.note:
    if "RESIDUI" in n or "catalogo" in n or "SCENARIO" in n:
        print("NOTA", n[:300])
import collections  # noqa: E402
print("EVENTI", collections.Counter(e[1] for e in EV))
SALTA = set((sys.argv[5] if len(sys.argv) > 5 else "").split(","))
for pt, ev, p, sk in EV:
    if ev in SALTA:
        continue
    t = datetime.datetime.fromtimestamp((pt or 0) / 1000, datetime.UTC).strftime("%H:%M:%S") if pt else "-"
    print(t, ev, json.dumps(p, default=str)[:260], sk or "")
