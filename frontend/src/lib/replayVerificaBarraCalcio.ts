// ============================================================================
// replayVerificaBarraCalcio - VERIFICATORE della barra di Match Replay, PARTE
// CALCIO: tabellone, gol, cartellini, angoli e motore delle opportunita'.
// (La parte generica -- estremi, ordine, simboli fuori barra, calcio d'inizio,
// sospensioni, buchi -- sta in `replayVerificaBarra.ts` e la riusa il tennis.)
//
// Ordine dell'utente (07/10/2026): la coerenza barra / simboli / tabellone e' uno
// standard per TUTTE le partite, presenti e future. Questo modulo costruisce la
// barra di una partita con le STESSE funzioni della pagina
//   - `timelineEventMarkers`   (simboli: gol, cartellini, angoli)
//   - `punteggioAlTs`          (tabellone al cursore)
//   - `buildSnapshots`         (motore delle opportunita': punteggio per bucket)
// e poi le sottopone a oracoli scritti dalla REGOLA con un codice diverso: se la
// pagina sbaglia, il verificatore fallisce. Le funzioni della pagina si possono
// sostituire (`opzioni.funzioni`) per PROVARE che il verificatore diventa rosso con
// i difetti noti (vedi `replayVerificaBarra.partite.test.ts`, falsificazione).
//
// I 4 DIFETTI DI STAMATTINA (94af2eb) che questo modulo sa riconoscere:
//   D1 tabellone a 0-0 dopo ogni riga-evento       -> TABELLONE_DIVERSO_DAL_FEED / TABELLONE_FINALE
//   D2 stesso difetto nel motore opportunita'       -> MOTORE_PUNTEGGIO
//   D3 simboli di fatti fuori registrazione         -> SIMBOLO_FUORI_REGISTRAZIONE
//   D4 gol del punteggio perso dalla timeline       -> GOL_SENZA_SIMBOLO
// ============================================================================
import type { ReplayData, ScoreEvent } from '@/lib/live';
import { buildSnapshots } from '@/lib/opportunities/snapshot';
import type { Snapshot } from '@/lib/opportunities/types';
import { punteggioAlTs, timelineEventMarkers, type TimelineMarker } from '@/lib/replayTimelineEvents';
import {
    BUCKET_BARRA_MS, creaRilievo, esitoDaRilievi, idMercatiSospensione, kickoffIndexSuPassi, kickoffTsDaFrame,
    oraUtc, passiBarra, passoVisibile, sospesiPerPasso, verificaBarraGenerica,
    type CodiceRilievo, type EsitoVerificaBarra, type EstremiRegistrazione, type GravitaRilievo, type Rilievo,
} from '@/lib/replayVerificaBarra';

/** Le funzioni della pagina che il verificatore mette alla prova. */
export interface FunzioniPagina {
    timelineEventMarkers: typeof timelineEventMarkers;
    punteggioAlTs: typeof punteggioAlTs;
    buildSnapshots: typeof buildSnapshots;
}
export const FUNZIONI_PAGINA: FunzioniPagina = { timelineEventMarkers, punteggioAlTs, buildSnapshots };

export interface OpzioniVerificaCalcio {
    /** estremi di `get_replay_meta` (ts_min, ts_max, inplay_from_ts); senza, si usano i frame */
    estremi?: EstremiRegistrazione | null;
    /** snapshot del motore gia' calcolati dalla pagina (evita di rifarli) */
    snapshots?: ReadonlyArray<Snapshot> | null;
    /** false = non controllare il motore delle opportunita' (default true) */
    controllaMotore?: boolean;
    /** funzioni della pagina da sostituire (solo per falsificare il verificatore) */
    funzioni?: Partial<FunzioniPagina>;
}

/** scarto massimo fra l'istante di un gol nel punteggio e quello del suo simbolo
 *  (la timeline Betfair e le righe del punteggio non sono simultanee: visti <= 11 s) */
const FINESTRA_ABBINAMENTO_GOL_MS = 180_000;
/** un simbolo di gol senza aumento del punteggio e' un gol ANNULLATO (VAR) se il
 *  punteggio scende entro questo tempo */
const FINESTRA_VAR_MS = 5 * 60_000;

const msDi = (ts: string): number => Date.parse(ts);
const ordTs = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);
const lato = (t: string | null | undefined): 'home' | 'away' | null => (t === 'home' || t === 'away' ? t : null);

function campo(o: unknown, k: string): unknown {
    return o != null && typeof o === 'object' ? (o as Record<string, unknown>)[k] : undefined;
}
/** conteggio cumulativo (angoli, cartellini) di una squadra nel payload di una riga del punteggio */
function conteggio(r: ScoreEvent, squadra: 'home' | 'away', chiave: string): number | null {
    const v = campo(campo(campo(r.payload, 'score'), squadra), chiave);
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
const eKickOff = (t: string | null | undefined): boolean => String(t ?? '').toLowerCase().replace(/[^a-z]/g, '') === 'kickoff';

/** Esegue una funzione della pagina: se lancia un errore la pagina si romperebbe su questa
 *  partita, quindi diventa un'incoerenza (e il verificatore va avanti con il valore di ripiego). */
function protetto<T>(rilievi: Rilievo[], nome: string, ripiego: T, f: () => T): T {
    try {
        return f();
    } catch (e) {
        const spiegazione = `La funzione ${nome} della pagina lancia un errore su questa partita (${e instanceof Error ? e.message : String(e)}): la pagina non la mostrerebbe.`;
        if (!rilievi.some(r => r.codice === 'FUNZIONE_PAGINA_ERRORE' && r.spiegazione === spiegazione)) {
            rilievi.push(creaRilievo('FUNZIONE_PAGINA_ERRORE', 'errore', spiegazione, { ambito: 'calcio' }));
        }
        return ripiego;
    }
}

interface RigaPunteggio { ts: string; ms: number; home: number; away: number; source: string; minute: number | null }

export function verificaBarraReplayCalcio(replay: ReplayData, opzioni: OpzioniVerificaCalcio = {}): EsitoVerificaBarra {
    const fn: FunzioniPagina = { ...FUNZIONI_PAGINA, ...(opzioni.funzioni ?? {}) };
    const frames = replay.frames ?? [];
    const markets = replay.markets ?? [];
    // come la pagina: tutte le righe, ordinate CONFRONTANDO LE STRINGHE dei ts
    const righe: ScoreEvent[] = [...(replay.score_timeline ?? [])].sort((a, b) => ordTs(a.ts, b.ts));
    const casa = replay.event?.home_name || 'Casa';
    const ospiti = replay.event?.away_name || 'Ospiti';

    // ---- la barra, costruita come la pagina ----
    const passi = passiBarra(frames);
    const kickoffTs = kickoffTsDaFrame(frames);
    const kickoffIndex = kickoffIndexSuPassi(passi, kickoffTs);
    const sospesi = sospesiPerPasso(passi, frames, markets);
    const span = Math.max(1, passi.length - 1);
    const erroriFunzioni: Rilievo[] = [];
    const simboli: TimelineMarker[] = passi.length > 0
        ? protetto(erroriFunzioni, 'timelineEventMarkers (simboli della barra)', [], () => fn.timelineEventMarkers(righe, passi, casa, ospiti, span))
        : [];
    const ids = idMercatiSospensione(markets);
    const primoKickOff = righe.filter(r => eKickOff(r.event_type) && Number.isFinite(msDi(r.ts))).sort((a, b) => msDi(a.ts) - msDi(b.ts))[0];

    const rilievi: Rilievo[] = verificaBarraGenerica({
        passi, simboli, frames, kickoffTs, kickoffIndex, sospesi,
        mercatiSospensione: ids.length > 0 ? ids : null,
        estremi: opzioni.estremi ?? null,
        inizioDichiarato: primoKickOff?.ts ?? null,
    });
    rilievi.push(...erroriFunzioni, ...verificaCalcio(replay, righe, passi, simboli, fn, opzioni));

    const conteggiSimboli: Record<string, number> = {};
    for (const s of simboli) conteggiSimboli[s.kind] = (conteggiSimboli[s.kind] ?? 0) + 1;
    return esitoDaRilievi(rilievi, {
        passi: passi.length,
        frames: frames.length,
        simboli: conteggiSimboli,
        righePunteggio: righe.filter(r => r.score_home != null && r.score_away != null).length,
        righeEvento: righe.filter(r => !!r.event_type).length,
    });
}

function verificaCalcio(
    replay: ReplayData,
    righe: ReadonlyArray<ScoreEvent>,
    passi: ReadonlyArray<{ ts: string; minute: number | null }>,
    simboli: ReadonlyArray<TimelineMarker>,
    fn: FunzioniPagina,
    opzioni: OpzioniVerificaCalcio,
): Rilievo[] {
    const out: Rilievo[] = [];
    const n = passi.length;
    const msPassi = passi.map(p => msDi(p.ts));
    const R = (codice: CodiceRilievo, gravita: GravitaRilievo, spiegazione: string,
        extra: { istante?: string | null; passo?: number | null; occorrenze?: number } = {}) => {
        const passo = extra.passo ?? null;
        out.push(creaRilievo(codice, gravita, spiegazione, {
            ambito: 'calcio', istante: extra.istante ?? null, passo,
            minuto: passo != null ? passi[passo]?.minute ?? null : null, occorrenze: extra.occorrenze,
        }));
    };
    if (n === 0) return out;

    // ---- righe che PORTANO il punteggio (le righe-evento della timeline non lo portano) ----
    const righeTs = righe.filter(r => !Number.isFinite(msDi(r.ts)));
    if (righeTs.length > 0) {
        R('TS_NON_VALIDO', 'errore', `${righeTs.length} righe del punteggio hanno un orario illeggibile (es. "${righeTs[0].ts}").`,
            { occorrenze: righeTs.length });
    }
    const conPunteggio: RigaPunteggio[] = righe
        .filter(r => r.score_home != null && r.score_away != null && Number.isFinite(msDi(r.ts)))
        .map(r => ({ ts: r.ts, ms: msDi(r.ts), home: r.score_home as number, away: r.score_away as number, source: r.source, minute: r.minute }))
        .sort((a, b) => a.ms - b.ms);
    const hasDiscrete = righe.some(r => !!r.event_type);
    // finestra della registrazione: i fatti fuori da qui NON hanno un istante sulla barra
    // (nessun simbolo, e' voluto: vedi D3) e non si pretendono dal verificatore
    const inizioReg = msPassi[0];
    const fineReg = msPassi[n - 1] + BUCKET_BARRA_MS;
    const dentro = (ms: number): boolean => ms >= inizioReg && ms <= fineReg;

    if (conPunteggio.length === 0) {
        R('PUNTEGGIO_ASSENTE', 'nota',
            'La partita non ha nessuna riga con il punteggio: il tabellone resta 0 - 0 e i gol non si possono confrontare con il punteggio.');
    } else {
        const verita = (ms: number): { home: number; away: number } => {
            let h = 0, a = 0;
            for (const r of conPunteggio) { if (r.ms > ms) break; h = r.home; a = r.away; }
            return { home: h, away: a };
        };

        // ---- (1) tabellone a OGNI passo = ultima riga CHE PORTA il punteggio ----
        let discordi = 0;
        let primo: { i: number; mostra: string; vero: string } | null = null;
        for (let i = 0; i < n; i++) {
            const m = protetto(out, 'punteggioAlTs (tabellone)', { home: -1, away: -1, minute: null }, () => fn.punteggioAlTs(righe, passi[i].ts));
            const v = verita(msPassi[i]);
            if (m.home !== v.home || m.away !== v.away) {
                discordi += 1;
                if (!primo) primo = { i, mostra: `${m.home} - ${m.away}`, vero: `${v.home} - ${v.away}` };
            }
        }
        if (primo) {
            R('TABELLONE_DIVERSO_DAL_FEED', 'errore',
                `Il tabellone mostra un punteggio diverso da quello del feed in ${discordi} passi su ${n} (primo: alle ${oraUtc(passi[primo.i].ts)} mostra ${primo.mostra}, il feed dice ${primo.vero}). `
                + 'Succede quando una riga-evento (gol, giallo, fine tempo) senza punteggio azzera il tabellone.',
                { passo: primo.i, istante: passi[primo.i].ts, occorrenze: discordi });
        }

        // ---- (2) il tabellone non scende: o e' una correzione del feed (VAR), o e' incoerenza ----
        const correzioni: RigaPunteggio[] = [];
        let scendeN = 0;
        let scendePrimo: { prev: RigaPunteggio; cur: RigaPunteggio } | null = null;
        for (let k = 1; k < conPunteggio.length; k++) {
            const prev = conPunteggio[k - 1], cur = conPunteggio[k];
            if (cur.home >= prev.home && cur.away >= prev.away) continue;
            if (cur.source === prev.source) {
                correzioni.push(cur);
                R('TABELLONE_CORREZIONE_FEED', 'nota',
                    `Il feed "${cur.source}" ha CORRETTO il punteggio da ${prev.home} - ${prev.away} a ${cur.home} - ${cur.away} alle ${oraUtc(cur.ts)} (gol annullato dal VAR o rettifica): il tabellone scende e va bene cosi'.`,
                    { istante: cur.ts, passo: passoVisibile(msPassi, cur.ms) });
            } else {
                scendeN += 1;
                if (!scendePrimo) scendePrimo = { prev, cur };
            }
        }
        if (scendePrimo) {
            const { prev, cur } = scendePrimo;
            R('TABELLONE_SCENDE', 'errore',
                `Il tabellone scende senza una correzione del feed ${scendeN === 1 ? 'una volta' : `${scendeN} volte`}: le due fonti non concordano (es. "${prev.source}" ${prev.home} - ${prev.away} alle ${oraUtc(prev.ts)}, poi "${cur.source}" ${cur.home} - ${cur.away} alle ${oraUtc(cur.ts)}). `
                + 'Il tabellone mostrato va avanti e indietro.',
                { istante: cur.ts, passo: passoVisibile(msPassi, cur.ms), occorrenze: scendeN });
        }

        // ---- (3) tabellone a fine replay = ultimo punteggio registrato ----
        const dentroReg = conPunteggio.filter(r => r.ms <= fineReg);
        const ultima = dentroReg[dentroReg.length - 1];
        const fine = protetto(out, 'punteggioAlTs (tabellone)', { home: -1, away: -1, minute: null }, () => fn.punteggioAlTs(righe, passi[n - 1].ts));
        if (ultima && (fine.home !== ultima.home || fine.away !== ultima.away)) {
            R('TABELLONE_FINALE', 'errore',
                `A fine replay il tabellone mostra ${fine.home} - ${fine.away} ma l'ultimo punteggio registrato (alle ${oraUtc(ultima.ts)}) e' ${ultima.home} - ${ultima.away}.`,
                { passo: n - 1, istante: ultima.ts });
        }

        // ---- (4) gol del punteggio <-> simboli di gol, uno a uno ----
        const attesi: { team: 'home' | 'away'; ms: number; ts: string }[] = [];
        let mh = 0, ma = 0;
        for (const r of conPunteggio) {
            if (dentro(r.ms)) {
                for (let k = mh; k < r.home; k++) attesi.push({ team: 'home', ms: r.ms, ts: r.ts });
                for (let k = ma; k < r.away; k++) attesi.push({ team: 'away', ms: r.ms, ts: r.ts });
            }
            mh = Math.max(mh, r.home); ma = Math.max(ma, r.away);
        }
        const gol = simboli
            .map(s => ({ s, ms: msDi(s.ts), preso: false }))
            .filter(g => g.s.kind === 'goal');
        const piuVicino = (ms: number, squadra: 'home' | 'away' | null): number => {
            let best = -1, bestD = Infinity;
            gol.forEach((g, j) => {
                if (g.preso) return;
                if (squadra != null && lato(g.s.team) !== squadra) return;
                const d = Math.abs(g.ms - ms);
                if (d <= FINESTRA_ABBINAMENTO_GOL_MS && d < bestD) { best = j; bestD = d; }
            });
            return best;
        };
        const orfani: typeof attesi = [];
        for (const a of attesi) {
            const j = piuVicino(a.ms, a.team);
            if (j >= 0) gol[j].preso = true; else orfani.push(a);
        }
        for (const a of orfani) {
            const nome = a.team === 'home' ? replay.event?.home_name || 'Casa' : replay.event?.away_name || 'Ospiti';
            const j = piuVicino(a.ms, null);
            if (j >= 0) {
                gol[j].preso = true;
                R('GOL_SQUADRA_DIVERSA', 'avviso',
                    `Il punteggio dice che ha segnato "${nome}" alle ${oraUtc(a.ts)} ma il simbolo del gol vicino e' assegnato all'altra squadra (autogol o dato del feed da controllare).`,
                    { istante: a.ts, passo: passoVisibile(msPassi, a.ms) });
            } else {
                R('GOL_SENZA_SIMBOLO', 'errore',
                    `Il punteggio sale per "${nome}" alle ${oraUtc(a.ts)} ma sulla barra non c'e' nessun simbolo di gol entro 3 minuti.`,
                    { istante: a.ts, passo: passoVisibile(msPassi, a.ms) });
            }
        }
        for (const g of gol) {
            if (g.preso) continue;
            const annullato = correzioni.some(c => c.ms >= g.ms - 60_000 && c.ms <= g.ms + FINESTRA_VAR_MS);
            if (annullato) {
                R('GOL_ANNULLATO', 'nota',
                    `Il simbolo "${g.s.label}" delle ${oraUtc(g.s.ts)} non ha un aumento del punteggio: il punteggio e' stato corretto subito dopo (gol annullato).`,
                    { istante: g.s.ts, passo: passoVisibile(msPassi, g.ms) });
            } else {
                R('SIMBOLO_GOL_SENZA_AUMENTO', 'errore',
                    `C'e' un simbolo di gol ("${g.s.label}", ${g.s.minute != null ? `${g.s.minute}' ` : ''}alle ${oraUtc(g.s.ts)}) ma il punteggio non aumenta per quella squadra entro 3 minuti.`,
                    { istante: g.s.ts, passo: passoVisibile(msPassi, g.ms) });
            }
        }
    }

    // ---- (5) cartellini e angoli: simboli = conteggi cumulativi del punteggio ----
    const tipi: { kind: 'yellow' | 'red' | 'corner'; chiave: string; nome: string; codice: CodiceRilievo }[] = [
        { kind: 'yellow', chiave: 'numberOfYellowCards', nome: 'cartellini gialli', codice: 'CARTELLINI_DIVERSI' },
        { kind: 'red', chiave: 'numberOfRedCards', nome: 'cartellini rossi', codice: 'CARTELLINI_DIVERSI' },
        { kind: 'corner', chiave: 'numberOfCorners', nome: 'calci d\'angolo', codice: 'ANGOLI_DIVERSI' },
    ];
    const righeNonEvento = righe.filter(r => !r.event_type);
    for (const t of tipi) {
        // massimo del conteggio visto fino a fine registrazione, e quello gia' raggiunto
        // PRIMA dell'inizio (non hanno un istante sulla barra): i simboli attesi sono la differenza
        const massimo = { home: null as number | null, away: null as number | null };
        const prima = { home: 0, away: 0 };
        for (const r of righeNonEvento) {
            const ms = msDi(r.ts);
            if (!Number.isFinite(ms)) continue;
            for (const sq of ['home', 'away'] as const) {
                const c = conteggio(r, sq, t.chiave);
                if (c == null) continue;
                if (ms <= fineReg) massimo[sq] = Math.max(massimo[sq] ?? 0, c);
                if (ms < inizioReg) prima[sq] = Math.max(prima[sq], c);
            }
        }
        if (massimo.home == null && massimo.away == null) {
            if (righeNonEvento.length > 0) {
                R('CONTEGGI_ASSENTI', 'nota', `Il feed del punteggio non porta il conteggio dei ${t.nome}: simboli e conteggi non si possono confrontare.`);
            }
            continue;
        }
        for (const sq of ['home', 'away'] as const) {
            const atteso = Math.max(0, (massimo[sq] ?? 0) - prima[sq]);
            const visti = simboli.filter(s => s.kind === t.kind && lato(s.team) === sq).length;
            if (visti === atteso) continue;
            const nome = sq === 'home' ? replay.event?.home_name || 'Casa' : replay.event?.away_name || 'Ospiti';
            // i gialli/rossi con la timeline discreta vengono da un'ALTRA fonte (get_event_timeline):
            // una differenza e' un dato del feed da guardare; angoli e cartellini derivati sono della pagina
            const gravita: GravitaRilievo = t.kind !== 'corner' && hasDiscrete ? 'avviso' : 'errore';
            R(t.codice, gravita,
                `${t.nome[0].toUpperCase()}${t.nome.slice(1)} di "${nome}": il punteggio ne conta ${atteso}, sulla barra ci sono ${visti} simboli.`);
        }
    }

    // ---- (6) il motore delle opportunita' vede lo stesso punteggio del tabellone ----
    if (conPunteggio.length > 0 && opzioni.controllaMotore !== false) {
        const snaps: ReadonlyArray<Snapshot> = opzioni.snapshots
            ?? protetto<ReadonlyArray<Snapshot>>(out, 'buildSnapshots (motore delle opportunita\')', [], () => fn.buildSnapshots(replay, BUCKET_BARRA_MS));
        let errati = 0;
        let primo: { s: Snapshot; vero: string } | null = null;
        for (const s of snaps) {
            const fineBucket = msDi(s.ts) + BUCKET_BARRA_MS - 1;
            let h = 0, a = 0;
            for (const r of conPunteggio) { if (r.ms > fineBucket) break; h = r.home; a = r.away; }
            if (s.scoreHome !== h || s.scoreAway !== a) {
                errati += 1;
                if (!primo) primo = { s, vero: `${h} - ${a}` };
            }
        }
        if (primo) {
            R('MOTORE_PUNTEGGIO', 'errore',
                `Il motore delle opportunita' vede un punteggio sbagliato in ${errati} bucket su ${snaps.length} (primo: alle ${oraUtc(primo.s.ts)} vede ${primo.s.scoreHome} - ${primo.s.scoreAway}, il feed dice ${primo.vero}).`,
                { istante: primo.s.ts, occorrenze: errati });
        }
    }
    return out;
}
