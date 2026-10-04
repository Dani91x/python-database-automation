"""04/10/2026 - Falsificazione del cantiere Safe/Omega (punte a multipli di 0,50 e residuo
non ritentato). Ogni mutazione: applicata, test lanciati, file ripristinato con
``git checkout`` dal commit, verificato ``git diff --quiet``. ASCII-only.

Uso (dalla radice del worktree, a lavoro committato): python <questo file> [M1 M2 ...]
"""
import io
import re
import subprocess
import sys

PY = sys.executable
TEST = ["Betfair/safe_strategy/tests/test_punte_multiple_050_2026_10_04.py",
        "Betfair/omega/tests/test_punte_multiple_050_omega_2026_10_04.py"]

EX = "Betfair/safe_strategy/execution.py"
OMK = "Betfair/omega/omega_market.py"
BS = "Betfair/safe_strategy/bot_service.py"
OSV = "Betfair/omega/omega_service.py"

M = [
    ("M1 REST senza arrotondamento", OMK,
     "        size_f = float(_v.legalized_size)\n", "        pass\n"),
    ("M2 REST senza dichiarazione", OMK,
     "        punta_050=punta_050,\n    )", "        punta_050=None,\n    )"),
    ("M3 place senza arrotondamento", EX,
     "    if v.via != _MI.VIA_DIRETTA or v.residuo <= 0.0:\n        return size",
     "    if True:\n        return size"),
    ("M4 place: esito senza punta_050", EX,
     "    if punta and out.punta_050 is None:", "    if False:"),
    ("M5 close_trade senza pre-verifica del residuo", EX,
     "    if st[\"filled_ids\"] and _residuo_senza_via(", "    if False and _residuo_senza_via("),
    ("M6 residuo senza via sempre falso", EX,
     "    if _MI.importo_piazzabile(side, size).via != _MI.VIA_NESSUNA:\n        return False",
     "    if True:\n        return False"),
    ("M7 avviso a ogni giro", EX,
     "    if not critico:\n        return False\n    selezione",
     "    if False:\n        return False\n    selezione"),
    ("M8 residuo mai ricordato", EX,
     "    if isinstance(meta.get(RESIDUO_KEY), dict):\n        return\n    selezione",
     "    return\n    selezione"),
    ("M9 chiusura abbinata: residuo non ricordato subito", EX,
     "        if abbinata:\n            _ricorda_residuo(", "        if False:\n            _ricorda_residuo("),
    ("M10 Safe: candidati non saltano il residuo", BS,
     "        if X.residuo_ricordato(t):\n            continue\n        if str(t.get(\"strategy\")",
     "        if False:\n            continue\n        if str(t.get(\"strategy\")"),
    ("M11 Omega: candidati non saltano il residuo", OSV,
     "        if X.residuo_ricordato(t):\n            # 04/10/2026",
     "        if False:\n            # 04/10/2026"),
    ("M12 Safe _send_exit senza ramo del residuo", BS,
     "    if err == X.ERR_RESIDUO:\n        # 04/10/2026: il resto",
     "    if False:\n        # 04/10/2026: il resto"),
    ("M13 Omega green-up senza ramo del residuo", OSV,
     "    if err == X.ERR_RESIDUO:\n        # 04/10/2026: il resto di una chiusura gia' abbinata non ha nessuna via\n        # (sotto",
     "    if False:\n        # 04/10/2026: il resto di una chiusura gia' abbinata non ha nessuna via\n        # (sotto"),
    ("M14 terminale: punta non multipla accettata", "Betfair/order_exec.py",
     "    if side_up == \"BACK\" and float(_v.residuo or 0.0) > 0.0:", "    if False:"),
    ("M15 terminale: importo cambiato in silenzio", "Betfair/order_exec.py",
     "        raise ValueError(\n            f\"{_euro(size)}: la punta",
     "        size = sotto\n    if False:\n        raise ValueError(\n            f\"{_euro(size)}: la punta"),
    ("M16 Omega stato 'pending' invece di residual_dropped", OSV,
     "    if not covered and not res.get(\"pending_fill\") and X.residuo_ricordato(tr):",
     "    if False:"),
    ("M17 Omega automatico senza ramo del residuo", "Betfair/omega/omega_proposte.py",
     "    if err == X.ERR_RESIDUO:", "    if False:"),
    ("M18 combo arrotondata in silenzio", BS,
     "    if a_multiplo:\n", "    if False:\n"),
]

righe = []
solo = sys.argv[1:]
for nome, f, old, new in M:
    if solo and nome.split()[0] not in solo:
        continue
    s = io.open(f, encoding="utf-8", newline="").read()
    if "\r\n" in s:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    n = s.count(old)
    if n != 1:
        righe.append(f"{nome}: MUTAZIONE NON APPLICABILE (trovate {n})")
        continue
    io.open(f, "w", encoding="utf-8", newline="").write(s.replace(old, new))
    try:
        r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider",
                            "--no-header", "--tb=no"], capture_output=True, text=True)
        out = r.stdout
        fail = re.findall(r"^FAILED (\S+)", out, re.M)
        riass = out.strip().splitlines()[-1] if out.strip() else r.stderr[-200:]
        righe.append(f"{nome}: {riass}")
        for x in fail:
            righe.append(f"    rosso: {x.split('::', 1)[-1]}")
    finally:
        subprocess.run(["git", "checkout", "--", f], check=True)
    pulito = subprocess.run(["git", "diff", "--quiet", "--", f]).returncode == 0
    righe.append(f"    ripristino {f}: {'ok' if pulito else 'SPORCO!'}")
print("\n".join(righe))
