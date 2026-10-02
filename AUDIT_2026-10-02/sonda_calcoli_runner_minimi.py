"""Sonda del revisore (02/10): i 3 calcoli a mano, confronto col codice patchato, e la
banda INVALID_PROFIT_RATIO del parcheggio LAY (1 + 0,008/S al tick superiore).
Uso: dalla radice del worktree patchato, python AUDIT_2026-10-02/sonda_calcoli_runner_minimi.py"""
import bisect

from flumine.utils import PRICES_FLOAT

from Betfair.stream import live_order_build as LB
from Betfair.stream.trading import submin as S


def su(p):
    return PRICES_FLOAT[bisect.bisect_left(PRICES_FLOAT, p - 1e-9)]


def giu(p):
    return PRICES_FLOAT[bisect.bisect_right(PRICES_FLOAT, p + 1e-9) - 1]


print("=== caso 1: BANCA Over 0,43 @18 (mercato a 2 esiti)")
q, z = 18.0, 0.43
e = q / (q - 1)
s = round(z * (q - 1), 2)
print("a mano: quota esatta %.6f, tick su %s, tick giu %s, size %.2f" % (e, su(e), giu(e), s))
print("a mano: scarto se vince Over %+.4f, se vince Under %+.4f (con 1,05: %+.4f)" % (
    -s + z * (q - 1), s * (su(e) - 1) - z, s * (giu(e) - 1) - z))
v = LB.verdetto_minimi("it", "lay", q, z, altra_selezione=(2, 0.0))
print("codice:", v.esito, v.equivalente)
v3 = LB.verdetto_minimi("it", "lay", q, z, altra_selezione=None)
print("codice 3+ esiti:", v3.esito, (v3.motivo or "")[:90])

print("=== caso 2: PUNTA 0,80 @1,50")
q, z = 1.50, 0.80
e = q / (q - 1)
s = round(z * (q - 1), 2)
print("a mano: equivalente BANCA %.2f @ %s (tick giu di %.4f): sotto il minimo 1,00 -> trim" % (
    s, giu(e), e))
v = LB.verdetto_minimi("it", "back", q, z, altra_selezione=(2, 0.0))
print("codice 2 esiti:", v.esito, (v.motivo or "")[:120])
p = S.pianifica_submin(side="back", target_price=q, target_size=z, jurisdiction="it")
print("piano trim:", p.park_mode, p.park_price, p.park_size, "riduzione", p.size_reduction)
print("    (variante BANCA 0,80 @1,50 -> equivalente PUNTA %.2f @ %s)" % (
    round(0.8 * 0.5, 2), su(3.0)))
v = LB.verdetto_minimi("it", "lay", q, z, altra_selezione=(2, 0.0))
print("    codice:", v.esito, (v.motivo or "")[:100])
p = S.pianifica_submin(side="lay", target_price=q, target_size=z, jurisdiction="it")
print("    piano trim LAY:", p.park_mode, p.park_price, p.park_size, "riduzione", p.size_reduction,
      p.rifiuto)

print("=== caso 3: 2,00 @1,05")
for side in ("back", "lay"):
    v = LB.verdetto_minimi("it", side, 1.05, 2.0, altra_selezione=(2, 0.0))
    eq = LB.equivalente_lato_opposto(side, 1.05, 2.0)
    print(side, "codice:", v.esito, v.size, "| equivalente teorico:", eq.side, eq.size, "@",
          eq.price, "scarti", eq.scarto_se_vince_chiesta, eq.scarto_se_vince_altra)

print("=== parcheggio LAY: banda INVALID_PROFIT_RATIO (-20%/+25%) sulla liability arrotondata")
fuori = []
for c in range(50, 100):
    t = c / 100
    pq = S.quota_parcheggio_lontano("lay", t)
    L = t * (pq - 1)
    r = round(L + 1e-12, 2)
    dev = (r - L) / L
    if dev < -0.20 or dev > 0.25:
        fuori.append((t, pq, round(L, 4), r, round(dev * 100, 1)))
print("residui 0,50..0,99 fuori banda: %d su 50" % len(fuori))
for x in fuori:
    print("   residuo %.2f parcheggio %s liability %.4f -> %.2f (%+.1f%%)" % x)
