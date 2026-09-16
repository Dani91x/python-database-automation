// ============================================================================
// righeBot.test.ts — CALCIO E TENNIS NON STANNO NELLA STESSA PLANCIA.
//
// «PAPER E LIVE SONO COSE DISTINTE E NON DEVONO MAI MISCHIARSI, COME CALCIO E
// TENNIS» (utente, 16/09). Qui si certifica la parte «come calcio e tennis»:
// nella scheda calcio il tennis non compare, e viceversa. E si certifica che
// lo stato di ogni riga esce da `variants` + `strategy_modes`, mai da un flag.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { righeInterruttori, statoServizioDi, type StatoBotPlancia } from './righeBot';

function bot(over: Partial<StatoBotPlancia> = {}): StatoBotPlancia {
    return {
        bot: 'safe', inCorsa: false, modalita: 'paper',
        varianti: null, modiStrategia: null, stato: 'stopped', etaPushS: 3,
        motivoBlocco: null, tettoPartite: null, partiteEsposte: null,
        stopFermaSoloAperture: false, fermatoAllAvvioAt: null,
        ...over,
    };
}

const TRE = [
    bot({ bot: 'omega', inCorsa: true, modalita: 'live', stato: 'running' }),
    bot({
        bot: 'safe', inCorsa: true, modalita: 'live', stato: 'running',
        varianti: ['punta', 'tennis'],
        modiStrategia: { punta: 'paper', tennis: 'live' },
    }),
    bot({ bot: 'mike', inCorsa: false, stato: 'stopped' }),
];

describe('una riga per interruttore, filtrate per sport', () => {
    it('scheda calcio: Omega, Mike e le tre strategie di calcio. Niente tennis', () => {
        expect(righeInterruttori(TRE, 'calcio').map((r) => r.id))
            .toEqual(['omega', 'mike', 'safe-base', 'safe-esatto', 'safe-punta']);
    });

    it('scheda tennis: solo Safe tennis. Niente calcio', () => {
        expect(righeInterruttori(TRE, 'tennis').map((r) => r.id)).toEqual(['safe-tennis']);
    });

    it('senza scheda scelta ci sono tutti e sei', () => {
        expect(righeInterruttori(TRE, null)).toHaveLength(6);
    });

    it('un bot che non c e non produce righe fantasma', () => {
        expect(righeInterruttori([TRE[1]], 'calcio').map((r) => r.id))
            .toEqual(['safe-base', 'safe-esatto', 'safe-punta']);
    });
});

describe('lo stato di ogni riga esce dal servizio, non da un flag', () => {
    it('acceso = il servizio e in corsa E la strategia sta in `variants`', () => {
        const r = righeInterruttori(TRE, null);
        const di = (id: string) => r.find((x) => x.id === id)!;
        expect(di('safe-punta').acceso).toBe(true);
        expect(di('safe-base').acceso).toBe(false);
        expect(di('safe-tennis').acceso).toBe(true);
        expect(di('omega').acceso).toBe(true);
        expect(di('mike').acceso).toBe(false);
    });

    it('SOLDI VERI solo dove e scritto due volte', () => {
        const r = righeInterruttori(TRE, null);
        expect(r.find((x) => x.id === 'safe-tennis')!.modalita).toBe('live');
        expect(r.find((x) => x.id === 'safe-punta')!.modalita).toBe('paper');
        expect(r.find((x) => x.id === 'omega')!.modalita).toBe('live');
    });

    it('una strategia spenta si scrive «fermo», non «in esecuzione»', () => {
        const r = righeInterruttori(TRE, 'calcio');
        expect(r.find((x) => x.id === 'safe-base')!.stato).toBe('stopped');
        expect(r.find((x) => x.id === 'safe-punta')!.stato).toBe('running');
    });

    it('«sta fermandosi» vale per TUTTE le strategie del servizio', () => {
        const r = righeInterruttori(
            [bot({ inCorsa: true, stato: 'stopping', varianti: ['base'] })], 'calcio',
        );
        expect(r.every((x) => x.stato === 'stopping')).toBe(true);
    });

    it('servizio in corsa senza `variants` = STATO NON LETTO, e non si comanda', () => {
        const r = righeInterruttori([bot({ inCorsa: true, stato: 'running' })], 'calcio');
        expect(r.every((x) => x.statoNoto === false)).toBe(true);
        expect(r.every((x) => x.stato === 'ignoto')).toBe(true);
    });

    it('il foglio parametri compare UNA volta per bot, sulla sua prima riga', () => {
        const r = righeInterruttori(TRE, 'calcio');
        expect(r.filter((x) => x.bot === 'safe' && x.primaDelBot).map((x) => x.id))
            .toEqual(['safe-base']);
        expect(r.find((x) => x.id === 'omega')!.primaDelBot).toBe(true);
    });

    it('nella scheda tennis il foglio di Safe sta sulla sua unica riga', () => {
        expect(righeInterruttori(TRE, 'tennis')[0].primaDelBot).toBe(true);
    });

    it('le etichette si possono cambiare per contesto: nella scheda tennis si chiama «Tennis»', () => {
        expect(righeInterruttori(TRE, 'tennis', { 'safe-tennis': 'Tennis' })[0].etichetta)
            .toBe('Tennis');
    });
});

describe('statoServizioDi — la traduzione non perde niente', () => {
    it('porta con se varianti e modi, che sono la verita dello stato', () => {
        expect(statoServizioDi(TRE[1])).toEqual({
            inCorsa: true, modalita: 'live',
            varianti: ['punta', 'tennis'],
            modiStrategia: { punta: 'paper', tennis: 'live' },
        });
    });
});
