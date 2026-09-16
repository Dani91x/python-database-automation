// ============================================================================
// comandiBot.test.ts — LA CONTROL ROOM E LA PAGINA DEL BOT DEVONO MANDARE LA
// STESSA RIGA.
//
// Il difetto che questi test impediscono: due implementazioni dello stesso
// interruttore. Fino al 15/09 la scheda tennis aveva un percorso suo
// (`creaComandiTennis`) accanto a quello generale, e «avvia» voleva dire due
// cose diverse a seconda di dove si trovava il dito. Adesso c'e' un solo
// motore di comandi (`@/lib/interruttori`), e qui si certifica che l'unica
// differenza rimasta — il gesto «solo tennis», chiesto dall'utente per nome il
// 15/09 — sia proprio quella e nient'altro.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/omega', () => ({
    activateOmega: vi.fn(async () => ({})),
    stopOmega: vi.fn(async () => ({})),
    updateOmegaParams: vi.fn(async () => ({})),
}));
vi.mock('@/lib/safeBot', () => ({
    activateSafe: vi.fn(async () => ({})),
    stopSafe: vi.fn(async () => ({})),
    updateSafeParams: vi.fn(async () => ({})),
}));
vi.mock('@/lib/mike', () => ({
    activateMike: vi.fn(async () => ({})),
    stopMike: vi.fn(async () => ({})),
    updateMikeParams: vi.fn(async () => ({})),
}));

import { creaComandiControlRoom } from './comandiBot';
import {
    creaInterruttori, BotFermoNonCambiaModalita,
    type SorgenteInterruttori, type Bot,
} from '@/lib/interruttori';
import { STAKE_TENNIS } from './soloTennis';
import { activateSafe, updateSafeParams } from '@/lib/safeBot';
import { activateMike, updateMikeParams } from '@/lib/mike';

const mActSafe = vi.mocked(activateSafe);
const mUpdSafe = vi.mocked(updateSafeParams);
const mActMike = vi.mocked(activateMike);
const mUpdMike = vi.mocked(updateMikeParams);

beforeEach(() => { vi.clearAllMocks(); });

/** la riga di control com'e' oggi: tennis in live, calcio in prova */
const CORRENTI: Record<string, unknown> = {
    variants: ['base', 'esatto', 'punta', 'tennis'],
    strategy_modes: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'live' },
    stake: { laySize: 2, backSize: 5 },
    auto_trade_tennis: false,
    tennis_exit_approval: true,
};

function sorgente(): SorgenteInterruttori {
    return {
        params: (b: Bot) => (b === 'safe' ? CORRENTI : { stake: 10 }),
        servizio: (b: Bot) => (b === 'safe'
            ? {
                inCorsa: true, modalita: 'live',
                varianti: ['base', 'esatto', 'punta', 'tennis'],
                modiStrategia: { base: 'paper', esatto: 'paper', punta: 'paper', tennis: 'live' },
            }
            : { inCorsa: false, modalita: null }),
        obiettivoOmega: () => 250,
    };
}

describe('la pagina del bot e la Control Room producono LO STESSO payload', () => {
    it('accendere «base» in prova: stessa RPC, stessi campi', async () => {
        // quello che fa la PAGINA di Safe (comandi condivisi, nessuna scheda)
        await creaInterruttori(sorgente(), vi.fn()).accendi('safe-base', 'paper');
        const daPagina = mUpdSafe.mock.calls[0][0];
        vi.clearAllMocks();

        // quello che fa la CONTROL ROOM nella scheda calcio
        await creaComandiControlRoom(sorgente(), vi.fn(), 'calcio').accendi('safe-base', 'paper');
        const daControlRoom = mUpdSafe.mock.calls[0][0];

        expect(daControlRoom).toEqual(daPagina);
    });

    it('spegnere «punta»: stessa RPC, stessi campi', async () => {
        await creaInterruttori(sorgente(), vi.fn()).spegni('safe-punta');
        const daPagina = mUpdSafe.mock.calls[0][0];
        vi.clearAllMocks();
        await creaComandiControlRoom(sorgente(), vi.fn(), null).spegni('safe-punta');
        expect(mUpdSafe.mock.calls[0][0]).toEqual(daPagina);
    });

    it('anche il cambio di importo passa dalla stessa funzione', async () => {
        await creaInterruttori(sorgente(), vi.fn())
            .cambiaImporto('safe-tennis', 'stake.per_strategia.tennis', 4);
        const daPagina = mUpdSafe.mock.calls[0][0];
        vi.clearAllMocks();
        await creaComandiControlRoom(sorgente(), vi.fn(), 'tennis')
            .cambiaImporto('safe-tennis', 'stake.per_strategia.tennis', 4);
        expect(mUpdSafe.mock.calls[0][0]).toEqual(daPagina);
    });
});

describe('la scheda tennis: l UNICA differenza, e dichiarata', () => {
    it('da li «avvia» accende il tennis e SPEGNE le altre tre', async () => {
        await creaComandiControlRoom(sorgente(), vi.fn(), 'tennis').accendi('safe-tennis', 'live');
        // il servizio e' gia' armato in live per il tennis: non si riattiva, si
        // riscrivono i parametri (niente `started_at` azzerato a meta' giornata)
        expect(mUpdSafe).toHaveBeenCalledTimes(1);
        expect(mActSafe).not.toHaveBeenCalled();
        const p = mUpdSafe.mock.calls[0][0] as Record<string, unknown>;
        expect(p.variants).toEqual(['tennis']);
        expect(p.strategy_modes).toEqual({
            base: 'paper', esatto: 'paper', punta: 'paper',
            tennis: 'live', model: 'paper', manual: 'paper',
        });
        // le tre cose che quel gesto AGGIUNGE, chieste dall'utente il 15/09
        expect((p.stake as Record<string, unknown>).per_strategia)
            .toEqual({ tennis: STAKE_TENNIS });
        expect(p.auto_trade_tennis).toBe(true);
        // e non porta via niente
        expect(p.tennis_exit_approval).toBe(true);
    });

    it('fuori dalla scheda tennis lo stesso gesto tocca SOLO il tennis', async () => {
        await creaComandiControlRoom(sorgente(), vi.fn(), 'calcio').accendi('safe-tennis', 'live');
        const p = mUpdSafe.mock.calls[0][0] as Record<string, unknown>;
        expect(p.variants).toEqual(['base', 'esatto', 'punta', 'tennis']);
        expect(p.auto_trade_tennis).toBe(false);   // non si configura niente
    });

    it('«passa a prova» non riconfigura niente: e una de-escalation', async () => {
        await creaComandiControlRoom(sorgente(), vi.fn(), 'tennis')
            .cambiaModalita('safe-tennis', 'paper');
        // era l'ULTIMA strategia in live: il servizio torna in prova, e questo
        // si puo' fare solo riarmandolo (`safe_activate('paper')`)
        expect(mActSafe).toHaveBeenCalledTimes(1);
        expect(mActSafe.mock.calls[0][0]).toBe('paper');
        const p = mActSafe.mock.calls[0][1] as Record<string, unknown>;
        // il tennis torna in prova, ma le entrate automatiche e lo stake
        // restano come l'operatore li ha lasciati
        expect((p.strategy_modes as Record<string, string>).tennis).toBe('paper');
        expect(p.auto_trade_tennis).toBe(false);
        expect(p.stake).toEqual({ laySize: 2, backSize: 5 });
    });

    it('Mike e Omega dalla scheda tennis passano dai comandi normali', async () => {
        await creaComandiControlRoom(sorgente(), vi.fn(), 'tennis').accendi('mike', 'paper');
        expect(mActMike).toHaveBeenCalledWith('paper');
        expect(mActSafe).not.toHaveBeenCalled();
    });
});

// ===========================================================================
// IL GESTO «CAMBIA MODALITA'» SU UN BOT FERMO — stesso esito dalle due strade,
// e in nessuna delle due c'e' un'accensione.
// ===========================================================================

/** tutto fermo: e' il caso in cui `X_activate` accenderebbe il bot */
function sorgenteTuttoFermo(): SorgenteInterruttori {
    return {
        params: (b: Bot) => (b === 'safe' ? CORRENTI : { stake: 10 }),
        servizio: () => ({ inCorsa: false, modalita: null, varianti: null, modiStrategia: null }),
        obiettivoOmega: () => 250,
    };
}

describe('cambia modalita su un bot FERMO: nessuna accensione, da nessuna parte', () => {
    it('Mike: pagina e Control Room mandano LO STESSO payload, e non e un avvio', async () => {
        await creaInterruttori(sorgenteTuttoFermo(), vi.fn()).cambiaModalita('mike', 'live');
        const daPagina = mUpdMike.mock.calls[0];
        vi.clearAllMocks();
        await creaComandiControlRoom(sorgenteTuttoFermo(), vi.fn(), 'calcio').cambiaModalita('mike', 'live');
        expect(mUpdMike.mock.calls[0]).toEqual(daPagina);
        expect(mActMike).not.toHaveBeenCalled();
    });

    it('Safe: tutte e due le strade si RIFIUTANO, e nessuna chiama `safe_activate`', async () => {
        await expect(creaInterruttori(sorgenteTuttoFermo(), vi.fn()).cambiaModalita('safe-base', 'live'))
            .rejects.toBeInstanceOf(BotFermoNonCambiaModalita);
        await expect(creaComandiControlRoom(sorgenteTuttoFermo(), vi.fn(), 'calcio')
            .cambiaModalita('safe-base', 'live')).rejects.toBeInstanceOf(BotFermoNonCambiaModalita);
        expect(mActSafe).not.toHaveBeenCalled();
        expect(mUpdSafe).not.toHaveBeenCalled();
    });

    it('anche il gesto «solo tennis» della scheda tennis non accende a modalita', async () => {
        // `accendi` puo` far partire il servizio (e` il suo mestiere)...
        await creaComandiControlRoom(sorgenteTuttoFermo(), vi.fn(), 'tennis').accendi('safe-tennis', 'live');
        expect(mActSafe).toHaveBeenCalledTimes(1);
        vi.clearAllMocks();
        // ...«passa a soldi veri» no.
        await expect(creaComandiControlRoom(sorgenteTuttoFermo(), vi.fn(), 'tennis')
            .cambiaModalita('safe-tennis', 'live')).rejects.toBeInstanceOf(BotFermoNonCambiaModalita);
        expect(mActSafe).not.toHaveBeenCalled();
    });
});
