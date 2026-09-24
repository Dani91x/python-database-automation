// ============================================================================
// chiuseGiornata.ts - LE CHIUSE DI UNA GIORNATA, lette A RICHIESTA (24/09).
//
// Ordine dell'utente: "Posizioni chiuse / storico: e' LENTISSIMO nel
// caricamento, i dati sono mischiati per giornata". La scheda mostra SUBITO
// la giornata di oggi con le righe gia' in memoria (lettura dei 30 s e canali
// al ms: nessuna attesa) e legge dal database UNA giornata alla volta, solo
// quando serve:
//   - oggi, per completare le catene (una chiusura la cui apertura e' uscita
//     dalla finestra delle 200 righe di Safe, reperto B15, torna intera);
//   - un giorno passato, quando il trader lo sceglie.
// Il risultato si MEMORIZZA per (giornata, modalita'): tornare su un giorno
// gia' visto non rilegge niente. Oggi scade dopo `SCADENZA_OGGI_MS`.
//
// FONTE: la RPC `get_posizioni_chiuse_giornata(p_day, p_mode)` (migrazione
// `migrations/posizioni_chiuse_giornata_2026-09-24.sql`): i cicli con almeno
// una gamba REGOLATA nel giorno (Roma), catene intere, 4 bot tennis inclusi,
// UNA modalita' (obbligatoria). Finche' la migrazione non e' applicata si
// RIPIEGA sulle RPC di storico per bot (`get_*_day_trades`), e il ripiego si
// DICHIARA: niente bot tennis per i giorni passati, catene al primo livello.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import type { Bot, Modo } from '@/lib/controlRoom';
import { isBotTennis } from '@/lib/controlRoom';
import {
    eFirmaMancante, fetchMikeDayTrades, fetchOmegaDayTradesPerModo, fetchSafeDayTrades,
    type DayTrade,
} from '@/lib/dailyHistory';
import type { TennisBotOrderRow } from '@/lib/tennis';
import { rigaDaOrdineTennis, type TradeChiudibile } from '@/lib/posizioniChiuse';

export const RPC_CHIUSE_GIORNATA = 'get_posizioni_chiuse_giornata';

/** quanto resta buona la lettura di OGGI (le altre giornate non scadono) */
export const SCADENZA_OGGI_MS = 60_000;

export interface ChiuseGiornata {
    giorno: string;
    modo: Modo;
    righe: TradeChiudibile[];
    /** `rpc` = lettura completa; `ripiego` = RPC di storico per bot */
    fonte: 'rpc' | 'ripiego';
    /** cio' che il trader deve sapere di questa lettura (ripieghi, cadute) */
    avvisi: string[];
    lettoAlle: number;
}

function comeRighe(v: unknown): Record<string, unknown>[] {
    return Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : [];
}

function marca(righe: readonly Record<string, unknown>[], bot: Bot, sport?: string): TradeChiudibile[] {
    const out: TradeChiudibile[] = [];
    for (const r of righe) {
        if (typeof r.id !== 'number') continue;
        out.push({ ...(r as object), __bot: bot, sport: (r.sport as string) ?? sport } as TradeChiudibile);
    }
    return out;
}

/** Le righe della risposta della RPC, con lo stesso contratto della memoria. */
export function righeDaRisposta(data: unknown): TradeChiudibile[] {
    const d = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
    const tennis: TradeChiudibile[] = [];
    for (const o of comeRighe(d.tennis)) {
        const r = rigaDaOrdineTennis(o as unknown as TennisBotOrderRow, null,
            (b) => isBotTennis(b as Bot));
        if (r) tennis.push(r);
    }
    return [
        ...marca(comeRighe(d.omega), 'omega', 'calcio'),
        ...marca(comeRighe(d.safe), 'safe'),
        ...marca(comeRighe(d.mike), 'mike', 'calcio'),
        ...tennis,
    ];
}

/** Le righe di un giorno dalle RPC di storico: apertura + chiusure appiattite. */
export function righeDaStorico(trades: readonly DayTrade[], bot: Bot, sport?: string): TradeChiudibile[] {
    const piatte: Record<string, unknown>[] = [];
    for (const t of trades) {
        const { closes, total_pnl: _tp, placed_in_day: _pd, settled_in_day: _sd, ...apertura } = t;
        piatte.push(apertura as unknown as Record<string, unknown>);
        for (const c of closes ?? []) piatte.push(c as unknown as Record<string, unknown>);
    }
    return marca(piatte, bot, sport);
}

async function leggiRipiego(giorno: string, modo: Modo): Promise<ChiuseGiornata> {
    const avvisi = [
        'Lettura di ripiego (migrazione posizioni_chiuse_giornata non applicata): '
        + 'bot tennis assenti per i giorni passati, catene di chiusura al primo livello.',
    ];
    const [o, s, m] = await Promise.allSettled([
        fetchOmegaDayTradesPerModo(giorno, modo),
        fetchSafeDayTrades(giorno, null, modo),
        fetchMikeDayTrades(giorno, modo),
    ]);
    const righe: TradeChiudibile[] = [];
    if (o.status === 'fulfilled') {
        // senza il filtro di modalita' sul server si filtra qui: mai mischiate
        righe.push(...righeDaStorico(o.value.trades, 'omega', 'calcio')
            .filter((r) => String(r.mode ?? '').toLowerCase() === modo));
    } else avvisi.push(`Omega non letto: ${o.reason instanceof Error ? o.reason.message : String(o.reason)}`);
    if (s.status === 'fulfilled') {
        righe.push(...righeDaStorico(s.value, 'safe')
            .filter((r) => String(r.mode ?? '').toLowerCase() === modo));
    } else avvisi.push(`Safe non letto: ${s.reason instanceof Error ? s.reason.message : String(s.reason)}`);
    if (m.status === 'fulfilled') {
        righe.push(...righeDaStorico(m.value, 'mike', 'calcio')
            .filter((r) => String(r.mode ?? '').toLowerCase() === modo));
    } else avvisi.push(`Mike non letto: ${m.reason instanceof Error ? m.reason.message : String(m.reason)}`);
    return { giorno, modo, righe, fonte: 'ripiego', avvisi, lettoAlle: Date.now() };
}

/** UNA giornata, UNA modalita', dal database (nessuna memoria qui). */
export async function leggiChiuseGiornata(giorno: string, modo: Modo): Promise<ChiuseGiornata> {
    const { data, error } = await supabase.rpc(RPC_CHIUSE_GIORNATA as never, {
        p_day: giorno, p_mode: modo,
    } as never);
    if (error) {
        if (eFirmaMancante(error.message)) return leggiRipiego(giorno, modo);
        throw new Error(error.message);
    }
    return { giorno, modo, righe: righeDaRisposta(data), fonte: 'rpc', avvisi: [], lettoAlle: Date.now() };
}

// ------------------------------------------------------------------ memoria
const memoria = new Map<string, Promise<ChiuseGiornata>>();
const lettaAlle = new Map<string, number>();

function chiave(giorno: string, modo: Modo): string {
    return `${giorno}|${modo}`;
}

/**
 * La giornata richiesta, dalla memoria se c'e' (e se oggi, non scaduta).
 * Una lettura fallita NON resta in memoria: al prossimo tentativo si rilegge.
 */
export function chiuseGiornata(
    giorno: string, modo: Modo,
    opz: { oggi: string; forza?: boolean; ora?: number; leggi?: typeof leggiChiuseGiornata },
): Promise<ChiuseGiornata> {
    const k = chiave(giorno, modo);
    const ora = opz.ora ?? Date.now();
    const quando = lettaAlle.get(k);
    const scaduta = giorno === opz.oggi && quando != null && ora - quando > SCADENZA_OGGI_MS;
    const giaLetta = memoria.get(k);
    if (giaLetta && !opz.forza && !scaduta) return giaLetta;
    const p = (opz.leggi ?? leggiChiuseGiornata)(giorno, modo);
    memoria.set(k, p);
    lettaAlle.set(k, ora);
    p.catch(() => { if (memoria.get(k) === p) { memoria.delete(k); lettaAlle.delete(k); } });
    return p;
}

/** Svuota la memoria (test; e il pulsante "rileggi"). */
export function dimenticaChiuseGiornata(): void {
    memoria.clear();
    lettaAlle.clear();
}
