// ============================================================================
// soloTennis.test.ts — «deve partire SOLO lui, come ieri, a 3 euro».
//
// Qui si difende una cosa sola, ma è quella che muove denaro vero: avviare
// dalla scheda tennis NON deve accendere il calcio. Safe è un servizio solo,
// e `safe_activate('live')` da solo accende tutto quello che la mappa
// `strategy_modes` non ha spento.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    paramsSoloTennis, differenzeSoloTennis, altreInLiveAdesso, STAKE_TENNIS, STRATEGIE_SAFE,
} from './soloTennis';

/** i parametri come stanno sul servizio, con dentro anche roba che nessun tipo
 *  conosce: è esattamente quello che arriva dalla riga di control */
const CORRENTI = {
    stake: { backSize: 5, laySize: 2 },
    strategy_modes: { tennis: 'paper', base: 'live', esatto: 'live' },
    variants: ['base', 'esatto', 'punta', 'tennis'],
    auto_trade_tennis: false,
    tennis_exit_approval: true,
    daily_loss_stop: -50,
    exits: { due_game: true },
    chiave_che_nessuno_conosce: 42,
};

describe('paramsSoloTennis — in live ci va SOLO il tennis', () => {
    it('il tennis prende la modalità scelta, tutte le altre vanno in prova', () => {
        const p = paramsSoloTennis(CORRENTI, 'live');
        const modi = p.strategy_modes as Record<string, string>;
        expect(modi.tennis).toBe('live');
        for (const s of STRATEGIE_SAFE) {
            if (s !== 'tennis') expect(modi[s]).toBe('paper');
        }
    });

    it('nessuna strategia resta NON DICHIARATA: una chiave assente eredita il servizio, e in live sono soldi veri', () => {
        const p = paramsSoloTennis({ stake: { backSize: 3 } }, 'live');
        const modi = p.strategy_modes as Record<string, string>;
        for (const s of STRATEGIE_SAFE) expect(modi[s]).toBeDefined();
    });

    it('una strategia che oggi non conosciamo viene comunque SPENTA', () => {
        const p = paramsSoloTennis(
            { strategy_modes: { tennis: 'paper', strategia_nuova: 'live' } }, 'live',
        );
        expect((p.strategy_modes as Record<string, string>).strategia_nuova).toBe('paper');
    });

    it('avviare in PROVA non mette niente in live, nemmeno il tennis', () => {
        const p = paramsSoloTennis(CORRENTI, 'paper');
        const modi = p.strategy_modes as Record<string, string>;
        expect(Object.values(modi)).not.toContain('live');
    });
});

describe('paramsSoloTennis — lo stake è 3,00 € e non si discute', () => {
    it('backSize forzato a 3, laySize (che è del calcio) intatto', () => {
        const p = paramsSoloTennis(CORRENTI, 'live');
        expect(p.stake).toEqual({ backSize: STAKE_TENNIS, laySize: 2 });
        expect(STAKE_TENNIS).toBe(3);
    });

    it('anche se il servizio non dichiara nessuno stake', () => {
        const p = paramsSoloTennis({ variants: ['tennis'] }, 'live');
        expect((p.stake as Record<string, number>).backSize).toBe(3);
    });
});

describe('paramsSoloTennis — il bot deve poter ENTRARE davvero', () => {
    it('accende le entrate automatiche: il 14/09 erano spente e il bot non entrava', () => {
        expect(paramsSoloTennis(CORRENTI, 'live').auto_trade_tennis).toBe(true);
    });

    it('il tennis viene abilitato ad aprire se mancava', () => {
        const p = paramsSoloTennis({ variants: ['base'] }, 'live');
        expect(p.variants).toEqual(['base', 'tennis']);
    });

    // ⚠️ REVIEW 15/09, GRAVE — scrivere `['tennis']` su una colonna che non
    // aveva `variants` spegneva base, esatto e punta PER SEMPRE, anche in
    // prova: il default lo mette il servizio in lettura, non il database.
    it('se il servizio non dichiara `variants` NON si scrive niente', () => {
        expect('variants' in paramsSoloTennis({ stake: { backSize: 3 } }, 'live')).toBe(false);
        // un valore illeggibile si lascia PASSARE com'è: non lo si sostituisce
        // con `['tennis']`, che il servizio accetterebbe come lista valida
        expect(paramsSoloTennis({ variants: 'rotto' }, 'live').variants).toBe('rotto');
    });

    it('una lista vuota si lascia com’e’: e’ il servizio a metterci il default', () => {
        expect(paramsSoloTennis({ variants: [] }, 'live').variants).toEqual([]);
    });

    it('le varianti del calcio NON si tolgono: fermarle non è stato chiesto', () => {
        expect(paramsSoloTennis(CORRENTI, 'live').variants)
            .toEqual(['base', 'esatto', 'punta', 'tennis']);
    });
});

describe('paramsSoloTennis — non porta via niente', () => {
    it('tetti, uscite e chiavi ignote passano intatti', () => {
        const p = paramsSoloTennis(CORRENTI, 'live');
        expect(p.tennis_exit_approval).toBe(true);
        expect(p.daily_loss_stop).toBe(-50);
        expect(p.exits).toEqual({ due_game: true });
        expect(p.chiave_che_nessuno_conosce).toBe(42);
    });

    it('non muta i parametri di partenza', () => {
        const copia = JSON.parse(JSON.stringify(CORRENTI));
        paramsSoloTennis(CORRENTI, 'live');
        expect(CORRENTI).toEqual(copia);
    });
});

describe('differenzeSoloTennis — si dice PRIMA del clic', () => {
    it('elenca il calcio che si spegne, lo stake e le entrate', () => {
        const d = differenzeSoloTennis(CORRENTI, 'live').join(' · ');
        expect(d).toMatch(/base, esatto/);
        expect(d).toMatch(/3,00/);
        expect(d).toMatch(/entrate automatiche/);
    });

    it('se è già come deve essere, in prova non annuncia niente', () => {
        const gia = {
            stake: { backSize: 3 }, auto_trade_tennis: true,
            strategy_modes: { tennis: 'paper', base: 'paper' }, variants: ['tennis'],
        };
        expect(differenzeSoloTennis(gia, 'paper')).toEqual([]);
    });

    it('parametri non letti: nessuna promessa', () => {
        expect(differenzeSoloTennis(null, 'live')).toEqual([]);
        expect(differenzeSoloTennis({}, 'live')).toEqual([]);
    });
});

describe('altreInLiveAdesso — il calcio che opera davvero non si nasconde', () => {
    it('elenca le strategie non-tennis a soldi veri', () => {
        expect(altreInLiveAdesso('live', { tennis: 'live', base: 'live', punta: 'paper' }))
            .toEqual(['base']);
    });

    it('il tennis non si conta: la riga della plancia è già sua', () => {
        expect(altreInLiveAdesso('live', { tennis: 'live' })).toEqual([]);
    });

    it('servizio in prova = nessuna, il mode è un TETTO', () => {
        expect(altreInLiveAdesso('paper', { base: 'live' })).toEqual([]);
        expect(altreInLiveAdesso(null, { base: 'live' })).toEqual([]);
    });
});
