"""esposizione_fuori_bot.py - la posizione di CONTO che NON e' dei bot (08/10/2026, W2).

Ordine dell'utente (08/10): "se apro dal sito devo poter chiudere anche dall'app".
Gli ordini fatti su betfair.com compaiono nella pagina (RPC
``get_live_orders_account_open``) ma il ``greenup`` di sempre legge l'esposizione dal
blotter flumine della strategia del runner, che quegli ordini non li ha mai (flumine li
scarta: ``flumine/order/process.py`` "Strategy not available to create order").

Il ``greenup`` con ``params.esposizione = 'fuori_bot'`` (``live_order_worker``) legge
invece la posizione dal CONTO (``listCurrentOrders`` del mercato, la fonte di verita') e
ne tiene SOLO gli ordini che non sono dei bot: ordini dal sito e ordini manuali dell'app.
Qui c'e' la logica PURA (nessun I/O): normalizzazione degli ordini del conto, prima
cernita per riferimenti, esposizione abbinata con la STESSA funzione di flumine, effetto
della copertura sul verdetto di conto dei bot.

RICONOSCIMENTO "ORDINE DI UN BOT" - nessuna regola nuova, si riusano quelle che esistono:
  * ``customerStrategyRef``: un ordine del sito non ne ha; il terminale manuale dell'app
    calcio piazza con ``live`` (``live_order_worker.CUSTOMER_STRATEGY_REF``). Ogni altro
    valore e' di un bot (Mike/Omega/Safe REST: ``mike``/``omega``/``safe``; comandi del
    motore: il nome dell'attore; scalper/sniper/theta/media under: il nome della loro
    strategia flumine, ``flumine/markets/market.py`` ``str(order.trade.strategy)[:15]``)
    o comunque non e' dell'utente: NON fuori bot (nel dubbio mai coprire);
  * ``customerOrderRef`` con il prefisso di un bot: ``reconcile_worker.
    _OUR_ORDER_REF_PREFIXES`` (omega-, safe-t, mike-t) piu' ``<attore>-`` per ogni
    attore dei comandi del motore (``motore_ordini.ATTORI_COMANDO`` tolto ``desktop``:
    safe-, omega-, mike-, safe_tennis-, tennis_*-);
  * le esclusioni della RPC ``get_live_orders_account_open`` (migrazione
    ``live_orders_account_open_2026-09-30.sql``): ``bet_id`` in omega_trades /
    safe_strategy_trades / mike_trades (mode live), riga dello specchio
    ``betfair_live_orders`` con ``source`` diversa da 'runner'/'account'. Queste letture
    del DB le fa il worker (``live_order_worker._proprietari_bot``), qui si danno solo le
    costanti.
  * in piu', per chiudere la finestra in cui un bot ha piazzato DALLA CODA del runner
    (``customerStrategyRef`` 'live') ma non ha ancora scritto il ``bet_id`` nella sua
    tabella: la riga di ``betfair_live_order_requests`` con quel ``bet_id`` e un
    ``client_ref`` con il prefisso di un bot, o ``params.source`` di un bot, o
    ``params.comando`` di un attore che non sia il desktop.

Codice ASCII-only, commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

#: il parametro e il suo unico valore ammesso (contratto del coordinatore, W1/W2)
PARAM = "esposizione"
FUORI_BOT = "fuori_bot"

#: ``customerStrategyRef`` del terminale manuale dell'app calcio. Deve restare uguale a
#: ``live_order_worker.CUSTOMER_STRATEGY_REF`` (lo verifica un test di contratto: qui non
#: si importa il worker per non legare la logica pura al runner).
STRATEGIA_MANUALE_APP = "live"

#: le ``source`` dello specchio che la RPC ``get_live_orders_account_open`` considera
#: "non dei bot" (runner = terminale manuale, account = copia di un ordine del sito)
SOURCE_SPECCHIO_A_MANO = ("runner", "account")

#: le tabelle dei bot con una riga per ogni loro ordine (stesse della RPC e di
#: ``reconcile_worker._TABELLE_BOT``: un test di contratto le confronta)
TABELLE_BOT = ("omega_trades", "safe_strategy_trades", "mike_trades")

#: la ``source`` dello specchio dello scalper calcio: e' un bot (nessun attore del
#: motore, ma ``params.source`` di una sua riga di coda lo direbbe con questo nome)
SOURCE_SCALPER = "scalper"

#: la tolleranza PIU' LARGA dei verdetti di conto dei bot (Mike e Safe 0,05; Omega
#: 0,01): sotto, il bot dice "piatta". Un test di contratto la confronta con le loro.
EPS_VERDETTO_BOT = 0.05


def attori_bot() -> frozenset:
    """Gli attori dei comandi del motore che sono BOT (tutti tranne il desktop)."""
    from ..motore_ordini import ATTORI_COMANDO

    return frozenset(a for a in ATTORI_COMANDO if a != "desktop")


def prefissi_ref_bot() -> Tuple[str, ...]:
    """I prefissi dei ``customerOrderRef``/``client_ref`` dei bot, dalle regole che
    esistono gia' (vedi il docstring del modulo). Ordinati: deterministici."""
    from ..reconcile_worker import _OUR_ORDER_REF_PREFIXES

    pref = set(_OUR_ORDER_REF_PREFIXES)
    pref.update(f"{a}-" for a in attori_bot())
    return tuple(sorted(pref))


def normalizza(ordine: Any) -> Dict[str, Any]:
    """UN ordine del conto (``CurrentOrder`` di betfairlightweight o il suo dict
    camelCase) nella grafia di ``listCurrentOrders``: la STESSA funzione con cui il
    runner pubblica il conto sul canale (``esiti_ordini_canale.ordine_del_conto``).
    Nessun campo dedotto: cio' che manca resta ``None``."""
    from ..esiti_ordini_canale import ordine_del_conto

    return ordine_del_conto(ordine)


def _testo(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _num(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def sulla_selezione(o: Dict[str, Any], market_id: str, selection_id: int,
                    handicap: float) -> bool:
    """L'ordine (camelCase) e' su (mercato, selezione, handicap)?"""
    if _testo(o.get("marketId")) != _testo(market_id):
        return False
    try:
        if int(o.get("selectionId")) != int(selection_id):
            return False
    except (TypeError, ValueError):
        return False
    return abs(_num(o.get("handicap")) - float(handicap or 0.0)) <= 1e-6


def motivo_bot_da_riferimenti(o: Dict[str, Any],
                              prefissi: Optional[Iterable[str]] = None) -> Optional[str]:
    """Prima cernita SENZA DB: il motivo per cui l'ordine e' di un bot (o non e'
    dell'utente) secondo i suoi riferimenti; ``None`` = candidato "fuori bot" (lo
    decideranno poi le letture del DB).

    ``customerStrategyRef`` ammessi: assente (sito) o ``live`` (terminale manuale app
    calcio). Il confronto e' esatto sul valore che Betfair restituisce, senza
    maiuscole/minuscole (Betfair lo restituisce come lo si e' scritto)."""
    csr = _testo(o.get("customerStrategyRef"))
    if csr and csr.lower() != STRATEGIA_MANUALE_APP:
        return f"strategia:{csr}"
    cor = _testo(o.get("customerOrderRef"))
    if cor:
        for p in (tuple(prefissi) if prefissi is not None else prefissi_ref_bot()):
            if cor.startswith(p):
                return f"ref:{cor}"
    return None


def motivo_bot_da_coda(riga: Dict[str, Any],
                       prefissi: Optional[Iterable[str]] = None) -> Optional[str]:
    """Una riga di ``betfair_live_order_requests`` (chiavi della tabella: ``client_ref``,
    ``params``) dice che l'ordine e' nato da un BOT? Motivo o ``None``."""
    cref = _testo(riga.get("client_ref"))
    for p in (tuple(prefissi) if prefissi is not None else prefissi_ref_bot()):
        if cref.startswith(p):
            return f"coda:{cref}"
    params = riga.get("params") if isinstance(riga.get("params"), dict) else {}
    src = _testo(params.get("source")).lower()
    if src and (src in attori_bot() or src == SOURCE_SCALPER):
        return f"coda_source:{src}"
    com = params.get("comando")
    if isinstance(com, dict):
        att = _testo(com.get("attore"))
        if att and att != "desktop":
            return f"coda_attore:{att}"
    return None


#: la tabella di un bot -> il suo nome (stesso vocabolario di ``reconcile_worker``)
_BOT_DELLA_TABELLA = {"omega_trades": "omega", "safe_strategy_trades": "safe",
                      "mike_trades": "mike"}


def _bot_del_ref(ref: str) -> str:
    """Il bot di un ``customerOrderRef``/``client_ref``: l'attore del suo prefisso
    (``mike-t12`` -> mike, ``safe_tennis-t3`` -> safe_tennis, ``omega-t9`` -> omega)."""
    for p in sorted(prefissi_ref_bot(), key=len, reverse=True):
        if ref.startswith(p):
            nome = p.rstrip("-")
            return nome[:-2] if nome.endswith("-t") else nome
    return ref


def bot_di(motivo: str) -> str:
    """Il NOME del bot da un motivo di esclusione (per sommare le gambe di uno stesso
    bot riconosciute da regole diverse). ``tabella:`` e' l'identita' piu' affidabile:
    Safe piazza via REST con il ``customerStrategyRef`` di Omega (nota di
    ``reconcile_worker``), la tabella invece non mente."""
    tipo, _, valore = str(motivo).partition(":")
    valore = valore.strip()
    if tipo == "tabella":
        return _BOT_DELLA_TABELLA.get(valore, valore)
    if tipo in ("ref", "coda"):
        return _bot_del_ref(valore)
    if tipo in ("strategia", "specchio", "coda_source", "coda_attore"):
        return valore.lower() or tipo
    return "sconosciuto"


def esposizione_abbinata(ordini: Iterable[Dict[str, Any]]) -> Tuple[float, float]:
    """(profit_if_win, profit_if_lose) dell'ABBINATO degli ordini (camelCase), con la
    STESSA funzione con cui il blotter di flumine calcola ``matched_profit_if_win/lose``
    (``flumine.utils.calculate_matched_exposure``: quella del green-up di sempre).

    Gli ordini senza abbinato non contano. Un ordine con abbinato ma senza un prezzo
    medio sensato (> 1) e' una lettura che non si sa interpretare: si SOLLEVA (mai un
    prezzo inventato: difetto 3 del catalogo)."""
    from flumine.utils import calculate_matched_exposure

    mb: List[Tuple[float, float]] = []
    ml: List[Tuple[float, float]] = []
    for o in ordini:
        sm = _num(o.get("sizeMatched"))
        if sm <= 0:
            continue
        apm = _num(o.get("averagePriceMatched"))
        if not apm > 1.0:
            raise ValueError(f"ordine {o.get('betId')}: abbinato {sm} senza prezzo medio "
                             f"({o.get('averagePriceMatched')!r})")
        lato = _testo(o.get("side")).upper()
        if lato == "BACK":
            mb.append((apm, sm))
        elif lato == "LAY":
            ml.append((apm, sm))
        else:
            raise ValueError(f"ordine {o.get('betId')}: lato sconosciuto {o.get('side')!r}")
    return calculate_matched_exposure(mb, ml)


def netto_size(ordini: Iterable[Dict[str, Any]]) -> float:
    """BACK meno LAY dell'ABBINATO, in euro di size: l'aritmetica dei verdetti di conto
    dei bot (``mike.service._netto_su_selezione``, ``omega_service._netto_di_conto``,
    ``safe_strategy.bot_service._netto_su_selezione``)."""
    tot = 0.0
    for o in ordini:
        sm = _num(o.get("sizeMatched"))
        if sm <= 0:
            continue
        tot += sm if _testo(o.get("side")).upper() == "BACK" else -sm
    return round(tot, 2)


def vivo_nel_conto(atteso: float, conto: float) -> float:
    """Quanto della posizione di un bot (``atteso``) SOPRAVVIVE nel netto di conto: la
    formula identica dei tre verdetti (Mike ``_verdetto_di_conto``, Omega
    ``sorveglia_posizione_di_conto``, Safe ``_sorveglia_posizione_di_conto``)."""
    return (min(atteso, max(0.0, conto)) if atteso > 0
            else max(atteso, min(0.0, conto)))


def effetto_sui_bot(netti_bot: Dict[str, float], conto_prima: float,
                    delta: float) -> List[Dict[str, Any]]:
    """Che cosa diranno i verdetti di conto dei bot dopo una copertura che sposta il
    netto di conto della selezione di ``delta`` (BACK +size, LAY -size).

    ``netti_bot``: bot -> netto delle sue gambe abbinate sul conto (la sua posizione).
    Torna una voce per ogni bot la cui posizione, dopo, sopravvive MENO di prima:
    ``verdetto`` = ``chiusa`` (non sopravvive piu') o ``ridotta``. Lista vuota = nessun
    bot vedra' la sua posizione toccata."""
    out: List[Dict[str, Any]] = []
    dopo_conto = round(conto_prima + delta, 2)
    for bot, mio in sorted(netti_bot.items()):
        if abs(mio) <= EPS_VERDETTO_BOT:
            continue
        prima = vivo_nel_conto(mio, conto_prima)
        dopo = vivo_nel_conto(mio, dopo_conto)
        if abs(dopo) + 0.01 >= abs(prima):
            continue
        verdetto = "chiusa" if abs(dopo) <= EPS_VERDETTO_BOT else "ridotta"
        out.append({"bot": bot, "posizione": round(mio, 2),
                    "viva_prima": round(prima, 2), "viva_dopo": round(dopo, 2),
                    "netto_conto_prima": round(conto_prima, 2),
                    "netto_conto_dopo": dopo_conto, "verdetto": verdetto})
    return out
