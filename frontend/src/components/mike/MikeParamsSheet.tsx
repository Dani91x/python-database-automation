// ============================================================================
// MikeParamsSheet — TUTTI i parametri del bot Mike, sul pannello CONDIVISO
// (`ParamsSheetBase`, design system §12): clamp VISIBILE ("clampato a 100
// (ammesso 0,50 … 100)"), pallino "modifiche non salvate", un solo bottone
// «Salva parametri» e il bottone «Default» che riporta ai valori di fabbrica
// (= quelli del servizio, MIKE_PARAM_DEFAULTS, specchio di config.py).
//
// La spec arriva da MIKE_PARAM_FIELDS: aggiungere un parametro al data-layer lo
// fa comparire qui senza toccare questo file.
// ============================================================================
import { useMemo } from 'react';
import { ParamsSheetBase, type ParamGroup } from '@/components/trading/ParamsSheetBase';
import {
    MIKE_PARAM_FIELDS, MIKE_PARAM_GROUP_LABEL, MIKE_PARAM_DEFAULTS, mergeMikeParams,
    type MikeParamGroup, type MikeParams,
} from '@/lib/mike';

const GROUPS: MikeParamGroup[] = ['generale', 'pre', 'cover', 'cashout', 'uscite', 'reentry', 'rischio'];

const GROUP_NOTE: Partial<Record<MikeParamGroup, string>> = {
    generale: 'finestra di lavoro, importo e commissione: valgono per tutte le partite.',
    pre: 'ingresso Under 3.5 e green-up ciclico prima del calcio d’inizio.',
    cover: 'copertura Over 4.5 in gioco: "intelligente ma non lenta".',
    cashout: 'chiusura globale a profitto (Under 3.5 + Over 4.5), soglia e cash out intelligente.',
    uscite: 'uscite in perdita all’intervallo e nel secondo tempo (a modello o regola fissa).',
    reentry: 're-ingresso sull’Under 4.5 dopo un gol e una chiusura in profitto.',
    rischio: 'tetti e stop: sono l’ultima barriera prima dei soldi veri.',
};

export interface MikeParamsSheetProps {
    params: MikeParams;
    busy: boolean;
    onSave: (p: MikeParams) => Promise<void> | void;
}

export function MikeParamsSheet({ params, busy, onSave }: MikeParamsSheetProps) {
    const groups = useMemo<ParamGroup[]>(() => GROUPS.map((g) => ({
        label: MIKE_PARAM_GROUP_LABEL[g],
        note: GROUP_NOTE[g],
        fields: MIKE_PARAM_FIELDS.filter((f) => f.group === g).map((f) => {
            if (f.kind === 'number') {
                return { key: f.key, label: f.label, hint: f.hint, type: 'number' as const, min: f.min, max: f.max, step: f.step };
            }
            if (f.kind === 'bool') return { key: f.key, label: f.label, hint: f.hint, type: 'boolean' as const };
            if (f.kind === 'choice') {
                return {
                    key: f.key, label: f.label, hint: f.hint, type: 'select' as const,
                    options: f.choices.map((c) => ({ value: c, label: c })),
                };
            }
            // stringa libera (filtro competizioni): nessun clamp, nessun cast
            return { key: f.key, label: f.label, hint: f.hint, type: 'text' as const };
        }),
    })), []);

    return (
        <ParamsSheetBase
            title="Parametri Mike"
            symbol={<span className="text-teal-300 text-xl" aria-hidden>🎯</span>}
            description="Tutto modificabile. Salva per applicare a caldo: il servizio rilegge i parametri a ogni ciclo. I valori fuori dai limiti vengono riportati nei limiti e te lo diciamo."
            groups={groups}
            values={params}
            busy={busy}
            triggerTestId="mike-params-trigger"
            onSave={(v) => onSave(mergeMikeParams(v))}
            onReset={() => ({ ...MIKE_PARAM_DEFAULTS })}
            footer="La modalità (PAPER/LIVE) non è un parametro: si cambia solo dal toggle in alto, con conferma."
        />
    );
}

export default MikeParamsSheet;
