"""attribuzione.py - CHI ha fatto un ordine del conto (comparto C, W1-C2, 09/10/2026).

Scopo: dato un ordine come lo dice Betfair (``OrdineDalConto``: ``rfs`` =
``customerStrategyRef``, ``rfo`` = ``customerOrderRef``) dire il suo ``Autore``
(contratto ``Betfair/nucleo/ordini/contratto.py``): l'utente dall'app
(``desktop``), un bot per nome, il sito Betfair (``sito``: nessun riferimento
nostro) o ``sconosciuto`` (c'e' un riferimento ma non e' di nessuno dei nostri).

NESSUNA REGOLA NUOVA. Le costanti si IMPORTANO dal codice di oggi (una volta,
pigramente, in ``regole_di_oggi``): il ``customerStrategyRef`` del terminale
manuale calcio (``live_order_worker.CUSTOMER_STRATEGY_REF``) e tennis
(``tennis_live_order_worker.CUSTOMER_STRATEGY_REF``); gli attori dei comandi del
motore (``motore_ordini.ATTORI_COMANDO``: il motore scrive ``strategy_ref`` =
attore, ``valida_comando``); i ref di strategia dei bot REST (``omega_config``,
``mike.config``, ``bot_service.SAFE_STRATEGY_REF``) e il ref storico che Safe e
Mike usavano prima del 24/09 (``bot_service._SAFE_REFS_STORICI``); i prefissi
dei ``customerOrderRef`` dei bot (``esposizione_fuori_bot.prefissi_ref_bot`` +
``bot_di``); i nomi flumine dello scalper calcio
(``scalper_session.PREFISSI_STRATEGIA``: ``customerStrategyRef`` = prefisso +
event_id, 15 caratteri) e dei quattro bot tennis (``tennis_runner._BOT_REGISTRY``:
nessun ``name`` -> il nome della classe, che flumine taglia a 15 caratteri,
``flumine/markets/market.py``); le ``source`` dello specchio e le tabelle dei bot
(``esposizione_fuori_bot``, ``reconcile_worker``, ``canale_bot_tennis``).

Due livelli, come oggi (W2/W3a, ``esposizione_fuori_bot`` docstring):
  1. RIFERIMENTI dell'ordine (``attribuisci_riferimenti``), senza DB;
  2. INDIZI dati come dati (``Indizio``): righe gia' lette altrove (tabelle dei
     bot, specchio, coda del runner) con i motivi di oggi
     (``esposizione_fuori_bot.proprietari_bot`` / ``motivo_bot_da_coda``,
     ``reconcile_worker._proprietari``). Un indizio di un bot VINCE sui
     riferimenti (la tabella non mente: Safe ha piazzato via REST col ref di
     Omega); se i riferimenti dicevano un ALTRO bot il conflitto si scrive.

REVISIONE 09/10 (G1): il ``customerStrategyRef`` del terminale manuale (``live``
calcio, ``tennis``) lo portano ANCHE gli ordini dei bot e del risk engine passati
dalla CODA del runner (customerOrderRef di flumine). Da solo NON basta a dire
``desktop``: l'attribuzione e' PROVVISORIA (``sconosciuto``, nessun comando sul
ladder) finche' un indizio non dice un bot o non da' un'evidenza POSITIVA
dell'utente (riga di coda non di un bot, ack di un comando del desktop).
SECONDA REVISIONE 09/10: una riga di coda prova SOLO se ha PIAZZATO quell'ordine
(``AZIONI_CHE_PIAZZANO``; mai cancel/replace) e il suo bet_id si legge anche da
``result`` (righe ``local<id>`` del ladder); i ritentativi ``ft`` ereditano dal
genitore; la coda tennis ha ``indizi_da_riga_tennis``.

Entrate: ``OrdineDalConto`` (o i soli ``csr``/``cor``), indizi opzionali,
regole (di serie quelle di oggi). Uscite: ``Attribuzione`` (autore, motivo,
fonte, conflitto). NON fa: nessuna lettura del DB, nessuna rete, nessun file;
non decide cosa un bot deve fare di un ordine altrui (resta ai bot); non
cambia nessuna regola di oggi: dove questo modulo e la classificazione di oggi
danno esiti diversi c'e' una DIVERGENZA scritta nel referto W1-C2.

Importare questo modulo non importa il codice di oggi (solo ``regole_di_oggi``
lo fa, al primo uso). ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import (Any, Dict, FrozenSet, Iterable, List, Literal, Mapping, Optional,
                    Sequence, Tuple, get_args)

from Betfair.nucleo.betfair.contratto import OrdineDalConto
from Betfair.nucleo.ordini.contratto import Autore

logger = logging.getLogger(__name__)

#: tutti gli autori del contratto, nell'ordine del contratto
AUTORI: Tuple[str, ...] = tuple(get_args(Autore))
DESKTOP = "desktop"
SITO = "sito"
SCONOSCIUTO = "sconosciuto"
RISK = "risk"
SCALPER = "scalper"
#: gli autori che sono l'UTENTE (gli altri sono bot o non nostri)
AUTORI_UTENTE: FrozenSet[str] = frozenset({DESKTOP, SITO})

FonteAttribuzione = Literal["riferimenti", "indizio", "dichiarato"]

#: prefisso dei ``client_ref`` della coda scritti dal risk engine
#: (``risk_engine_worker``: ``risk<id>``, ``risk<id>o``, ``risk<id>s``, ...).
#: Il codice di oggi non lo esporta come costante: il test
#: ``test_c2_attribuzione`` lo ricava dai sorgenti di produzione e fallisce se
#: un ``client_ref`` del risk engine non lo porta o se un altro produttore lo usa.
PREFISSO_CODA_RISCHIO = "risk"

#: ``customerStrategyRef`` scritto da un percorso nostro ma senza un autore nel
#: contratto: il terminale vecchio ``order_exec.py`` ("watchlist"). Oggi
#: ``reconcile_worker`` lo mette fra gli "altri_bot": qui resta ``sconosciuto``
#: (divergenza D4 del referto, decisione dell'utente).
RIF_FUORI_CONTRATTO: FrozenSet[str] = frozenset({"watchlist"})


@dataclass(frozen=True)
class RegoleAttribuzione:
    """Le costanti di oggi, gia' normalizzate (minuscolo dove Betfair confronta
    senza maiuscole: ``esposizione_fuori_bot.motivo_bot_da_riferimenti``)."""

    rif_manuali: FrozenSet[str]                    # {"live", "tennis"} -> desktop
    rif_attori: Mapping[str, str]                  # csr -> autore (attori del motore + REST)
    rif_classi_flumine: Mapping[str, str]          # csr (nome classe[:15], minuscolo) -> bot tennis
    prefissi_scalper: Tuple[str, ...]              # ("mu", "scm", "scn", "sct")
    rif_storici_condivisi: FrozenSet[str]          # {"omega"}: ref usato anche da Safe/Mike prima del 24/09
    prefissi_ref: Tuple[Tuple[str, str], ...]      # (prefisso customerOrderRef, autore), piu' lunghi prima
    sorgenti_bot_tennis: FrozenSet[str]            # source di tennis_live_orders dei 4 bot
    source_scalper: str                            # "scalper"
    source_a_mano: FrozenSet[str]                  # {"runner", "account"}
    tabelle_bot: Mapping[str, str]                 # tabella -> autore
    prefisso_coda_rischio: str = PREFISSO_CODA_RISCHIO
    rif_fuori_contratto: FrozenSet[str] = RIF_FUORI_CONTRATTO


_REGOLE: Optional[RegoleAttribuzione] = None
_REGOLE_LOCK = threading.Lock()


def regole_di_oggi() -> RegoleAttribuzione:
    """Le regole costruite dalle costanti del codice di oggi (import pigro, UNA
    volta per processo; nessun file, socket o thread). Thread-safe."""
    global _REGOLE
    with _REGOLE_LOCK:
        if _REGOLE is None:
            _REGOLE = _costruisci_regole()
        return _REGOLE


def _costruisci_regole() -> RegoleAttribuzione:
    from Betfair.mike import config as mike_config
    from Betfair.omega import omega_config
    from Betfair.safe_strategy import bot_service as safe_bot
    from Betfair.stream import live_order_worker as low
    from Betfair.stream import motore_ordini
    from Betfair.stream import reconcile_worker as rw
    from Betfair.stream.scalper import scalper_session
    from Betfair.stream.tennis_live import canale_bot_tennis
    from Betfair.stream.tennis_live import tennis_live_order_worker as tlow
    from Betfair.stream.tennis_live import tennis_runner
    from Betfair.stream.trading import esposizione_fuori_bot as efb

    manuali = frozenset({str(low.CUSTOMER_STRATEGY_REF).lower(),
                         str(tlow.CUSTOMER_STRATEGY_REF).lower()})
    attori: Dict[str, str] = {}
    # il motore scrive ``strategy_ref`` = attore, tagliato a 15 caratteri
    # (``live_order_worker._strategy_ref_corrente``)
    for attore in sorted(motore_ordini.ATTORI_COMANDO):
        attori[str(attore)[:15].lower()] = str(attore)
    # i ref di strategia dei bot REST (``omega_market.ref_di_strategia``)
    attori[str(omega_config.CUSTOMER_STRATEGY_REF).lower()] = "omega"
    attori[str(mike_config.CUSTOMER_STRATEGY_REF).lower()] = "mike"
    attori[str(safe_bot.SAFE_STRATEGY_REF).lower()] = "safe"
    classi: Dict[str, str] = {}
    for chiave, voce in tennis_runner._BOT_REGISTRY.items():
        classi[str(voce[0].__name__)[:15].lower()] = str(chiave)
    # revisione 09/10 (M5): i runner STANDALONE dello scalper calcio
    # (``run_scalper.py:85``, ``run_scalper_live.py:271``, ``run_theta.py:127``)
    # creano la strategia SENZA ``name``: il customerStrategyRef e' il nome della
    # CLASSE tagliato a 15 (``flumine/markets/market.py``)
    for cls in _classi_scalper():
        classi[str(cls.__name__)[:15].lower()] = SCALPER
    prefissi: List[Tuple[str, str]] = []
    for p in efb.prefissi_ref_bot():
        prefissi.append((str(p), efb.bot_di(f"ref:{p}")))
    prefissi.sort(key=lambda x: (-len(x[0]), x[0]))
    tabelle = {t: efb.bot_di(f"tabella:{t}") for t in efb.TABELLE_BOT}
    return RegoleAttribuzione(
        rif_manuali=manuali,
        rif_attori=attori,
        rif_classi_flumine=classi,
        prefissi_scalper=tuple(sorted(str(v) for v in
                                      scalper_session.PREFISSI_STRATEGIA.values())),
        rif_storici_condivisi=frozenset(str(r).lower()
                                        for r in safe_bot._SAFE_REFS_STORICI),
        prefissi_ref=tuple(prefissi),
        sorgenti_bot_tennis=frozenset(canale_bot_tennis.SORGENTI_BOT_TENNIS),
        source_scalper=str(rw.SOURCE_SCALPER),
        source_a_mano=frozenset(efb.SOURCE_SPECCHIO_A_MANO),
        tabelle_bot=tabelle,
    )


def _classi_scalper() -> Tuple[type, ...]:
    """Le strategie flumine dello scalper calcio (sessione e runner standalone)."""
    from Betfair.stream.scalper.media_under_bot import MediaUnderStrategy
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy
    from Betfair.stream.scalper.sniper_bot import SniperStrategy
    from Betfair.stream.scalper.theta_bot import ThetaStrategy

    return (ScalperStrategy, SniperStrategy, ThetaStrategy, MediaUnderStrategy)


@dataclass(frozen=True)
class Attribuzione:
    """L'esito: ``autore`` del contratto, ``motivo`` leggibile (nel vocabolario dei
    motivi di oggi: ``strategia:<csr>``, ``ref:<cor>``, ``tabella:<t>``...),
    ``fonte`` (riferimenti, indizio o autore dichiarato dalla sorgente in prova),
    ``conflitto`` se due fonti dicevano due bot diversi (mai nascosto).

    ``provvisoria`` (revisione 09/10, G1): il ref del terminale manuale (``live``,
    ``tennis``) lo scrivono ANCHE gli ordini dei bot e del risk engine passati
    dalla CODA del runner (``safe_strategy/execution.py`` enqueue_place,
    ``risk_engine_worker._enqueue``): senza un'evidenza positiva l'autore e'
    ``sconosciuto`` provvisorio (nessun comando sul ladder), mai ``desktop``."""

    autore: str
    motivo: str
    fonte: FonteAttribuzione
    conflitto: Optional[str] = None
    provvisoria: bool = False

    @property
    def dell_utente(self) -> bool:
        return self.autore in AUTORI_UTENTE


TipoIndizio = Literal["tabella", "coda", "specchio", "specchio_tennis", "adottato", "utente"]
#: forza degli indizi (minore = piu' forte): la tabella del bot non mente
#: (``esposizione_fuori_bot.bot_di``), poi la riga di coda, poi lo specchio;
#: gli indizi dell'UTENTE contano solo se nessun indizio dice un bot
_FORZA: Mapping[str, int] = {"tabella": 0, "coda": 1, "specchio": 2, "specchio_tennis": 2,
                             "adottato": 3, "utente": 4}


@dataclass(frozen=True)
class Indizio:
    """Un fatto letto altrove (DB, specchio, coda) su un ``bet_id``, come dato.

    ``tipo``: ``tabella`` (riga in una tabella dei bot: ``valore`` = tabella),
    ``coda`` (riga di ``betfair_live_order_requests``: ``valore`` = il motivo di
    ``motivo_bot_da_coda`` o ``rischio:<client_ref>``), ``specchio`` /
    ``specchio_tennis`` (``source`` della riga), ``adottato`` (riga
    ``role='utente'`` di ``mike_trades``: l'ordine resta dell'utente,
    ``reconcile_worker._proprietari``), ``utente`` (EVIDENZA POSITIVA che e'
    dell'utente dall'app: la riga di coda con quel bet_id NON e' di un bot ne'
    del risk engine -- ``indizi_da_riga_coda`` -- o il bet_id e' fra gli ack dei
    comandi del desktop -- ``indizio_ack_desktop``)."""

    tipo: TipoIndizio
    valore: str


def _testo(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _autore_da_prefisso(cor: str, regole: RegoleAttribuzione) -> Optional[str]:
    for p, autore in regole.prefissi_ref:
        if cor.startswith(p):
            return autore
    return None


def _e_scalper(csr: str, regole: RegoleAttribuzione) -> bool:
    """``customerStrategyRef`` di una strategia della sessione scalper:
    prefisso del ruolo + event_id numerico (``scalper_session.nome_strategia``)."""
    for p in regole.prefissi_scalper:
        resto = csr[len(p):]
        if csr.startswith(p) and resto.isdigit():
            return True
    return False


def attribuisci_riferimenti(csr: Optional[str], cor: Optional[str],
                            regole: Optional[RegoleAttribuzione] = None) -> Attribuzione:
    """Primo livello: i soli riferimenti dell'ordine (``rfs``, ``rfo``)."""
    r = regole or regole_di_oggi()
    s = _testo(csr)
    o = _testo(cor)
    if not s:
        if not o:
            return Attribuzione(SITO, "sito", "riferimenti")
        bot = _autore_da_prefisso(o, r)
        if bot is not None:
            return Attribuzione(bot, f"ref:{o}", "riferimenti")
        return Attribuzione(SCONOSCIUTO, f"ref_ignoto:{o}", "riferimenti")
    sl = s.lower()
    if sl in r.rif_manuali:
        # come ``motivo_bot_da_riferimenti``: il ref del terminale manuale vale
        # "dell'utente" solo se il customerOrderRef non e' di un bot
        bot = _autore_da_prefisso(o, r) if o else None
        if bot is not None:
            return Attribuzione(bot, f"ref:{o}", "riferimenti")
        # revisione 09/10 (G1): il solo ref manuale NON basta (bot e risk dalla
        # coda del runner lo portano uguale): provvisorio finche' un indizio non
        # dice di chi e'; nessun comando sul ladder nel frattempo
        return Attribuzione(SCONOSCIUTO, f"strategia_manuale_da_confermare:{s}", "riferimenti",
                            provvisoria=True)
    if sl in r.rif_attori:
        return _da_attore(s, sl, o, r)
    if sl in r.rif_classi_flumine:
        return Attribuzione(r.rif_classi_flumine[sl], f"strategia:{s}", "riferimenti")
    if _e_scalper(s, r):
        return Attribuzione(SCALPER, f"strategia:{s}", "riferimenti")
    if sl in r.rif_fuori_contratto:
        return Attribuzione(SCONOSCIUTO, f"strategia_fuori_contratto:{s}", "riferimenti")
    return Attribuzione(SCONOSCIUTO, f"strategia_ignota:{s}", "riferimenti")


def _da_attore(s: str, sl: str, o: str, r: RegoleAttribuzione) -> Attribuzione:
    """Un ``customerStrategyRef`` di un attore: decide il ref, salvo i due casi
    in cui il ``customerOrderRef`` dice di piu' (dal codice di oggi):
    ref storico condiviso (Safe/Mike REST col ref di Omega prima del 24/09,
    ``bot_service._SAFE_REFS_STORICI``) e Safe tennis via REST (``safe`` +
    ``safe_tennis-t<id>``, ``bot_service._SAFE_PREFISSI_ORDINE``)."""
    autore = r.rif_attori[sl]
    dal_ref = _autore_da_prefisso(o, r) if o else None
    if dal_ref is None or dal_ref == autore:
        return Attribuzione(autore, f"strategia:{s}", "riferimenti")
    if sl in r.rif_storici_condivisi:
        return Attribuzione(dal_ref, f"strategia_storica:{s}+ref:{o}", "riferimenti")
    if autore == "safe" and dal_ref == "safe_tennis":
        return Attribuzione(dal_ref, f"strategia:{s}+ref:{o}", "riferimenti")
    return Attribuzione(autore, f"strategia:{s}", "riferimenti",
                        conflitto=f"customerOrderRef {o} di {dal_ref}")


def indizio_da_motivo(motivo: str) -> Optional[Indizio]:
    """Un motivo di ``esposizione_fuori_bot.proprietari_bot`` /
    ``motivo_bot_da_coda`` (``tabella:``, ``specchio:``, ``coda:``,
    ``coda_source:``, ``coda_attore:``) come ``Indizio``. ``None`` se il
    formato non e' uno di questi (si logga: mai indovinato)."""
    tipo, sep, valore = _testo(motivo).partition(":")
    if not sep or not valore:
        logger.warning("[attribuzione] motivo non riconosciuto: %r", motivo)
        return None
    if tipo == "tabella":
        return Indizio("tabella", valore)
    if tipo == "specchio":
        return Indizio("specchio", valore)
    if tipo in ("coda", "coda_source", "coda_attore"):
        return Indizio("coda", f"{tipo}:{valore}")
    logger.warning("[attribuzione] motivo non riconosciuto: %r", motivo)
    return None


#: azioni della coda che PIAZZANO un ordine nuovo: il bet_id del loro ``result``
#: e' un ordine di chi ha mandato il comando (``live_order_worker._LOCAL_ACTIONS``
#: + ``place_submin``). ``cancel`` e ``replace`` NON lo sono: l'utente puo'
#: annullare o spostare un ordine di un bot (seconda revisione 09/10, punto 1c).
AZIONI_CHE_PIAZZANO: FrozenSet[str] = frozenset({"place", "place_submin", "greenup", "dutch",
                                                 "cashout_all", "cashout_event"})
#: prefisso dei ``client_ref`` dei ritentativi del follow-through
#: (``live_order_worker`` ``ft<rid>m<market>r<n>`` / ``ft<rid>s<sel>r<n>``, con
#: ``params.ft_parent`` = id della riga genitore)
PREFISSO_FOLLOW_THROUGH = "ft"


def _risultato(riga: Mapping[str, Any]) -> Mapping[str, Any]:
    """La colonna ``result`` (jsonb: dict; tollerata anche la stringa JSON)."""
    res = riga.get("result")
    if isinstance(res, str):
        import json

        try:
            res = json.loads(res)
        except ValueError:
            logger.warning("[attribuzione] result non JSON: %r", res[:80])
            return {}
    return res if isinstance(res, Mapping) else {}


def bet_id_della_riga(riga: Mapping[str, Any]) -> Optional[str]:
    """Il bet_id dell'ordine che la riga ha PIAZZATO: la colonna ``bet_id``
    (scritta da ``live_order_worker._write_done`` per la coda DB) o
    ``result.bet_id`` (l'unico posto per le righe ``local<id>`` di
    ``_record_local_request``, dove la colonna ``bet_id`` e' quella del
    comando: NULL per un place)."""
    dal_risultato = _testo(_risultato(riga).get("bet_id"))
    return dal_risultato or _testo(riga.get("bet_id")) or None


def indizi_da_riga_coda(riga: Mapping[str, Any],
                        regole: Optional[RegoleAttribuzione] = None, *,
                        bet_id: Optional[str] = None,
                        genitore: Optional[Mapping[str, Any]] = None) -> Tuple[Indizio, ...]:
    """Una riga di ``betfair_live_order_requests`` (colonne vere: ``client_ref``,
    ``action``, ``params``, ``bet_id``, ``result``). Prova SOLO se ha PIAZZATO
    l'ordine (``AZIONI_CHE_PIAZZANO``) e, con ``bet_id``, solo se e' quello
    piazzato (``bet_id_della_riga``). Allora: il motivo di oggi
    (``motivo_bot_da_coda``), ``rischio:<client_ref>`` se e' del risk engine,
    altrimenti ``utente`` (comando dell'app). Un ritentativo ``ft...`` con
    ``params.ft_parent`` eredita l'autore della riga ``genitore``; senza
    genitore non prova niente."""
    from Betfair.stream.trading.esposizione_fuori_bot import motivo_bot_da_coda

    r = regole or regole_di_oggi()
    if _testo(riga.get("action")).lower() not in AZIONI_CHE_PIAZZANO:
        return ()
    if bet_id is not None and bet_id_della_riga(riga) != _testo(bet_id):
        return ()
    cref = _testo(riga.get("client_ref"))
    params = riga.get("params") if isinstance(riga.get("params"), Mapping) else {}
    if cref.startswith(PREFISSO_FOLLOW_THROUGH) and params.get("ft_parent") is not None:
        if genitore is None or str(genitore.get("id")) != str(params.get("ft_parent")):
            return ()
        return indizi_da_riga_coda(genitore, r)
    motivo = motivo_bot_da_coda(dict(riga))
    if motivo:
        ind = indizio_da_motivo(motivo)
        return (ind,) if ind is not None else ()
    if cref.startswith(r.prefisso_coda_rischio):
        return (Indizio("coda", f"rischio:{cref}"),)
    return (Indizio("utente", f"coda:{cref}"),)


def indizi_da_riga_tennis(riga: Mapping[str, Any],
                          regole: Optional[RegoleAttribuzione] = None, *,
                          bet_id: Optional[str] = None) -> Tuple[Indizio, ...]:
    """Una riga di ``tennis_live_order_queue`` (colonne vere: ``client_ref``,
    ``payload`` -- il comando, con ``action``, ``comando``/``source`` --,
    ``result``): la stessa regola di ``indizi_da_riga_coda`` (il ``/order`` del
    ladder tennis scrive ``local<sid>``, ``tennis_live_order_worker.py:1830``; i
    comandi del motore ``cmd<id>`` con ``payload.comando``, ``esecutore_tennis.py:266``)."""
    payload = riga.get("payload") if isinstance(riga.get("payload"), Mapping) else {}
    vista = {"client_ref": riga.get("client_ref"), "action": payload.get("action"),
             "params": dict(payload), "result": riga.get("result"),
             "bet_id": payload.get("bet_id")}
    return indizi_da_riga_coda(vista, regole, bet_id=bet_id)


# ---------------------------------------------------------------------------
# replaceOrders: l'ordine NUOVO eredita l'autore di quello SOSTITUITO (terza
# verifica del coordinatore 09/10: parita' col ladder di oggi, dove un ordine
# dell'utente spostato resta controllabile)
# ---------------------------------------------------------------------------
#: prefissi dei ref interni con cui il runner calcio (``live_order_worker._cust_ref``,
#: ``awlq<id>``) e il runner tennis (``awtq<sid>``) scrivono gli specchi
PREFISSO_REF_CALCIO = "awlq"


def origine_della_riga_specchio(riga: Mapping[str, Any]) -> Optional[int]:
    """L'id della richiesta di coda da cui DISCENDE l'ordine di una riga di
    ``betfair_live_orders``: ``request_id`` o il ``client_order_ref``
    ``awlq<id>`` (``live_trading_strategy._request_id_from_ref``). Un rimpiazzo
    di flumine (``Trade.create_order_replacement``) eredita il ``context`` del
    sostituito, quindi lo specchio lo scrive sotto lo STESSO ``awlq<id>``
    della richiesta d'origine, anche dopo piu' replace."""
    rid = riga.get("request_id")
    if rid is not None:
        try:
            return int(rid)
        except (TypeError, ValueError):
            return None
    ref = _testo(riga.get("client_order_ref"))
    if ref.startswith(PREFISSO_REF_CALCIO) and ref[len(PREFISSO_REF_CALCIO):].isdigit():
        return int(ref[len(PREFISSO_REF_CALCIO):])
    return None


def indizi_da_origine(riga_specchio: Mapping[str, Any], riga_coda: Mapping[str, Any],
                      regole: Optional[RegoleAttribuzione] = None) -> Tuple[Indizio, ...]:
    """Gli indizi della richiesta d'ORIGINE (``betfair_live_order_requests``, colonne
    vere) per l'ordine di una riga dello specchio che ne discende: l'ordine
    piazzato o un suo rimpiazzo dopo uno o piu' replace (calcio: la riga di
    replace porta in ``result`` il bet_id VECCHIO, lo snapshot di
    ``_do_replace`` e' preso prima del rimpiazzo asincrono di flumine; il legame
    col nuovo e' lo specchio). La richiesta e' quella con ``id`` = origine (coda
    DB) o ``client_ref`` = ``local<origine>`` (canale locale)."""
    origine = origine_della_riga_specchio(riga_specchio)
    if origine is None:
        return ()
    if str(riga_coda.get("id")) != str(origine) and \
            _testo(riga_coda.get("client_ref")) != f"local{origine}":
        return ()
    return indizi_da_riga_coda(riga_coda, regole)


def eredita(sostituito: Attribuzione, vecchio_bet_id: str, propria: Attribuzione) -> Attribuzione:
    """L'attribuzione dell'ordine NUOVO di un replace: quella dell'ordine
    SOSTITUITO (autore e provvisorieta', qualunque fossero). Fanno eccezione solo
    le prove PROPRIE del nuovo che dicono un bot (una riga di tabella o di coda
    col suo bet_id) o l'attore dichiarato dalla sorgente in prova: restano, e se
    dicono un autore diverso il conflitto si scrive. Niente si inventa: un
    sostituito provvisorio da' un nuovo provvisorio."""
    if propria.fonte == "dichiarato":
        return propria
    if propria.fonte == "indizio" and propria.autore not in AUTORI_UTENTE \
            and propria.autore != SCONOSCIUTO:
        if propria.autore != sostituito.autore:
            return Attribuzione(propria.autore, propria.motivo, propria.fonte,
                                f"sostituisce {vecchio_bet_id} di {sostituito.autore}")
        return propria
    return Attribuzione(sostituito.autore, f"sostituisce:{vecchio_bet_id}", "indizio",
                        sostituito.conflitto, provvisoria=sostituito.provvisoria)


def legame_da_replace_tennis(riga_coda: Mapping[str, Any],
                             riga_specchio: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    """(bet_id sostituito, bet_id nuovo) da una riga di ``tennis_live_order_queue``
    con ``payload.action = replace`` (``payload.bet_id`` = sostituito,
    ``result.customer_order_ref`` = il ref del comando) e la riga di
    ``tennis_live_orders`` del rimpiazzo, scritta sotto lo STESSO ref
    (``tennis_live_order_worker._do_replace`` traccia il trade col ref del
    replace). ``None`` se non e' un replace o i ref non coincidono."""
    payload = riga_coda.get("payload") if isinstance(riga_coda.get("payload"), Mapping) else {}
    if _testo(payload.get("action")).lower() != "replace":
        return None
    vecchio = _testo(payload.get("bet_id"))
    ref = _testo(_risultato(riga_coda).get("customer_order_ref"))
    nuovo = _testo(riga_specchio.get("bet_id"))
    if not vecchio or not ref or not nuovo or nuovo == vecchio:
        return None
    if _testo(riga_specchio.get("client_order_ref")) != ref:
        return None
    return vecchio, nuovo


def indizio_ack_desktop(bet_id: str) -> Indizio:
    """Il bet_id e' fra gli esiti dei comandi mandati DAL DESKTOP (ack del canale
    ``order`` o del comando con attore ``desktop``): evidenza positiva."""
    return Indizio("utente", f"ack_desktop:{_testo(bet_id)}")


def indizio_da_riga_bot(tabella: str, riga: Mapping[str, Any]) -> Indizio:
    """Una riga di una tabella dei bot con quel ``bet_id``. La riga
    ``role='utente'`` di ``mike_trades`` non fa l'ordine di Mike
    (``reconcile_worker._proprietari``, 30/09)."""
    if tabella == "mike_trades" and _testo(riga.get("role")) == "utente":
        return Indizio("adottato", "mike")
    return Indizio("tabella", tabella)


def _autore_di_indizio(ind: Indizio, csr: str, cor: str,
                       r: RegoleAttribuzione) -> Optional[str]:
    """L'autore che un indizio dice (``None`` = l'indizio non dice un bot)."""
    v = ind.valore
    if ind.tipo in ("adottato", "utente"):
        return None
    if ind.tipo == "tabella":
        autore = r.tabelle_bot.get(v)
        if autore == "safe" and (cor.startswith("safe_tennis-") or
                                 csr.lower() == "safe_tennis" or csr.lower() == "tennis"):
            # la tabella di Safe ha calcio e tennis: lo sport lo dicono i
            # riferimenti (ref dell'attore tennis o il terminale tennis)
            return "safe_tennis"
        return autore
    if ind.tipo == "coda":
        tipo, _, val = v.partition(":")
        if tipo == "rischio":
            return RISK
        if tipo == "coda":
            return _autore_da_prefisso(val, r) or SCONOSCIUTO
        val = val.lower()
        if val == r.source_scalper:
            return SCALPER
        return val if val in AUTORI else SCONOSCIUTO
    src = v.strip().lower()
    if ind.tipo == "specchio_tennis":
        if src in ("", "manual"):
            return None
        return src if src in AUTORI else SCONOSCIUTO
    if src in r.source_a_mano or not src:
        return None
    if src == r.source_scalper:
        return SCALPER
    if src.startswith("bot:"):
        a = attribuisci_riferimenti(src[4:], None, r)
        if a.provvisoria:
            return None                      # "bot:tennis" di R1: non dice nulla di piu'
        return a.autore if not a.dell_utente else SCONOSCIUTO
    return src if src in AUTORI else SCONOSCIUTO


def attribuisci(ordine: OrdineDalConto, indizi: Iterable[Indizio] = (),
                regole: Optional[RegoleAttribuzione] = None) -> Attribuzione:
    """Riferimenti dell'ordine, poi gli indizi (il piu' forte che dice un bot
    vince). Un indizio ``adottato`` non sposta mai un ordine dell'utente. Un
    ordine col ref manuale resta PROVVISORIO (``sconosciuto``) finche' un
    indizio non dice un bot o non da' un'evidenza positiva dell'utente."""
    r = regole or regole_di_oggi()
    csr = _testo(ordine.customer_strategy_ref)
    cor = _testo(ordine.customer_order_ref)
    base = attribuisci_riferimenti(csr, cor, r)
    ordinati = sorted(set(indizi), key=lambda i: (_FORZA.get(i.tipo, 9), i.valore))
    for ind in ordinati:
        autore = _autore_di_indizio(ind, csr, cor, r)
        if autore is None:
            continue
        motivo = f"{ind.tipo}:{ind.valore}"
        if autore == base.autore:
            return Attribuzione(autore, motivo, "indizio", base.conflitto)
        conflitto = None
        if base.autore not in AUTORI_UTENTE and base.autore != SCONOSCIUTO:
            conflitto = f"riferimenti dicono {base.autore} ({base.motivo})"
        return Attribuzione(autore, motivo, "indizio", conflitto)
    if base.provvisoria:
        for ind in ordinati:
            if ind.tipo in ("utente", "adottato"):
                return Attribuzione(DESKTOP, f"{ind.tipo}:{ind.valore}", "indizio")
    return base


def attribuisci_dichiarato(attore: Optional[str], ordine: OrdineDalConto,
                           regole: Optional[RegoleAttribuzione] = None) -> Attribuzione:
    """Ordine IN PROVA: la sorgente paper conosce l'attore del comando. Un attore
    che non e' un autore del contratto non si indovina: si torna ai riferimenti
    e il motivo lo dice."""
    a = _testo(attore)
    if a and a in AUTORI:
        return Attribuzione(a, f"attore:{a}", "dichiarato")
    base = attribuisci(ordine, (), regole)
    if a:
        return Attribuzione(base.autore, base.motivo, base.fonte,
                            conflitto=f"attore dichiarato {a!r} fuori dal contratto")
    return base


def autori_ammessi() -> Sequence[str]:
    """Gli autori del contratto (per la UI e i test)."""
    return AUTORI
