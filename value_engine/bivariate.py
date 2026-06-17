"""
bivariate.py — modello bivariato gol-casa / gol-trasferta per i mercati legati al PUNTEGGIO
(1X2, Doppia Chance, DNB, BTTS, Risultato Esatto), condizionabile su minuto + punteggio corrente.

OGNI FORMULA E' DERIVATA DALLA TEORIA E VERIFICATA CON MONTE CARLO (vedi test_bivariate_mc.py),
non copiata da file esistenti. Pure Python (niente numpy) per essere template 1:1 del port TypeScript.

CODICE "MONEY-GRADE": le funzioni FALLISCONO RUMOROSAMENTE (sollevano) su input incoerenti o fuori
dominio, invece di restituire numeri sbagliati in silenzio.

--- FORMULE E DERIVAZIONI ---
1) Poisson PMF:  P(X=k) = e^-λ · λ^k / k!  (gol di una squadra in un intervallo, intensita' costante).
2) Dixon-Coles (1997): correzione tau sulle 4 celle basse correlate (x=gol casa tasso λ, y=gol trasf tasso μ):
     τ(0,0)=1−λμρ ; τ(0,1)=1+λρ ; τ(1,0)=1+μρ ; τ(1,1)=1−ρ ; altrove 1.
   P(x,y)=Poisson(x;λ)·Poisson(y;μ)·τ(x,y), normalizzata. A ρ=0 → due Poisson indipendenti.
3) Condizionamento in-play: gol rimanenti in [t,T] ~ Poisson(λ·(T−t)/T). Punteggio finale = attuale +
   rimanenti; i mercati si leggono dalla distribuzione finale. (DC sulle celle basse dei gol rimanenti:
   esatto a t=0, approssimazione in-play.)
4) Derivazione (λ,μ) da quote pre-match de-viggate: bisezione su totale (per Over2.5) e supremazia
   (per Home), con VALIDAZIONE round-trip finale.
"""
from __future__ import annotations
from math import exp, factorial
from typing import Callable, Optional, List, Dict, Tuple

MAX_GOALS = 15            # P(Poisson(7) > 15) < 1e-4: sicuro per ogni lambda calcistico realistico
_ROUNDTRIP_TOL = 0.02     # tolleranza di convergenza per derive_lambdas


def pois(lam: float, k: int) -> float:
    """P(Poisson(lam) = k)."""
    if not isinstance(k, int) or k < 0:
        raise TypeError(f"k deve essere int >= 0, ricevuto {k!r}")
    if lam < 0:
        raise ValueError(f"lam deve essere >= 0, ricevuto {lam}")
    return exp(-lam) * (lam ** k) / factorial(k)


def dc_tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Correzione Dixon-Coles sulle 4 celle basse (x=gol casa, y=gol trasferta)."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam: float, mu: float, rho: float = -0.13,
                 max_goals: int = MAX_GOALS) -> List[List[float]]:
    """Matrice P(gol_casa=i, gol_trasferta=j), DC-corretta e normalizzata a somma 1.
    Solleva se la correzione DC esce dal dominio valido (tau < 0), segno di |rho|/lambda incompatibili."""
    lam = max(lam, 1e-6)
    mu = max(mu, 1e-6)
    ph = [pois(lam, i) for i in range(max_goals + 1)]
    pa = [pois(mu, j) for j in range(max_goals + 1)]
    M = [[ph[i] * pa[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    # tau clampato a >=0: per lambda fuori dominio DC (lam >= 1/|rho|, nonfisico per il calcio) la
    # correzione si annulla invece di crashare; un eventuale risultato distorto viene comunque
    # RIGETTATO dalla validazione round-trip in derive_lambdas. Cosi' la ricerca non si rompe mai.
    for (i, j) in ((0, 0), (0, 1), (1, 0), (1, 1)):
        M[i][j] *= max(0.0, dc_tau(i, j, lam, mu, rho))
    s = sum(sum(row) for row in M)
    return [[v / s for v in row] for row in M]


def _over(tot: Dict[int, float], line_floor: int) -> float:
    """P(gol totali >= line_floor + 1)."""
    return sum(v for k, v in tot.items() if k >= line_floor + 1)


def _markets_from_matrix(M: List[List[float]]) -> Dict[str, float]:
    """Probabilita' dei mercati dalla matrice del punteggio (finale)."""
    n = len(M)
    H = D = A = 0.0
    btts = 0.0
    tot: Dict[int, float] = {}
    for i in range(n):
        for j in range(n):
            p = M[i][j]
            if i > j:
                H += p
            elif i == j:
                D += p
            else:
                A += p
            if i >= 1 and j >= 1:
                btts += p
            tot[i + j] = tot.get(i + j, 0.0) + p
    ha = H + A
    if ha < 1e-9:                      # pareggio quasi certo: DNB indefinito
        dnb_h = dnb_a = float("nan")
    else:
        dnb_h = H / ha
        dnb_a = A / ha
    return {
        "H": H, "D": D, "A": A,
        "DC_1X": H + D, "DC_12": H + A, "DC_X2": D + A,
        "DNB_H": dnb_h, "DNB_A": dnb_a,
        "BTTS": btts, "BTTS_NO": 1.0 - btts,
        "O15": _over(tot, 1), "U15": 1 - _over(tot, 1),
        "O25": _over(tot, 2), "U25": 1 - _over(tot, 2),
        "O35": _over(tot, 3), "U35": 1 - _over(tot, 3),
    }


def _bisect(f: Callable[[float], float], lo: float, hi: float, it: int = 64) -> float:
    """Bisezione. SOLLEVA se non c'e' cambio di segno nel bracket (no fallback silenzioso:
    un estremo sbagliato qui significherebbe quote/probabilita' errate -> soldi persi)."""
    flo, fhi = f(lo), f(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0:
        raise ValueError(f"_bisect: nessun cambio di segno su [{lo}, {hi}] "
                         f"(f(lo)={flo:.6g}, f(hi)={fhi:.6g})")
    for _ in range(it):
        m = (lo + hi) / 2.0
        fm = f(m)
        if fm == 0.0:
            return m
        if flo * fm <= 0:
            hi = m
        else:
            lo, flo = m, fm
    return (lo + hi) / 2.0


def derive_lambdas(p_home: float, p_over25: float, rho: float = -0.13,
                   max_goals: int = MAX_GOALS) -> Tuple[float, float]:
    """Ricava (lambda_casa, mu_trasferta) dalle prob DE-VIGGATE di Home(1X2) e Over2.5.
    Itera bisezione su totale e supremazia, poi VALIDA il round-trip (solleva se non converge)."""
    p_home = min(max(p_home, 1e-4), 1 - 1e-4)
    p_over25 = min(max(p_over25, 1e-4), 1 - 1e-4)

    def over25_at(mu_tot: float, s: float) -> float:
        lam = max((mu_tot + s) / 2.0, 1e-6)
        mu = max((mu_tot - s) / 2.0, 1e-6)
        return _markets_from_matrix(score_matrix(lam, mu, rho, max_goals))["O25"]

    def home_at(mu_tot: float, s: float) -> float:
        lam = max((mu_tot + s) / 2.0, 1e-6)
        mu = max((mu_tot - s) / 2.0, 1e-6)
        return _markets_from_matrix(score_matrix(lam, mu, rho, max_goals))["H"]

    s = 0.0
    mu_tot = 2.5
    for _ in range(12):
        mu_tot = _bisect(lambda mt, _s=s: over25_at(mt, _s) - p_over25, 0.05, 15.0)
        s = _bisect(lambda x, _m=mu_tot: home_at(_m, x) - p_home, -12.0, 12.0)

    lam_out = max((mu_tot + s) / 2.0, 1e-6)
    mu_out = max((mu_tot - s) / 2.0, 1e-6)
    mk = _markets_from_matrix(score_matrix(lam_out, mu_out, rho, max_goals))
    if abs(mk["H"] - p_home) > _ROUNDTRIP_TOL or abs(mk["O25"] - p_over25) > _ROUNDTRIP_TOL:
        raise ValueError(
            f"derive_lambdas non converge (quote incoerenti?): "
            f"p_home={p_home:.4f}->{mk['H']:.4f}, p_over25={p_over25:.4f}->{mk['O25']:.4f}"
        )
    return lam_out, mu_out


def conditional_markets(lam: float, mu: float, rho: float, minute: float, gh: int, ga: int,
                        T: float = 90.0,
                        remaining_frac: Optional[Callable[[float, float], float]] = None,
                        max_goals: int = MAX_GOALS) -> Dict[str, float]:
    """Probabilita' dei mercati a punteggio dato (minuto, gol casa, gol trasferta).
    Gol rimanenti ~ Poisson(lambda * frazione tempo rimasto); punteggio finale = attuale + rimanenti."""
    frac = remaining_frac(minute, T) if remaining_frac else max(T - minute, 0.0) / T
    frac = max(0.0, min(1.0, frac))
    R = score_matrix(lam * frac, mu * frac, rho, max_goals)
    n = len(R)
    fn = n + max(gh, ga)
    M = [[0.0] * fn for _ in range(fn)]
    for a in range(n):
        for b in range(n):
            M[gh + a][ga + b] += R[a][b]
    return _markets_from_matrix(M)


# codici mercato a punteggio derivati dalla matrice (self-documenting, niente set stantio)
SCORE_MARKETS = frozenset(_markets_from_matrix([[1.0]]).keys())


def evaluate(market: str, *, p_home: float, p_over25: float, minute: float, gh: int, ga: int,
             rho: float = -0.13, T: float = 90.0,
             remaining_frac: Optional[Callable[[float, float], float]] = None) -> float:
    """Prob condizionata di un mercato a punteggio. p_home/p_over25 = prob pre-match DE-VIGGATE.
    Solleva ValueError se le quote sono incoerenti (vedi derive_lambdas)."""
    lam, mu = derive_lambdas(p_home, p_over25, rho)
    mk = conditional_markets(lam, mu, rho, minute, gh, ga, T=T, remaining_frac=remaining_frac)
    if market not in mk:
        raise KeyError(f"Mercato bivariato non gestito: {market}")
    return mk[market]
