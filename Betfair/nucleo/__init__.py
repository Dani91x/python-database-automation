"""Betfair.nucleo - i comparti del modulo Betfair (architettura nuova, dal 09/10/2026).

Un comparto per cartella, un contratto tipato per comparto (``contratto.py``),
un ``COSA_FA.md`` per cartella. Riferimenti: ``ARCHITETTURA_2026-10/04_ARCHITETTURA_OBIETTIVO.md``
(par. 2 l'albero, par. 2.3 le dipendenze ammesse, par. 3 i contratti) e
``ARCHITETTURA_2026-10/AVANZAMENTO.md`` (stato dei lavori).

Comparti:
  * ``betfair/``        (A) sessione, REST, stream dei prezzi e degli ordini del conto, ladder
  * ``ordini/``         (C) porta unica degli ordini, libro ordini del conto, riconciliazione
  * ``dati/``           (G) archivio locale invisibile, postino verso il cloud, registro tabelle
  * ``stato_partita/``  (B) stato della partita calcolato una volta

REGOLA DELL'ONDATA 1 (09/10): il codice di questo pacchetto NON e' agganciato
all'app. Nessun file esistente lo importa finche' la tappa di aggancio non e'
certificata, firmata dal PC e approvata dall'utente (interruttore
``ARCH_<COMPONENTE>=vecchio|ombra|nuovo``, di serie ``vecchio``).

Importare questo pacchetto non deve avere effetti collaterali: niente rete,
niente file, niente thread al caricamento.
"""
