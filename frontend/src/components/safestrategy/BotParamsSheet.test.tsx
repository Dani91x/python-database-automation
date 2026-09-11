// Test COMPONENTE del pannello parametri del bot Safe Strategy, ora costruito
// su ParamsSheetBase: gruppi (Rischio / Auto-trade / Uscite modello /
// Tennis-Anomalie), merge dei parametri grezzi al salvataggio (chiavi ignote
// preservate, exits e risk sempre espliciti) e le due regressioni dell'audit:
//   H-14  varianti: nessuna riattivazione silenziosa, salvataggio a vuoto rifiutato
//   H-15  clamp VISIBILE e valore EFFETTIVO del servizio dichiarato sul campo
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BotParamsSheet, mergeExits, EXITS_DEFAULTS } from './BotParamsSheet';
import { mergeBotParams, type SafeParamsEffective } from '@/lib/safeBot';

// Questi test montano la pagina/sheet INTERI (decine di campi, Radix, portali):
// su una macchina carica il default di 5 s di vitest scade per LENTEZZA, non per
// un difetto. Timeout esplicito: la suite deve essere verde anche sotto carico.
vi.setConfig({ testTimeout: 20_000 });


const RAW = {
    commission_pct: 5,
    auto_trade_combos: true,
    variants: ['base', 'esatto', 'punta', 'tennis'],
    risk: { daily_liability_cap: 800, daily_loss_stop: -30 },
    exits: { enabled: true, hold_max_risk: 0.03, model_take_profit_frac: 0.7 },
    unknown_key_from_service: { keep: 'me' },
};

async function openSheet(
    onSave = vi.fn(),
    raw: Record<string, unknown> = RAW,
    effective: SafeParamsEffective | null = null,
) {
    const user = userEvent.setup();
    render(
        <BotParamsSheet
            params={mergeBotParams(raw)}
            rawParams={raw}
            effective={effective}
            onSave={onSave}
        />,
    );
    await user.click(screen.getByTestId('params-trigger'));
    await screen.findByTestId('params-sheet');
    return { user, onSave };
}

function group(label: string): HTMLElement {
    return screen.getByTestId('params-sheet').querySelector(`[data-group="${label}"]`) as HTMLElement;
}

describe('BotParamsSheet — gruppi e valori', () => {
    it('Rischio: legge params.risk (valori DB + default per i mancanti)', async () => {
        await openSheet();
        expect(group('Rischio')).toBeInTheDocument();
        expect((screen.getByLabelText('Cap liability giornaliera €') as HTMLInputElement).value).toBe('800');
        expect((screen.getByLabelText('Stop perdita giornaliera €') as HTMLInputElement).value).toBe('-30');
        expect((screen.getByLabelText('Cap liability per evento €') as HTMLInputElement).value).toBe('150'); // default
    });

    it('Auto-trade: quattro interruttori con nota di rischio, stato dal DB', async () => {
        await openSheet();
        expect(group('Auto-trade')).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /MODELLO in automatico/ })).not.toBeChecked();
        expect(screen.getByRole('checkbox', { name: /ANOMALIE di prezzo/ })).not.toBeChecked();
        expect(screen.getByRole('checkbox', { name: /COMBINAZIONI/ })).toBeChecked();
        expect(screen.getByRole('checkbox', { name: /TENNIS in automatico/ })).not.toBeChecked();
        expect(screen.getByText(/se una gamba non si abbina/)).toBeInTheDocument();
    });

    it('Uscite modello e Tennis/Anomalie: campi presenti con i valori DB', async () => {
        await openSheet();
        expect(group('Uscite modello')).toBeInTheDocument();
        expect((screen.getByLabelText('Tieni se P(perdita) ≤ (0-1)') as HTMLInputElement).value).toBe('0.03');
        expect((screen.getByLabelText('Modello · incassa a frazione del max (0-1)') as HTMLInputElement).value).toBe('0.7');
        expect((screen.getByLabelText('Residuo · tentativi max') as HTMLInputElement).value).toBe('15');
        expect(group('Tennis / Anomalie')).toBeInTheDocument();
        expect((screen.getByLabelText(/Stake auto-trade modello/) as HTMLInputElement).value).toBe('5');
    });

    it('salvataggio: chiavi ignote preservate, toggles/risk/exits/variants espliciti', async () => {
        const { user, onSave } = await openSheet();
        await user.click(screen.getByRole('checkbox', { name: /TENNIS in automatico/ }));
        const cap = screen.getByLabelText('Cap liability giornaliera €');
        await user.clear(cap);
        await user.type(cap, '600');
        const hold = screen.getByLabelText('Tieni se P(perdita) ≤ (0-1)');
        await user.clear(hold);
        await user.type(hold, '0.05');
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const saved = onSave.mock.calls[0][0] as Record<string, unknown>;
        expect(saved.unknown_key_from_service).toEqual({ keep: 'me' });
        expect(saved.auto_trade_tennis).toBe(true);
        expect(saved.auto_trade_combos).toBe(true);
        expect(saved.auto_trade_anomalies).toBe(false);
        expect(saved.variants).toEqual(['base', 'esatto', 'punta', 'tennis']);
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

describe('BotParamsSheet — H-14 varianti', () => {
    it('variants vuote sul DB: avviso esplicito, nessuna riattivazione silenziosa', async () => {
        await openSheet(vi.fn(), { ...RAW, variants: [] }, { variants: ['base', 'esatto', 'punta', 'tennis'] });
        expect(screen.getByTestId('variants-invalid')).toHaveTextContent(/nessuna strategia valida/i);
        expect(screen.getByTestId('params-variants-effective')).toHaveTextContent('base, esatto, punta, tennis');
    });

    it('salvare senza nessuna strategia selezionata viene RIFIUTATO', async () => {
        const { user, onSave } = await openSheet();
        for (const name of ['Base', 'Risultato Esatto', 'Punta', 'Tennis']) {
            await user.click(screen.getByRole('checkbox', { name }));
        }
        await user.click(screen.getByTestId('params-save'));
        expect(await screen.findByTestId('params-refused')).toHaveTextContent(/almeno una/i);
        expect(onSave).not.toHaveBeenCalled();
    });

    it('varianti effettive diverse da quelle salvate: la scheda lo dice', async () => {
        await openSheet(vi.fn(), RAW, { variants: ['base'] });
        expect(screen.getByTestId('variants-differ')).toHaveTextContent('base');
    });
});

describe('BotParamsSheet — H-15 clamp e valore effettivo', () => {
    it('valore fuori range: clampato e DICHIARATO con i limiti del servizio', async () => {
        const { user } = await openSheet();
        const comm = screen.getByLabelText('Commissione %');
        await user.clear(comm);
        await user.type(comm, '50');
        // il servizio clampa la commissione a 0-20 (bot_service.resolve_params)
        const clamped = screen.getByTestId('params-clamped');
        expect(clamped).toHaveAttribute('data-field', 'commission_pct');
        expect(clamped).toHaveTextContent('clampato a 20');
        expect(clamped).toHaveTextContent('ammesso 0 … 20');
        expect((comm as HTMLInputElement).value).toBe('20');
    });

    // contratto backend 11/09: il DB NON viene riallineato sulle chiavi
    // money-critical, quindi la scheda mostra SEMPRE salvato E in uso
    it('parametro in uso diverso da quello salvato: mostra ENTRAMBI i valori', async () => {
        await openSheet(vi.fn(), { ...RAW, commission_pct: 50 }, { commission_pct: 20 });
        const eff = screen.getAllByTestId('params-effective')
            .find((e) => e.getAttribute('data-field') === 'commission_pct') as HTMLElement;
        expect(eff).toHaveTextContent('salvato 50');
        expect(eff).toHaveTextContent('il servizio usa 20');
        expect(screen.getByTestId('params-sheet'))
            .toHaveTextContent(/database NON viene riallineato/i);
    });

    it("le correzioni dichiarate dall'attività params_clamped compaiono sul campo", async () => {
        const user = userEvent.setup();
        render(
            <BotParamsSheet
                params={mergeBotParams(RAW)}
                rawParams={RAW}
                effective={null}
                corrections={{ max_spread_ratio: { stored: 0.5, effective: 1 } }}
                persisted={['variants']}
                onSave={vi.fn()}
            />,
        );
        await user.click(screen.getByTestId('params-trigger'));
        await screen.findByTestId('params-sheet');
        const eff = screen.getAllByTestId('params-effective')
            .find((e) => e.getAttribute('data-field') === 'max_spread_ratio') as HTMLElement;
        expect(eff).toHaveTextContent('il servizio usa 1');
        expect(eff).toHaveTextContent('correzione dichiarata dal servizio');
        // chiavi corrette DAVVERO sul database
        expect(screen.getByTestId('params-persisted')).toHaveTextContent('variants');
    });

    it('stop perdita: il segno non conta, la scheda mostra sempre quello vero', async () => {
        const { user, onSave } = await openSheet(
            vi.fn(), { ...RAW, risk: { ...RAW.risk, daily_loss_stop: 30 } }, { risk: { daily_loss_stop: 30 } },
        );
        // nessun clamp sul segno: 30 resta 30 nel campo...
        const loss = screen.getByLabelText('Stop perdita giornaliera €') as HTMLInputElement;
        expect(loss.value).toBe('30');
        expect(screen.queryByTestId('params-clamped')).toBeNull();
        // ...ma lo stop in uso e' -30 EUR e viene dichiarato
        expect(screen.getByTestId('params-loss-stop')).toHaveTextContent('stop in uso: −30,00 €');
        // e si puo' salvare anche col meno, senza che nulla venga corretto
        await user.clear(loss);
        await user.type(loss, '-45');
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const saved = onSave.mock.calls[0][0] as { risk: Record<string, number> };
        expect(saved.risk.daily_loss_stop).toBe(-45);
    });

    it('exits e risk effettivi sono letti dalle loro sezioni', async () => {
        await openSheet(vi.fn(), RAW, { exits: { hold_max_risk: 1 }, risk: { daily_liability_cap: 500 } });
        const fields = screen.getAllByTestId('params-effective').map((e) => e.getAttribute('data-field'));
        expect(fields).toContain('exits.hold_max_risk');
        expect(fields).toContain('risk.daily_liability_cap');
    });
});

describe('BotParamsSheet — Default', () => {
    it('il bottone Default riporta ai valori di fabbrica', async () => {
        const { user } = await openSheet();
        await user.click(screen.getByTestId('params-reset'));
        expect((screen.getByLabelText('Cap liability giornaliera €') as HTMLInputElement).value).toBe('500');
        expect(within(group('Strategie abilitate')).getByRole('checkbox', { name: 'Base' })).toBeChecked();
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

// ---------------------------------------------------------------------------
// Senza `control.stats.params_effective` (servizio mai avviato o migrazione
// safe_strategy_bot_v2.sql assente) non si sa con quali valori gira il bot: la
// scheda lo DICE. Prima mostrava i valori locali come "in uso dal servizio",
// mentre il servizio clampa in memoria senza riallineare il DB (H-15).
// ---------------------------------------------------------------------------
describe('BotParamsSheet — valori in uso non disponibili', () => {
    it('senza params_effective: avviso esplicito, nessuna riga "in uso dal servizio"', async () => {
        await openSheet(vi.fn(), RAW, null);
        const nota = screen.getByTestId('params-effective-missing');
        expect(nota).toHaveTextContent(/valori in uso non disponibili/);
        expect(nota).toHaveTextContent(/servizio mai avviato o\s+migrazione assente/);
        expect(nota).toHaveTextContent(/safe_strategy_bot_v2\.sql/);
        expect(nota).toHaveTextContent(/valori SALVATI/);
        // la riga che spacciava i locali per valori del servizio non c'e' piu'
        expect(screen.queryByTestId('params-variants-effective')).toBeNull();
    });

    it('con params_effective: si torna a dichiarare le strategie in uso', async () => {
        await openSheet(vi.fn(), RAW, { variants: ['base', 'tennis'] } as SafeParamsEffective);
        expect(screen.queryByTestId('params-effective-missing')).toBeNull();
        expect(screen.getByTestId('params-variants-effective')).toHaveTextContent('base, tennis');
    });
});
