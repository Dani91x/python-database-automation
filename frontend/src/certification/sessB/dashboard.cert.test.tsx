// FASE 3 sessione B — Dashboard: lista partite + scheda partita + 7 pannelli, DATI VERI (sola lettura).
// Salva il testo visibile e il registro delle risposte RPC/select per ogni vista.
import { describe, it, expect, vi } from 'vitest';
import { render, waitFor, fireEvent } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('./clientB');
    return { supabase: m.supabase };
});
vi.mock('sonner', () => ({
    toast: Object.assign((m: string) => { void m; }, { success: () => {}, warning: () => {}, error: () => {}, info: () => {} }),
}));

import Dashboard from '@/pages/Dashboard';
import { blocked, log } from './clientB';
import { visibleText, sleep, save, guardWebSocket, wsSends, App } from './util';

guardWebSocket();
const FIXTURES = (process.env.SESSB_FIXTURES ?? '1492980,1498845,1637820,1528882,1533042').split(',');
const PANELS = ['Frequenze Mercati', 'Studio Ritardi', 'Poisson', 'Tactical Engine', 'Modelli ML', 'Direzione', 'Quote Betfair'];

function findButton(label: string): HTMLElement | undefined {
    return Array.from(document.querySelectorAll('button'))
        .find((b) => (b.textContent || '').trim().startsWith(label)) as HTMLElement | undefined;
}

(process.env.CERT_RUN === '1' ? describe : describe.skip)('dashboard sessione B', () => {
    it('lista partite', async () => {
        log.length = 0;
        const r = render(<App path={'/dashboard'}><Dashboard /></App>);
        await sleep(25_000);
        save('dash_list.txt', visibleText(document.body));
        for (const g of ['Friendlies Clubs', 'Primera Nacional', 'CONCACAF Nations League']) {
            const el = Array.from(document.querySelectorAll('button, [role="button"], h3, div'))
                .find((e) => (e.textContent || '').trim().startsWith(g) && /partit/.test(e.textContent || '') && (e.textContent || '').length < 80) as HTMLElement | undefined;
            if (el) { fireEvent.click(el); await sleep(1500); }
        }
        save('dash_list_aperta.txt', visibleText(document.body));
        save('dash_list_log.json', log.map((l) => ({ ...l, data: Array.isArray(l.data) ? { n: l.data.length, first: l.data[0], last: l.data[l.data.length - 1] } : l.data })));
        r.unmount();
        expect(blocked).toEqual([]);
    }, 120_000);

    for (const fx of FIXTURES) {
        it(`scheda ${fx}`, async () => {
            log.length = 0;
            const r = render(<App path={`/dashboard?fixture=${fx}`}><Dashboard /></App>);
            await waitFor(() => expect(findButton('Poisson')).toBeTruthy(), { timeout: 60_000 }).catch(() => {});
            await sleep(2_000);
            save(`dash_${fx}_scheda.txt`, visibleText(document.body));
            for (const p of PANELS) {
                const b = findButton(p);
                if (!b) { save(`dash_${fx}_${p.replace(/\s/g, '_')}.txt`, 'PULSANTE ASSENTE'); continue; }
                const before = log.length;
                fireEvent.click(b);
                await sleep(p === 'Frequenze Mercati' || p === 'Studio Ritardi' || p === 'Direzione' ? 25_000 : 10_000);
                const dlg = document.querySelector('[role="dialog"]');
                save(`dash_${fx}_${p.replace(/\s/g, '_')}.txt`, dlg ? visibleText(dlg) : visibleText(document.body));
                save(`dash_${fx}_${p.replace(/\s/g, '_')}_log.json`, log.slice(before));
                fireEvent.keyDown(dlg ?? document.body, { key: 'Escape' });
                await sleep(800);
            }
            r.unmount();
            expect(blocked).toEqual([]);
        }, 400_000);
    }

    it('nessuna scrittura', () => {
        save('dash_guard.json', { blocked, wsSends });
        expect(blocked).toEqual([]);
        expect(wsSends).toEqual([]);
    });
});
