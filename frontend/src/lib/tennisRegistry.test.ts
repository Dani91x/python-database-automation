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

import { TENNIS_BOT_REGISTRY, HINT_ACCESO_DI_DEFAULT } from './tennis';

function proField(key: string) {
    const pro = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_pro');
    expect(pro).toBeDefined();
    const f = pro!.params.find((p) => p.key === key);
    expect(f).toBeDefined();
    return f!;
}

describe('TENNIS_BOT_REGISTRY tennis_pro (fix audit #9)', () => {
    // 25/09 (decisione utente): la superficie NON e' piu' un parametro della
    // scheda: la decide il runner per OGNI partita dal nome del torneo
    // (tennis_scalper/superficie.py). Il vecchio select mandava 'grass' ovunque.
    it('surface non e\' piu\' un parametro: la decide il runner dalla partita', () => {
        const pro = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_pro')!;
        expect(pro.params.find((p) => p.key === 'surface')).toBeUndefined();
        expect(pro.defaults).not.toHaveProperty('surface');
    });

    it('trend/adapt/maker ACCESI di default, con la dicitura della decisione utente', () => {
        const pro = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_pro')!;
        for (const k of ['trend', 'adapt', 'maker']) {
            expect(pro.defaults[k]).toBe('on');
            const f = proField(k);
            expect(f.bool).toBe(true);
            expect(f.hint).toContain(HINT_ACCESO_DI_DEFAULT);
            // spegnibili: l'opzione off c'e'
            expect((f.options ?? []).map((o) => o.value)).toEqual(expect.arrayContaining(['on', 'off']));
        }
        expect(HINT_ACCESO_DI_DEFAULT).toMatch(/ACCESO di default \(decisione utente 25\/09\)/);
        expect(HINT_ACCESO_DI_DEFAULT).toMatch(/mai certificato sul banco fuori dall'erba/);
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
