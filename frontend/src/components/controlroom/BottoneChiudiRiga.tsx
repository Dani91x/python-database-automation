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
//   - riga non chiudibile (bot tennis senza partita/mercato, gamba di
//     chiusura, coperta, in volo, modalita' ignota) -> "Chiudi" spento,
//     `title` = il motivo (D3, 24/09: i bot tennis ora si chiudono);
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
import type { ClicOrdine } from '@/lib/esitoAbbinamento';
import type { ContestoPrezzoVisto } from '@/lib/schedaAlMs';
import type { EsitoSeguito } from './useSeguiOrdini';
import type { SorgenteLadder } from './usePrezzoAlMs';

export interface ChiusuraRigaApi {
    chiudi: (riga: RigaDaChiudere) => Promise<void>;
    stato: (bot: Bot, id: number) => StatoChiusuraRiga | null;
    /** B17 (25/09) — l'esito dell'ORDINE di chiusura (abbinato a che prezzo). Opzionale. */
    esito?: (bot: Bot, id: number) => EsitoSeguito | null;
    /** B17 — per le schede nella partita (Mike): seguire un clic e leggerne l'esito */
    seguiClic?: (clic: Omit<ClicOrdine, 'idsNotiAlClic'>) => void;
    esitoOrdine?: (chiave: string) => EsitoSeguito | null;
    esitiOrdini?: EsitoSeguito[];
    /**
     * 25/09 (residui B17) - la sorgente del ladder AL MS per il "se chiudo
     * ora" delle righe (`useChiusuraAlMs`). Assente = solo lo scanner, dichiarato.
     */
    sorgenteLadder?: SorgenteLadder | null;
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

export function BottoneChiudiRiga({ riga, testId = 'cr-op-chiudi', variante = 'riga', prezzoAlClic }: {
    riga: RigaDaChiudere;
    testId?: string;
    variante?: 'riga' | 'orfana';
    /**
     * 25/09 (residui B17) - il prezzo "se chiudo ora" A VIDEO nell'istante del
     * clic (al ms o scanner) col suo contesto: va alla scheda per il delta dopo
     * l'abbinamento, MAI nel payload della richiesta.
     */
    prezzoAlClic?: () => { prezzo: number | null; contesto: ContestoPrezzoVisto };
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
    // B17 (25/09) — dopo la richiesta, l'ORDINE: a che prezzo e quanto abbinato
    const es = api.esito?.(riga.bot, riga.id) ?? null;
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
                    const visto = prezzoAlClic?.();
                    void api.chiudi(visto ? { ...riga, prezzoVisto: visto.prezzo, contestoVisto: visto.contesto } : riga)
                        .finally(() => setInVolo(false));
                }}
            >Chiudi</button>
            {fase && (
                <span className={`text-[9px] ${CLS_FASE[fase]}`} data-testid={`${testId}-esito`}
                    data-fase={fase} title={s?.motivo ?? undefined}>
                    {TESTO_FASE[fase]}{s?.motivo && (fase === 'rifiutata' || fase === 'ignota'
                        || fase === 'presa_in_carico' || fase === 'inviata') ? `: ${s.motivo}` : ''}
                </span>
            )}
            {es && (es.gambe.length > 0 || es.esito.terminale) && (
                <span className="text-[9px] text-white/70" data-testid={`${testId}-ordine`}
                    data-fase={es.esito.fase} title={`esito: ${es.esito.fonte}`}>
                    {es.esito.simulato ? '[paper] ' : ''}{es.esito.testo}
                </span>
            )}
        </span>
    );
}
