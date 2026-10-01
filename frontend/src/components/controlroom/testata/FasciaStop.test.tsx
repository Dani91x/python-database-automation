// ============================================================================
// StopPerdita.test.tsx - P4 (30/09): gli stop di perdita in testata.
// Finti con le chiavi dei produttori veri:
//  - riga `betfair_live_risk_state` scritta da `daily_stop_worker._publish_state`
//    (Betfair/stream/daily_stop_worker.py:334-347): mode, day, realized,
//    open_mtm, total, limit_value, stop_fired, detail{reason, degraded, kill_switch}
//    + id, updated_at della tabella (migrations/betfair_live_pnl_journal.sql:51-62);
//  - Safe `stats.risk` (lib/safeBot SafeRiskStats: daily_loss_stop, loss_stop_active);
//  - Mike `control.params.daily_loss_stop` (mike/config.py:318) e `stats.daily_stop`
//    (mike/service.py:4107);
//  - Omega `control.params` strategy_version / v3_daily_loss_cap / daily_loss_cap.
// Oggi (progetto par. 0): stop del conto SPENTO (limit_value null, reason limit_off).
// 01/10: modifica sul posto (salvataggio iniettato: la funzione vera e le sue
// RPC sono collaudate in salvaStop.test.ts), cancello «parametri non letti»,
// conferma in LIVE, frasi chiare al posto di quelle criptiche.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StopPerdita, vaiAllaRigaDelBot, NOTA_TENNIS_SCALPER } from './FasciaStop';
import { stopDelConto, stopDeiBot, type StopPerditaTestata } from './stopPerdita';
import type { LiveRiskState } from '@/lib/liveOrders';

const NOW = Date.parse('2026-09-30T14:20:00Z');
const RIGA_OGGI: LiveRiskState = {
    id: 1, mode: 'live', day: '2026-09-30', realized: 0, open_mtm: -0.74, total: -0.74,
    limit_value: null, stop_fired: false,
    detail: { reason: 'limit_off', degraded: false, kill_switch: false },
    updated_at: '2026-09-30T14:19:00+00:00',
};

function bot(over: Partial<Parameters<typeof stopDeiBot>[0]> = {}) {
    return stopDeiBot({
        safe: { modalita: 'paper', risk: { daily_loss_stop: -50, loss_stop_active: false } },
        mike: { modalita: 'live', params: { daily_loss_stop: 50, max_open_matches: 10 }, stats: { daily_stop: false } },
        omega: { modalita: 'paper', params: { strategy_version: 3, v3_daily_loss_cap: 300 } },
        ...over,
    });
}

function mostra(stop: StopPerditaTestata | undefined, vai = vi.fn(() => true)) {
    render(<MemoryRouter><StopPerdita stop={stop} vai={vai} /></MemoryRouter>);
    return vai;
}

describe('stopDelConto', () => {
    it('oggi: limit_value null -> SPENTO, motivo limit_off, eta\' dell\'ultimo cambio', () => {
        const c = stopDelConto(RIGA_OGGI, NOW);
        expect(c).toMatchObject({ letto: true, soglia: null, scattato: false, motivo: 'limit_off', etaS: 60 });
    });
    it('soglia attiva e P&L di giornata', () => {
        const c = stopDelConto({ ...RIGA_OGGI, limit_value: 40, total: -12.5, detail: { reason: 'under_limit' } }, NOW);
        expect(c.soglia).toBe(40);
        expect(c.oggi).toBe(-12.5);
    });
    it('riga mai letta: non letto (mai "spento")', () => {
        expect(stopDelConto(null, NOW)).toMatchObject({ letto: false, soglia: null });
    });
});

describe('stopDeiBot', () => {
    it('Safe dal servizio (segno normalizzato), Mike dal parametro, Omega dal motore v3', () => {
        const [s, m, o] = bot();
        expect(s).toMatchObject({ bot: 'safe', modalita: 'paper', soglia: 50, letto: true });
        expect(m).toMatchObject({ bot: 'mike', modalita: 'live', soglia: 50, letto: true });
        expect(o).toMatchObject({ bot: 'omega', modalita: 'paper', soglia: 300, letto: true });
        expect(o.fonte).toMatch(/v3_daily_loss_cap/);
    });
    it('Safe con stop positivo nel servizio (50): stessa soglia (il segno non conta)', () => {
        expect(bot({ safe: { modalita: 'paper', risk: { daily_loss_stop: 50 } } })[0].soglia).toBe(50);
    });
    it('Omega motore v2: daily_loss_cap (0 = spento)', () => {
        const o = bot({ omega: { modalita: 'paper', params: { strategy_version: 2, daily_loss_cap: 0, v3_daily_loss_cap: 300 } } })[2];
        expect(o.soglia).toBe(0);
        expect(o.fonte).toMatch(/daily_loss_cap/);
        expect(o.fonte).not.toMatch(/v3_/);
    });
    it('parametri non letti: nessun numero (mai il predefinito spacciato per vero)', () => {
        const [s, m, o] = bot({
            safe: { modalita: null, risk: null },
            mike: { modalita: null, params: null, stats: null },
            omega: { modalita: null, params: {} },
        });
        expect(s.soglia).toBeNull();
        expect(m.soglia).toBeNull();
        expect(o.soglia).toBeNull();
    });
    it('Mike: stop scattato dichiarato dal servizio', () => {
        expect(bot({ mike: { modalita: 'live', params: { daily_loss_stop: 50 }, stats: { daily_stop: true } } })[1].scattato).toBe(true);
    });
});

// 01/10: i parametri GREZZI dei bot come li porta il modello di vista
// (`vm.bots[].params`, chiavi di produzione)
const PARAMS = {
    safe: { variants: ['base'], risk: { daily_loss_stop: -50 } },
    mike: { daily_loss_stop: 50, max_open_matches: 10 },
    omega: { strategy_version: 3, v3_daily_loss_cap: 300 },
};

describe('StopPerdita - a schermo', () => {
    it('oggi: «Conto: SPENTO» e ogni bot col SUO nome, la SUA modalita\' e il suo valore', () => {
        mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toBe('SPENTO');
        const safe = screen.getByTestId('cr-stop-safe');
        expect(safe.textContent).toMatch(/Safe/);
        expect(safe.textContent).toMatch(/PAPER/);
        expect(safe.textContent).toMatch(/50,00/);
        const mike = screen.getByTestId('cr-stop-mike');
        expect(mike.textContent).toMatch(/Mike/);
        expect(mike.textContent).toMatch(/LIVE/);
        expect(mike.textContent).toMatch(/50,00/);
        expect(screen.getByTestId('cr-stop-omega').textContent).toMatch(/300,00/);
    });

    it('01/10 - una riga per stop: modalita\' col suo colore, stato, fonte ed eta\'', () => {
        render(<MemoryRouter><StopPerdita stop={{ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() }}
            statoServizio={{ safe: { fonte: 'canale', etaS: 3 }, mike: { fonte: 'database', etaS: 12 } }} /></MemoryRouter>);
        // conto: la modalita' su cui il runner calcola lo stop (mode della riga)
        expect(screen.getByTestId('cr-stop-conto-modo').textContent).toBe('LIVE');
        expect(screen.getByTestId('cr-stop-conto-modo').className).toMatch(/red/);
        expect(screen.getByTestId('cr-stop-conto-fonte').textContent).toMatch(/runner calcio .* cambio 1 min fa/);
        expect(screen.getByTestId('cr-stop-safe-modo').textContent).toBe('PAPER');
        expect(screen.getByTestId('cr-stop-safe-stato').textContent).toBe('attivo');
        expect(screen.getByTestId('cr-stop-safe-fonte').textContent).toMatch(/servizio Safe .* canale .* 3 s fa/);
        expect(screen.getByTestId('cr-stop-mike-fonte').textContent).toMatch(/parametro Mike .* database .* 12 s fa/);
        expect(screen.getByTestId('cr-stop-omega-fonte').textContent).toMatch(/stato del servizio non letto/);
    });

    it('stop del conto attivo: soglia e P&L di giornata', () => {
        mostra({ conto: stopDelConto({ ...RIGA_OGGI, limit_value: 40, total: -12.5 }, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toMatch(/40,00/);
        expect(screen.getByTestId('cr-stop-conto-stato').textContent).toMatch(/attivo/);
        expect(screen.getByTestId('cr-stop-conto-oggi').textContent).toMatch(/12,50/);
    });

    it('stop del conto scattato: lo dice, freno generale', () => {
        mostra({ conto: stopDelConto({ ...RIGA_OGGI, limit_value: 40, stop_fired: true }, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toMatch(/SCATTATO/);
        expect(screen.getByTestId('cr-stop-conto-stato').textContent).toMatch(/^SCATTATO/);
    });

    it('stop del conto non letto: «non letto», mai «SPENTO» ne\' 0,00', () => {
        mostra({ conto: stopDelConto(null, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toBe('non letto');
        expect(screen.getByTestId('cr-stop-conto').textContent).not.toMatch(/0,00/);
    });

    it('ogni bot ha ancora la strada al SUO foglio completo (riga di Comando dei bot)', () => {
        const vai = mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        fireEvent.click(screen.getByTestId('cr-stop-mike-modifica'));
        expect(vai).toHaveBeenCalledWith('mike');
        fireEvent.click(screen.getByTestId('cr-stop-omega-modifica'));
        expect(vai).toHaveBeenCalledWith('omega');
        expect(screen.getByTestId('cr-stop-safe').getAttribute('title')).toMatch(/Stop perdita giornaliera/);
    });
});

describe('R_T (30/09) + 01/10 - frasi chiare, mai criptiche', () => {
    it('Omega: la soglia NON e\' presentata come armata: lo dice in chiaro; Safe e Mike "attivo"', () => {
        mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-omega-stato').textContent).toBe('Omega non pubblica se lo stop e\' scattato');
        expect(screen.getByTestId('cr-stop-omega-stato').textContent).not.toMatch(/attivo/);
        expect(screen.getByTestId('cr-stop-safe-stato').textContent).toBe('attivo');
        expect(screen.getByTestId('cr-stop-mike-stato').textContent).toBe('attivo');
        expect(document.body.textContent).not.toMatch(/scatto non pubblicato|stop proprio non pubblicato/);
    });
    it('conto SPENTO con un bot in LIVE: ambra; tutti in paper: grigio (testo invariato)', () => {
        mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() }); // Mike LIVE
        const v = screen.getByTestId('cr-stop-conto-valore');
        expect(v.textContent).toBe('SPENTO');
        expect(v.className).toMatch(/amber/);
    });
    it('conto SPENTO, tutti in paper: nessuna ambra', () => {
        render(<MemoryRouter><StopPerdita stop={{ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot({ mike: { modalita: 'paper', params: { daily_loss_stop: 50 }, stats: null } }) }} qualcheBotLive={false} /></MemoryRouter>);
        expect(screen.getByTestId('cr-stop-conto-valore').className).not.toMatch(/amber/);
    });
    it('un bot LIVE fuori dai tre (tennis) accende l\'ambra tramite qualcheBotLive', () => {
        render(<MemoryRouter><StopPerdita stop={{ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot({ mike: { modalita: 'paper', params: { daily_loss_stop: 50 }, stats: null } }) }} qualcheBotLive /></MemoryRouter>);
        expect(screen.getByTestId('cr-stop-conto-valore').className).toMatch(/amber/);
    });
    it('tennis e scalper: la verita\' verificata nel codice (nessuno stop proprio; lo stop del conto li ferma ma non conta le loro perdite)', () => {
        mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        const el = screen.getByTestId('cr-stop-altri');
        expect(el.textContent).toBe(NOTA_TENNIS_SCALPER.testo);
        expect(el.textContent).toMatch(/Tennis e Scalper: nessuno stop proprio/);
        expect(el.textContent).toMatch(/non lo fanno scattare/);
        expect(el.getAttribute('title')).toMatch(/runner calcio/);
    });
});

// ------------------------------------------------------------ 01/10 modifica sul posto

function conParametri(over: {
    stop?: StopPerditaTestata; params?: Parameters<typeof StopPerdita>[0]['params'];
    salva?: ReturnType<typeof vi.fn>; onSalvato?: () => void; qualcheBotLive?: boolean;
} = {}) {
    const salva = over.salva ?? vi.fn(async () => 35);
    render(<MemoryRouter><StopPerdita
        stop={over.stop ?? { conto: stopDelConto({ ...RIGA_OGGI, mode: 'paper' }, NOW), bot: bot({ mike: { modalita: 'paper', params: PARAMS.mike, stats: { daily_stop: false } } }) }}
        params={'params' in over ? over.params : PARAMS}
        salva={salva as never}
        onSalvato={over.onSalvato}
        qualcheBotLive={over.qualcheBotLive ?? false}
    /></MemoryRouter>);
    return salva;
}

describe('01/10 - ogni stop si modifica DALLA TESTATA', () => {
    it('clic sulla cifra -> campo con la cifra in vigore (negativa), Salva chiama la funzione con chi, perdita e i parametri GREZZI', async () => {
        const onSalvato = vi.fn();
        const salva = conParametri({ onSalvato });
        fireEvent.click(screen.getByTestId('cr-stop-mike-valore'));
        const campo = screen.getByTestId('cr-stop-mike-campo') as HTMLInputElement;
        expect(campo.value).toBe('-50,00');
        fireEvent.change(campo, { target: { value: '-40' } });
        fireEvent.click(screen.getByTestId('cr-stop-mike-salva'));
        await waitFor(() => expect(salva).toHaveBeenCalledWith('mike', 40, PARAMS.mike));
        // riscontro: la cifra RESTITUITA dal database, poi la rilettura della pagina
        await waitFor(() => expect(screen.getByTestId('cr-stop-mike-esito').textContent).toMatch(/salvato: .*35,00 .*\(letto dal database\)/));
        // digitato 40, riga del DB 35: mai la cifra digitata
        expect(screen.getByTestId('cr-stop-mike-esito').textContent).not.toMatch(/40,00/);
        expect(onSalvato).toHaveBeenCalledTimes(1);
    });

    it('la cifra mostrata dopo il salvataggio e\' quella del DATABASE, non quella digitata', async () => {
        conParametri({ salva: vi.fn(async () => 45) });
        fireEvent.click(screen.getByTestId('cr-stop-omega-valore'));
        fireEvent.change(screen.getByTestId('cr-stop-omega-campo'), { target: { value: '-40' } });
        fireEvent.click(screen.getByTestId('cr-stop-omega-salva'));
        await waitFor(() => expect(screen.getByTestId('cr-stop-omega-esito').textContent).toMatch(/45,00/));
        expect(screen.getByTestId('cr-stop-omega-esito').textContent).not.toMatch(/40,00/);
    });

    it('conto: digitato −40, la riga del DB dice 35 -> «salvato: −35,00 € (letto dal database)»', async () => {
        const salva = conParametri({ salva: vi.fn(async () => 35) });
        fireEvent.click(screen.getByTestId('cr-stop-conto-valore'));
        fireEvent.change(screen.getByTestId('cr-stop-conto-campo'), { target: { value: '-40' } });
        fireEvent.click(screen.getByTestId('cr-stop-conto-salva'));
        await waitFor(() => expect(salva).toHaveBeenCalledWith('conto', 40, null));
        await waitFor(() => expect(screen.getByTestId('cr-stop-conto-esito').textContent).toBe('salvato: −35,00 € (letto dal database)'));
    });

    it('importo non valido: lo dice e NON salva', () => {
        const salva = conParametri();
        fireEvent.click(screen.getByTestId('cr-stop-safe-valore'));
        fireEvent.change(screen.getByTestId('cr-stop-safe-campo'), { target: { value: '-40,555' } });
        fireEvent.click(screen.getByTestId('cr-stop-safe-salva'));
        expect(screen.getByTestId('cr-stop-safe-errore').textContent).toMatch(/non valido/);
        expect(salva).not.toHaveBeenCalled();
    });

    it('errore della scrittura: "non salvato" col motivo, nessun "salvato"', async () => {
        conParametri({ salva: vi.fn(async () => { throw new Error('non autorizzato'); }) });
        fireEvent.click(screen.getByTestId('cr-stop-safe-valore'));
        fireEvent.change(screen.getByTestId('cr-stop-safe-campo'), { target: { value: '-40' } });
        fireEvent.click(screen.getByTestId('cr-stop-safe-salva'));
        await waitFor(() => expect(screen.getByTestId('cr-stop-safe-errore').textContent).toMatch(/non salvato: non autorizzato/));
        expect(screen.queryByTestId('cr-stop-safe-esito')).toBeNull();
    });

    it('Annulla: nessun salvataggio, torna la cifra', () => {
        const salva = conParametri();
        fireEvent.click(screen.getByTestId('cr-stop-omega-valore'));
        fireEvent.click(screen.getByTestId('cr-stop-omega-annulla'));
        expect(screen.getByTestId('cr-stop-omega-valore').textContent).toMatch(/300,00/);
        expect(salva).not.toHaveBeenCalled();
    });
});

describe('01/10 - CANCELLO: parametri non letti = campo disabilitato, e lo dice', () => {
    it('Mike e Omega senza parametri letti: cifra non cliccabile, "parametri non letti: modifica disabilitata"', () => {
        const salva = conParametri({ params: { safe: PARAMS.safe, mike: null, omega: {} } });
        for (const b of ['mike', 'omega']) {
            const v = screen.getByTestId(`cr-stop-${b}-valore`) as HTMLButtonElement;
            expect(v.disabled).toBe(true);
            fireEvent.click(v);
            expect(screen.queryByTestId(`cr-stop-${b}-campo`)).toBeNull();
            expect(screen.getByTestId(`cr-stop-${b}-non-modificabile`).textContent).toMatch(/parametri non letti: modifica disabilitata/);
        }
        // Safe letto: modificabile
        expect((screen.getByTestId('cr-stop-safe-valore') as HTMLButtonElement).disabled).toBe(false);
        expect(salva).not.toHaveBeenCalled();
    });
    it('nessun parametro passato (finto di prima): niente e\' modificabile', () => {
        conParametri({ params: undefined });
        expect((screen.getByTestId('cr-stop-safe-valore') as HTMLButtonElement).disabled).toBe(true);
    });
    it('conto: stato del runner non letto = non modificabile da qui', () => {
        conParametri({ stop: { conto: stopDelConto(null, NOW), bot: bot() } });
        expect((screen.getByTestId('cr-stop-conto-valore') as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByTestId('cr-stop-conto-non-modificabile').textContent).toMatch(/non letto/);
    });
});

describe('01/10 - LIVE (soldi veri): conferma esplicita, che scade', () => {
    it('Mike in LIVE: Salva NON scrive, chiede conferma; Conferma scrive', async () => {
        const salva = conParametri({ stop: { conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() } }); // Mike LIVE
        fireEvent.click(screen.getByTestId('cr-stop-mike-valore'));
        fireEvent.change(screen.getByTestId('cr-stop-mike-campo'), { target: { value: '-40' } });
        fireEvent.click(screen.getByTestId('cr-stop-mike-salva'));
        expect(salva).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-stop-mike-richiesta-conferma').textContent).toMatch(/Mike e' in LIVE \(soldi veri\): confermi lo stop a .*40,00/);
        fireEvent.click(screen.getByTestId('cr-stop-mike-conferma'));
        await waitFor(() => expect(salva).toHaveBeenCalledWith('mike', 40, PARAMS.mike));
    });
    it('Safe in PAPER: nessuna conferma, scrive subito', async () => {
        const salva = conParametri({ stop: { conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() } });
        fireEvent.click(screen.getByTestId('cr-stop-safe-valore'));
        fireEvent.change(screen.getByTestId('cr-stop-safe-campo'), { target: { value: '-40' } });
        fireEvent.click(screen.getByTestId('cr-stop-safe-salva'));
        expect(screen.queryByTestId('cr-stop-safe-richiesta-conferma')).toBeNull();
        await waitFor(() => expect(salva).toHaveBeenCalledWith('safe', 40, PARAMS.safe));
    });
    it('Safe PAPER ma con una strategia in LIVE (modiStrategia): conferma, lo stop e\' comune', () => {
        const salva = vi.fn(async () => 35);
        render(<MemoryRouter><StopPerdita stop={{ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() }}
            params={PARAMS} salva={salva as never} strategieLive={{ safe: true }} /></MemoryRouter>);
        fireEvent.click(screen.getByTestId('cr-stop-safe-valore'));
        fireEvent.click(screen.getByTestId('cr-stop-safe-salva'));
        expect(screen.getByTestId('cr-stop-safe-richiesta-conferma').textContent).toMatch(/strategie in LIVE/);
        expect(salva).not.toHaveBeenCalled();
    });
    it('modalita\' NON letta: si chiede conferma (potrebbe essere LIVE)', () => {
        const salva = conParametri({ stop: { conto: stopDelConto(RIGA_OGGI, NOW), bot: bot({ omega: { modalita: null, params: PARAMS.omega } }) } });
        fireEvent.click(screen.getByTestId('cr-stop-omega-valore'));
        fireEvent.click(screen.getByTestId('cr-stop-omega-salva'));
        expect(screen.getByTestId('cr-stop-omega-richiesta-conferma').textContent).toMatch(/non letta/);
        expect(salva).not.toHaveBeenCalled();
    });
    it('conto con un bot LIVE: conferma; la conferma dimenticata scade dopo 10 s e non scrive', () => {
        vi.useFakeTimers();
        try {
            const salva = conParametri({ qualcheBotLive: true });
            fireEvent.click(screen.getByTestId('cr-stop-conto-valore'));
            fireEvent.change(screen.getByTestId('cr-stop-conto-campo'), { target: { value: '-80' } });
            fireEvent.click(screen.getByTestId('cr-stop-conto-salva'));
            expect(screen.getByTestId('cr-stop-conto-richiesta-conferma').textContent).toMatch(/soldi veri/);
            act(() => { vi.advanceTimersByTime(10_001); });
            expect(screen.queryByTestId('cr-stop-conto-conferma')).toBeNull();
            expect(screen.getByTestId('cr-stop-conto-errore').textContent).toMatch(/conferma scaduta/);
            expect(salva).not.toHaveBeenCalled();
        } finally {
            vi.useRealTimers();
        }
    });
});

describe('vaiAllaRigaDelBot - porta alla riga, mette il fuoco sul foglio, non lo apre', () => {
    it('riga presente: fuoco sul primo pulsante del foglio parametri del bot, nessun clic', () => {
        document.body.innerHTML = `
            <div data-testid="cr-pannello-bot"></div>
            <div data-testid="cr-parametri-mike"><button id="foglio">parametri</button></div>`;
        const b = document.getElementById('foglio') as HTMLButtonElement;
        const clic = vi.fn();
        b.addEventListener('click', clic);
        expect(vaiAllaRigaDelBot('mike')).toBe(true);
        expect(document.activeElement).toBe(b);
        expect(clic).not.toHaveBeenCalled();
    });
    it('riga non visibile (filtro sport): porta al pannello e lo dice (false)', () => {
        document.body.innerHTML = '<div data-testid="cr-pannello-bot"></div>';
        expect(vaiAllaRigaDelBot('omega')).toBe(false);
    });
});
