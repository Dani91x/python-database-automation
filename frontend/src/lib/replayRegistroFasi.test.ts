// 08/10 (cantiere 10) — REGISTRO OPERAZIONI E P&L DEL BOT: i cicli sono quelli
// del BOT (`esito.cicli_bot`) e il registro si divide per FASE della partita.
//
// Difetto visto dall'utente (Match Replay 35768297, media under): il registro
// contava 3 cicli «da posizione piatta a piatta» mentre il bot e il DB ne
// contano 4: il ciclo 1 chiuso alle 23:04:21 con il rientro automatico nello
// stesso istante veniva FUSO col ciclo 2 (le righe nate in quell'istante
// entrano nel ciclo ancora aperto, `cicliOperativi`). E il registro metteva in
// fila pre-partita e gioco senza separarli.
//
// Dati: ESITI VERI del banco (`__fixtures__/replay_pro`, `applica_bot.esegui`)
// e le cronologie IPS VERE delle stesse registrazioni (`replay_barra_*`: le
// righe di `live_score_timeline` come le riceve la pagina; tennis
// `replay_tennis_35790089`). I casi costruiti partono da una riga VERA e da un
// ciclo dichiarato VERO (stesse chiavi e tipi) e cambiano solo i valori.
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import type { CicloDichiarato, EsitoBot } from './replayBot';
import { analizzaEsito } from './useOperativitaBot';
import {
    eventiDelRegistro, sezioniPerFase, testoEvento, type MetodoConto,
} from './replayOperazioni';
import {
    confiniCalcio, faseCalcioAl, faseCalcioDaConfini, fasiFisse, faseTennisDaEtichetta,
    FASE_1T, FASE_2T, FASE_GIOCO_CALCIO, FASE_INTERVALLO, FASE_PRE, type FaseReplay,
} from './replayFasi';
import { FIXTURE_BARRA, replayDaFixture } from './__fixtures__/replayBarra';
import { ESITO_4, RIGHE_4, rigaDaVera } from './__fixtures__/registroCicliFinti';
import { faseTennis, inizioInGioco, ordinaPunteggio, type TennisReplayData } from './tennisReplay';
import tennisFixture from './__fixtures__/replay_tennis_35790089.json';
import mediaClicMulti69 from './__fixtures__/replay_pro/esito_media_clic_multi_69.json';
import mediaClic69 from './__fixtures__/replay_pro/esito_media_clic_69.json';
import mediaPresto84 from './__fixtures__/replay_pro/esito_media_presto_84.json';
import mediaPresto69 from './__fixtures__/replay_pro/esito_media_presto_69.json';
import scalperBase69 from './__fixtures__/replay_pro/esito_scalper_base_69.json';
import mike69 from './__fixtures__/replay_pro/esito_mike_69.json';
import omega84 from './__fixtures__/replay_pro/esito_omega_apertura_84.json';
import tennisScalper from './__fixtures__/replay_pro/esito_tennis_scalper.json';
import tennisSwing from './__fixtures__/replay_pro/esito_tennis_swing.json';

const E = (x: unknown) => x as EsitoBot;
const MULTI = E(mediaClicMulti69);
const ESITI: Array<[string, EsitoBot, '35797769' | '35760084' | 'tennis']> = [
    ['media_clic_multi_69', MULTI, '35797769'],
    ['media_clic_69', E(mediaClic69), '35797769'],
    ['media_presto_84', E(mediaPresto84), '35760084'],
    ['media_presto_69', E(mediaPresto69), '35797769'],
    ['scalper_base_69', E(scalperBase69), '35797769'],
    ['mike_69', E(mike69), '35797769'],
    ['omega_apertura_84', E(omega84), '35760084'],
    ['tennis_scalper', E(tennisScalper), 'tennis'],
    ['tennis_swing', E(tennisSwing), 'tennis'],
];

// le cronologie IPS VERE, ordinate come le ordina la pagina
const IPS = {
    '35797769': [...replayDaFixture(FIXTURE_BARRA['35797769']).score_timeline].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0)),
    '35760084': [...replayDaFixture(FIXTURE_BARRA['35760084']).score_timeline].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0)),
};
const TENNIS = tennisFixture as unknown as TennisReplayData;
const PUNTEGGI_TENNIS = ordinaPunteggio(TENNIS.score_timeline);
const IN_GIOCO_TENNIS = inizioInGioco(TENNIS.frames);
const faseTennisAl = (ms: number) => faseTennisDaEtichetta(faseTennis(PUNTEGGI_TENNIS, new Date(ms).toISOString(), IN_GIOCO_TENNIS));

function faseDi(reg: '35797769' | '35760084' | 'tennis'): (ms: number) => FaseReplay {
    if (reg === 'tennis') return faseTennisAl;
    const c = confiniCalcio(IPS[reg]);
    return ms => faseCalcioDaConfini(c, ms);
}
const metodoDi = (e: EsitoBot): MetodoConto => (e.conto_dichiarato?.metodo === 'cicli' ? 'cicli' : 'regolamento');

// ---------------------------------------------------------------------------
// fasi del calcio dallo stato IPS VERO
// ---------------------------------------------------------------------------
describe('fasi del calcio dagli stati IPS della registrazione (KickOff / FirstHalfEnd / SecondHalfKickOff)', () => {
    it('35797769: i confini sono gli istanti VERI degli eventi della timeline Betfair', () => {
        const c = confiniCalcio(IPS['35797769']);
        expect(c).toEqual({
            inizio: Date.parse('2026-07-10T19:01:02.613496+00:00'),
            finePrimo: Date.parse('2026-07-10T19:50:45.705431+00:00'),
            ripresa: Date.parse('2026-07-10T20:07:16.335194+00:00'),
            inizioDaIps: true,
        });
        const fm = (ms: number) => faseCalcioAl(IPS['35797769'], ms).id;
        const f = (iso: string) => fm(Date.parse(iso));
        expect(f('2026-07-10T18:30:00Z')).toBe('pre');
        expect(fm(c.inizio! - 1)).toBe('pre');                       // 1 ms prima del fischio
        expect(fm(c.inizio!)).toBe('1t');
        // recupero del 1° tempo (minuto 46-51 con KickOff): ancora 1° tempo
        expect(f('2026-07-10T19:49:00Z')).toBe('1t');
        expect(fm(c.finePrimo! - 1)).toBe('1t');
        expect(fm(c.finePrimo!)).toBe('int');
        expect(fm(c.ripresa! - 1)).toBe('int');
        expect(fm(c.ripresa!)).toBe('2t');
        // dopo SecondHalfEnd si resta nel 2° tempo
        expect(f('2026-07-10T21:30:00Z')).toBe('2t');
    });

    it('35760084: stessa regola sull\'altra registrazione vera', () => {
        const c = confiniCalcio(IPS['35760084']);
        expect(c.inizioDaIps).toBe(true);
        expect(c.inizio).not.toBeNull();
        expect(c.finePrimo).toBeGreaterThan(c.inizio!);
        expect(c.ripresa).toBeGreaterThan(c.finePrimo!);
    });

    it('un KickOff RI-EMESSO a meta\' partita (riconnessione del feed) non sposta il calcio d\'inizio', () => {
        const vero = IPS['35797769'];
        const ko = vero.find(r => r.event_type === 'KickOff')!;
        const riemesso = { ...ko, ts: '2026-07-10T19:30:00.000000+00:00', minute: 0 };
        const conRiemesso = [...vero, riemesso].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
        expect(confiniCalcio(conRiemesso)).toEqual(confiniCalcio(vero));
        // un FirstHalfEnd ri-emesso DOPO la ripresa non riporta all'intervallo
        const fhe = vero.find(r => r.event_type === 'FirstHalfEnd')!;
        const tardi = [...vero, { ...fhe, ts: '2026-07-10T20:30:00.000000+00:00' }].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
        expect(faseCalcioAl(tardi, Date.parse('2026-07-10T20:40:00Z'))).toBe(FASE_2T);
    });

    it('senza gli stati dei tempi la fase e\' «IN GIOCO (tempi IPS non registrati)», mai inventata dal minuto', () => {
        const senza = IPS['35797769'].filter(r => r.event_type !== 'FirstHalfEnd' && r.event_type !== 'SecondHalfKickOff');
        expect(faseCalcioAl(senza, Date.parse('2026-07-10T20:30:00Z'))).toBe(FASE_GIOCO_CALCIO);
        expect(faseCalcioAl(senza, Date.parse('2026-07-10T18:30:00Z'))).toBe(FASE_PRE);
        // senza KickOff: l'inizio e' la prima riga col minuto (il confine di minutoDiGioco)
        const senzaKo = IPS['35797769'].filter(r => r.event_type !== 'KickOff');
        const primoMinuto = senzaKo.find(r => r.minute != null)!;
        expect(confiniCalcio(senzaKo)).toMatchObject({ inizio: Date.parse(primoMinuto.ts), inizioDaIps: false });
        expect(faseCalcioAl([], 0)).toBe(FASE_PRE);
    });

    it('tennis: PRE-PARTITA e SET n da `faseTennis` (35790089, registrazione vera)', () => {
        expect(faseTennisDaEtichetta('pre')).toBe(FASE_PRE);
        expect(faseTennisDaEtichetta('Set 2')).toMatchObject({ id: 'set2', nome: 'SET 2' });
        expect(faseTennisDaEtichetta('In gioco').id).toBe('gioco');
        // prima del primo frame in gioco (flag di mercato): PRE-PARTITA, come `faseTennis`
        expect(faseTennisAl(Date.parse(IN_GIOCO_TENNIS!) - 1)).toBe(FASE_PRE);
        const r = PUNTEGGI_TENNIS.find(x => x.ts >= IN_GIOCO_TENNIS! && x.score.current_set != null)!;
        expect(faseTennisAl(Date.parse(r.ts)).nome).toBe(`SET ${r.score.current_set}`);
        expect(fasiFisse('tennis').map(f => f.nome)).toEqual(['PRE-PARTITA', 'SET 1', 'SET 2']);
        expect(fasiFisse('calcio')).toEqual([FASE_PRE, FASE_1T, FASE_INTERVALLO, FASE_2T]);
    });
});

// ---------------------------------------------------------------------------
// i cicli del registro: quelli del BOT
// ---------------------------------------------------------------------------
describe('il registro usa ESATTAMENTE i cicli del bot quando l\'esito li porta', () => {
    it('esiti veri della media under: numero, istanti, origine, lordo/netto del bot; ogni ordine in un solo ciclo', () => {
        for (const e of [MULTI, E(mediaClic69), E(mediaPresto84), E(mediaPresto69)]) {
            const a = analizzaEsito(e);
            const r = a.registro;
            expect(r.fonte).toBe('bot');
            expect(r.cicli.map(c => c.n)).toEqual(e.cicli_bot!.map(d => d.ciclo));
            r.cicli.forEach((c, i) => {
                const d = e.cicli_bot![i];
                expect(c.dichiarato).toBe(d);
                expect(c.daMs).toBe(d.inizio_ms);
                if (d.fine_ms != null) expect(c.aMs).toBe(d.fine_ms);
                expect(c.pnl).toBe(d.lordo);
                expect(c.ordini.map(k => k.slice(2)).sort()).toEqual([...d.ordini_id].sort());
            });
            expect(r.fuoriCiclo).toEqual([]);
            expect(r.mancanti).toEqual([]);
        }
        // 35760084: il ciclo aperto regolato dal libro finale finisce alla chiusura del mercato
        const p84 = analizzaEsito(E(mediaPresto84)).registro.cicli[0];
        expect(p84.stato).toBe('regolato');
        expect(p84.aMs).toBe(E(mediaPresto84).esiti_mercati![p84.marketId].chiuso_ms);
    });

    it('senza cicli_bot: ripiego «da posizione piatta a piatta», dichiarato come tale, numeri di prima', () => {
        for (const e of [E(scalperBase69), E(mike69), E(omega84), E(tennisScalper), E(tennisSwing)]) {
            const a = analizzaEsito(e);
            expect(a.registro.fonte).toBe('ordini');
            expect(a.registro.cicli.map(c => [c.n, c.daMs, c.aMs, c.ordini]))
                .toEqual(a.cicli.map(c => [c.n, c.daMs, c.aMs, c.ordini]));
            expect(a.registro.cicli.map(c => c.pnl)).toEqual(a.cicli.map(c => (c.stato === 'regolato' ? c.regolato : c.garantito)));
        }
    });
});

// ---- contratto Python <-> TS sulla forma di cicli_bot (lato TS; lato Python:
// `Betfair/stream/tests/test_contratto_cicli_bot_ts_2026_10_08.py`) ----
// tsc rifiuta questo oggetto se manca o avanza una chiave rispetto al tipo
const CHIAVI_CICLO: Record<keyof CicloDichiarato, true> = {
    ciclo: true, ordini: true, rientri: true, banca: true, esito: true, lordo: true, netto: true,
    inizio_ms: true, fine_ms: true, puntato: true, ordini_id: true, origine: true, clic: true,
    prima_punta_ordine: true, prima_punta_ms: true, riga: true,
};
describe('contratto: le chiavi di cicli_bot negli esiti VERI sono quelle del tipo CicloDichiarato', () => {
    it('ogni ciclo di ogni esito della media under', () => {
        const attese = Object.keys(CHIAVI_CICLO).sort();
        for (const [nome, e] of ESITI) {
            for (const c of e.cicli_bot ?? []) expect([nome, Object.keys(c).sort()]).toEqual([nome, attese]);
        }
    });
});

// ---- il difetto: 4 cicli del bot, due coppie che si toccano nello stesso istante ----
// (l'esito costruito sta in `__fixtures__/registroCicliFinti.ts`, lo usa anche il test del componente)

describe('il caso del difetto: 4 cicli del bot, due coppie che si toccano nello stesso istante', () => {
    const a = analizzaEsito(ESITO_4);
    it('la regola «da piatto a piatto» li fonde (il ripiego di prima: 2 cicli)', () => {
        expect(a.cicli.filter(c => c.abbinatoBack + c.abbinatoLay > 0)).toHaveLength(2);
    });
    it('il registro ne mostra 4, coi numeri e le origini del bot; i due che si toccano restano 2', () => {
        const r = a.registro;
        expect(r.fonte).toBe('bot');
        expect(r.cicli.map(c => c.n)).toEqual([1, 2, 3, 4]);
        expect(r.cicli.map(c => c.dichiarato!.origine)).toEqual(['clic', 'rientro_automatico', 'clic', 'rientro_automatico']);
        expect(r.cicli[0].aMs).toBe(2000);
        expect(r.cicli[1].daMs).toBe(1950);
        expect(r.cicli[0].ordini).toEqual(['o:ap', 'o:ab']);
        expect(r.cicli[1].ordini).toEqual(['o:bp', 'o:bb']);
        expect(r.cicli.map(c => c.pnl)).toEqual([0.18, 0.18, 0.18, 0.18]);
        // i totali non cambiano: il conto dei cicli (ricavati) e' quello del referto del bot
        expect(a.cicliConto).toMatchObject({ lordo: 0.72, commissione: 0.04, netto: 0.68 });
    });
    it('vista cronologica: le chiusure di ciclo sono quelle del bot (4), non quelle ricavate (2)', () => {
        const ev = eventiDelRegistro(a.eventi, a.registro);
        const chiusure = ev.filter(e => e.tipo === 'ciclo_chiuso');
        expect(chiusure.map(e => [e.ciclo, e.ms])).toEqual([[1, 2000], [2, 3000], [3, 6000], [4, 7000]]);
        expect(testoEvento(chiusure[0])).toBe('CICLO 1 del bot chiuso: CHIUSO — lordo +0,18 · netto +0,17');
        // gli eventi degli ordini sono tutti quelli di prima, nello stesso ordine
        expect(ev.filter(e => e.ordine).map(e => e.id)).toEqual(a.eventi.filter(e => e.ordine).map(e => e.id));
        // a pari istante prima gli eventi degli ordini, poi la chiusura del ciclo
        const i2000 = ev.filter(e => e.ms === 2000);
        expect(i2000[i2000.length - 1].tipo).toBe('ciclo_chiuso');
    });
    it('il clic rifiutato «ciclo aperto» nomina il ciclo DEL BOT', () => {
        const clic = [{ ...MULTI.clic_bot![1], id: 'clic-x', clic_ms: 2500, letto_ms: 2500 }];
        const b = analizzaEsito({ ...ESITO_4, clic_bot: clic });
        expect(b.clic[0].testo).toMatch(/^RIFIUTATO: il ciclo 2 è ancora aperto: BANCA 10,19 @ 2,16/);
        // senza i cicli del bot resta il numero ricavato (1)
        const c = analizzaEsito({ ...ESITO_4, clic_bot: clic, cicli_bot: null });
        expect(c.clic[0].testo).toMatch(/^RIFIUTATO: il ciclo 1 è ancora aperto/);
    });
    it('ordini che il bot non mette in nessun ciclo restano nel registro («fuori dai cicli del bot»)', () => {
        const extra = [rigaDaVera({ _ms: 8000, _ordine: 'x', side: 'back', price: 3, size: 2, status: 'EXECUTION_COMPLETE', size_remaining: 0 })];
        const b = analizzaEsito({ ...ESITO_4, righe: [...RIGHE_4, ...extra], ordini: 9 });
        expect(b.registro.fuoriCiclo).toEqual(['o:x']);
        expect(b.registro.cicli.flatMap(c => c.ordini).length + b.registro.fuoriCiclo.length).toBe(b.ordini.length);
    });
});

// ---------------------------------------------------------------------------
// sezioni per fase: cicli, ordini, P&L; totali come oggi
// ---------------------------------------------------------------------------
describe('sezioni per fase sugli esiti VERI: nessun ciclo e nessun ordine perso, totali uguali a quelli di oggi', () => {
    for (const [nome, e, reg] of ESITI) {
        it(`${nome}: la somma delle fasi e' il totale di oggi (${reg})`, () => {
            const a = analizzaEsito(e);
            const fase = faseDi(reg);
            const metodo = metodoDi(e);
            const s = sezioniPerFase(a.registro, a.ordini, fase, fasiFisse(e.sport === 'tennis' ? 'tennis' : 'calcio'),
                metodo, e.esiti_mercati ?? null, a.aliquota);
            // le sezioni fisse ci sono sempre, in ordine
            const fisse = fasiFisse(e.sport === 'tennis' ? 'tennis' : 'calcio').map(f => f.id);
            expect(s.map(x => x.fase.id).filter(id => fisse.includes(id))).toEqual(fisse);
            // ogni ciclo in UNA sezione: quella in cui e' nato
            expect(s.flatMap(x => x.cicli).map(c => c.n).sort((p, q) => p - q)).toEqual(a.registro.cicli.map(c => c.n).sort((p, q) => p - q));
            for (const x of s) for (const c of x.cicli) expect(fase(c.daMs).id).toBe(x.fase.id);
            // ogni ordine in UNA sezione
            expect(s.reduce((t, x) => t + x.ordini, 0)).toBe(a.ordini.length);
            // il lordo delle fasi somma al lordo di oggi (lo stesso metodo del riquadro)
            const totale = metodo === 'cicli' ? a.cicliConto.lordo : a.regolato.lordo;
            expect(Math.round(s.reduce((t, x) => t + x.lordo, 0) * 100) / 100).toBe(totale);
        });
    }

    it('media under 35797769 (4 clic veri): ciclo 1 PRE-PARTITA chiuso nel 1° tempo, ciclo 2 nel 1° tempo, ciclo 3 nato all\'INTERVALLO e chiuso nel 2° tempo', () => {
        const a = analizzaEsito(MULTI);
        const fase = faseDi('35797769');
        const s = sezioniPerFase(a.registro, a.ordini, fase, fasiFisse('calcio'), 'cicli', MULTI.esiti_mercati ?? null, a.aliquota);
        expect(s.map(x => [x.fase.id, x.cicli.map(c => c.n), x.lordo])).toEqual([
            ['pre', [1], 0.02], ['1t', [2], 0.11], ['int', [3], 0.35], ['2t', [], 0],
        ]);
        expect(fase(a.registro.cicli[0].aMs!).id).toBe('1t');
        expect(fase(a.registro.cicli[2].aMs!).id).toBe('2t');
        expect(s.map(x => x.ordini)).toEqual([4, 2, 4, 0]);
    });
});
