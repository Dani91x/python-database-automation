"""Falsificazione del REVISORE (02/10) su RUNNER_MINIMI_CHIUSURE.

Da lanciare dalla radice di un EXPORT ISOLATO dell'albero patchato (git archive), non dal
worktree: nel worktree i test leggono il .env del checkout principale e alcuni
diventano rossi per ragioni d'ambiente. Ogni mutazione: applica, lancia il set mirato,
confronta i rossi con la base (i rossi preesistenti o dipendenti dall'ordine non contano),
ripristina byte per byte."""
import subprocess
import sys

NEW = "Betfair/stream/tests/test_runner_minimi_chiusure_2026_10_01.py"
TESTS = [
    NEW,
    "Betfair/stream/tests/test_live_order_build.py",
    "Betfair/stream/tests/test_submin.py",
    "Betfair/stream/tests/test_submin_nucleo_2026_09_17.py",
    "Betfair/stream/tests/test_motore_ordini_2026_09_24.py",
    "Betfair/stream/tests/test_motore_submin_fok_caso_b_d1ter_2026_09_28.py",
    "Betfair/stream/tests/test_live_order_worker.py",
    "Betfair/stream/tests/test_cashout_pro_2026_09_10.py",
    "Betfair/safe_strategy/tests/test_audit_2026_09_11.py",
    "Betfair/safe_strategy/tests/test_execution.py",
    "Betfair/safe_strategy/tests/test_p_blocco3_2026_09_28.py",
    "Betfair/omega/test_place_and_trim_2026_09_13.py",
]
LB = "Betfair/stream/live_order_build.py"
MO = "Betfair/stream/motore_ordini.py"
SU = "Betfair/stream/trading/submin.py"
MI = "Betfair/stream/trading/minimi_it.py"
EX = "Betfair/safe_strategy/execution.py"
OM = "Betfair/omega/omega_market.py"
LW = "Betfair/stream/live_order_worker.py"

MUT = [
    ("R1 equivalente BANCA col tick in SU (limite peggiore per chi punta)", LB,
     'tick = _tick_su(esatta) if lato == "back" else _tick_giu(esatta)',
     'tick = _tick_su(esatta)'),
    ("R2 parcheggio abbinabile ammesso (guardia SUBMIN_PARCHEGGIO_ABBINABILE tolta)", SU,
     "    if passiva is not True and quota_non_abbinabile(",
     "    if False and quota_non_abbinabile("),
    ("R3 parcheggio LAY sempre a 1,01 (banda INVALID_PROFIT_RATIO ignorata)", SU,
     "    return max(base, float(tick))\n",
     "    return base\n"),
    ("R4 rifiuto senza il residuo dichiarato al trader", LB,
     '    residuo = (f"residuo {s.upper()} {float(size):.2f}@{price} NON piazzato: va dichiarato "\n'
     '               f"al trader (scelta sua: lasciarlo, oppure aumentare e richiudere)")\n',
     '    residuo = ""\n'),
    ("R5 paper: il motore non applica i minimi (0,99 diretto in paper)", MO,
     '        if piano.get("minimi_originale") is None:\n',
     '        if piano.get("mode") == "paper":\n            return\n'
     '        if piano.get("minimi_originale") is None:\n'),
    ("R6 IT_MIN_LAY a 0,50", MI, "IT_MIN_LAY = 1.00\n", "IT_MIN_LAY = 0.50\n"),
    ("R7 IT_MIN_BACK a 2,00 (vecchio listino)", MI, "IT_MIN_BACK = 1.00\n", "IT_MIN_BACK = 2.00\n"),
    ("R8 equivalente anche su mercati a 3+ esiti (len != 2 -> < 2)", MO,
     "    if len(runners) != 2:\n", "    if len(runners) < 2:\n"),
    ("R9 tolleranza dell'equivalenza a 1,00 EUR", LB,
     "TOLLERANZA_EQUIVALENZA = 0.01\n", "TOLLERANZA_EQUIVALENZA = 1.00\n"),
    ("R10 Safe fuori canale: rifiuto certo sotto 0,50 tolto", EX,
     "    if submin_fuori_canale and size < SUBMIN_IMPORTO_FINALE_MIN - 1e-9:\n",
     "    if False:\n"),
    ("R11 Omega REST: regola d'ingresso 0,50 tolta", OM,
     "        _SUBMIN.verifica_importo_finale(side_l, target)\n",
     "        pass\n"),
    ("R12 worker: chiusura live sotto minimo torna al place diretto", LW,
     "    sotto_minimo_live = (\n        _is_live_mode(mode)\n",
     "    sotto_minimo_live = (\n        False\n"),
    ("R13 Safe: chiusure di nuovo esenti fuori canale", EX,
     "    sotto_minimo_chiusura = bool(min_live > 0 and size < min_live - 1e-9 and is_closing)\n",
     "    sotto_minimo_chiusura = False\n"),
    ("R14 riporto: quota media = quota mandata (non riportata al chiesto)", MO,
     '"size_matched": abbinato, "average_price_matched": (quota or 0.0),',
     '"size_matched": abbinato, "average_price_matched": d.get("average_price_matched"),'),
    ("R15 taglia rifiutata ricordata senza il modo (paper e live mischiati)", MO,
     '        chiave = (str(piano.get("mode")), str(riga["side"]).lower(),\n',
     '        chiave = ("x", str(riga["side"]).lower(),\n'),
]


def rossi():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf",
                        *TESTS], capture_output=True, text=True)
    f = sorted(x.split(" ")[1] for x in r.stdout.splitlines() if x.startswith("FAILED"))
    riga = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x][-1:]
    return set(f), (riga[0] if riga else r.stdout[-300:])


base, rb = rossi()
print("BASE:", rb, "| rossi preesistenti:", sorted(base), flush=True)
for nome, path, vecchio, nuovo in MUT:
    raw = open(path, "rb").read()
    testo = raw.decode("utf-8")
    if "\r\n" in testo:   # export con fine riga CRLF (core.autocrlf): ancore adattate
        vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
    if vecchio not in testo:
        print("%s: PUNTO NON TROVATO" % nome, flush=True)
        continue
    try:
        open(path, "wb").write(testo.replace(vecchio, nuovo, 1).encode("utf-8"))
        f, riga = rossi()
        nuovi = sorted(f - base)
        print("%s: %s | %s | nuovi rossi: %s" % (
            nome, "ROSSO" if nuovi else "VERDE (SOPRAVVIVE)", riga, nuovi[:6]), flush=True)
    finally:
        open(path, "wb").write(raw)
fin, rf = rossi()
print("RIPRISTINO:", rf, "| uguale alla base:", fin == base, flush=True)
