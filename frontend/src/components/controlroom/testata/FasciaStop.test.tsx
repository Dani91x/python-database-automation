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
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StopPerdita, vaiAllaRigaDelBot } from './FasciaStop';
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

describe('StopPerdita - a schermo', () => {
    it('oggi: \u00abConto: SPENTO\u00bb e ogni bot col SUO nome, la SUA modalita\' e il suo valore', () => {
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

    it('stop del conto attivo: soglia e P&L di giornata', () => {
        mostra({ conto: stopDelConto({ ...RIGA_OGGI, limit_value: 40, total: -12.5 }, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toMatch(/40,00/);
        expect(screen.getByTestId('cr-stop-conto-oggi').textContent).toMatch(/12,50/);
    });

    it('stop del conto scattato: lo dice, freno generale', () => {
        mostra({ conto: stopDelConto({ ...RIGA_OGGI, limit_value: 40, stop_fired: true }, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toMatch(/SCATTATO/);
    });

    it('stop del conto non letto: \u00abnon letto\u00bb, mai \u00abSPENTO\u00bb ne\' 0,00', () => {
        mostra({ conto: stopDelConto(null, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-valore').textContent).toBe('non letto');
        expect(screen.getByTestId('cr-stop-conto').textContent).not.toMatch(/0,00/);
    });

    it('ogni stop porta al SUO editor: il conto a Segui Live, i bot alla loro riga', () => {
        const vai = mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-conto-modifica').getAttribute('href')).toBe('/segui-live');
        fireEvent.click(screen.getByTestId('cr-stop-mike-modifica'));
        expect(vai).toHaveBeenCalledWith('mike');
        fireEvent.click(screen.getByTestId('cr-stop-omega-modifica'));
        expect(vai).toHaveBeenCalledWith('omega');
        expect(screen.getByTestId('cr-stop-safe').getAttribute('title')).toMatch(/Stop perdita giornaliera/);
    });
});

describe('R_T (30/09) - review finale', () => {
    it('Omega: la soglia NON e\' presentata come armata: "scatto non pubblicato"; Safe e Mike no', () => {
        mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        expect(screen.getByTestId('cr-stop-omega').textContent).toMatch(/scatto non pubblicato/);
        expect(screen.queryByTestId('cr-stop-safe-scatto')).toBeNull();
        expect(screen.queryByTestId('cr-stop-mike-scatto')).toBeNull();
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
    it('tennis e scalper: "stop proprio non pubblicato", mai "nessuno stop"', () => {
        mostra({ conto: stopDelConto(RIGA_OGGI, NOW), bot: bot() });
        const el = screen.getByTestId('cr-stop-altri');
        expect(el.textContent).toMatch(/Tennis, Scalper: stop proprio non pubblicato/);
        expect(el.textContent).not.toMatch(/nessuno/);
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
