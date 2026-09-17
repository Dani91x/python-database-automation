// ============================================================================
// DettaglioRigaView.tsx — COME SI MOSTRA il dettaglio di una riga.
//
// I numeri li calcola `dettaglioRiga.ts` (che a sua volta non calcola niente di
// nuovo: chiama le funzioni delle pagine originali). Qui c'è solo il montaggio,
// con le regole del design system: i soldi da `fmtMoney`, le quote da
// `fmtOdds`, le percentuali da `fmtPct`, e ciò che non c'è è `—`, mai 0,00 €.
//
// Gli stessi pezzi servono a DUE posti — la colonna delle posizioni aperte e la
// scheda della partita — perché è la stessa posizione: mostrarla con due
// vocabolari diversi nella stessa pagina è il modo più veloce per far sbagliare
// un trader.
// ============================================================================
import { fmtMoney, fmtOdds, fmtPct, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { DettaglioRiga, QuotaViva } from '@/components/controlroom/dettaglioRiga';

/** Badge di stato ricco: lo stesso di Omega e Safe, stessa etichetta italiana. */
export function BadgeStato({ d, testId = 'cr-stato-riga' }: { d: DettaglioRiga; testId?: string }) {
    return (
        <span
            className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${d.stato.cls}`}
            data-testid={testId}
        >{d.stato.label}</span>
    );
}

/** Minuto e punteggio AL MOMENTO DELL'INGRESSO: dicono a che partita il bot è
 *  entrato, che non è quella di adesso. Nessuno dei due c'è → niente riga. */
export function Ingresso({ d, testId = 'cr-ingresso' }: { d: DettaglioRiga; testId?: string }) {
    if (d.ingresso.minuto == null && d.ingresso.punteggio == null) return null;
    return (
        <span className="text-[10px] text-white/40" data-testid={testId}
            title="minuto e punteggio al momento dell'ingresso">
            ingresso <span className="text-white/65">
                {d.ingresso.minuto != null ? `${d.ingresso.minuto}′` : ''}
                {d.ingresso.punteggio ? ` ${d.ingresso.punteggio}` : ''}
            </span>
        </span>
    );
}

/** Quota d'ingresso → quota di ADESSO → tick di movimento. */
export function QuotaOra({ v, testId = 'cr-quota-viva' }: { v: QuotaViva; testId?: string }) {
    return (
        <span className="text-[10px] text-white/40 tabular-nums" data-testid={testId}
            title="miglior BACK e miglior LAY di adesso sulla stessa selezione, dal feed di scansione">
            ora <span className="text-teal-300 font-mono">B {fmtOdds(v.back)}</span>
            <span className="text-white/25"> / </span>
            <span className="text-sky-300 font-mono">L {fmtOdds(v.lay)}</span>
            {v.tick != null && (
                <span className={`ml-1 font-mono ${v.tick > 0 ? 'text-emerald-400' : v.tick < 0 ? 'text-red-400' : 'text-white/40'}`}
                    data-testid={`${testId}-tick`}
                    title="tick di movimento dall'ingresso: positivo = a favore della posizione">
                    {v.tick > 0 ? '+' : ''}{v.tick} tick
                </span>
            )}
        </span>
    );
}

const PNL_LABEL: Record<DettaglioRiga['pnlVivo']['stato'], string> = {
    settled: 'regolato',
    locked: 'bloccato',
    partial: 'caso peggiore',
    open: 'aperto',
    none: 'nessun P&L',
};

/**
 * P&L VIVO. La Control Room mostrava un numero SOLO a regolamento avvenuto:
 * una posizione già coperta (P&L ormai certo) restava senza numero. Qui si
 * dice anche COSA è quel numero — regolato, bloccato, caso peggiore — perché
 * un «bloccato» e un «aperto» non si leggono allo stesso modo.
 */
export function PnlVivo({ d, testId = 'cr-pnl-vivo' }: { d: DettaglioRiga; testId?: string }) {
    if (d.pnlVivo.stato === 'none' || (d.pnlVivo.stato === 'open' && d.pnlVivo.valore == null)) {
        return (
            <span className="text-[10px] text-white/30" data-testid={testId} data-stato={d.pnlVivo.stato}>
                P&amp;L {DASH}
            </span>
        );
    }
    return (
        <span className="text-[10px] tabular-nums" data-testid={testId} data-stato={d.pnlVivo.stato}
            title={`P&L ${PNL_LABEL[d.pnlVivo.stato]}`}>
            <span className="text-white/40">{PNL_LABEL[d.pnlVivo.stato]} </span>
            <span className={`font-mono font-semibold ${pnlClass(d.pnlVivo.valore)}`}>
                {d.pnlVivo.valore == null ? DASH : fmtMoney(d.pnlVivo.valore, { signed: true })}
            </span>
        </span>
    );
}

/** Copertura: quanto della posizione è già chiuso e quanto rischia ancora. */
export function Copertura({ d, testId = 'cr-copertura-riga' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.copertura) return null;
    const pct = d.copertura.frazione == null ? null : Math.round(d.copertura.frazione * 100);
    return (
        <span className="text-[10px] text-white/40" data-testid={testId}
            data-completa={d.copertura.completa ? '1' : undefined}
            title="quota di stake già coperta e responsabilità ancora a rischio">
            coperta <span className="text-white/65">{pct == null ? DASH : `${pct} %`}</span>
            {d.copertura.residua != null && (
                <span className="text-white/30"> · a rischio <span className="font-mono">{fmtMoney(d.copertura.residua)}</span></span>
            )}
        </span>
    );
}

/** Badge green-up del servizio: stato, motivo, tentativi — mai una deduzione. */
export function Greenup({ d, testId = 'cr-greenup' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.greenup) return null;
    return (
        <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${d.greenup.cls}`}
            data-testid={testId} data-stato={d.greenup.state} title={d.greenup.title}>
            {d.greenup.label}
        </span>
    );
}

/** P(perdita) del MODELLO contro quella implicita nel MERCATO (Omega). */
export function ModelloP({ d, testId = 'cr-modello-p' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.modello) return null;
    return (
        <span className="text-[10px] text-white/40 tabular-nums" data-testid={testId}
            title="P(perdita) secondo il modello del bot contro quella implicita nella quota LAY di adesso (1/quota)">
            P(perdita) <span className="text-white/70">{fmtPct(d.modello.pModello)}</span>
            <span className="text-white/25"> · mercato </span>
            <span className="text-white/60">{fmtPct(d.modello.pMercato)}</span>
            {d.modello.margine != null && (
                <span className={`ml-1 ${d.modello.margine > 0 ? 'text-emerald-400' : 'text-red-400'}`}
                    data-testid={`${testId}-margine`}
                    title="mercato − modello: positivo = il mercato paga più del rischio che il modello vede">
                    {d.modello.margine > 0 ? '+' : ''}{fmtPct(d.modello.margine)}
                </span>
            )}
        </span>
    );
}

/** L'uscita dichiarata dal servizio (`meta.exit_kind`). */
export function Uscita({ d, testId = 'cr-uscita' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.uscita) return null;
    return (
        <span className="text-[9px] uppercase tracking-wider px-1 rounded bg-teal-500/15 text-teal-300"
            data-testid={testId} title="tipo di uscita dichiarato dal servizio">
            {ETICHETTA_USCITA[d.uscita] ?? d.uscita.replace(/_/g, ' ')}
        </span>
    );
}

const ETICHETTA_USCITA: Record<string, string> = {
    greenup: 'green-up',
    cashout: 'cash out',
    manual: 'manuale',
    market_close: 'chiusura a mercato',
    stop: 'stop',
};
