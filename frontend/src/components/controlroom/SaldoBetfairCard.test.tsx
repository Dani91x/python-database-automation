import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { SaldoBetfairCard, checkedAtDiMessaggioAccount } from './SaldoBetfairCard';
import type { LiveAccountRow, LiveHeartbeatRow } from '@/lib/liveOrders';
import type { LocalChannel } from '@/lib/localChannel';

function account(over: Partial<LiveAccountRow> = {}): LiveAccountRow {
    return { id: 1, available: 1234.56, exposure: 18.4, updated_at: new Date().toISOString(), ...over };
}
function heartbeat(over: Partial<LiveHeartbeatRow> = {}): LiveHeartbeatRow {
    return {
        id: 1, ts: new Date().toISOString(), pid: 123, mode: 'LIVE',
        watchdog_ts: new Date().toISOString(), watchdog_pid: 124,
        updated_at: new Date().toISOString(), ...over,
    };
}

/**
 * 18/09 (raccordo) — canale locale FINTO: di default MUTO (mai un messaggio),
 * cioè esattamente lo scenario da certificare per difetto ("il canale è
 * un'accelerazione, mai l'unica fonte"). Chi vuole provare il canale ACCESO
 * passa `onAccount` e lo invoca a mano.
 */
function canaleFinto(onAccountRef?: { current: ((d: unknown) => void) | null }): LocalChannel {
    return {
        subscribe: vi.fn((topic: string, cb: (d: unknown) => void) => {
            if (topic === 'account' && onAccountRef) onAccountRef.current = cb;
            return () => { /* unsubscribe */ };
        }),
    } as unknown as LocalChannel;
}

function depsDi(a: LiveAccountRow | null, h: LiveHeartbeatRow | null, onAccountRef?: { current: ((d: unknown) => void) | null }) {
    return {
        fetchAccount: vi.fn(async () => a),
        subscribeAccount: vi.fn(() => () => {}),
        fetchHeartbeat: vi.fn(async () => h),
        subscribeHeartbeat: vi.fn(() => () => {}),
        getCanale: vi.fn(() => canaleFinto(onAccountRef)),
    };
}

beforeEach(() => {
    try { window.localStorage.clear(); } catch { /* jsdom sempre disponibile qui */ }
});
afterEach(() => vi.restoreAllMocks());

describe('SaldoBetfairCard', () => {
    it('mostra il saldo e l’esposizione formattati', async () => {
        const deps = depsDi(account({ available: 1234.56, exposure: 18.4 }), heartbeat());
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/1234,56/));
        expect(s.getByTestId('saldo-betfair-esposizione').textContent).toMatch(/18,40/);
    });

    it('SALDO NASCOSTO non compare nel DOM: il testo diventa i pallini', async () => {
        const deps = depsDi(account({ available: 1234.56 }), heartbeat());
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/1234,56/));
        fireEvent.click(s.getByTestId('saldo-betfair-occhio'));
        expect(s.getByTestId('saldo-betfair-valore').textContent).not.toMatch(/1234,56/);
        expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/••••/);
        expect(s.container.textContent ?? '').not.toContain('1234,56');
    });

    it('la preferenza nascosto si ricorda (localStorage)', async () => {
        window.localStorage.setItem('cr-saldo-nascosto', '1');
        const deps = depsDi(account({ available: 1234.56 }), heartbeat());
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-occhio').getAttribute('aria-pressed')).toBe('true'));
        expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/••••/);
    });

    it('SALDO VECCHIO (battito lontano) e canale MUTO → stato arancione', async () => {
        const vecchio = new Date(Date.now() - 10 * 60 * 1000).toISOString(); // 10 minuti fa
        const deps = depsDi(account(), heartbeat({ ts: vecchio }));
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non verificato di recente/));
    });

    it('errore di lettura: nessun numero inventato', async () => {
        const deps = {
            fetchAccount: vi.fn(async () => { throw new Error('rete'); }),
            subscribeAccount: vi.fn(() => () => {}),
            fetchHeartbeat: vi.fn(async () => null),
            subscribeHeartbeat: vi.fn(() => () => {}),
            getCanale: vi.fn(() => canaleFinto()),
        };
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non leggibile/));
        expect(s.getByTestId('saldo-betfair-valore').textContent).toBe('—');
    });

    // ── 18/09 (raccordo) — canale locale 47331, topic "account" ──────────
    it('messaggio "account" recente dal canale locale → fresco, anche col battito vecchissimo', async () => {
        const onAccountRef: { current: ((d: unknown) => void) | null } = { current: null };
        const vecchissimo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        const deps = depsDi(account(), heartbeat({ ts: vecchissimo }), onAccountRef);
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non verificato di recente/));
        // il canale locale parla ORA: deve VINCERE sul battito vecchio
        onAccountRef.current?.({ available: 100, exposure: 0, checked_at: new Date().toISOString() });
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').getAttribute('title')).toMatch(/canale locale/i));
        expect(s.getByTestId('saldo-betfair-nota').textContent).not.toMatch(/non verificato di recente/);
    });

    it('un messaggio "manuale" (senza "available", ma CON un campo "checked_at" omonimo) NON viene letto come saldo', async () => {
        const onAccountRef: { current: ((d: unknown) => void) | null } = { current: null };
        const vecchissimo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        const deps = depsDi(account(), heartbeat({ ts: vecchissimo }), onAccountRef);
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non verificato di recente/));
        // un messaggio manuale che (per ipotesi) portasse anche un `checked_at`
        // non deve MAI essere confuso col saldo: si distingue guardando
        // `available` (contratto B1 §6/§19), non la sola presenza di `checked_at`.
        onAccountRef.current?.({ manual_pnl_eur: 12.3, manual_pnl_day: '2026-09-18', checked_at: new Date().toISOString() });
        // nessun cambiamento: resta il ripiego sul battito vecchio (dato un
        // margine per un eventuale re-render fuori da `act`, si aspetta un
        // istante e si verifica che NON sia mai passato a "canale locale")
        await new Promise((r) => setTimeout(r, 50));
        expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non verificato di recente/);
        expect(s.getByTestId('saldo-betfair-nota').getAttribute('title')).not.toMatch(/canale locale/i);
    });
});

describe('checkedAtDiMessaggioAccount — funzione pura, testata direttamente', () => {
    it('un messaggio di saldo (con "available") ne estrae il checked_at', () => {
        expect(checkedAtDiMessaggioAccount({ available: 12, exposure: 0, checked_at: '2026-09-18T10:00:00Z' }))
            .toBe('2026-09-18T10:00:00Z');
    });

    it('un messaggio "manuale" (senza "available"), anche con un checked_at omonimo, torna null', () => {
        expect(checkedAtDiMessaggioAccount({ manual_pnl_eur: 12.3, checked_at: '2026-09-18T10:00:00Z' })).toBeNull();
    });

    it('messaggio vuoto/malformato: null, mai un crash', () => {
        expect(checkedAtDiMessaggioAccount(null)).toBeNull();
        expect(checkedAtDiMessaggioAccount(undefined)).toBeNull();
        expect(checkedAtDiMessaggioAccount('stringa')).toBeNull();
        expect(checkedAtDiMessaggioAccount({ available: 12 })).toBeNull(); // checked_at assente
    });

    // ── FALSIFICAZIONE (eseguita, non solo dichiarata) ─────────────────────
    // mutazione manuale: tolto il controllo `typeof msg.available !== 'number'`
    // → il secondo test qui sopra diventa ROSSO (torna la stringa invece di
    // null). Ripristinato: md5 del file IDENTICO prima/dopo
    // (`6300559066ff5b72c382539c9ffd6715`).
});
