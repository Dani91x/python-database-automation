"""
value_engine — calcolatore di valore live per mercati calcio.

Moduli puri (prob/odds in -> prezzi out), nessun I/O salvo cli.py / calibrate.py.
  poisson_total  : mercati a gol totali (FT/HT) via Poisson sul tempo rimasto
  bivariate      : mercati legati al punteggio (1X2/DC/DNB/BTTS/CS) via Dixon-Coles  [task #5]
  devig          : rimozione del margine del banco
  pricing        : fair odds + quota minima ingresso back/lay (commissione)
  markets        : registry market_code -> evaluator
  goal_timing    : distribuzione non uniforme dei gol nel tempo  [task #6]
  cli            : interfaccia a riga di comando
"""
from .pricing import MarketPrice, price, value_flags  # noqa: F401
from .markets import evaluate, prob_total, is_total, TOTALS  # noqa: F401
