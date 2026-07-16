// Test logica PURA di ladderConfig.ts (colonne configurabili + profili per-sport in
// localStorage). jsdom fornisce localStorage; lo puliamo tra i test.
import { describe, it, expect, beforeEach } from 'vitest';
import {
    DEFAULT_COLUMN_ORDER,
    PROFILE_VERSION,
    REQUIRED_COLUMN,
    defaultProfile,
    normalizeProfile,
    loadProfile,
    saveProfile,
    resetProfile,
    visibleColumns,
    listColumns,
    toggleColumn,
    reorderColumn,
    migrateProfileV1,
    type LadderProfile,
} from './ladderConfig';

beforeEach(() => localStorage.clear());

describe('defaultProfile', () => {
    it('contiene tutte le colonne di default nell\'ordine', () => {
        const p = defaultProfile('calcio');
        expect(p.sport).toBe('calcio');
        expect(p.columns.map((c) => c.key)).toEqual([...DEFAULT_COLUMN_ORDER]);
    });
    it('price è sempre visibile, piq/wom nascoste di default', () => {
        const p = defaultProfile('calcio');
        expect(p.columns.find((c) => c.key === 'price')?.visible).toBe(true);
        expect(p.columns.find((c) => c.key === 'piq')?.visible).toBe(false);
        expect(p.columns.find((c) => c.key === 'wom')?.visible).toBe(false);
    });
});

describe('normalizeProfile', () => {
    it('input non-oggetto → default', () => {
        expect(normalizeProfile('tennis', null).columns.map((c) => c.key))
            .toEqual([...DEFAULT_COLUMN_ORDER]);
        expect(normalizeProfile('tennis', 42).sport).toBe('tennis');
    });
    it('scarta chiavi sconosciute e duplicati (tiene la prima)', () => {
        const raw = {
            sport: 'calcio',
            columns: [
                { key: 'price', visible: true },
                { key: 'bogus', visible: true },
                { key: 'price', visible: false }, // duplicato ignorato
            ],
        };
        const p = normalizeProfile('calcio', raw);
        const priceCols = p.columns.filter((c) => c.key === 'price');
        expect(priceCols).toHaveLength(1);
        expect(p.columns.some((c) => (c.key as string) === 'bogus')).toBe(false);
    });
    it('appende le colonne mancanti nell\'ordine di default', () => {
        const raw = { sport: 'calcio', columns: [{ key: 'price', visible: true }] };
        const p = normalizeProfile('calcio', raw);
        expect(p.columns.map((c) => c.key).sort()).toEqual([...DEFAULT_COLUMN_ORDER].sort());
    });
    it('forza price visibile anche se salvata nascosta', () => {
        const raw = { sport: 'calcio', columns: [{ key: 'price', visible: false }] };
        expect(normalizeProfile('calcio', raw).columns.find((c) => c.key === REQUIRED_COLUMN)?.visible)
            .toBe(true);
    });
});

describe('save/load/reset round-trip', () => {
    it('saveProfile poi loadProfile ritorna lo stesso ordine/visibilità', () => {
        let p = defaultProfile('calcio');
        p = toggleColumn(p, 'piq');       // rendi visibile piq
        expect(saveProfile(p)).toBe(true);
        const loaded = loadProfile('calcio');
        expect(loaded.columns.find((c) => c.key === 'piq')?.visible).toBe(true);
    });
    it('loadProfile senza salvataggio → default', () => {
        expect(loadProfile('mai-salvato').columns.map((c) => c.key)).toEqual([...DEFAULT_COLUMN_ORDER]);
    });
    it('loadProfile con JSON rotto → default (nessun throw)', () => {
        localStorage.setItem('ladderProfile:calcio', '{ non-json');
        expect(loadProfile('calcio').columns.map((c) => c.key)).toEqual([...DEFAULT_COLUMN_ORDER]);
    });
    it('resetProfile rimuove il salvataggio', () => {
        saveProfile(defaultProfile('calcio'));
        resetProfile('calcio');
        expect(localStorage.getItem('ladderProfile:calcio')).toBeNull();
    });
    it('profili di sport diversi non si sovrascrivono', () => {
        saveProfile(toggleColumn(defaultProfile('calcio'), 'piq'));
        saveProfile(defaultProfile('tennis'));
        expect(loadProfile('calcio').columns.find((c) => c.key === 'piq')?.visible).toBe(true);
        expect(loadProfile('tennis').columns.find((c) => c.key === 'piq')?.visible).toBe(false);
    });
});

// v2: LAY a sinistra della quota, BACK a destra — i profili v1 salvati (senza
// `version`) devono migrare in load scambiando le posizioni di avail_back/avail_lay.
describe('migrazione profili v1 → v2 (swap lati BACK/LAY)', () => {
    // ordine di default STORICO v1 (BACK a sinistra, LAY a destra)
    const V1_DEFAULT_ORDER = [
        'my_lay', 'trd', 'avail_back', 'price', 'avail_lay', 'pnl', 'ev', 'my_back', 'piq', 'wom',
    ];

    it('il nuovo default ha LAY a sinistra e BACK a destra della quota', () => {
        const keys = [...DEFAULT_COLUMN_ORDER];
        const iLay = keys.indexOf('avail_lay');
        const iPrice = keys.indexOf('price');
        const iBack = keys.indexOf('avail_back');
        expect(iLay).toBeLessThan(iPrice);
        expect(iPrice).toBeLessThan(iBack);
        // le mie size restano sul lato del proprio side
        expect(keys.indexOf('my_lay')).toBeLessThan(iPrice);
        expect(keys.indexOf('my_back')).toBeGreaterThan(iPrice);
    });

    it('profilo v1 = default storico → dopo load l\'ordine è il default v2', () => {
        const raw = {
            sport: 'calcio',
            columns: V1_DEFAULT_ORDER.map((key) => ({ key, visible: true })),
        }; // senza version → v1
        localStorage.setItem('ladderProfile:calcio', JSON.stringify(raw));
        const loaded = loadProfile('calcio');
        expect(loaded.columns.map((c) => c.key)).toEqual([...DEFAULT_COLUMN_ORDER]);
    });

    it('profilo v1 personalizzato → swap solo di avail_back/avail_lay, visibilità preservata', () => {
        const raw = {
            sport: 'tennis',
            columns: [
                { key: 'pnl', visible: false },
                { key: 'avail_back', visible: true },
                { key: 'price', visible: true },
                { key: 'avail_lay', visible: false },
                { key: 'my_back', visible: true },
            ],
        };
        localStorage.setItem('ladderProfile:tennis', JSON.stringify(raw));
        const loaded = loadProfile('tennis');
        const keys = loaded.columns.map((c) => c.key);
        // le posizioni 1 e 3 sono scambiate
        expect(keys[1]).toBe('avail_lay');
        expect(keys[3]).toBe('avail_back');
        // la visibilità segue la CHIAVE, non la posizione
        expect(loaded.columns.find((c) => c.key === 'avail_lay')?.visible).toBe(false);
        expect(loaded.columns.find((c) => c.key === 'avail_back')?.visible).toBe(true);
        expect(loaded.columns.find((c) => c.key === 'pnl')?.visible).toBe(false);
    });

    it('profilo v2 già migrato → load NON riapplica lo swap (idempotenza)', () => {
        const p = defaultProfile('calcio');
        expect(saveProfile(p)).toBe(true); // salva con version corrente
        const loaded = loadProfile('calcio');
        expect(loaded.columns.map((c) => c.key)).toEqual([...DEFAULT_COLUMN_ORDER]);
        expect(loaded.version).toBe(PROFILE_VERSION);
    });

    it('migrateProfileV1 su input malformato → passthrough senza throw', () => {
        expect(migrateProfileV1(null)).toBeNull();
        expect(migrateProfileV1(42)).toBe(42);
        expect(migrateProfileV1({ columns: 'x' })).toEqual({ columns: 'x' });
    });

    it('save/load round-trip stampa la version', () => {
        saveProfile(defaultProfile('calcio'));
        const raw = JSON.parse(localStorage.getItem('ladderProfile:calcio') ?? '{}');
        expect(raw.version).toBe(PROFILE_VERSION);
    });
});

describe('toggleColumn', () => {
    it('inverte la visibilità e NON muta l\'originale (PURA)', () => {
        const p = defaultProfile('calcio');
        const before = p.columns.find((c) => c.key === 'pnl')?.visible;
        const next = toggleColumn(p, 'pnl');
        expect(next.columns.find((c) => c.key === 'pnl')?.visible).toBe(!before);
        expect(p.columns.find((c) => c.key === 'pnl')?.visible).toBe(before); // immutato
    });
    it('price non è nascondibile (no-op)', () => {
        const p = defaultProfile('calcio');
        const next = toggleColumn(p, REQUIRED_COLUMN);
        expect(next.columns.find((c) => c.key === REQUIRED_COLUMN)?.visible).toBe(true);
    });
});

describe('reorderColumn', () => {
    it('sposta una colonna alla nuova posizione', () => {
        const p = defaultProfile('calcio');
        const next = reorderColumn(p, 'pnl', 0);
        expect(next.columns[0].key).toBe('pnl');
    });
    it('clampa toIndex agli estremi', () => {
        const p = defaultProfile('calcio');
        const next = reorderColumn(p, 'price', 999);
        expect(next.columns[next.columns.length - 1].key).toBe('price');
    });
    it('chiave inesistente → invariato', () => {
        const p = defaultProfile('calcio');
        const next = reorderColumn(p, 'trd', 0);
        // trd esiste: verifichiamo invece che una chiave davvero assente ritorni lo stesso ref
        const nonexistent = { sport: 'calcio', columns: p.columns.filter((c) => c.key !== 'trd') } as LadderProfile;
        expect(reorderColumn(nonexistent, 'trd', 0)).toBe(nonexistent);
        expect(next.columns[0].key).toBe('trd');
    });
});

describe('visibleColumns / listColumns', () => {
    it('visibleColumns esclude le nascoste mantenendo l\'ordine', () => {
        const vis = visibleColumns(defaultProfile('calcio'));
        expect(vis).toContain('price');
        expect(vis).not.toContain('piq');
    });
    it('listColumns ritorna una copia (no aliasing)', () => {
        const p = defaultProfile('calcio');
        const list = listColumns(p);
        list[0].visible = !list[0].visible;
        expect(p.columns[0].visible).not.toBe(list[0].visible);
    });
});
