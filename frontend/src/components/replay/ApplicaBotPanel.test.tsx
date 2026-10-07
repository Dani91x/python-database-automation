// 07/10 — il riquadro «Applica bot» per tutti i bot: scelta del bot dello
// sport, scenario, modalita', pannello Parametri, accensione al cursore, e la
// richiesta che parte col payload giusto (supabase finto con la firma vera:
// rpc(nome, args) -> { data, error }).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: (...a: unknown[]) => rpc(...a) } }));

import { ApplicaBotPanel } from './ApplicaBotPanel';
import { EsitoBotPanel, righeCambiati } from './EsitoBotPanel';
import { CATALOGO_BOT } from '@/lib/replayBotCatalogo';
import { useApplicaBot } from '@/lib/useApplicaBot';
import type { CatalogoBot, EsitoBot } from '@/lib/replayBot';

const CURSORE = Date.parse('2026-10-06T18:30:00Z');

function Banco({ sport, catalogo }: { sport: 'calcio' | 'tennis'; catalogo?: ReadonlyArray<CatalogoBot> }) {
    const applica = useApplicaBot();
    return <ApplicaBotPanel sport={sport} eventId="35797769" cursoreMs={CURSORE} applica={applica}
        catalogo={catalogo} etichettaIstante={() => "30'"} />;
}

function opzioniBot(): string[] {
    const sel = screen.getByTestId('applica-bot-bot') as HTMLSelectElement;
    return Array.from(sel.querySelectorAll('option')).map(o => o.value).filter(Boolean);
}

beforeEach(() => {
    rpc.mockReset();
    rpc.mockResolvedValue({ data: 'R1', error: null });
});

describe('ApplicaBotPanel', () => {
    it('calcio: solo i bot calcio; tennis: solo i bot tennis', () => {
        const { unmount } = render(<Banco sport="calcio" />);
        expect(opzioniBot().sort()).toEqual(['mike', 'omega', 'safe_base', 'safe_esatto', 'safe_punta', 'scalper_calcio']);
        unmount();
        render(<Banco sport="tennis" />);
        expect(opzioniBot().sort()).toEqual(['safe_tennis', 'tennis_flb', 'tennis_pro', 'tennis_scalper', 'tennis_swing']);
    });

    it('bot -> scenario -> parametri: un parametro cambiato e\' evidenziato e parte da solo', async () => {
        render(<Banco sport="calcio" />);
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'mike' } });
        fireEvent.change(screen.getByTestId('applica-bot-scenario'), { target: { value: 'Mike - come in produzione' } });
        expect(screen.getByTestId('parametri-bot-frase').textContent).toBe('Varianti dei parametri: la strategia non cambia');
        fireEvent.click(screen.getByTestId('parametri-bot-apri'));
        const campo = screen.getByTestId('param-bot-campo-stake') as HTMLInputElement;
        expect(campo.value).toBe('10');
        expect(screen.getByTestId('param-bot-stake').textContent).toMatch(/di serie: 10 EUR/);
        fireEvent.change(campo, { target: { value: '4' } });
        expect(screen.getByTestId('param-bot-stake').getAttribute('data-cambiato')).toBe('si');
        // un interruttore riportato alla serie non e' una sostituzione
        fireEvent.click(screen.getByTestId('param-bot-switch-pre_enabled'));
        fireEvent.click(screen.getByTestId('param-bot-switch-pre_enabled'));
        expect(screen.getByTestId('param-bot-pre_enabled').getAttribute('data-cambiato')).toBe('no');
        fireEvent.click(screen.getByTestId('applica-bot-accendi'));
        expect(screen.getByTestId('applica-bot-istante').textContent).toMatch(/30'/);
        await act(async () => { fireEvent.click(screen.getByTestId('applica-bot-avvia')); });
        expect(rpc).toHaveBeenCalledWith('request_backtest', {
            p_params: { tipo: 'applica_bot', bot: 'mike', scenario: 'base', event_id: '35797769',
                parametri: { stake: 4 }, dal_ms: CURSORE },
        });
    });

    it('valore fuori dominio: errore scritto e Applica spento; Ripristina torna alla serie', () => {
        render(<Banco sport="calcio" />);
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'mike' } });
        fireEvent.change(screen.getByTestId('applica-bot-scenario'), { target: { value: 'Mike - come in produzione' } });
        fireEvent.click(screen.getByTestId('parametri-bot-apri'));
        fireEvent.change(screen.getByTestId('param-bot-campo-stake'), { target: { value: '9999' } });
        expect(screen.getByRole('alert').textContent).toMatch(/massimo 500/);
        expect((screen.getByTestId('applica-bot-avvia') as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(screen.getByTestId('parametri-bot-ripristina'));
        expect((screen.getByTestId('param-bot-campo-stake') as HTMLInputElement).value).toBe('10');
        expect((screen.getByTestId('applica-bot-avvia') as HTMLButtonElement).disabled).toBe(false);
    });

    it('di serie (niente cambiato, niente accensione): il payload del 06/10', async () => {
        render(<Banco sport="calcio" />);
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'scalper_calcio' } });
        fireEvent.change(screen.getByTestId('applica-bot-scenario'), { target: { value: 'Scalper - Media Under 2,5' } });
        await act(async () => { fireEvent.click(screen.getByTestId('applica-bot-avvia')); });
        expect(rpc).toHaveBeenCalledWith('request_backtest', {
            p_params: { tipo: 'applica_bot', bot: 'scalper_calcio', scenario: 'media-under-paper', event_id: '35797769' },
        });
    });

    it('Prova / Soldi veri simulati scelgono lo scenario gemello', async () => {
        render(<Banco sport="calcio" />);
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'scalper_calcio' } });
        fireEvent.change(screen.getByTestId('applica-bot-scenario'), { target: { value: 'Scalper - maker' } });
        fireEvent.click(screen.getByRole('radio', { name: 'Soldi veri simulati' }));
        await act(async () => { fireEvent.click(screen.getByTestId('applica-bot-avvia')); });
        expect(rpc.mock.calls[0][1].p_params.scenario).toBe('base');
    });

    it('i clic «Attiva adesso» SOLO per un bot che li dichiara', async () => {
        const conClic = CATALOGO_BOT.map(b => (b.bot === 'mike' ? { ...b, clic_ms: true } : b));
        render(<Banco sport="calcio" catalogo={conClic} />);
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'omega' } });
        fireEvent.change(screen.getByTestId('applica-bot-scenario'), { target: { value: 'Omega - motore V4 (come in produzione)' } });
        expect(screen.queryByTestId('applica-bot-clic')).toBeNull();
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'mike' } });
        fireEvent.change(screen.getByTestId('applica-bot-scenario'), { target: { value: 'Mike - come in produzione' } });
        fireEvent.click(screen.getByText(/clic «Attiva adesso» al cursore/));
        await act(async () => { fireEvent.click(screen.getByTestId('applica-bot-avvia')); });
        expect(rpc.mock.calls[0][1].p_params.clic_ms).toEqual([CURSORE]);
    });

    it('un bot disattivato si vede col motivo e non parte', () => {
        const spento = CATALOGO_BOT.map(b => (b.bot === 'omega' ? { ...b, disattivato: 'manca la cronologia' } : b));
        render(<Banco sport="calcio" catalogo={spento} />);
        fireEvent.change(screen.getByTestId('applica-bot-bot'), { target: { value: 'omega' } });
        expect(screen.getByTestId('applica-bot-disattivato').textContent).toMatch(/manca la cronologia/);
    });
});

describe('EsitoBotPanel', () => {
    const esito: EsitoBot = {
        bot: 'mike', scenario: 'base', event_id: '35797769', etichetta: 'Mike - come in produzione (soldi veri simulati)',
        righe: [], ordini: 0, violazioni: ['K1', 'K1'], note: [], parametri_cambiati: { stake: 4 },
        parametri_usati: { stake: 4 }, dal_ms: CURSORE, accensione: "ACCENSIONE dell'utente a ...",
    };
    it('intestazione: parametri cambiati con le etichette, accensione, violazioni', () => {
        render(<EsitoBotPanel esito={esito} nowMs={CURSORE} nomeMercato={m => m} nomeSelezione={(_m, s) => String(s)} />);
        expect(screen.getByTestId('esito-bot-parametri').textContent).toMatch(/Stake Under 3,5: 4 EUR \(di serie 10 EUR\)/);
        expect(screen.getByTestId('esito-bot-accensione').textContent).toMatch(/acceso dalle/);
        expect(screen.getByTestId('esito-bot-violazioni').textContent).toBe('violazioni: K1');
        expect(screen.getByTestId('ordini-bot')).toBeTruthy();
    });
    it('esito del 06/10 (senza i campi nuovi): tutto di serie, acceso dall\'inizio', () => {
        const vecchio: EsitoBot = { ...esito, parametri_cambiati: undefined, dal_ms: undefined, accensione: undefined, violazioni: [] };
        expect(righeCambiati(vecchio, CATALOGO_BOT)).toEqual([]);
        render(<EsitoBotPanel esito={vecchio} nowMs={0} nomeMercato={m => m} nomeSelezione={(_m, s) => String(s)} />);
        expect(screen.getByTestId('esito-bot-parametri').textContent).toBe('parametri: tutti di serie');
        expect(screen.getByTestId('esito-bot-accensione').textContent).toMatch(/dall.inizio/);
    });
});
