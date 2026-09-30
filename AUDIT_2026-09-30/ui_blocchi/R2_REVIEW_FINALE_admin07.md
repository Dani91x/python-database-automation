# R2 — correzioni dalla review finale (admin-07), 30/09 ore 22:26

Patch: `R2_REVIEW_FINALE.patch` (21 file, +266/−51, solo `frontend/src`, md5 d5c4d64c2678),
`apply --check` pulita su F2b `55df3f8` e su F3 `7f708eb`. Costruita da me sull'albero
`scratchpad/integra` (= F2b + queste correzioni): ogni reperto riletto nel codice prima
di correggerlo; ogni correzione con un test che la falsifica (6 mutazioni mie, tutte rosse,
ripristino da copia con `cmp`).

Fonti dei reperti: revisore indipendente A (regressioni, Sonnet), revisore indipendente B
(verita' contro il Python, Sonnet), review incrociata di admin-bc (revisore Sonnet). Tutti in
sola lettura, nessuno ha costruito il codice.

## Corretti (tutti con test)
| # | Gravita' | Dove | Reperto | Correzione |
|---|---|---|---|---|
| R2-1 / bc-M1 / B-A3 | ALTO (soldi) | `CashOutGlobale.tsx` | «Confermo: chiudi tutte» restava attivo anche se dopo l'armatura scattava il blocco (prezzi fermi/ignoti, cifra non calcolabile), se il piano cambiava (gamba chiusa da sola, gamba nuova) e per un tempo illimitato | conferma spenta col `blocco` (motivo visibile anche da armato); l'armatura CADE se cambia la firma del piano o il blocco; scadenza `SCADENZA_ARMATURA_MS = 10 s`; test R2-1 e M1 |
| bc-M2 | ALTO (soldi) | `CashOutGlobale.tsx::pianoChiusuraPartita` | i 4 bot tennis chiudono la PARTITA (`chiudi_bot` per event/market) ma il piano mandava UN comando PER RIGA: N chiusure identiche con soldi veri | dedup per (bot, partita, mercato) come Mike; frase di conferma con gli effetti per bot (title); test M2 |
| R2-4 / B-M6 | ALTO (verita', soldi) | `ControlRoom.tsx:1446`, `useControlRoom.ts` (aperto adesso), `SchedaPreMatch.tsx` | nel tennis il Match Odds e' a DUE esiti solo nella scheda in gioco: posizioni aperte, «aperto adesso» e pre-match contavano «nessuno vince» → partita coperta P1+P2 letta «A RISCHIO −20» e cifre diverse fra schede | `dueEsitiPartita(sport, mo_market_id, dueEsitiMike)` in tutti e tre i punti; test R2-4 (unit). RESIDUO: fuori programma (nessun feed → nessun `mo_market_id`): dichiarato |
| B-A1 | ALTO (verita') | `SchedaPartita.tsx` («conclusa»), `ControlRoom.tsx` («DA REGOLARE») | `stato === 'chiusa'` = «non in gioco e orario passato»: anche ritardi, sospensioni, rinvii | «conclusa» e «DA REGOLARE» solo con `statoMercato === 'CLOSED'` (Match Odds chiuso da Betfair); altrimenti «non in gioco · orario passato» col title |
| B-A2 | ALTO (verita') | `OrdiniContoPartita.tsx` | «aperto per il conto letto alle HH:MM:SS»: `letto_at` della RPC e' `now()` dell'interrogazione, le righe vengono dallo SPECCHIO scritto dal runner (vecchio se il runner e' fermo) | «aperto secondo lo specchio degli ordini interrogato alle …» + nota «lo specchio lo aggiorna il runner»; dettaglio del marchio. CHIESTO ad admin-bc per domani: la RPC porti anche l'istante dell'ultima scrittura dello specchio |
| R2-2 / bc-M6 / B-M5 | MEDIO (verita') | `apertoAdesso.ts`, `ObiettivoVoci.tsx` | «aperto adesso» calcolato a memo sulla firma dei dati: a feed fermo la cifra restava «adesso» senza eta'; il tooltip diceva «se chiudo TUTTO» ma conta solo i bot | `etaPrezziS` + `calcolatoAlMs` nel risultato; la pagina fa crescere l'eta' col suo orologio; marchio con eta' e avviso ambra «prezzi di N s fa» oltre 20 s; tooltip «solo gambe dei bot»; test R2-2 |
| R2-3 / A-3 | MEDIO | `useControlRoom.ts` firma dell'aperto | mancavano `pnl`, `stato`, `residuo`, `esposizioneSelezioni` che `gambeDaOperazioni` legge per tennis e scalper: una gamba regolata restava «aperta» finche' il feed non scriveva | aggiunti alla firma |
| R2-5 / A-5 / B-M7 | MEDIO | `ControlRoom.tsx::SchedaFuoriProgramma` | la stessa gamba LIVE resa due volte (`RigaOperazione` + `RigaPosizioneOrfana`), due «Chiudi» | una riga per gamba (`RigaPosizioneOrfana`, testid di sempre); test |
| B-M1 | MEDIO (verita') | `ControlRoom.tsx` banner | «Nessun bot sta usando soldi veri» anche con la modalita' di un bot NON LETTA | con modalita' non lette il banner lo dice e nomina i bot (`cr-banner-modalita-non-lette`); test |
| bc-M4 | MEDIO (verita') | `tradeStatus.ts` | `live_not_matched:<stato>` senza codice → «NON ABBINATO (tutto o niente)» anche con stato EXECUTABLE (percorso sotto-minimo non FOK di Safe): l'ordine poteva essere ancora sul book | «tutto o niente» solo con stato TERMINALE (`STATI_TERMINALI_FOK`); altrimenti ERRORE col motivo; test |
| bc-M5 | MEDIO (verita') | `ControlRoom.tsx`, `useControlRoom.ts` | «Omega oggi non ha ancora girato» anche con la riga di Omega NON LETTA | `omegaLetto` → «stato di Omega non letto: …» |
| bc-M3 | MEDIO (verita') | `useControlRoom.ts` plancia Mike | con fonte BOT (conto non letto) la cifra LIVE di Mike comprende gli ordini dell'utente mentre la pillola BOT dice il contrario | nota nel marchio: «righe di Mike: comprendono anche gli ordini fatti dall'utente sulle sue partite» (la cifra non si altera: e' vera, ora e' detta) |
| B-M2 / B-M3 | MEDIO (verita') | `fonteSoldi.ts`, `ObiettivoHero.tsx` | title base di CONTO «comprende tutti gli ordini» anche sulle voci per bot/sport (`per_fonte`); eta' del P&L del conto = ultimo CAMBIO dei regolati (il worker ripubblica solo al cambio), non «letto N min fa» | title base neutro + «eta' = ultimo cambio dei regolati»; dettaglio «solo gli ordini che il conto attribuisce a questa voce» sulle voci per bot |
| B-M9 | BASSO (verita') | `SchedaPartita.tsx` barra tennis | il title diceva «eta' delle quote» per `state.updated_ms`, che e' la ricostruzione dello stato da parte del runner (dice che il runner gira, non che lo stream sia vivo) | title corretto |
| B-M14 | MEDIO (verita') | `ObiettivoHero.tsx`, `SplitSport.tsx` | «per giorno di regolamento» diventa falso se l'utente applica la migrazione facoltativa `tennis_bot_daily_giorno_partita` (stessa firma della RPC: la UI non lo sa) | «per giorno come lo pubblica il servizio (regolamento, o partita se la migrazione del 30/09 e' applicata)» |

## Non corretti oggi (dichiarati, da fare domani prima del live se rilevanti)
- **A-6**: «Chiudi tutte» manda i comandi di riga ma non registra la partita come «chiusa dall'utente» per Safe/Omega (`cashout_event`): se Safe/Omega possono rientrare dopo la chiusura di riga e' un fatto del BACKEND da verificare (i comandi di riga sono gli stessi dei pulsanti «Chiudi» certificati).
- **A-7**: `usePrezziAlMs` indicizza il ladder per posizione: per UN render dopo un cambio della lista una selezione puo' leggere il prezzo di un'altra (pre-esistente, esposto di piu' ora).
- **B-M4**: `senza_commissione`/`sospetti_sito` del conto letti e mai mostrati: ordini regolati senza commissione leggibile non entrano nel netto del conto e la UI puo' dire «nessun ordine regolato oggi» (backend + UI).
- **B-M10**: «FEED FERMO (N s)» di Mike e il blocco del «Chiudi tutte» usano l'eta' dell'ULTIMO CAMBIO della riga scanner: un mercato quieto ma vivo si legge «fermo» (errore documentato in `lib/controlRoom.ts:320-340`; lato scanner c'e' ora `odds_seen_ms`: da usare domani).
- **B-M11**: `open_liability` di Safe/Omega e' la somma per RIGA (lorda), Mike netta: lo scarto «NON TORNANO» della testata confronta grandezze diverse (title da correggere: «per riga, lorda»).
- **B-M12**: `cr-pnl-partita` (numero grande della scheda) senza etichetta di fonte (calcolo del bot per Omega/Safe, conto per Mike).
- **B-M13**: pagine Mike/Omega/Safe: control non letto → «INATTIVO» e «+0,00 €» (fuori dal mio dominio: pagine dei bot).
- **B-M15**: stimato tennis senza `bet_id`: finestra transitoria di doppio conteggio conto+stimato fino al poll.
- **B-M16**: cinque perimetri diversi per «oggi LIVE» (tessere, plancia, composizione, obiettivo, pagina Mike) senza nota di passaggio: da uniformare con l'utente.
- **A-8** carico: `firmaAperto` e i calcoli per scheda a ogni tic (solo CPU, da misurare con l'app).
- BASSI dei tre referti (ASCII nei commenti, `<div>` dentro `<button>`, «Responsabilita'» residua in InvestAction/ReportPersonale, diciture «cash out globale» in `chiusuraUtente.ts`, Safe con sport ignoto in chiave `safe`, modalita' ignota contata LIVE in `ContaAperte`).

## Numeri
- tsc 0 sull'albero R2; test dei file toccati: 267 + 151 verdi; mutazioni mie 6/6 rosse.
- Giro largo (controlroom + trading + pages + lib) e suite intera su F4: vedi `REVIEW_FINALE_PRIMA_DELLA_CONSEGNA.md` §A.
