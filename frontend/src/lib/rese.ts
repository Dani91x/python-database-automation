// ============================================================================
// rese.ts - resa a video dei casi limite della Dashboard (FIX-B, 26/09/2026, KO11).
//
// Reperti della fase 3 (AUDIT_2026-09-25/E2E_FASE3_PAGINE_SESSIONE_B_2026-09-26.md §1.1):
//   U0022 gol previsti NULL resi "0"        -> "—" (un dato assente non e' uno zero)
//   U0026 played=0 reso "NaN per match"      -> "—"
//   U0029 minuti NULL resi 0 nel grafico     -> barra assente + avviso se tutti NULL
//   U0056 date ISO UTC grezze (Studio Ritardi) -> data di Roma gg/mm/aaaa
//   U0011 partite del giorno dopo a "00:00" senza data -> "27/09 00:00"
// Funzioni PURE, fuso Europe/Rome (lo stesso di lib/format.ts).
// ============================================================================
import { DASH } from './format';

const TZ = 'Europe/Rome';

/** gol previsti dall'API ("-2.5", "1.5", ...): NULL/vuoto -> "—", mai "0" */
export function golPrevisto(v: string | number | null | undefined): string {
    if (v === null || v === undefined) return DASH;
    const s = String(v).trim();
    return s === '' ? DASH : s;
}

/** media per partita con 1 decimale; partite 0/NULL o valori non finiti -> "—" (mai NaN) */
export function mediaPerPartita(totale: number | null | undefined, partite: number | null | undefined): string {
    if (totale === null || totale === undefined || partite === null || partite === undefined) return DASH;
    if (!(partite > 0)) return DASH;
    const m = totale / partite;
    return Number.isFinite(m) ? m.toFixed(1) : DASH;
}

export const FASCE_MINUTI = ['0-15', '16-30', '31-45', '46-60', '61-75', '76-90', '91-105', '106-120'] as const;

export interface PuntoMinuti { range: string; count: number | null }

/** serie del grafico "Goals by Minute": il NULL resta NULL (barra assente), non 0 */
export function serieMinuti(minute: Record<string, { total: number | null } | undefined> | null | undefined): PuntoMinuti[] {
    return FASCE_MINUTI.map(range => {
        const t = minute?.[range]?.total;
        return { range, count: typeof t === 'number' && Number.isFinite(t) ? t : null };
    });
}

/** true se nessuna fascia ha un numero: il grafico non va disegnato come "tutti zero" */
export function minutiTuttiAssenti(serie: PuntoMinuti[]): boolean {
    return serie.every(p => p.count === null);
}

function parti(d: Date): { y: string; m: string; g: string; hh: string; mm: string } | null {
    try {
        const f = new Intl.DateTimeFormat('it-IT', {
            timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
        }).formatToParts(d);
        const get = (t: string) => f.find(p => p.type === t)?.value ?? '';
        const hh = get('hour') === '24' ? '00' : get('hour');
        return { y: get('year'), m: get('month'), g: get('day'), hh, mm: get('minute') };
    } catch {
        return null;
    }
}

function aData(iso: string | number | Date | null | undefined): Date | null {
    if (iso === null || iso === undefined || iso === '') return null;
    const d = iso instanceof Date ? iso : new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
}

/** data di Roma "gg/mm/aaaa"; NULL/invalida -> "—" */
export function fmtDataRoma(iso: string | number | Date | null | undefined): string {
    const d = aData(iso);
    const p = d && parti(d);
    return p ? `${p.g}/${p.m}/${p.y}` : DASH;
}

/** giorno di calendario di Roma "aaaa-mm-gg" (chiave per raggruppare); NULL -> null */
export function giornoRoma(iso: string | number | Date | null | undefined): string | null {
    const d = aData(iso);
    const p = d && parti(d);
    return p ? `${p.y}-${p.m}-${p.g}` : null;
}

/**
 * Orario di una partita nella lista del giorno: "HH:MM" se cade nel giorno di Roma
 * `oggi` ("aaaa-mm-gg"), altrimenti "gg/mm HH:MM" (la partita e' di un altro giorno).
 */
export function orarioPartita(iso: string | number | Date | null | undefined, oggi: string): string {
    const d = aData(iso);
    const p = d && parti(d);
    if (!p) return DASH;
    const giorno = `${p.y}-${p.m}-${p.g}`;
    return giorno === oggi ? `${p.hh}:${p.mm}` : `${p.g}/${p.m} ${p.hh}:${p.mm}`;
}
