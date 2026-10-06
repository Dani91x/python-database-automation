# SEGUI LIVE FERMO E ALLARMI «CAMBIO_GBP_EUR» (06/10/2026)

Sessione cloud, ramo `feature/segui-live-fix` da `master` `2fa58a4`. Segnalazioni
dell'utente: (1) home piena di «WARN/CRITICAL CAMBIO_GBP_EUR ... '_TradingFinto' object
has no attribute 'account'»; (2) in Segui Live il clic su una partita resta su
«Richiesta registrata / Aggancio stream (runner) / Primo dato ladder»; (3) quali
partite entrano nella pagina. Nessun ordine, nessun accesso al DB, app non avviata.

## 0. IN EVIDENZA — cio' che NON ho potuto verificare

1. **La causa sul PC e' dedotta**, non osservata (niente DB, niente log del runner).
   Il testo citato dall'utente e' quello del passo 3 (nel passo 2 la scheda aggiunge
   la frase sull'esposizione aperta): follow STREAMING senza ladder, che e'
   esattamente una partita dell'auto-follow (silenziosa per progetto).
2. **L'aggancio a caldo delle partite manuali non e' esercitato su Betfair vero**:
   usa la stessa risottoscrizione dell'auto-follow (in produzione dal 25/09), provata
   qui con l'auto-follow vero e un sottoscrittore finto con la firma vera.
3. **Due migrazioni da applicare** (le applica l'utente):
   `migrations/segui_live_apri_partita_2026-10-06.sql` (senza, il clic su una partita
   dei bot dice «Non riesco ad aprire la partita ... serve la migrazione») e
   `migrations/ack_allarmi_replay_cambio_2026-10-06.sql` (toglie dalla home gli
   allarmi gia' scritti dai replay).
4. **Frontend**: dopo il pull serve `npm run build` sul PC (`dist` non e' nel repo).
5. File fuori dal dominio della modalita' media under: `runner.py`, `db.py`,
   `auto_follow.py`, `SeguiLive.tsx`, `live.ts`. Da rivedere dal coordinatore.

## 1. Allarmi CAMBIO_GBP_EUR nella home

**Causa**: li scrivevano i REPLAY dello Scalper lanciati sul PC, non il bot vero.
- La sessione chiama `valuta.CAMBIO.avvia(trading)` (`scalper_session.py:1708`): nel
  replay `trading` e' il Betfair finto (`_TradingFinto`, senza `account`), la lettura
  del cambio falliva e `valuta._alert_db` scriveva l'allarme.
- Il banco vietava `db_client.get_supabase_client`, ma `Betfair/stream/db.py` ha
  importato il NOME (`from db_client import get_supabase_client`) e teneva il client
  vero: sul PC (credenziali presenti) ogni funzione non bloccata a mano di
  `Betfair.stream.db` scriveva nel DB vero durante un replay. In cloud no (senza
  credenziali il client non nasce), per questo i miei referti non lo mostravano.

**Correzione** (`replay_registrazioni._iniezioni`): il processo usa il cambio FISSO del
banco (`valuta.cambio_banco()`, lo stesso con cui il banco converte gia' le quote);
ogni modulo che ha copiato il nome `get_supabase_client` riceve il divieto per la
durata del replay (chi lo copia durante il replay ritrova il client vero dopo).
**Effetto sui referti: nessuno** (rilanciati `C` e `media-under-riavvio`: identici al
giro 4; avvisi del cambio nei log da 6 a 0).

## 2. Segui Live fermo su «Aggancio stream»

Cause trovate nel codice:
1. **Partite dei bot**: le righe `origine='auto'` (l'auto-follow del runner) compaiono
   nella lista, STREAMING, ma sono silenziose (niente `live_now`). Il runner prevede
   «un clic dell'utente la porta a PENDING e torna un follow manuale»
   (`_nuovi_follow_manuali`), ma il clic nella pagina faceva solo `setSelected`.
2. **Ricostruzione rinviata**: ogni partita manuale nuova chiedeva il restart della
   subscription, rinviato finche' il runner non e' flat; con i bot al lavoro non
   arrivava mai (passo 2 per sempre).
3. **Status riportato a PENDING**: il giro della watchlist (120 s) riscriveva PENDING
   su una partita gia' STREAMING che il runner non riaggancia piu'.
4. **Tetto gonfiato**: il tetto contava anche i mercati delle partite FINITE (mai tolti
   da `market_to_event`): in un processo lungo REFUSE e PENDING per sempre.
5. La spia del runner citata dal testo stava solo nel terminale, assente proprio
   durante l'aggancio.

Correzioni:
- `runner._aggancio_a_caldo`: con l'auto-follow agganciato la partita manuale si
  cataloga e entra nel piano (`imposta_manuali`) e nella sottoscrizione A CALDO,
  senza ricostruzione e senza attesa del flat; il catalogo di una partita senza
  mercati si ritenta al piu' ogni 60 s. Senza auto-follow: la strada di sempre.
- `auto_follow.AutoFollow.agganciato()` / `sveglia()` (due metodi pubblici).
- `_catalog_events`: il tetto conta i manuali che si sottoscrivono
  (`mercati_manuali_da_sottoscrivere`), non quelli delle partite finite.
- `db.register_follow`: una riga STREAMING manuale resta STREAMING; una riga dell'
  auto-follow chiesta dalla watchlist diventa manuale (`origine='manuale'`).
- RPC `segui_live_apri_partita` + `SeguiLive.tsx`: aprire una partita dei bot la
  promuove a follow manuale; la scheda di aggancio mostra la spia del runner (e lo
  dice se e' fermo) e l'esito dell'apertura.

## 3. Quali partite entrano in Segui Live

RPC `get_live_follows` (`migrations/live_follow_origine_2026-09-25.sql`), solo calcio:
- le partite della **watchlist con «Segui live»** (`follow_live = true`) con calcio
  d'inizio da 12 ore fa in poi, **senza limite in avanti** (non «entro 1 ora»);
- le partite **seguite dal runner senza watchlist**: quelle dei bot
  (`origine='auto'`, badge «auto»), quelle aperte da Omega «Trading», ecc., con data
  da 12 ore fa in poi;
- comprese le CLOSED/ERROR delle ultime 12 ore; esclusa solo UPLOADED.

## 4. Test e falsificazione

- `Betfair/stream/tests/test_replay_scalper_db_isolato_2026_10_06.py` (4): il difetto
  esiste fuori dal banco; nel replay cambio fisso e nessun allarme; DB vero vietato
  anche a chi ha copiato il nome; chi lo copia durante il replay ritrova il client.
  Falsificazione: 3 mutazioni, 3 rosse.
- `Betfair/stream/tests/test_segui_live_aggancio_a_caldo_2026_10_06.py` (8): aggancio a
  caldo con ordini vivi; senza auto-follow la ricostruzione di sempre; catalogo non
  ritentato a ogni giro; tetto senza le finite e con le vive; `register_follow` nei tre
  casi. Falsificazione: 7 mutazioni (K1-K7), 7 rosse.
- `frontend/src/pages/SeguiLive.apertura.test.tsx` (8) e `SeguiLive.clicAuto.test.tsx`
  (2, la pagina vera): falsificazione 3 mutazioni, 3 rosse.
- Suite Python `python -m pytest Betfair/ -q -p no:cacheprovider`: **10195 verdi, 5
  rossi** (i tempi di Safe, rossi uguali su master in questo ambiente). Frontend
  `npx vitest run`: 4981 verdi, 0 rossi; `npx tsc -p tsconfig.app.json --noEmit`: 0
  errori; `npm run build`: ok.
- Replay: `C` (base, paper sulla 35760084) e `media-under-riavvio` identici al giro 4.

## 5. Non fatto (consigli per la velocita' della pagina)

Dall'analisi: il terminale si ridisegna ogni secondo (`setNowTick`), la lista dei
follow si rilegge ogni 15 s, `live_now` arriva dal runner ogni 5 s (sul desktop il
canale locale e' piu' veloce). Non li ho toccati: sono scelte di altre sessioni e non
sono la causa del blocco.
