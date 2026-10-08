// ============================================================================
// ScatolaCashOut.tsx - 08/10 (cantiere W1): la SCATOLA di una partita nella
// pagina «Cash Out» (`pages/CashOut.tsx`). Monta pezzi che il software ha gia':
//   * testata: `NomiPartita`, `StatoPill` e `TennisVivoBar` (`SchedaPartita`),
//     `StatoPartitaRiga` (scheda «Posizioni aperte»), `AzioniPartita` con
//     `soloMediaStatistiche` (Video | Stats Betfair e «Statistiche», come nel
//     prototipo) col ritorno al Cash Out;
//   * una riga per gamba dei bot: `RigaOperazione` (quota di adesso, «chiudi
//     ora» al ms, il «Chiudi» del SUO bot = comando di oggi, `chiudiRiga.ts`)
//     con un testo che dice quanto chiude (Mike: tutte le sue gambe), e il
//     pulsante «Ladder» del mercato;
//   * una riga per selezione con ordini fuori dai bot (sito, app): «se chiudo
//     ora» con la matematica UNICA (`lib/cashOutPartita.ts`) e il comando del
//     contratto con il cantiere W2 (`sendGreenupFuoriBot`), solo LIVE, con la
//     doppia conferma;
//   * in fondo il cash out della posizione: `CashOutPartita` (Safe),
//     `CashOutGlobalePartita` (gambe dei bot, LIVE e PROVA separati, «Chiudi
//     tutte le gambe dei bot») e, se ci sono ordini fuori dai bot, il totale
//     LIVE bot + fuori bot con un solo gesto che orchestra i comandi esistenti.
// Secondo giro: la scatola riporta alla pagina la cifra che GIA' calcola
// (`onSintesi`, una fonte per scatola) per il riepilogo in testa.
// Nessuna lettura nuova: tutto arriva da `useControlRoom()` della pagina.
// 08/10 sera (D-6): una scatola CONCLUSA (Match Odds chiuso da Betfair,
// posizioni da regolare) dice «conclusa · posizioni da regolare» e tiene i
// pulsanti di cash out SPENTI col motivo (`motivoCashOutConclusa`, stesso
// meccanismo dei pulsanti di soldi spenti); lo scalper resta fermabile (il suo
// pulsante ferma la sessione, non piazza un cash out sul mercato chiuso).
// ============================================================================
import { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import { AzioniPartita } from '@/components/controlroom/AzioniPartita';
import { NomiPartita } from '@/components/controlroom/NomiPartita';
import { StatoPill, TennisVivoBar } from '@/components/controlroom/SchedaPartita';
import { CashOutPartita } from '@/components/controlroom/CashOutPartita';
import {
    CashOutGlobalePartita, motivoPrezziFermi, pianoChiusuraPartita, testoPiano, SCADENZA_ARMATURA_MS,
    type ComandoChiusura,
} from '@/components/controlroom/CashOutGlobale';
import { RigaOperazione } from '@/components/controlroom/DettaglioRigaView';
import { ChiusuraRigaContext } from '@/components/controlroom/BottoneChiudiRiga';
import { ATTESA_CONFERMA_USCITE_MS } from '@/components/controlroom/InterruttoreUscite';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import { useCashOutPartita, useRiportaSintesi, type SintesiCashOut } from '@/components/controlroom/useCashOutPartita';
import { trovaEsitoCashOut } from '@/components/controlroom/trovaEsitoUscita';
import { faseMostrata, TESTO_FASE, type FaseChiusura } from '@/components/controlroom/chiudiRiga';
import { RigaPosizioneOrfana, StatoPartitaRiga } from '@/components/controlroom/aperte/PosizioniAperte';
import { statoPartitaAperta } from '@/components/controlroom/aperte/statoPartitaAperta';
import {
    gambeFuoriBot, motivoCashOutConclusa, selezioniFuoriBot, testoCashOutRiga, TESTO_CONCLUSA,
    type ScatolaCashOut as Scatola, type SelezioneFuoriBot,
} from '@/components/controlroom/aperte/cashOutPagina';
import { dueEsitiMike, dueEsitiPartita, esitoDecisoMike } from '@/lib/cashOutPartita';
import { sendGreenupFuoriBot } from '@/lib/liveOrders';
import { apriLadderPopout } from '@/lib/ladderPopout';
import { ORIGINI_RITORNO } from '@/lib/ritorno';
import { isErrorRow, isSettled } from '@/lib/eventGroups';
import { BOT_LABEL } from '@/lib/controlRoom';
import { fmtAge, fmtMoney, fmtOdds, fmtTime, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { MikeEvent } from '@/lib/mike';
import type { StatoChiusuraEvento } from '@/lib/chiusuraUtente';
import type { SorgenteLadder } from '@/components/controlroom/usePrezzoAlMs';

/** I gesti di Safe sulla partita (come `SchedaPartita.safe`). */
export interface SafeScatola {
    modalita: 'paper' | 'live' | null;
    statoChiusura: (eventId: string) => StatoChiusuraEvento;
    onCashOut: (eventId: string) => Promise<void>;
    onRiprendi: (eventId: string) => Promise<void>;
}

const NESSUNA_RIGA: [] = [];

// ------------------------------------------------------------------ comandi

/** L'esito di un green-up degli ordini fuori dai bot, con le parole del «Chiudi» di riga. */
export interface EsitoFuoriBot { fase: FaseChiusura; motivo: string | null }

/** Manda il comando del contratto W2 e traduce l'esito; non lancia mai. */
export async function greenupFuoriBot(marketId: string, selectionId: number): Promise<EsitoFuoriBot> {
    try {
        const r = await sendGreenupFuoriBot({ marketId, selectionId });
        return r.ok ? { fase: 'eseguita', motivo: r.detail ?? null } : { fase: 'rifiutata', motivo: r.error ?? 'comando non eseguito' };
    } catch (e) {
        // timeout del polling: l'ordine POTREBBE essere partito (mai reinviare)
        return { fase: 'ignota', motivo: e instanceof Error ? e.message : String(e) };
    }
}

/**
 * Il pulsante dei SOLDI VERI con la doppia conferma, nella stessa forma del
 * «Chiudi» di riga in live (`BottoneChiudiRiga`): il primo clic arma, la
 * conferma e' inerte per ATTESA_CONFERMA_USCITE_MS e cade da sola dopo
 * SCADENZA_ARMATURA_MS o se il pulsante si spegne.
 */
export function BottoneSoldiVeri({ testo, ambito, testId, spentoPerche, inVolo, onConferma }: {
    testo: string;
    ambito: string;
    testId: string;
    /** non null = spento, col motivo scritto */
    spentoPerche: string | null;
    inVolo: boolean;
    onConferma: () => void;
}) {
    const [armatoDa, setArmatoDa] = useState<number | null>(null);
    const [, setTic] = useState(0);
    useEffect(() => {
        if (armatoDa == null) return undefined;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_USCITE_MS + 20);
        const s = window.setTimeout(() => setArmatoDa(null), SCADENZA_ARMATURA_MS);
        return () => { window.clearTimeout(t); window.clearTimeout(s); };
    }, [armatoDa]);
    useEffect(() => { if (spentoPerche != null || inVolo) setArmatoDa(null); }, [spentoPerche, inVolo]);
    const troppoPresto = armatoDa != null && Date.now() - armatoDa < ATTESA_CONFERMA_USCITE_MS;
    if (armatoDa != null) {
        return (
            <span className="inline-flex items-baseline gap-1 flex-wrap">
                <button type="button" data-testid={`${testId}-conferma`} disabled={troppoPresto}
                    onClick={() => { if (!troppoPresto) { setArmatoDa(null); onConferma(); } }}
                    className="h-6 px-2 text-[10px] rounded bg-orange-500 text-black font-bold uppercase disabled:opacity-40">
                    Conferma
                </button>
                <span className="text-[10px] text-orange-300" data-testid={`${testId}-armato`}>
                    Live, soldi veri: confermi? {ambito}.{' '}
                    <button type="button" className="underline" onClick={() => setArmatoDa(null)}
                        data-testid={`${testId}-annulla`}>annulla</button>
                </span>
            </span>
        );
    }
    return (
        <span className="inline-flex items-baseline gap-1 flex-wrap">
            <button type="button" data-testid={testId} disabled={spentoPerche != null || inVolo}
                title={spentoPerche ?? `soldi veri: ${ambito}`}
                onClick={() => setArmatoDa(Date.now())}
                className="h-6 px-2 text-[10px] uppercase tracking-wider rounded border border-rose-500/40 bg-rose-500/10 text-rose-200 font-semibold disabled:opacity-40">
                {testo}
            </button>
            <span className="text-[9px] text-white/45" data-testid={`${testId}-ambito`}>{ambito}</span>
            {spentoPerche != null && (
                <span className="text-[9px] text-white/40" data-testid={`${testId}-spento`}>{spentoPerche}</span>
            )}
        </span>
    );
}

/** «Ladder»: apre il ladder di QUEL mercato nella finestra pop-out (stessa del LadderView). */
function BottoneLadder({ sport, marketId, eventId, eventName, marketName, giocatori }: {
    sport: 'calcio' | 'tennis';
    marketId: string | null;
    eventId: string;
    eventName: string;
    marketName?: string | null;
    giocatori?: { p1: string | null; p2: string | null } | null;
}) {
    return (
        <button type="button" data-testid="co-ladder" data-market={marketId ?? ''}
            disabled={!marketId}
            title={marketId ? 'apri il ladder di questo mercato in una finestra a parte'
                : 'il bot non pubblica il mercato di questa riga: niente ladder da aprire'}
            onClick={() => {
                if (!marketId) return;
                const ok = apriLadderPopout({
                    sport, marketId, eventId, eventName, marketName,
                    p1: giocatori?.p1 ?? null, p2: giocatori?.p2 ?? null,
                });
                if (!ok) toast.error('Popup bloccato dal browser', { description: 'Consenti i popup per aprire il ladder.' });
            }}
            className="shrink-0 h-5 px-1.5 text-[9px] uppercase tracking-wider rounded border border-white/15 text-white/70 hover:text-white disabled:opacity-40 inline-flex items-center gap-1">
            <ExternalLink className="w-2.5 h-2.5" />Ladder
        </button>
    );
}

// ------------------------------------------------------- ordini fuori dai bot

/** Una selezione con ordini fuori dai bot: ordini, «se chiudo ora», cash out, ladder. */
function RigaFuoriBot({ sel, sorgente, dueEsiti, eventId, eventName, spentoConclusa = null }: {
    sel: SelezioneFuoriBot;
    sorgente: SorgenteLadder | null;
    dueEsiti?: (marketId: string) => boolean;
    eventId: string;
    eventName: string;
    /** D-6: partita conclusa (mercato CHIUSO): il cash out e' spento con questo motivo */
    spentoConclusa?: string | null;
}) {
    const gambe = useMemo(() => gambeFuoriBot(sel.ordini, dueEsiti), [sel.ordini, dueEsiti]);
    const r = useCashOutPartita({ operazioni: NESSUNA_RIGA, gambeExtra: gambe, sorgente, sport: 'calcio', dueEsiti });
    const [inVolo, setInVolo] = useState(false);
    const [esito, setEsito] = useState<EsitoFuoriBot | null>(null);
    const live = r?.live ?? null;
    const origini = sel.origini.join(' + ');
    const spento = spentoConclusa ?? (!sel.abbinato ? 'nulla di abbinato su questa selezione: niente da chiudere'
        : live == null ? 'cifra non calcolabile'
            : motivoPrezziFermi(live) ?? (live.netto == null ? 'cifra non calcolabile: non si chiude alla cieca' : null));
    return (
        <div className="flex items-start gap-2 text-[11px]" data-testid="co-fuori-bot"
            data-origine={origini} data-selezione={sel.chiave}>
            <div className="flex-1 min-w-0 flex items-baseline gap-1.5 flex-wrap">
                <span className="text-[9px] font-bold uppercase tracking-wider px-1 rounded bg-indigo-400/10 text-indigo-200 border border-indigo-400/30"
                    data-testid="co-fuori-bot-origine"
                    title="ordine tuo fuori dai bot: «Sito» = fatto su betfair.com (trovato sul conto), «App» = dal ladder dell'app">
                    {origini}
                </span>
                <span className="text-white/75">{sel.selezione ?? `selezione ${sel.selectionId}`}</span>
                {sel.mercato && <span className="text-white/40">{sel.mercato}</span>}
                {sel.ordini.map((o) => (
                    <span key={o.bet_id} className="font-mono tabular-nums text-white/60" data-testid="co-fuori-bot-ordine">
                        <span className={o.side === 'LAY' ? 'text-rose-300' : 'text-sky-300'}>{o.side}</span>
                        {o.price_matched == null
                            ? <span className="text-white/50"> non abbinato</span>
                            : <>{' '}{fmtMoney(o.size_matched)} @ {fmtOdds(o.price_matched)}</>}
                        {o.size_remaining > 0 && <span className="text-white/40"> (+{fmtMoney(o.size_remaining)} sul book)</span>}
                    </span>
                ))}
                <span className="text-[10px] text-white/40 flex items-baseline gap-1" data-testid="co-fuori-bot-chiudo-ora">
                    chiudi ora
                    {live?.netto != null ? (
                        <span className={`font-mono font-semibold ${pnlClass(live.netto)}`} data-testid="co-fuori-bot-pnl"
                            title="P&L netto di commissione chiudendo ADESSO, per intero, gli ordini fuori dai bot di questa selezione">
                            {fmtMoney(live.netto, { signed: true })}
                        </span>
                    ) : (
                        <span className="text-orange-400" data-testid="co-fuori-bot-pnl"
                            title={live?.mancanti.join('; ') || 'nulla di abbinato'}>{DASH}</span>
                    )}
                    {live?.netto != null && (
                        <MarchioSoldi fonte="pagina" etaS={live.etaIgnota ? null : live.etaPrezziS ?? undefined}
                            dettaglio="ordini fuori dai bot, stessa matematica del cash out della partita" testId="co-fuori-bot-marchio" />
                    )}
                </span>
                <BottoneSoldiVeri testo="Cash out" testId="co-fuori-bot-cashout"
                    ambito={`green-up degli ordini ${origini} su questa selezione (non tocca i bot)`}
                    spentoPerche={spento} inVolo={inVolo}
                    onConferma={() => {
                        setInVolo(true);
                        setEsito({ fase: 'inviata', motivo: null });
                        void greenupFuoriBot(sel.marketId, sel.selectionId)
                            .then(setEsito).finally(() => setInVolo(false));
                    }} />
                {esito && (
                    <span className="text-[9px] text-white/70" data-testid="co-fuori-bot-esito" data-fase={esito.fase}>
                        {TESTO_FASE[esito.fase]}{esito.motivo ? `: ${esito.motivo}` : ''}
                    </span>
                )}
            </div>
            <BottoneLadder sport="calcio" marketId={sel.marketId} eventId={eventId} eventName={eventName}
                marketName={sel.mercato} />
        </div>
    );
}

/**
 * Il cash out di TUTTA la posizione LIVE col conto: gambe dei bot + ordini
 * fuori dai bot, la stessa somma (`useCashOutPartita` con le gambe in piu').
 * Un gesto solo: prima i comandi dei bot (il piano di «Chiudi tutte le gambe
 * dei bot», `pianoChiusuraPartita`, uno dopo l'altro), poi un green-up per
 * ogni selezione fuori dai bot. Solo LIVE: la prova resta nel riquadro dei bot.
 */
function CashOutPosizioneConto({ s, mike, sorgente, dueEsiti, onSintesi }: {
    s: Scatola;
    mike: MikeEvent | null;
    sorgente: SorgenteLadder | null;
    dueEsiti?: (marketId: string) => boolean;
    /** secondo giro: la cifra della scatola (LIVE bot + fuori bot, PROVA dei bot) per il riepilogo */
    onSintesi?: (x: SintesiCashOut | null) => void;
}) {
    const api = useContext(ChiusuraRigaContext);
    const gambe = useMemo(() => gambeFuoriBot(s.fuoriBot, dueEsiti), [s.fuoriBot, dueEsiti]);
    const esitoDeciso = useMemo(() => esitoDecisoMike(mike, s.operazioni), [mike, s.operazioni]);
    const r = useCashOutPartita({ operazioni: s.operazioni, gambeExtra: gambe, sorgente, sport: s.sport, dueEsiti, esitoDeciso });
    useRiportaSintesi(r, onSintesi);
    const piano = useMemo(() => pianoChiusuraPartita(s.operazioni, 'live'), [s.operazioni]);
    const selezioni = useMemo(() => selezioniFuoriBot(s.fuoriBot).filter((x) => x.abbinato), [s.fuoriBot]);
    const [inVolo, setInVolo] = useState(false);
    const [inviati, setInviati] = useState<ComandoChiusura[]>([]);
    const [esitiFuori, setEsitiFuori] = useState<{ chi: string; esito: EsitoFuoriBot }[]>([]);
    if (gambe.length === 0) return null;
    const live = r?.live ?? null;
    const spento = motivoCashOutConclusa(s) ?? (!api ? 'comandi dei bot non disponibili su questa pagina'
        : live == null ? 'cifra non calcolabile'
            : motivoPrezziFermi(live) ?? (live.netto == null ? 'cifra della posizione non calcolabile: non si chiude alla cieca' : null));
    const esegui = async () => {
        if (!api) return;
        setInVolo(true);
        const mandati: ComandoChiusura[] = [];
        const fuori: { chi: string; esito: EsitoFuoriBot }[] = [];
        try {
            // IN SEQUENZA, come «Chiudi tutte le gambe dei bot»: prima i bot...
            for (const c of piano.comandi) {
                await api.chiudi(c.riga);
                mandati.push(c);
                setInviati([...mandati]);
            }
            // ...poi gli ordini fuori dai bot, una selezione alla volta
            for (const sel of selezioni) {
                const e = await greenupFuoriBot(sel.marketId, sel.selectionId);
                fuori.push({ chi: `${sel.origini.join(' + ')} ${sel.selezione ?? sel.selectionId}`, esito: e });
                setEsitiFuori([...fuori]);
            }
        } finally {
            setInVolo(false);
        }
    };
    return (
        <div className="px-2.5 pt-1.5" data-testid="co-posizione-conto">
            <div className="flex flex-col gap-1 rounded border border-white/10 px-2 py-1.5">
                <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-white/80">
                        Cash out globale della posizione LIVE: bot + ordini fuori dai bot (se chiudo tutto adesso)
                    </span>
                    {live?.netto != null ? (
                        <>
                            <span className={`font-mono text-[15px] font-bold ${pnlClass(live.netto)}`} data-testid="co-posizione-conto-netto">
                                {fmtMoney(live.netto, { signed: true })}
                            </span>
                            <span className="text-[10px] text-white/50">netto commissione</span>
                            <MarchioSoldi fonte="pagina" etaS={live.etaIgnota ? null : live.etaPrezziS ?? undefined}
                                dettaglio="somma per mercato e selezione delle gambe LIVE dei bot e degli ordini fuori dai bot, chiuse al miglior prezzo di adesso"
                                testId="co-posizione-conto-marchio" />
                        </>
                    ) : (
                        <span className="text-[11px] font-semibold text-orange-400" data-testid="co-posizione-conto-non-calcolabile">
                            NON CALCOLABILE: {live?.mancanti.join('; ') || 'nessuna gamba'}
                        </span>
                    )}
                </div>
                <div className="text-[10px] text-white/50" data-testid="co-posizione-conto-piano">
                    {testoPiano(piano)}; {selezioni.length} {selezioni.length === 1 ? 'selezione' : 'selezioni'} con ordini fuori dai bot
                </div>
                <BottoneSoldiVeri testo="Cash out di tutta la posizione" testId="co-posizione-conto-cashout"
                    ambito="prima i comandi dei bot, poi il green-up degli ordini fuori dai bot"
                    spentoPerche={spento} inVolo={inVolo} onConferma={() => { void esegui(); }} />
                {inviati.map((c) => {
                    // l'esito del comando del bot, letto a ogni render (come «Chiudi tutte le gambe»)
                    const st = api?.stato(c.bot, c.riga.id) ?? null;
                    return (
                        <div key={`${c.bot}:${c.riga.id}`} className="text-[10px] text-white/60" data-testid="co-posizione-conto-esito"
                            data-bot={c.bot}>
                            {BOT_LABEL[c.bot]} #{c.riga.id}: {st ? TESTO_FASE[faseMostrata(st)] : 'in invio'}{st?.motivo ? `: ${st.motivo}` : ''}
                        </div>
                    );
                })}
                {esitiFuori.map((e) => (
                    <div key={e.chi} className="text-[10px] text-white/60" data-testid="co-posizione-conto-esito" data-bot="fuori-bot">
                        {e.chi}: {TESTO_FASE[e.esito.fase]}{e.esito.motivo ? `: ${e.esito.motivo}` : ''}
                    </div>
                ))}
            </div>
        </div>
    );
}

// -------------------------------------------------------------------- scatola

/** La fase scritta per una partita FUORI dal programma (dentro il programma vale `StatoPill`). */
function FaseFuoriProgramma({ s, nowMs }: { s: Scatola; nowMs: number }) {
    const f = s.fase;
    const testo = f.nota === 'in-gioco' ? 'in gioco (dal servizio di Mike)'
        : f.nota === 'fischio-fra' && f.koMs != null ? `fischio alle ${fmtTime(f.koMs)} · fra ${fmtAge(Math.max(0, Math.round((f.koMs - nowMs) / 1000)))}`
            // stesso testo di `StatoPill` per «orario passato, il feed dice non in gioco»
            : f.nota === 'fischio-passato' ? 'non in gioco · orario passato'
                : f.nota === 'orario-passato' ? 'orario passato · fase non dichiarata'
                    : 'orario non dichiarato';
    return (
        <span className="shrink-0 text-[11px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-white/50"
            data-testid="co-fase-fuori-programma" data-nota={f.nota}
            title="partita fuori dal programma dello scanner: la fase viene dai dati del bot (Mike: orario e «in gioco»; Omega: orario della riga)">
            {testo}
        </span>
    );
}

export function ScatolaCashOut({ s, mike, safe, sorgente, nowMs, onSintesi }: {
    s: Scatola;
    mike: MikeEvent | null;
    safe: SafeScatola;
    sorgente: SorgenteLadder | null;
    nowMs: number;
    /**
     * secondo giro: la cifra «se chiudo tutto adesso» della scatola per il
     * riepilogo della pagina, quella che la scatola GIA' calcola: col conto
     * (bot + fuori dai bot) se ci sono ordini fuori dai bot abbinati,
     * altrimenti il cash out della partita dei bot. `undefined` = scatola
     * smontata (esce dal riepilogo).
     */
    onSintesi?: (x: SintesiCashOut | null | undefined) => void;
}) {
    const p = s.partita;
    const dueEsiti = useMemo(
        () => dueEsitiPartita(s.sport, p?.marketId ?? null, dueEsitiMike(mike)),
        [s.sport, p?.marketId, mike],
    );
    const selezioni = useMemo(() => selezioniFuoriBot(s.fuoriBot), [s.fuoriBot]);
    // UNA fonte per scatola: il totale col conto se esiste, altrimenti quello dei bot
    const conConto = useMemo(() => gambeFuoriBot(s.fuoriBot).length > 0, [s.fuoriBot]);
    const riporta = useRef(onSintesi);
    riporta.current = onSintesi;
    useEffect(() => () => riporta.current?.(undefined), []);
    const prova = s.posizioni.some((x) => x.modalita === 'paper');
    // D-6: non null = partita conclusa, i cash out sono spenti con questo motivo
    const conclusa = motivoCashOutConclusa(s);
    const viveSafe = s.operazioni.filter((o) => o.bot === 'safe' && !isSettled(o.stato) && !isErrorRow(o.stato)).length;
    return (
        <article className="rounded border border-white/10 bg-white/[0.02] overflow-hidden"
            data-testid={`co-scatola-${s.eventId}`} data-event-id={s.eventId} data-fase={s.fase.fase}>
            {/* ── testata: chi gioca, soldi, stato, strumenti ── */}
            <div className="px-2.5 pt-2 flex items-start gap-2 flex-wrap" data-testid="co-testata">
                <span className="text-white/25 text-[13px] leading-none mt-0.5" aria-label={s.sport}>
                    {s.sport === 'tennis' ? '🎾' : '⚽'}
                </span>
                <NomiPartita nome={s.nome}
                    homeTeamId={p?.extra?.homeTeamId ?? null} awayTeamId={p?.extra?.awayTeamId ?? null} />
                {s.live && (
                    <Badge variant="outline" className="h-4 px-1 text-[9px] border-red-500/40 text-red-300" data-testid="co-soldi-live">LIVE</Badge>
                )}
                {prova && (
                    <Badge variant="outline" className="h-4 px-1 text-[9px] border-white/20 text-white/40" data-testid="co-soldi-prova">PROVA</Badge>
                )}
                {/* lo stato in una parola, come nella scheda «Posizioni aperte»: sulle gambe LIVE dei bot */}
                {s.posizioni.some((x) => x.modalita !== 'paper') && (
                    <StatoPartitaRiga
                        esito={statoPartitaAperta(s.operazioni, {
                            // D-6: stessa regola della sezione «Concluse» (Match Odds CHIUSO)
                            chiusa: s.fase.nota === 'conclusa',
                            dueEsiti,
                        })}
                        testId={`co-stato-${s.eventId}`} />
                )}
                {conclusa != null ? (
                    <span className="shrink-0 text-[11px] px-1.5 py-0.5 rounded bg-white/5 text-white/50"
                        data-testid="co-fase-conclusa"
                        title="Betfair ha CHIUSO il Match Odds: la partita e' finita, le posizioni restano aperte finche' Betfair non le regola">
                        {TESTO_CONCLUSA}
                    </span>
                ) : p ? <StatoPill p={p} /> : <FaseFuoriProgramma s={s} nowMs={nowMs} />}
                {p?.stato === 'pre' && p.koMs != null && (
                    <span className="shrink-0 text-[10px] font-mono text-white/35" data-testid="co-fischio-fra">
                        fra {fmtAge(Math.max(0, Math.round((p.koMs - nowMs) / 1000)))}
                    </span>
                )}
                <span className="ml-auto">
                    {p ? (
                        <AzioniPartita p={p} scheda="cash-out" soloMediaStatistiche
                            ritorno={ORIGINI_RITORNO['cash-out']} />
                    ) : (
                        <BetfairMediaButtons eventId={s.eventId} compact />
                    )}
                </span>
            </div>
            {s.sport === 'tennis' && (
                <TennisVivoBar eventId={s.eventId} abilitato={s.posizioni.length > 0} giocatori={p?.giocatori ?? null} />
            )}

            {/* ── le gambe: bot, orfane, fuori dai bot ── */}
            <div className="px-2.5 py-2 space-y-1.5" data-testid="co-gambe">
                {conclusa != null && (
                    <div className="text-[10px] text-white/50" data-testid="co-conclusa-motivo">{conclusa}</div>
                )}
                {s.righe.map((o) => (
                    <div key={`${o.bot}-${o.id}`} className="flex items-start gap-2" data-testid="co-gamba" data-bot={o.bot}>
                        <div className="flex-1 min-w-0">
                            <RigaOperazione o={o} chiudi={{
                                ...testoCashOutRiga(o, s.righe),
                                // lo scalper ferma la sessione (nessun ordine sul mercato chiuso)
                                spentoPerche: o.bot === 'scalper' ? null : conclusa,
                            }} />
                        </div>
                        <BottoneLadder sport={s.sport} marketId={o.marketId} eventId={s.eventId} eventName={s.nome}
                            giocatori={p?.giocatori ?? null} />
                    </div>
                ))}
                {s.orfane.map((x) => <RigaPosizioneOrfana key={`${x.bot}-${x.id}`} p={x} />)}
                {selezioni.map((sel) => (
                    <RigaFuoriBot key={sel.chiave} sel={sel} sorgente={sorgente} dueEsiti={dueEsiti}
                        eventId={s.eventId} eventName={s.nome} spentoConclusa={conclusa} />
                ))}
            </div>

            {/* ── il cash out della posizione ── */}
            <div className="pb-2" data-testid="co-piede">
                {viveSafe > 0 && (
                    <div className="px-2.5 pt-1.5">
                        <CashOutPartita eventId={s.eventId} modalita={safe.modalita} posizioniVive={viveSafe}
                            stato={safe.statoChiusura(s.eventId)} onCashOut={safe.onCashOut} onRiprendi={safe.onRiprendi}
                            compatto esito={trovaEsitoCashOut(s.operazioni, 'safe')} spentoPerche={conclusa} />
                    </div>
                )}
                <CashOutGlobalePartita sport={s.sport} operazioni={s.operazioni} mike={mike} moMarketId={p?.marketId ?? null}
                    onSintesi={conConto ? undefined : (x) => riporta.current?.(x)} spentoPerche={conclusa} />
                {s.fuoriBot.length > 0 && (
                    <CashOutPosizioneConto s={s} mike={mike} sorgente={sorgente} dueEsiti={dueEsiti}
                        onSintesi={conConto ? (x) => riporta.current?.(x) : undefined} />
                )}
            </div>
        </article>
    );
}
