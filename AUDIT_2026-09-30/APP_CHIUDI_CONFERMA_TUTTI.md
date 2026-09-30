# Chiudi con conferma in live per TUTTI i bot (decisione dell'utente, 30/09 16:20)

Codice: `frontend/src/components/controlroom/BottoneChiudiRiga.tsx`: tolto `BOT_CON_CONFERMA_LIVE`; `chiedeConferma = riga.modalita !== 'paper'` (live e modalita' ignota chiedono la conferma, paper un clic). Testo e stima invariati.

Test aggiornati (decisione dell'utente 30/09, non piegati):
1. `BottoneChiudiMikeConferma.test.tsx`: «Omega live chiude ancora al primo clic» sostituito da: per omega/tennis_scalper/tennis_pro/safe in LIVE primo clic arma, annulla non manda, conferma manda la STESSA richiesta; omega/tennis_flb in PAPER un clic.
2. `BottoneChiudiRiga.test.tsx` «riga omega (live)»: dopo il primo clic verifica nessuna richiesta, poi clic su Conferma, stessa richiesta.
3. `pages/ControlRoom.test.tsx` «il comando Chiudi chiama vm.chiudi con la RIGA» (Safe live): primo clic non manda, conferma manda lo stesso payload.
I test tennis D3 sono in paper: invariati.

Falsificazione: mutazione «solo mike» -> 6 rossi (3 file). Ripristinato, diff identico (hash uguale al patch). tsc 0 errori; vitest controlroom + ControlRoom.test.tsx: 53 file, 828 test verdi.
