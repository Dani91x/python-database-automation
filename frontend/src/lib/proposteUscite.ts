// ============================================================================
// proposteUscite.ts - LE PROPOSTE D'USCITA DEI BOT DI FLUSSO (28/09, CANTIERE N).
//
// "OGNI BOT, PER ORA, DEVE PASSARE DA ME, IO APPROVO LE USCITE" (utente, 28/09).
//
// I 4 bot tennis e lo scalper calcio, a uscite MANUALI, non chiudono: tengono
// la proposta coi numeri nel loro battito (`stats.uscite_proposte`, chiavi di
// `Betfair/stream/uscite_proposte.proposta_di`). Qui la si legge (PURO: nessuna
// fetch nuova, i dati arrivano con le righe che la Control Room ha gia') e la
// si FIRMA con la RPC owner-only del suo bot
// (`migrations/uscite_approva_bot_flusso_2026-09-28.sql`). L'uscita poi la
// esegue il bot la prossima volta che la strategia la decide ANCORA, sul
// mercato di adesso, entro 120 s.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

/** Una proposta, con i nomi della pagina (dalle chiavi VERE del bot). */
export interface PropostaFlusso {
    chiave: string;
    bot: string;
    motivo: string;
    urgente: boolean;
    eventId: string;
    marketId: string | null;
    selectionId: number | null;
    latoIngresso: string | null;
    prezzo: number | null;
    latoChiusura: string | null;
    sizeChiusura: number | null;
    /** quanto si incassa (+) o si perde (-) chiudendo ORA, spalmato */
    seChiudi: number | null;
    /** se si TIENE: esito se la selezione vince / se perde */
    seVince: number | null;
    sePerde: number | null;
    frazione: number | null;
    /** secondi epoch della decisione (fermo finche' la proposta vive) */
    decidedAt: number | null;
}

/** Le parole del motivo (una sola tabella per tutti i bot di flusso). */
export const MOTIVO_TESTO: Record<string, string> = {
    target: 'presa di profitto',
    scaglione: 'presa di profitto parziale',
    green: 'green-up sullo swing',
    stop: 'stop (in perdita)',
    time: 'uscita a tempo',
    timeout: 'uscita a tempo',
    strutturale: 'uscita strutturale (game/set cambiato)',
    scratch: 'chiusura a pari',
};

const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null;
const txt = (v: unknown): string | null =>
    typeof v === 'string' && v.trim() ? v.trim() : null;

/** Da `stats.uscite_proposte` (lista del bot) alle proposte della pagina.
 *  `eventId` di riserva quando la proposta non lo porta (scalper: e' la sessione). */
export function leggiProposteFlusso(grezze: unknown, eventId?: string | null): PropostaFlusso[] {
    if (!Array.isArray(grezze)) return [];
    const out: PropostaFlusso[] = [];
    for (const g of grezze) {
        if (g == null || typeof g !== 'object' || Array.isArray(g)) continue;
        const o = g as Record<string, unknown>;
        const chiave = txt(o.chiave);
        const bot = txt(o.bot) ?? (chiave ? chiave.split('|')[0] : null);
        const ev = txt(o.event_id) ?? (eventId ? String(eventId) : null);
        if (!chiave || !bot || !ev) continue;
        out.push({
            chiave, bot, motivo: txt(o.motivo) ?? '?', urgente: o.urgente === true, eventId: ev,
            marketId: txt(o.market_id), selectionId: num(o.selection_id),
            latoIngresso: txt(o.lato_ingresso), prezzo: num(o.prezzo),
            latoChiusura: txt(o.lato_chiusura), sizeChiusura: num(o.size_chiusura),
            seChiudi: num(o.se_chiudi), seVince: num(o.se_vince), sePerde: num(o.se_perde),
            frazione: num(o.frazione), decidedAt: num(o.decided_at),
        });
    }
    return out;
}

/**
 * LA FIRMA: la RPC del bot giusto, con la chiave della proposta. Nessun ordine
 * parte da qui: la firma arriva al bot al suo battito (3-5 s) e l'uscita parte
 * solo se la strategia la vuole ancora.
 */
export async function approvaPropostaFlusso(p: Pick<PropostaFlusso, 'bot' | 'eventId' | 'chiave'>): Promise<void> {
    // lo scalper calcio E lo sniper (stessa sessione) firmano con la RPC dello
    // scalper: le loro chiavi cominciano con 'scalper|'
    const { error } = p.bot === 'scalper' || p.bot === 'sniper' || p.chiave.startsWith('scalper|')
        ? await supabase.rpc('scalper_approva_uscita', { p_event_id: p.eventId, p_chiave: p.chiave })
        : await supabase.rpc('tennis_bot_approva_uscita', {
            p_event_id: p.eventId, p_bot_key: p.bot, p_chiave: p.chiave,
        });
    if (error) throw new Error(error.message);
}
