// ============================================================================
// 07/10 - Il VERIFICATORE della barra sa diventare rosso? (falsificazione del
// verificatore stesso: "un test che non sa diventare rosso non certifica".)
//
// Per OGNI codice di incoerenza: si parte da una barra coerente (una partita vera
// della registrazione, o un replay sintetico minimo con le stesse chiavi e tipi del
// vero), si introduce quel difetto e si pretende quel codice. La parte generica
// (`verificaBarraGenerica`) lavora su una `BarraDaVerificare` costruita con le stesse
// funzioni della pagina; la parte calcio su un `ReplayData`.
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { Frame, Market, ReplayData, ScoreEvent } from '@/lib/live';
import { timelineEventMarkers } from '@/lib/replayTimelineEvents';
import {
    BUCKET_BARRA_MS, kickoffIndexSuPassi, kickoffTsDaFrame, idMercatiSospensione, passiBarra, sospesiPerPasso,
    verificaBarraGenerica, type BarraDaVerificare, type CodiceRilievo, type EstremiRegistrazione, type Rilievo,
} from '@/lib/replayVerificaBarra';
import { verificaBarraReplayCalcio, type FunzioniPagina } from '@/lib/replayVerificaBarraCalcio';
import { formattaReferto, rigaRilievo } from '@/lib/replayVerificaBarraTesto';
import { caricaPartita, eventiConFixture } from './__fixtures__/replayBarraTutte';
import { spostaSimboli } from './__fixtures__/replayBarraMutanti';

const incoerenti = (r: Rilievo[]): CodiceRilievo[] => r.filter(x => x.gravita !== 'nota').map(x => x.codice);
const tuttiCodici = (r: Rilievo[]): CodiceRilievo[] => r.map(x => x.codice);
const msDi = (ts: string): number => Date.parse(ts);
const iso = (ms: number): string => new Date(ms).toISOString().replace('Z', '+00:00');

// ---------------------------------------------------------------------------
// barra coerente da una partita VERA (la prima registrazione con sospensioni e simboli)
// ---------------------------------------------------------------------------
function barraVera(ev: string): { b: BarraDaVerificare; replay: ReplayData; estremi: EstremiRegistrazione } {
    const { replay, estremi } = caricaPartita(ev);
    const passi = passiBarra(replay.frames);
    const kickoffTs = kickoffTsDaFrame(replay.frames);
    const ids = idMercatiSospensione(replay.markets);
    const righe = [...replay.score_timeline].sort((a, c) => (a.ts < c.ts ? -1 : a.ts > c.ts ? 1 : 0));
    const b: BarraDaVerificare = {
        passi,
        simboli: timelineEventMarkers(righe, passi, replay.event.home_name, replay.event.away_name, Math.max(1, passi.length - 1)),
        frames: replay.frames,
        kickoffTs,
        kickoffIndex: kickoffIndexSuPassi(passi, kickoffTs),
        sospesi: sospesiPerPasso(passi, replay.frames, replay.markets),
        mercatiSospensione: ids.length > 0 ? ids : null,
        estremi,
    };
    return { b, replay, estremi };
}
const EV = eventiConFixture();
const EVENTO = EV.includes('35760084') ? '35760084' : EV[0];

describe('verificaBarraGenerica - barra coerente di una partita vera', () => {
    it('0 incoerenze (le note sono i buchi dichiarati)', () => {
        const { b } = barraVera(EVENTO);
        const r = verificaBarraGenerica(b);
        expect(incoerenti(r), formattaReferto(EVENTO, { rilievi: r, incoerenze: r, note: [], ok: false, conteggi: { passi: 0, frames: 0, simboli: {}, righePunteggio: 0, righeEvento: 0, buchi: 0 } })).toEqual([]);
        expect(r.every(x => x.codice === 'BUCO_REGISTRAZIONE' || x.codice === 'SOSPENSIONE_NON_VISIBILE')).toBe(true);
    });
});

describe('verificaBarraGenerica - ogni difetto introdotto deve essere visto', () => {
    const base = () => barraVera(EVENTO).b;
    const con = (m: (b: BarraDaVerificare) => Partial<BarraDaVerificare>): Rilievo[] => {
        const b = base();
        return verificaBarraGenerica({ ...b, ...m(b) });
    };

    it('NESSUN_FRAME: replay senza frame', () => {
        expect(incoerenti(con(() => ({ frames: [], passi: [] })))).toEqual(['NESSUN_FRAME']);
    });

    it('TS_NON_VALIDO: un frame con l\'orario illeggibile', () => {
        const r = con(b => ({ frames: [...b.frames, { ...b.frames[0], ts: 'non-una-data' }] }));
        expect(incoerenti(r)).toContain('TS_NON_VALIDO');
    });

    it('TS_ORDINE_STRINGHE: orari in formati diversi che il confronto di stringhe mette fuori tempo (la pagina li ordina come testo)', () => {
        const r = con(b => ({
            // 18:30 UTC scritto con fuso +02:00 e quindi "dopo" come testo di un frame delle 19:00 UTC
            frames: [...b.frames, { ...b.frames[0], ts: '2099-01-01T20:30:00.000+02:00' }, { ...b.frames[0], ts: '2099-01-01T19:00:00.000+00:00' }],
        }));
        expect(incoerenti(r)).toContain('TS_ORDINE_STRINGHE');
    });

    it('PASSI_NON_ORDINATI: due passi scambiati', () => {
        const r = con(b => {
            const p = [...b.passi];
            [p[10], p[11]] = [p[11], p[10]];
            return { passi: p };
        });
        expect(incoerenti(r)).toContain('PASSI_NON_ORDINATI');
    });

    it('ESTREMO_INIZIO: la barra non parte dal primo frame', () => {
        // senza gli estremi dichiarati: il confronto e' con il primo frame della registrazione
        expect(incoerenti(con(b => ({ passi: b.passi.slice(3), estremi: null })))).toContain('ESTREMO_INIZIO');
        expect(incoerenti(con(b => ({ passi: b.passi.slice(3) })))).toContain('ESTREMO_INIZIO');
    });

    it('ESTREMO_FINE: la barra finisce prima dell\'ultimo frame', () => {
        // senza gli estremi dichiarati: il confronto e' con l'ultimo frame della registrazione
        expect(incoerenti(con(b => ({ passi: b.passi.slice(0, -3), estremi: null })))).toContain('ESTREMO_FINE');
        expect(incoerenti(con(b => ({ passi: b.passi.slice(0, -3) })))).toContain('ESTREMO_FINE');
    });

    it('ESTREMO_INIZIO / ESTREMO_FINE rispetto agli estremi dichiarati dal server', () => {
        const { b } = barraVera(EVENTO);
        const est = b.estremi as EstremiRegistrazione;
        const prima = verificaBarraGenerica({ ...b, estremi: { ...est, ts_min: iso(msDi(est.ts_min as string) - 3600_000) } });
        const dopo = verificaBarraGenerica({ ...b, estremi: { ...est, ts_max: iso(msDi(est.ts_max as string) + 600_000) } });
        expect(incoerenti(prima)).toContain('ESTREMO_INIZIO');
        expect(incoerenti(dopo)).toContain('ESTREMO_FINE');
    });

    it('FRAME_FUORI_ESTREMI: frame fuori dagli estremi dichiarati', () => {
        const { b } = barraVera(EVENTO);
        const est = b.estremi as EstremiRegistrazione;
        const r = verificaBarraGenerica({ ...b, estremi: { ...est, ts_min: iso(msDi(est.ts_min as string) + 1800_000) } });
        expect(incoerenti(r)).toContain('FRAME_FUORI_ESTREMI');
    });

    it('SIMBOLO_FUORI_BARRA: posizione oltre il 100% o non numerica', () => {
        expect(incoerenti(con(b => ({ simboli: [{ ...b.simboli[0], pctLeft: 1.2 }, ...b.simboli.slice(1)] })))).toContain('SIMBOLO_FUORI_BARRA');
        expect(incoerenti(con(b => ({ simboli: [{ ...b.simboli[0], pctLeft: Number.NaN }, ...b.simboli.slice(1)] })))).toContain('SIMBOLO_FUORI_BARRA');
    });

    it('SIMBOLO_FUORI_REGISTRAZIONE: un simbolo di un fatto prima del primo frame o dopo l\'ultimo', () => {
        const { b } = barraVera(EVENTO);
        const primo = msDi(b.passi[0].ts), ultimo = msDi(b.passi[b.passi.length - 1].ts);
        const prima = verificaBarraGenerica({ ...b, simboli: [{ ...b.simboli[0], ts: iso(primo - 60_000), pctLeft: 0 }, ...b.simboli.slice(1)] });
        const dopo = verificaBarraGenerica({ ...b, simboli: [...b.simboli, { ...b.simboli[0], ts: iso(ultimo + 60_000), pctLeft: 1 }] });
        expect(incoerenti(prima)).toContain('SIMBOLO_FUORI_REGISTRAZIONE');
        expect(incoerenti(dopo)).toContain('SIMBOLO_FUORI_REGISTRAZIONE');
    });

    it('SIMBOLO_NON_ORDINATO: simboli alla rinfusa', () => {
        const r = con(b => ({ simboli: [b.simboli[1], b.simboli[0], ...b.simboli.slice(2)] }));
        expect(incoerenti(r)).toContain('SIMBOLO_NON_ORDINATO');
    });

    it('SIMBOLO_PRIMA_DELL_ISTANTE: i simboli un passo prima del loro istante', () => {
        const r = con(b => {
            const span = b.passi.length - 1;
            return { simboli: b.simboli.map(s => ({ ...s, pctLeft: Math.max(0, s.pctLeft - 1 / span) })) };
        });
        expect(incoerenti(r)).toContain('SIMBOLO_PRIMA_DELL_ISTANTE');
    });

    it('SIMBOLO_POSIZIONE: simboli un passo dopo, oppure tra due passi', () => {
        const dopo = con(b => {
            const span = b.passi.length - 1;
            return { simboli: b.simboli.map(s => ({ ...s, pctLeft: Math.min(1, s.pctLeft + 1 / span) })) };
        });
        expect(incoerenti(dopo)).toContain('SIMBOLO_POSIZIONE');
        const tra = con(b => {
            const span = b.passi.length - 1;
            return { simboli: [{ ...b.simboli[0], pctLeft: b.simboli[0].pctLeft + 0.4 / span }, ...b.simboli.slice(1)] };
        });
        expect(incoerenti(tra)).toContain('SIMBOLO_POSIZIONE');
    });

    it('KICKOFF_FUORI_POSTO: la lineetta un passo dopo, o un calcio d\'inizio che non e\' il primo frame in gioco', () => {
        expect(incoerenti(con(b => ({ kickoffIndex: b.kickoffIndex + 1 })))).toContain('KICKOFF_FUORI_POSTO');
        expect(incoerenti(con(b => ({ kickoffTs: b.passi[b.kickoffIndex + 5].ts })))).toContain('KICKOFF_FUORI_POSTO');
    });

    it('KICKOFF_DIVERSO_DA_META: il primo in gioco della registrazione e\' un altro', () => {
        const { b } = barraVera(EVENTO);
        const est = b.estremi as EstremiRegistrazione;
        const r = verificaBarraGenerica({ ...b, estremi: { ...est, inplay_from_ts: iso(msDi(est.inplay_from_ts as string) - 600_000) } });
        expect(incoerenti(r)).toContain('KICKOFF_DIVERSO_DA_META');
    });

    it('KICKOFF_DISCORDANTE: l\'inizio dichiarato dal feed (dentro la registrazione) e\' lontano dalla lineetta', () => {
        const { b } = barraVera(EVENTO);
        const k = msDi(b.kickoffTs as string);
        expect(incoerenti(verificaBarraGenerica({ ...b, inizioDichiarato: iso(k + 600_000) }))).toContain('KICKOFF_DISCORDANTE');
        // entro la tolleranza: nessun rilievo; fuori dalla registrazione: non si confronta
        expect(incoerenti(verificaBarraGenerica({ ...b, inizioDichiarato: iso(k + 20_000) }))).toEqual([]);
        expect(incoerenti(verificaBarraGenerica({ ...b, inizioDichiarato: iso(msDi(b.passi[0].ts) - 600_000) }))).toEqual([]);
    });

    it('KICKOFF_IN_RITARDO: un buco della registrazione proprio al fischio d\'inizio', () => {
        const { b } = barraVera(EVENTO);
        const k = msDi(b.kickoffTs as string);
        // un frame appena PRIMA del fischio nello stesso bucket da 10 s (il passo parte da li') e 4 minuti senza frame dopo
        const prima: Frame = { ...b.frames[0], ts: iso(k - 1), inplay: false, minute: null, ladder: {} };
        const frames = [prima, ...b.frames.filter(f => msDi(f.ts) < k + 1 || msDi(f.ts) > k + 240_000)];
        const passi = passiBarra(frames);
        const kt = kickoffTsDaFrame(frames);
        const r = verificaBarraGenerica({
            ...b, frames, passi, kickoffTs: kt, kickoffIndex: kickoffIndexSuPassi(passi, kt),
            sospesi: sospesiPerPasso(passi, frames, []), mercatiSospensione: null, simboli: [], estremi: null,
        });
        expect(tuttiCodici(r)).toContain('KICKOFF_IN_RITARDO');
        expect(r.find(x => x.codice === 'KICKOFF_IN_RITARDO')?.gravita).toBe('avviso');
    });

    it('SOSPENSIONE_LUNGHEZZA: segmenti e passi non corrispondono', () => {
        expect(incoerenti(con(b => ({ sospesi: b.sospesi.slice(1) })))).toContain('SOSPENSIONE_LUNGHEZZA');
    });

    it('SOSPENSIONE_DISCORDANTE: un segmento di sospensione che lo stato del mercato non dice (e viceversa)', () => {
        const { b } = barraVera(EVENTO);
        const idx = b.sospesi.findIndex(s => s);
        expect(idx, 'la partita scelta deve avere almeno un passo sospeso').toBeGreaterThanOrEqual(0);
        const tolto = [...b.sospesi]; tolto[idx] = false;
        const aggiunto = [...b.sospesi]; aggiunto[5] = true;
        expect(incoerenti(verificaBarraGenerica({ ...b, sospesi: tolto }))).toContain('SOSPENSIONE_DISCORDANTE');
        expect(incoerenti(verificaBarraGenerica({ ...b, sospesi: aggiunto }))).toContain('SOSPENSIONE_DISCORDANTE');
    });

    it('SOSPENSIONE_FUORI_ESTREMI: un segmento di sospensione fuori dagli estremi dichiarati', () => {
        const { b } = barraVera(EVENTO);
        const idx = b.sospesi.findIndex(s => s);
        const est = b.estremi as EstremiRegistrazione;
        const r = verificaBarraGenerica({ ...b, estremi: { ...est, ts_max: iso(msDi(b.passi[idx].ts) - 1000) } });
        expect(incoerenti(r)).toContain('SOSPENSIONE_FUORI_ESTREMI');
    });

    it('BUCO_REGISTRAZIONE (nota): un buco di 3 minuti in gioco e uno di 15 minuti prima del calcio d\'inizio sono dichiarati, non sono incoerenze', () => {
        const { b } = barraVera(EVENTO);
        const k = msDi(b.kickoffTs as string);
        const frames = b.frames.filter(f => msDi(f.ts) < k + 600_000 || msDi(f.ts) > k + 600_000 + 180_000)
            .filter(f => msDi(f.ts) < k - 1800_000 || msDi(f.ts) > k - 900_000);
        const passi = passiBarra(frames);
        const kt = kickoffTsDaFrame(frames);
        const r = verificaBarraGenerica({
            ...b, frames, passi, kickoffTs: kt, kickoffIndex: kickoffIndexSuPassi(passi, kt),
            sospesi: sospesiPerPasso(passi, frames, []), mercatiSospensione: null, simboli: [], estremi: null,
        });
        const buchi = r.filter(x => x.codice === 'BUCO_REGISTRAZIONE');
        expect(buchi.length).toBeGreaterThanOrEqual(2);
        expect(buchi.every(x => x.gravita === 'nota')).toBe(true);
        expect(incoerenti(r)).toEqual([]);
        expect(buchi.map(x => x.spiegazione).join(' ')).toContain('pre-match');
    });

    it('INIZIO_IN_CORSO (nota): registrazione che comincia a partita in corso', () => {
        const { b } = barraVera(EVENTO);
        const tagli = b.frames.filter(f => msDi(f.ts) >= msDi(b.passi[Math.floor(b.passi.length * 0.7)].ts));
        const passi = passiBarra(tagli);
        const kt = kickoffTsDaFrame(tagli);
        const r = verificaBarraGenerica({
            ...b, frames: tagli, passi, kickoffTs: kt, kickoffIndex: kickoffIndexSuPassi(passi, kt),
            sospesi: sospesiPerPasso(passi, tagli, []), mercatiSospensione: null, simboli: [], estremi: null,
        });
        expect(r.find(x => x.codice === 'INIZIO_IN_CORSO')?.gravita).toBe('nota');
        expect(incoerenti(r)).toEqual([]);
    });

    it('SOSPENSIONE_NON_VISIBILE (nota): una sospensione di 4 secondi cade fra due passi', () => {
        const t0 = msDi('2026-10-07T19:00:00.000+00:00');
        const frames: Frame[] = [];
        for (let i = 0; i < 40; i++) {
            const t = t0 + i * 10_000;
            frames.push({ market_id: '1.1', ts: iso(t), minute: i < 6 ? 0 : Math.floor(i / 6), inplay: i >= 6, status: 'OPEN', ladder: {} });
        }
        // sospeso da 19:02:03 a 19:02:07: nessun passo (19:02:00 e 19:02:10) ci cade dentro
        frames.push({ market_id: '1.1', ts: iso(t0 + 123_000), minute: 2, inplay: true, status: 'SUSPENDED', ladder: {} });
        frames.push({ market_id: '1.1', ts: iso(t0 + 127_000), minute: 2, inplay: true, status: 'OPEN', ladder: {} });
        frames.sort((a, c) => (a.ts < c.ts ? -1 : 1));
        const passi = passiBarra(frames);
        const kt = kickoffTsDaFrame(frames);
        const r = verificaBarraGenerica({
            passi, simboli: [], frames, kickoffTs: kt, kickoffIndex: kickoffIndexSuPassi(passi, kt),
            sospesi: sospesiPerPasso(passi, frames, [{ market_id: '1.1', market_type: 'MATCH_ODDS' }]), mercatiSospensione: ['1.1'],
        });
        expect(r.find(x => x.codice === 'SOSPENSIONE_NON_VISIBILE')?.gravita).toBe('nota');
        expect(incoerenti(r)).toEqual([]);
    });
});

// ---------------------------------------------------------------------------
// PARTE CALCIO su un replay sintetico minimo: stesse chiavi e tipi del vero
// ---------------------------------------------------------------------------
const T0 = msDi('2026-10-07T19:00:00.000+00:00');
const MERCATO: Market = {
    market_id: '1.1', market_type: 'MATCH_ODDS', market_name: 'MATCH_ODDS', sort_priority: 1,
    selections: [{ selection_id: 1, name: 'Casa', sort_priority: 1 }, { selection_id: 2, name: 'Ospiti', sort_priority: 2 }],
};
function frameSintetici(n = 120): Frame[] {
    const out: Frame[] = [];
    for (let i = 0; i < n; i++) {
        out.push({ market_id: '1.1', ts: iso(T0 + i * 10_000), minute: Math.floor(i / 6), inplay: i >= 6, status: 'OPEN', ladder: {} });
    }
    return out;
}
const riga = (secondi: number, h: number | null, a: number | null, source = 'betfair', extra: Partial<ScoreEvent> = {}): ScoreEvent => ({
    ts: iso(T0 + secondi * 1000), minute: Math.floor(secondi / 60), score_home: h, score_away: a, event_type: null, source,
    payload: { score: { home: { numberOfCorners: 0, numberOfYellowCards: 0, numberOfRedCards: 0 }, away: { numberOfCorners: 0, numberOfYellowCards: 0, numberOfRedCards: 0 } } },
    ...extra,
});
const rigaEvento = (secondi: number, tipo: string, team: 'home' | 'away' | null): ScoreEvent => ({
    ts: iso(T0 + secondi * 1000), minute: Math.floor(secondi / 60), score_home: null, score_away: null, event_type: tipo, source: 'betfair',
    payload: { team, team_name: team, type: tipo, minute: Math.floor(secondi / 60) },
});
const conConteggi = (r: ScoreEvent, c: { hc?: number; ac?: number; hy?: number; ay?: number }): ScoreEvent => ({
    ...r,
    payload: { score: {
        home: { numberOfCorners: c.hc ?? 0, numberOfYellowCards: c.hy ?? 0, numberOfRedCards: 0 },
        away: { numberOfCorners: c.ac ?? 0, numberOfYellowCards: c.ay ?? 0, numberOfRedCards: 0 },
    } },
});
const replay = (righe: ScoreEvent[], frames: Frame[] = frameSintetici()): ReplayData => ({
    event: { event_id: '1', fixture_id: null, league_name: 'Lega', home_name: 'Casa', away_name: 'Ospiti', open_date: iso(T0), status: 'UPLOADED' },
    markets: [MERCATO], frames, score_timeline: righe,
});
const verifica = (r: ReplayData, funzioni?: Partial<FunzioniPagina>) => verificaBarraReplayCalcio(r, { funzioni });

describe('verificaBarraReplayCalcio - replay sintetico', () => {
    const buona = (): ScoreEvent[] => [
        riga(0, 0, 0), riga(120, 0, 0), rigaEvento(300, 'Goal', 'home'), riga(302, 1, 0), riga(600, 1, 0), rigaEvento(900, 'FirstHalfEnd', null), riga(1100, 1, 0),
    ];

    it('partita coerente (gol, riga-evento senza punteggio, intervallo): 0 incoerenze', () => {
        const e = verifica(replay(buona()));
        expect(e.incoerenze, formattaReferto('sintetico', e)).toEqual([]);
        expect(e.conteggi.simboli.goal).toBe(1);
    });

    it('PUNTEGGIO_ASSENTE (nota): nessuna riga con il punteggio', () => {
        const e = verifica(replay([rigaEvento(60, 'KickOff', null)]));
        expect(e.note.map(x => x.codice)).toContain('PUNTEGGIO_ASSENTE');
        expect(e.ok, formattaReferto('senza punteggio', e)).toBe(true);
    });

    it('TABELLONE_SCENDE (errore): due fonti discordanti -> il tabellone va avanti e indietro', () => {
        const righe = [riga(0, 0, 0), riga(300, 1, 0, 'betfair'), riga(310, 0, 0, 'api_football'), riga(320, 1, 0, 'api_football')];
        const e = verifica(replay(righe));
        expect(e.incoerenze.map(x => x.codice)).toContain('TABELLONE_SCENDE');
        expect(e.incoerenze.find(x => x.codice === 'TABELLONE_SCENDE')?.spiegazione).toContain('api_football');
    });

    it('TABELLONE_CORREZIONE_FEED (nota, VAR): la STESSA fonte corregge il punteggio -> non e\' incoerenza; il simbolo del gol annullato e\' una nota', () => {
        const righe = [riga(0, 0, 0), rigaEvento(298, 'Goal', 'home'), riga(300, 1, 0), riga(400, 0, 0)];
        const e = verifica(replay(righe));
        expect(e.note.map(x => x.codice)).toContain('TABELLONE_CORREZIONE_FEED');
        expect(e.incoerenze.map(x => x.codice)).not.toContain('TABELLONE_SCENDE');
        expect(e.incoerenze, formattaReferto('var', e)).toEqual([]);
    });

    it('GOL_ANNULLATO (nota): un Goal discreto mai arrivato al punteggio ma con il punteggio corretto subito dopo', () => {
        const righe = [riga(0, 0, 0), riga(200, 1, 0), riga(240, 0, 0), rigaEvento(210, 'Goal', 'away')];
        const e = verifica(replay(righe));
        expect(e.note.map(x => x.codice)).toContain('GOL_ANNULLATO');
    });

    it('SIMBOLO_GOL_SENZA_AUMENTO (errore): un Goal discreto senza nessun aumento del punteggio e senza correzione', () => {
        const righe = [riga(0, 0, 0), rigaEvento(300, 'Goal', 'home'), riga(600, 0, 0), riga(900, 0, 0)];
        const e = verifica(replay(righe));
        expect(e.incoerenze.map(x => x.codice)).toContain('SIMBOLO_GOL_SENZA_AUMENTO');
    });

    it('GOL_SENZA_SIMBOLO (errore): il punteggio sale ma la funzione dei simboli non disegna il gol', () => {
        const senzaGol: FunzioniPagina['timelineEventMarkers'] = (a, b, c, d, f) => timelineEventMarkers(a, b, c, d, f).filter(m => m.kind !== 'goal');
        const e = verifica(replay(buona()), { timelineEventMarkers: senzaGol });
        expect(e.incoerenze.map(x => x.codice)).toContain('GOL_SENZA_SIMBOLO');
    });

    it('GOL_SQUADRA_DIVERSA (avviso): il simbolo del gol e\' dell\'altra squadra rispetto al punteggio', () => {
        const scambia: FunzioniPagina['timelineEventMarkers'] = (a, b, c, d, f) =>
            timelineEventMarkers(a, b, c, d, f).map(m => (m.kind === 'goal' ? { ...m, team: m.team === 'home' ? 'away' : 'home' } : m));
        const e = verifica(replay(buona()), { timelineEventMarkers: scambia });
        expect(e.incoerenze.map(x => x.codice)).toContain('GOL_SQUADRA_DIVERSA');
        expect(e.incoerenze.find(x => x.codice === 'GOL_SQUADRA_DIVERSA')?.gravita).toBe('avviso');
    });

    it('TABELLONE_DIVERSO_DAL_FEED e TABELLONE_FINALE: il tabellone non segue le righe del punteggio', () => {
        const fermo: FunzioniPagina['punteggioAlTs'] = () => ({ home: 0, away: 0, minute: null });
        const e = verifica(replay(buona()), { punteggioAlTs: fermo });
        const c = e.incoerenze.map(x => x.codice);
        expect(c).toContain('TABELLONE_DIVERSO_DAL_FEED');
        expect(c).toContain('TABELLONE_FINALE');
    });

    it('MOTORE_PUNTEGGIO: il motore opportunita\' vede un punteggio diverso dal feed', () => {
        const sbagliato: FunzioniPagina['buildSnapshots'] = (r, b) => buildSnapshotsFinti(r, b);
        const e = verifica(replay(buona()), { buildSnapshots: sbagliato });
        expect(e.incoerenze.map(x => x.codice)).toContain('MOTORE_PUNTEGGIO');
    });

    it('FUNZIONE_PAGINA_ERRORE: una funzione della pagina che lancia un errore e\' un\'incoerenza (una sola volta), non un crash del verificatore', () => {
        const scoppia = (nome: string) => () => { throw new Error(`${nome} scoppia`); };
        const a = verifica(replay(buona()), { punteggioAlTs: scoppia('punteggioAlTs') as FunzioniPagina['punteggioAlTs'] });
        const b = verifica(replay(buona()), { timelineEventMarkers: scoppia('simboli') as FunzioniPagina['timelineEventMarkers'] });
        const c = verifica(replay(buona()), { buildSnapshots: scoppia('motore') as FunzioniPagina['buildSnapshots'] });
        for (const [e, testo] of [[a, 'punteggioAlTs scoppia'], [b, 'simboli scoppia'], [c, 'motore scoppia']] as const) {
            const r = e.incoerenze.filter(x => x.codice === 'FUNZIONE_PAGINA_ERRORE');
            expect(r, formattaReferto('errore', e)).toHaveLength(1);
            expect(r[0].spiegazione).toContain(testo);
            expect(e.ok).toBe(false);
        }
    });

    it('ANGOLI_DIVERSI (errore): il punteggio conta 3 angoli, la barra ne mostra 1 (la funzione dei simboli ne perde due)', () => {
        const righe = [conConteggi(riga(0, 0, 0), {}), conConteggi(riga(300, 0, 0), { hc: 1 }), conConteggi(riga(600, 0, 0), { hc: 3 })];
        // la funzione vera conta un simbolo per unita' (salto di 2 fra due righe = 2 simboli): coerente
        expect(verifica(replay(righe)).incoerenze).toEqual([]);
        const unoSolo: FunzioniPagina['timelineEventMarkers'] = (a, b, c, d, f) => {
            const m = timelineEventMarkers(a, b, c, d, f);
            const primo = m.findIndex(x => x.kind === 'corner');
            return m.filter((x, i) => x.kind !== 'corner' || i === primo);
        };
        const e = verifica(replay(righe), { timelineEventMarkers: unoSolo });
        const a = e.incoerenze.find(x => x.codice === 'ANGOLI_DIVERSI');
        expect(a?.gravita).toBe('errore');
        expect(a?.spiegazione).toContain('conta 3');
    });

    it('CARTELLINI_DIVERSI (avviso con timeline discreta): il punteggio conta 2 gialli, la timeline ne ha 1', () => {
        const righe = [
            conConteggi(riga(0, 0, 0), {}), rigaEvento(300, 'YellowCard', 'home'), conConteggi(riga(302, 0, 0), { hy: 1 }),
            conConteggi(riga(900, 0, 0), { hy: 2 }),
        ];
        const e = verifica(replay(righe));
        const a = e.incoerenze.find(x => x.codice === 'CARTELLINI_DIVERSI');
        expect(a?.gravita).toBe('avviso');
    });

    it('CONTEGGI_ASSENTI (nota): il feed non porta i conteggi dei cartellini', () => {
        const senza = (r: ScoreEvent): ScoreEvent => ({ ...r, payload: { score: { home: {}, away: {} } } });
        const e = verifica(replay([senza(riga(0, 0, 0)), senza(riga(300, 0, 0))]));
        expect(e.note.map(x => x.codice)).toContain('CONTEGGI_ASSENTI');
    });

    it('un fatto fuori registrazione non si pretende: righe del punteggio prima del primo frame non danno GOL_SENZA_SIMBOLO', () => {
        // registrazione che parte a partita in corso: il gol del 1-0 e' avvenuto PRIMA del primo frame
        const righe = [riga(-1000, 0, 0), riga(-600, 1, 0), riga(300, 1, 0)];
        const e = verifica(replay(righe));
        expect(e.incoerenze, formattaReferto('fuori', e)).toEqual([]);
    });
});

// motore opportunita' difettoso: sempre 0-0
import { buildSnapshots } from '@/lib/opportunities/snapshot';
function buildSnapshotsFinti(r: ReplayData, b?: number) {
    return buildSnapshots(r, b).map(s => ({ ...s, scoreHome: 0, scoreAway: 0 }));
}

describe('formato del referto', () => {
    it('ogni rilievo ha codice, gravita\', spiegazione per il trader e un\'etichetta nel referto', () => {
        const e = verifica(replay([riga(0, 0, 0), riga(300, 1, 0, 'betfair'), riga(310, 0, 0, 'api_football')]));
        const r = e.incoerenze[0];
        expect(r.spiegazione.length).toBeGreaterThan(20);
        expect(rigaRilievo(r)).toContain(`[ERRORE] ${r.codice}`);
        expect(formattaReferto('x', e)).toContain('INCOERENTE x');
        expect(BUCKET_BARRA_MS).toBe(10_000);
    });
});

describe('falsificazione dei simboli spostati (funzione della pagina sostituita)', () => {
    it('simboli un passo prima o dopo: SIMBOLO_PRIMA_DELL_ISTANTE / SIMBOLO_POSIZIONE sulla partita vera', () => {
        const { replay: rep, estremi } = caricaPartita(EVENTO);
        const prima = verificaBarraReplayCalcio(rep, { estremi, funzioni: { timelineEventMarkers: spostaSimboli(timelineEventMarkers, -1) } });
        const dopo = verificaBarraReplayCalcio(rep, { estremi, funzioni: { timelineEventMarkers: spostaSimboli(timelineEventMarkers, +1) } });
        expect(prima.incoerenze.map(x => x.codice)).toContain('SIMBOLO_PRIMA_DELL_ISTANTE');
        expect(dopo.incoerenze.map(x => x.codice)).toContain('SIMBOLO_POSIZIONE');
    });
});
