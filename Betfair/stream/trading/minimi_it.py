"""Minimi di puntata di Betfair Exchange Italia: UNA definizione per tutto il repo.

04/10/2026 - REGOLA DELLE PUNTE (ordine dell'utente, testuale: "SOTTO 1 EURO si usa place
and trim (0.50 il minimo), SOPRA 1 EURO i MULTIPLI DI 0.50 FUNZIONANO, IN BACK"):

  * PUNTA piazzata DIRETTA: da 1,00 EUR in su SOLO multipli di 0,50 (1,00 / 1,50 /
    2,00 ...). Una punta di importo calcolato non multiplo si arrotonda PER DIFETTO
    (decisione dell'utente del 04/10: 7,27 -> 7,00); il resto (0,27) NON e'
    piazzabile e va DICHIARATO a chi ha chiesto l'ordine (mai dimenticato in
    silenzio: lo chiude l'utente);
  * PUNTA sotto 1,00: place-and-trim, importo finale minimo 0,50
    (``SUBMIN_IMPORTO_FINALE_MIN``); sotto 0,50 nessun ordine, con nessuna tecnica;
  * BANCA invariata: minimo 1,00 EUR sulla PUNTATA DEL BACKER (il ``size`` di una LAY,
    mai la liability), al centesimo (banche del bot accettate al centesimo: 5,07 /
    6,32 / 6,23); sotto 1,00 place-and-trim con finale >= 0,50, sotto 0,50 niente;
  * NESSUNA eccezione per gli ordini che riducono l'esposizione (chiusure, green-up,
    hedge): il 01/10 una banca di chiusura da 0,43 @18 e' stata rifiutata
    ``INVALID_BET_SIZE`` 21 volte; il 04/10 (Umea FC v Hammarby, LIVE) una PUNTA di
    chiusura da 7,27 @1,07 e' stata rifiutata ``INVALID_BET_SIZE``.

PERCHE' LA VERSIONE DEL 01/10 ERA SBAGLIATA. Il 01/10 qui si era scritto "punta al
centesimo, nessun passo di 0,50: la punta da 7,47 EUR del 01/10 e' stata accettata e
abbinata". Quella punta era un ordine messo dall'UTENTE dal SITO (Cash Out, riga
``role='utente'``), non dal bot via API: il Cash Out del sito non e' soggetto ai minimi
degli ordini via API (il 04/10 lo stesso Cash Out ha chiuso con banche da 0,47 e 0,03).
Tutte le punte non multiple di 0,50 accettate sul conto erano dell'utente; tutte le punte
del bot accettate erano multiple di 0,50; l'unica punta del bot non multipla (7,27) e'
stata rifiutata. Una regola di Betfair si prova SOLO con ordini del bot via API. La
documentazione per sviluppatori ("can only be incremented in multiples of 50 Euro Cents")
aveva ragione sul passo; il minimo diretto resta 1,00 (Nota informativa betfair.it).

Fonti: AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md, CRONOSTORIA 04/10 (righe 5161-5170
di ``mike_trades``). Modulo SENZA dipendenze (nemmeno flumine): lo importano il motore
ordini (``live_order_build``, ``trading.submin``), il banco (``backtest.minimi_banco``),
Safe (``execution._min_size_live``), Omega (``omega_market.SUBMIN_MIN_*``) e Mike, con
questi nomi esatti. Non ridefinire questi numeri altrove: un duplicato e' un difetto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any

#: PUNTA minima .it (EUR) piazzata diretta
IT_MIN_BACK = 1.00
#: BANCA minima .it (EUR) sul size = puntata del backer (la liability non conta), al centesimo
IT_MIN_LAY = 1.00
#: floor di legge (DM 47/2013 art. 8): sotto non si va MAI, con nessuna tecnica
IT_FLOOR_LEGGE = 0.50
#: 04/10/2026 - passo della PUNTA piazzata DIRETTA da ``IT_MIN_BACK`` in su: solo
#: multipli di 0,50 (regola dell'utente; documentazione per sviluppatori "multiples of
#: 50 Euro Cents"). Vale PRIMA di mandare, non solo dopo un rifiuto.
IT_PASSO_PUNTA_DIRETTA = 0.50
#: alias storico (01/10: era il passo del SOLO ripiego dopo un ``INVALID_BET_SIZE``)
IT_PASSO_PUNTA_RIPIEGO = IT_PASSO_PUNTA_DIRETTA
# TRE soglie, da non confondere (decisione del coordinatore, 01/10/2026; passo 04/10):
#   * ordine piazzato DIRETTO: >= 1,00 (``IT_MIN_BACK`` / ``IT_MIN_LAY``), la PUNTA a
#     multipli di ``IT_PASSO_PUNTA_DIRETTA``;
#   * place-and-trim: parcheggio >= 1,00 (il parcheggio e' un ordine diretto) e importo
#     FINALE dopo la riduzione >= 0,50, il floor di LEGGE (DM 47/2013 art. 8; le guide
#     italiane 2014-2020 ottengono 0,50 / 1,00 / 1,50 riducendo);
#   * sotto 0,50: MAI nessun ordine, con nessuna tecnica (nessuna testimonianza di
#     riuscita; "rifiutato del tutto"): rifiuto esplicito, residuo dichiarato al trader.
#: importo FINALE minimo di un place-and-trim su .it (= floor di legge)
SUBMIN_IMPORTO_FINALE_MIN = IT_FLOOR_LEGGE
#: 02/10/2026 (RUNNER_MINIMI_CORREZIONI, punto 11, decisione del coordinatore): chi sa
#: riconciliare un ordine tradotto nello specchio, nei cleared e nei ripieghi REST. La via
#: "equivalente sull'altra selezione" del motore vale SOLO per questi attori (``attore`` /
#: ``strategy_ref`` del comando), in paper come in live. Oggi NESSUNO: Safe e Omega
#: rileggono l'ordine VERO nei ripieghi live oltre la scadenza (difetti aperti), Mike in
#: live non passa dal canale (ha la sua patch), gli ordini manuali dell'app aspettano la
#: conferma dell'utente sul green-up di mercato. Per tutti gli altri: diretto ->
#: place-and-trim (finale >= 0,50) -> rifiuto ``SOTTO_MINIMO_NON_PIAZZABILE``. Un attore si
#: aggiunge solo dopo averne verificato la riconciliazione.
ATTORI_CON_TRADUZIONE: frozenset = frozenset()
#: codice INTERNO del rifiuto di un ordine sotto il minimo senza via legittima
SOTTO_MINIMO_NON_PIAZZABILE = "SOTTO_MINIMO_NON_PIAZZABILE"

#: le vie di ``importo_piazzabile``
VIA_DIRETTA = "diretto"
VIA_PLACE_AND_TRIM = "place_and_trim"
VIA_NESSUNA = "nessuna"

_TOL = 0.0005


@dataclass(frozen=True)
class ImportoPiazzabile:
    """Come esce un importo rispetto ai minimi .it (``importo_piazzabile``).

    ``chiesto`` = l'importo chiesto al centesimo; ``importo`` = quello che parte
    (0,0 con ``VIA_NESSUNA``); ``residuo`` = chiesto - importo, la parte che NON parte
    e va dichiarata (mai negativa)."""

    via: str
    chiesto: float
    importo: float
    residuo: float


def _centesimi(x: Any) -> Decimal:
    return Decimal(str(round(float(x), 2)))


def importo_piazzabile(lato: str, importo: Any) -> ImportoPiazzabile:
    """LA regola dei minimi .it per UN ordine: dato il lato (``back``/``lay``) e
    l'importo chiesto, la via e l'importo piazzabile, col residuo. Pura.

      * punta >= 1,00: diretta, a multiplo di 0,50 PER DIFETTO (7,27 -> 7,00, residuo
        0,27); banca >= 1,00: diretta al centesimo, residuo 0;
      * 0,50 <= importo < 1,00 (entrambi i lati): place-and-trim dell'importo chiesto;
      * sotto 0,50 (o non numerico / non positivo): nessun ordine, residuo = chiesto.

    Solleva ``ValueError`` solo su un lato non valido."""
    s = str(lato or "").strip().lower()
    if s not in ("back", "lay"):
        raise ValueError(f"lato non valido: {lato!r} (atteso back|lay)")
    try:
        x = float(importo)
    except (TypeError, ValueError):
        return ImportoPiazzabile(VIA_NESSUNA, 0.0, 0.0, 0.0)
    if not math.isfinite(x) or x <= 0:
        return ImportoPiazzabile(VIA_NESSUNA, 0.0, 0.0, 0.0)
    try:
        chiesto = _centesimi(x)
    except InvalidOperation:
        return ImportoPiazzabile(VIA_NESSUNA, 0.0, 0.0, 0.0)
    c = float(chiesto)
    minimo = IT_MIN_LAY if s == "lay" else IT_MIN_BACK
    if c >= minimo - _TOL:
        if s == "lay":
            return ImportoPiazzabile(VIA_DIRETTA, c, c, 0.0)
        passo = Decimal(str(IT_PASSO_PUNTA_DIRETTA))
        giu = (chiesto / passo).to_integral_value(rounding=ROUND_FLOOR) * passo
        d = float(giu)
        return ImportoPiazzabile(VIA_DIRETTA, c, d, float(chiesto - giu))
    if c >= SUBMIN_IMPORTO_FINALE_MIN - _TOL:
        return ImportoPiazzabile(VIA_PLACE_AND_TRIM, c, c, 0.0)
    return ImportoPiazzabile(VIA_NESSUNA, c, 0.0, c)


def punta_diretta_valida(importo: Any) -> bool:
    """True se una PUNTA di questo importo e' piazzabile DIRETTA cosi' com'e' (>= 1,00 e
    multipla di 0,50). Pura."""
    v = importo_piazzabile("back", importo)
    return v.via == VIA_DIRETTA and v.residuo <= 0.0
