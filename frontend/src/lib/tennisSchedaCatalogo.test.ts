// 08/10 sera (D-4, decisione dell'utente: "esporre") - PARITA' fra la SCHEDA dei
// bot tennis (`TENNIS_BOT_REGISTRY`, lib/tennis.ts: e' cio' che l'utente vede e
// salva) e il CATALOGO del banco (`CATALOGO_BOT`, generato da Python
// `replay_bot.parametri_modificabili`, che legge i default dall'ISTANZA VERA del
// bot costruita da `_instantiate_bot`).
//
//  * stesse chiavi (il catalogo ha in piu' solo lo stake, che la scheda tiene
//    nell'interruttore);
//  * stesso default di produzione (scenario `base` del banco = preset del
//    runner + default della classe): la scheda non cambia il bot finche'
//    l'utente non tocca un numero;
//  * limiti della scheda DENTRO quelli del catalogo (il catalogo si allarga
//    solo dove uno scenario del banco usa gia' un valore fuori dalla scheda);
//  * le soglie che `gate-aperto` apriva fuori dalla scheda e che il bot LEGGE
//    ci sono; quelle che il bot NON legge (`min_total_matched`, `min_matched`
//    dello scalper) NON ci sono: sarebbe una bugia a schermo.
import { describe, it, expect, vi } from 'vitest';

// tennis.ts importa il client Supabase (createClient a import-time): in test le
// VITE_SUPABASE_* non esistono -> mock del modulo (qui si confrontano i registri).
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn() },
}));

import { TENNIS_BOT_REGISTRY, type TennisBotKey } from './tennis';
import { CATALOGO_BOT } from './replayBotCatalogo';
import type { VoceParametro } from './replayBot';

const BOT: TennisBotKey[] = ['tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing'];

function vociDelBanco(bot: TennisBotKey, scenario = 'base'): Map<string, VoceParametro> {
    const cat = CATALOGO_BOT.find((b) => b.bot === bot);
    expect(cat, bot).toBeDefined();
    const sc = cat!.scenari.find((s) => s.scenario === scenario);
    expect(sc, `${bot}/${scenario}`).toBeDefined();
    return new Map(sc!.parametri.map((v) => [v.chiave, v]));
}

function scheda(bot: TennisBotKey) {
    const d = TENNIS_BOT_REGISTRY.find((x) => x.key === bot);
    expect(d, bot).toBeDefined();
    return d!;
}

/** D-4: le soglie che `gate-aperto` apre e che il bot legge (referto del
 *  cantiere 6, par. 5), ora nella scheda. */
const ESPOSTE_D4: Record<TennisBotKey, string[]> = {
    tennis_scalper: ['warmup_ms'],
    tennis_pro: ['min_book_size', 'price_min'],
    tennis_flb: ['min_lay_size'],
    tennis_swing: ['conf_ticks', 'min_matched', 'price_max', 'price_min'],
};

/** chiavi che il bot NON legge (o che lo scenario non cambia): mai a schermo */
const MAI_A_SCHERMO: Record<TennisBotKey, string[]> = {
    tennis_scalper: ['min_matched', 'min_total_matched'],
    tennis_pro: ['min_total_matched'],
    tennis_flb: ['min_total_matched'],
    tennis_swing: ['min_total_matched'],
};

describe('scheda dei bot tennis = catalogo del banco (D-4)', () => {
    it.each(BOT)('%s: stesse chiavi (il catalogo ha in piu\' solo lo stake)', (bot) => {
        const banco = [...vociDelBanco(bot).keys()].filter((k) => k !== 'stake').sort();
        const ui = scheda(bot).params.map((f) => f.key).sort();
        expect(ui).toEqual(banco);
        // i default sono SOLO quelli dei campi: l'armatura li manda tutti al bot
        // (`TennisBotPanel` parte da `defaults`), una chiave in piu' arriverebbe al bot
        expect(Object.keys(scheda(bot).defaults).sort()).toEqual(ui);
    });

    it.each(BOT)('%s: default della scheda = default di produzione del bot', (bot) => {
        const banco = vociDelBanco(bot);
        const d = scheda(bot);
        for (const f of d.params) {
            const v = banco.get(f.key)!;
            const def = d.defaults[f.key];
            expect(def, `${bot}.${f.key}: default mancante nella scheda`).toBeDefined();
            if (v.tipo === 'bool') {
                expect(def, `${bot}.${f.key}`).toBe(v.default ? 'on' : 'off');
            } else if (v.tipo === 'scelta') {
                expect(def, `${bot}.${f.key}`).toBe(v.default);
                const valori = (f.options ?? []).map((o) => o.value).sort();
                expect(valori, `${bot}.${f.key}`).toEqual([...(v.scelte ?? [])].sort());
            } else {
                expect(Number(def), `${bot}.${f.key}`).toBeCloseTo(Number(v.default), 9);
            }
        }
    });

    it.each(BOT)('%s: limiti della scheda dentro quelli del catalogo', (bot) => {
        const banco = vociDelBanco(bot);
        for (const f of scheda(bot).params) {
            const v = banco.get(f.key)!;
            if (v.tipo !== 'int' && v.tipo !== 'float') continue;
            expect(f.min, `${bot}.${f.key} min`).toBeGreaterThanOrEqual(v.min!);
            expect(f.max, `${bot}.${f.key} max`).toBeLessThanOrEqual(v.max!);
            expect(f.step, `${bot}.${f.key} passo`).toBeGreaterThan(0);
            // il default sta nei limiti della scheda (il campo non si apre fuori scala)
            const def = Number(scheda(bot).defaults[f.key]);
            expect(def, `${bot}.${f.key} default`).toBeGreaterThanOrEqual(f.min);
            expect(def, `${bot}.${f.key} default`).toBeLessThanOrEqual(f.max);
        }
    });

    it.each(BOT)('%s: le soglie di gate-aperto che il bot legge sono nella scheda', (bot) => {
        const ui = new Map(scheda(bot).params.map((f) => [f.key, f]));
        const aperto = vociDelBanco(bot, 'gate-aperto');
        for (const k of ESPOSTE_D4[bot]) {
            const f = ui.get(k);
            expect(f, `${bot}.${k} non e' nella scheda`).toBeDefined();
            expect(f!.label.trim().length, `${bot}.${k} senza etichetta`).toBeGreaterThan(0);
            expect(f!.hint.trim().length, `${bot}.${k} senza spiegazione`).toBeGreaterThan(0);
            // il valore che il banco usa in gate-aperto si puo' impostare dalla scheda
            const g = Number(aperto.get(k)!.default);
            expect(g, `${bot}.${k}: gate-aperto ${g} fuori dalla scheda`).toBeGreaterThanOrEqual(f!.min);
            expect(g, `${bot}.${k}: gate-aperto ${g} fuori dalla scheda`).toBeLessThanOrEqual(f!.max);
        }
    });

    it.each(BOT)('%s: le chiavi che il bot NON legge non sono a schermo', (bot) => {
        const ui = scheda(bot).params.map((f) => f.key);
        const banco = [...vociDelBanco(bot).keys()];
        for (const k of MAI_A_SCHERMO[bot]) {
            expect(ui, `${bot}.${k}`).not.toContain(k);
            expect(banco, `${bot}.${k}`).not.toContain(k);
        }
    });
});
