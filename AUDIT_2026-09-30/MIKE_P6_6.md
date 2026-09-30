# CANTIERE MIKE-APP - Pacchetto P6, blocco 6: etichette della copertura nuova (da integrare INSIEME a P5), 29/09/2026

Patch: `AUDIT_2026-09-29/MIKE_P6_6.patch`. `--check` pulito su master `08b9c6a` (che contiene gia'
P6 blocchi 1-3 e 5 e P5 blocco 1), sia senza sia con P6_4 (i file condivisi hanno pezzi lontani).
**Da integrare col pacchetto P5 che aggiunge `cover_form` a `config.py`**: senza, il contratto
Python dei parametri e' ROSSO (`solo_ui: cover_form`). Verificato: col `config.py` di master +
la sola riga `cover_form = ("lay_under45", str, None, None, ("lay_under45", "back_over45"))` del
progetto P5 (in memoria) il contratto e' 5/5 verde.

## 1. Cosa e' cambiato
| Dove | Cosa |
|---|---|
| `lib/mike.ts` nuova `roleLabelGamba({role, side, selection})` | il nome della gamba da LATO e SELEZIONE: `over_cover` banca Under = «Copertura: banca Under 4.5»; punta Over = «Copertura: punta Over 4.5»; `over_close` banca Over = «Chiusura Over 4.5» (tutte e due le forme, come oggi); `over_close` punta Under (ripiego sotto 0,50, M3.3) = «Chiusura copertura: punta Under 4.5». Lato o selezione ignoti = nome del ruolo, mai una forma indovinata. Accetta anche i nomi Betfair («Under 4.5 Goals») |
| `MIKE_ROLE_LABEL.over_cover` | «Copertura Over 4.5» -> «Copertura linea 4.5» (il ruolo da solo non dice la forma) |
| usato in | ordini sul book della card (`MikeMatchCard`), tabella Operazioni (`MikeEventPnlTable`, da `side` + `selection_name`), ordini della proposta (`PropostaUscitaMike`), ordini dell'esito della chiusura (`mikeEsitoChiusura`), righe di attivita' con `role` (`mikeActivityLine`) e proposte nell'attivita' |
| `investedOf` | capitale impegnato = puntate + RISCHIO delle banche di apertura (importo x (quota - 1)): 10 + 12,63 x 0,18 = 12,27. Identico a `engine.invested` di master (`e023a0d`). Forma vecchia invariata (12,26) |
| `positionRows` | se un mercato ha gambe sulle DUE selezioni (banca Under 4,5 di copertura + banca Over 4,5 di chiusura) si fa UNA riga per mercato, pari con lo scarto del motore (0,01, conti senza arrotondare): dopo la chiusura non compaiono due posizioni finte. Mercato con una selezione sola: identico a prima |
| parametro `cover_form` (NUOVO) | «Forma della copertura», scelte `lay_under45` (di serie) / `back_over45` (forma vecchia), gruppo copertura; `MIKE_PARAM_DEFAULTS.cover_form = 'lay_under45'`; `MIKE_COVER_FORM_LABEL` |
| testi | gruppo «Copertura (linea 4.5)»; fasi LIVE_UNCOVERED / LIVE_COVER_PENDING / LIVE_COVERED senza «Over 4.5»; `cover_place_at_ticks` «Copertura: cuscinetto di N tick» (banca: N tick SOPRA il miglior lay, M3.2; punta: sotto); `cashout_base` e `cashout_profit_pct` (rischio della banca); attivita' `cover` con la forma dal payload (`side`/`selection`, poi `cover_form`, poi generica) e l'etichetta «COPERTURA LINEA 4.5»; `MikeParamsSheet` note dei gruppi; `MikeCashOutButton` testo del dialogo; `pages/Mike.tsx` nota dei Risultati Live; `DayDetail` «COPERTURA 4.5», `PerformancePanel` «Copertura linea 4.5», `dailyHistory` motivo d'uscita «copertura sulla linea 4.5», `DettaglioRigaView` «copertura linea 4.5» (mappe per ruolo usate solo da Mike) |

Rimasto com'e' (e' il MERCATO, non la copertura): le quote «Over 4.5 back / lay» e «P(Over 4.5)
modello» della card e della scheda in Control Room, «Under 3.5 / Over 4.5» nel titolo del bot.

## 2. Test
- Nuovo `src/components/mike/MikeP6Blocco6Copertura.test.tsx`, 8 test con gambe delle DUE forme
  (numeri del progetto P5: 10 a 1,50; punta Over 2,26 a 6,60; banca Under 12,63 a 1,18; chiusura
  banca Over 0,71 a 21): nomi, capitale 12,26 / 12,27, posizioni per mercato (pari = nessuna riga
  4.5; senza chiusura = una riga «Under 4.5 LAY» a 1,18; forma vecchia invariata), esito della
  chiusura, tabella, attivita' `cover`, parametro, fasi.
- Test esistenti modificati: nessuno (il test di `PropostaUscitaMike` resta identico: «Chiusura
  Over 4.5 lay ...»).
- `npx vitest run src/lib src/components/controlroom src/components/trading src/components/mike
  src/pages/Mike src/pages/ControlRoom` -> **201 file, 3444 verdi, 1 saltato (preesistente)**;
  `tsc` 0 errori.
- Falsificazione (`falsifica_mike_p6.mjs 6`): 8 su 8 ROSSE (K1 forma dedotta dal ruolo; K2 banca
  contata per importo; K3 posizioni per selezione; K4 pari sugli arrotondati; K5 tabella col solo
  ruolo; K6 attivita' senza forma; K7 serie sulla forma vecchia; K8 fase con «Over 4.5»).

## 3. Da decidere / non verificato
- `cover_good_price` («Copri subito se Over 4.5 >=»): non so se il motore di P5, in forma banca,
  confronta la quota Over (equivalente) o la quota lay Under. Etichetta lasciata com'e': va
  allineata a cio' che fa `engine._decide_uncovered` nella forma nuova.
- Il payload dell'attivita' `cover` del motore di P5 (lato/selezione o `cover_form`): non letto
  (P5 non e' su master); il testo regge tutti e tre i casi.
- Dal vivo nulla.
