# BRIEF FASE 2 — Certificare tutto cio' che hai scritto + correggere il dutching (09/10/2026)

Stessa sessione dell'audit: conosci gia' il lavoro. Ordine dell'utente: **ogni cosa che scrivi deve
essere vera e certificata da te**; poi correggi il punto 1 (dutching). Nient'altro.

## 0. Perche' questa fase
La verifica del coordinatore (`verifica_coordinatore/ESITO_VERIFICA.md`, referti `V1_ML.md`,
`V2_POISSON.md`, `V3_BOT.md`) ha trovato errori nei tuoi referti:
- A4 Safe tennis: FALSO in due punti. Gli ingressi di Safe tennis (`Betfair/safe_strategy/engine.py:1567`
  `evaluate_tennis`) seguono le regole dell'utente e non usano il modello; il modello entra solo nel
  cancello degli incassi (`bot_service.py:5295`). Safe tennis E' certificato (replay 09/10, 18/18 OK,
  `CRONOSTORIA.md:5609-5618`). Non avevi letto la cronostoria del giorno.
- M3: «lo scalper usa il grezzo» FALSO (`bias_resolver.py:87` legge solo l'1X2, quasi calibrato).
- M20 Mike: e' una SCELTA DOCUMENTATA (`Betfair/mike/COSTITUZIONE_MIKE.md:157-158`), non un errore.
- M22, M21, M1: impatto sovrastimato. A3: sottostimato. Righe citate sbagliate in H (437->401, 36->40).
- MA2, M1, A2, A3, MA1 erano gia' in `AUDIT_2026-10-02/AUDIT_ML_POISSON.md` (CRONOSTORIA.md:4888):
  non li hai citati.

## 1. Compito A — certificazione di TUTTI i tuoi referti
Per OGNI reperto di `05_ERRORI_DI_PROGETTAZIONE.md` (A, MA, M, B: tutti, nessuno escluso) e per ogni
affermazione di fatto in 00-04, 06, 07 e `DECISIONI_PER_L_UTENTE.md`:
1. rileggi il codice citato (file:riga ATTUALI) e verifica che il percorso sia vivo e chi lo consuma;
2. cerca in `CRONOSTORIA.md` (git grep), nelle costituzioni dei bot (`Betfair/*/COSTITUZIONE_*.md`),
   in `PIANO_MODIFICHE_MIKE_2026-09-29.md` e negli audit precedenti se e' gia' noto, gia' deciso
   dall'utente o gia' corretto: una scelta documentata dell'utente NON e' un errore;
3. stato di certificazione dei bot: solo dalla cronostoria e dai referti del banco, mai «non risulta»;
4. verdetto: CONFERMATO / FALSO / RIDIMENSIONATO / SCELTA DOCUMENTATA / GIA' NOTO (con riferimento);
   i numeri si rifanno con codice tuo; cio' che non puoi verificare si scrive «NON VERIFICATO» e non
   entra nel riepilogo come fatto.
Consegne: `05` riscritto con la colonna verdetto e gravita' ricalcolata; `07_RIEPILOGO_PER_L_UTENTE.md`
riscritto solo con fatti certificati, in italiano chiaro per un non tecnico; `DECISIONI_PER_L_UTENTE.md`
ripulito (via le decisioni basate su reperti falsi o su scelte gia' prese); correzioni puntuali in
00-04 e 06; `CERTIFICAZIONE_REFERTI.md` con la tabella reperto -> verdetto -> prova -> come hai verificato.
Usa i referti V1/V2/V3 come input, ma riverifica tu dove li contraddici o li estendi.

## 2. Compito B — correzione del dutching (punto 1)
Reperti A1 + M11:
- A1: con `mode=variable` e lato LAY il worker piazza ordini BACK (`Betfair/stream/live_order_worker.py`
  ~2914-2919: `dutch_variable` restituisce sempre `side="back"`); la UI blocca solo target+lay.
- M11: l'anteprima di `frontend/src/components/live/DutchingPanel.tsx` (~194-209: stake proporzionale a
  peso/quota) diverge da cio' che il server piazza (`Betfair/stream/trading/dutching.py` ~184-244:
  profitto proporzionale al peso).
Correzione richiesta, MINIMA:
1. variable + lay RIFIUTATO in due punti: nel worker (errore esplicito, zero ordini, come gia' avviene per
   target+lay) e nella UI (opzione non selezionabile / invio bloccato con motivo leggibile);
2. l'anteprima UI calcola esattamente cio' che il server piazza (stessa formula di `dutch_variable`,
   stessi arrotondamenti), cosi' cio' che l'utente conferma e' cio' che va a mercato;
3. controlla anche il caso segnalato in V3: pesi irrealizzabili -> il server risponde ok=True senza
   ordini; la UI non deve mostrare «inviato» se non e' partito niente (se la correzione esce dal
   perimetro, scrivila nelle decisioni).
Non cambiare la semantica dei modi equal/target ne' alcun altro comportamento.
Test (TDD): test nuovi in `Betfair/stream/tests/test_dutching.py`, `Betfair/stream/tests/test_live_order_dutch_cashout.py`,
`frontend/src/components/live/DutchingPanel.test.tsx`; i finti con chiavi e tipi identici al vero;
OGNI test nuovo va falsificato (togli la correzione -> il test diventa rosso; rimettila -> verde) e la
falsificazione va scritta nel referto con l'output. Poi:
`.venv/Scripts/python.exe -m pytest Betfair/stream/tests/test_dutching.py Betfair/stream/tests/test_live_order_dutch_cashout.py -q -p no:cacheprovider`,
la suite intera `python -m pytest Betfair/ -q -p no:cacheprovider` (confronta con lo stato prima della
modifica: nessun test prima verde diventa rosso), in `frontend/`: `npx vitest run src/components/live/DutchingPanel.test.tsx`
e `npx tsc -p tsconfig.app.json --noEmit` (0 errori, mai @ts-ignore/any).
NON eseguire `npm run build` (lo fa il coordinatore ad app chiusa), niente commit.
Consegna: `REFERTO_FIX_DUTCHING.md` con diff (git diff dei file toccati), test, falsificazione, numeri
delle suite prima/dopo, cio' che non hai potuto verificare.

## 3. Ordine e budget
Prima B (soldi veri, piu' urgente), poi A. Budget: circa 43 USD in tutto per questa fase (il contatore
parte da 36,97 USD gia' spesi). Delegati Sonnet per le verifiche a tappeto, in primo piano, max 4.
Quando A e B sono consegnati: `FATTO.txt` con l'elenco.

## 4. Condizioni dell'utente
Strategie dei bot intoccabili; nessuna modifica fuori dal perimetro dichiarato nel prompt; mai ordini
Betfair; mai avviare/chiudere app, bot, processi; mai terminare processi; niente commit, mai
`git add -A`, mai checkout/stash; DB solo SELECT leggere con LIMIT.
