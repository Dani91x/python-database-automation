// ============================================================================
// Scoperta di TUTTE le registrazioni del repository per il verificatore della barra
// (07/10/2026). Nessun elenco a mano: ogni cartella di `registrazioni_banco/<event>/`
// con il raw dello stream e' una partita da verificare. Una registrazione aggiunta
// domani entra nel test senza toccarlo; se manca la sua fixture, il test fallisce e
// scrive il comando che la genera.
//
// La fixture `replay_barra_<event>.json` la produce `tools/replay_barra_fixture.py`
// (curator vero dal raw + punteggi + timeline + campionamento del server) e porta con
// se' l'impronta (sha256) dei file di registrazione da cui deriva: se la registrazione
// cambia, la fixture risulta VECCHIA e il test fallisce.
// ============================================================================
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import type { ReplayData, ScoreEvent } from '@/lib/live';
import type { EstremiRegistrazione } from '@/lib/replayVerificaBarra';
import { replayDaFixture, type FixtureBarra } from './replayBarraConversione';

/** radice del repository (questo file sta in frontend/src/lib/__fixtures__) */
export const RADICE_REPO = resolve(__dirname, '../../../..');
export const CARTELLA_REGISTRAZIONI = join(RADICE_REPO, 'registrazioni_banco');
const CARTELLA_FIXTURE = __dirname;

export interface FixtureBarraCompleta extends FixtureBarra {
    meta: EstremiRegistrazione & { n_mercati?: number; bucket_pre_sec?: number; bucket_in_sec?: number };
    sorgente: Record<string, string | null>;
}

/** Ogni sottocartella di `registrazioni_banco/` con il raw dello stream (ordinate). */
export function eventiRegistrati(): string[] {
    if (!existsSync(CARTELLA_REGISTRAZIONI)) return [];
    return readdirSync(CARTELLA_REGISTRAZIONI, { withFileTypes: true })
        .filter(d => d.isDirectory())
        .map(d => d.name)
        .filter(ev => {
            const dir = join(CARTELLA_REGISTRAZIONI, ev);
            return existsSync(join(dir, `${ev}.raw.jsonl.gz`)) || existsSync(join(dir, `${ev}.raw.jsonl`));
        })
        .sort();
}

export const percorsoFixture = (ev: string): string => join(CARTELLA_FIXTURE, `replay_barra_${ev}.json`);
export const comandoRigenera = (ev: string): string => `python3 tools/replay_barra_fixture.py ${ev}`;

/**
 * 08/10 (cantiere 12): impronta sha256 INDIPENDENTE DAI FINE RIGA. Un file di testo (.jsonl) puo' stare sul
 * disco con LF (Linux, repository) o con CRLF (Windows con `core.autocrlf=true`): prima di fare lo sha il
 * contenuto passa da `\r\n` a `\n`, cosi' la stessa registrazione da' la stessa impronta ovunque. I file
 * binari (.gz) NON si toccano: una coppia di byte 0d 0a dentro un gzip non e' un fine riga.
 * (Stessa regola di `tools/replay_barra_fixture.py::_sha256_file`.)
 */
export function improntaContenuto(contenuto: Buffer, testo: boolean): string {
    const dati = testo ? Buffer.from(contenuto.toString('latin1').replace(/\r\n/g, '\n'), 'latin1') : contenuto;
    return createHash('sha256').update(dati).digest('hex');
}

function sha256(percorso: string, testo: boolean): string | null {
    if (!existsSync(percorso)) return null;
    return improntaContenuto(readFileSync(percorso), testo);
}

/** sha256 dei file di registrazione come stanno nel repository (stessa regola del generatore Python).
 *  `cartella` e' la radice delle registrazioni (i test ne passano una temporanea; di serie quella del repository). */
export function impronteSorgente(ev: string, cartella: string = CARTELLA_REGISTRAZIONI): Record<string, string | null> {
    const dir = join(cartella, ev);
    const out: Record<string, string | null> = {};
    for (const nome of [`${ev}.raw.jsonl`, `${ev}.scores.jsonl`, `${ev}.timeline.jsonl`]) {
        out[nome] = sha256(join(dir, nome), true) ?? sha256(join(dir, `${nome}.gz`), false);
    }
    return out;
}

export function fixtureEsiste(ev: string): boolean {
    return existsSync(percorsoFixture(ev));
}

export function caricaFixtureCompleta(ev: string): FixtureBarraCompleta {
    if (!fixtureEsiste(ev)) {
        throw new Error(`manca la fixture ${percorsoFixture(ev)}. Generala (dalla radice del repository): ${comandoRigenera(ev)}`);
    }
    return JSON.parse(readFileSync(percorsoFixture(ev), 'utf-8')) as FixtureBarraCompleta;
}

/** Le registrazioni che hanno gia' la loro fixture. I test che LAVORANO sui dati usano questo
 *  elenco, cosi' una registrazione nuova senza fixture fa cadere solo il test di CONTRATTO
 *  (con il comando da lanciare) e non manda in crash gli altri. */
export function eventiConFixture(): string[] {
    return eventiRegistrati().filter(fixtureEsiste);
}

export function caricaPartita(ev: string): { replay: ReplayData; estremi: EstremiRegistrazione; fixture: FixtureBarraCompleta } {
    const fixture = caricaFixtureCompleta(ev);
    return { replay: replayDaFixture(fixture), estremi: fixture.meta, fixture };
}

/**
 * Il primo gol che RESTA, di una squadra qualsiasi: la prima riga di punteggio con almeno un gol
 * dopo la quale nessuna riga torna a un punteggio piu' basso. Un gol ANNULLATO (35768365, 1-0 al
 * 28' poi 0-0) non va bene: la seconda fonte a 0-0 darebbe due segnalazioni invece di una. E non
 * si guarda solo la squadra di casa: in 35774000 (0-3) segnano solo gli ospiti.
 */
export function primoGolCheResta(replay: ReplayData): ScoreEvent | null {
    const righe = replay.score_timeline.filter(r => r.score_home != null && r.score_away != null);
    for (let i = 0; i < righe.length; i++) {
        const g = righe[i];
        if ((g.score_home ?? 0) + (g.score_away ?? 0) <= 0) continue;
        const annullato = righe.slice(i + 1).some(r => (r.score_home ?? 0) < (g.score_home ?? 0) || (r.score_away ?? 0) < (g.score_away ?? 0));
        if (!annullato) return g;
    }
    return null;
}

/** Difetto nei DATI usato dai test: una seconda fonte (api_football) che 5 s dopo il primo gol che
 *  resta rimette il punteggio a 0-0 -> una sola segnalazione TABELLONE_SCENDE. */
export function conFonteInRitardo(replay: ReplayData): ReplayData {
    const g = primoGolCheResta(replay);
    if (!g) throw new Error('la partita deve avere un gol che resta');
    const tardi = new Date(Date.parse(g.ts) + 5000).toISOString().replace('Z', '+00:00');
    return { ...replay, score_timeline: [...replay.score_timeline, { ...g, ts: tardi, source: 'api_football', score_home: 0, score_away: 0 }] };
}
