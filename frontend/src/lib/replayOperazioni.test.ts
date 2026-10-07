// 07/10 sera — REPLAY PROFESSIONALE: la libreria pura che dalla cronologia
// degli ordini del bot (righe `betfair_live_orders` + `_ms` del banco) ricava
// registro, ladder all'istante e P&L. Fixture = ESITI VERI del banco
// (`applica_bot.esegui`, la funzione del worker) sulle registrazioni reali:
// media under dello Scalper con accensione e clic (35797769, 35760084), Mike
// (35797769), Omega (35760084), Tennis Scalper e Tennis Swing (35790089).
// Il test chiave: il P&L della lib e' IL P&L DEL BANCO al centesimo.
// Le righe «finte» dei casi costruiti partono da una riga VERA (stesse chiavi
// e tipi) e cambiano solo i valori.
import { describe, it, expect } from 'vitest';
import type { EsitoBot, RigaBot } from './replayBot';
import { analizzaEsito } from './useOperativitaBot';
import {
    analizza, contoRegolato, eventiDellOrdine, indiceTimelineAl, istanteCursore, ladderBotAl,
    ordiniDaRighe, round2, statoOrdineTesto, statoOrdiniAl, testoEvento, riepilogoAl,
} from './replayOperazioni';
import mediaClicMulti69 from './__fixtures__/replay_pro/esito_media_clic_multi_69.json';
import mediaClic69 from './__fixtures__/replay_pro/esito_media_clic_69.json';
import mediaPresto84 from './__fixtures__/replay_pro/esito_media_presto_84.json';
import mediaPresto69 from './__fixtures__/replay_pro/esito_media_presto_69.json';
import scalperBase69 from './__fixtures__/replay_pro/esito_scalper_base_69.json';
import mike69 from './__fixtures__/replay_pro/esito_mike_69.json';
import omega84 from './__fixtures__/replay_pro/esito_omega_apertura_84.json';
import tennisScalper from './__fixtures__/replay_pro/esito_tennis_scalper.json';
import tennisSwing from './__fixtures__/replay_pro/esito_tennis_swing.json';

const ESITI: Record<string, EsitoBot> = {
    media_clic_multi_69: mediaClicMulti69 as unknown as EsitoBot,
    media_clic_69: mediaClic69 as unknown as EsitoBot,
    media_presto_84: mediaPresto84 as unknown as EsitoBot,
    media_presto_69: mediaPresto69 as unknown as EsitoBot,
    scalper_base_69: scalperBase69 as unknown as EsitoBot,
    mike_69: mike69 as unknown as EsitoBot,
    omega_apertura_84: omega84 as unknown as EsitoBot,
    tennis_scalper: tennisScalper as unknown as EsitoBot,
    tennis_swing: tennisSwing as unknown as EsitoBot,
};

describe('il P&L della lib e\' quello del banco, al centesimo, su ogni esito vero', () => {
    for (const [nome, esito] of Object.entries(ESITI)) {
        it(`${nome}: a regolamento = banco (Python) = flumine; cicli = referto del bot`, () => {
            const a = analizzaEsito(esito);
            expect(esito.versione).toBe(2);
            expect(a.ordini.length).toBe(esito.ordini);
            const banco = esito.conto_banco!;
            expect(a.regolato.lordo).toBe(banco.lordo);
            expect(a.regolato.commissione).toBe(banco.commissione);
            expect(a.regolato.netto).toBe(banco.netto);
            expect(a.regolato.mercati).toEqual(banco.mercati);
            if (esito.conto_flumine) {
                // il regolamento di FLUMINE nel banco (order.simulated.profit)
                expect(a.regolato.lordo).toBe(esito.conto_flumine.lordo);
                expect(a.regolato.mercati).toEqual(esito.conto_flumine.mercati);
            }
            const d = esito.conto_dichiarato;
            if (d?.metodo === 'cicli') {
                expect(a.cicliConto).toEqual({ lordo: d.lordo, commissione: d.commissione, netto: d.netto,
                    cicliEsitoIgnoto: d.cicli_esito_ignoto ?? 0 });
            } else if (d?.metodo === 'regolamento') {
                expect([a.regolato.lordo, a.regolato.commissione, a.regolato.netto]).toEqual([d.lordo, d.commissione, d.netto]);
            }
        });
    }

    it('i numeri del banco che la lib deve ridare (scritti qui: un cambio del banco si vede)', () => {
        const r = (n: string) => analizzaEsito(ESITI[n]);
        expect(r('media_clic_multi_69').cicliConto).toEqual({ lordo: 0.48, commissione: 0.02, netto: 0.46, cicliEsitoIgnoto: 0 });
        expect(r('media_clic_69').cicliConto).toMatchObject({ lordo: 0.13, commissione: 0.01, netto: 0.13 });
        expect(r('media_presto_84').cicliConto).toMatchObject({ lordo: -157.02, netto: -157.02 });
        expect(r('media_presto_69').cicliConto).toMatchObject({ lordo: 0.16, commissione: 0.01, netto: 0.15 });
        expect(r('scalper_base_69').regolato).toMatchObject({ lordo: 0.13, commissione: 0.01, netto: 0.12 });
        expect(r('mike_69').regolato).toMatchObject({ lordo: 0.14, commissione: 0.01, netto: 0.13 });
        expect(r('omega_apertura_84').regolato).toMatchObject({ lordo: 5.26, commissione: 0.26, netto: 5 });
        expect(r('tennis_scalper').regolato.lordo).toBe(-10.08);
        expect(r('tennis_swing').regolato.lordo).toBe(-3.48);
    });
});

describe('media under, 4 clic veri sulla 35797769 (uno rifiutato perche\' il ciclo era aperto)', () => {
    const esito = ESITI.media_clic_multi_69;
    const etichetta = (ms: number) => `t${ms}`;
    const a = analizzaEsito(esito, etichetta);

    it('ogni clic ha il suo esito leggibile; il rifiuto dice QUALE ciclo e CHE COSA lo teneva aperto', () => {
        expect(a.clic.map(c => c.esito)).toEqual(['eseguito', 'rifiutato', 'eseguito', 'eseguito']);
        expect(a.clic[0].testo).toMatch(/^ESEGUITO: prima punta 10,00 @ 2,20 alle t\d+/);
        const rif = a.clic[1].testo;
        expect(rif).toMatch(/^RIFIUTATO: il ciclo 1 è ancora aperto: BANCA 11,52 @ 2,20 non ancora abbinata, abbinata per intero solo alle t1783710628105/);
        // il clic eseguito porta alla prima punta (un ordine vero del registro)
        for (const c of a.clic.filter(x => x.eseguito)) {
            expect(c.ordine).not.toBeNull();
            expect(a.perChiave.get(c.ordine!)!.lato).toBe('back');
            expect(c.seekMs).toBe(a.perChiave.get(c.ordine!)!.primoMs);
        }
    });

    it('i cicli della lib sono quelli del bot (stessi ordini, stesso P&L, stessa fine)', () => {
        const veri = a.cicli.filter(c => c.abbinatoBack + c.abbinatoLay > 0);
        expect(veri).toHaveLength(esito.cicli_bot!.length);
        veri.forEach((c, i) => {
            const b = esito.cicli_bot![i];
            expect(c.ordini.map(k => k.slice(2)).sort()).toEqual([...b.ordini_id].sort());
            expect(Math.round(c.garantito * 100) / 100).toBe(b.lordo);
            expect(c.stato).toBe('chiuso');
            expect(c.origine).toBe('uscita in profitto');
            expect(Math.abs((c.aMs ?? 0) - (b.fine_ms ?? 0))).toBeLessThanOrEqual(1500);
        });
    });
});

describe('registro: una riga per ORDINE, eventi sotto, legami di sostituzione', () => {
    it('35760084: la banca tolta per il rientro e rimessa (annulla e ripiazza) e\' un legame, non due righe uguali', () => {
        const a = analizzaEsito(ESITI.media_presto_84);
        const vecchia = a.ordini.find(o => o.lato === 'lay' && o.quota === 2.74)!;
        const nuova = a.ordini.find(o => o.lato === 'lay' && o.quota === 2.78)!;
        expect(vecchia.sostituitoDa).toBe(nuova.chiave);
        expect(nuova.sostituisce).toBe(vecchia.chiave);
        const piazzata = a.eventi.find(e => e.ordine === nuova.chiave && e.tipo === 'piazzato')!;
        expect(testoEvento(piazzata)).toBe('BANCA SPOSTATA da 2,74 a 2,78 (riprezzo, 20,14) (tolta per il rientro: PUNTA 10,00 @ 2,82, poi rimessa)');
        const tolta = a.eventi.find(e => e.ordine === vecchia.chiave && e.tipo === 'annullato')!;
        expect(testoEvento(tolta)).toMatch(/^TOLTA 10,15 non abbinati \(abbinato 0,00\): sostituita dal nuovo ordine$/);
        // MAI «chiuso» per un ordine con abbinato 0 tolto dal mercato
        const ultima = vecchia.righe[vecchia.righe.length - 1];
        expect(statoOrdineTesto(ultima, true)).toBe('sostituito');
        expect(statoOrdineTesto(ultima, false)).toBe('annullato');
    });

    it('35790089 tennis: il replace di flumine (stesso ref, due bet id) e\' due ordini legati, dichiarato dal banco', () => {
        const a = analizzaEsito(ESITI.tennis_scalper);
        expect(a.ordini).toHaveLength(72);
        const stessoRef = a.ordini.filter(o => o.ref === 'sc76783175');
        expect(stessoRef.map(o => o.betId)).toEqual(['100000000027', '100000000028']);
        const [v, n] = stessoRef;
        expect(n.sostituisce).toBe(v.chiave);
        expect(n.sostituzioneDichiarata).toBe(true);
        const e = a.eventi.find(x => x.ordine === n.chiave && x.tipo === 'piazzato')!;
        expect(testoEvento(e)).toBe('BANCA SPOSTATA da 1,01 a 1,69 (riprezzo, 0,79) (replace di Betfair)');
        // il vecchio: richiesta di riprezzo, poi tolto per intero
        expect(a.eventi.filter(x => x.ordine === v.chiave).map(x => x.tipo))
            .toEqual(['piazzato', 'appoggiato', 'annullato', 'riprezzo_richiesto', 'annullato']);
        // le due quote dello scalper spostate insieme NON sono un «rientro»
        const spostate = a.eventi.filter(x => x.tipo === 'piazzato' && x.sostituisce);
        expect(spostate.length).toBeGreaterThan(10);
        expect(spostate.filter(x => (x.motivoSostituzione ?? '').includes('rientro'))).toEqual([]);
    });

    it('esito di PRIMA (senza _ordine): due bet id con lo stesso ref restano due ordini', () => {
        const senza = (ESITI.tennis_scalper.righe as RigaBot[]).map(r => {
            const { _ordine, _sostituisce, ...resto } = r;
            void _ordine; void _sostituisce;
            return resto as RigaBot;
        });
        const o = ordiniDaRighe(senza).filter(x => x.ref === 'sc76783175');
        expect(o.map(x => x.betId)).toEqual(['100000000027', '100000000028']);
    });
});

// ---- casi costruiti da una riga VERA (stesse chiavi e tipi) ----------------
const VERA = (mediaClicMulti69 as unknown as EsitoBot).righe[0];
const MID = VERA.market_id;
const UNDER = VERA.selection_id;
const OVER = 47973;
function riga(o: Partial<RigaBot> & { _ms: number; _ordine: string }): RigaBot {
    return {
        ...VERA, bet_id: null, client_order_ref: `d30755a527963-${o._ordine}`, size_matched: 0, size_remaining: o.size ?? VERA.size ?? 0,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 0, status: 'EXECUTABLE',
        matched_at: null, _trade_id: `t-${o._ordine}`, _sostituisce: null, ...o,
    } as RigaBot;
}

describe('ciclo di vita di un ordine (eventi e stato all\'istante)', () => {
    const R: RigaBot[] = [
        riga({ _ms: 1000, _ordine: '1', side: 'lay', price: 2.2, size: 11.52, status: 'PENDING', size_remaining: 11.52 }),
        riga({ _ms: 2000, _ordine: '1', side: 'lay', price: 2.2, size: 11.52, bet_id: '7', size_remaining: 11.52 }),
        riga({ _ms: 3000, _ordine: '1', side: 'lay', price: 2.2, size: 11.52, bet_id: '7', size_matched: 9.52, average_price_matched: 2.2, size_remaining: 2 }),
        riga({ _ms: 4000, _ordine: '1', side: 'lay', price: 2.2, size: 11.52, bet_id: '7', size_matched: 11.52, average_price_matched: 2.2, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
    ];
    const [o] = ordiniDaRighe(R);
    it('piazzato -> appoggiato -> abbinato in parte -> abbinato per intero', () => {
        const ev = eventiDellOrdine(o);
        expect(ev.map(e => e.tipo)).toEqual(['piazzato', 'appoggiato', 'abbinato_parziale', 'abbinato_totale']);
        expect(testoEvento(ev[2])).toBe('abbinata IN PARTE 9,52 @ 2,20 — totale 9,52 su 11,52, residuo 2,00');
        expect(ev[3].abbinatoEvento).toBe(2);
    });
    it('ladder all\'istante: in volo, appoggiato, parziale, abbinato (la cronologia, non lo stato finale)', () => {
        const a = (ms: number) => ladderBotAl([o], ms, MID)[UNDER]?.livelli[0];
        expect(ladderBotAl([o], 999, MID)).toEqual({});
        expect(a(1000)).toMatchObject({ lato: 'lay', quota: 2.2, inVolo: 11.52, appoggiato: 0, abbinato: 0 });
        expect(a(2500)).toMatchObject({ appoggiato: 11.52, abbinato: 0 });
        expect(a(3000)).toMatchObject({ appoggiato: 2, abbinato: 9.52 });
        expect(a(9999)).toMatchObject({ appoggiato: 0, abbinato: 11.52 });
        const s = ladderBotAl([o], 9999, MID)[UNDER];
        expect(s.seVinceSel).toBeCloseTo(-11.52 * 1.2, 9);
        expect(s.sePerdeSel).toBeCloseTo(11.52, 9);
    });
    it('annullato con parziale, scaduto (lapse) e rifiutato', () => {
        const P = [
            riga({ _ms: 1, _ordine: 'a', side: 'back', price: 3, size: 10, bet_id: '1' }),
            riga({ _ms: 2, _ordine: 'a', side: 'back', price: 3, size: 10, bet_id: '1', size_matched: 4, average_price_matched: 3, size_remaining: 0, size_cancelled: 6, status: 'EXECUTION_COMPLETE' }),
            riga({ _ms: 1, _ordine: 'b', side: 'back', price: 3, size: 10, bet_id: '2' }),
            riga({ _ms: 5, _ordine: 'b', side: 'back', price: 3, size: 10, bet_id: '2', size_remaining: 0, size_lapsed: 10, status: 'EXECUTION_COMPLETE' }),
            riga({ _ms: 1, _ordine: 'c', side: 'back', price: 3, size: 10, status: 'EXECUTION_COMPLETE', size_remaining: 0 }),
        ];
        const oo = ordiniDaRighe(P);
        const tipi = (k: string) => eventiDellOrdine(oo.find(x => x.chiave === `o:${k}`)!).map(e => e.tipo);
        expect(tipi('a')).toEqual(['piazzato', 'appoggiato', 'abbinato_parziale', 'annullato']);
        expect(tipi('b')).toEqual(['piazzato', 'appoggiato', 'scaduto']);
        expect(tipi('c')).toEqual(['piazzato', 'rifiutato']);
        const ult = (k: string) => { const x = oo.find(y => y.chiave === `o:${k}`)!; return x.righe[x.righe.length - 1]; };
        expect(statoOrdineTesto(ult('a'))).toBe('abbinato 4.00, resto annullato');
        expect(statoOrdineTesto(ult('b'))).toBe('scaduto');
        expect(statoOrdineTesto(ult('c'))).toBe('rifiutato (mai sul book)');
        expect(statoOrdiniAl(oo, 1).filter(x => x.vivo)).toHaveLength(2);
    });
});

describe('caso vero dal DB (richiesta 9a30d0a2): due banche tolte e rimesse IDENTICHE nello stesso ms per il rientro', () => {
    // bet 6 -> 7 @2,04 10,20 e bet 9 -> 10 @2,10 25,19 (ricostruito con le chiavi vere)
    const R: RigaBot[] = [
        riga({ _ms: 100, _ordine: '5', side: 'back', price: 2.08, size: 10, bet_id: '5', size_matched: 10, average_price_matched: 2.08, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
        riga({ _ms: 100, _ordine: '6', side: 'lay', price: 2.04, size: 10.2, bet_id: '6' }),
        riga({ _ms: 200, _ordine: '6', side: 'lay', price: 2.04, size: 10.2, bet_id: '6', size_remaining: 0, size_cancelled: 10.2, status: 'EXECUTION_COMPLETE' }),
        riga({ _ms: 200, _ordine: '8', side: 'back', price: 2.12, size: 10, bet_id: '8', status: 'PENDING' }),
        riga({ _ms: 200, _ordine: '7', side: 'lay', price: 2.04, size: 10.2, bet_id: '7' }),
        riga({ _ms: 300, _ordine: '9', side: 'lay', price: 2.1, size: 25.19, bet_id: '9' }),
        riga({ _ms: 400, _ordine: '9', side: 'lay', price: 2.1, size: 25.19, bet_id: '9', size_remaining: 0, size_cancelled: 25.19, status: 'EXECUTION_COMPLETE' }),
        riga({ _ms: 400, _ordine: '11', side: 'back', price: 2.14, size: 20, bet_id: '11', status: 'PENDING' }),
        riga({ _ms: 400, _ordine: '10', side: 'lay', price: 2.1, size: 25.19, bet_id: '10' }),
    ];
    const a = analizza(R, null);
    it('nel registro: «BANCA tolta e RIMESSA identica» col motivo del rientro, e la vecchia e\' «sostituito»', () => {
        const t = (k: string) => testoEvento(a.eventi.find(e => e.ordine === `o:${k}` && e.tipo === 'piazzato')!);
        expect(t('7')).toBe('BANCA tolta e RIMESSA identica 10,20 @ 2,04 (tolta per il rientro: PUNTA 10,00 @ 2,12, poi rimessa)');
        expect(t('10')).toBe('BANCA tolta e RIMESSA identica 25,19 @ 2,10 (tolta per il rientro: PUNTA 20,00 @ 2,14, poi rimessa)');
        const vecchia = a.ordini.find(o => o.chiave === 'o:6')!;
        expect(statoOrdineTesto(vecchia.righe[vecchia.righe.length - 1], vecchia.sostituitoDa != null)).toBe('sostituito');
        // all'istante 200 sul ladder c'e' UNA banca a 2,04 (la nuova), non due
        const l = ladderBotAl(a.ordini, 200, MID)[UNDER].livelli.filter(x => x.lato === 'lay' && x.quota === 2.04);
        expect(l).toHaveLength(1);
        expect(l[0].appoggiato).toBe(10.2);
    });
});

describe('cicli: chiusura in perdita, regolamento del mercato, piu\' mercati', () => {
    const ESITI_MERCATO = { [MID]: { market_type: 'OVER_UNDER_25', runners: { [String(UNDER)]: 'LOSER', [String(OVER)]: 'WINNER' }, ordine_runner: [UNDER, OVER], stato: 'CLOSED', in_gioco_ms: null, chiuso_ms: 99_000, aliquota: 0.05, vincitori: [OVER] } };
    it('uscita in perdita (coperta) e un ciclo aperto regolato dalla chiusura del mercato; un secondo mercato separato', () => {
        const R: RigaBot[] = [
            riga({ _ms: 10, _ordine: 'p', side: 'back', price: 2.0, size: 10, bet_id: '1', size_matched: 10, average_price_matched: 2.0, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
            riga({ _ms: 10, _ordine: 'q', side: 'lay', price: 2.2, size: 9.09, bet_id: '2', size_matched: 9.09, average_price_matched: 2.2, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
            riga({ _ms: 20, _ordine: 'r', side: 'back', price: 2.0, size: 5, bet_id: '3', size_matched: 5, average_price_matched: 2.0, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
            riga({ _ms: 30, _ordine: 'x', market_id: '1.999', side: 'back', price: 3.0, size: 2, bet_id: '4', size_matched: 2, average_price_matched: 3, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
        ];
        const a = analizza(R, ESITI_MERCATO);
        const [c1, c2, c3] = a.cicli;
        expect(c1).toMatchObject({ n: 1, marketId: MID, stato: 'chiuso', origine: 'uscita in perdita', aMs: 10 });
        expect(c1.garantito).toBeCloseTo(Math.min(10 - 9.09 * 1.2, -10 + 9.09), 9);
        expect(c2).toMatchObject({ n: 2, marketId: MID, stato: 'regolato', aMs: 99_000, regolato: -5 });
        expect(c3).toMatchObject({ n: 3, marketId: '1.999', stato: 'aperto', regolato: null });
        expect(a.eventi.filter(e => e.tipo === 'mercato_chiuso')).toHaveLength(1);
        const conto = contoRegolato(a.ordini, ESITI_MERCATO);
        expect(conto.mercati).toEqual({ [MID]: -10 + 9.09 - 5 });
        expect(conto.mercatiNonRegolati).toEqual(['1.999']);
        const t = riepilogoAl(a.ordini, a.cicli, 25, ESITI_MERCATO);
        expect(t.cicliChiusi).toBe(1);
        expect(t.esposizione).toBeGreaterThan(0);
    });
});

describe('il salto della timeline all\'istante esatto', () => {
    const TL = [{ ts: '2026-07-10T18:00:00+00:00' }, { ts: '2026-07-10T18:00:10+00:00' }, { ts: '2026-07-10T18:00:20+00:00' }];
    const t1 = Date.parse(TL[1].ts);
    it('indice del passo che contiene l\'istante; cursore esatto finche\' la barra non si muove', () => {
        expect(indiceTimelineAl(TL, t1 + 9_999)).toBe(1);
        expect(indiceTimelineAl(TL, t1)).toBe(1);
        expect(indiceTimelineAl(TL, t1 - 1)).toBe(0);
        expect(indiceTimelineAl(TL, 0)).toBe(0);
        expect(istanteCursore(TL, 1, { index: 1, ms: t1 + 1234 })).toEqual({ ts: new Date(t1 + 1234).toISOString(), ms: t1 + 1234, esatto: true });
        expect(istanteCursore(TL, 2, { index: 1, ms: t1 + 1234 })).toMatchObject({ ms: Date.parse(TL[2].ts), esatto: false });
    });
});

describe('arrotondamenti come Python/flumine (il banco arrotonda per ordine con round(x, 2))', () => {
    it('round2 = round(x, 2) di Python (valori di riferimento calcolati con Python 3)', () => {
        const python: Array<[number, number]> = [[0.125, 0.12], [0.375, 0.38], [0.015, 0.01], [0.045, 0.04], [1.005, 1.0],
            [2.675, 2.67], [-0.125, -0.12], [0.135, 0.14], [10.115, 10.12], [0.0236, 0.02], [1.8476, 1.85]];
        for (const [x, atteso] of python) expect(round2(x)).toBe(atteso);
    });
    it('profitto al centesimo PER ORDINE (flumine), non sul totale: 3 punte vincenti da 0,15 @ 1,10 = 0,06 (Python: 3 x round(0,015..., 2)), non 0,05', () => {
        const ESITO = { [MID]: { market_type: 'OVER_UNDER_25', runners: { [String(UNDER)]: 'WINNER', [String(OVER)]: 'LOSER' }, ordine_runner: [UNDER, OVER], stato: 'CLOSED', in_gioco_ms: null, chiuso_ms: 9, aliquota: 0.05, vincitori: [UNDER] } };
        const R = ['a', 'b', 'c'].map(k => riga({ _ms: 1, _ordine: k, side: 'back', price: 1.1, size: 0.15, bet_id: k, size_matched: 0.15, average_price_matched: 1.1, size_remaining: 0, status: 'EXECUTION_COMPLETE' }));
        expect(contoRegolato(ordiniDaRighe(R), ESITO).lordo).toBe(0.06);
        // pareggio esatto: 0,25 @ 1,50 vincente = 0,125 -> 0,12 (come Python), non 0,13
        const P = [riga({ _ms: 1, _ordine: 'z', side: 'back', price: 1.5, size: 0.25, bet_id: 'z', size_matched: 0.25, average_price_matched: 1.5, size_remaining: 0, status: 'EXECUTION_COMPLETE' })];
        expect(contoRegolato(ordiniDaRighe(P), ESITO).lordo).toBe(0.12);
    });
});

describe('nuova gestione della banca (media under, delegato parallelo): spostata con replace e integrazione', () => {
    it('banca spostata: nuovo ordine dello STESSO trade con importo uguale a quello tolto (preferito a un altro nato prima)', () => {
        const R: RigaBot[] = [
            riga({ _ms: 100, _ordine: 'A', _trade_id: 'T', side: 'lay', price: 2.2, size: 10, bet_id: '1' }),
            riga({ _ms: 200, _ordine: 'A', _trade_id: 'T', side: 'lay', price: 2.2, size: 10, bet_id: '1', size_remaining: 0, size_cancelled: 10, status: 'EXECUTION_COMPLETE' }),
            riga({ _ms: 200, _ordine: 'X', _trade_id: 'ALTRO', side: 'lay', price: 2.3, size: 4, bet_id: '2' }),
            riga({ _ms: 300, _ordine: 'C', _trade_id: 'T', side: 'lay', price: 2.16, size: 10, bet_id: '3' }),
        ];
        const a = analizza(R, null);
        expect(a.ordini.find(o => o.chiave === 'o:C')!.sostituisce).toBe('o:A');
        expect(a.ordini.find(o => o.chiave === 'o:X')!.sostituisce).toBeNull();
        expect(testoEvento(a.eventi.find(e => e.ordine === 'o:C' && e.tipo === 'piazzato')!))
            .toBe('BANCA SPOSTATA da 2,20 a 2,16 (riprezzo, 10,00)');
    });
    it('integrazione: ordine nuovo alla stessa quota di una banca gia\' sul book', () => {
        const R: RigaBot[] = [
            riga({ _ms: 100, _ordine: 'B', side: 'lay', price: 2.2, size: 11.52, bet_id: '1' }),
            riga({ _ms: 150, _ordine: 'B', side: 'lay', price: 2.2, size: 11.52, bet_id: '1', size_matched: 3, average_price_matched: 2.2, size_remaining: 8.52 }),
            riga({ _ms: 200, _ordine: 'I', side: 'lay', price: 2.2, size: 5.1, bet_id: '2' }),
        ];
        const a = analizza(R, null);
        expect(testoEvento(a.eventi.find(e => e.ordine === 'o:I' && e.tipo === 'piazzato')!))
            .toBe('INTEGRAZIONE della BANCA: +5,10 @ 2,20 (alla stessa quota della BANCA già sul book, 8,52 non abbinati)');
        // sul ladder a 2,20: 8,52 + 5,10 appoggiati, 3,00 abbinati
        const l = ladderBotAl(a.ordini, 200, MID)[UNDER].livelli.find(x => x.lato === 'lay' && x.quota === 2.2)!;
        expect(l.appoggiato).toBeCloseTo(13.62, 9);
        expect(l.abbinato).toBe(3);
    });
});
