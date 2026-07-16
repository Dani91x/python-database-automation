// Fix audit 16/07 (#9) — TENNIS_BOT_REGISTRY, scheda tennis_pro:
//  * le opzioni superficie coprono TUTTE le chiavi su cui il bot Python si
//    biforca: ("grass","fast") vs il resto (clay/hard/WTA);
//  * hint VERITIERI: `trend` FLIPPA i setup di dominio in trend-following BACK
//    (non è un "filtro expected-rate"); `adapt` sceglie la DIREZIONE dal regime
//    (Kaufman ER), non riduce lo stake dopo perdite.
import { describe, it, expect, vi } from 'vitest';

// tennis.ts importa il client Supabase (createClient a import-time): in test le
// VITE_SUPABASE_* non esistono → mock del modulo (qui testiamo SOLO il registro).
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn() },
}));

import { TENNIS_BOT_REGISTRY } from './tennis';

function proField(key: string) {
    const pro = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_pro');
    expect(pro).toBeDefined();
    const f = pro!.params.find((p) => p.key === key);
    expect(f).toBeDefined();
    return f!;
}

describe('TENNIS_BOT_REGISTRY tennis_pro (fix audit #9)', () => {
    it('surface copre anche fast (veloce/indoor) e wta', () => {
        const values = (proField('surface').options ?? []).map((o) => o.value);
        expect(values).toEqual(expect.arrayContaining(['hard', 'clay', 'grass', 'fast', 'wta']));
    });

    it('hint di trend descrive il flip trend-following (BACK del dominante)', () => {
        const hint = proField('trend').hint.toLowerCase();
        expect(hint).toContain('back');
        expect(hint).toContain('trend-following');
        // il vecchio hint FALSO parlava di "expected-rate": non deve tornare
        expect(hint).not.toContain('expected-rate');
    });

    it('hint di adapt descrive la direzione dal regime (Kaufman ER), non lo stake', () => {
        const hint = proField('adapt').hint.toLowerCase();
        expect(hint).toContain('direzione');
        expect(hint).toContain('kaufman');
        // il vecchio hint FALSO parlava di riduzione stake dopo perdite
        expect(hint).not.toContain('stake');
    });
});
