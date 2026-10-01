// ============================================================================
// InterruttoreUscite.tsx - IL PULSANTE DELLE USCITE, UGUALE PER OGNI BOT.
//
// Ordine dell'utente (28/09, testuale): "TUTTI I BOT DEVONO AVERE LA
// POSSIBILITA' DI USCITE MANUALI, OVVERO APPROVATE DA ME, OPPURE, TOTALMENTE
// AUTOMATICHE! SERVE UN PULSANTE [...] OGNI BOT, PER ORA, DEVE PASSARE DA ME".
//
// UN componente, montato nello STESSO punto della riga di ogni bot (Omega,
// Mike, Safe per strategia, scalper, i quattro bot tennis), con le STESSE
// parole per tutti:
//   - stato sempre visibile: "uscite: MANUALI, approvi tu" oppure
//     "uscite: AUTOMATICHE" (o "uscite: non lette", senza pulsante);
//   - "passa ad automatiche" chiede CONFERMA (secondo clic, inerte per
//     ATTESA_CONFERMA_MS: un doppio clic non la colpisce) - da li' il bot
//     chiude da solo;
//   - "passa a manuali" non chiede niente: riduce il rischio.
// Lo stato mostrato e' quello che RISPONDE il servizio, mai quello sperato.
// Prima del 28/09 i bot tennis avevano un pulsante loro (UsciteTennis.tsx) con
// parole e posto diversi: sostituito da questo.
// ============================================================================
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import type { StatoUscite } from '@/lib/interruttori';

/** Stessa attesa anti-doppio-clic della conferma "soldi veri" (review 15/09). */
export const ATTESA_CONFERMA_USCITE_MS = 400;

export const TESTO_USCITE_MANUALI = 'MANUALI, approvi tu';
export const TESTO_USCITE_AUTOMATICHE = 'AUTOMATICHE';

/** La frase dello stato, senza il prefisso "uscite:". */
export function testoStatoUscite(u: StatoUscite): string {
    if (u.automatiche == null) return `non lette${u.nota ? ` (${u.nota})` : ''}`;
    if (u.automatiche) return `${TESTO_USCITE_AUTOMATICHE}${u.nota ? ` (${u.nota})` : ''}`;
    const aperte = u.aperte != null
        ? ` - ${u.aperte} ${u.aperte === 1 ? 'posizione aperta' : 'posizioni aperte'}`
            + (u.aperte > 0 && u.daMin != null ? ` da ${u.daMin} min` : '')
        : '';
    return `${TESTO_USCITE_MANUALI}${aperte}${u.nota ? ` (${u.nota})` : ''}`;
}

/**
 * 30/09 (B2, A12) - i tooltip dei pulsanti, guidati dallo STATO: dove
 * l'interruttore governa solo le uscite in perdita (Mike, `soloUsciteInPerdita`)
 * non si puo' dire «in profitto e in perdita». Per gli altri bot: le parole di sempre.
 */
export function titoloPassaAManuali(u: StatoUscite): string {
    return u.soloUsciteInPerdita
        ? 'le uscite in PERDITA della strategia diventano PROPOSTE nella scheda: le approvi tu. Le uscite in profitto (green-up, uscita al fischio, cash out in profitto) le esegue sempre il bot; le protezioni restano automatiche'
        : 'le uscite della strategia (in profitto e in perdita) diventano PROPOSTE nella scheda: le approvi tu. Le protezioni restano automatiche';
}

export function titoloConfermaAutomatiche(u: StatoUscite): string {
    return u.soloUsciteInPerdita
        ? 'confermi? da qui il bot esegue da solo anche le uscite in PERDITA secondo la sua strategia (quelle in profitto le esegue gia’ da solo)'
        : 'confermi? da qui il bot chiude da solo secondo la sua strategia, in profitto e in perdita';
}

export interface InterruttoreUsciteProps {
    /** id della riga (test id stabili: cr-uscite-<id>, cr-uscite-stato-<id>, ...) */
    id: string;
    uscite: StatoUscite;
    /** assente = solo lettura (nessun pulsante) */
    cambia?: (automatiche: boolean) => Promise<void> | void;
    occupato?: boolean;
}

export function InterruttoreUscite({ id, uscite, cambia, occupato = false }: InterruttoreUsciteProps) {
    /** istante in cui la conferma e' comparsa; null = non armata */
    const [armataDa, setArmataDa] = useState<number | null>(null);
    const [, setTic] = useState(0);
    useEffect(() => {
        if (armataDa == null) return;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_USCITE_MS + 20);
        return () => window.clearTimeout(t);
    }, [armataDa]);
    // se il servizio risponde con un altro stato la conferma non ha piu' senso
    useEffect(() => { setArmataDa(null); }, [uscite.automatiche]);
    const troppoPresto = armataDa != null && Date.now() - armataDa < ATTESA_CONFERMA_USCITE_MS;

    const colore = uscite.automatiche == null ? 'text-orange-300'
        : uscite.automatiche ? 'text-emerald-300' : 'text-amber-300 font-semibold';

    return (
        <div className="flex items-center gap-2 mt-1.5 flex-wrap text-[10.5px]"
            data-testid={`cr-uscite-${id}`}>
            <span className="text-white/40">uscite:</span>
            <span className={colore} data-testid={`cr-uscite-stato-${id}`}>
                {testoStatoUscite(uscite)}
            </span>
            {uscite.automatiche === true && cambia && (
                <Button
                    type="button" size="sm" variant="ghost"
                    disabled={occupato}
                    onClick={() => void cambia(false)}
                    data-testid={`cr-uscite-cambia-${id}`}
                    title={titoloPassaAManuali(uscite)}
                    className="h-6 px-2 text-[10px] ds-v2-pulsante ds-v2-pulsante--sm ds-v2-pulsante--secondario"
                >passa a manuali</Button>
            )}
            {uscite.automatiche === false && cambia && (armataDa != null ? (
                <>
                    <Button
                        type="button" size="sm" variant="ghost"
                        disabled={occupato || troppoPresto}
                        onClick={() => { setArmataDa(null); void cambia(true); }}
                        data-testid={`cr-uscite-conferma-${id}`}
                        title={titoloConfermaAutomatiche(uscite)}
                        className="h-6 px-2 text-[10px] bg-amber-600/70 hover:bg-amber-600 text-white ds-v2-pulsante ds-v2-pulsante--sm"
                    >confermi? passa ad automatiche</Button>
                    <Button
                        type="button" size="sm" variant="ghost"
                        disabled={occupato}
                        onClick={() => setArmataDa(null)}
                        data-testid={`cr-uscite-annulla-${id}`}
                        className="h-6 px-2 text-[10px] ds-v2-pulsante ds-v2-pulsante--sm ds-v2-pulsante--secondario"
                    >annulla</Button>
                </>
            ) : (
                <Button
                    type="button" size="sm" variant="ghost"
                    disabled={occupato}
                    onClick={() => setArmataDa(Date.now())}
                    data-testid={`cr-uscite-cambia-${id}`}
                    title="il bot chiuderebbe da solo: si conferma col secondo clic"
                    className="h-6 px-2 text-[10px] ds-v2-pulsante ds-v2-pulsante--sm ds-v2-pulsante--secondario"
                >passa ad automatiche</Button>
            ))}
        </div>
    );
}

export default InterruttoreUscite;
