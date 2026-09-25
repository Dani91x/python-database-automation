"""Falsificazione del PROFILO RAPIDO (25/09): rimessi i due reperti, il profilo
deve dire KO sullo scenario giusto. Ripristino dal contenuto salvato + sha1.

    python AUDIT_2026-09-25/strada_unica/falsifica_rapidi.py <data_dir>
"""
import hashlib
import os
import subprocess
import sys

MUT = [
    ("reperto 2 rimesso: FOK sotto il minimo", "safe_base", "R8",
     "Betfair/safe_strategy/execution.py",
     "            time_in_force=(None if sotto_minimo else PO.FOK),\n",
     "            time_in_force=PO.FOK,\n"),
    ("reperto 1 rimesso: nessuna base del primo seq", "omega", "R9",
     "Betfair/safe_strategy/porta_ordini.py",
     "        if self.seq_visto == 0 and not self._sopra:\n"
     "            self.seq_visto = seq - 1          # primo contatto: la base\n", ""),
]


def main() -> int:
    data_dir = sys.argv[1]
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x")
    ko = 0
    for nome, bot, scen, f, vecchio, nuovo in MUT:
        orig = open(f, encoding="utf-8").read()
        assert vecchio in orig, nome
        try:
            open(f, "w", encoding="utf-8").write(orig.replace(vecchio, nuovo, 1))
            r = subprocess.run([sys.executable, "-m", "Betfair.stream.backtest.certifica", bot,
                                "35760084", "--scenari", "rapidi", "--worker", "1",
                                "--data-dir", data_dir], env=env, capture_output=True,
                               text=True, timeout=300)
        finally:
            open(f, "w", encoding="utf-8").write(orig)
        ok_rip = (hashlib.sha1(open(f, encoding="utf-8").read().encode()).hexdigest()
                  == hashlib.sha1(orig.encode()).hexdigest())
        righe = [x for x in r.stdout.splitlines() if x.startswith(("KO ", "OK ", "N/A"))
                 and scen in x]
        rosso = r.returncode != 0 and any(x.startswith("KO ") for x in righe)
        if not rosso:
            ko += 1
        print("%s %-44s exit=%d %s | ripristino %s" % ("ROSSO " if rosso else "VERDE!", nome,
                                                      r.returncode, righe, "OK" if ok_rip
                                                      else "KO"))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
