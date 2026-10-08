### esiti
- [identico] DOPO: `OK 35797769 [base] tick=117442 decisioni= 6451 azioni= 2 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [cap-stretto] tick=121046 decisioni= 6459 azioni= 1 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [bot-fermo] tick=120899 decisioni= 6456 azioni= 3 stati=stopped/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [esiti-ignoti] tick=116568 decisioni= 6451 azioni= 6 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [feed-stantio] tick=121046 decisioni= 6459 azioni= 1 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [riavvio] tick=120899 decisioni= 6456 azioni= 3 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [paper] tick=121046 decisioni= 6459 azioni= 1 stati=running/paper [COMPLETE]`
- [identico] DOPO: `OK 35797769 [ordini-manuali] tick=120899 decisioni= 6456 azioni= 3 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [due-lay] tick=120846 decisioni= 6453 azioni= 5 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [manuale-e-bot] tick=117375 decisioni= 6450 azioni= 4 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [cashout-globale] tick=117792 decisioni= 6452 azioni= 3 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [chiusura-fuori-app] tick=117781 decisioni= 6452 azioni= 2 stati=running/live [COMPLETE]`
- [DIVERSO] DOPO: `OK 35797769 [chiusura-fuori-app-ridotta] tick=117781 decisioni= 6452 azioni= 2 stati=running/live [COMPLETE]`
  PRIMA: `OK 35797769 [chiusura-fuori-app-ridotta] tick=117376 decisioni= 6449 azioni= 2 stati=running/live [COMPLETE]`
- [NUOVO] DOPO: `OK 35797769 [chiusura-fuori-app-canale] tick=117781 decisioni= 6452 azioni= 2 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [rifiuti-betfair] tick=117422 decisioni= 6452 azioni= 2 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [timeout-dopo-accettazione] tick=117434 decisioni= 6451 azioni= 2 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [chiusura-abbinata-in-parte] tick=117295 decisioni= 6447 azioni= 5 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [selezione-aggiuntiva] tick=117442 decisioni= 6451 azioni= 2 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [proposta-approvata] tick=117197 decisioni= 6445 azioni= 7 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [proposta-scaduta] tick=117442 decisioni= 6451 azioni= 3 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [proposta-anomalia-effimera] tick=117280 decisioni= 6447 azioni= 5 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [combos-automatiche] tick=117284 decisioni= 6446 azioni= 5 stati=running/live [COMPLETE]`
- [identico] DOPO: `OK 35797769 [combos-gamba-automatica] tick=117284 decisioni= 6446 azioni= 5 stati=running/live [COMPLETE]`

### violazioni (viol>0, KO, FALLITO)

### righe diverse negli scenari ESISTENTI
#### manuale-e-bot
    -      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive']
    +      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive', 'save_event_model']
    +      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: get_event: tabella `events` (anagrafica partite): non e' nello stream di mercato registrato
#### chiusura-fuori-app
    +      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: proprietari_bot_conto: tabelle degli altri bot e coda del runner (proprietari degli ordini altrui sul conto): non sono nel replay, un ordine non del bot si decide dai riferimenti (nessun altro bot)
#### chiusura-fuori-app-ridotta
    -      nota: giri di run_once: 6449 | ordini reali su flumine: 1 | righe safe_strategy_trades: 1 | place osservati: 1 | uscite valutate: 908
    -      nota: [BASE] valutata 3847 volte | stati {'no': 3774, 'nd': 73} | segnali 0 | scartata per: dogLay:no x3516, score:no x2786, minute:no x2164, secondHalf:no x1898, minute:nd x461, secondHalf:nd x461
    -      nota: [ESATTO] valutata 7694 volte | stati {'no': 6587, 'nd': 771, 'signal': 336} | segnali 336 | scartata per: entry:no x6211, secondHalf:no x3796, minute:no x3002, entry:nd x1143, minute:nd x922, secondHalf:nd x922
    -      nota: [PUNTA] valutata 3847 volte | stati {'no': 3816, 'nd': 31} | segnali 0 | scartata per: score:no x3386, entry:nd x3247, leadFav:no x2786, minute:no x2504, minute:nd x461, score:nd x461
    -      nota: attivita' del servizio: posizione_di_conto x64, diagnosi x26, exit_hold x23, exit_wait x6, skip x2, place x1, replay_chiusura_fuori_app x1, flusso_interrotto x1, settle x1, settle_position x1
    +      nota: giri di run_once: 6452 | ordini reali su flumine: 1 | righe safe_strategy_trades: 1 | place osservati: 1 | uscite valutate: 0
    +      nota: [BASE] valutata 3850 volte | stati {'no': 3777, 'nd': 73} | segnali 0 | scartata per: dogLay:no x3515, score:no x2787, minute:no x2164, secondHalf:no x1898, minute:nd x461, secondHalf:nd x461
    +      nota: [ESATTO] valutata 7700 volte | stati {'no': 6592, 'nd': 772, 'signal': 336} | segnali 336 | scartata per: entry:no x6211, secondHalf:no x3796, minute:no x3002, entry:nd x1149, minute:nd x922, secondHalf:nd x922
    +      nota: [PUNTA] valutata 3850 volte | stati {'no': 3819, 'nd': 31} | segnali 0 | scartata per: score:no x3389, entry:nd x3248, leadFav:no x2787, minute:no x2504, minute:nd x461, score:nd x461
    +      nota: attivita' del servizio: diagnosi x26, skip x4, place x1, replay_chiusura_fuori_app x1, posizione_di_conto x1, chiuso_dall_utente x1, settle x1, settle_position x1
    -      nota: scarti dichiarati dal servizio: minuto_ingresso_oltre_uscita x2
    +      nota: scarti dichiarati dal servizio: partita_chiusa_dall_utente x2 | minuto_ingresso_oltre_uscita x2
    +      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: proprietari_bot_conto: tabelle degli altri bot e coda del runner (proprietari degli ordini altrui sul conto): non sono nel replay, un ordine non del bot si decide dai riferimenti (nessun altro bot)
    +      nota: [CHIUSO IL 16/09] l'utente ha chiuso a mano tutte le operazioni della partita. Safe ADESSO ce l'ha, il cash-out globale: kind `cashout_event` in `process_requests`, marcatore `meta.chiuso_dall_utente` sulle righe (sopravvive al riavvio) e `riprendi_evento` per tornare indietro (consegna S1 del 16/09 sera). Il reperto di ieri — nessuno stato per evento, quindi il bot poteva riaprire al cambiare del punteggio — non vale piu': qui si verifica che dal giro dopo non apra, non copra e non esca (controllo T14).
    -      nota:   B1   SPEC §1 tabella: Mercato = 1X2                                             x3847   viol=0   conforme
    -      nota:   B2   SPEC §1: BANCA (lay)                                                       x3847   viol=0   conforme
    +      nota:   B1   SPEC §1 tabella: Mercato = 1X2                                             x3850   viol=0   conforme
    +      nota:   B2   SPEC §1: BANCA (lay)                                                       x3850   viol=0   conforme
    -      nota:   B4   SPEC §1: minuto ingresso DAL 55' (soglia, non fascia)                      x3847   viol=0   conforme
    -      nota:   B5   SPEC §1: punteggio 1-0 / 2-1 / 2-0 (orientato sulla favorita)              x3847   viol=0   conforme
    -      nota:   B6   SPEC §1: quota favorita pre-match 1.40-1.80                                x3847   viol=0   conforme
    -      nota:   B7   SPEC §1: quota sfavorita pre-match 4-8                                     x3847   viol=0   conforme
    -      nota:   B8   SPEC §1 + decisione dell'utente 25/09 (Q1): quota di entrata 20-34 = QUOTA x3847   viol=0   conforme
    -      nota:   B9   decisione dell'utente 25/09 (Q1): NESSUN filtro sulla quota live della FAV x3847   viol=0   conforme
    +      nota:   B4   SPEC §1: minuto ingresso DAL 55' (soglia, non fascia)                      x3850   viol=0   conforme
    +      nota:   B5   SPEC §1: punteggio 1-0 / 2-1 / 2-0 (orientato sulla favorita)              x3850   viol=0   conforme
    +      nota:   B6   SPEC §1: quota favorita pre-match 1.40-1.80                                x3850   viol=0   conforme
    +      nota:   B7   SPEC §1: quota sfavorita pre-match 4-8                                     x3850   viol=0   conforme
    +      nota:   B8   SPEC §1 + decisione dell'utente 25/09 (Q1): quota di entrata 20-34 = QUOTA x3850   viol=0   conforme
    +      nota:   B9   decisione dell'utente 25/09 (Q1): NESSUN filtro sulla quota live della FAV x3850   viol=0   conforme
    -      nota:   B11  PROCESSO §6.2 / CERT 13/09: `pre_ko` CONGELATO al primo tick in-play, mai  x3417   viol=0   conforme
    +      nota:   B11  PROCESSO §6.2 / CERT 13/09: `pre_ko` CONGELATO al primo tick in-play, mai  x3420   viol=0   conforme
    -      nota:   B18  DECISIONE DELL'UTENTE 07/10: 'SAFE BASE SEMPRE E SOLO SECONDO TEMPO'       x3847   viol=0   conforme
    +      nota:   B18  DECISIONE DELL'UTENTE 07/10: 'SAFE BASE SEMPRE E SOLO SECONDO TEMPO'       x3850   viol=0   conforme
    -      nota:   E1   SPEC §2: LAY su Risultato Esatto, selezione «Altro risultato»              x7694   viol=0   conforme
    -      nota:   E2   SPEC §2: minuto ingresso DAL 48' (soglia)                                  x7694   viol=0   conforme
    -      nota:   E3   SPEC §2: punteggio 0-0 / 1-0 / 1-1 / 2-1 (qualsiasi orientamento)          x7694   viol=0   conforme
    +      nota:   E1   SPEC §2: LAY su Risultato Esatto, selezione «Altro risultato»              x7700   viol=0   conforme
    +      nota:   E2   SPEC §2: minuto ingresso DAL 48' (soglia)                                  x7700   viol=0   conforme
    +      nota:   E3   SPEC §2: punteggio 0-0 / 1-0 / 1-1 / 2-1 (qualsiasi orientamento)          x7700   viol=0   conforme
    -      nota:   E5   SPEC §2: quota di entrata 30-70                                            x7694   viol=0   conforme
    +      nota:   E5   SPEC §2: quota di entrata 30-70                                            x7700   viol=0   conforme
    -      nota:   E7   CERT 13/09: UN SOLO lato «Altro risultato» per partita                     x6449   viol=0   conforme
    -      nota:   E8   SPEC §2 uscita in profitto: esci comunque entro il 70-75'                  x908    viol=0   conforme
    -      nota:   E9   SPEC §2 uscita in perdita: la squadra BANCATA segna comunque -> esci e acc x908    viol=0   conforme
    -      nota:   E10  SPEC §2 «Selezione aggiuntiva»: scontri diretti senza troppe partite da 4+ x7694   viol=0   conforme
    -      nota:   E11  DECISIONE DELL'UTENTE 07/10: ESATTO 'tassativo nel secondo tempo, il primo x7694   viol=0   conforme
    +      nota:   E7   CERT 13/09: UN SOLO lato «Altro risultato» per partita                     x6452   viol=0   conforme
    +      nota:   E8   SPEC §2 uscita in profitto: esci comunque entro il 70-75'                  x0      viol=0   non lo so
    +      nota:   E9   SPEC §2 uscita in perdita: la squadra BANCATA segna comunque -> esci e acc x0      viol=0   non lo so
    +      nota:   E10  SPEC §2 «Selezione aggiuntiva»: scontri diretti senza troppe partite da 4+ x7700   viol=0   conforme
    +      nota:   E11  DECISIONE DELL'UTENTE 07/10: ESATTO 'tassativo nel secondo tempo, il primo x7700   viol=0   conforme
    -      nota:   P1   SPEC §4: PUNTA (back) sul 1X2, selezione = la favorita in vantaggio        x3847   viol=0   conforme
    -      nota:   P2   SPEC §4: minuto ingresso DAL 66' (soglia)                                  x3847   viol=0   conforme
    -      nota:   P3   SPEC §4: punteggio 2-0 / 3-1 / 3-0 (orientato sul leader)                  x3847   viol=0   conforme
    -      nota:   P4   SPEC §4: quota di entrata 1.03-1.10                                        x3847   viol=0   conforme
    -      nota:   P5   SPEC §4: aspetta 3-4' dopo il gol                                          x3847   viol=0   conforme
    +      nota:   P1   SPEC §4: PUNTA (back) sul 1X2, selezione = la favorita in vantaggio        x3850   viol=0   conforme
    +      nota:   P2   SPEC §4: minuto ingresso DAL 66' (soglia)                                  x3850   viol=0   conforme
    +      nota:   P3   SPEC §4: punteggio 2-0 / 3-1 / 3-0 (orientato sul leader)                  x3850   viol=0   conforme
    +      nota:   P4   SPEC §4: quota di entrata 1.03-1.10                                        x3850   viol=0   conforme
    +      nota:   P5   SPEC §4: aspetta 3-4' dopo il gol                                          x3850   viol=0   conforme
    -      nota:   T4   CERT 13/09 + 12/09: mai chiudere in perdita quando il margine e' ampio (de x444    viol=0   conforme
    +      nota:   T4   CERT 13/09 + 12/09: mai chiudere in perdita quando il margine e' ampio (de x0      viol=0   non lo so
    -      nota:   T6   PROCESSO §6.3 / manuale: lo stop giornaliero e i tetti fermano le APERTURE x6449   viol=0   conforme
    -      nota:   T7   CERT 13/09: i tetti di rischio a 0 sono SPENTI                             x6449   viol=0   conforme
    +      nota:   T6   PROCESSO §6.3 / manuale: lo stop giornaliero e i tetti fermano le APERTURE x6452   viol=0   conforme
    +      nota:   T7   CERT 13/09: i tetti di rischio a 0 sono SPENTI                             x6452   viol=0   conforme
    -      nota:   T12  Regola di piattaforma (utente, 16/09): MAI due lay DEL BOT sullo stesso me x909    viol=0   conforme
    +      nota:   T12  Regola di piattaforma (utente, 16/09): MAI due lay DEL BOT sullo stesso me x912    viol=0   conforme
    -      nota:   T14  Ordine dell'utente (16/09 h18:20): dopo il CASH-OUT GLOBALE del trader il  x0      viol=0   non lo so
    +      nota:   T14  Ordine dell'utente (16/09 h18:20): dopo il CASH-OUT GLOBALE del trader il  x919    viol=0   conforme
    -      nota:   J4   Catalogo §7.4/§7.6 + C.12a: nessuna riga TERMINALE con un ordine ancora VI x6449   viol=0   conforme
    -      nota:   J5   Catalogo §7.5: `closes_trade_id` in COLONNA, non nel meta                  x6449   viol=0   conforme
    +      nota:   J4   Catalogo §7.4/§7.6 + C.12a: nessuna riga TERMINALE con un ordine ancora VI x6452   viol=0   conforme
    +      nota:   J5   Catalogo §7.5: `closes_trade_id` in COLONNA, non nel meta                  x6452   viol=0   conforme
    -      nota:   J7   PROCESSO §6.4: mai due ordini vivi per lo stesso segnale                   x6449   viol=0   conforme
    -      nota:   K1   PROCESSO §7.36                                                             x917    viol=0   conforme
    +      nota:   J7   PROCESSO §6.4: mai due ordini vivi per lo stesso segnale                   x6452   viol=0   conforme
    +      nota:   K1   PROCESSO §7.36                                                             x920    viol=0   conforme
    -      nota:   K3   PROCESSO §7.36                                                             x917    viol=0   conforme
    -      nota:   K4   PROCESSO §7.36                                                             x909    viol=0   conforme
    -      nota:   K5   PROCESSO §7.36                                                             x917    viol=0   conforme
    +      nota:   K3   PROCESSO §7.36                                                             x920    viol=0   conforme
    +      nota:   K4   PROCESSO §7.36                                                             x912    viol=0   conforme
    +      nota:   K5   PROCESSO §7.36                                                             x920    viol=0   conforme
    -      nota:   K7   PROCESSO §7.36                                                             x917    viol=0   conforme
    +      nota:   K7   PROCESSO §7.36                                                             x920    viol=0   conforme
    -      motivo x933: base: no (score,dogLay)
    +      motivo x934: base: no (score,dogLay)
#### chiusura-abbinata-in-parte
    -      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive', 'save_event_model']
    -      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: get_event: tabella `events` (anagrafica partite): non e' nello stream di mercato registrato
    +      nota: metodi di database chiamati dal servizio e ASSENTI dal banco: ['proposte_di_chiusura_vive']

### testa
    -SCENARI: base, cap-stretto, bot-fermo, esiti-ignoti, feed-stantio, riavvio, paper, ordini-manuali, due-lay, manuale-e-bot, cashout-globale, chiusura-fuori-app, chiusura-fuori-app-ridotta, rifiuti-betfair, timeout-dopo-accettazione, chiusura-abbinata-in-parte, selezione-aggiuntiva, proposta-approvata, proposta-scaduta, proposta-anomalia-effimera, combos-automatiche, combos-gamba-automatica
    +SCENARI: base, cap-stretto, bot-fermo, esiti-ignoti, feed-stantio, riavvio, paper, ordini-manuali, due-lay, manuale-e-bot, cashout-globale, chiusura-fuori-app, chiusura-fuori-app-ridotta, chiusura-fuori-app-canale, rifiuti-betfair, timeout-dopo-accettazione, chiusura-abbinata-in-parte, selezione-aggiuntiva, proposta-approvata, proposta-scaduta, proposta-anomalia-effimera, combos-automatiche, combos-gamba-automatica

### coda
    +WARNING:safe.execution:[safe.exec] punta 2.17 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.17 dichiarato (trade 2)
    +WARNING:safe.execution:[safe.exec] punta 2.38 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.38 dichiarato (trade 5)
    +CRITICAL:safe.bot:[safe.bot] 35797769: partita CHIUSA DALL'UTENTE (cashout) -> il bot non gestisce piu' nulla su di essa
    +WARNING:safe.execution:[safe.exec] punta 2.17 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.17 dichiarato (trade 2)
    +WARNING:safe.execution:[safe.exec] punta 2.17 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.17 dichiarato (trade 2)
    +WARNING:safe.execution:[safe.exec] punta 2.17 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.17 dichiarato (trade 3)
    +WARNING:safe.execution:[safe.exec] punta 2.29 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.29 dichiarato (trade 2)
    +CRITICAL:safe.bot:[safe.bot] 35797769: partita CHIUSA DALL'UTENTE (cashout) -> il bot non gestisce piu' nulla su di essa
    +CRITICAL:safe.bot:[safe.bot] 35797769: partita CHIUSA DALL'UTENTE (fuori_app) -> il bot non gestisce piu' nulla su di essa
    +CRITICAL:safe.bot:[safe.bot] 35797769: partita CHIUSA DALL'UTENTE (fuori_app) -> il bot non gestisce piu' nulla su di essa
    +CRITICAL:safe.bot:[safe.bot] 35797769: partita CHIUSA DALL'UTENTE (fuori_app) -> il bot non gestisce piu' nulla su di essa
    +WARNING:safe.execution:[safe.exec] punta 2.17 -> 2.00 (multiplo di 0,50 per difetto): residuo 0.17 dichiarato (trade 2)
    +WARNING:safe.execution:[safe.exec] punta 6.02 -> 6.00 (multiplo di 0,50 per difetto): residuo 0.02 dichiarato (trade 1)
    +WARNING:safe.execution:[safe.exec] punta 3.98 -> 3.50 (multiplo di 0,50 per difetto): residuo 0.48 dichiarato (trade 2)
    +WARNING:safe.execution:[safe.exec] punta 6.02 -> 6.00 (multiplo di 0,50 per difetto): residuo 0.02 dichiarato (trade 1)
    +WARNING:safe.execution:[safe.exec] punta 3.98 -> 3.50 (multiplo di 0,50 per difetto): residuo 0.48 dichiarato (trade 2)
    -ESITO: 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni
    +ESITO: 23 partite senza violazioni, 0 con violazioni, 0 senza decisioni
    -     B1  x80841   [SPEC §1 tabella: Mercato = 1X2] la BASE opera solo sul mercato Ma
    -     B2  x80841   [SPEC §1: BANCA (lay)] la BASE e' una BANCA: il lato e' sempre LAY
    +     B1  x84694   [SPEC §1 tabella: Mercato = 1X2] la BASE opera solo sul mercato Ma
    +     B2  x84694   [SPEC §1: BANCA (lay)] la BASE e' una BANCA: il lato e' sempre LAY
    -     B4  x80841   [SPEC §1: minuto ingresso DAL 55' (soglia, non fascia)] nessun ing
    -     B5  x80841   [SPEC §1: punteggio 1-0 / 2-1 / 2-0 (orientato sulla favorita)] si
    -     B6  x80841   [SPEC §1: quota favorita pre-match 1.40-1.80] la favorita pre-KO d
    -     B7  x80841   [SPEC §1: quota sfavorita pre-match 4-8] la sfavorita pre-KO deve 
    -     B8  x80841   [SPEC §1 + decisione dell'utente 25/09 (Q1): quota di entrata 20-3
    -     B9  x80841   [decisione dell'utente 25/09 (Q1): NESSUN filtro sulla quota live 
    +     B4  x84694   [SPEC §1: minuto ingresso DAL 55' (soglia, non fascia)] nessun ing
    +     B5  x84694   [SPEC §1: punteggio 1-0 / 2-1 / 2-0 (orientato sulla favorita)] si
    +     B6  x84694   [SPEC §1: quota favorita pre-match 1.40-1.80] la favorita pre-KO d
    +     B7  x84694   [SPEC §1: quota sfavorita pre-match 4-8] la sfavorita pre-KO deve 
    +     B8  x84694   [SPEC §1 + decisione dell'utente 25/09 (Q1): quota di entrata 20-3
    +     B9  x84694   [decisione dell'utente 25/09 (Q1): NESSUN filtro sulla quota live 
    -     B11 x71811   [PROCESSO §6.2 / CERT 13/09: `pre_ko` CONGELATO al primo tick in-p
    +     B11 x75234   [PROCESSO §6.2 / CERT 13/09: `pre_ko` CONGELATO al primo tick in-p
    -     E1  x161682  [SPEC §2: LAY su Risultato Esatto, selezione «Altro risultato»] me
    -     E2  x161682  [SPEC §2: minuto ingresso DAL 48' (soglia)] nessun ingresso prima 
    -     E3  x161682  [SPEC §2: punteggio 0-0 / 1-0 / 1-1 / 2-1 (qualsiasi orientamento)
    -     E4  x7095    [SPEC §2: si banca chi ha segnato AL MASSIMO 1 gol] il lato bancat
    -     E5  x161682  [SPEC §2: quota di entrata 30-70] il LAY di «Altro risultato» deve
    +     E1  x169388  [SPEC §2: LAY su Risultato Esatto, selezione «Altro risultato»] me
    +     E2  x169388  [SPEC §2: minuto ingresso DAL 48' (soglia)] nessun ingresso prima 
    +     E3  x169388  [SPEC §2: punteggio 0-0 / 1-0 / 1-1 / 2-1 (qualsiasi orientamento)
    +     E4  x7431    [SPEC §2: si banca chi ha segnato AL MASSIMO 1 gol] il lato bancat
    +     E5  x169388  [SPEC §2: quota di entrata 30-70] il LAY di «Altro risultato» deve
    -     E7  x141939  [CERT 13/09: UN SOLO lato «Altro risultato» per partita] mai due l
    -     E8  x10975   [SPEC §2 uscita in profitto: esci comunque entro il 70-75'] oltre 
    -     E9  x10975   [SPEC §2 uscita in perdita: la squadra BANCATA segna comunque -> e
    -     E10 x161682  [SPEC §2 «Selezione aggiuntiva»: scontri diretti senza troppe part
    -     E11 x161682  [DECISIONE DELL'UTENTE 07/10: ESATTO 'tassativo nel secondo tempo,
    -     B18 x80841   [DECISIONE DELL'UTENTE 07/10: 'SAFE BASE SEMPRE E SOLO SECONDO TEM
    -     P1  x80841   [SPEC §4: PUNTA (back) sul 1X2, selezione = la favorita in vantagg
    -     P2  x80841   [SPEC §4: minuto ingresso DAL 66' (soglia)] nessun ingresso prima 
    -     P3  x80841   [SPEC §4: punteggio 2-0 / 3-1 / 3-0 (orientato sul leader)] si ent
    -     P4  x80841   [SPEC §4: quota di entrata 1.03-1.10] il BACK del leader deve star
    -     P5  x80841   [SPEC §4: aspetta 3-4' dopo il gol] fra il gol e l'ingresso devono
    +     E7  x148394  [CERT 13/09: UN SOLO lato «Altro risultato» per partita] mai due l
    +     E8  x10067   [SPEC §2 uscita in profitto: esci comunque entro il 70-75'] oltre 
    +     E9  x10067   [SPEC §2 uscita in perdita: la squadra BANCATA segna comunque -> e
    +     E10 x169388  [SPEC §2 «Selezione aggiuntiva»: scontri diretti senza troppe part
    +     E11 x169388  [DECISIONE DELL'UTENTE 07/10: ESATTO 'tassativo nel secondo tempo,
    +     B18 x84694   [DECISIONE DELL'UTENTE 07/10: 'SAFE BASE SEMPRE E SOLO SECONDO TEM
    +     P1  x84694   [SPEC §4: PUNTA (back) sul 1X2, selezione = la favorita in vantagg
    +     P2  x84694   [SPEC §4: minuto ingresso DAL 66' (soglia)] nessun ingresso prima 
    +     P3  x84694   [SPEC §4: punteggio 2-0 / 3-1 / 3-0 (orientato sul leader)] si ent
    +     P4  x84694   [SPEC §4: quota di entrata 1.03-1.10] il BACK del leader deve star
    +     P5  x84694   [SPEC §4: aspetta 3-4' dopo il gol] fra il gol e l'ingresso devono
    -     T1  x63      [B.5 (16/09): stake PER STRATEGIA, con ripiego per lato] l'importo
    -     T2  x89      [PROCESSO §6.4 / CERT 12/09: FILL OR KILL — un parziale e' un ERRO
    +     T1  x64      [B.5 (16/09): stake PER STRATEGIA, con ripiego per lato] l'importo
    +     T2  x90      [PROCESSO §6.4 / CERT 12/09: FILL OR KILL — un parziale e' un ERRO
    -     T4  x5364    [CERT 13/09 + 12/09: mai chiudere in perdita quando il margine e' 
    +     T4  x4920    [CERT 13/09 + 12/09: mai chiudere in perdita quando il margine e' 
    -     T6  x141939  [PROCESSO §6.3 / manuale: lo stop giornaliero e i tetti fermano le
    -     T7  x141939  [CERT 13/09: i tetti di rischio a 0 sono SPENTI] un cap a zero non
    -     T8  x63      [CERT 14/09: MODALITA' PER STRATEGIA (`strategy_modes`)] ogni riga
    +     T6  x148394  [PROCESSO §6.3 / manuale: lo stop giornaliero e i tetti fermano le
    +     T7  x148394  [CERT 13/09: i tetti di rischio a 0 sono SPENTI] un cap a zero non
    +     T8  x64      [CERT 14/09: MODALITA' PER STRATEGIA (`strategy_modes`)] ogni riga
    -     T12 x13620   [Regola di piattaforma (utente, 16/09): MAI due lay DEL BOT sullo 
    +     T12 x14535   [Regola di piattaforma (utente, 16/09): MAI due lay DEL BOT sullo 
    -     T14 x1838    [Ordine dell'utente (16/09 h18:20): dopo il CASH-OUT GLOBALE del t
    -     J1  x35      [Catalogo §7.1: chiave scritta in una grafia e letta in un'altra] 
    -     J2  x89      [Catalogo §7.2: `res.ok` mai letto — un rifiuto trattato come esec
    -     J3  x35      [Catalogo §7.3: campo inesistente letto con getattr -> prezzo medi
    -     J4  x141939  [Catalogo §7.4/§7.6 + C.12a: nessuna riga TERMINALE con un ordine 
    -     J5  x141939  [Catalogo §7.5: `closes_trade_id` in COLONNA, non nel meta] ogni g
    -     J6  x35      [Catalogo §7.7: `bet_id` salvato SOLO se abbinato] quando Betfair 
    -     J7  x141939  [PROCESSO §6.4: mai due ordini vivi per lo stesso segnale] l'idemp
    -     K1  x42119   [PROCESSO §7.36] cio' che la RIGA crede (abbinato e prezzo medio) 
    +     T14 x3676    [Ordine dell'utente (16/09 h18:20): dopo il CASH-OUT GLOBALE del t
    +     J1  x36      [Catalogo §7.1: chiave scritta in una grafia e letta in un'altra] 
    +     J2  x90      [Catalogo §7.2: `res.ok` mai letto — un rifiuto trattato come esec
    +     J3  x36      [Catalogo §7.3: campo inesistente letto con getattr -> prezzo medi
    +     J4  x148394  [Catalogo §7.4/§7.6 + C.12a: nessuna riga TERMINALE con un ordine 
    +     J5  x148394  [Catalogo §7.5: `closes_trade_id` in COLONNA, non nel meta] ogni g
    +     J6  x36      [Catalogo §7.7: `bet_id` salvato SOLO se abbinato] quando Betfair 
    +     J7  x148394  [PROCESSO §6.4: mai due ordini vivi per lo stesso segnale] l'idemp
    +     K1  x43042   [PROCESSO §7.36] cio' che la RIGA crede (abbinato e prezzo medio) 
    -     K3  x42197   [PROCESSO §7.36] il riferimento con cui il bot ha piazzato si RILE
    -     K4  x41968   [PROCESSO §7.36] una riga 'open' dichiara un ordine che a mercato 
    -     K5  x42119   [PROCESSO §7.36] il RESIDUO che la riga dichiara e' quello che il 
    +     K3  x43120   [PROCESSO §7.36] il riferimento con cui il bot ha piazzato si RILE
    +     K4  x42883   [PROCESSO §7.36] una riga 'open' dichiara un ordine che a mercato 
    +     K5  x43042   [PROCESSO §7.36] il RESIDUO che la riga dichiara e' quello che il 
    -     K7  x42119   [PROCESSO §7.36] ogni ordine ABBINATO a mercato appartiene a una r
    +     K7  x43042   [PROCESSO §7.36] ogni ordine ABBINATO a mercato appartiene a una r
