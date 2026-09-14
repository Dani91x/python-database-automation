// ============================================================================
// SplitSport.tsx — CALCIO E TENNIS, SEPARATI E LEGGIBILI.
//
// Richiesta dell'utente: «non c'è distinzione tra guadagno del tennis e del
// calcio». Oggi il tennis opera con **soldi veri** e il calcio in **prova**:
// sommarli in un numero solo non è una semplificazione, è una bugia.
//
// DISEGNO — due entità, quindi due identità fisse: ogni sport tiene **sempre**
// lo stesso colore, anche quando uno dei due è a zero (il colore segue
// l'entità, mai il suo rango). La modalità è la cosa più importante della
// tessera e sta in alto: un numero in euro veri e uno simulato non possono
// somigliarsi.
//
// I numeri arrivano dal **server** (`get_safe_daily.by_sport`): qui non si
// riconta niente — il client che ricontava produceva numeri diversi da quelli
// del servizio, ed è già costato una card con due verità dentro.
// ============================================================================
import { Card } from '@/components/ui/card';
import { fmtMoney, fmtPct, DASH } from '@/lib/format';
import { pnlClass, T } from '@/lib/tradeStatus';
import type { DailyBreakdown } from '@/lib/dailyHistory';

/** Identità fissa per sport: il colore segue l'entità, non il rango. */
const SPORT = {
    calcio: { nome: 'Calcio', icona: '⚽', accento: 'text-sky-300', bordo: 'border-sky-400/30', fondo: 'bg-sky-400/[0.06]' },
    tennis: { nome: 'Tennis', icona: '🎾', accento: 'text-secondary', bordo: 'border-secondary/30', fondo: 'bg-secondary/[0.06]' },
} as const;

export type SportKey = keyof typeof SPORT;

export interface SplitSportProps {
    /** aggregati per sport dal server; `null` = non ancora letti */
    perSport: Record<string, DailyBreakdown> | null;
    /** modalità con cui quello sport sta operando ADESSO (dal servizio) */
    modalita: Record<SportKey, 'paper' | 'live' | null>;
    /** posizioni aperte per sport, dal vivo */
    aperte?: Record<SportKey, number>;
    testId?: string;
}

export function SplitSport({ perSport, modalita, aperte, testId = 'cr-split-sport' }: SplitSportProps) {
    return (
        <div className="grid gap-2 sm:grid-cols-2" data-testid={testId}>
            {(Object.keys(SPORT) as SportKey[]).map((k) => (
                <Tessera
                    key={k}
                    sport={k}
                    dato={perSport?.[k] ?? null}
                    modalita={modalita[k]}
                    aperte={aperte?.[k] ?? 0}
                    letto={perSport != null}
                />
            ))}
        </div>
    );
}

function Tessera({ sport, dato, modalita, aperte, letto }: {
    sport: SportKey;
    dato: DailyBreakdown | null;
    modalita: 'paper' | 'live' | null;
    aperte: number;
    letto: boolean;
}) {
    const s = SPORT[sport];
    const live = modalita === 'live';
    // «non ancora letto» e «nessuna operazione» sono due cose diverse: la prima
    // e' un trattino, la seconda uno zero legittimo.
    const pnl = dato ? dato.pnl : null;
    const esiti = dato ? dato.won + dato.lost : 0;
    const winRate = dato && esiti > 0 ? dato.won / esiti : null;

    return (
        <Card className={`glass-card p-2.5 ${s.bordo} ${live ? s.fondo : 'bg-white/[0.02]'}`}
            data-testid={`cr-sport-${sport}`}>
            <div className="flex items-baseline gap-2">
                <span aria-hidden="true">{s.icona}</span>
                <span className={`text-[12px] font-bold uppercase tracking-wider ${s.accento}`}>{s.nome}</span>
                {modalita == null ? (
                    <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300"
                        title="il servizio non dichiara la modalità per questo sport">modalità n/d</span>
                ) : live ? (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/20 text-red-300"
                        title="soldi veri: ordine reale su Betfair">{T.modeLive}</span>
                ) : (
                    <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/45">{T.modePaper}</span>
                )}
                {aperte > 0 && (
                    <span className="ml-auto text-[10px] text-white/45">
                        {aperte} {aperte === 1 ? 'aperta' : 'aperte'}
                    </span>
                )}
            </div>

            <div className={`font-mono text-2xl font-bold tabular-nums mt-1 ${pnlClass(pnl)}`}
                data-testid={`cr-sport-${sport}-pnl`}>
                {!letto ? DASH : fmtMoney(pnl, { signed: true })}
            </div>

            <div className="text-[10.5px] text-white/45 mt-0.5 flex items-baseline gap-2 flex-wrap">
                {!letto ? (
                    <span>giornata non ancora letta</span>
                ) : !dato || dato.n === 0 ? (
                    <span>nessuna operazione oggi</span>
                ) : (
                    <>
                        <span><span className="font-mono text-white/70">{dato.n}</span> {dato.n === 1 ? 'operazione' : 'operazioni'}</span>
                        <span className="text-emerald-400/80 font-mono">{dato.won} V</span>
                        <span className="text-red-400/80 font-mono">{dato.lost} P</span>
                        {winRate != null && (
                            <span title="vinte su vinte+perse">{fmtPct(winRate, 0)}</span>
                        )}
                    </>
                )}
            </div>
        </Card>
    );
}

export default SplitSport;
