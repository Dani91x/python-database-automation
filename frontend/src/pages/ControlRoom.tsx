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
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RefreshCw, Radio, ShieldAlert, Target, Circle } from 'lucide-react';
import { PageShell } from '@/components/trading/PageShell';
import { EmptyState } from '@/components/trading/EmptyState';
import { fmtMoney, fmtOdds, fmtAge, fmtTime, DASH } from '@/lib/format';
import { romeDay, dayLabel } from '@/lib/dailyHistory';
import {
    BOT_LABEL, affidabilePerPiazzare,
    type Bot, type GruppoCampionato, type PartitaGiornata, type Freschezza,
} from '@/lib/controlRoom';
import { runnerPhase, type RunnerPhase } from '@/lib/safeBot';
import { SchedaChiusura } from '@/components/controlroom/SchedaChiusura';
import { useControlRoom, type StatoBot, type PosizioneAperta, type Modalita } from '@/components/controlroom/useControlRoom';

// --------------------------------------------------------------- vocabolario
// Le parole del trader, in italiano, in un posto solo.

const LATO_LABEL: Record<'back' | 'lay', string> = { back: 'Punta', lay: 'Banca' };

const LATO_CLS: Record<'back' | 'lay', string> = {
    back: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    lay: 'bg-pink-500/15 text-pink-300 border-pink-500/30',
};

const BOT_CLS: Record<Bot, string> = {
    omega: 'text-primary',
    safe: 'text-secondary',
    mike: 'text-teal-300',
};

const BOT_SIGLA: Record<Bot, string> = { omega: 'Ω', safe: 'S', mike: 'M' };

const FRESCHEZZA_TESTO: Record<Freschezza, string> = {
    fresca: 'fresco',
    lenta: 'in ritardo',
    vecchia: 'vecchio',
    ignota: 'età sconosciuta',
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

const FRESCHEZZA_CLS: Record<Freschezza, string> = {
    fresca: 'text-emerald-400',
    lenta: 'text-secondary',
    vecchia: 'text-orange-400',
    ignota: 'text-orange-400',
};

// ============================================================================

export default function ControlRoom() {
    const vm = useControlRoom();
    const [soloConSegnali, setSoloConSegnali] = useState(false);
    const [soloLive, setSoloLive] = useState(false);

    const giornata = useMemo(() => filtra(vm.giornata, { soloLive, soloConSegnali }), [vm.giornata, soloLive, soloConSegnali]);

    const inLive = vm.bots.some((b) => b.modalita === 'live');

    return (
        <PageShell
            title="Control Room"
            header={<Testata vm={vm} inLive={inLive} />}
            footer="I numeri vengono dai tre servizi: il P&L è il netto di commissione che scrive il servizio, il target per partita lo calcola Omega. Questa pagina non ricalcola nulla."
        >
            {inLive && (
                <Card className="glass-card border-orange-500/40 bg-orange-500/10 p-3 flex items-start gap-3" data-testid="cr-banner-live">
                    <ShieldAlert className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
                    <div className="text-sm">
                        <div className="font-semibold text-orange-300">Sono in gioco soldi veri</div>
                        <div className="text-white/70">
                            {vm.bots.filter((b) => b.modalita === 'live').map((b) => descriviModalita(b)).join(' · ')}
                        </div>
                    </div>
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
                    </div>
                </Card>
            )}

            {vm.errore && (
                <Card className="glass-card border-orange-500/30 p-3 text-sm text-orange-300" data-testid="cr-errore">
                    {vm.errore}. I riquadri che dipendono da queste fonti mostrano l'ultimo dato letto, non uno più recente.
                </Card>
            )}

            <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)_330px] items-start">
                <ColonnaPartite
                    gruppi={giornata}
                    totali={vm.totali}
                    caricamento={vm.caricamento}
                    soloLive={soloLive} setSoloLive={setSoloLive}
                    soloConSegnali={soloConSegnali} setSoloConSegnali={setSoloConSegnali}
                    copertura={vm.copertura}
                />
                <NastroSegnali vm={vm} />
                <ColonnaPosizioni posizioni={vm.posizioni} />
            </div>
        </PageShell>
    );
}

// ------------------------------------------------------------------ testata

function Testata({ vm, inLive }: { vm: ReturnType<typeof useControlRoom>; inLive: boolean }) {
    const obiettivo = vm.obiettivo;
    const fatto = vm.realizzato;
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

                <Dato etichetta="Esposizione" valore={fmtMoney(vm.totali.liability)} />
                <Dato etichetta="Con posizione" valore={`${vm.totali.conPosizione} / ${vm.totali.partite}`} />
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

function Dato({ etichetta, valore }: { etichetta: string; valore: string }) {
    return (
        <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-wider text-white/40">{etichetta}</span>
            <span className="font-mono text-sm font-semibold tabular-nums">{valore}</span>
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

// ------------------------------------------------------- colonna delle partite

function ColonnaPartite({
    gruppi, totali, caricamento, soloLive, setSoloLive, soloConSegnali, setSoloConSegnali, copertura,
}: {
    gruppi: GruppoCampionato[];
    totali: ReturnType<typeof useControlRoom>['totali'];
    caricamento: boolean;
    soloLive: boolean; setSoloLive: (v: boolean) => void;
    soloConSegnali: boolean; setSoloConSegnali: (v: boolean) => void;
    copertura: ReturnType<typeof useControlRoom>['copertura'];
}) {
    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-partite">
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60">
                    Partite di oggi · {totali.partite}
                </span>
                <span className="text-[11px] text-white/40">{totali.live} in gioco</span>
            </div>

            <div className="px-3 py-2 border-b border-white/10 flex flex-wrap gap-1.5">
                <Filtro attivo={soloLive} onClick={() => setSoloLive(!soloLive)}>in gioco</Filtro>
                <Filtro attivo={soloConSegnali} onClick={() => setSoloConSegnali(!soloConSegnali)}>con operazioni</Filtro>
            </div>

            {/* CERT. 14/09 — spia del «controllo del gioco»: finché il dato non
                copre le partite, Base e Punta aprono SENZA una condizione che
                il manuale dichiara vincolante. Non compare se non c'è niente
                da dire (nessuna partita in gioco). */}
            {copertura.totale > 0 && copertura.senzaDato > 0 && (
                <div className="px-3 py-2 border-b border-white/10 text-[11px] text-secondary" data-testid="cr-copertura">
                    controllo del gioco: dato presente su {copertura.conDato} partite in gioco su {copertura.totale}
                </div>
            )}

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-4">
                {caricamento && gruppi.length === 0 && <div className="text-sm text-white/40">lettura del programma di oggi…</div>}
                {!caricamento && gruppi.length === 0 && (
                    <EmptyState>Il feed non ha partite di calcio per oggi, o i filtri le escludono tutte.</EmptyState>
                )}
                {gruppi.map((g) => (
                    <section key={g.campionato}>
                        <h3 className="text-[11px] uppercase tracking-wider text-white/50 mb-1.5 flex items-center gap-2">
                            {g.campionato}
                            <span className="flex-1 h-px bg-white/10" />
                        </h3>
                        <div className="space-y-1.5">
                            {g.partite.map((p) => <RigaPartita key={p.event_id} p={p} />)}
                        </div>
                    </section>
                ))}
            </div>
        </Card>
    );
}

function Filtro({ attivo, onClick, children }: { attivo: boolean; onClick: () => void; children: React.ReactNode }) {
    return (
        <button
            type="button" onClick={onClick} aria-pressed={attivo}
            className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${
                attivo ? 'border-primary/60 text-primary bg-primary/10' : 'border-white/15 text-white/50 hover:text-white/80'
            }`}
        >{children}</button>
    );
}

function RigaPartita({ p }: { p: PartitaGiornata }) {
    const soldi = p.soldi;
    const net = soldi?.netPnl ?? null;
    const bordo = p.stato === 'live' ? 'border-l-secondary' : soldi?.aperta ? 'border-l-primary' : 'border-l-white/15';

    return (
        <div className={`rounded border border-white/10 border-l-[3px] ${bordo} bg-white/[0.02] px-2.5 py-2`} data-testid="cr-partita">
            <div className="flex items-start justify-between gap-2">
                <span className="text-[13px] font-medium leading-tight">
                    <span className="text-white/30 mr-1" aria-label={p.sport === 'tennis' ? 'tennis' : 'calcio'}>
                        {p.sport === 'tennis' ? '🎾' : '⚽'}
                    </span>
                    {p.nome}
                </span>
                <StatoPill p={p} />
            </div>

            <div className="flex items-end justify-between gap-2 mt-1.5">
                <Mini etichetta="Target" valore={p.target ? fmtMoney(p.target.valore) : DASH}
                    nota={p.target?.fonte === 'ripiego' ? 'calcolato dalla pagina: il servizio non lo pubblica' : undefined} />
                <Mini etichetta="P&L" valore={net == null ? DASH : fmtMoney(net)}
                    cls={net == null ? 'text-white/40' : net >= 0 ? 'text-emerald-400' : 'text-red-400'} />
                {p.stato === 'live' && (
                    <span className="flex flex-col" data-testid="cr-latenza"
                        title="da quanto è vecchio il prezzo su cui si opererebbe (istante in cui lo scanner ha letto le quote)">
                        <span className="text-[9px] uppercase tracking-wider text-white/40">Quote</span>
                        <span className={`font-mono text-[13px] font-semibold ${FRESCHEZZA_CLS[p.freschezzaQuote]}`}>
                            {p.latenzaQuoteS == null ? DASH : fmtAge(p.latenzaQuoteS)}
                        </span>
                    </span>
                )}
                <span className="flex gap-1" title="bot che hanno operato su questa partita">
                    {(['omega', 'safe', 'mike'] as Bot[]).map((b) => (
                        <span key={b}
                            className={`w-4 h-4 rounded-sm grid place-items-center text-[9px] font-bold ${
                                soldi?.bots.includes(b) ? `bg-white/10 ${BOT_CLS[b]}` : 'bg-white/[0.04] text-white/20'
                            }`}
                        >{BOT_SIGLA[b]}</span>
                    ))}
                </span>
            </div>

            {p.avanzamento != null && (
                <div className="h-1 mt-1.5 rounded-sm bg-white/10 overflow-hidden">
                    <div className={`h-full ${net != null && net < 0 ? 'bg-red-400' : 'bg-emerald-400'}`}
                        style={{ width: `${p.avanzamento}%` }} />
                </div>
            )}
        </div>
    );
}

function StatoPill({ p }: { p: PartitaGiornata }) {
    if (p.stato === 'live') {
        // tennis: nessun minuto, il punteggio E' l'informazione (set · game)
        const testa = p.minuto != null ? `${p.minuto}′` : p.punteggio ? '' : 'in gioco';
        return (
            <span className="shrink-0 flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded bg-secondary/15 text-secondary">
                <Circle className="w-1.5 h-1.5 fill-current" />
                {testa}
                {p.punteggio && <span>{testa ? ' ' : ''}{p.punteggio}</span>}
            </span>
        );
    }
    if (p.stato === 'pre') {
        return (
            <span className="shrink-0 text-[11px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-white/50">
                {p.koMs != null ? fmtTime(p.koMs) : 'orario ignoto'}
            </span>
        );
    }
    return <span className="shrink-0 text-[11px] px-1.5 py-0.5 rounded bg-white/5 text-white/30">conclusa</span>;
}

function Mini({ etichetta, valore, cls, nota }: { etichetta: string; valore: string; cls?: string; nota?: string }) {
    return (
        <span className="flex flex-col" title={nota}>
            <span className="text-[9px] uppercase tracking-wider text-white/40">{etichetta}{nota ? ' *' : ''}</span>
            <span className={`font-mono text-[13px] font-semibold tabular-nums ${cls ?? ''}`}>{valore}</span>
        </span>
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
function NastroSegnali({ vm }: { vm: ReturnType<typeof useControlRoom> }) {
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

function ColonnaPosizioni({ posizioni }: { posizioni: PosizioneAperta[] }) {
    const live = posizioni.filter((p) => p.modalita === 'live');
    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="cr-posizioni">
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Posizioni aperte</span>
                <span className="text-[11px] text-white/40">{posizioni.length}</span>
            </div>

            {live.length > 0 && (
                <div className="px-3 py-1.5 border-b border-orange-500/30 bg-orange-500/10 text-[11px] text-orange-300">
                    {live.length} {live.length === 1 ? 'posizione' : 'posizioni'} con soldi veri
                </div>
            )}

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-2">
                {posizioni.length === 0 && (
                    <EmptyState>Nessuna posizione aperta. Quando un bot va a mercato, compare qui.</EmptyState>
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
                    </div>
                ))}
            </div>
        </Card>
    );
}

// ------------------------------------------------------------------ filtri

function filtra(
    gruppi: GruppoCampionato[],
    opt: { soloLive: boolean; soloConSegnali: boolean },
): GruppoCampionato[] {
    if (!opt.soloLive && !opt.soloConSegnali) return gruppi;
    const out: GruppoCampionato[] = [];
    for (const g of gruppi) {
        const partite = g.partite.filter((p) => {
            if (opt.soloLive && p.stato !== 'live') return false;
            if (opt.soloConSegnali && !(p.soldi && p.soldi.bots.length > 0)) return false;
            return true;
        });
        if (partite.length) out.push({ ...g, partite });
    }
    return out;
}
