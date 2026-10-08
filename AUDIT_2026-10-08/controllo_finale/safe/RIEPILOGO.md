# Controllo finale del banco - Safe (5 certificazioni, `--worker 3`)

Data: 08/10/2026. Esecutore: sessione cloud. Nessuna modifica al codice, nessuna modifica alle strategie.

## Stato di partenza

- Passo 0: `git fetch origin claude/blissful-sagan-hri7o6 && git checkout -B claude/blissful-sagan-hri7o6-finale-safe d01de76ea591a57850eff29063fa969abbf6559f`
  -> `git log --oneline -1` = `d01de76 docs: documento di verifica, riga e decisioni del cantiere 11, metodo con --worker 3` (OK).
- Registrazioni decompresse in `_live_raw/` con lo script di `registrazioni_banco/LEGGIMI.md`.
- Container: `pip install psutil` (4 core fisici). **Nota**: il container non aveva flumine
  (`ModuleNotFoundError: No module named 'flumine'` al primo lancio, rc=1 in 0 s, referto sovrascritto);
  e' stato quindi installato `pip install -r requirements.txt` nel solo container (versioni fissate:
  flumine 2.13.11, betfairlightweight 2.23.2, le stesse dichiarate nel riferimento).
- Ogni referto contiene la riga `worker: 3 su 4 core fisici (un processo per coppia evento x scenario, 23 coppie; ...)` (5/5).
- Impronta del codice bot: `ee82ce75a8ad (19 file)` in tutti i referti nuovi E nel riferimento -> nessuna differenza di tipo (b).

## Comandi e tempi (uno alla volta)

| # | comando | rc | durata (parete) | TEMPO TOTALE del referto |
|---|---|---|---|---|
| 1 | `python -m Betfair.stream.backtest.certifica safe_base 35797769 --scenari tutti --worker 3` | 0 | 624 s | 10m21.2s (621.2 s) - LENTO (avviso) |
| 2 | `python -m Betfair.stream.backtest.certifica safe_esatto 35797769 --scenari tutti --worker 3` | 0 | 591 s | 9m49.8s (589.8 s) |
| 3 | `python -m Betfair.stream.backtest.certifica safe_punta 35797769 --scenari tutti --worker 3` | 0 | 588 s | 9m45.7s (585.7 s) |
| 4 | `python -m Betfair.stream.backtest.certifica safe_esatto 35760084 --scenari tutti --worker 3` | 0 | 179 s | 2m57.6s (177.6 s) |
| 5 | `python -m Betfair.stream.backtest.certifica safe_punta 35760084 --scenari tutti --worker 3` | 0 | 174 s | 2m52.7s (172.7 s) |

Output: `<bot>_<ev>_tutti.txt` (stdout+stderr). Confronto: `confronto_<bot>_<ev>.txt`, prodotto da
`python -I confronta.py AUDIT_2026-10-08/W3A_DOPO_CLOUD/<bot>_<ev>_tutti.txt AUDIT_2026-10-08/controllo_finale/safe/<bot>_<ev>_tutti.txt`.

## Esiti (riga di esito)

| bot | evento | OK | NE | KO | righe di esito identiche al riferimento |
|---|---|---|---|---|---|
| safe_base | 35797769 | 23 | 0 | 0 | SI' (23/23, tick/decisioni/azioni/stati compresi) |
| safe_esatto | 35797769 | 23 | 0 | 0 | SI' (23/23) |
| safe_punta | 35797769 | 23 | 0 | 0 | SI' (23/23) |
| safe_esatto | 35760084 | 22 | 1 | 0 | SI' (23/23; NE = [chiusura-fuori-app-canale], NE anche nel riferimento) |
| safe_punta | 35760084 | 22 | 1 | 0 | SI' (23/23; NE = [chiusura-fuori-app-canale], NE anche nel riferimento) |

Nessun controllo violato nuovo, nessuna differenza nelle righe `nota:` di controllo, fill, P&L, righe, scarti.

## Metodo del confronto

Scenario per scenario (blocco = dalla riga di esito alla successiva), diff riga per riga. Escluse:
righe `tempo:` per scenario, `TEMPO TOTALE`, `LENTO`, `worker:`, `MEMORIA:`, righe di log `LIVELLO:modulo:`,
`comando:`, impronta del codice e percorso delle registrazioni nell'intestazione, righe vuote.
Classificate ATTESE (a): righe contenenti `save_event_model`, la nota «metodi di database chiamati dal
servizio e ASSENTI dal banco», la nota `[NON ESERCITABILE] ... get_event`.

## Differenze ATTESE

(a) note `save_event_model` / `[NON ESERCITABILE] get_event` spostate di scenario (reperto D-13), righe differenti:

| bot | evento | righe | scenari con la nota (riferimento -> nuovo) |
|---|---|---|---|
| safe_base | 35797769 | 3 | rif: base, manuale-e-bot, proposta-approvata, proposta-scaduta, proposta-anomalia-effimera, combos-automatiche, combos-gamba-automatica -> nuovo: gli stessi + **esiti-ignoti** (7 -> 8 scenari) |
| safe_esatto | 35797769 | 9 | rif: come sopra -> nuovo: base, **esiti-ignoti**, **rifiuti-betfair**, proposta-approvata, proposta-scaduta, proposta-anomalia-effimera, combos-automatiche, combos-gamba-automatica (manuale-e-bot non la ha piu'; 7 -> 8 scenari) |
| safe_punta | 35797769 | 3 | come safe_base: + **esiti-ignoti** (7 -> 8 scenari) |
| safe_esatto | 35760084 | 0 | - |
| safe_punta | 35760084 | 0 | - |

Totale righe attese (a): 15. Da notare per fedelta': non e' un puro spostamento, il numero di scenari con
la nota passa da 7 a 8 sui tre referti di 35797769.

(b) impronta del codice bot: 0 differenze (ee82ce75a8ad ovunque).

## Differenze NON ATTESE (per intero)

Una sola specie, presente in tutti e 5 i referti, 2 blocchi per referto (10 in totale): la riga
«attivita' del servizio» acquista `flusso_non_dichiarato x1`. Nient'altro cambia nei blocchi interessati
(riga di esito identica). Nessuna spiegazione aggiunta: solo i fatti.

### safe_base 35797769, safe_esatto 35797769, safe_punta 35797769 (identiche nei tre referti)

```
== [cap-stretto]
   PRIMA:       nota: attivita' del servizio: diagnosi x26, skip x7, replay_richiesta_manuale x1
   DOPO:        nota: attivita' del servizio: diagnosi x26, skip x7, replay_richiesta_manuale x1, flusso_non_dichiarato x1
== [bot-fermo]
   PRIMA:       nota: attivita' del servizio: replay_richiesta_manuale x2, settle x2, place x1, diagnosi x1, place_parziale x1, cashout x1, settle_position x1
   DOPO:        nota: attivita' del servizio: replay_richiesta_manuale x2, settle x2, flusso_non_dichiarato x1, place x1, diagnosi x1, place_parziale x1, cashout x1, settle_position x1
```

### safe_esatto 35760084, safe_punta 35760084 (identiche nei due referti)

```
== [bot-fermo]
   PRIMA:       nota: attivita' del servizio: replay_richiesta_manuale x2, place x1, diagnosi x1, place_parziale x1, cashout x1
   DOPO:        nota: attivita' del servizio: replay_richiesta_manuale x2, flusso_non_dichiarato x1, place x1, diagnosi x1, place_parziale x1, cashout x1
== [feed-stantio]
   PRIMA:       nota: attivita' del servizio: diagnosi x23, replay_richiesta_manuale x1, skip x1
   DOPO:        nota: attivita' del servizio: diagnosi x23, replay_richiesta_manuale x1, flusso_non_dichiarato x1, skip x1
```

### Dove compare `flusso_non_dichiarato` (fatto osservato, scenari con la voce nella riga di attivita')

| bot | evento | riferimento W3A_DOPO_CLOUD | nuovo (--worker 3) |
|---|---|---|---|
| safe_base | 35797769 | [base] | [base] [cap-stretto] [bot-fermo] |
| safe_esatto | 35797769 | [base] | [base] [cap-stretto] [bot-fermo] |
| safe_punta | 35797769 | [base] | [base] [cap-stretto] [bot-fermo] |
| safe_esatto | 35760084 | [cap-stretto] | [cap-stretto] [bot-fermo] [feed-stantio] |
| safe_punta | 35760084 | [cap-stretto] | [cap-stretto] [bot-fermo] [feed-stantio] |

Il riferimento ha la voce in un solo scenario per referto; il nuovo in tre. Non e' fra le differenze
dichiarate attese: va portata a chi coordina.

## File

- `safe_base_35797769_tutti.txt`, `safe_esatto_35797769_tutti.txt`, `safe_punta_35797769_tutti.txt`,
  `safe_esatto_35760084_tutti.txt`, `safe_punta_35760084_tutti.txt` (referti)
- `confronto_*.txt` (5 confronti), `confronta.py` (script del confronto), `tempi.log`
