// FASE 3 sessione B — casi limite della Dashboard (sola lettura): righe della lista, Ritardi HT su lega 667
// (stagione / ultime N), Frequenze HT 667, Direzione «stato attuale» (clic su una carta: solo lettura).
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('./clientB');
    return { supabase: m.supabase };
});
vi.mock('sonner', () => ({
    toast: Object.assign((m: string) => { void m; }, { success: () => {}, warning: () => {}, error: () => {}, info: () => {} }),
}));

import Dashboard from '@/pages/Dashboard';
import { RitardiPanel } from '@/components/dashboard/RitardiPanel';
import { MarketFrequencyPanel } from '@/components/dashboard/MarketFrequencyPanel';
import { DirezioneDashboard } from '@/components/dashboard/DirezioneDashboard';
import { blocked, log } from './clientB';
import { visibleText, sleep, save, guardWebSocket, wsSends, App } from './util';

guardWebSocket();
const btnText = (t: string, exact = false) => Array.from(document.querySelectorAll('button'))
    .find((b) => { const s = (b.textContent || '').replace(/\s+/g, ' ').trim(); return exact ? s === t : s.startsWith(t); }) as HTMLElement | undefined;
const dlg = () => document.querySelector('[role="dialog"]') ?? document.body;

(process.env.CERT_RUN === '1' ? describe : describe.skip)('casi limite dashboard', () => {
    it('righe della lista', async () => {
        const r = render(<App path="/dashboard"><Dashboard /></App>);
        await sleep(25_000);
        for (const g of ['Friendlies Clubs', 'Primera Nacional', 'Liga Pro Serie B']) {
            const b = btnText(g);
            if (b) { fireEvent.click(b); await sleep(1500); }
        }
        save('x_lista_righe.txt', visibleText(document.body));
        r.unmount();
    }, 90_000);

    it('ritardi 667 HT', async () => {
        log.length = 0;
        const r = render(<App path="/x"><RitardiPanel leagueId={667} leagueName="Friendlies Clubs" /></App>);
        fireEvent.click(btnText('Studio Ritardi')!);
        await sleep(3_000);
        fireEvent.click(btnText('Over Primo Tempo', true)!);
        fireEvent.click(btnText('Stagione', true)!);
        await sleep(25_000);
        save('x_ritardi_667_ovpt_stagione.txt', visibleText(dlg()));
        fireEvent.click(btnText('Ultime N', true)!);
        await sleep(20_000);
        save('x_ritardi_667_ovpt_ultime.txt', visibleText(dlg()));
        save('x_ritardi_667_log.json', log.map((l) => ({ ...l, data: (l.data as { meta?: unknown; stats?: unknown } | null)?.meta ? { meta: (l.data as { meta: unknown }).meta, stats: (l.data as { stats: unknown }).stats } : l.data })));
        r.unmount();
    }, 120_000);

    it('frequenze 667 HT', async () => {
        log.length = 0;
        const r = render(<App path="/x"><MarketFrequencyPanel leagueId={667} leagueName="Friendlies Clubs" /></App>);
        fireEvent.click(btnText('Frequenze Mercati')!);
        await sleep(3_000);
        const b = btnText('Under/Over Primo Tempo HT', true);
        if (b) fireEvent.click(b);
        await sleep(25_000);
        save('x_freq_667_ht.txt', visibleText(dlg()));
        save('x_freq_667_log.json', log.map((l) => ({ ...l, data: (l.data as { meta?: unknown } | null)?.meta ? { meta: (l.data as { meta: unknown }).meta, last: ((l.data as { points: unknown[] }).points ?? []).slice(-1) } : l.data })));
        r.unmount();
    }, 120_000);

    it('direzione stato attuale', async () => {
        log.length = 0;
        const r = render(<App path="/x"><DirezioneDashboard fixtureId="1492980" leagueName="First Division" homeName="Cobh Ramblers" awayName="Athlone Town" /></App>);
        fireEvent.click(btnText('Direzione')!);
        await sleep(12_000);
        const card = Array.from(dlg().querySelectorAll('button')).find((x) => (x.textContent || '').includes('Over 3.5')) as HTMLElement | undefined;
        if (card) fireEvent.click(card);
        await sleep(25_000);
        save('x_direzione_1492980_aperta.txt', visibleText(dlg()));
        save('x_direzione_log.json', log.map((l) => ({ ...l, data: (l.data as { meta?: unknown } | null)?.meta ? { meta: (l.data as { meta: unknown }).meta, stats: (l.data as { stats?: unknown }).stats, last: ((l.data as { points?: unknown[] }).points ?? []).slice(-1) } : l.data })));
        r.unmount();
    }, 120_000);

    it('nessuna scrittura', () => {
        save('x_guard.json', { blocked, wsSends });
        expect(blocked).toEqual([]);
    });
});
