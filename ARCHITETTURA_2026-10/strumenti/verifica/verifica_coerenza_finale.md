# Verifica di coerenza finale di 04/05/06/08 (08/10/2026)

Strumento: `strumenti/verifica/coerenza_finale.py` (sola lettura) + grep. Nessun contenuto tecnico cambiato.

## Controlli fatti (tutti coerenti salvo le 4 correzioni sotto)
- Decisioni: 86 righe `| U-nn |` in 05 §8, nessun id duplicato, nessun buco (U-01..U-86); 7+9+23+21+19 = 79 (8.1-8.5) + 7 (8.6) = 86.
  Ogni U citato in 04 (34 id), 06 (22), 08 (12) esiste in 05 §8; descrizioni a campione (U-01, 17-19, 24, 27, 32, 37, 39, 44, 47, 48, 59-64, 71-74, 79-86) coerenti coi titoli di 05.
- Tappe: 29 = T0A, T0B, T0C + T1..T26; ogni Tnn citato in 05/06/08 esiste (i T01-T09 in 04 sono id di test di G, non tappe).
  Percorso critico di 05 §3 (rettifica) = quello di 05 §5 (rettifica) = 08 R19.
- Settimane/giorni: somma della tabella 05 §5 = 112-146 giorni (ricalcolata); 112/5-146/5 = 22-29 settimane; percorso critico
  rettificato 72-93 giorni = 14,4-18,6 settimane (ricalcolato) -> 16-20 con le ombre; sottoinsieme 02/10: 42-54 giorni (ricalcolato) -> 10-12;
  il 65-84 «sole tappe elencate» e +7-9 (T5 3-4 + T9 4-5) ricalcolati. 06 §6 e 08 R19 coincidono con 05.
- Righe: 04 §10: 39.645/381.554 = 10,39% (-10,4%); 66.922/381.554 = 17,54% (-17,5%); 341.909 e 314.632 coerenti con ~341.900/~314.600; 254.864+126.690 = 381.554.
- Processi: 18 -> 8 (supervisore + 7 servizi) in 04 §0, §5.1, S15, §10, 05 R7, 06 §3.
- Voci di 01: 970 voci in 04/05/06/08; 971 identificatori (A-013/A-014 sulla stessa riga) in 05 §9 e 08. Rieseguito `f05_verifica_copertura.py`: 971 in 01, 971 coperti, 0 mancanti, 0 doppi, 0 inesistenti.
- Tempi del banco: Mike 728 s (~12 min, 06), scalper 6.916 s (~2 h), Omega 33 min su 35797769, Safe 258/254 s, obiettivo 300 s tetto 600 (10 min): coerenti fra 04 L14, 05 T0A/§5/R14, 06 §6.
- 89 tabelle (00 §0): coerente in 04, 05 (T2, U-86), 08.

## Incoerenze trovate e correzioni (nota «[coerenza 08/10]»)
1. 05 §5 (riga «circa 13-17 settimane»): valore superato non marcato inline -> aggiunta marca «SUPERATO ... ora 16-20».
2. 05 §5 (riga «8-10 settimane con due linee»): idem -> «SUPERATO ... ora 10-12».
3. 05 §8 intestazione: «79 decisioni» senza dire che con 8.6 sono 86 -> chiarito (U-01..U-79 + U-80..U-86 = 86).
4. 06 §5: «-10%» contro -10,4% di 04 §0/§10 -> «-10,4%».

## Note, non modificate (contenuto, non editoriale)
- Omega: 05 §0 «Omega (433 s)» (replay tutti, 04 §11) e «33 min sulla 35797769» (CANT 11) sono misure di replay diversi; coerenti, ma il lettore puo' confonderli.
- 06 dice «970 cose» e 05/08 «971 identificatori»: la differenza e' spiegata in 05 §9 (due id sulla stessa riga).
- Le stime di 05 §5 (giorni) sono dichiarate dall'autore come non misurate (05 §9).
