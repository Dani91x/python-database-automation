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
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RefreshCw, Radio, ShieldAlert, Target, Circle, SlidersHorizontal } from 'lucide-react';
import { PageShell } from '@/components/trading/PageShell';
import { EmptyState } from '@/components/trading/EmptyState';
import { DayBar } from '@/components/trading/DayBar';
import { ModeBanner } from '@/components/trading/ModeBanner';
import { SplitSport, type SportKey } from '@/components/controlroom/SplitSport';
import { SchedaPartita } from '@/components/controlroom/SchedaPartita';
import { pnlClass } from '@/lib/tradeStatus';
import { dayLabel as etichettaGiorno } from '@/lib/dailyHistory';
import { fmtMoney, fmtOdds, fmtAge, fmtTime, DASH } from '@/lib/format';
import { romeDay, dayLabel } from '@/lib/dailyHistory';
import {
    BOT_LABEL, affidabilePerPiazzare,
    type Bot, type GruppoCampionato, type Freschezza,
} from '@/lib/controlRoom';
import { runnerPhase, type RunnerPhase } from '@/lib/safeBot';
import { fmtMs, totaleCatena, totaleNostro, colloDiBottiglia } from '@/lib/controlRoomCatena';
import { SchedaChiusura } from '@/components/controlroom/SchedaChiusura';
import {
    useControlRoom,
    type StatoBot, type PosizioneAperta, type Modalita,
} from '@/components/controlroom/useControlRoom';
import { righeInterruttori } from '@/components/controlroom/righeBot';
import { PannelloBot } from '@/components/controlroom/PannelloBot';
import {
    STAKE_TENNIS, differenzeSoloTennis, altreInLiveAdesso,
} from '@/components/controlroom/soloTennis';
import { PosizioniChiuse } from '@/components/controlroom/PosizioniChiuse';
import { SchedaPreMatch } from '@/components/controlroom/SchedaPreMatch';
import { leggiRitorno, dimenticaRitorno, portaInVista } from '@/lib/ritorno';
import { creaComandiControlRoom } from '@/components/controlroom/comandiBot';
import { interruttoriDiSport, importiInterruttori } from '@/lib/interruttori';
import { BotParamsSheet } from '@/components/safestrategy/BotParamsSheet';
import { MikeParamsSheet } from '@/components/mike/MikeParamsSheet';
import { mergeBotParams, updateSafeParams } from '@/lib/safeBot';
import { mergeMikeParams, updateMikeParams } from '@/lib/mike';

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

const FRESCHEZZA_CLS: Record<Freschezza, string> = {
    fresca: 'text-emerald-400',
    lenta: 'text-secondary',
    vecchia: 'text-orange-400',
    ignota: 'text-orange-400',
};

// ============================================================================

export default function ControlRoom() {
    const vm = useControlRoom();
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
        return { calcio: vivo, tennis: vivo };
    }, [vm.runner]);

    const contaChiuse = useMemo(
        () => vm.chiuse.filter((c) => (sport == null || c.sport === sport) && c.modo === 'live').length,
        [vm.chiuse, sport],
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
        };
    }, [paramsDi, servizioDi, sport, vm.bots, vm.obiettivo, vm.ricarica]);

    // Gli importi: UNO per interruttore, con la chiave che il servizio legge
    // davvero. Se la strategia non ha ancora una chiave sua si mostra quella
    // per LATO e la riga lo DICHIARA (`importoDi`).
    const importi = useMemo(
        () => importiInterruttori(interruttoriDiSport(sport), paramsDi),
        [paramsDi, sport],
    );

    // ── LA PLANCIA, RISTRETTA ALLO SPORT SCELTO ──────────────────────────────
    // «Nella scheda tennis voglio vedere SOLO il bot di tennis» (utente,
    // 15/09). Il tennis lo fa unicamente Safe, con la strategia `tennis`:
    // Mike (Under 3.5) e Omega (risultato esatto) sono calcio e qui non hanno
    // niente da dire. Senza filtro sarebbe l'operatore a doversi ricordare
    // quale delle tre righe riguarda la partita che sta guardando.
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

            {/* LA GIORNATA — la barra vera: obiettivo, contatori, liability.
                ⚠️ REVIEW 15/09 — `live` riceve le POSIZIONI aperte con soldi
                veri, non le partite in gioco: in tutta la piattaforma quella
                etichetta significa «posizioni ancora vive, non regolate», e
                Mike, Omega e Safe passano tutti quel conteggio.
                role="progressbar". Il realizzato viene dagli AGGREGATI dei tre
                servizi: prima leggeva solo Omega, e una vincita del tennis non
                la muoveva di un pixel. */}
            <DayBar
                testId="cr-giornata"
                dayLabel={etichettaGiorno(romeDay(new Date(vm.nowMs)))}
                realized={vm.soldiGiornata.realizzato}
                goal={vm.obiettivo}
                matches={vm.totali.partite}
                operations={vm.soldiGiornata.operazioni}
                won={vm.soldiGiornata.vinte}
                lost={vm.soldiGiornata.perse}
                live={vm.totali.conPosizioneLive}
                openLiability={vm.totali.letti ? vm.totali.liability : null}
                note={vm.obiettivoStoricizzato ? undefined : 'obiettivo non ancora storicizzato per oggi: è quello corrente del servizio'}
                countsNote="Operazioni, vinte e perse: SOLO SOLDI VERI, sui tre bot. «Partite» invece è tutto il programma di oggi, comprese quelle su cui non si è operato."
                ids={{ day: 'cr-giornata-giorno', line: 'cr-giornata-riga' }}
            />

            {/* LA PROVA, SEPARATA. La barra sopra misura l'obiettivo con soldi
                veri; il paper e' esercitazione e non deve spostarla di un
                pixel — il 14/09 la spostava all'indietro. Ma nemmeno si
                nasconde: se il calcio sta perdendo in prova, il trader lo deve
                vedere, in un riquadro che non somma niente. */}
            {(vm.soldiGiornata.realizzatoPaper != null || vm.soldiGiornata.operazioniPaper) && (
                <div className="flex items-baseline gap-2 text-[11px] text-white/45 px-1"
                    data-testid="cr-riga-paper">
                    <span className="uppercase tracking-wider text-[9.5px] px-1.5 py-0.5 rounded bg-white/10">in prova</span>
                    <span className={pnlClass(vm.soldiGiornata.realizzatoPaper)}>
                        {fmtMoney(vm.soldiGiornata.realizzatoPaper, { signed: true })}
                    </span>
                    {vm.soldiGiornata.operazioniPaper != null && (
                        <span>su {vm.soldiGiornata.operazioniPaper} operazioni simulate</span>
                    )}
                    <span className="text-white/25">— non entra nell&apos;obiettivo</span>
                </div>
            )}

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
                modalita={modalitaPerSport(vm)}
                aperte={apertePerSport(vm)}
                selezionato={sport}
                onSeleziona={setSport}
            />

            <PannelloBot
                righe={righeBot} importi={importi} parametri={fogliParametri} comandi={comandi}
                titolo={soloTennis ? 'Bot del tennis' : 'Comando dei bot'}
                ambito={sport ?? 'tutti'}
                serviziAccesi={serviziAccesi}
                nota={soloTennis ? (
                    <>
                        {/* al FUTURO, perché è quello che il pulsante farà: al
                            presente sarebbe una promessa su uno stato che qui
                            non si controlla. */}
                        <strong className="text-white/80">Avviando da qui</strong> parte solo la
                        strategia tennis a <strong className="text-white/80">{fmtMoney(STAKE_TENNIS)}</strong> con
                        entrate automatiche, e tutte le altre strategie di Safe (calcio,
                        opportunità di modello, ordini manuali) <strong className="text-white/80">vengono
                        messe in prova</strong>. Mike e Omega non si toccano. Lo stake torna
                        a {fmtMoney(STAKE_TENNIS)} a ogni avvio da qui.
                        <span className="block mt-0.5 text-white/35">
                            «Ferma» invece spegne le aperture di <strong>tutto Safe</strong>, calcio in
                            prova compreso: il servizio è uno solo.
                        </span>
                        {cambiTennis.length > 0 && (
                            <span className="block mt-0.5 text-amber-300/90">
                                Rispetto a com&apos;è adesso cambierebbe: {cambiTennis.join(' · ')}.
                            </span>
                        )}
                        {approvazioneUscite === false && (
                            <span className="block mt-0.5 text-amber-300/90" data-testid="cr-tennis-uscite">
                                Le chiusure NON passano dalla tua approvazione: il 14/09 ci passavano.
                                Si cambia dalla scheda parametri, non da qui.
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

            {erroreComando && (
                <Card className="glass-card border-red-500/40 bg-red-500/10 p-2.5 text-[11.5px] text-red-200"
                    data-testid="cr-errore-comando">
                    <strong className="text-red-300">Il comando non è andato a buon fine:</strong>{' '}
                    {erroreComando}. Lo stato qui sopra è quello che dice il servizio: se non è
                    cambiato, <strong>il bot sta ancora facendo quello che faceva</strong>.
                </Card>
            )}

            <Catena vm={vm} />

            {vm.mikeRestingLive === false && (
                <Card className="glass-card border-orange-500/40 bg-orange-500/10 p-3 flex items-start gap-3" data-testid="cr-mike-resting">
                    <ShieldAlert className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
                    <div className="text-sm">
                        <div className="font-semibold text-orange-300">Mike: uscita appoggiata SPENTA in live</div>
                        <div className="text-white/70">
                            In live l'uscita torna «a mercato»: Mike esegue una strategia <strong>diversa</strong> da
                            quella provata in paper, e il ciclo che in demo chiude in profitto lì chiude in perdita.
                        </div>
                    </div>
                </Card>
            )}

            {vm.errore && (
                <Card className="glass-card border-orange-500/30 p-3 text-sm text-orange-300" data-testid="cr-errore">
                    {vm.errore}. I riquadri che dipendono da queste fonti mostrano l'ultimo dato letto, non uno più recente.
                </Card>
            )}

            {/* IL BANCO — quattro schede, e a destra il nastro delle uscite che
                NON si nasconde mai: una chiusura matura su soldi veri mentre il
                trader sta guardando un'altra scheda, e deve vederla lo stesso. */}
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px] items-start">
                <Tabs value={scheda} onValueChange={setScheda} className="min-w-0">
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
                            copertura={vm.copertura}
                        />
                    </TabsContent>

                    <TabsContent value="aperte" className="mt-3">
                        <ColonnaPosizioni posizioni={posizioni} onChiudi={vm.chiudi} sport={sport} />
                    </TabsContent>

                    <TabsContent value="chiuse" className="mt-3">
                        <PosizioniChiuse chiuse={vm.chiuse} sport={sport} />
                    </TabsContent>
                </Tabs>

                <NastroSegnali vm={vm} filtroSport={sport} />
            </div>
        </PageShell>
    );
}

/** Con che soldi opera ciascuno sport ADESSO. Il tennis segue la modalità
 *  della strategia `tennis` di Safe; il calcio quella delle sue tre varianti —
 *  se anche una sola è in live, il calcio è in live. */
function modalitaPerSport(vm: ReturnType<typeof useControlRoom>): Record<SportKey, 'paper' | 'live' | null> {
    const safe = vm.bots.find((b) => b.bot === 'safe') ?? null;
    const servizio = safe?.modalita ?? null;
    if (servizio == null) return { calcio: null, tennis: null };

    // ⚠️ `strategy_modes` dice CON CHE SOLDI, `varianti` dice CHI PUÒ APRIRE.
    // Confonderle scriveva «LIVE» accanto al calcio mentre il calcio era in
    // prova — la bugia peggiore che questa tessera possa dire.
    const modi = safe?.modiStrategia ?? null;
    const varianti = safe?.varianti ?? null;
    const apre = (v: string) => varianti == null || varianti.includes(v);

    // il `mode` del servizio e' un TETTO: in paper nessuna voce puo' far
    // uscire un euro vero. E una strategia non dichiarata vale PAPER: ai soldi
    // veri si arriva scrivendolo, mai ereditandolo.
    const con = (v: string): 'paper' | 'live' => {
        if (servizio !== 'live') return 'paper';
        if (!apre(v)) return 'paper';
        return modi?.[v] === 'live' ? 'live' : 'paper';
    };

    return {
        tennis: con('tennis'),
        // il calcio e' in live solo se ALMENO UNA delle sue tre varianti lo e'
        calcio: (['base', 'esatto', 'punta'] as const).some((v) => con(v) === 'live') ? 'live' : 'paper',
    };
}

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
    const obiettivo = vm.obiettivo;
    /**
     * ⚠️ REVIEW 14/09 — QUI C'ERA `vm.realizzato`, e sommava paper e live.
     *
     * `vm.realizzato` è `realized_today` di Omega, che nasce da
     * `omega_aggregates_sql()` SENZA filtro sulla modalità: somma in un numero
     * solo le righe con soldi veri e quelle simulate. Venti pixel più sotto la
     * DayBar mostrava `soldiGiornata.realizzato`, che è solo live — due
     * «realizzato» diversi nella stessa schermata, contro lo stesso obiettivo,
     * e quello in alto (sempre a schermo, `sticky`) conteneva denaro che non
     * esiste.
     *
     * Adesso testata e DayBar leggono LO STESSO numero, quello certificato:
     * `realizzatoOggi.live.totale`. Il paper resta visibile nella sua riga, che
     * dichiara «non entra nell'obiettivo».
     *
     * NON si tocca `omega_aggregates_sql`: quel `realized_today` alimenta anche
     * il target dinamico e le guardie giornaliere del servizio, quindi
     * filtrarlo lato server cambierebbe la strategia.
     */
    const fatto = vm.soldiGiornata.realizzato;
    const resta = obiettivo != null && fatto != null ? obiettivo - fatto : null;
    const pct = obiettivo != null && obiettivo > 0 && fatto != null
        ? Math.max(0, Math.min(100, (fatto / obiettivo) * 100))
        : 0;

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

                {/* obiettivo di giornata — lo stesso di Omega, non un secondo numero */}
                <div className="flex-1 min-w-[230px]" data-testid="cr-obiettivo">
                    <div className="flex items-baseline gap-2 text-sm">
                        <Target className="w-3.5 h-3.5 text-secondary" />
                        <span className="font-mono font-semibold tabular-nums">{fmtMoney(fatto)}</span>
                        <span className="text-xs text-white/50">
                            di {fmtMoney(obiettivo)}
                            {resta != null && resta > 0 && <> · restano <span className="font-mono">{fmtMoney(resta)}</span></>}
                            {resta != null && resta <= 0 && <> · <span className="text-emerald-400">obiettivo centrato</span></>}
                        </span>
                    </div>
                    <div className="h-1.5 mt-1 rounded-sm bg-white/10 overflow-hidden">
                        <div className="h-full bg-secondary transition-[width] duration-500" style={{ width: `${pct}%` }} />
                    </div>
                    {!vm.obiettivoStoricizzato && obiettivo != null && (
                        <div className="text-[10px] text-white/40 mt-0.5">obiettivo non ancora storicizzato per oggi: è quello corrente del servizio</div>
                    )}
                </div>

                {/* ESPOSIZIONE = SOLDI VERI IMPEGNATI. Prima sommava anche la
                    responsabilità delle posizioni simulate: dichiarava un
                    rischio che non esisteva (393,68 € contro 77,71 € reali).
                    Su un banco vero è il numero più pericoloso della pagina. */}
                {/* ⚠️ REVIEW 15/09 — finché i trade non sono letti questi numeri
                    NON sono zero: sono ignoti. Scrivere «0,00 €» sul numero
                    più pericoloso della pagina, durante il caricamento o dopo
                    una lettura fallita, è un'assenza travestita da sicurezza. */}
                <Dato etichetta="Esposizione"
                    valore={vm.totali.letti ? fmtMoney(vm.totali.liability) : DASH}
                    nota={!vm.totali.letti ? 'posizioni non ancora lette'
                        : vm.totali.liabilityPaper > 0
                            ? `+ ${fmtMoney(vm.totali.liabilityPaper)} in prova, non sono soldi veri`
                            : undefined} />
                <Dato etichetta="Con posizione"
                    valore={vm.totali.letti
                        ? `${vm.totali.conPosizioneLive} / ${vm.totali.partite}`
                        : `${DASH} / ${vm.totali.partite}`}
                    nota={vm.totali.letti && vm.totali.conPosizione > vm.totali.conPosizioneLive
                        ? `${vm.totali.conPosizione - vm.totali.conPosizioneLive} in prova`
                        : undefined} />
                <Freni freni={vm.freni} />
                <Runner r={vm.runner} />

                <div className="flex items-stretch gap-3" data-testid="cr-bots">
                    {vm.bots.map((b) => <ChipBot key={b.bot} b={b} />)}
                </div>

                <div className="flex items-center gap-2 text-[11px]" data-testid="cr-feed">
                    <Radio className={`w-3.5 h-3.5 ${FRESCHEZZA_CLS[vm.feedFreschezza]}`} />
                    <span className="text-white/50">feed</span>
                    <span className="font-mono">{vm.feedSorgente ?? DASH}</span>
                    <span className={FRESCHEZZA_CLS[vm.feedFreschezza]}>
                        {vm.feedEtaS == null ? FRESCHEZZA_TESTO.ignota : fmtAge(vm.feedEtaS)}
                    </span>
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
function Runner({ r }: { r: ReturnType<typeof useControlRoom>['runner'] }) {
    if (r == null) {
        return (
            <div className="flex flex-col" data-testid="cr-runner" title="stato del runner non letto">
                <span className="text-[10px] uppercase tracking-wider text-white/40">Runner</span>
                <span className="font-mono text-sm font-semibold text-white/60">ignoto</span>
            </div>
        );
    }
    // «mai battuto» vale GIU', non «non lo so»: un runner che non ha mai dato
    // segno di vita non sta eseguendo niente.
    const fase: RunnerPhase = runnerPhase(r);
    const testo = r.ageS == null ? 'mai avviato' : FASE_RUNNER[fase];
    const cls = fase === 'streaming' ? 'text-emerald-400' : fase === 'idle' ? 'text-secondary' : 'text-orange-400';
    return (
        <div className="flex flex-col" data-testid="cr-runner"
            title={r.ageS != null ? `ultimo battito ${fmtAge(Math.round(r.ageS))} fa` : 'il runner non ha mai battuto'}>
            <span className="text-[10px] uppercase tracking-wider text-white/40">Runner</span>
            <span className={`font-mono text-sm font-semibold ${cls}`}>
                {testo}
                {r.mode && <span className="text-white/40"> · {r.mode.toLowerCase()}</span>}
            </span>
        </div>
    );
}

/**
 * L'ULTIMO FRENO. I cap sono spenti per decisione dell'utente: lo stop di
 * perdita giornaliera è l'unica cosa che resta fra un comportamento imprevisto
 * e il conto. Sta in testata perché un freno che nessuno vede non è un freno.
 * Assente si scrive «assente», non «0,00 €».
 */
function Freni({ freni }: { freni: ReturnType<typeof useControlRoom>['freni'] }) {
    const soglia = freni?.daily_loss_stop;
    const scattato = freni?.loss_stop_active === true;
    const noto = typeof soglia === 'number' && Number.isFinite(soglia);
    return (
        <div className="flex flex-col" data-testid="cr-freni" title="stop per perdita giornaliera: oltre questa soglia il bot non apre più">
            <span className="text-[10px] uppercase tracking-wider text-white/40">Stop perdita</span>
            <span className={`font-mono text-sm font-semibold tabular-nums ${
                scattato ? 'text-red-400' : noto ? 'text-white/90' : 'text-orange-400'
            }`}>
                {scattato ? 'SCATTATO' : noto ? fmtMoney(soglia) : 'assente'}
            </span>
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

function Dato({ etichetta, valore, nota }: {
    etichetta: string; valore: string;
    /** seconda riga, per quello che NON va sommato al valore principale */
    nota?: string;
}) {
    return (
        <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider text-white/40">{etichetta}</span>
            <span className="font-mono text-sm font-semibold tabular-nums">{valore}</span>
            {nota && <span className="text-[9.5px] text-white/30 leading-tight">{nota}</span>}
        </div>
    );
}

/**
 * Il chip di un bot dice tre cose che devono stare insieme: **modalità**
 * (soldi veri o simulati), **se sta girando**, e **quanto è vecchio** il suo
 * ultimo messaggio. Un bot muto non è un bot fermo — e una pagina che non
 * distingue i due casi mente.
 */
function ChipBot({ b }: { b: StatoBot }) {
    const muto = b.canale !== 'connected' || !affidabilePerPiazzare(b.freschezzaPush);
    return (
        <div className="flex flex-col gap-0.5" data-testid={`cr-bot-${b.bot}`} title={descriviModalita(b)}>
            <span className={`flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide ${BOT_CLS[b.bot]}`}>
                <Circle className={`w-2 h-2 ${b.inCorsa && !muto ? 'fill-emerald-400 text-emerald-400' : 'fill-orange-400 text-orange-400'}`} />
                {BOT_LABEL[b.bot]}
            </span>
            <span className="text-[10px] text-white/50">
                <EtichettaModalita modalita={b.modalita} />
                {' · '}
                {b.etaPushS == null
                    ? <span className="text-orange-400">senza spinta</span>
                    : <span className={FRESCHEZZA_CLS[b.freschezzaPush]}>{fmtAge(b.etaPushS)}</span>}
            </span>
        </div>
    );
}

function EtichettaModalita({ modalita }: { modalita: Modalita | null }) {
    if (modalita === 'live') return <span className="text-orange-300 font-semibold">LIVE</span>;
    if (modalita === 'paper') return <span className="text-white/60">paper</span>;
    return <span className="text-orange-400">modalità ignota</span>;
}

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
    copertura?: ReturnType<typeof useControlRoom>['copertura'];
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
                                    registra={registrazioni.has(p.event_id)}
                                    registratoreVivo={registratori[p.sport === 'tennis' ? 'tennis' : 'calcio']}
                                />
                            ))}
                        </div>
                    </section>
                ))}
            </div>
        </Card>
    );
}

// ---------------------------------------------------------- nastro dei segnali

/**
 * IL NASTRO. Qui arrivano le proposte dei tre bot e da qui si approva o si
 * ignora. Il cancelletto vero — i bot che PROPONGONO invece di piazzare —
 * richiede lo stato `proposed` nelle tre code, che i proprietari dei bot
 * stanno aggiungendo: finché non c'è, la pagina lo DICHIARA invece di
 * mostrare un nastro vuoto che sembrerebbe «nessun segnale».
 */
function NastroSegnali({ vm, filtroSport }: {
    vm: ReturnType<typeof useControlRoom>;
    /** serve SOLO a dirlo a schermo: il nastro non si filtra mai. */
    filtroSport: SportKey | null;
}) {
    const bloccati = vm.bots.filter((b) => b.canale !== 'connected' || !affidabilePerPiazzare(b.freschezzaPush));
    const urgenti = vm.proposte.filter((p) => p.proposta.payload?.urgente === true).length;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-nastro">
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Uscite — decidi tu</span>
                <span className="text-[11px] text-white/40">
                    {vm.proposte.length} in attesa
                    {urgenti > 0 && <span className="text-orange-300 font-semibold"> · {urgenti} urgenti</span>}
                </span>
            </div>

            {/* IL NASTRO NON SI FILTRA MAI. Un'uscita matura su una posizione
                con soldi veri: nasconderla perché il trader sta guardando
                l'altro sport sarebbe il modo piu' veloce di perdere un
                profitto. Qui si DICHIARA che restano tutte. */}
            {filtroSport != null && (
                <div className="px-3 py-1.5 border-b border-white/10 text-[10.5px] text-white/45"
                    data-testid="cr-nastro-non-filtrato">
                    Il filtro <span className="text-white/70">{filtroSport}</span> non tocca questo nastro:
                    le uscite compaiono da entrambi gli sport.
                </div>
            )}

            {bloccati.length > 0 && (
                <div className="px-3 py-2 border-b border-white/10 text-[11px] text-orange-300" data-testid="cr-bot-muti">
                    {bloccati.map((b) => BOT_LABEL[b.bot]).join(', ')}: nessuna spinta recente.
                    I numeri di {bloccati.length > 1 ? 'questi bot' : 'questo bot'} potrebbero essere vecchi —
                    non si piazza su dati di cui non conosciamo l&apos;età.
                </div>
            )}

            {/* tolleranza: oltre questo scostamento dal prezzo della proposta
                l&apos;approvazione si spegne. È una leva del trader, non una
                costante sepolta. */}
            <div className="px-3 py-1.5 border-b border-white/10 flex items-center gap-2 text-[11px] text-white/50">
                <label htmlFor="cr-slippage">scostamento massimo dal prezzo della proposta</label>
                <input
                    id="cr-slippage" type="number" step="0.5" min="0.5" max="20"
                    value={vm.slippagePct}
                    onChange={(e) => vm.setSlippagePct(Math.max(0.5, Number(e.target.value) || 2))}
                    className="w-16 px-1.5 py-0.5 rounded border border-white/15 bg-white/5 font-mono text-right text-white/90"
                />
                <span>%</span>
            </div>

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-2.5">
                {vm.proposte.length === 0 && (
                    <EmptyState>
                        <span className="font-semibold block mb-1">Nessuna uscita da decidere</span>
                        Il bot apre da solo. Quando matura un&apos;uscita non la esegue: la propone qui, con il prezzo
                        che si aggiorna da solo, l&apos;importo davvero abbinabile e il confronto fra chiudere e tenere.
                        Le urgenti stanno in cima.
                    </EmptyState>
                )}
                {vm.proposte.map((pv) => (
                    <SchedaChiusura
                        key={pv.proposta.id}
                        proposta={pv.proposta}
                        vivo={pv.vivo}
                        etaQuoteS={pv.etaQuoteS}
                        etaScannerS={vm.feedEtaS}
                        bloccabileOra={pv.bloccabileOra}
                        slippagePct={vm.slippagePct}
                        onApprova={vm.approva}
                        onIgnora={vm.ignora}
                    />
                ))}
            </div>
        </Card>
    );
}

// ------------------------------------------------------- colonna posizioni

function ColonnaPosizioni({ posizioni, onChiudi, sport }: {
    posizioni: PosizioneAperta[];
    onChiudi: (tradeId: number) => Promise<void>;
    sport: SportKey | null;
}) {
    const live = posizioni.filter((p) => p.modalita === 'live');
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
                {posizioni.length === 0 && (
                    <EmptyState>{sport
                        ? `Nessuna posizione aperta sul ${sport}. Clicca di nuovo la tessera per rivedere tutti gli sport.`
                        : 'Nessuna posizione aperta. Quando un bot va a mercato, compare qui.'}</EmptyState>
                )}
                {posizioni.map((p) => (
                    <div key={`${p.bot}-${p.id}`} className="rounded border border-white/10 bg-white/[0.02] px-2.5 py-2" data-testid="cr-posizione">
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
                            {p.liability != null && <> · responsabilità <span className="font-mono">{fmtMoney(p.liability)}</span></>}
                        </div>
                        {/* QUANTO VALE CHIUDERE ADESSO — il bot propone solo quando la
                            regola del manuale scatta, e fa bene. Ma una posizione può
                            essere in profitto molto prima, e va VISTO in continuo invece
                            che scoperto per caso. Mostrarlo non cambia la strategia. */}
                        {p.chiusura && (
                            <div className="mt-1.5 pt-1.5 border-t border-white/10 flex items-baseline gap-2 flex-wrap"
                                data-testid="cr-chiusura-viva">
                                <span className="text-[10px] uppercase tracking-wider text-white/40">chiudi ora</span>
                                {p.chiusura.prezzo == null ? (
                                    <span className="text-[11px] text-orange-400">prezzo non disponibile</span>
                                ) : (
                                    <>
                                        <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                            p.chiusura.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                                        }`}>{p.chiusura.lato === 'lay' ? 'banca' : 'punta'}</span>
                                        <span className="font-mono text-[12px]">{fmtOdds(p.chiusura.prezzo)}</span>
                                        <span className={`font-mono text-[13px] tabular-nums ${pnlClass(p.chiusura.bloccabile)}`}
                                            data-testid="cr-bloccabile"
                                            title="P&L garantito chiudendo per intero adesso: identico sui due esiti">
                                            {fmtMoney(p.chiusura.bloccabile, { signed: true })}
                                        </span>
                                        {p.chiusura.abbinabile != null && (
                                            <span className="text-[10px] text-white/35">
                                                {fmtMoney(p.chiusura.abbinabile)} abbinabili
                                            </span>
                                        )}
                                        <Button
                                            size="sm" variant="ghost"
                                            onClick={() => void onChiudi(p.id)}
                                            className="ml-auto h-6 px-2 text-[10px] uppercase tracking-wider border border-white/15 text-white/70 hover:text-white hover:border-emerald-500/50"
                                            data-testid="cr-chiudi"
                                        >Chiudi</Button>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </Card>
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
