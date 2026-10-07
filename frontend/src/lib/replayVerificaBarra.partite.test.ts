// ============================================================================
// 07/10 - LA COERENZA BARRA / SIMBOLI / TABELLONE E' UNO STANDARD PER TUTTE LE
// PARTITE, PRESENTI E FUTURE. (Ordine dell'utente, testuale: "NON SOLO SULLE DUE
// PARTITE, DEVE ESSERE UNO STANDARD PER TUTTE QUELLE PRESENTI E QUELLE FUTURE.")
//
// Questo test SCOPRE DA SOLO ogni registrazione in `registrazioni_banco/<event>/`
// (nessun elenco a mano: una cartella aggiunta domani entra senza toccare il test),
// carica la sua fixture `__fixtures__/replay_barra_<event>.json` (generata dal raw con
// `python3 tools/replay_barra_fixture.py <event>`: curator vero, punteggi, timeline,
// campionamento del server) e la passa al verificatore:
//   - CONTRATTO: la fixture di ogni registrazione presente ESISTE ed e' AGGIORNATA
//     (impronta sha256 dei file sorgente): se manca o e' vecchia il test e' rosso e dice
//     il comando da lanciare;
//   - 0 INCOERENZE su barra, simboli e tabellone (le note, come i buchi della
//     registrazione, sono dichiarate ma non sono incoerenze);
//   - FALSIFICAZIONE: i QUATTRO difetti di stamattina (94af2eb) rimessi uno a uno ->
//     il verificatore deve diventare rosso su OGNI partita a cui il difetto si applica:
//       D1 tabellone a 0-0 dopo le righe-evento (punteggioAlTs difettosa)
//       D2 stesso difetto nel motore opportunita' (buildSnapshots difettosa)
//       D3 simboli di fatti fuori registrazione incollati a 0% / 100%
//       D4 gol del punteggio perso dalla timeline
//     D3 e D4 con la funzione dei simboli com'era PRIMA del fix
//     (`__fixtures__/replayTimelineEventsLegacy.ts`, copia difettosa di proposito).
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { ReplayData, ScoreEvent } from '@/lib/live';
import { kindDiTipo } from '@/lib/replayTimelineEvents';
import { verificaBarraReplayCalcio, type OpzioniVerificaCalcio } from '@/lib/replayVerificaBarraCalcio';
import { formattaReferto } from '@/lib/replayVerificaBarraTesto';
import type { EsitoVerificaBarra, EstremiRegistrazione } from '@/lib/replayVerificaBarra';
import {
    caricaPartita, comandoRigenera, eventiConFixture, eventiRegistrati, fixtureEsiste, impronteSorgente, percorsoFixture,
    caricaFixtureCompleta,
} from './__fixtures__/replayBarraTutte';
import { punteggioAlTsD1, buildSnapshotsD2, timelineEventMarkersD3D4 } from './__fixtures__/replayBarraMutanti';

const EVENTI = eventiRegistrati();

const codici = (e: EsitoVerificaBarra): string[] => e.incoerenze.map(r => r.codice);
const verifica = (replay: ReplayData, estremi: EstremiRegistrazione | null, extra: OpzioniVerificaCalcio = {}) =>
    verificaBarraReplayCalcio(replay, { estremi, ...extra });
const ms = (ts: string): number => Date.parse(ts);
const perTs = (a: ScoreEvent, b: ScoreEvent): number => ms(a.ts) - ms(b.ts);

describe('registrazioni scoperte', () => {
    it('c\'e\' almeno una registrazione in registrazioni_banco/ (altrimenti il test non verifica nulla)', () => {
        expect(EVENTI.length).toBeGreaterThan(0);
    });
});

describe.each(EVENTI)('partita %s (registrazioni_banco)', (ev) => {
    it('CONTRATTO: la fixture della registrazione esiste ed e\' aggiornata', () => {
        expect(
            fixtureEsiste(ev),
            `manca la fixture ${percorsoFixture(ev)}. Generala (dalla radice del repository): ${comandoRigenera(ev)}`,
        ).toBe(true);
        const fx = caricaFixtureCompleta(ev);
        expect(fx.sorgente, `fixture di ${ev} senza impronta dei file sorgente: rigenerala con ${comandoRigenera(ev)}`).toBeTruthy();
        expect(fx.meta, `fixture di ${ev} senza gli estremi della registrazione: rigenerala con ${comandoRigenera(ev)}`).toBeTruthy();
        expect(
            fx.sorgente,
            `la registrazione ${ev} e' cambiata dopo la generazione della fixture: rigenerala con ${comandoRigenera(ev)}`,
        ).toEqual(impronteSorgente(ev));
    });

    it('0 INCOERENZE: barra, simboli, calcio d\'inizio, sospensioni, tabellone, gol, cartellini, angoli, motore', () => {
        const { replay, estremi } = caricaPartita(ev);
        const e = verifica(replay, estremi);
        expect(e.conteggi.passi).toBeGreaterThan(0);
        expect(e.incoerenze, `\n${formattaReferto(ev, e)}\n`).toEqual([]);
        expect(e.ok).toBe(true);
    });

    it('i simboli verificati sono davvero quelli della partita (il verificatore non gira a vuoto)', () => {
        const { replay, estremi } = caricaPartita(ev);
        const e = verifica(replay, estremi);
        const attesi = replay.score_timeline.filter(r => ['goal', 'yellow', 'red'].includes(kindDiTipo(r.event_type) ?? '')).length;
        const visti = (e.conteggi.simboli.goal ?? 0) + (e.conteggi.simboli.yellow ?? 0) + (e.conteggi.simboli.red ?? 0);
        expect(visti).toBe(attesi);
        expect(e.conteggi.righePunteggio).toBe(replay.score_timeline.filter(r => r.score_home != null && r.score_away != null).length);
    });
});

// ----------------------------------------------------------------------------
// FALSIFICAZIONE: i quattro difetti di stamattina rimessi uno a uno
// ----------------------------------------------------------------------------
describe.each(eventiConFixture())('falsificazione sulla partita %s', (ev) => {
    const { replay, estremi } = caricaPartita(ev);
    const righe = [...replay.score_timeline].sort(perTs);
    const conPunteggio = righe.filter(r => r.score_home != null && r.score_away != null);
    const primoNonZero = conPunteggio.find(r => (r.score_home ?? 0) + (r.score_away ?? 0) > 0);
    // D1/D2 si vedono solo se c'e' una riga-evento DOPO una riga con punteggio diverso da 0-0
    const d1Applicabile = !!primoNonZero && righe.some(r => r.event_type && ms(r.ts) > ms(primoNonZero.ts));
    const ultimaRiga = righe[righe.length - 1];
    const finaleSbagliato = !!ultimaRiga && ultimaRiga.score_home == null && conPunteggio.some(r => (r.score_home ?? 0) + (r.score_away ?? 0) > 0);

    it('D1 tabellone a 0-0 dopo le righe-evento: rosso (TABELLONE_DIVERSO_DAL_FEED' + ' e, a fine replay, TABELLONE_FINALE)', () => {
        const e = verifica(replay, estremi, { funzioni: { punteggioAlTs: punteggioAlTsD1 } });
        if (!d1Applicabile) {
            expect(e.ok, 'D1 non si applica a questa partita (punteggio sempre 0-0 o nessuna riga-evento dopo un gol)').toBe(true);
            return;
        }
        expect(codici(e)).toContain('TABELLONE_DIVERSO_DAL_FEED');
        if (finaleSbagliato) expect(codici(e)).toContain('TABELLONE_FINALE');
        expect(e.ok).toBe(false);
    });

    it('D2 stesso difetto nel motore opportunita\' (buildSnapshots): rosso (MOTORE_PUNTEGGIO)', () => {
        const e = verifica(replay, estremi, { funzioni: { buildSnapshots: buildSnapshotsD2 } });
        if (!d1Applicabile) {
            expect(e.ok).toBe(true);
            return;
        }
        expect(codici(e)).toContain('MOTORE_PUNTEGGIO');
        expect(e.ok).toBe(false);
    });

    // fatti con un istante sulla barra: gol, cartellini
    const fatti = righe.filter(r => ['goal', 'yellow', 'red'].includes(kindDiTipo(r.event_type) ?? ''));
    const taglio = (replayOriginale: ReplayData, da: number | null, a: number | null): ReplayData => ({
        ...replayOriginale,
        frames: replayOriginale.frames.filter(f => (da == null || ms(f.ts) >= da) && (a == null || ms(f.ts) <= a)),
    });
    const msFrames = replay.frames.map(f => ms(f.ts)).sort((x, y) => x - y);
    const t70 = msFrames[Math.floor(msFrames.length * 0.7)];

    it('D3 registrazione che INIZIA a partita in corso: la funzione vera e\' pulita, quella di prima del fix e\' rossa (SIMBOLO_FUORI_REGISTRAZIONE)', () => {
        const v = taglio(replay, t70, null);
        const primoFrame = Math.min(...v.frames.map(f => ms(f.ts)));
        const applicabile = fatti.some(r => ms(r.ts) < primoFrame);
        expect(applicabile, 'la partita deve avere un fatto prima del taglio per provare D3').toBe(true);
        const bene = verifica(v, null);
        expect(bene.incoerenze, `\n${formattaReferto(ev, bene)}\n`).toEqual([]);
        const male = verifica(v, null, { funzioni: { timelineEventMarkers: timelineEventMarkersD3D4 } });
        expect(codici(male)).toContain('SIMBOLO_FUORI_REGISTRAZIONE');
    });

    it('D3 registrazione che FINISCE prima della partita: rossa con la funzione di prima del fix', () => {
        const v = taglio(replay, null, t70);
        const ultimoFrame = Math.max(...v.frames.map(f => ms(f.ts)));
        expect(fatti.some(r => ms(r.ts) > ultimoFrame + 10_000)).toBe(true);
        const bene = verifica(v, null);
        expect(bene.incoerenze, `\n${formattaReferto(ev, bene)}\n`).toEqual([]);
        const male = verifica(v, null, { funzioni: { timelineEventMarkers: timelineEventMarkersD3D4 } });
        expect(codici(male)).toContain('SIMBOLO_FUORI_REGISTRAZIONE');
    });

    const primoGoal = righe.find(r => kindDiTipo(r.event_type) === 'goal');
    it('D4 gol nel punteggio ma assente dalla timeline (poll perso): la funzione vera lo disegna, quella di prima del fix no (GOL_SENZA_SIMBOLO)', () => {
        if (!primoGoal) {
            expect(true, 'partita senza gol: D4 non si applica').toBe(true);
            return;
        }
        const senza: ReplayData = { ...replay, score_timeline: replay.score_timeline.filter(r => r !== primoGoal) };
        const bene = verifica(senza, estremi);
        expect(bene.incoerenze, `\n${formattaReferto(ev, bene)}\n`).toEqual([]);
        const male = verifica(senza, estremi, { funzioni: { timelineEventMarkers: timelineEventMarkersD3D4 } });
        expect(codici(male)).toContain('GOL_SENZA_SIMBOLO');
    });
});
