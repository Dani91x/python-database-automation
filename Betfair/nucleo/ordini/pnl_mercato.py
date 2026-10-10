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
vincitore (``numberOfWinners`` = 1) e nessun handicap. Seconda revisione 09/10:
senza ``numberOfWinners`` il modello vale solo per i ``marketType`` a vincitore
unico per definizione (altrimenti ``vincitori_ignoti``); ``posizione_per_json``
da' la posizione per la UI con ``null`` al posto di ``NaN``.

DECISIONE 5 DELL'UTENTE (10/10, "tutti i mercati", come Bet Angel e Geeks Toy):
il "se vince" PER SELEZIONE si calcola SEMPRE, su OGNI mercato, con la stessa
formula: P&L degli abbinati del mercato se vince QUELLA selezione e PERDONO
TUTTE le altre. Accanto, la QUALITA' del numero (``CalcoloPosizione.qualita``):
  * ``esatto``: mercato a vincitore unico (sopra). Il P&L e' quello di prima,
    riga per riga (stesso codice, stessi test di parita'), e l'esposizione
    massima e' esatta (la peggiore fra gli esiti, runner noti);
  * ``per_selezione``: piu' vincitori (piazzati, doppia chance), handicap e
    linee (asiatici, ``LINE``), tipo o vincitori ignoti: il numero vale per la
    selezione (o la LINEA: selezione + handicap) e NON e' un esito unico del
    mercato (due selezioni possono vincere insieme; push e mezze vincite degli
    asiatici non sono modellati). L'esposizione massima resta la STIMA
    PRUDENTE di prima: somma, linea per linea, della peggiore fra (se vince,
    se perde, 0) di flumine (``stima_prudente`` nei ``motivi``): vale per ogni
    esito, push e mezze vincite compresi, ma non e' stretta.
Le chiavi: ``se_vince_per_linea`` (estensione) ha la coppia (selection_id,
handicap) su ogni mercato; ``PosizioneMercato.se_vince`` (contratto, chiave
``selection_id``) ha le selezioni con UNA sola linea: una selezione con piu'
handicap (asiatico a piu' linee) non ci entra (``linee_multiple``), mai una
somma di linee diverse sotto la stessa chiave.
Mercati ``LINE`` (``bettingType``): il prezzo dell'ordine e' la LINEA, la quota
e' 2,0 (documentazione Betfair, enum ``MarketBettingType``): il P&L si fa a
quota 2,0, come ``flumine.markets.blotter.Blotter.get_exposures`` per il ladder
``LINE_RANGE`` (``linea_a_quota_2`` nei ``motivi``).
Senza l'elenco dei runner l'esposizione esatta NON si calcola (``None``; ``NaN``
nella posizione del contratto): mai l'esito fittizio "vince un runner senza
ordini". Mai un numero inventato.

Entrate: ``OrdineConto`` (dal libro); dal book i parametri del mercato
(``parametri_dal_book`` li legge dalla ``MarketDefinition`` VERA di
betfairlightweight). Uscite: ``PosizioneMercato`` e, come estensioni
dichiarate, ``CalcoloPosizione`` (qualita', linee, motivi), ``EsposizioneSelezione``
(se vince / se perde della selezione da sola) e ``calcolo_per_json`` (per la
UI). NON fa: nessun I/O,
nessuna somma fra modi diversi (un ordine di un altro modo o mercato SOLLEVA),
nessun non abbinato (il worst case con i non abbinati resta a flumine).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import dataclasses
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

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
#: ``marketDefinition.marketType`` a vincitore unico PER DEFINIZIONE (seconda
#: revisione 09/10, punto 4): con questi il modello vale anche senza
#: ``numberOfWinners``. Elenco chiuso e dichiarato nel referto (par. 11): le
#: partite (1X2, risultato esatto, primo tempo, gol si'/no) e le linee over/under.
TIPI_MERCATO_UN_VINCITORE = frozenset({"MATCH_ODDS", "CORRECT_SCORE", "HALF_TIME",
                                       "HALF_TIME_SCORE", "BOTH_TEAMS_TO_SCORE"})
PREFISSI_MERCATO_UN_VINCITORE = ("OVER_UNDER_", "FIRST_HALF_GOALS_")


def vincitore_unico_per_definizione(tipo_mercato: Optional[str]) -> bool:
    """Il ``marketType`` ha un solo vincitore per definizione?"""
    t = str(tipo_mercato or "").upper()
    return t in TIPI_MERCATO_UN_VINCITORE or t.startswith(PREFISSI_MERCATO_UN_VINCITORE)


#: la qualita' del "se vince" (decisione 5 dell'utente, 10/10): ``esatto`` = mercato a
#: vincitore unico, il numero e' l'esito del mercato; ``per_selezione`` = il numero vale
#: per la selezione/linea (vince lei, perdono tutte le altre), non e' un esito unico
QUALITA_ESATTO = "esatto"
QUALITA_PER_SELEZIONE = "per_selezione"
#: ``bettingType`` in cui il prezzo dell'ordine e' la LINEA e la quota e' 2,0
#: (enum ``MarketBettingType`` di Betfair; ``flumine`` blotter.py, ladder ``LINE_RANGE``)
TIPI_A_LINEA = frozenset({"LINE"})
QUOTA_MERCATI_A_LINEA = 2.0
#: prefisso dei ``bettingType`` asiatici (``ASIAN_HANDICAP_DOUBLE_LINE``/``_SINGLE_LINE``)
PREFISSO_ASIATICO = "ASIAN_HANDICAP"

#: una linea del mercato: (selection_id, handicap); ``runner`` accetta anche l'int nudo
Linea = Tuple[int, float]
VoceRunner = Union[int, Tuple[int, Optional[float]]]


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
      nell'esposizione (la UI lo deve dire).

    Decisione 5 dell'utente (10/10):
    * ``qualita``: ``esatto`` o ``per_selezione`` (vedi il docstring del modulo);
      ``supportato`` resta e vale ``qualita == esatto``;
    * ``se_vince_per_linea``: (selection_id, handicap) -> P&L se vince quella
      linea e perdono tutte le altre, su OGNI mercato (le linee con ordini e
      quelle dell'elenco dei runner); ``se_vince_per_linea_per_autore`` idem per
      autore."""

    posizione: PosizioneMercato
    scartati: Tuple[str, ...]
    a_linee: bool
    supportato: bool = True
    esposizione_massima: Optional[float] = None
    runner_noti: bool = False
    motivi: Tuple[str, ...] = ()
    solo_abbinato: bool = True
    qualita: str = QUALITA_ESATTO
    se_vince_per_linea: Mapping[Linea, float] = field(default_factory=dict)
    se_vince_per_linea_per_autore: Mapping[str, Mapping[Linea, float]] = field(
        default_factory=dict)

    @property
    def esposizione_esatta(self) -> bool:
        """L'esposizione massima e' esatta (modello a vincitore unico, runner noti)?
        Altrimenti e' la stima prudente o non calcolabile."""
        return self.qualita == QUALITA_ESATTO and self.esposizione_massima is not None


def _abbinati_validi(ordini: Sequence[OrdineConto], *,
                     prezzo_richiesto: bool = True) -> Tuple[List[OrdineConto], List[str]]:
    """Gli abbinati che entrano nel P&L. ``prezzo_richiesto=False`` (mercati ``LINE``):
    la quota e' 2,0 per regolamento e ``averagePriceMatched`` non e' garantito
    (documentazione Betfair, ``bf_2687396.txt`` r.1148): un abbinato senza prezzo medio
    o con la linea <= 1,0 NON si scarta (revisione del 10/10)."""
    buoni: List[OrdineConto] = []
    scartati: List[str] = []
    for o in ordini:
        if not o.abbinato or o.abbinato <= 0:
            continue
        if not prezzo_richiesto:
            buoni.append(o)
            continue
        if o.prezzo_medio is None or not o.prezzo_medio > 1.0:
            scartati.append(o.bet_id)
            continue
        buoni.append(o)
    return buoni, scartati


def esposizioni_per_selezione(ordini: Iterable[OrdineConto], *,
                              quota: Optional[float] = None) -> Dict[Tuple[int, float],
                                                                     EsposizioneSelezione]:
    """(selection_id, handicap) -> se vince / se perde degli ABBINATI, con la
    funzione di flumine (``calculate_matched_exposure``: arrotonda al centesimo
    per selezione, come il blotter). ``quota``: quota fissa al posto del prezzo
    medio (mercati ``LINE``: 2,0, come il blotter per il ladder ``LINE_RANGE``)."""
    from flumine.utils import calculate_matched_exposure

    per_sel: Dict[Tuple[int, float], Tuple[List[Tuple[float, float]],
                                           List[Tuple[float, float]]]] = {}
    buoni, _ = _abbinati_validi(list(ordini), prezzo_richiesto=quota is None)
    for o in buoni:
        mb, ml = per_sel.setdefault((int(o.selection_id), float(o.handicap)), ([], []))
        if quota is not None:
            (mb if o.lato == "back" else ml).append((float(quota), float(o.abbinato)))
            continue
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


def pnl_se_vince_linea(abbinati: Sequence[OrdineConto], linea: Linea, *,
                       quota: Optional[float] = None) -> float:
    """La stessa formula di ``pnl_se_vince`` per UNA LINEA (selection_id,
    handicap): vince la linea, perdono tutte le altre (decisione 5, 10/10). Un
    ordine e' "suo" se ha la stessa selezione E lo stesso handicap. ``quota``:
    quota fissa al posto del prezzo medio (mercati ``LINE``: 2,0). Non
    arrotondato."""
    sid, hc = int(linea[0]), float(linea[1])
    v = 0.0
    for a in abbinati:
        suo = int(a.selection_id) == sid and abs(float(a.handicap) - hc) <= 1e-9
        importo = float(a.abbinato)
        prezzo = float(quota) if quota is not None else float(a.prezzo_medio or 0.0)
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
                    a_linee: bool, tipo_mercato: Optional[str] = None) -> List[str]:
    """Perche' il modello "un solo vincitore" non vale (vuoto = vale)."""
    motivi: List[str] = []
    if tipo_scommessa is None:
        motivi.append("tipo_ignoto")
    elif str(tipo_scommessa).upper() not in TIPI_UN_VINCITORE:
        motivi.append(f"tipo_non_supportato:{tipo_scommessa}")
    if vincitori is not None and int(vincitori) != 1:
        motivi.append(f"vincitori:{int(vincitori)}")
    elif vincitori is None and not vincitore_unico_per_definizione(tipo_mercato):
        # mercati "piazzati" (piu' vincitori) non si riconoscono dal bettingType
        motivi.append("vincitori_ignoti")
    if a_linee:
        motivi.append("handicap")
    return motivi


def _linee_runner(runner: Optional[Iterable[VoceRunner]]) -> Tuple[List[int], List[Linea]]:
    """L'elenco dei runner diviso in int nudi (selection_id, mercati senza
    handicap: come prima) e coppie (selection_id, handicap) del book (asiatici:
    la stessa selezione con piu' handicap). ``hc`` assente (None) = 0,0."""
    nudi: List[int] = []
    coppie: List[Linea] = []
    for r in runner or ():
        if isinstance(r, (tuple, list)):
            coppie.append((int(r[0]), float(r[1] or 0.0)))
        else:
            nudi.append(int(r))
    return nudi, coppie


def calcola(market_id: str, modo: Modo, ordini: Iterable[OrdineConto], *,
            runner: Optional[Iterable[VoceRunner]] = None,
            tipo_scommessa: Optional[str] = None,
            vincitori: Optional[int] = None,
            tipo_mercato: Optional[str] = None) -> CalcoloPosizione:
    """La ``PosizioneMercato`` del mercato. Dal book (``marketDefinition``,
    vedi ``parametri_dal_book``): ``runner`` = l'elenco delle selezioni (int,
    o coppie (selection_id, handicap) per i mercati con handicap),
    ``tipo_scommessa`` = ``bettingType``, ``vincitori`` = ``numberOfWinners``,
    ``tipo_mercato`` = ``marketType`` (senza ``numberOfWinners`` il modello vale
    solo per i tipi a vincitore unico per definizione:
    ``vincitore_unico_per_definizione``).

    * qualita' ``esatto`` (vincitore unico, nessun handicap): il calcolo di
      prima; ``runner`` ignoto -> ``se_vince`` delle selezioni con ordini,
      esposizione NON calcolabile (``None``; ``NaN`` nella posizione del
      contratto): mai l'esito fittizio "vince un runner senza ordini";
    * qualita' ``per_selezione`` (tutto il resto, decisione 5 del 10/10): il
      "se vince" per linea su ogni mercato (``_per_selezione``), esposizione =
      stima prudente linea per linea."""
    tutti = list(ordini)
    _controlla(market_id, modo, tutti)
    # LINE: quota 2,0 per regolamento, il prezzo medio non serve (e puo' mancare)
    buoni, scartati = _abbinati_validi(tutti, prezzo_richiesto=_quota_fissa(tipo_scommessa) is None)
    a_linee = any(abs(float(o.handicap)) > 1e-9 for o in tutti)
    nudi, coppie = _linee_runner(runner)
    a_linee = a_linee or any(abs(h) > 1e-9 for _s, h in coppie)
    motivi = _non_supportato(tipo_scommessa, vincitori, a_linee, tipo_mercato)
    back: Dict[int, List[Tuple[float, float]]] = {}
    lay: Dict[int, List[Tuple[float, float]]] = {}
    for o in buoni:
        (back if o.lato == "back" else lay).setdefault(int(o.selection_id), []).append(
            (float(o.prezzo_medio or 0.0), float(o.abbinato)))
    selezioni = sorted(set(back) | set(lay) | set(nudi) | {s for s, _h in coppie})
    abb_back = {s: round(float(sum(x[1] for x in back.get(s, []))), 2) for s in selezioni}
    abb_lay = {s: round(float(sum(x[1] for x in lay.get(s, []))), 2) for s in selezioni}
    pm_back = {s: _media_pesata(back.get(s, [])) for s in selezioni}
    pm_lay = {s: _media_pesata(lay.get(s, [])) for s in selezioni}
    runner_noti = runner is not None
    if motivi:
        return _per_selezione(str(market_id), modo, buoni, scartati, a_linee, motivi,
                              tipo_scommessa, nudi, coppie, runner_noti,
                              (abb_back, abb_lay, pm_back, pm_lay))
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
    # a vincitore unico non ci sono handicap: la linea e' (selezione, 0,0)
    return CalcoloPosizione(pos, tuple(scartati), False, supportato=True,
                            esposizione_massima=esposizione, runner_noti=runner_noti,
                            motivi=tuple(motivi), qualita=QUALITA_ESATTO,
                            se_vince_per_linea={(s, 0.0): v for s, v in se_vince.items()},
                            se_vince_per_linea_per_autore={
                                a: {(s, 0.0): v for s, v in m.items()}
                                for a, m in per_autore.items()})


def _quota_fissa(tipo_scommessa: Optional[str]) -> Optional[float]:
    """2,0 per i mercati ``LINE`` (il prezzo e' la linea), altrimenti None."""
    return QUOTA_MERCATI_A_LINEA if str(tipo_scommessa or "").upper() in TIPI_A_LINEA else None


def _per_selezione(market_id: str, modo: Modo, buoni: List[OrdineConto], scartati: List[str],
                   a_linee: bool, motivi: List[str], tipo_scommessa: Optional[str],
                   nudi: List[int], coppie: List[Linea], runner_noti: bool,
                   abbinati: Tuple[Mapping[int, float], Mapping[int, float],
                                   Mapping[int, Optional[float]],
                                   Mapping[int, Optional[float]]]) -> CalcoloPosizione:
    """Decisione 5 dell'utente (10/10): il "se vince" per LINEA su un mercato non a
    vincitore unico, con la qualita' ``per_selezione``; l'esposizione resta la stima
    prudente di prima (ora con la quota 2,0 sui mercati ``LINE``).

    Le linee: quelle degli ordini abbinati, le coppie del book e gli int nudi del
    book come (selezione, 0,0) SOLO se quella selezione non ha gia' una linea (mai
    una linea 0,0 inventata su un asiatico). Nel contratto (chiave selection_id)
    entrano le selezioni con UNA sola linea."""
    quota = _quota_fissa(tipo_scommessa)
    if quota is not None:
        motivi.append("linea_a_quota_2")
    if str(tipo_scommessa or "").upper().startswith(PREFISSO_ASIATICO):
        motivi.append("asiatico_push_non_modellato")
    linee_ordini = {(int(o.selection_id), float(o.handicap)) for o in buoni}
    con_linea = {s for s, _h in linee_ordini} | {s for s, _h in coppie}
    linee = sorted(linee_ordini | set(coppie) | {(s, 0.0) for s in nudi if s not in con_linea})
    per_linea = {ln: round(pnl_se_vince_linea(buoni, ln, quota=quota), 2) for ln in linee}
    per_linea_autore: Dict[str, Mapping[Linea, float]] = {}
    for autore in sorted({o.autore for o in buoni}):
        suoi = [o for o in buoni if o.autore == autore]
        per_linea_autore[autore] = {ln: round(pnl_se_vince_linea(suoi, ln, quota=quota), 2)
                                    for ln in linee}
    quante: Dict[int, int] = {}
    for s, _h in linee:
        quante[s] = quante.get(s, 0) + 1
    if any(n > 1 for n in quante.values()):
        motivi.append("linee_multiple")
    se_vince = {s: v for (s, _h), v in per_linea.items() if quante[s] == 1}
    per_autore = {a: {s: v for (s, _h), v in m.items() if quante[s] == 1}
                  for a, m in per_linea_autore.items()}
    if not runner_noti:
        motivi.append("runner_ignoti")
    # stima prudente: per ogni esito (push e mezze vincite comprese),
    # sum_i min(0, se vince_i, se perde_i) <= P&L
    espo = esposizioni_per_selezione(buoni, quota=quota)
    peggio = round(sum(min(0.0, e.se_vince, e.se_perde) for e in espo.values()), 2)
    if quota is not None:
        # mercati LINE: il prezzo e' la linea, e ordini a linee DIVERSE sulla stessa
        # selezione NON si compensano (un esito fra le due linee li fa perdere
        # entrambi): la stima si fa ORDINE PER ORDINE, mai linea per linea
        peggio = round(sum(min(0.0, e.se_vince, e.se_perde) for o in buoni
                           for e in esposizioni_per_selezione([o], quota=quota).values()), 2)
        motivi.append("stima_per_ordine")
    abb_back, abb_lay, pm_back, pm_lay = abbinati
    pos = PosizioneMercato(market_id=market_id, modo=modo, se_vince=se_vince,
                           se_vince_per_autore=per_autore, abbinato_back=abb_back,
                           abbinato_lay=abb_lay, prezzo_medio_back=pm_back,
                           prezzo_medio_lay=pm_lay, esposizione_massima=peggio)
    return CalcoloPosizione(pos, tuple(scartati), a_linee, supportato=False,
                            esposizione_massima=peggio, runner_noti=runner_noti,
                            motivi=tuple(motivi + ["stima_prudente"]),
                            qualita=QUALITA_PER_SELEZIONE, se_vince_per_linea=per_linea,
                            se_vince_per_linea_per_autore=per_linea_autore)


def posizione_mercato(market_id: str, modo: Modo, ordini: Iterable[OrdineConto], *,
                      runner: Optional[Iterable[VoceRunner]] = None,
                      tipo_scommessa: Optional[str] = None,
                      vincitori: Optional[int] = None,
                      tipo_mercato: Optional[str] = None) -> PosizioneMercato:
    """Solo la posizione (vedi ``calcola``)."""
    return calcola(market_id, modo, ordini, runner=runner, tipo_scommessa=tipo_scommessa,
                   vincitori=vincitori, tipo_mercato=tipo_mercato).posizione


def _per_json(v: Any) -> Any:
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, Mapping):
        return {str(k): _per_json(x) for k, x in v.items()}
    return v


def posizione_per_json(pos: PosizioneMercato) -> Dict[str, Any]:
    """La posizione pronta per il JSON della UI (seconda revisione 09/10, punto 5):
    ``NaN`` (esposizione non calcolabile) -> ``None`` (``null``), chiavi delle
    selezioni in testo (JSON non ha chiavi numeriche). Nient'altro cambia."""
    return {f.name: _per_json(getattr(pos, f.name)) for f in dataclasses.fields(pos)}


def _linee_json(linee: Mapping[Linea, float]) -> List[Dict[str, Any]]:
    return [{"selection_id": int(s), "handicap": float(h), "se_vince": float(v)}
            for (s, h), v in sorted(linee.items())]


def calcolo_per_json(c: CalcoloPosizione) -> Dict[str, Any]:
    """Il calcolo per il JSON della UI (decisione 5, 10/10): la posizione di
    ``posizione_per_json`` e accanto cio' che il ladder deve poter mostrare:
    ``qualita`` (``esatto``/``per_selezione``), il tipo dell'esposizione
    (``esatta``, ``stima_prudente`` o ``non_calcolabile``), i ``motivi``, le
    linee (selection_id, handicap, se_vince; anche per autore) e
    ``solo_abbinato``."""
    if c.esposizione_massima is None:
        tipo_esposizione = "non_calcolabile"
    elif c.esposizione_esatta:
        tipo_esposizione = "esatta"
    else:
        tipo_esposizione = "stima_prudente"
    d = posizione_per_json(c.posizione)
    d.update({"qualita": c.qualita, "esposizione_tipo": tipo_esposizione,
              "motivi": list(c.motivi), "solo_abbinato": c.solo_abbinato,
              "se_vince_per_linea": _linee_json(c.se_vince_per_linea),
              "se_vince_per_linea_per_autore": {
                  str(a): _linee_json(m)
                  for a, m in sorted(c.se_vince_per_linea_per_autore.items())}})
    return d


def parametri_dal_book(definizione: Any) -> Dict[str, Any]:
    """I parametri di ``calcola`` dalla ``MarketDefinition`` VERA di
    betfairlightweight (stream: ``MarketBook.market_definition``; attributi
    ``betting_type``, ``number_of_winners``, ``market_type``, ``runners`` con
    ``selection_id``/``handicap``/``status``): ``runner`` come coppie
    (selection_id, handicap) -- ``hc`` assente = 0,0 -- senza i runner
    ``REMOVED`` (non possono vincere). Nessun valore inventato: cio' che il
    book non dice resta None."""
    runner = [(int(r.selection_id), float(r.handicap or 0.0))
              for r in (getattr(definizione, "runners", None) or ())
              if str(getattr(r, "status", "") or "").upper() != "REMOVED"]
    vincitori = getattr(definizione, "number_of_winners", None)
    return {"runner": runner,
            "tipo_scommessa": getattr(definizione, "betting_type", None),
            "vincitori": int(vincitori) if vincitori is not None else None,
            "tipo_mercato": getattr(definizione, "market_type", None)}
