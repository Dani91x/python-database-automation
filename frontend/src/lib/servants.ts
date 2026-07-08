// ============================================================================
// servants.ts — MACRO registrabili ("servants" di Bet Angel, roadmap C27).
// Una macro = sequenza di AZIONI da vocabolario FISSO, salvata in localStorage e
// richiamata con i tasti 1-9 sulla selezione sotto il cursore. Logica PURA:
// niente React/rete — l'esecuzione la fa il ladder traducendo gli step in intent
// (che passano da TUTTE le guardie normali: conferma LIVE, kill-switch, ecc.).
// ============================================================================

export type ServantStep =
    | {
        kind: 'place';
        side: 'back' | 'lay';
        // dove piazzare: al best del proprio lato, all'LTP, o N tick dal best
        // (>0 = più a fondo nel book, meno aggressivo; <0 = attraversa lo spread).
        price: 'best' | 'ltp' | { ticksFromBest: number };
        // stake: quello corrente del ladder, o un importo fisso in €.
        stake: 'current' | number;
    }
    | { kind: 'greenup' }                                  // cash-out totale selezione
    | { kind: 'cancel_side'; side: 'back' | 'lay' | 'both' };

export interface Servant {
    slot: number;          // 1..9 → hotkey
    name: string;
    steps: ServantStep[];
}

export const MAX_SERVANTS = 9;
export const MAX_STEPS = 6;

const LS_KEY = 'servants:v1';

// ---------------------------------------------------------------- validazione
function validStep(raw: unknown): ServantStep | null {
    if (!raw || typeof raw !== 'object') return null;
    const o = raw as Record<string, unknown>;
    if (o.kind === 'greenup') return { kind: 'greenup' };
    if (o.kind === 'cancel_side') {
        const s = o.side;
        if (s === 'back' || s === 'lay' || s === 'both') return { kind: 'cancel_side', side: s };
        return null;
    }
    if (o.kind === 'place') {
        const side = o.side;
        if (side !== 'back' && side !== 'lay') return null;
        let price: 'best' | 'ltp' | { ticksFromBest: number };
        if (o.price === 'best' || o.price === 'ltp') price = o.price;
        else if (o.price && typeof o.price === 'object'
                 && Number.isInteger((o.price as { ticksFromBest?: unknown }).ticksFromBest)
                 && Math.abs((o.price as { ticksFromBest: number }).ticksFromBest) <= 20) {
            price = { ticksFromBest: (o.price as { ticksFromBest: number }).ticksFromBest };
        } else return null;
        let stake: 'current' | number;
        if (o.stake === 'current') stake = 'current';
        else if (typeof o.stake === 'number' && Number.isFinite(o.stake) && o.stake > 0 && o.stake <= 10_000) {
            stake = Math.round(o.stake * 100) / 100;
        } else return null;
        return { kind: 'place', side, price, stake };
    }
    return null;
}

export function normalizeServants(raw: unknown): Servant[] {
    if (!Array.isArray(raw)) return [];
    const out: Servant[] = [];
    const seen = new Set<number>();
    for (const s of raw) {
        if (!s || typeof s !== 'object') continue;
        const o = s as Record<string, unknown>;
        const slot = typeof o.slot === 'number' ? Math.floor(o.slot) : NaN;
        if (!(slot >= 1 && slot <= MAX_SERVANTS) || seen.has(slot)) continue;
        const steps = (Array.isArray(o.steps) ? o.steps : [])
            .map(validStep)
            .filter((x): x is ServantStep => x != null)
            .slice(0, MAX_STEPS);
        if (!steps.length) continue;
        seen.add(slot);
        out.push({
            slot,
            name: typeof o.name === 'string' && o.name.trim() ? o.name.trim().slice(0, 40) : `Macro ${slot}`,
            steps,
        });
    }
    return out.sort((a, b) => a.slot - b.slot);
}

// ---------------------------------------------------------------- persistenza
function safeStorage(): Storage | null {
    try {
        if (typeof localStorage !== 'undefined') return localStorage;
    } catch { /* accesso negato */ }
    return null;
}

export function loadServants(): Servant[] {
    try {
        const raw = safeStorage()?.getItem(LS_KEY);
        if (!raw) return [];
        return normalizeServants(JSON.parse(raw));
    } catch {
        return [];
    }
}

export function saveServants(list: Servant[]): boolean {
    try {
        const s = safeStorage();
        if (!s) return false;
        s.setItem(LS_KEY, JSON.stringify(normalizeServants(list)));
        return true;
    } catch {
        return false;
    }
}

export function upsertServant(list: Servant[], servant: Servant): Servant[] {
    return normalizeServants([...list.filter(s => s.slot !== servant.slot), servant]);
}

export function removeServant(list: Servant[], slot: number): Servant[] {
    return list.filter(s => s.slot !== slot);
}

// ------------------------------------------------------- risoluzione prezzi
// Traduce lo step 'place' in un prezzo CONCRETO dato il book corrente della
// selezione. tickStep(price, n) è iniettato (ladder tick: matching.tickUp/Down).
export function resolveStepPrice(
    step: Extract<ServantStep, { kind: 'place' }>,
    book: { bestBack: number | null; bestLay: number | null; ltp: number | null },
    tickStep: (price: number, n: number) => number,
): number | null {
    if (step.price === 'ltp') return book.ltp;
    const base = step.side === 'back' ? book.bestBack : book.bestLay;
    if (base == null) return null;
    if (step.price === 'best') return base;
    const n = step.price.ticksFromBest;
    // BACK: +n = quota più ALTA (più a fondo nel book); LAY: +n = quota più BASSA.
    const dir = step.side === 'back' ? n : -n;
    return tickStep(base, dir);
}

// Etichetta breve per la UI/legenda.
export function servantLabel(s: Servant): string {
    const parts = s.steps.map(st => {
        if (st.kind === 'greenup') return 'green-up';
        if (st.kind === 'cancel_side') return `annulla ${st.side === 'both' ? 'tutto' : st.side.toUpperCase()}`;
        const px = st.price === 'best' ? 'best' : st.price === 'ltp' ? 'LTP' : `${st.price.ticksFromBest > 0 ? '+' : ''}${st.price.ticksFromBest}t`;
        const stk = st.stake === 'current' ? '€corrente' : `€${st.stake}`;
        return `${st.side.toUpperCase()} ${stk}@${px}`;
    });
    return `${s.slot}· ${s.name}: ${parts.join(' → ')}`;
}
