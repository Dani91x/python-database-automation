// ============================================================================
// 08/10 (cantiere 13) - LE 13 PARTITE INCOERENTI DEL DATABASE: i CASI riprodotti
// qui con i formati veri (righe di `score_timeline` e frame come le da' la pagina,
// fixture delle registrazioni del banco) e la CLASSE di ciascuno:
//   (a) falso positivo del VERIFICATORE -> si corregge il verificatore
//   (b) difetto della PAGINA            -> si corregge la pagina
//   (c) difetto dei DATI registrati     -> nessuna correzione a mano: il rilievo resta
//       un'incoerenza ma DICHIARATA "per dati" con il motivo (campo `perDati`),
//       visibile nel referto e nell'avviso della pagina.
//
// Casi (sul PC, `AUDIT_2026-10-07/certificazione_db/verifica_barra_tutte.txt`):
//   A1 SIMBOLO_GOL_SENZA_AUMENTO dopo una correzione VAR della STESSA squadra (35787218,
//      35777617, 35768297, 35768365): il gol vero dopo il gol annullato riporta il
//      punteggio dove era gia' stato; il verificatore contava i gol attesi contro il
//      MASSIMO visto e non lo pretendeva -> simbolo "senza aumento". Classe (a).
//   A2 SIMBOLO_GOL_SENZA_AUMENTO a registrazione appena iniziata (35812264): il punteggio
//      sale prima del primo frame, il Goal della timeline arriva dentro la barra entro 3
//      minuti. Classe (a).
//   C1 KICKOFF_DISCORDANTE (35817305, 35817978, 35817332, 35828026, 35794996, 35796477):
//      confronto fra DUE DATI registrati (flag in gioco del mercato e KickOff del feed);
//      la pagina e' controllata da KICKOFF_FUORI_POSTO. Classe (c) con il motivo
//      (buco della registrazione / flag in gioco discorde).
//   C2 CARTELLINI_DIVERSI con la timeline discreta (35812264, 35823368, 35804974,
//      35787218): se la barra disegna ESATTAMENTE i cartellini della timeline, la
//      differenza e' fra le due fonti del feed (timeline e conteggi). Classe (c). Se la
//      barra ne perde o ne aggiunge rispetto alla timeline, NON e' "per dati".
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { Frame, Market, ReplayData, ScoreEvent } from '@/lib/live';
import { kindDiTipo, timelineEventMarkers } from '@/lib/replayTimelineEvents';
import { verificaBarraReplayCalcio, type FunzioniPagina } from '@/lib/replayVerificaBarraCalcio';
import { formattaReferto } from '@/lib/replayVerificaBarraTesto';
import type { EsitoVerificaBarra, EstremiRegistrazione } from '@/lib/replayVerificaBarra';
import { caricaPartita, eventiConFixture } from './__fixtures__/replayBarraTutte';

const msDi = (ts: string): number => Date.parse(ts);
const iso = (ms: number): string => new Date(ms).toISOString().replace('Z', '+00:00');
const codici = (e: EsitoVerificaBarra): string[] => e.incoerenze.map(r => r.codice);
const perTs = (a: ScoreEvent, b: ScoreEvent): number => msDi(a.ts) - msDi(b.ts);
const verifica = (replay: ReplayData, estremi: EstremiRegistrazione | null = null, funzioni?: Partial<FunzioniPagina>) =>
    verificaBarraReplayCalcio(replay, { estremi, funzioni });

// ---------------------------------------------------------------------------
// replay sintetico minimo: stesse chiavi e tipi del vero (come `replayVerificaBarra.test.ts`)
// ---------------------------------------------------------------------------
const T0 = msDi('2026-07-02T19:00:00.000+00:00');
const MERCATO: Market = {
    market_id: '1.1', market_type: 'MATCH_ODDS', market_name: 'MATCH_ODDS', sort_priority: 1,
    selections: [{ selection_id: 1, name: 'Casa', sort_priority: 1 }, { selection_id: 2, name: 'Ospiti', sort_priority: 2 }],
};
/** frame ogni 10 s per `n` passi; in gioco dal passo `daInGioco`; minuto = (passo - daInGioco) / 6 */
function frameSintetici(n = 400, daInGioco = 6, primoMinuto = 0): Frame[] {
    const out: Frame[] = [];
    for (let i = 0; i < n; i++) {
        const m = i < daInGioco ? null : primoMinuto + Math.floor((i - daInGioco) / 6);
        out.push({ market_id: '1.1', ts: iso(T0 + i * 10_000), minute: m, inplay: i >= daInGioco, status: 'OPEN', ladder: {} });
    }
    return out;
}
const CONTEGGI_ZERO = { score: { home: { numberOfCorners: 0, numberOfYellowCards: 0, numberOfRedCards: 0 }, away: { numberOfCorners: 0, numberOfYellowCards: 0, numberOfRedCards: 0 } } };
/** riga del punteggio a `secondi` da T0; il minuto e' quello dell'orologio (inizio a 60 s) + `minutoBase` */
const riga = (secondi: number, h: number, a: number, source = 'betfair', minutoBase = 0): ScoreEvent => ({
    ts: iso(T0 + secondi * 1000), minute: minutoBase + Math.max(0, Math.floor((secondi - 60) / 60)), score_home: h, score_away: a,
    event_type: null, source, payload: CONTEGGI_ZERO,
});
const rigaEvento = (secondi: number, tipo: string, team: 'home' | 'away' | null, minutoBase = 0): ScoreEvent => {
    const minuto = minutoBase + Math.max(0, Math.floor((secondi - 60) / 60));
    return {
        ts: iso(T0 + secondi * 1000), minute: minuto, score_home: null, score_away: null, event_type: tipo, source: 'betfair',
        payload: { team, team_name: team, type: tipo, minute: minuto },
    };
};
const replaySintetico = (righe: ScoreEvent[], frames: Frame[] = frameSintetici()): ReplayData => ({
    event: { event_id: '1', fixture_id: null, league_name: 'Lega', home_name: 'Casa', away_name: 'Ospiti', open_date: iso(T0), status: 'UPLOADED' },
    markets: [MERCATO], frames, score_timeline: righe,
});

// ---------------------------------------------------------------------------
// A1 - gol vero DOPO un gol annullato dal VAR della stessa squadra
// ---------------------------------------------------------------------------
describe('A1 (classe a): gol vero dopo un gol annullato dal VAR della stessa squadra', () => {
    // come 35787218 Argentina - Egypt: 0-1, gol annullato 0-2 -> 0-1 (correzione del feed),
    // poi il gol vero del 0-2 sette minuti dopo, con il suo Goal nella timeline
    const var_ = (): ScoreEvent[] => [
        riga(0, 0, 0), riga(60, 0, 0),
        rigaEvento(600, 'Goal', 'away'), riga(605, 0, 1),
        rigaEvento(1500, 'Goal', 'away'), riga(1505, 0, 2),
        riga(1620, 0, 1), // correzione VAR (stessa fonte): il tabellone scende
        rigaEvento(2040, 'Goal', 'away'), riga(2046, 0, 2), // il gol VERO: il punteggio torna a 0-2
        riga(3000, 0, 2),
    ];

    it('la pagina disegna 3 gol e il tabellone segue il feed; il verificatore non segnala il gol vero', () => {
        const e = verifica(replaySintetico(var_()));
        expect(e.conteggi.simboli.goal).toBe(3);
        expect(e.note.map(x => x.codice)).toContain('TABELLONE_CORREZIONE_FEED');
        expect(e.incoerenze, formattaReferto('A1 sintetico', e)).toEqual([]);
    });

    it('lo stesso con la squadra di casa e due correzioni (come 35768297 Portugal - Croatia)', () => {
        const righe = [
            riga(0, 0, 0), riga(60, 0, 0),
            rigaEvento(600, 'Goal', 'away'), riga(605, 0, 1),
            rigaEvento(900, 'Goal', 'away'), riga(905, 0, 2), riga(1000, 0, 1), // annullato (ospiti)
            rigaEvento(1300, 'Goal', 'home'), riga(1305, 1, 1), riga(1420, 0, 1), // annullato (casa)
            rigaEvento(1800, 'Goal', 'home'), riga(1806, 1, 1), // gol vero della casa: torna a 1-1
            riga(2600, 1, 1),
        ];
        const e = verifica(replaySintetico(righe));
        expect(e.conteggi.simboli.goal).toBe(4);
        expect(e.incoerenze, formattaReferto('A1 due correzioni', e)).toEqual([]);
    });

    it('sulla partita VERA del banco con un gol annullato inserito 8 minuti prima di un gol vero: 0 incoerenze', () => {
        const ev = eventiConFixture().includes('35760084') ? '35760084' : eventiConFixture()[0];
        const { replay, estremi } = caricaPartita(ev);
        const righe = [...replay.score_timeline].sort(perTs);
        const conPunteggio = righe.filter(r => r.score_home != null && r.score_away != null);
        // l'ultimo gol con almeno 10 minuti di punteggio fermo prima
        let g = -1;
        for (let i = conPunteggio.length - 1; i > 0; i--) {
            const p = conPunteggio[i - 1], c = conPunteggio[i];
            const sale = (c.score_home ?? 0) > (p.score_home ?? 0) || (c.score_away ?? 0) > (p.score_away ?? 0);
            if (!sale) continue;
            const ultimoCambio = conPunteggio.slice(0, i).reverse().find(r => r.score_home !== c.score_home || r.score_away !== c.score_away);
            const fermoDa = conPunteggio.slice(0, i).filter(r => r.score_home === p.score_home && r.score_away === p.score_away)[0];
            if (ultimoCambio && fermoDa && msDi(c.ts) - msDi(fermoDa.ts) >= 600_000) { g = i; break; }
        }
        expect(g, 'serve un gol con 10 minuti di punteggio fermo prima').toBeGreaterThan(0);
        const p = conPunteggio[g - 1], c = conPunteggio[g];
        const casa = (c.score_home ?? 0) > (p.score_home ?? 0);
        const T = msDi(c.ts);
        // il gol annullato: riga del punteggio con +1 (stessa fonte, stesse chiavi del vero), Goal della timeline,
        // poi la correzione del feed che riporta il punteggio di prima
        const sorella = (ms: number, h: number | null, a: number | null): ScoreEvent => ({ ...p, ts: iso(ms), score_home: h, score_away: a });
        const minutoA = (ms: number): number | null => [...righe].filter(r => r.score_home != null && msDi(r.ts) <= ms).pop()?.minute ?? null;
        const goalVero = righe.find(r => kindDiTipo(r.event_type) === 'goal' && Math.abs(msDi(r.ts) - T) <= 180_000);
        expect(goalVero, 'il gol vero deve avere il suo Goal nella timeline').toBeTruthy();
        const goalAnnullato: ScoreEvent = {
            ...(goalVero as ScoreEvent), ts: iso(T - 482_000), minute: minutoA(T - 482_000),
            payload: { ...((goalVero as ScoreEvent).payload as Record<string, unknown>), minute: minutoA(T - 482_000) },
        };
        const conVar: ReplayData = {
            ...replay,
            score_timeline: [
                ...replay.score_timeline,
                goalAnnullato,
                sorella(T - 480_000, (p.score_home ?? 0) + (casa ? 1 : 0), (p.score_away ?? 0) + (casa ? 0 : 1)),
                sorella(T - 360_000, p.score_home, p.score_away),
            ],
        };
        const prima = verifica(replay, estremi);
        expect(prima.incoerenze, formattaReferto(`${ev} originale`, prima)).toEqual([]);
        const e = verifica(conVar, estremi);
        expect(e.note.map(x => x.codice)).toContain('TABELLONE_CORREZIONE_FEED');
        expect(e.incoerenze, formattaReferto(`${ev} con VAR`, e)).toEqual([]);
        expect(e.conteggi.simboli.goal).toBe((prima.conteggi.simboli.goal ?? 0) + 1);
    });

    it('un VAR che RIPRISTINA il gol (sale, scende, risale, UN solo Goal) resta coerente e la barra ha un solo gol', () => {
        const righe = [riga(0, 0, 0), riga(60, 0, 0), rigaEvento(600, 'Goal', 'home'), riga(605, 1, 0), riga(700, 0, 0), riga(820, 1, 0), riga(2000, 1, 0)];
        const e = verifica(replaySintetico(righe));
        expect(e.conteggi.simboli.goal).toBe(1);
        expect(e.incoerenze, formattaReferto('ripristino', e)).toEqual([]);
    });

    it('NON nasconde un simbolo in piu\': due Goal per UNA risalita -> uno resta SIMBOLO_GOL_SENZA_AUMENTO', () => {
        const righe = [
            riga(0, 0, 0), riga(60, 0, 0),
            rigaEvento(600, 'Goal', 'away'), riga(605, 0, 1), riga(700, 0, 0), // annullato
            rigaEvento(1500, 'Goal', 'away'), riga(1505, 0, 1), // gol vero
            rigaEvento(1560, 'Goal', 'away'), // simbolo in piu' (nessun gol)
            riga(2600, 0, 1),
        ];
        const e = verifica(replaySintetico(righe));
        expect(codici(e).filter(c => c === 'SIMBOLO_GOL_SENZA_AUMENTO')).toHaveLength(1);
    });

    it('NON nasconde un simbolo dell\'altra squadra: la risalita degli ospiti non giustifica un Goal della casa', () => {
        const righe = [
            riga(0, 0, 0), riga(60, 0, 0),
            rigaEvento(600, 'Goal', 'away'), riga(605, 0, 1), riga(700, 0, 0),
            rigaEvento(1500, 'Goal', 'home'), riga(1505, 0, 1), // il Goal e' della casa, risalgono gli ospiti
            riga(2600, 0, 1),
        ];
        const e = verifica(replaySintetico(righe));
        expect(codici(e)).toContain('SIMBOLO_GOL_SENZA_AUMENTO');
    });

    it('NON confonde il ritardo di un\'altra fonte con un gol: risalita fra fonti diverse -> resta SIMBOLO_GOL_SENZA_AUMENTO (e TABELLONE_SCENDE)', () => {
        const righe = [
            riga(0, 0, 0), riga(60, 0, 0),
            rigaEvento(600, 'Goal', 'home'), riga(605, 1, 0, 'betfair'),
            riga(1500, 0, 0, 'api_football'), riga(1520, 1, 0, 'api_football'), // fonte in ritardo: scende e risale
            rigaEvento(1530, 'Goal', 'home'), // simbolo in piu' vicino alla risalita
            riga(2600, 1, 0, 'betfair'),
        ];
        const e = verifica(replaySintetico(righe));
        expect(codici(e)).toContain('TABELLONE_SCENDE');
        expect(codici(e)).toContain('SIMBOLO_GOL_SENZA_AUMENTO');
    });

    it('un Goal senza nessun aumento resta SIMBOLO_GOL_SENZA_AUMENTO (il caso del test di prima non cambia)', () => {
        const righe = [riga(0, 0, 0), riga(60, 0, 0), rigaEvento(900, 'Goal', 'home'), riga(1200, 0, 0), riga(2600, 0, 0)];
        expect(codici(verifica(replaySintetico(righe)))).toContain('SIMBOLO_GOL_SENZA_AUMENTO');
    });
});

// ---------------------------------------------------------------------------
// A2 - registrazione iniziata a partita in corso, gol appena prima del primo frame
// ---------------------------------------------------------------------------
describe('A2 (classe a): il punteggio sale appena PRIMA del primo frame, il Goal arriva dentro la barra', () => {
    // come 35812264 Beijing Guoan - Liaoning: la registrazione parte al 56', il Goal del 55' arriva dopo
    const frames = (): Frame[] => frameSintetici(300, 0, 56);
    it('nessun SIMBOLO_GOL_SENZA_AUMENTO quando l\'aumento e\' entro 3 minuti dal simbolo', () => {
        const righe = [
            riga(-600, 0, 0, 'betfair', 45), riga(-40, 0, 1, 'betfair', 55), // 0-1 prima del primo frame (T0)
            rigaEvento(20, 'Goal', 'away', 55), // il Goal della timeline, dentro la barra, minuto coerente
            riga(300, 0, 1, 'betfair', 56), riga(2000, 0, 1, 'betfair', 56),
        ];
        const e = verifica(replaySintetico(righe, frames()));
        expect(e.conteggi.simboli.goal, formattaReferto('A2', e)).toBe(1);
        expect(e.incoerenze, formattaReferto('A2', e)).toEqual([]);
    });
    it('l\'aumento prima del primo frame ma oltre 3 minuti dal simbolo: resta SIMBOLO_GOL_SENZA_AUMENTO', () => {
        const righe = [
            riga(-900, 0, 0, 'betfair', 45), riga(-400, 0, 1, 'betfair', 55),
            rigaEvento(20, 'Goal', 'away', 55),
            riga(300, 0, 1, 'betfair', 56), riga(2000, 0, 1, 'betfair', 56),
        ];
        const e = verifica(replaySintetico(righe, frames()));
        expect(e.conteggi.simboli.goal, formattaReferto('A2 lontano', e)).toBe(1);
        expect(codici(e)).toContain('SIMBOLO_GOL_SENZA_AUMENTO');
    });
});

// ---------------------------------------------------------------------------
// C1 - KICKOFF_DISCORDANTE e' fra DUE DATI registrati: dichiarato "per dati" con il motivo
// ---------------------------------------------------------------------------
const EV = eventiConFixture().includes('35760084') ? '35760084' : eventiConFixture()[0];
function conKickOffA(replay: ReplayData, ms: number): ReplayData {
    return {
        ...replay,
        score_timeline: replay.score_timeline.map(r => (r.event_type === 'KickOff' ? { ...r, ts: iso(ms) } : r)),
    };
}
const primoInGioco = (replay: ReplayData): number => Math.min(...replay.frames.filter(f => f.inplay).map(f => msDi(f.ts)));
/** toglie i frame degli 8 minuti prima del primo frame in gioco (il buco del registratore) */
const conBucoAlFischio = (replay: ReplayData): ReplayData => {
    const k = primoInGioco(replay);
    return { ...replay, frames: replay.frames.filter(f => { const t = msDi(f.ts); return t < k - 480_000 || t >= k; }) };
};

describe('C1 (classe c): KICKOFF_DISCORDANTE dichiarato per dati, con il motivo', () => {
    it('la partita vera e\' coerente (il KickOff del feed e\' vicino al primo frame in gioco)', () => {
        const { replay, estremi } = caricaPartita(EV);
        expect(replay.score_timeline.some(r => r.event_type === 'KickOff')).toBe(true);
        expect(verifica(replay, estremi).incoerenze).toEqual([]);
    });

    it('BUCO: nessun frame fra l\'inizio dichiarato e il primo frame in gioco (come le 4 partite del 16/07, buco 14:58 - 15:06:49)', () => {
        const { replay, estremi } = caricaPartita(EV);
        const k = primoInGioco(replay);
        const e = verifica(conKickOffA(conBucoAlFischio(replay), k - 360_000), estremi);
        expect(codici(e), formattaReferto('buco', e)).toEqual(['KICKOFF_DISCORDANTE']);
        const r = e.incoerenze[0];
        expect(r.gravita).toBe('avviso');
        expect(r.perDati).toMatch(/^buco della registrazione fra le .* UTC e le .* UTC: nessun frame registrato/);
        expect(e.note.map(x => x.codice)).toContain('BUCO_REGISTRAZIONE');
        expect(formattaReferto('buco', e)).toContain('INCOERENTE PER DATI buco');
        expect(formattaReferto('buco', e)).toContain('[PER DATI: buco della registrazione');
        // le note e gli altri rilievi NON portano la chiave (i rilievi di sempre restano identici)
        expect(e.rilievi.filter(x => x.codice !== 'KICKOFF_DISCORDANTE').every(x => !Object.prototype.hasOwnProperty.call(x, 'perDati'))).toBe(true);
    });

    it('FLAG: frame registrati con il mercato NON in gioco dopo l\'inizio dichiarato (come 35796477 e 35794996)', () => {
        const { replay, estremi } = caricaPartita(EV);
        const k = primoInGioco(replay);
        const e = verifica(conKickOffA(replay, k - 360_000), estremi);
        expect(codici(e)).toEqual(['KICKOFF_DISCORDANTE']);
        expect(e.incoerenze[0].perDati).toMatch(/^\d+ frame registrati fra l'inizio dichiarato dal feed .* hanno il mercato NON in gioco/);
    });

    it('FLAG al contrario: il mercato e\' in gioco prima del KickOff del feed', () => {
        const { replay, estremi } = caricaPartita(EV);
        const k = primoInGioco(replay);
        const e = verifica(conKickOffA(replay, k + 360_000), estremi);
        expect(codici(e)).toEqual(['KICKOFF_DISCORDANTE']);
        expect(e.incoerenze[0].perDati).toMatch(/^il mercato e' in gioco dalle .* UTC, il feed dichiara l'inizio alle/);
    });

    it('un difetto della PAGINA insieme a un dato discorde: la partita NON e\' "solo per dati"', () => {
        const { replay, estremi } = caricaPartita(EV);
        const k = primoInGioco(replay);
        const senzaGol: FunzioniPagina['timelineEventMarkers'] = (a, b, c, d, f) => timelineEventMarkers(a, b, c, d, f).filter(m => m.kind !== 'goal');
        const e = verifica(conKickOffA(conBucoAlFischio(replay), k - 360_000), estremi, { timelineEventMarkers: senzaGol });
        expect(codici(e)).toContain('KICKOFF_DISCORDANTE');
        expect(codici(e)).toContain('GOL_SENZA_SIMBOLO');
        expect(e.incoerenze.find(x => x.codice === 'GOL_SENZA_SIMBOLO')?.perDati).toBeUndefined();
        expect(formattaReferto('misto', e)).toMatch(/^INCOERENTE misto/);
    });
});

// ---------------------------------------------------------------------------
// C2 - CARTELLINI_DIVERSI con la timeline discreta
// ---------------------------------------------------------------------------
const EV2 = eventiConFixture().includes('35797769') ? '35797769' : eventiConFixture()[0];
describe('C2: CARTELLINI_DIVERSI per dati SOLO se la barra disegna esattamente i cartellini della timeline', () => {
    const base = () => caricaPartita(EV2);
    const gialloOspiti = (replay: ReplayData): ScoreEvent => {
        const g = replay.score_timeline.find(r => r.event_type === 'YellowCard' && (r.payload as { team?: string }).team === 'away');
        if (!g) throw new Error('la partita deve avere un giallo degli ospiti');
        return g;
    };

    it('la partita vera e\' coerente', () => {
        const { replay, estremi } = base();
        expect(verifica(replay, estremi).incoerenze).toEqual([]);
    });

    it('un giallo in piu\' nella TIMELINE (il conteggio non lo ha): la barra lo disegna, avviso dichiarato per dati', () => {
        const { replay, estremi } = base();
        const g = gialloOspiti(replay);
        // un giallo in piu' 7 minuti dopo, con il minuto coerente col suo ts (stesse chiavi del vero)
        const m = (g.minute ?? 0) + 7;
        const extra: ScoreEvent = { ...g, ts: iso(msDi(g.ts) + 420_000), minute: m, payload: { ...(g.payload as Record<string, unknown>), minute: m } };
        const e = verifica({ ...replay, score_timeline: [...replay.score_timeline, extra] }, estremi);
        expect(codici(e), formattaReferto('giallo in piu', e)).toEqual(['CARTELLINI_DIVERSI']);
        const r = e.incoerenze[0];
        expect(r.gravita).toBe('avviso');
        expect(r.spiegazione).toMatch(/il punteggio ne conta 2, sulla barra ci sono 3 simboli/);
        expect(r.perDati).toMatch(/la barra disegna i 3 cartellini gialli della timeline Betfair .* i conteggi del punteggio ne dicono 2/);
    });

    it('la PAGINA perde un giallo della timeline: avviso NON per dati', () => {
        const { replay, estremi } = base();
        const perdeUno: FunzioniPagina['timelineEventMarkers'] = (a, b, c, d, f) => {
            const m = timelineEventMarkers(a, b, c, d, f);
            const i = m.findIndex(x => x.kind === 'yellow' && x.team === 'away');
            return m.filter((_, j) => j !== i);
        };
        const e = verifica(replay, estremi, { timelineEventMarkers: perdeUno });
        const r = e.incoerenze.find(x => x.codice === 'CARTELLINI_DIVERSI');
        expect(r, formattaReferto('perde', e)).toBeTruthy();
        expect(r?.perDati).toBeUndefined();
        expect(formattaReferto('perde', e)).not.toContain('INCOERENTE PER DATI');
    });

    it('la PAGINA disegna un giallo che la timeline non ha: avviso NON per dati', () => {
        const { replay, estremi } = base();
        const aggiunge: FunzioniPagina['timelineEventMarkers'] = (a, b, c, d, f) => {
            const m = timelineEventMarkers(a, b, c, d, f);
            const y = m.find(x => x.kind === 'yellow' && x.team === 'away');
            return y ? [...m, { ...y }].sort((p, q) => (p.ts < q.ts ? -1 : p.ts > q.ts ? 1 : 0)) : m;
        };
        const e = verifica(replay, estremi, { timelineEventMarkers: aggiunge });
        const r = e.incoerenze.find(x => x.codice === 'CARTELLINI_DIVERSI');
        expect(r).toBeTruthy();
        expect(r?.perDati).toBeUndefined();
    });

    it('cartellino RI-EMESSO dal feed (stesso minuto, ts 15 minuti dopo): la pagina lo scarta, nessuna incoerenza', () => {
        const { replay, estremi } = base();
        const g = gialloOspiti(replay);
        const doppio: ScoreEvent = { ...g, ts: iso(msDi(g.ts) + 900_000) };
        const e = verifica({ ...replay, score_timeline: [...replay.score_timeline, doppio] }, estremi);
        expect(e.incoerenze, formattaReferto('doppio', e)).toEqual([]);
    });
});
