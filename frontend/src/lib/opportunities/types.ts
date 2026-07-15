// ============================================================================
// types.ts — contratto condiviso del motore di opportunità Betfair.
// PURE TypeScript, NESSUNA dipendenza da React. Tutto unit-testabile.
//
// La `Ladder` (LadderMap) è la STESSA struttura di live.ts/replay-pnl.ts:
//   ladder[selectionId] = { back:[[price,size]...], lay:[[price,size]...], ltp, tv }
//   index 0 = best (back = miglior prezzo a cui BANCARE prendendo denaro
//   disponibile-per-bancare; lay = miglior prezzo a cui LAYARE).
// ============================================================================
import type { Ladder as LadderMap } from '@/lib/live';

// Re-export del tipo ladder così i consumer del motore importano da un punto solo.
export type { LadderMap };

// Livello di rischio dell'opportunità (ordinamento: arb > low > directional).
export type RiskTier = 'arb' | 'low' | 'directional';

// Selezione "leggera" (sottoinsieme di ReplaySelection di live.ts).
export interface SelLite {
    selection_id: number;
    name: string | null;
    sort_priority?: number | null;
}

// Mercato "leggero" (metadati, senza prezzi).
export interface MarketLite {
    market_id: string;
    market_type: string | null;
    market_name: string | null;
    selections: SelLite[];
}

// Stato quotato di un mercato in un dato istante (prezzi correnti).
export interface MarketState {
    market_id: string;
    market_type: string | null;
    status: string;
    ladder: LadderMap; // ladder[selId] = {back:[[price,size]...], lay:[[...]], ltp, tv}; index0 = best
    // ts del FRAME sottostante (carry-forward): serve alla validazione per capire
    // se un look-ahead osserva dati NUOVI o lo stesso frame trascinato.
    frame_ts?: string;
}

// Fotografia dell'intera partita in un bucket temporale.
export interface Snapshot {
    ts: string;
    minute: number | null;
    scoreHome: number;
    scoreAway: number;
    markets: MarketLite[];
    state: Record<string, MarketState>; // keyed by market_id
}

// Una gamba di un'operazione (una bet concreta da piazzare ORA).
export interface Leg {
    marketId: string;
    marketName: string;
    selectionId: number;
    selectionName: string;
    side: 'back' | 'lay';
    price: number;
    stake: number;        // stake desiderato (£)
    matchedStake: number; // stake realisticamente piazzabile ORA con questi prezzi
}

// Un'opportunità rilevata da un detector.
export interface Opportunity {
    id: string;
    tier: RiskTier;
    type: string;
    title: string;
    instruction: string;
    legs: Leg[];
    profit: number;     // profitto atteso in £ (netto commissioni)
    profitPct: number;  // profitto in % sullo stake/esposizione
    confidence: number; // 0..1
    explanation: string;
    phase: string;
    exitPlan?: string;
}

// Configurazione del motore (default: stake 100, minProfitPct 0.5,
// commission 0.05, delaySec 6).
export interface OppConfig {
    stake: number;
    minProfitPct: number;
    commission: number;
    delaySec: number;
    // Frazione MINIMA di fill richiesta su OGNI gamba di un arbitraggio (tier 'arb')
    // perché sia considerato affidabile: con liquidità sottile le proporzioni del
    // dutching saltano. Assente/0 = nessun vincolo (retro-compatibile coi test).
    minFillRatio?: number;
}

// Firma di un detector: data una fotografia + config → lista di opportunità.
export type Detector = (snap: Snapshot, cfg: OppConfig) => Opportunity[];
