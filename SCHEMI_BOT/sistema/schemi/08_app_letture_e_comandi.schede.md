# Sistema - Capitolo 8: l'app, da dove legge e come comanda i bot (schede)

Schema: `08_app_letture_e_comandi.html` (sorgente `08_app_letture_e_comandi.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione G (e C, A-20).

Schede dell'inventario usate: G-1 ... G-7, C-14, A-20.

Come si legge: il «guscio» e' la parte dell'app che accende i programmi e apre la finestra; lo
«schermo» e' la pagina che vedi. Lo schermo legge dal database e dai fili; comanda i bot solo
scrivendo nel database con delle funzioni apposite.

---

## Guscio dell'app

**Cosa fa**
- Serve la pagina sulla porta 47330 del computer, apre la finestra sulla «board» e passa allo
  schermo la chiave dei fili.

**Quando**
- All'apertura.

**Numeri**
- Finestra 1600 x 900.

**Esempio con le cifre**
- Apri l'app: la finestra carica `http://127.0.0.1:47330/board`.

**Cosa vedi nell'app**
- La finestra principale.

**Se qualcosa va storto**
- Se la pagina e' vecchia, il guscio la ricostruisce prima di aprirla.

**Per il tecnico**
- G-1 `desktop/main.js:25`, `desktop/main.js:903`; G-2 `desktop/preload.js:21`.

## Schermo dell'app

**Cosa fa**
- Mostra le pagine (board, Mike, Safe, Omega, tennis, Control Room) e i pulsanti.

**Quando**
- Sempre.

**Numeri**
- Riletture: Mike 15 s, Safe 15 s, Omega 15 s, scalper 4 s, bot tennis 30 s, Control Room 30 s.

**Esempio con le cifre**
- Nella pagina di Mike lo stato si rilegge ogni 15 s; nel frattempo arrivano gli aggiornamenti
  istantanei.

**Cosa vedi nell'app**
- Tutto.

**Se qualcosa va storto**
- Un filo giu': la pagina resta aggiornata dalla rilettura.

**Per il tecnico**
- G-5 `frontend/src/components/mike/useMike.ts:31`, `frontend/src/components/controlroom/useControlRoom.ts:208`.

## Funzioni di comando

**Cosa fa**
- Funzioni del database chiamate dai pulsanti: accendi, ferma, cambia parametri, chiedi
  un'azione, arma un bot tennis.

**Quando**
- Al clic.

**Numeri**
- Esempi: accendi Mike, accendi Safe, accendi Omega, accendi scalper, arma bot tennis.

**Esempio con le cifre**
- «Accendi Mike in prova»: la funzione scrive il comando nella tabella di Mike.

**Cosa vedi nell'app**
- Il pulsante cambia stato.

**Se qualcosa va storto**
- Errore del database: messaggio nella pagina.

**Per il tecnico**
- G-3 `frontend/src/lib/mike.ts:2228`, `frontend/src/lib/safeBot.ts:1147`, `frontend/src/lib/omega.ts:1311`,
  `frontend/src/lib/scalper.ts:145`, `frontend/src/lib/tennis.ts:876`.

## Letture di stato

**Cosa fa**
- Funzioni del database che restituiscono lo stato completo di un bot, piu' gli aggiornamenti
  istantanei delle tabelle.

**Quando**
- Ogni 15 s (pagine dei bot) e a ogni cambiamento.

**Numeri**
- Mike ascolta 5 tabelle in diretta (comandi, eventi, operazioni, attivita', richieste).

**Esempio con le cifre**
- Mike chiude un'operazione: la riga cambia nel database e la pagina la riceve subito.

**Cosa vedi nell'app**
- Le schede delle partite, la testata.

**Se qualcosa va storto**
- Rilettura ogni 15 s.

**Per il tecnico**
- G-4 `frontend/src/lib/mike.ts:2248`, `frontend/src/lib/mike.ts:2345`, `frontend/src/lib/safeBot.ts:1177`.

## Fili 47331-47338

**Cosa fa**
- Notizie in diretta dai programmi; dallo schermo verso i bot passa solo la sveglia (e gli ordini
  verso i runner, capitolo 7).

**Quando**
- In diretta.

**Numeri**
- 8 fili (capitolo 4a).

**Esempio con le cifre**
- Premi «ferma Safe»: la funzione scrive il comando e lo schermo sveglia Safe sul 47335.

**Cosa vedi nell'app**
- Aggiornamenti istantanei.

**Se qualcosa va storto**
- Senza sveglia il bot vede il comando al suo giro.

**Per il tecnico**
- C-14; G-6 `frontend/src/lib/localChannel.ts:338`.

## Tabelle di comando

**Cosa fa**
- Una tabella per bot con lo stato voluto dall'utente (acceso, fermo, prova o vero, parametri).

**Quando**
- Scritta al clic; letta dai bot a ogni giro.

**Numeri**
- Mike 58 letture al minuto, Safe 36, scalper 18, ponte 18 (capitolo 5).

**Esempio con le cifre**
- Mike rilegge la sua tabella ogni secondo: un clic e' visto entro 1 s anche senza sveglia.

**Cosa vedi nell'app**
- Lo stato del bot.

**Se qualcosa va storto**
- -

**Per il tecnico**
- G-7 `mike_control`, `safe_strategy_control`, `omega_control`, `scalper_control`,
  `tennis_bot_control`.

## Mike

**Cosa fa**
- Rilegge la sua tabella di comando.

**Quando**
- Ogni 1 s (5 s a vuoto).

**Numeri**
- 58 letture al minuto.

**Esempio con le cifre**
- Clic alle 18:00:00.0, Mike lo vede entro le 18:00:01.

**Cosa vedi nell'app**
- Pagina di Mike.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `Betfair/mike/service.py:3953`; A-20.

## Bot Safe

**Cosa fa**
- Rilegge la sua tabella di comando.

**Quando**
- Ogni 2 s (due volte per giro).

**Numeri**
- 36 letture al minuto.

**Esempio con le cifre**
- Clic alle 18:00:00, Safe lo vede entro le 18:00:02.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `Betfair/safe_strategy/bot_service.py:9864`, `Betfair/safe_strategy/bot_service.py:10581`.

## Omega

**Cosa fa**
- Rilegge la sua tabella di comando.

**Quando**
- Ogni 20 s; a bot fermo ogni 60 s.

**Numeri**
- 1 lettura nel minuto misurato (fermo).

**Esempio con le cifre**
- Senza sveglia, un clic puo' aspettare fino a 60 s a bot fermo.

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `Betfair/omega/omega_service.py:7809`; A-20.

## Scalper calcio

**Cosa fa**
- Rilegge le sue due tabelle di comando.

**Quando**
- Ogni 3 s.

**Numeri**
- 36 letture al minuto.

**Esempio con le cifre**
- Clic «arma» alle 18:00:00, sessione accesa entro le 18:00:03.

**Cosa vedi nell'app**
- Pannello scalper.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `Betfair/stream/scalper/scalper_service.py:75`.

## Ponte tennis

**Cosa fa**
- Rilegge i comandi dei bot tennis.

**Quando**
- Ogni 15 s, o subito con la sveglia.

**Numeri**
- 18 letture al minuto.

**Esempio con le cifre**
- Arma un bot tennis: senza sveglia fino a 15 s di attesa.

**Cosa vedi nell'app**
- Pannello bot tennis.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `Betfair/stream/tennis_live/tennis_bot_service.py:170`.

## Frecce

- Guscio -> schermo: pagina e chiave, all'apertura.
- Schermo -> funzioni di comando: al clic di un pulsante.
- Letture di stato -> schermo: ogni 15 s e in diretta.
- Fili -> schermo: notizie in diretta.
- Funzioni di comando -> tabelle di comando: scrive.
- Tabelle di comando -> Mike, Safe, Omega, scalper, ponte: ognuno rilegge al suo ritmo (scritto
  nel riquadro del bot).

## Punti da decidere

1. Lo schermo non parla col guscio per nulla di operativo: tutto passa dal database o dai fili.

## Punti non chiariti

1. Non misurato quante chiamate al database fa lo schermo: il navigatore non scrive registri.
