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
| _(F-1)_ | B1bis+P13+T_P4+G_P7+G_P8bis+C_P12b + M1 + M2 | admin-bc | _(in corsa)_ |
| _(F)_ | corsia scanner (b)(c)(d-1)(e) | admin-bc + revisore indipendente | 21 test, 12 mutazioni rosse; suite; replay base |

### B.2 Reperti
| # | Gravita' | Dove | Reperto | Esito |
|---|---|---|---|---|
| M2 (da admin-07) | ALTO | `BottoneChiudiRiga.tsx` | Conferma nello stesso punto del Chiudi: doppio clic = soldi veri senza conferma voluta | CORRETTO (400 ms, `ATTESA_CONFERMA_USCITE_MS`), 3 test adeguati + 1 nuovo |
| M1 (da admin-07) | MEDIO | `ParamsSheetBase.tsx` | dopo il salvataggio la bozza tornava ai valori vecchi finche' la rilettura non arrivava | CORRETTO (bozza = valori salvati), test nuovo |
| M3 | MEDIO | storico Mike | etichetta «per regolamento» vera solo con la migrazione `mike_storico_giorno_regolamento_2026-09-29.sql` applicata | l'utente ha dichiarato alle 12:xx «migrazioni applicate»; da confermare a voce nel rapporto |
| M4 | MEDIO | `Mike.tsx:771` | testo fisso «P&L del conto Betfair per le partite regolate dal 30/09/2026» | _(aperto / in correzione)_ |
| B4 | BASSO | badge flusso | «UNDER/OVER 3,5 FERMA» anche su partite che Mike non opera | RINVIATO a domani (cosmetico, veritiero: la linea e' ferma davvero) |

### B.3 Non verificato
- L'app a schermo (nessun build/riavvio finche' la review non e' chiusa).
- Il blocco `score` del record `eventTimelines` al KickOff (vedi `STATO_CORSIA_SCANNER_VELOCITA.md`).

---

## C. Review incrociata

_(admin-07 sui commit frontend di admin-bc: `REVIEW_INCROCIATA_COMMIT_FRONTEND_admin07.md`;
admin-bc sull'integrazione finale di `useControlRoom.ts` e `pages/ControlRoom.tsx`)_
