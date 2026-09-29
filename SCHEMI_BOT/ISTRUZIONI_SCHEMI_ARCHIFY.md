# Come si costruisce uno schema di un bot con archify (istruzioni per chi disegna)

Leggi PRIMA `SCHEMI_BOT/REGOLE_DI_CHIAREZZA.md`: valgono per ogni parola che scrivi.

## Lo strumento
- La skill sta in `C:\Users\Admin\.claude\skills\archify`. Leggi `SKILL.md`, poi lo schema JSON del
  tipo che usi (`schemas/<tipo>.schema.json`, `schemas/common.schema.json`), UN esempio dello stesso
  tipo in `examples/` e il `README.md` in `renderers/<tipo>/`.
- Comandi (da lanciare con la cartella della skill come cartella di lavoro):
  `node bin/archify.mjs validate <tipo> <file.json> --quality showcase --json`
  `node bin/archify.mjs deliver <tipo> <file.json> <file.html> --quality showcase --json`
- NON lanciare `scripts/check-update.mjs`, `preview`, `--open`: niente rete, niente finestre.
- Un comando che esce con errore non e' un successo. Se dopo due giri di correzione il numero di
  errori non scende, fermati e scrivi quali diagnostici restano.

## Cose gia' imparate (non riscoprirle)
- `lifecycle`: la corsia `main` e' OBBLIGATORIA (fascia in alto, colonne 0-4); la corsia `terminal`
  e' la fascia in basso (colonne 0-2); ogni altra corsia finisce nella fascia di mezzo (colonne 0-2).
  La colonna N delle fasce basse sta sotto la colonna N+2 della fascia alta. Il binario fra gli
  stati della corsia `main` e' disegnato da solo: NON mettere transizioni fra stati di `main`.
  Le frecce buone sono le discese verticali (`route: "straight"`, `fromSide: "bottom"`,
  `toSide: "top"`). Niente diagonali, niente incroci. E' una mappa delle fasi, non un grafo fitto.
- `workflow`: usa `schema_version: 2`, colonne logiche 0-5, `mainPath` con il percorso principale,
  niente `meta.viewBox`. Adatto ai controlli in sequenza con deviazioni (si'/no).
- `meta.views[].note`: al massimo 140 caratteri. `meta.quality_profile`: `"showcase"`.
- Non mettere `meta.locale` (l'italiano non e' fra le lingue dell'interfaccia: i pulsanti del
  visualizzatore restano in inglese, il contenuto e' in italiano). Non mettere `meta.subtitle`,
  `meta.visual_preset`, `meta.animation`.
- Al massimo 12 riquadri. Etichette corte: titolo 2-3 parole, sottotitolo 3-5 parole. Il dettaglio
  NON va nello schema: va nelle schede.
- Scrivi SUBITO il primo candidato e validalo: non progettare le coordinate a parole.

## Cosa si consegna per OGNI schema (cartella `SCHEMI_BOT/<bot>/schemi/`)
1. `NN_nome.<tipo>.json` - la specifica archify.
2. `NN_nome.html` - prodotto da `deliver` (non modificarlo a mano).
3. `NN_nome.schede.md` - le schede in parole semplici, UNA PER RIQUADRO dello schema, nell'ordine
   dello schema, col formato fisso della regola 14 di `REGOLE_DI_CHIAREZZA.md`:
   **Cosa fa** / **Quando** / **Numeri** / **Esempio con le cifre** / **Cosa vedi nell'app** /
   **Se qualcosa va storto** / **Per il tecnico** (file:riga e nomi interni).
   Dopo le schede dei riquadri, una sezione «Frecce» con una riga per ogni passaggio
   (`da -> a: condizione esatta con i numeri`), e una sezione «Punti da decidere» con le differenze
   dalla Costituzione e le cose strane che riguardano QUESTO schema.
   TUTTE le logiche dell'inventario che appartengono al capitolo devono comparire in una scheda:
   in testa al file elenca i numeri delle schede dell'inventario che hai usato.

## Fonti e divieti
- La fonte dei fatti e' l'inventario verificato in `SCHEMI_BOT/<bot>/inventario/`. Se un fatto ti
  sembra dubbio o manca, leggi il codice e scrivi cosa hai trovato; non inventare numeri.
- SOLA LETTURA sul codice del repo. Scrivi SOLO i tuoi file in `SCHEMI_BOT/<bot>/schemi/`.
- Niente test, replay, script del repo, `.bat`, comandi git che scrivono, commit, database.
