// ============================================================================
// 07/10 - VERIFICATORE DELLA BARRA DEL REPLAY TENNIS (`tennisReplayVerificaBarra.ts`).
//
// SCOPRE DA SOLO le registrazioni tennis (nessun elenco a mano):
//   - ogni fixture `__fixtures__/replay_tennis_<evento>.json` (uscita del convertitore
//     vero su una registrazione vera) deve dare 0 incoerenze;
//   - ogni registrazione `_live_raw_tennis/<giorno>/<evento>/<evento>.raw.jsonl`
//     trovata risalendo dal frontend (la cartella e' fuori da git: in un checkout senza
//     registrazioni il controllo e' SALTATO con il motivo) deve avere la sua fixture,
//     altrimenti rosso con il comando per generarla.
// FALSIFICAZIONE: ogni difetto rimesso apposta deve far diventare rosso il verificatore
// (simbolo perso, simbolo spostato prima del suo istante, simbolo fuori registrazione,
// break / fine set / tie-break non coerenti col tabellone, set che scendono, passaggio
// in gioco perso, segmento di sospensione sbagliato).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Frame } from '@/lib/live';
import type { TennisScoreState } from '@/lib/tennis';
import { simboliTennis, type TennisReplayData, type TennisScoreRow } from '@/lib/tennisReplay';
import { verificaBarraTennis } from '@/lib/tennisReplayVerificaBarra';
import type { EsitoVerificaBarra } from '@/lib/replayVerificaBarra';

const QUI = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(QUI, '__fixtures__');
const PREFISSO = 'replay_tennis_';

function fixtureTennis(): string[] {
    return readdirSync(FIXTURES)
        .filter(f => f.startsWith(PREFISSO) && f.endsWith('.json'))
        .map(f => f.slice(PREFISSO.length, -'.json'.length))
        .sort();
}

/** `_live_raw_tennis` risalendo dalla cartella del test (worktree -> checkout principale). */
function cartellaRegistrazioni(): string | null {
    let d = QUI;
    for (let i = 0; i < 12; i++) {
        const c = join(d, '_live_raw_tennis');
        if (existsSync(c)) return c;
        const su = resolve(d, '..');
        if (su === d) break;
        d = su;
    }
    return null;
}

function registrazioniTennis(radice: string): string[] {
    const out = new Set<string>();
    for (const giorno of readdirSync(radice, { withFileTypes: true })) {
        if (!giorno.isDirectory()) continue;
        for (const ev of readdirSync(join(radice, giorno.name), { withFileTypes: true })) {
            if (ev.isDirectory() && existsSync(join(radice, giorno.name, ev.name, `${ev.name}.raw.jsonl`))) out.add(ev.name);
        }
    }
    return [...out].sort();
}

const carica = (ev: string): TennisReplayData =>
    JSON.parse(readFileSync(join(FIXTURES, `${PREFISSO}${ev}.json`), 'utf-8')) as TennisReplayData;
const codici = (e: EsitoVerificaBarra): string[] => e.incoerenze.map(r => r.codice);
const clona = (d: TennisReplayData): TennisReplayData => JSON.parse(JSON.stringify(d)) as TennisReplayData;

const EVENTI = fixtureTennis();
const RADICE_RAW = cartellaRegistrazioni();

describe('registrazioni tennis scoperte', () => {
    it('c\'e\' almeno una fixture tennis (altrimenti il test non verifica nulla)', () => {
        expect(EVENTI.length).toBeGreaterThan(0);
    });

    it.skipIf(RADICE_RAW == null)('ogni registrazione di _live_raw_tennis ha la sua fixture (saltato se la cartella, fuori da git, manca)', () => {
        const registrate = registrazioniTennis(RADICE_RAW as string);
        expect(registrate.length).toBeGreaterThan(0);
        const senza = registrate.filter(ev => !EVENTI.includes(ev));
        expect(senza, `registrazioni tennis senza fixture: ${senza.join(', ')}. Generale con `
            + 'python3 AUDIT_2026-10-07/replay_tennis/genera_fixture_frontend.py').toEqual([]);
    });
});

describe.each(EVENTI)('partita tennis %s', (ev) => {
    const dati = carica(ev);

    it('barra, simboli e tabellone coerenti: 0 incoerenze', () => {
        const e = verificaBarraTennis(dati);
        expect(e.incoerenze.map(r => `${r.codice}: ${r.spiegazione}`)).toEqual([]);
        expect(e.ok).toBe(true);
        expect(e.conteggi.frames).toBe(dati.frames.length);
        expect(e.conteggi.righePunteggio).toBe(dati.score_timeline.length);
        // tutti gli eventi di gioco hanno un simbolo
        const eventi = dati.score_timeline.reduce((s, r) => s + r.event_types.length, 0);
        const simboli = Object.entries(e.conteggi.simboli).filter(([k]) => k !== 'inplay').reduce((s, [, n]) => s + n, 0);
        expect(simboli).toBe(eventi);
        expect(e.rilievi.every(r => r.ambito === 'tennis')).toBe(true);
    });

    it('nessun testo parla di calcio d\'inizio', () => {
        const d = clona(dati);
        d.frames = d.frames.map(f => ({ ...f, inplay: false }));
        d.frames[5] = { ...d.frames[5], inplay: true };
        const e = verificaBarraTennis(d, { simboli: (...a) => simboliTennis(...a).filter(s => s.tipo !== 'inplay') });
        expect(codici(e)).toContain('TENNIS_INPLAY_SIMBOLO');
        expect(e.rilievi.some(r => /calcio/.test(r.spiegazione))).toBe(false);
    });

    // ---- falsificazione: ogni difetto rimesso -> rosso ----
    it('F1 simbolo di break perso dalla barra -> TENNIS_EVENTO_SENZA_SIMBOLO', () => {
        const e = verificaBarraTennis(dati, { simboli: (...a) => simboliTennis(...a).filter(s => s.tipo !== 'break') });
        expect(codici(e)).toContain('TENNIS_EVENTO_SENZA_SIMBOLO');
    });

    it('F2 simbolo spostato un passo prima del suo istante -> SIMBOLO_PRIMA_DELL_ISTANTE', () => {
        const e = verificaBarraTennis(dati, {
            simboli: (righe, passi, ...r) => {
                const span = Math.max(1, passi.length - 1);
                return simboliTennis(righe, passi, ...r).map(s => (s.tipo === 'set_end' && s.pctLeft > 0
                    ? { ...s, pctLeft: Math.round(s.pctLeft * span - 1) / span } : s));
            },
        });
        expect(codici(e)).toContain('SIMBOLO_PRIMA_DELL_ISTANTE');
    });

    it('F3 simbolo di un fatto fuori registrazione incollato a un estremo -> SIMBOLO_FUORI_REGISTRAZIONE', () => {
        const d = clona(dati);
        const ultimo = d.score_timeline[d.score_timeline.length - 1];
        ultimo.ts = '2026-12-31T23:59:59+00:00';
        const e = verificaBarraTennis(d);
        expect(codici(e)).toContain('SIMBOLO_FUORI_REGISTRAZIONE');
    });

    it('F4 simbolo inventato senza riga di punteggio -> TENNIS_SIMBOLO_SENZA_EVENTO', () => {
        const e = verificaBarraTennis(dati, {
            simboli: (...a) => {
                const s = simboliTennis(...a);
                const b = s.find(x => x.tipo === 'break');
                return b ? [...s, { ...b, tipo: 'tiebreak' as const }].sort((x, y) => (x.ts < y.ts ? -1 : x.ts > y.ts ? 1 : 0)) : s;
            },
        });
        expect(codici(e)).toContain('TENNIS_SIMBOLO_SENZA_EVENTO');
    });

    it('F5 break tolto dalla riga (game vinto da chi riceveva) -> TENNIS_BREAK_INCOERENTE', () => {
        const d = clona(dati);
        const r = d.score_timeline.find(x => x.event_types.includes('BREAK'));
        expect(r, 'la partita deve avere almeno un break').toBeTruthy();
        r!.event_types = r!.event_types.filter(x => x !== 'BREAK');
        expect(codici(verificaBarraTennis(d))).toContain('TENNIS_BREAK_INCOERENTE');
    });

    it('F6 break dichiarato su un game tenuto da chi serviva -> TENNIS_BREAK_INCOERENTE', () => {
        const d = clona(dati);
        const i = d.score_timeline.findIndex((x, k) => k > 0 && !x.event_types.includes('BREAK')
            && !d.score_timeline[k - 1].score.tiebreak
            && x.score.games.p1 + x.score.games.p2 === d.score_timeline[k - 1].score.games.p1 + d.score_timeline[k - 1].score.games.p2 + 1);
        expect(i, 'la partita deve avere almeno un game tenuto').toBeGreaterThan(0);
        d.score_timeline[i].event_types = [...d.score_timeline[i].event_types, 'BREAK'];
        expect(codici(verificaBarraTennis(d))).toContain('TENNIS_BREAK_INCOERENTE');
    });

    it('F7 fine set tolta -> TENNIS_FINE_SET_INCOERENTE; tie-break tolto -> TENNIS_TIEBREAK_INCOERENTE', () => {
        const d = clona(dati);
        const s = d.score_timeline.find(x => x.event_types.includes('SET_END'));
        expect(s).toBeTruthy();
        s!.event_types = s!.event_types.filter(x => x !== 'SET_END');
        expect(codici(verificaBarraTennis(d))).toContain('TENNIS_FINE_SET_INCOERENTE');
        const t = clona(dati);
        const tb = t.score_timeline.find(x => x.event_types.includes('TIEBREAK_START'));
        expect(tb).toBeTruthy();
        tb!.event_types = tb!.event_types.filter(x => x !== 'TIEBREAK_START');
        expect(codici(verificaBarraTennis(t))).toContain('TENNIS_TIEBREAK_INCOERENTE');
    });

    it('F8 set vinti che scendono -> TENNIS_SET_SCENDONO', () => {
        const d = clona(dati);
        const n = d.score_timeline.length;
        expect(d.score_timeline[n - 1].score.sets.p1 + d.score_timeline[n - 1].score.sets.p2).toBeGreaterThan(0);
        const r = d.score_timeline[n - 1];
        r.score = { ...r.score, sets: { p1: 0, p2: 0 } };
        expect(codici(verificaBarraTennis(d))).toContain('TENNIS_SET_SCENDONO');
    });

    it('sospensione del Match Odds nel dato: la pagina la disegna e il verificatore resta verde', () => {
        // il verificatore confronta la barra della pagina col suo oracolo: un frame sospeso
        // del Match Odds deve diventare un segmento, e il verificatore resta verde
        const d = clona(dati);
        const mo = d.markets.find(m => (m.market_type || '').toUpperCase() === 'MATCH_ODDS');
        expect(mo).toBeTruthy();
        const k = d.frames.findIndex(f => f.market_id === mo!.market_id);
        d.frames[k] = { ...d.frames[k], status: 'SUSPENDED' } as Frame;
        expect(verificaBarraTennis(d).ok).toBe(true);
    });
});

// ---- caso costruito: regole di dominio sulla carta ----
function stato(s1: number, s2: number, g1: number, g2: number, server: 1 | 2 | null, tiebreak = false): TennisScoreState {
    return {
        status: 'InPlay', sets: { p1: s1, p2: s2 }, games: { p1: g1, p2: g2 }, points: { p1: '0', p2: '0' },
        server, tiebreak, game_sequence: { p1: [], p2: [] }, service_breaks: { p1: 0, p2: 0 },
        current_set: s1 + s2 + 1, current_game: null, set_summary: null,
        pressure: null as unknown as TennisScoreState['pressure'], win_prob_p1: null, source: 'ips', updated_ms: null,
    };
}
const riga = (ts: string, score: TennisScoreState, ev: string[] = []): TennisScoreRow =>
    ({ ts, source: 'ips', score, event_types: ev, point: null });

function partitaCostruita(righe: TennisScoreRow[]): TennisReplayData {
    const frames: Frame[] = [];
    for (let i = 0; i < 30; i++) {
        frames.push({
            market_id: '1.1', ts: new Date(Date.UTC(2026, 6, 7, 12, 0, i * 10)).toISOString(), minute: null,
            inplay: true, status: 'OPEN', ladder: [],
        } as unknown as Frame);
    }
    return {
        event: { event_id: '1', competition_name: null, player1_name: 'A', player2_name: 'B', open_date: null, valuta: 'GBP' },
        markets: [{ market_id: '1.1', market_type: 'MATCH_ODDS', market_name: 'Match Odds', selections: [] } as unknown as TennisReplayData['markets'][number]],
        frames, score_timeline: righe,
    };
}

describe('regole di dominio su una partita costruita', () => {
    const t = (s: number) => new Date(Date.UTC(2026, 6, 7, 12, 0, s)).toISOString();

    it('game vinto da chi riceveva con BREAK: verde; senza: rosso', () => {
        const ok = partitaCostruita([riga(t(5), stato(0, 0, 0, 0, 1)), riga(t(25), stato(0, 0, 0, 1, 2), ['BREAK'])]);
        expect(verificaBarraTennis(ok).ok).toBe(true);
        const ko = partitaCostruita([riga(t(5), stato(0, 0, 0, 0, 1)), riga(t(25), stato(0, 0, 0, 1, 2))]);
        expect(codici(verificaBarraTennis(ko))).toEqual(['TENNIS_BREAK_INCOERENTE']);
    });

    it('game del tie-break vinto da chi riceveva: non e\' un break', () => {
        const d = partitaCostruita([riga(t(5), stato(0, 0, 6, 6, 1, true)), riga(t(25), stato(0, 1, 0, 0, 2), ['SET_END', 'SET_START'])]);
        expect(verificaBarraTennis(d).ok).toBe(true);
    });

    it('salto di piu\' game: nota, nessun break dedotto', () => {
        const d = partitaCostruita([riga(t(5), stato(0, 0, 0, 0, 1)), riga(t(25), stato(0, 0, 2, 1, 2), ['SALTO'])]);
        const e = verificaBarraTennis(d);
        expect(e.ok).toBe(true);
        expect(e.note.map(r => r.codice)).toContain('TENNIS_SALTO');
    });

    it('nessuna riga di punteggio: nota, non incoerenza', () => {
        const e = verificaBarraTennis(partitaCostruita([]));
        expect(e.ok).toBe(true);
        expect(e.note.map(r => r.codice)).toContain('PUNTEGGIO_ASSENTE');
    });
});
