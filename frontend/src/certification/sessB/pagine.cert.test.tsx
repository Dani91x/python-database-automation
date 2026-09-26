// FASE 3 sessione B — Analytics, Report personale, Live P&L, Omega, Safe, Mike (+ fogli parametri), DATI VERI.
// Solo letture: client clientB (RPC non volatili, scritture bloccate), realtime stub, canale locale spento.
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('./clientB');
    return { supabase: m.supabase };
});
vi.mock('sonner', () => ({
    toast: Object.assign((m: string) => { void m; }, { success: () => {}, warning: () => {}, error: () => {}, info: () => {} }),
}));

import Analytics from '@/pages/Analytics';
import ReportPersonale from '@/pages/ReportPersonale';
import LivePnl from '@/pages/LivePnl';
import Omega from '@/pages/Omega';
import Mike from '@/pages/Mike';
import SafeStrategy from '@/pages/SafeStrategy';
import { SafeStrategyProvider } from '@/components/safestrategy/SafeStrategyProvider';
import { blocked, log } from './clientB';
import { visibleText, sleep, save, guardWebSocket, wsSends, App } from './util';

guardWebSocket();
const ONLY = process.env.SESSB_ONLY ? process.env.SESSB_ONLY.split(',') : null;
const want = (n: string) => !ONLY || ONLY.includes(n);

function btn(pred: (b: HTMLElement) => boolean): HTMLElement | undefined {
    return Array.from(document.querySelectorAll('button')).find((b) => pred(b as HTMLElement)) as HTMLElement | undefined;
}
const byText = (t: string) => btn((b) => (b.textContent || '').replace(/\s+/g, ' ').trim().includes(t));
function slimLog(from = 0) {
    return log.slice(from).map((l) => ({ ...l, data: Array.isArray(l.data) && l.data.length > 60 ? { n: l.data.length, head: l.data.slice(0, 60) } : l.data }));
}
function wrap(el: React.ReactElement, path: string) {
    return render(<App path={path}>{el}</App>);
}

async function dumpBot(name: string, el: React.ReactElement, path: string) {
    log.length = 0;
    const r = wrap(el, path);
    await sleep(30_000);
    save(`${name}_iniziale.txt`, visibleText(document.body));
    save(`${name}_iniziale_log.json`, slimLog());
    const labels = Array.from(document.querySelectorAll('[role="tab"]')).map((t) => (t.textContent || '').trim()).filter(Boolean);
    for (const label of labels) {
        const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((t) => (t.textContent || '').trim() === label) as HTMLElement | undefined;
        if (!tab) continue;
        const b = log.length;
        fireEvent.mouseDown(tab); fireEvent.click(tab);
        await sleep(12_000);
        save(`${name}_tab_${label.replace(/[^\w]+/g, '_').slice(0, 30)}.txt`, visibleText(document.body));
        save(`${name}_tab_${label.replace(/[^\w]+/g, '_').slice(0, 30)}_log.json`, slimLog(b));
    }
    // foglio parametri (apertura in lettura, nessun Salva)
    const p = btn((x) => /Parametri/.test(x.getAttribute('title') || '') || /^Parametri/.test((x.textContent || '').trim()));
    if (p) {
        fireEvent.click(p);
        await sleep(3_000);
        const dlg = document.querySelector('[role="dialog"]');
        save(`${name}_parametri.txt`, dlg ? visibleText(dlg) : 'DIALOG ASSENTE');
        fireEvent.keyDown(dlg ?? document.body, { key: 'Escape' });
    } else save(`${name}_parametri.txt`, 'PULSANTE PARAMETRI ASSENTE');
    r.unmount();
}

(process.env.CERT_RUN === '1' ? describe : describe.skip)('pagine sessione B', () => {
    if (want('analytics')) it('analytics', async () => {
        log.length = 0;
        const r = wrap(<Analytics />, '/analytics');
        await sleep(30_000);
        save('analytics_motori.txt', visibleText(document.body));
        save('analytics_motori_log.json', slimLog());
        for (const t of ['Decisioni', 'Crea Strategia', 'Reportistiche', 'Backtest Automatico']) {
            const b0 = log.length;
            const b = byText(t);
            if (!b) { save(`analytics_${t}.txt`, 'TAB ASSENTE'); continue; }
            fireEvent.click(b);
            await sleep(t === 'Reportistiche' ? 60_000 : 25_000);
            save(`analytics_${t.replace(/\s/g, '_')}.txt`, visibleText(document.body));
            save(`analytics_${t.replace(/\s/g, '_')}_log.json`, slimLog(b0));
        }
        r.unmount();
    }, 400_000);

    if (want('report')) it('report personale', async () => {
        log.length = 0;
        const r = wrap(<ReportPersonale />, '/report-personale');
        await sleep(30_000);
        save('report_personale.txt', visibleText(document.body));
        save('report_personale_log.json', slimLog());
        r.unmount();
    }, 120_000);

    if (want('livepnl')) it('live pnl', async () => {
        log.length = 0;
        const r = wrap(<LivePnl />, '/live-pnl');
        await sleep(25_000);
        save('livepnl_tutte.txt', visibleText(document.body));
        save('livepnl_log.json', slimLog());
        for (const m of ['paper', 'live']) {
            const sel = Array.from(document.querySelectorAll('select')).find((s) => Array.from((s as HTMLSelectElement).options).some((o) => o.value === m)) as HTMLSelectElement | undefined;
            if (sel) { fireEvent.change(sel, { target: { value: m } }); await sleep(4_000); save(`livepnl_${m}.txt`, visibleText(document.body)); }
            else {
                const b = byText(m.toUpperCase()) ?? byText(m);
                if (b) { fireEvent.click(b); await sleep(4_000); save(`livepnl_${m}.txt`, visibleText(document.body)); }
            }
        }
        const selM = Array.from(document.querySelectorAll('select'))[0] as HTMLSelectElement | undefined;
        if (selM) fireEvent.change(selM, { target: { value: 'all' } });
        const dateIn = document.querySelector('input[type="date"]') as HTMLInputElement | null;
        if (dateIn) {
            const b0 = log.length;
            fireEvent.change(dateIn, { target: { value: '2026-09-14' } });
            await sleep(8_000);
            save('livepnl_2026-09-14.txt', visibleText(document.body));
            save('livepnl_2026-09-14_log.json', slimLog(b0));
        }
        r.unmount();
    }, 150_000);

    if (want('omega')) it('omega', async () => { await dumpBot('omega', <Omega />, '/omega'); }, 400_000);
    if (want('mike')) it('mike', async () => { await dumpBot('mike', <Mike />, '/mike'); }, 400_000);
    if (want('safe')) it('safe', async () => { await dumpBot('safe', <SafeStrategyProvider><SafeStrategy /></SafeStrategyProvider>, '/safe-strategy'); }, 400_000);

    it('nessuna scrittura', () => {
        save(`pagine_guard_${ONLY ? ONLY.join('_') : 'tutte'}.json`, { blocked, wsSends });
        expect(wsSends).toEqual([]);
    });
});
