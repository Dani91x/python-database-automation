# DOPO W3a - Safe (base, esatto, punta) - replay cloud del 08/10

Codice: `b4d91ed` (ramo `claude/blissful-sagan-hri7o6-w3a-dopo-safe`), impronta del codice bot nei
referti `ee82ce75a8ad` (19 file). PRIMA = `AUDIT_2026-10-08/riferimenti_cloud/` (su `1ac69d0`,
impronta `19cd848fe8d2`).

Comando, per ognuno dei 6 lanci (registrazioni decompresse in `_live_raw/` con lo script di
`registrazioni_banco/LEGGIMI.md`):
`python -m Betfair.stream.backtest.certifica <bot> <evento> --scenari tutti --worker 1`

Macchina: **nproc = 4**. Lanci in parallelo con `xargs -P 4` (4 insieme, poi i 2 di safe_punta
appena si liberava un posto). Durata complessiva dei 6 lanci: **3021 s**. Nota: il LEGGIMI dice
«uno alla volta»; il parallelo e' per ordine del coordinatore, quindi i tempi sono gonfiati dalla
contesa sulle CPU (gli esiti no: il banco gira a tempo di mercato).

Stdout e stderr dello stesso file (`2>&1`): le righe `WARNING:`/`CRITICAL:` in coda ai referti
DOPO sono quelle che nel PRIMA stavano nei `.err` separati (verificato su safe_base 35760084: stesse
10 righe WARNING, identiche).

## Esiti

| bot | evento | ESITO | OK | NE | KO | tempo DOPO (certifica) | tempo PRIMA |
|---|---|---|---|---|---|---|---|
| safe_base   | 35760084 | 23 senza violazioni, 0 con violazioni | 22 | 1 | 0 | 686.7 s | 426.1 s |
| safe_base   | 35797769 | 23 senza violazioni, 0 con violazioni | 23 | 0 | 0 | 2409.5 s | 1422.0 s |
| safe_esatto | 35760084 | 23 senza violazioni, 0 con violazioni | 22 | 1 | 0 | 675.6 s | 416.3 s |
| safe_esatto | 35797769 | 23 senza violazioni, 0 con violazioni | 23 | 0 | 0 | 2418.5 s | 1426.3 s |
| safe_punta  | 35760084 | 23 senza violazioni, 0 con violazioni | 22 | 1 | 0 | 656.3 s | 423.6 s |
| safe_punta  | 35797769 | 23 senza violazioni, 0 con violazioni | 23 | 0 | 0 | 2329.5 s | 1415.1 s |

Tempi misurati con `time` di bash (reale / user): base 35760084 689.3/670.7; base 35797769
2412.2/2372.0; esatto 35760084 678.1/664.6; esatto 35797769 2421.0/2377.3; punta 35760084
658.7/644.9; punta 35797769 2331.7/2296.6. Tutti sopra il tetto di 600 s (avviso LENTO, l'esito
non cambia); il PRIMA era gia' sopra (1415-1426 s su 35797769).

**Scenari KO: nessuno.** Nessun controllo con `viol>0` in nessuno dei 6 referti.
NE (non esercitato, senza violazioni): `35760084 [chiusura-fuori-app-canale]` per i tre bot (la Safe
non apre su 35760084: atteso).

I tre bot (base/esatto/punta) danno referti identici fra loro nelle righe confrontate (stesso
servizio con tutte e tre le strategie accese): i confronti PRIMA/DOPO dei tre sono identici byte per
byte per ciascun evento.

## Differenze dal PRIMA

Confronto con `confronti/confronta.py` (esclusi: righe di tempo, LENTO, TEMPO TOTALE, impronta del
codice, comando, percorso delle registrazioni). Uscite complete in `confronti/`.

### ATTESE (referto W3A §4.1 e §10)

1. **Scenario NUOVO `chiusura-fuori-app-canale`** (elenco SCENARI in testa, ESITO da 22 a 23):
   * 35760084, tre bot: `NE 35760084 [chiusura-fuori-app-canale] tick= 41300 decisioni= 3512 azioni= 0 stati=running/live [COMPLETE]`
   * 35797769, tre bot: `OK 35797769 [chiusura-fuori-app-canale] tick=117781 decisioni= 6452 azioni= 2 stati=running/live [COMPLETE]`;
     T14 x919 conforme; «canale del conto: messaggi 1 | verdetto 'chiusa' 'fuori dall'app (stream
     ordini)' | latenza dallo stream al verdetto 0 ms».
2. **`chiusura-fuori-app-ridotta` cambia su 35797769 (ora ferma il bot)**, tre bot uguali:
   * PRIMA: `OK 35797769 [chiusura-fuori-app-ridotta] tick=117376 decisioni= 6449 azioni= 2 stati=running/live [COMPLETE]`
   * DOPO:  `OK 35797769 [chiusura-fuori-app-ridotta] tick=117781 decisioni= 6452 azioni= 2 stati=running/live [COMPLETE]`
   * nel blocco: `uscite valutate` da 908 a 0; attivita' da `posizione_di_conto x64, ..., exit_hold
     x23, exit_wait x6, skip x2, ...` a `..., skip x4, ..., posizione_di_conto x1,
     chiuso_dall_utente x1, ...`; scarti `+ partita_chiusa_dall_utente x2`; nuova nota
     `[CHIUSO IL 16/09] ...` (verifica T14); **T14 da x0 «non lo so» a x919 conforme**; E8, E9 da
     x908 conforme a x0 «non lo so» e T4 da x444 conforme a x0 «non lo so» (il bot e' fermo, non
     valuta piu' uscite); contatori B/E/P/T/J/K +3..+6 per i 3 giri in piu'.
   * su 35760084 lo scenario e' IDENTICO al PRIMA (la Safe non apre).
3. **Nota «NON ESERCITABILE: proprietari_bot_conto»** solo su 35797769, negli scenari
   `chiusura-fuori-app`, `chiusura-fuori-app-ridotta`, `chiusura-fuori-app-canale`:
   `nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: proprietari_bot_conto: tabelle degli altri bot e coda del runner (proprietari degli ordini altrui sul conto): non sono nel replay, un ordine non del bot si decide dai riferimenti (nessun altro bot)`.
   Su 35760084 non compare (nessun ordine del conto da classificare).
4. Coda (copertura): i contatori crescono dei soli giri dello scenario nuovo (35760084: B x63878 ->
   x66924, +3046 = un giro di `base`; 35797769: B x80841 -> x84694, T14 x1838 -> x3676 = 2 -> 4
   scenari a x919) e dei giri in piu' di `-ridotta`; E8/E9 x10975 -> x10067 e T4 x5364 -> x4920
   (la `-ridotta` non valuta piu' uscite). Nessun controllo in violazione.

### NON ATTESE

Una sola, su **35797769, tutti e tre i bot**, solo righe di NOTA (esito, tick, decisioni, azioni e
controlli invariati in entrambi gli scenari): la dichiarazione dei metodi assenti `save_event_model`
/ `get_event` passa dallo scenario `chiusura-abbinata-in-parte` allo scenario `manuale-e-bot`.

* `manuale-e-bot` (riga di esito identica: `OK 35797769 [manuale-e-bot] tick=117375 decisioni= 6450 azioni= 4 stati=running/live [COMPLETE]`)
  * PRIMA: `      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive']`
  * DOPO:  `      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive', 'save_event_model']`
  * DOPO, riga in piu': `      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: get_event: tabella `events` (anagrafica partite): non e' nello stream di mercato registrato`
* `chiusura-abbinata-in-parte` (riga di esito identica: `OK 35797769 [chiusura-abbinata-in-parte] tick=117295 decisioni= 6447 azioni= 5 stati=running/live [COMPLETE]`)
  * PRIMA: `      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive', 'save_event_model']`
  * PRIMA, riga che manca nel DOPO: `      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: get_event: tabella `events` (anagrafica partite): non e' nello stream di mercato registrato`
  * DOPO:  `      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive']`

Negli altri scenari che dichiarano `save_event_model` (`base`, `proposta-*`, `combos-*`) nessun
cambiamento. Lo spostamento e' uguale per i tre bot, quindi riproducibile e non dovuto al caso.
`manuale-e-bot` gira PRIMA dello scenario nuovo, quindi non lo spiega l'ordine degli scenari. Non
ho trovato chiamate dirette a `get_event`/`save_event_model` nel codice della Safe
(`grep`: solo `bot_db.get_event` e i finti dei replay), quindi la causa va cercata nel percorso che
le chiama (probabilmente il modello evento condiviso con Omega, raggiunto in modo indiretto). **Non
indagato oltre (non ho modificato codice): da portare al coordinatore.**

Nessuna altra riga diversa negli scenari esistenti, su nessuno dei 6 referti.
