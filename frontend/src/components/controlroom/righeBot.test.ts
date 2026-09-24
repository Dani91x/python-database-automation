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
            .toEqual(['omega', 'mike', 'safe-base', 'safe-esatto', 'safe-punta',
                'safe-model', 'safe-manual']);
    });

    it('scheda tennis, con i soli tre servizi del calcio: resta Safe tennis', () => {
        expect(righeInterruttori(TRE, 'tennis').map((r) => r.id)).toEqual(['safe-tennis']);
    });

    it('con i soli tre servizi del calcio non nascono righe tennis fantasma', () => {
        // 24/09 — sei + le due righe di Safe «modello» e «a mano»
        expect(righeInterruttori(TRE, null)).toHaveLength(8);
    });

    it('un bot che non c e non produce righe fantasma', () => {
        expect(righeInterruttori([TRE[1]], 'calcio').map((r) => r.id))
            .toEqual(['safe-base', 'safe-esatto', 'safe-punta', 'safe-model', 'safe-manual']);
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


// ============================================================================
// I QUATTRO BOT DEL TENNIS (17/09) — «indipendenti come gli altri».
//
// Falsificazione fatta a mano prima di scriverli: togliendo i quattro
// `Interruttore` da `lib/interruttori.ts` questi test diventano rossi (nessuna
// riga tennis), e facendo leggere a `righeBot` il `pnlOggi` invece del
// `pnlOggiPaper` per una riga in prova il test del P&L diventa rosso.
// ============================================================================
const QUATTRO: StatoBotPlancia[] = [
    bot({
        bot: 'tennis_scalper', inCorsa: true, modalita: 'live', stato: 'running',
        pnlOggi: 1.25, pnlOggiPaper: -9.99,
    }),
    bot({
        bot: 'tennis_pro', inCorsa: true, modalita: 'paper', stato: 'running',
        pnlOggi: 7.77, pnlOggiPaper: -0.4,
    }),
    bot({ bot: 'tennis_flb', inCorsa: false, modalita: 'paper', stato: 'stopped' }),
    // modalita' NON dichiarata dal servizio: non si indovina
    bot({ bot: 'tennis_swing', inCorsa: true, modalita: null, stato: 'running' }),
];

describe('i quattro bot tennis sono QUATTRO RIGHE INDIPENDENTI', () => {
    it('nella scheda tennis compaiono tutti e quattro, accanto a Safe tennis', () => {
        expect(righeInterruttori([...TRE, ...QUATTRO], 'tennis').map((r) => r.id))
            .toEqual(['safe-tennis', 'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing']);
    });

    it('nella scheda CALCIO non compare nemmeno uno', () => {
        const ids = righeInterruttori([...TRE, ...QUATTRO], 'calcio').map((r) => r.id);
        expect(ids.some((i) => i.startsWith('tennis_'))).toBe(false);
    });

    it('ogni riga ha il SUO stato e la SUA modalita: niente si eredita', () => {
        const r = righeInterruttori(QUATTRO, 'tennis');
        const di = (id: string) => r.find((x) => x.id === id)!;
        expect(di('tennis_scalper')).toMatchObject({ acceso: true, modalita: 'live', stato: 'running' });
        expect(di('tennis_pro')).toMatchObject({ acceso: true, modalita: 'paper', stato: 'running' });
        expect(di('tennis_flb')).toMatchObject({ acceso: false, modalita: 'paper', stato: 'stopped' });
        // modalita' non dichiarata resta `null`: il pannello scrive «modalita n/d»
        expect(di('tennis_swing').modalita).toBeNull();
    });

    it('spegnerne uno non tocca gli altri tre', () => {
        const spento = QUATTRO.map((b) => (b.bot === 'tennis_scalper'
            ? { ...b, inCorsa: false, stato: 'stopped' } : b));
        const r = righeInterruttori(spento, 'tennis');
        expect(r.find((x) => x.id === 'tennis_scalper')!.acceso).toBe(false);
        expect(r.find((x) => x.id === 'tennis_pro')!.acceso).toBe(true);
        expect(r.find((x) => x.id === 'tennis_swing')!.acceso).toBe(true);
    });

    it('ognuno porta il foglio parametri della SUA riga: sono servizi diversi', () => {
        expect(righeInterruttori(QUATTRO, 'tennis').every((x) => x.primaDelBot)).toBe(true);
    });

    it('il P&L mostrato e quello della MODALITA della riga, mai la somma', () => {
        const r = righeInterruttori(QUATTRO, 'tennis');
        const di = (id: string) => r.find((x) => x.id === id)!;
        expect(di('tennis_scalper').pnlOggi).toBe(1.25);   // live -> il live
        expect(di('tennis_pro').pnlOggi).toBe(-0.4);       // prova -> quello in prova
        // senza modalita' dichiarata non si sceglie: nessun numero
        expect(di('tennis_swing').pnlOggi).toBeNull();
        // nessuna riga porta 1.25 + (-0.4): la somma non esiste da nessuna parte
        expect(r.map((x) => x.pnlOggi)).not.toContain(0.85);
    });

    it('P&L assente = null, mai 0: «niente di regolato» non e «ho chiuso in pari»', () => {
        expect(righeInterruttori(QUATTRO, 'tennis').find((x) => x.id === 'tennis_flb')!.pnlOggi)
            .toBeNull();
    });
});
