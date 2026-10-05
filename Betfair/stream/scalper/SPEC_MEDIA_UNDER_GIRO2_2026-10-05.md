# MEDIA UNDER — secondo giro (05/10/2026): esito della verifica, correzioni, test sui replay

Per chi ha costruito la modalita' (pull request #3, ora integrata su `master`). Resta valida in tutto la
specifica `SPEC_MEDIA_UNDER_2026-10-05.md`: stessi vincoli, stessi file vietati, stessa regola «dove
non e' deciso non decidere».

## 1. Esito della verifica del revisore (sul PC dell'utente, Python 3.13)

- Test nuovi: 122 verdi. Suite `Betfair/` intera sul master integrato: 10123 verdi, 0 rossi. Frontend:
  `tsc` 0 errori, 4971 test verdi, build fatta.
- I 15 scenari certificati dello Scalper + `base`/`paper` sulla 35760084, rilanciati sul codice della
  pull request con la modalita' spenta: IDENTICI riga per riga a quelli del 04/10 (referti in
  `AUDIT_2026-10-05/replay/scalper_15_con_media_spenta/`).
- I tre scenari nuovi lanciati per la prima volta su una registrazione VERA (35797769, referto
  `AUDIT_2026-10-05/replay/media_under_35797769_coord.txt`, 144 s): 0 violazioni. `media-under` e
  `media-under-paper` (Under 2,5): 1 ingresso, 1 rientro, passaggio in gioco, banca PERSIST abbinata in
  gioco, 1 ciclo chiuso; controlli M1-M9 tutti sollecitati. `media-under-35`: NESSUN ordine.
- Falsificazione del revisore, 10 mutazioni: 8 rosse, 2 SOPRAVVISSUTE (punto 2.1).

## 2. Correzioni da fare

### 2.1 Due buchi nei test (mutazioni sopravvissute)

- In `MediaUnderStrategy._forse_rientro`, con `su < self.par.tick_rientro` cambiato in `su < 0` tutti i
  test restano verdi. Il rientro non parte lo stesso (lo ricontrolla `_punta_di_rientro`), ma la banca
  viene annullata e riappoggiata a ogni book. Serve un test: quota salita di meno di N tick dall'ultimo
  ingresso -> nessun annullo della banca, nessun ordine nuovo, stato `IN_POSIZIONE`, per molti book di
  fila. E valuta se il doppio controllo vada lasciato o se `_forse_rientro` debba decidere una volta
  sola (senza cambiare il comportamento).
- In `_assicura_banca`, con il confronto «banca gia' giusta» reso sempre vero (la banca non si
  riallinea mai) tutti i test restano verdi. Serve un test del riallineamento: punta abbinata in due
  tempi (prima una parte, poi il resto) -> banca vecchia annullata, attesa che sia morta, banca nuova
  per l'importo della posizione vera; mai due banche vive insieme durante il passaggio.
- Rifai la falsificazione su questi due punti e riporta la tabella.

### 2.2 Il referto dei replay della modalita' deve dire la verita' a colpo d'occhio

- La riga dello scenario esce `azioni= 0` anche quando la modalita' ha piazzato ordini (conta solo il
  maker, che in questi scenari non e' armato). Deve contare gli ordini della modalita'.
- La nota finale dice «rientri 0; totale puntato 0» dopo un ciclo chiuso: non si capisce cosa e'
  successo. Serve un riepilogo PER CICLO, in euro: quota e importo dell'ingresso, ogni rientro (quota,
  importo esatto e piazzato), totale puntato massimo, banca finale (importo, quota), dove si e'
  abbinata (pre-match o in gioco, minuto), profitto lordo e netto, e la riga `NETTO` come gli altri bot.
- Uno scenario in cui la modalita' non piazza NESSUN ordine non e' un «OK»: deve uscire `NE` (non
  esercitato) col motivo. Oggi `media-under-35` sulla 35797769 esce OK con zero ordini. Aggiungi il
  conteggio dei motivi di non ingresso (quota fuori intervallo, liquidita', flusso, spread, finestra
  prima del fischio, attesa iniziale) cosi' si vede quale filtro ha fermato l'ingresso.

### 2.3 Ordini messi a mano nel riquadro «chiusura» (richiesta dell'utente: «importo reale»)

La tua proposta P14 e' approvata dal revisore con questi limiti: solo in sessione in SOLDI VERI e solo
con posizione aperta; al massimo una lettura per battito della sessione; le righe lette entrano SOLO
nel calcolo del riquadro (mai negli ordini o nei cicli della modalita'); il riquadro scrive la fonte e
l'ora del dato («ordini del bot + ordini del conto letti alle hh:mm:ss») e, se la lettura fallisce,
torna a «solo ordini del bot» dicendolo. In prova mai. Test con righe nella forma vera della tabella.

## 3. Test sui replay (ora puoi lanciarli)

Le registrazioni sono nel repository, compresse: `registrazioni_banco/` (leggi `LEGGIMI.md`: si
scompattano in `_live_raw/`). Regole: solo dal punto d'ingresso unico `python -m
Betfair.stream.backtest.certifica scalper_calcio <evento> --scenari ...`, UN replay alla volta, ognuno
sotto i 5 minuti (tetto 10: un replay piu' lento e' un difetto da riportare, non da aspettare), mai
dati inventati, mai registrazioni modificate.

1. Conferma di non regressione: i 15 scenari dello Scalper sulla 35797769 e `base,paper` sulla 35760084
   devono restare identici ai referti in `AUDIT_2026-10-05/replay/scalper_15_con_media_spenta/` (righe
   `OK`/`KO`).
2. I tre scenari `media-under*` su ENTRAMBE le registrazioni.
3. Scenari dichiarati in piu' (stessa registrazione, parametri diversi, ognuno col suo nome e la sua
   descrizione nel banco): obiettivo fisso 0,30 netti; `media_max_rientri` = 1; `media_rischio_max` =
   30; `media_tick_rientro` = 1 con `media_tick_chiusura` = 1. Per ognuno il riepilogo per ciclo del
   punto 2.2.
4. Scenari di guasto usando l'infrastruttura che il banco ha gia' per lo Scalper (`riavvio`,
   `rifiuti-betfair`, `esiti-ignoti`, `kill-switch`, `bot-fermo`) con la modalita' accesa: cosa resta a
   mercato, cosa viene dichiarato, nessun ordine dopo il blocco.
5. Nel referto: per ogni scenario esito, controlli M sollecitati / mai sollecitati, tempi. Se su queste
   due registrazioni un controllo M non viene mai sollecitato, dillo: non forzarlo.

Se un replay mostra un comportamento diverso dalla specifica: correggi la causa con un test che la
riproduce (falsificato), e scrivi nel referto prima -> dopo.

## 4. Punti in attesa della decisione dell'utente (NON toccarli)

P1 (stop della sessione con posizione aperta: oggi l'arresto toglie anche la banca PERSIST), P8 (salto
di quota: importo del rientro senza limite se `media_rischio_max` e' spento), P13 (riavvio a posizione
aperta: modalita' bloccata). Restano come sono finche' l'utente non decide.

## 5. Consegna

Ramo nuovo `feature/scalper-media-under-giro2` da `master`, pull request verso `master`, commit con
percorsi espliciti (mai `git add -A`), nessuna riga di attribuzione. Referto
`AUDIT_2026-10-05/SCALPER_MEDIA_UNDER_GIRO2.md` con i referti dei replay in
`AUDIT_2026-10-05/replay/giro2/` e, in evidenza, cio' che non hai potuto verificare.
