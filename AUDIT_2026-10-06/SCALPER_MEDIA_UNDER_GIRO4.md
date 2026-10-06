# SCALPER CALCIO — «MEDIA UNDER», quarto giro (06/10/2026)

Delegato (sessione cloud). Ramo `feature/scalper-media-under-giro4`, nato da
`feature/scalper-media-under-giro3` (PR #5, non ancora fusa): questo ramo CONTIENE il
giro 3 e lo sostituisce. Decisioni dell'utente del 06/10: **P1 = A** (lo stop lascia la
banca PERSIST), **P8 = A** (nessun cambiamento), **P13** («in caso di crash, caduta rete
ecc, il BOT DEVE ESSERE IN GRADO DI RIPRENDERE ESATTAMENTE DAL PUNTO IN CUI e' SENZA
ERRORI E SENZA OPERAZIONI DOPPIE [...] LA PERSISTENZA e' FONDAMENTALE»; precisato: «LA
PERSISTENZA MI INTERESSA PER IL LIVE! PER TUTTI I BOT»), e il nome di strategia per
partita «per tutti». Nessun ordine vero, nessuna chiamata a Betfair, nessun accesso al
DB, nessun `.env`, app non avviata. Replay solo da
`python -m Betfair.stream.backtest.certifica`, uno alla volta (`--worker 1`), sulle due
registrazioni VERE di `registrazioni_banco/`.

## 0. IN EVIDENZA — cio' che NON ho potuto verificare

1. **L'adozione degli ordini da parte di flumine sull'exchange VERO non e' esercitata.**
   La ripresa si fonda su un comportamento di flumine 2.13.11 letto nel sorgente
   (`process_current_orders` -> `create_order_from_current`, abbinamento per
   `name_hash` = sha1 del nome della strategia, primi 13 caratteri): il banco lo
   SIMULA (`_adotta_ordini_vivi`), non lo prova. Primo avvio in soldi veri dopo un
   crash = la prima prova vera. Se flumine non riadotta entro 60 s la modalita' si
   ferma in BLOCCATA e lo dice (nessun ordine nuovo): il guasto possibile e' «ferma»,
   non «doppia».
2. **Gli ordini GIA' CHIUSI letti dal conto** (cicli precedenti al crash, punte
   abbinate per intero) entrano nella ricostruzione da `listCurrentOrders`
   (`OrdineDelConto`): provati dai test con le classi vere di betfairlightweight
   (`CurrentOrders`), non su una risposta vera dell'exchange.
3. **Il PAPER non riprende**: dopo un crash in paper la modalita' resta BLOCCATA
   (come prima). Decisione dell'utente: la persistenza serve in live. In paper non c'e'
   un conto da cui rileggere.
4. **Gli altri slot dello Scalper (maker, sniper, theta) e i bot tennis NON
   riprendono dal conto.** L'utente ha detto «per tutti i bot»: Mike, Omega e Safe
   riprendono gia' dal DB; per lo Scalper ho fatto la parte che serve a tutti (il nome
   di strategia per partita, §1) e la ripresa della sola media. Maker/sniper/theta e
   tennis sono un lavoro a parte (tennis vietato in questa serie): serve una spec del
   coordinatore.
5. **Ambiente**: Python 3.11 (l'utente 3.13); frontend non toccato e non rilanciato. I
   5 test sui tempi di Safe sono rossi qui come su `master` (§4).
6. **Resto del giro 2**: il worktree `scratchpad/wt_master` non e' stato rimosso
   (rimozione negata dai permessi; e' fuori dal repo, nella cartella temporanea della
   sessione).
7. **La modalita' NON e' certificata** (mancano paper e soldi veri dal vivo).

## 1. Il nome di strategia per partita (tutte le strategie della sessione)

`scalper_session.py`: `PREFISSI_STRATEGIA = {maker: scm, sniper: scn, theta: sct,
media: mu}` e `nome_strategia(ruolo, event_id)` = prefisso + event_id, tagliato a 15
caratteri (il `customerStrategyRef` di Betfair). Passato a Scalper, Sniper, Theta e
MediaUnder.

Perche': prima tutte le sessioni dello Scalper si chiamavano come la CLASSE. Una
sessione in soldi veri, all'avvio, poteva (a) farsi riadottare da flumine gli ordini di
un'ALTRA partita con la stessa classe, (b) leggerli dal conto come propri e (c)
annullarli allo stop. Con il nome per partita ogni sessione vede solo i suoi.

## 2. P1 — lo stop lascia appoggiata la banca PERSIST

- `media_under_bot.py`: allo stop (`force_flat`) la punta in corso si RITIRA
  (`_ritira_la_punta_allo_stop`), la banca si porta sull'intera posizione abbinata,
  `pronta_allo_stop()` dice quando e' cosi'; `banca_da_lasciare(o)` riconosce la banca
  da lasciare (LAY, viva, PERSIST, della posizione corrente).
- `scalper_session.py`: l'argomento `da_lasciare` arriva a tutte le strade di uscita:
  `annulla_ordini_vivi_all_arresto` (la banca non si annulla, `esito["lasciati"]`),
  `chiudi_all_arresto` (problema DICHIARATO: «media under: banca PERSIST di chiusura
  lasciata appoggiata (decisione dell'utente P1...)»), `_handle_flumine_crash` (lo
  sweep del crash toglie la banca dall'elenco; se resta SOLO la banca non c'e' sweep, e
  mai il ripiego su tutto il mercato), `_uscita_su_eccezione`. `_all_flat` aspetta
  `pronta_allo_stop()`.
- Controllo S3 del banco: «a sessione chiusa nessun ordine vivo, OPPURE il servizio lo
  ha DICHIARATO»: la banca lasciata e' dichiarata, quindi S3 passa per la via giusta.

## 3. P13 — la ripresa in soldi veri dal conto

- All'armo in soldi veri (`not session_paper`) `prepara_ripresa_media` legge dal conto
  gli ordini della strategia (`listCurrentOrders` con `customer_strategy_refs` = il
  nome della media per QUELLA partita, tutte le pagine con `from_record`). Se il conto
  non si legge, si riprova a ogni battito (`attende_il_conto`).
- Ordini trovati -> stato nuovo **RIPRESA**: NESSUN ordine finche' flumine non ha
  riadottato tutti gli ordini EXECUTABLE del conto (i loro bet_id nel blotter della
  strategia). Poi `_ricostruisci`: cicli chiusi e P&L, rientri fatti, ultimo ingresso,
  obiettivo (fisso o automatico), banca e punta vive, stato (INGRESSO, RIENTRO,
  IN_POSIZIONE, MASSIMO con l'avviso gia' dato, FERMO). Da li' la modalita' continua
  come se il crash non ci fosse stato. Adozione non completa in 60 s
  (`ATTESA_RIPRESA_MS`) -> BLOCCATA, detto.
- Conto vuoto -> la modalita' parte da zero, come prima.
- Esposizione: `_esposizioni_nette` della sessione conta anche gli ordini letti dal
  conto non presenti nel blotter. **Difetto vero trovato dal replay** (vedi §4.2): senza,
  dopo una ripresa la sessione dichiarava un falso «non flat».

## 4. I replay (referti in `AUDIT_2026-10-06/replay/giro4/`)

Comando: `bash AUDIT_2026-10-06/strumenti/replay_giro4.sh` (09:51-10:55, riepilogo in
`riepilogo.txt`). Confronto: `python AUDIT_2026-10-06/strumenti/confronta_giro4.py`
contro `replay/giro3/`.

### 4.1 Lo Scalper con la modalita' spenta

I 15 scenari sulla 35797769 (A1, A2, B1, B2, B3) e `base,paper` sulla 35760084 (C):
righe OK/KO/NE **IDENTICHE** al giro 3. «ESITO scalper: identico».

### 4.2 La modalita'

- `media_35797769`, `varianti_35797769`, `media_35760084`, `liquidita_35797769`,
  `liquidita_35760084`: **IDENTICI** al giro 3 (righe, cicli, NETTO).
- `guasti_35797769`: diversi SOLO i tre scenari dove agiscono P13 e P1, come atteso:

| Scenario | Giro 3 | Giro 4 |
|---|---|---|
| `media-under-riavvio` (processo ucciso a posizione aperta, riarmo dopo 120 s) | dopo il crash la modalita' BLOCCATA: nessun rientro; banca vecchia 10,19 @2,14 abbinata al 8'07"; +0,17 | **riprende dal conto**: rientro @2,22 (10,00), banca 20,18 @2,18 abbinata in gioco al 9'53"; +0,18 lordo, **+0,17 netto**; riga del ciclo **identica carattere per carattere** alla corsa senza crash (`media_35797769`, `media-under`); M1-M11 tutti sollecitati, OK |
| `media-under-kill-switch` | banca annullata allo stop, «NON piu' a mercato» | banca **VIVA a mercato** (resto 10,19), dichiarata; S3 OK per dichiarazione |
| `media-under-bot-fermo` | come sopra | come sopra |

La prima esecuzione di `media-under-riavvio` sul codice del giro 4 era uscita **KO**
(M11, M6, S3): i controlli e l'esposizione della sessione vedevano solo gli ordini della
strategia NUOVA. Era un difetto di produzione (falso «non flat» dopo una ripresa),
corretto con `ordini_dal_conto` in `_esposizioni_nette`, nelle righe del banco e nei
controlli M su tutte le sessioni della modalita'.

Tempi: tutti gli scenari sotto i 5 minuti (il piu' lento `sniper-paper`, 267 s; della
modalita' il piu' lento `media-under-tick-1`, 185 s; `media-under-riavvio` 145 s).

## 5. Test e falsificazione

- Nuovo `Betfair/stream/tests/test_scalper_media_under_giro4_2026_10_06.py` (24 test, 45 casi con l'esecuzione differita di 1 e di 4 book):
  A nomi per partita; B P1 allo stop e nel crash (con le falsificazioni); C P13 (stessa
  mossa successiva della corsa senza crash, nessun ordine prima dell'adozione e poi
  BLOCCATA, ordini del conto, cicli chiusi, MASSIMO, conto vuoto, conto illeggibile e
  nuovo tentativo, pagine, stop durante RIPRESA); D banco (adozione al riavvio, controlli
  su tutte le sessioni); il nuovo tentativo al battito (sorgente); E i test delle
  mutazioni sopravvissute alla prima falsificazione (J4, J5, J8, J18).
- Adattato: `test_scalper_arresto_ordinato_2026_10_02.py` (il testo atteso della chiamata
  `_uscita_su_eccezione(...)` ora contiene `da_lasciare=da_lasciare`).
- Tolto prima del commit: un test «tutti gli ordini dallo stream» che verificava
  l'adozione in un flumine PAPER: e' un artefatto del simulatore (in paper flumine non
  adotta nulla), non verificabile sul banco (§0.1).
- Falsificazione `python AUDIT_2026-10-06/strumenti/mutazioni_media_under_giro4.py`:
  **22 mutazioni, 21 rosse, 1 equivalente** (esito in
  `mutazioni_media_under_giro4_esito.json`):

| # | mutazione | test rossi |
|---|---|---|
| J1 | il nome della strategia non dipende dalla partita | 1 |
| J2 | la media under torna al nome della classe | 1 |
| J3 | P1 spento: la banca non e' mai da lasciare | 6 |
| J4 | allo stop la punta in corso resta sul book | 1 |
| J5 | pronta allo stop anche con la banca che non copre la posizione | 1 |
| J6 | l'annullo all'arresto toglie anche la banca da lasciare | 2 |
| J7 | lo sweep del crash annulla anche la banca da lasciare | 4 |
| J8 | solo la banca nel blotter: lo sweep ripiega sul market-wide | 2 |
| J9 | in RIPRESA la modalita' opera (nessun freno: ordini doppi) | 16 |
| J10 | la ripresa non aspetta che flumine riadotti gli ordini vivi | 4 |
| J11 | ricostruzione: un rientro in piu' | 4 |
| J12 | ricostruzione: ultimo ingresso = il primo | 2 |
| J13 | ricostruzione: obiettivo perso | 2 |
| J14 | ricostruzione: cicli chiusi dimenticati | 2 |
| J15 | ricostruzione al massimo: l'avviso del massimo si ripete | **0 (equivalente, sotto)** |
| J16 | ordini sul conto ma la modalita' parte come nuova | 18 |
| J17 | ripresa senza adozione: mai bloccata (attesa infinita, nessun avviso) | 1 |
| J18 | l'esposizione della sessione non conta gli ordini letti dal conto | 2 |
| J19 | lettura del conto senza le pagine successive | 1 |
| J20 | in soldi veri il conto non si legge all'avvio | 1 |
| J21 | i controlli M vedono solo la sessione corrente (doppi dopo un riavvio invisibili) | 2 |
| J22 | il banco non simula l'adozione di flumine | 2 |

  Alla PRIMA esecuzione ne erano sopravvissute cinque (J4, J5, J8, J15, J18): i test
  non le vedevano. Ho scritto un test per ciascuna (sezione E del file del giro 4) e
  le ho rilanciate:
  - J4: il ritiro della punta allo stop si vede solo dal MOTIVO dell'annullo (senza
    il ritiro la punta muore comunque per scadenza dopo 30 s);
  - J5: il caso del resto della punta abbinato mentre il suo annullo e' in viaggio
    (esecuzione differita di 4 book): la banca da 14,05 non copre piu' i 20 puntati
    e la sessione non deve dirsi pronta;
  - J8: dopo una ripresa nel blotter c'e' SOLO la banca: nessuno sweep, mai il
    ripiego su tutto il mercato;
  - J18: l'esposizione della sessione dopo la ripresa e' quella del processo morto.
  - **J15 e' EQUIVALENTE** (nessun test puo' vederla): l'avviso del massimo parte solo
    quando una punta si abbina (`_punta_morta`), e dopo una ricostruzione in MASSIMO
    non ci sono punte vive ne' se ne piazzano; al ciclo nuovo la chiave si toglie. La
    riga resta come difesa (se un giorno l'avviso partisse anche altrove).

- Suite `python -m pytest Betfair/ -q -p no:cacheprovider`: **10183 verdi, 5 rossi**, 54
  saltati, 6 xfailed (444 s). Verdi = 10138 del giro 3 + i 45 casi nuovi. I 5 rossi sono
  i test sui tempi di Safe (`Betfair/safe_strategy/tests/test_velocita_feed_2026_09_30.py`,
  dominio non toccato), gli stessi dei giri 2 e 3, rossi identici su `master` in questo
  ambiente. Una prima esecuzione con `-p no:logging` (mia svista) dava 49 errori: tolgono
  la fixture `caplog`; con il comando standard spariscono.

## 6. File toccati

| File | Cosa |
|---|---|
| `Betfair/stream/scalper/scalper_session.py` | nome per partita; `da_lasciare` su arresto, chiusura, crash, eccezione; `leggi_ordini_media_dal_conto`, `prepara_ripresa_media` (armo e battito); esposizione con gli ordini del conto |
| `Betfair/stream/scalper/media_under_bot.py` | stato RIPRESA, `OrdineDelConto`, `prepara_ripresa`, `_forse_riprendi`, `_ricostruisci`; P1 (`banca_da_lasciare`, `pronta_allo_stop`, `_ritira_la_punta_allo_stop`) |
| `Betfair/stream/scalper/tools/replay_registrazioni.py` | `list_current_orders` per strategia con `CurrentOrders` vero; adozione simulata al riavvio; controlli M su tutte le sessioni e sugli ordini del conto |
| `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md` | §15: P1 e P13 |
| `Betfair/stream/tests/banco_media_under.py` | `nome` della strategia, `ponte` nel book |
| `Betfair/stream/tests/test_scalper_media_under_giro4_2026_10_06.py` | NUOVO |
| `Betfair/stream/tests/test_scalper_arresto_ordinato_2026_10_02.py` | testo della chiamata (§5) |
| `AUDIT_2026-10-06/strumenti/` | `replay_giro4.sh`, `confronta_giro4.py`, `mutazioni_media_under_giro4.py` (+ esito) |
| `AUDIT_2026-10-06/replay/giro4/` | i referti |

Nessun file vietato toccato; nessuna migrazione; nessuna regola di strategia cambiata
(soglie, stake, tetti, gambe invariati): P1 e P13 sono le decisioni dell'utente.
