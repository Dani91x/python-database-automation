// ============================================================================
// ProposteUsciteFlusso.test.tsx - 28/09 (CANTIERE N): le uscite da approvare
// dei bot di flusso. Le proposte sono costruite con le CHIAVI VERE che il bot
// scrive (`Betfair/stream/uscite_proposte.proposta_di` + `chiave`, `decided_at`,
// `proposed_at`; il ponte tennis aggiunge `event_id`).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: (...a: unknown[]) => rpc(...a), from: vi.fn(), channel: vi.fn() },
}));

import { ProposteUsciteFlusso } from './ProposteUsciteFlusso';
import { leggiProposteFlusso, approvaPropostaFlusso, type PropostaFlusso } from '@/lib/proposteUscite';

/** Una proposta come la scrive il bot (chiavi Python, snake_case). */
function grezza(over: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        bot: 'tennis_swing', motivo: 'stop', urgente: true, market_id: '1.23', selection_id: 111,
        lato_ingresso: 'BACK', prezzo: 1.62, lato_chiusura: 'LAY', size_chiusura: 1.85,
        se_chiudi: -0.15, se_vince: 1.0, se_perde: -2.0,
        chiave: 'tennis_swing|1.23|111|1000|stop', decided_at: 1_790_000_000, proposed_at: 1_790_000_005,
        event_id: '345', ...over,
    };
}

beforeEach(() => { vi.clearAllMocks(); rpc.mockResolvedValue({ data: {}, error: null }); });

describe('leggiProposteFlusso', () => {
    it('dalle chiavi del bot ai nomi della pagina', () => {
        const [p] = leggiProposteFlusso([grezza()]);
        expect(p).toMatchObject({
            chiave: 'tennis_swing|1.23|111|1000|stop', bot: 'tennis_swing', motivo: 'stop',
            urgente: true, eventId: '345', marketId: '1.23', selectionId: 111,
            latoChiusura: 'LAY', sizeChiusura: 1.85, prezzo: 1.62, seChiudi: -0.15,
            seVince: 1.0, sePerde: -2.0, decidedAt: 1_790_000_000,
        });
    });
    it('scalper: la partita viene dalla sessione; righe storte scartate', () => {
        const out = leggiProposteFlusso([
            grezza({ bot: 'scalper', chiave: 'scalper|1.9|7|x|target', event_id: undefined }),
            null, 'x', { motivo: 'stop' },
        ], '999');
        expect(out.map((p) => [p.bot, p.eventId])).toEqual([['scalper', '999']]);
        expect(leggiProposteFlusso(undefined)).toEqual([]);
    });
});

describe('approvaPropostaFlusso: la RPC del bot giusto', () => {
    it('tennis -> tennis_bot_approva_uscita con evento, bot e chiave', async () => {
        await approvaPropostaFlusso({ bot: 'tennis_pro', eventId: '1', chiave: 'tennis_pro|a|1|2|stop' });
        expect(rpc).toHaveBeenCalledWith('tennis_bot_approva_uscita',
            { p_event_id: '1', p_bot_key: 'tennis_pro', p_chiave: 'tennis_pro|a|1|2|stop' });
    });
    it('scalper -> scalper_approva_uscita', async () => {
        await approvaPropostaFlusso({ bot: 'scalper', eventId: '9', chiave: 'scalper|1.9|7|x|stop' });
        expect(rpc).toHaveBeenCalledWith('scalper_approva_uscita', { p_event_id: '9', p_chiave: 'scalper|1.9|7|x|stop' });
    });
    it('sniper (stessa sessione dello scalper) -> scalper_approva_uscita', async () => {
        await approvaPropostaFlusso({ bot: 'sniper', eventId: '9', chiave: 'scalper|1.2|3|sn-o1|stop' });
        expect(rpc).toHaveBeenCalledWith('scalper_approva_uscita', { p_event_id: '9', p_chiave: 'scalper|1.2|3|sn-o1|stop' });
    });
    it('errore della RPC (migrazione non applicata): si dice, niente parte', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'function does not exist' } });
        await expect(approvaPropostaFlusso({ bot: 'scalper', eventId: '9', chiave: 'k' }))
            .rejects.toThrow('function does not exist');
    });
});

describe('ProposteUsciteFlusso - che cosa si vede e che cosa parte', () => {
    it('niente proposte: niente scheda', () => {
        const s = render(<ProposteUsciteFlusso proposte={[]} nowMs={0} />);
        expect(s.queryByTestId('cr-proposte-flusso')).toBeNull();
    });

    it('i numeri: cosa chiude, a che prezzo, se chiudi ora, se tieni', () => {
        const p = leggiProposteFlusso([grezza()]);
        const s = render(<ProposteUsciteFlusso proposte={p} nowMs={1_790_000_030_000} />);
        expect(s.getByTestId('cr-proposte-flusso-titolo').textContent)
            .toContain('stop (in perdita)');
        expect(s.getByTestId('cr-proposte-flusso-titolo').textContent).toContain('deciso 30 s fa');
        expect(s.getByTestId('cr-proposte-flusso-ordine').textContent).toContain('chiude LAY');
        expect(s.getByTestId('cr-proposte-flusso-ordine').textContent).toMatch(/1[.,]62/);
        const numeri = s.getByTestId('cr-proposte-flusso-numeri').textContent ?? '';
        expect(numeri).toContain('se chiudi ora');
        expect(numeri).toContain('se tieni');
    });

    it('"approva uscita" firma QUELLA proposta e lo dice', async () => {
        const approva = vi.fn(async (_p: PropostaFlusso) => {});
        const p = leggiProposteFlusso([grezza(), grezza({ chiave: 'tennis_swing|1.23|111|1000|time', motivo: 'time' })]);
        const s = render(<ProposteUsciteFlusso proposte={p} nowMs={0} approva={approva} />);
        const bottoni = s.getAllByTestId('cr-proposte-flusso-approva');
        await act(async () => { fireEvent.click(bottoni[1]); });
        expect(approva).toHaveBeenCalledTimes(1);
        expect(approva.mock.calls[0]?.[0]?.chiave).toBe('tennis_swing|1.23|111|1000|time');
        expect(s.getByTestId('cr-proposte-flusso-esito').textContent).toContain('se la condizione vale ancora');
    });
});
