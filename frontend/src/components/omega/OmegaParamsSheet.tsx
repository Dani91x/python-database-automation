// ============================================================================
// OmegaParamsSheet.tsx — il foglio parametri di Omega, MONTATO ANCHE FUORI
// DA `pages/Omega.tsx` (Control Room, 18/09).
//
// «Ogni bot deve avere i suoi parametri di configurazione DEDICATI A LUI»
// (utente, 18/09). Omega e' l'unico dei tre bot del calcio che in Control
// Room non aveva NESSUN foglio (A1, riga 144: gap piu' piccolo, il componente
// esisteva gia'). Qui non nasce nessuna logica nuova: si riusa `ParamsSheetBase`
// (lo stesso di `Omega.tsx:540`) e le costanti gia' esportate da `lib/omega.ts`
// (`OMEGA_PARAM_GROUPS`, `OMEGA_PARAM_DEFAULTS`, `OMEGA_DAILY_GOAL_MAX`,
// `omegaParamsPatch`, `updateOmegaParams`) — le STESSE che usa la pagina.
//
// L'UNICA cosa che NON si puo' riusare 1:1 e' il gruppo "Obiettivo" (che in
// Omega.tsx e' una COSTANTE PRIVATA di modulo, non esportata): e' un blocco di
// puro assemblaggio (un campo, nessuna logica), duplicato qui per necessita' —
// non per scelta — perche' `pages/Omega.tsx` e' fuori dal mio perimetro (di
// altri costruttori). Va tenuto allineato a mano se cambia la, vedi referto.
// ============================================================================
import {
    ParamsSheetBase, type ParamGroup, type ParamValues,
} from '@/components/trading/ParamsSheetBase';
import {
    OMEGA_PARAM_GROUPS, OMEGA_PARAM_DEFAULTS, OMEGA_DAILY_GOAL_MAX,
    omegaParamsPatch, updateOmegaParams, type OmegaParams,
    USCITE_PROTEZIONE_KEY, modoUsciteProtezione,
} from '@/lib/omega';

/** Il gruppo "Obiettivo" — DUPLICATO DICHIARATO da `pages/Omega.tsx` (vedi
 *  commento in testa al file): l'obiettivo giornaliero vive sulla colonna
 *  dedicata `omega_control.daily_goal`, non dentro `params`, quindi non e'
 *  nella whitelist di `OMEGA_PARAM_GROUPS`. */
const OMEGA_PARAM_GROUPS_UI: ParamGroup[] = [
    {
        label: 'Obiettivo',
        note: 'quanto deve produrre la giornata: il servizio ne ricava il target per partita e per gamba.',
        fields: [{
            key: '__daily_goal', label: 'Obiettivo giornaliero (€)', type: 'number' as const,
            min: 0, max: OMEGA_DAILY_GOAL_MAX, step: 10,
            hint: 'storicizzato a fine giornata: lo Storico giudica "centrato" solo sull’obiettivo di QUEL giorno',
        }],
    },
    ...OMEGA_PARAM_GROUPS,
];

export interface OmegaParamsSheetProps {
    /** i parametri grezzi dalla riga di control (`omega_control.params`) */
    rawParams: Record<string, unknown> | null;
    /** l'obiettivo di oggi (`omega_control.daily_goal`), fuori da `params` */
    dailyGoal: number | null;
    busy?: boolean;
    /** richiamato dopo un salvataggio riuscito: la pagina rilegge dal servizio */
    onSaved: () => void;
    triggerTestId?: string;
}

export function OmegaParamsSheet({
    rawParams, dailyGoal, busy = false, onSaved, triggerTestId = 'cr-omega-params-trigger',
}: OmegaParamsSheetProps) {
    const values: ParamValues = {
        __daily_goal: dailyGoal ?? 250,
        ...(OMEGA_PARAM_DEFAULTS as unknown as Record<string, number | boolean | string>),
        ...(rawParams as unknown as Record<string, number | boolean | string> ?? {}),
        // 24/09 — i due pulsanti mostrano il valore COME LO LEGGE il servizio:
        // assente o sconosciuto = «Avvisa e proponi» (fail-closed)
        [USCITE_PROTEZIONE_KEY]: modoUsciteProtezione((rawParams ?? {})[USCITE_PROTEZIONE_KEY]),
    };

    async function save(next: ParamValues) {
        const goal = Number(next.__daily_goal);
        const draft = { ...next } as Record<string, unknown>;
        delete draft.__daily_goal;
        // H-07 (lib/omega.ts): si manda lo STATO DEL SERVIZIO piu' SOLO le
        // chiavi che l'utente ha davvero cambiato — mai un default della UI
        // sopra un valore vivo che nessuno ha chiesto di toccare.
        const payload = omegaParamsPatch(rawParams, draft);
        await updateOmegaParams({
            dailyGoal: Number.isFinite(goal) && goal >= 0 ? goal : undefined,
            params: payload as Partial<OmegaParams>,
        });
        onSaved();
    }

    return (
        <ParamsSheetBase
            title="Parametri Omega"
            symbol={<span className="text-primary text-xl" aria-hidden>{'Ω'}</span>}
            description="Limiti e unita' sono quelli della whitelist del servizio: un valore fuori range viene clampato e dichiarato. «Salva parametri» invia i valori del servizio piu' le TUE modifiche, non i default della UI."
            groups={OMEGA_PARAM_GROUPS_UI}
            values={values}
            onSave={save}
            onReset={() => ({
                __daily_goal: 250,
                ...(OMEGA_PARAM_DEFAULTS as unknown as Record<string, number | boolean | string>),
            })}
            busy={busy}
            triggerTestId={triggerTestId}
            footer={<>I tre cap (liability/partita, stop-loss, liability aperta) sono <b>OFF di default</b>: Omega e' set-and-forget. Mettili &gt; 0 per attivarli.</>}
        />
    );
}

export default OmegaParamsSheet;
