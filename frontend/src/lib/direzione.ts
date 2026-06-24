// ============================================================================
// Cruscotto DIREZIONE — per-partita. Unisce i motori e dice, mercato per mercato,
// la direzione migliore + quanto e' affidabile (hit-rate storico reale dalla pagella).
// La matematica vive in Postgres (RPC get_direction): il client riceve tutto pronto.
//   affidabilita = hit-rate reale della fascia (pagella), per-lega con shrinkage->globale
//   banda Wilson 95% | lift = affid - base | concordanza motori | quota | dettaglio motori
// NESSUNA dipendenza dagli altri pannelli.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ---------- Tipi (specchiano l'output jsonb della RPC) ----------
export type EngineProbs = Record<string, number>;           // { selezione: prob } per Poisson/ML/TacticAI

export interface DirMarket {
    market: string;
    direction: string;
    affidabilita: number;        // 0..1  hit-rate reale calibrato
    wilson_low: number;          // 0..1  estremo basso banda 95%
    wilson_high: number;         // 0..1  estremo alto banda 95%
    n: number;                   // partite-equivalenti della stima
    base: number;                // 0..1  frequenza base del mercato
    lift: number;                // affid - base (il VERO segnale)
    odds: number | null;         // quota della direzione
    scope: 'lega' | 'globale';   // fonte dell'affidabilita'
    concordi: string[];          // motori che puntano la stessa direzione
    motori_totali: number;       // motori disponibili per il mercato
    engines: {
        poisson?: EngineProbs | null;
        ml?: EngineProbs | null;
        tacticai?: EngineProbs | null;
        api?: { dir: string } | null;
    };
}

export interface DirezioneData {
    fixture_id: number;
    league_id: number | null;
    generated_at?: string;
    markets: DirMarket[];
}

export async function fetchDirezione(fixtureId: string): Promise<DirezioneData | null> {
    const { data, error } = await supabase.rpc('get_direction', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    // la RPC torna un oggetto jsonb; difesa runtime contro forme inattese (array/null)
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    return data as DirezioneData;
}

// ---------- Etichette leggibili ----------
const MARKET_LABELS: Record<string, string> = {
    '1x2': 'Esito finale',
    'ht_1x2': '1° tempo · esito',
    'over_1_5': 'Over 1.5',
    'over_2_5': 'Over 2.5',
    'over_3_5': 'Over 3.5',
    'btts': 'Gol/Gol (BTTS)',
    'first_half_over_0_5': '1° tempo · Over 0.5',
};
export const marketLabel = (m: string): string => MARKET_LABELS[m] ?? m;

export function selectionLabel(market: string, sel: string): string {
    if (market === '1x2' || market === 'ht_1x2') {
        return { H: '1 (Casa)', D: 'X (Pari)', A: '2 (Trasf.)' }[sel] ?? sel;
    }
    if (market === 'btts') return { Yes: 'Sì', No: 'No' }[sel] ?? sel;
    return sel; // Over / Under
}

export const ENGINE_LABELS: Record<string, string> = {
    poisson: 'Poisson',
    ml: 'ML',
    tacticai: 'TacticAI',
    api: 'API / book',
};

// ---------- Semaforo: forza del segnale (basata sul lift) ----------
export type Strength = 'forte' | 'medio' | 'debole';
export function strength(lift: number): Strength {
    if (lift >= 0.10) return 'forte';
    if (lift > 0) return 'medio';
    return 'debole';
}

// L'argmax di un motore = la selezione che quel motore indica (per il dettaglio).
export function enginePick(probs?: EngineProbs | null): string | null {
    if (!probs) return null;
    let best: string | null = null, bv = -Infinity;
    for (const [k, v] of Object.entries(probs)) {
        if (typeof v === 'number' && v > bv) { bv = v; best = k; }
    }
    return best;
}
