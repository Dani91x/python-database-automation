# Revisione indipendente: schema «come ha perso Mike» (partita 35760084) e referti del replay

Sessione `admin-bc` (Fable 5.1), 29/09/2026, dalle 19:10 alle 20:45 circa. Lavoro chiesto dalla sessione
coordinatrice `admin-e7` su ordine dell'utente: leggere, controllare e mostrare all'utente il materiale.

**Perimetro rispettato**: sola lettura. Nessun file di codice toccato, nessun replay lanciato, nessun
processo avviato, nessun commit. Unico file scritto: questo referto.

**Chiusura**: l'utente alle 20:45 ha ordinato «finite tutte le task attualmente attive e ci pensiamo
domani». Le decisioni qui sotto restano quindi APERTE per domani.

---

## 1. Cosa e' stato controllato e come

| Oggetto | Fonte usata | Esito |
|---|---|---|
| Risultato scenario normale -14,00 EUR, fill 1,71 e 4,00, 5 ordini, 17 proposte / 15 decadute | `replay/mike_tutti_P3_P4_3.txt`, `mike_tutti_P4_4_P5_1.txt`, `mike_tutti_P2BIS_P5_2_505s.txt`, `mike_tutti_P2BIS_P5_2B.txt` | confermato, identico nei quattro |
| Risultato scenario guasto dati -17,50 EUR, fill 1,71 e 2,64, 4 ordini, 10 proposte / 8 decadute | stessi referti, scenario `lettura-dati-ko` | confermato, identico nei quattro |
| 18 scenari, 0 violazioni | stessi referti | confermato |
| Minuti dei gol 7, 27, 45, 62 | `_live_raw/35760084/35760084.scores.jsonl` (cambi di punteggio 16:08:24, 16:28:27, 16:46:43, 17:23:59 UTC) | confermato |
| Fine della registrazione | `_live_raw/35760084/35760084.jsonl`, ultima riga 17:54:15 UTC; punteggi fino al minuto 92-93 | la registrazione copre tutta la partita |
| Ultimo aggiornamento di ogni mercato | stessa registrazione, per `market_id`; nomi da `35760084.raw.jsonl` (`marketType`) | vedi reperto 2 |
| Pagina unica e scheda dopo la correzione (19:58) | `SCHEMI_BOT/mike/partita_35760084/COME_HA_PERSO_35760084.html`, `SCHEDA_PARTITA.md` | le 6 correzioni chieste ci sono |
| Interruttore della copertura | `Betfair/mike/config.py:212` | valore di serie `back_over45` (forma vecchia) |
| Replay da 505,8 s | `replay/mike_tutti_P2BIS_P5_2_505s.txt`, commit `a742f5e` | 18 OK, 0 KO, 0 violazioni, nessuna riga «LENTO» |

Non controllato da me: le cifre delle singole 17 proposte e i loro orari (vengono dalla sonda del delegato,
non dal referto), l'importo 10,12 della banca pre-partita negli scenari diversi da
`chiusura-abbinata-in-parte` (dove il referto lo riporta), il contenuto dei quattro schemi come disegno.

---

## 2. Reperti, in ordine di importanza

### Reperto 1 — L'impronta «codice bot» del referto non copre il motore (DIFETTO DEL BANCO, APERTO)

- `Betfair/stream/backtest/certifica.py:192` calcola lo sha1 di `scheda.moduli_produzione` piu'
  `scheda.controlli`.
- Per Mike il registro (`Betfair/stream/backtest/registro_bot.py:118-122`) elenca solo
  `Betfair.mike.service` e `Betfair.mike.certificazione`: due file.
- Ricalcolato il 29/09 alle 20:40 su quei due file: `d45edb00f591`, uguale a quello stampato nei referti.
- `Betfair/mike/engine.py` (374 righe cambiate nel commit `9692eb4`) e `Betfair/mike/config.py` NON entrano
  nell'impronta. Non entrano nemmeno i moduli condivisi che il servizio importa
  (`safe_strategy.execution`, `stream.trading.stato_mercato`, ...).
- Prova: `mike_tutti_P4_4_P5_1.txt` (prima di `9692eb4`) e i due `mike_tutti_P2BIS_*` (dopo) portano la
  stessa impronta `d45edb00f591 (2 file)` e danno numeri diversi nello scenario `punteggio-ko`.

| Scenario `punteggio-ko` | P3_P4_3 e P4_4_P5_1 | P2BIS_505s e P2BIS_P5_2B |
|---|---|---|
| fill | 14,0 EUR (1,71 e 4,0) | 13,5 EUR (1,71 e 4,0) |
| P&L | -14,00 | -13,50 |
| proposte / decadute | 18 / 16 | 14 / 12 |
| motivi piu' ripetuti | chiudere (-2.34), (-2.38) | chiudere (-3.07), (-3.11) |
| motivi dichiarati in piu' | | `mercato_riaperto x2` |

- Gli altri 17 scenari sono identici nei quattro referti (esito, decisioni, azioni, ordini, fill, P&L,
  proposte e decadute).
- Il cambio dei numeri e' coerente con P2-bis («il punteggio assente non vale zero gol») e probabilmente e'
  voluto. In `MIKE_P2BIS.md` e `MIKE_P5_2B.md` non ho trovato ne' «13,50» ne' «punteggio-ko»: da scrivere
  come differenza attesa.
- Conseguenza: la riproducibilita' di `PROCESSO_STANDARD_BOT.md` §6.8 non e' garantita. Con ogni
  probabilita' vale anche per Omega, Safe, scalper e tennis, che nel registro hanno un solo modulo di
  produzione. NON verificato bot per bot.
- **Decisione dell'utente richiesta**: correggere l'impronta e' una modifica al banco comune. Nessuna
  correzione proposta ne' fatta.

### Reperto 2 — Il mercato Under 3,5 si ferma perche' e' deciso dal quarto gol (CHIUSO)

| Mercato | Gol che lo decide (UTC) | Ultima riga (UTC) |
|---|---|---|
| OVER_UNDER_05 | primo, 16:08:24 | 16:09:09 |
| OVER_UNDER_15 | secondo, 16:28:27 | 16:29:41 |
| OVER_UNDER_25 | terzo, 16:46:43 | 16:47:56 |
| OVER_UNDER_35 | quarto, 17:23:59 | 17:25:24 |
| OVER_UNDER_45 | nessuno | 17:54:11 |

Non e' un limite della registrazione. Accolto dal coordinatore.

### Reperto 3 — La sonda della banca Under 4,5 e' KO sul controllo J6 (APERTO, in lavorazione dal coordinatore)

- `replay/sonda_coordinatore_forma_banca_35760084.txt`: «ESITO: 1 partite senza violazioni, 2 con
  violazioni». KO su `base` e `cap-stretto`, controllo J6 (mai sovracopertura): «12.63 Over in volo+proposti
  contro un residuo previsto di 4.21».
- I numeri tornano: banca 12,63 EUR abbinata a 1,33, risultato -14,17 con 4 gol.
- Lettura probabile: il controllo confronta l'importo della banca con il residuo calcolato per la puntata.
  E' un controllo non ancora adattato alla forma nuova.
- Stato dichiarato dal coordinatore: forma nuova dietro interruttore, spenta di serie, non certificata.

### Reperto 4 — Perche' le proposte d'uscita si fermano alle 19:41 (APERTO, indagine del coordinatore)

- La scheda lo spiegava con la mancanza di un prezzo fresco dell'Under 3,5. Non regge: quel mercato e'
  fermo dalle 19:25:24 italiane e le proposte dalla 12 alla 17 nascono tutte dopo (19:25:33 - 19:41:34).
- Il coordinatore ha ritirato la dicitura «fatto verificato» e ha aperto un'indagine in sola lettura.

### Reperto 5 — Quale conto fa Mike per «chiudendo ora» dopo il gol che decide (APERTO, stessa indagine)

- Dopo il quarto gol l'Under 3,5 e' perso di sicuro (-10,00) e si puo' chiudere solo l'Over 4,5.
- Le cifre proposte (-2,54 al minuto 64) sono compatibili con «-10,00 piu' incasso della gamba Over 4,5».
- La scheda pero' dice che il conto ha usato un prezzo dell'Under 3,5 vecchio di 16 minuti. Se e' cosi', la
  cifra proposta all'utente da firmare puo' essere sbagliata.
- Stessa domanda per gli avvisi «flusso fermo» (`flusso_interrotto x37`, `flusso_interrotto_senza_rest x28`):
  guasto vero o mercato deciso scambiato per flusso fermo.

### Reperto 6 — Tempo della certificazione sopra il tetto (APERTO)

| Referto | Scenari | Tempo |
|---|---|---|
| `mike_tutti_P3_P4_3.txt` | 18 | 973,2 s |
| `mike_tutti_P4_4_P5_1.txt` | 18 | 872,6 s |
| `mike_tutti_P2BIS_P5_2B.txt` | 18 | 810,6 s |
| `mike_tutti_P2BIS_P5_2_505s.txt` | 18 | 505,8 s |

Standard dell'utente: 300 s, tetto 600 s. Il migliore e' sotto il tetto ma sopra l'obiettivo. Il coordinatore
lo misura a PC libero nel replay finale.

### Reperti minori, accolti e corretti dal coordinatore

- Esiti con i 4,00 EUR davvero abbinati: +2,75 (0-3 gol), -14,00 (4 gol), +1,40 (5 o piu'). «Circa +2» valeva
  solo a copertura piena.
- Orari in UTC presentati come ora italiana: corretti (ingresso 17:08, fischio 18:00).
- Minuto del quarto gol: 62, una sola dicitura.
- Frase «la registrazione finisce prima»: tolta.
- Referto citato aggiornato.
- Schema 4 sul guasto dei dati aggiunto.

### Da correggere ancora nella scheda

- `SCHEDA_PARTITA.md` riga 270: «circa 25 minuti» fra le 19:30:38 e le 19:41. Sono circa 11. Il coordinatore
  ha detto che lo fa correggere; alle 20:45 non ho ricontrollato.
- Le due spiegazioni dei reperti 2 e 4 vanno riportate nella scheda e nella pagina.

---

## 3. Punto di ripresa per domani

1. **Decisione dell'utente sul reperto 1**: correggere o no l'impronta del codice nel banco comune, e
   controllare gli altri bot.
2. Leggere l'esito dell'indagine del coordinatore sui reperti 4 e 5, poi ricontrollarlo in modo
   indipendente sulla registrazione.
3. Dopo la taratura di J6, rileggere il referto ufficiale della forma nuova: deve dare 0 violazioni prima
   che la banca Under 4,5 diventi di serie.
4. Ricontrollare pagina e scheda dopo le ultime correzioni (riga 270, reperti 2 e 4).
5. Confronto numero per numero del replay finale a PC libero contro la tabella del reperto 1: 17 scenari
   devono restare identici, `punteggio-ko` deve dare -13,50.

Finche' il reperto 1 resta aperto: due referti con la stessa impronta NON sono per questo fatti con lo
stesso codice. Usare gli hash dei file che il coordinatore scrive a parte.
