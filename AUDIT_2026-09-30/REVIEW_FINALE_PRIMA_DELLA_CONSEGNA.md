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

Commit F: _(da scrivere)_

---

## A. Sezione UI (admin-07) — firma: _(in attesa)_

_(scrive solo admin-07)_

---

## B. Sezione backend + fusione (admin-bc) — firma: _(in attesa)_

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
| _(F2)_ | seconda ondata W_* di admin-07 + Safe/Omega P&L netto | _(in corsa)_ | |

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
| Safe-netto | ALTO (P&L) | `safe_strategy/execution.py:2152` | profit di Betfair preso come gia' netto di commissione | _(delegato in corsa)_ |
| M5 | MEDIO | `mikeEsitoChiusura.ts` | «nessuna esposizione» dalla credenza del bot, non dagli ordini riletti | PARZIALE: P13 mostra l'esito VERO delle gambe di chiusura («NON ABBINATO (verificato su Betfair)», «RIFIUTATO»); la dichiarazione «nessuna esposizione» resta della gamba del bot: DICHIARATO |

### B.3 Non verificato
- L'app a schermo (nessun build/riavvio finche' la review non e' chiusa).
- Il blocco `score` del record `eventTimelines` al KickOff (vedi `STATO_CORSIA_SCANNER_VELOCITA.md`).

---

## C. Review incrociata

_(admin-07 sui commit frontend di admin-bc: `REVIEW_INCROCIATA_COMMIT_FRONTEND_admin07.md`;
admin-bc sull'integrazione finale di `useControlRoom.ts` e `pages/ControlRoom.tsx`)_
