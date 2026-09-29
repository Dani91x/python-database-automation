// ============================================================================
// useMikeEventoAlMs.test.tsx - piano Mike 29/09, M7.1: le cifre della proposta
// VIVE dal canale al ms del bot, con l'eta' del dato a video. Il finto del
// canale ha la forma di `LocalChannel` (subscribe/onStatus/getStatus) e il push
// quella di `service._pubblica_evento` (la scheda SENZA dossier/markets/ctx/updated_at).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import type { LocalStatus } from '@/lib/localChannel';
import type { MikeEvent } from '@/lib/mike';
import type { CanaleEventiMike } from './useMikeEventoAlMs';
import { PropostaUscitaMike } from '@/components/controlroom/PropostaUscitaMike';
import { EsitoChiusuraMike } from '@/components/controlroom/EsitoChiusuraMike';

function canaleFinto() {
    const subs = new Map<string, Set<(d: unknown) => void>>();
    const stati = new Set<(s: LocalStatus) => void>();
    const ch: CanaleEventiMike = {
        subscribe: (t, cb) => { const s = subs.get(t) ?? new Set(); s.add(cb); subs.set(t, s); return () => { s.delete(cb); }; },
        onStatus: (cb) => { stati.add(cb); return () => { stati.delete(cb); }; },
        getStatus: () => 'connected',
    };
    const fn = () => ch;
    return {
        fn,
        spingi: (d: unknown) => act(() => { for (const cb of subs.get('mike_event') ?? []) cb(d); }),
        cade: () => act(() => { for (const cb of stati) cb('off'); }),
        iscritti: () => (subs.get('mike_event')?.size ?? 0),
    };
}

const ORA_S = Date.now() / 1000;

function proposta() {
    return {
        chiave: 'chiusura|c0', categoria: 'chiusura', ciclo: 0, stato: 'LIVE_COVERED',
        stato_voluto: 'LIVE_CLOSING', motivo: 'loss_2t: uscita a modello', close_reason: 'loss_2t',
        ordini: [{ ruolo: 'under_close', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.9, size: 7.9 }],
        bloccabile: -2.1, urgente: true, minuto: 60, gol: 2, decided_at: ORA_S - 20, proposed_at: ORA_S - 20,
    };
}

/** riga del DATABASE: la cifra e' di 20 s fa (volatile scritta ogni 5 s, riletta ogni 30 s) */
function evDb(): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date().toISOString(), mode: 'paper', markets: {}, state: 'LIVE_COVERED',
        cycle_no: 0, entry_price_initial: 1.5, dossier: null,
        live: { feed_age_s: 1, published_ts: ORA_S - 20, cashout: { net: -2.1 }, books: {}, goals: 2 } as unknown as MikeEvent['live'],
        positions: [], ctx: { uscita_proposta: proposta(), close_reason: null }, skipped: false, settled_pnl: null,
        updated_at: new Date().toISOString(),
    };
}

/** il push del bot: stessa scheda, niente ctx, cifra di adesso */
function push(net: number, pubTs: number, over: Record<string, unknown> = {}) {
    return {
        event_id: 'E1', state: 'LIVE_COVERED', mode: 'paper', positions: [],
        live: { feed_age_s: 0.4, published_ts: pubTs, published_at: new Date(pubTs * 1000).toISOString(),
            cashout: { net }, books: {}, goals: 2 },
        ...over,
    };
}

describe('M7.1 - la cifra «chiudendo ora» segue il canale al ms', () => {
    it('senza canale: cifra del database, dichiarata VECCHIA con la sua eta’', () => {
        render(<PropostaUscitaMike ev={evDb()} sorgenteLadder={null} canaleMike={null} />);
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−2,10 €');
        const eta = screen.getByTestId('cr-mike-proposta-eta-cifra');
        expect(eta.getAttribute('data-vecchia')).toBe('1');
        expect(eta.textContent).toMatch(/^\(VECCHIA: aggiornata 2\d s fa\)$/);
    });

    it('col canale: ogni push aggiorna la cifra e l’eta’; il ctx (la proposta) resta del database', () => {
        const c = canaleFinto();
        render(<PropostaUscitaMike ev={evDb()} sorgenteLadder={null} canaleMike={c.fn} />);
        expect(c.iscritti()).toBe(1);
        c.spingi(push(-1.75, Date.now() / 1000 - 1));
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−1,75 €');
        const eta = screen.getByTestId('cr-mike-proposta-eta-cifra');
        expect(eta.getAttribute('data-vecchia')).toBe('0');
        expect(eta.textContent).toBe('(aggiornata 1 s fa)');
        c.spingi(push(-1.6, Date.now() / 1000));
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−1,60 €');
        // la proposta non sparisce anche se il push non porta `ctx`
        expect(screen.getByTestId('cr-mike-proposta-titolo')).toBeTruthy();
    });

    it('push di un’altra partita o piu’ vecchio del database: ignorato', () => {
        const c = canaleFinto();
        render(<PropostaUscitaMike ev={evDb()} sorgenteLadder={null} canaleMike={c.fn} />);
        c.spingi({ ...push(9.99, Date.now() / 1000), event_id: 'ALTRA' });
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−2,10 €');
        c.spingi(push(8.88, ORA_S - 60));
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−2,10 €');
    });

    it('il canale cade: si torna al database, mai una foto ferma', () => {
        const c = canaleFinto();
        render(<PropostaUscitaMike ev={evDb()} sorgenteLadder={null} canaleMike={c.fn} />);
        c.spingi(push(-1.75, Date.now() / 1000));
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−1,75 €');
        c.cade();
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−2,10 €');
    });

    it('senza proposta nessuna sottoscrizione', () => {
        const c = canaleFinto();
        const e = { ...evDb(), ctx: {} };
        render(<PropostaUscitaMike ev={e} sorgenteLadder={null} canaleMike={c.fn} />);
        expect(c.iscritti()).toBe(0);
    });
});

describe('M7.1 - l’esito della chiusura segue lo stesso canale', () => {
    it('lo stato LIVE_CLOSING spinto dal bot compare subito, prima della rilettura del database', () => {
        const c = canaleFinto();
        const e = { ...evDb(), ctx: { close_reason: 'loss_2t', attempts: 0 } };
        render(<EsitoChiusuraMike ev={e} canaleMike={c.fn} />);
        expect(screen.queryByTestId('cr-mike-esito-chiusura')).toBeNull();
        c.spingi(push(-2.0, Date.now() / 1000, { state: 'LIVE_CLOSING' }));
        expect(screen.getByTestId('cr-mike-esito-chiusura-titolo').textContent).toBe('Chiusura in corso - tentativo 1');
    });
});
