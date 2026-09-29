# CANTIERE MIKE-APP - Pacchetto P6, blocco 3: le cifre della proposta vive (M7.1), 29/09/2026

Patch: `AUDIT_2026-09-29/MIKE_P6_3.patch`, sopra P6_1 e P6_2 (verificato su master `83c999b`
+ P6_1 + P6_2: `git apply --cached --check` pulito). Solo frontend.

## 1. Misura del ritardo di OGGI (letta dal codice, non cronometrata dal vivo)

La cifra «chiudendo ora» e' `live.cashout.net`, calcolata dal bot a ogni giro
(`Betfair/mike/service.py`, `cashout_live` circa riga 4593) a partire dai prezzi dello scanner.

| Tratto | Pagina di Mike | Card di Mike in Control Room |
|---|---|---|
| Bot: ricalcolo della cifra | a ogni giro (~1 s in gioco; `decide_min_interval_ms` 500) | idem |
| Canale al ms 47333 (`_persist` -> `_pubblica_evento`, a ogni giro) | GIA' ascoltato (`useMike`, lotti ogni 250 ms) | **NON ascoltato** (la Control Room ascolta di Mike solo `mike_stato`) |
| Database: `cashout` e' fra i campi VOLATILI (`_LIVE_VOLATILI`) | riscritto solo ogni `publish_heartbeat_s` = 5 s | idem |
| Lettura del database | realtime + attesa di raggruppamento 1,5 s + RPC; comunque ogni 15 s | ogni **30 s** (`RICARICA_MS`), piu' riletture mirate solo quando cambia una riga `mike_trades` |
| **Ritardo totale fra dato del bot e cifra a video** | ~0,3-1,3 s col canale; senza canale 1,5-6,5 s (fino a 20 s se manca il realtime) | **fino a ~35 s** (5 s di scrittura + 30 s di lettura) |

La proposta stessa (`ctx.uscita_proposta`) viaggia SOLO dal database: il bot non spinge `ctx`
sul canale (`_FUORI_DAL_PUSH`). Si scrive subito (e' un fatto), quindi compare dopo il realtime
(pagina) o alla rilettura dei 30 s (Control Room).

## 2. Cosa e' cambiato
| File | Cosa |
|---|---|
| `frontend/src/components/mike/useMikeEventoAlMs.ts` (NUOVO) | hook: si iscrive al topic `mike_event` del canale GIA' esistente (`getLocalChannel('mike')`, nessun canale nuovo), tiene l'ultimo push della STESSA partita e lo fonde con la riga del database con la regola della pagina (`fondiEventiLocali`). Il push vince solo se piu' recente (`live.published_ts`); canale caduto = push buttato, si torna al database |
| `frontend/src/components/controlroom/PropostaUscitaMike.tsx` | usa l'hook (attivo solo con una proposta viva): cifre, badge del feed, prezzi di ripiego e bottone leggono la scheda piu' fresca. Accanto a «chiudendo ora» l'eta': «(aggiornata 1 s fa)»; oltre `CIFRA_VECCHIA_S` = 5 s la cifra e' barrata in ambra con «(VECCHIA: aggiornata N s fa)»; eta' ignota = «(VECCHIA: eta' del dato sconosciuta)» |
| `frontend/src/components/controlroom/EsitoChiusuraMike.tsx` | usa lo stesso hook: stato, gambe e `live` al ms, `ctx` dal database |

Regola del bottone «approva uscita» INVARIATA (spento con feed fermo o ignoto; nessun controllo
sull'importo: M7.3). Cambia solo la FONTE: ora e' la scheda piu' fresca, quindi in Control Room
il bottone non resta spento per un dato vecchio di 30 s quando il bot e' vivo sul canale.

Nella pagina di Mike il risultato e' identico a prima (la pagina fondeva gia' il canale): cambia
solo l'eta' scritta accanto alla cifra. In Control Room il ritardo passa da ~35 s a ~1 s quando
l'app desktop e' collegata al canale.

## 3. Test nuovi (`useMikeEventoAlMs.test.tsx`, 6 test)
Senza canale: cifra del database dichiarata VECCHIA con l'eta'; col canale: due push, cifra ed
eta' seguono, la proposta (ctx del database) resta; push di un'altra partita o piu' vecchio:
ignorato; canale che cade: si torna al database; senza proposta nessuna iscrizione; l'esito della
chiusura mostra LIVE_CLOSING spinto dal bot prima della rilettura del database.
Finto del canale con la forma di `LocalChannel`, push con la forma di `_pubblica_evento`.

## 4. Test esistenti modificati
Nessuno (i 10 di `PropostaUscitaMike.test.tsx` restano verdi senza ritocchi).

## 5. Numeri
- `npx vitest run src/pages/Mike src/pages/ControlRoom src/components/mike src/lib/mike src/components/controlroom`
  -> **66 file, 1068 verdi, 1 saltato (preesistente)**.
- `tsc` 0 errori.

## 6. Falsificazione (`falsifica_mike_p6.mjs 3`): 6 mutazioni, 6 ROSSE
F1 la proposta non ascolta il canale (2 rossi); F2 push di un'altra partita accettato; F3 push
piu' vecchio vince; F4 caduta del canale ignorata; F5 cifra mai vecchia; F6 esito senza canale.

## 7. Non verificato
- Il ritardo e' MISURATO SUL CODICE, non cronometrato: niente app, niente bot accesi.
- Carico: in Control Room ogni card di Mike visibile si iscrive al canale (un push per partita per
  giro, filtrato per partita: ridisegna solo il riquadro della proposta/esito). Non misurato con
  30 partite.

## 8. Campi dal bot
Nessuno indispensabile. Se si volesse la proposta al ms anche nel suo contenuto, il bot dovrebbe
spingere `ctx.uscita_proposta` nel push (oggi `ctx` e' escluso).

## 9. Da controllare in paper
Con una proposta di uscita in perdita a video: «chiudendo ora X (aggiornata 0-1 s fa)» che
cambia a ogni secondo, sia nella pagina di Mike sia in Control Room. Chiudendo l'app desktop
(canale spento) la cifra diventa «VECCHIA».
