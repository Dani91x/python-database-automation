// ============================================================================
// format.ts — FORMATTER UNICI del design system di trading (Omega/Safe/Mike).
//
// Regola d'oro: sotto gli occhi di un trader i numeri devono avere UNA forma.
// Denaro in formato ITALIANO ("12,50 €", segno davanti), quote con la virgola
// ("2,04"), percentuali con la virgola e lo spazio ("12,5 %"), orari SEMPRE in
// Europe/Rome. Il meno è quello tipografico U+2212 ("−"), non il trattino.
//
// Tutte le funzioni sono PURE e tollerano null/undefined/NaN → "—".
// Nessun import: questo file è la base di tutto il resto.
// ============================================================================

/** meno tipografico (U+2212): l'unico segno negativo ammesso nella UI */
export const MINUS = '−';
/** placeholder unico per "dato assente" */
export const DASH = '—';

const TZ = 'Europe/Rome';

function finite(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

/** numero → stringa italiana con `digits` decimali fissi (virgola decimale). */
function itFixed(n: number, digits: number): string {
    return n.toFixed(digits).replace('.', ',');
}

export interface MoneyOpts {
    /** true = mostra sempre il segno ("+12,50 €"); false = solo il meno */
    signed?: boolean;
    /** decimali (default 2) */
    decimals?: number;
    /** simbolo valuta (default '€'); '' per il numero nudo */
    currency?: string;
}

/**
 * Denaro in formato italiano: `12,50 €` · `+12,50 €` · `−12,50 €`.
 * null/undefined/NaN → "—" (mai "0,00 €": un dato assente non è uno zero).
 */
export function fmtMoney(v: number | null | undefined, opts: MoneyOpts = {}): string {
    const n = finite(v);
    if (n === null) return DASH;
    const decimals = opts.decimals ?? 2;
    const currency = opts.currency ?? '€';
    // -0 va mostrato come 0: il segno meno su zero è rumore
    const neg = n < 0 && Number(Math.abs(n).toFixed(decimals)) !== 0;
    const sign = neg ? MINUS : opts.signed ? '+' : '';
    const body = itFixed(Math.abs(n), decimals);
    return currency ? `${sign}${body} ${currency}` : `${sign}${body}`;
}

/** Quota Betfair: `2,04`. null/NaN → "—". */
export function fmtOdds(v: number | null | undefined): string {
    const n = finite(v);
    return n === null ? DASH : itFixed(n, 2);
}

/**
 * Percentuale: `12,5 %`.
 * ATTENZIONE alla scala: `v` è una FRAZIONE 0–1 (0,125 → "12,5 %").
 * Per un valore già in punti percentuali usa `fmtPctPoints`.
 */
export function fmtPct(v: number | null | undefined, digits = 1): string {
    const n = finite(v);
    return n === null ? DASH : `${itFixed(n * 100, digits)} %`;
}

/** Percentuale da valore GIÀ in punti percentuali: 12,5 → "12,5 %". */
export function fmtPctPoints(v: number | null | undefined, digits = 1): string {
    const n = finite(v);
    return n === null ? DASH : `${itFixed(n, digits)} %`;
}

/** Numero generico in formato italiano con `digits` decimali. */
export function fmtNum(v: number | null | undefined, digits = 0): string {
    const n = finite(v);
    return n === null ? DASH : itFixed(n, digits);
}

/** Tick di prezzo: `2 tick` / `1 tick` / `—`. */
export function fmtTicks(n: number | null | undefined): string {
    const v = finite(n);
    if (v === null) return DASH;
    const abs = Math.abs(Math.round(v));
    return `${abs} tick`;
}

function romeParts(iso: string | number | Date | null | undefined, seconds: boolean): string | null {
    if (iso === null || iso === undefined || iso === '') return null;
    const d = iso instanceof Date ? iso : new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    try {
        return new Intl.DateTimeFormat('it-IT', {
            timeZone: TZ, hour: '2-digit', minute: '2-digit',
            ...(seconds ? { second: '2-digit' } : {}),
            hour12: false,
        }).format(d);
    } catch {
        // ambienti Intl minimi senza timeZone: meglio l'ora locale del "—"
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        const ss = String(d.getSeconds()).padStart(2, '0');
        return seconds ? `${hh}:${mm}:${ss}` : `${hh}:${mm}`;
    }
}

/** Ora dell'orologio di Roma: `18:05` (o `18:05:07` con `{seconds:true}`). */
export function fmtTime(iso: string | number | Date | null | undefined, opts: { seconds?: boolean } = {}): string {
    return romeParts(iso, Boolean(opts.seconds)) ?? DASH;
}

/** Data + ora di Roma: `gio 11 set · 18:05`. */
export function fmtDateTime(iso: string | number | Date | null | undefined): string {
    if (iso === null || iso === undefined || iso === '') return DASH;
    const d = iso instanceof Date ? iso : new Date(iso);
    if (Number.isNaN(d.getTime())) return DASH;
    const time = romeParts(d, false) ?? DASH;
    let day: string;
    try {
        day = new Intl.DateTimeFormat('it-IT', {
            timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short',
        }).format(d).replace(/\./g, '').replace(/,/g, '');
    } catch {
        day = `${d.getDate()}`;
    }
    return `${day} · ${time}`;
}

/** Età di un dato in secondi → `3 s` · `2 min` · `1 h 05`. */
export function fmtAge(sec: number | null | undefined): string {
    const n = finite(sec);
    if (n === null) return DASH;
    const s = Math.max(0, Math.round(n));
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min`;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h} h ${String(m).padStart(2, '0')}`;
}

/** Età in secondi fra due istanti (ms). null se l'istante non è leggibile. */
export function ageSeconds(iso: string | null | undefined, nowMs: number): number | null {
    if (!iso) return null;
    const ms = Date.parse(iso);
    if (!Number.isFinite(ms)) return null;
    return Math.max(0, Math.round((nowMs - ms) / 1000));
}
