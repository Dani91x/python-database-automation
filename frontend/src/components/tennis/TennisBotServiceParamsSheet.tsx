// ============================================================================
// TennisBotServiceParamsSheet.tsx — il foglio parametri dei 4 bot tennis
// COME SERVIZIO (`tennis_bot_service_control`), 18/09.
//
// Prima di oggi NESSUN foglio esisteva per questi quattro bot in nessuna
// pagina (A1, riga 147): l'unico editor era lo stake, dentro l'interruttore
// stesso. Qui si costruisce il foglio sui campi che il SERVIZIO LEGGE DAVVERO:
// `TENNIS_BOT_REGISTRY` (`lib/tennis.ts`, sez. 5, pensato per l'armatura
// PER EVENTO) e' stato VERIFICATO in sola lettura contro il codice di
// produzione dei quattro bot —
//   Betfair/stream/tennis_scalper/tennis_scalper_bot.py  (c.get('scalp_ticks',...), ecc.)
//   Betfair/stream/tennis_scalper/tennis_pro_bot.py      (c.get('bp_target_ticks',...), ecc.)
//   Betfair/stream/tennis_scalper/tennis_flb_bot.py      (c.get('lay_max',...), ecc.)
//   Betfair/stream/tennis_scalper/tennis_swing_bot.py    (c.get('N',...), c.get('zin',...), ecc.)
// — chiave per chiave, tipo per tipo: OGNI campo di `TENNIS_BOT_REGISTRY`
// corrisponde a un `c.get(<stessa chiave>, <stesso default>)` nel bot vero.
// Il ponte fra la riga PER SERVIZIO (questa) e l'esecuzione PER EVENTO e'
// `Betfair/stream/tennis_live/tennis_bot_service.py::riconcilia_interruttori`,
// che passa `d["params"]` (cioe' QUESTA colonna) a `tennis_bot_arm` invariata:
// non c'e' nessuna traduzione di chiave nel mezzo.
//
// I campi booleani del registro sono `type: 'select'` con `bool: true`
// (valori 'on'/'off'): e' lo STESSO schema e la STESSA conversione gia' in
// produzione in `components/tennis/TennisBotPanel.tsx` (armatura per evento,
// funzione `handleToggle`) — riusata qui identica, non reinventata.
// ============================================================================
import {
    ParamsSheetBase, type ParamField, type ParamGroup, type ParamValues,
} from '@/components/trading/ParamsSheetBase';
import {
    TENNIS_BOT_REGISTRY, updateTennisBotService,
    type TennisBotKey, type TennisBotParamField,
} from '@/lib/tennis';

/** Un campo del registro -> un campo di `ParamsSheetBase`. Stessa chiave,
 *  stesso min/max/step/opzioni: nessuna traduzione di significato. */
function campoDi(f: TennisBotParamField): ParamField {
    return {
        key: f.key,
        label: f.label,
        hint: f.hint,
        type: f.type === 'select' ? 'select' : 'number',
        min: f.min,
        max: f.max,
        step: f.step,
        options: f.options,
    };
}

export interface TennisBotServiceParamsSheetProps {
    botKey: TennisBotKey;
    /** i parametri grezzi della riga di control di QUESTO bot
     *  (`tennis_bot_service_control.params`); `null` = non ancora letti */
    rawParams: Record<string, unknown> | null;
    busy?: boolean;
    onSaved: () => void;
    triggerTestId?: string;
}

export function TennisBotServiceParamsSheet({
    botKey, rawParams, busy = false, onSaved, triggerTestId,
}: TennisBotServiceParamsSheetProps) {
    const descrittore = TENNIS_BOT_REGISTRY.find((d) => d.key === botKey);
    if (!descrittore) return null;

    // I parametri CORRENTI del servizio, con ripiego sui default del registro
    // (che sono gli STESSI default del bot Python: `c.get(chiave, default)`).
    // `scriviChiave`/`updateTennisBotService` sostituiscono l'INTERA colonna
    // `params`: partire dai correnti (non dai soli campi noti) preserva
    // qualunque chiave che il registro non conosce ancora.
    const correnti = (rawParams ?? {}) as Record<string, unknown>;
    const values: ParamValues = {};
    for (const f of descrittore.params) {
        const v = correnti[f.key];
        if (f.type === 'select' && f.bool) {
            // booleano vero -> 'on'/'off' (stesso schema di TennisBotPanel)
            const b = typeof v === 'boolean' ? v : undefined;
            values[f.key] = b === undefined
                ? String(descrittore.defaults[f.key] ?? 'off')
                : (b ? 'on' : 'off');
        } else if (f.type === 'select') {
            values[f.key] = typeof v === 'string' ? v : String(descrittore.defaults[f.key] ?? '');
        } else {
            const n = Number(v);
            values[f.key] = Number.isFinite(n) ? n : Number(descrittore.defaults[f.key] ?? 0);
        }
    }

    const groups: ParamGroup[] = [{
        label: descrittore.name,
        note: descrittore.short,
        fields: descrittore.params.map(campoDi),
    }];

    async function save(next: ParamValues) {
        // si riparte SEMPRE dai parametri correnti (compresa qualunque chiave
        // che il registro non elenca): `updateTennisBotService` sostituisce
        // l'intera colonna, mandare solo i campi noti cancellerebbe il resto.
        const payload: Record<string, unknown> = { ...correnti };
        for (const f of descrittore!.params) {
            const v = next[f.key];
            if (f.type === 'select' && f.bool) {
                payload[f.key] = v === 'on';
            } else if (f.type === 'select') {
                payload[f.key] = String(v ?? '');
            } else {
                const n = Number(v);
                if (Number.isFinite(n)) payload[f.key] = n;
            }
        }
        await updateTennisBotService(botKey, { params: payload });
        onSaved();
    }

    return (
        <ParamsSheetBase
            title={`Parametri ${descrittore.name}`}
            description="Sono gli STESSI parametri che il bot Python legge per ogni evento che arma (verificati chiave per chiave contro il codice del bot). Salvando qui si cambia il servizio: gli eventi gia' armati li rileggono al giro successivo."
            groups={groups}
            values={values}
            busy={busy}
            onSave={save}
            onReset={() => ({ ...(descrittore!.defaults as unknown as ParamValues) })}
            triggerTestId={triggerTestId ?? `cr-tennis-params-trigger-${botKey}`}
            footer={rawParams == null
                ? <span className="text-amber-300">parametri non ancora letti dal servizio: qui sotto ci sono i default del registro, non necessariamente quelli in uso.</span>
                : undefined}
        />
    );
}

export default TennisBotServiceParamsSheet;
