import { describe, it, expect } from 'vitest';
import { componiObiettivo, type RigaComponente } from './composizioneObiettivo';

// finti con le stesse chiavi/tipi delle righe vere (status/pnl/mode/sport/origin)
function riga(over: Partial<RigaComponente> = {}): RigaComponente {
    return { status: 'won', pnl: 1, mode: 'live', sport: 'calcio', origin: 'auto', ...over };
}

describe('componiObiettivo', () => {
    it('separa Omega, Safe calcio, Safe tennis, Mike, bot tennis, manuale', () => {
        const out = componiObiettivo({
            omega: [riga({ pnl: 14.2 })],
            safe: [
                riga({ pnl: 9.6, sport: 'calcio' }),
                riga({ pnl: -3, sport: 'tennis' }),
            ],
            mike: [riga({ pnl: 0.8 })],
            tennisBot: [riga({ pnl: 2, sport: 'tennis' })],
        });
        const per = Object.fromEntries(out.righe.map((r) => [r.chiave, r.valore]));
        expect(per.omega).toBe(14.2);
        expect(per.safe_calcio).toBe(9.6);
        expect(per.safe_tennis).toBe(-3);
        expect(per.mike).toBe(0.8);
        expect(per.bot_tennis).toBe(2);
        expect(per.manuale).toBeNull();
    });

    it('le righe manuali (origin=manual) sono SOTTRATTE dal loro bot e messe nel bucket Manuale, mai raddoppiate', () => {
        const out = componiObiettivo({
            omega: [riga({ pnl: 10, origin: 'auto' }), riga({ pnl: 5, origin: 'manual' })],
            safe: [],
            mike: [],
            tennisBot: [],
        });
        const per = Object.fromEntries(out.righe.map((r) => [r.chiave, r.valore]));
        expect(per.omega).toBe(10);     // solo la riga auto
        expect(per.manuale).toBe(5);    // solo la riga manuale
        expect(out.totale).toBe(15);    // la somma copre ENTRAMBE, una volta sola
    });

    it('INVARIANTE: la somma delle righe di composizione coincide col realizzato di tutte le righe insieme', () => {
        const omega = [riga({ pnl: 14.2 }), riga({ pnl: -1, origin: 'manual' })];
        const safe = [riga({ pnl: 9.6, sport: 'calcio' }), riga({ pnl: -3, sport: 'tennis', origin: 'manual' })];
        const mike = [riga({ pnl: 0.8 })];
        const tennisBot = [riga({ pnl: 2, sport: 'tennis' })];
        const out = componiObiettivo({ omega, safe, mike, tennisBot });
        const tutte = [...omega, ...safe, ...mike, ...tennisBot];
        const sommaAttesa = tutte.reduce((a, r) => a + (r.pnl ?? 0), 0);
        expect(out.totale).toBeCloseTo(sommaAttesa, 2);
    });

    it('il paper NON entra mai nel totale ed è su una riga separata', () => {
        const out = componiObiettivo({
            omega: [riga({ pnl: 14.2, mode: 'live' }), riga({ pnl: -99, mode: 'paper' })],
            safe: [], mike: [], tennisBot: [],
        });
        expect(out.totale).toBe(14.2);
        expect(out.provaPaper).toBe(-99);
    });

    it('nessuna riga per un bot = —, mai 0 (assente non è zero)', () => {
        const out = componiObiettivo({ omega: [], safe: [], mike: [], tennisBot: [] });
        for (const r of out.righe) expect(r.valore).toBeNull();
        expect(out.totale).toBeNull();
        expect(out.provaPaper).toBeNull();
    });

    it('righe sconosciute (sport assente) non finiscono ne in calcio ne in tennis di Safe', () => {
        const out = componiObiettivo({
            omega: [], mike: [], tennisBot: [],
            safe: [riga({ pnl: 5, sport: null })],
        });
        const per = Object.fromEntries(out.righe.map((r) => [r.chiave, r.valore]));
        expect(per.safe_calcio).toBeNull();
        expect(per.safe_tennis).toBeNull();
    });

    // ── FALSIFICAZIONE (documentata nel referto) ──────────────────────────
    // mutazione manuale: `eManuale` ritorna sempre `false` → il test
    // "le righe manuali sono sottratte..." diventa rosso (manuale resta
    // null, omega diventa 15 invece di 10). Verificato e ripristinato.
    it('falsificazione: una riga manuale non deve mai finire nel bucket automatico del suo bot', () => {
        const out = componiObiettivo({
            omega: [riga({ pnl: 5, origin: 'manual' })],
            safe: [], mike: [], tennisBot: [],
        });
        const per = Object.fromEntries(out.righe.map((r) => [r.chiave, r.valore]));
        expect(per.omega).toBeNull();
        expect(per.manuale).toBe(5);
    });

    // ── 18/09 (raccordo) — le DUE voci manuali fuori dai bot ──────────────
    it('manuale sito Betfair e manuale app: due righe SEPARATE, mai mischiate fra loro né col bucket "manuale" dei bot', () => {
        const out = componiObiettivo({
            omega: [riga({ pnl: 10 })], safe: [], mike: [], tennisBot: [],
            manualeSito: [riga({ pnl: 3, sport: 'calcio' })],
            manualeApp: [riga({ pnl: -1.5, sport: 'calcio' })],
        });
        const per = Object.fromEntries(out.righe.map((r) => [r.chiave, r.valore]));
        expect(per.manuale_sito).toBe(3);
        expect(per.manuale_app).toBe(-1.5);
        expect(per.manuale).toBeNull(); // bucket dei bot: nessuna riga origin=manual qui
        expect(out.totale).toBeCloseTo(11.5, 2); // 10 + 3 - 1.5
    });

    it('senza manualeSito/manualeApp (chiamante che non li passa ancora): comportamento IDENTICO a ieri', () => {
        const out = componiObiettivo({ omega: [riga({ pnl: 10 })], safe: [], mike: [], tennisBot: [] });
        const per = Object.fromEntries(out.righe.map((r) => [r.chiave, r.valore]));
        expect(per.manuale_sito).toBeNull();
        expect(per.manuale_app).toBeNull();
        expect(out.totale).toBe(10);
    });

    it('INVARIANTE estesa: la somma include anche le due voci manuali, senza doppio conteggio', () => {
        const omega = [riga({ pnl: 14.2 })];
        const manualeSito = [riga({ pnl: 3 })];
        const manualeApp = [riga({ pnl: -2 })];
        const out = componiObiettivo({
            omega, safe: [], mike: [], tennisBot: [], manualeSito, manualeApp,
        });
        const tutte = [...omega, ...manualeSito, ...manualeApp];
        const sommaAttesa = tutte.reduce((a, r) => a + (r.pnl ?? 0), 0);
        expect(out.totale).toBeCloseTo(sommaAttesa, 2);
    });
});
