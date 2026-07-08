// Test logica PURA di workspace.ts (layout area di lavoro per-evento + keybindings).
import { describe, it, expect, beforeEach } from 'vitest';
import {
    DEFAULT_PANEL_ORDER,
    DEFAULT_KEYBINDINGS,
    defaultLayout,
    normalizeLayout,
    loadLayout,
    saveLayout,
    resetLayout,
    togglePanel,
    collapsePanel,
    setActiveMarket,
    setColumnsProfile,
    resolveHotkey,
} from './workspace';

beforeEach(() => localStorage.clear());

describe('defaultLayout', () => {
    it('include tutti i pannelli nell\'ordine; audit/settings chiusi', () => {
        const l = defaultLayout('27:1234');
        expect(l.panels.map((p) => p.key)).toEqual([...DEFAULT_PANEL_ORDER]);
        expect(l.panels.find((p) => p.key === 'ladder')?.open).toBe(true);
        expect(l.panels.find((p) => p.key === 'audit')?.open).toBe(false);
        expect(l.panels.find((p) => p.key === 'settings')?.open).toBe(false);
        expect(l.activeMarketId).toBeNull();
        expect(l.columnsProfile).toBe('calcio');
    });
});

describe('normalizeLayout', () => {
    it('input non-oggetto → default', () => {
        expect(normalizeLayout('e1', null).panels.map((p) => p.key)).toEqual([...DEFAULT_PANEL_ORDER]);
    });
    it('scarta pannelli sconosciuti/duplicati e appende i mancanti', () => {
        const raw = {
            eventId: 'e1',
            panels: [
                { key: 'ladder', open: false, collapsed: true },
                { key: 'bogus', open: true },
                { key: 'ladder', open: true }, // duplicato ignorato
            ],
            activeMarketId: '1.99',
            columnsProfile: 'tennis',
        };
        const l = normalizeLayout('e1', raw);
        expect(l.panels.filter((p) => p.key === 'ladder')).toHaveLength(1);
        expect(l.panels.find((p) => p.key === 'ladder')?.open).toBe(false);
        expect(l.panels.some((p) => (p.key as string) === 'bogus')).toBe(false);
        expect(l.panels.map((p) => p.key).sort()).toEqual([...DEFAULT_PANEL_ORDER].sort());
        expect(l.activeMarketId).toBe('1.99');
        expect(l.columnsProfile).toBe('tennis');
    });
    it('columnsProfile vuoto/non-stringa → default calcio', () => {
        expect(normalizeLayout('e1', { columnsProfile: '' }).columnsProfile).toBe('calcio');
        expect(normalizeLayout('e1', { columnsProfile: 5 }).columnsProfile).toBe('calcio');
    });
});

describe('save/load/reset round-trip', () => {
    it('saveLayout poi loadLayout preserva stato', () => {
        let l = defaultLayout('e1');
        l = togglePanel(l, 'audit');           // apri audit
        l = setActiveMarket(l, '1.55');
        l = setColumnsProfile(l, 'cavalli');
        expect(saveLayout(l)).toBe(true);
        const loaded = loadLayout('e1');
        expect(loaded.panels.find((p) => p.key === 'audit')?.open).toBe(true);
        expect(loaded.activeMarketId).toBe('1.55');
        expect(loaded.columnsProfile).toBe('cavalli');
    });
    it('loadLayout senza salvataggio → default', () => {
        expect(loadLayout('mai').panels.map((p) => p.key)).toEqual([...DEFAULT_PANEL_ORDER]);
    });
    it('loadLayout con JSON rotto → default (nessun throw)', () => {
        localStorage.setItem('workspace:e1', 'not-json{');
        expect(loadLayout('e1').activeMarketId).toBeNull();
    });
    it('resetLayout rimuove il salvataggio', () => {
        saveLayout(defaultLayout('e1'));
        resetLayout('e1');
        expect(localStorage.getItem('workspace:e1')).toBeNull();
    });
    it('eventi diversi non si sovrascrivono', () => {
        saveLayout(setActiveMarket(defaultLayout('e1'), '1.1'));
        saveLayout(setActiveMarket(defaultLayout('e2'), '2.2'));
        expect(loadLayout('e1').activeMarketId).toBe('1.1');
        expect(loadLayout('e2').activeMarketId).toBe('2.2');
    });
});

describe('togglePanel / collapsePanel', () => {
    it('togglePanel apre/chiude e de-collassa alla chiusura (PURA)', () => {
        let l = defaultLayout('e1');
        l = collapsePanel(l, 'ladder', true);
        expect(l.panels.find((p) => p.key === 'ladder')?.collapsed).toBe(true);
        const closed = togglePanel(l, 'ladder');
        const lad = closed.panels.find((p) => p.key === 'ladder');
        expect(lad?.open).toBe(false);
        expect(lad?.collapsed).toBe(false); // chiudere azzera il collasso
    });
    it('collapsePanel no-op su pannello chiuso', () => {
        const l = defaultLayout('e1'); // audit chiuso
        const next = collapsePanel(l, 'audit', true);
        expect(next.panels.find((p) => p.key === 'audit')?.collapsed).toBe(false);
    });
    it('non muta l\'originale', () => {
        const l = defaultLayout('e1');
        const openBefore = l.panels.find((p) => p.key === 'audit')?.open;
        togglePanel(l, 'audit');
        expect(l.panels.find((p) => p.key === 'audit')?.open).toBe(openBefore);
    });
});

describe('resolveHotkey', () => {
    it('mappa i tasti di default', () => {
        expect(resolveHotkey('b')).toBe('back_preset');
        expect(resolveHotkey('l')).toBe('lay_preset');
        expect(resolveHotkey('c')).toBe('cancel_under_cursor');
        expect(resolveHotkey('g')).toBe('greenup');
        expect(resolveHotkey('ArrowUp')).toBe('move_up');
        expect(resolveHotkey('ArrowDown')).toBe('move_down');
    });
    it('mappa le hotkey complete del ladder (B16)', () => {
        expect(resolveHotkey('+')).toBe('stake_up');
        expect(resolveHotkey('-')).toBe('stake_down');
        expect(resolveHotkey('s')).toBe('cycle_preset');
        expect(resolveHotkey(' ')).toBe('center_ladder');
        expect(resolveHotkey('PageUp')).toBe('prev_market');
        expect(resolveHotkey('PageDown')).toBe('next_market');
        expect(resolveHotkey('S')).toBe('cycle_preset'); // normalizzazione lowercase
    });
    it('normalizza maiuscole a minuscole per i tasti singoli', () => {
        expect(resolveHotkey('B')).toBe('back_preset');
        expect(resolveHotkey('G')).toBe('greenup');
    });
    it('tasto non mappato → null', () => {
        expect(resolveHotkey('z')).toBeNull();
        expect(resolveHotkey('')).toBeNull();
    });
    it('accetta binding custom', () => {
        const custom = { ...DEFAULT_KEYBINDINGS, z: 'greenup' as const };
        expect(resolveHotkey('z', custom)).toBe('greenup');
    });
});
