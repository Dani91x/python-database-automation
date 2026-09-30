// ============================================================================
// SchedaMike.test.tsx — copre il badge di FRESCHEZZA DEL FEED (18/09), nato
// dal difetto certificato il 13/09 (chiusura su prezzi vecchi credendoli di
// adesso): stesse funzioni e soglie di `MikeMatchCard.tsx`, mai una seconda
// formula. Ogni test qui e' stato FALSIFICATO (vedi CHECKPOINT).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SchedaMike } from './SchedaMike';
import type { MikeEvent } from '@/lib/mike';

function ev(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date(Date.now() + 3600_000).toISOString(), mode: 'paper', markets: {}, state: 'WATCH',
        cycle_no: 0, entry_price_initial: null, dossier: null, live: null, positions: [], ctx: null,
        skipped: false, settled_pnl: null, updated_at: new Date().toISOString(), ...over,
    };
}

describe('SchedaMike — freschezza del feed (cert. 13/09)', () => {
    it('feed vecchio (>20s) mostra il badge rosso FEED FERMO', () => {
        render(<SchedaMike ev={ev({ live: { feed_age_s: 45 } as MikeEvent['live'] })} />);
        const badge = screen.getByTestId('cr-mike-feed-age');
        expect(badge).toHaveTextContent('FEED FERMO (45 s)');
        expect(badge.className).toMatch(/red/);
    });

    it('feed fresco (<=5s) mostra il badge verde con i secondi', () => {
        render(<SchedaMike ev={ev({ live: { feed_age_s: 2 } as MikeEvent['live'] })} />);
        const badge = screen.getByTestId('cr-mike-feed-age');
        expect(badge).toHaveTextContent('feed 2 s');
        expect(badge.className).toMatch(/emerald/);
    });

    it('feed intermedio (<=20s) mostra il badge ambra', () => {
        render(<SchedaMike ev={ev({ live: { feed_age_s: 12 } as MikeEvent['live'] })} />);
        const badge = screen.getByTestId('cr-mike-feed-age');
        expect(badge).toHaveTextContent('feed 12 s');
        expect(badge.className).toMatch(/amber/);
    });

    it('nessun dato di eta pubblicato: badge "nessun dato", MAI verde/fresco', () => {
        render(<SchedaMike ev={ev({ live: {} as MikeEvent['live'] })} />);
        const badge = screen.getByTestId('cr-mike-feed-age');
        expect(badge).toHaveTextContent('FEED: NESSUN DATO');
        expect(badge.className).not.toMatch(/emerald/);
    });

    it('partita CHIUSA (SETTLED): "partita chiusa", MAI il rosso FEED FERMO — nessun falso allarme', () => {
        render(<SchedaMike ev={ev({
            state: 'SETTLED', settled_pnl: 3.2,
            live: { feed_age_s: 9999 } as MikeEvent['live'],
        })} />);
        const badge = screen.getByTestId('cr-mike-feed-age');
        expect(badge).toHaveTextContent('partita chiusa');
        expect(badge).not.toHaveTextContent('FEED FERMO');
    });

    it('partita in ERROR/SKIPPED: stesso trattamento terminale, nessun allarme di feed', () => {
        render(<SchedaMike ev={ev({ state: 'ERROR', live: { feed_age_s: 500 } as MikeEvent['live'] })} />);
        expect(screen.getByTestId('cr-mike-feed-age')).toHaveTextContent('partita chiusa');
    });

    it('30/09 A3: la linea 4.5 mostra l\'Under (copertura di serie, banca) E l\'Over (chiusura), senza "(la copertura)" sull\'Over', () => {
        const live = {
            books: {
                'OU45|UNDER': { best_back: 1.17, best_lay: 1.18 },
                'OU45|OVER': { best_back: 9.4, best_lay: 10 },
            },
        } as unknown as MikeEvent['live'];
        render(<SchedaMike ev={ev({ live })} />);
        const u45 = screen.getByTestId('cr-mike-u45');
        const o45 = screen.getByTestId('cr-mike-o45');
        expect(u45).toHaveTextContent('Under 4.5');
        expect(u45).toHaveTextContent('1,17');
        expect(u45.getAttribute('title')).toMatch(/banca Under 4.5/);
        expect(o45).toHaveTextContent('Over 4.5');
        expect(o45.getAttribute('title')).toContain('chiusura della copertura');
        expect(o45.getAttribute('title')).not.toContain('(la copertura)');
        expect(screen.getByTestId('cr-mike-p4-mercato').getAttribute('title'))
            .toMatch(/perdono l.Under 3,5 e la copertura/);
    });

    it('testId personalizzato si propaga al badge di eta', () => {
        render(<SchedaMike ev={ev({ live: { feed_age_s: 1 } as MikeEvent['live'] })} testId="foo" />);
        expect(screen.getByTestId('foo-feed-age')).toBeInTheDocument();
    });
});
