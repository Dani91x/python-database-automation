// ============================================================================
// useApplicaBot — la richiesta «Applica bot» e il suo esito (07/10).
// Stesso giro del 06/10 (MatchReplay): la richiesta va nella coda del Backtest
// Automatico, l'esito si rilegge ogni 3 s finche' non e' DONE/ERROR. Estratto
// in un hook per riusarlo identico nel Match Replay (calcio) e nel Replay
// Tennis: il riquadro (ApplicaBotPanel) e il risultato (EsitoBotPanel) lo
// ricevono come prop.
// ============================================================================
import { useCallback, useEffect, useState } from 'react';
import {
    leggiEsitoBot, richiediApplicaBot,
    type EsitoBot, type OpzioniApplica, type RigaBot, type StatoRichiestaBot,
} from '@/lib/replayBot';

/** dopo quanto, in coda, la UI dice che il banco del replay non e' acceso */
export const ATTESA_BANCO_SPENTO_MS = 20_000;
/** ogni quanto si rilegge l'esito */
export const RILETTURA_ESITO_MS = 3000;

export interface RichiestaBot {
    id: string;
    stato: StatoRichiestaBot | null;
    errore?: string;
    inviataMs?: number;
    /** 07/10 sera: che cosa la pagina ha MANDATO (bot, scenario, opzioni), per
     *  confrontarlo con l'esito (avvisi) e per rilanciare coi clic nuovi */
    inviato?: { eventId: string; bot: string; scenario: string; opzioni: OpzioniApplica };
}

export interface ApplicaBot {
    richiesta: RichiestaBot | null;
    /** l'esito COMPLETO (DONE con esito), altrimenti null */
    esito: EsitoBot | null;
    /** la cronologia degli ordini dell'esito ([] senza esito) */
    righe: RigaBot[];
    /** una richiesta in coda o in corso: il pulsante resta spento */
    inCorso: boolean;
    /** le opzioni dell'ultima richiesta mandata (null: nessuna) */
    inviato: OpzioniApplica | null;
    invia: (eventId: string, bot: string, scenario: string, opzioni?: OpzioniApplica) => void;
    azzera: () => void;
}

export function useApplicaBot(): ApplicaBot {
    const [richiesta, setRichiesta] = useState<RichiestaBot | null>(null);
    useEffect(() => {
        if (!richiesta || richiesta.errore || !richiesta.id) return undefined;
        const st = richiesta.stato?.status;
        if (st === 'DONE' || st === 'ERROR') return undefined;
        let vivo = true;
        const id = setInterval(() => {
            leggiEsitoBot(richiesta.id)
                .then(stato => { if (vivo) setRichiesta(r => (r && r.id === richiesta.id ? { ...r, stato } : r)); })
                .catch((e: unknown) => {
                    if (vivo) setRichiesta(r => (r ? { ...r, errore: e instanceof Error ? e.message : String(e) } : r));
                });
        }, RILETTURA_ESITO_MS);
        return () => { vivo = false; clearInterval(id); };
    }, [richiesta]);
    const invia = useCallback((eventId: string, bot: string, scenario: string, opzioni: OpzioniApplica = {}) => {
        if (!eventId) return;
        const inviato = { eventId, bot, scenario, opzioni };
        // 07/10 sera: la richiesta e' «in corso» SUBITO (prima della risposta
        // della RPC): un secondo clic non parte in parallelo ma si accoda
        setRichiesta({ id: '', stato: { status: 'PENDING', error_detail: null, esito: null }, inviataMs: Date.now(), inviato });
        richiediApplicaBot(eventId, bot, scenario, opzioni)
            .then(id => setRichiesta({ id, stato: { status: 'PENDING', error_detail: null, esito: null }, inviataMs: Date.now(), inviato }))
            .catch((e: unknown) => setRichiesta({ id: '', stato: null, errore: e instanceof Error ? e.message : String(e), inviato }));
    }, []);
    const azzera = useCallback(() => setRichiesta(null), []);
    const st = richiesta?.stato?.status;
    const esito = st === 'DONE' ? (richiesta?.stato?.esito ?? null) : null;
    return {
        richiesta,
        esito,
        righe: esito?.righe ?? [],
        inCorso: !richiesta?.errore && (st === 'PENDING' || st === 'RUNNING'),
        inviato: richiesta?.inviato?.opzioni ?? null,
        invia,
        azzera,
    };
}
