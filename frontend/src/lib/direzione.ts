// ============================================================================
// Cruscotto DIREZIONE — per-partita. Unisce i motori e dice, mercato per mercato,
// la direzione migliore + quanto e' affidabile (hit-rate storico reale dalla pagella).
// La matematica vive in Postgres (RPC get_direction): il client riceve tutto pronto.
//   affidabilita = hit-rate reale della fascia (pagella), per-lega con shrinkage->globale
//   banda Wilson 95% | lift = affid - base | concordanza motori | quota | dettaglio motori
// NESSUNA dipendenza dagli altri pannelli.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import type { DirectionOdds } from '@/lib/betfair';

// ---------- Tipi (specchiano l'output jsonb della RPC) ----------
export type EngineProbs = Record<string, number>;           // { selezione: prob } per Poisson/ML/TacticAI

export interface DirMarket {
    market: string;
    direction: string;
    // calibrated=false quando manca la previsione Poisson: i campi di affidabilita'
    // (affidabilita/wilson/n/base/lift/scope) sono NULL e la direzione viene dai motori
    // disponibili (ML/TacticAI/API). poisson_missing = quel mercato non ha Poisson.
    calibrated: boolean;
    poisson_missing: boolean;
    affidabilita: number | null;        // 0..1  hit-rate reale calibrato (null se non calibrato)
    wilson_low: number | null;          // 0..1  estremo basso banda 95%
    wilson_high: number | null;         // 0..1  estremo alto banda 95%
    n: number | null;                   // partite-equivalenti della stima
    base: number | null;                // 0..1  frequenza base del mercato
    lift: number | null;                // affid - base (il VERO segnale)
    odds: number | null;                // quota della direzione
    scope: 'lega' | 'globale' | null;   // fonte dell'affidabilita'
    concordi: string[];                 // motori che puntano la stessa direzione
    motori_totali: number;              // motori disponibili per il mercato
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
    poisson_present?: boolean;   // false => avviso: consigli poco affidabili (manca Poisson)
    markets: DirMarket[];
}

export async function fetchDirezione(fixtureId: string): Promise<DirezioneData | null> {
    const { data, error } = await supabase.rpc('get_direction', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    // la RPC torna un oggetto jsonb; difesa runtime contro forme inattese (array/null)
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    return data as DirezioneData;
}

// ---------- Eta' dei dati MATERIALIZZATI della Direzione (R5, 25/09) ----------
// RPC get_direction_eta (migrations/get_direction_eta_2026-09-25.sql):
//   pagella_generated_at = max(direction_pagella.generated_at) delle righe Poisson
//   quota_righe / quota_con_prezzo = righe di analytics_bets della partita e quante
//   hanno una quota. analytics_bets NON ha una colonna di tempo: l'eta' della quota
//   non e' misurabile (quota_eta sempre null), se ne dichiara solo la presenza.
export interface DirezioneEta {
    fixture_id: number;
    pagella_generated_at: string | null;
    quota_righe: number;
    quota_con_prezzo: number;
    quota_eta: null;
    now: string;                 // ora del server al momento della lettura
}

export async function fetchDirezioneEta(fixtureId: string): Promise<DirezioneEta> {
    const { data, error } = await supabase.rpc('get_direction_eta', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('risposta inattesa');
    return data as DirezioneEta;
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
        return ({
            H: '1 (Casa)', D: 'X (Pari)', A: '2 (Trasf.)',
            // doppia chance dall'advice API (1X = casa o pari, X2 = pari o trasf.)
            '1X': '1X (Casa/Pari)', X2: 'X2 (Pari/Trasf.)', '12': '12 (no Pari)',
        } as Record<string, string>)[sel] ?? sel;
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

// ---------- Quota della carta: FONTE dichiarata (FIX-B 26/09, KO6 referto fase 3) ----------
// get_direction.odds = coalesce(analytics_bets.odds_betfair, odds_book) e odds_betfair e'
// quasi sempre NULL: quella quota e' di fatto del BOOKMAKER. Regola (nessun cambio della
// logica di Direzione, solo fonte/etichetta):
//   1. quota Betfair back migliore della direzione (get_betfair_direction_odds) se c'e'
//      -> fonte 'betfair', il giudizio di valore (banda bassa > 1/quota) si fa su di lei;
//   2. altrimenti la quota di get_direction -> fonte 'book', mostrata come "quota book"
//      e MAI giudicata "valore" (una quota bookmaker non e' eseguibile su Betfair).
export type FonteQuota = 'betfair' | 'book';
export interface QuotaCarta { odds: number | null; fonte: FonteQuota | null; giudicabile: boolean }

export function quotaDirezione(
    m: Pick<DirMarket, 'direction' | 'odds'>,
    bfMercato?: DirectionOdds[string],
): QuotaCarta {
    const back = bfMercato?.[m.direction]?.back?.[0]?.price;
    if (typeof back === 'number' && Number.isFinite(back) && back > 1) return { odds: back, fonte: 'betfair', giudicabile: true };
    if (typeof m.odds === 'number' && Number.isFinite(m.odds) && m.odds > 1) return { odds: m.odds, fonte: 'book', giudicabile: false };
    return { odds: null, fonte: null, giudicabile: false };
}

// ---------- Semaforo: forza del segnale (basata sul lift) ----------
// 'nd' = non calibrato (manca Poisson): nessun lift -> indicatore neutro.
export type Strength = 'forte' | 'medio' | 'debole' | 'nd';
export function strength(lift: number | null | undefined): Strength {
    if (lift == null) return 'nd';
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
