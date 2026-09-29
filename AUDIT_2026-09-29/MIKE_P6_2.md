# CANTIERE MIKE-APP - Pacchetto P6, blocco 2: l'esito della chiusura nella scheda (M7.2), 29/09/2026

Patch: `AUDIT_2026-09-29/MIKE_P6_2.patch`, SOPRA `MIKE_P6_1.patch` (verificato: su un indice
temporaneo = master `83c999b` + P6_1 applicata, `git apply --cached --check` pulito).
Solo frontend, nessun Python, nessun commit.

## 1. Cosa e' cambiato
| File | Cosa |
|---|---|
| `frontend/src/lib/mikeEsitoChiusura.ts` (NUOVO) | funzione pura `esitoChiusuraMike(ev, {nowMs, tentativiMax})` + `contiPerMercato`, `esposizioniAperte` |
| `frontend/src/components/controlroom/EsitoChiusuraMike.tsx` (NUOVO) | il riquadro a video (un colore per esito, `data-tipo`) |
| `frontend/src/components/controlroom/SchedaMike.tsx` | +2 righe: import e montaggio sotto `PropostaUscitaMike` (card di Mike in Control Room) |
| `frontend/src/pages/Mike.tsx` | +4 righe: import e montaggio sotto `PropostaUscitaMike` in `renderCard` (pagina di Mike), con `tentativiMax = bot.params.close_max_attempts` |

Stesso componente e stessa funzione nei due punti: nessun secondo percorso.

## 2. Da dove arrivano i dati (tutti gia' pubblicati dal bot, nessuna lettura nuova)
- `ev.state` (LIVE_CLOSING = in corso; FLAT / SETTLING = chiusa; WATCH + `ctx.close_reason='manual'`
  + `ctx.no_reentry` = chiusa col tuo comando in pre-partita).
- `ev.ctx.close_reason` (motivo: `profit` = da sola in profitto, `manual` = Chiudi/Cash out,
  `loss_*` = uscita in perdita firmata), `ctx.attempts` (tentativo n = attempts + 1),
  `ctx.flatten_pending` (comando dell'utente in corso).
- `ev.positions` = le gambe del bot (`engine.Leg`): chiesto `size`, abbinato `matched`, prezzo
  medio `avg_price`, `status` (`pending` = sul book, `pending_reconcile` = esito ignoto, `open`,
  `cancelled`), `archived`.
- `ev.live.locked` (risultato bloccato netto) o, se manca, `live.pnl_totale_by_total` quando e'
  uguale su tutti i totali ancora possibili; `live.goals`; `live.published_ts` (eta' dei dati).

## 3. Le quattro frasi, e quando
- **«Chiusura in corso - tentativo n di M»** + una riga per ordine di chiusura (`under_close`,
  `over_close`, `manual_close`): «Chiusura Under 3.5 · banca · chiesti 10,14 € · abbinati 4,00 €
  @ 1,48 · abbinato in parte, resto sul book». Stato LIVE_CLOSING, o comando dell'utente in corso.
- **«CHIUSA - risultato bloccato +X,XX € - nessuna esposizione residua su questa partita»**
  SOLO se: (1) su OGNI mercato il risultato «se vince l'Under» e «se vince l'Over», calcolato
  dagli importi ABBINATI, e' uguale (entro 1 centesimo; mercato gia' deciso dai gol = certo);
  (2) nessun ordine vivo e nessun ordine a esito ignoto sulla partita; (3) risultato bloccato
  pubblicato; (4) dati della partita non piu' vecchi di 75 s.
- **«NON COMPLETA - resta esposizione di X,XX € su <selezione> [- tentativo n di M]»**: i conti
  degli abbinati NON sono pari (anche se il bot si dice FLAT: vincono i conti), oppure tentativi
  esauriti in LIVE_CLOSING. Sotto, per ogni linea: «linea 3.5: se vince l'Under +2,60 € / se
  vince l'Over −5,00 €». X = perdita peggiore sulla linea (o lo sbilancio, se entrambi positivi).
- **«CHIUSURA DA VERIFICARE ...»** coi motivi: ordine a esito ignoto, ordine ancora sul book,
  risultato bloccato non pubblicato, dati senza ora o vecchi di N s.

Conto PER MERCATO e non per selezione: dopo P5 la copertura e' una banca sull'Under 4,5 e la
sua chiusura una banca sull'Over 4,5; si pareggiano solo insieme (M3.4). Test dedicato.

## 4. Test nuovi (`EsitoChiusuraMike.test.tsx`, 15 test)
Nessun esito su partita che lavora e dopo un re-ingresso; in corso con ordine e tentativo;
flatten pre-partita in corso; tentativi esauriti -> NON COMPLETA 20 di 20; CHIUSA; FLAT
dichiarato ma banca abbinata a meta' -> NON COMPLETA con i due numeri; esito ignoto, ordine
vivo, risultato non pubblicato, dati vecchi -> DA VERIFICARE; linea decisa dai gol -> CHIUSA con
−10,00 dalla tabella per gol; copertura P5 pari per mercato; chiusura manuale pre-partita;
montaggio in `SchedaMike`. Finti: chiavi di `engine.Leg`, `service._CTX_FIELDS`, `ev["live"]`.

## 5. Test esistenti modificati
Nessuno.

## 6. Numeri
- `npx vitest run src/pages/Mike src/components/mike src/lib/mike src/components/controlroom`
  -> **64 file, 950 verdi, 1 saltato (gia' saltato prima)**.
- `npx tsc -p tsconfig.app.json --noEmit` -> **0 errori**.

## 7. Falsificazione (`falsifica_mike_p6.mjs 2`): 10 mutazioni, 10 ROSSE
E1 si crede allo stato FLAT (niente prova sui conti); E2 conti per selezione invece che per
mercato (10 rossi); E3 esito ignoto ignorato; E4 ordini vivi ignorati; E5 dati vecchi
ignorati; E6 linea decisa contata come esposta; E7 tentativi esauriti letti come «in corso»;
E8 risultato non pubblicato non segnalato; E9 SchedaMike non monta l'esito; E10 tentativo
contato da zero. Ripristino da copia con hash: file identici.

## 8. Cosa NON ho potuto verificare
- Dal vivo: nessuna chiusura vera o paper vista a video (niente app, per regola).
- Nella Control Room il massimo dei tentativi e' il valore di serie (20): la card di Mike in
  Control Room non riceve i parametri del bot (servirebbe toccare `pages/ControlRoom.tsx`). Con
  il parametro cambiato dall'utente la pagina di Mike e' giusta, la Control Room direbbe 20.
- La velocita' con cui l'esito cambia in Control Room: senza il blocco 3 (M7.1) la card legge
  il database ogni 30 s; col blocco 3 lo stato e le gambe arrivano dal canale al ms. Il
  contesto (`close_reason`, `attempts`) arriva solo dal database (il bot non lo spinge sul canale).

## 9. Campi che servirebbero dal bot (NON inventati, NON toccato il Python)
1. **Quando le gambe sono state confermate da Betfair.** Il piano chiede che l'assenza di
   esposizione si dichiari sui conti «riletti da Betfair». Le gambe di `positions` sono
   aggiornate dal bot con lo stato ordini di Betfair, ma nessun campo dice QUANDO e' stata
   l'ultima rilettura. Proposta: `live.ordini_verificati_ts` (epoch s dell'ultima rilettura degli
   ordini della partita da Betfair / dal runner in paper) nel blocco `ev["live"] = {...}` di
   `Betfair/mike/service.py` (circa riga 4604), NON fra i `_LIVE_VOLATILI` (e' un fatto), e
   dichiarato in `MikeLive` (il contratto Python lo pretende). Con quello la scheda scriverebbe «verificato su Betfair N s fa» e
   non firmerebbe «nessuna esposizione» oltre una soglia.
2. **Risultato bloccato per MERCATO dopo P5.** `engine.locked_pnl` usa `open_selections` (per
   selezione): con copertura Under 4,5 + chiusura Over 4,5 tornerebbe `None` anche a posizione
   pari. La scheda ripiega su `pnl_totale_by_total` (gia' pubblicato), quindi funziona; ma e' un
   punto per il delegato P5 (M3.4).
3. Facoltativo: `ctx.close_max_attempts` o simile, per il «di M» della Control Room.

## 10. Da controllare in paper
Dopo un cash out (automatico in profitto o dal pulsante): sotto la card compare «Chiusura in
corso - tentativo 1 di 20» con gli ordini, poi «CHIUSA - risultato bloccato ... - nessuna
esposizione residua su questa partita». Stessa scritta nella card di Mike in Control Room.
