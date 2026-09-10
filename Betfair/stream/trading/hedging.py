"""hedging.py — planner PURO di copertura/flatten multi-posizione (Fase 5).

Per chi: l'azione ``cashout_all`` (global cash-out, benchmark Betting Toolkit) e la UI usano
``plan_flatten`` per chiudere IN UN COLPO tutte le posizioni aperte — di un mercato o
dell'INTERO evento (più mercati) — riusando ESATTAMENTE la matematica di trading/greenup
(``compute_greenup``, che pareggia W e L al best opposto). Nessun ordine viene piazzato qui:
si producono i piani (uno per selezione con esposizione ≠ 0) che il worker accoderà.

⚠️ Copertura cross-market "correlata" (es. Over 2.5 vs Correct Score): NON è offerta come
netting automatico — nessun tool la fa in modo affidabile e mescolare esposizioni di mercati
diversi senza un modello di correlazione è pericoloso. Qui il "global cash-out" chiude ogni
mercato PER CONTO SUO (flatten indipendente), che è il comportamento corretto e sicuro.

Logica pura: testabile a unità. È il worker a leggere W/L e best price freschi da flumine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .greenup import GreenupPlan, compute_greenup


@dataclass(frozen=True)
class PositionInput:
    """Esposizione MATCHED di una selezione + best price opposti (dal book), da flumine."""

    market_id: str
    selection_id: int
    handicap: float
    matched_if_win: float
    matched_if_lose: float
    best_back_price: Optional[float]
    best_lay_price: Optional[float]


@dataclass(frozen=True)
class FlattenLeg:
    market_id: str
    selection_id: int
    handicap: float
    plan: GreenupPlan          # actionable=False se la selezione è già piatta / prezzo assente


@dataclass(frozen=True)
class FlattenPlan:
    legs: Tuple[FlattenLeg, ...]
    note: str

    @property
    def actionable_legs(self) -> Tuple[FlattenLeg, ...]:
        """Solo le gambe che generano davvero un ordine (esposizione ≠ 0 e prezzo disponibile)."""
        return tuple(leg for leg in self.legs if leg.plan.actionable)

    @property
    def actionable(self) -> bool:
        return len(self.actionable_legs) > 0


def plan_flatten(
    positions: Sequence[PositionInput],
    fraction: float = 1.0,
) -> FlattenPlan:
    """Piano di chiusura (green-up) per OGNI posizione fornita, alla frazione ``fraction``.

    Una gamba per posizione: usa ``compute_greenup`` (identica alla cash-out di una singola
    selezione) sulle esposizioni e sul best opposto. Le posizioni già piatte o senza prezzo
    utile restano con ``plan.actionable=False`` (nessun ordine). ``fraction`` in (0,1] per un
    cash-out globale PARZIALE (clampata dentro compute_greenup).
    """
    legs: List[FlattenLeg] = []
    for pos in positions:
        plan = compute_greenup(
            matched_if_win=pos.matched_if_win,
            matched_if_lose=pos.matched_if_lose,
            best_back_price=pos.best_back_price,
            best_lay_price=pos.best_lay_price,
            fraction=fraction,
        )
        legs.append(
            FlattenLeg(
                market_id=pos.market_id,
                selection_id=pos.selection_id,
                handicap=pos.handicap,
                plan=plan,
            )
        )
    n_act = sum(1 for leg in legs if leg.plan.actionable)
    return FlattenPlan(
        legs=tuple(legs),
        note=f"flatten {n_act}/{len(legs)} posizioni (frazione {max(0.0, min(1.0, fraction)):.2f})",
    )


def net_open_pnl(
    positions: Sequence[PositionInput],
) -> Tuple[float, float]:
    """(worst_case, best_case) del P&L complessivo se si greenasse ORA tutto.

    Somma, su tutte le posizioni, il P&L bloccato dal green-up al best opposto (expected_if_win
    == expected_if_lose per selezione, entro arrotondamento). Utile per il display "P&L globale"
    del pulsante cash-out-all prima del commit. Le posizioni non chiudibili contribuiscono col
    loro W/L attuale non coperto (worst = min(W,L)).
    """
    worst = 0.0
    best = 0.0
    for pos in positions:
        plan = compute_greenup(
            matched_if_win=pos.matched_if_win,
            matched_if_lose=pos.matched_if_lose,
            best_back_price=pos.best_back_price,
            best_lay_price=pos.best_lay_price,
            fraction=1.0,
        )
        if plan.actionable:
            worst += min(plan.expected_if_win, plan.expected_if_lose)
            best += max(plan.expected_if_win, plan.expected_if_lose)
        else:
            # non chiudibile: resta esposto → worst = peggior esito, best = migliore
            worst += min(pos.matched_if_win, pos.matched_if_lose)
            best += max(pos.matched_if_win, pos.matched_if_lose)
    return round(worst, 2), round(best, 2)


# ---------------------------------------------------------------------------
# CASH-OUT PAREGGIATO (equal distribution) — semantica NATIVA "Cash Out" Betfair
# ---------------------------------------------------------------------------
# Differenza dal flatten indipendente (plan_flatten): lì ogni selezione viene chiusa PER
# CONTO SUO (W_i = L_i per selezione, ma il P&L del MERCATO resta diverso da esito a esito
# se le posizioni sono su più runner). Qui invece si risolve UN sistema unico sull'INTERO
# mercato: una gamba per runner (BACK dove serve backare, LAY dove serve layare) tale che
# il P&L FINALE sia lo STESSO su OGNI esito — è ciò che fa il pulsante "Cash Out" di
# Betfair e la "cash out all" di Bet Angel.
#
# MATEMATICA (esatta, nessuna approssimazione):
#   P_k = payoff del MERCATO se vince il runner k, PRIMA della copertura
#       = matched_if_win_k + somma_{j!=k} matched_if_lose_j
#   x_i = stake FIRMATO della gamba sul runner i: x_i > 0 = BACK x_i @ b_i,
#         x_i < 0 = LAY |x_i| @ l_i  (p_i = b_i se x_i>0, l_i se x_i<0).
#   Contributo della gamba i al payoff dell'esito k:  +x_i*(p_i-1) se k=i,  -x_i altrimenti.
#   Payoff finale:  F_k = P_k + x_k*p_k - somma_i x_i .
#   Imponendo F_k = E per ogni k e scegliendo
#       E = (somma_i P_i/p_i) / (somma_i 1/p_i)   ->   somma_i x_i = 0   e   x_k = (E - P_k)/p_k
#   si ottiene F_k = E ESATTO per ogni k (verificato numericamente nei test).
# Il lato di ogni gamba dipende dal SEGNO di x_i, che a sua volta dipende dal prezzo usato:
# si itera (max _EQ_MAX_ITER giri) finché i lati sono stabili.
#
# ATTENZIONE: ``positions`` deve contenere TUTTI i runner del mercato (anche quelli senza
# esposizione): il payoff P_k dipende dal matched_if_lose di OGNI altro runner — un runner
# mancante falserebbe l'intero sistema.

_EQ_MAX_ITER = 5             # giri massimi di stabilizzazione dei lati (back/lay)
_EQ_TOL = 0.01               # tolleranza di pareggio dichiarata (1 cent)
_EQ_GRID = 40                # campioni per lato nella ricerca di E che minimizza lo sbilancio


def market_payoffs(positions: Sequence[PositionInput]) -> Tuple[float, ...]:
    """P&L del MERCATO per ogni esito, PRIMA di qualunque copertura.

    ``P_k = matched_if_win_k + somma_{j!=k} matched_if_lose_j``: se vince il runner k si
    incassa il suo profit-se-vince e il profit-se-perde di TUTTI gli altri. Richiede
    l'elenco COMPLETO dei runner del mercato (vedi nota sopra).
    """
    total_lose = sum(float(p.matched_if_lose) for p in positions)
    return tuple(
        round(float(p.matched_if_win) + total_lose - float(p.matched_if_lose), 10)
        for p in positions
    )


def _eq_price(pos: PositionInput, want_back: bool) -> Optional[float]:
    """Prezzo utilizzabile per la gamba: BACK -> best available-to-back, LAY -> best
    available-to-lay (prezzi "taker", immediatamente abbinabili). None se assente/assurdo."""
    price = pos.best_back_price if want_back else pos.best_lay_price
    if price is None:
        return None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if not (p > 1.0) or p > 1000.0:
        return None
    return p


class EqualizeNotConverged(ValueError):
    """I lati (back/lay) delle gambe non si sono stabilizzati entro ``_EQ_MAX_ITER`` giri:
    almeno una gamba avrebbe il segno di un lato e il prezzo dell'ALTRO. Un ordine a quel
    prezzo sarebbe SBAGLIATO (quota non abbinabile in quel verso): rifiuto esplicito."""


def _eq_solve(
    payoffs: Sequence[float], positions: Sequence[PositionInput], e_shift: float = 0.0
) -> "Optional[Tuple[List[float], List[float], float]]":
    """Risolve il sistema di pareggio. Ritorna (x firmati, prezzi usati, E) oppure None se
    manca un prezzo NECESSARIO. ``e_shift`` sposta E (solo per la ricerca anti-arrotondamento).
    Solleva ``EqualizeNotConverged`` se, a fine iterazioni, il lato di una gamba NON coincide
    con quello del prezzo con cui e' stata calcolata (MEDIUM-4 review 10/09).
    """
    want_back = [True] * len(positions)     # ipotesi di partenza: tutti al prezzo BACK
    used_back: List[bool] = list(want_back)  # lati dei PREZZI con cui xs e' stato calcolato
    prices: List[float] = []
    xs: List[float] = []
    e_val = 0.0
    for _ in range(_EQ_MAX_ITER):
        prices = []
        for pos, wb in zip(positions, want_back):
            p = _eq_price(pos, wb)
            if p is None:
                # Prezzo del lato NECESSARIO assente: il pareggio non è calcolabile. MAI
                # ripiegare sul prezzo dell'altro lato (sarebbe una quota non abbinabile
                # in quel verso -> ordine a un prezzo sbagliato).
                return None
            prices.append(p)
        used_back = list(want_back)
        inv = sum(1.0 / p for p in prices)
        if inv <= 0.0:
            return None
        e_val = sum(pk / p for pk, p in zip(payoffs, prices)) / inv + float(e_shift)
        xs = [(e_val - pk) / p for pk, p in zip(payoffs, prices)]
        new_back = [x >= 0.0 for x in xs]
        if new_back == want_back:
            break
        want_back = new_back
    # Verifica FINALE (indipendente dal break): ogni gamba deve avere il lato del prezzo
    # con cui e' stata calcolata. Altrimenti niente gambe: mai un prezzo del lato sbagliato.
    if [x >= 0.0 for x in xs] != used_back:
        raise EqualizeNotConverged("equalize_non_convergente")
    return xs, prices, e_val


def _eq_final_payoffs(
    payoffs: Sequence[float], xs: Sequence[float], prices: Sequence[float]
) -> List[float]:
    """F_k = P_k + x_k*p_k - somma_i x_i, con gli x GIA' arrotondati al centesimo."""
    s = sum(xs)
    return [pk + x * p - s for pk, x, p in zip(payoffs, xs, prices)]


def _spread(values: Sequence[float]) -> float:
    """Massima differenza tra i payoff finali (0 = pareggio perfetto)."""
    if not values:
        return 0.0
    return round(max(values) - min(values), 6)


def _eq_round(xs: Sequence[float]) -> List[float]:
    return [round(x, 2) for x in xs]


def plan_equalize(
    positions: Sequence[PositionInput],
    *,
    fraction: float = 1.0,
    amount: Optional[float] = None,
) -> FlattenPlan:
    """Cash-out PAREGGIATO del mercato: una gamba per runner, P&L finale UGUALE su ogni esito.

    Argomenti:
      positions: TUTTI i runner del mercato (anche senza esposizione) con W/L matched e i
        best price dal book. Devono appartenere allo STESSO mercato (contratto: ValueError).
      fraction: scala TUTTE le size (1 = pareggio totale; 0.5 = metà strada). Con f<1 i
        payoff finali NON sono uguali (copertura parziale): F_k = (1-f)*P_k + f*E.
      amount: BUDGET TOTALE di stake in euro (somma |x_i|). Ha la PRECEDENZA su ``fraction``
        ed è CAPPATO al pareggio totale (chiedere più del necessario pareggia e basta).

    Ritorna un ``FlattenPlan``: se un prezzo necessario manca (book vuoto/sospeso) TUTTE le
    gambe sono non-actionable (rifiuto ESPLICITO: un pareggio a metà sarebbe peggio del nulla).
    Nei ``GreenupPlan`` di ogni gamba: ``expected_if_win`` = payoff del MERCATO se vince QUEL
    runner, ``expected_if_lose`` = peggior payoff tra gli ALTRI esiti (uguali fra loro a f=1).
    """
    positions = list(positions)
    if not positions:
        return FlattenPlan(legs=(), note="nessun runner: niente da pareggiare")
    market_ids = {p.market_id for p in positions}
    if len(market_ids) > 1:
        raise ValueError(
            "plan_equalize: le posizioni devono appartenere a UN SOLO mercato, "
            f"trovati {sorted(market_ids)}"
        )

    payoffs = market_payoffs(positions)

    def _reject(why: str) -> FlattenPlan:
        legs_ko = tuple(
            FlattenLeg(
                market_id=p.market_id, selection_id=p.selection_id, handicap=p.handicap,
                plan=GreenupPlan(None, None, None, round(pk, 2), round(pk, 2), why),
            )
            for p, pk in zip(positions, payoffs)
        )
        return FlattenPlan(legs=legs_ko, note=why)

    try:
        solved = _eq_solve(payoffs, positions)
    except EqualizeNotConverged:
        return _reject(
            "cash-out pareggiato NON calcolabile: equalize_non_convergente "
            "(lati back/lay instabili, nessun prezzo affidabile)"
        )
    if solved is None:
        return _reject("cash-out pareggiato NON calcolabile: prezzo mancante su una gamba")

    # Anti-arrotondamento: gli stake vanno al centesimo, quindi il pareggio ESATTO può
    # rompersi (su quote alte un centesimo di stake vale parecchi centesimi di payoff).
    # Si cerca la E che MINIMIZZA lo sbilancio residuo, entro la SOLA granularità imposta
    # dall'arrotondamento (+-0.01*max(p)): il P&L non si sposta oltre il costo del round.
    best = solved
    best_spread = _spread(_eq_final_payoffs(payoffs, _eq_round(solved[0]), solved[1]))
    if best_spread > _EQ_TOL:
        span = 0.01 * max(solved[1])
        for i in range(-_EQ_GRID, _EQ_GRID + 1):
            if i == 0:
                continue
            try:
                cand = _eq_solve(payoffs, positions, e_shift=span * i / _EQ_GRID)
            except EqualizeNotConverged:
                continue        # candidato instabile: si scarta, resta la soluzione base
            if cand is None:
                continue
            spread = _spread(_eq_final_payoffs(payoffs, _eq_round(cand[0]), cand[1]))
            if spread < best_spread - 1e-9:
                best_spread = spread
                best = cand
    xs, prices, e_val = best

    # Scala: amount (budget totale) VINCE su fraction; entrambi cappati al pareggio totale.
    scale = max(0.0, min(1.0, float(fraction) if fraction is not None else 1.0))
    scale_note = f"frazione {scale:.2f}"
    if amount is not None:
        total_abs = sum(abs(x) for x in xs)
        try:
            amt = float(amount)
        except (TypeError, ValueError):
            amt = -1.0
        if not (amt > 0.0):
            return _reject(f"cash-out pareggiato: amount non valido ({amount!r})")
        if total_abs <= 0.0:
            return _reject("cash-out pareggiato: mercato gia' pareggiato (nessuno stake)")
        scale = min(1.0, amt / total_abs)
        scale_note = (
            f"budget {amt:.2f} su {total_abs:.2f} totali"
            + (" (CAPPATO al pareggio totale)" if amt >= total_abs else "")
        )

    xs_final = _eq_round([x * scale for x in xs])
    finals = _eq_final_payoffs(payoffs, xs_final, prices)
    residual = _spread(finals)

    legs: List[FlattenLeg] = []
    for idx, (pos, x, price, fk) in enumerate(zip(positions, xs_final, prices, finals)):
        others = [f for j, f in enumerate(finals) if j != idx]
        worst_other = round(min(others), 2) if others else round(fk, 2)
        if abs(x) < 0.01:
            plan = GreenupPlan(
                None, None, None, round(fk, 2), worst_other,
                "gamba non necessaria (size sotto il centesimo)",
            )
        else:
            side = "back" if x > 0 else "lay"
            plan = GreenupPlan(
                side=side, price=price, size=round(abs(x), 2),
                expected_if_win=round(fk, 2), expected_if_lose=worst_other,
                note=f"{side.upper()} {abs(x):.2f}@{price} (pareggio E={e_val:.2f})",
            )
        legs.append(
            FlattenLeg(
                market_id=pos.market_id, selection_id=pos.selection_id,
                handicap=pos.handicap, plan=plan,
            )
        )
    n_act = sum(1 for leg in legs if leg.plan.actionable)
    note = (
        f"pareggio {n_act}/{len(legs)} gambe, P&L finale {min(finals):.2f}..{max(finals):.2f} "
        f"({scale_note}; sbilancio residuo {residual:.2f})"
    )
    return FlattenPlan(legs=tuple(legs), note=note)
