"""Minimi di puntata di Betfair Exchange Italia: UNA definizione per tutto il repo.

01/10/2026 - CORREZIONE DEFINITIVA (ordine dell'utente, confermato dalla Nota informativa di
betfair.it: "L'importo minimo della scommesse nello Sport e su Exchange e' pari a Euro
1,00"; blog ufficiale betfair.it del 30/10/2023: anche la bancata minima a 1 EUR):

  * PUNTA minima 1,00 EUR, al centesimo (nessun passo di 0,50: la punta da 7,47 EUR del
    01/10 e' stata accettata e abbinata);
  * BANCA minima 1,00 EUR sulla PUNTATA DEL BACKER (il ``size`` di una LAY, mai la
    liability), al centesimo;
  * NESSUNA eccezione per gli ordini che riducono l'esposizione (chiusure, green-up,
    hedge): il 01/10 una banca di chiusura da 0,43 @18 e' stata rifiutata
    ``INVALID_BET_SIZE`` 21 volte;
  * floor di legge (DM 18/03/2013 n. 47, art. 8): 0,50 EUR. Sotto non si va con nessun
    trucco. Sotto il minimo diretto (1,00) le vie del motore ordini, in quest'ordine:
    l'ordine EQUIVALENTE sul lato opposto dell'altra selezione di un mercato a due
    esiti; il place-and-trim con parcheggio >= 1,00 e importo finale >= 0,50
    (``SUBMIN_IMPORTO_FINALE_MIN``); altrimenti il rifiuto esplicito
    ``SOTTO_MINIMO_NON_PIAZZABILE`` col residuo dichiarato al trader.

Fonti: AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md e
AUDIT_2026-10-01/RICERCA_TOOL_ITALIA_STAKE_MINIMI.md. Modulo SENZA dipendenze (nemmeno
flumine): lo importano il motore ordini (``live_order_build``, ``trading.submin``), Safe
(``execution._min_size_live``), Omega (``omega_market.SUBMIN_MIN_*``) e Mike, con questi
nomi esatti. Non ridefinire questi numeri altrove: un duplicato e' un difetto.
"""
from __future__ import annotations

#: PUNTA minima .it (EUR), al centesimo
IT_MIN_BACK = 1.00
#: BANCA minima .it (EUR) sul size = puntata del backer (la liability non conta)
IT_MIN_LAY = 1.00
#: floor di legge (DM 47/2013 art. 8): sotto non si va MAI, con nessuna tecnica
IT_FLOOR_LEGGE = 0.50
#: passo della documentazione per sviluppatori ("multiples of 50 Euro Cents"), smentito
#: dall'API il 01/10: usato SOLO per l'unico ripiego dopo un INVALID_BET_SIZE reale
IT_PASSO_PUNTA_RIPIEGO = 0.50
# TRE soglie, da non confondere (decisione del coordinatore, 01/10/2026):
#   * ordine piazzato DIRETTO: >= 1,00 (``IT_MIN_BACK`` / ``IT_MIN_LAY``);
#   * place-and-trim: parcheggio >= 1,00 (il parcheggio e' un ordine diretto) e importo
#     FINALE dopo la riduzione >= 0,50, il floor di LEGGE (DM 47/2013 art. 8; le guide
#     italiane 2014-2020 ottengono 0,50 / 1,00 / 1,50 riducendo);
#   * sotto 0,50: MAI nessun ordine, con nessuna tecnica (nessuna testimonianza di
#     riuscita; "rifiutato del tutto"): rifiuto esplicito, residuo dichiarato al trader.
#: importo FINALE minimo di un place-and-trim su .it (= floor di legge)
SUBMIN_IMPORTO_FINALE_MIN = IT_FLOOR_LEGGE
#: codice INTERNO del rifiuto di un ordine sotto il minimo senza via legittima
SOTTO_MINIMO_NON_PIAZZABILE = "SOTTO_MINIMO_NON_PIAZZABILE"
