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
    /** sport selezionato: filtra tutto il resto della pagina. `null` = tutti */
    selezionato: SportKey | null;
    /** clic sulla tessera: seleziona, o deseleziona se già selezionata */
    onSeleziona: (s: SportKey | null) => void;
    /** aggregati per sport dal server con i SOLDI VERI; `null` = non letti */
    perSport: Record<string, DailyBreakdown> | null;
    /**
     * Gli stessi aggregati IN PROVA.
     *
     * ⚠️ REVIEW 15/09 — la tessera del calcio scriveva «MODALITÀ PAPER» e
     * sotto un P&L costruito escludendo tutte le righe paper: l'etichetta
     * diceva una cosa e il numero un'altra. Il numero grande deve essere
     * quello della modalità DICHIARATA. I due non si sommano mai.
     */
    perSportPaper?: Record<string, DailyBreakdown> | null;
    /** modalità con cui quello sport sta operando ADESSO (dal servizio) */
    modalita: Record<SportKey, 'paper' | 'live' | null>;
    /** posizioni aperte per sport, **divise per modalità**: «2 aperte» senza
     *  dire con che soldi non è un'informazione, è un'ambiguità */
    aperte?: Record<SportKey, { live: number; paper: number }>;
    testId?: string;
}

export function SplitSport({
    perSport, perSportPaper = null, modalita, aperte, selezionato, onSeleziona,
    testId = 'cr-split-sport',
}: SplitSportProps) {
    return (
        <div className="grid gap-2 sm:grid-cols-2" data-testid={testId}>
            {(Object.keys(SPORT) as SportKey[]).map((k) => (
                <Tessera
                    key={k}
                    sport={k}
                    dato={perSport?.[k] ?? null}
                    datoPaper={perSportPaper?.[k] ?? null}
                    modalita={modalita[k]}
                    aperte={aperte?.[k] ?? { live: 0, paper: 0 }}
                    letto={perSport != null}
                    scelto={selezionato === k}
                    spento={selezionato != null && selezionato !== k}
                    onClick={() => onSeleziona(selezionato === k ? null : k)}
                />
            ))}
        </div>
    );
}

function Tessera({ sport, dato, datoPaper, modalita, aperte, letto, scelto, spento, onClick }: {
    sport: SportKey;
    dato: DailyBreakdown | null;
    datoPaper: DailyBreakdown | null;
    modalita: 'paper' | 'live' | null;
    aperte: { live: number; paper: number };
    letto: boolean;
    scelto: boolean;
    spento: boolean;
    onClick: () => void;
}) {
    const s = SPORT[sport];
    const live = modalita === 'live';
    // IL NUMERO GRANDE E' QUELLO DELLA MODALITA' DICHIARATA dalla tessera:
    // «paper» sopra un P&L che esclude le righe paper era una contraddizione
    // a due centimetri di distanza.
    const mio = live ? dato : datoPaper;
    const altro = live ? datoPaper : dato;
    // «non ancora letto» e «nessuna operazione» sono due cose diverse: la prima
    // e' un trattino, la seconda uno zero legittimo.
    const pnl = mio ? mio.pnl : null;
    const esiti = mio ? mio.won + mio.lost : 0;
    const winRate = mio && esiti > 0 ? mio.won / esiti : null;

    return (
        <Card
            className={`glass-card p-2.5 transition-all ${s.bordo} ${live ? s.fondo : 'bg-white/[0.02]'} ${
                scelto ? 'ring-2 ring-white/50' : spento ? 'opacity-45' : 'hover:brightness-125'
            }`}
            data-testid={`cr-sport-${sport}`}
        >
            {/* la tessera E' il filtro: clic = «mostrami solo questo sport»,
                secondo clic = torna a vedere tutto. Le proposte di chiusura
                restano visibili comunque: un'uscita non si nasconde dietro un
                filtro. */}
            <button
                type="button" onClick={onClick} aria-pressed={scelto}
                data-testid={`cr-filtro-${sport}`}
                className="w-full text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-white/60 rounded"
                title={scelto ? 'mostra di nuovo tutti gli sport' : `mostra solo ${s.nome.toLowerCase()}`}
            >
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
                {(aperte.live > 0 || aperte.paper > 0) && (
                    <span className="ml-auto text-[10px] flex items-baseline gap-1.5">
                        {aperte.live > 0 && (
                            <span className="text-red-300" title="posizioni con soldi veri">
                                {aperte.live} {aperte.live === 1 ? 'aperta' : 'aperte'}
                            </span>
                        )}
                        {aperte.paper > 0 && (
                            <span className="text-white/35" title="posizioni simulate">
                                {aperte.paper} in prova
                            </span>
                        )}
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
                ) : !mio || mio.n === 0 ? (
                    <span>
                        nessuna operazione {live ? 'con soldi veri' : 'in prova'} oggi
                        {altro && altro.n > 0 && (
                            <span className="text-white/25">
                                {' '}· {altro.n} {live ? 'in prova' : 'con soldi veri'}
                            </span>
                        )}
                    </span>
                ) : (
                    <>
                        <span><span className="font-mono text-white/70">{mio.n}</span> {mio.n === 1 ? 'operazione' : 'operazioni'}</span>
                        <span className="text-emerald-400/80 font-mono">{mio.won} V</span>
                        <span className="text-red-400/80 font-mono">{mio.lost} P</span>
                        {winRate != null && (
                            <span title="vinte su vinte+perse">{fmtPct(winRate, 0)}</span>
                        )}
                    </>
                )}
            </div>
            <div className="text-[9.5px] uppercase tracking-wider mt-1.5 text-white/30">
                {scelto ? 'stai vedendo solo questo — clicca per tutti' : 'clicca per vedere solo questo sport'}
            </div>
            </button>
        </Card>
    );
}

export default SplitSport;
