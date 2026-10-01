# Reperto 3 (RUNNER_MINIMI_CHIUSURE): divergenza di strategia da portare all'utente

Data: 01/10/2026. Va portato all'utente domani. Le strategie NON sono state toccate.

Si applicano i minimi .it definitivi del 01/10:
- ordine diretto: almeno 1,00 per la punta e per la banca;
- place-and-trim: parcheggio da 1,00 e importo finale di almeno 0,50;
- sotto 0,50 nessun ordine: rifiuto `SOTTO_MINIMO_NON_PIAZZABILE`, con il residuo dichiarato.

Con queste regole, alcune uscite che le strategie decidono oggi non si possono eseguire su .it.
**In live Betfair le rifiutava gia'** (`INVALID_BET_SIZE`). In paper invece venivano
«eseguite», perche' il client simulato non conosce i minimi.

## 1. Take-profit di Omega a quota 1000

- Caso tipico: banca 5,00 @55 sul Risultato Esatto, chiusa in take-profit puntando la stessa
  selezione a circa 990-1000. La punta di chiusura vale 5 x 55 / 1000, circa **0,28 EUR**.
- Per costruzione e' sempre cosi': il take-profit chiede un utile bloccato di almeno 4,50 su
  5,00, quindi una quota di almeno circa 550. A quelle quote la punta di chiusura resta sotto
  i 0,50 EUR con questi stake.
- Il Risultato Esatto ha piu' di 2 esiti, quindi l'equivalente sull'altra selezione non
  esiste. Sotto 0,50 il place-and-trim non e' ammesso. Esito: **rifiuto certo**, e la
  posizione resta aperta col residuo dichiarato.
- Nel codice di oggi:
  - fuori dal canale: `execution.place` rifiuta prima di qualunque invio;
  - sul canale: il motore rifiuta `SOTTO_MINIMO_NON_PIAZZABILE`.
- Test di logica coinvolti, isolati dai minimi con la manopola `SAFE_MIN_SIZE_LIVE` (c'e'
  il commento in ogni test):
  - `omega/test_omega_greenup_2026_09_10.py`: `test_take_profit_blocca_il_profitto_quasi_pieno`,
    `test_p_o1_green_up_integrale_col_fill_in_volo_e_greenup`;
  - `omega/test_omega_audit_2026_09_11.py`: `test_rev_h3_...`, `test_rev_m3_...`,
    `test_rev_m4_...`.

## 2. Residui sotto 0,50 delle uscite di Safe

- Le uscite di Safe con fill cappato dalla liquidita' lasciano residui piccoli (per esempio
  0,85 o 0,92 nei test), e la seconda passata li richiude.
- Sui mercati a piu' di 2 esiti, senza canale:
  - **tra 0,50 e 1,00** si richiudono col place-and-trim;
  - **sotto 0,50** sono un rifiuto certo, e il residuo resta dichiarato.
- Test di logica coinvolti, isolati con la stessa manopola:
  - `safe_strategy/tests/test_bot_service.py`: 3 test sui residui di uscita;
  - `safe_strategy/tests/test_audit_2026_09_11.py`: `test_rev_m3_green_up_in_coda_resta_greenup`.

## 3. Domande per l'utente

1. Per Omega: si accetta che il take-profit sotto 0,50 non sia eseguibile? Oppure si cambia
   la regola di uscita (stake, soglia, quota) tenendo il paper uguale al live?
2. Per Safe: il residuo sotto 0,50 si lascia aperto e dichiarato, oppure si «aumenta e si
   richiude» (scelta del trader, come per gli strumenti autorizzati ADM)?
