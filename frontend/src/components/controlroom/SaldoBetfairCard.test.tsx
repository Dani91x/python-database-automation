import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, waitFor, act } from '@testing-library/react';
import { SaldoBetfairCard, checkedAtDiMessaggioAccount, CANALI_SALDO } from './SaldoBetfairCard';
import type { LiveAccountRow, LiveHeartbeatRow } from '@/lib/liveOrders';
import { getLocalChannel, type LocalChannel } from '@/lib/localChannel';

// 23/09 — il singleton vero aprirebbe WebSocket su 127.0.0.1: qui un finto con
// la stessa firma (`subscribe(topic, cb) → off`), per verificare il DEFAULT.
vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig<typeof import('@/lib/localChannel')>()),
    getLocalChannel: vi.fn(() => ({ subscribe: vi.fn(() => () => {}) })),
}));

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
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da \d\d:\d\d/));
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
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da \d\d:\d\d/));
        // il canale locale parla ORA: deve VINCERE sul battito vecchio
        onAccountRef.current?.({ available: 100, exposure: 0, checked_at: new Date().toISOString() });
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').getAttribute('title')).toMatch(/canale locale/i));
        expect(s.getByTestId('saldo-betfair-nota').textContent).not.toMatch(/non aggiornato da \d\d:\d\d/);
    });

    it('un messaggio "manuale" (senza "available", ma CON un campo "checked_at" omonimo) NON viene letto come saldo', async () => {
        const onAccountRef: { current: ((d: unknown) => void) | null } = { current: null };
        const vecchissimo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        const deps = depsDi(account(), heartbeat({ ts: vecchissimo }), onAccountRef);
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da \d\d:\d\d/));
        // un messaggio manuale che (per ipotesi) portasse anche un `checked_at`
        // non deve MAI essere confuso col saldo: si distingue guardando
        // `available` (contratto B1 §6/§19), non la sola presenza di `checked_at`.
        onAccountRef.current?.({ manual_pnl_eur: 12.3, manual_pnl_day: '2026-09-18', checked_at: new Date().toISOString() });
        // nessun cambiamento: resta il ripiego sul battito vecchio (dato un
        // margine per un eventuale re-render fuori da `act`, si aspetta un
        // istante e si verifica che NON sia mai passato a "canale locale")
        await new Promise((r) => setTimeout(r, 50));
        expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da \d\d:\d\d/);
        expect(s.getByTestId('saldo-betfair-nota').getAttribute('title')).not.toMatch(/canale locale/i);
    });
});

// ── 23/09 — il VALORE dal topic "account" (bug: saldo fermo in pagina) ─────
describe('SaldoBetfairCard — valore dal canale "account" (23/09)', () => {
    /** N canali finti: ognuno registra la sua callback "account". */
    function canaliFinti(n: number) {
        const cbs: Array<((d: unknown) => void) | null> = Array.from({ length: n }, () => null);
        const canali = cbs.map((_, i) => ({
            subscribe: vi.fn((topic: string, cb: (d: unknown) => void) => {
                if (topic === 'account') cbs[i] = cb;
                return () => { cbs[i] = null; };
            }),
        }) as unknown as LocalChannel);
        return { canali, invia: (i: number, d: unknown) => cbs[i]?.(d) };
    }
    function depsCanali(a: LiveAccountRow | null, h: LiveHeartbeatRow | null, canali: LocalChannel[]) {
        return {
            fetchAccount: vi.fn(async () => a),
            subscribeAccount: vi.fn(() => () => {}),
            fetchHeartbeat: vi.fn(async () => h),
            subscribeHeartbeat: vi.fn(() => () => {}),
            getCanali: vi.fn(() => canali),
        };
    }
    const vecchio = (s: number) => new Date(Date.now() - s * 1000).toISOString();

    it('un saldo sul topic "account" più recente del database AGGIORNA il numero e l’età', async () => {
        const { canali, invia } = canaliFinti(1);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ available: 100, exposure: 0, updated_at: vecchio(600) }), heartbeat({ ts: vecchio(3600) }), canali)} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/100,00/));
        expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da \d\d:\d\d/);
        act(() => invia(0, { available: 250.5, exposure: -12, checked_at: new Date().toISOString() }));
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/250,50/));
        expect(s.getByTestId('saldo-betfair-esposizione').textContent).toMatch(/12,00/);
        expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/controllato: \d+ s/);
        expect(s.getByTestId('saldo-betfair-nota').textContent).not.toMatch(/non aggiornato/);
    });

    it('un messaggio VECCHIO (checked_at precedente) è ignorato, anche se arriva dopo e da un altro canale', async () => {
        const { canali, invia } = canaliFinti(2);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ available: 100, updated_at: vecchio(600) }), heartbeat(), canali)} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/100,00/));
        act(() => invia(0, { available: 250, exposure: 0, checked_at: vecchio(5) }));
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/250,00/));
        act(() => invia(1, { available: 90, exposure: 0, checked_at: vecchio(60) }));
        await new Promise((r) => setTimeout(r, 30));
        expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/250,00/);
        // uno PIU' recente dall'altro canale invece vince
        act(() => invia(1, { available: 77, exposure: 0, checked_at: new Date().toISOString() }));
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/77,00/));
    });

    it('un messaggio del canale più vecchio della riga del database non scavalca il database', async () => {
        const { canali, invia } = canaliFinti(1);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ available: 100, updated_at: vecchio(2) }), heartbeat(), canali)} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/100,00/));
        act(() => invia(0, { available: 55, exposure: 0, checked_at: vecchio(300) }));
        await new Promise((r) => setTimeout(r, 30));
        expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/100,00/);
    });

    it('CANALI MUTI = comportamento di prima: numero del database, «ultimo cambio»', async () => {
        const { canali } = canaliFinti(3);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ available: 321.1, updated_at: vecchio(8) }), heartbeat(), canali)} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/321,10/));
        expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/ultimo cambio: \d+ s/);
        // tutti e tre i canali sono stati ascoltati sul topic "account"
        for (const c of canali) expect((c.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe('account');
    });

    it('saldo non verificato: «non aggiornato da HH:MM» con l’ora dell’ultima lettura, mai un numero muto', async () => {
        const ora = new Date(Date.now() - 45 * 60 * 1000);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ updated_at: ora.toISOString() }), heartbeat({ ts: vecchio(3600) }), canaliFinti(1).canali)} />);
        const hhmm = new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', hour12: false }).format(ora);
        // F2: a cavallo della mezzanotte di Roma (fra le 00:00 e le 00:45) i 45
        // minuti fa sono di IERI e il testo porta anche la data.
        const giorno = (d: Date) => new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit' }).format(d);
        const atteso = giorno(ora) === giorno(new Date()) ? hhmm : `${giorno(ora)} ${hhmm}`;
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toContain(`non aggiornato da ${atteso}`));
    });

    it('F2: ultimo controllo di un altro giorno -> "non aggiornato da GG/MM HH:MM", mai un\'ora che sembra di oggi', async () => {
        const ieri = new Date(Date.now() - 30 * 3600 * 1000);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ updated_at: ieri.toISOString() }), heartbeat({ ts: vecchio(3600) }), canaliFinti(1).canali)} />);
        const gm = new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit' }).format(ieri);
        const hhmm = new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', hour12: false }).format(ieri);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toContain(`non aggiornato da ${gm} ${hhmm}`));
    });

    it('F2: ultimo controllo di oggi -> solo HH:MM, senza data', async () => {
        // 1 minuto fa (sempre oggi, salvo il minuto dopo la mezzanotte) e battito vecchio
        const ora = new Date(Date.now() - 60 * 1000);
        const s = render(<SaldoBetfairCard deps={depsCanali(account({ updated_at: ora.toISOString() }), heartbeat({ ts: vecchio(3600) }), canaliFinti(1).canali)} />);
        const giorno = (d: Date) => new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit' }).format(d);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da /));
        if (giorno(ora) === giorno(new Date())) {
            expect(s.getByTestId('saldo-betfair-nota').textContent).toMatch(/non aggiornato da \d\d:\d\d$/);
        }
    });

    it('di default ascolta i 5 canali dei processi che piazzano ordini veri (porte esistenti)', async () => {
        expect([...CANALI_SALDO]).toEqual(['calcio', 'tennis', 'mike', 'omega', 'safe']);
        const spia = getLocalChannel as unknown as ReturnType<typeof vi.fn>;
        spia.mockClear();
        const deps = {
            fetchAccount: vi.fn(async () => account()),
            subscribeAccount: vi.fn(() => () => {}),
            fetchHeartbeat: vi.fn(async () => heartbeat()),
            subscribeHeartbeat: vi.fn(() => () => {}),
        };
        const s = render(<SaldoBetfairCard deps={deps} />);
        await waitFor(() => expect(s.getByTestId('saldo-betfair-valore').textContent).toMatch(/1234,56/));
        expect(spia.mock.calls.map((c) => c[0])).toEqual(['calcio', 'tennis', 'mike', 'omega', 'safe']);
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
