# SCALPER CALCIO — «MEDIA UNDER», terzo giro (06/10/2026)

Delegato (sessione cloud). Ramo `feature/scalper-media-under-giro3` da `master` `b0a1553`.
Valgono `SPEC_MEDIA_UNDER_2026-10-05.md` e `SPEC_MEDIA_UNDER_GIRO2_2026-10-05.md`; regola
nuova dell'utente del 06/10 (sostituisce il punto Q1 del referto del giro 2). Nessun ordine
vero, nessuna chiamata a Betfair, nessun accesso al DB, nessun `.env`, app non avviata.
Replay solo da `python -m Betfair.stream.backtest.certifica`, uno alla volta
(`--worker 1`), sulle due registrazioni VERE di `registrazioni_banco/`.

## 0. IN EVIDENZA — cio' che NON ho potuto verificare

1. **La regola nuova e' stata esercitata su UNA partita.** Sulla 35797769 agisce in due
   scenari (`media-under-tick-1`: ciclo 2 da -0,25 a +0,12; `media-under-35-liquidita-50`:
   rientro abbinato in parte, resto annullato, ciclo +0,14). Sulla 35760084 la modalita'
   non entra mai, nemmeno con la liquidita' minima a 100 e a 50 EUR (§3.1).
2. **Il caso «resto abbinato mentre il suo annullo e' in viaggio»** (la banca si
   riallinea sull'intera posizione) e' provato solo dal banco di prova con l'esecuzione
   differita di 4 book, mai visto su una registrazione.
3. **Media esattamente su un tick**: scelta mia (§4, Q1): il tick STRETTAMENTE sotto
   (media 2,20 esatta -> 2,18). Non capitato sulle due partite; provato solo dai test.
4. **Arrotondamento della banca al centesimo**: con un profitto teorico di pochi
   centesimi l'arrotondamento HALF_UP della banca puo' spostare il risultato di meno di
   un centesimo; non ho visto il caso (tutti i cicli chiusi >= +0,09).
5. **Ambiente**: Python 3.11 (l'utente 3.13); frontend non toccato e non rilanciato.
6. **La modalita' NON e' certificata** (mancano paper e soldi veri); P1, P8, P13 restano
   in attesa dell'utente.

## 1. La regola nuova: «e' sempre la quota media che comanda»

`media_under_bot.py`:

- `quota_della_banca(ultimo_ingresso, pos, N)`: la banca di chiusura va al PIU' BASSO fra
  `tick_sotto(ultimo_ingresso, N)` e `tick_sotto_la_media(pos.quota_media)` (il tick
  della scala vera STRETTAMENTE sotto la quota media delle punte abbinate), sulla
  posizione REALE abbinata. Usata da `_assicura_banca` (prima: solo l'ultimo ingresso).
- `_annulla_resti_delle_punte`: quando la banca si appoggia (posizione con punte
  abbinate), ogni punta ancora sul book con un resto non abbinato si annulla (ingresso o
  rientro). La banca copre l'intera posizione; se il resto si abbina mentre l'annullo e'
  in viaggio, la banca si riallinea (la regola del giro 2: annullo, attesa che sia morta,
  banca nuova).
- L'attivita' `media_banca` dice quando la quota viene dalla media («... (PERSIST, sotto
  la quota media 1.5057)», campo `dalla_media`).
- **Con i rientri abbinati per intero non cambia niente**: la formula del rientro chiude
  in profitto proprio a «ultimo ingresso - N tick», quindi la media sta sopra e il tick
  sotto la media non e' piu' basso (test sul vettore A; replay: `media-under`,
  `-paper`, `-obiettivo-030`, `-rientri-1`, `-rischio-30` e i 5 guasti IDENTICI al
  giro 2 del coordinatore, cicli e NETTO compresi).

**L'esempio dell'utente** (test `test_esempio_dell_utente_la_media_comanda`): punte 10
@2,18, 10 @2,20, 20 @2,22 e 2,99 abbinati su 40 @2,24 -> media 2,2074 -> banca 43,14
@2,20 sull'intera posizione (resto 37,01 annullato) -> **+0,14**; la regola di prima
(2,22, 42,75) -> -0,25.

**Banco**: M6 vuole la quota nuova; controllo nuovo **M11**: ogni banca viva prima del
fischio sta STRETTAMENTE sotto la quota media delle punte abbinate del ciclo e accanto a
lei nessun resto di punta e' vivo senza l'annullo gia' chiesto (stato `Cancelling`
ammesso: l'annullo e' in viaggio). Sollecitato in ogni scenario con una banca (da 287 a
5052 giri).

## 2. I replay (referti in `AUDIT_2026-10-06/replay/giro3/`)

Comando: `bash AUDIT_2026-10-06/strumenti/replay_giro3.sh` (riepilogo in
`riepilogo.txt`). Tempo per scenario fra 31 e 259 s: tutti sotto i 5 minuti (il piu'
lento `sniper-paper` 259 s; della modalita' il piu' lento 155 s).

### 2.1 I due replay chiesti dall'utente

| Partita | Scenario | Esito | Azioni | Riepilogo per ciclo | NETTO | Tempo |
|---|---|---|---|---|---|---|
| 35797769 | `media-under-liquidita-100` (Under 2,5, 100 EUR per lato) | OK | 5 | ingresso 10,00 @2,18 (139'43" al fischio); rientro @2,22 esatto 10,19, piazzato e abbinato 10,00; banca 20,18 @2,18 abbinata in gioco al 9'53"; +0,18 lordo, +0,17 netto | +0,17 | 148 s |
| 35797769 | `media-under-35-liquidita-50` (Under 3,5, 50 EUR per lato) | OK | 6 | ingresso 10,00 @1,43 (94'08" al fischio); rientro 1 @1,45 esatto 10,14, piazzato 10,00, **abbinato 2,98** (resto annullato, regola nuova); rientro 2 @1,47 esatto 20,28, piazzato e abbinato 20,00; totale 32,98; banca 33,12 @1,45 abbinata pre-match (7'14" al fischio); +0,14 lordo, +0,13 netto | +0,13 | 155 s |
| 35760084 | `media-under-liquidita-100` | **NE** | 0 | non entra: «liquidita' sotto il minimo al miglior prezzo (min size)» (x2392 book) | 0 | 32 s |
| 35760084 | `media-under-35-liquidita-50` | **NE** | 0 | non entra: liquidita' (x2410 book) | 0 | 32 s |

**Perche' la 35760084 non entra** (lettura del file della registrazione, non un replay:
Under in pre-match, minimo fra le quantita' al miglior prezzo di punta e di banca,
importi dello stream in GBP; il banco li converte in EUR): Under 2,5 mediana 8,6, massimo
51,2, mai >= 100, una volta >= 50; Under 3,5 mediana 10,3, 90° percentile 30,6, massimo
78,4, 8 aggiornamenti >= 50 (ma non insieme agli altri filtri: spread, flusso,
riscaldamento). Un mercato cosi' sottile non arriva a 100 EUR per lato.

### 2.2 I 12 scenari della modalita' e i 3 sulla 35760084, confronto col giro 2 del coordinatore

`python AUDIT_2026-10-06/strumenti/confronta_giro3.py` (righe OK/KO/NE, righe dei cicli
e NETTO contro `AUDIT_2026-10-05/replay/giro2_coord/`):

- `media_35797769`, `guasti_35797769`, `media_35760084`: **IDENTICI**.
- `varianti_35797769`: identici `obiettivo-030`, `rientri-1`, `rischio-30`; **diverso
  `media-under-tick-1`** (la regola nuova, attesa):
  - giro 2: ciclo 2 rientro 3 @2,24 abbinato 2,99 su 40,00, banca 42,75 @2,22,
    **-0,25**; NETTO della partita **-0,16**; azioni 19;
  - giro 3: alla prima parte abbinata (1,49) la banca si appoggia e il resto si annulla;
    banca 41,61 @2,20 (sotto la media), abbinata in gioco al 9'53", **+0,12** lordo
    (+0,11 netto); NETTO della partita **+0,20**; azioni 17.

### 2.3 Lo Scalper con la modalita' spenta

I 15 scenari sulla 35797769 e `base,paper` sulla 35760084: righe OK/KO/NE **IDENTICHE**
a `giro2_coord` (gruppi A1, A2, B1, B2, B3, C).

## 3. Test e falsificazione

- Nuovo `Betfair/stream/tests/test_scalper_media_under_giro3_2026_10_06.py` (15 casi):
  l'esempio dell'utente; il vettore A invariato; la media su un tick; su flumine vero il
  rientro in parte con resto annullato, banca sotto la media e ciclo in profitto; i
  rientri per intero con la banca dove era; M11 muto sul bot e rosso sui due difetti; M6
  con la regola nuova; i due scenari di liquidita'.
- Cambiati nei giri precedenti (descrivevano la regola vecchia): giro 2
  `test_punta_abbinata_in_due_tempi_la_banca_si_riallinea` (ora: resto annullato con
  l'annullo veloce, banca riallineata con quello lento) e `test_ciclo_chiuso_in_perdita_lo_dice`
  (ora sul testo, `testo_ciclo_chiuso`: la perdita non e' piu' raggiungibile dal bot);
  giro 1 `test_controlli_m_rossi_sui_difetti` (M6 falsificato con 3 tick dichiarati:
  con 1 tick la banca a 1,52 e' GIUSTA, la media 1,525 comanda) e l'elenco dei
  controlli M (M11).
- Falsificazione `python AUDIT_2026-10-06/strumenti/mutazioni_media_under_giro3.py`:
  **12 mutazioni, 12 rosse** (esito in `mutazioni_media_under_giro3_esito.json`):

| # | mutazione | test rossi |
|---|---|---|
| H1 | la media non comanda (regola vecchia) | 10 |
| H2 | il piu' alto fra le due quote | 31 |
| H3 | tick sotto la media non stretto | 1 |
| H4 | il resto delle punte non si annulla | 9 |
| H5 | l'annullo dei resti non tocca le punte | 9 |
| H6 | l'attivita' non dice «dalla media» | 2 |
| H7 | M11 muto su una banca non in profitto | 2 |
| H8 | M11 muto su un resto vivo | 2 |
| H9 | M11 rosso con l'annullo gia' chiesto | 4 |
| H10 | M6 con la regola vecchia | 6 |
| H11 | lo scenario Under 3,5 gira sull'Under 2,5 | 2 |
| H12 | lo scenario 100 gira coi 300 di serie | 1 |

  Rilanciate anche le tre del revisore (G1 soglia del rientro, G2 banca mai
  riallineata, G3 solo la quota): ancora rosse coi test del giro 3.
- Suite `python -m pytest Betfair/ -q -p no:cacheprovider`: **10138 verdi, 5 rossi**, 54
  saltati, 6 xfailed (454 s). I 5 rossi sono i test sui tempi di Safe
  (`Betfair/safe_strategy/tests/test_velocita_feed_2026_09_30.py`, dominio non toccato),
  gli stessi del giro 2, rossi identici su `master` pulito in questo ambiente (sul PC
  dell'utente il coordinatore li ha verdi).

## 4. Punti dove la regola non decide

- **Q1 — Media esattamente su un tick.** «Arrotondata al tick inferiore»: ho preso il tick
  STRETTAMENTE sotto, perche' chiudere sulla media stessa da' zero e la regola dice
  «sempre in profitto». Esempio: 10 @2,18 + 10 @2,22 = media 2,20 -> banca a 2,18
  (chiudendo a 2,20: 0,00). Se si vuole «al tick, compreso», e' la mutazione H3.
- **Q2 — «In qualsiasi fase».** L'annullo dei resti vale ogni volta che la banca si
  appoggia o si riallinea in pre-match. In gioco la modalita' non annulla niente (spec
  par.3.6) e le punte LAPSE le toglie Betfair al fischio: nessun caso.
- **Q3 — Una banca riallineata dopo che il resto si e' abbinato «in viaggio».** La regola
  vuole la banca sull'intera posizione: la banca vecchia si annulla e si rimette (mai due
  vive insieme). Effetto: un annullo e un piazzamento in piu'.
- P1, P8, P13: in attesa dell'utente, non toccati.

## 5. File toccati

| File | Cosa |
|---|---|
| `Betfair/stream/scalper/media_under_bot.py` | `tick_sotto_la_media`, `quota_della_banca`, `testo_ciclo_chiuso`; `_assicura_banca` (quota della media, annullo dei resti, attivita'); `_annulla_resti_delle_punte` |
| `Betfair/stream/scalper/certificazione.py` | M6 con la regola nuova; M11 (`_m_tick_sotto_media`, `_q_m_banca_viva`) |
| `Betfair/stream/scalper/tools/replay_registrazioni.py` | scenari `media-under-liquidita-100`, `media-under-35-liquidita-50`; `mercato_media` legge il mercato della variante |
| `Betfair/stream/tests/test_scalper_media_under_giro3_2026_10_06.py` | NUOVO |
| `Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py`, `..._2026_10_05.py` | i tre test della regola vecchia (§3) |
| `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md` | §14: la regola |
| `AUDIT_2026-10-06/strumenti/` | `replay_giro3.sh`, `confronta_giro3.py`, `mutazioni_media_under_giro3.py` (+ esito) |
| `AUDIT_2026-10-06/replay/giro3/` | i referti |

Nessun file vietato toccato; nessuna migrazione; nessuna regola di strategia oltre a
quella dell'utente (soglie, stake, tetti e gambe invariati).
