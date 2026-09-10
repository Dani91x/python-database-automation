// Test COMPONENTE del pannello parametri del bot: sezioni Rischio / Auto-trade /
// Uscite modello / Tennis-Anomalie, e il merge dei parametri grezzi al salvataggio
// (chiavi ignote preservate, exits e risk sempre espliciti).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BotParamsSheet, mergeExits, EXITS_DEFAULTS } from './BotParamsSheet';
import { mergeBotParams } from '@/lib/safeBot';

const RAW = {
    commission_pct: 5,
    auto_trade_combos: true,
    risk: { daily_liability_cap: 800, daily_loss_stop: -30 },
    exits: { enabled: true, hold_max_risk: 0.03, model_take_profit_frac: 0.7 },
    unknown_key_from_service: { keep: 'me' },
};

async function openSheet(onSave = vi.fn()) {
    const user = userEvent.setup();
    render(<BotParamsSheet params={mergeBotParams(RAW)} rawParams={RAW} onSave={onSave} />);
    await user.click(screen.getByRole('button', { name: /Parametri/ }));
    await screen.findByTestId('risk-section');
    return { user, onSave };
}

describe('BotParamsSheet — sezioni nuove', () => {
    it('Rischio: legge params.risk (valori DB + default per i mancanti)', async () => {
        await openSheet();
        expect((screen.getByLabelText('Cap liability giornaliera €') as HTMLInputElement).value).toBe('800');
        expect((screen.getByLabelText('Stop perdita giornaliera €') as HTMLInputElement).value).toBe('-30');
        expect((screen.getByLabelText('Cap liability per evento €') as HTMLInputElement).value).toBe('150'); // default
    });

    it('Auto-trade: quattro interruttori con nota di rischio, stato dal DB', async () => {
        await openSheet();
        expect(screen.getByTestId('autotrade-section')).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /MODELLO in automatico/ })).toHaveAttribute('data-state', 'unchecked');
        expect(screen.getByRole('checkbox', { name: /ANOMALIE di prezzo/ })).toHaveAttribute('data-state', 'unchecked');
        expect(screen.getByRole('checkbox', { name: /COMBINAZIONI/ })).toHaveAttribute('data-state', 'checked');
        expect(screen.getByRole('checkbox', { name: /TENNIS in automatico/ })).toHaveAttribute('data-state', 'unchecked');
        expect(screen.getByText(/se una gamba non si abbina/)).toBeInTheDocument();
    });

    it('Uscite modello e Tennis/Anomalie: campi presenti con i valori DB', async () => {
        await openSheet();
        expect(screen.getByTestId('model-exits-section')).toBeInTheDocument();
        expect((screen.getByLabelText('Tieni se P(perdita) ≤ (0-1)') as HTMLInputElement).value).toBe('0.03');
        expect((screen.getByLabelText('Modello · incassa a frazione del max (0-1)') as HTMLInputElement).value).toBe('0.7');
        expect((screen.getByLabelText('Residuo · tentativi max') as HTMLInputElement).value).toBe('15');
        expect(screen.getByTestId('model-stake-section')).toBeInTheDocument();
        expect((screen.getByLabelText(/Stake auto-trade modello/) as HTMLInputElement).value).toBe('5');
    });

    it('salvataggio: chiavi ignote preservate, toggles/risk/exits espliciti', async () => {
        const { user, onSave } = await openSheet();
        await user.click(screen.getByRole('checkbox', { name: /TENNIS in automatico/ }));
        const cap = screen.getByLabelText('Cap liability giornaliera €');
        await user.clear(cap);
        await user.type(cap, '600');
        const hold = screen.getByLabelText('Tieni se P(perdita) ≤ (0-1)');
        await user.clear(hold);
        await user.type(hold, '0.05');
        await user.click(screen.getByRole('button', { name: 'Salva parametri' }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const saved = onSave.mock.calls[0][0] as Record<string, unknown>;
        expect(saved.unknown_key_from_service).toEqual({ keep: 'me' });
        expect(saved.auto_trade_tennis).toBe(true);
        expect(saved.auto_trade_combos).toBe(true);
        expect(saved.auto_trade_anomalies).toBe(false);
        const risk = saved.risk as Record<string, number>;
        expect(risk.daily_liability_cap).toBe(600);
        expect(risk.daily_loss_stop).toBe(-30);
        expect(risk.per_event_max_trades).toBe(3);
        const exits = saved.exits as Record<string, unknown>;
        expect(exits.hold_max_risk).toBe(0.05);
        expect(exits.model_take_profit_frac).toBe(0.7);
        expect(exits.residual_max_attempts).toBe(15);
        expect(exits.base_exit_minute).toBe(80);
    });
});

describe('mergeExits — parametri uscite modello', () => {
    it('default per i mancanti, valori validi tenuti, malformati scartati', () => {
        expect(mergeExits(null)).toEqual(EXITS_DEFAULTS);
        const m = mergeExits({ risk_cap: 0.2, ev_margin: 'x', model_free_cashout_p_lose: 0.01 });
        expect(m.risk_cap).toBe(0.2);
        expect(m.ev_margin).toBe(0.1);
        expect(m.model_free_cashout_p_lose).toBe(0.01);
        expect(m.residual_retry_s).toBe(20);
    });
});
