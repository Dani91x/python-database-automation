# tennis_pro: superficie vera per partita, varianti trend/adapt/maker accese (25/09)

> **I setup su terra e cemento NON sono certificati sul banco: non esiste nessuna
> registrazione fuori dall'erba** (tutte le 128 cartelle di `tennis_rec` sono del 07/07,
> Wimbledon; `MISURA_PUNTO8_2026-09-25.md` §6). Anche le varianti `trend`, `adapt` e `maker`
> non sono mai state certificate sul banco, nemmeno sull'erba. Questo lavoro fa scegliere al
> bot il ramo giusto e accende le varianti, come ha chiesto l'utente. Se questi rami
> guadagnano lo diranno il paper e le registrazioni future.

Decisione dell'utente (25/09, h21:30): «Accendili, poi valuteremo come fare, per ora voglio
vedere i bot in azione» e «tutti i bot devono avere gli aiuti e le migliorie accese di
default». Resta valido «i bot a ogni riavvio restano spenti, li avvio io»: qui non cambia.

Voci chiuse: TN1 e TN3 di `AIUTI_SPENTI_DI_DEFAULT_2026-09-25.md`.

---

## 1. Superficie (TN1)

**Prima.**
- `surface` aveva il default `"grass"` in `tennis_pro_bot.py:116`.
- Nessun runner la passava (grep di `surface` in `tennis_live/`: 0 risultati).
- In più la scheda UI (`frontend/src/lib/tennis.ts`) mandava `surface: 'grass'` di default
  in ogni armamento.
- Risultato: il bot girava sempre come su erba.
  - Il break point comprava sempre chi serve.
  - Serving-for-set, doppio break e favorito compresso erano spenti su ogni partita
    (salvo che fossero accese le varianti).

**Adesso.**
- Modulo nuovo `Betfair/stream/tennis_scalper/superficie.py`.
  - Contiene la mappa dei tornei come DATI (`MAPPA_TORNEI`, riga 66), una voce per torneo,
    ognuna con superficie, parole chiave e fonte.
  - `risolvi(competizione)` (riga 298) decide con tre regole, nell'ordine:
    1. **nome**: il nome della competizione dichiara la superficie (`clay`, `grass`, `hard`,
       `indoor`, `terra`, `erba`, `cemento`, `carpet`). È il caso dei Challenger e degli ITF,
       per esempio «Challenger Genova (Clay)». Fonte `nome`.
    2. **mappa**: cerca le parole chiave del torneo a parola intera, sul nome normalizzato
       (minuscolo, senza accenti e senza apostrofi). Così «halle» NON scatta dentro
       «challenger». Fonte `mappa`.
    3. **default**: `'hard'` (cemento), DICHIARATO con fonte `default` e con il motivo
       («torneo sconosciuto» oppure «competizione non nota»).
  - Il testo per la UI è `Superficie.testo()`: «terra (mappa: Roland Garros)» oppure
    «cemento (default: torneo sconosciuto)».
- Runner (`Betfair/stream/tennis_live/tennis_runner.py`):
  - `_resolve_market` (:545-547) chiede anche `COMPETITION` nella STESSA
    `listMarketCatalogue` (proiezione a peso 0, nessuna chiamata in più). La meta porta
    `competition_name`.
  - `_con_competizione` (:604): se il catalogo non ha la competizione, prende quella della
    riga `tennis_live_follow.competition_name`. Il ponte la copia da
    `tennis_markets.competition_name` (`tennis_bot_service.ensure_follows_for_bots`), il
    feed unico da `competition`. Vale per i follow manuali, per quelli automatici e per i
    comandi (`_ET.meta_da_catalogo`).
  - `_instantiate_bot(..., competition_name=None)`, solo per `tennis_pro` (:770):
    - chiama `superficie_della_partita` (:827), che usa `competition_name` o, se manca, il
      `params['surface_torneo']` di un armamento precedente;
    - aggiunge ai params `surface`, `surface_fonte`, `surface_voce`, `surface_torneo`,
      `surface_testo`;
    - **vince sempre** sul `surface` già presente nei params: il vecchio `'grass'` salvato
      dalla UI non si distingue da una scelta. Se lo sovrascrive lo scrive nel log e
      nell'attività.
  - I due chiamanti (build :2617, armamento a caldo :2131) passano
    `meta.get("competition_name")`.
  - `_scrivi_superficie` (:839), chiamata dopo `running` (:2173, :2637):
    - scrive la superficie nei `params` della riga `tennis_bot_control` con la funzione
      nuova `tennis_db.set_tennis_bot_params` (`tennis_db.py:346`). Solo la colonna
      `params` già esistente, nessuna colonna nuova;
    - scrive un'attività `superficie` con testo, fonte, voce, torneo e `richiesta_ignorata`;
    - non scrive niente se la riga porta già la stessa superficie;
    - non solleva mai.
- Bot (`tennis_pro_bot.py:121-123`): legge `surface` dal contesto (la passa il runner) e
  dichiara `surface_fonte`. Il default `"grass"` della classe resta SOLO per chi istanzia a
  mano (`backtest_pro`, `run_tennis_pro`, test), e lo dichiara: «non passata: default della
  classe (erba)».
- UI:
  - Il select «Superficie» è tolto dalla scheda di tennis_pro (`tennis.ts`). La superficie la
    decide la partita, e un select che il runner ignora sarebbe una bugia.
  - Nel pannello per partita (`TennisBotPanel.tsx:235`, `data-testid="tennis-pro-superficie"`)
    compare la riga «superficie: terra (mappa: Roland Garros)», oppure «superficie: cemento
    (default: torneo sconosciuto)» in ambra.
  - Una superficie senza fonte appare in rosso come «(fonte non dichiarata)» e non viene mai
    inventata.
  - Prima dell'armamento la riga dice «la decide il runner all'armamento, dal nome del
    torneo».
  - La lettura avviene in `superficieDaParams` (`tennis.ts:690`).

**Perché.** La superficie è un dato della partita, non del bot. Con il fisso a erba tre
setup su sei non partivano mai, e sul break point il bot stava dalla parte sbagliata in ogni
partita non su erba.

### La mappa (dati)

- **Erba**, 13 voci: Wimbledon, Queen's, Halle, Eastbourne, Newport, 's-Hertogenbosch,
  Mallorca, Bad Homburg, Nottingham, Birmingham, Stuttgart (ATP), Berlin (WTA),
  Ilkley/Surbiton.
- **Terra**, 31 voci: Roland Garros/French Open, Madrid, Roma/Internazionali, Montecarlo,
  Barcellona, Amburgo, Umag, Kitzbuhel, Gstaad, Bastad, Bucarest, Marrakech, Estoril,
  Ginevra, Lione (ATP), Monaco di Baviera, Houston, Charleston, Buenos Aires, Rio, Santiago,
  Cordoba, Rabat, Palermo, Praga, Strasburgo, Parma, Budapest, Bogota, Iasi, più
  «WTA Stuttgart» (terra indoor).
- **Cemento**, 40 voci: US Open, Australian Open, Indian Wells, Miami, Cincinnati,
  Toronto/Montreal, Dubai, Doha, Shanghai, Pechino, Tokyo, Vienna, Basilea, Rotterdam,
  Parigi Bercy, Washington, Atlanta, Los Cabos, Winston-Salem, Acapulco, Adelaide,
  Brisbane, Auckland, Hong Kong, Chengdu, Hangzhou, Wuhan, Astana, Anversa, Stoccolma,
  Metz, Marsiglia, Montpellier, Dallas, Delray Beach, Abu Dhabi, Seoul, ATP Finals
  (Torino), più «WTA Lyon» e «Newport Beach (Challenger)».
- **Voci ambigue**: stanno sopra la voce generica della città. Sono WTA Stuttgart (terra)
  prima di Stuttgart (erba), WTA Lyon (cemento) prima di Lyon (terra), Newport Beach
  (cemento) prima di Newport (erba) e Paris Masters prima di tutto.
- **Fonte di ogni voce**: il calendario ufficiale ATP/WTA, cioè la superficie del torneo.
  Per le voci ambigue la nota è nel campo `fonte`.

## 2. Varianti trend / adapt / maker (TN3)

**Prima.** `trend`, `adapt` e `maker` avevano default `False` (`tennis_pro_bot.py:123,
127, 148`), e anche la UI li metteva a `'off'`.

**Adesso.**
- Nel bot il default è `True` (`tennis_pro_bot.py:133, 138, 160`); si spengono solo con un
  `False` esplicito.
- Nella UI (`tennis.ts:782`) i default sono `'on'` e l'opzione `off` resta. Ogni hint porta
  «ACCESO di default (decisione utente 25/09); mai certificato sul banco fuori dall'erba»
  (`HINT_ACCESO_DI_DEFAULT`, `tennis.ts:668`).
- Il foglio della Control Room (`TennisBotServiceParamsSheet.tsx`) legge gli stessi
  default dal registro: non è stato toccato.

**Perché.** È la decisione dell'utente del 25/09.

## 3. Divergenze e conseguenze da portare all'utente (NON sono scelte di questo lavoro)

1. **Con le varianti accese, i setup di dominio girano anche su ERBA.**
   - Nel bot i setup si accendono con `_enable_rev = _lay_rev or self.trend or self.adapt`
     (`tennis_pro_bot.py`, riga di `_enable_rev`, invariata).
   - Con `adapt=True` di default, serving-for-set, doppio break e favorito compresso sono
     attivi su OGNI superficie. La direzione la sceglie il regime di prezzo (efficiency
     ratio di Kaufman): trend porta a BACK, range a LAY, regime neutro a nessun ingresso.
   - `adapt` ha la precedenza su `trend` (`_setup_side`).
   - Quindi «lay-reversal solo su terra/cemento» vale SOLO a varianti spente. Il test lo
     dichiara in entrambe le direzioni.
   - La logica del bot non è stata toccata.
2. **`maker=True`**: gli ingressi entrano un tick meglio del touch (in coda). Il fill non è
   garantito ed è gestito dal timeout d'ingresso: ci saranno meno ingressi riempiti.
3. **Il banco cambia numeri.** `replay_bot.py` chiama `_instantiate_bot` senza
   `competition_name`, quindi sulle registrazioni di Wimbledon tennis_pro gira come
   «cemento (default: competizione non nota)»:
   - il break point passa dal lato del ribattitore;
   - i tre setup di reversione si accendono;
   - in più ci sono le varianti accese.
   - I numeri del referto precedente NON sono confrontabili con quelli di stasera.
   - Se il coordinatore vuole che il banco giri come erba, `replay_bot.py` (fuori dal mio
     perimetro) può mettere nei params della riga `{"surface_torneo": "Wimbledon 2026"}`: il
     runner lo usa quando manca `competition_name` (`superficie_della_partita`).
   - L'attività `superficie` la scrivono i chiamanti del runner, non `_instantiate_bot`:
     il banco non vede tipi d'attività nuovi.
4. **Params del servizio già salvati.** Il foglio parametri della Control Room, a ogni
   salvataggio, scrive TUTTI i campi del registro.
   - Se l'utente ha salvato il foglio di tennis_pro prima di oggi, la riga
     `tennis_bot_service_control.params` porta `trend:false, adapt:false, maker:false`
     ESPLICITI. Quei `False` vincono sul nuovo default e le varianti restano spente finché
     non si risalva il foglio.
   - Può esserci anche `surface:'grass'`: quella ora è ignorata dal runner.
   - NON verificato sul DB (niente DB in questo lavoro): da controllare in sola lettura.
5. **Niente più scelta manuale della superficie.** Il select è stato tolto perché il suo
   `'grass'` di default non si distingueva da una scelta vera. Se l'utente vuole poter
   forzare la superficie di una partita serve una chiave dedicata (per esempio
   `surface_utente`): è una decisione sua.
6. **`fast` e `wta`.**
   - La mappa non restituisce mai `fast` né `wta`: le superfici sono `grass`, `clay`, `hard`.
   - Il bot tratta `hard` come terra (ramo non-erba).
   - Una partita WTA su erba risulta `grass`.

## 4. Test

Nuovi:
- `Betfair/stream/tennis_scalper/tests/test_tennis_pro_superficie_2026_09_25.py`: 54 test.
  - Mappa: 29 tornei sulle 3 superfici e 5 Challenger/ITF con la superficie nel nome.
  - «halle» dentro «challenger» non scatta.
  - Torneo sconosciuto e nome assente danno il default dichiarato, con il suo testo.
  - Ogni voce della mappa ha dati completi.
  - Varianti: default `True`; `False` esplicito le spegne, anche una sola.
  - Lay-reversal attivi solo su terra/cemento a varianti spente, e attivi anche su erba a
    varianti accese (fatto dichiarato).
  - Lato del break point per superficie.
  - Il bot dichiara la fonte.
- `Betfair/stream/tennis_live/tests/test_tennis_pro_superficie_runner_2026_09_25.py`:
  19 test.
  - I finti hanno le chiavi del vero: `MarketCatalogue` VERO di betfairlightweight, riga
    `tennis_markets` come la seleziona `_market_row_for`, riga `tennis_live_follow` come la
    scrive `register_tennis_follow`, riga per partita prodotta dalla funzione VERA del ponte
    `_riga_armatura` da una riga vera di `tennis_bot_service_control`.
  - Catalogo con `COMPETITION` in una sola chiamata; ripiego sulla riga di follow; il
    catalogo vince sul follow.
  - `_instantiate_bot` passa superficie e fonte (mappa, nome, default e None); il vecchio
    `'grass'` è ignorato; ripiego su `surface_torneo`; varianti accese e spente passano dalla
    riga del ponte; gli altri bot non ricevono la superficie.
  - Catena intera: `tennis_markets`, poi `ensure_follows_for_bots`, poi `_risolvi_follow`,
    poi `_instantiate_bot`.
  - `_scrivi_superficie` scrive params e attività, rispetta il default dichiarato, non
    riscrive se la superficie è già uguale e non solleva se il DB cade.
  - `set_tennis_bot_params` aggiorna solo la colonna `params`.
- `frontend/src/components/tennis/TennisBotPanel.superficie.test.tsx`: 11 test.
  - `superficieDaParams` per mappa, default, fonte assente e superficie assente.
  - Il pannello mostra superficie e fonte (anche il titolo con il torneo), il default in
    ambra, la fonte assente in rosso, la riga prima dell'armamento, e la riga solo per
    tennis_pro.
  - ARMA senza toccare nulla manda `trend/adapt/maker = true` e nessun `surface`.

Aggiornati:
- `tennis_scalper/tests/test_tennis_pro.py`: `_dry` spegne le varianti con `False` ESPLICITO,
  perché quei test descrivono la variante base (LAY di reversione, ingresso al touch).
- `frontend/src/lib/tennisRegistry.test.ts`: il test «surface copre fast/wta» è sostituito
  da «surface non è più un parametro»; aggiunto il test sui default `'on'` con la dicitura.

### Falsificazione

Script: `AUDIT_2026-09-25/mutazioni_tennis_pro_superficie_2026-09-25.py`. Muta una stringa
alla volta e ripristina dalla copia fatta prima (mai `git checkout`), verificando che il file
torni identico. Esito:

| Mutazione | Esito |
|---|---|
| M1 il runner non passa la superficie (sempre erba) | ROSSO, 9 falliti |
| M2 mappa ignorata in `risolvi` | ROSSO, 39 |
| M3 sconosciuto = erba invece di cemento dichiarato | ROSSO, 10 |
| M4 / M5 / M6 default `trend` / `adapt` / `maker` False | ROSSO, 3 / 3 / 2 |
| M7 fonte non dichiarata nei params | ROSSO, 13 |
| M8 catalogo senza `COMPETITION` | ROSSO, 1 |
| M9 niente ripiego sulla riga di follow | ROSSO, 2 |
| M10 parola non intera (halle dentro challenger) | ROSSO, 2 |
| M11 UI: default varianti `off` | ROSSO, 2 |
| M12 UI: fonte ignorata (sempre «mappa») | ROSSO, 4 |
| M13 UI: `surface: 'grass'` di nuovo nei default | ROSSO, 3 |

Dopo il ripristino: tutti verdi, `git diff` identico a prima delle mutazioni.

## 5. NON VERIFICATO

- **Replay sul banco** (`certifica tennis_pro`): non lanciato, lo lancia il coordinatore.
  - Atteso: i numeri cambiano rispetto al referto precedente, per i punti 3.1-3.3.
  - Il conteggio dei 22 scenari «certificati» dipende dai controlli di condotta, non dal P&L,
    e non l'ho visto.
- **I nomi reali delle competizioni** in `tennis_markets.competition_name` e nel catalogo
  Betfair: nessun accesso al DB. Le parole chiave sono scritte sui nomi ufficiali dei tornei
  e sul formato Betfair noto (per esempio «Wimbledon 2026», «ATP Hamburg»).
  - Da controllare in sola lettura: quante righe di settembre finiscono in `default`.
- **Il contenuto attuale di `tennis_bot_service_control.params` per `tennis_pro`**: vedi il
  punto 3.4.
- **La scrittura dei params sulla riga dal runner vero**: provata solo con un client finto
  (catena `update`/`eq`). Non l'ho provata su Supabase né con la RPC `get_tennis_bots_state`,
  che deve restituire `params` aggiornati. Dal tipo `TennisBotControl` lo fa, ma non l'ho
  eseguita.
- **Il pannello nell'app viva**: provato solo con vitest. `npm run build` non è stato
  lanciato, perché lo fa il coordinatore o l'utente.
- **`test_cert_banco_2026_09_16.py` e `test_banco_comune_2026_09_16.py`**: non lanciati,
  perché rigiocano registrazioni e sono di competenza del coordinatore.

## 6. File toccati

Modificati:
- `Betfair/stream/tennis_scalper/tennis_pro_bot.py`: default delle varianti,
  `surface_fonte`.
- `Betfair/stream/tennis_live/tennis_runner.py`: `COMPETITION`, `_con_competizione`,
  `competition_name` in `_instantiate_bot` e nei chiamanti, `superficie_della_partita`,
  `_scrivi_superficie`.
- `Betfair/stream/tennis_live/tennis_db.py`: `set_tennis_bot_params`.
- `Betfair/stream/tennis_scalper/tests/test_tennis_pro.py`: `_dry` con le varianti spente
  esplicite.
- `frontend/src/lib/tennis.ts`: registro di tennis_pro, `HINT_ACCESO_DI_DEFAULT`,
  `NOME_SUPERFICIE`, `superficieDaParams`.
- `frontend/src/components/tennis/TennisBotPanel.tsx`: la riga della superficie.
- `frontend/src/lib/tennisRegistry.test.ts`.

Nuovi:
- `Betfair/stream/tennis_scalper/superficie.py`
- `Betfair/stream/tennis_scalper/tests/test_tennis_pro_superficie_2026_09_25.py`
- `Betfair/stream/tennis_live/tests/test_tennis_pro_superficie_runner_2026_09_25.py`
- `frontend/src/components/tennis/TennisBotPanel.superficie.test.tsx`
- `AUDIT_2026-09-25/mutazioni_tennis_pro_superficie_2026-09-25.py`
- questo referto

Non toccati: `tennis_bot_service.py` (il ponte), `replay_bot.py`,
`TennisBotServiceParamsSheet.tsx`, le migrazioni.

## 7. Comandi ed esito

Tutti i pytest sono stati lanciati con `SUPABASE_URL=http://127.0.0.1:9
SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`.

- `python -m pytest -q -p no:cacheprovider` su `Betfair/stream/tennis_scalper/tests/`, sui
  test nuovi del runner e sui test esistenti che toccano tennis_pro o il runner:
  - `tennis_live/tests/`: `test_modalita_e_guardie_tennis_2026_09_24`,
    `test_ponte_interruttori_2026_09_17`, `test_tennis_bot_params`,
    `test_tennis_iscrizione_a_caldo_2026_09_25`, `test_tennis_audit_runner`,
    `test_tennis_hardening`, `test_chiudi_ora_bot_tennis_2026_09_24`,
    `test_falsificazione_bot_tennis_2026_09_17`, `test_tennis_single_stream_2026_09_09`,
    `test_tennis_auto_mode_2026_09_25`, `test_paper_execution_gap5`,
    `test_specchio_pnl_ref_2026_09_17`, `test_tennis_bot_canale_f3_2026_09_18`,
    `test_tennis_bot_canale_posizioni_2026_09_24`, `test_motore_ordini_tennis_2026_09_25`;
  - `stream/tests/`: `test_stato_mercato_freno_2026_09_24`, `test_registro_bot_2026_09_16`,
    `test_contratto_strada_unica_2026_09_25`;
  - `backtest/tools/misura_punto8/test_misura_punto8.py`.
  - Esito: **776 passed**.
  - Prima di correggere `_dry`, 6 test di `test_tennis_pro.py` erano rossi, come atteso per
    via dei nuovi default.
- `npx vitest run src/lib/tennisRegistry.test.ts src/components/tennis/`: **33 passed**, 4 file.
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**.
- `python AUDIT_2026-09-25/mutazioni_tennis_pro_superficie_2026-09-25.py <copie>`:
  **13 su 13 ROSSO**, ripristino verificato.
- Per vitest ho creato una junction `frontend/node_modules` verso il checkout principale
  (`mklink /J`). Va tolta con `cmd /c rmdir`, MAI `git worktree remove --force`.
