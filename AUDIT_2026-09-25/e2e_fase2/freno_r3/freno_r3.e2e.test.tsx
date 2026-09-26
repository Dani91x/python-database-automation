// ============================================================================
// freno.e2e.test.tsx — E2E FASE 2 (26/09), Z13.4: il FRENO dalla Control Room (componente VERO
// `RigaFreno`, client Supabase VERO). Seconda e ultima scrittura ammessa dal brief.
// GUARDIA: l'unica RPC non di lettura ammessa e' `set_live_kill_switch` (tira: p_on=true in F1;
// rilascia: p_on=false in F2). Tutto il resto e' BLOCCATO prima dell'invio.
// Fotografia prima/dopo di `betfair_live_settings` e riga oraria in ACCENSIONE_ORA.txt.
//   F1: npx vitest run --config e2e_fase2/vitest.e2e.config.ts freno -t F1
//   F2: npx vitest run --config e2e_fase2/vitest.e2e.config.ts freno -t F2
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, act, cleanup } from '@testing-library/react';
import { appendFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const registro: { ts: string; rpc: string; args: unknown; esito: string }[] = [];
const ATTESO: { on: boolean | null } = { on: null };
vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('../e2e_fase1/clientVero');
    const s = m.supabase as unknown as Record<string, unknown> & { rpc: (...a: unknown[]) => unknown };
    const vera = s.rpc;
    s.rpc = (name: unknown, args?: unknown, ...rest: unknown[]) => {
        const n = String(name);
        const lettura = /^(get_[a-z0-9_]+|betfair_live_is_owner|trading_[a-z0-9_]+)$/.test(n);
        if (!lettura) {
            const on = (args as { p_on?: unknown } | undefined)?.p_on;
            if (n !== 'set_live_kill_switch' || on !== ATTESO.on) {
                registro.push({ ts: new Date().toISOString(), rpc: n, args, esito: 'BLOCCATA' });
                throw new Error(`FASE2-FRENO: RPC BLOCCATA: ${n} ${JSON.stringify(args)}`);
            }
            registro.push({ ts: new Date().toISOString(), rpc: n, args, esito: 'inviata' });
        }
        return vera(name, args, ...rest);
    };
    return { supabase: m.supabase };
});

import { raw } from '../e2e_fase1/clientVero';
import { RigaFreno } from '@/components/controlroom/RigaFreno';

const MAIN = 'C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/AUDIT_2026-09-25/e2e_fase2';
const OUT = resolve(MAIN, 'freno_r3');
mkdirSync(OUT, { recursive: true });
const settings = async () => (await raw.from('betfair_live_settings').select('*').eq('id', 1).single()).data as Record<string, unknown>;
const pausa = (ms: number) => new Promise((r) => setTimeout(r, ms));
function ora(riga: string) {
    const d = new Date();
    appendFileSync(resolve(MAIN, 'ACCENSIONE_ORA.txt'),
        `${riga}\tlocale ${d.toLocaleString('it-IT', { timeZone: 'Europe/Rome', hour12: false })}\tUTC ${d.toISOString()}\n`, 'utf8');
}
async function attendiTestId(s: ReturnType<typeof render>, id: string, ms = 15000) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
        if (s.queryByTestId(id)) return;
        await act(async () => { await pausa(250); });
    }
    throw new Error(`non comparso: ${id}`);
}
async function clicca(s: ReturnType<typeof render>, id: string, passi: string[]) {
    const el = s.getByTestId(id);
    if ((el as HTMLButtonElement).disabled) throw new Error(`disabilitato: ${id}`);
    passi.push(`${new Date().toISOString()} clic ${id} («${el.textContent?.trim()}»)`);
    await act(async () => { fireEvent.click(el); });
}

describe('FASE 2 — RIAVVIO 3 — Z13.4 freno (3° ciclo)', () => {
    it('F0 falsificazione guardia: p_on sbagliato e altre RPC bloccate', async () => {
        const { supabase } = await import('@/integrations/supabase/client');
        const rpc = (supabase as unknown as { rpc: (n: string, a?: unknown) => unknown }).rpc;
        ATTESO.on = null;
        expect(() => rpc('set_live_kill_switch', { p_on: true })).toThrow(/BLOCCATA/);
        expect(() => rpc('set_live_order_mode', { p_mode: 'live' })).toThrow(/BLOCCATA/);
        expect(registro.every((r) => r.esito === 'BLOCCATA')).toBe(true);
    });

    it('F1 tira il freno (un clic)', async () => {
        const passi: string[] = [];
        const prima = await settings();
        writeFileSync(resolve(OUT, 'F1_prima.json'), JSON.stringify(prima, null, 1));
        expect([prima.order_mode, prima.kill_switch]).toEqual(['paper', false]);
        ATTESO.on = true;
        const s = render(<RigaFreno />);
        await attendiTestId(s, 'cr-freno-tira');
        passi.push(`a video prima: stato=${s.queryByTestId('cr-freno-stato')?.textContent} fonte=${s.queryByTestId('cr-freno-fonte')?.textContent}`);
        await clicca(s, 'cr-freno-tira', passi);
        const t0 = Date.now();
        while (Date.now() - t0 < 15000 && (await settings()).kill_switch !== true) await pausa(300);
        const dopo = await settings();
        writeFileSync(resolve(OUT, 'F1_dopo.json'), JSON.stringify(dopo, null, 1));
        ora(`R3 FRENO TIRATO\tkill_switch=${dopo.kill_switch}\torder_mode=${dopo.order_mode}`);
        await act(async () => { await pausa(1500); });
        passi.push(`a video dopo: stato=${s.queryByTestId('cr-freno-stato')?.textContent}`);
        writeFileSync(resolve(OUT, 'F1_esito.json'), JSON.stringify({ passi, registro }, null, 1));
        s.unmount(); cleanup();
        expect([dopo.kill_switch, dopo.order_mode]).toEqual([true, 'paper']);
    });

    it('F2 rilascia il freno (doppia conferma)', async () => {
        const passi: string[] = [];
        const prima = await settings();
        writeFileSync(resolve(OUT, 'F2_prima.json'), JSON.stringify(prima, null, 1));
        expect(prima.kill_switch).toBe(true);
        ATTESO.on = false;
        const s = render(<RigaFreno />);
        await attendiTestId(s, 'cr-freno-rilascia');
        await clicca(s, 'cr-freno-rilascia', passi);
        await act(async () => { await pausa(500); });
        await attendiTestId(s, 'cr-freno-conferma-1');
        await clicca(s, 'cr-freno-conferma-1', passi);
        await act(async () => { await pausa(500); });
        const intermedio = (await settings()).kill_switch;
        passi.push(`dopo 2 clic su 3: kill_switch=${intermedio}`);
        await attendiTestId(s, 'cr-freno-conferma-2');
        await clicca(s, 'cr-freno-conferma-2', passi);
        const t0 = Date.now();
        while (Date.now() - t0 < 15000 && (await settings()).kill_switch !== false) await pausa(300);
        const dopo = await settings();
        writeFileSync(resolve(OUT, 'F2_dopo.json'), JSON.stringify(dopo, null, 1));
        ora(`R3 FRENO RILASCIATO\tkill_switch=${dopo.kill_switch}\torder_mode=${dopo.order_mode}`);
        writeFileSync(resolve(OUT, 'F2_esito.json'), JSON.stringify({ passi, registro }, null, 1));
        s.unmount(); cleanup();
        expect(intermedio).toBe(true);
        expect([dopo.kill_switch, dopo.order_mode]).toEqual([false, 'paper']);
    });
});
