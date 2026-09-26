// ============================================================================
// fixPagine2609.giornata.test.tsx - F-1 / F-2 / F-3 del test e2e FASE 3 (26/09).
//
//  F-1  P&L «oggi» per bot: era null per Omega/Mike/Safe mentre le Posizioni
//       chiuse della stessa pagina mostravano +0,95 / +0,79 €.
//  F-2  due verità sullo stesso denaro: barra/riga «in prova» per giorno di
//       PIAZZAMENTO, Posizioni chiuse per giorno di REGOLAMENTO. Decisione del
//       coordinatore (26/09): il REALIZZATO di oggi e' per giorno di
//       regolamento ovunque.
//  F-3  «giornata non ancora letta» con la lettura riuscita e vuota.
//
// Righe finte con le chiavi di `omega_trades` / `safe_strategy_trades` /
// `mike_trades` (le stesse di `get_*_state`), tipi identici.
//
// FALSIFICAZIONE (26/09): rimettendo in `righeGiornataPerCiclo` il filtro
// paper sul PIAZZAMENTO dell'apertura, «F-2 regolata oggi, piazzata ieri» e
// «F-2 somma = Posizioni chiuse» diventano rossi; rimettendo `pnlOggi: null`
// per Omega/Mike in `useControlRoom`, «F-1 righeInterruttori» resta verde ma
// `pnlChiuseDelGiorno` e' il solo punto di calcolo (test rosso se si toglie
// il filtro di modalita' o di giornata); rimettendo in SplitSport
// `pnl = mio ? mio.pnl : null`, «F-3» diventa rosso.
// ============================================================================
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { righeGiornataPerCiclo, type RigaTradeReale } from '@/lib/composizioneObiettivo';
import {
    filtraChiuse, pnlChiuseDelGiorno, posizioniChiuse, riepilogoChiuse, type TradeChiudibile,
} from '@/lib/posizioniChiuse';
import { perSportGiornata } from '@/lib/controlRoom';
import { righeInterruttori, type StatoBotPlancia } from '@/components/controlroom/righeBot';
import { SplitSport } from '@/components/controlroom/SplitSport';

const OGGI = '2026-09-26';
const giornoDi = (iso: string | null | undefined): string => {
    const ms = iso ? Date.parse(iso) : NaN;
    if (!Number.isFinite(ms)) return '';
    return new Date(ms + 2 * 3600 * 1000).toISOString().slice(0, 10);   // Roma, ora legale
};

function trade(p: Partial<TradeChiudibile> & { id: number; __bot: TradeChiudibile['__bot'] }): TradeChiudibile {
    return {
        event_id: '35000001', event_name: 'A v B', status: 'won', mode: 'paper', side: 'lay',
        price: 55, size: 1, pnl: 0.95, bet_id: `paper-${p.id}`, placed_at: '2026-09-26T08:00:00Z',
        settled_at: '2026-09-26T08:57:03Z', closes_trade_id: null, origin: 'auto', sport: 'calcio',
        ...p,
    } as TradeChiudibile;
}

// il caso del 26/09: Safe tennis #341 piazzato il 24/09, regolato oggi
const SAFE_341 = trade({
    id: 341, __bot: 'safe', sport: 'tennis', strategy: 'tennis', pnl: 0.03,
    placed_at: '2026-09-24T16:00:00Z', settled_at: '2026-09-26T07:30:00Z',
} as Partial<TradeChiudibile> & { id: number; __bot: 'safe' });
const OMEGA_116 = trade({ id: 116, __bot: 'omega', pnl: 0.95 });
// Mike 5063: apertura + copertura (ciclo), entrambe regolate oggi
const MIKE_5063 = trade({ id: 5063, __bot: 'mike', side: 'back', pnl: 1.0 });
const MIKE_5064 = trade({ id: 5064, __bot: 'mike', side: 'lay', pnl: -0.93, closes_trade_id: 5063 });
// piazzata oggi, regolata DOMANI: non e' realizzato di oggi
const OMEGA_DOMANI = trade({ id: 120, __bot: 'omega', pnl: 5, settled_at: '2026-09-26T22:30:00Z' });
// ancora aperta: niente realizzato
const OMEGA_APERTA = trade({ id: 121, __bot: 'omega', status: 'open', pnl: 0, settled_at: null });
// live: mai nel paper
const MIKE_LIVE = trade({ id: 5080, __bot: 'mike', mode: 'live', pnl: 2.0, bet_id: '3900001' });

const TUTTE = [SAFE_341, OMEGA_116, MIKE_5063, MIKE_5064, OMEGA_DOMANI, OMEGA_APERTA, MIKE_LIVE];

describe('F-2: realizzato di oggi IN PROVA per giorno di REGOLAMENTO', () => {
    it('regolata oggi ma piazzata ieri: entra oggi (prima spariva)', () => {
        const r = righeGiornataPerCiclo([SAFE_341 as unknown as RigaTradeReale], { oggi: OGGI, giornoDi });
        expect(r).toHaveLength(1);
        expect(r[0].pnl).toBe(0.03);
        expect(r[0].mode).toBe('paper');
    });
    it('piazzata oggi ma regolata domani (giorno di Roma): NON entra oggi', () => {
        const r = righeGiornataPerCiclo([OMEGA_DOMANI as unknown as RigaTradeReale], { oggi: OGGI, giornoDi });
        expect(r).toHaveLength(0);
    });
    it('la somma paper della barra = il totale delle Posizioni chiuse in prova di oggi', () => {
        const barra = righeGiornataPerCiclo(TUTTE as unknown as RigaTradeReale[], { oggi: OGGI, giornoDi })
            .filter((x) => x.mode === 'paper')
            .reduce((s, x) => Math.round((s + (x.pnl ?? 0)) * 100) / 100, 0);
        const chiuse = riepilogoChiuse(filtraChiuse(posizioniChiuse(TUTTE), { giorno: OGGI, modo: 'paper' }));
        expect(chiuse.totale).toBe(1.05);           // 0,03 + 0,95 + (1,00 − 0,93)
        expect(barra).toBe(chiuse.totale);
    });
});

describe('F-1: P&L «oggi» per bot dalla STESSA regola delle Posizioni chiuse', () => {
    const chiuse = posizioniChiuse(TUTTE);
    it('Omega/Mike/Safe in prova hanno un numero, non «—»', () => {
        expect(pnlChiuseDelGiorno(chiuse, { giorno: OGGI, bot: 'omega', modo: 'paper' })).toBe(0.95);
        expect(pnlChiuseDelGiorno(chiuse, { giorno: OGGI, bot: 'mike', modo: 'paper' })).toBe(0.07);
        expect(pnlChiuseDelGiorno(chiuse, { giorno: OGGI, bot: 'safe', modo: 'paper', strategia: 'tennis' })).toBe(0.03);
    });
    it('modalita\' e giornata separate: live a parte, nessuna chiusa = null', () => {
        expect(pnlChiuseDelGiorno(chiuse, { giorno: OGGI, bot: 'mike', modo: 'live' })).toBe(2.0);
        expect(pnlChiuseDelGiorno(chiuse, { giorno: OGGI, bot: 'omega', modo: 'live' })).toBeNull();
        expect(pnlChiuseDelGiorno(chiuse, { giorno: '2026-09-25', bot: 'omega', modo: 'paper' })).toBeNull();
        expect(pnlChiuseDelGiorno(chiuse, { giorno: OGGI, bot: 'safe', modo: 'paper', strategia: 'base' })).toBeNull();
    });
    it('righeInterruttori: la riga Omega in prova mostra il suo P&L; Safe per strategia, mai duplicato', () => {
        const base = {
            inCorsa: true, varianti: ['base', 'tennis'], stato: 'running', etaPushS: 1, motivoBlocco: null,
            tettoPartite: null, partiteEsposte: null, stopFermaSoloAperture: false, fermatoAllAvvioAt: null,
        };
        const omega: StatoBotPlancia = {
            ...base, bot: 'omega', modalita: 'paper', varianti: null, modiStrategia: null,
            pnlOggi: null, pnlOggiPaper: 0.95,
        };
        const safe: StatoBotPlancia = {
            ...base, bot: 'safe', modalita: 'paper', modiStrategia: { base: 'paper', tennis: 'paper' },
            pnlOggi: null, pnlOggiPaper: null,
            pnlOggiPerStrategia: { tennis: { live: null, paper: 0.03 }, base: { live: null, paper: null } },
        };
        const calcio = righeInterruttori([omega, safe], 'calcio');
        expect(calcio.find((r) => r.id === 'omega')!.pnlOggi).toBe(0.95);
        expect(calcio.find((r) => r.id === 'safe-base')!.pnlOggi).toBeNull();
        const tennis = righeInterruttori([omega, safe], 'tennis');
        expect(tennis.find((r) => r.id === 'safe-tennis')!.pnlOggi).toBe(0.03);
    });
});

describe('F-3: letta e vuota = 0,00 € oggi, non «non ancora letta»', () => {
    it('perSportGiornata senza righe da due sport a zero, non null', () => {
        const v = perSportGiornata([], [], {});
        expect(v.calcio).toEqual({ n: 0, pnl: 0, won: 0, lost: 0 });
        expect(v.tennis).toEqual({ n: 0, pnl: 0, won: 0, lost: 0 });
    });
    it('perSportGiornata divide per sport e conta solo le righe regolate', () => {
        const v = perSportGiornata([
            { status: 'won', pnl: 0.95, mode: 'paper', sport: 'calcio' },
            { status: 'lost', pnl: -0.9, mode: 'paper', sport: 'calcio' },
            { status: 'open', pnl: null, mode: 'paper', sport: 'calcio' },
            { status: 'won', pnl: 0.03, mode: 'paper', sport: 'tennis' },
        ], [{ status: 'won', pnl: 1.1, mode: 'paper', sport: 'tennis' }], { tennis: { n: 4, won: 3, lost: 1 } });
        expect(v.calcio).toEqual({ n: 2, pnl: 0.05, won: 1, lost: 1 });
        expect(v.tennis).toEqual({ n: 5, pnl: 1.13, won: 4, lost: 1 });
    });
    it('la tessera con la giornata letta e vuota scrive 0,00 € e «nessuna operazione»', () => {
        render(<SplitSport selezionato={null} onSeleziona={() => undefined}
            perSport={{}} perSportPaper={{}} modalita={{ calcio: 'paper', tennis: 'paper' }} />);
        expect(screen.queryAllByText('giornata non ancora letta')).toHaveLength(0);
        expect(screen.getByTestId('cr-sport-calcio-pnl').textContent).toBe('+0,00 €');
        expect(screen.getByTestId('cr-sport-tennis').textContent).toContain('nessuna operazione in prova oggi');
    });
    it('non letta (null) resta «—» e «giornata non ancora letta»', () => {
        render(<SplitSport selezionato={null} onSeleziona={() => undefined}
            perSport={null} modalita={{ calcio: 'paper', tennis: 'paper' }} />);
        expect(screen.getAllByText('giornata non ancora letta')).toHaveLength(2);
    });
});
