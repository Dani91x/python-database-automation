"""pnl_mercato.py - P&L di MERCATO "se vince" su tutti gli ordini (comparto C, W1-C2, 09/10/2026).

Scopo: ``PosizioneMercato`` (contratto ``Betfair/nucleo/ordini/contratto.py``)
per UN mercato e UN modo: per ogni selezione il P&L se vince quella selezione
(Betfair "profit & loss if wins") su TUTTI gli ordini ABBINATI del mercato, back
e lay, totale e per autore; abbinato e prezzo medio per lato; esposizione
massima (la perdita peggiore fra gli esiti, <= 0).

Nessuna formula nuova, tutte RIUSATE o riprese riga per riga con test di parita':
  * per selezione, (se vince, se perde) = ``flumine.utils.calculate_matched_exposure``
    (la STESSA che usa ``Blotter.get_exposures`` -> ``matched_profit_if_win/lose``,
    e da cui partono il green-up ``trading/greenup.py`` e lo specchio
    ``betfair_live_positions``): si CHIAMA, non si copia;
  * per il mercato, il P&L se vince ``k`` = la formula del frontend
    ``frontend/src/lib/replayOperazioni.ts:189-197`` ``pnlSeVince``: back
    ``importo*(prezzo-1)`` se e' la sua selezione, altrimenti ``-importo``; lay
    l'opposto; somma su tutti gli abbinati, arrotondata al centesimo UNA volta;
  * prezzo medio per lato = ``flumine.utils.wap`` (media pesata sull'abbinato);
  * P&L bloccato chiudendo a un prezzo = ``frontend/src/lib/ladderMath.ts:10-13``
    ``lockedPnlAt`` (``L + (W-L)/p``), la stessa di ``greenup.compute_greenup``.

COMMISSIONE: NON applicata. Le viste di oggi per lo stesso numero (ladder
``lockedPnlAt``/``pnlSeVince``, ``blotter.get_exposures``) sono LORDE; la
commissione per ordine e' una regola del regolato (``reconcile_worker.
commissioni_per_ordine``, F-009) e resta li' (scheda F, nessuna regola cambiata).

QUANDO IL MODELLO "UN SOLO VINCITORE" VALE (revisione 09/10, G2 e M4): il tipo
del mercato dal book (``marketDefinition.bettingType`` = ``ODDS``), un solo
vincitore (``numberOfWinners`` = 1) e nessun handicap. Altrimenti (tipo assente,
asiatico anche con la sola linea 0,0, ``LINE``, piu' vincitori, handicap != 0)
``se_vince`` e ``se_vince_per_autore`` restano VUOTI e ``esposizione_massima``
e' la somma, linea per linea, della peggiore fra (se vince, se perde) di flumine
(stima prudente, dichiarata nei ``motivi``). Senza l'elenco dei runner
l'esposizione NON si calcola (``None``; ``NaN`` nella posizione del contratto):
mai l'esito fittizio "vince un runner senza ordini". Mai un numero inventato.

Entrate: ``OrdineConto`` (dal libro). Uscite: ``PosizioneMercato`` e, come
estensione dichiarata, ``EsposizioneSelezione`` (se vince / se perde della
selezione da sola, cio' che il ladder mostra per riga). NON fa: nessun I/O,
nessuna somma fra modi diversi (un ordine di un altro modo o mercato SOLLEVA),
nessun non abbinato (il worst case con i non abbinati resta a flumine).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from Betfair.nucleo.comuni import Modo
from Betfair.nucleo.ordini.contratto import OrdineConto, PosizioneMercato

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EsposizioneSelezione:
    """Estensione (W1-C2): la selezione DA SOLA, come ``blotter.get_exposures``:
    P&L degli abbinati se vince / se perde quella selezione (lordo)."""

    selection_id: int
    handicap: float
    se_vince: float
    se_perde: float


#: ``marketDefinition.bettingType`` per cui vale il modello "un solo vincitore"
#: (revisione 09/10, M4): ``ODDS``. ``LINE``, ``RANGE``, ``ASIAN_HANDICAP_*``
#: (anche con la sola linea 0,0: push e mezze vincite) NON sono supportati.
TIPI_UN_VINCITORE = frozenset({"ODDS"})


@dataclass(frozen=True)
class CalcoloPosizione:
    """La posizione e cio' che il calcolo dichiara (estensione W1-C2):

    * ``scartati``: abbinato senza prezzo medio > 1 (mai un prezzo inventato,
      PSB par. 7 n.3);
    * ``supportato``: il modello "un solo vincitore" vale (tipo ``ODDS``, un
      vincitore, nessun handicap); se no ``se_vince`` e' VUOTO e
      ``esposizione_massima`` e' la stima prudente linea per linea;
    * ``esposizione_massima``: ``None`` se non calcolabile (elenco dei runner
      ignoto: nella ``PosizioneMercato`` del contratto, che vuole un float, e'
      ``NaN``) -- revisione 09/10, G2: mai un numero fittizio;
    * ``motivi``: perche' non e' completa/supportata (tipo_ignoto, handicap,
      runner_ignoti, abbinato_mancante, ...);
    * ``solo_abbinato``: sempre True -- gli ordini NON abbinati non entrano
      nell'esposizione (la UI lo deve dire)."""

    posizione: PosizioneMercato
    scartati: Tuple[str, ...]
    a_linee: bool
    supportato: bool = True
    esposizione_massima: Optional[float] = None
    runner_noti: bool = False
    motivi: Tuple[str, ...] = ()
    solo_abbinato: bool = True


def _abbinati_validi(ordini: Sequence[OrdineConto]) -> Tuple[List[OrdineConto], List[str]]:
    buoni: List[OrdineConto] = []
    scartati: List[str] = []
    for o in ordini:
        if not o.abbinato or o.abbinato <= 0:
            continue
        if o.prezzo_medio is None or not o.prezzo_medio > 1.0:
            scartati.append(o.bet_id)
            continue
        buoni.append(o)
    return buoni, scartati


def esposizioni_per_selezione(ordini: Iterable[OrdineConto]) -> Dict[Tuple[int, float],
                                                                      EsposizioneSelezione]:
    """(selection_id, handicap) -> se vince / se perde degli ABBINATI, con la
    funzione di flumine (``calculate_matched_exposure``: arrotonda al centesimo
    per selezione, come il blotter)."""
    from flumine.utils import calculate_matched_exposure

    per_sel: Dict[Tuple[int, float], Tuple[List[Tuple[float, float]],
                                           List[Tuple[float, float]]]] = {}
    buoni, _ = _abbinati_validi(list(ordini))
    for o in buoni:
        mb, ml = per_sel.setdefault((int(o.selection_id), float(o.handicap)), ([], []))
        (mb if o.lato == "back" else ml).append((float(o.prezzo_medio or 0.0), float(o.abbinato)))
    out: Dict[Tuple[int, float], EsposizioneSelezione] = {}
    for (sid, hc), (mb, ml) in sorted(per_sel.items()):
        w, lo = calculate_matched_exposure(mb, ml)
        out[(sid, hc)] = EsposizioneSelezione(sid, hc, float(w), float(lo))
    return out


def pnl_se_vince(abbinati: Sequence[OrdineConto], vincitore: Optional[int]) -> float:
    """``pnlSeVince`` di ``replayOperazioni.ts:189-197``, riga per riga
    (``vincitore=None`` = vince un runner senza ordini). Non arrotondato."""
    v = 0.0
    for a in abbinati:
        suo = vincitore is not None and int(a.selection_id) == int(vincitore)
        importo = float(a.abbinato)
        prezzo = float(a.prezzo_medio or 0.0)
        if a.lato == "back":
            v += importo * (prezzo - 1) if suo else -importo
        else:
            v += -importo * (prezzo - 1) if suo else importo
    return v


def pnl_bloccato(prezzo: float, se_vince: float, se_perde: float) -> float:
    """``lockedPnlAt`` di ``ladderMath.ts:10-13``: P&L bloccato chiudendo
    l'intera posizione a ``prezzo`` (``prezzo <= 1`` -> non chiudibile -> L)."""
    import math

    if not math.isfinite(prezzo) or prezzo <= 1:
        return se_perde
    return se_perde + (se_vince - se_perde) / prezzo


def _media_pesata(coppie: List[Tuple[float, float]]) -> Optional[float]:
    """Prezzo medio pesato sull'abbinato con ``flumine.utils.wap`` (arrotonda al
    centesimo); ``None`` se non c'e' abbinato su quel lato."""
    from flumine.utils import wap

    if not coppie:
        return None
    _size, media = wap([(None, p, s) for p, s in coppie])
    return float(media) if media else None


def _controlla(market_id: str, modo: Modo, ordini: Sequence[OrdineConto]) -> None:
    for o in ordini:
        if str(o.market_id) != str(market_id):
            raise ValueError(f"ordine {o.bet_id} del mercato {o.market_id}, non {market_id}")
        if o.modo != modo:
            raise ValueError(f"ordine {o.bet_id} in {o.modo}: paper e live mai sommati")


def _non_supportato(tipo_scommessa: Optional[str], vincitori: Optional[int],
                    a_linee: bool) -> List[str]:
    """Perche' il modello "un solo vincitore" non vale (vuoto = vale)."""
    motivi: List[str] = []
    if tipo_scommessa is None:
        motivi.append("tipo_ignoto")
    elif str(tipo_scommessa).upper() not in TIPI_UN_VINCITORE:
        motivi.append(f"tipo_non_supportato:{tipo_scommessa}")
    if vincitori is not None and int(vincitori) != 1:
        motivi.append(f"vincitori:{int(vincitori)}")
    if a_linee:
        motivi.append("handicap")
    return motivi


def calcola(market_id: str, modo: Modo, ordini: Iterable[OrdineConto], *,
            runner: Optional[Iterable[int]] = None,
            tipo_scommessa: Optional[str] = None,
            vincitori: Optional[int] = None) -> CalcoloPosizione:
    """La ``PosizioneMercato`` del mercato. Dal book (``marketDefinition``):
    ``runner`` = l'elenco delle selezioni, ``tipo_scommessa`` = ``bettingType``,
    ``vincitori`` = ``numberOfWinners``.

    * modello non supportato (tipo assente o non ``ODDS``, piu' vincitori,
      handicap): ``se_vince`` VUOTO, esposizione prudente linea per linea;
    * supportato ma ``runner`` ignoto: ``se_vince`` delle selezioni con ordini,
      esposizione NON calcolabile (``None``; ``NaN`` nella posizione del
      contratto): mai l'esito fittizio "vince un runner senza ordini"."""
    tutti = list(ordini)
    _controlla(market_id, modo, tutti)
    buoni, scartati = _abbinati_validi(tutti)
    a_linee = any(abs(float(o.handicap)) > 1e-9 for o in tutti)
    motivi = _non_supportato(tipo_scommessa, vincitori, a_linee)
    back: Dict[int, List[Tuple[float, float]]] = {}
    lay: Dict[int, List[Tuple[float, float]]] = {}
    for o in buoni:
        (back if o.lato == "back" else lay).setdefault(int(o.selection_id), []).append(
            (float(o.prezzo_medio or 0.0), float(o.abbinato)))
    selezioni = sorted(set(back) | set(lay) | {int(s) for s in (runner or ())})
    abb_back = {s: round(float(sum(x[1] for x in back.get(s, []))), 2) for s in selezioni}
    abb_lay = {s: round(float(sum(x[1] for x in lay.get(s, []))), 2) for s in selezioni}
    pm_back = {s: _media_pesata(back.get(s, [])) for s in selezioni}
    pm_lay = {s: _media_pesata(lay.get(s, [])) for s in selezioni}
    runner_noti = runner is not None
    if motivi:
        # stima prudente: per ogni esito, sum_i min(se vince_i, se perde_i) <= P&L
        espo = esposizioni_per_selezione(buoni)
        peggio = round(sum(min(0.0, e.se_vince, e.se_perde) for e in espo.values()), 2)
        pos = PosizioneMercato(market_id=str(market_id), modo=modo, se_vince={},
                               se_vince_per_autore={}, abbinato_back=abb_back,
                               abbinato_lay=abb_lay, prezzo_medio_back=pm_back,
                               prezzo_medio_lay=pm_lay, esposizione_massima=peggio)
        return CalcoloPosizione(pos, tuple(scartati), a_linee, supportato=False,
                                esposizione_massima=peggio, runner_noti=runner_noti,
                                motivi=tuple(motivi + ["stima_prudente"]))
    se_vince = {s: round(pnl_se_vince(buoni, s), 2) for s in selezioni}
    per_autore: Dict[str, Mapping[int, float]] = {}
    for autore in sorted({o.autore for o in buoni}):
        suoi = [o for o in buoni if o.autore == autore]
        per_autore[autore] = {s: round(pnl_se_vince(suoi, s), 2) for s in selezioni}
    esposizione: Optional[float] = None
    if runner_noti:
        esposizione = round(min([0.0] + list(se_vince.values())), 2)
    else:
        motivi.append("runner_ignoti")
    pos = PosizioneMercato(market_id=str(market_id), modo=modo, se_vince=se_vince,
                           se_vince_per_autore=per_autore, abbinato_back=abb_back,
                           abbinato_lay=abb_lay, prezzo_medio_back=pm_back,
                           prezzo_medio_lay=pm_lay,
                           esposizione_massima=esposizione if esposizione is not None
                           else math.nan)
    return CalcoloPosizione(pos, tuple(scartati), False, supportato=True,
                            esposizione_massima=esposizione, runner_noti=runner_noti,
                            motivi=tuple(motivi))


def posizione_mercato(market_id: str, modo: Modo, ordini: Iterable[OrdineConto], *,
                      runner: Optional[Iterable[int]] = None,
                      tipo_scommessa: Optional[str] = None,
                      vincitori: Optional[int] = None) -> PosizioneMercato:
    """Solo la posizione (vedi ``calcola``)."""
    return calcola(market_id, modo, ordini, runner=runner, tipo_scommessa=tipo_scommessa,
                   vincitori=vincitori).posizione
