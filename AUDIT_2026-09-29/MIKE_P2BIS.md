# CANTIERE MIKE-MOTORE - Pacchetto P2-bis (29/09/2026)

Patch: `AUDIT_2026-09-29/MIKE_P2BIS.patch`, fatta e provata su master `08b9c6a` (contiene gia'
P1-P3, P4 1-5, P5 blocco 1, P6 1-5). Verificato anche: si applica pulita su `bf48003`. Nessun
commit. Worktree riallineato a master prima del lavoro (il non consegnato salvato in
`AUDIT_mike_motore_tmp/`, fuori dal repo tracciato).

| File | + / - |
|---|---|
| `Betfair/mike/engine.py` | +12 / -4 (solo punto B) |
| `Betfair/mike/tools/synth_mike.py` | +151 / -8 (punto C) |
| `Betfair/mike/tests/test_mike_p2bis_2026_09_29.py` | nuovo, 11 test (A e B) |

## A. Test mancanti (codice NON toccato)
| Mutazione del coordinatore | Test | Esito della mutazione |
|---|---|---|
| Z1 fischio senza `lay_in_volo(...) is None` | `test_z1_...` (banca `pending` abbinata per intero e banca a esito ignoto: conti piatti ma nessun giro chiuso) | ROSSO (2) |
| Z3 WATCH senza `params["pre_enabled"]` | `test_z3_...` (pre-partita spento dopo il segno: resta WATCH, nessun ordine) | ROSSO |
| Z12 `_decide_ko_green` solo `l.is_live` | `test_z12_...` (banca a esito ignoto al fischio: niente banca del fischio, niente seconda puntata col gol, niente copertura a finestra scaduta) | ROSSO |
| Z16 veto gia' scattato ignorato | `test_z16_...` (veto scattato, P ora 0,95: niente ultimo ingresso) | ROSSO |
| C3 banco B6 sullo stato muto | `test_c3_...` (ingresso dopo il segno da PRE_OPEN e da HOLD senza gambe nuove: B6 parla; da WATCH tace) | ROSSO |

## B. Punteggio assente (M8.4)
- `smart_cashout`: con `goals is None` non scatta (telemetria `punteggio_assente: True`). Prima
  `int(goals or 0)`.
- `cover_timing`: con `goals is None` -> `"wait"` (prima dello `skip` e del `cover_policy`).
- `_decide_uncovered` (2 righe, dove la copertura ORDINATA trasformava ogni "wait" in "cover"):
  `... and snap.goals is not None`, e il motivo dell'attesa diventa «copertura: punteggio
  assente, attendo». ATTENZIONE: sono le uniche 2 righe toccate nelle funzioni della copertura
  (conflitto possibile col delegato della copertura: righe 3577 e 3613 di questo master).
- Seconda puntata: gia' ferma senza punteggio (`gol_dopo_il_fischio` torna falso): provato.
Test prima rossi: M0 (motore di master senza B) -> 4 test rossi; poi verdi.
Mutazioni B1-B4 (una per riga): tutte ROSSE.

`AUDIT_2026-09-29/mike_p2bis/falsifica_mike_p2bis.py <engine di prima>`: M0, Z1, Z3, Z12, Z16,
C3, B1, B2, B3, B4 tutte ROSSE, ripristino verificato (hash).
Suite `Betfair/mike` su 08b9c6a + patch: **1165 verdi**. Su bf48003 (prima): 1133 verdi, e
`-k "mike or banco or certifica or uscite"` con `Betfair/stream/tests`: 1483 verdi, 25 saltati.

Conseguenza da sapere (non e' un difetto, e' la regola): con il punteggio assente una posizione
scoperta RESTA scoperta finche' il punteggio non torna (la copertura aspetta).

## C. Registrazioni sintetiche (dichiarate SINTETICHE, cartella `_synth_mike_*`)
- `reingresso_2gol`: come `reingresso`, gol al 15' e al 25'; dopo il primo l'Under 4,5 resta a
  1,40 (<= ingresso 1,50: niente rientro con 1 gol), dopo il secondo sale a 1,60: rientro con
  2 gol. Finisce 2-0.
- `ultimo_ingresso`: ingresso, banca abbinata a 25' dal fischio (piatto), mercati SOSPESI da
  24' a 10' (nessun giro nuovo), al segno riaprono a 1,50/1,52: ultimo ingresso con banca a
  1,48 non abbinata; al fischio LAPSE, poi il gioco (0-0).
- I casi esistenti `reingresso` e `prezzo_migliore` escono IDENTICI byte per byte
  (`mike_p2bis/confronta_synth.py`).
- Comando per rigenerarli (dalla radice del repo; i file vanno in `_live_raw/`, ignorata da git):
  `python -m Betfair.mike.tools.synth_mike --caso reingresso_2gol`
  `python -m Betfair.mike.tools.synth_mike --caso ultimo_ingresso`
  (da un worktree aggiungere `--data-dir "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"`).
- `certifica mike _synth_mike_reingresso_2gol _synth_mike_ultimo_ingresso --scenari base
  --trasporto canale --worker 0` (ambiente neutro): **2/2 OK, 0 violazioni**; H1 x1, H2 x1
  (rientro con 2 gol), B6 x1, D3 x771. Tempo 94 s totali (25,4 s | 128 tick/s ciascuna).
  Referto: `AUDIT_2026-09-29/mike_p2bis/replay_sintetiche.txt`.

## Reperti trovati costruendo le sintetiche
1. **Book incrociato nelle sintetiche (difetto dello strumento)**: `Costruttore.tick` scrive un
   solo livello `atb`/`atl` per selezione; i messaggi `rc` sono DELTA, quindi un livello a cui si
   e' scritto una volta (es. `atl` 1,48) resta nel ladder quando il prezzo si sposta (servirebbe
   mandarlo a size 0). Nel caso `ultimo_ingresso` il book risultava back 1,50 / lay 1,48
   (incrociato). Aggirato nel caso nuovo (la banca si abbina con lo scambiato `trd` senza
   spostare il book). I casi `reingresso`/`prezzo_migliore` hanno lo stesso limite dopo il
   fischio e dopo il gol (ho lasciato intatti i loro file): da correggere nello strumento,
   cambiera' i loro referti.
2. **Ultimo ingresso e dato del primo giro dopo il segno (decisione per l'utente)**: con un
   controllo d'ingresso che non passa al PRIMO giro dopo il segno (anche per un book momentaneo,
   es. lo spread) l'ultimo ingresso e' perso fino al fischio (si valuta una volta). Mercato
   sospeso e prezzi non vivi invece fanno aspettare. Se l'utente vuole, anche un book assente o
   uno spread fuori soglia al segno si possono trattare come "aspetto" invece di "valutato".

## Cosa NON ho verificato
- Il replay completo (`--scenari tutti`): lo fa il coordinatore.
- Il punteggio assente sul servizio vero in paper (solo motore e test).
