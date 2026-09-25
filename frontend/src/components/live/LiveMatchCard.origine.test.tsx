// 25/09 AUTO-FOLLOW: la card del follow dice CHI lo ha chiesto (manuale = "Segui
// live" dell'utente, auto = il runner la segue da solo per i bot). Riga con le
// chiavi vere di get_live_follows (migrazione live_follow_origine_2026-09-25.sql).
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', () => ({ supabase: {} }));

import { LiveMatchCard } from './LiveMatchCard';
import type { LiveFollow } from '@/lib/live';

function riga(origine: LiveFollow['origine']): LiveFollow {
    return {
        event_id: '35760084', fixture_id: null, league_name: 'Serie A',
        home_name: 'Casa', away_name: 'Ospiti', open_date: '2026-09-25T16:00:00Z',
        status: 'STREAMING', error_detail: null, inplay: true, minute: 12,
        score_home: 0, score_away: 0, live_status: 'OPEN', score_source: 'betfair',
        updated_at: null, origine,
    };
}

describe('LiveMatchCard - origine del follow (auto-follow 25/09)', () => {
    it('auto: badge "auto" con la spiegazione', () => {
        render(<LiveMatchCard follow={riga('auto')} />);
        const b = screen.getByTestId('origine-follow');
        expect(b.textContent).toBe('auto');
        expect(b.getAttribute('title')).toContain('DA SOLA');
    });

    it('manuale e colonna assente (prima della migrazione): "manuale"', () => {
        const { unmount } = render(<LiveMatchCard follow={riga('manuale')} />);
        expect(screen.getByTestId('origine-follow').textContent).toBe('manuale');
        unmount();
        render(<LiveMatchCard follow={riga(undefined)} />);
        expect(screen.getByTestId('origine-follow').textContent).toBe('manuale');
    });
});
