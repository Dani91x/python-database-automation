# Istruzioni di progetto — python-database-automation (Betfair bot)

Comunicare in italiano. Codice ASCII-only, commenti in italiano.

## Lo standard per OGNI bot, presente e futuro (ordine dell'utente, 16/09/2026)

Leggi `PROCESSO_STANDARD_BOT.md` prima di toccare un bot. I cinque gradini, nessuno
saltabile: **progetto → mappa di ogni condizione e della consapevolezza degli ordini →
replay flumine sulle registrazioni reali con il codice di produzione, in tutti gli
scenari → paper come specchio della realtà → live solo se il paper conferma.**

- Quando l'utente nomina «paper», «live», «attivare» o un bot nuovo: **prima chiedi se
  è certificato sul replay** e, se non lo è, dillo. È un promemoria dovuto.
- La certificazione passa **solo** dal punto d'ingresso unico del banco comune
  (`python -m Betfair.stream.backtest.certifica <bot> ...`, vedi
  `Betfair/stream/backtest/`): nessun replay «a parte», nessuna classe di laboratorio
  al posto di quella di produzione, nessun fill o snapshot scritto a mano.
- Un bot nuovo si **registra** nel registro del banco con il suo servizio di produzione e
  i suoi controlli di condotta; il test di contratto rifiuta un bot in produzione senza
  registrazione.
- Le strategie **non si alterano** mai di iniziativa (soglie, stake, tetti, gambe).
  L'unica differenza ammessa è paper o live. Le divergenze si scrivono e si portano
  all'utente.
- Paper e live non si sommano mai; calcio e tennis non si mischiano; i bot li accende
  solo l'utente dalla UI (all'avvio dell'app nessun bot opera: `Betfair/stream/avvio_app.py`).
- I finti nei test hanno le identiche chiavi e tipi del vero. Un test che non sa
  diventare rosso non certifica: ogni test nuovo va falsificato.
- Chi certifica rilegge il diff, rilancia test e replay di persona.
- **Copertura obbligatoria del banco** (`PROCESSO_STANDARD_BOT.md` §6: dati di mercato,
  scanner vero, servizio intero a cadenza reale, ciclo di vita dell'ordine con parziali e
  bet delay, persistenza e UI, concorrenza, scenari, falsificazione, referto riproducibile)
  e **catalogo dei 35 errori già visti** (§7): sono i criteri di accettazione di ogni
  lavoro sui bot e vanno copiati, per riferimento, in ogni brief a un delegato.
- Definizione di fatto per un bot: §7 in coda (controlli sollecitati o ⊘ con causa,
  falsificazione rossa sui difetti applicabili, parità paper/live, stati e fasi elencati,
  firma di chi ha rieseguito il replay).

## Cronostoria e metodo di sessione (ordine dell'utente, 17/09/2026, standard di default)

- **`CRONOSTORIA.md`** (radice) è il punto d'ingresso unico: una sezione per giornata con stato
  di partenza verificato, task certificate, checkpoint, reperti aperti, decisioni e **punto
  esatto di ripresa**. All'avvio di ogni sessione si legge l'ULTIMA sezione, si verifica di
  persona lo stato (git, DB in sola lettura, suite, app) e si riparte da lì: mai da zero, mai
  rifacendo lavoro già certificato. A ogni task certificata si aggiunge il checkpoint; a fine
  sessione si chiude la sezione con «punto di ripresa» e «prossimi passi».
- **Coordinatore + delegati**: la sessione principale coordina e REVISIONA; ogni task va a un
  agente (Opus 5 per costruzione complessa, Sonnet 5 per revisioni, fix piccoli, audit). Il
  coordinatore non si fida del referto: rilegge il diff, rilancia test e replay, falsifica in
  entrambe le direzioni. Regola completa: `~/.claude/rules/sessione-coordinatore-cronostoria.md`.

## Vincoli operativi

- Mai `git add -A` (c'è un log da 3 GB). `git fetch` prima di ogni push: lavorano più
  sessioni sullo stesso repo.
- L'app desktop la avvia e la riavvia l'utente; l'exe è un avviatore del `main.js` vivo:
  mai ricompilarlo, mai chiudere l'app. Dopo modifiche a `frontend/src`: `npm run build`.
- Nessun processo, registratore o runner nuovo senza permesso esplicito.
- Mai uccidere backtest o replay lunghi senza chiedere.
- Le migrazioni SQL si scrivono in `migrations/` e le applica l'utente.
- Test: `python -m pytest Betfair/ -q -p no:cacheprovider`; `frontend/`: `npx vitest run`,
  `npx tsc -p tsconfig.app.json --noEmit` (**0 errori** dal 17/09: non regredire, mai `@ts-ignore`/`any` per zittire).

## Documenti di riferimento

`PROCESSO_STANDARD_BOT.md` · `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` ·
`HANDOFF_CONTROL_ROOM.md` · `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md` ·
`Betfair/mike/COSTITUZIONE_MIKE.md` · `SPEC_STRATEGIA_S.md` · `ESECUZIONE_LIVE.md`.
