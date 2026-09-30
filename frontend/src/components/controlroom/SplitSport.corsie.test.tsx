// ============================================================================
// SplitSport.corsie.test.tsx - P2 (30/09), il CONFINE live/paper della tessera.
//
// Ogni corsia legge SOLO il suo dato: la LIVE `perSport`, la PROVA
// `perSportPaper`, cifra e contatori compresi. Richiesto dal coordinatore
// dopo una sua mutazione sopravvissuta (PROVA che leggeva il dato LIVE).
// Finti con la forma vera di `DailyBreakdown` ({ n, pnl, won, lost }).
//
// FALSIFICAZIONE: in SplitSport `<Corsia tipo="prova" ... dato={dato}>` (la
// PROVA legge il live) -> rossi; `<Corsia tipo="live" ... dato={datoPaper}>`
// (la LIVE legge il paper) -> rossi.
// ============================================================================
import { describe, expect, it } from 'vitest';
import { render, within } from '@testing-library/react';
import { SplitSport } from './SplitSport';

const LIVE = { n: 3, pnl: 1.5, won: 2, lost: 1 };
const PAPER = { n: 4, pnl: -2.2, won: 1, lost: 3 };

function tessera(perSport: Record<string, typeof LIVE>, perSportPaper: Record<string, typeof LIVE>) {
    const s = render(<SplitSport selezionato={null} onSeleziona={() => undefined}
        perSport={perSport} perSportPaper={perSportPaper} />);
    const calcio = s.getByTestId('cr-sport-calcio');
    return {
        live: within(calcio).getByTestId('cr-sport-calcio-live'),
        prova: within(calcio).getByTestId('cr-sport-calcio-prova'),
        livePnl: within(calcio).getByTestId('cr-sport-calcio-live-pnl').textContent,
        provaPnl: within(calcio).getByTestId('cr-sport-calcio-prova-pnl').textContent,
    };
}

describe('W_G (30/09): la corsia LIVE dal CONTO quando letto', () => {
    it('conto letto: LIVE = voce del conto (non le righe), marchio CONTO con eta\'; 0 ordini = 0,00 dichiarato', () => {
        const s = render(<SplitSport selezionato={null} onSeleziona={() => undefined}
            perSport={{ calcio: LIVE }} perSportPaper={{}} contoEtaS={180}
            perSportConto={{ calcio: { pnl: 2, ordini: 1 }, tennis: { pnl: 0, ordini: 0 } }} />);
        const calcio = s.getByTestId('cr-sport-calcio');
        expect(within(calcio).getByTestId('cr-sport-calcio-live-pnl').textContent).toBe('+2,00 €');
        expect(within(calcio).getByTestId('cr-sport-calcio-live-fonte').getAttribute('data-fonte')).toBe('conto');
        expect(within(calcio).getByTestId('cr-sport-calcio-live-fonte').textContent).toContain('3 min fa');
        expect(within(calcio).getByTestId('cr-sport-calcio-live-conto').textContent).toBe('1 ordine regolato oggi');
        // le righe dei bot (1,50) non sono la cifra LIVE quando c'e' il conto
        expect(within(calcio).getByTestId('cr-sport-calcio-live').textContent).not.toContain('1,50');
        const tennis = s.getByTestId('cr-sport-tennis');
        expect(within(tennis).getByTestId('cr-sport-tennis-live-pnl').textContent).toBe('+0,00 €');
        expect(within(tennis).getByTestId('cr-sport-tennis-live-conto').textContent).toBe('nessuna operazione regolata oggi');
    });

    it('conto NON letto: le righe dei bot col marchio BOT (come prima)', () => {
        const s = render(<SplitSport selezionato={null} onSeleziona={() => undefined}
            perSport={{ calcio: LIVE }} perSportPaper={{}} perSportConto={null} />);
        expect(s.getByTestId('cr-sport-calcio-live-pnl').textContent).toBe('+1,50 €');
        expect(s.getByTestId('cr-sport-calcio-live-fonte').getAttribute('data-fonte')).toBe('bot');
    });
});

describe('tessera sport: ogni corsia legge SOLO il suo dato', () => {
    it('live e paper diversi: LIVE mostra solo il live, PROVA solo il paper, contatori compresi', () => {
        const t = tessera({ calcio: LIVE }, { calcio: PAPER });
        expect(t.livePnl).toBe('+1,50 €');
        expect(t.provaPnl).toBe('−2,20 €');
        const live = t.live.textContent ?? '';
        const prova = t.prova.textContent ?? '';
        expect(live).toContain('3 operazioni');
        expect(live).toContain('2 V');
        expect(live).toContain('1 P');
        expect(live).not.toContain('2,20');
        expect(live).not.toContain('4 operazioni');
        expect(prova).toContain('4 operazioni');
        expect(prova).toContain('1 V');
        expect(prova).toContain('3 P');
        expect(prova).not.toContain('1,50');
        expect(prova).not.toContain('3 operazioni');
    });

    it('solo il paper presente: la LIVE e\' 0,00 senza operazioni, la PROVA porta il paper', () => {
        const t = tessera({}, { calcio: PAPER });
        expect(t.livePnl).toBe('+0,00 €');
        expect(t.live.textContent).toContain('nessuna operazione con soldi veri oggi');
        expect(t.provaPnl).toBe('−2,20 €');
        expect(t.prova.textContent).toContain('4 operazioni');
    });

    it('solo il live presente: la PROVA e\' 0,00 senza operazioni, la LIVE porta il live', () => {
        const t = tessera({ calcio: LIVE }, {});
        expect(t.provaPnl).toBe('+0,00 €');
        expect(t.prova.textContent).toContain('nessuna operazione in prova oggi');
        expect(t.livePnl).toBe('+1,50 €');
        expect(t.live.textContent).toContain('3 operazioni');
    });
});
