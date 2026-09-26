// ============================================================================
// plancia.e2e.test.tsx — E2E FASE 2 (26/09): passo D in SOLA LETTURA.
// Monta l'hook VERO della Control Room (`useControlRoom`) con il client Supabase VERO e salva il
// view-model (quello che la pagina mostra: righe bot, realizzato di oggi, totali, posizioni, proposte)
// in un file con l'istante, per il confronto con il DB (script Python). GUARDIA: solo letture
// (`get_*`, `betfair_live_is_owner`, `trading_*`); qualunque altra RPC viene BLOCCATA prima dell'invio;
// scritture dirette su tabella gia' bloccate da `clientVero`.
// Uso: npx vitest run --config e2e_fase2/vitest.e2e.config.ts plancia -t D1
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const bloccateD: string[] = [];
const lette: string[] = [];
vi.mock('@/integrations/supabase/client', async () => {
    const m = await import('../e2e_fase1/clientVero');
    const s = m.supabase as unknown as Record<string, unknown> & { rpc: (...a: unknown[]) => unknown };
    const vera = s.rpc;
    s.rpc = (name: unknown, args?: unknown, ...rest: unknown[]) => {
        const n = String(name);
        if (!/^(get_[a-z0-9_]+|betfair_live_is_owner|trading_[a-z0-9_]+)$/.test(n)) {
            bloccateD.push(n);
            throw new Error(`FASE2-D: RPC non di lettura BLOCCATA: ${n}`);
        }
        lette.push(n);
        return vera(name, args, ...rest);
    };
    return { supabase: m.supabase };
});

import { useControlRoom } from '@/components/controlroom/useControlRoom';

const OUT = resolve('C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/AUDIT_2026-09-25/e2e_fase2/plancia');
mkdirSync(OUT, { recursive: true });

describe('FASE 2 — D: il view-model vero della Control Room', () => {
    it('D1 fotografia del view-model', async () => {
        const { result, unmount } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false), { timeout: 60_000 });
        // un secondo giro di letture per stabilizzare (canali locali possono arrivare dopo)
        await new Promise((r) => setTimeout(r, 8000));
        const vm = result.current as unknown as Record<string, unknown>;
        const ts = new Date().toISOString();
        const nome = `vm_${ts.replace(/[:.]/g, '-')}.json`;
        const sicuro = (v: unknown) => {
            const visti = new WeakSet();
            return JSON.parse(JSON.stringify(v, (_k, x) => {
                if (typeof x === 'function') return undefined;
                if (x && typeof x === 'object') { if (visti.has(x)) return '[ciclo]'; visti.add(x); }
                if (x instanceof Map) return Object.fromEntries(x);
                return x;
            }));
        };
        writeFileSync(resolve(OUT, nome), JSON.stringify({ ts, rpc_lette: [...new Set(lette)], bloccate: bloccateD, vm: sicuro(vm) }, null, 1), 'utf8');
        unmount();
        expect(bloccateD).toEqual([]);
    });
});
