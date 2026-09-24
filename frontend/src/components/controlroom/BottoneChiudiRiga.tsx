// ============================================================================
// BottoneChiudiRiga.tsx — il «Chiudi» di UNA riga, cablato per singolo bot
// (B16, 24/09). La logica sta in `chiudiRiga.ts`; qui c'e' solo il montaggio.
//
// Il bottone arriva alla riga da un CONTESTO (`ChiusuraRigaContext`) che la
// pagina della Control Room fornisce: le schede che mostrano le righe
// (`SchedaPartita`, `SchedaPreMatch`) non cambiano firma, e dove il contesto
// manca (test storici, altre pagine) il bottone non si monta - nessun comando
// che non ha dietro un servizio.
//
// Cosa dice, sempre, invece di sparire in silenzio:
//   · riga chiudibile → «Chiudi» acceso, `title` = cosa fara' QUEL bot;
//   · riga non chiudibile (bot tennis, gamba di chiusura, coperta, in volo,
//     modalita' ignota) → «Chiudi» spento, `title` = il motivo;
//   · dopo il clic → «richiesta inviata / presa in carico / eseguita /
//     rifiutata: motivo / esito ignoto» accanto al bottone.
// ============================================================================
import { createContext, useContext, useState } from 'react';
import { BOT_LABEL } from '@/lib/controlRoom';
import {
    chiudibile, cosaFaIlClic, faseMostrata, inCorso, TESTO_FASE,
    type RigaDaChiudere, type StatoChiusuraRiga, type FaseChiusura,
} from './chiudiRiga';
import type { Bot } from '@/lib/controlRoom';

export interface ChiusuraRigaApi {
    chiudi: (riga: RigaDaChiudere) => Promise<void>;
    stato: (bot: Bot, id: number) => StatoChiusuraRiga | null;
}

export const ChiusuraRigaContext = createContext<ChiusuraRigaApi | null>(null);

const CLS_FASE: Record<FaseChiusura, string> = {
    inviata: 'text-sky-300',
    presa_in_carico: 'text-amber-300',
    eseguita: 'text-emerald-400',
    rifiutata: 'text-red-400',
    ignota: 'text-orange-400',
};

const CLS_BOTTONE: Record<'riga' | 'orfana', string> = {
    riga: 'h-5 px-1.5 text-[9px] uppercase tracking-wider rounded border border-white/15 text-white/70 '
        + 'hover:text-white hover:border-emerald-500/50 disabled:opacity-40 disabled:hover:text-white/70 '
        + 'disabled:hover:border-white/15 disabled:cursor-not-allowed',
    orfana: 'ml-auto h-6 px-2 text-[10px] uppercase tracking-wider rounded border border-white/15 text-white/70 '
        + 'hover:text-white hover:border-emerald-500/50 disabled:opacity-40 disabled:cursor-not-allowed',
};

export function BottoneChiudiRiga({ riga, testId = 'cr-op-chiudi', variante = 'riga' }: {
    riga: RigaDaChiudere;
    testId?: string;
    variante?: 'riga' | 'orfana';
}) {
    const api = useContext(ChiusuraRigaContext);
    const [inVolo, setInVolo] = useState(false);
    if (!api) return null;
    const c = chiudibile(riga);
    if (c == null) return null;
    const s = api.stato(riga.bot, riga.id);
    const occupato = inVolo || inCorso(s);
    const acceso = c.ok && !occupato;
    const titolo = !c.ok
        ? `non chiudibile: ${c.motivo}`
        : occupato
            ? 'richiesta di chiusura gia\' in corso su questa riga'
            : `${BOT_LABEL[riga.bot]}: ${cosaFaIlClic(riga.bot)}`;
    const fase = s ? faseMostrata(s) : null;
    return (
        <span className="inline-flex items-baseline gap-1" data-testid={`${testId}-box`}>
            <button
                type="button"
                className={CLS_BOTTONE[variante]}
                disabled={!acceso}
                title={titolo}
                aria-label={titolo}
                data-testid={testId}
                data-bot={riga.bot}
                data-motivo={c.ok ? undefined : c.motivo}
                onClick={() => {
                    if (!acceso) return;
                    setInVolo(true);
                    void api.chiudi(riga).finally(() => setInVolo(false));
                }}
            >Chiudi</button>
            {fase && (
                <span className={`text-[9px] ${CLS_FASE[fase]}`} data-testid={`${testId}-esito`}
                    data-fase={fase} title={s?.motivo ?? undefined}>
                    {TESTO_FASE[fase]}{s?.motivo && (fase === 'rifiutata' || fase === 'ignota'
                        || fase === 'presa_in_carico' || fase === 'inviata') ? `: ${s.motivo}` : ''}
                </span>
            )}
        </span>
    );
}
