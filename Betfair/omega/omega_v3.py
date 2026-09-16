# -*- coding: utf-8 -*-
"""omega_v3 — IL MOTORE PROBABILISTICO DI OMEGA V3, tutto in funzioni PURE.

Ordine dell'utente (16/09 sera): «1 ingresso HT (HALF_TIME_SCORE) + 1 ingresso nel 2T
(CORRECT_SCORE), lay 1 EUR; la selezione la decidono i DATI nel tempo e nel punteggio
reale, non la quota; qualsiasi selezione che dia profitto per decadimento del tempo o
per probabilita' nettamente a favore; il green-up passa dalla Control Room come
proposta e decide l'utente». E, del coordinatore: «trova la soluzione matematica e
probabilistica piu' avanzata e adatta a questo bot».

Qui non c'e' I/O, non c'e' database, non c'e' Betfair: si entra con numeri e si esce
con numeri. E' il modulo che il banco (`tools/banco_modelli.py`) mette alla prova e che
il servizio poi chiama: cio' che viene certificato E' cio' che opera.

===========================================================================
1. I MODELLI, E DA DOVE VENGONO
===========================================================================

Tutti stimano la stessa cosa: la distribuzione dei GOL RESIDUI (dh, da) dal minuto
corrente alla fine del periodo (45' per la gamba HT, 90' per quella FT), dato il
punteggio corrente. Da li' la probabilita' di OGNI selezione del mercato — scoreline
esatte e aggregati «Any Unquoted / Any Other Home|Away|Draw» — e' una somma di celle.

* `poisson`  — Poisson indipendenti (Maher 1982, *Statistica Neerlandica* 36: il primo
  a modellare i gol di calcio come due Poisson con forze di attacco/difesa). E' la
  base di confronto: nessuna dipendenza fra i due lati, nessuna sovradispersione.

* `dixon_coles` — Dixon & Coles (1997), *Applied Statistics* 46(2) 265-280. Aggiunge
  la correzione `tau` sulle quattro celle basse (0-0, 1-0, 0-1, 1-1), dove il Poisson
  indipendente sbaglia in modo sistematico. Per l'HALF_TIME_SCORE — un mercato in cui
  quelle quattro celle sono quasi tutta la massa — non e' un dettaglio.

* `dixon_robinson` — Dixon & Robinson (1998), *The Statistician* 47(3) 523-538:
  l'intensita' dei gol NON e' costante nella partita (cresce verso la fine dei tempi)
  e DIPENDE DAL PUNTEGZIO CORRENTE (chi e' sotto attacca, chi e' avanti si copre). Qui
  e' implementato come profilo temporale `exp(c1*u + c2*u^2)` sul minuto normalizzato
  u = t/90 piu' un termine di squilibrio `exp(-beta*d)` / `exp(+beta*d)` sulla
  differenza reti d = casa - ospite.

* `bivariato` — Karlis & Ntzoufras (2003), *The Statistician* 52(3) 381-393: Poisson
  bivariato X = X1 + X3, Y = X2 + X3, con una componente comune X3 ~ Poisson(lambda3)
  che introduce correlazione POSITIVA fra i due punteggi. Si misura se i dati la
  giustificano: sul calcio la correlazione osservata e' piccola e spesso negativa, e in
  quel caso e' `dixon_coles` lo strumento giusto, non questo.

* `gamma_poisson` — aggiornamento BAYESIANO coniugato dei lambda in gioco. Il tasso di
  ciascuna squadra e' incerto: Lambda ~ Gamma(a, a/mu). Vedere n gol in una frazione e
  di partita aggiorna il posteriore a Gamma(a + n, a/mu + e), e la distribuzione
  PREDITTIVA dei gol residui su esposizione r e' una BINOMIALE NEGATIVA
  NegBin(a + n, (a/mu + e)/(a/mu + e + r)). E' la forma esatta di cio' che oggi il
  codice v2 approssima con una mistura log-normale su lambda (`model_lambda_cv` 0,30,
  `omega_model.py:300`): stessa coda grassa, ma coniugata, in forma chiusa, e che
  IMPARA dai gol gia' visti invece di ignorarli. Sul parametro di forma `a` si legge
  direttamente la sovradispersione: cv = 1/sqrt(a).

* `fusione` — il MERCATO sa cose che noi non sappiamo (formazioni, infortuni, soldi).
  La probabilita' finale e' uno shrinkage in LOGIT fra modello e probabilita' implicita
  devigata del book, con peso `w` stimato PER FASCIA DI QUOTA sui nostri dati:
  logit(p) = w*logit(p_modello) + (1-w)*logit(p_mercato). E' la forma standard di
  combinazione di previsioni probabilistiche (Satopaa et al. 2014, *International
  Journal of Forecasting* 30(2): il pool logaritmico batte la media aritmetica quando
  le fonti sono calibrate ma non indipendenti). Il margine k di V3 si applica DOPO la
  fusione.

===========================================================================
2. IL CANCELLO — «le probabilita' dalla nostra parte», in numeri
===========================================================================

Con lay di stake s a quota L e commissione c: si incassa s(1-c) se il risultato NON
esce, si perde s(L-1) se esce. Il pareggio e' `p_implicita = (1-c)/(L-c)`. Imponendo
`P_nostra <= p_implicita / k` l'EV per gamba vale **s(1-c)(1 - 1/k)**, indipendente
dalla quota. k e' MISURATO (`tools/misura_k.py`, referto `K_MISURATO_2026-09-16.md`) e
non scende mai sotto 2: al prezzo di lay davvero disponibile il bias del mercato NON e'
dimostrato, quindi il margine deve coprire spread ed errore di modello.

===========================================================================
3. L'USCITA — proposta, mai esecuzione
===========================================================================

Nessuna chiusura automatica in V3. Si calcola il PROFITTO BLOCCABILE (chiudere un lay
vuol dire backare la stessa selezione: back_size = s*L/B, profitto = s*(1 - L/B) al
netto di commissione) e la sua TRAIETTORIA attesa: finche' il punteggio regge, il
tempo che passa fa scendere la probabilita' dell'evento e salire il prezzo di
riacquisto. Si propone quando l'EV di TENERE scende sotto il profitto bloccabile ORA,
tenuto conto del fatto che aspettare e' anche un'opzione (`ev_di_tenere` include il
massimo lungo la traiettoria). La proposta porta con se' i numeri e il motivo; a
premere APPROVA e' l'utente, dalla Control Room.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Costanti di struttura
# --------------------------------------------------------------------------
PERIODO_HT = "ht"           # mercato HALF_TIME_SCORE, si regola al 45'
PERIODO_FT = "ft"           # mercato CORRECT_SCORE, si regola al 90'
FINE_PERIODO = {PERIODO_HT: 45.0, PERIODO_FT: 90.0}
# recupero atteso: i gol del recupero contano nel punteggio del periodo
RECUPERO = {PERIODO_HT: 2.0, PERIODO_FT: 4.0}
MAX_GOL_RESIDUI = {PERIODO_HT: 6, PERIODO_FT: 10}
STAKE_STANDARD = 1.0        # ordine dell'utente: lay 1,00 EUR
K_MINIMO = 2.0              # §3.3: il margine non scende mai sotto 2

_SCORELINE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_ANY_RE = re.compile(r"any\s*(other|unquoted)", re.IGNORECASE)
_HOME_RE = re.compile(r"home", re.IGNORECASE)
_AWAY_RE = re.compile(r"away", re.IGNORECASE)
_DRAW_RE = re.compile(r"draw", re.IGNORECASE)


def parse_scoreline(nome: str) -> Optional[Tuple[int, int]]:
    """(casa, ospite) da "2 - 1"; None se non e' una scoreline numerica."""
    m = _SCORELINE_RE.match(nome or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def e_aggregato(nome: str) -> bool:
    """«Any Unquoted», «Any Other Home Win», ... — la coda vera del mercato."""
    return bool(_ANY_RE.search(nome or ""))


def direzione_aggregato(nome: str) -> Optional[str]:
    """'home' | 'away' | 'draw' | None (aggregato senza direzione, tipico dell'HT)."""
    if _DRAW_RE.search(nome or ""):
        return "draw"
    if _HOME_RE.search(nome or ""):
        return "home"
    if _AWAY_RE.search(nome or ""):
        return "away"
    return None


# --------------------------------------------------------------------------
# 1. PARAMETRI DEI MODELLI
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Parametri:
    """I parametri stimati sul banco (`tools/banco_modelli.py`).

    I default sono quelli del codice v2 (Poisson-DC con rho -0,13 e cv 0,30) cosi'
    che, senza un fit, V3 non sia peggio di V2. Il fit vero li sostituisce."""

    modello: str = "dixon_coles"
    # livello: gol totali attesi a partita intera (usato solo quando non arrivano
    # lambda dalla catena di produzione)
    gol_totali: float = 2.60
    quota_casa: float = 0.54            # frazione dei gol attesa alla squadra di casa
    # profilo temporale: intensita' ~ exp(c1*u + c2*u^2), u = minuto/90
    profilo_c1: float = 0.0
    profilo_c2: float = 0.0
    # Dixon-Coles
    rho: float = -0.13
    dc_sempre: bool = False             # True = tau anche con punteggio != 0-0
    # Dixon-Robinson: effetto della differenza reti sulle due intensita'
    beta_squilibrio: float = 0.0
    # effetto del numero di gol gia' visti sul livello (selezione/eterogeneita')
    eta_gol_visti: float = 0.0
    # Karlis-Ntzoufras: componente comune (correlazione positiva)
    lambda3: float = 0.0
    # Gamma-Poisson: forma del prior per lato (cv = 1/sqrt(a)); 0 = nessuna incertezza
    forma_gamma: float = 0.0
    # mistura log-normale su lambda, per confronto con il v2 (0 = spenta)
    cv_lambda: float = 0.0
    # fusione col mercato: peso del MODELLO in logit, per fascia di p_implicita
    peso_modello: float = 1.0
    peso_per_fascia: Tuple[Tuple[float, float], ...] = ()   # ((p_max, peso), ...) crescente

    def con(self, **kw: Any) -> "Parametri":
        return replace(self, **kw)


# --------------------------------------------------------------------------
# 2. PROFILO TEMPORALE (Dixon & Robinson 1998)
# --------------------------------------------------------------------------
def _integrale_profilo(t0: float, t1: float, c1: float, c2: float,
                       passi: int = 24) -> float:
    """Integrale di exp(c1*u + c2*u^2), u = t/90, fra t0 e t1 (Simpson).

    E' l'ESPOSIZIONE ai gol nell'intervallo, non un tempo: se l'intensita' cresce
    verso la fine, gli ultimi 10 minuti pesano piu' dei primi 10."""
    a, b = float(min(t0, t1)), float(max(t0, t1))
    if b - a <= 1e-9:
        return 0.0
    if abs(c1) < 1e-12 and abs(c2) < 1e-12:
        return (b - a) / 90.0
    n = max(2, int(passi) // 2 * 2)
    h = (b - a) / n
    tot = 0.0
    for i in range(n + 1):
        t = a + i * h
        u = t / 90.0
        w = 1.0 if i in (0, n) else (4.0 if i % 2 else 2.0)
        tot += w * math.exp(c1 * u + c2 * u * u)
    return tot * h / 3.0 / 90.0


def esposizione(minuto: float, periodo: str, p: Parametri) -> Tuple[float, float]:
    """(esposizione GIA' CONSUMATA dal via, esposizione RESIDUA fino a fine periodo),
    entrambe in frazioni dell'esposizione di una partita intera.

    Il periodo HT finisce al 45' + recupero: i gol del recupero del primo tempo
    contano nel punteggio del 45' (`RECUPERO`)."""
    fine = FINE_PERIODO[periodo] + RECUPERO[periodo]
    m = max(0.0, float(minuto))
    consumata = _integrale_profilo(0.0, min(m, fine), p.profilo_c1, p.profilo_c2)
    residua = _integrale_profilo(min(m, fine), fine, p.profilo_c1, p.profilo_c2)
    totale = _integrale_profilo(0.0, 90.0 + RECUPERO[PERIODO_FT], p.profilo_c1, p.profilo_c2)
    if totale <= 0:
        return 0.0, 0.0
    return consumata / totale, max(0.0, residua / totale)


# --------------------------------------------------------------------------
# 3. LA GRIGLIA DEI GOL RESIDUI
# --------------------------------------------------------------------------
def _tau_dc(h: int, a: int, lh: float, la: float, rho: float) -> float:
    """Correzione Dixon-Coles (1997) sulle quattro celle basse, mai negativa."""
    if h == 0 and a == 0:
        return max(0.0, 1.0 - lh * la * rho)
    if h == 1 and a == 0:
        return max(0.0, 1.0 + la * rho)
    if h == 0 and a == 1:
        return max(0.0, 1.0 + lh * rho)
    if h == 1 and a == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1.0))


def _negbin_pmf(k: int, forma: float, beta: float) -> float:
    """NegBin in parametrizzazione Gamma-Poisson: conteggio con prior Gamma(forma,
    beta) e esposizione 1 -> P(k) = C(forma+k-1,k) (beta/(beta+1))^forma (1/(beta+1))^k."""
    if forma <= 0:
        return 1.0 if k == 0 else 0.0
    q = beta / (beta + 1.0)
    return math.exp(math.lgamma(forma + k) - math.lgamma(forma) - math.lgamma(k + 1.0)
                    + forma * math.log(q) + k * math.log(1.0 - q))


def _pmf_bivariato(dh: int, da: int, l1: float, l2: float, l3: float) -> float:
    """Poisson bivariato (Karlis & Ntzoufras 2003), forma a convoluzione."""
    if l3 <= 0:
        return _poisson_pmf(dh, l1) * _poisson_pmf(da, l2)
    tot = 0.0
    for k in range(min(dh, da) + 1):
        tot += (_poisson_pmf(dh - k, l1) * _poisson_pmf(da - k, l2) * _poisson_pmf(k, l3))
    return tot


# Gauss-Hermite a 5 nodi: mistura log-normale su lambda (confronto col v2)
_GH5 = ((0.0, 0.9453087204829419), (0.9585724646138185, 0.3936193231522412),
        (-0.9585724646138185, 0.3936193231522412),
        (2.0201828704560856, 0.019953242059045913),
        (-2.0201828704560856, 0.019953242059045913))


def intensita_residue(*, minuto: float, punteggio: Tuple[int, int], periodo: str,
                      p: Parametri,
                      lambdas: Optional[Tuple[float, float]] = None) -> Tuple[float, float]:
    """(lambda residuo casa, lambda residuo ospite) fino a fine periodo.

    `lambdas` = i lambda PRE-PARTITA a 90' della catena di produzione
    (`omega_service._prematch_lambdas`). Senza, si usa il livello medio dei
    parametri: e' quello che serve al banco, dove i lambda per partita non
    esistono perche' i conteggi sono aggregati su 1,4 M di partite."""
    sh, sa = int(punteggio[0]), int(punteggio[1])
    consumata, residua = esposizione(minuto, periodo, p)
    if lambdas is not None:
        lh0, la0 = max(1e-6, float(lambdas[0])), max(1e-6, float(lambdas[1]))
    else:
        tot = max(1e-6, float(p.gol_totali))
        lh0, la0 = tot * p.quota_casa, tot * (1.0 - p.quota_casa)

    # Dixon & Robinson 1998: chi e' sotto attacca, chi e' avanti si copre.
    d = sh - sa
    sq_h = math.exp(-p.beta_squilibrio * d)
    sq_a = math.exp(+p.beta_squilibrio * d)
    # i gol gia' visti dicono qualcosa sul LIVELLO della partita (eterogeneita').
    # Nel modello Gamma-Poisson questo termine e' superfluo: lo fa il posteriore.
    liv = math.exp(p.eta_gol_visti * (sh + sa)) if p.modello != "gamma_poisson" else 1.0

    if p.modello == "gamma_poisson" and p.forma_gamma > 0:
        # posteriore coniugato per lato: Gamma(a + gol_visti, a/mu + esposizione_usata)
        a = float(p.forma_gamma)
        bh = a / lh0 + consumata
        ba = a / la0 + consumata
        # media posteriore x esposizione residua x effetto squilibrio
        lh = (a + sh) / max(1e-9, bh) * residua * sq_h
        la = (a + sa) / max(1e-9, ba) * residua * sq_a
        return max(1e-9, lh), max(1e-9, la)

    return (max(1e-9, lh0 * residua * sq_h * liv),
            max(1e-9, la0 * residua * sq_a * liv))


def griglia_residua(*, minuto: float, punteggio: Tuple[int, int], periodo: str,
                    p: Parametri,
                    lambdas: Optional[Tuple[float, float]] = None,
                    max_gol: Optional[int] = None) -> Dict[Tuple[int, int], float]:
    """P(gol residui = (dh, da)) fino a fine periodo, normalizzata sulla griglia.

    PURA e deterministica: stessi ingressi, stessa uscita, sempre."""
    sh, sa = int(punteggio[0]), int(punteggio[1])
    mg = int(max_gol if max_gol is not None else MAX_GOL_RESIDUI[periodo])
    lh, la = intensita_residue(minuto=minuto, punteggio=punteggio, periodo=periodo,
                               p=p, lambdas=lambdas)
    applica_tau = (p.modello in ("dixon_coles", "dixon_robinson", "gamma_poisson", "fusione")
                   and (p.dc_sempre or (sh == 0 and sa == 0)))

    griglia: Dict[Tuple[int, int], float] = {}

    if p.modello == "gamma_poisson" and p.forma_gamma > 0:
        # predittiva NegBin per lato (i due lati restano indipendenti dato il
        # posteriore: la dipendenza fra i punteggi la porta tau di Dixon-Coles)
        consumata, residua = esposizione(minuto, periodo, p)
        a = float(p.forma_gamma)
        if lambdas is not None:
            lh0, la0 = max(1e-6, float(lambdas[0])), max(1e-6, float(lambdas[1]))
        else:
            tot = max(1e-6, float(p.gol_totali))
            lh0, la0 = tot * p.quota_casa, tot * (1.0 - p.quota_casa)
        d = sh - sa
        rh = max(1e-12, residua * math.exp(-p.beta_squilibrio * d))
        ra = max(1e-12, residua * math.exp(+p.beta_squilibrio * d))
        # beta del posteriore riscalato sull'esposizione residua
        bh = (a / lh0 + consumata) / rh
        ba = (a / la0 + consumata) / ra
        ph = [_negbin_pmf(k, a + sh, bh) for k in range(mg + 1)]
        pa = [_negbin_pmf(k, a + sa, ba) for k in range(mg + 1)]
        for h in range(mg + 1):
            for x in range(mg + 1):
                v = ph[h] * pa[x]
                if applica_tau:
                    v *= _tau_dc(h, x, lh, la, p.rho)
                griglia[(h, x)] = v
    elif p.modello == "bivariato" and p.lambda3 > 0:
        l3 = float(p.lambda3) * esposizione(minuto, periodo, p)[1]
        l1, l2 = max(1e-9, lh - l3), max(1e-9, la - l3)
        for h in range(mg + 1):
            for x in range(mg + 1):
                griglia[(h, x)] = _pmf_bivariato(h, x, l1, l2, l3)
    elif p.cv_lambda and p.cv_lambda > 0:
        # mistura log-normale su lambda (il v2: `omega_model.residual_grid`)
        sigma = math.sqrt(math.log(1.0 + float(p.cv_lambda) ** 2))
        for x_node, w in _GH5:
            theta = math.exp(sigma * math.sqrt(2.0) * x_node - 0.5 * sigma * sigma)
            wk = w / math.sqrt(math.pi)
            lht, lat = lh * theta, la * theta
            # le marginali si calcolano UNA volta per nodo, non dentro la doppia
            # scansione: stessi numeri, 121 esponenziali invece di 242 per nodo
            vh = [_poisson_pmf(k, lht) for k in range(mg + 1)]
            va = [_poisson_pmf(k, lat) for k in range(mg + 1)]
            for h in range(mg + 1):
                for x in range(mg + 1):
                    v = vh[h] * va[x]
                    if applica_tau:
                        v *= _tau_dc(h, x, lht, lat, p.rho)
                    griglia[(h, x)] = griglia.get((h, x), 0.0) + wk * v
    else:
        vh = [_poisson_pmf(k, lh) for k in range(mg + 1)]
        va = [_poisson_pmf(k, la) for k in range(mg + 1)]
        for h in range(mg + 1):
            for x in range(mg + 1):
                v = vh[h] * va[x]
                if applica_tau:
                    v *= _tau_dc(h, x, lh, la, p.rho)
                griglia[(h, x)] = v

    tot = sum(griglia.values())
    if tot <= 0 or not math.isfinite(tot):
        return {}
    return {k: v / tot for k, v in griglia.items()}


def griglia_finale(*, minuto: float, punteggio: Tuple[int, int], periodo: str,
                   p: Parametri, lambdas: Optional[Tuple[float, float]] = None,
                   max_gol: Optional[int] = None) -> Dict[Tuple[int, int], float]:
    """Come `griglia_residua`, ma indicizzata sul PUNTEGGIO DI FINE PERIODO."""
    sh, sa = int(punteggio[0]), int(punteggio[1])
    res = griglia_residua(minuto=minuto, punteggio=punteggio, periodo=periodo,
                          p=p, lambdas=lambdas, max_gol=max_gol)
    return {(sh + h, sa + a): v for (h, a), v in res.items()}


# --------------------------------------------------------------------------
# 4. FUSIONE COL MERCATO (pool logaritmico in logit)
# --------------------------------------------------------------------------
def _logit(x: float) -> float:
    q = min(1.0 - 1e-12, max(1e-12, float(x)))
    return math.log(q / (1.0 - q))


def _inv_logit(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def peso_fusione(p_mercato: float, p: Parametri) -> float:
    """Peso del MODELLO nella fusione, per fascia di probabilita' di mercato.
    `peso_per_fascia` = ((soglia_p, peso), ...) in ordine crescente di soglia."""
    for soglia, peso in (p.peso_per_fascia or ()):
        if float(p_mercato) <= float(soglia):
            return max(0.0, min(1.0, float(peso)))
    return max(0.0, min(1.0, float(p.peso_modello)))


def fondi_col_mercato(p_modello: float, p_mercato: Optional[float], p: Parametri) -> float:
    """logit(p) = w*logit(modello) + (1-w)*logit(mercato). Senza prezzo di mercato
    resta il modello: non si inventa un'informazione che non c'e'."""
    if p_mercato is None or not math.isfinite(float(p_mercato)) or not (0.0 < float(p_mercato) < 1.0):
        return float(p_modello)
    w = peso_fusione(float(p_mercato), p)
    if w >= 1.0:
        return float(p_modello)
    return _inv_logit(w * _logit(p_modello) + (1.0 - w) * _logit(float(p_mercato)))


# --------------------------------------------------------------------------
# 5. LE PROBABILITA' DI OGNI SELEZIONE DEL MERCATO (aggregati compresi)
# --------------------------------------------------------------------------
def probabilita_selezioni(*, periodo: str, minuto: float, punteggio: Tuple[int, int],
                          nomi: Sequence[str], p: Parametri,
                          lambdas: Optional[Tuple[float, float]] = None,
                          max_gol: Optional[int] = None) -> Dict[str, float]:
    """P(la selezione si verifica a fine periodo | minuto, punteggio) per OGNI nome
    del mercato — scoreline esatte E aggregati.

    L'aggregato non e' «una selezione che non sappiamo leggere»: e' la somma delle
    celle della griglia che NON sono quotate e che vanno nella sua direzione. E' la
    coda vera del mercato, e il modello la sa gia' calcolare."""
    griglia = griglia_finale(minuto=minuto, punteggio=punteggio, periodo=periodo,
                             p=p, lambdas=lambdas, max_gol=max_gol)
    if not griglia:
        return {}
    quotate = {sc for sc in (parse_scoreline(n) for n in nomi) if sc is not None}
    fuori: Dict[str, float] = {}
    for nome in nomi:
        sc = parse_scoreline(nome)
        if sc is not None:
            fuori[nome] = float(griglia.get(sc, 0.0))
            continue
        if not e_aggregato(nome):
            continue                       # nome che non sappiamo leggere: si salta
        direzione = direzione_aggregato(nome)
        tot = 0.0
        for (h, a), v in griglia.items():
            if (h, a) in quotate:
                continue
            if direzione == "home" and not (h > a):
                continue
            if direzione == "away" and not (a > h):
                continue
            if direzione == "draw" and not (h == a):
                continue
            tot += v
        fuori[nome] = tot
    return fuori


# --------------------------------------------------------------------------
# 6. IL CANDIDATO: quale selezione si banca, e con quale margine
# --------------------------------------------------------------------------
def p_implicita(prezzo_lay: float, commissione: float) -> Optional[float]:
    """Pareggio del lay: (1-c)/(L-c). Identica a quella del v2 e a quella con cui
    k e' stato misurato: il margine si confronta con lo stesso metro."""
    try:
        L = float(prezzo_lay)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(L):
        return None
    c = max(0.0, min(0.5, float(commissione)))
    den = L - c
    if den <= 0:
        return None
    val = (1.0 - c) / den
    return val if 0.0 < val <= 1.0 else None


def liability(size: float, prezzo: float) -> float:
    return round(float(size) * (float(prezzo) - 1.0), 2)


def ev_gamba(p_nostra: float, prezzo: float, size: float, commissione: float) -> float:
    """EV di un lay: (1-P)*s*(1-c) - P*s*(L-1)."""
    P = max(0.0, min(1.0, float(p_nostra)))
    s = float(size)
    c = max(0.0, min(0.5, float(commissione)))
    return round((1.0 - P) * s * (1.0 - c) - P * s * (float(prezzo) - 1.0), 4)


@dataclass(frozen=True)
class RunnerV3:
    """Uno runner del book, come lo vede V3 (stesse chiavi di `omega_engine.ScoreRunner`)."""
    selection_id: int
    name: str
    lay_price: Optional[float] = None
    lay_size: float = 0.0
    back_price: Optional[float] = None
    back_size: float = 0.0


@dataclass(frozen=True)
class CandidatoV3:
    """La selezione scelta, con TUTTI i numeri della decisione. Il `motivo` e' una
    frase leggibile: e' quello che finisce nel referto e nella proposta."""
    selection_id: int
    name: str
    price: float
    size: float
    p_modello: float
    p_fusa: float
    p_empirica: Optional[float]
    n_empirico: Optional[int]
    p_nostra: float
    p_implicita: float
    k_usato: float
    margine: float                 # p_implicita / p_nostra: quante volte il margine chiesto
    ev: float
    liability: float
    motivo: str
    scartati: Tuple[Tuple[str, str], ...] = ()      # (nome, perche')


def candidato(*, periodo: str, runners: Sequence[RunnerV3], probabilita: Dict[str, float],
              k_tab: Optional[Dict[Tuple[str, str], float]] = None,
              secchio_di: Optional[Callable[[float], str]] = None,
              p_empirica: Optional[Callable[[str], Optional[Tuple[float, int]]]] = None,
              n_min_empirico: int = 200,
              commissione: float = 0.05,
              size: float = STAKE_STANDARD,
              min_liquidita: float = 1.0,
              distanza_minima_gol: int = 1,
              punteggio: Tuple[int, int] = (0, 0),
              p_max: float = 1.0,
              cap_liability_gamba: float = 0.0,
              k_default: float = K_MINIMO) -> Optional[CandidatoV3]:
    """La selezione da bancare, o None con i motivi degli scarti.

    REGOLA (ordine dell'utente + coordinatore): NON vince la quota piu' alta e non
    vince nemmeno la P piu' bassa in assoluto; vince la selezione con **P_nostra
    minima FRA QUELLE CHE PASSANO IL MARGINE** `P_nostra <= p_implicita / k`, con k
    misurato per secchio di p_implicita. Si puo' quindi bancare anche una quota
    bassa — «lo 0-0 HT a quota bassa se i dati confermano» — e si scarta una quota
    altissima se il margine non c'e'.

    `p_empirica(nome) -> (P, n)` e' il VETO DI CODA obbligatorio dove i dati
    esistono: la P usata e' il massimo fra modello fuso e dato storico. Con
    `n < n_min_empirico` la tabella non parla e NON si finge che abbia parlato:
    la selezione passa solo col modello, ma il motivo lo dice.
    """
    sh, sa = int(punteggio[0]), int(punteggio[1])
    migliore: Optional[CandidatoV3] = None
    scartati: List[Tuple[str, str]] = []

    for r in runners:
        nome = str(r.name or "")
        prezzo = r.lay_price
        if prezzo is None or not math.isfinite(float(prezzo)) or float(prezzo) <= 1.0:
            scartati.append((nome, "senza_lay"))
            continue
        lay_size = float(r.lay_size or 0.0)
        if not math.isfinite(lay_size) or lay_size < float(min_liquidita):
            scartati.append((nome, "liquidita_insufficiente"))
            continue
        sc = parse_scoreline(nome)
        if sc is not None:
            if sc[0] < sh or sc[1] < sa:
                scartati.append((nome, "irraggiungibile"))
                continue
            if (sc[0] - sh) + (sc[1] - sa) < int(distanza_minima_gol):
                # MAI il risultato corrente, e mai uno a un gol se la regola lo chiede
                scartati.append((nome, "troppo_vicino_al_punteggio"))
                continue
        p_mod = probabilita.get(nome)
        if p_mod is None or not math.isfinite(float(p_mod)):
            scartati.append((nome, "fuori_griglia"))
            continue
        p_imp = p_implicita(float(prezzo), commissione)
        if p_imp is None:
            scartati.append((nome, "prezzo_non_valido"))
            continue
        # fusione col mercato: il book sa cose che noi non sappiamo
        p_fusa = float(p_mod)
        emp_p: Optional[float] = None
        emp_n: Optional[int] = None
        if p_empirica is not None:
            got = p_empirica(nome)
            if got is not None:
                emp_p, emp_n = float(got[0]), int(got[1])
        # P_NOSTRA = la piu' ALTA fra le viste disponibili: sbagliare per difetto
        # costa la liability intera, per eccesso solo un'occasione persa
        p_nostra = p_fusa if emp_p is None else max(p_fusa, emp_p)
        if p_nostra > float(p_max):
            scartati.append((nome, "p_oltre_il_tetto"))
            continue
        etichetta = secchio_di(p_imp) if secchio_di is not None else ""
        k = float(k_default)
        if k_tab:
            k = max(float(k_default), float(k_tab.get((periodo, etichetta), k_default)))
        soglia = p_imp / max(1e-9, k)
        if p_nostra > soglia:
            scartati.append((nome, f"margine_insufficiente(k={k:g})"))
            continue
        if cap_liability_gamba and cap_liability_gamba > 0:
            if liability(size, float(prezzo)) > float(cap_liability_gamba) + 1e-9:
                scartati.append((nome, "oltre_il_cap_di_gamba"))
                continue
        margine = p_imp / max(1e-12, p_nostra)
        fonte = "modello"
        if emp_p is not None and emp_p >= p_fusa:
            fonte = f"dato storico (n={emp_n})"
        cand = CandidatoV3(
            selection_id=int(r.selection_id), name=nome, price=float(prezzo),
            size=float(size), p_modello=float(p_mod), p_fusa=float(p_fusa),
            p_empirica=emp_p, n_empirico=emp_n, p_nostra=float(p_nostra),
            p_implicita=float(p_imp), k_usato=k, margine=float(margine),
            ev=ev_gamba(p_nostra, float(prezzo), size, commissione),
            liability=liability(size, float(prezzo)),
            motivo=(f"P_nostra {p_nostra*100:.2f}% ({fonte}) contro p_implicita "
                    f"{p_imp*100:.2f}% a quota {float(prezzo):g}: margine {margine:.2f}x "
                    f"(serve {k:g}x, secchio {etichetta or 'n/d'})"),
        )
        if migliore is None or (cand.p_nostra, -cand.margine, cand.price) < (
                migliore.p_nostra, -migliore.margine, migliore.price):
            migliore = cand

    if migliore is None:
        return None
    return replace(migliore, scartati=tuple(scartati))


# --------------------------------------------------------------------------
# 7. LA FINESTRA D'INGRESSO
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Finestra:
    minuto_min: int
    minuto_max: int
    motivo: str


# Misurate sul banco e sulle 42 registrazioni (v. CHECKPOINT_V3): prima del minimo
# la griglia residua e' troppo piatta perche' una cella scenda sotto l'1 %; dopo il
# massimo il book del periodo si svuota e non c'e' piu' controparte.
FINESTRE_DEFAULT = {
    PERIODO_HT: Finestra(25, 44, "griglia abbastanza concentrata dal 25'; il book HT "
                                 "regge fino al fischio"),
    PERIODO_FT: Finestra(55, 85, "dopo il 45' il punteggio del 1T e' noto; oltre l'85' "
                                 "il CS resta spesso senza controparte"),
}


def finestra_ingresso(periodo: str, *, minuto_min: Optional[int] = None,
                      minuto_max: Optional[int] = None) -> Finestra:
    base = FINESTRE_DEFAULT[periodo]
    lo = base.minuto_min if minuto_min is None else int(minuto_min)
    hi = base.minuto_max if minuto_max is None else int(minuto_max)
    if lo > hi:
        lo, hi = hi, lo
    return Finestra(lo, hi, base.motivo)


def in_finestra(periodo: str, minuto: Optional[float], *, minuto_min: Optional[int] = None,
                minuto_max: Optional[int] = None) -> bool:
    if minuto is None:
        return False
    f = finestra_ingresso(periodo, minuto_min=minuto_min, minuto_max=minuto_max)
    return f.minuto_min <= float(minuto) <= f.minuto_max


# --------------------------------------------------------------------------
# 8. L'USCITA: profitto bloccabile e traiettoria attesa
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Posizione:
    """Una gamba aperta di V3 (sempre un LAY)."""
    periodo: str
    selection_name: str
    lay_price: float
    size: float
    punteggio_ingresso: Tuple[int, int] = (0, 0)
    minuto_ingresso: float = 0.0


@dataclass(frozen=True)
class Bloccabile:
    """Quanto si porterebbe a casa chiudendo ORA, e a quali condizioni."""
    profitto: float            # EUR netti di commissione, uguale in ogni esito
    back_price: float
    back_size: float
    attuabile: bool            # c'e' abbastanza controparte sul lato back?
    nota: str


def profitto_bloccabile(posizione: Posizione, *, back_price: Optional[float],
                        back_size: Optional[float] = None,
                        commissione: float = 0.05) -> Optional[Bloccabile]:
    """Chiudere un LAY vuol dire BACKARE la stessa selezione.

    Lay s a L, back sb a B: perche' il risultato sia lo stesso in entrambi gli esiti
    serve `sb = s*L/B`, e il profitto e' `s*(1 - L/B)` — positivo solo se B > L,
    cioe' se il prezzo si e' allontanato (per un layer e' la direzione buona).
    Al netto: la commissione si paga sulla vincita netta del mercato."""
    if back_price is None:
        return None
    try:
        B = float(back_price)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(B) or B <= 1.0:
        return None
    s, L = float(posizione.size), float(posizione.lay_price)
    sb = s * L / B
    lordo = s - sb
    c = max(0.0, min(0.5, float(commissione)))
    netto = round(lordo * (1.0 - c) if lordo > 0 else lordo, 4)
    disponibile = float(back_size or 0.0)
    attuabile = disponibile >= sb - 1e-9
    return Bloccabile(profitto=netto, back_price=B, back_size=round(sb, 2),
                      attuabile=attuabile,
                      nota=("controparte sufficiente" if attuabile else
                            f"servono {sb:.2f} EUR di back, ce ne sono {disponibile:.2f}"))


def ev_di_tenere(posizione: Posizione, *, p_evento: float,
                 commissione: float = 0.05) -> float:
    """EV di portare la gamba al settlement, con la P di oggi che l'evento esca."""
    return ev_gamba(p_evento, posizione.lay_price, posizione.size, commissione)


@dataclass(frozen=True)
class PuntoTraiettoria:
    minuto: float
    p_evento: float
    back_equo: float
    bloccabile_atteso: float


def traiettoria_bloccabile(posizione: Posizione, *, minuto: float,
                           punteggio: Tuple[int, int], p: Parametri,
                           lambdas: Optional[Tuple[float, float]] = None,
                           passo: int = 5, commissione: float = 0.05
                           ) -> List[PuntoTraiettoria]:
    """La TRAIETTORIA attesa del profitto bloccabile da qui a fine periodo.

    A ogni minuto futuro si stima, **condizionando sul fatto che il punteggio sia
    ancora questo** (che e' l'ipotesi in cui la posizione e' viva), la probabilita'
    che la selezione esca; da li' il prezzo di back EQUO (1/P) e il profitto che si
    riuscirebbe a bloccare. Non e' una previsione del book: e' il valore del tempo
    che passa, che e' l'unica cosa che nel frattempo lavora per noi.

    Serve a rispondere alla domanda giusta prima di proporre un'uscita: **aspettare
    vale piu' di chiudere adesso?**"""
    fine = FINE_PERIODO[posizione.periodo] + RECUPERO[posizione.periodo]
    fuori: List[PuntoTraiettoria] = []
    m = float(minuto)
    while m <= fine + 1e-9:
        griglia = griglia_finale(minuto=m, punteggio=punteggio, periodo=posizione.periodo,
                                 p=p, lambdas=lambdas)
        sc = parse_scoreline(posizione.selection_name)
        if sc is not None:
            pe = float(griglia.get(sc, 0.0))
        else:
            # aggregato: senza la lista dei nomi quotati non e' calcolabile in modo
            # onesto -> si dichiara None saltando il punto
            pe = float("nan")
        if math.isfinite(pe) and pe > 0:
            back_equo = 1.0 / pe
            b = profitto_bloccabile(posizione, back_price=back_equo,
                                    back_size=float("inf"), commissione=commissione)
            fuori.append(PuntoTraiettoria(minuto=m, p_evento=pe, back_equo=back_equo,
                                          bloccabile_atteso=(b.profitto if b else 0.0)))
        m += max(1, int(passo))
    return fuori


@dataclass(frozen=True)
class PropostaUscita:
    """La PROPOSTA che finisce in Control Room. Non e' un ordine: e' una domanda
    all'utente, con i numeri in mano."""
    proponi: bool
    motivo_codice: str
    profitto_bloccabile: float
    back_price: float
    back_size: float
    ev_tenere: float
    meglio_aspettare: bool
    bloccabile_max_atteso: float
    minuto_del_massimo: Optional[float]
    p_evento: float
    testo: str


def proposta_uscita(posizione: Posizione, *, minuto: float, punteggio: Tuple[int, int],
                    back_price: Optional[float], back_size: Optional[float],
                    p_evento: float, p: Parametri,
                    lambdas: Optional[Tuple[float, float]] = None,
                    commissione: float = 0.05,
                    margine_attesa: float = 0.02) -> PropostaUscita:
    """Propone (o no) di bloccare il profitto, con il motivo scritto.

    La regola NON e' una soglia fissa: si confrontano tre numeri —
      · `bloccabile` = cosa si porta a casa chiudendo adesso, certo;
      · `ev_tenere`  = cosa vale portarla al settlement con la P di adesso;
      · `bloccabile_max_atteso` = il massimo della traiettoria se il punteggio regge.
    Si propone quando chiudere adesso vale PIU' che tenere **e** piu' che aspettare
    (entro `margine_attesa`, il premio che si paga per la certezza). In tutti gli
    altri casi si tiene, e si dice perche' — la memoria del 12/09 («le chiusure
    distruggono valore») e' la ragione per cui questa funzione e' cosi' timida."""
    b = profitto_bloccabile(posizione, back_price=back_price, back_size=back_size,
                            commissione=commissione)
    ev_h = ev_di_tenere(posizione, p_evento=p_evento, commissione=commissione)
    traj = traiettoria_bloccabile(posizione, minuto=minuto, punteggio=punteggio, p=p,
                                  lambdas=lambdas, commissione=commissione)
    futuri = [t for t in traj if t.minuto > minuto + 1e-9]
    max_att = max((t.bloccabile_atteso for t in futuri), default=float("-inf"))
    min_max = None
    if futuri:
        best = max(futuri, key=lambda t: t.bloccabile_atteso)
        min_max = best.minuto
    if b is None:
        return PropostaUscita(False, "nessun_prezzo_di_back", 0.0, 0.0, 0.0, ev_h,
                              False, (0.0 if max_att == float("-inf") else max_att),
                              min_max, float(p_evento),
                              "nessun prezzo di back: non c'e' niente da bloccare")
    meglio_aspettare = bool(futuri and max_att > b.profitto + float(margine_attesa))
    if not b.attuabile:
        return PropostaUscita(False, "controparte_insufficiente", b.profitto, b.back_price,
                              b.back_size, ev_h, meglio_aspettare,
                              (0.0 if max_att == float("-inf") else max_att), min_max,
                              float(p_evento), b.nota)
    if b.profitto <= 0:
        return PropostaUscita(False, "bloccabile_non_positivo", b.profitto, b.back_price,
                              b.back_size, ev_h, meglio_aspettare,
                              (0.0 if max_att == float("-inf") else max_att), min_max,
                              float(p_evento),
                              f"chiudere ora vale {b.profitto:.2f} EUR: si tiene")
    if b.profitto < ev_h:
        return PropostaUscita(False, "tenere_vale_di_piu", b.profitto, b.back_price,
                              b.back_size, ev_h, meglio_aspettare,
                              (0.0 if max_att == float("-inf") else max_att), min_max,
                              float(p_evento),
                              f"bloccabile {b.profitto:.2f} EUR contro un EV di tenere "
                              f"di {ev_h:.2f} EUR: si tiene")
    if meglio_aspettare:
        return PropostaUscita(False, "aspettare_vale_di_piu", b.profitto, b.back_price,
                              b.back_size, ev_h, True,
                              max_att, min_max, float(p_evento),
                              f"bloccabile {b.profitto:.2f} EUR ora, ma se il punteggio "
                              f"regge al {min_max:.0f}' ci si attende {max_att:.2f} EUR")
    return PropostaUscita(True, "blocca_il_profitto", b.profitto, b.back_price,
                          b.back_size, ev_h, False,
                          (0.0 if max_att == float("-inf") else max_att), min_max,
                          float(p_evento),
                          f"chiudere ora blocca {b.profitto:.2f} EUR (back {b.back_price:g} "
                          f"per {b.back_size:.2f} EUR) contro un EV di tenere di "
                          f"{ev_h:.2f} EUR; aspettare non migliora "
                          f"({(max_att if max_att != float('-inf') else 0.0):.2f} EUR atteso)")
