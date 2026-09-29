# CANTIERE MIKE-MOTORE - Pacchetto P3: rientro con 1 o 2 gol (29/09/2026)

Patch: `AUDIT_2026-09-29/MIKE_P3.patch`, SOPRA P2 (verificato su indice temporaneo:
master + P1 + P2 applicate, P3 `--check` pulita). Nessun commit.

## 1. Cosa e' cambiato (M6.1, decisione 20)
| File | + / - | Cosa |
|---|---|---|
| `Betfair/mike/config.py` | +3 / -1 | `reentry_max_goals`: `(1, int, 0, 1)` -> `(2, int, 0, 2)` (valore di serie 2, limite massimo 2, minimo invariato) |
| `Betfair/mike/certificazione.py` | +3 / -3 | controllo H2: "1 o 2 gol e primo tempo" (era "ESATTAMENTE 1") |
| `frontend/src/lib/mike.ts` | +2 / -2 | pannello: `max: 1` -> `2`, default `1` -> `2`, suggerimento aggiornato. FUORI dal perimetro dichiarato ma OBBLIGATO: il test di contratto `test_contratto_parametri_stessi_clamp_scelte_e_default` confronta whitelist e pannello; senza, la UI bloccherebbe il 2. **Serve `npm run build`** (non l'ho lanciato: app viva, lo decide il coordinatore). |
| `migrations/mike_reentry_max_goals_2026-09-29.sql` | nuovo | porta a 2 il valore SALVATO in `mike_control.params` solo se e' ancora 1 (il vecchio default). SOLO DATI, idempotente, NON applicata: la applica l'utente. |
| test: `test_mike_engine.py` | +3 / -2 | `test_reentry_guards`: il caso "2 gol -> niente rientro" diventa "3 gol -> niente rientro" (decisione 20) |
| `Betfair/mike/tests/test_mike_p3_rientro_2026_09_29.py` | nuovo, 8 test | |

Il motore NON e' toccato: `engine.py` legge gia' `reentry_max_goals` e tiene il minimo di 1 gol
(`g < 1`). Tutte le altre condizioni del rientro invariate (provato con 2 gol: oltre il 45',
quota Under 4,5 non sopra il primo ingresso, chiusura non in profitto, rientro gia' fatto,
chiusura dell'utente -> nessun rientro).

## 2. Collegamenti controllati
`reentry_max_goals`: `engine.py` (unico lettore, `_decide_flat`), `config.py`, `certificazione.py`
(H2 ora, era indipendente dal parametro e resta indipendente: 1 o 2), frontend `lib/mike.ts`
(pannello e default), test di contratto UI, SQL (nessun vincolo sul parametro).

## 3. Test e falsificazione
Nuovi: parametro (default 2, clamp a 2), rientro con 0/1/2/3 gol in manuale e automatico, altre
condizioni con 2 gol, valore salvato 1 = esattamente 1 gol, banco H2.
Suite `Betfair/mike`: **1083 verdi**.
`AUDIT_2026-09-29/mike_p3/falsifica_mike_p3.py`: M1 (default e limite di prima), M2 (limite 2 ma
default 1), M3 (minimo di 1 gol tolto), M4 (H2 di prima), M5 (H2 muto), M6 (pannello max 1):
tutte ROSSE; ripristino verificato.

## 4. Replay (`AUDIT_2026-09-29/mike_p3/replay_p3_mike_tutti.txt`)
**15/15 OK, 0 violazioni**, azioni per scenario IDENTICHE al P2 (su 35760084 non c'e' mai un
rientro: H1 e H2 a zero casi, come nel riferimento). Tempi (s | tick/s): base 153,2|366; taker
145,5|386; cap-stretto 154,1|364; bot-fermo 94,3|596; senza-seconda-puntata 140,2|401;
feed-stantio 97,2|578; esiti-ignoti 145,8|386; taker-esiti-ignoti 149,2|377; riavvio 158,7|354;
gol-precoce 141,8|396; cashout-globale 134,3|419; chiuso-fuori-app 142,5|394;
copertura-rifiutata 138,9|405; rifiuti-betfair 134,7|417; chiusura-abbinata-in-parte 138,6|406.
Totale 764 s (LENTO, PC condiviso).

## 5. Cosa NON ho potuto verificare
- Il rientro con 2 gol sul replay (nessuna registrazione usata ha il caso): solo test.
- Il valore oggi salvato nel DB (non letto: DB non necessario). Se vale 1, finche' l'utente non
  applica la migrazione (o non lo cambia dal pannello) Mike rientra ancora solo con 1 gol.

## 6. Rischi e decisioni
- Nessun rischio per le partite in corso (parametro letto a caldo a ogni giro).
- Il suggerimento del pannello diceva "1 = linea 4.5 (unica nel feed)": con 2 gol il rientro resta
  sull'Under 4,5 (non sulla linea 5.5, che il feed non ha), come deciso dall'utente.
