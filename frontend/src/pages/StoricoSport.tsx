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
//     Si sceglie una moneta e si guarda quella; l'altra è a un clic (il
//     selettore in testata) e NESSUNA sua cifra compare in questa vista
//     (01/10, ordine dell'utente: «massima distinzione»). `totaleModo` LANCIA
//     se qualcuno prova a mescolare.
//  2. **Non ricalcola il P&L.** Le giornate arrivano dalle RPC dei tre bot,
//     che passano tutte dal motore condiviso `trading_daily_history`: stessa
//     matematica dello Storico dentro Omega, Safe e Mike. Una seconda verità
//     sotto gli occhi del trader diverge sempre.
//  3. **Non finge che i bot senza storico abbiano fatto zero.** Lo scalper del
//     calcio non registra operazioni per giornata: è elencato a parte, con il
//     motivo. (I quattro bot del tennis hanno uno storico dal 17/09 e dal
//     01/10 entrano qui.) Uno zero affermativo su un dato che non esiste è
//     peggio di un buco dichiarato.
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
import { EquityCard, EQUITY_AXIS_NOTE_GIORNATE } from '@/components/trading/EquityCard';
import { BarreGiornaliere } from '@/components/trading/BarreGiornaliere';
import { DailyCalendar } from '@/components/trading/DailyCalendar';
import { DayDetail } from '@/components/trading/DayDetail';
import { fmtMoney, fmtPct, fmtNum, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import {
    dayLabel, attributionOf, calendarGridBounds, historyWindow, filterRange,
    GIORNATA_PARTITA_TESTO, GIORNATA_RIPIEGO_TESTO,
} from '@/lib/dailyHistory';
import { FONTE_PNL_BREVE } from '@/lib/fontePnl';
import {
    FONTI_STORICO, FONTI_ASSENTI, INTERVALLO_LABEL, MODO_LABEL, eBotTennisStorico,
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
    // B-16 (01/10): «oggi» si ricalcola (una pagina aperta oltre mezzanotte
    // restava su ieri); i test lo fissano con la prop
    const [oggiVivo, setOggiVivo] = useState(() => oggiOperativo());
    useEffect(() => {
        if (oggi) return undefined;
        const id = setInterval(() => setOggiVivo(oggiOperativo()), 60_000);
        return () => clearInterval(id);
    }, [oggi]);
    const giornoOggi = oggi ?? oggiVivo;
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

    // B-15 (01/10): la finestra letta copre il PERIODO e la GRIGLIA del mese a
    // schermo (come lo Storico dei bot): ogni cella del calendario è una
    // giornata letta davvero, mai «nessuna operazione» su dati mai chiesti
    const griglia = useMemo(() => calendarGridBounds(ym.year, ym.month), [ym]);
    const finestra = useMemo(() => historyWindow(griglia, range), [griglia, range]);

    // ── LETTURA: una guardia anti-risposte fuori ordine, come TradingHistory ──
    const seq = useRef(0);
    useEffect(() => {
        const mio = ++seq.current;
        setCaricamento(true);
        setErrore(null);
        caricaStoricoSport(sport, finestra.from, finestra.to)
            .then((s) => { if (mio === seq.current) { setSerie(s); setCaricamento(false); } })
            .catch((e) => {
                if (mio !== seq.current) return;
                setErrore(String((e as Error)?.message ?? e));
                setCaricamento(false);
            });
    }, [sport, finestra.from, finestra.to, ricarica]);

    // ── DETTAGLIO DEL GIORNO (dichiarato qui: serve anche al criterio) ──
    const [dettaglio, setDettaglio] = useState<{ day: string; modo: ModoStorico; righe: TradeGiornoBot[] } | null>(null);

    /**
     * 01/10 - il database manda il giorno della PARTITA? Lo dicono le righe
     * del dettaglio (`in_day`): se mancano, la giornata è ancora quella del
     * criterio precedente e la pagina lo DICHIARA (mai un giorno partita
     * calcolato qui). null = nessuna riga da cui saperlo.
     */
    const criterioVecchio = useMemo<boolean | null>(() => {
        if (!dettaglio) return null;
        const righe = dettaglio.righe.flatMap((d) => d.trades);
        if (righe.length === 0) return null;
        return righe.some((t) => typeof t.in_day !== 'boolean');
    }, [dettaglio]);

    // ── le serie della MODALITÀ scelta, e quelle che non sanno separarla ──
    // (i numeri sono del PERIODO; il calendario usa tutta la finestra letta)
    const serieModo = useMemo(() => serie.filter((s) => s.modo === modo), [serie, modo]);
    const seriePeriodo = useMemo(
        () => serieModo.map((s) => ({ ...s, righe: filterRange(s.righe, range.from, range.to) })),
        [serieModo, range.from, range.to],
    );
    const aggregati = useMemo(() => seriePeriodo.map(aggregaBot).map((a) => (
        // C-01: col criterio di prima il P&L di Mike è per regolamento e
        // l'importo per piazzamento: due giorni diversi, ROI non calcolabile
        criterioVecchio && a.bot === 'mike' ? { ...a, stake: null, roi: null } : a
    )), [seriePeriodo, criterioVecchio]);
    const separabili = useMemo(() => aggregati.filter((a) => a.modoAttendibile), [aggregati]);
    const nonSeparabili = useMemo(() => aggregati.filter((a) => !a.modoAttendibile && !a.errore), [aggregati]);
    const conErrore = useMemo(() => aggregati.filter((a) => a.errore), [aggregati]);

    // il totale somma SOLO la modalità scelta e SOLO i bot che sanno separarla.
    // A-01 (01/10): dell'altra moneta NESSUNA cifra in questa vista.
    const totale = useMemo(() => totaleModo(aggregati, modo), [aggregati, modo]);
    const stakeTennisAssente = useMemo(
        () => separabili.some((a) => eBotTennisStorico(a.bot) && a.giorni > 0), [separabili]);

    // filtro per bot: cambia quello che si VEDE nei grafici e nel calendario
    const filtroBot = useCallback(
        (s: { modoAttendibile: boolean; bot: string }) => s.modoAttendibile && (botScelto === 'tutti' || s.bot === botScelto),
        [botScelto],
    );
    const serieVisibili = useMemo(() => seriePeriodo.filter(filtroBot), [seriePeriodo, filtroBot]);
    const righeUnite = useMemo(
        () => unisciGiornate(serieVisibili.map((s) => s.righe)), [serieVisibili],
    );
    // il calendario: tutte le giornate LETTE (periodo + griglia del mese)
    const righeCalendario = useMemo(
        () => unisciGiornate(serieModo.filter(filtroBot).map((s) => s.righe)), [serieModo, filtroBot],
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
                // B-01 (01/10): il criterio vero, uguale per tutti i bot; niente
                // nomi di funzioni del database davanti al trader
                `${GIORNATA_PARTITA_TESTO} Le giornate sono quelle che il database calcola per ogni bot, `
                + 'con la stessa matematica dello Storico dentro Omega, Safe e Mike: questa pagina non '
                + 'ricalcola nessun P&L e non somma mai soldi veri e prova.'
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

                {/* A-09 (01/10): la moneta si sceglie in UN posto solo, il
                    selettore in testata (NESSUN «entrambi»: due monete
                    diverse non hanno un totale) */}

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

            {criterioVecchio && (
                <Card className="glass-card border-amber-500/40 bg-amber-500/[0.07] p-3 text-[11.5px] text-amber-200"
                    data-testid="storico-giornata-ripiego" role="note">
                    <b className="text-amber-300">Attenzione:</b> {GIORNATA_RIPIEGO_TESTO} (Omega e Safe per giorno di
                    piazzamento, Mike per giorno di regolamento). Il ROI di Mike non si calcola: P&amp;L e importo
                    cadrebbero su giorni diversi.
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
                        // D-04 (01/10): ogni cifra in soldi veri dice la sua fonte
                        sub={<span data-testid="storico-kpi-pnl-fonte">{fonteTotale(modo, totale)}</span>}
                        hint="somma del P&L realizzato delle giornate del periodo, netto di commissione, SOLO di questa moneta"
                    />
                    <StatTile
                        label="Operazioni"
                        value={fmtNum(totale.operazioni)}
                        testId="storico-kpi-operazioni"
                        sub={`${fmtNum(totale.regolate)} regolate`}
                        hint={'aperture delle partite del periodo (le coperture non contano come operazioni a sé)'
                            + (sport === 'tennis' ? '; per i 4 bot tennis sono gli ordini regolati: il servizio non scrive il legame ingresso-uscita' : '')}
                    />
                    <StatTile
                        label="Vinte / perse"
                        value={<span><span className="text-emerald-400">{totale.vinte}</span>
                            <span className="text-slate-500"> / </span>
                            <span className="text-red-400">{totale.perse}</span></span>}
                        testId="storico-kpi-vp"
                        // C-05 (01/10): regolate = vinte + perse + pari/annullate, detto
                        sub={`${totale.winRate == null ? 'nessun esito' : `${fmtPct(totale.winRate, 1)} vinte`} · ${fmtNum(totale.pari)} pari/annullate`}
                        hint="esito della POSIZIONE intera (apertura + coperture), non della singola riga: vinta se il P&L è positivo, persa se negativo; a zero o annullata è «pari/annullata», fuori da vinte e perse"
                    />
                    <StatTile
                        label="Importo piazzato"
                        value={totale.stake == null ? DASH : fmtMoney(totale.stake)}
                        testId="storico-kpi-stake"
                        sub={totale.stake == null ? 'dato non disponibile' : 'somma degli importi di apertura'}
                        hint="somma degli importi messi a mercato in apertura, per le partite del periodo. Sui lay NON è la liability: sono due grandezze diverse."
                    />
                    <StatTile
                        label="ROI su importo piazzato"
                        value={totale.roi == null ? DASH : fmtPct(totale.roi, 1)}
                        tone={totale.roi == null ? 'plain' : toneOf(totale.roi)}
                        testId="storico-kpi-roi"
                        sub={totale.roi == null ? 'manca l’importo piazzato' : 'P&L / importo piazzato'}
                        hint="P&L realizzato diviso l'importo piazzato, per le partite del periodo"
                    />
                </KpiRow>

                {totale.stake == null && (
                    // C-02 (01/10): in parole, senza nomi di file del database
                    <div className="px-1 text-[10.5px] text-amber-300/90" data-testid="storico-manca-stake">
                        ROI non disponibile: manca l&apos;importo piazzato per giornata
                        {stakeTennisAssente
                            ? ' (i bot tennis non registrano l’importo piazzato per giornata).'
                            : ' (dato non disponibile: serve un aggiornamento del database).'}
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
                                {nonSeparabili.map((a) => a.etichetta).join(', ')}: storico per moneta non disponibile
                            </div>
                            <div>
                                {/* A-02/A-03 (01/10): nessuna cifra (sarebbe di due monete
                                    insieme) e nessun nome tecnico davanti al trader */}
                                Il database non separa ancora le sue giornate fra soldi veri e prova: per questo
                                il bot resta FUORI da tutti i numeri di questa pagina, in entrambe le monete
                                (dato non disponibile: serve un aggiornamento del database).
                            </div>
                            <ul className="pt-1 space-y-0.5">
                                {nonSeparabili.map((a) => (
                                    <li key={`${a.bot}-${a.modo}`} className="text-[11px]"
                                        data-testid={`storico-misto-${a.bot}`}>
                                        {a.etichetta}: non incluso nei totali
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
                                <th className="text-right px-3 py-1.5 font-normal">ROI su importo piazzato</th>
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
                    Hai scelto un bot il cui storico non è separato per moneta: curva, barre e calendario
                    qui sotto restano vuoti apposta (vedi il riquadro qui sopra).
                </div>
            )}

            {/* ── LE DUE CURVE ── */}
            <div className="grid gap-4 xl:grid-cols-2 items-start">
                <EquityCard
                    series={curva}
                    scope={`${MODO_LABEL[modo]} · ${botScelto === 'tutti' ? 'tutti i bot' : botScelto} · ${INTERVALLO_LABEL[intervallo].toLowerCase()}`}
                    emptyLabel="nessuna giornata con partite concluse in questo periodo — la curva compare alla prima"
                    label={`Curva globale ${SPORT_LABEL[sport].toLowerCase()} ${MODO_LABEL[modo]}`}
                    testId="storico-curva"
                    axisNote={EQUITY_AXIS_NOTE_GIORNATE}
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
                        rows={righeCalendario}
                        year={ym.year}
                        month={ym.month}
                        selectedDay={giornoScelto}
                        onSelectDay={onGiorno}
                        onMonthChange={onMese}
                        today={giornoOggi}
                        loading={caricamento}
                    />
                    <div className="text-[10px] text-slate-500 mt-2" data-testid="storico-calendario-nota">
                        Il calendario mostra il MESE scelto, letto per intero; i numeri qui sopra sono del periodo
                        {' '}«{INTERVALLO_LABEL[intervallo].toLowerCase()}».
                        {finestra.periodTruncated && (
                            <> Con questo mese a schermo il periodo non entra tutto nel limite di lettura: i numeri
                            qui sopra partono dal {dayLabel(finestra.from)}.</>
                        )}
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
                                    <DettaglioBot key={d.bot} d={d} giorno={giornoScelto} />
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
                            className={`px-2.5 py-1 transition ${modo === 'paper' ? 'bg-white/15 text-white/80' : 'text-slate-400 hover:text-white'}`}
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
    const tennis = eBotTennisStorico(a.bot);
    return (
        <tr data-testid={`storico-bot-riga-${a.bot}`} className="hover:bg-white/[0.03]">
            <td className={`px-3 py-1.5 ${a.accento}`}>{a.etichetta}</td>
            <td className={`px-2 py-1.5 text-right font-mono tabular-nums font-semibold ${pnlClass(a.pnl)}`}
                data-testid={`storico-bot-pnl-${a.bot}`}>
                {fmtMoney(a.pnl, { signed: true })}
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-white/70"
                title={tennis ? 'ordini regolati: il servizio non scrive il legame ingresso-uscita' : undefined}>
                {fmtNum(a.operazioni)}{tennis && <span className="text-white/35 font-sans text-[10px]"> ordini</span>}
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                <span className="text-emerald-400">{a.vinte}</span>
                <span className="text-slate-500"> / </span>
                <span className="text-red-400">{a.perse}</span>
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-white/70">
                {a.winRate == null ? DASH : fmtPct(a.winRate, 1)}
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-white/70"
                title={a.stake == null ? (tennis ? 'i bot tennis non registrano l’importo piazzato per giornata' : 'dato non disponibile') : undefined}>
                {a.stake == null ? DASH : fmtMoney(a.stake)}
            </td>
            <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${a.roi == null ? 'text-white/40' : pnlClass(a.roi)}`}>
                {a.roi == null ? DASH : fmtPct(a.roi, 1)}
            </td>
        </tr>
    );
}

function DettaglioBot({ d, giorno }: { d: TradeGiornoBot; giorno: string }) {
    // A-02 (01/10): un bot senza storico per moneta non mostra righe (sarebbero
    // di due monete); il bot tennis rimanda alle Chiuse (nessuna lettura in più)
    const nota = d.errore ? null
        : !d.modoAttendibile ? 'storico per moneta non disponibile: righe non mostrate (sarebbero di soldi veri e prova insieme)'
            : d.senzaDettaglio ?? null;
    return (
        <div data-testid={`storico-dettaglio-${d.bot}`}>
            <div className="flex items-baseline gap-2 mb-1">
                <span className="text-[11px] uppercase tracking-wider text-white/55">{d.etichetta}</span>
                {!nota && !d.errore && (
                    <span className="text-[10px] text-white/35">{d.trades.length} {d.trades.length === 1 ? 'operazione' : 'operazioni'}</span>
                )}
            </div>
            {d.errore
                ? <div className="text-[11px] text-orange-300">{d.errore}</div>
                : nota || d.variante == null
                    ? <div className="text-[11px] text-white/45" data-testid={`storico-dettaglio-nota-${d.bot}`}>{nota}</div>
                    // B-04 (01/10): il criterio del dettaglio è quello della cella, mai cablato
                    : <DayDetail day={giorno} trades={d.trades} variant={d.variante} attribution={attributionOf(d.variante)} />}
        </div>
    );
}

/** D-04 (01/10): la fonte del P&L del totale, in parole (vocabolario di `lib/fontePnl`). */
function fonteTotale(modo: ModoStorico, t: { reale: number | null; stimato: number | null; stimati: number | null; bot: number }): string {
    if (modo === 'paper') return `fonte: ${FONTE_PNL_BREVE.simulato}`;
    if (t.bot > 0 && t.reale != null && t.stimato != null) {
        // D-03: quanti ordini sono ancora stimati, se la fonte lo dice
        const quanti = t.stimati != null && t.stimati > 0
            ? ` (${t.stimati} ${t.stimati === 1 ? 'ordine ancora stimato' : 'ordini ancora stimati'})` : '';
        return `di cui ${FONTE_PNL_BREVE.conto} ${fmtMoney(t.reale, { signed: true })} · ${FONTE_PNL_BREVE.stima} ${fmtMoney(t.stimato, { signed: true })}${quanti}`;
    }
    // C-03 (01/10): il motore somma il P&L scritto da ogni bot; conto e stima
    // non sono separati per giornata, e lo si dice invece di attribuirgli una fonte
    return `fonte: P&L scritto da ogni bot (${FONTE_PNL_BREVE.conto} e ${FONTE_PNL_BREVE.stima} non separati per giornata)`;
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
