"""Differenziale: worker di HEAD vs worker modificato sugli stessi scenari."""
import importlib.util
import json
import subprocess
import sys

W = '/home/user/python-database-automation/.claude/worktrees/agent-a1c21d4fd7008caf6'
sys.path.insert(0, W)
sys.path.insert(0, '/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w2')

import Betfair.stream  # noqa: E402,F401
import Betfair.stream.live_order_worker as nuovo  # noqa: E402

src = subprocess.run(['git', '-C', W, 'show', 'b5547eb:Betfair/stream/live_order_worker.py'],
                     capture_output=True, text=True, check=True).stdout
path = '/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w2/low_head.py'
open(path, 'w').write(src)
spec = importlib.util.spec_from_file_location('Betfair.stream._low_head', path)
vecchio = importlib.util.module_from_spec(spec)
vecchio.__package__ = 'Betfair.stream'
sys.modules['Betfair.stream._low_head'] = vecchio
spec.loader.exec_module(vecchio)

import scenari_parita as SP  # noqa: E402

for m in (nuovo, vecchio):
    m._modo_processo = lambda: "PAPER"
    m._live_order_mode = lambda: "PAPER"
    m._jurisdiction = lambda: "it"
    m._max_stake = lambda: 10.0

diff = 0
tot = 0
snapshot = {}
for sc in SP.scenari():
    a = SP.esegui(vecchio, sc)
    b = SP.esegui(nuovo, sc)
    tot += 1
    snapshot[sc["nome"]] = b
    if a != b:
        diff += 1
        print("DIVERSO", sc["nome"])
        print(" HEAD:", json.dumps(a)[:600])
        print(" NUOVO:", json.dumps(b)[:600])
print(f"scenari {tot}, diversi {diff}")
json.dump(snapshot, open('/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w2/snapshot_parita.json', 'w'), indent=1, sort_keys=True)
