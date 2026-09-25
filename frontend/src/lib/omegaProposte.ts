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
    /** quanto è impegnato su questa gamba (con stake fisso 1 €: quota − 1) */
    liability?: number | null;
    /** da dove viene la P (catena λ del servizio): è un codice, non una frase */
    p_fonte?: string | null;
    /** il tetto di rischio scattato, quando il motivo è `cap` */
    cap_scattato?: string | null;
    /** perché la proposta si ripresenta dopo che l'avevi ignorata */
    riproposta_perche?: string | null;
    /** l'istante della firma: lo aggiunge la RPC `omega_request_approve` */
    approved_at?: string | null;
    minute?: number | null;
    score?: string | null;
    mode?: 'paper' | 'live' | null;
    /** istante della DECISIONE: non si rinfresca mai */
    decided_at?: string | null;
    /** ultimo aggiornamento della proposta */
    proposed_at?: string | null;
    /** 24/09 — gli ingredienti del ricalcolo al prezzo di adesso
     *  (`omega_proposte._ingredienti_del_payload`) */
    commissione?: number | null;
    margine_attesa?: number | null;
    max_attesa?: number | null;
    p_lose_max?: number | null;
    /** 24/09 — la valutazione del servizio: `valida=false` = il bot non la
     *  proporrebbe piu' (la scheda resta, decide l'utente) */
    valutazione?: { valida?: boolean | null; motivo_codice?: string | null;
        testo?: string | null; valutata_at?: string | null; dal?: string | null } | null;
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
    // 17/09 — LE PROPOSTE CHE NON SONO UN AFFARE (ordine dell'utente: la scheda
    // vale «SIA IN PROFIT CHE IN LOSS»). Qui il bot non offre un guadagno: chiede
    // di ridurre il rischio, e il testo deve dirlo senza ambiguità.
    protezione: 'chiudere adesso costa, ma tenere costa di più: si blocca la perdita minore',
    cap: 'un tetto di rischio è scattato: il bot chiede di ridurre l’esposizione',
    rischio: 'il rischio che il risultato bancato esca ha superato la soglia che hai messo',
};

/** I motivi con cui il servizio PROPONE di chiudere (gli altri dicono perché si tiene). */
const MOTIVI_CHE_PROPONGONO = new Set(['blocca_il_profitto', 'protezione', 'cap', 'rischio']);

/** Una proposta che NON è un guadagno: la scheda la deve gridare, non colorarla di verde. */
export function eUnaProtezioneOmega(p: PropostaUscitaOmegaPayload): boolean {
    const codice = String(p.motivo_codice ?? '');
    if (codice === 'protezione' || codice === 'cap' || codice === 'rischio') return true;
    const bloccabile = Number(p.profitto_bloccabile);
    return Number.isFinite(bloccabile) && bloccabile < 0;
}

export function motivoUscitaOmegaLabel(codice: string | null | undefined): string | null {
    const k = codice != null ? String(codice).trim().toLowerCase() : '';
    if (!k) return null;
    return MOTIVO_IT[k] ?? k.replace(/_/g, ' ');
}

// -------------------------------------------------------------- il giudizio

/**
 * 24/09 — ORDINE DELL'UTENTE («me lo segnala e decido io»): da oggi il testo
 * che torna e' un AVVISO della scheda, non un blocco (`SchedaChiusuraOmega`
 * lascia il bottone acceso).
 *
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
    if (!MOTIVI_CHE_PROPONGONO.has(String(p.motivo_codice ?? ''))) {
        return `il servizio non propone di chiudere: ${motivoUscitaOmegaLabel(p.motivo_codice) ?? 'motivo non dichiarato'}`;
    }
    if (!Number.isFinite(back) || back <= 1) {
        return 'prezzo di back non disponibile nella proposta: guarda il prezzo di adesso';
    }
    if (!Number.isFinite(size) || size <= 0) {
        return 'importo di chiusura non disponibile nella proposta';
    }
    // ⚠️ il numero può essere NEGATIVO: è una perdita che si blocca, ed è una
    // proposta legittima (protezione / cap). Si pretende che ci SIA, non che sia
    // positivo — pretenderlo positivo renderebbe non approvabile proprio la
    // proposta che l'utente ha chiesto il 17/09.
    if (p.profitto_bloccabile == null || !Number.isFinite(Number(p.profitto_bloccabile))) {
        return 'risultato bloccabile non dichiarato dal servizio';
    }
    return null;
}

// ------------------------------------------------- l'uscita AL PREZZO DI ADESSO

/**
 * 24/09 — ORDINE DELL'UTENTE: «tutti i valori e i calcoli devono aggiornarsi al
 * cambiare del prezzo; la scheda deve segnalarmi se c'è ancora o no, decido io».
 *
 * PORTA TypeScript di `Betfair/omega/omega_proposte.py:esito_uscita_al_prezzo`,
 * cioè la decisione di `omega_v3.proposta_uscita` (e il bloccabile di
 * `omega_v3.profitto_bloccabile`) al prezzo di back di ADESSO, con gli
 * ingredienti che NON dipendono dal prezzo scritti dal servizio nel payload
 * (`ev_tenere`, `max_attesa`, `p_evento`, `commissione`, `margine_attesa`,
 * `p_lose_max`, `cap_scattato`). Legata al Python dal file d'oro
 * `omegaUscita.golden.json` (`python -m Betfair.omega.tools.genera_oro_uscita`).
 */
export interface EsitoUscitaAlPrezzo {
    profitto: number | null;
    back_price: number | null;
    back_stake: number | null;
    attuabile: boolean;
    meglio_aspettare: boolean;
    proponi: boolean;
    motivo_codice: string;
}

/** `float(v)` di Python su un campo del payload: numeri e stringhe numeriche;
 *  `finito` = rifiuta anche nan/inf e i booleani (come `_fin`). */
function numeroPy(v: unknown, finito: boolean): number | null {
    if (v == null || typeof v === 'boolean') return finito || v == null ? null : Number(v);
    const x = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
    if (Number.isNaN(x) && typeof v !== 'number') return null;
    if (finito && !Number.isFinite(x)) return null;
    return x;
}

function arrotondaPy(x: number, cifre: number): number {
    const f = 10 ** cifre;
    return Math.round(x * f) / f;
}

export function esitoUscitaAlPrezzo(a: {
    lay_price: unknown; size: unknown; back_price: unknown; back_size: unknown;
    ev_tenere: unknown; max_attesa: unknown; p_evento: unknown;
    commissione: unknown; margine_attesa: unknown;
    cap_scattato?: string | null; p_lose_max?: unknown;
}): EsitoUscitaAlPrezzo {
    const out: EsitoUscitaAlPrezzo = {
        profitto: null, back_price: null, back_stake: null, attuabile: false,
        meglio_aspettare: false, proponi: false, motivo_codice: 'posizione_senza_numeri',
    };
    const lay = numeroPy(a.lay_price, true);
    const s = numeroPy(a.size, true);
    const evH = numeroPy(a.ev_tenere, true);
    const pe = numeroPy(a.p_evento, true);
    const comm = numeroPy(a.commissione, true);
    const marg = numeroPy(a.margine_attesa, true);
    if (lay == null || s == null || lay <= 1 || s <= 0 || evH == null || pe == null
        || comm == null || marg == null) return out;
    // --- omega_v3.profitto_bloccabile ---
    const B = numeroPy(a.back_price, false);
    if (B == null || !Number.isFinite(B) || B <= 1) {
        out.motivo_codice = 'nessun_prezzo_di_back';
        return out;
    }
    const sb = s * lay / B;
    const lordo = s - sb;
    const c = Math.max(0, Math.min(0.5, comm));
    const profitto = arrotondaPy(lordo > 0 ? lordo * (1 - c) : lordo, 4);
    const disponibile = numeroPy(a.back_size, false) ?? 0;
    const attuabile = disponibile >= sb - 1e-9;
    // --- omega_v3.proposta_uscita, ramo per ramo ---
    const ma = numeroPy(a.max_attesa, false);
    const meglio = ma != null && ma > profitto + marg;
    out.profitto = profitto;
    out.back_price = B;
    out.back_stake = arrotondaPy(sb, 2);
    out.attuabile = attuabile;
    out.meglio_aspettare = meglio;
    const plm = numeroPy(a.p_lose_max, false) || 0;
    let motivo: string;
    let proponi: boolean;
    if (!attuabile) { motivo = 'controparte_insufficiente'; proponi = false; }
    else if (a.cap_scattato) { motivo = 'cap'; proponi = true; }
    else if (plm > 0 && pe > plm) { motivo = 'rischio'; proponi = true; }
    else if (profitto <= 0) {
        if (evH < profitto) { motivo = 'protezione'; proponi = true; }
        else { motivo = 'bloccabile_non_positivo'; proponi = false; }
    } else if (profitto < evH) { motivo = 'tenere_vale_di_piu'; proponi = false; }
    else if (meglio) { motivo = 'aspettare_vale_di_piu'; proponi = false; }
    else { motivo = 'blocca_il_profitto'; proponi = true; }
    out.motivo_codice = motivo;
    out.proponi = proponi;
    return out;
}

/**
 * Prima quello che URGE, poi quello che conviene, poi il resto. A parità, la più
 * vecchia. Una protezione (o un cap) davanti a un green-up: non approvare una
 * protezione COSTA, non approvare un profitto no.
 */
function priorita(p: PropostaUscitaOmegaPayload | undefined): number {
    const codice = String(p?.motivo_codice ?? '');
    if (codice === 'cap' || codice === 'protezione' || codice === 'rischio') return 0;
    if (codice === 'blocca_il_profitto') return 1;
    return 2;
}

export function ordinaProposteOmega(
    p: readonly PropostaUscitaOmega[],
): PropostaUscitaOmega[] {
    return [...p].sort((a, b) => {
        const pa = priorita(a.payload), pb = priorita(b.payload);
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
export async function approvaPropostaOmega(
    id: number,
    opts?: {
        /** B17 (25/09) — il prezzo di BACK a video al clic */
        prezzoVisto?: number | null;
        /** eta', fonte, `prezzo_vivo_assente`, istante del clic, prezzo del segnale */
        contesto?: Record<string, unknown> | object | null;
    },
): Promise<void> {
    // B17 (25/09) — i due parametri nuovi SOLO se ci sono: senza, la chiamata
    // e' identica a prima (firma `omega_request_approve(bigint)`). Con, serve
    // la migrazione `omega_request_approve_contesto_2026-09-25.sql` (il
    // chiamante ripiega sul solo p_id su PGRST202).
    const params: Record<string, unknown> = { p_id: id };
    if (typeof opts?.prezzoVisto === 'number' && Number.isFinite(opts.prezzoVisto) && opts.prezzoVisto > 1) {
        params.p_price = opts.prezzoVisto;
    }
    if (opts?.contesto && typeof opts.contesto === 'object') params.p_contesto = opts.contesto;
    const { data, error } = await supabase.rpc('omega_request_approve', params as never);
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

/**
 * Realtime sulla coda di Omega: UN solo canale, come per la Safe.
 *
 * ⚠️ REPERTO O-1 (17/09): la tabella è `omega_manual_requests`, la coda che il
 * servizio DRENA davvero (`omega_db.pending_manual_requests`). La migrazione del
 * 16/09 ne aveva creata una seconda (`omega_requests`) che nessun worker legge:
 * una proposta approvata lì sarebbe rimasta ferma per sempre, e il trader
 * avrebbe visto «fatto» su una posizione ancora aperta. Una coda sola.
 * (`migrations/omega_proposte_coda_unica_2026-09-17.sql`)
 */
export function subscribeProposteOmega(onChange: () => void): () => void {
    const ch = supabase
        .channel('control-room-proposte-omega')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'omega_manual_requests' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(ch); };
}
