"""04/10/2026 - Rinumera i test della traduzione di Safe e Omega (Ashdod: banca Over 0,43
@18 -> punta Under 7,31 @1,06) sulla regola delle punte: banca Over 0,25 @19 -> punta
Under 4,50 @1,06, gli stessi numeri dei test del runner gia' su master
(``test_runner_minimi_correzioni_2026_10_02.py``). Sostituzioni letterali, una volta
sola; chi lo usa rilegge il diff. ASCII-only.

Uso: python rinumera_tradotti_punte_050.py <file> [<file> ...]
"""
import io
import sys

SOST = [
    ("7.74", "4.75"), ("7,74", "4,75"),
    ("0.4386", "0.27"), ("0,4386", "0,27"),
    ("7.31", "4.5"), ("7,31", "4,50"),
    ("0.43", "0.25"), ("0,43", "0,25"),
    ("0.44", "0.27"), ("0,44", "0,27"),
    ("18.0", "19.0"), ("@18", "@19"), ("/18 ", "/19 "), ("x 18 ", "x 19 "),
    ("17.5", "18.5"),
    ("matched=3.66, remaining=3.65", "matched=2.25, remaining=2.25"),
]

for path in sys.argv[1:]:
    with io.open(path, encoding="utf-8", newline="") as f:
        t = f.read()
    for a, b in SOST:
        t = t.replace(a, b)
    # liability della banca chiesta: 0,25 x (19 - 1)
    t = t.replace("round(0.25 * 17.0, 2)", "round(0.25 * 18.0, 2)")
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(t)
    print("ok", path)
