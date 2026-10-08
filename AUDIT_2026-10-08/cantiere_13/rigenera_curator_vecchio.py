"""Prova della causa: rigenera la fixture con il curator PRIMA di 9e86c3a (regola (d) assente)
e confronta byte per byte con la fixture del repository. Solo lettura del repo."""
import importlib.util, sys, os
R = sys.argv[1]; vecchio = sys.argv[2]
spec = importlib.util.spec_from_file_location("g", os.path.join(R, "tools/replay_barra_fixture.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
sc = importlib.util.spec_from_file_location("curator_vecchio", vecchio)
cv = importlib.util.module_from_spec(sc); sc.loader.exec_module(cv)
g.curate_event = cv.curate_event  # unica sostituzione: il curator di prima
for ev in sys.argv[3:]:
    s = g.serializza(g.costruisci_fixture(ev))
    att = open(g.nome_fixture(ev), encoding="utf-8").read()
    print(ev, "IDENTICA" if s == att else "DIVERSA", len(s), len(att))
