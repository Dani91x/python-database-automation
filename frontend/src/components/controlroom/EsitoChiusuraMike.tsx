// ============================================================================
// EsitoChiusuraMike.tsx - L'ESITO DELLA CHIUSURA NELLA SCHEDA DI MIKE (29/09, M7.2).
//
// Montato UNA volta nella pagina di Mike (sotto la card della partita, accanto
// alla proposta di uscita) e UNA volta nella card di Mike in Control Room
// (`SchedaMike`): stesso componente, stessa funzione pura
// (`lib/mikeEsitoChiusura.ts`), nessun secondo percorso, nessuna lettura nuova.
// Dopo ogni chiusura (firmata, partita da sola in profitto, o col Chiudi /
// Cash out) dice: chiusura in corso con gli ordini e l'abbinato; oppure CHIUSA
// col risultato bloccato e «nessuna esposizione residua» (solo se i conti degli
// ordini abbinati lo provano); oppure NON COMPLETA con l'esposizione che resta;
// oppure DA VERIFICARE col motivo. Senza chiusure da raccontare non disegna niente.
// ============================================================================
import { fmtMoney, fmtOdds } from '@/lib/format';
import { MIKE_TERMINAL_STATES, type MikeEvent } from '@/lib/mike';
import { esitoChiusuraMike, type TipoEsitoChiusura } from '@/lib/mikeEsitoChiusura';
import { useSecondTick } from '@/components/mike/useMikeClock';
import { useMikeEventoAlMs, type CanaleEventiMike } from '@/components/mike/useMikeEventoAlMs';

const STILE: Record<TipoEsitoChiusura, string> = {
    in_corso: 'border-sky-400/40 bg-sky-400/10 text-sky-100',
    chiusa: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
    non_completa: 'border-red-500/50 bg-red-500/10 text-red-100',
    da_verificare: 'border-amber-400/50 bg-amber-400/10 text-amber-100',
};

export function EsitoChiusuraMike({ ev: evDb, tentativiMax, testId = 'cr-mike-esito-chiusura', canaleMike }: {
    ev: MikeEvent;
    /** `close_max_attempts` dei parametri del bot; assente = valore di serie */
    tentativiMax?: number | null;
    testId?: string;
    /** M7.1 — il canale locale di Mike (test: un finto; null = solo il database) */
    canaleMike?: (() => CanaleEventiMike) | null;
}) {
    const terminaleDb = MIKE_TERMINAL_STATES.includes(evDb.state);
    // M7.1: stato, gambe e `live` dal canale al ms (via principale), `ctx` dal database
    const { ev } = useMikeEventoAlMs(evDb, !terminaleDb, canaleMike);
    const terminale = MIKE_TERMINAL_STATES.includes(ev.state);
    const adesso = useSecondTick(!terminale);
    // il «di M» solo se i parametri del bot sono noti (pagina di Mike); la card
    // della Control Room non li riceve: «tentativo n» e basta, mai un 20 finto
    const max = typeof tentativiMax === 'number' && Number.isFinite(tentativiMax) && tentativiMax > 0
        ? tentativiMax : null;
    const e = esitoChiusuraMike(ev, { nowMs: adesso, tentativiMax: max });
    if (e == null) return null;
    return (
        <div className={`rounded border px-2.5 py-2 space-y-1 text-[10.5px] ${STILE[e.tipo]}`}
            data-testid={testId} data-tipo={e.tipo}>
            <div className="font-semibold" data-testid={`${testId}-titolo`}>{e.titolo}</div>
            {e.motivo && <div className="text-white/60" data-testid={`${testId}-motivo`}>{e.motivo}</div>}
            {e.ordini.length > 0 && (
                <ul className="font-mono text-white/80 space-y-0.5" data-testid={`${testId}-ordini`}>
                    {e.ordini.map((o) => (
                        <li key={o.ref} data-testid={`${testId}-ordine`}>
                            {`${o.ruolo} · ${o.lato} · chiesti ${fmtMoney(o.chiesto)} · abbinati ${fmtMoney(o.abbinato)}`
                                + ` @ ${fmtOdds(o.prezzo)} · ${o.stato}`}
                        </li>
                    ))}
                </ul>
            )}
            {e.dettagli.map((d) => (
                <div key={d} className="text-white/70" data-testid={`${testId}-dettaglio`}>{d}</div>
            ))}
        </div>
    );
}

export default EsitoChiusuraMike;
