"""minimi.py - UNA definizione delle taglie .it per la porta degli ordini (W1-C1, 09/10/2026).

Scopo
-----
Oggi le regole di taglia (quanto si puo' piazzare su Betfair Italia) vivono in CINQUE
posti (scheda C par. 3 punto 2; ``git grep`` del 09/10, file:riga nel doc
``doc/C1_PORTA.md`` par. 5):

  1. ``Betfair/stream/trading/minimi_it.py`` ``importo_piazzabile`` - LA regola dei
     numeri (punta >= 1,00 a multipli di 0,50 per difetto, banca >= 1,00 al centesimo,
     0,50-0,99 place-and-trim, sotto 0,50 niente);
  2. ``Betfair/stream/trading/submin.py`` ``place_min_size`` / ``porta_al_minimo_apertura``
     / ``verifica_importo_finale`` - il minimo di piazzamento e la "porta al minimo"
     delle aperture tennis;
  3. ``Betfair/stream/live_order_build.py`` ``min_stake_rules`` (e ``verdetto_minimi``) -
     il verdetto del runner (motore e coda);
  4. ``Betfair/stream/tennis_scalper/condotta_ordini.py`` ``size_legale`` / ``diretta_ok``
     / ``spezza_esatta`` - le taglie dei 4 bot tennis;
  5. lo scalper: ``Betfair/stream/scalper/scalper_bot.py`` ``spezza_uscita`` e il
     dimensionamento dentro ``ScalperStrategy._place`` (``MIN_STAKE`` 1,00,
     ``size_step``, ``live_min_bet``), con il gemello tennis
     ``Betfair/stream/tennis_scalper/tennis_scalper_bot.py`` ``_place`` (``MIN_STAKE``
     2,00); in piu' Safe ``safe_strategy/execution.py`` ``_min_size_live``.

Questo modulo NON sceglie fra le definizioni quando divergono (brief comune par. 1
regola 4): ogni definizione di oggi e' una POLITICA esplicita che il chiamante passa,
e per ognuna si restituisce ESATTAMENTE il valore di oggi. I numeri (1,00 / 0,50 /
passo 0,50) NON sono ricopiati: vengono da ``minimi_it`` (import). La parita' e'
provata dal test ``tests/test_c1_minimi.py`` su una griglia di importi, prezzi e lati
contro le funzioni di oggi importate come arbitro.

Entrate: lato (``back``/``lay``, maiuscole accettate dove oggi lo sono), importo,
politica e le opzioni della politica (le stesse di oggi). Uscite: per politica, il
valore di oggi con la stessa forma (tuple, bool, float) oppure ``Taglia``, la forma
uniforme per la porta.

Cosa NON fa: nessuna giurisdizione .com (resta in ``live_order_build``: il conto e'
.it); nessun ordine equivalente sull'altra selezione (``verdetto_minimi`` lo decide
col book: resta nel motore, ``minimi_it.ATTORI_CON_TRADUZIONE`` e' vuoto); nessuna
rete, nessuno stato, nessun file. Importarlo non ha effetti collaterali.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

from Betfair.stream.trading import minimi_it as _MI
from Betfair.stream.trading.minimi_it import (
    IT_MIN_BACK,
    IT_MIN_LAY,
    IT_PASSO_PUNTA_DIRETTA,
    SOTTO_MINIMO_NON_PIAZZABILE,
    SUBMIN_IMPORTO_FINALE_MIN,
    VIA_DIRETTA,
    VIA_NESSUNA,
    VIA_PLACE_AND_TRIM,
    ImportoPiazzabile,
    importo_piazzabile,
)

__all__ = [
    "POLITICHE", "Politica", "Taglia", "VerdettoRunner", "VerdettoPorta", "verdetto_porta", "verdetto_desktop",
    "importo_piazzabile", "verdetto_runner", "porta_al_minimo", "size_legale_tennis",
    "diretta_ok_tennis", "spezza_esatta_tennis", "spezza_uscita_scalper",
    "taglia_scalper", "soglia_safe", "taglia",
]

#: le politiche di oggi, una per definizione (nessuna scelta fra esse)
Politica = Literal[
    "regola_it",            # minimi_it.importo_piazzabile
    "runner",               # live_order_build.min_stake_rules (.it), motore e coda
    "apertura_al_minimo",   # submin.porta_al_minimo_apertura + min_stake_rules = size_legale ingresso
    "copertura_esatta",     # condotta_ordini.size_legale(riduce_liability=True)
    "spezza_tennis",        # condotta_ordini.spezza_esatta
    "spezza_scalper",       # scalper_bot.spezza_uscita
    "scalper_calcio",       # ScalperStrategy._place (dimensionamento)
    "scalper_tennis",       # tennis_scalper_bot._place (dimensionamento)
]
POLITICHE: Tuple[str, ...] = (
    "regola_it", "runner", "apertura_al_minimo", "copertura_esatta",
    "spezza_tennis", "spezza_scalper", "scalper_calcio", "scalper_tennis",
)

# Tolleranze: le STESSE dei moduli di oggi (non sono regole di taglia, sono
# confronti fra float); ognuna e' annotata con la riga da cui viene.
_EPS_LB = 1e-9        # live_order_build._EPS
_TOL_SUBMIN = 1e-6    # trading/submin._TOL (porta_al_minimo_apertura)
_EPS_SCALPER = 1e-9   # scalper_bot._EPS / tennis_scalper_bot._EPS
#: MIN_STAKE degli INGRESSI dello scalper tennis (tennis_scalper_bot.py:86): e' 2,00 e
#: NON viene da minimi_it. Divergenza di oggi (calcio 1,00): riportata, non scelta.
MIN_STAKE_SCALPER_TENNIS = 2.0
#: soglia del "bump" delle uscite dello scalper sotto il minimo (scalper_bot.py _place,
#: tennis_scalper_bot.py _place): da 0,25 in su si arrotonda al gradino da 0,50
SOGLIA_BUMP_SCALPER = 0.25
GRADINO_BUMP_SCALPER = 0.5


@dataclass(frozen=True)
class VerdettoRunner:
    """Gli stessi campi, nello stesso ordine, di ``live_order_build.MinStakeVerdict``."""

    valid: bool
    legalized_size: Optional[float]
    reason: Optional[str]
    residuo: float = 0.0


@dataclass(frozen=True)
class Taglia:
    """La forma UNIFORME di un verdetto di taglia, per la porta.

    ``diretto`` = importo che parte con un ordine diretto (0,0 se nessuno);
    ``place_and_trim`` = parte che va col place-and-trim (0,0 se nessuna);
    ``residuo`` = parte NON piazzata, da dichiarare a chi ha chiesto (mai negativa);
    ``motivo`` = il testo di oggi quando l'ordine (o una parte) non parte;
    ``via`` = ``diretto`` | ``place_and_trim`` | ``spezzata`` (diretta + resto) |
    ``esatta`` (la via ``_place_exact`` dello scalper, che divide a modo suo: la
    divisione NON e' modellata qui, vedi il referto) | ``nessuna``."""

    politica: str
    lato: str
    chiesto: float
    diretto: float
    place_and_trim: float
    residuo: float
    motivo: Optional[str] = None
    via: str = "diretto"

    @property
    def piazzabile(self) -> bool:
        return self.via != "nessuna"


# ---------------------------------------------------------------------------
# 3. il verdetto del runner (live_order_build.min_stake_rules, ramo .it)
# ---------------------------------------------------------------------------
def verdetto_runner(lato: str, importo: Optional[float]) -> VerdettoRunner:
    """``min_stake_rules("it", lato, prezzo, importo)`` di oggi (il prezzo non conta su
    .it). Stessi campi e stessi testi di ``MinStakeVerdict``. Pura."""
    s = (lato or "").lower()
    if s not in ("back", "lay"):
        return VerdettoRunner(False, None, f"side non valido: {lato!r}")
    if importo is None or not math.isfinite(importo) or importo <= 0:
        return VerdettoRunner(False, None, f"size non valida: {importo!r}")
    legale = round(float(importo), 2)
    regola = importo_piazzabile(s, importo)
    if s == "back":
        if regola.via != VIA_DIRETTA:
            return VerdettoRunner(
                False, None,
                f"{SOTTO_MINIMO_NON_PIAZZABILE}: BACK size {legale:.2f} < minimo "
                f"{IT_MIN_BACK:.2f} EUR (.it)")
        return VerdettoRunner(True, regola.importo, None, residuo=regola.residuo)
    if regola.via != VIA_DIRETTA:
        return VerdettoRunner(
            False, None,
            f"{SOTTO_MINIMO_NON_PIAZZABILE}: LAY size {legale:.2f} < minimo "
            f"{IT_MIN_LAY:.2f} EUR (.it, conta lo stake del backer)")
    return VerdettoRunner(True, legale, None)


@dataclass(frozen=True)
class VerdettoPorta:
    """Gli stessi campi di ``live_order_build.VerdettoMinimi`` senza l'equivalente."""

    esito: str              # "diretto" | "submin" | "impossibile"
    size: Optional[float]
    motivo: Optional[str]
    residuo: float = 0.0


def verdetto_porta(lato: str, prezzo: float, importo: float, *,
                   submin_disponibile: bool) -> VerdettoPorta:
    """``live_order_build.verdetto_minimi("it", lato, prezzo, importo,
    altra_selezione=None, submin_disponibile=...)`` di oggi: il verdetto del motore
    quando l'equivalente sull'altra selezione NON e' ammesso (oggi per TUTTI gli
    attori: ``minimi_it.ATTORI_CON_TRADUZIONE`` e' vuoto). Stessi testi. Pura."""
    v = verdetto_runner(lato, importo)
    if v.valid:
        return VerdettoPorta("diretto", v.legalized_size, None, residuo=v.residuo)
    s = (lato or "").lower()
    valida = s in ("back", "lay") and importo is not None
    try:
        valida = valida and math.isfinite(float(importo)) and float(importo) > 0
    except (TypeError, ValueError):
        valida = False
    if not valida:
        motivo = v.reason or "ordine non valido"
        if not motivo.startswith(SOTTO_MINIMO_NON_PIAZZABILE):
            motivo = f"{SOTTO_MINIMO_NON_PIAZZABILE}: {motivo}"
        return VerdettoPorta("impossibile", None, motivo)
    chiesta = round(float(importo), 2)
    perche_no_eq = "mercato non a due esiti (equivalente non applicabile)"
    residuo = (f"residuo {s.upper()} {float(importo):.2f}@{prezzo} NON piazzato: va "
               f"dichiarato al trader (scelta sua: lasciarlo, oppure aumentare e richiudere)")
    if float(importo) < SUBMIN_IMPORTO_FINALE_MIN - _EPS_LB \
            or chiesta < SUBMIN_IMPORTO_FINALE_MIN - _EPS_LB:
        return VerdettoPorta(
            "impossibile", None,
            f"{SOTTO_MINIMO_NON_PIAZZABILE}: {s.upper()} {float(importo):.2f} sotto il minimo "
            f"(e sotto {SUBMIN_IMPORTO_FINALE_MIN:.2f}, importo minimo del place-and-trim: "
            f"sotto il floor di legge di 0,50 non si tenta mai); {perche_no_eq}; {residuo}")
    if not submin_disponibile:
        return VerdettoPorta(
            "impossibile", None,
            f"{v.reason}; {perche_no_eq}; place-and-trim non disponibile su questo "
            f"esecutore; {residuo}")
    return VerdettoPorta(
        "submin", chiesta,
        f"{s.upper()} {chiesta:.2f}@{prezzo} sotto il minimo: place-and-trim ({perche_no_eq}; "
        f"in gioco su .it il bet delay si paga due volte, parcheggio e riprezzo: calcio "
        f"circa 5 -> 10 s)")


def _euro(x: float) -> str:
    """Come ``order_exec._euro``: importo con la virgola decimale (7.5 -> '7,50')."""
    return f"{float(x):.2f}".replace(".", ",")


def verdetto_desktop(lato: str, importo: float) -> Optional[str]:
    """La politica RIFIUTA del terminale del desktop (``order_exec.place_order``, righe
    ~273-290): stesso minimo del runner, ma una punta non multipla di 0,50 NON si tronca:
    si RIFIUTA indicando i due importi validi vicini. None = l'importo passa cosi' com'e';
    altrimenti il testo del ``ValueError`` di oggi. Pura."""
    size = round(float(importo), 2)
    v = verdetto_runner(str(lato).lower(), size)
    if not v.valid:
        return f"stake \u20ac{size:.2f} sotto il minimo Betfair .it: {v.reason}."
    if str(lato).upper() == "BACK" and float(v.residuo or 0.0) > 0.0:
        sotto = float(v.legalized_size)
        sopra = round(sotto + IT_PASSO_PUNTA_DIRETTA, 2)
        return (f"{_euro(size)}: la punta va a multipli di 0,50, usa {_euro(sotto)} o "
                f"{_euro(sopra)}.")
    return None


# ---------------------------------------------------------------------------
# 2. la porta al minimo delle aperture (trading/submin.py)
# ---------------------------------------------------------------------------
def _minimo_lato(lato: str) -> float:
    """``submin.place_min_size("it", lato)``: solleva su un lato non valido come oggi."""
    s = (lato or "").lower()
    if s not in ("back", "lay"):
        raise ValueError(f"side non valido: {lato!r} (atteso back|lay)")
    return IT_MIN_BACK if s == "back" else IT_MIN_LAY


def porta_al_minimo(lato: str, importo: float) -> float:
    """``submin.porta_al_minimo_apertura("it", lato, importo)``: un'apertura sotto il
    minimo del lato si porta AL minimo; sopra resta identica. Pura."""
    s = round(float(importo), 2)
    minimo = round(float(_minimo_lato(lato)), 2)
    return minimo if s < minimo - _TOL_SUBMIN else s


# ---------------------------------------------------------------------------
# 4. le taglie dei bot tennis (tennis_scalper/condotta_ordini.py)
# ---------------------------------------------------------------------------
def diretta_ok_tennis(importo: float, lato: str) -> bool:
    """``condotta_ordini.diretta_ok``: BACK >= minimo e multiplo di 0,50; LAY >= minimo."""
    s = round(float(importo or 0.0), 2)
    up = str(lato or "").upper()
    if up == "BACK":
        return s + 1e-9 >= IT_MIN_BACK and \
            abs(s / IT_PASSO_PUNTA_DIRETTA - round(s / IT_PASSO_PUNTA_DIRETTA)) < 1e-6
    if up == "LAY":
        return s + 1e-9 >= IT_MIN_LAY
    return False


def size_legale_tennis(importo: float, lato: str, *, live: bool,
                       riduce: bool = False) -> Tuple[Optional[float], Optional[str]]:
    """``condotta_ordini.size_legale(importo, lato, live=..., riduce_liability=...)``
    sulla giurisdizione .it: stessa tupla, stessi testi. Pura."""
    s = round(max(0.0, float(importo or 0.0)), 2)
    if s < 0.01:
        return None, "size %.2f sotto il minimo tecnico di 0,01" % s
    if not live:
        return s, None
    up = str(lato or "").upper()
    if up not in ("BACK", "LAY"):
        return None, "side non valido: %r" % lato
    if riduce:
        if diretta_ok_tennis(s, up):
            return s, None
        return None, ("copertura %.2f %s non piazzabile direttamente: va per "
                      "l'uscita esatta (place-and-trim), mai gonfiata" % (s, up))
    s = porta_al_minimo(up.lower(), s)
    verdetto = verdetto_runner(up.lower(), s)
    if not verdetto.valid:
        return None, str(verdetto.reason or "size non legale")
    return round(float(verdetto.legalized_size), 2), None


def spezza_esatta_tennis(importo: float, lato: str) -> Tuple[float, float]:
    """``condotta_ordini.spezza_esatta``: (parte diretta, resto per il place-and-trim)."""
    s = round(float(importo or 0.0), 2)
    up = str(lato or "").upper()
    if diretta_ok_tennis(s, up):
        return s, 0.0
    if up == "BACK" and s + 1e-9 >= IT_MIN_BACK:
        diretta = round(math.floor(s / IT_PASSO_PUNTA_DIRETTA + 1e-9) * IT_PASSO_PUNTA_DIRETTA, 2)
        return diretta, round(s - diretta, 2)
    return 0.0, s


# ---------------------------------------------------------------------------
# 5. lo scalper (scalper_bot.py spezza_uscita e _place; tennis_scalper_bot.py _place)
# ---------------------------------------------------------------------------
def spezza_uscita_scalper(lato: str, importo: float) -> Tuple[float, float, float]:
    """``scalper_bot.spezza_uscita(lato, prezzo, importo)``: (diretta, place-and-trim,
    residuo); il prezzo non conta. Pura."""
    s = round(float(importo or 0.0), 2)
    if s < 0.01:
        return 0.0, 0.0, 0.0
    v = importo_piazzabile("back" if (lato or "").upper() == "BACK" else "lay", s)
    if v.via == VIA_DIRETTA:
        diretta, resto = round(v.importo, 2), round(v.residuo, 2)
        if resto >= 0.01:
            giu = round(diretta - IT_PASSO_PUNTA_DIRETTA, 2)
            if giu >= float(IT_MIN_BACK) - 1e-9:
                return giu, round(s - giu, 2), 0.0
        return diretta, 0.0, resto
    if v.via == VIA_PLACE_AND_TRIM:
        return 0.0, round(v.importo, 2), round(v.residuo, 2)
    return 0.0, 0.0, round(v.residuo, 2)


def _diretta_ok_scalper(variante: str, lato: str, importo: float) -> bool:
    """``_size_direct_ok`` di oggi: calcio passa da ``spezza_uscita``, tennis confronta
    con il minimo del lato e il passo della punta (due scritture della stessa regola)."""
    if variante == "calcio":
        d, trim, residuo = spezza_uscita_scalper(lato, importo)
        return trim <= 0 and residuo <= 0 and abs(d - round(float(importo), 2)) < 1e-6
    minimo = IT_MIN_BACK if (lato or "").upper() == "BACK" else IT_MIN_LAY
    if importo < minimo - _EPS_SCALPER:
        return False
    if (lato or "").upper() != "BACK":
        return True
    mult = importo / _MI.IT_PASSO_PUNTA_RIPIEGO
    return abs(mult - round(mult)) < 1e-6


def taglia_scalper(lato: str, prezzo: float, importo: float, *,
                   variante: Literal["calcio", "tennis"], ingresso: bool,
                   uscita_esatta: bool, size_step: float,
                   live_min_bet: float) -> Tuple[str, Optional[float]]:
    """Il dimensionamento di ``_place`` dello scalper di oggi, SOLO la parte di taglia.

    ``ingresso`` = ``floor_min``; ``uscita_esatta`` = ``exact_exits and not dry_run and
    slot is not None`` (le condizioni di oggi per la via esatta). Ritorna
    ``("diretto", importo)`` (l'ordine LIMIT che parte), ``("esatta", importo)``
    (``_place_exact``: diretta + place-and-trim) oppure ``("nessuno", None)``.
    I freni dopo il dimensionamento (stato del mercato, freno live, freno rifiuti,
    tetto transazioni, dry-run) NON cambiano la taglia e non sono qui. Pura."""
    if variante not in ("calcio", "tennis"):
        raise ValueError(f"variante dello scalper non valida: {variante!r}")
    size = round(float(importo), 2)
    if ingresso:
        minimo_ingresso = float(IT_MIN_BACK) if variante == "calcio" else MIN_STAKE_SCALPER_TENNIS
        if size < minimo_ingresso:
            size = minimo_ingresso
    elif size < 0.01:
        return "nessuno", None
    if float(prezzo) <= 1.0:
        return "nessuno", None
    if not ingresso and uscita_esatta and not _diretta_ok_scalper(variante, lato, size):
        return "esatta", size
    if variante == "calcio":
        arrotonda = size_step > 0 and not (not ingresso and uscita_esatta)
    else:
        arrotonda = size_step > 0 and (str(lato).upper() == "BACK" or ingresso)
    if arrotonda:
        size = round(round(size / size_step) * size_step, 2)
        if size < size_step:
            size = 0.0
    minimo_lato = (float(IT_MIN_BACK) if (lato or "").upper() == "BACK"
                   else float(IT_MIN_LAY)) if live_min_bet > 0 else 0.0
    if live_min_bet > 0 and not ingresso and size < minimo_lato:
        if size >= SOGLIA_BUMP_SCALPER:
            size = max(minimo_lato, round(math.ceil(size / GRADINO_BUMP_SCALPER)
                                          * GRADINO_BUMP_SCALPER, 2))
        else:
            return "nessuno", None
    if size < 0.01:
        return "nessuno", None
    return "diretto", size


# ---------------------------------------------------------------------------
# Safe: la soglia che sceglie fra place normale e place-and-trim
# ---------------------------------------------------------------------------
def soglia_safe(lato: str = "back", override: Optional[str] = None) -> float:
    """``safe_strategy.execution._min_size_live(lato)``: ``override`` e' il valore
    grezzo di ``SAFE_MIN_SIZE_LIVE`` (letto dal CHIAMANTE, qui niente ambiente)."""
    raw = (override or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return float(IT_MIN_LAY) if str(lato).lower() == "lay" else float(IT_MIN_BACK)


# ---------------------------------------------------------------------------
# la forma uniforme per la porta
# ---------------------------------------------------------------------------
def _da_importo(politica: str, lato: str, v: ImportoPiazzabile) -> Taglia:
    if v.via == VIA_DIRETTA:
        return Taglia(politica, lato, v.chiesto, v.importo, 0.0, v.residuo)
    if v.via == VIA_PLACE_AND_TRIM:
        return Taglia(politica, lato, v.chiesto, 0.0, v.importo, v.residuo,
                      via="place_and_trim")
    return Taglia(politica, lato, v.chiesto, 0.0, 0.0, v.residuo,
                  f"{SOTTO_MINIMO_NON_PIAZZABILE}: sotto {SUBMIN_IMPORTO_FINALE_MIN:.2f}",
                  via="nessuna")


def _da_coppia(politica: str, lato: str, chiesto: float, diretta: float, resto: float,
               residuo: float) -> Taglia:
    """Una divisione (diretta, place-and-trim, residuo) nella forma uniforme."""
    if diretta > 0.0 and resto > 0.0:
        via = "spezzata"
    elif diretta > 0.0:
        via = "diretto"
    elif resto > 0.0:
        via = "place_and_trim"
    else:
        via = "nessuna"
    return Taglia(politica, lato, chiesto, diretta, resto, residuo, via=via)


def taglia(politica: str, lato: str, importo: float, *, prezzo: float = 2.0,
           ingresso: bool = True, uscita_esatta: bool = False, size_step: float = 0.0,
           live_min_bet: float = 0.0, live: bool = True) -> Taglia:
    """Il verdetto di taglia della ``politica`` nella forma uniforme ``Taglia``.

    Ogni politica e' una definizione di oggi; le opzioni sono le sue (lo scalper:
    ``ingresso``, ``uscita_esatta``, ``size_step``, ``live_min_bet``; il tennis:
    ``live``). Una politica sconosciuta solleva ``ValueError``: mai un default."""
    s = (lato or "").lower()
    chiesto = round(float(importo or 0.0), 2)
    if politica == "regola_it":
        return _da_importo(politica, s, importo_piazzabile(s, importo))
    if politica == "runner":
        v = verdetto_runner(s, importo)
        if v.valid:
            return Taglia(politica, s, chiesto, float(v.legalized_size), 0.0, v.residuo)
        return Taglia(politica, s, chiesto, 0.0, 0.0, chiesto, v.reason, via="nessuna")
    if politica in ("apertura_al_minimo", "copertura_esatta"):
        size, motivo = size_legale_tennis(importo, s, live=live,
                                          riduce=politica == "copertura_esatta")
        if size is None:
            return Taglia(politica, s, chiesto, 0.0, 0.0, chiesto, motivo, via="nessuna")
        return Taglia(politica, s, chiesto, size, 0.0, 0.0)
    if politica == "spezza_tennis":
        diretta, resto = spezza_esatta_tennis(importo, s)
        return _da_coppia(politica, s, chiesto, diretta, resto, 0.0)
    if politica == "spezza_scalper":
        diretta, trim, residuo = spezza_uscita_scalper(s, importo)
        return _da_coppia(politica, s, chiesto, diretta, trim, residuo)
    if politica in ("scalper_calcio", "scalper_tennis"):
        variante: Literal["calcio", "tennis"] = (
            "calcio" if politica == "scalper_calcio" else "tennis")
        via, size = taglia_scalper(s, prezzo, importo, variante=variante,
                                   ingresso=ingresso, uscita_esatta=uscita_esatta,
                                   size_step=size_step, live_min_bet=live_min_bet)
        if via == "diretto":
            return Taglia(politica, s, chiesto, float(size or 0.0), 0.0, 0.0)
        if via == "esatta":
            return Taglia(politica, s, chiesto, 0.0, 0.0, 0.0,
                          "uscita esatta: la divide _place_exact dello scalper", via="esatta")
        return Taglia(politica, s, chiesto, 0.0, 0.0, chiesto, "nessun ordine (scalper)",
                      via="nessuna")
    raise ValueError(f"politica di taglia sconosciuta: {politica!r} (attese: {POLITICHE})")


#: per i test e il doc: i nomi delle vie della regola unica, riesportati
VIE = (VIA_DIRETTA, VIA_PLACE_AND_TRIM, VIA_NESSUNA)
