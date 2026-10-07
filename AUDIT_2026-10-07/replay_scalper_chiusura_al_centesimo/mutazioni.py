"""Falsificazione: una mutazione alla volta, test mirati, ripristino del file."""
import subprocess
import sys

W = "/home/user/python-database-automation/.claude/worktrees/agent-abbefe960f380ce4c"
SB = W + "/Betfair/stream/scalper/scalper_bot.py"
SN = W + "/Betfair/stream/scalper/sniper_bot.py"
T_NEW = "Betfair/stream/tests/test_scalper_chiusura_al_centesimo_2026_10_07.py"
T_S4 = "Betfair/stream/tests/test_cantiere_s4_scratch_firmato_esatto_2026_09_29.py"
T_SN = "Betfair/stream/tests/test_sniper_bot_2026_07_10.py"

MUT = [
    ("M1 punta: resto sotto 0,50 lasciato residuo", SB,
     "            if giu >= float(IT_BACK_MIN_STAKE) - 1e-9:",
     "            if False and giu >= float(IT_BACK_MIN_STAKE) - 1e-9:  # MUTAZIONE", [T_NEW, T_SN]),
    ("M2 parcheggio 2,00 scritto a mano", SB,
     '        placed_size=round(float(place_min_size("it", lato)), 2),',
     '        placed_size=2.0,  # MUTAZIONE', [T_NEW]),
    ("M3 parcheggio LAY sempre 1,01", SB,
     "    park = quota_parcheggio_lontano(lato, float(target))",
     "    park = 1.01 if lato == 'lay' else 1000.0  # MUTAZIONE", [T_NEW]),
    ("M4 pre-dimensione: aggiunta sotto il minimo saltata", SB,
     '            if (cs == "LAY" and self.exact_exits and not self.dry_run',
     '            if (False and cs == "LAY" and self.exact_exits and not self.dry_run  # MUTAZIONE', [T_NEW]),
    ("M5 scratch non aspetta la sequenza della close vecchia", SB,
     "                if (close is not None and self._vivo_o_in_volo(close)) or any(",
     "                if (close is not None and self._vivo_o_in_volo(close)) or False and any(  # MUTAZIONE", [T_S4]),
    ("M8 scratch: sequenza della close vecchia ne' ritirata ne' aspettata", SB,
     "                if slot.submins:\n                    self._cancel_submins(market, slot)\n                for o in slot.flatten_orders:\n                    self._cancel_if_live(market, o)\n                if (close is not None and self._vivo_o_in_volo(close)) or any(",
     "                if (close is not None and self._vivo_o_in_volo(close)) or False and any(  # MUTAZIONE", [T_S4]),
    ("M6 testo del residuo senza l'ordine", SB,
     "        g = compute_green(net_win, net_lose, quota) if quota else None",
     "        g = None  # MUTAZIONE", [T_NEW]),
    ("M7 sniper: parcheggio 2,00 (non usa stato_parcheggio)", SN,
     "            state = stato_parcheggio(side, price, rest)",
     "            state = stato_parcheggio(side, price, rest); state = __import__('dataclasses').replace(state, placed_size=2.0) if state else state  # MUTAZIONE",
     [T_NEW]),
]

sel = sys.argv[1:] or [m[0][:2] for m in MUT]
for nome, f, a, b, tests in MUT:
    if nome[:2] not in sel:
        continue
    orig = open(f).read()
    assert orig.count(a) == 1, (nome, orig.count(a))
    open(f, "w").write(orig.replace(a, b))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"],
                           cwd=W, capture_output=True, text=True, timeout=600)
        ultima = [x for x in r.stdout.splitlines() if "passed" in x or "failed" in x][-1:]
        print(nome, "->", "ROSSO" if r.returncode else "VERDE (NON CATTURATA)", ultima)
    finally:
        open(f, "w").write(orig)
