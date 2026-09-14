// ============================================================================
// SchedaPartita.tsx — LA RIGA DI UNA PARTITA nel banco operativo.
//
// Non inventa niente: **monta insieme cose che il software ha già** —
//   · `BetfairMediaButtons`  video e statistiche ufficiali Betfair (lo stesso
//                            componente di Mike, Omega, Safe e Tennis);
//   · il terminale di trading su QUESTA partita, con la rotta che usano già
//     Omega (`/segui-live?event=…`) e la lista tennis (`/tennis/terminal?…`);
//   · `fmtMoney` / `fmtOdds` / `fmtAge` del design system, mai un formato nuovo.
//
// COSA AGGIUNGE, e serve a un trader:
//  1. **il target di QUESTA partita e quanto ne manca** — la barra è un metro,
//     non un grafico: dice una grandezza, e basta;
//  2. **i tre bot come simboli cliccabili**: acceso = ha operato qui, e il clic
//     apre COSA ha fatto, riga per riga, con prezzo, importo ed esito;
//  3. **lo stato del prezzo** distinto fra «fermo» (il mercato non si muove: è
//     il prezzo corrente) e «vecchio» (non sappiamo cosa fa il mercato).
//
// REGOLE DEL DESIGN SYSTEM rispettate alla lettera: i soldi passano da
// `fmtMoney`, le quote da `fmtOdds`, nessuno stato in inglese sotto gli occhi
// del trader, e un valore che non c'è è `—`, mai `0,00 €`.
// ============================================================================
import { useState } from 'react';
import { ChevronRight, Circle } from 'lucide-react';
import { AzioniPartita } from '@/components/controlroom/AzioniPartita';
import { fmtMoney, fmtOdds, fmtAge, fmtTime, DASH } from '@/lib/format';
import { BOT_LABEL, type Bot, type PartitaGiornata, type StatoQuote } from '@/lib/controlRoom';
import type { OperazionePartita } from '@/components/controlroom/useControlRoom';

const BOT_SIGLA: Record<Bot, string> = { omega: 'Ω', safe: 'S', mike: 'M' };
const BOT_CLS: Record<Bot, string> = {
    omega: 'text-primary border-primary/40 bg-primary/10',
    safe: 'text-secondary border-secondary/40 bg-secondary/10',
    mike: 'text-teal-300 border-teal-400/40 bg-teal-400/10',
};

/** «fermo» NON è un allarme: è un mercato che non si muove, e quel prezzo è
 *  quello corrente. Solo «vecchio» e «ignoto» meritano l'arancione. */
const QUOTE_CLS: Record<StatoQuote, string> = {
    fresco: 'text-emerald-400',
    fermo: 'text-white/50',
    vecchio: 'text-orange-400',
    ignoto: 'text-orange-400',
};
const QUOTE_TESTO: Record<StatoQuote, (s: string) => string> = {
    fresco: (s) => s,
    fermo: (s) => `fermo ${s}`,
    vecchio: (s) => `vecchio ${s}`,
    ignoto: () => 'età ignota',
};

export interface SchedaPartitaProps {
    p: PartitaGiornata;
    operazioni: OperazionePartita[];
    /** la scheda aperta adesso: serve a tornare ESATTAMENTE qui */
    scheda?: string;
    /** questa partita sta registrando? */
    registra?: boolean | null;
}

export function SchedaPartita({ p, operazioni, scheda = 'live', registra = null }: SchedaPartitaProps) {
    const [aperto, setAperto] = useState<Bot | null>(null);

    const soldi = p.soldi;
    // IL NUMERO GRANDE E' QUELLO DEI SOLDI VERI. Il paper esiste, si vede, ma
    // sta sotto e non si somma: sul tennis la stessa partita può avere righe
    // di entrambe le modalità, e un solo numero sarebbe la media di due mondi.
    const net = soldi?.live.netPnl ?? null;
    const netPaper = soldi?.paper.netPnl ?? null;
    const apertaLive = soldi?.live.aperta ?? false;
    const apertaPaper = soldi?.paper.aperta ?? false;
    const target = p.target?.valore ?? null;
    const manca = target != null && net != null ? Math.max(0, target - net) : target;

    const bordo = p.stato === 'live' ? 'border-l-secondary'
        : apertaLive ? 'border-l-primary'
            : apertaPaper ? 'border-l-white/25' : 'border-l-white/12';

    const perBot = (b: Bot) => operazioni.filter((o) => o.bot === b);

    return (
        <div className={`rounded border border-white/10 border-l-[3px] ${bordo} bg-white/[0.02]`}
            data-testid="cr-partita" data-event-id={p.event_id}>
            {/* ── riga 1: chi gioca, stato, e gli strumenti ── */}
            <div className="px-2.5 pt-2 flex items-start gap-2">
                <span className="text-white/25 text-[13px] leading-none mt-0.5"
                    aria-label={p.sport === 'tennis' ? 'tennis' : 'calcio'}>
                    {p.sport === 'tennis' ? '🎾' : '⚽'}
                </span>
                <span className="text-[13px] font-medium leading-tight flex-1 min-w-0">{p.nome}</span>
                <StatoPill p={p} />
            </div>

            <div className="px-2.5 pt-1 flex items-center gap-1.5 flex-wrap">
                {/* la STESSA riga di pulsanti di ogni altra scheda: video,
                    statistiche, trading, segui live — e ognuno si segna il
                    punto di ritorno prima di portare il trader altrove. */}
                <AzioniPartita p={p} scheda={scheda} registra={registra} />
                {p.stato === 'live' && (
                    <span className={`text-[10px] font-mono ml-auto ${QUOTE_CLS[p.statoQuote]}`}
                        data-testid="cr-latenza"
                        title={p.statoQuote === 'fermo'
                            ? 'il prezzo non cambia da questo tempo, ma lo scanner sta guardando: è il prezzo CORRENTE'
                            : 'da quando il prezzo è cambiato l’ultima volta'}>
                        {p.latenzaQuoteS == null
                            ? QUOTE_TESTO[p.statoQuote]('')
                            : QUOTE_TESTO[p.statoQuote](fmtAge(p.latenzaQuoteS))}
                    </span>
                )}
            </div>

            {/* ── riga 2: il METRO — target, fatto, quanto manca ── */}
            <div className="px-2.5 pt-2">
                <div className="flex items-baseline justify-between gap-2 text-[11px]">
                    <span className="text-white/40">
                        target <span className="font-mono text-white/70">{target == null ? DASH : fmtMoney(target)}</span>
                        {p.target?.fonte === 'ripiego' && <span className="text-white/30" title="calcolato dalla pagina: il servizio non lo pubblica"> *</span>}
                    </span>
                    <span className="flex items-baseline gap-2">
                        <span className={`font-mono text-[14px] font-bold tabular-nums ${
                            net == null ? 'text-white/35' : net >= 0 ? 'text-emerald-400' : 'text-red-400'
                        }`} data-testid="cr-pnl-partita">{net == null ? DASH : fmtMoney(net)}</span>
                        {manca != null && manca > 0 && net != null && (
                            <span className="text-[10px] text-white/40">manca {fmtMoney(manca)}</span>
                        )}
                        {target != null && net != null && net >= target && (
                            <span className="text-[10px] text-emerald-400 font-semibold">target centrato</span>
                        )}
                    </span>
                </div>
                {netPaper != null && (
                    <div className="text-[10px] text-white/35 mt-0.5" data-testid="cr-pnl-partita-paper">
                        in prova <span className={`font-mono ${netPaper >= 0 ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
                            {fmtMoney(netPaper, { signed: true })}
                        </span> — non entra nel target
                    </div>
                )}
                {p.avanzamento != null && (
                    <div className="h-1 mt-1 rounded-sm bg-white/8 overflow-hidden">
                        <div className={`h-full ${net != null && net < 0 ? 'bg-red-400' : 'bg-emerald-400'}`}
                            style={{ width: `${p.avanzamento}%` }} />
                    </div>
                )}
            </div>

            {/* ── riga 3: i tre bot, cliccabili se hanno operato ── */}
            <div className="px-2.5 py-2 flex items-center gap-1.5">
                {(['omega', 'safe', 'mike'] as Bot[]).map((b) => {
                    const ops = perBot(b);
                    const attivo = ops.length > 0;
                    return (
                        <button
                            key={b} type="button"
                            disabled={!attivo}
                            onClick={() => setAperto(aperto === b ? null : b)}
                            aria-expanded={aperto === b}
                            data-testid={`cr-bot-${b}-${p.event_id}`}
                            title={attivo
                                ? `${BOT_LABEL[b]}: ${ops.length} ${ops.length === 1 ? 'operazione' : 'operazioni'} — clicca per il dettaglio`
                                : `${BOT_LABEL[b]}: nessuna operazione su questa partita`}
                            className={`w-6 h-5 rounded-sm grid place-items-center text-[10px] font-bold border transition-colors ${
                                attivo ? `${BOT_CLS[b]} hover:brightness-125 cursor-pointer`
                                    : 'border-white/8 bg-white/[0.02] text-white/15 cursor-default'
                            } ${aperto === b ? 'ring-1 ring-white/40' : ''}`}
                        >{BOT_SIGLA[b]}</button>
                    );
                })}
                {soldi && (soldi.live.liability > 0 || soldi.paper.liability > 0) ? (
                    <span className="ml-auto text-[10px] text-white/40 flex items-baseline gap-1.5">
                        {soldi.live.liability > 0 && (
                            <span title="responsabilità impegnata con SOLDI VERI">
                                resp. <span className="font-mono text-white/65">{fmtMoney(soldi.live.liability)}</span>
                            </span>
                        )}
                        {soldi.paper.liability > 0 && (
                            <span className="text-white/30" title="responsabilità impegnata in PROVA: non sono soldi veri e non si sommano">
                                prova <span className="font-mono">{fmtMoney(soldi.paper.liability)}</span>
                            </span>
                        )}
                    </span>
                ) : null}
            </div>

            {/* ── dettaglio: COSA ha fatto quel bot su questa partita ── */}
            {aperto && (
                <div className="px-2.5 pb-2 border-t border-white/8 pt-1.5" data-testid="cr-dettaglio-bot">
                    <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1">
                        {BOT_LABEL[aperto]} — operazioni su questa partita
                    </div>
                    <div className="space-y-1">
                        {perBot(aperto).map((o) => (
                            <div key={`${o.bot}-${o.id}`} className="flex items-baseline gap-1.5 text-[11px] flex-wrap">
                                <ChevronRight className="w-2.5 h-2.5 text-white/25 shrink-0" />
                                <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                                    o.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                                }`}>{o.lato === 'lay' ? 'banca' : 'punta'}</span>
                                <span className="text-white/75 truncate max-w-[9rem]">{o.selezione ?? DASH}</span>
                                <span className="font-mono text-white/60">{fmtOdds(o.prezzo)}</span>
                                <span className="font-mono text-white/45">{fmtMoney(o.size)}</span>
                                {o.quale && <span className="text-[9px] text-white/30 uppercase">{o.quale}</span>}
                                {o.modalita === 'live'
                                    ? <span className="text-[9px] px-1 rounded bg-orange-500/20 text-orange-300">live</span>
                                    : <span className="text-[9px] px-1 rounded bg-white/8 text-white/35">paper</span>}
                                <span className={`ml-auto font-mono font-semibold ${
                                    o.pnl == null ? 'text-white/30' : o.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                                }`}>{o.pnl == null ? DASH : fmtMoney(o.pnl)}</span>
                                <span className="text-[9px] text-white/25 font-mono">{fmtTime(o.at)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function StatoPill({ p }: { p: PartitaGiornata }) {
    if (p.stato === 'live') {
        const testa = p.minuto != null ? `${p.minuto}′` : p.punteggio ? '' : 'in gioco';
        return (
            <span className="shrink-0 flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded bg-secondary/15 text-secondary">
                <Circle className="w-1.5 h-1.5 fill-current" />
                {testa}{p.punteggio && <span>{testa ? ' ' : ''}{p.punteggio}</span>}
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

export default SchedaPartita;
