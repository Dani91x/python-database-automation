"""Mutazioni per la falsificazione (tennis_pro superficie + varianti, 25/09).

Ogni mutazione sostituisce UNA stringa del codice, lancia i test nuovi e deve
dare ROSSO; poi il file torna identico dalla copia fatta PRIMA di mutare (mai
`git checkout`: nel worktree di un delegato ha gia' cancellato lavoro).

Uso (dalla radice del repo):
  python AUDIT_2026-09-25/mutazioni_tennis_pro_superficie_2026-09-25.py <cartella_copie>
"""
import io
import os
import shutil
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PY_T = ["Betfair/stream/tennis_scalper/tests/test_tennis_pro_superficie_2026_09_25.py",
        "Betfair/stream/tennis_live/tests/test_tennis_pro_superficie_runner_2026_09_25.py"]
FE_T = ["src/lib/tennisRegistry.test.ts",
        "src/components/tennis/TennisBotPanel.superficie.test.tsx"]

MUT = [
    ("M1 runner non passa la superficie: bot sempre erba",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "        params.update(sup.come_params())\n",
     "        pass  # MUTAZIONE\n", "py"),
    ("M2 mappa ignorata in risolvi",
     "Betfair/stream/tennis_scalper/superficie.py",
     "        for voce in MAPPA_TORNEI:\n",
     "        for voce in ():\n", "py"),
    ("M3 sconosciuto = erba invece di cemento dichiarato",
     "Betfair/stream/tennis_scalper/superficie.py",
     'SUPERFICIE_DEFAULT = "hard"', 'SUPERFICIE_DEFAULT = "grass"', "py"),
    ("M4 default trend False",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     'c.get("trend", True)', 'c.get("trend", False)', "py"),
    ("M5 default adapt False",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     'c.get("adapt", True)', 'c.get("adapt", False)', "py"),
    ("M6 default maker False",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     'c.get("maker", True)', 'c.get("maker", False)', "py"),
    ("M7 fonte non dichiarata nei params",
     "Betfair/stream/tennis_scalper/superficie.py",
     '            "surface_fonte": self.fonte,\n', "", "py"),
    ("M8 catalogo senza COMPETITION",
     "Betfair/stream/tennis_live/tennis_runner.py",
     '"EVENT", "COMPETITION"]', '"EVENT"]', "py"),
    ("M9 niente ripiego sulla riga di follow",
     "Betfair/stream/tennis_live/tennis_runner.py",
     '    if not meta.get("competition_name") and follow.get("competition_name"):',
     '    if False:', "py"),
    ("M10 parola non intera (halle dentro challenger)",
     "Betfair/stream/tennis_scalper/superficie.py",
     'return bool(p) and re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])",',
     'return bool(p) and re.search(re.escape(p),', "py"),
    ("M11 UI default varianti off",
     "frontend/src/lib/tennis.ts",
     "trend: 'on', adapt: 'on', maker: 'on' },",
     "trend: 'off', adapt: 'off', maker: 'off' },", "fe"),
    ("M12 UI fonte ignorata (sempre 'mappa')",
     "frontend/src/lib/tennis.ts",
     "const fonte = typeof p.surface_fonte === 'string' && p.surface_fonte ? p.surface_fonte : null;",
     "const fonte = 'mappa' as string | null;", "fe"),
    ("M13 UI surface 'grass' di nuovo nei default",
     "frontend/src/lib/tennis.ts",
     "            trend: 'on', adapt: 'on', maker: 'on' },",
     "            surface: 'grass', trend: 'on', adapt: 'on', maker: 'on' },", "fe"),
]


def _leggi(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _scrivi(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def main(copie):
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9",
               SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x", NO_COLOR="1",
               FORCE_COLOR="0")
    esiti = []
    for nome, rel, old, new, tipo in MUT:
        path = os.path.join(RADICE, rel)
        copia = os.path.join(copie, os.path.basename(rel))
        assert _leggi(copia) == _leggi(path), "copia non allineata: " + rel
        orig = _leggi(path)
        testo = orig.replace("\r\n", "\n")
        if old not in testo:
            esiti.append((nome, "NON APPLICABILE (stringa assente)"))
            continue
        mut = testo.replace(old, new, 1)
        if "\r\n" in orig:
            mut = mut.replace("\n", "\r\n")
        _scrivi(path, mut)
        try:
            if tipo == "py":
                r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                    *PY_T], cwd=RADICE, env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=600)
            else:
                r = subprocess.run("npx vitest run " + " ".join(FE_T),
                                   cwd=os.path.join(RADICE, "frontend"), env=env,
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=600, shell=True)
            righe = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
            sint = [x for x in righe if "passed" in x or "failed" in x][-2:]
            esiti.append((nome, ("ROSSO" if r.returncode != 0 else "VERDE (!!)")
                          + " | " + " / ".join(sint)))
        finally:
            shutil.copyfile(copia, path)
        assert _leggi(path) == orig, "ripristino fallito: " + rel
    for n, e in esiti:
        print("%-55s %s" % (n, e))


if __name__ == "__main__":
    main(sys.argv[1])
