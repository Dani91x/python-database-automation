# Inserisce i blocchi x_add_*.md nelle consegne 03, 05, 06 (solo file dentro ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML)
import io, os
D = os.path.dirname(os.path.abspath(__file__))
R = os.path.dirname(os.path.dirname(D))
def rd(n):
    return io.open(os.path.join(D, n), encoding="utf-8").read()
def rw(n, s=None):
    p = os.path.join(R, n)
    if s is None:
        return io.open(p, encoding="utf-8").read()
    io.open(p, "w", encoding="utf-8").write(s)

s = rw("03_COMPONENTI_MATEMATICI.md")
assert "Sezioni 16-18" not in s
rw("03_COMPONENTI_MATEMATICI.md", s.rstrip("\n") + "\n" + rd("x_add_03.md"))

s = rw("05_ERRORI_DI_PROGETTAZIONE.md")
assert "| A4 |" not in s
a = "\n## MEDIO-ALTO"
assert s.count(a) == 1
i = s.index(a)
s = s[:i].rstrip("\n") + "\n" + rd("x_add_05_A4.md") + s[i:]
i = s.index("| M18 |"); j = s.index("\n", i)
s = s[:j + 1] + rd("x_add_05_M.md") + s[j + 1:]
a = "\n## Concordanza degli identificativi"
assert s.count(a) == 1
i = s.index(a)
s = s[:i].rstrip("\n") + "\n" + rd("x_add_05_B.md") + s[i:]
s = s.replace("| A1-A3, MA1-MA2, M1-M18, B1-B39 |", "| A1-A4, MA1-MA2, M1-M23, B1-B41 |")
rw("05_ERRORI_DI_PROGETTAZIONE.md", s)

s = rw("06_PIANO_MIGLIORAMENTI.md")
assert "| 29 |" not in s
a = "\n## Ordine consigliato"
i = s.index(a)
s = s[:i].rstrip("\n") + "\n" + rd("x_add_06.md") + s[i:]
s = s.replace("1 -> 2 -> 6 (sicurezza e coerenza, ore)",
              "1 -> 2 -> 6 (sicurezza e coerenza, ore) ; 29 e 31 da portare subito all'utente (Safe tennis e stop giornaliero)")
rw("06_PIANO_MIGLIORAMENTI.md", s)
print("ok")
