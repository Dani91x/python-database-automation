// ============================================================================
// multiLadder.ts — layout PURO del MULTI-LADDER (B19): N ladder affiancati anche
// di mercati/eventi/sport diversi, persistiti in localStorage. Nessun React.
//
// Uno "slot" = un ladder nel workspace multi-ladder. L'id è deterministico
// (sport:marketId) → lo stesso mercato non può comparire due volte.
// ============================================================================

export interface LadderSlot {
    id: string;          // `${sport}:${marketId}` (deterministico, dedup)
    sport: string;       // 'calcio' | 'tennis' | …: seleziona le sorgenti dati
    eventId: string;
    marketId: string;
    marketName: string;
    eventName: string;
    p1?: string;         // tennis: nomi giocatori per le selezioni fallback
    p2?: string;
}

// cap slot: oltre, il browser non regge N sottoscrizioni realtime + il layout degrada.
export const MAX_SLOTS = 8;

const LS_KEY = 'multiLadder:slots';

export function slotId(sport: string, marketId: string): string {
    return `${sport}:${marketId}`;
}

// Normalizza una lista slot (parziale/corrotta): scarta voci malformate e duplicati,
// ricalcola l'id deterministico, applica il cap.
export function normalizeSlots(raw: unknown): LadderSlot[] {
    if (!Array.isArray(raw)) return [];
    const out: LadderSlot[] = [];
    const seen = new Set<string>();
    for (const s of raw) {
        if (!s || typeof s !== 'object') continue;
        const o = s as Record<string, unknown>;
        const sport = typeof o.sport === 'string' && o.sport ? o.sport : null;
        const eventId = typeof o.eventId === 'string' && o.eventId ? o.eventId : null;
        const marketId = typeof o.marketId === 'string' && o.marketId ? o.marketId : null;
        if (!sport || !eventId || !marketId) continue;
        const id = slotId(sport, marketId);
        if (seen.has(id)) continue;
        seen.add(id);
        out.push({
            id, sport, eventId, marketId,
            marketName: typeof o.marketName === 'string' ? o.marketName : marketId,
            eventName: typeof o.eventName === 'string' ? o.eventName : '',
            ...(typeof o.p1 === 'string' ? { p1: o.p1 } : {}),
            ...(typeof o.p2 === 'string' ? { p2: o.p2 } : {}),
        });
        if (out.length >= MAX_SLOTS) break;
    }
    return out;
}

// Aggiunge uno slot (PURA: nuova lista). Duplicato (stesso sport+mercato) o cap
// raggiunto → lista INVARIATA (stessa referenza: il chiamante può testare l'esito).
export function addSlot(slots: LadderSlot[], slot: Omit<LadderSlot, 'id'>): LadderSlot[] {
    const id = slotId(slot.sport, slot.marketId);
    if (slots.some(s => s.id === id)) return slots;
    if (slots.length >= MAX_SLOTS) return slots;
    return [...slots, { ...slot, id }];
}

// Rimuove uno slot per id (PURA: nuova lista).
export function removeSlot(slots: LadderSlot[], id: string): LadderSlot[] {
    return slots.filter(s => s.id !== id);
}

// ---------- persistenza (localStorage, a prova di ambiente senza Storage) ----------
function safeStorage(): Storage | null {
    try {
        if (typeof localStorage !== 'undefined') return localStorage;
    } catch { /* accesso negato */ }
    return null;
}

export function loadSlots(): LadderSlot[] {
    try {
        const raw = safeStorage()?.getItem(LS_KEY);
        if (!raw) return [];
        return normalizeSlots(JSON.parse(raw));
    } catch {
        return [];
    }
}

export function saveSlots(slots: LadderSlot[]): boolean {
    try {
        const s = safeStorage();
        if (!s) return false;
        s.setItem(LS_KEY, JSON.stringify(normalizeSlots(slots)));
        return true;
    } catch {
        return false;
    }
}
