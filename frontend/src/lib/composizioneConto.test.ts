// ============================================================================
// composizioneConto.test.ts - P7 (30/09): con il conto letto, il realizzato
// LIVE di ogni bot viene da `pnl_reale_oggi.per_fonte` (attribuzione del
// backend), non dalle righe che la pagina ha caricato. Una posizione LIVE di
// Mike piazzata IERI e regolata OGGI (che `get_mike_state` non porta) finisce
// sotto Mike, non in «Altro sul conto Betfair».
//
// Il finto del conto ha la forma di `leggiPnlRealeOggi` (colonna JSONB
// `betfair_live_account.pnl_reale_oggi`: day, netto, ordini, per_fonte{9 voci
// {netto, ordini}}, bet_ids, senza_commissione, sospetti_sito, letto_at).
// ============================================================================
import { describe, expect, it } from 'vitest';
import {
    componiObiettivo, differenzaContoRighe, leggiPnlRealeOggi, rigaSintetica,
    type PnlRealeOggi, type RigaComponente,
} from './composizioneObiettivo';
import { composizioneDalConto, perSportDalConto } from './composizioneConto';

const OGGI = '2026-09-30';

function conto(perFonte: Partial<Record<string, { netto: number; ordini: number }>>): PnlRealeOggi {
    const zero = { netto: 0, ordini: 0 };
    const pf = {
        omega: zero, safe_calcio: zero, safe_tennis: zero, mike: zero, bot_tennis: zero,
        manuale_app: zero, manuale_sito: zero, altri_bot: zero, scalper: zero, ...perFonte,
    };
    const netto = Object.values(pf).reduce((s, v) => s + (v?.netto ?? 0), 0);
    return leggiPnlRealeOggi({
        day: OGGI, netto, ordini: 1, per_fonte: pf, bet_ids: ['3900001'],
        senza_commissione: 0, sospetti_sito: 0, letto_at: `${OGGI}T12:41:00+00:00`,
    }, OGGI)!;
}

/** come fa il hook con il conto letto: «Altro» = altri_bot + differenza conto-righe */
function composizioneDiOggi(c: PnlRealeOggi, righe: { omega: RigaComponente[]; safe: RigaComponente[]; mike: RigaComponente[] }) {
    const diff = differenzaContoRighe(c, [...righe.omega, ...righe.safe, ...righe.mike]);
    const altri = c.per_fonte.altri_bot.ordini > 0 ? c.per_fonte.altri_bot.netto : null;
    const altro = (altri != null || Math.abs(diff) >= 0.005) ? Math.round(((altri ?? 0) + diff) * 100) / 100 : null;
    const r = altro == null ? null : rigaSintetica(altro, null, { sport: 'calcio' });
    return componiObiettivo({ ...righe, tennisBot: [], altro: r ? [r] : [] });
}

describe('W_G: perSportDalConto - il LIVE per sport dalle voci del conto', () => {
    it('calcio = Mike+Omega+Safe calcio+Scalper; tennis = Safe tennis+bot tennis; manuali/altri fuori', () => {
        const c = conto({
            mike: { netto: 2, ordini: 1 }, omega: { netto: -0.5, ordini: 1 }, scalper: { netto: 0.1, ordini: 2 },
            safe_calcio: { netto: 0.3, ordini: 1 }, safe_tennis: { netto: 0.41, ordini: 1 },
            bot_tennis: { netto: -0.2, ordini: 3 }, manuale_sito: { netto: 5, ordini: 1 }, altri_bot: { netto: 1, ordini: 1 },
        });
        // 04/10: runner senza `per_sport` -> gli ordini a mano (+5) si DICHIARANO fuori dalle tessere
        expect(perSportDalConto(c)).toEqual({
            calcio: { pnl: 1.9, ordini: 5, aManoNonSeparato: 5 },
            tennis: { pnl: 0.21, ordini: 4, aManoNonSeparato: 5 },
        });
    });
    it('Safe TENNIS di ieri regolato oggi: nel tennis, non nel calcio (il difetto della «differenza» nel calcio)', () => {
        const c = conto({ safe_tennis: { netto: 0.41, ordini: 1 } });
        expect(perSportDalConto(c)).toEqual({
            calcio: { pnl: 0, ordini: 0, aManoNonSeparato: null },
            tennis: { pnl: 0.41, ordini: 1, aManoNonSeparato: null },
        });
    });
    it('conto non letto: null', () => {
        expect(perSportDalConto(null)).toBeNull();
    });
});

describe('composizioneDalConto - la voce del bot dal conto', () => {
    it('Mike: posizione di IERI regolata OGGI (riga non caricata) -> sotto Mike, non in «Altro»', () => {
        const c = conto({ mike: { netto: 2.0, ordini: 1 } });
        const righe = { omega: [], safe: [], mike: [] };
        const base = composizioneDiOggi(c, righe);
        // PRIMA: la voce di Mike vuota e i 2,00 in «Altro sul conto»
        expect(base.righe.find((r) => r.chiave === 'mike')!.valore).toBeNull();
        expect(base.righe.find((r) => r.chiave === 'altro')!.valore).toBe(2);
        const dopo = composizioneDalConto(base, c, righe);
        const mike = dopo.righe.find((r) => r.chiave === 'mike')!;
        expect(mike.valore).toBe(2);
        expect(mike.fonte).toBe('conto');
        expect(dopo.righe.find((r) => r.chiave === 'altro')!.valore).toBeNull();
        // il totale non cambia: stessi soldi, voce giusta
        expect(dopo.totale).toBe(base.totale);
    });

    it('reale dal conto + stimato del bot (chiuso dal bot, Betfair non ha regolato), dichiarato', () => {
        const c = conto({ mike: { netto: 1.5, ordini: 1 } });
        const stimata: RigaComponente = {
            status: 'won', pnl: 0.4, mode: 'live', sport: 'calcio', origin: 'auto', pnlReale: null, pnlStimato: 0.4,
        };
        const regolata: RigaComponente = {
            status: 'won', pnl: 1.5, mode: 'live', sport: 'calcio', origin: 'auto', pnlReale: 1.5, pnlStimato: null,
        };
        const righe = { omega: [], safe: [], mike: [regolata, stimata] };
        const base = composizioneDiOggi(c, righe);
        const dopo = composizioneDalConto(base, c, righe);
        const mike = dopo.righe.find((r) => r.chiave === 'mike')!;
        expect(mike).toMatchObject({ valore: 1.9, reale: 1.5, stimato: 0.4, fonte: 'conto' });
        expect(dopo.totale).toBe(base.totale);
    });

    it('Safe calcio e tennis separati per voce del conto; paper mai dentro', () => {
        const c = conto({ safe_calcio: { netto: -0.9, ordini: 2 }, safe_tennis: { netto: 0.41, ordini: 1 } });
        const paper: RigaComponente = { status: 'won', pnl: 7.6, mode: 'paper', sport: 'calcio', origin: 'auto' };
        const righe = { omega: [], safe: [paper], mike: [] };
        const dopo = composizioneDalConto(composizioneDiOggi(c, righe), c, righe);
        expect(dopo.righe.find((r) => r.chiave === 'safe_calcio')!.valore).toBe(-0.9);
        expect(dopo.righe.find((r) => r.chiave === 'safe_tennis')!.valore).toBe(0.41);
        expect(dopo.totale).toBe(-0.49);
    });

    it('0 ordini sul conto e nessuna riga: la voce resta «—» (null), mai 0,00 inventato', () => {
        const c = conto({});
        const righe = { omega: [], safe: [], mike: [] };
        const dopo = composizioneDalConto(composizioneDiOggi(c, righe), c, righe);
        expect(dopo.righe.find((r) => r.chiave === 'omega')!.valore).toBeNull();
        expect(dopo.dalConto).toBe(true);
    });

    it('conto NON letto: la composizione di prima, invariata (ripiego dichiarato sulle righe)', () => {
        const regolata: RigaComponente = { status: 'won', pnl: 1.5, mode: 'live', sport: 'calcio', origin: 'auto' };
        const base = componiObiettivo({ omega: [], safe: [], mike: [regolata], tennisBot: [] });
        const dopo = composizioneDalConto(base, null, { omega: [], safe: [], mike: [regolata] });
        expect(dopo.dalConto).toBe(false);
        expect(dopo.righe.map((r) => r.valore)).toEqual(base.righe.map((r) => r.valore));
        expect(dopo.righe.find((r) => r.chiave === 'mike')!.fonte).toBe('bot');
    });
});
