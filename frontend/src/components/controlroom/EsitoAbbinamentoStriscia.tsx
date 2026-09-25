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
        </div>
    );
}

export default EsitoAbbinamentoStriscia;
