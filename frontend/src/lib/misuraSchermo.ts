// ============================================================================
// misuraSchermo.ts - 11/10/2026 (M-2 della mappatura dei flussi): la misura M1
// "messaggio Betfair -> ladder A SCHERMO", tratti c e d, dentro la pagina.
//
// Che cosa misura (solo con il monitor acceso: `monitorSaluteAcceso()`, cioe'
// la build fatta con MONITOR_SALUTE=1; spento = nessuna misura, nessun timer,
// nessun messaggio, nessun campo in piu'):
//   - all'ARRIVO di un push 'ladder' sul canale locale (`localChannel.ts`, un
//     solo punto) si annotano l'istante (performance.now e Date.now) e le marche
//     che il processo ha messo nel payload: `ts_pub_ms` (pubblicazione), `rx_ms`
//     (arrivo nel processo del messaggio Betfair con quel `pt`), `pt`;
//   - il ladder (`LadderView`, un solo hook) dopo il COMMIT della riga chiede un
//     requestAnimationFrame: il suo istante e' l'inizio del frame che dipinge la
//     riga nuova (`useLayoutEffect` + rAF = prima del paint di quel frame).
//   Tratti (ms): pagina_canale_ms (ts_pub_ms -> arrivo), pagina_dipinto_ms
//   (arrivo -> frame), pagina_pub_dipinto_ms (ts_pub_ms -> frame),
//   pagina_rx_dipinto_ms (rx_ms -> frame: M1 sull'orologio del PC, senza lo
//   scarto con Betfair), pagina_pt_dipinto_ms (pt -> frame: orologi diversi).
//   Python e pagina leggono lo STESSO orologio di sistema (Date.now / time.time);
//   gli intervalli dentro la pagina usano performance.now (monotono).
//
// Dove vanno: ogni 30 s un RIASSUNTO per sport (istogramma a secchi fissi, gli
// stessi bordi di Betfair/monitor/registro.py::BORDI_MS: un test li confronta e
// il Python rifiuta un riassunto con bordi diversi) viaggia come richiesta
// `salute` sul canale locale del runner GIA' APERTO (47331 calcio, 47332
// tennis): nessuna connessione nuova, nessuna lettura nuova. Il runner lo fonde
// nella sua riga di `monitor_metrics` (Betfair/monitor/sonde.py::misure_pagina).
//
// Mai un'eccezione verso il chiamante: la misura non rompe il canale ne' il ladder.
// ============================================================================
import { useLayoutEffect } from 'react';
import { monitorSaluteAcceso } from '@/lib/monitorSalute';
import type { LocalResponse, LocalSport, LocalStatus } from '@/lib/localChannel';

/** Bordi superiori dei secchi in ms: IDENTICI a `Betfair/monitor/registro.py::BORDI_MS`. */
export const BORDI_MS: readonly number[] = [
    0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 60000,
];

/** I tratti che il Python accetta (`sonde.TRATTI_PAGINA`). */
export const TRATTI_PAGINA = [
    'pagina_canale_ms', 'pagina_dipinto_ms', 'pagina_pub_dipinto_ms',
    'pagina_rx_dipinto_ms', 'pagina_pt_dipinto_ms',
] as const;
export type TrattoPagina = typeof TRATTI_PAGINA[number];

/** Ogni quanto parte il riassunto (stessa finestra della riga di `monitor_metrics`). */
export const INTERVALLO_RIASSUNTO_MS = 30_000;
/** Versione del riassunto (`sonde.VERSIONE_PAGINA`). */
export const VERSIONE_RIASSUNTO = 1;
/** Mercati con un push in attesa di essere dipinto, al massimo (memoria limitata). */
export const MAX_ARRIVI = 500;

/** Il minimo del LocalChannel che serve qui (iniettabile nei test). */
export interface CanaleMisura {
    readonly sport: LocalSport;
    getStatus(): LocalStatus;
    request(method: string, params: Record<string, unknown>): Promise<LocalResponse>;
}

interface Istogramma { n: number; somma: number; min: number | null; max: number | null; secchi: number[] }

interface Arrivo {
    sport: LocalSport;
    perf: number;
    wall: number;
    tsPub: number | null;
    rx: number | null;
    pt: number | null;
}

interface DatiSport {
    canale: CanaleMisura;
    tratti: Map<TrattoPagina, Istogramma>;
    contatori: { push_ladder: number; dipinti: number };
}

/** Orologi (sostituibili nei test). */
const orologi = {
    perf: (): number => (typeof performance !== 'undefined' ? performance.now() : Date.now()),
    wall: (): number => Date.now(),
};

const arrivi = new Map<string, Arrivo>();
const perSport = new Map<LocalSport, DatiSport>();
let timer: ReturnType<typeof setInterval> | null = null;

const numero = (v: unknown): number | null =>
    (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null);

function nuovoIstogramma(): Istogramma {
    return { n: 0, somma: 0, min: null, max: null, secchi: new Array(BORDI_MS.length + 1).fill(0) };
}

/** Indice del secchio: il primo bordo >= v (come `bisect.bisect_left` del Python). */
export function secchioDi(v: number): number {
    let lo = 0;
    let hi = BORDI_MS.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (BORDI_MS[mid] < v) lo = mid + 1; else hi = mid;
    }
    return lo;
}

function aggiungi(h: Istogramma, v: number): void {
    h.n += 1;
    h.somma += v;
    h.min = h.min == null || v < h.min ? v : h.min;
    h.max = h.max == null || v > h.max ? v : h.max;
    h.secchi[secchioDi(v)] += 1;
}

function datiDi(canale: CanaleMisura): DatiSport {
    let d = perSport.get(canale.sport);
    if (!d) {
        d = { canale, tratti: new Map(), contatori: { push_ladder: 0, dipinti: 0 } };
        perSport.set(canale.sport, d);
    }
    d.canale = canale;
    return d;
}

function registra(d: DatiSport, nome: TrattoPagina, v: number): void {
    if (!Number.isFinite(v)) return;
    let h = d.tratti.get(nome);
    if (!h) { h = nuovoIstogramma(); d.tratti.set(nome, h); }
    aggiungi(h, v);
}

function avviaTimer(): void {
    if (timer != null) return;
    timer = setInterval(() => { inviaRiassunti(); }, INTERVALLO_RIASSUNTO_MS);
}

/** La misura e' accesa? (monitor acceso alla build) */
export function misuraAccesa(): boolean {
    return monitorSaluteAcceso();
}

/**
 * Un push 'ladder' e' arrivato sul canale (chiamata da `LocalChannel` solo a
 * monitor acceso). Annota l'arrivo per il mercato e il tratto canale -> pagina.
 */
export function notaArrivoLadder(canale: CanaleMisura, d: unknown): void {
    try {
        if (!d || typeof d !== 'object') return;
        const m = d as Record<string, unknown>;
        const mid = typeof m.market_id === 'string' ? m.market_id : null;
        if (!mid) return;
        const perf = orologi.perf();
        const wall = orologi.wall();
        const dati = datiDi(canale);
        dati.contatori.push_ladder += 1;
        const tsPub = numero(m.ts_pub_ms);
        if (tsPub != null) registra(dati, 'pagina_canale_ms', wall - tsPub);
        arrivi.delete(mid);   // l'ultimo arrivo va in coda (ordine = eta')
        arrivi.set(mid, { sport: canale.sport, perf, wall, tsPub, rx: numero(m.rx_ms), pt: numero(m.pt) });
        while (arrivi.size > MAX_ARRIVI) {
            const primo = arrivi.keys().next().value;
            if (primo === undefined) break;
            arrivi.delete(primo);
        }
        avviaTimer();
    } catch {
        /* la misura non rompe mai il canale */
    }
}

/**
 * Il frame che dipinge il ladder di `marketId` e' cominciato: chiude l'ultimo
 * arrivo non ancora dipinto di quel mercato (un push = una misura; due push
 * fusi in un solo render contano una volta, l'ultimo).
 */
export function segnaDipinto(marketId: string): void {
    try {
        const a = arrivi.get(marketId);
        if (!a) return;
        arrivi.delete(marketId);
        const d = perSport.get(a.sport);
        if (!d) return;
        const dt = orologi.perf() - a.perf;
        const pixel = a.wall + dt;
        d.contatori.dipinti += 1;
        registra(d, 'pagina_dipinto_ms', dt);
        if (a.tsPub != null) registra(d, 'pagina_pub_dipinto_ms', pixel - a.tsPub);
        if (a.rx != null) registra(d, 'pagina_rx_dipinto_ms', pixel - a.rx);
        if (a.pt != null) registra(d, 'pagina_pt_dipinto_ms', pixel - a.pt);
    } catch {
        /* la misura non rompe mai il ladder */
    }
}

/**
 * Hook del ladder: dopo il commit di una riga nuova chiede UN frame e lo segna.
 * Spento: nessun frame chiesto, nessun effetto.
 */
export function useMisuraDipinto(marketId: string | null | undefined, row: unknown): void {
    useLayoutEffect(() => {
        if (!marketId || row == null || !misuraAccesa()) return undefined;
        if (typeof requestAnimationFrame !== 'function') return undefined;
        const id = requestAnimationFrame(() => { segnaDipinto(marketId); });
        return () => { cancelAnimationFrame(id); };
    }, [marketId, row]);
}

/** Il riassunto da mandare per uno sport (forma di `sonde.misure_pagina`). */
export function riassuntoDi(sport: LocalSport): Record<string, unknown> | null {
    const d = perSport.get(sport);
    if (!d) return null;
    const tratti: Record<string, unknown> = {};
    for (const [nome, h] of d.tratti) {
        tratti[nome] = { n: h.n, somma: h.somma, min: h.min, max: h.max, secchi: [...h.secchi] };
    }
    return { v: VERSIONE_RIASSUNTO, bordi: [...BORDI_MS], tratti, contatori: { ...d.contatori } };
}

/**
 * Manda i riassunti (uno per sport con dati) sul canale gia' aperto e li azzera.
 * Canale giu': il riassunto si scarta (la misura non aspetta). Mai solleva.
 */
export function inviaRiassunti(): number {
    let mandati = 0;
    if (!misuraAccesa()) return 0;
    for (const [sport, d] of [...perSport]) {
        try {
            const p = riassuntoDi(sport);
            perSport.delete(sport);
            if (!p || d.canale.getStatus() !== 'connected') continue;
            d.canale.request('salute', p).catch(() => { /* best-effort */ });
            mandati += 1;
        } catch {
            /* la misura non rompe mai niente */
        }
    }
    return mandati;
}

/** SOLO PER I TEST: azzera stato e timer, e sostituisce gli orologi. */
export function __resetMisuraSchermo(o?: { perf?: () => number; wall?: () => number }): void {
    arrivi.clear();
    perSport.clear();
    if (timer != null) { clearInterval(timer); timer = null; }
    orologi.perf = o?.perf ?? ((): number => (typeof performance !== 'undefined' ? performance.now() : Date.now()));
    orologi.wall = o?.wall ?? ((): number => Date.now());
}

/** SOLO PER I TEST: quanti mercati aspettano il dipinto e se il timer gira. */
export function __statoMisuraSchermo(): { arrivi: number; sport: number; timer: boolean } {
    return { arrivi: arrivi.size, sport: perSport.size, timer: timer != null };
}
