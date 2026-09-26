// FASE 3 sessione B — Safe: sotto-scheda «Trade» (tabella posizioni) sui dati veri, sola lettura.
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('./clientB');
    return { supabase: m.supabase };
});
vi.mock('sonner', () => ({
    toast: Object.assign((m: string) => { void m; }, { success: () => {}, warning: () => {}, error: () => {}, info: () => {} }),
}));

import SafeStrategy from '@/pages/SafeStrategy';
import { SafeStrategyProvider } from '@/components/safestrategy/SafeStrategyProvider';
import { blocked, log } from './clientB';
import { visibleText, sleep, save, guardWebSocket, wsSends, App } from './util';

guardWebSocket();

(process.env.CERT_RUN === '1' ? describe : describe.skip)('safe trade', () => {
    it('sotto-scheda Trade', async () => {
        log.length = 0;
        const r = render(<App path="/safe-strategy"><SafeStrategyProvider><SafeStrategy /></SafeStrategyProvider></App>);
        await sleep(30_000);
        const b = Array.from(document.querySelectorAll('button, [role="tab"]'))
            .find((x) => /^Trade\s*\(/.test((x.textContent || '').trim())) as HTMLElement | undefined;
        if (b) { fireEvent.mouseDown(b); fireEvent.click(b); }
        await sleep(10_000);
        save('safe_trade.txt', visibleText(document.body));
        save('safe_trade_log.json', log.filter((l) => l.name === 'get_safe_state').slice(0, 1));
        save('safe_trade_guard.json', { trovato: Boolean(b), blocked, wsSends });
        r.unmount();
        expect(blocked).toEqual([]);
    }, 120_000);
});
