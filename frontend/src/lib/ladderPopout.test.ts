// ============================================================================
// ladderPopout.test.ts - 08/10 (cantiere W1): la finestra del ladder di un
// mercato, con la STESSA ricetta del bottone «stacca» del LadderView (B19).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { apriLadderPopout, urlLadderPopout, nomeFinestraLadder, FINESTRA_LADDER_POPOUT } from './ladderPopout';

describe('ladder pop-out', () => {
    it('indirizzo: parametri e ordine del LadderView, gli assenti omessi', () => {
        expect(urlLadderPopout({
            sport: 'tennis', marketId: '1.250', eventId: '34000001', marketName: 'Match Odds',
            eventName: 'Sinner v Alcaraz', p1: 'Sinner', p2: 'Alcaraz',
        })).toBe('/ladder-popout?sport=tennis&market=1.250&event=34000001&name=Match+Odds&eventName=Sinner+v+Alcaraz&p1=Sinner&p2=Alcaraz');
        expect(urlLadderPopout({ sport: 'calcio', marketId: '1.9', eventId: null, marketName: '' }))
            .toBe('/ladder-popout?sport=calcio&market=1.9');
    });

    it('finestra: nome ladder_<marketId>, 560x860 come il LadderView', () => {
        expect(nomeFinestraLadder('1.250')).toBe('ladder_1.250');
        expect(FINESTRA_LADDER_POPOUT).toBe('popup=yes,width=560,height=860,resizable=yes,scrollbars=yes');
        const apri = vi.spyOn(window, 'open').mockImplementation(() => null);
        expect(apriLadderPopout({ sport: 'calcio', marketId: '1.9', eventId: 'E' })).toBe(false);
        expect(apri).toHaveBeenCalledWith('/ladder-popout?sport=calcio&market=1.9&event=E', 'ladder_1.9',
            'popup=yes,width=560,height=860,resizable=yes,scrollbars=yes');
        apri.mockRestore();
    });

    it('la ricetta e\' quella del LadderView (stesse misure e stesso nome nel sorgente del bottone «stacca»)', () => {
        const lv = readFileSync(join(__dirname, '..', 'components', 'live', 'LadderView.tsx'), 'utf-8');
        expect(lv).toContain(`'${FINESTRA_LADDER_POPOUT}'`);
        expect(lv).toContain('`ladder_${marketId}`');
        expect(lv).toContain('window.open(`/ladder-popout?${q.toString()}`');
    });
});
