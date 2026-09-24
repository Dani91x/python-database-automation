// ============================================================================
// TennisBotPanel.test.tsx — gate ordini reali per bot (armamento singolo).
//
// Il gate money-critical vive in handleArm (TennisBotPanel.tsx:498-537): con
// orderMode LIVE e checkbox "dry-run" tolta, un window.confirm chiede
// conferma prima di chiamare armTennisBot; se negato l'ordine reale NON parte.
// In PAPER (sempre simulato per costruzione) e in LIVE con dry-run selezionato
// (default prudente) nessuna conferma nativa e' richiesta.
//
// NOTA PER IL COORDINATORE: il brief parlava di un "doppio gate" (DUE
// window.confirm). Letto il sorgente (TennisBotPanel.tsx:498-537) esiste UN
// solo window.confirm, non due — verificato con `grep -n "confirm(" `, un solo
// riscontro. Questi test certificano il gate SINGOLO realmente presente; non
// ho aggiunto un secondo confirm al componente (layout/logica UI intoccabile
// senza permesso esplicito dell'utente). Segnalare la discrepanza.
//
// I FINTI PARLANO COME IL VERO: default e parametri vengono da
// TENNIS_BOT_REGISTRY (lib/tennis.ts), non duplicati a mano.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/tennis', async () => {
    const actual = await vi.importActual<typeof import('@/lib/tennis')>('@/lib/tennis');
    return {
        ...actual,
        fetchTennisBotsState: vi.fn(async () => ({ controls: [], activity: [] })),
        subscribeTennisBots: vi.fn(() => () => { /* no-op unsub */ }),
        armTennisBot: vi.fn(async (
            eventId: string,
            botKey: string,
            dryRun: boolean,
            stake: number,
            params: Record<string, number | string | boolean>,
        ) => ({
            event_id: eventId,
            bot_key: botKey,
            status: 'armed',
            dry_run: dryRun,
            stake,
            params,
            stats: null,
            error: null,
            requested_at: null,
            started_at: null,
            stopped_at: null,
            heartbeat_at: null,
        })),
        disarmTennisBot: vi.fn(async (eventId: string, botKey: string) => ({
            event_id: eventId,
            bot_key: botKey,
            status: 'stopping',
            dry_run: true,
            stake: 0,
            params: {},
            stats: null,
            error: null,
            requested_at: null,
            started_at: null,
            stopped_at: null,
            heartbeat_at: null,
        })),
    };
});

import { TennisBotPanel } from './TennisBotPanel';
import { armTennisBot, TENNIS_BOT_REGISTRY } from '@/lib/tennis';

const mArm = vi.mocked(armTennisBot);

const SCALPER = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_scalper')!;

// payload atteso quando NESSUN parametro e' stato toccato: identico a
// descriptor.defaults ma con i campi bool ('on'/'off' -> true/false), esattamente
// come fa handleToggle in TennisBotPanel.tsx:161-166 (i finti parlano come il vero:
// derivato dal registro, non ricopiato a mano).
function payloadDefaultAtteso(): Record<string, number | string | boolean> {
    const payload: Record<string, number | string | boolean> = { ...SCALPER.defaults };
    for (const f of SCALPER.params) {
        if (f.type === 'select' && f.bool) payload[f.key] = payload[f.key] === 'on';
    }
    return payload;
}

async function montaPannello(orderMode: 'OFF' | 'PAPER' | 'LIVE') {
    const user = userEvent.setup();
    render(<TennisBotPanel eventId="evt1" marketId="mkt1" orderMode={orderMode} />);
    await screen.findByText('Tennis Scalper');
    const cardEl = screen.getByText('Tennis Scalper').closest('div.rounded-xl.border') as HTMLElement;
    return { user, card: within(cardEl) };
}

beforeEach(() => {
    vi.clearAllMocks();
});

describe('TennisBotPanel — gate ordini reali (tennis_scalper)', () => {
    it('1) servizio PAPER: ARMA senza toccare nulla -> nessuna conferma, arma con dry_run=false (PAPER e\' sempre simulato)', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('PAPER');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', false, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    it('2) servizio LIVE, checkbox dry-run NON tolta (default prudente): ARMA senza conferma, dry_run=true', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm');
        const { user, card } = await montaPannello('LIVE');
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'checked');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', true, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    it('3) servizio LIVE, checkbox dry-run TOLTA: ARMA chiede conferma; negata -> NON arma con ordini reali', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
        const { user, card } = await montaPannello('LIVE');
        await user.click(card.getByRole('checkbox')); // toglie il dry-run
        expect(card.getByRole('checkbox')).toHaveAttribute('data-state', 'unchecked');
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        expect(confirmSpy).toHaveBeenCalledTimes(1);
        expect(String(confirmSpy.mock.calls[0][0])).toMatch(/ORDINI REALI/i);
        expect(mArm).not.toHaveBeenCalled();
    });

    it('4) servizio LIVE, checkbox dry-run TOLTA, conferma ACCETTATA: arma con dry_run=false esplicito', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
        const { user, card } = await montaPannello('LIVE');
        await user.click(card.getByRole('checkbox'));
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        expect(confirmSpy).toHaveBeenCalledTimes(1);
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        expect(mArm).toHaveBeenCalledWith('evt1', 'tennis_scalper', false, SCALPER.defaultStake, payloadDefaultAtteso());
    });

    it('5) armTennisBot riceve gli argomenti nel TIPO esatto (dry_run booleano, non stringa \'on\'/\'off\')', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const { user, card } = await montaPannello('LIVE');
        await user.click(card.getByRole('checkbox'));
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        const [eventId, botKey, dryRun, stake, params] = mArm.mock.calls[0];
        expect(eventId).toBe('evt1');
        expect(botKey).toBe('tennis_scalper');
        expect(typeof dryRun).toBe('boolean');
        expect(dryRun).toBe(false);
        expect(typeof stake).toBe('number');
        const p = params as Record<string, unknown>;
        expect(typeof p.one_tick_per_phase).toBe('boolean');
        expect(p.one_tick_per_phase).not.toBe('on');
        expect(p.one_tick_per_phase).not.toBe('off');
    });
});
