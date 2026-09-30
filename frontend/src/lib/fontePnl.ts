/**
 * 30/09 — OGNI CIFRA DICE COS'E' (ordine dell'utente: «IL TRADER DEVE SAPERE
 * COSA STA GUARDANDO E CHE DATI!!! [...] MASSIMA COERENZA»).
 *
 * UNA parola per la stessa cosa in tutte e tre le pagine (Mike, Control Room,
 * Storico). Le fonti del P&L realizzato di Mike sono tre:
 *
 * - `conto`    LIVE regolato da Betfair: il P&L del CONTO sui mercati della
 *              partita, ordini di Mike E dell'utente (righe `utente`), numeri
 *              di `listClearedOrders` (`meta.pnl_fonte === 'betfair'` sulle
 *              righe, `ctx.pnl_conto.fonte === 'betfair'` sulla partita);
 * - `simulato` PAPER: soldi finti, esiti del runner paper;
 * - `stima`    LIVE non (ancora) regolato da Betfair: calcolo del bot.
 *
 * Specchio del backend: `Betfair/mike/regolato_conto.py` (`PNL_FONTE_BETFAIR`,
 * ruolo `utente`) e `service._settle_trades` (`ctx.pnl_conto`).
 */
import { fmtMoney } from '@/lib/format';

export type FontePnl = 'conto' | 'simulato' | 'stima';

/** L'etichetta per esteso: la STESSA frase in ogni pagina. */
export const FONTE_PNL_TESTO: Record<FontePnl, string> = {
    conto: 'P&L del conto Betfair (tutte le operazioni: Mike + utente)',
    simulato: 'simulato (runner paper)',
    stima: 'stima del bot (Betfair non ha ancora regolato)',
};

/** La forma breve, per le pillole e le intestazioni strette. */
export const FONTE_PNL_BREVE: Record<FontePnl, string> = {
    conto: 'conto Betfair',
    simulato: 'simulato',
    stima: 'stima',
};

/** Il ruolo della riga di un ordine dell'UTENTE sui mercati di Mike. */
export const RUOLO_UTENTE = 'utente';
export const RUOLO_UTENTE_TESTO = 'Ordine tuo (non del bot)';

export interface RigaPnl {
    mode?: string | null;
    role?: string | null;
    status?: string | null;
    pnl_betfair?: number | string | null;
    meta?: Record<string, unknown> | null;
}

/** true se la riga e' un ordine dell'utente (non una gamba di Mike). */
export function isRigaUtente(r: RigaPnl): boolean {
    return r.role === RUOLO_UTENTE || (r.meta ?? {})['fonte'] === 'utente';
}

/** La fonte del P&L di UNA riga regolata. */
export function fontePnlRiga(r: RigaPnl): FontePnl {
    if (String(r.mode ?? '').toLowerCase() === 'paper') return 'simulato';
    const f = (r.meta ?? {})['pnl_fonte'];
    if (f === 'betfair' || (r.pnl_betfair != null && r.pnl_betfair !== '')) return 'conto';
    return 'stima';
}

/**
 * La fonte di un INSIEME di righe (una partita, una giornata): `conto` solo se
 * TUTTE le righe regolate con P&L lo sono; basta una stima perche' la cifra sia
 * (in parte) una stima. Paper = simulato. Nessuna riga regolata = null.
 */
export function fontePnlRighe(righe: RigaPnl[]): FontePnl | null {
    const regolate = righe.filter((r) => ['won', 'lost', 'void'].includes(String(r.status ?? '')));
    if (!regolate.length) return null;
    if (regolate.every((r) => String(r.mode ?? '').toLowerCase() === 'paper')) return 'simulato';
    return regolate.every((r) => fontePnlRiga(r) !== 'stima') ? 'conto' : 'stima';
}

/** La fonte del P&L di una PARTITA di Mike (`mike_events`). */
export function fontePnlPartita(ev: { mode?: string | null; ctx?: Record<string, unknown> | null }): FontePnl {
    if (String(ev.mode ?? '').toLowerCase() === 'paper') return 'simulato';
    const pc = (ev.ctx ?? {})['pnl_conto'] as Record<string, unknown> | undefined;
    return pc && pc['fonte'] === 'betfair' ? 'conto' : 'stima';
}

/** «di cui Mike +2,10 € · di cui utente −4,68 €» (vuoto se l'utente non c'e'). */
export function scomposizioneConto(mike: number | null | undefined, utente: number | null | undefined): string {
    const u = Number(utente ?? 0);
    if (!Number.isFinite(u) || Math.abs(u) < 0.005) return '';
    const m = Number(mike ?? 0);
    return `di cui Mike ${fmtMoney(m, { signed: true })} · di cui utente ${fmtMoney(u, { signed: true })}`;
}

/** La scomposizione dalla partita (`ctx.pnl_conto`). */
export function scomposizionePartita(ev: { ctx?: Record<string, unknown> | null }): string {
    const pc = (ev.ctx ?? {})['pnl_conto'] as Record<string, unknown> | undefined;
    if (!pc || pc['fonte'] !== 'betfair') return '';
    return scomposizioneConto(Number(pc['mike']), Number(pc['utente']));
}

/** Somma di Mike e dell'utente su un insieme di righe regolate. */
export function sommaPerChi(righe: Array<RigaPnl & { pnl?: number | string | null }>): { mike: number; utente: number } {
    let mike = 0;
    let utente = 0;
    for (const r of righe) {
        if (!['won', 'lost', 'void'].includes(String(r.status ?? ''))) continue;
        const v = Number(r.pnl ?? 0);
        if (!Number.isFinite(v)) continue;
        if (isRigaUtente(r)) utente += v; else mike += v;
    }
    return { mike: Math.round(mike * 100) / 100, utente: Math.round(utente * 100) / 100 };
}
