# Fotografia della selezione V3 col codice di OGGI (HEAD, prima del cantiere):
# per ogni campione del book vero, il candidato col mercato INTERO e col
# mercato SENZA aggregati. Scritta nella fixture come riferimento ("oro").
import json, sys
from Betfair.omega import omega_engine as E, omega_config as C, omega_v3 as V3
from Betfair.omega import omega_proposte as PR

LAMBDAS = (1.45, 1.15)
percorso = sys.argv[1]
dati = json.load(open(percorso))
params = C.resolve_params({})
par = PR.parametri_modello()


def runners_di(c, con_aggregati):
    out = []
    for sid, nome, lp, ls, bp, bs in c["runners"]:
        if not con_aggregati and V3.e_aggregato(nome):
            continue
        out.append(E.ScoreRunner(selection_id=sid, name=nome, lay_price=lp,
                                 lay_size=ls, back_price=bp, back_size=bs))
    return out


def scegli(c, con_aggregati):
    rr = runners_di(c, con_aggregati)
    m = c["minuto"]
    fin = (1, 44) if m <= 44 else (46, 85)
    cand, scarti = E.seleziona_v3(rr, periodo="ft", minuto=float(m),
                                  punteggio=tuple(c["punteggio"]), params=params,
                                  lambdas=LAMBDAS, parametri_modello=par, k_tab=None,
                                  finestra=fin, p_mercato=V3.p_mercato_devigata(rr))
    return {"candidato": None if cand is None else
            {"name": cand.name, "selection_id": cand.selection_id, "price": cand.price,
             "p_nostra": cand.p_nostra, "margine": cand.margine},
            "scarti": [[n, s] for n, s in scarti]}


for c in dati["campioni"]:
    c["oggi_con_aggregati"] = scegli(c, True)
    c["oggi_senza_aggregati"] = scegli(c, False)
dati["oggi"] = ("selezione col codice di HEAD 8226d766 (prima del cantiere 07/10), "
                "lambdas %s, parametri di produzione, fusione col mercato" % (LAMBDAS,))
json.dump(dati, open(percorso, "w"), separators=(",", ":"))
for c in dati["campioni"]:
    a = c["oggi_con_aggregati"]["candidato"]
    b = c["oggi_senza_aggregati"]["candidato"]
    print(c["event_id"], c["minuto"], c["punteggio"], a and a["name"], b and b["name"],
          [s for s in c["oggi_con_aggregati"]["scarti"] if V3.e_aggregato(s[0])])
