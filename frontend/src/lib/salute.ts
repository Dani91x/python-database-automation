// ============================================================================
// salute.ts - dati e regole PURE della pagina "Salute" (T0A, 09/10/2026).
//
// La pagina legge UNA RPC ogni 10 s sul client Supabase che l'app ha gia'
// (`monitor_salute_stato`, migrazione `migrations/monitor_metrics_2026-10-09.sql`)
// e la vitalita' dei raccoglitori ogni 5 minuti (`monitor_vitalita_raccoglitori`).
// Nessun canale nuovo, nessuna connessione nuova.
//
// Le righe le scrive `Betfair/monitor/` (una ogni 30 s per servizio, solo con
// MONITOR_SALUTE=1). Le soglie sono gli OBIETTIVI PROVVISORI della scheda I par. 7
// (stessi numeri di `Betfair/monitor/referto.py::OBIETTIVI`: un test li confronta).
// Calcio e tennis non si mischiano: ogni riga porta lo sport del servizio.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

/** Obiettivi provvisori (I par. 7, 04 par. 7 L15-L19): da confermare a fine baseline. */
export const OBIETTIVI = {
    cpu_servizio_p95_pct: 30,
    cpu_app_media_pct: 100,
    rss_crescita_pct: 5,
    db_bot_al_minuto: 60,
    orologio_ms: 100,
    transazioni_ora: 5000,
} as const;

/** Una riga e' "viva" se piu' giovane di 90 s (tre righe perse = in ritardo, 5 min = muta). */
export const RIGA_VIVA_S = 90;
export const RIGA_MUTA_S = 300;

export interface Riassunto {
    n: number;
    somma: number;
    min: number | null;
    max: number | null;
    p50: number | null;
    p99: number | null;
    secchi: number[];
}

export interface Metriche {
    v: number;
    finestra_s: number;
    processo?: Record<string, unknown>;
    contatori?: Record<string, Record<string, number>>;
    tratti?: Record<string, Riassunto>;
    valori?: Record<string, Record<string, unknown>>;
    sistema?: Record<string, unknown>;
}

/** Stesse colonne di `monitor_metrics` (senza id/creato_at, che la RPC non usa qui). */
export interface RigaSalute {
    servizio: string;
    sport: string | null;
    ts: string;
    pid: number;
    host: string | null;
    avvio_ts: string | null;
    uptime_s: number | null;
    cpu_pct: number | null;
    rss_mb: number | null;
    db_richieste: number;
    rest_richieste: number;
    metriche: Metriche;
}

export interface SerieSalute {
    servizio: string;
    t: string;
    cpu_media: number | null;
    cpu_max: number | null;
    rss_max: number | null;
    db_richieste: number;
    rest_richieste: number;
    righe: number;
}

export interface StatoSalute {
    adesso: string;
    ore: number;
    ultimi: RigaSalute[];
    serie: SerieSalute[];
    sistema: { servizio: string; ts: string; sistema: Record<string, unknown> | null }[];
}

export interface Raccoglitore {
    tabella: string;
    colonna: string;
    max: string | null;
    eta_ore?: number | null;
    errore?: string;
}

export type Semaforo = 'vivo' | 'ritardo' | 'muto';

/** Stato di un servizio dall'eta' della sua ultima riga. */
export function semaforo(ts: string | null | undefined, adessoMs: number): Semaforo {
    const ms = ts ? Date.parse(ts) : NaN;
    if (!Number.isFinite(ms)) return 'muto';
    const eta = (adessoMs - ms) / 1000;
    if (eta <= RIGA_VIVA_S) return 'vivo';
    if (eta <= RIGA_MUTA_S) return 'ritardo';
    return 'muto';
}

function finestraMin(r: RigaSalute): number | null {
    const f = Number(r.metriche?.finestra_s);
    return Number.isFinite(f) && f > 0 ? f / 60 : null;
}

/** Richieste al minuto nell'ultima finestra (DB o REST Betfair). */
export function alMinuto(r: RigaSalute, quale: 'db' | 'rest'): number | null {
    const m = finestraMin(r);
    if (m === null) return null;
    const n = quale === 'db' ? r.db_richieste : r.rest_richieste;
    return Number.isFinite(Number(n)) ? Number(n) / m : null;
}

function somma(d: Record<string, number> | undefined): number {
    return Object.values(d ?? {}).reduce((a, b) => a + (Number(b) || 0), 0);
}

export interface TotaliApp {
    servizi: number;
    vivi: number;
    cpu: number | null;
    rssMb: number | null;
    dbAlMinuto: number | null;
    restAlMinuto: number | null;
    erroriLog: number;
    transazioni: number;
    orologioMs: number | null;
}

/** Totali dell'app dall'ULTIMA riga di ogni servizio VIVO (i muti non si sommano). */
export function totali(ultimi: readonly RigaSalute[], adessoMs: number): TotaliApp {
    const vivi = ultimi.filter((r) => semaforo(r.ts, adessoMs) !== 'muto');
    const sommaDi = (f: (r: RigaSalute) => number | null): number | null => {
        const v = vivi.map(f).filter((x): x is number => x !== null && Number.isFinite(x));
        return v.length ? v.reduce((a, b) => a + b, 0) : null;
    };
    let orologio: number | null = null;
    for (const r of vivi) {
        for (const [k, t] of Object.entries(r.metriche?.tratti ?? {})) {
            if (k.startsWith('feed_rx_pt_ms.') && t && t.min !== null && Number.isFinite(Number(t.min))) {
                orologio = orologio === null ? Number(t.min) : Math.min(orologio, Number(t.min));
            }
        }
    }
    return {
        servizi: ultimi.length,
        vivi: ultimi.filter((r) => semaforo(r.ts, adessoMs) === 'vivo').length,
        cpu: sommaDi((r) => (r.cpu_pct == null ? null : Number(r.cpu_pct))),
        rssMb: sommaDi((r) => (r.rss_mb == null ? null : Number(r.rss_mb))),
        dbAlMinuto: sommaDi((r) => alMinuto(r, 'db')),
        restAlMinuto: sommaDi((r) => alMinuto(r, 'rest')),
        erroriLog: vivi.reduce((a, r) => a + somma(r.metriche?.contatori?.log_errori), 0),
        transazioni: vivi.reduce((a, r) => a + somma(r.metriche?.contatori?.transazioni), 0),
        orologioMs: orologio,
    };
}

/** Che cosa misura ogni tratto (stessi nomi di `Betfair/monitor/referto.py`). */
export const TRATTI: readonly { prefisso: string; testo: string }[] = [
    { prefisso: 'feed_rx_pt_ms.', testo: 'L1 Betfair pt -> ricezione (include lo scarto dell\'orologio)' },
    { prefisso: 'ladder_pub_pt_ms', testo: 'L3 pt -> ladder pubblicato sul canale' },
    { prefisso: 'canale_coda_ms', testo: 'L6 attesa in coda del canale' },
    { prefisso: 'diario_fsync_ms', testo: 'L6b diario write-ahead (flush + fsync)' },
    { prefisso: 'betfair_place_ms', testo: 'L7 placeOrders -> risposta' },
    { prefisso: 'betfair_replace_ms', testo: 'L7 replaceOrders -> risposta' },
    { prefisso: 'betfair_cancel_ms', testo: 'cancelOrders -> risposta' },
    { prefisso: 'pacchetto_attesa_ms', testo: 'pacchetto ordini in attesa del pool' },
    { prefisso: 'flumine_latenza_alta_ms', testo: 'book con latenza oltre 2 s' },
    { prefisso: 'db_ms', testo: 'richiesta al DB -> risposta' },
    { prefisso: 'rest_ms.', testo: 'REST Betfair per metodo' },
    { prefisso: 'monitor_giro_ms', testo: 'costo del monitor (fuori dal ciclo)' },
];

export function spiegaTratto(nome: string): string {
    return TRATTI.find((t) => nome.startsWith(t.prefisso))?.testo ?? '';
}

export interface RigaTratto {
    servizio: string;
    nome: string;
    n: number;
    p50: number | null;
    p99: number | null;
    max: number | null;
}

/** I tratti dell'ultima finestra di ogni servizio, nell'ordine di TRATTI. */
export function trattiUltimi(ultimi: readonly RigaSalute[]): RigaTratto[] {
    const out: RigaTratto[] = [];
    const ordine = (nome: string) => {
        const i = TRATTI.findIndex((t) => nome.startsWith(t.prefisso));
        return i < 0 ? TRATTI.length : i;
    };
    for (const r of ultimi) {
        for (const [nome, t] of Object.entries(r.metriche?.tratti ?? {})) {
            if (!t || !(Number(t.n) > 0)) continue;
            out.push({ servizio: r.servizio, nome, n: Number(t.n), p50: t.p50, p99: t.p99, max: t.max });
        }
    }
    return out.sort((a, b) => ordine(a.nome) - ordine(b.nome) || a.nome.localeCompare(b.nome)
        || a.servizio.localeCompare(b.servizio));
}

/** Versione di Electron e di Chromium dall'user agent (il renderer non vede Node). */
export function versioniDesktop(userAgent: string | null | undefined): { electron: string | null; chrome: string | null } {
    const ua = String(userAgent ?? '');
    const e = /Electron\/([\d.]+)/.exec(ua);
    const c = /Chrome\/([\d.]+)/.exec(ua);
    return { electron: e ? e[1] : null, chrome: c ? c[1] : null };
}

function comeStato(d: unknown): StatoSalute | null {
    if (!d || typeof d !== 'object') return null;
    const o = d as Partial<StatoSalute>;
    if (!Array.isArray(o.ultimi)) return null;
    return {
        adesso: String(o.adesso ?? ''),
        ore: Number(o.ore ?? 0),
        ultimi: o.ultimi as RigaSalute[],
        serie: Array.isArray(o.serie) ? (o.serie as SerieSalute[]) : [],
        sistema: Array.isArray(o.sistema) ? (o.sistema as StatoSalute['sistema']) : [],
    };
}

/** UNA chiamata: ultima riga per servizio + serie a 5 minuti delle ultime `ore`. */
export async function leggiStatoSalute(ore = 6): Promise<{ stato: StatoSalute | null; errore: string | null }> {
    const { data, error } = await supabase.rpc('monitor_salute_stato', { p_ore: ore });
    if (error) return { stato: null, errore: error.message };
    return { stato: comeStato(data), errore: null };
}

export async function leggiRaccoglitori(): Promise<{ tabelle: Raccoglitore[]; errore: string | null }> {
    const { data, error } = await supabase.rpc('monitor_vitalita_raccoglitori');
    if (error) return { tabelle: [], errore: error.message };
    const t = (data as { tabelle?: unknown } | null)?.tabelle;
    return { tabelle: Array.isArray(t) ? (t as Raccoglitore[]) : [], errore: null };
}
