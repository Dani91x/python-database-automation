"""Sposta il decoratore di J4 sulla funzione giusta. Lanciato una volta."""
import io

p = "Betfair/safe_strategy/certificazione_tennis.py"
s = io.open(p, encoding="utf-8").read()
dec = '''@_controllo("J4", "catalogo §7.4/7.6: il ref con cui si RILEGGE e' lo stesso del "
                  "piazzamento (`safe_tennis-t<id>` da F1 25/09, `safe-t<id>` legacy "
                  "sulle registrazioni pre-fix), e porta mercato e selezione",
            quando=lambda o: bool(o.ordini))
'''
assert s.count(dec) == 1
s = s.replace(dec, "")
old = "\ndef _j4(oss: Osservazione) -> Optional[str]:\n"
assert s.count(old) == 1
s = s.replace(old, "\n" + dec + "def _j4(oss: Osservazione) -> Optional[str]:\n")
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
