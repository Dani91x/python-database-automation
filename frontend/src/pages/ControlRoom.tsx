// ============================================================================
// ControlRoom.tsx — IL BANCO DELLA GIORNATA.
//
// Non è una dashboard in più: è il posto da cui si decide. Tre bot (Omega,
// Safe, Mike) lavorano per un obiettivo di giornata; questa pagina mette UN
// FILTRO DI SCELTA davanti a quello che già fanno. L'operatore approva o
// scarta — i bot fanno il resto.
//
// COSA QUESTA PAGINA NON FA, e non deve mai iniziare a fare:
//   · non calcola segnali (li leggono dai tre bot);
//   · non ricalcola il P&L (viene da `eventGroups`, netto di commissione
//     scritto dal servizio);
//   · non ricalcola il target per partita (lo pubblica il servizio di Omega:
//     `MissionPanel.tsx:221-226` avverte per iscritto che una seconda copia
//     locale fu un bug);
//   · non apre una seconda strada verso Betfair: l'approvazione passa dalla
//     CODA richieste che già esiste, con le sue guardie e la sua idempotenza.
//
// LAYOUT: testata con la giornata · partite per campionato in ordine
// cronologico · nastro dei segnali · posizioni aperte.
// ============================================================================
import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RefreshCw, Radio, ShieldAlert, Circle, SlidersHorizontal } from 'lucide-react';
import { PageShell } from '@/components/trading/PageShell';
import { EmptyState } from '@/components/trading/EmptyState';
import type { DayBarProps } from '@/components/trading/DayBar';
import { ModeBanner } from '@/components/trading/ModeBanner';
import { SplitSport, type SportKey } from '@/components/controlroom/SplitSport';
import { corsiePerSport } from '@/lib/giornataCorsie';
import { etaContoS } from '@/lib/composizioneConto';
import { SchedaPartita } from '@/components/controlroom/SchedaPartita';
import { ObiettivoHero } from '@/components/controlroom/ObiettivoHero';
import { SaldoBetfairCard } from '@/components/controlroom/SaldoBetfairCard';
import { UsciteColonna } from '@/components/controlroom/UsciteColonna';
import { OpportunitaColonna } from '@/components/controlroom/OpportunitaColonna';
import { pnlClass } from '@/lib/tradeStatus';
import { dayLabel as etichettaGiorno } from '@/lib/dailyHistory';
import { fmtMoney, fmtOdds, fmtAge, fmtTime, DASH } from '@/lib/format';
import { romeDay, dayLabel } from '@/lib/dailyHistory';
import {
    BOT_LABEL, affidabilePerPiazzare, BOT_TENNIS, isBotTennis,
    type Bot, type GruppoCampionato, type Freschezza, type PartitaGiornata,
} from '@/lib/controlRoom';
import { runnerPhase, type RunnerPhase } from '@/lib/safeBot';
import { fmtMs, totaleCatena, totaleNostro, colloDiBottiglia } from '@/lib/controlRoomCatena';
import type { StatoChiusuraEvento } from '@/lib/chiusuraUtente';
import {
    useControlRoom,
    type StatoBot, type PosizioneAperta,
} from '@/components/controlroom/useControlRoom';
import { righeInterruttori } from '@/components/controlroom/righeBot';
import { PannelloBot } from '@/components/controlroom/PannelloBot';
import { RigaOrdiniReali } from '@/components/controlroom/RigaOrdiniReali';
import { RigaFreno } from '@/components/controlroom/RigaFreno';
import { ProposteUsciteFlusso } from '@/components/controlroom/ProposteUsciteFlusso';
import { RigaCapacitaMercati } from '@/components/controlroom/RigaCapacitaMercati';
import { FasciaSoldiVeri } from '@/components/controlroom/testata/FasciaSoldiVeri';
import { StopPerdita } from '@/components/controlroom/testata/FasciaStop';
import {
    modoChip, statoChip, usciteChip, pallinoChip, aggiornatoChip, tettoRunner, sorgenteFeed, riassuntoDati, type Tono,
} from '@/components/controlroom/testata/paroleImpianto';
import {
    STAKE_TENNIS, differenzeSoloTennis, altreInLiveAdesso,
} from '@/components/controlroom/soloTennis';
import { PosizioniChiuse } from '@/components/controlroom/PosizioniChiuse';
import { BottoneChiudiRiga, ChiusuraRigaContext, type ChiusuraRigaApi } from '@/components/controlroom/BottoneChiudiRiga';
import { prezzoAlClic, useChiusuraAlMs } from '@/components/controlroom/useChiusuraAlMs';
import type { SorgenteLadder } from '@/components/controlroom/usePrezzoAlMs';
import { sorgenteLadderAlMs } from '@/lib/localTransport';
import { StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import {
    BadgeStato, Ingresso, QuotaOra, PnlVivo, Copertura, Greenup, ModelloP, Uscita,
} from '@/components/controlroom/DettaglioRigaView';
import { StoricoLink } from '@/components/trading/StoricoLink';
import { SchedaPreMatch } from '@/components/controlroom/SchedaPreMatch';
import { leggiRitorno, dimenticaRitorno, portaInVista } from '@/lib/ritorno';
import { creaComandiControlRoom } from '@/components/controlroom/comandiBot';
import {
    interruttoriDiSport, importiInterruttori, type InterruttoreId,
    usciteInterruttori, conPosizioniAperte, usciteBotTennis,
} from '@/lib/interruttori';
import { BotParamsSheet, type StrategiaFiltro } from '@/components/safestrategy/BotParamsSheet';
import { MikeParamsSheet } from '@/components/mike/MikeParamsSheet';
import { mergeBotParams, updateSafeParams } from '@/lib/safeBot';
import { mergeMikeParams, updateMikeParams } from '@/lib/mike';
// 18/09 — TASK 4: parametri DEDICATI per bot. `OmegaParamsSheet` riusa
// `ParamsSheetBase` esattamente come `pages/Omega.tsx` (stesse costanti di
// `lib/omega.ts`); `TennisBotServiceParamsSheet` costruisce il foglio sui
// campi che il SERVIZIO legge davvero (`TENNIS_BOT_REGISTRY`, verificato in
// sola lettura contro `Betfair/stream/tennis_scalper/*_bot.py`).
import { OmegaParamsSheet } from '@/components/omega/OmegaParamsSheet';
import { TennisBotServiceParamsSheet } from '@/components/tennis/TennisBotServiceParamsSheet';

// --------------------------------------------------------------- vocabolario
// Le parole del trader, in italiano, in un posto solo.

// Lato: le stesse parole e gli stessi colori del resto della piattaforma —
// BACK sky, LAY **rose** (non pink: il design system dichiara rose, e due
// rosa diversi per la stessa cosa rallentano la lettura).
const LATO_LABEL: Record<'back' | 'lay', string> = { back: 'BACK', lay: 'LAY' };

const LATO_CLS: Record<'back' | 'lay', string> = {
    back: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    lay: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
};

const BOT_CLS: Record<Bot, string> = {
    omega: 'text-primary',
    safe: 'text-secondary',
    mike: 'text-teal-300',
    scalper: 'text-violet-300',
    // i quattro del tennis, stessa famiglia di colore della scheda partita
    tennis_scalper: 'text-amber-300',
    tennis_pro: 'text-amber-200',
    tennis_flb: 'text-orange-300',
    tennis_swing: 'text-yellow-300',
};


/** I TRE STATI DEL RUNNER — «vivo» non basta.
 *  14/09: il battito diceva «2 settembre» mentre il processo girava (corretto in
 *  `ad68253`: ora batte anche da fermo). Ma «vivo» e «utilizzabile» restano due
 *  cose diverse: `live_order_worker` nasce dentro il framework, quindi con il
 *  runner IN ATTESA la coda non ha nessuno dall'altro capo. Il dubbio non
 *  concede mai la coda (`runnerPhase`, fail-closed). */
const FASE_RUNNER: Record<RunnerPhase, string> = {
    off: 'spento',
    idle: 'vivo, in attesa',
    streaming: 'in streaming',
};

/**
 * COSA DIRE DI UN PREZZO — segnalato dall'utente il 14/09 su «Quote 2 min».
 *
 * Lo scanner scrive **solo quando qualcosa cambia**: l'età della riga dice «da
 * quanto quel prezzo non si muove», NON «da quanto non lo guardiamo». Su un
 * mercato poco scambiato un prezzo fermo da minuti è **corretto e corrente** —
 * chiamarlo «vecchio» è la stessa bugia che ha fatto credere morto un runner
 * che stava benissimo. I due casi si distinguono solo incrociando con la
 * vitalità dello SCANNER.
 */


const FRESCHEZZA_TESTO: Record<Freschezza, string> = {
    fresca: 'fresco', lenta: 'in ritardo', vecchia: 'vecchio', ignota: 'età sconosciuta',
};

// 25/09 (residui B17) - la sorgente del ladder al ms per il "se chiudo ora"
// delle righe (la stessa delle schede delle proposte)
const SORGENTE_LADDER_RIGHE: SorgenteLadder = (sport) => sorgenteLadderAlMs(sport);

const FRESCHEZZA_CLS: Record<Freschezza, string> = {
    fresca: 'text-emerald-400',
    lenta: 'text-secondary',
    vecchia: 'text-orange-400',
    ignota: 'text-orange-400',
};

// ============================================================================

export default function ControlRoom() {
    const vm = useControlRoom();
    // B16 (24/09) — il «Chiudi» per singolo bot, portato alle righe dal contesto
    const chiusuraRiga = useMemo<ChiusuraRigaApi>(
        () => ({
            chiudi: vm.chiudi, stato: vm.statoChiusuraRiga,
            // B17 (25/09) — l'esito dell'ordine dopo il clic (assenti nei finti storici)
            esito: vm.esitoChiusuraRiga, seguiClic: vm.seguiClic, esitoOrdine: vm.esitoOrdine,
            esitiOrdini: vm.esitiOrdini,
            // 25/09 (residui B17) - "Chiudi" di riga al prezzo del ms
            sorgenteLadder: SORGENTE_LADDER_RIGHE,
        }),
        [vm.chiudi, vm.statoChiusuraRiga, vm.esitoChiusuraRiga, vm.seguiClic, vm.esitoOrdine, vm.esitiOrdini],
    );
    // LO SPORT SCELTO filtra il banco: `null` = tutti e due.
    const [sport, setSport] = useState<SportKey | null>(null);

    // LA SCHEDA APERTA. Si riapre da sola se si torna qui da un'altra pagina:
    // «torna indietro» deve riportare al punto esatto, non in cima.
    const [scheda, setScheda] = useState<string>(() => leggiRitorno()?.scheda ?? 'live');

    // ora filtra SOLO lo sport: lo stato della partita lo decide la scheda
    const giornata = useMemo(
        () => filtra(vm.giornata, { sport }),
        [vm.giornata, sport],
    );

    // Lo sport di una posizione non sta sulla posizione: si ricava dalla
    // partita. Un evento che NON conosciamo resta VISIBILE — una posizione con
    // soldi veri non sparisce mai per colpa di un filtro (fail-open voluto).
    const sportDiEvento = useMemo(() => {
        const m = new Map<string, SportKey>();
        for (const g of vm.giornata) for (const p of g.partite) m.set(p.event_id, p.sport === 'tennis' ? 'tennis' : 'calcio');
        return m;
    }, [vm.giornata]);

    const posizioni = useMemo(() => {
        if (sport == null) return vm.posizioni;
        return vm.posizioni.filter((p) => (sportDiEvento.get(p.eventId) ?? sport) === sport);
    }, [vm.posizioni, sport, sportDiEvento]);

    const inLive = vm.bots.some((b) => b.modalita === 'live');

    // quante righe ha ogni scheda: un numero sulla linguetta evita di doverle
    // aprire tutte per scoprire quale ha qualcosa dentro.
    const [contaPre, contaLive] = useMemo(() => {
        let pre = 0, live = 0;
        for (const g of giornata) for (const p of g.partite) {
            if (p.stato === 'live') live += 1; else if (p.stato === 'pre') pre += 1;
        }
        return [pre, live];
    }, [giornata]);
    /**
     * I due registratori sono vivi?
     *
     * ⚠️ REVIEW 15/09 — REC diventava rosso appena il FLAG era scritto sul
     * database, ma la registrazione la fa il PROCESSO. Runner fermo = spia
     * rossa e zero registrazione. Il dato c'era gia' in pagina.
     *
     * Il runner e' UNO per sport: `vm.runner` e' quello che la pagina legge
     * gia' per la riga «Runner» della testata. Quando non lo sappiamo vale
     * `null`, e la scheda dice «flag acceso» senza promettere altro.
     */
    const registratori = useMemo(() => {
        // runner non letto = NON LO SAPPIAMO, mai «spento» e mai «vivo»
        const vivo = vm.runner == null ? null : runnerPhase(vm.runner) !== 'off';
        // 25/09 (voce 6): il runner TENNIS ha il suo canale (47332); se tace
        // resta la lettura di prima (quella del runner calcio)
        const vivoTennis = vm.runnerTennis == null ? vivo : runnerPhase(vm.runnerTennis) !== 'off';
        return { calcio: vivo, tennis: vivoTennis };
    }, [vm.runner, vm.runnerTennis]);

    /**
     * LA GIORNATA OPERATIVA della pagina (Europe/Rome), una sola volta: la
     * usano la barra della giornata e la scheda delle posizioni chiuse, che
     * dal 17/09 mostra SOLO oggi.
     */
    const giornoOperativo = useMemo(() => romeDay(new Date(vm.nowMs)), [vm.nowMs]);

    // il contatore della scheda deve contare QUELLO CHE LA SCHEDA MOSTRA:
    // soldi veri, dello sport scelto, e SOLO della giornata di oggi.
    const contaChiuse = useMemo(
        () => vm.chiuse.filter((c) => (sport == null || c.sport === sport)
            && c.modo === 'live' && c.giorno === giornoOperativo).length,
        [vm.chiuse, sport, giornoOperativo],
    );

    // RITORNO AL PUNTO ESATTO: si consuma UNA volta sola, quando le righe ci
    // sono. Consumarlo prima riporterebbe su una lista ancora vuota.
    const [ritornoFatto, setRitornoFatto] = useState(false);
    useEffect(() => {
        if (ritornoFatto || vm.caricamento) return;
        const r = leggiRitorno();
        if (!r) { setRitornoFatto(true); return; }
        setRitornoFatto(true);
        dimenticaRitorno();
        const t = window.setTimeout(() => {
            if (r.eventId && portaInVista(r.eventId)) return;
            window.scrollTo({ top: r.scorrimento, behavior: 'smooth' });
        }, 80);
        return () => window.clearTimeout(t);
    }, [ritornoFatto, vm.caricamento]);

    // ── COMANDO DEI BOT ──────────────────────────────────────────────────────
    // I parametri li legge dallo STATO GIA' CARICATO: il comando non fa una
    // lettura sua, o potrebbe salvare partendo da una versione diversa da
    // quella che il trader sta guardando.
    const paramsDi = useCallback(
        (b: Bot) => vm.bots.find((x) => x.bot === b)?.params ?? null,
        [vm.bots],
    );
    const servizioDi = useCallback(
        (b: Bot) => {
            const s = vm.bots.find((x) => x.bot === b);
            return s == null ? null : {
                inCorsa: s.inCorsa, modalita: s.modalita,
                varianti: s.varianti, modiStrategia: s.modiStrategia,
            };
        },
        [vm.bots],
    );
    const [erroreComando, setErroreComando] = useState<string | null>(null);
    const comandi = useMemo(() => {
        // ⚠️ NELLA SCHEDA TENNIS «AVVIA» VUOL DIRE UN'ALTRA COSA.
        // Safe è un servizio solo e porta dentro sia il tennis sia le tre
        // strategie del calcio: da qui parte SOLO il tennis, a 3,00 €, e tutto
        // il resto resta in prova. Lo decide `creaComandiControlRoom`, che usa
        // le STESSE funzioni condivise delle pagine dei bot.
        const base = creaComandiControlRoom({
            params: paramsDi,
            servizio: servizioDi,
            obiettivoOmega: () => vm.bots.find((x) => x.bot === 'omega')?.obiettivoGiorno ?? vm.obiettivo,
        }, vm.ricarica, sport);
        // un comando che fallisce in silenzio e' peggio di un comando assente:
        // il trader crede di aver fermato un bot che sta ancora operando.
        const avvolgi = <A extends unknown[]>(f: (...a: A) => Promise<void>) => async (...a: A) => {
            setErroreComando(null);
            try { await f(...a); } catch (e) {
                setErroreComando(e instanceof Error ? e.message : String(e));
                throw e;
            }
        };
        return {
            accendi: avvolgi(base.accendi), spegni: avvolgi(base.spegni),
            cambiaModalita: avvolgi(base.cambiaModalita), cambiaImporto: avvolgi(base.cambiaImporto),
            fermaBot: avvolgi(base.fermaBot), scriviAccensioni: base.scriviAccensioni,
            cambiaModalitaServizio: avvolgi(base.cambiaModalitaServizio),
            // 25/09 — «Uscite automatiche» per singolo bot
            ...(base.cambiaUscite ? { cambiaUscite: avvolgi(base.cambiaUscite) } : {}),
        };
    }, [paramsDi, servizioDi, sport, vm.bots, vm.obiettivo, vm.ricarica]);

    // Gli importi: UNO per interruttore, con la chiave che il servizio legge
    // davvero. Se la strategia non ha ancora una chiave sua si mostra quella
    // per LATO e la riga lo DICHIARA (`importoDi`).
    const importi = useMemo(
        () => importiInterruttori(interruttoriDiSport(sport), paramsDi),
        [paramsDi, sport],
    );
    // 25/09 — «uscite: automatiche / manuali, N posizioni aperte da X min»,
    // riga per riga, dai parametri del servizio e dalle posizioni gia' lette.
    const uscite = useMemo(() => {
        const out = conPosizioniAperte(
            usciteInterruttori(interruttoriDiSport(sport), paramsDi),
            (vm.posizioni ?? []).map((p) => ({ bot: p.bot, piazzataAt: p.piazzataAt, gamba: p.dettaglio?.gamba ?? null })),
            vm.nowMs,
        );
        // 28/09 (CANTIERE N): i 4 bot tennis nello STESSO pulsante degli altri
        // (prima avevano `UsciteTennis` nello slot dei parametri, con altre
        // parole). Lo stato e' la colonna della loro riga di control.
        for (const i of interruttoriDiSport(sport)) {
            if (!isBotTennis(i.bot)) continue;
            const b = vm.bots.find((x) => x.bot === i.bot);
            out[i.id] = usciteBotTennis(b?.usciteTennis, b?.autoTennis ?? null, vm.nowMs);
        }
        return out;
    }, [paramsDi, sport, vm.posizioni, vm.nowMs, vm.bots]);

    // ── LA PLANCIA, RISTRETTA ALLO SPORT SCELTO ──────────────────────────────
    // «Nella scheda tennis voglio vedere SOLO i bot di tennis» (utente,
    // 15/09). Mike (Under 3.5) e Omega (risultato esatto) sono calcio e qui non
    // hanno niente da dire. Senza filtro sarebbe l'operatore a doversi
    // ricordare quale riga riguarda la partita che sta guardando.
    //
    // 17/09 — nella scheda tennis le righe adesso sono CINQUE: la strategia
    // `tennis` di Safe piu' i QUATTRO BOT del tennis (scalper, pro, flb,
    // swing), che sono servizi indipendenti con la loro riga di control. Il
    // filtro per sport li porta dentro da solo: l'elenco e' uno
    // (`INTERRUTTORI`), e non ce n'e' un secondo da tenere allineato.
    const soloTennis = sport === 'tennis';
    const righeBot = useMemo(
        () => righeInterruttori(vm.bots, sport, soloTennis ? { 'safe-tennis': 'Tennis' } : undefined),
        [vm.bots, sport, soloTennis],
    );
    /** i SERVIZI accesi, per il freno d'emergenza: sono bot, non strategie */
    const serviziAccesi = useMemo(
        () => vm.bots.filter((b) => b.inCorsa).map((b) => ({ bot: b.bot, modalita: b.modalita })),
        [vm.bots],
    );
    /**
     * Che cosa cambia l'avvio dalla scheda tennis, detto PRIMA del clic.
     * Si chiede in `'paper'` di proposito: cosi' l'elenco contiene solo i
     * cambiamenti di CONFIGURAZIONE, che avvengono con tutti e due i pulsanti.
     * Chiedendolo in `'live'` ci finirebbe dentro anche «tennis -> soldi veri»,
     * che pero' e' vero solo per uno dei due — e comparirebbe sopra il
     * pulsante «avvia in prova».
     */
    const cambiTennis = useMemo(
        () => (soloTennis ? differenzeSoloTennis(paramsDi('safe'), 'paper') : []),
        [soloTennis, paramsDi],
    );
    /**
     * Che cosa sta uscendo con soldi veri ADESSO, oltre al tennis. Una plancia
     * ristretta a una riga non deve nascondere il calcio che opera davvero
     * dentro lo stesso servizio.
     */
    const altreLive = useMemo(() => {
        if (!soloTennis) return [];
        const safe = vm.bots.find((b) => b.bot === 'safe') ?? null;
        return altreInLiveAdesso(safe?.modalita, safe?.modiStrategia);
    }, [soloTennis, vm.bots]);
    /** le chiusure del tennis passano dalla tua approvazione? (ieri sì) */
    const approvazioneUscite = useMemo(
        () => (soloTennis ? paramsDi('safe')?.tennis_exit_approval : undefined),
        [soloTennis, paramsDi],
    );

    // i fogli parametri sono ESATTAMENTE quelli delle pagine dei bot: due
    // schede diverse per lo stesso servizio sarebbero due verita'.
    //
    // ⚠️ REVIEW 14/09 — MONTATI SOLO SE I PARAMETRI SONO STATI LETTI.
    //
    // Con `rawParams` nullo, `BotParamsSheet` parte da `{}` e al salvataggio
    // manda un oggetto di soli valori predefiniti; `safe_update_params` fa
    // `coalesce(p_params, params)` e lo scrive AL POSTO DI TUTTO. Si
    // perderebbero `strategy_modes` e `tennis_exit_approval`, che
    // `mergeBotParams` non conosce nemmeno: cioe' le due cose che oggi
    // tengono i soldi veri sul solo tennis.
    //
    // La pagina di Safe monta lo stesso componente dietro `if (bot.available)`
    // (`SafeStrategy.tsx:1008`). Qui quel cancello mancava.
    const fogliParametri = useMemo(() => {
        const safeParams = paramsDi('safe');
        const mibeParams = paramsDi('mike');
        const letto = (p: Record<string, unknown> | null) => p != null && Object.keys(p).length > 0;
        return {
            safe: letto(safeParams) ? (
                <BotParamsSheet
                    params={mergeBotParams(safeParams)}
                    rawParams={safeParams}
                    onSave={async (p) => { await updateSafeParams(p); vm.ricarica(); }}
                />
            ) : <ParametriNonLetti bot="Safe" />,
            mike: letto(mibeParams) ? (
                <MikeParamsSheet
                    params={mergeMikeParams(mibeParams)}
                    busy={false}
                    onSave={async (p) => { await updateMikeParams(p); vm.ricarica(); }}
                />
            ) : <ParametriNonLetti bot="Mike" />,
        };
    }, [paramsDi, vm.ricarica]);

    // TASK 4 (18/09) — «ogni bot deve avere i suoi parametri DEDICATI A LUI».
    // Un foglio per RIGA (non per bot): Omega (gap A1 piu' piccolo, riusa
    // `ParamsSheetBase` come la sua pagina), le QUATTRO strategie di Safe
    // (stesso `BotParamsSheet` di sopra, filtrato con `soloStrategia`: stesse
    // chiavi, stesso salvataggio, SOLO i campi di quella strategia — vedi
    // `gruppiDellaStrategia`), i quattro bot tennis (nessun foglio esisteva:
    // costruito sui campi che il SERVIZIO legge davvero, `TENNIS_BOT_REGISTRY`
    // verificato contro il codice Python dei quattro bot). Stesso cancello
    // "parametri non letti" di sopra: qui si scrive l'INTERA colonna, aprirlo
    // prima che il servizio l'abbia dichiarata la sostituirebbe con i default.
    const fogliParametriPerRiga = useMemo(() => {
        const safeParams = paramsDi('safe');
        const omegaParams = paramsDi('omega');
        const letto = (p: Record<string, unknown> | null) => p != null && Object.keys(p).length > 0;
        const out: Partial<Record<InterruttoreId, ReactNode>> = {};

        out.omega = letto(omegaParams) ? (
            <OmegaParamsSheet
                rawParams={omegaParams}
                dailyGoal={vm.bots.find((x) => x.bot === 'omega')?.obiettivoGiorno ?? vm.obiettivo}
                onSaved={() => vm.ricarica()}
                triggerTestId="cr-omega-params-trigger"
            />
        ) : <ParametriNonLetti bot="Omega" />;

        // chiave tipizzata esplicita: un template `safe-${s}` in valore si
        // allarga a `string`, e `out` vuole le chiavi vere di `InterruttoreId`.
        const rigaDiStrategia: Record<StrategiaFiltro, InterruttoreId> = {
            base: 'safe-base', esatto: 'safe-esatto', punta: 'safe-punta', tennis: 'safe-tennis',
        };
        (['base', 'esatto', 'punta', 'tennis'] as const).forEach((s: StrategiaFiltro) => {
            out[rigaDiStrategia[s]] = letto(safeParams) ? (
                <BotParamsSheet
                    params={mergeBotParams(safeParams)}
                    rawParams={safeParams}
                    soloStrategia={s}
                    triggerTestId={`cr-safe-${s}-params-trigger`}
                    onSave={async (p) => { await updateSafeParams(p); vm.ricarica(); }}
                />
            ) : <ParametriNonLetti bot="Safe" />;
        });

        for (const bot of BOT_TENNIS) {
            const rawParams = paramsDi(bot);
            const foglio = letto(rawParams) ? (
                <TennisBotServiceParamsSheet
                    botKey={bot}
                    rawParams={rawParams}
                    onSaved={() => vm.ricarica()}
                />
            ) : <ParametriNonLetti bot={BOT_LABEL[bot]} />;
            // 28/09 (CANTIERE N): l'interruttore delle uscite dei bot tennis
            // e' quello comune della riga (`InterruttoreUscite` in PannelloBot),
            // non piu' un pulsante suo qui accanto al foglio.
            out[bot] = foglio;
        }

        return out;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [paramsDi, vm.bots, vm.obiettivo, vm.ricarica]);

    return (
        <PageShell
            title="Control Room"
            header={<Testata vm={vm} inLive={inLive} />}
            footer="I numeri vengono dai tre servizi: il P&L è il netto di commissione che scrive il servizio, il target per partita lo calcola Omega. Questa pagina non ricalcola nulla."
        >
            {/* MODALITA' — role="alert" e le parole del design system, non un
                riquadro fatto a mano. Dice QUALI strategie usano soldi veri. */}
            <ModeBanner
                mode={inLive ? 'live' : 'paper'}
                testId="cr-banner-modalita"
                liveText={
                    <>Ordini REALI su Betfair per: <b>{
                        vm.bots.filter((b) => b.modalita === 'live')
                            .map((b) => descriviModalita(b)).join(' · ') || 'nessun bot'
                    }</b>. Tutto il resto opera in prova.</>
                }
                paperText="Nessun bot sta usando soldi veri: tutte le operazioni sono simulate sui prezzi live."
            />

            {/* ═══ ZONA 1 — L'OBIETTIVO (hero, una volta sola) + SALDO ═══════
                ⚠️ REVIEW 15/09 — `live` riceve le POSIZIONI aperte con soldi
                veri, non le partite in gioco: in tutta la piattaforma quella
                etichetta significa «posizioni ancora vive, non regolate», e
                Mike, Omega e Safe passano tutti quel conteggio.
                role="progressbar". Il realizzato viene dagli AGGREGATI dei tre
                servizi: prima leggeva solo Omega, e una vincita del tennis non
                la muoveva di un pixel.
                18/09 — l'obiettivo E' modificabile da qui (Task 2): la matita
                apre `ObiettivoEditor`, che scrive con `vm.salvaObiettivo`
                (RPC `omega_update_params({ dailyGoal })`, verificato che NON
                tocca `params`/`mode`). L'AVVISO sul motore non si nasconde:
                Omega legge `daily_goal` a OGNI ciclo (`omega_service.py`), un
                bot in corsa vede il nuovo target dal ciclo successivo. */}
            <div className="grid gap-4 lg:grid-cols-[1.9fr_1fr] items-start">
                <ObiettivoHero
                    dayBar={{
                        dayLabel: etichettaGiorno(giornoOperativo),
                        realized: vm.soldiGiornata.realizzato,
                        // 24/09 - parte stimata del realizzato e posizioni vive ("se chiudo ora")
                        realizedEstimated: vm.soldiGiornata.realizzatoStimato,
                        inProgress: vm.soldiGiornata.inCorso,
                        goal: vm.obiettivo,
                        matches: vm.totali.partite,
                        operations: vm.soldiGiornata.operazioni,
                        won: vm.soldiGiornata.vinte,
                        lost: vm.soldiGiornata.perse,
                        live: vm.totali.conPosizioneLive,
                        openLiability: vm.totali.letti ? vm.totali.liability : null,
                        note: [
                            vm.obiettivoStoricizzato ? null : 'obiettivo non ancora storicizzato per oggi: \u00e8 quello corrente del servizio',
                            vm.soldiGiornata.fonteReale === 'conto'
                                ? 'P&L netto di commissione da Betfair, tutto il conto (bot, manuale app e sito)'
                                : vm.soldiGiornata.fonteReale === 'righe'
                                    ? 'conto Betfair non letto: P&L dalle righe dei bot'
                                    : null,
                        ].filter(Boolean).join(' - '),
                        countsNote: ['Operazioni, vinte e perse: SOLO SOLDI VERI, sui tre bot e sui 4 bot tennis (conteggi reali). «Partite» invece è tutto il programma di oggi, comprese quelle su cui non si è operato.', vm.soldiGiornata.notaContatori].filter(Boolean).join(' '),
                        ids: { day: 'cr-giornata-giorno', line: 'cr-giornata-riga' },
                    } satisfies DayBarProps}
                    composizione={vm.composizioneOggi}
                    manualeSito={vm.manualeSitoBetfair}
                    prova={vm.provaGiornata ?? null}
                    contoEtaS={etaContoS(vm.contoLettoAt, vm.nowMs)}
                    onSalvaObiettivo={vm.salvaObiettivo}
                    avvisoMotore={
                        vm.bots.find((b) => b.bot === 'omega')?.inCorsa
                            ? 'Omega è IN CORSA: il nuovo obiettivo cambia da subito il target per partita che il servizio calcola (letto a ogni ciclo).'
                            : null
                    }
                />
                <SaldoBetfairCard testId="cr-saldo" />
            </div>

            {/* I GIORNI PRECEDENTI HANNO UNA CASA. Tutta questa pagina parla
                della giornata di oggi (ordine dell'utente, 17/09): lo Storico
                è dove si guarda il resto, ed è raggiungibile da qui senza
                cercarlo dentro le schede dei singoli bot. */}
            <div className="flex items-center gap-2 flex-wrap text-[11px] text-white/45 px-1"
                data-testid="cr-riga-storico">
                <span>Questa pagina mostra <b className="text-white/70">solo la giornata di oggi</b>. I giorni precedenti:</span>
                <StoricoLink sport={sport} testId="cr-storico" />
            </div>

            {/* LA PROVA, SEPARATA. 30/09 (P8): la riga «in prova» che stava
                qui (`cr-riga-paper`) e' TOLTA: ripeteva la riga della
                composizione e metteva fra le cifre di oggi partite di giorni
                precedenti regolate oggi (+7,60 = 4 partite di Safe del 26/09).
                La prova vive ora nella corsia PROVA del riquadro Obiettivo
                (per bot: partite di oggi / arretrati regolati oggi) e nella
                corsia PROVA delle tessere sport, mai sommata ai soldi veri. */}

            {/* Due conti sullo stesso denaro che non coincidono: si DICHIARA.
                Scegliere il piu' bello sarebbe la bugia peggiore della pagina. */}
            {vm.soldiGiornata.discordanza && (
                <Card className="glass-card border-orange-500/40 bg-orange-500/10 p-2.5 text-[11.5px] text-orange-200"
                    data-testid="cr-discordanza">
                    <strong className="text-orange-300">Realizzato live: due conti diversi.</strong>{' '}
                    {vm.soldiGiornata.discordanza}. Finché non coincidono, il numero qui sopra è
                    quello calcolato dalla pagina sulle righe dei trade: verifica prima di operarci sopra.
                </Card>
            )}

            {/* CALCIO E TENNIS, SEPARATI: oggi uno opera con soldi veri e
                l'altro in prova. Sommarli sarebbe una bugia. */}
            <SplitSport
                perSport={vm.soldiGiornata.perSport}
                perSportPaper={vm.soldiGiornata.perSportPaper}
                corsie={corsiePerSport(vm.bots)}
                aperte={apertePerSport(vm)}
                prova={vm.provaGiornata ?? null}
                selezionato={sport}
                onSeleziona={setSport}
            />

            <PannelloBot
                righe={righeBot} importi={importi} uscite={uscite} parametri={fogliParametri}
                parametriRiga={fogliParametriPerRiga} comandi={comandi}
                titolo={soloTennis ? 'Bot del tennis' : 'Comando dei bot'}
                ambito={sport ?? 'tutti'}
                serviziAccesi={serviziAccesi}
                ordiniReali={<><RigaOrdiniReali /><RigaFreno /><RigaCapacitaMercati /></>}
                nota={soloTennis ? (
                    <>
                        {/* al FUTURO, perché è quello che il pulsante farà: al
                            presente sarebbe una promessa su uno stato che qui
                            non si controlla. */}
                        <strong className="text-white/80">Avviando da qui</strong> si
                        AGGIUNGE la strategia tennis a <strong className="text-white/80">{fmtMoney(STAKE_TENNIS)}</strong> con
                        entrate automatiche, senza toccare le strategie di calcio già accese (base,
                        esatto, punta restano esattamente come sono ADESSO); opportunità di modello e
                        ordini manuali <strong className="text-white/80">vengono messi in prova</strong>. Mike
                        e Omega non si toccano. Lo stake torna a {fmtMoney(STAKE_TENNIS)} a ogni avvio da qui.
                        <span className="block mt-0.5 text-white/35">
                            «Ferma» invece spegne le aperture di <strong>tutto Safe</strong>, calcio
                            compreso: il servizio è uno solo. Per spegnere solo una strategia di
                            calcio usa la sua riga nella scheda calcio.
                        </span>
                        {cambiTennis.length > 0 && (
                            <span className="block mt-0.5 text-amber-300/90">
                                Rispetto a com&apos;è adesso cambierebbe: {cambiTennis.join(' · ')}.
                            </span>
                        )}
                        {approvazioneUscite === false && (
                            <span className="block mt-0.5 text-amber-300/90" data-testid="cr-tennis-uscite">
                                Le chiusure NON passano dalla tua approvazione: il 14/09 ci passavano.
                                Si cambia da «uscite» sulla riga del tennis qui sotto (o dalla scheda parametri).
                            </span>
                        )}
                        {/* IL PRESENTE, quando è brutto: una riga sola chiamata
                            «Tennis» non deve nascondere il calcio che sta
                            piazzando ordini veri dentro lo stesso servizio. */}
                        {altreLive.length > 0 && (
                            <span className="block mt-1 text-red-300 font-semibold" data-testid="cr-tennis-altre-live">
                                ⚠ ADESSO Safe sta operando con soldi veri anche su: {altreLive.join(', ')}.
                                Sono nello stesso servizio e da questa scheda non si vedono.
                            </span>
                        )}
                    </>
                ) : undefined}
            />

            {/* 28/09 (CANTIERE N): le uscite da approvare dei bot di flusso
                (4 bot tennis, scalper calcio), con i numeri e "approva". Mike,
                Omega e Safe hanno le loro schede proposta di sempre. */}
            <ProposteUsciteFlusso
                proposte={vm.bots.filter((b) => sport == null
                    || (sport === 'tennis') === isBotTennis(b.bot))
                    .flatMap((b) => b.proposteUscite ?? [])}
                nowMs={vm.nowMs}
            />

            {erroreComando && (
                <Card className="glass-card border-red-500/40 bg-red-500/10 p-2.5 text-[11.5px] text-red-200"
                    data-testid="cr-errore-comando">
                    <strong className="text-red-300">Il comando non è andato a buon fine:</strong>{' '}
                    {erroreComando}. Lo stato qui sopra è quello che dice il servizio: se non è
                    cambiato, <strong>il bot sta ancora facendo quello che faceva</strong>.
                </Card>
            )}

            {vm.mikeRestingLive === false && (
                <Card className="glass-card border-orange-500/40 bg-orange-500/10 p-3 flex items-start gap-3" data-testid="cr-mike-resting">
                    <ShieldAlert className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
                    <div className="text-sm">
                        <div className="font-semibold text-orange-300">Mike: uscita appoggiata SPENTA in live</div>
                        <div className="text-white/70">
                            In live l'uscita torna «a mercato»: Mike esegue una strategia <strong>diversa</strong> da
                            quella provata in paper, e il ciclo che in demo chiude in profitto lì chiude in perdita.
                        </div>
                        {/* 30/09 (B2, B4): la valvola agisce solo in live
                            (`service._live_exit_override`); l'avviso NON sparisce
                            in paper (va letto prima di passare a LIVE), dice il modo */}
                        <div className="text-orange-200/90 mt-0.5" data-testid="cr-mike-resting-modo">
                            {(() => {
                                const modo = vm.bots.find((b) => b.bot === 'mike')?.modalita ?? null;
                                return modo === 'live'
                                    ? 'Mike è in LIVE adesso: riguarda i soldi veri di questo momento.'
                                    : modo === 'paper'
                                        ? 'Mike ora è in PAPER: in paper non cambia niente, vale solo quando Mike è in LIVE.'
                                        : 'Modalità di Mike non letta: vale solo quando Mike è in LIVE.';
                            })()}
                        </div>
                    </div>
                </Card>
            )}

            {vm.errore && (
                <Card className="glass-card border-orange-500/30 p-3 text-sm text-orange-300" data-testid="cr-errore">
                    {vm.errore}. I riquadri che dipendono da queste fonti mostrano l'ultimo dato letto, non uno più recente.
                </Card>
            )}

            {/* ═══ ZONA 4 — IL BANCO, tre colonne fisse ═══════════════════════
                Sinistra (larga): le tab. Centro: «Uscite — decidi tu». Destra:
                «Opportunità di modello». Le due colonne di decisione NON si
                nascondono mai, qualunque tab sia aperta a sinistra e qualunque
                sport sia filtrato (ognuna lo dichiara). Su schermi meno larghi
                si impilano: uscite sopra (più urgenti), poi opportunità. */}
            <div className="grid gap-4 items-start
                lg:grid-cols-[minmax(0,1fr)_340px]
                xl:grid-cols-[minmax(0,1fr)_340px_340px]">
                {/* B16 (24/09) — il «Chiudi» di ogni riga, cablato sul SUO bot:
                    il contesto non disegna niente, porta solo il comando. */}
                <ChiusuraRigaContext.Provider value={chiusuraRiga}>
                <Tabs value={scheda} onValueChange={setScheda} className="min-w-0 xl:[grid-column:1]">
                    <TabsList className="w-full justify-start flex-wrap h-auto gap-1 bg-white/[0.03] p-1">
                        <Scheda valore="pre" conta={contaPre} testId="cr-tab-pre">Pre-match</Scheda>
                        <Scheda valore="live" conta={contaLive} testId="cr-tab-live">Live</Scheda>
                        <Scheda valore="aperte" conta={posizioni.length} testId="cr-tab-aperte"
                            evidenzia={posizioni.some((x) => x.modalita === 'live')}>Posizioni aperte</Scheda>
                        <Scheda valore="chiuse" conta={contaChiuse} testId="cr-tab-chiuse">Posizioni chiuse</Scheda>
                    </TabsList>

                    <TabsContent value="pre" className="mt-3">
                        <ElencoPartite
                            gruppi={giornata} stato="pre" scheda={scheda}
                            caricamento={vm.caricamento} nowMs={vm.nowMs}
                            registrazioni={vm.registrazioni} registratori={registratori}
                            operazioni={vm.operazioni}
                        />
                    </TabsContent>

                    <TabsContent value="live" className="mt-3">
                        <ElencoPartite
                            gruppi={giornata} stato="live" scheda={scheda}
                            caricamento={vm.caricamento} nowMs={vm.nowMs}
                            registrazioni={vm.registrazioni} registratori={registratori}
                            operazioni={vm.operazioni}
                            mikeEventi={vm.mikeEventi}
                            copertura={vm.copertura}
                            safe={{
                                // la modalita' la DICHIARA il servizio: non
                                // dichiarata NON vale «paper» (fail-closed).
                                modalita: vm.bots.find((b) => b.bot === 'safe')?.modalita ?? null,
                                statoChiusura: vm.statoChiusura,
                                onCashOut: vm.cashOutEvento,
                                onRiprendi: vm.riprendiEvento,
                            }}
                        />
                    </TabsContent>

                    {/* TASK 5 (18/09) — STESSA GEOMETRIA DI «LIVE»: `SchedaPartita`
                        per ogni partita con una posizione (live o paper), invece
                        della card povera `ColonnaPosizioni`. Il comando "Chiudi"
                        per SINGOLA posizione (che `SchedaPartita` non espone: solo
                        cash-out AGGREGATO di partita via `safe.onCashOut`) resta
                        raggiungibile sotto, per le posizioni che non sono su una
                        partita nota al programma di oggi (fail-open, mai perse). */}
                    <TabsContent value="aperte" className="mt-3">
                        <AperteTab
                            giornata={giornata} posizioni={posizioni} sport={sport}
                            registrazioni={vm.registrazioni} registratori={registratori}
                            operazioni={vm.operazioni} mikeEventi={vm.mikeEventi}
                            safe={{
                                modalita: vm.bots.find((b) => b.bot === 'safe')?.modalita ?? null,
                                statoChiusura: vm.statoChiusura,
                                onCashOut: vm.cashOutEvento,
                                onRiprendi: vm.riprendiEvento,
                            }}
                        />
                    </TabsContent>

                    <TabsContent value="chiuse" className="mt-3">
                        <PosizioniChiuse righe={vm.righeChiuse} chiuse={vm.chiuse} sport={sport}
                            giorno={giornoOperativo} barra={vm.composizioneOggi} />
                    </TabsContent>
                </Tabs>
                </ChiusuraRigaContext.Provider>

                {/* le due colonne di decisione: su schermi < xl si impilano in
                    un'unica colonna di griglia (uscite sopra, poi opportunità);
                    da xl in su diventano due colonne reali (`xl:contents`). */}
                <div className="flex flex-col gap-4 xl:contents">
                    <UsciteColonna vm={vm} filtroSport={sport} />
                    <OpportunitaColonna vm={vm} filtroSport={sport} />
                </div>
            </div>

            {/* ═══ ZONA 5 — DIAGNOSTICA, richiudibile, chiusa di default ═════
                Riassunto a una riga SEMPRE visibile (il `<summary>` nativo non
                si nasconde mai): il dettaglio salto-per-salto si apre solo se
                serve. Logica della Catena INVARIATA. */}
            <details className="glass-card border border-white/10 rounded-xl" data-testid="cr-catena-dettagli">
                <summary className="cursor-pointer select-none px-3 py-2 text-[11px] uppercase tracking-wider text-white/50 flex items-center gap-2">
                    <span>Da Betfair al tuo schermo</span>
                    <span className="font-mono text-[12px] text-white/70">{fmtMs(vm.schermo.schermoMs)}</span>
                    <span className="text-white/30 normal-case tracking-normal">— dettagli ▸</span>
                </summary>
                <div className="px-0 pb-0">
                    <Catena vm={vm} />
                </div>
            </details>
        </PageShell>
    );
}

// 30/09 (P2) — `modalitaPerSport` (una modalita' per sport, presa dal SOLO
// Safe) e' stata tolta: con Mike in LIVE la tessera del calcio diceva PAPER.
// Le tessere ricevono ora le corsie di TUTTI i bot (`corsiePerSport`,
// `lib/giornataCorsie.ts`), con la stessa regola di Safe per strategia
// (`mode` del servizio = tetto, `strategy_modes` = con che soldi).

/** Posizioni aperte per sport, **separate per modalità**: la tessera dice
 *  «2 aperte» e il trader deve sapere se sono soldi veri o una prova. */
function apertePerSport(vm: ReturnType<typeof useControlRoom>):
    Record<SportKey, { live: number; paper: number }> {
    const out = { calcio: { live: 0, paper: 0 }, tennis: { live: 0, paper: 0 } };
    for (const g of vm.giornata) {
        for (const p of g.partite) {
            const s = p.soldi;
            if (!s) continue;
            const k: SportKey = p.sport === 'tennis' ? 'tennis' : 'calcio';
            if (s.live.aperta) out[k].live += 1;
            if (s.paper.aperta) out[k].paper += 1;
        }
    }
    return out;
}

// ------------------------------------------------------------------- catena

/**
 * DA BETFAIR AL PIXEL. Due righe: sopra quanto e' vecchio cio' che il trader
 * sta guardando ADESSO, preso come il PEGGIORE dei tre canali (mostrare il
 * migliore sarebbe un semaforo verde acceso da un sensore su tre); sotto la
 * catena dell'ultima operazione, salto per salto, col collo di bottiglia
 * indicato. Un salto non misurato vale «—», MAI zero: «istantaneo» e «non lo
 * so» sono due affermazioni diverse.
 */
function Catena({ vm }: { vm: ReturnType<typeof useControlRoom> }) {
    const { schermo, ultimaCatena } = vm;
    const totale = totaleCatena(ultimaCatena.salti);
    const nostro = totaleNostro(ultimaCatena.salti);
    const collo = colloDiBottiglia(ultimaCatena.salti);
    const misurati = ultimaCatena.salti.filter((s) => s.ms != null).length;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-catena">
            <div className="px-3 py-2 border-b border-white/10 flex flex-wrap items-baseline gap-x-5 gap-y-1">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Da Betfair al tuo schermo</span>
                <Tratto etichetta="feed" ms={schermo.feedMs} />
                <Tratto etichetta="spinta dai bot" ms={schermo.pushMs} />
                <Tratto etichetta="lettura database" ms={schermo.letturaMs} />
                <span className="ml-auto flex items-baseline gap-1.5" data-testid="cr-schermo">
                    <span className="text-[10px] uppercase tracking-wider text-white/40">quello che vedi e vecchio di</span>
                    <span className={`font-mono text-sm font-bold tabular-nums ${
                        schermo.schermoMs == null ? 'text-orange-400'
                            : schermo.schermoMs <= 5000 ? 'text-emerald-400'
                            : schermo.schermoMs <= 30000 ? 'text-secondary' : 'text-orange-400'
                    }`}>{fmtMs(schermo.schermoMs)}</span>
                </span>
            </div>

            <div className="px-3 py-2 flex flex-wrap items-baseline gap-x-4 gap-y-1" data-testid="cr-catena-operazione">
                <span className="text-[11px] uppercase tracking-wider text-white/60">
                    Ultima operazione
                    {ultimaCatena.trade != null && <span className="text-white/35"> · #{ultimaCatena.trade}</span>}
                </span>
                {misurati === 0 ? (
                    <span className="text-[11px] text-white/40">
                        nessun istante registrato su questa operazione — i tempi si scrivono dalle prossime
                    </span>
                ) : (
                    <>
                        {ultimaCatena.salti.map((s) => (
                            <span key={s.id} className="flex flex-col" title={s.spiega}>
                                <span className={`text-[9px] uppercase tracking-wider ${
                                    s.nostro ? 'text-white/40' : 'text-secondary/70'
                                }`}>{s.nome}</span>
                                <span className={`font-mono text-[13px] font-semibold tabular-nums ${
                                    s.ms == null ? 'text-white/30'
                                        : collo && s.id === collo.id ? 'text-orange-400' : 'text-white/85'
                                }`}>{fmtMs(s.ms)}</span>
                            </span>
                        ))}
                        <span className="ml-auto flex items-baseline gap-3">
                            {collo?.ms != null && (
                                <span className="text-[10.5px] text-orange-300" data-testid="cr-collo">
                                    piu lento: <b>{collo.nome}</b>
                                </span>
                            )}
                            <span className="flex flex-col text-right">
                                <span className="text-[9px] uppercase tracking-wider text-white/40">nostro / totale</span>
                                <span className="font-mono text-[13px] font-semibold tabular-nums">
                                    {fmtMs(nostro)} <span className="text-white/35">/ {fmtMs(totale)}</span>
                                </span>
                            </span>
                        </span>
                    </>
                )}
            </div>
        </Card>
    );
}

function Tratto({ etichetta, ms }: { etichetta: string; ms: number | null }) {
    return (
        <span className="flex items-baseline gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-white/40">{etichetta}</span>
            <span className="font-mono text-[12px] font-semibold tabular-nums text-white/80">{fmtMs(ms)}</span>
        </span>
    );
}

// ------------------------------------------------------------------ testata

function Testata({ vm, inLive }: { vm: ReturnType<typeof useControlRoom>; inLive: boolean }) {
    // ── ZONA 0 (18/09, riordino) — BARRA DI STATO GLOBALE RIDOTTA ────────────
    // L'obiettivo (numero + barra + storicizzazione) ora vive UNA SOLA VOLTA,
    // nella Zona 1 (`ObiettivoHero`, testid `cr-obiettivo`): qui restano SOLO
    // identità, modalità, salute feed, runner, freni, ricarica — grigio se
    // sano, colore solo per anomalie (checklist A5 §3.3 regole 1 e 5).
    // T_P5 (30/09): chi arriva dal canale in tempo reale e chi dal database
    const datiRiassunto = riassuntoDati([
        { nome: 'quote scanner', canale: vm.fonteScan === 'locale' },
        { nome: 'stato scanner', canale: vm.fonteStatoScanner === 'canale' },
        ...(['omega', 'safe', 'mike', 'tennis'] as const).map((b) => ({
            nome: b === 'tennis' ? 'Tennis' : BOT_LABEL[b],
            canale: vm.fonteRighe[b].fonte === 'locale',
        })),
    ]);
    return (
        <header
            className={`sticky top-0 z-30 border-b backdrop-blur ${inLive ? 'border-orange-500/40 bg-orange-950/30' : 'border-white/10 bg-background/80'}`}
            data-testid="cr-testata"
        >
            <div className="container mx-auto max-w-7xl px-4 lg:px-6 py-2.5 flex flex-wrap items-center gap-x-6 gap-y-2">
                <div className="flex items-baseline gap-3">
                    <Link to="/dashboard" className="text-[11px] uppercase tracking-[0.2em] text-white/40 hover:text-white/70">
                        AI Terminal
                    </Link>
                    <span className="font-semibold tracking-wide">CONTROL ROOM</span>
                    <span className="text-xs text-white/50">{dayLabel(romeDay(new Date(vm.nowMs)))}</span>
                </div>

                {/* P3 (30/09) - SOLDI VERI ADESSO: l'esposizione e' quella del
                    CONTO (getAccountFunds, con fonte ed eta'), accanto il rischio
                    LIVE secondo i bot (stima netta dei servizi) e lo scarto se
                    non tornano. La somma LORDA per riga (39,15 contro 9,95 del
                    conto, 30/09) non compare piu'. Mai 0,00 per un dato non
                    letto: «—» e il motivo. */}
                <FasciaSoldiVeri s={vm.soldiVeri} />
                <Freni stop={vm.stopPerdita} />
                <Runner r={vm.runner} fonte={vm.fonteRunner} />
                <Runner r={vm.runnerTennis} fonte={vm.fonteRunnerTennis} tennis />

                <div className="flex items-stretch gap-3" data-testid="cr-bots">
                    {vm.bots.map((b) => <ChipBot key={b.bot} b={b} nowMs={vm.nowMs} />)}
                </div>

                <div className="flex items-center gap-2 text-[11px]" data-testid="cr-feed">
                    <Radio className={`w-3.5 h-3.5 ${FRESCHEZZA_CLS[vm.feedFreschezza]}`} />
                    <span className="text-white/50">Quote dello scanner</span>
                    {/* T_P5 (30/09): «rest» = RIPIEGO (stream fermo), in ambra;
                        prima era grigio e il colore guardava solo l'eta' */}
                    <span className={`font-mono ${TONO_CLS[sorgenteFeed(vm.feedSorgente).tono]}`}
                        data-testid="cr-feed-sorgente">{sorgenteFeed(vm.feedSorgente).testo}</span>
                    <span className={FRESCHEZZA_CLS[vm.feedFreschezza]}>
                        {vm.feedEtaS == null ? FRESCHEZZA_TESTO.ignota : fmtAge(vm.feedEtaS)}
                    </span>
                    {/* T_P5 (30/09): UNA riga per il trader («Dati: tempo reale» o
                        «dal database per: ...»); il dettaglio tecnico di prima resta
                        tutto, dentro il <details> qui sotto (stessi data-testid). */}
                    <span className={TONO_CLS[datiRiassunto.tono]} data-testid="cr-dati-riassunto">
                        {datiRiassunto.testo}
                    </span>
                    <details className="inline" data-testid="cr-dati-dettaglio">
                        <summary className="inline cursor-pointer text-white/30 list-none">dettaglio</summary>
                    {/* STADIO B2c (18/09, raccordo) — sobrio, mai vistoso: quale
                        canale sta parlando ADESSO: "canale locale" se l'ultima
                        riga dello scanner (47336) e' arrivata da li' da poco,
                        altrimenti "database" (realtime/giro dei 30 s). */}
                    <span className="text-white/30" data-testid="cr-fonte-scan"
                        title="da dove arriva l'aggiornamento dello scanner: canale locale (push, ~0 latenza) o database (poll/realtime)">
                        · {vm.fonteScan === 'locale' ? 'canale locale' : 'database'}
                    </span>
                    {/* 25/09 (voce 14): lo STATO dello scanner (eta' del feed qui
                        a sinistra): push `scanner_stato` o riga del database */}
                    <span className="text-white/30" data-testid="cr-fonte-stato-scanner"
                        title="stato dello scanner: canale locale (push scanner_stato, 47336) o database (safe_strategy_status, realtime)">
                        {'\u00b7'} stato {vm.fonteStatoScanner === 'canale' ? 'canale' : 'db'}
                    </span>
                    {/* C6 b (23/09) - lo stesso indicatore per le RIGHE dei tre
                        bot (posizioni e proposte): fonte ed eta' dell'ultima
                        notizia. Canali muti = sempre "database". */}
                    <span className="text-white/30" data-testid="cr-fonte-righe"
                        title="righe dei bot: canale locale (messaggio per riga, piu' fresco del database) o database (poll dei 30 s), con l'eta' dell'ultima notizia">
                        {'·'} righe{(['omega', 'safe', 'mike', 'tennis'] as const).map((b) => {
                            const f = vm.fonteRighe[b];
                            // 24/09: i 4 bot tennis in una voce (canale 47337)
                            const nome = b === 'tennis' ? 'Tennis' : BOT_LABEL[b];
                            return (
                                <span key={b} data-testid={`cr-fonte-righe-${b}`}>
                                    {' '}{nome} {f.fonte === 'locale' ? 'canale' : 'db'}{' '}
                                    {f.etaS == null ? DASH : fmtAge(f.etaS)}
                                </span>
                            );
                        })}
                    </span>
                    </details>
                </div>

                <Button size="sm" variant="ghost" onClick={vm.ricarica} className="h-7 px-2 text-white/60" data-testid="cr-ricarica">
                    <RefreshCw className="w-3.5 h-3.5" />
                </Button>
            </div>
        </header>
    );
}

/**
 * STATO DEL RUNNER — tre stati, non due.
 *
 * 14/09: il battito diceva «2 settembre» mentre il processo girava, perché chi
 * lo scrive vive dentro il framework e il runner era parcheggiato in attesa di
 * eventi. Tre sessioni hanno inseguito un runner morto che stava benissimo.
 * Adesso il runner batte anche da fermo: battito fresco = processo vivo.
 * «Vivo ma senza lavoro» è uno stato LEGITTIMO e si scrive così — un
 * indicatore che grida guasto su un comportamento normale fa ignorare anche i
 * guasti veri.
 */
function Runner({ r, fonte, tennis = false }: {
    r: ReturnType<typeof useControlRoom>['runner'];
    /** 25/09 (voce 6): da dove viene la riga e quanto e' vecchia la notizia */
    fonte: ReturnType<typeof useControlRoom>['fonteRunner'];
    /** il runner TENNIS: solo dal canale 47332 (nessun battito sul database) */
    tennis?: boolean;
}) {
    const testid = tennis ? 'cr-runner-tennis' : 'cr-runner';
    const etichetta = tennis ? 'Runner tennis' : 'Runner';
    const notaFonte = (
        <span className="text-[9.5px] text-white/30" data-testid={`${testid}-fonte`}
            title="canale locale (processo collegato, eta' dell'ultimo messaggio) o database (battito al giro dei 30 s)">
            {fonte.fonte === 'canale' ? 'canale' : 'db'} {fonte.etaS == null ? DASH : fmtAge(fonte.etaS)}
        </span>
    );
    if (r == null) {
        return (
            <div className="flex flex-col" data-testid={testid}
                title={tennis ? 'canale del runner tennis (47332) spento: stato non noto' : 'stato del runner non letto'}>
                <span className="text-[10px] uppercase tracking-wider text-white/40">{etichetta}</span>
                <span className="font-mono text-sm font-semibold text-white/60">{tennis ? 'canale spento' : 'ignoto'}</span>
            </div>
        );
    }
    // «mai battuto» vale GIU', non «non lo so»: un runner che non ha mai dato
    // segno di vita non sta eseguendo niente.
    const fase: RunnerPhase = runnerPhase(r);
    const testo = r.ageS == null ? 'mai avviato' : FASE_RUNNER[fase];
    const cls = fase === 'streaming' ? 'text-emerald-400' : fase === 'idle' ? 'text-secondary' : 'text-orange-400';
    const tetto = tettoRunner(r.mode);
    return (
        <div className="flex flex-col" data-testid={testid}
            title={r.ageS != null ? `ultimo battito ${fmtAge(Math.round(r.ageS))} fa` : 'il runner non ha mai battuto'}>
            <span className="text-[10px] uppercase tracking-wider text-white/40">{etichetta}</span>
            <span className={`font-mono text-sm font-semibold ${cls}`}>
                {testo}
                {/* T_P5 (30/09): «live+paper» era il TETTO del .env del runner
                    (runner.py::heartbeat_mode), non il modo di un bot */}
                {tetto && (
                    <span className="text-white/40" data-testid={`${testid}-tetto`} title={tetto.titolo}>
                        {' · '}{tetto.testo}
                    </span>
                )}
            </span>
            {notaFonte}
        </div>
    );
}

/**
 * L'ULTIMO FRENO. I cap sono spenti per decisione dell'utente: lo stop di
 * perdita giornaliera è l'unica cosa che resta fra un comportamento imprevisto
 * e il conto. Sta in testata perché un freno che nessuno vede non è un freno.
 * Assente si scrive «assente», non «0,00 €».
 */
// P4 (30/09) - «Stop perdita −50,00» era lo stop di SAFE presentato come se
// fosse l'unico: adesso il contenitore `cr-freni` porta lo stop del CONTO e
// quello di ogni bot, con modalita' e punto dove si modifica (`StopPerdita`).
function Freni({ stop }: { stop: ReturnType<typeof useControlRoom>['stopPerdita'] | undefined }) {
    return (
        <div className="flex flex-col" data-testid="cr-freni">
            <StopPerdita stop={stop} />
        </div>
    );
}

/** Il posto del foglio parametri quando lo stato del bot non e' stato letto.
 *  Non un pulsante spento e muto: la ragione, scritta. Aprire quel foglio
 *  adesso permetterebbe un salvataggio che sostituisce TUTTI i parametri. */
function ParametriNonLetti({ bot }: { bot: string }) {
    return (
        <span className="text-[10px] text-orange-300/80 flex items-center gap-1"
            data-testid="cr-parametri-non-letti"
            title={`i parametri di ${bot} non sono ancora stati letti dal servizio: `
                + 'aprire la scheda adesso permetterebbe di salvarli sostituendo '
                + 'quelli veri con i valori predefiniti'}>
            <SlidersHorizontal className="w-3 h-3" />parametri non letti
        </span>
    );
}

/**
 * Il chip di un bot dice tre cose che devono stare insieme: **modalità**
 * (soldi veri o simulati), **se sta girando**, e **quanto è vecchio** il suo
 * ultimo messaggio. Un bot muto non è un bot fermo — e una pagina che non
 * distingue i due casi mente.
 */
function ChipBot({ b, nowMs }: { b: StatoBot; nowMs: number }) {
    const muto = b.canale !== 'connected' || !affidabilePerPiazzare(b.freschezzaPush);
    // T_P5 (30/09) - stessa grammatica per ogni bot: MODO · AGGIORNATO.
    // «senza spinta» non c'e' piu': fermo = "fermo: non invia aggiornamenti"
    // (normale), acceso e muto oltre la sua cadenza = "ACCESO MA MUTO da N s".
    const etaBattito = b.battitoAt == null || !Number.isFinite(Date.parse(b.battitoAt))
        ? null : Math.max(0, (nowMs - Date.parse(b.battitoAt)) / 1000);
    // T_P5b: STATO con le parole del design system, MODO sempre quello
    // dichiarato (LIVE resta rosso anche a bot fermo), uscite se il servizio
    // dichiara che fermare toglie solo le aperture
    const stato = statoChip(b.stato);
    const modo = modoChip(b);
    const uscite = usciteChip(b);
    const pallino = pallinoChip({ inCorsa: b.inCorsa, muto, modalita: b.modalita });
    const agg = aggiornatoChip({ inCorsa: b.inCorsa, etaS: b.etaPushS ?? etaBattito, freschezza: b.freschezzaPush });
    return (
        <div className="flex flex-col gap-0.5" data-testid={`cr-bot-${b.bot}`} title={descriviModalita(b)}>
            <span className={`flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide ${BOT_CLS[b.bot]}`}>
                <Circle className={`w-2 h-2 ${PALLINO_CLS[pallino]}`} data-pallino={pallino} />
                {BOT_LABEL[b.bot]}
            </span>
            <span className="text-[10px] text-white/50">
                {stato && (
                    <><span className={TONO_CLS[stato.tono]} data-testid={`cr-bot-statoservizio-${b.bot}`}>{stato.testo}</span>{' · '}</>
                )}
                <span className={TONO_CLS[modo.tono]} data-testid={`cr-bot-modo-${b.bot}`}>{modo.testo}</span>
                {uscite && (
                    <>{' · '}<span className="text-teal-300" data-testid={`cr-bot-uscite-${b.bot}`} title={uscite.titolo}>{uscite.testo}</span></>
                )}
                {' · '}
                <span className={TONO_CLS[agg.tono]} data-testid={`cr-bot-aggiornato-${b.bot}`}>{agg.testo}</span>
            </span>
            {/* 25/09 (voce 4) - da dove viene lo STATO mostrato (modalita',
                stato, parametri): push del canale o riga del database */}
            {b.fonteStato != null && (
                <span className="text-[9.5px] text-white/30" data-testid={`cr-bot-fonte-${b.bot}`}
                    title="stato del bot: canale locale (push *_stato, piu' fresco del database) o database (giro dei 30 s)">
                    stato {b.fonteStato === 'canale' ? 'canale' : 'db'}{' '}
                    {b.etaStatoS == null ? DASH : fmtAge(b.etaStatoS)}
                </span>
            )}
        </div>
    );
}

// T_P5 (30/09): `EtichettaModalita` sostituita da `modoChip` (testata/paroleImpianto)
const TONO_CLS: Record<Tono, string> = {
    live: 'text-red-300 font-semibold',
    paper: 'text-slate-300',
    neutro: 'text-white/40',
    ok: 'text-emerald-400',
    attenzione: 'text-amber-300',
    allarme: 'text-red-400 font-semibold',
};

// T_P5b: un bot fermo in LIVE non e' grigio come un bot fermo in paper
const PALLINO_CLS: Record<'vivo' | 'muto' | 'fermo-live' | 'fermo', string> = {
    vivo: 'fill-emerald-400 text-emerald-400',
    muto: 'fill-red-400 text-red-400',
    'fermo-live': 'fill-red-400/40 text-red-400/70',
    fermo: 'fill-white/30 text-white/30',
};

/** «LIVE · solo tennis» invece di «LIVE»: con una parte del bot in soldi veri
 *  e una in simulazione, la modalità da sola sarebbe fuorviante. */
function descriviModalita(b: StatoBot): string {
    const m = b.modalita === 'live' ? 'LIVE' : b.modalita === 'paper' ? 'paper' : 'modalità ignota';
    if (b.varianti && b.varianti.length) return `${BOT_LABEL[b.bot]}: ${m} · apre solo ${b.varianti.join(', ')}`;
    return `${BOT_LABEL[b.bot]}: ${m}`;
}

// ------------------------------------------------------- elenco delle partite

/** Una linguetta con il suo conteggio: si vede quale scheda ha qualcosa
 *  dentro senza doverle aprire tutte. */
function Scheda({ valore, conta, children, testId, evidenzia = false }: {
    valore: string; conta: number; children: React.ReactNode;
    testId: string; evidenzia?: boolean;
}) {
    return (
        <TabsTrigger value={valore} data-testid={testId}
            className="text-[11px] uppercase tracking-wider data-[state=active]:bg-white/10">
            {children}
            <span className={`ml-1.5 font-mono text-[10px] ${
                evidenzia ? 'text-red-300 font-bold' : 'text-white/40'
            }`}>{conta}</span>
        </TabsTrigger>
    );
}

/**
 * LE PARTITE DI UNA SCHEDA, raggruppate per campionato e in ordine di orario.
 *
 * Una sola lista per due schede: «Pre-match» e «Live» mostrano le stesse
 * partite in due stati diversi, e duplicare il componente avrebbe voluto dire
 * mantenere due volte le stesse regole di raggruppamento.
 */
function ElencoPartite({
    gruppi, stato, scheda, caricamento, nowMs, registrazioni, registratori, operazioni, copertura,
    safe, mikeEventi,
}: {
    gruppi: GruppoCampionato[];
    stato: 'pre' | 'live';
    scheda: string;
    caricamento: boolean;
    nowMs: number;
    registrazioni: Set<string>;
    /** il registratore di ciascuno sport e' vivo? Senza, REC mentirebbe. */
    registratori: { calcio: boolean | null; tennis: boolean | null };
    operazioni: ReturnType<typeof useControlRoom>['operazioni'];
    /** 17/09 — le partite di Mike col loro modello, gia' lette dall'hook */
    mikeEventi?: ReturnType<typeof useControlRoom>['mikeEventi'];
    copertura?: ReturnType<typeof useControlRoom>['copertura'];
    /** i due gesti dell'utente sulla partita: cash out globale e «Riprendi» */
    safe?: {
        modalita: 'paper' | 'live' | null;
        statoChiusura: (eventId: string) => StatoChiusuraEvento;
        onCashOut: (eventId: string) => Promise<void>;
        onRiprendi: (eventId: string) => Promise<void>;
    };
}) {
    const filtrati = useMemo(() => {
        const out: GruppoCampionato[] = [];
        for (const g of gruppi) {
            const partite = g.partite.filter((p) => p.stato === stato);
            if (partite.length) out.push({ ...g, partite });
        }
        return out;
    }, [gruppi, stato]);

    const quante = filtrati.reduce((n, g) => n + g.partite.length, 0);

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden"
            data-testid={stato === 'pre' ? 'cr-elenco-pre' : 'cr-elenco-live'}>
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60">
                    {stato === 'pre' ? 'Non ancora cominciate' : 'In gioco adesso'}
                </span>
                <span className="text-[11px] text-white/40">
                    {quante} {quante === 1 ? 'partita' : 'partite'} in {filtrati.length}{' '}
                    {filtrati.length === 1 ? 'competizione' : 'competizioni'}
                </span>
            </div>

            {/* CERT. 14/09 — spia del «controllo del gioco»: finché il dato non
                copre le partite, Base e Punta aprono SENZA una condizione che il
                manuale dichiara vincolante. */}
            {copertura && copertura.totale > 0 && copertura.senzaDato > 0 && (
                <div className="px-3 py-2 border-b border-white/10 text-[11px] text-secondary" data-testid="cr-copertura">
                    controllo del gioco: dato presente su {copertura.conDato} partite in gioco su {copertura.totale}
                    {copertura.pct != null && <> ({Math.round(copertura.pct)}%)</>}. Dove manca, quella condizione
                    non ha potuto girare.
                </div>
            )}

            <div className="max-h-[calc(100vh-300px)] overflow-y-auto p-3 space-y-3">
                {caricamento && quante === 0 && (
                    <div className="text-sm text-white/40">lettura del programma di oggi…</div>
                )}
                {!caricamento && quante === 0 && (
                    <EmptyState>
                        {stato === 'pre'
                            ? 'Nessuna partita in attesa: o sono tutte in gioco, o la giornata è finita.'
                            : 'Nessuna partita in gioco adesso. Le prossime sono nella scheda Pre-match.'}
                    </EmptyState>
                )}

                {filtrati.map((g) => (
                    <section key={g.campionato}>
                        <h3 className="text-[11px] uppercase tracking-wider text-white/50 mb-1.5 flex items-center gap-2">
                            <span className="truncate">{g.campionato}</span>
                            <span className="text-white/25 font-mono">{g.partite.length}</span>
                            {g.primoKoMs != null && (
                                <span className="ml-auto text-white/25 font-mono normal-case tracking-normal">
                                    dalle {fmtTime(g.primoKoMs)}
                                </span>
                            )}
                        </h3>
                        <div className="space-y-1.5">
                            {g.partite.map((p) => stato === 'pre' ? (
                                <SchedaPreMatch
                                    key={p.event_id} p={p} scheda={scheda}
                                    mancaS={p.koMs == null ? null : Math.max(0, Math.round((p.koMs - nowMs) / 1000))}
                                    registra={registrazioni.has(p.event_id)}
                                    registratoreVivo={registratori[p.sport === 'tennis' ? 'tennis' : 'calcio']}
                                />
                            ) : (
                                <SchedaPartita
                                    key={p.event_id} p={p} scheda={scheda}
                                    operazioni={operazioni.get(p.event_id) ?? []}
                                    mike={mikeEventi?.get(p.event_id) ?? null}
                                    registra={registrazioni.has(p.event_id)}
                                    registratoreVivo={registratori[p.sport === 'tennis' ? 'tennis' : 'calcio']}
                                    safe={safe ? {
                                        modalita: safe.modalita,
                                        chiusa: safe.statoChiusura(p.event_id),
                                        onCashOut: safe.onCashOut,
                                        onRiprendi: safe.onRiprendi,
                                    } : undefined}
                                />
                            ))}
                        </div>
                    </section>
                ))}
            </div>
        </Card>
    );
}

// ------------------------------------------------------------- tab «Aperte»

/**
 * TASK 5 (18/09) — «Aperte» con la STESSA geometria di «Live»: `SchedaPartita`
 * per ogni partita del programma di oggi che ha una posizione (live o paper),
 * conservando ogni comando che offriva `ColonnaPosizioni`. Una posizione su
 * un evento SCONOSCIUTO al programma (fail-open: non deve MAI sparire) resta
 * visibile in fondo con la vecchia riga compatta, «Chiudi» compreso — perché
 * `SchedaPartita`/`AzioniPartita`/`CashOutPartita` offrono solo il cash-out
 * AGGREGATO di partita (`safe.onCashOut`), non la chiusura di UNA SOLA
 * posizione (`onChiudi(tradeId)`, che quindi resta qui, non perso).
 */
function AperteTab({
    giornata, posizioni, sport, registrazioni, registratori, operazioni, mikeEventi, safe,
}: {
    giornata: GruppoCampionato[];
    posizioni: PosizioneAperta[];
    sport: SportKey | null;
    registrazioni: Set<string>;
    registratori: { calcio: boolean | null; tennis: boolean | null };
    operazioni: ReturnType<typeof useControlRoom>['operazioni'];
    mikeEventi?: ReturnType<typeof useControlRoom>['mikeEventi'];
    safe: {
        modalita: 'paper' | 'live' | null;
        statoChiusura: (eventId: string) => StatoChiusuraEvento;
        onCashOut: (eventId: string) => Promise<void>;
        onRiprendi: (eventId: string) => Promise<void>;
    };
}) {
    // `vm.posizioni` resta l'UNICA fonte di verità di "che cosa è aperto"
    // (stessa lista che alimenta il contatore della linguetta): qui si
    // raggruppa per partita SOLO per scegliere la geometria — una card
    // `SchedaPartita` se l'evento è nel programma di oggi, altrimenti la
    // riga compatta di sempre. Derivarla da `giornata.soldi.aperta` invece
    // di `posizioni` creerebbe una SECONDA fonte di verità, che può
    // divergere (es. la riga cambia prima che il programma la rilegga).
    const { partiteConPosizione, orfane } = useMemo(() => {
        const partiteMap = new Map<string, PartitaGiornata>();
        for (const g of giornata) for (const p of g.partite) partiteMap.set(p.event_id, p);
        const eventiUnici = Array.from(new Set(posizioni.map((p) => p.eventId)));
        const partite = eventiUnici
            .map((id) => partiteMap.get(id))
            .filter((p): p is PartitaGiornata => p != null);
        // posizioni «orfane»: non su nessuna partita nota al programma di
        // oggi — MAI nascoste (una con soldi veri su un evento sconosciuto è
        // comunque una posizione vera, fail-open).
        const senzaScheda = posizioni.filter((p) => !partiteMap.has(p.eventId));
        return { partiteConPosizione: partite, orfane: senzaScheda };
    }, [giornata, posizioni]);
    const live = posizioni.filter((p) => p.modalita === 'live');
    const vuoto = partiteConPosizione.length === 0 && orfane.length === 0;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-posizioni">
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-white/60">
                    Posizioni aperte{sport && <span className="text-white/35 normal-case tracking-normal"> · solo {sport}</span>}
                </span>
                <span className="text-[11px] text-white/40">{posizioni.length}</span>
            </div>

            {live.length > 0 && (
                <div className="px-3 py-1.5 border-b border-orange-500/30 bg-orange-500/10 text-[11px] text-orange-300">
                    {live.length} {live.length === 1 ? 'posizione' : 'posizioni'} con soldi veri
                </div>
            )}

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-2">
                {vuoto && (
                    <EmptyState>{sport
                        ? `Nessuna posizione aperta sul ${sport}. Clicca di nuovo la tessera per rivedere tutti gli sport.`
                        : 'Nessuna posizione aperta. Quando un bot va a mercato, compare qui.'}</EmptyState>
                )}

                {partiteConPosizione.map((p) => (
                    <SchedaPartita
                        key={p.event_id} p={p} scheda="aperte"
                        operazioni={operazioni.get(p.event_id) ?? []}
                        mike={mikeEventi?.get(p.event_id) ?? null}
                        registra={registrazioni.has(p.event_id)}
                        registratoreVivo={registratori[p.sport === 'tennis' ? 'tennis' : 'calcio']}
                        safe={{
                            modalita: safe.modalita,
                            chiusa: safe.statoChiusura(p.event_id),
                            onCashOut: safe.onCashOut,
                            onRiprendi: safe.onRiprendi,
                        }}
                    />
                ))}

                {orfane.length > 0 && (
                    <div className="pt-1">
                        <div className="text-[10px] uppercase tracking-wider text-white/35 px-0.5 pb-1"
                            title="una posizione su un evento non presente nel programma di oggi: mai nascosta">
                            posizioni su una partita fuori dal programma di oggi
                        </div>
                        <div className="space-y-2">
                            {orfane.map((p) => (
                                <RigaPosizioneOrfana key={`${p.bot}-${p.id}`} p={p} />
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </Card>
    );
}

/** la vecchia card compatta di `ColonnaPosizioni` (18/09): sopravvive SOLO
 *  per le posizioni orfane (vedi `AperteTab`) — stesso markup, stessi
 *  testid, stesso comando "Chiudi" per singola posizione: nessuna
 *  regressione sul contenuto, solo sul quando compare. */
function RigaPosizioneOrfana({ p }: {
    p: PosizioneAperta;
}) {
    // 25/09 (residui B17) - "chiudi ora" AL MS prima del clic (ripiego dichiarato)
    const ch = useChiusuraAlMs(p.chiusura, useContext(ChiusuraRigaContext)?.sorgenteLadder ?? null);
    return (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2.5 py-2" data-testid="cr-posizione">
            <div className="flex items-baseline gap-2">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${BOT_CLS[p.bot]}`}>{BOT_LABEL[p.bot]}</span>
                {p.modalita === 'live'
                    ? <Badge variant="outline" className="h-4 px-1 text-[9px] border-orange-500/40 text-orange-300">live</Badge>
                    : <Badge variant="outline" className="h-4 px-1 text-[9px] border-white/20 text-white/40">paper</Badge>}
                <span className="ml-auto font-mono text-[11px] text-white/40">{fmtTime(p.piazzataAt)}</span>
            </div>
            <div className="text-[12px] mt-1 leading-tight">{p.partita}</div>
            <div className="flex items-baseline gap-2 mt-1 text-[11px] text-white/60">
                {p.lato && (
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-wider ${LATO_CLS[p.lato]}`}>
                        {LATO_LABEL[p.lato]}
                    </span>
                )}
                <span className="truncate">{p.selezione ?? DASH}</span>
                <span className="font-mono ml-auto">{fmtOdds(p.prezzo)}</span>
            </div>
            <div className="text-[11px] text-white/40 mt-0.5">
                importo <span className="font-mono">{fmtMoney(p.size)}</span>
                {p.liability != null && <> · liability <span className="font-mono">{fmtMoney(p.liability)}</span></>}
            </div>
            {/* ── IL DETTAGLIO CHE LA SCHEDA DEL BOT MOSTRA GIÀ (17/09) ──
                chiesto/abbinato/residuo, quota di adesso e tick, minuto e
                punteggio d'ingresso, stato ricco, P&L vivo, green-up, modello.
                Tutto dalle stesse righe già in memoria: nessuna lettura in più. */}
            <div className="mt-1 flex items-baseline gap-x-2 gap-y-0.5 flex-wrap">
                <StatoOrdineCompatto riga={p.ordine} testId="cr-pos-stato-ordine" />
                {p.vivo && <QuotaOra v={p.vivo} testId="cr-pos-quota-viva" />}
            </div>
            {p.dettaglio && (
                <div className="mt-0.5 flex items-baseline gap-x-2 gap-y-0.5 flex-wrap"
                    data-testid="cr-pos-dettaglio">
                    <BadgeStato d={p.dettaglio} testId="cr-pos-stato" />
                    <Greenup d={p.dettaglio} testId="cr-pos-greenup" />
                    <Uscita d={p.dettaglio} testId="cr-pos-uscita" />
                    <Ingresso d={p.dettaglio} testId="cr-pos-ingresso" />
                    <Copertura d={p.dettaglio} testId="cr-pos-copertura" />
                    <PnlVivo d={p.dettaglio} testId="cr-pos-pnl-vivo" />
                    <ModelloP d={p.dettaglio} testId="cr-pos-modello" />
                </div>
            )}
            {/* QUANTO VALE CHIUDERE ADESSO — il bot propone solo quando la
                regola del manuale scatta, e fa bene. Ma una posizione può
                essere in profitto molto prima, e va VISTO in continuo invece
                che scoperto per caso. Mostrarlo non cambia la strategia. */}
            {ch && (
                <div className="mt-1.5 pt-1.5 border-t border-white/10 flex items-baseline gap-2 flex-wrap"
                    data-testid="cr-chiusura-viva" data-fonte={ch.fonte ?? ''}>
                    <span className="text-[10px] uppercase tracking-wider text-white/40">chiudi ora</span>
                    {ch.prezzo == null ? (
                        <span className="text-[11px] text-orange-400">prezzo non disponibile</span>
                    ) : (
                        <>
                            <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                ch.lato === 'lay' ? 'bg-rose-500/15 text-rose-300' : 'bg-sky-500/15 text-sky-300'
                            }`}>{ch.lato === 'lay' ? 'banca' : 'punta'}</span>
                            <span className="font-mono text-[12px]" data-testid="cr-chiusura-prezzo">{fmtOdds(ch.prezzo)}</span>
                            <span className={`font-mono text-[13px] tabular-nums ${pnlClass(ch.bloccabile)}`}
                                data-testid="cr-bloccabile"
                                title="P&L garantito chiudendo per intero adesso: identico sui due esiti">
                                {fmtMoney(ch.bloccabile, { signed: true })}
                            </span>
                            {ch.abbinabile != null && (
                                <span className="text-[10px] text-white/35">
                                    {fmtMoney(ch.abbinabile)} abbinabili
                                </span>
                            )}
                            <span className={`text-[10px] ${ch.alMs ? 'text-white/30' : 'text-orange-300/80'}`}
                                data-testid="cr-chiusura-fonte">
                                {ch.testoFonte}
                            </span>
                            {/* B16 (24/09) — stesso posto, stesso testid: ora il
                                comando va al bot DELLA RIGA, non a Safe per tutti */}
                            <BottoneChiudiRiga
                                riga={{
                                    bot: p.bot, id: p.id, eventId: p.eventId,
                                    modalita: p.modalita, stato: p.ordine?.status ?? '',
                                    // 24/09 - scalper: firma della sessione e residuo
                                    ...(p.firma != null ? { firma: p.firma } : {}),
                                    ...(p.residuo ? { residuo: true } : {}),
                                }}
                                testId="cr-chiudi" variante="orfana"
                                prezzoAlClic={() => prezzoAlClic(ch, Date.now())}
                                stimaOra={ch.bloccabile}
                            />
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

// ------------------------------------------------------------------ filtri

function filtra(
    gruppi: GruppoCampionato[],
    opt: { sport?: SportKey | null },
): GruppoCampionato[] {
    if (opt.sport == null) return gruppi;
    const out: GruppoCampionato[] = [];
    for (const g of gruppi) {
        const partite = g.partite.filter(
            (p) => (p.sport === 'tennis' ? 'tennis' : 'calcio') === opt.sport,
        );
        if (partite.length) out.push({ ...g, partite });
    }
    return out;
}
