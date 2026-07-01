// ============================================================================
// ladderConfig.ts — configurazione PURA delle COLONNE del ladder + PROFILI
// per-sport, persistiti in localStorage. Nessun React, nessun DOM: solo TS +
// localStorage, interamente testabile a unità.
//
// Un "profilo" è l'insieme ordinato di colonne del ladder scelte per uno sport
// (calcio, tennis, cavalli…). L'utente può mostrare/nascondere e riordinare le
// colonne; la scelta viene salvata per sport e ripristinata alla riapertura.
// ============================================================================

// Colonne disponibili nel ladder (mirror dei ladder pro tipo Geeks Toy / Bet Angel):
//   my_lay     — le tue size LAY non abbinate a quel prezzo
//   avail_back — denaro disponibile in BACK (lato blu/sky)
//   price      — la quota (colonna centrale)
//   avail_lay  — denaro disponibile in LAY (lato rosa/rose)
//   my_back    — le tue size BACK non abbinate a quel prezzo
//   pnl        — P&L "what-if" bloccando a quel prezzo
//   trd        — volume TRADED a quel prezzo
//   piq        — Position In Queue (denaro davanti a te)
//   wom        — Weight Of Money (sbilanciamento back/lay)
export type ColumnKey =
    | 'my_lay'
    | 'avail_back'
    | 'price'
    | 'avail_lay'
    | 'my_back'
    | 'pnl'
    | 'trd'
    | 'piq'
    | 'wom';

// Una colonna del profilo: chiave + se è visibile. L'ORDINE nell'array = ordine
// di rendering (sinistra→destra).
export interface LadderColumn {
    key: ColumnKey;
    visible: boolean;
}

// Un profilo = lista ordinata di colonne per uno sport.
export interface LadderProfile {
    sport: string;
    columns: LadderColumn[];
}

// Etichette IT brevi per intestazione colonna (informative; la UI può sovrascrivere).
export const COLUMN_LABELS: Record<ColumnKey, string> = {
    my_lay: 'Mio LAY',
    avail_back: 'Banco BACK',
    price: 'Quota',
    avail_lay: 'Banco LAY',
    my_back: 'Mio BACK',
    pnl: 'P&L',
    trd: 'TRD',
    piq: 'PIQ',
    wom: 'WOM',
};

// Ordine di DEFAULT delle colonne (layout classico a scaletta: le mie size ai lati,
// la quota al centro, il banco sui due lati). 'price' è SEMPRE presente e visibile.
export const DEFAULT_COLUMN_ORDER: readonly ColumnKey[] = [
    'my_lay',
    'trd',
    'avail_back',
    'price',
    'avail_lay',
    'pnl',
    'my_back',
    'piq',
    'wom',
] as const;

// Colonne visibili di default (le "extra" piq/wom partono nascoste per non affollare).
const DEFAULT_HIDDEN: ReadonlySet<ColumnKey> = new Set<ColumnKey>(['piq', 'wom']);

// 'price' non può mai essere nascosta né rimossa: è la spina dorsale del ladder.
export const REQUIRED_COLUMN: ColumnKey = 'price';

const ALL_KEYS: ReadonlySet<ColumnKey> = new Set<ColumnKey>(DEFAULT_COLUMN_ORDER);

// Prefisso chiave localStorage: una entry per sport.
const LS_PREFIX = 'ladderProfile:';

function storageKey(sport: string): string {
    return `${LS_PREFIX}${sport}`;
}

// Profilo di default per uno sport (non tocca localStorage).
export function defaultProfile(sport: string): LadderProfile {
    return {
        sport,
        columns: DEFAULT_COLUMN_ORDER.map((key) => ({
            key,
            visible: !DEFAULT_HIDDEN.has(key),
        })),
    };
}

// Normalizza un profilo (potenzialmente parziale/corrotto da storage) in uno valido:
//  - scarta chiavi sconosciute e duplicati (tiene la prima occorrenza);
//  - APPENDE le chiavi mancanti nell'ordine di default (schema-evolution safe);
//  - forza 'price' presente e visibile.
export function normalizeProfile(sport: string, raw: unknown): LadderProfile {
    const base = defaultProfile(sport);
    if (!raw || typeof raw !== 'object' || !Array.isArray((raw as { columns?: unknown }).columns)) {
        return base;
    }
    const seen = new Set<ColumnKey>();
    const columns: LadderColumn[] = [];
    for (const c of (raw as { columns: unknown[] }).columns) {
        if (!c || typeof c !== 'object') continue;
        const key = (c as { key?: unknown }).key;
        if (typeof key !== 'string' || !ALL_KEYS.has(key as ColumnKey)) continue;
        const k = key as ColumnKey;
        if (seen.has(k)) continue;
        seen.add(k);
        const visible = (c as { visible?: unknown }).visible;
        columns.push({ key: k, visible: typeof visible === 'boolean' ? visible : true });
    }
    // append chiavi mancanti nell'ordine di default
    for (const key of DEFAULT_COLUMN_ORDER) {
        if (!seen.has(key)) columns.push({ key, visible: !DEFAULT_HIDDEN.has(key) });
    }
    // 'price' sempre presente e visibile
    const price = columns.find((c) => c.key === REQUIRED_COLUMN);
    if (price) price.visible = true;
    else columns.push({ key: REQUIRED_COLUMN, visible: true });
    return { sport, columns };
}

// Carica il profilo di uno sport da localStorage (o il default se assente/illeggibile).
// Robusto: qualunque errore (JSON rotto, storage non disponibile) → default.
export function loadProfile(sport: string): LadderProfile {
    try {
        const rawStr = safeStorage()?.getItem(storageKey(sport));
        if (!rawStr) return defaultProfile(sport);
        return normalizeProfile(sport, JSON.parse(rawStr));
    } catch {
        return defaultProfile(sport);
    }
}

// Salva il profilo di uno sport in localStorage (normalizzato prima di scrivere).
// Ritorna true se scritto, false se lo storage non è disponibile.
export function saveProfile(profile: LadderProfile): boolean {
    const norm = normalizeProfile(profile.sport, profile);
    try {
        const s = safeStorage();
        if (!s) return false;
        s.setItem(storageKey(norm.sport), JSON.stringify(norm));
        return true;
    } catch {
        return false;
    }
}

// Rimuove il profilo salvato di uno sport (torna al default alla prossima load).
export function resetProfile(sport: string): void {
    try {
        safeStorage()?.removeItem(storageKey(sport));
    } catch {
        /* storage non disponibile: no-op */
    }
}

// Le sole chiavi visibili, nell'ordine corrente (per il rendering del ladder).
export function visibleColumns(profile: LadderProfile): ColumnKey[] {
    return profile.columns.filter((c) => c.visible).map((c) => c.key);
}

// Elenco completo (chiave + visibile) nell'ordine corrente — per il pannello di config.
export function listColumns(profile: LadderProfile): LadderColumn[] {
    return profile.columns.map((c) => ({ ...c }));
}

// Mostra/nascondi una colonna (PURA: ritorna un nuovo profilo). 'price' non è nascondibile.
export function toggleColumn(profile: LadderProfile, key: ColumnKey): LadderProfile {
    if (key === REQUIRED_COLUMN) return profile; // no-op: la quota resta sempre visibile
    return {
        sport: profile.sport,
        columns: profile.columns.map((c) =>
            c.key === key ? { key: c.key, visible: !c.visible } : { ...c },
        ),
    };
}

// Riordina spostando la colonna `key` alla posizione `toIndex` (PURA: nuovo profilo).
// toIndex è clampato in [0, n-1]. Se la chiave non esiste, ritorna il profilo invariato.
export function reorderColumn(profile: LadderProfile, key: ColumnKey, toIndex: number): LadderProfile {
    const cols = profile.columns.map((c) => ({ ...c }));
    const from = cols.findIndex((c) => c.key === key);
    if (from < 0) return profile;
    const n = cols.length;
    const dest = Math.min(n - 1, Math.max(0, Math.trunc(toIndex)));
    if (dest === from) return profile;
    const [moved] = cols.splice(from, 1);
    cols.splice(dest, 0, moved);
    return { sport: profile.sport, columns: cols };
}

// Accesso a localStorage a prova di SSR/ambiente senza Storage.
function safeStorage(): Storage | null {
    try {
        if (typeof localStorage !== 'undefined') return localStorage;
    } catch {
        /* accesso negato */
    }
    return null;
}
