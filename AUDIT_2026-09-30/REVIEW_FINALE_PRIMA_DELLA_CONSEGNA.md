# REVIEW FINALE PRIMA DELLA CONSEGNA — 30/09/2026

Ordine dell'utente (19:00 circa, alla sessione UI): «prima di consegnarmi tutto il lavoro
pushato, dovrete fare entrambi una review approfondita di tutto quello che avete toccato.
Non voglio per nessun motivo regressioni o malfunzionamenti di nessun tipo. Coordinatevi».

Regole concordate fra le due sessioni (admin-bc backend+fusione, admin-07 UI):
congelamento alle 19:15 (da li' solo correzioni di reperti, ognuna ripassata dai test);
ognuno rivede il SUO per intero sul commit finale **F** (non sulle patch singole);
review incrociata dove i domini si toccano; un reperto ALTO senza il tempo di correggerlo
bene = revert del blocco, non rattoppo; «consegnato» solo con entrambe le sezioni firmate
e ALTI a zero.

Commit F (finale della serata): **`5e8ed11`** (F4). Sequenza: `f58b595` → `e5ec3c9` → `d4b4f6b` → `04b8d20` (S) → `c4fa7d9` → `2b029a9` → `2a5cbba` → `1b1fe3b` (F2) → `55df3f8` (F2b) → `7f708eb` (F3) → `0cc87a1` → `5e8ed11` (F4). Build: `npm run build` su F4 (1m20s). Push: dopo entrambe le firme.

---

## A. Sezione UI (admin-07) — firma: admin-07, 30/09 ore 22:54 (su F4 `5e8ed11`)

### A.1 Cosa e' entrato oggi dalla sessione UI (tutto in `frontend/src`)
Prima ondata, fusa da admin-bc nei commit `670f8a5`, `f58b595`, `e5ec3c9`, `d4b4f6b`, `04b8d20`:
P1 marchio della fonte dei soldi, C_P11, G_P2 (tessere a due corsie), B1 (nomi e quote), B2
(glossario), T_P3 (fascia SOLDI VERI), C_P12a/b (cash out di partita netto), G_P8/P8bis (prova
per giorno di partita, arretrati), B1bis (linee O/U e tennis), P13 (esiti veri degli ordini),
T_P4 (stop del conto), G_P7 (fonte per voce), guardia anti doppio clic, T_P5/P5b (chip bot
veritieri), R1 = R_C/R_B2/R_T/R_B1/R_G (correzioni della review di verita').
Seconda ondata `W_TUTTO_su_2a5cbba.patch` (55 file) in F2 `1b1fe3b`: W_C (chiudi tutte le gambe
della partita, in sequenza), W_T_P15 (posizioni aperte LIVE/PROVA con stato per partita), W_B1
(scheda pre-match completa, barra tennis, spread), W_G (Obiettivo P6, «aperto adesso», tessere
LIVE dal conto), W_B2 (esiti reali Omega/Safe, liability lorda/netta, parole della plancia, P&L
LIVE della plancia dal conto), W_T_P14 (ordini del conto fuori dai bot per partita).
F2b `55df3f8`: «IN VERDE» / «PAREGGIATA» (decisione dell'utente, 21:47: «fai tu»).
F4 `5e8ed11`: `R2_REVIEW_FINALE.patch` (21 file), le correzioni della review finale (A.3).

### A.2 Come e' stato verificato (da me, non sul referto dei delegati)
| Passo | Esito |
|---|---|
| Ogni blocco: diff riletto riga per riga, test dei file toccati rilanciati, 2-3 mutazioni MIE (ripristino da copia + `cmp`); un checkpoint per blocco in `CRONOSTORIA.md` (blocco UI admin-07) | 30 mutazioni mie in giornata: 24 rosse, 6 equivalenti motivate (nessuna sopravvissuta senza spiegazione) |
| Incrementali di corsia con alberi temporanei, impilati con `--3way`; 2 conflitti risolti a mano; `integra` ≡ `verifica-ui` salvo i 24 file dei commit frontend di admin-bc (diff identico file per file) | F2 `1b1fe3b`: albero frontend IDENTICO al mio indice di verifica (diff vuoto) |
| F1 master `04b8d20`: suite frontend INTERA | tsc 0; 300 file / 4541 test verdi, 10/50 saltati, 0 rossi, 938 s (sotto carico dei replay) |
| F2b `55df3f8`: suite frontend INTERA a PC libero | tsc 0; 307 file / 4640 test verdi, 10/50 saltati, 0 rossi, 590 s |
| R2 (albero F2b + patch): tsc + `components/controlroom` + `components/trading` + `pages` + `src/lib` | tsc 0; 239 file / 3959 test verdi, 1 saltato, 0 rossi |
| F4 `5e8ed11`: suite frontend INTERA | tsc 0; 307 file / 4649 test verdi, 10/50 saltati, 0 rossi, 465 s (PC libero, 22:52); albero frontend = mio albero R2 + `0cc87a1` di admin-bc (riletto) |
| Revisori indipendenti (Sonnet, sola lettura, contesto pulito, non chi ha costruito): A regressioni, B verita' contro il Python; piu' la review incrociata di admin-bc | A: 0 ALTI, 7 MEDI, 6 BASSI. B: 3 ALTI, 16 MEDI, 8 BASSI. bc: 0 ALTI, 6 MEDI. Esito per reperto in `AUDIT_2026-09-30/ui_blocchi/R2_REVIEW_FINALE_admin07.md` |

### A.3 Reperti sul mio dominio
Corretti in giornata (prima della review finale): «Liability aperta 39,15» lorda e «in corso
(stimato)» tolti dall'Obiettivo (R_G); corsia PROVA alimentata con dati LIVE (G_P2); doppio clic
= chiusura live senza conferma (C_GUARDIA + M2 di admin-bc); «SPENTO · ultimo modo live» su bot
live fermo (T_P5b); «ultimo book N s fa» falso (`seen_ms` fuori firma → «ultimo CAMBIO»);
`toFixed` nel title delle posizioni aperte (design guard rosso, W_T_P15).
Corretti nella review finale (R2, tutti con test, 6 mutazioni rosse):
| # | Gravita' | Reperto | Correzione |
|---|---|---|---|
| R2-1 / bc-M1 / B-A3 | ALTO (soldi) | «Confermo: chiudi tutte» restava attivo con prezzi fermi/ignoti sopraggiunti, con il piano cambiato, per un tempo illimitato | conferma spenta col blocco; l'armatura cade a cambio piano/blocco; scadenza 10 s |
| bc-M2 | ALTO (soldi) | bot tennis: un comando di chiusura PER RIGA mentre il bot chiude la PARTITA → N chiusure identiche | dedup per (bot, partita, mercato) |
| R2-4 / B-M6 | ALTO (verita') | tennis Match Odds a due esiti solo nella scheda in gioco: partita coperta P1+P2 letta «A RISCHIO −20» in posizioni aperte, «aperto adesso», pre-match | `dueEsitiPartita` nei tre punti (residuo dichiarato: fuori programma senza feed) |
| B-A1 | ALTO (verita') | «conclusa» / «DA REGOLARE» anche per ritardi, sospensioni, rinvii | solo con Match Odds `CLOSED`; altrimenti «non in gioco · orario passato» |
| B-A2 | ALTO (verita') | «aperto per il conto letto alle»: `letto_at` = `now()` dell'interrogazione, righe dallo specchio del runner | etichetta «secondo lo specchio degli ordini interrogato alle …» + nota; chiesta ad admin-bc l'ultima scrittura dello specchio per domani |
| R2-2, R2-3, R2-5, B-M1, bc-M4, bc-M5, bc-M3, B-M2/M3, B-M9, B-M14 | MEDI | eta' e perimetro dell'«aperto adesso»; firma incompleta; fuori programma con righe doppie; banner PAPER verde con modalita' non lette; «tutto o niente» su stato EXECUTABLE; Omega non letto ≠ non ha girato; Mike righe con ordini dell'utente; title CONTO ed eta' = ultimo cambio; title barra tennis; testo tennis bot neutro sulla migrazione | vedi referto R2 |

Non corretti oggi, dichiarati (nessun ALTO frontend): A-6 (backend: dopo un «Chiudi» di riga
Safe/Omega possono rientrare? da verificare da admin-bc), A-7 (`usePrezziAlMs` per posizione, un
render), B-M4 (`senza_commissione` mai mostrato), B-M10 («FEED FERMO» su ultimo cambio, da
passare a `odds_seen_ms`), B-M11 (liability Safe/Omega per riga lorda vs Mike netta: title),
B-M12 (`cr-pnl-partita` senza fonte), B-M13 (pagine bot: control non letto = «INATTIVO»),
B-M15/M16 (perimetri diversi di «oggi LIVE», da uniformare con l'utente), bassi.

### A.4 Test esistenti modificati di proposito, testid tolti, file condivisi
Test esistenti modificati (motivo nei referti dei blocchi e in R2): `CashOutPartita`,
`DettaglioRigaView`, `MarchioSoldi`, `ObiettivoHero`, `PropostaUscitaMike`, `ResiduiB17.schede`,
`SchedaPartita`, `SchedaPreMatch`, `SchedaPropostaOpportunita`, `dettaglioRiga`,
`fixPagine2609.giornata`, `useTennisVivo`, `useMikeEventoAlMs`, `EventPnlTable`, `designGuard`,
`certezzaChiusura`, `chiusuraAlMs`, `chiusuraUtente`, `controlRoom`, `interruttoriUscite`,
`scalperControlRoom`, `tradeStatus`, `ControlRoom.test.tsx`, `P13EsitiChiusura`, `PannelloBot`,
`useControlRoom`, `useControlRoom.provaGiornata`, `CashOutGlobale.montaggio`,
`B2GlossarioAuditCR`, `righeBot`, `composizioneConto`, `cashOutPartita`, `soldiVeri`,
`FasciaSoldiVeri`, `useChiusuraAlMs.parita`, `PosizioniChiuse.raggruppamento`, `OrdiniContoPartita`,
`W_B2EsitiOmegaSafe`, `statoPartitaAperta`, `apertoAdesso`. Nessun test cancellato.
Test nuovi: 22 (prima ondata) + 8 (W_*) + 1 (IN VERDE) + 8 (R2).
testid tolti: `cr-riga-paper` (riga doppia della scheda in gioco, R_B1; test adeguato).
`cr-calcio-vivo-quote`, `cr-tennis-vivo-quote`, `cr-latenza` restano nel DOM (prop `testId`).
File condivisi riletti: `components/trading/DayBar.tsx` (solo prop opzionali; pagine Mike/Omega/
Safe verdi), `ParamsSheetBase.tsx` (M1 di admin-bc), `lib/tradeStatus.ts` (`statusMetaOf`/
`STATUS_META` invariati), `lib/liveOrders.ts` (solo aggiunte, 39 righe, fuori dal dominio:
segnalato), `SchedaMike.tsx` (8 righe; admin-bc non aveva altro da fondere).

### A.5 Non verificato
- L'app a schermo (nessun build/riavvio fino alla chiusura della review): la descrizione
  schermo per schermo in cronostoria e' dedotta dai test di pagina.
- La RPC `get_live_orders_account_open` chiamata davvero dal frontend (finti nella forma del
  contratto; admin-bc l'ha provata come SELECT sul DB vero).
- Stato reale delle migrazioni sul DB (la UI e' scritta per reggere entrambi i casi dove conta).

---

## B. Sezione backend + fusione (admin-bc) — firma: admin-bc (Fable 5.1), 30/09 ore 22:58 (su F4 `5e8ed11`). ALTI a zero: M2, R-seen, Safe-netto corretti e verificati; tutto il resto dichiarato.

### B.1 Commit di oggi rivisti
| Commit | Cosa | Rivisto da | Comandi e numeri |
|---|---|---|---|
| `b2b6b69` … `670f8a5` | vedi CRONOSTORIA 30/09 | admin-bc (diff, suite, replay) | replay finali `AUDIT_2026-09-30/replay/*_FINALE.txt` |
| `f58b595` | T_P3+C_P12a+G_P8 (fusione) | admin-bc | tsc 0; vitest 101 file / 1474 test |
| `e5ec3c9` | B1bis+P13+T_P4+G_P7+G_P8bis+C_P12b+guardia doppio clic + M1 + M2 + M4 | admin-bc (fusione, tsc, vitest) | tsc 0; controlroom+pages 87 file / 1263; riscontro+trading 234 |
| `d4b4f6b` | T_P5 | admin-bc | tsc 0; 28 file / 487 |
| `04b8d20` (S) | corsia scanner (b)(c)(d-1)(e) + fermi_da_ms/odds_seen_ms + Mike ou_blocks + R1 (R_C,R_B2,R_T,R_B1,R_G) + testi Mike veritieri | admin-bc + revisore indipendente Sonnet (0 ALTI, 6 reperti corretti) | 28+2+3 test nuovi, 23 mutazioni rosse; suite 6586+4627+3459; replay Mike 25/25 identici, Omega 13, Safe 14; tsc 0; vitest 1796+256 |
| `c4fa7d9` | badge linee ferme con eta' vera | admin-bc | tsc 0; 19 test |
| `2a5cbba` | backend per la UI (RPC ordini conto, 23514, pnl_letto_at, stop Omega, tennis daily) | admin-bc (diff riletto, 3 mutazioni mie) | suite stream+omega 4652; delegato: 15/15 mutazioni rosse |
| `1b1fe3b` (F2) | seconda ondata W_* di admin-07 (55 file, patch cumulativa) | admin-bc (fusione, tsc, vitest) + admin-07 (220 file / 3712, 8 mutazioni) | tsc 0; vitest 252 file / 4087 |
| `55df3f8` (F2b) | IN VERDE / PAREGGIATA (decisione dell'utente) | admin-bc | tsc 0; 143 test |
| `7f708eb` (F3) | Safe: P&L regolato al NETTO della commissione (profit di Betfair e' lordo, prova sul DB) | admin-bc (diff, 2 mutazioni mie) + delegato Opus (10 mutazioni, replay Safe x3 + Omega identici) | suite safe+omega 3492 |
| `0cc87a1` | conferma del «Chiudi» live si disarma e scade (review incrociata M1) | admin-bc | tsc 0; 30 test; 2 mutazioni rosse |
| `5e8ed11` (F4) | R2 di admin-07: correzioni della review incrociata (C-M1..M5 nel suo dominio) + reperti dei suoi revisori | admin-bc (tsc, vitest) + admin-07 (6 mutazioni) | tsc 0; vitest 239 file / 3961 |

### B.2 Reperti
| # | Gravita' | Dove | Reperto | Esito |
|---|---|---|---|---|
| M2 (da admin-07) | ALTO | `BottoneChiudiRiga.tsx` | Conferma nello stesso punto del Chiudi: doppio clic = soldi veri senza conferma voluta | CORRETTO (400 ms, `ATTESA_CONFERMA_USCITE_MS`), 3 test adeguati + 1 nuovo |
| M1 (da admin-07) | MEDIO | `ParamsSheetBase.tsx` | dopo il salvataggio la bozza tornava ai valori vecchi finche' la rilettura non arrivava | CORRETTO (bozza = valori salvati), test nuovo |
| M3 | MEDIO | storico Mike | etichetta «per regolamento» vera solo con la migrazione `mike_storico_giorno_regolamento_2026-09-29.sql` applicata | l'utente ha dichiarato alle 12:xx «migrazioni applicate»; da confermare a voce nel rapporto |
| M4 | MEDIO | `Mike.tsx:771` | testo fisso «P&L del conto Betfair per le partite regolate dal 30/09/2026» | CORRETTO in `e5ec3c9` (regola senza data; ogni riga porta la fonte) |
| B4 | BASSO | badge flusso | «UNDER/OVER 3,5 FERMA» anche su partite che Mike non opera | veritiero (la linea e' ferma davvero); eta' ora VERA (`c4fa7d9`) |
| R-seen | ALTO (review UI) | scanner/Mike | `seen_ms` fuori firma: «ultimo book N s fa» era l'eta' della riga; Mike scartava linee vive dopo 90 s | CORRETTO in `04b8d20` (`fermi_da_ms`, `ou_blocks`) e `c4fa7d9` |
| R-sc1..6 | MEDIO/BASSO (revisore scanner) | `service.py` | sveglia anche tennis; riavvio = fischio; ordine sveglia/assegnazioni; stop lento; iterazione non copiata; forma timeline non registrata | 5 CORRETTI in `04b8d20`; il 6° (forma reale della timeline) DICHIARATO non verificabile senza il vivo, con ripiego sicuro |
| 23514 | MEDIO | `reconcile_worker.py` | il runner riscriveva gli ordini dei bot nello specchio (CHECK li rifiuta a ogni giro) | CORRETTO in `2a5cbba` |
| Safe-netto | ALTO (P&L) | `safe_strategy/execution.py:2152` | profit di Betfair preso come gia' netto di commissione (prova: #332 back 3,00 @ 1,16 → profit 0,48 = lordo) | CORRETTO in `7f708eb`; Omega gia' netta (2 test) |
| M5 | MEDIO | `mikeEsitoChiusura.ts` | «nessuna esposizione» dalla credenza del bot, non dagli ordini riletti | PARZIALE: P13 mostra l'esito VERO delle gambe di chiusura («NON ABBINATO (verificato su Betfair)», «RIFIUTATO»); la dichiarazione «nessuna esposizione» resta della gamba del bot: DICHIARATO |

### B.3 Non verificato
- **L'app a schermo: NESSUNO dei due l'ha vista** (nessun riavvio con posizioni aperte; il build e' fatto). Domattina PRIMA cosa: aprirla e passare la lista schermo per schermo lasciata da admin-07 in cronostoria.
- Le due funzioni SQL nuove non compilate dal server (vietato scrivere sul DB): se una migrazione da' errore, si corregge dal testo.
- Le parti nuove dello scanner dal vivo (sveglia, timeline al fischio): il banco non le esercita; verifica con i contatori `ips` e il log «primo punteggio … fonte».
- Il blocco `score` del record `eventTimelines` al KickOff (vedi `STATO_CORSIA_SCANNER_VELOCITA.md`).

---

## C. Review incrociata

- admin-07 sui commit frontend di admin-bc: `REVIEW_INCROCIATA_COMMIT_FRONTEND_admin07.md` (0 ALTI dichiarati; M2 alzato ad ALTO e corretto in `e5ec3c9`; M1, M4 corretti; M3 nel rapporto).
- admin-bc sull'integrazione finale (revisore indipendente Sonnet, sola lettura, F2 + IN VERDE; tsc 0; controlroom+lib+pages 222 file / 3719 verdi): **NESSUN ALTO**. Runtime (TDZ, hook, sottoscrizioni, loop, `inVolo`) a posto; nessuna somma LIVE+PAPER; payload del «Chiudi» identico a prima; conferma inerte 400 ms in BottoneChiudiRiga, CashOutPartita, CashOutGlobale, InterruttoreUscite.

| # | Gravita' | Dove | Reperto | Esito |
|---|---|---|---|---|
| C-M1 | MEDIO | `CashOutGlobale.tsx:174-215`, `BottoneChiudiRiga.tsx` | conferma armata che non scade ne' si disarma (piano vuoto → ricompare gia' oltre i 400 ms → un clic manda ordini LIVE; prezzi fermi → «Confermo» ancora attivo) | `BottoneChiudiRiga` CORRETTO in `0cc87a1`; `CashOutGlobale` → admin-07 |
| C-M2 | MEDIO | `CashOutGlobale.tsx:145-157` | tennis: comando per RIGA invece che per PARTITA (N `chiudi_bot` identici); frase di conferma senza gli effetti (tennis non rientra, scalper sessione fermata, Mike ciclo intero) | → admin-07 |
| C-M3 | MEDIO | `useControlRoom.ts:2705` vs `:2179` | righe «utente» di Mike escluse dalla composizione ma incluse in `chiuse` (fonte BOT): plancia e composizione divergono | → admin-07 |
| C-M4 | MEDIO | `lib/tradeStatus.ts:301` | ogni `live_not_matched:<stato>` → «NON ABBINATO (tutto o niente)» anche per Omega/Safe (ordine LAPSE potrebbe restare sul book) | → admin-07 |
| C-M5 | MEDIO | `ControlRoom.tsx:587`, `useControlRoom.ts:4017` | «Omega oggi non ha ancora girato» anche a lettura fallita (omega null) | → admin-07 |
| C-M6 | MEDIO | `ObiettivoVoci.tsx:19-30` | «aperto adesso (se chiudo tutto)» senza eta' dei prezzi ne' controllo prezzi fermi; conta solo i bot | → admin-07 |
| A-6 (da admin-07) | da verificare → VERIFICATO | Safe/Omega backend | dopo un «Chiudi» di riga, il bot rientra sulla stessa partita? | NO. Safe: le righe chiuse (stato diverso da `error`) restano in `traded_signal_keys` per (partita, segnale) (`bot_db.py:266-277`): lo stesso segnale non si ripresenta; un segnale DIVERSO della stessa partita (ESATTO/PUNTA/BASE) resta ammesso per progetto. Omega: la partita chiusa dall'utente e' uno STATO sull'evento (`omega_service.py:1855-1868`, R8 16/09): nessuna apertura finche' non si preme «Riprendi». Mike: `no_reentry` dopo `chiuso_dall_utente` (R3). |
| C-B1..5 | BASSO | vari | «conto non letto: P&L dalle righe dei bot» senza righe; banner `=== 'live'` vs `!== 'paper'`; PAREGGIATA/IN VERDE al lordo e solo bot (dirlo sulla parola); `firmaAperto` a ogni secondo (CPU); `ParamsSheetBase` bozza senza riconferma | → admin-07 (primi 4); l'ultimo DICHIARATO (e' la correzione M1, migliore del vecchio comportamento) |
