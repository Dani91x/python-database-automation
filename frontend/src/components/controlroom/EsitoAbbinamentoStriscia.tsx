// ============================================================================
// EsitoAbbinamentoStriscia.tsx - B17 (25/09): IL MESSAGGIO DOPO IL CLIC.
//
// «una volta che clicco, devo sapere a che prezzo e' stato abbinato il mio
// ordine rispetto al segnale e soprattutto se e' stato realmente abbinato,
// con un messaggio» (utente, 25/09). Il testo lo scrive `lib/esitoAbbinamento`
// (puro, testato); qui c'e' solo il montaggio: messaggio, prezzo visto e del
// segnale, fonte ed eta' dell'esito, cartellino PAPER quando l'abbinamento e'
// simulato (stesso messaggio del live).
// ============================================================================
import { Loader2 } from 'lucide-react';
import { fmtOdds } from '@/lib/format';
import { esitoGamba, testoModoGambe, type FaseEsito } from '@/lib/esitoAbbinamento';
import type { EsitoSeguito } from './useSeguiOrdini';

const CLS: Record<string, string> = {
    ok: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    parziale: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    ko: 'border-red-500/30 bg-red-500/10 text-red-200',
    ignoto: 'border-orange-500/30 bg-orange-500/10 text-orange-200',
    attesa: 'border-white/10 bg-white/[0.03] text-white/70',
};

export function EsitoAbbinamentoStriscia({ seguito, testId = 'cr-esito-abbinamento' }: {
    seguito: EsitoSeguito;
    testId?: string;
}) {
    const { clic, esito } = seguito;
    return (
        <div
            className={`px-3 py-1.5 border-b text-[10.5px] space-y-0.5 ${CLS[esito.tono] ?? CLS.attesa}`}
            data-testid={testId}
            data-fase={esito.fase}
            data-chiave={clic.chiave}
            data-terminale={esito.terminale ? '1' : '0'}
            role={esito.tono === 'ko' ? 'alert' : undefined}
        >
            <div className="flex items-baseline gap-1.5 flex-wrap">
                {!esito.terminale && <Loader2 className="w-3 h-3 animate-spin shrink-0 self-center" />}
                <span className="text-white/50">{clic.etichetta}</span>
                {esito.simulato
                    ? <span className="text-[9px] font-bold uppercase px-1 rounded bg-white/10 text-white/60"
                        data-testid={`${testId}-paper`}
                        title="paper: l'abbinamento e' simulato sul book vero, il messaggio e' quello del live">
                        paper · abbinamento simulato
                    </span>
                    : clic.modo === 'live'
                        ? <span className="text-[9px] font-bold uppercase px-1 rounded bg-orange-500/20 text-orange-300">soldi veri</span>
                        : null}
            </div>
            <div className="font-semibold" data-testid={`${testId}-testo`}>{esito.testo}</div>
            <div className="text-white/45 flex flex-wrap gap-x-2" data-testid={`${testId}-prezzi`}>
                <span>visto al clic {fmtOdds(clic.prezzoVisto)}</span>
                <span>segnale {fmtOdds(clic.prezzoSegnale)}</span>
                {esito.prezzoMedio !== null && <span>medio abbinato {fmtOdds(esito.prezzoMedio)}</span>}
            </div>
            <div className="text-white/35" data-testid={`${testId}-fonte`}>esito: {esito.fonte}</div>
            {/* 25/09 (residui B17) - come sono state trovate le gambe: per chiave
                o, se il servizio non l'ha scritta, per correlazione DICHIARATA */}
            {(seguito.modoGambe === 'chiave' || seguito.modoGambe === 'correlazione') && (
                <div className={seguito.modoGambe === 'correlazione' ? 'text-orange-300/80' : 'text-white/35'}
                    data-testid={`${testId}-modo`} data-modo={seguito.modoGambe}>
                    gambe: {testoModoGambe(seguito.modoGambe)}
                </div>
            )}
        </div>
    );
}

/** Una riga del dettaglio per ordine del cash out globale. */
export interface RigaOrdineCashOut {
    chiave: string;
    testo: string;
    tono: 'ok' | 'parziale' | 'ko' | 'attesa';
}

const TONO_FASE: Record<FaseEsito, RigaOrdineCashOut['tono']> = {
    inviato: 'attesa', in_corso: 'attesa', accettato: 'attesa', parziale: 'parziale',
    totale: 'ok', non_abbinato: 'ko', rifiutato: 'ko', ignoto: 'attesa',
};

/**
 * 25/09 (residui B17) - IL DETTAGLIO PER ORDINE del cash out globale (puro,
 * testato). Una riga per ogni ordine di chiusura DICHIARATO dal servizio
 * (`result.closing_trade_ids`), nell'ordine del servizio: l'esito della sua
 * riga (stesse parole di `esitoAbbinamento`) oppure «in attesa della riga».
 * Poi una riga per ogni posizione che il servizio dichiara NON chiusa
 * (`result.non_chiuse`), col suo motivo. Nessun id indovinato.
 */
export function righeOrdiniCashOut(seguito: EsitoSeguito): RigaOrdineCashOut[] {
    const dichiarati = seguito.richiesta?.tradeIds ?? [];
    const out: RigaOrdineCashOut[] = dichiarati.map((id) => {
        const i = seguito.gambe.findIndex((g) => g.id === id);
        if (i < 0) {
            return { chiave: `o${id}`, testo: `ordine #${id}: in attesa della riga dell'ordine`, tono: 'attesa' };
        }
        const e = esitoGamba(seguito.gambe[i].riga);
        return {
            chiave: `o${id}`,
            testo: `ordine #${id}: ${seguito.esito.righe[i] ?? seguito.esito.testo}`,
            tono: TONO_FASE[e.fase],
        };
    });
    for (const n of seguito.richiesta?.nonChiuse ?? []) {
        out.push({
            chiave: `n${n.tradeId ?? out.length}`,
            testo: `posizione #${n.tradeId ?? '?'} NON chiusa: rifiutato: ${n.motivo}`
                + (n.closingTradeId !== null ? ` (ordine #${n.closingTradeId} partito)` : ''),
            tono: 'ko',
        });
    }
    return out;
}

const CLS_RIGA: Record<RigaOrdineCashOut['tono'], string> = {
    ok: 'text-emerald-300', parziale: 'text-amber-300', ko: 'text-red-300', attesa: 'text-white/60',
};

/** Il messaggio del clic + il dettaglio per ordine (cash out globale di partita). */
export function EsitoOrdiniCashOut({ seguito, testId = 'cr-cashout-ordini' }: {
    seguito: EsitoSeguito;
    testId?: string;
}) {
    const righe = righeOrdiniCashOut(seguito);
    return (
        <div data-testid={testId}>
            <EsitoAbbinamentoStriscia seguito={seguito} testId={`${testId}-esito`} />
            {righe.length > 0 && (
                <ul className="px-3 py-1 text-[10.5px] space-y-0.5" data-testid={`${testId}-lista`}>
                    {righe.map((r) => (
                        <li key={r.chiave} className={CLS_RIGA[r.tono]} data-testid={`${testId}-riga`}
                            data-tono={r.tono}>
                            {r.testo}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

export default EsitoAbbinamentoStriscia;
