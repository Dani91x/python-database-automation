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


@dataclass(frozen=True)
class Attribuzione:
    """L'esito: ``autore`` del contratto, ``motivo`` leggibile (nel vocabolario dei
    motivi di oggi: ``strategia:<csr>``, ``ref:<cor>``, ``tabella:<t>``...),
    ``fonte`` (riferimenti, indizio o autore dichiarato dalla sorgente in prova),
    ``conflitto`` se due fonti dicevano due bot diversi (mai nascosto)."""

    autore: str
    motivo: str
    fonte: FonteAttribuzione
    conflitto: Optional[str] = None

    @property
    def dell_utente(self) -> bool:
        return self.autore in AUTORI_UTENTE


TipoIndizio = Literal["tabella", "coda", "specchio", "specchio_tennis", "adottato"]
#: forza degli indizi (minore = piu' forte): la tabella del bot non mente
#: (``esposizione_fuori_bot.bot_di``), poi la riga di coda, poi lo specchio
_FORZA: Mapping[str, int] = {"tabella": 0, "coda": 1, "specchio": 2, "specchio_tennis": 2,
                             "adottato": 3}


@dataclass(frozen=True)
class Indizio:
    """Un fatto letto altrove (DB, specchio, coda) su un ``bet_id``, come dato.

    ``tipo``: ``tabella`` (riga in una tabella dei bot: ``valore`` = tabella),
    ``coda`` (riga di ``betfair_live_order_requests``: ``valore`` = il motivo di
    ``motivo_bot_da_coda`` o ``rischio:<client_ref>``), ``specchio`` /
    ``specchio_tennis`` (``source`` della riga), ``adottato`` (riga
    ``role='utente'`` di ``mike_trades``: l'ordine resta dell'utente,
    ``reconcile_worker._proprietari``)."""

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
        return Attribuzione(DESKTOP, f"strategia_manuale:{s}", "riferimenti")
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


def indizi_da_riga_coda(riga: Mapping[str, Any],
                        regole: Optional[RegoleAttribuzione] = None) -> Tuple[Indizio, ...]:
    """Una riga di ``betfair_live_order_requests`` (chiavi della tabella:
    ``client_ref``, ``params``): il motivo di oggi (``motivo_bot_da_coda``) o,
    se e' del risk engine, ``rischio:<client_ref>``. Vuota = nessun bot."""
    from Betfair.stream.trading.esposizione_fuori_bot import motivo_bot_da_coda

    r = regole or regole_di_oggi()
    motivo = motivo_bot_da_coda(dict(riga))
    if motivo:
        ind = indizio_da_motivo(motivo)
        return (ind,) if ind is not None else ()
    cref = _testo(riga.get("client_ref"))
    if cref.startswith(r.prefisso_coda_rischio):
        return (Indizio("coda", f"rischio:{cref}"),)
    return ()


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
    if ind.tipo == "adottato":
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
        return a.autore if not a.dell_utente else SCONOSCIUTO
    return src if src in AUTORI else SCONOSCIUTO


def attribuisci(ordine: OrdineDalConto, indizi: Iterable[Indizio] = (),
                regole: Optional[RegoleAttribuzione] = None) -> Attribuzione:
    """Riferimenti dell'ordine, poi gli indizi (il piu' forte che dice un bot
    vince). Un indizio ``adottato`` non sposta mai un ordine dell'utente."""
    r = regole or regole_di_oggi()
    csr = _testo(ordine.customer_strategy_ref)
    cor = _testo(ordine.customer_order_ref)
    base = attribuisci_riferimenti(csr, cor, r)
    for ind in sorted(indizi, key=lambda i: (_FORZA.get(i.tipo, 9), i.valore)):
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
