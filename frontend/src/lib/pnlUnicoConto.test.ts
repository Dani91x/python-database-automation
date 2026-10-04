// ============================================================================
// 04/10 - TEST DI CONTRATTO «LE VISTE TORNANO COL CONTO».
//
// Segnalazione dell'utente: «la scheda Calcio dice LIVE -10,75 EUR CONTO
// BETFAIR, Posizioni chiuse -5,68. Non abbiamo mai perso 10 euro: uniforma».
//
// Il caso di prova e' la giornata VERA del 04/10, letta dal DB in sola lettura:
//   * `betfair_live_account.pnl_reale_oggi` (runner di prima): 7 ordini, lordo
//     -5,13, commissione 0,02, netto -5,15; per_fonte mike 5 ordini -10,75,
//     manuale_sito 2 ordini +5,60 (lordo +5,62);
//   * la stessa giornata come la scrive il runner NUOVO (chiavi additive
//     `per_posizione`/`chiusure_a_mano`/`per_sport`, numeri del test Python
//     `Betfair/stream/tests/test_pnl_unico_conto_2026_10_04.py`);
//   * le righe `mike_trades` 5152..5160 (colonne vere), con la riga «utente»
//     5160 (bet 445577040174, +5,07: la chiusura messa a mano dal sito).
// Ogni vista deve dire: conto netto -5,15 = bot (Mike) -5,68 + a mano +0,53.
// ============================================================================
import { describe, expect, it } from 'vitest';
import {
    componiObiettivo, differenzaContoRighe, leggiPnlRealeOggi, righeGiornataPerCiclo, rigaSintetica,
    type RigaComponente, type RigaTradeReale,
} from './composizioneObiettivo';
import {
    composizioneDalConto, contoPerVista, perSportDalConto, righeMikeDelConto,
} from './composizioneConto';
import { filtraChiuse, posizioniChiuse, riepilogoChiuse, type TradeChiudibile } from './posizioniChiuse';
import { realizzatoGiornata } from './controlRoom';
import { romeDay } from './dailyHistory';

const OGGI = '2026-10-04';

const VUOTA = { netto: 0, lordo: 0, ordini: 0, senza_commissione: 0 };
const FONTI_VUOTE = {
    omega: VUOTA, scalper: VUOTA, altri_bot: VUOTA, bot_tennis: VUOTA, manuale_app: VUOTA,
    safe_calcio: VUOTA, safe_tennis: VUOTA,
};

/** IL PAYLOAD VERO del 04/10 (runner di prima), copiato dal DB. */
const PAYLOAD_DB_04_10 = {
    day: OGGI, lordo: -5.13, netto: -5.15, ordini: 7,
    bet_ids: ['445568321596', '445568325409', '445568328282', '445569572640', '445572059076',
        '445572454155', '445577040174'],
    letto_at: '2026-10-04T13:08:03.439008+00:00',
    per_fonte: {
        ...FONTI_VUOTE,
        mike: { lordo: -10.75, netto: -10.75, ordini: 5, senza_commissione: 0 },
        manuale_sito: { lordo: 5.62, netto: 5.6, ordini: 2, senza_commissione: 0 },
    },
    commissione: 0.02, pnl_letto_at: '2026-10-04T13:08:02.527996+00:00',
    sospetti_sito: 0, senza_commissione: 0,
};

const SPORT_VUOTO = {
    netto: 0, lordo: 0, commissione: 0, ordini: 0, senza_commissione: 0,
    bot: { netto: 0, lordo: 0, ordini: 0 }, a_mano: { netto: 0, lordo: 0, ordini: 0 },
    chiusure_a_mano: { netto: 0, lordo: 0, ordini: 0 },
};

/** LA STESSA GIORNATA dal runner nuovo (uscita di `componi_regolati`). */
const PAYLOAD_NUOVO_04_10 = {
    ...PAYLOAD_DB_04_10,
    per_posizione: {
        ...FONTI_VUOTE,
        mike: { netto: -5.68, lordo: -5.68, ordini: 6, senza_commissione: 0 },
        manuale_sito: { netto: 0.53, lordo: 0.55, ordini: 1, senza_commissione: 0 },
    },
    chiusure_a_mano: { mike: { netto: 5.07, lordo: 5.07, ordini: 1, bet_ids: ['445577040174'] } },
    per_sport: {
        calcio: {
            netto: -5.15, lordo: -5.13, commissione: 0.02, ordini: 7, senza_commissione: 0,
            bot: { netto: -5.68, lordo: -5.68, ordini: 6 },
            a_mano: { netto: 0.53, lordo: 0.55, ordini: 1 },
            chiusure_a_mano: { netto: 5.07, lordo: 5.07, ordini: 1 },
        },
        tennis: SPORT_VUOTO,
        altro: SPORT_VUOTO,
    },
};

/** Le righe LIVE di Mike del 04/10 (colonne vere di `mike_trades`). */
function riga(id: number, ev: string, eventName: string, role: string, status: string, side: string,
    pnl: number, pnlBetfair: number | null, bet: string, placed: string, settled: string | null,
    closes: number | null, extra: Partial<TradeChiudibile> = {}) {
    return {
        id, event_id: ev, event_name: eventName, sport: 'calcio', role, mode: 'live', status, side,
        origin: role === 'utente' ? 'manual' : 'auto', strategy: role === 'utente' ? 'manual_close' : role,
        signal_key: role === 'utente' ? `utente-${bet}` : `${role}-0-1`,
        market_type: 'OVER_UNDER_35', selection_name: 'Under 3.5 Goals',
        pnl, pnl_betfair: pnlBetfair, pnl_betfair_settled_at: pnlBetfair == null ? null : settled,
        bet_id: bet, placed_at: placed, settled_at: settled, closes_trade_id: closes,
        meta: role === 'utente' ? { fonte: 'utente', pnl_fonte: 'betfair' } : { pnl_fonte: 'betfair' },
        giorno_partita: OGGI, giorno_da: 'partita',
        __bot: 'mike' as const,
        ...extra,
    };
}
const FAR = '36124393', MIY = '36124534', VAS = '36133296';
const MIKE_04_10 = [
    riga(5152, FAR, 'Farense v Chaves', 'under_entry', 'lost', 'back', -5, -5, '445568321596', '2026-10-04T09:23:29Z', '2026-10-04T13:09:02Z', null),
    riga(5153, FAR, 'Farense v Chaves', 'under_green', 'error', 'lay', 0, null, '445568324077', '2026-10-04T09:23:31Z', null, 5152),
    riga(5154, MIY, 'Tegevajaro Miyazaki v Omiya', 'under_entry', 'won', 'back', 2.2, 2.2, '445568325409', '2026-10-04T09:23:32Z', '2026-10-04T13:09:01Z', null),
    riga(5155, MIY, 'Tegevajaro Miyazaki v Omiya', 'under_green', 'lost', 'lay', -2.13, -2.13, '445568328282', '2026-10-04T09:23:34Z', '2026-10-04T13:09:01Z', 5154),
    riga(5156, VAS, 'Vasalunds IF v FC Arlanda', 'under_entry', 'lost', 'back', -5, -5, '445572059076', '2026-10-04T10:03:50Z', '2026-10-04T13:19:06Z', null),
    riga(5157, VAS, 'Vasalunds IF v FC Arlanda', 'under_green', 'error', 'lay', 0, null, '445572063578', '2026-10-04T10:03:52Z', null, 5156),
    riga(5158, FAR, 'Farense v Chaves', 'ko_green', 'error', 'lay', 0, null, '445572154142', '2026-10-04T10:04:39Z', null, 5152),
    riga(5159, FAR, 'Farense v Chaves', 'over_cover', 'lost', 'lay', -0.82, -0.82, '445572454155', '2026-10-04T10:07:30Z', '2026-10-04T13:09:02Z', null,
        { market_type: 'OVER_UNDER_45', selection_name: 'Under 4.5 Goals' }),
    riga(5160, VAS, 'Vasalunds IF v FC Arlanda', 'utente', 'won', 'lay', 5.07, 5.07, '445577040174', '2026-10-04T13:19:06Z', '2026-10-04T13:19:06Z', 5156),
];

const giornoDi = (iso: string | null | undefined): string => {
    const ms = iso ? Date.parse(iso) : NaN;
    return Number.isFinite(ms) ? romeDay(new Date(ms)) : '';
};

/** Barra e composizione come le costruisce `useControlRoom` (stesse funzioni). */
function viste(payload: unknown) {
    const reale = leggiPnlRealeOggi(payload, OGGI);
    if (!reale) throw new Error('payload non letto');
    const opz = { oggi: OGGI, giornoDi, regolatiBetfair: new Set(reale.bet_ids), sport: 'calcio' };
    const mikeRighe = righeGiornataPerCiclo(
        righeMikeDelConto(MIKE_04_10, reale) as unknown as RigaTradeReale[], opz);
    const nettoFonte = (f: 'manuale_sito') => (reale.per_fonte[f].ordini > 0 ? reale.per_fonte[f].netto : null);
    const soloSe = (r: RigaComponente | null) => (r ? [r] : []);
    const manualeSito = soloSe(rigaSintetica(nettoFonte('manuale_sito'), null, { sport: 'calcio', origin: 'manual' }));
    const diff = differenzaContoRighe(reale, mikeRighe);
    const altro = soloSe(rigaSintetica(Math.abs(diff) >= 0.005 ? diff : null, null, { sport: 'calcio' }));
    const base = componiObiettivo({
        omega: [], safe: [], mike: mikeRighe, tennisBot: [], manualeSito, manualeApp: [], altro, scalper: [],
    });
    const composizione = composizioneDalConto(base, reale, { omega: [], safe: [], mike: mikeRighe });
    const barra = realizzatoGiornata([...mikeRighe, ...manualeSito, ...altro]
        .filter((r) => String(r.mode).toLowerCase() === 'live')).totale;
    return { reale, mikeRighe, diff, composizione, barra };
}

const voce = (c: ReturnType<typeof viste>['composizione'], k: string) => c.righe.find((r) => r.chiave === k)?.valore ?? null;

describe('04/10 - una sola verita\' col conto (runner nuovo)', () => {
    it('tessera Calcio: tutto il conto dello sport, bot -5,68 + a mano +0,53 = -5,15 netto', () => {
        // FALSIFICAZIONE: la tessera torna alla formula «solo voci dei bot»
        // (per_fonte mike+omega+safe+scalper) -> -10,75 o -5,68 -> rosso
        const t = perSportDalConto(leggiPnlRealeOggi(PAYLOAD_NUOVO_04_10, OGGI))!;
        expect(t.calcio).toEqual({
            pnl: -5.15, ordini: 7, bot: -5.68, aMano: 0.53, ordiniAMano: 1,
            chiusureAMano: 5.07, ordiniChiusureAMano: 1, commissione: 0.02,
        });
        expect(t.tennis.pnl).toBe(0);
    });

    it('composizione e barra: Mike -5,68 (con la tua chiusura), Manuale sito +0,53, totale -5,15, nessun «Altro»', () => {
        // FALSIFICAZIONE: escludere SEMPRE le righe «utente» di Mike (filtro di
        // prima): le righe dicono -10,75 contro il conto -5,68 -> differenza
        // +5,07 in «Altro sul conto» -> rosso
        const v = viste(PAYLOAD_NUOVO_04_10);
        expect(v.reale.attribuzione).toBe('posizione');
        expect(v.diff).toBe(0);
        expect(voce(v.composizione, 'mike')).toBe(-5.68);
        expect(voce(v.composizione, 'manuale_sito')).toBe(0.53);
        expect(voce(v.composizione, 'altro')).toBeNull();
        expect(v.composizione.totale).toBe(-5.15);
        expect(v.barra).toBe(-5.15);
        expect(v.composizione.chiusureAMano).toEqual([
            { chiave: 'mike', etichetta: 'Mike', netto: 5.07, ordini: 1 },
        ]);
    });

    it('Posizioni chiuse: 4 posizioni (2 V, 2 P) -5,68 = bot del conto; + a mano +0,53 = conto -5,15', () => {
        // La quarta posizione e' la copertura Over di Farense (riga 5159,
        // over_cover, nessun closes_trade_id: una posizione a se', -0,82).
        const pos = filtraChiuse(posizioniChiuse(MIKE_04_10 as unknown as TradeChiudibile[]),
            { modo: 'live', giorno: OGGI });
        const r = riepilogoChiuse(pos);
        expect([r.n, r.vinte, r.perse]).toEqual([4, 2, 2]);
        expect(r.totale).toBe(-5.68);
        expect(pos.map((p) => [p.id, p.pnlGlobale]).sort((a, b) => Number(a[0]) - Number(b[0])))
            .toEqual([[5152, -5], [5154, 0.07], [5156, 0.07], [5159, -0.82]]);
        const conto = contoPerVista(leggiPnlRealeOggi(PAYLOAD_NUOVO_04_10, OGGI), 'calcio')!;
        expect(conto).toEqual({ netto: -5.15, ordini: 7, bot: -5.68, aMano: 0.53, ordiniAMano: 1, commissione: 0.02 });
        // le posizioni dei bot della scheda = la parte «bot» del conto
        expect(conto.bot).toBe(r.totale);
        expect(Math.round((r.totale! + conto.aMano) * 100) / 100).toBe(conto.netto);
        expect(contoPerVista(leggiPnlRealeOggi(PAYLOAD_NUOVO_04_10, OGGI), null)!.netto).toBe(-5.15);
    });

    it('tutte le viste dicono la stessa cifra del conto', () => {
        const reale = leggiPnlRealeOggi(PAYLOAD_NUOVO_04_10, OGGI)!;
        const v = viste(PAYLOAD_NUOVO_04_10);
        const tessera = perSportDalConto(reale)!.calcio.pnl;
        const chiuse = contoPerVista(reale, 'calcio')!.netto;
        expect(new Set([reale.netto, tessera, chiuse, v.barra, v.composizione.totale])).toEqual(new Set([-5.15]));
    });
});

describe('04/10 - runner di prima (payload vero del DB): niente scomposizione inventata', () => {
    it('la tessera dichiara fuori gli ordini a mano e il conto intero resta -5,15', () => {
        // FALSIFICAZIONE: tacere gli ordini a mano (aManoNonSeparato assente) -> rosso
        const reale = leggiPnlRealeOggi(PAYLOAD_DB_04_10, OGGI)!;
        expect(reale.attribuzione).toBe('ordine');
        expect(reale.perSport).toBeNull();
        const t = perSportDalConto(reale)!;
        expect(t.calcio).toEqual({ pnl: -10.75, ordini: 5, aManoNonSeparato: 5.6 });
        expect(contoPerVista(reale, 'calcio')).toBeNull();
        // composizione e barra: invariate, tornano col conto per un'altra via
        const v = viste(PAYLOAD_DB_04_10);
        expect(voce(v.composizione, 'mike')).toBe(-10.75);
        expect(voce(v.composizione, 'manuale_sito')).toBe(5.6);
        expect(v.diff).toBe(0);
        expect(v.composizione.totale).toBe(-5.15);
        expect(v.composizione.chiusureAMano).toEqual([]);
    });

    it('le righe «utente» di Mike restano fuori se il conto non le conta con Mike', () => {
        const reale = leggiPnlRealeOggi(PAYLOAD_DB_04_10, OGGI);
        expect(righeMikeDelConto(MIKE_04_10, reale).map((r) => r.id)).not.toContain(5160);
        const nuovo = leggiPnlRealeOggi(PAYLOAD_NUOVO_04_10, OGGI);
        expect(righeMikeDelConto(MIKE_04_10, nuovo).map((r) => r.id)).toContain(5160);
        // una riga «utente» NON adottata dal conto resta fuori anche col runner nuovo
        const altra = { ...MIKE_04_10[8], id: 9999, bet_id: '1', signal_key: 'utente-1' };
        expect(righeMikeDelConto([altra], nuovo)).toEqual([]);
    });
});
