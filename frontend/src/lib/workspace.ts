// ============================================================================
// workspace.ts — salvataggio/ripristino PURO del LAYOUT dell'area di lavoro
// (quali pannelli sono aperti/collassati, tab di mercato attivo, profilo colonne
// selezionato) in localStorage, keyed PER EVENTO. Più una mappa di KEYBINDINGS
// di default come DATI (nessun DOM, nessun listener qui). Testabile a unità.
// ============================================================================

// Pannelli operativi che possono essere aperti/collassati nell'area di lavoro.
export type PanelKey =
    | 'ladder'
    | 'orders'
    | 'positions'
    | 'risk'
    | 'dutching'
    | 'xhedge'
    | 'scalper'
    | 'audit'
    | 'settings';

// Stato di un pannello: presente nel layout e collassato o no.
export interface PanelState {
    key: PanelKey;
    open: boolean;       // presente/montato nell'area di lavoro
    collapsed: boolean;  // montato ma ridotto a intestazione
}

// Layout completo dell'area di lavoro per un evento.
export interface WorkspaceLayout {
    eventId: string;
    panels: PanelState[];
    activeMarketId: string | null;  // tab mercato attivo
    columnsProfile: string;         // sport-key del profilo colonne ladder (vedi ladderConfig)
}

// Pannelli di default (aperti, non collassati; audit/settings partono chiusi).
const DEFAULT_OPEN: ReadonlySet<PanelKey> = new Set<PanelKey>([
    'ladder', 'orders', 'positions', 'risk', 'dutching', 'xhedge', 'scalper',
]);
export const DEFAULT_PANEL_ORDER: readonly PanelKey[] = [
    'ladder', 'orders', 'positions', 'risk', 'dutching', 'xhedge', 'scalper',
    'audit', 'settings',
] as const;

const ALL_PANELS: ReadonlySet<PanelKey> = new Set<PanelKey>(DEFAULT_PANEL_ORDER);

const LS_PREFIX = 'workspace:';

function storageKey(eventId: string): string {
    return `${LS_PREFIX}${eventId}`;
}

// Layout di default per un evento (non tocca localStorage). columnsProfile default 'calcio'.
export function defaultLayout(eventId: string, columnsProfile = 'calcio'): WorkspaceLayout {
    return {
        eventId,
        panels: DEFAULT_PANEL_ORDER.map((key) => ({
            key,
            open: DEFAULT_OPEN.has(key),
            collapsed: false,
        })),
        activeMarketId: null,
        columnsProfile,
    };
}

// Normalizza un layout (parziale/corrotto) in uno valido: scarta pannelli sconosciuti
// e duplicati, appende i pannelli mancanti nell'ordine di default, tipizza i campi.
export function normalizeLayout(eventId: string, raw: unknown): WorkspaceLayout {
    const base = defaultLayout(eventId);
    if (!raw || typeof raw !== 'object') return base;
    const obj = raw as Record<string, unknown>;

    const panels: PanelState[] = [];
    const seen = new Set<PanelKey>();
    if (Array.isArray(obj.panels)) {
        for (const p of obj.panels) {
            if (!p || typeof p !== 'object') continue;
            const key = (p as { key?: unknown }).key;
            if (typeof key !== 'string' || !ALL_PANELS.has(key as PanelKey)) continue;
            const k = key as PanelKey;
            if (seen.has(k)) continue;
            seen.add(k);
            const open = (p as { open?: unknown }).open;
            const collapsed = (p as { collapsed?: unknown }).collapsed;
            panels.push({
                key: k,
                open: typeof open === 'boolean' ? open : DEFAULT_OPEN.has(k),
                collapsed: typeof collapsed === 'boolean' ? collapsed : false,
            });
        }
    }
    for (const key of DEFAULT_PANEL_ORDER) {
        if (!seen.has(key)) panels.push({ key, open: DEFAULT_OPEN.has(key), collapsed: false });
    }

    const activeMarketId = typeof obj.activeMarketId === 'string' ? obj.activeMarketId : null;
    const columnsProfile = typeof obj.columnsProfile === 'string' && obj.columnsProfile.length > 0
        ? obj.columnsProfile
        : base.columnsProfile;

    return { eventId, panels, activeMarketId, columnsProfile };
}

// Carica il layout di un evento da localStorage (o default se assente/illeggibile).
export function loadLayout(eventId: string): WorkspaceLayout {
    try {
        const rawStr = safeStorage()?.getItem(storageKey(eventId));
        if (!rawStr) return defaultLayout(eventId);
        return normalizeLayout(eventId, JSON.parse(rawStr));
    } catch {
        return defaultLayout(eventId);
    }
}

// Salva il layout di un evento (normalizzato). Ritorna true se scritto.
export function saveLayout(layout: WorkspaceLayout): boolean {
    const norm = normalizeLayout(layout.eventId, layout);
    try {
        const s = safeStorage();
        if (!s) return false;
        s.setItem(storageKey(norm.eventId), JSON.stringify(norm));
        return true;
    } catch {
        return false;
    }
}

// Rimuove il layout salvato di un evento (torna al default alla prossima load).
export function resetLayout(eventId: string): void {
    try {
        safeStorage()?.removeItem(storageKey(eventId));
    } catch {
        /* storage non disponibile */
    }
}

// Apri/chiudi un pannello (PURA: nuovo layout). Aprire un pannello lo de-collassa.
export function togglePanel(layout: WorkspaceLayout, key: PanelKey): WorkspaceLayout {
    return {
        ...layout,
        panels: layout.panels.map((p) => {
            if (p.key !== key) return { ...p };
            const open = !p.open;
            return { key: p.key, open, collapsed: open ? p.collapsed : false };
        }),
    };
}

// Collassa/espandi un pannello (PURA). No-op se il pannello è chiuso.
export function collapsePanel(layout: WorkspaceLayout, key: PanelKey, collapsed: boolean): WorkspaceLayout {
    return {
        ...layout,
        panels: layout.panels.map((p) =>
            p.key === key && p.open ? { ...p, collapsed } : { ...p },
        ),
    };
}

// Imposta il tab di mercato attivo (PURA).
export function setActiveMarket(layout: WorkspaceLayout, marketId: string | null): WorkspaceLayout {
    return { ...layout, activeMarketId: marketId };
}

// Imposta il profilo colonne selezionato (PURA).
export function setColumnsProfile(layout: WorkspaceLayout, sport: string): WorkspaceLayout {
    return { ...layout, columnsProfile: sport };
}

// ---------- KEYBINDINGS (dati; nessun DOM/listener qui) ----------
// Azioni scatenabili da tastiera nell'area di lavoro operativa.
export type HotkeyAction =
    | 'back_preset'        // piazza BACK al preset sotto il cursore
    | 'lay_preset'         // piazza LAY al preset sotto il cursore
    | 'cancel_under_cursor'// annulla gli ordini alla riga sotto il cursore
    | 'greenup'            // green-up totale del mercato attivo
    | 'cashout_event'      // cash-out dell'intero evento
    | 'move_up'            // sposta il focus/prezzo di 1 tick su
    | 'move_down'          // sposta il focus/prezzo di 1 tick giù
    | 'kill_switch';       // attiva il kill-switch globale (panico)

// Mappa DEFAULT tasto→azione. Chiavi = valori di KeyboardEvent.key normalizzati lowercase
// (le frecce restano 'ArrowUp'/'ArrowDown'). Sola definizione DATI: il binding effettivo
// dei listener avviene nel componente React, non qui.
export const DEFAULT_KEYBINDINGS: Readonly<Record<string, HotkeyAction>> = {
    b: 'back_preset',
    l: 'lay_preset',
    c: 'cancel_under_cursor',
    g: 'greenup',
    x: 'cashout_event',
    ArrowUp: 'move_up',
    ArrowDown: 'move_down',
    Escape: 'kill_switch',
};

// Etichette IT per la legenda hotkey (informative).
export const HOTKEY_LABELS: Record<HotkeyAction, string> = {
    back_preset: 'BACK preset',
    lay_preset: 'LAY preset',
    cancel_under_cursor: 'Annulla sotto il cursore',
    greenup: 'Green-up',
    cashout_event: 'Cash-out evento',
    move_up: 'Su 1 tick',
    move_down: 'Giù 1 tick',
    kill_switch: 'Kill-switch',
};

// Risolve un tasto in azione dato un set di binding (default = DEFAULT_KEYBINDINGS).
// Normalizza i tasti a singolo carattere in lowercase; lascia intatti i nomi speciali
// ('ArrowUp', 'Escape', …). Ritorna null se il tasto non è mappato.
export function resolveHotkey(
    key: string,
    bindings: Readonly<Record<string, HotkeyAction>> = DEFAULT_KEYBINDINGS,
): HotkeyAction | null {
    if (!key) return null;
    const norm = key.length === 1 ? key.toLowerCase() : key;
    return bindings[norm] ?? bindings[key] ?? null;
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
