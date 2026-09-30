# T_P4 - Stop perdita in testata: conto + ogni bot, con il punto dove si modifica (B4)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4993b702a303cacc`
Base: `1d058a7` (nessun merge dopo, per regola del coordinatore). Nessun commit.
Patch: `AUDIT_2026-09-30/ui_blocchi/T_P4.patch` = diff CUMULATIVO di `frontend/` (P3 + P4).

## 1. PRIMA -> DOPO a schermo (dentro il contenitore storico `cr-freni`)

| Prima | Dopo |
|---|---|
| `STOP PERDITA −50,00 €` (di chi? era Safe, in paper) | `STOP PERDITA` / `Conto: SPENTO ✎` (✎ = collegamento a `/segui-live`) |
| | `Safe PAPER −50,00 € ✎ · Mike LIVE −50,00 € ✎ · Omega PAPER −300,00 € ✎` |
| stop assente: `assente` | Safe non dichiarato dal servizio: `assente`; Mike/Omega con parametri non letti: `non letto` (mai il valore predefinito spacciato per vero) |
| scattato: `SCATTATO` | Safe/Mike scattato: `SCATTATO`; conto scattato: `SCATTATO: freno generale tirato` |
| | stop del conto attivo: `Conto: −40,00 € oggi −12,50 € ✎`; riga mai letta: `Conto: non letto` (mai «SPENTO») |
| | soglia 0 di un bot: `spento` |

Tooltip di ogni voce: da dove viene il numero (chiave), dove si modifica, «vale solo per le aperture di <bot>».
Conto: «stop del CONTO (betfair_live_settings.daily_loss_limit, applicato dal runner): raggiunto, tira il freno
generale. Stato del runner: limit_off. Riga aggiornata al cambio, ultimo cambio N fa.»

## 2. Fonti

| Voce | Fonte |
|---|---|
| Conto | `betfair_live_risk_state` (singleton): `limit_value`, `stop_fired`, `total`, `detail.reason/degraded`, `updated_at`; scritta al cambio da `Betfair/stream/daily_stop_worker.py::_publish_state` (:318-354), soglia da `betfair_live_settings.daily_loss_limit` (:124-137). Letta con `fetchLiveRiskState` + `subscribeLiveRiskState` (`lib/liveOrders.ts:793/:804`) |
| Safe | `safe.control.stats.risk.daily_loss_stop` / `loss_stop_active` dichiarati dal servizio (lo stesso `vm.freni` di prima), segno normalizzato con `normalizeLossStop` (`lib/safeBot.ts:928`, come `BotParamsSheet`); `safe_strategy/risk.py:43/:84-88/:176-179` |
| Mike | `mike.control.params.daily_loss_stop` (con i predefiniti di `mergeMikeParams`, `lib/mike.ts:597/:607` = `mike/config.py:318`), scattato = `stats.daily_stop` (`mike/service.py:3916-3917/:4107`) |
| Omega | `omega.control.params`: motore `strategy_version` (predefinito 3) -> `v3_daily_loss_cap` (predefinito 300), motore 2 -> `daily_loss_cap` (predefinito 0). Stessa scelta del servizio `omega_service.py:1847-1849`, `omega_config.py:221/:262/:434` |
| Modalita' | `vm.bots[].modalita` (= `control.mode` del servizio) |

## 3. Dove si modifica (nessun salvataggio nuovo, nessuna RPC nuova, nessuna scrittura)

- **Conto**: collegamento a `/segui-live`, pannello «Controlli runner · limiti · audit», campo «Stop giornaliero»
  (`LiveControlsPanel.tsx:168/:189/:350`, `set_live_settings`: il controllo di sempre).
- **Bot**: il pulsante ✎ porta alla riga del bot in «Comando dei bot» (`[data-testid="cr-parametri-<bot>"]`, il
  foglio parametri gia' montato dalla pagina col suo cancello «parametri non letti»), la centra e mette il FUOCO
  sul suo pulsante: NON lo apre e non salva niente (test: nessun clic). Se la riga non e' visibile (scheda
  tennis filtrata o gruppo chiuso) porta al pannello.
- Perche' questa via e non l'apertura del foglio dalla testata: aprirlo da qui vorrebbe dire montare una seconda
  istanza del foglio (seconda via di salvataggio dello stesso servizio, e un secondo cancello «parametri non letti»
  da tenere allineato) oppure sollevare lo stato del foglio fuori da `PannelloBot` (fuori perimetro). Portare alla
  riga e' un hunk solo, zero scritture, e il cancello resta quello che c'e'.

## 4. Velocita'

Una lettura NUOVA, leggera: `betfair_live_risk_state` (riga singleton) una volta all'apertura + push Realtime;
nessun poll, niente nel giro dei 30 s. Nessuna lettura della Control Room la portava: `RigaFreno` legge
`get_live_settings` ogni 30 s per il FRENO (kill switch), non lo stato dello stop; non l'ho duplicata. Test:
una fetch e una sottoscrizione (falsificato, P4-6).

## 5. File

Toccati in P4: `frontend/src/pages/ControlRoom.tsx` (`Freni` monta `StopPerdita`; import),
`frontend/src/components/controlroom/useControlRoom.ts` (import accorpato di `fetchLiveRiskState`/`subscribeLiveRiskState`,
campo `stopPerdita` nel VM, stato `statoRischioConto`, effetto one-shot+realtime, `useMemo stopPerdita`),
`frontend/src/pages/ControlRoom.test.tsx` (il finto `vm()` costruisce `stopPerdita` con le funzioni vere dagli
stessi `freni`; 1 test nuovo), `frontend/src/components/controlroom/useControlRoom.soldiVeri.test.tsx` (mock delle
due funzioni + 2 test). Nuovi: `components/controlroom/testata/stopPerdita.ts`, `testata/FasciaStop.tsx`
(componente `StopPerdita`: nome file diverso per la collisione di maiuscole con `stopPerdita.ts` su Windows),
`testata/FasciaStop.test.tsx`.

Campo nuovo del VM: `stopPerdita: { conto: StopConto, bot: StopBot[] }`. `freni` resta (invariato).

## 6. Test

- Nuovi: `FasciaStop.test.tsx` 15; hook +2; pagina +1.
- Esistenti invariati e verdi: `freni — ...` «mostra la soglia» (/50,00/), «SOGLIA ASSENTE ... assente, MAI 0,00»,
  «stop già scattato: SCATTATO». Nessun test esistente cambiato in P4 (il finto `vm()` ha una chiave in piu',
  costruita dagli stessi `freni` che il test sovrascrive).
- `npx tsc -p tsconfig.app.json --noEmit` = 0; `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom
  --maxWorkers=2` = **58 file, 906 test verdi** (489 s).

## 7. Falsificazioni (`T_falsificazioni/mut_p4.json`, stesso script fuori dal repo, ripristino con hash)

| Mutazione | Esito |
|---|---|
| P4-1 stop del conto spento letto come soglia 0 | ROSSO 2 |
| P4-2 conto non letto scritto SPENTO | ROSSO 1 |
| P4-3 Omega ignora il motore | ROSSO 2 |
| P4-4 Mike: predefinito spacciato per vero a parametri non letti | ROSSO 1 |
| P4-5 il pulsante clicca (apre) invece di mettere il fuoco | ROSSO 1 |
| P4-6 una lettura in piu' dello stop del conto | ROSSO 1 |
| P4-7 push realtime dello stop ignorato | ROSSO 1 |
| P4-8 testata col vecchio numero di Safe senza nome | ROSSO 3 (pagina) |

`git diff --stat` identico prima/dopo.

## 8. COSA NON HO FATTO

- Aprire il foglio parametri dalla testata (motivo in §3).
- Omega «scattato»: il servizio non pubblica un booleano dello stop (lo si vede solo nel motivo del blocco
  della sua riga): mostro la soglia, non lo stato.
- Stop di Safe per modalita'/strategia: mostro quello unico del servizio con la modalita' del servizio.
- I 4 bot tennis e lo scalper: non hanno uno stop di perdita giornaliera che la pagina conosca: non elencati.

## 9. COSA NON HO POTUTO VERIFICARE

- L'app a schermo (larghezza della riga dei tre stop nella testata sticky; scorrimento e fuoco sul foglio reale).
- Il valore vero di oggi di Omega (`strategy_version`/`v3_daily_loss_cap` nella riga di control): il progetto dice
  «Omega spento»; la pagina mostrera' quello che dicono i parametri con la regola del servizio.
- Che la regola di Omega resti quella di `omega_service.py:1847-1849` per il motore v4 (mandato del 17/09): se il
  servizio usa un'altra chiave, il numero sarebbe sbagliato. Dato che servirebbe dal backend (forma esatta):
  `omega_control.stats.stop_perdita = { soglia: number, chiave: string, scattato: boolean }` (idem per Mike:
  `stats.daily_stop` c'e' gia', manca la soglia EFFETTIVA dopo i predefiniti).
- Che `betfair_live_risk_state` sia aggiornata quando il runner e' spento (scrive il runner): a runner spento la
  riga resta l'ultima scritta; l'eta' e' nel tooltip.

## Verifica del coordinatore UI (admin-07), 30/09 18:55
- Terzo giro, albero integrato (`1d058a7` + C_P12a + B1bis + P13 + T_P4 + G_P7): `npx tsc -p tsconfig.app.json --noEmit` = 0 errori; `npx vitest run src/components/controlroom src/components/trading src/pages/ControlRoom.test.tsx` + 9 test di lib toccati = 91 file, 1478 test verdi.
- La patch in QUESTA cartella e l INCREMENTALE ricavato da me sul master `f58b595`; ordine di applicazione: `B1bis.patch` → `P13_ESITI_CHIUSURA.patch` → `T_P4.patch` → `G_P7.patch` (fusione a tre vie senza conflitti; su ogni file toccato il risultato e identico byte per byte all albero verificato).
- Mutazioni MIE (oltre le 8 del delegato), ROSSE: riga dello stop del conto NON letta trattata come «SPENTO» letto (2 rossi); Omega letto sempre col motore 2 (10).
- Da sapere: UNA lettura nuova (`betfair_live_risk_state`, una volta + realtime, nessun poll). La regola di Omega (motore 3 → `v3_daily_loss_cap`, predefinito 300) e replicata dal servizio: se il servizio cambia, va cambiata anche qui (chiesto al backend `stats.stop_perdita`). La matita porta alla riga del bot e mette il fuoco sul foglio esistente: non lo apre e non salva.
