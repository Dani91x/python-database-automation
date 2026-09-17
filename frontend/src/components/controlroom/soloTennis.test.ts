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
    stakeTennisEffettivo, accensioniSoloTennis,
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

describe('paramsSoloTennis — lo stake e’ 3,00 € e non si discute', () => {
    // ⚠️ B.5, 16/09 — lo stake del tennis si scrive sulla chiave SUA.
    // Prima andava su `stake.backSize`, che pero’ valeva anche per la PUNTA:
    // portare il tennis a 3 portava a 3 anche la punta, in silenzio.
    it('si scrive su `stake.per_strategia.tennis`; backSize e laySize restano intatti', () => {
        const p = paramsSoloTennis(CORRENTI, 'live');
        expect(p.stake).toEqual({
            backSize: 5, laySize: 2, per_strategia: { tennis: STAKE_TENNIS },
        });
        expect(STAKE_TENNIS).toBe(3);
    });

    it('anche se il servizio non dichiara nessuno stake', () => {
        const p = paramsSoloTennis({ variants: ['tennis'] }, 'live');
        expect(stakeTennisEffettivo(p)).toBe(3);
    });

    it('lo stake della PUNTA non si muove: erano la stessa chiave, adesso no', () => {
        const p = paramsSoloTennis(CORRENTI, 'live');
        expect((p.stake as Record<string, unknown>).backSize).toBe(5);
    });
});

describe('paramsSoloTennis — auto_trade_tennis NON e’ il suo interruttore', () => {
    // ⚠️ REPERTO 17/09 sera — `auto_trade_tennis` governa il SECONDO motore
    // (opportunita’ di modello tennis, paper), non le entrate della Strategia
    // S. La scheda «solo tennis» accende la Strategia S da `variants`, sempre:
    // `auto_trade_tennis` lo lascia esattamente com’e’, qualunque sia.
    it('con auto_trade_tennis:true nei correnti, resta true', () => {
        const p = paramsSoloTennis({ ...CORRENTI, auto_trade_tennis: true }, 'live');
        expect(p.auto_trade_tennis).toBe(true);
    });

    it('con auto_trade_tennis:false nei correnti, resta false (NON lo accende)', () => {
        const p = paramsSoloTennis({ ...CORRENTI, auto_trade_tennis: false }, 'live');
        expect(p.auto_trade_tennis).toBe(false);
    });

    it('assente nei correnti, resta assente: la scheda non lo scrive', () => {
        const p = paramsSoloTennis({ variants: ['tennis'] }, 'live');
        expect(p.auto_trade_tennis).toBeUndefined();
    });

    // ⚠️ 16/09 — `variants` adesso dice CHI E’ ACCESO, e ogni strategia
    // ha il suo interruttore: «parte solo lui» quindi SPEGNE le altre tre. Il
    // danno del 15/09 (base/esatto/punta spente per sempre, anche in prova) non
    // e’ piu’ irreversibile: si riaccendono dalla scheda calcio.
    it('«solo il tennis» scrive `variants: [tennis]`, sempre e in modo esplicito', () => {
        expect(paramsSoloTennis({ variants: ['base'] }, 'live').variants).toEqual(['tennis']);
        expect(paramsSoloTennis({ stake: { backSize: 3 } }, 'live').variants).toEqual(['tennis']);
        expect(paramsSoloTennis({ variants: [] }, 'live').variants).toEqual(['tennis']);
        expect(paramsSoloTennis(CORRENTI, 'live').variants).toEqual(['tennis']);
    });

    it('un `variants` illeggibile viene SOSTITUITO: non si eredita una lista rotta', () => {
        expect(paramsSoloTennis({ variants: 'rotto' }, 'live').variants).toEqual(['tennis']);
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
    it('elenca il calcio che si spegne e lo stake', () => {
        const d = differenzeSoloTennis(CORRENTI, 'live').join(' · ');
        expect(d).toMatch(/base, esatto/);
        expect(d).toMatch(/3,00/);
    });

    // ⚠️ REPERTO 17/09 sera — `auto_trade_tennis` non e’ piu’ fra le cose che
    // questa scheda annuncia di cambiare: non lo cambia piu’.
    it('NON annuncia piu’ le «entrate automatiche»: la scheda non lo tocca', () => {
        const d = differenzeSoloTennis(CORRENTI, 'live').join(' · ');
        expect(d).not.toMatch(/entrate automatiche/);
    });

    it('se è già come deve essere, in prova non annuncia niente', () => {
        const gia = {
            stake: { backSize: 3 }, auto_trade_tennis: true,
            strategy_modes: { tennis: 'paper', base: 'paper' }, variants: ['tennis'],
        };
        expect(differenzeSoloTennis(gia, 'paper')).toEqual([]);
    });

    it('DICE quali strategie spegne: «solo lui» adesso e’ letterale', () => {
        expect(differenzeSoloTennis(CORRENTI, 'paper').join(' · '))
            .toMatch(/base, esatto, punta → spente/);
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

describe('accensioniSoloTennis — e’ un caso particolare del modello, non un percorso a parte', () => {
    it('il tennis nella modalita’ scelta, le altre tre spente', () => {
        expect(accensioniSoloTennis('live'))
            .toEqual({ base: null, esatto: null, punta: null, tennis: 'live' });
        expect(accensioniSoloTennis('paper'))
            .toEqual({ base: null, esatto: null, punta: null, tennis: 'paper' });
    });
});
