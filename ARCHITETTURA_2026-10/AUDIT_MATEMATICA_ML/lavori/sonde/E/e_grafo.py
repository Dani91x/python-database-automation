import ast, os, re, subprocess, sys, collections
R = os.getcwd()
files = subprocess.run(["git","ls-files","*.py"],capture_output=True,text=True,encoding="utf-8").stdout.splitlines()
skip = re.compile(r'^(AUDIT_|ARCHITETTURA_|_checkpoint|_AUDIT|SCHEMI_BOT|docs/)')
files = [f for f in files if not skip.match(f)]
fset = set(files)
def modname(f):
    m = f[:-3].replace("/",".")
    if m.endswith(".__init__"): m = m[:-9]
    return m
mod2f = {modname(f): f for f in files}
# anche modulo "foglia" per script in radice
def resolve(m):
    while m:
        if m in mod2f: return mod2f[m]
        if "." not in m: return None
        m = m.rsplit(".",1)[0]
    return None
edges = collections.defaultdict(set)
dotted = re.compile(r'[\'"]((?:Betfair|Prediction|value_engine|tactical_engine|market_intelligence|Ai Engine|ai_engine)(?:\.\w+)+)[\'"]')
for f in files:
    try: src = open(f,encoding="utf-8",errors="replace").read()
    except Exception: continue
    pkg = modname(f).rsplit(".",1)[0] if "." in modname(f) else ""
    if f.endswith("__init__.py"): pkg = modname(f)
    try: t = ast.parse(src)
    except Exception: t = None
    if t:
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                for a in n.names:
                    r = resolve(a.name)
                    if r: edges[f].add(r)
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    parts = pkg.split(".") if pkg else []
                    parts = parts[:len(parts)-(n.level-1)] if n.level>1 else parts
                    base = ".".join(parts + ([base] if base else []))
                r = resolve(base)
                if r: edges[f].add(r)
                for a in n.names:
                    r = resolve(base+"."+a.name)
                    if r: edges[f].add(r)
    for m in dotted.findall(src):
        r = resolve(m)
        if r: edges[f].add(r)
roots = ["Betfair/stream/avvio_app.py","Betfair/stream/watchdog.py","Betfair/stream/tennis_live/tennis_runner.py",
 "Betfair/stream/scalper/scalper_service.py","Betfair/stream/tennis_live/tennis_bot_service.py","Betfair/safe_strategy/service.py",
 "Betfair/omega/omega_service.py","Betfair/safe_strategy/bot_service.py","Betfair/mike/service.py","Betfair/stream/backtest/worker.py",
 "betfair_tennis_odds.py","daily_yesterday_backfill.py","leagues_mapper.py","compute_ml_post_calibration.py","build_analytics_signals.py",
 "merge_engine_signals.py","enrich_analytics_snapshots.py","refresh_analytics_bets.py","build_direzione.py","cloud_retrain_shard.py",
 "seasons_catchup.py","validate_walkforward.py","generate_dynamic_cal.py","update_poisson_calibration.py","generate_dc_rho.py",
 "Prediction/predictions_results_backfill.py","Prediction/today_predictions_backfill.py","Betfair/stream/scalper/genera_atlante.py"]
for r in roots:
    if r not in fset: print("RADICE NON TROVATA", r, file=sys.stderr)
roots = [r for r in roots if r in fset]
# processi lanciati da subprocess/Popen con "-m modulo" dentro Betfair
sub = re.compile(r'[\'"]-m[\'"]\s*,\s*[\'"]([\w.]+)[\'"]|python[^\n]{0,40}-m\s+([\w.]+)')
for f in files:
    try: src = open(f,encoding="utf-8",errors="replace").read()
    except Exception: continue
    for a,b in sub.findall(src):
        r = resolve(a or b)
        if r: edges[f].add(r)
par = {r: None for r in roots}
q = collections.deque(roots)
while q:
    x = q.popleft()
    for y in edges[x]:
        if y not in par:
            par[y] = x; q.append(y)
out = open(sys.argv[1],"w",encoding="utf-8")
for f in files:
    if f in par:
        chain=[];x=f
        while x and len(chain)<4: chain.append(x.split("/")[-1]); x=par[x]
        out.write(f"LIVE\t{f}\t{'<-'.join(chain)}\n")
    else:
        # importatori (non-test) del file
        imp=[g for g in files if f in edges[g] and not re.search(r'(^|/)test_|/tests?/',g)]
        out.write(f"NONRAGG\t{f}\t{';'.join(i.split('/')[-1] for i in imp[:3])}\n")
print(len(roots), "radici;", len(par), "raggiungibili su", len(files))
