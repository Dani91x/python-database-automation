// UsciteTennis.test.tsx — l'interruttore delle uscite dei bot tennis (25/09).
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { UsciteTennis } from './UsciteTennis';
import { leggiAutoTennis } from './tennisAuto';

function auto(over: Record<string, unknown> = {}) {
    return leggiAutoTennis({
        auto: {
            attivo: true, tetto: 5, armate_feed: 1, armate_a_mano: 0, seguite_a_mano: 0,
            in_attesa: 0, feed_letto: true, feed_vivo: true, feed_partite: 3,
            feed_eta_s: 2, fonte: 'safe_strategy_scan', origine_ok: true,
            live_in_dry_run: false, uscite_automatiche: true,
            uscite_sempre_automatiche: false, posizioni_aperte_manuali: 0,
            posizione_aperta_dal: null, letto_at: null, ...over,
        },
    });
}

const NOW = Date.parse('2026-09-25T10:00:00Z');

describe('UsciteTennis', () => {
    it('passare a MANUALI chiede conferma (primo clic non scrive)', async () => {
        const scrivi = vi.fn(async () => ({}));
        render(<UsciteTennis botKey="tennis_flb" auto={auto()} nowMs={NOW} scrivi={scrivi} />);
        fireEvent.click(screen.getByTestId('cr-uscite-manuali-tennis_flb'));
        expect(scrivi).not.toHaveBeenCalled();
        fireEvent.click(screen.getByTestId('cr-uscite-conferma-tennis_flb'));
        await waitFor(() => expect(scrivi).toHaveBeenCalledWith('tennis_flb', false));
    });

    it('tornare ad AUTOMATICHE non chiede niente', async () => {
        const scrivi = vi.fn(async () => ({}));
        render(<UsciteTennis botKey="tennis_pro" auto={auto({ uscite_automatiche: false })}
            nowMs={NOW} scrivi={scrivi} />);
        fireEvent.click(screen.getByTestId('cr-uscite-automatiche-tennis_pro'));
        await waitFor(() => expect(scrivi).toHaveBeenCalledWith('tennis_pro', true));
    });

    it('a uscite manuali l\'avviso e\' SEMPRE visibile', () => {
        render(<UsciteTennis botKey="tennis_swing" auto={auto({
            uscite_automatiche: false, posizioni_aperte_manuali: 1,
            posizione_aperta_dal: '2026-09-25T09:55:00Z',
        })} nowMs={NOW} />);
        expect(screen.getByTestId('cr-uscite-avviso-tennis_swing').textContent).toBe(
            'uscite manuali: posizione aperta da 5 min — chiudi con «Chiudi» dalla scheda partita');
    });

    it('scalper: nessun interruttore, detto in chiaro', () => {
        render(<UsciteTennis botKey="tennis_scalper" auto={auto({ uscite_sempre_automatiche: true })}
            nowMs={NOW} />);
        expect(screen.getByTestId('cr-uscite-tennis_scalper').textContent).toBe('uscite: sempre automatiche');
        expect(screen.queryByTestId('cr-uscite-manuali-tennis_scalper')).toBeNull();
    });

    it('colonna assente (non dichiarato): niente interruttore', () => {
        const { container } = render(<UsciteTennis botKey="tennis_flb"
            auto={auto({ uscite_automatiche: null })} nowMs={NOW} />);
        expect(container.textContent).toBe('');
    });

    it('errore della RPC: lo dice, lo stato resta quello del servizio', async () => {
        const scrivi = vi.fn(async () => { throw new Error('non autorizzato (owner-only)'); });
        render(<UsciteTennis botKey="tennis_flb" auto={auto({ uscite_automatiche: false })}
            nowMs={NOW} scrivi={scrivi} />);
        fireEvent.click(screen.getByTestId('cr-uscite-automatiche-tennis_flb'));
        await waitFor(() => expect(screen.getByTestId('cr-uscite-errore-tennis_flb').textContent)
            .toBe('non salvato: non autorizzato (owner-only)'));
        expect(screen.getByTestId('cr-uscite-automatiche-tennis_flb')).toBeTruthy();
    });
});
