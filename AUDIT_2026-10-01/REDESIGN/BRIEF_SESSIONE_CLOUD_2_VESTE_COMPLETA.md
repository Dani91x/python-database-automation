# Brief 2 per la sessione cloud — Veste COMPLETA del redesign «guscio v2», fedele al prototipo

Sei l'esecutore (sessione cloud) del coordinatore admin-01 sul repo `Dani91x/python-database-automation`,
ramo di partenza `master` al commit `d488490` o successivo. Lingua: italiano in tutto. Stesso contesto del primo
brief (`BRIEF_SESSIONE_CLOUD.md`, nella stessa cartella): leggilo per intero, insieme a `REFERTO_CLOUD.md`
(il tuo referto della prima sessione), `PIANO_INTEGRAZIONE.md`, `INVENTARIO_FUNZIONALITA.md` +
`inventario_parti/*.md` e il prototipo in `prototipo/` (index.html + js/*.js).

## Cosa è già fatto (su master, verificato e fuso dal coordinatore)
La prima sessione ha consegnato la CORNICE: interruttore `ui.shell` (spento di default), `AppShell`, sidebar,
testata globale, test «fotografia» (`frontend/src/fotografia/`), tabella del Programma del giorno, contenitori
della Control Room. Tutto verificato: 314 file / 4829 test verdi, parità con interruttore spento provata.

## Cosa manca, ed è il mandato di questa sessione
L'utente ha visto l'app col guscio acceso e ha detto: «il design mi sembra quello attuale». Ha ragione: le fasi
4-7 della prima sessione hanno cambiato solo i contenitori esterni (62 righe in tutto). L'INTERNO delle pagine
(schede, tabelle, KPI, pannelli, chip, badge, ladder, tipografia, densità, colori semantici) è ancora quello di
oggi. Il mandato: **con il guscio acceso, ogni schermata deve somigliare al prototipo, componente per
componente**, non solo starci dentro. Criterio di accettazione: affiancando lo screenshot della pagina col guscio
acceso e la schermata corrispondente del prototipo, un trader deve riconoscere lo stesso design (gerarchia, densità,
tessere, tabelle, chip, colori). Dove il prototipo e la produzione differiscono nei CONTENUTI (dati finti contro
dati veri), vale la produzione; dove differiscono nella VESTE, vale il prototipo.

## Regole TASSATIVE (invariate dal primo brief)
- Parità 1:1 di funzionalità: stessi testi, stessi `data-testid`, stessi comandi, stesso ordine dei blocchi, stessi
  dati, stesse chiamate. La fotografia (`fotografia.test.tsx`) è il metro: con interruttore SPENTO identica a quella
  committata; con interruttore ACCESO stesse pagine (testi/testid/comandi), solo cornice e classi diverse.
- VIETATO toccare: Python, SQL, `migrations/`, `desktop/`, hook React (`use*.ts`), `frontend/src/lib/**` (salvo
  `uiShell.ts`/`navigazione.ts` già tuoi), chiamate RPC/Supabase e canali, testi a schermo, testid, ordine dei blocchi,
  conferme a due tempi, numeri e formattazioni, `package.json`/lockfile. Nessuna RPC nuova, nessuna lettura in più.
- Bug e incongruenze trovati: SEGNALATI nel referto, non corretti (eccezioni ammesse e da elencare: PAPER di un solo
  colore, LAY `rose` unico, mojibake nei commenti se li incontri: sono sola grafica/testo di commento).
- L'interruttore resta SPENTO di default. Con `off` l'app è quella di oggi byte per byte.

## Come si fa la veste interna senza toccare le pagine nella logica
1. **Classi condizionate dal guscio.** Tutto lo stile nuovo vive sotto il selettore `[data-shell="v2"]` in
   `frontend/src/index.css` (classi `.ds-v2-*` già avviate) e, dove serve, in classi `className` aggiunte ai
   componenti. Con `off` le classi `.ds-v2-*` non hanno effetto (nessun selettore senza `[data-shell="v2"]`).
   Il test `cssGuscio.test.ts` lo verifica: tienilo verde ed estendilo.
2. **Componenti base `components/ui/*` (shadcn):** NON cambiarne l'aspetto di default (lo usano le pagine con guscio
   spento). Se serve una variante, aggiungila come classe `.ds-v2-*` applicata dal contesto, mai cambiando il default.
3. **Per ogni pagina**, nell'ordine: Programma del giorno (già in tabella: rifinisci), Control Room (tutti i blocchi:
   testata, SOLDI VERI, stop e runner, Obiettivo, tessere sport, comando dei bot, schede partita pre-match e live,
   uscite, posizioni aperte, posizioni chiuse, glossario), Omega, Safe Strategy (calcio e tennis), Mike, Segui live
   e terminal calcio (ladder «layout v2» del prototipo, toolbar, conferma ordine), Tennis dashboard, Tennis terminal
   (4 bot), Multi-ladder, Ladder pop-out, Market watch, Live P&L, Storico calcio, Storico tennis, Trade journal,
   Report personale, Watchlist, Match replay, Analytics, Cruscotto partite, Scelta sport, Accesso, Conferma email,
   Reimposta password, 404. Per ciascuna: confronta con la schermata del prototipo (`prototipo/js/s_*.js`), elenca
   nel referto i componenti ritoccati e quelli lasciati con il motivo.
4. **Tipografia e numeri:** Sora per i titoli, Inter per il testo, numeri tabulari (`font-variant-numeric:
   tabular-nums`) per ogni cifra; dimensioni e densità come nel prototipo.
5. **Colori semantici uniformi** (dal prototipo e da `index.css`): profitto/perdita, back `sky`/lay `rose` come
   l'exchange, PAPER di un solo colore ovunque, LIVE col suo colore, marchio della fonte (CONTO/BOT/PROVA/STIMA) con
   lo stesso stile in tutte le pagine. Nessun colore nuovo fuori dai token.
6. **Tessere KPI, tabelle dense, chip di stato, schede:** una classe per tipo (`.ds-v2-kpi`, `.ds-v2-tabella`,
   `.ds-v2-chip-*`, `.ds-v2-scheda`…) riusata in tutte le pagine, così la veste è coerente e il CSS resta piccolo.
7. **Sticky e scroll:** rispetta quanto scoperto nella prima sessione (testate non incollate come oggi); nessuno
   scroll orizzontale a 1280 px; verifica 1280/1600/1920.

## Verifiche a ogni pagina (non a fine lavoro)
- `npx tsc -p tsconfig.app.json --noEmit` = 0 errori.
- `npx vitest run src/fotografia` verde SENZA rigenerare le fotografie `off` (se una fotografia `off` cambia, hai
  rotto la parità: torna indietro). Le fotografie `v2`/`guscio` si rigenerano solo per cornice e classi, e il diff
  va letto e spiegato nel referto (solo classi, mai testi/testid/comandi).
- `npx vitest run` suite intera verde con lo stesso conteggio di partenza (314 file / 4829 test) + i tuoi test nuovi.
  Attenzione: la fotografia sotto carico fotografa stati di caricamento (falsi rossi): se usi Chromium o altre suite in
  parallelo, rilancia la fotografia a macchina scarica prima di concludere la pagina.
- Screenshot a 1280 e 1600 px, `off` e `v2`, per ogni pagina, in `AUDIT_2026-10-01/REDESIGN/confronto2/`, e per
  ogni pagina un'immagine affiancata «prototipo | v2» (`confronto2/<pagina>.affianco.png`): è ciò che l'utente
  guarderà per primo.
- Falsificazione dei test nuovi (comportamento vecchio → rosso → ripristino), output nel referto.

## Consegna (nessuna fusione: la fanno il coordinatore e l'utente domani mattina)
- Ramo `redesign/veste-completa` da `master` (`d488490`+). Commit per pagina, in italiano, percorsi espliciti (mai
  `git add -A`), push dopo OGNI pagina. Pull request in bozza verso `master` aperta dopo la prima pagina e aggiornata
  a ogni push, titolo «Redesign veste completa — fedele al prototipo, dietro ui.shell (spento di default)».
- Referto `AUDIT_2026-10-01/REDESIGN/REFERTO_CLOUD_2.md` (anche nel corpo della PR): per ogni pagina, componenti
  ritoccati e non, screenshot affiancati, numeri di tsc/suite/fotografia, falsificazioni, bug segnalati, «cosa non ho
  potuto verificare». Scrivi la verità: un «non fatto» dichiarato vale più di un «fatto» non provato.
- Lavora finché l'elenco delle pagine è completo. Se il credito o il tempo finiscono prima, fermati a fine pagina con
  tutto pushato e il referto aggiornato: dichiara a che pagina sei arrivato. Nessun build, nessun riavvio, nessuna
  modifica a master.
