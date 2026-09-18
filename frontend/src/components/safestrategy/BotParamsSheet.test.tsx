// Test COMPONENTE del pannello parametri del bot Safe Strategy, ora costruito
// su ParamsSheetBase: gruppi (Rischio / Auto-trade / Uscite modello /
// Tennis-Anomalie), merge dei parametri grezzi al salvataggio (chiavi ignote
// preservate, exits e risk sempre espliciti) e le due regressioni dell'audit:
//   H-14  varianti: nessuna riattivazione silenziosa, salvataggio a vuoto rifiutato
//   H-15  clamp VISIBILE e valore EFFETTIVO del servizio dichiarato sul campo
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
    BotParamsSheet, mergeExits, EXITS_DEFAULTS, gruppiDellaStrategia,
    type StrategiaFiltro,
} from './BotParamsSheet';
import type { ParamGroup } from '@/components/trading/ParamsSheetBase';
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

    it('«Auto-trade» non ha più una vista: nessuno di quei quattro piazza più da solo', async () => {
        await openSheet();
        expect(group('Auto-trade')).toBeNull();
        expect(screen.queryByRole('checkbox', { name: /NON piazza più da sola/ })).toBeNull();
    });

    it('Proponimi...: quattro rubinetti NUOVI, default ACCESO, stato dal DB', async () => {
        await openSheet();
        expect(group('Proponimi...')).toBeInTheDocument();
        // RAW non porta nessuna chiave `proponi_*`: devono risultare ACCESE
        // (default TRUE, comportamento di oggi), non spente come farebbe
        // un `Boolean(undefined)`.
        expect(screen.getByRole('checkbox', { name: /Proponimi le opportunità di MODELLO calcio/ })).toBeChecked();
        expect(screen.getByRole('checkbox', { name: /Proponimi le opportunità di MODELLO tennis/ })).toBeChecked();
        expect(screen.getByRole('checkbox', { name: /Proponimi le COMBINAZIONI/ })).toBeChecked();
        expect(screen.getByRole('checkbox', { name: /Proponimi le ANOMALIE di prezzo/ })).toBeChecked();
    });

    it('Proponimi...: un rubinetto spento sul DB si mostra spento', async () => {
        await openSheet(vi.fn(), { ...RAW, proponi_combo: false });
        expect(screen.getByRole('checkbox', { name: /Proponimi le COMBINAZIONI/ })).not.toBeChecked();
        expect(screen.getByRole('checkbox', { name: /Proponimi le opportunità di MODELLO calcio/ })).toBeChecked();
    });

    it('salvare non tocca gli auto_trade_* storici: restano quelli del DB, invariati', async () => {
        const onSave = vi.fn();
        const { user } = await openSheet(onSave, RAW);
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const salvato = onSave.mock.calls[0][0] as Record<string, unknown>;
        // RAW aveva SOLO auto_trade_combos=true: nessuna casella per questi
        // quattro e' a schermo, ma il salvataggio non li deve azzerare.
        expect(salvato.auto_trade_combos).toBe(true);
        expect(salvato.auto_trade_opportunities).toBe(false);
        expect(salvato.auto_trade_anomalies).toBe(false);
        expect(salvato.auto_trade_tennis).toBe(false);
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
        // 18/09 — l'unico interruttore interattivo di questo tipo, ora, è un
        // rubinetto NUOVO (`proponi_*`): nasce acceso, il clic lo spegne.
        await user.click(screen.getByRole('checkbox', { name: /Proponimi le opportunità di MODELLO tennis/ }));
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
        expect(saved.proponi_tennis).toBe(false);
        // gli auto_trade_* storici non hanno più una casella: passano INVARIATI
        expect(saved.auto_trade_tennis).toBe(false);
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

// ---------------------------------------------------------------------------
// CERT. 14/09 — MODALITA' PER STRATEGIA
// L'interruttore live del servizio e' uno solo: senza questa mappa, accendere
// il tennis a soldi veri accendeva anche le tre varianti del calcio.
// ---------------------------------------------------------------------------
describe('BotParamsSheet — modalita per strategia', () => {
    it('mostra una scelta per ogni strategia, col valore salvato sul DB', async () => {
        await openSheet(vi.fn(), {
            ...RAW,
            strategy_modes: { tennis: 'live', base: 'paper' },
        });
        const sheet = screen.getByTestId('params-sheet');
        expect(within(sheet).getByText(/Modalità per strategia/)).toBeTruthy();
        // il salvato si rilegge, non si perde per strada
        const tendina = (nome: RegExp) => within(sheet).getByRole('combobox', { name: nome });
        expect(tendina(/^Tennis$/)).toHaveValue('live');
        expect(tendina(/Base \(banca 1X2\)/)).toHaveValue('paper');
        // una strategia non nominata resta «come il servizio», non diventa un
        // valore fisso che poi nessuno ricorda di aver messo
        expect(tendina(/Ordini manuali/)).toHaveValue('');
    });

    it('dichiara che il servizio in PAPER e un TETTO', async () => {
        await openSheet();
        const sheet = screen.getByTestId('params-sheet');
        expect(sheet.textContent).toMatch(/se il servizio è in PAPER\s+resta tutto in paper/);
        expect(sheet.textContent).toMatch(/conferma LIVE/);
        // ...e che il live NON si eredita: e' la regola che vale nella
        // configurazione che si usa davvero (servizio armato in live)
        expect(sheet.textContent).toMatch(/solo scrivendoli,\s+mai per eredità/);
        expect(sheet.textContent).toMatch(/non dichiarata<\/b>? ?resta in\s+PAPER|non dichiarata.{0,30}resta in\s+PAPER/);
        // e che una posizione aperta non cambia mai modalita'
        expect(sheet.textContent).toMatch(/si chiudono con quella con cui sono nate/);
    });

    it('salva la mappa; «come il servizio» NON scrive la chiave', async () => {
        const { user, onSave } = await openSheet(vi.fn(), {
            ...RAW,
            strategy_modes: { tennis: 'live', base: 'paper' },
        });
        const sheet = screen.getByTestId('params-sheet');
        await user.selectOptions(
            within(sheet).getByRole('combobox', { name: /Risultato Esatto/ }), 'paper');
        await user.click(within(sheet).getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const payload = onSave.mock.calls[0][0] as Record<string, unknown>;
        expect(payload.strategy_modes).toEqual({ base: 'paper', esatto: 'paper', tennis: 'live' });
        // le chiavi ignote del servizio restano intatte: safe_update_params
        // SOSTITUISCE l'intero oggetto, un salvataggio parziale le cancellerebbe
        expect(payload.unknown_key_from_service).toEqual({ keep: 'me' });
    });
});

// ===========================================================================
// 18/09 — «ogni bot deve avere i suoi parametri DEDICATI A LUI» (utente).
// `soloStrategia` filtra la VISTA a una riga sola (base/esatto/punta/tennis):
// stesse chiavi, stesso salvataggio (l'intero `draft`), solo meno campi a
// video. `gruppiDellaStrategia` e' pura e testata a parte; qui si verifica
// che il FOGLIO VERO la usi davvero e non perda la semantica al salvataggio.
// ===========================================================================
describe('BotParamsSheet — gruppiDellaStrategia (funzione pura)', () => {
    const GRUPPI_FINTI: ParamGroup[] = [
        { label: 'Bot', fields: [{ key: 'poll_interval_s', label: 'Cadenza', type: 'number' }] },
        {
            label: 'Strategie abilitate',
            fields: [
                { key: 'variants.base', label: 'Base', type: 'boolean' },
                { key: 'variants.tennis', label: 'Tennis', type: 'boolean' },
            ],
        },
        {
            label: 'Condizioni delle strategie',
            fields: [
                { key: 'base.minuteMin', label: 'BASE · dal minuto', type: 'number' },
                { key: 'tennis.setsLeadMin', label: 'TENNIS · set di vantaggio', type: 'number' },
                { key: 'tennis.excludeDoubles', label: 'TENNIS: escludi i doppi', type: 'boolean' },
                { key: 'tennis_exit_approval', label: 'TENNIS: le chiusure le approvo io', type: 'boolean' },
            ],
        },
        {
            label: 'Uscite automatiche',
            fields: [
                { key: 'exits.enabled', label: 'Uscite automatiche attive', type: 'boolean' },
                { key: 'exits.base_exit_minute', label: 'BASE · uscita a tempo', type: 'number' },
                { key: 'exits.tennis_take_profit_min_odds', label: 'TENNIS · incassa da quota', type: 'number' },
                { key: 'exits.red_card_fav_exit', label: 'Rosso alla favorita', type: 'boolean' },
            ],
        },
        { label: 'Rischio', fields: [{ key: 'risk.daily_liability_cap', label: 'Cap €', type: 'number' }] },
    ];

    it('tennis: SOLO i suoi campi + le uscite condivise; nessun gruppo di servizio', () => {
        const filtrati = gruppiDellaStrategia(GRUPPI_FINTI, 'tennis');
        const etichette = filtrati.map((g) => g.label);
        expect(etichette).not.toContain('Bot');
        expect(etichette).not.toContain('Rischio');
        expect(etichette).toEqual(['Strategie abilitate', 'Condizioni delle strategie', 'Uscite automatiche']);

        const strategie = filtrati.find((g) => g.label === 'Strategie abilitate')!;
        expect(strategie.fields.map((f) => f.key)).toEqual(['variants.tennis']);

        const condizioni = filtrati.find((g) => g.label === 'Condizioni delle strategie')!;
        expect(condizioni.fields.map((f) => f.key)).toEqual([
            'tennis.setsLeadMin', 'tennis.excludeDoubles', 'tennis_exit_approval',
        ]);
        expect(condizioni.fields.some((f) => f.key === 'base.minuteMin')).toBe(false);

        const uscite = filtrati.find((g) => g.label === 'Uscite automatiche')!;
        // condivise (SEMPRE) + quella specifica del tennis, MAI quella di base
        expect(uscite.fields.map((f) => f.key)).toEqual([
            'exits.enabled', 'exits.tennis_take_profit_min_odds', 'exits.red_card_fav_exit',
        ]);
    });

    it('base: le condizioni SONO diverse da quelle del tennis, stesso gruppo', () => {
        const filtrati = gruppiDellaStrategia(GRUPPI_FINTI, 'base');
        const condizioni = filtrati.find((g) => g.label === 'Condizioni delle strategie')!;
        expect(condizioni.fields.map((f) => f.key)).toEqual(['base.minuteMin']);
        const uscite = filtrati.find((g) => g.label === 'Uscite automatiche')!;
        expect(uscite.fields.map((f) => f.key)).toEqual(['exits.enabled', 'exits.base_exit_minute', 'exits.red_card_fav_exit']);
    });

    it('FALSIFICAZIONE — un campo tolto dalla whitelist condivisa sparisce da OGNI strategia', () => {
        // mutazione: `exits.enabled` non e' piu' dichiarato condiviso ne'
        // pertinente a "esatto": deve sparire dal foglio di ESATTO.
        const mutati: ParamGroup[] = GRUPPI_FINTI.map((g) => (g.label === 'Uscite automatiche'
            ? { ...g, fields: g.fields.filter((f) => f.key !== 'exits.enabled') }
            : g));
        const prima = gruppiDellaStrategia(GRUPPI_FINTI, 'esatto')
            .find((g) => g.label === 'Uscite automatiche')!.fields.map((f) => f.key);
        const dopo = gruppiDellaStrategia(mutati, 'esatto')
            .find((g) => g.label === 'Uscite automatiche')!.fields.map((f) => f.key);
        expect(prima).toContain('exits.enabled');
        expect(dopo).not.toContain('exits.enabled');
    });

    it('nessuna strategia inventata: solo base/esatto/punta/tennis passano il filtro', () => {
        const tutte: StrategiaFiltro[] = ['base', 'esatto', 'punta', 'tennis'];
        for (const s of tutte) {
            const filtrati = gruppiDellaStrategia(GRUPPI_FINTI, s);
            // ogni campo filtrato o e' condiviso o parla ESPLICITAMENTE di `s`
            for (const g of filtrati) {
                for (const f of g.fields) {
                    const condiviso = ['exits.enabled', 'exits.loss_settle_delay_s', 'exits.exit_max_retries', 'exits.red_card_fav_exit'].includes(f.key);
                    const suo = f.key.includes(s) || f.key === `variants.${s}` || f.key === `strategy_modes.${s}`;
                    expect(condiviso || suo).toBe(true);
                }
            }
        }
    });
});

describe('BotParamsSheet — `soloStrategia` nel foglio vero', () => {
    const RAW_QUATTRO: Record<string, unknown> = {
        ...RAW,
        strategy_modes: { base: 'paper', esatto: 'live', punta: 'paper', tennis: 'live' },
        base: { minuteMin: 60 },
        tennis: { setsLeadMin: 1 },
        tennis_exit_approval: true,
    };

    async function openSheetFiltrato(soloStrategia: StrategiaFiltro, onSave = vi.fn()) {
        const user = userEvent.setup();
        render(
            <BotParamsSheet
                params={mergeBotParams(RAW_QUATTRO)}
                rawParams={RAW_QUATTRO}
                onSave={onSave}
                soloStrategia={soloStrategia}
                triggerTestId={`cr-safe-${soloStrategia}-params-trigger`}
            />,
        );
        await user.click(screen.getByTestId(`cr-safe-${soloStrategia}-params-trigger`));
        await screen.findByTestId('params-sheet');
        return { user, onSave };
    }

    it('mostra SOLO i campi del tennis: niente Rischio, niente Auto-trade, niente Base', async () => {
        await openSheetFiltrato('tennis');
        const sheet = screen.getByTestId('params-sheet');
        expect(sheet.textContent).toMatch(/TENNIS · set di vantaggio/);
        expect(sheet.textContent).not.toMatch(/BASE · dal minuto/);
        expect(sheet.textContent).not.toMatch(/Cap liability giornaliera/);
        expect(sheet.textContent).not.toMatch(/Opportunità di MODELLO/);
        // titolo dedicato, testid dedicato (niente collisione con altri fogli
        // montati sulle altre righe di Safe nello stesso pannello)
        expect(sheet.textContent).toMatch(/Parametri Safe · Tennis/);
    });

    it('salvare dal foglio del tennis NON tocca variants/modi delle altre tre', async () => {
        const { user, onSave } = await openSheetFiltrato('tennis');
        const sheet = screen.getByTestId('params-sheet');
        // tocca un campo del tennis (una condizione visibile in questo foglio)
        const campo = within(sheet).getByLabelText('TENNIS · set di vantaggio') as HTMLInputElement;
        await user.clear(campo);
        await user.type(campo, '2');
        await user.click(within(sheet).getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const payload = onSave.mock.calls[0][0] as Record<string, unknown>;
        // le variants/modi delle ALTRE strategie restano quelle di RAW_QUATTRO:
        // il foglio filtrato non le mostra, ma il salvataggio parte dal
        // draft INTERO, non da un sottoinsieme
        expect(payload.variants).toEqual(expect.arrayContaining(['base', 'esatto', 'punta', 'tennis']));
        expect(payload.strategy_modes).toEqual({ base: 'paper', esatto: 'live', punta: 'paper', tennis: 'live' });
        expect((payload.tennis as Record<string, unknown>).setsLeadMin).toBe(2);
        // e la chiave che il registro non conosce resta intatta
        expect(payload.unknown_key_from_service).toEqual({ keep: 'me' });
    });
});
