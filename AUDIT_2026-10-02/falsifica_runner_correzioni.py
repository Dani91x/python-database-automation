"""Falsificazione di RUNNER_MINIMI_CORREZIONI (02/10/2026).

Tre famiglie, tutte rilanciate sullo STESSO set di test (sotto):
  * C1-C19: una mutazione per ogni correzione nuova (punti 1-10);
  * M1-M8: le 8 del delegato del 01/10 (ancore aggiornate dove il codice e' cambiato);
  * R1-R15: le 15 del revisore del 02/10 (R3 riscritta sulla nuova quota di parcheggio).
Ogni mutazione deve far diventare ROSSO almeno un test che sulla base e' verde.

Uso (dalla radice di un EXPORT ISOLATO dell'albero, NON dal worktree: nel worktree i
test risalgono al .env del checkout principale):
    git archive -o corr.tar HEAD Betfair tactical_engine value_engine \
        market_intelligence Prediction tools football_data_scraper ":(glob)*.py"
    mkdir corr && tar -xf corr.tar -C corr && cd corr
    <python> falsifica_runner_correzioni.py
Ripristino byte per byte; ancore adattate a CRLF se l'export e' CRLF (core.autocrlf)."""
import subprocess
import sys

TESTS = [
    "Betfair/stream/tests/test_runner_minimi_correzioni_2026_10_02.py",
    "Betfair/stream/tests/test_runner_minimi_chiusure_2026_10_01.py",
    "Betfair/stream/tests/test_live_order_build.py",
    "Betfair/stream/tests/test_submin.py",
    "Betfair/stream/tests/test_submin_nucleo_2026_09_17.py",
    "Betfair/stream/tests/test_motore_ordini_2026_09_24.py",
    "Betfair/stream/tests/test_cashout_pro_2026_09_10.py",
    "Betfair/stream/tests/test_live_order_worker.py",
    "Betfair/safe_strategy/tests/test_audit_2026_09_11.py",
    "Betfair/safe_strategy/tests/test_execution.py",
    "Betfair/safe_strategy/tests/test_bot_service.py",
    "Betfair/safe_strategy/tests/test_safe_kill_switch_rest_o1_2026_09_24.py",
    "Betfair/safe_strategy/tests/test_p_blocco3_2026_09_28.py",
    "Betfair/omega/test_place_and_trim_2026_09_13.py",
    "Betfair/omega/test_omega_greenup_2026_09_10.py",
    "Betfair/omega/test_omega_audit_2026_09_11.py",
]
LB = "Betfair/stream/live_order_build.py"
MO = "Betfair/stream/motore_ordini.py"
SU = "Betfair/stream/trading/submin.py"
MI = "Betfair/stream/trading/minimi_it.py"
EX = "Betfair/safe_strategy/execution.py"
OM = "Betfair/omega/omega_market.py"
LW = "Betfair/stream/live_order_worker.py"
OE = "Betfair/order_exec.py"

MUT = [
    # ---------------- correzioni del 02/10 ----------------
    ("C1 p1 paper: la gamba di chiusura sotto minimo torna DIRETTA in paper", LW,
     "    sotto_minimo = (\n        size is not None\n",
     "    sotto_minimo = (\n        _is_live_mode(mode)\n        and size is not None\n"),
    ("C2 p1 paper: la chiusura sotto minimo si costruisce in paper", LW,
     "    del mode  # stessa decisione in ogni modalita'\n"
     "    if float(size) < _sub_minimum_floor(side) - 1e-9:\n",
     "    if _is_live_mode(mode) and float(size) < _sub_minimum_floor(side) - 1e-9:\n"),
    ("C3 p2 evento asincrono/dispatch senza codice", MO,
     "            extra.update(_estremi_errore(errore))\n", "            pass\n"),
    ("C4 p2 riga di coda senza error_code", LW,
     '    result["error_code"] = codice_errore(str(ex))\n', "    pass\n"),
    ("C5 p2 codice: solo il prefisso (codice in mezzo al testo perso)", MO,
     "    for c in _CODICI_NEL_TESTO:\n        if c in s:\n            return c\n", ""),
    ("C6 p3 cancel parziale NON convertito", MO,
     '            riga["size_reduction"] = r_vera\n', "            pass\n"),
    ("C7 p3 cancel parziale: floor 0,50 e banda tolti", MO,
     "            if residuo < SUBMIN_IMPORTO_FINALE_MIN - 1e-9 \\\n"
     "                    or not rendimento_in_banda(residuo, prezzo_vero):\n",
     "            if False:\n"),
    ("C8 p3 replace dell'ordine vero alla quota del chiesto", MO,
     '        piano["azione"] = "cancel"\n', "        return\n"),
    ("C9 p3 nuovo place prima del cancel confermato", MO,
     "            terminale = ordine is None or _status_name(ordine) in _STATI_TERMINALI_ORDINE\n",
     "            terminale = True\n"),
    ("C10 p5 runner non ACTIVE ammesso", MO,
     '        if st != "ACTIVE":\n            return None\n', ""),
    ("C11 p5 number_of_winners ignorato", MO,
     "            if int(nw) != 1:\n                return None\n", "            pass\n"),
    ("C12 p6 banda: tetto +25% allargato", SU,
     "BANDA_PROFIT_RATIO = (0.80, 1.25)\n", "BANDA_PROFIT_RATIO = (0.80, 1.40)\n"),
    ("C13 p6 banda: limite -20% tolto", SU,
     "BANDA_PROFIT_RATIO = (0.80, 1.25)\n", "BANDA_PROFIT_RATIO = (0.0, 1.25)\n"),
    ("C14 p6 ordine finale fuori banda non rifiutato", SU,
     "    if not rendimento_in_banda(tsize, tick):\n", "    if False:\n"),
    ("C15 p6 parcheggio = 1+0,008/S (la regola del 01/10)", SU,
     "        if rendimento_in_banda(t, p):\n            return float(p)\n",
     "        return float(p)\n"),
    ("C16 p7 REST diretto di omega senza guardia", OM,
     "    if not _v.valid:\n        raise PlaceRifiutato(\n",
     "    if False:\n        raise PlaceRifiutato(\n"),
    ("C17 p7 order_exec col vecchio minimo 2,00", OE,
     "from Betfair.stream.trading.minimi_it import IT_MIN_BACK as MIN_STAKE_EUR  # noqa: E402\n",
     "MIN_STAKE_EUR = 2.0\n"),
    ("C18 p9 green-up per sola selezione (doppia chiusura)", LW,
     "        if abs(w2) > 1e-9 or abs(l2) > 1e-9:\n", "        if False:\n"),
    ("C19 p10 CRITICAL a ogni ritento", EX,
     "    if ep is None:\n        registro[chiave] = [ts, 1]\n        return True, 1\n"
     "    ep[1] += 1\n    return False, ep[1]\n",
     "    if ep is None:\n        registro[chiave] = [ts, 1]\n        return True, 1\n"
     "    ep[1] += 1\n    return True, ep[1]\n"),
    ("C20 p8 D4: il freno non ferma la via sotto minimo", EX,
     "    blocco = None if is_closing else _live_brake()\n",
     "    blocco = None if (is_closing or submin_fuori_canale) else _live_brake()\n"),
    ("C21 p8 D7: chiusure sotto minimo di nuovo dirette fuori canale", EX,
     "    submin_fuori_canale = sotto_minimo or sotto_minimo_chiusura\n",
     "    submin_fuori_canale = sotto_minimo\n"),
    ("C22 p8 Omega gemelli: rifiuto locale sotto 0,50 tolto", EX,
     "    if submin_fuori_canale and size < SUBMIN_IMPORTO_FINALE_MIN - 1e-9:\n",
     "    if False:\n"),
    ("C23 p3 evento del cancel con la punta Under (non riportato al chiesto)", MO,
     "vedrebbe la punta Under)\n        piano[\"tradotto\"] = t\n",
     "vedrebbe la punta Under)\n        pass\n"),
    # ---------------- le 8 del delegato (01/10) ----------------
    ("M1 esenzione reduces_liability rimessa", LB,
     "    del reduces_liability  # informazione: mai un'esenzione dai minimi\n",
     "    if reduces_liability:\n        return MinStakeVerdict(True, round(float(size), 2), None)\n"),
    ("M2 floor della punta a 0,50 rimesso", LB,
     "        legal = round(float(size), 2)\n        if s == \"back\":\n",
     "        legal = round(float(size), 2)\n        if s == \"back\":\n"
     "            legal = _floor_to_step(legal, IT_BACK_STEP)\n"),
    ("M3 equivalente tick al piu' vicino", LB,
     "    tick = _tick_su(esatta) if lato == \"back\" else _tick_giu(esatta)\n",
     "    tick = get_nearest_price(esatta) if lato == \"back\" else _tick_giu(esatta)\n"),
    ("M4 eventi NON riportati al chiesto", MO,
     "                d = _riporta_tradotto(d, info[\"tradotto\"])\n", "                pass\n"),
    ("M5 nessun ripiego ai 0,50", MO,
     "            self._ripiega(s, nuova)\n            n += 1\n", "            pass\n"),
    ("M6 taglia rifiutata ritentata identica", MO,
     "        if not piano.get(\"submin\") and chiave in self._taglie_rifiutate:\n",
     "        if False:\n"),
    ("M7 floor del trim tolto dal verdetto", LB,
     "    if float(size) < SUBMIN_IMPORTO_FINALE_MIN - _EPS \\\n"
     "            or chiesta < SUBMIN_IMPORTO_FINALE_MIN - _EPS:\n",
     "    if False:\n"),
    ("M8 regola d'ingresso della macchina tolta", SU,
     "    if t < SUBMIN_IMPORTO_FINALE_MIN - _TOL:\n", "    if False:\n"),
    # ---------------- le 15 del revisore (02/10) ----------------
    ("R1 equivalente BANCA col tick in SU", LB,
     'tick = _tick_su(esatta) if lato == "back" else _tick_giu(esatta)', 'tick = _tick_su(esatta)'),
    ("R2 parcheggio abbinabile ammesso", SU,
     "    if passiva is not True and quota_non_abbinabile(",
     "    if False and quota_non_abbinabile("),
    ("R3 parcheggio LAY sempre a 1,01", SU,
     "    p = _tick_su(max(float(base), 1.0 + LIABILITY_MIN_RESIDUO_LAY / t))\n",
     "    return float(base)\n    p = None\n"),
    ("R4 rifiuto senza il residuo dichiarato", LB,
     '    residuo = (f"residuo {s.upper()} {float(size):.2f}@{price} NON piazzato: va dichiarato "\n'
     '               f"al trader (scelta sua: lasciarlo, oppure aumentare e richiudere)")\n',
     '    residuo = ""\n'),
    ("R5 paper: il motore salta i minimi", MO,
     '        if piano.get("minimi_originale") is None:\n',
     '        if piano.get("mode") == "paper":\n            return\n'
     '        if piano.get("minimi_originale") is None:\n'),
    ("R6 IT_MIN_LAY a 0,50", MI, "IT_MIN_LAY = 1.00\n", "IT_MIN_LAY = 0.50\n"),
    ("R7 IT_MIN_BACK a 2,00", MI, "IT_MIN_BACK = 1.00\n", "IT_MIN_BACK = 2.00\n"),
    ("R8 equivalente anche su 3+ esiti", MO,
     "    if len(runners) != 2:\n", "    if len(runners) < 2:\n"),
    ("R9 tolleranza dell'equivalenza a 1,00 EUR", LB,
     "TOLLERANZA_EQUIVALENZA = 0.01\n", "TOLLERANZA_EQUIVALENZA = 1.00\n"),
    ("R10 Safe fuori canale: rifiuto certo sotto 0,50 tolto", EX,
     "    if submin_fuori_canale and size < SUBMIN_IMPORTO_FINALE_MIN - 1e-9:\n",
     "    if False:\n"),
    ("R11 Omega REST: regola d'ingresso tolta", OM,
     "        _SUBMIN.verifica_importo_finale(side_l, target)\n", "        pass\n"),
    ("R12 worker: chiusura sotto minimo torna diretta (ogni modo)", LW,
     "    sotto_minimo = (\n        size is not None\n",
     "    sotto_minimo = (\n        False\n        and size is not None\n"),
    ("R13 Safe: chiusure di nuovo esenti fuori canale", EX,
     "    sotto_minimo_chiusura = bool(min_live > 0 and size < min_live - 1e-9 and is_closing)\n",
     "    sotto_minimo_chiusura = False\n"),
    ("R14 riporto: quota media non riportata al chiesto", MO,
     '"size_matched": abbinato, "average_price_matched": (quota or 0.0),',
     '"size_matched": abbinato, "average_price_matched": d.get("average_price_matched"),'),
    ("R15 taglia rifiutata senza il modo", MO,
     '        chiave = (str(piano.get("mode")), str(riga["side"]).lower(),\n',
     '        chiave = ("x", str(riga["side"]).lower(),\n'),
]


def rossi():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf",
                        *TESTS], capture_output=True, text=True)
    f = sorted(x.split(" ")[1] for x in r.stdout.splitlines() if x.startswith("FAILED"))
    e = sorted(x.split(" ")[1] for x in r.stdout.splitlines() if x.startswith("ERROR"))
    riga = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x
            or " error" in x][-1:]
    return set(f) | set(e), (riga[0] if riga else r.stdout[-300:])


if "--secco" in sys.argv:          # solo verifica delle ancore, nessun test
    for nome, path, vecchio, _n in MUT:
        t = open(path, "rb").read().decode("utf-8")
        v = vecchio.replace("\n", "\r\n") if "\r\n" in t else vecchio
        print(("ok      " if t.count(v) == 1 else "ANCORA %d " % t.count(v)) + nome)
    sys.exit(0)

base, rb = rossi()
print("BASE:", rb, "| rossi della base (esclusi dal confronto):", sorted(base), flush=True)
sopravvissute = []
for nome, path, vecchio, nuovo in MUT:
    raw = open(path, "rb").read()
    testo = raw.decode("utf-8")
    if "\r\n" in testo:
        vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
    if vecchio not in testo:
        print("%s: PUNTO NON TROVATO" % nome, flush=True)
        sopravvissute.append(nome + " (ancora)")
        continue
    try:
        open(path, "wb").write(testo.replace(vecchio, nuovo, 1).encode("utf-8"))
        f, riga = rossi()
        nuovi = sorted(f - base)
        if not nuovi:
            sopravvissute.append(nome)
        print("%s: %s | %s | nuovi rossi: %s" % (
            nome, "ROSSO" if nuovi else "VERDE (SOPRAVVIVE)", riga, nuovi[:5]), flush=True)
    finally:
        open(path, "wb").write(raw)
fin, rf = rossi()
print("RIPRISTINO:", rf, "| uguale alla base:", fin == base, flush=True)
print("SOPRAVVISSUTE:", sopravvissute or "nessuna", flush=True)
