# MIKE P4 - blocco 1 (ordini): M6.2, M6.3, M8.3 + M8.13, M8.14

Patch: `AUDIT_2026-09-29/MIKE_P4_1.patch` (applicabile su master 2768f04: `git apply --cached --check` OK).
Nessun commit. Worktree `agent-a535d1b25bc591004`.

## 1. Difetti, causa radice, prova

| Punto | Difetto riprodotto sul codice di oggi (test rosso su HEAD) | Correzione |
|---|---|---|
| M6.2 | `_RealMarket` (sportello di produzione) NON aveva `order_state_by_bet_id` (`service.py` `_rileggi_ordine_appoggiato`: `getattr(market, "order_state_by_bet_id")` -> None -> esito `ignoto/mercato_senza_lettura`). Il finto del banco ce l'aveva. Inoltre `_segui_resting_live`, con la lay uscita dai correnti SENZA sospensione annotata (es. passaggio in gioco, o sospensione non vista dal feed), andava subito in `pending_reconcile` e poi `_reconcile_unknown` (che legge solo i regolati SETTLED/VOIDED) la chiudeva «mai piazzata». | `_RealMarket.order_state_by_bet_id` = delega a `omega_market.order_state_by_bet_id` (RIUSO, stesse chiavi). La meta' «per bet_id» di `_rileggi_ordine_appoggiato` estratta in `_rileggi_per_bet_id` (codice identico) e usata anche da `_segui_resting_live` PRIMA della riconciliazione: esito certo (scaduto/abbinato/parziale) -> `_applica_esito_riapertura` (con `fonte: fuori_dai_correnti`); ignoto, vivo o rete giu' -> riconciliazione come prima. |
| M6.3 | `_sorveglia_sospensione` leggeva lo stato solo dal libro Under 3,5: banca del rientro sull'Under 4,5 sospeso con 3,5 aperto = NON annotata; 3,5 sospeso = annotate anche le lay sul 4,5 aperto. | Stato letto dal mercato/selezione DI OGNI gamba appoggiata; rilettura solo quando i mercati delle gambe annotate sono tutti aperti (se non si trova nessuna gamba annotata: Under 3,5 come prima). Attivita' `mercato_sospeso` con chiave in piu' `mercati`. Controllo R1 del banco (`certificazione.py`) allineato: guarda i mercati delle gambe annotate. |
| M8.3 | Un rifiuto per fermo NOSTRO (`live_order_mode_non_live`, `live/db_kill_switch_attivo`, `kill_switch_illeggibile`, `freni_live_non_letti`, runner giu') passava da `_rifiutata` e `_esito_rifiuto_mercato` (conteggio del freno copertura) prima di `_ferma_aperture`: 3 fermi = copertura bloccata fino a «Riprendi». | In `execute_place` `fermo_nostro = _rifiuto_non_di_mercato(fill_note)`: se vero niente `_rifiutata`, niente conteggio; resta `_ferma_aperture` (gia' esistente) che fa ripartire da sola al cessare della causa (`_aggiorna_aperture_ferme`). |
| M8.13 | Un ritiro nostro riuscito scriveva la riga `status='error'`, come un rifiuto. | `status` NON cambiato (vincolo CHECK `pending|open|hedged|won|lost|void|error` e la pagina lo legge). Nuova chiave `meta.esito_ordine`: `ritirato_da_noi`, `rifiutato`, `non_abbinato_fok`, `cancellato_da_betfair`, `fermato_da_noi`. Scritta in: `execute_place` (ramo rifiuto), `_mark_trade_cancelled`, `_segui_ordini_paper_su_runner` (terminale senza abbinato), `_chiudi_gamba_scaduta`. |
| M8.14 | Il motivo della decadenza (`lapseStatusReasonCode`) non era letto. | Alias in `_ALIAS_ORDINE` (`lapse_status_reason_code`/`lapseStatusReasonCode`), campo in `_classifica_ordine` (None se manca, mai inventato), copiato in `meta` da `_chiudi_gamba_scaduta` se presente. Oggi vale sempre None: la lettura di `omega_market` non lo porta (proposta sotto). |

## 2. File toccati (righe)
- `Betfair/mike/service.py`: +105 / -19 (diff stat 124). Nuove funzioni: `_RealMarket.order_state_by_bet_id`, `_rileggi_per_bet_id` (estratta, corpo identico), `_esito_del_rifiuto`; costanti `ESITO_*`.
- `Betfair/mike/certificazione.py`: +5 / -1 (R1).
- `Betfair/mike/tools/replay_registrazioni.py`: +76 / -1 (scenario `fermo-copertura`).
- NUOVO `Betfair/mike/tests/test_mike_p4_ordini_2026_09_29.py` (24 test).
- Nessuna firma cambiata, nessun nome di stato/ruolo/parametro/tabella/colonna/kind cambiato. Chiavi AGGIUNTE: `meta.esito_ordine`, `meta.lapse_status_reason_code`, payload `mercato_sospeso.mercati`, numeri di riapertura `lapse_status_reason_code`, `fonte`.

Collegamenti controllati (grep): `order_state_by_bet_id` (solo `service.py` per Mike; Safe/Omega hanno i loro sportelli; banco `banco_comune.py:849`); `_rifiuto_non_di_mercato`/`_ferma_aperture`/`_aggiorna_aperture_ferme`; `registra_rifiuto(_copertura)`, `tentativo_gia_rifiutato`, `copertura_bloccata` (engine, solo letti); `_ALIAS_ORDINE` (usato da `campo_ordine`, `ordine_normalizzato`: chiave nuova aggiunta solo se presente nell'ordine); `mike.ts`/`tradeStatus.ts` (nessun kind nuovo); R1/S3 in `certificazione.py`.

## 3. Test
- `python -m pytest Betfair/mike -q -p no:cacheprovider` = **1044 passed** (1020 + 24 nuovi), 0 test esistenti modificati.
- `python -m pytest Betfair/stream/tests -k "mike or banco or certifica"` = 293 passed, 25 skipped (eseguito a meta' lavoro; da rilanciare sullo stato finale: vedi P4_2).
- Nuovi test, tutti ROSSI sul codice di HEAD (15 falliti / 2 di controllo verdi per costruzione: «ignoto resta in riconciliazione» e «i rifiuti del mercato contano ancora»).

Mutazioni (ripristino da copia + hash, `MUTAZIONE`=0 verificato):
| Mutazione | Esito |
|---|---|
| M1 fermo nostro contato (`_esito_rifiuto_mercato` sempre) | rosso `test_tre_fermi_nostri_non_bloccano_la_copertura` |
| M1b `_rifiutata` anche sul fermo | rosso idem |
| M2 stato solo dal 3,5 | rossi 3 test M6.3 |
| M2b R1 solo sul 3,5 | rosso `test_il_controllo_R1_guarda_il_mercato_della_gamba` |
| M3 niente rilettura fuori dai correnti | rosso `test_ordine_uscito_dai_correnti_...` |
| M4 sportello cieco (`found: False`) | rossi 7 test M6.2 |
| Replay: M8.3 mutato | `fermo-copertura` KO? vedi sez. 4 (non falsificabile a livello di replay, motivo scritto) |

## 4. Replay
Riferimento: `AUDIT_2026-09-28/replay/giro_finale_29_09/mike_*_9048238.txt`.
- `--scenari copertura-rifiutata --trasporto entrambi`: referto IDENTICO al riferimento riga per riga (tolti i tempi). 0 violazioni. Tempo 127 s (riferimento 90 s; PC carico da un altro delegato e dalle mie suite).
- `--scenari tutti --trasporto canale` (16 scenari: i 15 di prima + `fermo-copertura`): 0 violazioni; i 15 scenari di prima IDENTICI al riferimento (diff: solo righe WARNING del socket del banco in ordine diverso). Tempo 754 s (LENTO: riferimento 446 s con la stessa pool; misurato con suite pytest in parallelo sulla macchina). `fermo-copertura` 126,6 s, 444 tick/s: «aperture ferme dichiarate 1 | riprese 1 | copertura bloccata 0 | coperture abbinate 1».
- ATTENZIONE: queste due corse sono state fatte a meta' lavoro (codice del blocco 1 senza M8.13/M8.14, che aggiungono solo chiavi nel meta). Una corsa sul codice ESATTO della patch P4_1 e' in esecuzione: esiti nel messaggio di consegna / in P4_2.
- Falsificazione a livello di replay di M8.3: con la mutazione M1 e `cover_rifiuti_max=1` lo scenario diventa rosso (M8.3 x1, copertura bloccata), MA con la stessa taratura il codice CORRETTO fa scattare il controllo S3 (falso positivo del controllo: `_cover_rifiutate` conta ogni copertura annullata senza abbinato come «rifiutata dal mercato», anche quella fermata da noi o mai partita per prezzo non disponibile). Taratura tolta: lo scenario gira col default (3), dimostra fermo -> ripresa -> copertura abbinata; la falsificazione di M8.3 resta a livello di test unitario. PROPOSTA: S3 conti solo le coperture arrivate al mercato (ordine presente in `MercatoFlumine`), da decidere.

## 5. Parita' paper/live
Stesso codice in entrambe: M8.3 vale per `blocco_paper` (freno paper) e per `_live_brake`; `esito_ordine` scritto sia sui rami paper (runner) sia live. M6.2/M6.3: la lettura per bet_id e' solo live (in paper l'esito lo dice il runner, invariato); M6.3 vale anche in paper (la sospensione annotata dal mercato giusto, poi l'annullo sul runner come prima).

## 6. Cosa NON ho fatto / NON verificato
- Nessuna chiamata vera a Betfair: `order_state_by_bet_id` provato col client finto che risponde con le chiavi grezze di Betfair.
- «Ritirato da noi» vs «cancellato da Betfair» nella rilettura per bet_id: la funzione condivisa di `omega_market` NON dice quale lista regolata (LAPSED o CANCELLED) ha trovato l'ordine. In quel percorso la gamba e' viva per Mike (un annullo nostro la toglie prima), quindi l'esito «scaduto» = Betfair; la distinzione certa richiede la proposta M8.14 sotto.
- Scenari di banco «sospensione con banca appoggiata sul 3,5 e sul 4,5»: il 3,5 e' coperto dallo scenario `gol-precoce` esistente sulle registrazioni con gol precoce (su 35760084 la sospensione con lay viva non capita: «riletture nessuna», come nel riferimento); per il 4,5 serve una registrazione con rientro appoggiato durante un gol: NON trovata, ⊘ dichiarato. Coperto da test unitari (`test_banca_del_rientro_*`).
- Gli scenari del banco non si possono provocare su un evento di mercato senza alterare la registrazione (vietato).

## 7. Proposte per il coordinatore (file fuori perimetro)
- M8.14, `Betfair/omega/omega_market.py`:
  - `_riga_corrente` (riga ~1433, dopo `"placed_date": o.get("placedDate"),`) aggiungere
    `"lapsed_date": o.get("lapsedDate"), "lapse_status_reason_code": o.get("lapseStatusReasonCode"),`
    (`CurrentOrder` di betfairlightweight li porta: `bettingresources.py:688-716`).
  - `order_state_by_bet_id`, ramo correnti (riga ~1374): aggiungere `"size_lapsed"`, `"size_cancelled"`, `"lapse_status_reason_code": o.get("lapseStatusReasonCode")`; ramo regolati (riga ~1391): `"bet_status": status` (dice se LAPSED o CANCELLED = cancellato da Betfair o ritirato da noi).
  - Il finto del banco (`banco_comune.py:872`) va allineato nella stessa modifica (stesse chiavi).
  Mike le legge gia' (alias + `_classifica_ordine`): nessun cambio in Mike quando arrivano.
- M8.13, UI: per mostrare «ritirato da noi / rifiutato / cancellato da Betfair / fermato da noi» basta leggere `meta.esito_ordine` nella scheda Trade (`frontend`); lo `status` resta 'error'. Se si vorra' uno status dedicato serve una migrazione del CHECK di `mike_trades` + UI.
- S3 (certificazione): vedi sez. 4.

## 8. Righe del motore (engine.py) da passare all'altro delegato
Nessuna per questo blocco.

## 9. Rischi per le partite in corso
- Una lay appoggiata live uscita dai correnti ora viene riletta per bet_id (una chiamata REST in piu', solo in quel giro): se Betfair la dice scaduta la gamba si chiude «cancellata da Betfair» invece di restare in riconciliazione; il motore puo' ri-appoggiarla (stessa regola della riapertura).
- Una partita con aperture ferme e un contatore del freno copertura GIA' salito per fermi vecchi (dati in `ctx.cover_rifiuti` salvati prima della patch) resta com'e': il contatore vecchio non viene ripulito (serve «Riprendi» se gia' bloccata).

## 10. Da controllare dal vivo in paper
- Col freno acceso e poi spento durante una copertura: attivita' `skip` con `aperture_ferme`, poi `state` `aperture_riprese`, poi la copertura parte; mai `error copertura_bloccata`.
- Righe `mike_trades` in `error`: `meta.esito_ordine` valorizzato.
