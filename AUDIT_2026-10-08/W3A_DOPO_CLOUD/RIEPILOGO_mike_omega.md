# DOPO W3a - Mike e Omega (replay cloud, 08/10/2026)

Codice: `b4d91ed` (ramo `claude/blissful-sagan-hri7o6-w3a-dopo-mo`). Macchina: container cloud,
`nproc` = 4. I 4 processi sono partiti IN PARALLELO, ciascuno `--worker 1`. Le registrazioni sono
quelle di `registrazioni_banco/`, decompresse in `_live_raw/` con lo script di `LEGGIMI.md`.
Ogni comando: `python -m Betfair.stream.backtest.certifica <bot> <evento> --scenari tutti --worker 1`.
Nessun codice modificato.

I riferimenti PRIMA sono due:
* Mike: `riferimenti_cloud/mike_<ev>_tutti.txt` (PRIMA su `1ac69d0`);
* Omega: `cantiere_7/replay/FINALE_<ev>_tutti.txt` (DOPO del cantiere 7, gia' integrato).

Strumento del confronto: `confronta.py` (in questa cartella). Per ogni scenario confronta la riga
di esito e tutte le righe del blocco; esclude i tempi e la testa (impronta, percorso). Uscita
completa in `confronto_righe_prima_dopo.txt`.

## Esito

| bot / evento | ESITO | OK / NE / KO | tempo (parete, 4 in parallelo) | tempo dichiarato dal banco |
|---|---|---|---|---|
| mike 35760084 | 29 partite senza violazioni | 28 / 1 / 0 | 757 s | 754.8 s |
| mike 35797769 | 29 partite senza violazioni | 23 / 6 / 0 | 2285 s | 2282.6 s |
| omega 35760084 | 22 partite senza violazioni | 22 / 0 / 0 | 319 s | 317.0 s |
| omega 35797769 | 22 partite senza violazioni | 20 / 2 / 0 | 1214 s | 1211.7 s |

* **Scenari KO: nessuno. Controlli violati: nessuno.**
* NE gia' presenti nel PRIMA (riga di esito identica):
  * mike 35760084: `cashout-dopo-copertura`;
  * mike 35797769: `gol-precoce`, `cashout-dopo-copertura`, `firma-dopo-gol-decisivo`,
    `firma-dopo-gol-decisivo-senza-chiusura`, `uscite-in-perdita-firmate`, `uscite-automatiche`.
* NE nuovi: omega 35797769 `chiuso-fuori-app-canale` e `ridotto-fuori-app-canale`. Causa
  dichiarata dal banco: «canale del conto mai sollecitato: Omega non ha aperto una posizione da
  chiudere/ridurre (E5-CANALE non giudicato)». Su questo evento Omega fa 0 azioni, con i motivi
  `no_runner_by_model` e `no_live_state`.
* Tempi oltre il tetto del banco di 600 s: mike su entrambi gli eventi e omega 35797769. I tempi
  sono misurati con 4 processi in parallelo su 4 core. E' un AVVISO del banco: l'esito non cambia.

## Differenze dal PRIMA

### Attese (referto `W3A_CONSAPEVOLEZZA_SERVIZI.md` §2.7, §4.1, §10)
* **Mike, scenari NUOVI**: `ridotto-fuori-app`, `annullato-dal-sito` e `manuale-app-paper <canale>`.
  Sono OK su entrambi gli eventi.
* **Omega, scenari NUOVI**: `chiuso-fuori-app-canale` e `ridotto-fuori-app-canale`.
  * Su 35760084 sono OK ed esercitati: E5 passa da `?? x0` a x218 e i MAI SOLLECITATI scendono da
    38 a 37.
  * Su 35797769 sono NE con causa dichiarata (Omega non apre). Vale la regola del §4.1: «NE con
    causa dichiarata dove il bot non apre».
* **Nota «NON ESERCITABILE: proprietari_bot_conto»**, aggiunta negli scenari con ordini
  dell'utente:
  * mike `chiuso-fuori-app`, gia' esistente, su entrambi gli eventi: unica riga diversa del blocco;
  * omega 35797769 `chiuso-fuori-app`, gia' esistente: unica riga diversa del blocco.

  Compare anche nei nuovi mike `manuale-app-paper` e omega 35760084 `*-canale`.
* **Coda del referto**:
  * la riga `SCENARI` contiene i nuovi scenari;
  * `ESITO` cresce del numero di scenari nuovi (mike da 26 a 29, omega da 20 a 22);
  * i contatori dei controlli crescono per i giri dei nuovi scenari.
* **Righe di log del servizio in coda ai .txt DOPO** (`CRITICAL:mike:...`, `WARNING:...`): nel PRIMA
  di Mike stavano in un `.err` separato, qui stderr e' unito a stdout (`2>&1`, come da ordine). Non
  e' una differenza di condotta.

### NON attesa (una)
**mike 35797769: la voce `posizione_di_conto xN` sparisce dalla nota «attivita' del servizio»** in
17 scenari ESISTENTI (`base`, `cap-stretto`, `senza-seconda-puntata`, `esiti-ignoti`, `riavvio`,
`gol-precoce`, `copertura-rifiutata`, `copertura-legacy`, `cashout-dopo-copertura`,
`ko-green-parziale`, `fermo-copertura`, `lettura-dati-ko`, `firma-dopo-gol-decisivo`,
`firma-dopo-gol-decisivo-senza-chiusura`, `uscite-in-perdita-firmate`, `uscite-automatiche`,
`punteggio-ko`).

* Nel PRIMA la voce compare da x95 a x319 per scenario; nel DOPO compare 0 volte. Fanno eccezione
  `chiuso-fuori-app` e i nuovi scenari, dove compare x1.
* Il resto della riga e' identico, salvo una differenza in `esiti-ignoti`: la lista mostra al piu'
  20 voci, quindi tolta `posizione_di_conto` entra in coda `chiusura_parziale x1`.
* Su 35760084 la differenza non c'e': li' `posizione_di_conto` non compariva nemmeno nel PRIMA.
* **Riga di esito identica** in tutti i 17 scenari: stesso tick, stesse decisioni, stesse azioni,
  stessi stati, stessa sigla OK/NE. Stessi `ESITO`, stessi conteggi dei controlli
  (R3 x9111 -> x36444 solo per i giri dei 3 scenari nuovi) e stessi MAI SOLLECITATI (11).

Righe complete PRIMA/DOPO, una coppia per scenario: `diff_posizione_di_conto_mike_35797769.txt`.
Esempio (`base`):
```
PRIMA:      nota: attivita' del servizio: posizione_di_conto x284, state x11, place x5, place_resting x3, skip x3, rilettura_alla_riapertura x2, feed_line_missing x2, flusso_interrotto x2, flusso_interrotto_senza_rest x2, pre_cycle x1, ordine_scaduto_alla_sospensione x1, cancel_richiesto x1, cancel_esito x1, cancel x1, cover x1, place_rifiutato x1, uscita_proposta x1, chiusura_parziale x1, settled x1
DOPO :      nota: attivita' del servizio: state x11, place x5, place_resting x3, skip x3, rilettura_alla_riapertura x2, feed_line_missing x2, flusso_interrotto x2, flusso_interrotto_senza_rest x2, pre_cycle x1, ordine_scaduto_alla_sospensione x1, cancel_richiesto x1, cancel_esito x1, cancel x1, cover x1, place_rifiutato x1, uscita_proposta x1, chiusura_parziale x1, settled x1
```

Ipotesi dell'esecutore, NON verificata (non ho rilanciato il PRIMA con il diario dettagliato):
* in `1ac69d0`, `_sorveglia_posizione_di_conto` scriveva `posizione_di_conto` a ogni lettura REST
  in due rami: per ogni selezione «parziale» («il conto contiene solo in PARTE la posizione di
  Mike... il bot continua») oppure per una gamba non ritrovata (`gambe_non_ritrovate`);
* con il verdetto in ESPOSIZIONE (§2.6 del referto), su 35797769 la posizione di Mike non risulta
  piu' parziale, cosi' le ~284 dichiarazioni spariscono.

La condotta resta coerente con questa ipotesi: nel DOPO un «parziale» fermerebbe Mike
(`chiuso_dall_utente`), e non succede, perche' le azioni sono identiche. Il referto §4.1 dice pero'
«Nessuno scenario esistente ha una riga diversa», e questo era misurato solo su 35760084. **Va
portato al coordinatore**: la conferma passa dal diario `posizione_di_conto` del PRIMA (quale
verdetto, quale selezione).

## File
* `mike_35760084_tutti.txt`, `mike_35797769_tutti.txt`, `omega_35760084_tutti.txt`,
  `omega_35797769_tutti.txt`: referti DOPO (stdout + stderr).
* `confronta.py`, `confronto_righe_prima_dopo.txt`: confronto riga per riga.
* `diff_posizione_di_conto_mike_35797769.txt`: le righe complete della differenza non attesa.
