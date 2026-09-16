// ============================================================================
// omegaProposte.ts — LE USCITE DI OMEGA DIVENTANO PROPOSTE.
//
// Ordine dell'utente (16/09 sera): «il green-up/cash-out passa dalla Control
// Room come proposta con avviso e decido io».
//
// LA MEMORIA CHE QUESTO FILE ONORA (12/09): tutte e cinque le chiusure
// automatiche di Omega v2 erano sbagliate — −42,39 € contro +79,95 € fatti
// dalle aperture. Su un lay la liability è GIÀ impegnata: chiudere non riduce
// il rischio preso, lo trasforma in perdita certa. Da qui in poi quella
// decisione la prende una persona, con i numeri davanti.
//
// NON È UN MODELLO NUOVO: è lo STESSO della Safe (`controlRoomProposte.ts`) —
// una riga `proposed` su una coda di richieste, che nessun worker drena finché
// un essere umano non la promuove a `pending`. Le due schede si somigliano
// apposta: due modi diversi di approvare la stessa cosa sarebbero due modi di
// sbagliarla.
//
// REGOLA CONDIVISA: **la proposta conserva la FOTOGRAFIA, la scheda mostra il
// prezzo VIVO.** `price_at_decision` dice su cosa il bot ha deciso; su cosa si
// piazza lo guarda l'utente un istante prima, dal feed.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

/** Il payload che il servizio scrive (`omega_v3.PropostaUscita` + l'identità
 *  della gamba). I nomi sono quelli della migrazione, campo per campo. */
export interface PropostaUscitaOmegaPayload {
    trade_id: number;
    event_id: string;
    event_name?: string | null;
    market_id?: string | null;
    market_type?: string | null;
    selection_id?: number | null;
    selection_name?: string | null;
    /** lato dell'ordine di CHIUSURA ('back' su un lay aperto) */
    side?: 'back' | 'lay' | null;
    entry_side?: 'back' | 'lay' | null;
    entry_price?: number | null;
    size?: number | null;
    /** FOTOGRAFIA al momento della decisione: NON è il prezzo su cui si piazza */
    price_at_decision?: number | null;
    size_available_at_decision?: number | null;
    /** in CODICE: la traduzione italiana vive in un posto solo, qui sotto */
    motivo_codice?: string | null;
    /** EUR netti, uguali in ogni esito, se si chiude ORA */
    profitto_bloccabile?: number | null;
    /** l'ordine che realizzerebbe quel profitto */
    back_price?: number | null;
    back_size?: number | null;
    /** quanto vale portarla al settlement con la P di adesso */
    ev_tenere?: number | null;
    /** P che il risultato bancato ESCA (modello v3) */
    p_evento?: number | null;
    /** la TRAIETTORIA: se il punteggio regge, quanto si bloccherebbe più avanti */
    meglio_aspettare?: boolean | null;
    bloccabile_max_atteso?: number | null;
    minuto_del_massimo?: number | null;
    minute?: number | null;
    score?: string | null;
    mode?: 'paper' | 'live' | null;
    /** istante della DECISIONE: non si rinfresca mai */
    decided_at?: string | null;
    /** ultimo aggiornamento della proposta */
    proposed_at?: string | null;
}

export interface PropostaUscitaOmega {
    id: number;
    kind: string;
    payload: PropostaUscitaOmegaPayload;
    created_at: string;
    updated_at?: string | null;
}

// ------------------------------------------------------------------- motivi

/**
 * `motivo_codice` → italiano. Sono i sei esiti di `omega_v3.proposta_uscita`:
 * UNO solo propone di chiudere, gli altri cinque dicono perché si TIENE. Una
 * chiave mancante manderebbe sotto gli occhi del trader «tenere_vale_di_piu».
 */
const MOTIVO_IT: Record<string, string> = {
    blocca_il_profitto: 'chiudere adesso blocca il profitto: vale più che tenere e più che aspettare',
    tenere_vale_di_piu: 'tenere vale di più che chiudere adesso',
    aspettare_vale_di_piu: 'se il punteggio regge, più avanti si bloccherebbe di più',
    bloccabile_non_positivo: 'chiudere adesso non porta a casa niente',
    controparte_insufficiente: 'non c’è abbastanza controparte per chiudere per intero',
    nessun_prezzo_di_back: 'nessun prezzo di back: non c’è niente da bloccare',
};

export function motivoUscitaOmegaLabel(codice: string | null | undefined): string | null {
    const k = codice != null ? String(codice).trim().toLowerCase() : '';
    if (!k) return null;
    return MOTIVO_IT[k] ?? k.replace(/_/g, ' ');
}

// -------------------------------------------------------------- il giudizio

/**
 * PERCHÉ non si può approvare adesso; `null` = si può.
 *
 * Fail-closed come la Safe: senza il profitto bloccabile e senza l'ordine che
 * lo realizza non si manda niente a Betfair. E una proposta che il servizio
 * stesso NON propone (`motivo_codice` diverso da `blocca_il_profitto`) resta
 * leggibile ma non approvabile: il bottone direbbe «chiudi» su una cosa che il
 * bot ha deciso di tenere.
 */
export function motivoNonApprovabileOmega(p: PropostaUscitaOmegaPayload): string | null {
    const back = Number(p.back_price);
    const size = Number(p.back_size);
    if (String(p.motivo_codice ?? '') !== 'blocca_il_profitto') {
        return `il servizio non propone di chiudere: ${motivoUscitaOmegaLabel(p.motivo_codice) ?? 'motivo non dichiarato'}`;
    }
    if (!Number.isFinite(back) || back <= 1) {
        return 'prezzo di back non disponibile: non si piazza al buio';
    }
    if (!Number.isFinite(size) || size <= 0) {
        return 'importo di chiusura non disponibile: non si piazza al buio';
    }
    if (p.profitto_bloccabile == null || !Number.isFinite(Number(p.profitto_bloccabile))) {
        return 'profitto bloccabile non dichiarato dal servizio';
    }
    return null;
}

/** Le proposte in cui chiudere conviene davvero, prima. A parità, la più vecchia. */
export function ordinaProposteOmega(
    p: readonly PropostaUscitaOmega[],
): PropostaUscitaOmega[] {
    return [...p].sort((a, b) => {
        const pa = a.payload?.motivo_codice === 'blocca_il_profitto' ? 0 : 1;
        const pb = b.payload?.motivo_codice === 'blocca_il_profitto' ? 0 : 1;
        if (pa !== pb) return pa - pb;
        return Date.parse(a.created_at) - Date.parse(b.created_at);
    });
}

// --------------------------------------------------------------------- I/O

/** Le proposte vive (`get_omega_proposte`). Nessun worker le drena: esistono
 *  soltanto per essere approvate o ignorate da una persona. */
export async function fetchProposteOmega(): Promise<PropostaUscitaOmega[]> {
    const { data, error } = await supabase.rpc('get_omega_proposte');
    if (error) throw new Error(error.message);
    const rows = Array.isArray(data) ? data : [];
    return rows.map((r) => {
        const o = (r ?? {}) as Record<string, unknown>;
        return {
            id: Number(o.id),
            kind: String(o.kind ?? ''),
            payload: (o.payload ?? {}) as PropostaUscitaOmegaPayload,
            created_at: String(o.created_at ?? ''),
            updated_at: o.updated_at == null ? null : String(o.updated_at),
        };
    }).filter((r) => Number.isFinite(r.id));
}

/**
 * L'esito che le RPC RITORNANO (non sollevano) quando la proposta non è più
 * approvabile: due schede aperte, o il doppio clic. Scartarlo farebbe credere
 * che l'ordine sia partito — è successo sulla Safe, review 15/09.
 */
type EsitoRpc = { ok?: boolean; status?: string; note?: string } | null;

function esigiOk(data: unknown, ripiego: string): void {
    const r = data as EsitoRpc;
    if (!r || r.ok !== true) throw new Error(r?.note?.trim() || ripiego);
}

/** APPROVA: `proposed → pending`. Da lì il percorso è quello di sempre. */
export async function approvaPropostaOmega(id: number): Promise<void> {
    const { data, error } = await supabase.rpc('omega_request_approve', { p_id: id });
    if (error) throw new Error(error.message);
    esigiOk(data, 'la proposta non è più in attesa di approvazione');
}

/** IGNORA: `proposed → rejected`, col motivo. Se la situazione CAMBIA il
 *  servizio ripropone: «torna alla prossima occasione». */
export async function ignoraPropostaOmega(
    id: number, motivo = 'ignorata dall’operatore',
): Promise<void> {
    const { data, error } = await supabase.rpc('omega_request_ignore', { p_id: id, p_reason: motivo });
    if (error) throw new Error(error.message);
    esigiOk(data, 'la proposta non è più in attesa di una decisione');
}

/** Realtime sulla coda di Omega: UN solo canale, come per la Safe. */
export function subscribeProposteOmega(onChange: () => void): () => void {
    const ch = supabase
        .channel('control-room-proposte-omega')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'omega_requests' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(ch); };
}
