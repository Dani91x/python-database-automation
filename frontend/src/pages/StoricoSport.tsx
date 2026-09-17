// ============================================================================
// StoricoSport.tsx — LA DASHBOARD DELLO STORICO di uno sport (/storico/calcio,
// /storico/tennis).
//
// Ordine dell'utente (17/09): «per i giorni precedenti deve esserci uno
// STORICO dedicato che il trader può consultare: uno AL TENNIS e uno AL
// CALCIO, con la chiara distinzione dei profitti o loss per bot; il trader
// deve leggerlo facilmente [...] con curva globale, giornaliera ecc.: una
// dashboard di storico avanzata».
//
// LE TRE COSE CHE QUESTA PAGINA NON FA, e non deve iniziare a fare:
//
//  1. **Non somma paper e live.** Mai, in nessun totale, per nessuna comodità.
//     Si sceglie una moneta e si guarda quella; l'altra è a un clic, in un
//     riquadro che dice quanto vale, senza entrare in questi numeri. È la
//     regola del 14/09 («i soldi veri si raggiungono solo scrivendolo») e
//     `totaleModo` LANCIA se qualcuno prova a mescolare.
//  2. **Non ricalcola il P&L.** Le giornate arrivano dalle RPC dei tre bot,
//     che passano tutte dal motore condiviso `trading_daily_history`: stessa
//     matematica dello Storico dentro Omega, Safe e Mike. Una seconda verità
//     sotto gli occhi del trader diverge sempre.
//  3. **Non finge che i bot senza storico abbiano fatto zero.** Lo scalper del
//     calcio e i quattro bot del tennis non scrivono operazioni regolate con
//     P&L su nessuna tabella (verificato sul database reale il 17/09): sono
//     elencati a parte, con il motivo. Uno zero affermativo su un dato che non
//     esiste è peggio di un buco dichiarato.
//
// Tutto il resto è riuso: `PageShell`, `StatTile`/`KpiRow`, `EquityCard`,
// `DailyCalendar`, `DayDetail`, `BarreGiornaliere`, e le funzioni pure di
// `lib/storicoSport` (testate in `storicoSport.test.ts`).
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, History, TrendingUp, BarChart3, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageShell } from '@/components/trading/PageShell';
import { EmptyState } from '@/components/trading/EmptyState';
import { StatTile, KpiRow, toneOf } from '@/components/trading/StatTile';
import { EquityCard } from '@/components/trading/EquityCard';
import { BarreGiornaliere } from '@/components/trading/BarreGiornaliere';
import { DailyCalendar } from '@/components/trading/DailyCalendar';
import { DayDetail } from '@/components/trading/DayDetail';
import { fmtMoney, fmtPct, fmtNum, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import { dayLabel } from '@/lib/dailyHistory';
import {
    FONTI_STORICO, FONTI_ASSENTI, INTERVALLO_LABEL, MODO_LABEL,
    SPORT_ICONA, SPORT_LABEL, rottaStorico,
    intervalloRange, caricaStoricoSport, caricaTradeGiorno, aggregaBot, totaleModo,
    unisciGiornate, curvaCumulata, barrePerGiorno, oggiOperativo,
    type SportStorico, type ModoStorico, type IntervalloKind,
    type SerieBot, type AggregatoBot, type TradeGiornoBot,
} from '@/lib/storicoSport';

const INTERVALLI: IntervalloKind[] = ['oggi', '7g', '30g', 'mese', 'tutto'];
const ALTRO_SPORT: Record<SportStorico, SportStorico> = { calcio: 'tennis', tennis: 'calcio' };

export interface StoricoSportProps {
    sport: SportStorico;
    /** giornata operativa corrente (i test la fissano) */
    oggi?: string;
}

export function StoricoSport({ sport, oggi }: StoricoSportProps) {
    const giornoOggi = oggi ?? oggiOperativo();
    const [modo, setModo] = useState<ModoStorico>('live');
    const [intervallo, setIntervallo] = useState<IntervalloKind>('30g');
    const [botScelto, setBotScelto] = useState<string>('tutti');
    const [serie, setSerie] = useState<SerieBot[]>([]);
    const [caricamento, setCaricamento] = useState(true);
    const [errore, setErrore] = useState<string | null>(null);
    const [ricarica, setRicarica] = useState(0);

    const range = useMemo(() => intervalloRange(intervallo, giornoOggi), [intervallo, giornoOggi]);

    // il mese del calendario e il giorno aperto nel dettaglio
    const [ym, setYm] = useState(() => ({
        year: Number(giornoOggi.slice(0, 4)), month: Number(giornoOggi.slice(5, 7)),
    }));
    const [giornoScelto, setGiornoScelto] = useState<string | null>(giornoOggi);

    // ── LETTURA: una guardia anti-risposte fuori ordine, come TradingHistory ──
    const seq = useRef(0);
    useEffect(() => {
        const mio = ++seq.current;
        setCaricamento(true);
        setErrore(null);
        caricaStoricoSport(sport, range.from, range.to)
            .then((s) => { if (mio === seq.current) { setSerie(s); setCaricamento(false); } })
            .catch((e) => {
                if (mio !== seq.current) return;
                setErrore(String((e as Error)?.message ?? e));
                setCaricamento(false);
            });
    }, [sport, range.from, range.to, ricarica]);

    // ── le serie della MODALITÀ scelta, e quelle che non sanno separarla ──
    const serieModo = useMemo(() => serie.filter((s) => s.modo === modo), [serie, modo]);
    const aggregati = useMemo(() => serieModo.map(aggregaBot), [serieModo]);
    const separabili = useMemo(() => aggregati.filter((a) => a.modoAttendibile), [aggregati]);
    const nonSeparabili = useMemo(() => aggregati.filter((a) => !a.modoAttendibile && !a.errore), [aggregati]);
    const conErrore = useMemo(() => aggregati.filter((a) => a.errore), [aggregati]);

    // il totale somma SOLO la modalità scelta e SOLO i bot che sanno separarla
    const totale = useMemo(() => totaleModo(aggregati, modo), [aggregati, modo]);
    // l'altra moneta, mostrata SENZA entrare in nessun numero di questa pagina
    const totaleAltraModalita = useMemo(() => {
        const altro: ModoStorico = modo === 'live' ? 'paper' : 'live';
        return totaleModo(serie.filter((s) => s.modo === altro).map(aggregaBot), altro);
    }, [serie, modo]);

    // filtro per bot: cambia quello che si VEDE nei grafici e nel calendario
    const serieVisibili = useMemo(
        () => serieModo.filter((s) => s.modoAttendibile && (botScelto === 'tutti' || s.bot === botScelto)),
        [serieModo, botScelto],
    );
    const righeUnite = useMemo(
        () => unisciGiornate(serieVisibili.map((s) => s.righe)), [serieVisibili],
    );
    const curva = useMemo(() => curvaCumulata(righeUnite), [righeUnite]);
    const barre = useMemo(
        () => barrePerGiorno(serieVisibili.map((s) => ({ etichetta: s.etichetta, righe: s.righe }))),
        [serieVisibili],
    );
    /**
     * Il bot scelto è uno di quelli che non sanno separare la modalità?
     * Senza dirlo, scegliendo Omega i grafici restavano vuoti e sembrava che
     * non avesse mai operato — mentre le sue giornate esistono, solo che sono
     * miste e non si possono mettere sotto «soldi veri» o «prova».
     */
    const botSceltoMisto = useMemo(
        () => botScelto !== 'tutti' && nonSeparabili.some((a) => a.bot === botScelto),
        [botScelto, nonSeparabili],
    );

    // ── DETTAGLIO DEL GIORNO: si carica alla selezione, bot per bot ──
    const [dettaglio, setDettaglio] = useState<{ day: string; modo: ModoStorico; righe: TradeGiornoBot[] } | null>(null);
    const [dettaglioCarica, setDettaglioCarica] = useState(false);
    const seqDay = useRef(0);
    useEffect(() => {
        if (!giornoScelto) { setDettaglio(null); return; }
        const day = giornoScelto, m = modo;
        const mio = ++seqDay.current;
        setDettaglioCarica(true);
        caricaTradeGiorno(sport, m, day)
            .then((righe) => {
                if (mio !== seqDay.current) return;
                setDettaglio({ day, modo: m, righe });
                setDettaglioCarica(false);
            })
            .catch(() => { if (mio === seqDay.current) { setDettaglio(null); setDettaglioCarica(false); } });
    }, [sport, modo, giornoScelto, ricarica]);
    // mai i trade di un altro giorno (o di un'altra moneta) sotto questa data
    const dettaglioValido = dettaglio && dettaglio.day === giornoScelto && dettaglio.modo === modo
        ? dettaglio.righe : null;

    const onMese = useCallback((year: number, month: number) => setYm({ year, month }), []);
    const onGiorno = useCallback((day: string) => setGiornoScelto(day), []);

    const titolo = `Storico ${SPORT_LABEL[sport].toLowerCase()}`;
    const altro = ALTRO_SPORT[sport];

    return (
        <PageShell
            title={`${titolo} — AI Terminal`}
            header={<Testata sport={sport} modo={modo} onModo={setModo}
                onRicarica={() => setRicarica((n) => n + 1)} caricamento={caricamento} />}
            footer={
                'Le giornate vengono dalle RPC dei bot (motore condiviso trading_daily_history): stessa '
                + 'matematica dello Storico dentro Omega, Safe e Mike. Giornata operativa = giorno di '
                + 'PIAZZAMENTO, fuso Europe/Rome. Questa pagina non ricalcola nessun P&L e non somma mai '
                + 'soldi veri e simulati.'
            }
        >
            {/* ── I FILTRI: periodo, moneta, bot. Sempre visibile quale è attivo ── */}
            <Card className="glass-card border-white/10 p-3 flex flex-wrap items-center gap-x-5 gap-y-2"
                data-testid="storico-filtri">
                <Gruppo etichetta="periodo">
                    {INTERVALLI.map((k) => (
                        <Pillola key={k} attivo={intervallo === k} onClick={() => setIntervallo(k)}
                            testId={`storico-periodo-${k}`}>{INTERVALLO_LABEL[k]}</Pillola>
                    ))}
                </Gruppo>

                <Gruppo etichetta="soldi">
                    <Pillola attivo={modo === 'live'} onClick={() => setModo('live')} testId="storico-modo-live"
                        titolo="solo operazioni con denaro reale">soldi veri</Pillola>
                    <Pillola attivo={modo === 'paper'} onClick={() => setModo('paper')} testId="storico-modo-paper"
                        titolo="solo operazioni simulate">prova</Pillola>
                    {/* NESSUN «entrambi»: due monete diverse non hanno un totale. */}
                </Gruppo>

                <Gruppo etichetta="bot">
                    <Pillola attivo={botScelto === 'tutti'} onClick={() => setBotScelto('tutti')}
                        testId="storico-bot-tutti">tutti</Pillola>
                    {FONTI_STORICO[sport].map((f) => (
                        <Pillola key={f.bot} attivo={botScelto === f.bot} onClick={() => setBotScelto(f.bot)}
                            testId={`storico-bot-${f.bot}`}>{f.etichetta}</Pillola>
                    ))}
                </Gruppo>

                <span className="ml-auto text-[10.5px] text-white/40" data-testid="storico-intervallo">
                    {dayLabel(range.from)} → {dayLabel(range.to)}
                </span>
            </Card>

            {errore && (
                <Card className="glass-card border-orange-500/40 bg-orange-500/10 p-3 text-sm text-orange-200"
                    data-testid="storico-errore">
                    Lettura non riuscita: {errore}. I riquadri sotto mostrano l&apos;ultimo dato letto, non uno più recente.
                </Card>
            )}

            {/* ── IL RIEPILOGO: il numero grande è di UNA moneta sola ── */}
            <div className="space-y-2">
                <div className="flex items-baseline gap-2 flex-wrap">
                    <h2 className="text-sm text-slate-300 flex items-center gap-2">
                        <History className="w-4 h-4 text-primary" aria-hidden />
                        {SPORT_ICONA[sport]} {titolo} · <b className={modo === 'live' ? 'text-red-300' : 'text-white/70'}>
                            {MODO_LABEL[modo]}
                        </b>
                    </h2>
                    <span className="text-[10.5px] text-white/40">
                        {INTERVALLO_LABEL[intervallo].toLowerCase()} · {totale.bot} {totale.bot === 1 ? 'bot' : 'bot'}
                    </span>
                </div>

                <KpiRow loading={caricamento} tiles={5}>
                    <StatTile
                        label={`P&L ${MODO_LABEL[modo]}`}
                        value={fmtMoney(totale.pnl, { signed: true })}
                        tone={toneOf(totale.pnl)}
                        testId="storico-kpi-pnl"
                        hint="somma del P&L realizzato delle giornate del periodo, netto di commissione, SOLO di questa modalità"
                    />
                    <StatTile
                        label="Operazioni"
                        value={fmtNum(totale.operazioni)}
                        testId="storico-kpi-operazioni"
                        sub={`${fmtNum(totale.regolate)} regolate`}
                        hint="aperture PIAZZATE nel periodo (le coperture non contano come operazioni a sé)"
                    />
                    <StatTile
                        label="Vinte / perse"
                        value={<span><span className="text-emerald-400">{totale.vinte}</span>
                            <span className="text-slate-500"> / </span>
                            <span className="text-red-400">{totale.perse}</span></span>}
                        testId="storico-kpi-vp"
                        sub={totale.winRate == null ? 'nessun esito' : `${fmtPct(totale.winRate, 1)} vinte`}
                        hint="esito della POSIZIONE intera (apertura + coperture), non della singola riga"
                    />
                    <StatTile
                        label="Importo piazzato"
                        value={totale.stake == null ? DASH : fmtMoney(totale.stake)}
                        testId="storico-kpi-stake"
                        sub={totale.stake == null ? 'migrazione da applicare' : 'somma delle size di apertura'}
                        hint="somma degli importi messi a mercato in apertura. Sui lay NON è la liability: sono due grandezze diverse."
                    />
                    <StatTile
                        label="ROI su stake"
                        value={totale.roi == null ? DASH : fmtPct(totale.roi, 1)}
                        tone={totale.roi == null ? 'plain' : toneOf(totale.roi)}
                        testId="storico-kpi-roi"
                        sub={totale.roi == null ? 'serve l’importo piazzato' : 'P&L / importo piazzato'}
                        hint="P&L realizzato diviso l'importo piazzato nel periodo"
                    />
                </KpiRow>

                {/* L'ALTRA MONETA: si vede, ma non entra in nessun numero qui sopra. */}
                <div className="flex items-baseline gap-2 text-[11px] text-white/45 px-1"
                    data-testid="storico-altra-modalita">
                    <span className="uppercase tracking-wider text-[9.5px] px-1.5 py-0.5 rounded bg-white/10">
                        {MODO_LABEL[modo === 'live' ? 'paper' : 'live']}
                    </span>
                    <span className={pnlClass(totaleAltraModalita.pnl)}>
                        {fmtMoney(totaleAltraModalita.pnl, { signed: true })}
                    </span>
                    <span>su {fmtNum(totaleAltraModalita.operazioni)} operazioni —
                        <strong className="text-white/60"> non è sommato</strong> ai numeri qui sopra:
                        sono due monete diverse.</span>
                </div>

                {totale.stake == null && (
                    <div className="px-1 text-[10.5px] text-amber-300/90" data-testid="storico-manca-stake">
                        ROI non calcolabile: serve l&apos;importo piazzato per giornata, che oggi nessuna RPC
                        espone. Lo aggiunge <code>migrations/storico_sport_2026-09-17.sql</code> —
                        <strong> da applicare</strong>.
                    </div>
                )}
            </div>

            {/* ── MODALITÀ NON SEPARABILE: fuori dai totali, mai dentro in silenzio ── */}
            {nonSeparabili.length > 0 && (
                <Card className="glass-card border-amber-500/40 bg-amber-500/[0.07] p-3"
                    data-testid="storico-modo-non-separabile">
                    <div className="flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" aria-hidden />
                        <div className="text-[11.5px] text-amber-100/90 space-y-1">
                            <div className="font-semibold text-amber-300">
                                {nonSeparabili.map((a) => a.etichetta).join(', ')}: soldi veri e simulati non separabili
                            </div>
                            <div>
                                La RPC di questo bot non sa filtrare per modalità (verificato sul database il 17/09:
                                <code> get_omega_daily</code> esiste solo con <code>p_from</code> e <code>p_to</code>).
                                Le sue righe sono <strong>miste</strong> e per questo restano FUORI dai totali qui
                                sopra: metterle dentro vorrebbe dire chiamare «soldi veri» delle righe che non lo sono.
                                La cura è <code>migrations/storico_sport_2026-09-17.sql</code> — <strong>da applicare</strong>.
                            </div>
                            <ul className="pt-1 space-y-0.5">
                                {nonSeparabili.map((a) => (
                                    <li key={`${a.bot}-${a.modo}`} className="font-mono text-[11px]"
                                        data-testid={`storico-misto-${a.bot}`}>
                                        {a.etichetta}: {fmtMoney(a.pnl, { signed: true })} su {fmtNum(a.operazioni)} operazioni
                                        <span className="text-amber-200/60"> (paper + live insieme)</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </Card>
            )}

            {conErrore.length > 0 && (
                <Card className="glass-card border-orange-500/30 p-3 text-[11.5px] text-orange-200"
                    data-testid="storico-bot-in-errore">
                    {conErrore.map((a) => (
                        <div key={`${a.bot}-${a.modo}`}>
                            <strong>{a.etichetta}</strong>: {a.errore}. Gli altri bot restano leggibili.
                        </div>
                    ))}
                </Card>
            )}

            {/* ── PER BOT: la «chiara distinzione dei profitti o loss per bot» ── */}
            <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="storico-per-bot">
                <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                    <span className="text-[11px] uppercase tracking-wider text-white/60">Per bot</span>
                    <span className="text-[10.5px] text-white/40">
                        {MODO_LABEL[modo]} · {INTERVALLO_LABEL[intervallo].toLowerCase()}
                    </span>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-[11.5px]">
                        <thead>
                            <tr className="text-[9.5px] uppercase tracking-wider text-white/35 border-b border-white/10">
                                <th className="text-left px-3 py-1.5 font-normal">bot</th>
                                <th className="text-right px-2 py-1.5 font-normal">P&amp;L</th>
                                <th className="text-right px-2 py-1.5 font-normal">operazioni</th>
                                <th className="text-right px-2 py-1.5 font-normal">vinte / perse</th>
                                <th className="text-right px-2 py-1.5 font-normal">% vinte</th>
                                <th className="text-right px-2 py-1.5 font-normal">importo piazzato</th>
                                <th className="text-right px-3 py-1.5 font-normal">ROI</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.06]">
                            {separabili.length === 0 && !caricamento && (
                                <tr><td colSpan={7} className="px-3 py-4">
                                    <EmptyState>
                                        Nessuna giornata con operazioni in {MODO_LABEL[modo]} in questo periodo.
                                    </EmptyState>
                                </td></tr>
                            )}
                            {separabili.map((a) => <RigaBot key={`${a.bot}-${a.modo}`} a={a} />)}
                        </tbody>
                        {separabili.length > 0 && (
                            <tfoot>
                                <tr className="border-t border-white/15 font-semibold" data-testid="storico-riga-totale">
                                    <td className="px-3 py-1.5">Totale {MODO_LABEL[modo]}</td>
                                    <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${pnlClass(totale.pnl)}`}>
                                        {fmtMoney(totale.pnl, { signed: true })}
                                    </td>
                                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fmtNum(totale.operazioni)}</td>
                                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                                        <span className="text-emerald-400">{totale.vinte}</span>
                                        <span className="text-slate-500"> / </span>
                                        <span className="text-red-400">{totale.perse}</span>
                                    </td>
                                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                                        {totale.winRate == null ? DASH : fmtPct(totale.winRate, 1)}
                                    </td>
                                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                                        {totale.stake == null ? DASH : fmtMoney(totale.stake)}
                                    </td>
                                    <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                                        {totale.roi == null ? DASH : fmtPct(totale.roi, 1)}
                                    </td>
                                </tr>
                            </tfoot>
                        )}
                    </table>
                </div>
            </Card>

            {/* ── BOT SENZA STORICO: dichiarati, non nascosti ── */}
            {FONTI_ASSENTI[sport].length > 0 && (
                <Card className="glass-card border-white/10 p-3" data-testid="storico-senza-storico">
                    <div className="text-[11px] uppercase tracking-wider text-white/45 mb-1.5">
                        Non compaiono in questi numeri
                    </div>
                    <ul className="space-y-1 text-[11px] text-white/50">
                        {FONTI_ASSENTI[sport].map((f) => (
                            <li key={f.id} data-testid={`storico-assente-${f.id}`}>
                                <b className="text-white/70">{f.etichetta}</b> — {f.perche}
                            </li>
                        ))}
                    </ul>
                    <div className="text-[10.5px] text-white/35 mt-1.5">
                        Non è uno zero: è un dato che il database non ha. Mostrarli a «0,00 €» direbbe che non
                        hanno guadagnato nulla, che è un&apos;altra cosa.
                    </div>
                </Card>
            )}

            {botSceltoMisto && (
                <div className="px-1 text-[11px] text-amber-300/90" data-testid="storico-bot-scelto-misto">
                    Hai scelto un bot le cui righe sono <strong>miste</strong> (paper + live): curva,
                    barre e calendario qui sotto restano vuoti apposta. I suoi numeri complessivi sono
                    nel riquadro «modalità non separabile» qui sopra.
                </div>
            )}

            {/* ── LE DUE CURVE ── */}
            <div className="grid gap-4 xl:grid-cols-2 items-start">
                <EquityCard
                    series={curva}
                    scope={`${MODO_LABEL[modo]} · ${botScelto === 'tutti' ? 'tutti i bot' : botScelto} · ${INTERVALLO_LABEL[intervallo].toLowerCase()}`}
                    emptyLabel="nessuna giornata regolata in questo periodo — la curva compare al primo incasso"
                    label={`Curva globale ${SPORT_LABEL[sport].toLowerCase()} ${MODO_LABEL[modo]}`}
                    testId="storico-curva"
                />

                <Card className="glass-card border-white/10 p-4" data-testid="storico-barre">
                    <div className="flex items-center gap-2 text-sm text-slate-300 mb-1">
                        <BarChart3 className="w-4 h-4 text-secondary" aria-hidden />
                        P&amp;L per giornata
                        <span className="text-[11px] text-slate-500">· {MODO_LABEL[modo]}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 mb-2">
                        una barra per giornata con operazioni (i giorni senza operazioni non diventano barre a
                        zero: non aver operato non è chiudere in pari) — clic su una barra per aprire il dettaglio
                    </div>
                    <BarreGiornaliere
                        barre={barre}
                        selectedDay={giornoScelto}
                        onSelectDay={onGiorno}
                        testId="storico-barre-grafico"
                    />
                </Card>
            </div>

            {/* ── CALENDARIO + DETTAGLIO DEL GIORNO ── */}
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-start">
                <Card className="glass-card border-white/10 p-4" data-testid="storico-calendario">
                    <div className="flex items-center gap-2 text-sm text-slate-300 mb-2">
                        <TrendingUp className="w-4 h-4 text-primary" aria-hidden />
                        Calendario — {MODO_LABEL[modo]}
                    </div>
                    <DailyCalendar
                        rows={righeUnite}
                        year={ym.year}
                        month={ym.month}
                        selectedDay={giornoScelto}
                        onSelectDay={onGiorno}
                        onMonthChange={onMese}
                        today={giornoOggi}
                        loading={caricamento}
                    />
                    <div className="text-[10px] text-slate-500 mt-2">
                        Il calendario mostra il MESE scelto; il periodo dei numeri qui sopra è
                        {' '}{INTERVALLO_LABEL[intervallo].toLowerCase()}. Una cella vuota fuori dal periodo
                        caricato significa «non letto», non «nessuna operazione».
                    </div>
                </Card>

                <Card className="glass-card border-white/10 p-4" data-testid="storico-dettaglio-giorno">
                    <div className="text-sm text-slate-300 mb-2">
                        Operazioni del giorno
                        {giornoScelto && <span className="text-[11px] text-slate-500"> · {dayLabel(giornoScelto, { weekday: true })}</span>}
                    </div>
                    {!giornoScelto && (
                        <EmptyState>Scegli una giornata dal calendario o dalle barre per vedere le operazioni.</EmptyState>
                    )}
                    {giornoScelto && dettaglioCarica && (
                        <div className="text-sm text-muted-foreground py-6 text-center">caricamento…</div>
                    )}
                    {giornoScelto && !dettaglioCarica && dettaglioValido && (
                        <div className="space-y-4">
                            {dettaglioValido
                                .filter((d) => botScelto === 'tutti' || d.bot === botScelto)
                                .map((d) => (
                                    <DettaglioBot key={d.bot} d={d} giorno={giornoScelto} modo={modo} />
                                ))}
                        </div>
                    )}
                </Card>
            </div>

            <div className="flex items-center gap-3 flex-wrap text-[11px] text-white/45">
                <Link to="/control-room" className="inline-flex items-center gap-1.5 hover:text-white">
                    <ArrowLeft className="w-3.5 h-3.5" aria-hidden /> Torna al banco della giornata
                </Link>
                <span className="text-white/20" aria-hidden>·</span>
                <Link to={rottaStorico(altro)} className="inline-flex items-center gap-1.5 hover:text-white"
                    data-testid="storico-altro-sport">
                    {SPORT_ICONA[altro]} Storico {SPORT_LABEL[altro].toLowerCase()}
                </Link>
            </div>
        </PageShell>
    );
}

// --------------------------------------------------------------- pezzi

function Testata({ sport, modo, onModo, onRicarica, caricamento }: {
    sport: SportStorico; modo: ModoStorico;
    onModo: (m: ModoStorico) => void; onRicarica: () => void; caricamento: boolean;
}) {
    const altro = ALTRO_SPORT[sport];
    return (
        <header className="sticky top-0 z-30 backdrop-blur bg-background/80 border-b border-white/10"
            data-testid="storico-testata">
            <div className="container mx-auto px-4 lg:px-6 max-w-7xl py-2.5 flex items-center gap-3 flex-wrap">
                <Link to="/control-room" className="text-[11px] text-white/45 hover:text-white inline-flex items-center gap-1">
                    <ArrowLeft className="w-3.5 h-3.5" aria-hidden /> Control Room
                </Link>
                <span className="text-white/15" aria-hidden>|</span>
                <h1 className="text-sm font-display font-black tracking-wide flex items-center gap-2">
                    <History className="w-4 h-4 text-primary" aria-hidden />
                    <span aria-hidden>{SPORT_ICONA[sport]}</span>
                    STORICO {SPORT_LABEL[sport].toUpperCase()}
                </h1>
                <Link to={rottaStorico(altro)}
                    className="text-[11px] text-white/45 hover:text-white inline-flex items-center gap-1"
                    data-testid="storico-testata-altro">
                    <span aria-hidden>{SPORT_ICONA[altro]}</span> passa al {SPORT_LABEL[altro].toLowerCase()}
                </Link>

                <div className="ml-auto flex items-center gap-2">
                    {/* la moneta è dichiarata in testata: si legge PRIMA dei numeri */}
                    <span
                        className={`text-[9.5px] font-bold uppercase tracking-wider px-2 py-1 rounded ${
                            modo === 'live' ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/50'
                        }`}
                        data-testid="storico-testata-modo"
                    >{MODO_LABEL[modo]}</span>
                    <div className="flex items-center rounded-lg border border-white/10 overflow-hidden text-[11px] font-bold"
                        role="group" aria-label="Modalità dello storico">
                        <button type="button" onClick={() => onModo('live')} aria-pressed={modo === 'live'}
                            data-testid="storico-testata-live"
                            className={`px-2.5 py-1 transition ${modo === 'live' ? 'bg-red-500/25 text-red-300' : 'text-slate-400 hover:text-white'}`}
                        >SOLDI VERI</button>
                        <button type="button" onClick={() => onModo('paper')} aria-pressed={modo === 'paper'}
                            data-testid="storico-testata-paper"
                            className={`px-2.5 py-1 transition ${modo === 'paper' ? 'bg-emerald-500/25 text-emerald-300' : 'text-slate-400 hover:text-white'}`}
                        >PROVA</button>
                    </div>
                    <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onRicarica}
                        disabled={caricamento} data-testid="storico-ricarica">
                        <RefreshCw className={`w-3.5 h-3.5 mr-1 ${caricamento ? 'animate-spin' : ''}`} aria-hidden />
                        Ricarica
                    </Button>
                </div>
            </div>
        </header>
    );
}

function RigaBot({ a }: { a: AggregatoBot }) {
    return (
        <tr data-testid={`storico-bot-riga-${a.bot}`} className="hover:bg-white/[0.03]">
            <td className={`px-3 py-1.5 ${a.accento}`}>{a.etichetta}</td>
            <td className={`px-2 py-1.5 text-right font-mono tabular-nums font-semibold ${pnlClass(a.pnl)}`}
                data-testid={`storico-bot-pnl-${a.bot}`}>
                {fmtMoney(a.pnl, { signed: true })}
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-white/70">{fmtNum(a.operazioni)}</td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                <span className="text-emerald-400">{a.vinte}</span>
                <span className="text-slate-500"> / </span>
                <span className="text-red-400">{a.perse}</span>
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-white/70">
                {a.winRate == null ? DASH : fmtPct(a.winRate, 1)}
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-white/70">
                {a.stake == null ? DASH : fmtMoney(a.stake)}
            </td>
            <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${a.roi == null ? 'text-white/40' : pnlClass(a.roi)}`}>
                {a.roi == null ? DASH : fmtPct(a.roi, 1)}
            </td>
        </tr>
    );
}

function DettaglioBot({ d, giorno, modo }: { d: TradeGiornoBot; giorno: string; modo: ModoStorico }) {
    return (
        <div data-testid={`storico-dettaglio-${d.bot}`}>
            <div className="flex items-baseline gap-2 mb-1">
                <span className="text-[11px] uppercase tracking-wider text-white/55">{d.etichetta}</span>
                <span className="text-[10px] text-white/35">{d.trades.length} {d.trades.length === 1 ? 'operazione' : 'operazioni'}</span>
                {!d.modoAttendibile && !d.errore && (
                    <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300"
                        title={`la RPC non sa filtrare per modalità: queste righe non sono solo «${MODO_LABEL[modo]}»`}>
                        modalità mista
                    </span>
                )}
            </div>
            {d.errore
                ? <div className="text-[11px] text-orange-300">{d.errore}</div>
                : <DayDetail day={giorno} trades={d.trades} variant={d.variante} attribution="placed" />}
        </div>
    );
}

function Gruppo({ etichetta, children }: { etichetta: string; children: React.ReactNode }) {
    return (
        <span className="flex items-center gap-1 flex-wrap">
            <span className="text-[9.5px] uppercase tracking-wider text-white/30 mr-0.5">{etichetta}</span>
            {children}
        </span>
    );
}

function Pillola({ attivo, onClick, children, testId, titolo }: {
    attivo: boolean; onClick: () => void; children: React.ReactNode;
    testId: string; titolo?: string;
}) {
    return (
        <button
            type="button" onClick={onClick} aria-pressed={attivo} data-testid={testId} title={titolo}
            className={`text-[10.5px] px-2 py-0.5 rounded border transition-colors ${
                attivo
                    ? 'border-primary/60 text-primary bg-primary/10'
                    : 'border-white/15 text-white/45 hover:text-white/80'
            }`}
        >{children}</button>
    );
}

/** Le due pagine concrete del router: stesso componente, sport diverso. */
export function StoricoCalcio() { return <StoricoSport sport="calcio" />; }
export function StoricoTennis() { return <StoricoSport sport="tennis" />; }

export default StoricoSport;
