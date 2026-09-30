// ============================================================================
// giornataCorsie.test.ts - P2 (30/09): le tessere sport elencano TUTTI i bot,
// ciascuno nella corsia della SUA modalita'. I finti hanno le chiavi di
// `StatoBot` (useControlRoom): `bot`, `modalita`, `inCorsa`, `varianti`,
// `modiStrategia`.
//
// Caso vero di oggi (progetto §0): Mike LIVE acceso, Safe e Omega in paper,
// scalper calcio senza modalita' dichiarata (spento), 4 bot tennis in paper.
// ============================================================================
import { describe, expect, it } from 'vitest';
import { corsiePerSport, type BotPerCorsie } from './giornataCorsie';

const OGGI: BotPerCorsie[] = [
    { bot: 'omega', modalita: 'paper', inCorsa: false, varianti: null, modiStrategia: null },
    { bot: 'safe', modalita: 'paper', inCorsa: true, varianti: ['base', 'esatto', 'tennis'],
        modiStrategia: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'paper' } },
    { bot: 'mike', modalita: 'live', inCorsa: true, varianti: null, modiStrategia: null },
    { bot: 'tennis_scalper', modalita: 'paper', inCorsa: true, varianti: null, modiStrategia: null },
    { bot: 'tennis_pro', modalita: 'paper', inCorsa: true, varianti: null, modiStrategia: null },
    { bot: 'tennis_flb', modalita: 'paper', inCorsa: true, varianti: null, modiStrategia: null },
    { bot: 'tennis_swing', modalita: 'paper', inCorsa: true, varianti: null, modiStrategia: null },
    { bot: 'scalper', modalita: null, inCorsa: false, varianti: null, modiStrategia: null },
];

const nomi = (v: { nome: string }[]) => v.map((x) => x.nome);

describe('corsiePerSport - ogni bot nella corsia della sua modalita\'', () => {
    it('Mike LIVE + Safe paper: Mike in LIVE, Safe e Omega in PROVA, scalper spento fra le ignote', () => {
        const c = corsiePerSport(OGGI);
        expect(nomi(c.calcio.live)).toEqual(['Mike']);
        expect(nomi(c.calcio.prova)).toEqual(['Omega', 'Safe base', 'Safe esatto', 'Safe punta']);
        expect(c.calcio.ignote).toEqual([{ chiave: 'scalper', nome: 'Scalper calcio', modalita: null, acceso: false }]);
        expect(c.calcio.liveAcceso).toBe(true);
        // Omega e' fermo: elencato, ma spento
        expect(c.calcio.prova.find((v) => v.chiave === 'omega')!.acceso).toBe(false);
        // Safe punta non e' fra le varianti che aprono: spenta, non sparita
        expect(c.calcio.prova.find((v) => v.chiave === 'safe-punta')!.acceso).toBe(false);
    });

    it('tennis: Safe tennis e i 4 bot tennis in PROVA, nessun LIVE', () => {
        const c = corsiePerSport(OGGI);
        expect(c.tennis.live).toEqual([]);
        expect(nomi(c.tennis.prova)).toEqual(['Safe tennis', 'Scalper', 'Pro', 'FLB', 'Swing']);
        expect(c.tennis.liveAcceso).toBe(false);
    });

    it('nessun bot LIVE: nessuna corsia LIVE accesa', () => {
        const c = corsiePerSport(OGGI.map((b) => ({ ...b, modalita: b.modalita == null ? null : 'paper' as const })));
        expect(c.calcio.live).toEqual([]);
        expect(c.calcio.liveAcceso).toBe(false);
    });

    it('bot LIVE ma FERMO: in corsia LIVE, spento, e la corsia non si dichiara accesa', () => {
        const c = corsiePerSport(OGGI.map((b) => (b.bot === 'mike' ? { ...b, inCorsa: false } : b)));
        expect(c.calcio.live).toEqual([{ chiave: 'mike', nome: 'Mike', modalita: 'live', acceso: false }]);
        expect(c.calcio.liveAcceso).toBe(false);
    });

    it('Safe: il mode del servizio e\' un tetto; strategy_modes decide per strategia', () => {
        const safeLive: BotPerCorsie = {
            bot: 'safe', modalita: 'live', inCorsa: true, varianti: null,
            modiStrategia: { base: 'live', tennis: 'paper' },
        };
        const c = corsiePerSport([safeLive]);
        expect(nomi(c.calcio.live)).toEqual(['Safe base']);
        // esatto e punta non dichiarate: PAPER, mai eredita' di soldi veri
        expect(nomi(c.calcio.prova)).toEqual(['Safe esatto', 'Safe punta']);
        expect(nomi(c.tennis.prova)).toEqual(['Safe tennis']);
        // servizio in paper: nessuna strategia in live, qualunque cosa dica strategy_modes
        const cp = corsiePerSport([{ ...safeLive, modalita: 'paper' }]);
        expect(cp.calcio.live).toEqual([]);
    });

    it('R_G: scalper spento con `modalitaUltima`: nella corsia di quell\'ultimo modo, dichiarato; null resta ignota', () => {
        const conUltimo = OGGI.map((b) => (b.bot === 'scalper' ? { ...b, modalitaUltima: 'paper' as const } : b));
        const c = corsiePerSport(conUltimo);
        expect(c.calcio.prova.find((v) => v.chiave === 'scalper')).toEqual(
            { chiave: 'scalper', nome: 'Scalper calcio', modalita: 'paper', acceso: false, ultimoModo: true });
        expect(c.calcio.ignote).toEqual([]);
        // senza ultimo modo resta fra le ignote
        const senza = corsiePerSport(OGGI.map((b) => (b.bot === 'scalper' ? { ...b, modalitaUltima: null } : b)));
        expect(senza.calcio.ignote.map((v) => v.chiave)).toEqual(['scalper']);
        // una modalita' dichiarata vince sempre sull'ultima
        const dich = corsiePerSport(OGGI.map((b) => (b.bot === 'mike' ? { ...b, modalitaUltima: 'paper' as const } : b)));
        expect(dich.calcio.live.map((v) => v.chiave)).toEqual(['mike']);
    });

    it('modalita\' non dichiarata o riga assente: ignota, MAI prova', () => {
        const c = corsiePerSport([{ bot: 'omega', modalita: null, inCorsa: true, varianti: null, modiStrategia: null }]);
        expect(c.calcio.ignote.map((v) => v.chiave)).toEqual(['omega', 'safe-base', 'safe-esatto', 'safe-punta', 'mike', 'scalper']);
        expect(c.calcio.prova).toEqual([]);
        // riga assente = acceso null (non letto), non «spento»
        expect(c.calcio.ignote.find((v) => v.chiave === 'mike')!.acceso).toBeNull();
    });
});
