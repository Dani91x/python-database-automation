// ============================================================================
// /board — «Programma del giorno» (app desktop). Due schede (⚽ calcio / 🎾 tennis)
// alimentate ESCLUSIVAMENTE dai canali LOCALI che esistono gia' (un singleton per
// sport, `getLocalChannel`): nessuna lettura DB per il tabellone, nessuna
// connessione nuova. Se un canale e' spento la scheda lo dice onestamente
// ("canale locale non attivo") — mai un tabellone vuoto spacciato per programma
// vuoto.
//
// 09/10/2026 — RIFATTA per ordine dell'utente (identica per calcio e tennis),
// riusando i componenti che c'erano. Contratto col backend:
// AUDIT_2026-10-09/programma_del_giorno/CONTRATTO.md.
//   1. design system v2 (classi ds-v2-*, inerti col guscio spento);
//   2. punteggio e minuto delle partite in gioco (`row.score`): calcio minuto,
//      gol, rossi; tennis set, game, punti e chi batte (`lib/matchClock`);
//   3. liquidita' in evidenza: abbinato del mercato (`fmtMoney`), barra
//      relativa agli altri eventi (`ui/progress`), importo disponibile sotto
//      ogni quota come Betfair;
//   4. menu' del mercato per scheda (voci dal push `board`, correct score
//      esclusi sul calcio; raggruppate con `lib/market-categories`); il mercato
//      scelto arriva dal push `board_mercato` dopo la richiesta (rinnovata ogni
//      30 s, mai per MATCH_ODDS) — vedi `components/board/useBoardCanale.ts`;
//   5. box quote che PIAZZANO DAVVERO: `PlaceConfirmDialog` + `localOrderApi`
//      (canale con ripiego DB, gli stessi dbApi del ladder), comando `place`
//      come `LadderView.execute`; la modalita' e' SEMPRE quella del runner,
//      ignota o OFF = conferma spenta con la ragione scritta;
//   6-7. Statistiche e Trading da `AzioniPartita`, con ritorno al punto esatto
//      (`lib/ritorno`, origine `board`).
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, Radio, CalendarClock } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { countdownToOff, formatMinute, formatScore } from '@/lib/matchClock';
import { DASH, fmtMoney, fmtOdds, fmtTime } from '@/lib/format';
import { useLocalStatus, localOrderApi } from '@/lib/localTransport';
import { getLocalChannel } from '@/lib/localChannel';
import { marketStatusMeta } from '@/lib/mike';
import { CATEGORIES, groupByCategory } from '@/lib/market-categories';
import { ORIGINI_RITORNO, schedaDiRitorno, useRitornoAlPunto } from '@/lib/ritorno';
import {
    LIVE_ORDER_STATUS_LABEL, type LiveOrderCommand, type LiveOrderSide,
} from '@/lib/liveOrders';
import { PlaceConfirmDialog } from '@/components/live/PlaceConfirmDialog';
import { AzioniPartita, dividiNomi, type PartitaAzioni } from '@/components/controlroom/AzioniPartita';
import { TENNIS_ORDER_API } from '@/components/tennis/TennisLadderColumn';
import { CALCIO_DB_ORDER_API } from '@/pages/SeguiLive';
import {
    MATCH_ODDS, escluso, eventiDelMercato, modoApplicato, modoOrdiniBoard, quotaLiquidita,
    vociMenu, volumeMassimo,
    type LineaQuote, type RigaBoard, type SelezioneBoard, type SportBoard, type TipoMercato,
} from '@/components/board/boardDati';
import { avviaMemoriaBoard, useBoardCanale } from '@/components/board/useBoardCanale';

const SPORT_TABS: { key: SportBoard; label: string }[] = [
    { key: 'calcio', label: '⚽ Calcio' },
    { key: 'tennis', label: '🎾 Tennis' },
];

/** importi del tabellone: euro interi col punto delle migliaia (`1.843.210 €`) */
const fmtImporto = (v: number | null): string => fmtMoney(v, { decimals: 0, migliaia: true });

// ---------------------------------------------------------- mercato scelto
// La scelta resta per scheda nella sessione del browser: tornando da
// Statistiche/Trading si ritrova lo stesso mercato (il «punto esatto»).
const chiaveMercato = (sport: SportBoard) => `board.mercato.${sport}`;

function leggiMercatoSalvato(sport: SportBoard): string {
    try {
        const v = sessionStorage.getItem(chiaveMercato(sport));
        return v && !escluso(sport, v) ? v : MATCH_ODDS;
    } catch {
        return MATCH_ODDS;
    }
}

function salvaMercato(sport: SportBoard, tipo: string): void {
    try { sessionStorage.setItem(chiaveMercato(sport), tipo); } catch { /* si perde solo il ricordo */ }
}

// ------------------------------------------------------------- box d'ordine
interface BoxOrdine {
    eventId: string;
    marketId: string;
    selectionId: number;
    handicap: number;
    side: LiveOrderSide;
    price: number;
    selName: string;
    contesto: string;
    /** la modalita' quando il box si e' aperto: se cambia, la conferma si spegne */
    modoApertura: 'paper' | 'live' | null;
}

interface Esito {
    tono: 'attesa' | 'ok' | 'errore';
    testo: string;
}

// ------------------------------------------------------------- pezzi di riga

/** Orario (Roma) e, sotto, IN-PLAY o il conto alla rovescia all'off. */
function Orario({ riga, nowMs }: { riga: RigaBoard; nowMs: number }) {
    const countdown = !riga.inplay ? countdownToOff(riga.open_date, nowMs) : null;
    return (
        <div className="flex flex-col w-[88px] flex-none ds-v2-board-orario">
            <span className="font-mono tabular-nums text-slate-200 ds-v2-board-ora">{fmtTime(riga.open_date)}</span>
            {riga.inplay ? (
                <span className="text-[9px] font-black text-emerald-300 animate-pulse ds-v2-chip ds-v2-board-inplay">● IN-PLAY</span>
            ) : countdown != null ? (
                <span className="text-[9px] font-mono tabular-nums text-amber-300" title="Countdown all'off">
                    OFF in {countdown}
                </span>
            ) : null}
        </div>
    );
}

/** Rossi di una squadra: solo se ce ne sono (mai un «0» inventato). */
function Rossi({ n, chi }: { n: number | null; chi: string }) {
    if (n == null || n <= 0) return null;
    return (
        <span className="inline-flex items-center gap-0.5 text-red-300 font-bold" title={`espulsi ${chi}: ${n}`}
            data-testid="board-rossi">
            <span aria-hidden className="inline-block w-[7px] h-[10px] rounded-[1px] bg-red-500" />
            {n}
        </span>
    );
}

/**
 * Punteggio e minuto delle partite IN GIOCO (contratto §1, `row.score`).
 * Prima del via non si mostra niente; in gioco senza punteggio, «—» (mai 0–0).
 */
function Punteggio({ riga }: { riga: RigaBoard }) {
    if (!riga.inplay) return null;
    const s = riga.score;
    if (!s) {
        return (
            <span className="text-[10px] text-slate-500" data-testid="board-punteggio"
                title="punteggio non ancora arrivato dal feed">{DASH}</span>
        );
    }
    if (s.sport === 'calcio') {
        const minuto = s.ht ? 'INT' : formatMinute(s.minute);
        return (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-mono tabular-nums ds-v2-board-punteggio"
                data-testid="board-punteggio">
                {minuto && <span className="text-emerald-300 font-black ds-v2-board-minuto" data-testid="board-minuto">{minuto}</span>}
                <Rossi n={s.red_home} chi="casa" />
                <span className="text-white font-black" data-testid="board-gol">{formatScore(s.home, s.away) ?? DASH}</span>
                <Rossi n={s.red_away} chi="ospiti" />
            </span>
        );
    }
    const [g1, g2] = dividiNomi(riga.event_name);
    const batte = s.server === 'p1' ? g1 : s.server === 'p2' ? g2 : null;
    const pezzi: string[] = [];
    const set = s.sets ? formatScore(s.sets.p1, s.sets.p2) : null;
    const game = s.games ? formatScore(s.games.p1, s.games.p2) : null;
    if (set) pezzi.push(`Set ${set}`);
    if (game) pezzi.push(`Game ${game}`);
    if (s.points) pezzi.push(`${s.points.p1}–${s.points.p2}`);
    return (
        <span className="inline-flex items-center gap-1.5 text-[11px] font-mono tabular-nums ds-v2-board-punteggio"
            data-testid="board-punteggio">
            <span className="text-white font-black" data-testid="board-set-game">{pezzi.length ? pezzi.join(' · ') : DASH}</span>
            {batte && (
                <span className="text-emerald-300 font-bold" data-testid="board-batte" title="al servizio">● batte {batte}</span>
            )}
        </span>
    );
}

/** Abbinato del mercato + barra relativa al mercato piu' scambiato della lista. */
function Liquidita({ v, max }: { v: number | null; max: number | null }) {
    const q = quotaLiquidita(v, max);
    return (
        <div className="w-[120px] flex-none ds-v2-board-liquidita" data-testid="board-liquidita">
            <div className="text-[9px] uppercase tracking-wider text-slate-500 ds-v2-board-etichetta">Abbinati</div>
            <div className="font-mono tabular-nums font-black text-[12px] text-slate-100 ds-v2-board-abbinati"
                data-testid="board-abbinati">{fmtImporto(v)}</div>
            {q != null ? (
                <Progress
                    value={q}
                    // ui/progress non passa `value` alla radice Radix: senza questo
                    // la barra non dichiara il suo valore (design system §7)
                    aria-valuenow={q}
                    aria-label={`Liquidità: ${q} % del mercato più scambiato della lista`}
                    className="h-1.5 mt-1 bg-white/10 ds-v2-board-barretta"
                    indicatorClassName="bg-primary/80"
                    data-testid="board-barra-liquidita"
                />
            ) : (
                <div className="text-[9px] text-slate-500 mt-0.5">liquidità non nota</div>
            )}
        </div>
    );
}

/** Una casella di quota cliccabile: prezzo e, sotto, l'importo disponibile. */
function BottoneQuota({ lato, prezzo, disponibile, nome, onClick, disabled }: {
    lato: 'back' | 'lay'; prezzo: number | null; disponibile: number | null; nome: string;
    onClick: () => void; disabled: boolean;
}) {
    const back = lato === 'back';
    const spento = disabled || prezzo == null || !(prezzo > 1);
    return (
        <button
            type="button"
            disabled={spento}
            onClick={onClick}
            aria-label={`${back ? 'BACK' : 'LAY'} ${nome} a ${fmtOdds(prezzo)}`}
            data-testid={`board-quota-${lato}`}
            className={`flex flex-col items-center justify-center min-w-[56px] h-[38px] px-1 rounded border font-mono tabular-nums transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                back
                    ? 'bg-sky-500/15 border-sky-500/40 text-sky-300 hover:bg-sky-500/25 ds-v2-quota--back'
                    : 'bg-rose-500/15 border-rose-500/40 text-rose-300 hover:bg-rose-500/25 ds-v2-quota--lay'
            } ds-v2-board-prezzo`}
        >
            <span className="text-[12px] font-bold leading-none">{fmtOdds(prezzo)}</span>
            <span className="text-[9px] leading-none mt-0.5 opacity-80 ds-v2-board-disp" data-testid={`board-disp-${lato}`}>
                {fmtImporto(disponibile)}
            </span>
        </button>
    );
}

// ------------------------------------------------------------ una scheda sport

function SportBoardScheda({ sport }: { sport: SportBoard }) {
    const [tipo, setTipo] = useState<string>(() => leggiMercatoSalvato(sport));
    const { stato, tabellone, mercato, erroreMercato, modo } = useBoardCanale(sport, tipo);

    // orologio per il countdown all'off e per la freschezza del modo dal `now` (1 s)
    const [nowTick, setNowTick] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setNowTick(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    const modoBox = modoOrdiniBoard(modoApplicato(modo.alCambio, modo.dalNow, nowTick), modo.freno);
    const voci = useMemo(() => vociMenu(sport, tabellone?.marketTypes ?? null), [sport, tabellone]);

    // ordini: il percorso manuale che esiste gia' (canale con ripiego DB)
    const orderApi = useMemo(
        () => localOrderApi(sport, sport === 'calcio' ? CALCIO_DB_ORDER_API : TENNIS_ORDER_API),
        [sport],
    );
    const [box, setBox] = useState<BoxOrdine | null>(null);
    const inviando = useRef(false);
    const [occupato, setOccupato] = useState(false);
    const [esito, setEsito] = useState<Esito | null>(null);

    const scegliTipo = useCallback((t: string) => {
        setTipo(t);
        salvaMercato(sport, t);
        setBox(null);
    }, [sport]);

    // un tipo che il runner non dichiara piu' (lista nota e non vuota): si torna al Match Odds
    useEffect(() => {
        const tipi = tabellone?.marketTypes;
        if (tipo === MATCH_ODDS || !tipi || tipi.length === 0) return;
        if (!voci.some((v) => v.market_type === tipo)) scegliTipo(MATCH_ODDS);
    }, [tipo, tabellone, voci, scegliTipo]);

    const vista = useMemo(
        () => (tabellone ? eventiDelMercato(tabellone.rows, tipo, mercato) : null),
        [tabellone, tipo, mercato],
    );
    const eventi = vista?.eventi ?? [];
    const maxVol = volumeMassimo(eventi);

    // ritorno da Statistiche/Trading: la partita torna in vista quando c'e'
    useRitornoAlPunto('/board', eventi.length > 0);

    const apriBox = (riga: RigaBoard, linea: LineaQuote, sel: SelezioneBoard, side: LiveOrderSide) => {
        const price = side === 'back' ? sel.back : sel.lay;
        if (price == null) return;
        // il nome del Match Odds e' quello del menu' (dal backend, in italiano)
        const nomeMercato = linea.market_name ?? voci[0]?.name ?? 'Match Odds';
        setBox({
            eventId: riga.event_id,
            marketId: linea.market_id,
            selectionId: sel.selection_id,
            // contratto §4: l'handicap della selezione; assente = 0 come nel ladder
            handicap: sel.handicap ?? 0,
            side,
            price,
            selName: sel.name ?? `selezione ${sel.selection_id}`,
            contesto: `${riga.event_name} · ${nomeMercato}`,
            modoApertura: modoBox.mode,
        });
    };

    /** Perche' il box aperto non puo' confermare adesso (null = puo'). */
    const motivoBlocco = (b: BoxOrdine): string | null => {
        if (occupato) return 'Un ordine è già in invio: attendi l\'esito prima del prossimo.';
        if (modoBox.motivo) return modoBox.motivo;
        if (b.modoApertura !== modoBox.mode) {
            return `La modalità ordini è cambiata mentre il box era aperto (ora ${modoBox.etichetta}): chiudi e riapri il box.`;
        }
        const linea = eventi.find((e) => e.riga.event_id === b.eventId)?.linee.find((l) => l.market_id === b.marketId);
        if (!linea) return 'Il mercato non è più nel tabellone: chiudi il box.';
        const st = marketStatusMeta(linea.status);
        if (st) return `Mercato ${st.label}: Betfair non accetta ordini adesso.`;
        return null;
    };

    const invia = async (b: BoxOrdine, amount: number, price: number) => {
        // guardia anti-doppio-invio (come LadderView.submit): un ordine alla volta
        if (inviando.current) return;
        const mode = modoBox.mode;
        if (mode == null || motivoBlocco(b) != null) return;
        inviando.current = true;
        setOccupato(true);
        setBox(null);
        const lato = b.side === 'back' ? 'BACK' : 'LAY';
        const etichetta = `${lato} ${b.selName} @ ${price.toFixed(2)} · ${fmtMoney(amount)}`;
        // backend 09/10: su una partita non ancora seguita il runner la aggancia al
        // volo (fino a ~7 s; il canale aspetta al piu' 10 s): lo si dice, non si tace
        setEsito({ tono: 'attesa', testo: `Invio in corso (aggancio della partita se non è già seguita): ${etichetta}…` });
        const cmd: LiveOrderCommand = {
            action: 'place', mode, market_id: b.marketId,
            selection_id: b.selectionId, handicap: b.handicap, side: b.side,
            order_type: 'LIMIT', price, persistence: 'LAPSE', size: amount,
        };
        try {
            const res = await orderApi.send(cmd);
            if (res.ok) {
                const dettagli = [
                    res.bet_id ? `bet ${res.bet_id}` : null,
                    res.status ? (LIVE_ORDER_STATUS_LABEL[res.status] ?? res.status) : null,
                    res.size_matched ? `abbinato ${fmtMoney(res.size_matched)}` : null,
                ].filter(Boolean).join(' · ');
                toast.success(`Ordine ${mode === 'live' ? 'REALE' : 'simulato'} piazzato`, {
                    description: `${etichetta}${dettagli ? ` · ${dettagli}` : ''}`,
                });
                setEsito({ tono: 'ok', testo: `✓ ${etichetta}${dettagli ? ` — ${dettagli}` : ''}` });
            } else {
                const motivo = res.error ?? res.detail ?? 'motivo non noto';
                toast.error('Ordine rifiutato', { description: `${etichetta}: ${motivo}` });
                setEsito({ tono: 'errore', testo: `✗ ${etichetta}: ${motivo}` });
            }
        } catch (e: unknown) {
            // trasporto: esito IGNOTO — il messaggio dice gia' «NON reinviare»
            const msg = e instanceof Error ? e.message : 'errore sconosciuto';
            toast.error('Errore ordine', { description: msg });
            setEsito({ tono: 'errore', testo: `✗ ${etichetta}: ${msg}` });
        } finally {
            inviando.current = false;
            setOccupato(false);
        }
    };

    if (stato === 'off') {
        return (
            <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center ds-v2-vuoto">
                <Radio className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-[11px] text-slate-400">
                    Canale locale {sport} non attivo (ws://127.0.0.1:{sport === 'calcio' ? 47331 : 47332}).
                    Avvia l'app desktop / il runner {sport} per il programma in tempo reale.
                </p>
            </Card>
        );
    }

    if (!tabellone || !vista) {
        return (
            <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center ds-v2-vuoto">
                <p className="text-[11px] text-slate-400">Canale connesso: in attesa del primo tabellone…</p>
            </Card>
        );
    }

    const chipModo = modoBox.mode === 'live'
        ? 'bg-red-500 text-white border-red-400 ds-v2-chip--live'
        : modoBox.mode === 'paper'
            ? 'bg-amber-500/15 text-amber-300 border-amber-500/40 ds-v2-chip--paper'
            : 'bg-white/10 text-white/70 border-white/15 ds-v2-chip--fermo';

    return (
        <div>
            {/* barra della scheda: menu' del mercato e modalita' ordini del runner */}
            <div className="flex items-center gap-3 flex-wrap mb-2 text-[11px] ds-v2-board-barra">
                <label className="flex items-center gap-2 font-bold text-slate-300">
                    Mercato
                    <MenuMercato sport={sport} voci={voci} tipo={tipo} onScegli={scegliTipo} />
                </label>
                <span className="text-slate-500" data-testid="board-conteggio">
                    {eventi.length} {eventi.length === 1 ? 'evento' : 'eventi'}
                </span>
                {!tabellone.marketTypes && (
                    <span className="text-slate-500" data-testid="board-tipi-assenti">
                        tipi di mercato non ancora letti dal runner: per ora solo Match Odds
                    </span>
                )}
                {!getLocalChannel(sport).puoComandare() && (
                    <span className="text-amber-300" data-testid="board-ripiego-db"
                        title="senza il token dell'app gli ordini passano dalla coda del database">
                        fuori dall'app: gli ordini vanno sulla coda DB, che non aggancia le partite non seguite
                    </span>
                )}
                <span
                    className={`ml-auto px-2 py-0.5 rounded-full border text-[10px] font-black ds-v2-chip ${chipModo}`}
                    data-testid="board-modo"
                    title={modoBox.motivo ?? 'la modalità ordini è quella del runner: la pagina non la sceglie'}
                >
                    {modoBox.etichetta}
                </span>
            </div>

            {esito && (
                <div
                    role="status"
                    data-testid="board-esito"
                    className={`mb-2 px-3 py-1.5 rounded-md border text-[11px] font-semibold ${
                        esito.tono === 'ok'
                            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 ds-v2-strip--paper'
                            : esito.tono === 'errore'
                                ? 'border-red-500/40 bg-red-500/10 text-red-300 ds-v2-strip--live'
                                : 'border-white/15 bg-white/5 text-slate-300 ds-v2-strip--info'
                    }`}
                >
                    {esito.testo}
                </div>
            )}

            {erroreMercato && (
                <div className="mb-2 text-[11px] text-amber-300" data-testid="board-mercato-errore">
                    Il runner non ha servito questo mercato: {erroreMercato}. Si riprova da soli ogni 30 s.
                </div>
            )}

            {vista.attesa ? (
                <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center ds-v2-vuoto">
                    <p className="text-[11px] text-slate-400" data-testid="board-mercato-attesa">
                        {erroreMercato
                            ? 'Nessuna quota per questo mercato: il runner non l\'ha servito (motivo sopra).'
                            : 'Caricamento delle quote del mercato scelto (il primo arrivo può richiedere una decina di secondi)…'}
                    </p>
                </Card>
            ) : eventi.length === 0 ? (
                <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center ds-v2-vuoto">
                    <p className="text-[11px] text-slate-400">
                        {tipo === MATCH_ODDS
                            ? 'Nessun evento nel programma di oggi.'
                            : 'Nessun evento del programma ha questo mercato.'}
                    </p>
                </Card>
            ) : (
                <div className="space-y-1.5 ds-v2-tabella ds-v2-board-tabella">
                    {eventi.map(({ riga, linee }) => {
                        const koMs = Date.parse(riga.open_date);
                        const partita: PartitaAzioni = {
                            event_id: riga.event_id,
                            sport,
                            nome: riga.event_name,
                            koMs: Number.isFinite(koMs) ? koMs : null,
                            marketId: riga.market_id,
                            media: null,
                            extra: { fixtureId: riga.fixture_id },
                        };
                        const boxQui = box && box.eventId === riga.event_id ? box : null;
                        return (
                            <div
                                key={riga.event_id}
                                data-event-id={riga.event_id}
                                data-testid="board-riga"
                                className="rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-[11px] ds-v2-riga"
                            >
                                <div className="flex items-center gap-3 flex-wrap">
                                    <Orario riga={riga} nowMs={nowTick} />

                                    {/* evento e punteggio */}
                                    <div className="flex-1 min-w-[180px]">
                                        <div className="font-bold text-slate-100 truncate ds-v2-board-evento" title={riga.event_name}>
                                            {riga.event_name}
                                        </div>
                                        <div className="flex items-center gap-2 flex-wrap mt-0.5">
                                            <Punteggio riga={riga} />
                                        </div>
                                    </div>

                                    {/* linee del mercato scelto: liquidita' + quote back/lay */}
                                    <div className="flex flex-col gap-1.5">
                                        {linee.map((l) => {
                                            const statoLinea = marketStatusMeta(l.status);
                                            return (
                                            <div key={l.market_id} className="flex items-center gap-3 ds-v2-board-linea"
                                                data-testid="board-linea" data-market-id={l.market_id}>
                                                {(l.market_name || statoLinea) && (
                                                    <span className="w-[110px] flex flex-col text-[10px] ds-v2-board-nome-linea">
                                                        {l.market_name && (
                                                            <span className="truncate text-slate-400" title={l.market_name}>{l.market_name}</span>
                                                        )}
                                                        {statoLinea && (
                                                            <span className={statoLinea.cls} data-testid="board-stato-mercato">{statoLinea.label}</span>
                                                        )}
                                                    </span>
                                                )}
                                                <Liquidita v={l.total_matched} max={maxVol} />
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    {l.selections.map((sel) => {
                                                        const nome = sel.name ?? DASH;
                                                        return (
                                                            <div key={`${sel.selection_id}:${sel.handicap ?? 0}`}
                                                                className="flex flex-col items-center" title={nome}
                                                                data-testid="board-selezione">
                                                                <span className="text-[10px] text-slate-400 truncate max-w-[118px] mb-0.5 ds-v2-board-nome">
                                                                    {nome}
                                                                </span>
                                                                <span className="inline-flex gap-1 ds-v2-board-quote">
                                                                    <BottoneQuota lato="back" prezzo={sel.back} disponibile={sel.back_size}
                                                                        nome={nome} disabled={false}
                                                                        onClick={() => apriBox(riga, l, sel, 'back')} />
                                                                    <BottoneQuota lato="lay" prezzo={sel.lay} disponibile={sel.lay_size}
                                                                        nome={nome} disabled={false}
                                                                        onClick={() => apriBox(riga, l, sel, 'lay')} />
                                                                </span>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                            );
                                        })}
                                    </div>

                                    {/* video/statistiche Betfair, Statistiche, Trading, Segui live */}
                                    <AzioniPartita
                                        p={partita}
                                        scheda={sport}
                                        ritorno={ORIGINI_RITORNO.board}
                                        statisticheTennis
                                    />
                                </div>

                                {boxQui && (
                                    <PlaceConfirmDialog
                                        key={`${boxQui.marketId}:${boxQui.selectionId}:${boxQui.side}:${boxQui.price}`}
                                        inline
                                        prezzoModificabile
                                        side={boxQui.side}
                                        price={boxQui.price}
                                        priceLabel={fmtOdds(boxQui.price)}
                                        initialAmount={0}
                                        asLiability={false}
                                        selName={boxQui.selName}
                                        contesto={boxQui.contesto}
                                        mode={modoBox.mode}
                                        bloccato={motivoBlocco(boxQui)}
                                        onConfirm={(amount, price) => { void invia(boxQui, amount, price); }}
                                        onCancel={() => setBox(null)}
                                    />
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {(vista.senzaMercato > 0 || vista.orfani > 0) && (
                <p className="mt-2 text-[10px] text-slate-500" data-testid="board-note-mercato">
                    {vista.senzaMercato > 0 && `${vista.senzaMercato} eventi del programma non hanno questo mercato.`}
                    {vista.senzaMercato > 0 && vista.orfani > 0 && ' '}
                    {vista.orfani > 0 && `${vista.orfani} mercati di eventi fuori dal programma non mostrati.`}
                </p>
            )}
        </div>
    );
}

/**
 * Il menu' del mercato (globale per la scheda, come la coupon di Betfair):
 * un <select> col design system. Sul calcio le voci sono raggruppate con le
 * categorie di `lib/market-categories` (le stesse di Segui live e del Replay).
 */
function MenuMercato({ sport, voci, tipo, onScegli }: {
    sport: SportBoard; voci: TipoMercato[]; tipo: string; onScegli: (t: string) => void;
}) {
    const etichetta = (v: TipoMercato) => `${v.name}${v.count != null ? ` (${v.count})` : ''}`;
    const opzione = (v: TipoMercato) => <option key={v.market_type} value={v.market_type}>{etichetta(v)}</option>;
    // la scelta corrente compare sempre, anche se la lista non e' ancora arrivata
    const tutte = voci.some((v) => v.market_type === tipo)
        ? voci : [...voci, { market_type: tipo, name: tipo, count: null }];
    let contenuto: ReactNode;
    if (sport === 'calcio') {
        const gruppi = groupByCategory(tutte);
        contenuto = CATEGORIES.filter((c) => (gruppi.get(c.key)?.length ?? 0) > 0).map((c) => (
            <optgroup key={c.key} label={c.label}>{(gruppi.get(c.key) ?? []).map(opzione)}</optgroup>
        ));
    } else {
        contenuto = tutte.map(opzione);
    }
    return (
        <select
            value={tipo}
            onChange={(e) => onScegli(e.target.value)}
            aria-label="Mercato"
            data-testid="board-mercato"
            className="rounded-md bg-black/50 border border-white/10 px-2 py-1 text-xs text-slate-100 ds-v2-campo"
        >
            {contenuto}
        </select>
    );
}

export default function Board() {
    // il ritorno da Statistiche/Trading riapre la scheda da cui si era partiti
    const [sport, setSport] = useState<SportBoard>(
        () => (schedaDiRitorno('/board') === 'tennis' ? 'tennis' : 'calcio'),
    );
    const calcioStatus = useLocalStatus('calcio');
    const tennisStatus = useLocalStatus('tennis');
    // la memoria dei due sport parte subito: il tabellone e il modo ordini che
    // arrivano sulla scheda non aperta ci sono gia' quando la si apre
    useEffect(() => { avviaMemoriaBoard('calcio'); avviaMemoriaBoard('tennis'); }, []);

    return (
        <div className="min-h-screen bg-background relative pb-16">
            <Helmet><title>Programma del giorno | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30 ds-v2-nascondi" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky ds-v2-non-sticky top-0 z-50 ds-v2-navbar">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between ds-v2-navbar-dentro">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" data-nav-legacy className="font-display font-black text-xl tracking-tighter">
                            AI <span className="text-primary">TERMINAL</span>
                        </Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-primary font-heading font-bold ml-4">
                            <CalendarClock className="w-4 h-4" /> PROGRAMMA
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/safe-strategy">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                🛡️ Safe Strategy
                            </Button>
                        </Link>
                        <Link to="/segui-live">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                Segui Live
                            </Button>
                        </Link>
                        <Link to="/dashboard" data-nav-legacy>
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                            </Button>
                        </Link>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 relative z-10 max-w-6xl ds-v2-pagina ds-v2-largo">
                <div className="mb-4">
                    <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight ds-v2-titolo">
                        Programma del <span className="text-primary">giorno</span>
                    </h1>
                    <p className="text-[11px] text-muted-foreground mt-1">
                        Tabellone in tempo reale dal canale locale del runner: quote, liquidità e punteggio
                        si aggiornano a ogni push (nessuna lettura DB). Clic su una quota per piazzare.
                    </p>
                </div>

                {/* schede sport + stato del canale per sport */}
                <div className="flex items-stretch gap-1 border-b border-white/5 mb-3 ds-v2-tabbar ds-v2-board-tabbar">
                    {SPORT_TABS.map(t => {
                        const st = t.key === 'calcio' ? calcioStatus : tennisStatus;
                        return (
                            <button
                                key={t.key}
                                type="button"
                                onClick={() => setSport(t.key)}
                                aria-pressed={sport === t.key}
                                className={`ds-v2-tab px-3 py-1.5 -mb-px rounded-t-lg text-xs font-bold border-b-2 transition-colors ${
                                    sport === t.key
                                        ? 'border-primary text-white bg-white/[0.06]'
                                        : 'border-transparent text-muted-foreground hover:text-white hover:bg-white/[0.03]'
                                }`}
                            >
                                {t.label}
                                <span
                                    className={`ml-1.5 inline-block w-1.5 h-1.5 rounded-full align-middle ${
                                        st === 'connected' ? 'bg-emerald-400' : 'bg-slate-600'
                                    }`}
                                    title={st === 'connected' ? 'Canale locale connesso' : 'Canale locale non attivo'}
                                />
                            </button>
                        );
                    })}
                </div>

                <SportBoardScheda key={sport} sport={sport} />
            </main>
        </div>
    );
}
