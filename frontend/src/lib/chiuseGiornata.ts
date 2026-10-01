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
// gia' visto non rilegge niente. OGGI e IERI scadono dopo `SCADENZA_OGGI_MS`
// (01/10, B-10: col giorno della partita una partita di ieri sera regolata
// stanotte o stamattina cambia IERI, che deve aggiornarsi senza riavvio).
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
    addDays, eFirmaMancante, fetchMikeDayTrades, fetchOmegaDayTradesPerModo, fetchSafeDayTrades,
    type DayTrade,
} from '@/lib/dailyHistory';
import type { TennisBotOrderRow } from '@/lib/tennis';
import {
    haGiornoDb, posizioniChiuse, rigaDaOrdineTennis, unisciRighe,
    type PosizioneChiusa, type TradeChiudibile,
} from '@/lib/posizioniChiuse';

export const RPC_CHIUSE_GIORNATA = 'get_posizioni_chiuse_giornata';

/** quanto resta buona la lettura di OGGI e di IERI (le altre giornate non scadono) */
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
    /**
     * 01/10 - la risposta porta il giorno della PARTITA (contratto SQL)?
     * true = si'; false = righe presenti ma senza (aggiornamento del database
     * non applicato: si dichiara); null = nessuna riga da cui saperlo.
     */
    giornoPartita?: boolean | null;
    /** 01/10 - quando e' PARTITA la lettura (ms): cio' che era regolato prima c'e' */
    chiestoAlle?: number;
}

/** 01/10 - le righe dicono il giorno della partita? (vedi `ChiuseGiornata.giornoPartita`) */
export function giornoPartitaDi(righe: readonly TradeChiudibile[]): boolean | null {
    if (righe.length === 0) return null;
    return righe.some((r) => haGiornoDb(r));
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
        // C-07 (01/10): il nome della partita arriva dalla lettura anche per il
        // tennis; prima era null e le giornate passate dicevano «evento 3456…»
        const nome = typeof o.event_name === 'string' && o.event_name.trim() ? o.event_name.trim() : null;
        const r = rigaDaOrdineTennis(o as unknown as TennisBotOrderRow, nome,
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
    const chiestoAlle = Date.now();
    // A-03/C-02 (01/10): in parole, senza nomi di migrazioni o funzioni
    const avvisi = [
        'Lettura di ripiego (il database non ha ancora la lettura completa delle chiuse): '
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
    return {
        giorno, modo, righe, fonte: 'ripiego', avvisi, lettoAlle: Date.now(),
        giornoPartita: giornoPartitaDi(righe), chiestoAlle,
    };
}

/** UNA giornata, UNA modalita', dal database (nessuna memoria qui). */
export async function leggiChiuseGiornata(giorno: string, modo: Modo): Promise<ChiuseGiornata> {
    const chiestoAlle = Date.now();
    const { data, error } = await supabase.rpc(RPC_CHIUSE_GIORNATA as never, {
        p_day: giorno, p_mode: modo,
    } as never);
    if (error) {
        if (eFirmaMancante(error.message)) return leggiRipiego(giorno, modo);
        throw new Error(error.message);
    }
    const righe = righeDaRisposta(data);
    return {
        giorno, modo, righe, fonte: 'rpc', avvisi: [], lettoAlle: Date.now(),
        giornoPartita: giornoPartitaDi(righe), chiestoAlle,
    };
}

// ------------------------------------------- le posizioni di UNA giornata
/**
 * 01/10 - una riga regolata piu' di questo PRIMA che partisse la lettura del
 * giorno, e che la lettura (col giorno della partita) non porta, NON e' di
 * quella giornata: e' di una partita di un altro giorno. Il margine copre il
 * ritardo fra il regolamento di Betfair e la scrittura della riga.
 */
export const MARGINE_LETTURA_MS = 5 * 60_000;

export interface PosizioniDellaGiornata {
    /** memoria + righe lette, con il giorno del database ereditato */
    posizioni: readonly PosizioneChiusa[];
    /** posizioni in memoria SENZA il giorno del database che la lettura dice
     *  di un altro giorno (partite di altri giorni): fuori dal giorno e dal totale */
    escluse: ReadonlySet<PosizioneChiusa>;
}

const NESSUNA = new Set<PosizioneChiusa>();

/**
 * 01/10 (rilievi bassi, punto 1) - LA REGOLA UNICA con cui la scheda
 * Posizioni chiuse e la plancia «oggi per bot» fanno la giornata: le righe in
 * memoria si uniscono alla lettura della giornata (`unisciRighe`: la memoria
 * eredita `giorno_partita`/`giorno_da`/`in_day` dal database), le posizioni si
 * costruiscono UNA volta e, se la lettura porta il giorno della partita, quelle
 * in memoria ancora senza giorno, regolate ben prima della lettura e che la
 * lettura non porta, si escludono (`MARGINE_LETTURA_MS`). Le righe senza il
 * dato restano sul giorno di REGOLAMENTO, provvisorie (`giornoConfermato`
 * false): il client non calcola mai il giorno della partita.
 */
export function posizioniDellaGiornata(
    righe: readonly TradeChiudibile[],
    chiuse: readonly PosizioneChiusa[] | undefined,
    lettura: Pick<ChiuseGiornata, 'righe' | 'giornoPartita' | 'chiestoAlle'> | null,
    giorno: string,
): PosizioniDellaGiornata {
    const posizioni = lettura && lettura.righe.length
        ? posizioniChiuse(unisciRighe(righe, lettura.righe))
        : (chiuse ?? posizioniChiuse(righe));
    if (!lettura || lettura.giornoPartita !== true || lettura.chiestoAlle == null) {
        return { posizioni, escluse: NESSUNA };
    }
    const escluse = new Set<PosizioneChiusa>();
    const limite = lettura.chiestoAlle - MARGINE_LETTURA_MS;
    for (const p of posizioni) {
        if (p.giornoConfermato || p.giorno !== giorno) continue;
        const ms = Date.parse(p.chiusaAt);
        if (Number.isFinite(ms) && ms < limite) escluse.add(p);
    }
    return { posizioni, escluse };
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
    // B-10 (01/10): scadono OGGI e IERI (partite serali regolate dopo mezzanotte)
    const recente = giorno === opz.oggi || giorno === addDays(opz.oggi, -1);
    const scaduta = recente && quando != null && ora - quando > SCADENZA_OGGI_MS;
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
