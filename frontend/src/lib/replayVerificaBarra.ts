// ============================================================================
// replayVerificaBarra - VERIFICATORE della barra di avanzamento di Match Replay
// (PARTE GENERICA, riusabile da ogni replay: calcio oggi, tennis domani).
//
// Ordine dell'utente (07/10/2026): "NON SOLO SULLE DUE PARTITE, DEVE ESSERE UNO
// STANDARD PER TUTTE QUELLE PRESENTI E QUELLE FUTURE." Questo modulo e il suo
// gemello `replayVerificaBarraCalcio.ts` trasformano i controlli fatti a mano il
// 07/10 (referto `AUDIT_2026-10-07/REPLAY_BARRA_SIMBOLI.md`) in una funzione PURA:
// dati della partita -> elenco delle INCOERENZE, ognuna con codice, istante e una
// spiegazione per il trader.
//
// DUE LIVELLI
//  1. COSTRUTTORI della barra (`passiBarra`, `kickoffTsDaFrame`,
//     `kickoffIndexSuPassi`, `sospesiPerPasso`): la stessa logica che la pagina
//     `MatchReplay.tsx` ha in linea (griglia da 10 s, primo frame in gioco,
//     sospensioni del Match Odds). La patch del referto fa chiamare QUESTE
//     funzioni alla pagina: da allora pagina e verificatore usano UN solo codice.
//     Finche' la patch non c'e', `replayVerificaBarra.pagina.test.tsx` monta la
//     pagina vera e confronta passo per passo con questi costruttori.
//  2. CONTROLLI (`verificaBarraGenerica`): lavorano su una `BarraDaVerificare` e
//     NON sanno nulla di sport. Gli oracoli qui sono scritti dalla REGOLA (primo
//     passo con ts >= istante del fatto, ultimo frame <= istante, ...) con un
//     codice diverso da quello della pagina: se la pagina sbaglia, falliscono.
//
// COME LO RIUSA IL TENNIS: il replay tennis costruisce i suoi passi, i suoi
// simboli (break, set, game) e le sue sospensioni, poi chiama
// `verificaBarraGenerica` (estremi, ordine, simboli fuori barra, posizione,
// calcio d'inizio, sospensioni, buchi) e aggiunge i SUOI controlli di dominio
// (game/set/punteggio) come fa `replayVerificaBarraCalcio.ts` per gol, cartellini e
// angoli. I tipi `Rilievo` / `EsitoVerificaBarra` e il formato del referto
// (`replayVerificaBarraTesto.ts`) sono comuni.
//
// GRAVITA
//   errore  = la barra o i simboli MENTONO (posizione sbagliata, simbolo prima del
//             suo istante, tabellone diverso dal feed): il test su tutte le partite
//             diventa rosso.
//   avviso  = incoerenza del DATO o del feed da guardare (due fonti discordanti,
//             cartellini diversi dai conteggi): rosso anche questo, si decide a mano.
//   nota    = fatto dichiarato, NON incoerenza (buco della registrazione, VAR,
//             sospensione troppo breve per essere disegnata): il referto lo elenca.
// ============================================================================
import type { Frame, Market } from '@/lib/live';

export type GravitaRilievo = 'errore' | 'avviso' | 'nota';
export type AmbitoRilievo = 'generico' | 'calcio' | 'tennis';

export type CodiceRilievo =
    // generici
    | 'NESSUN_FRAME' | 'TS_NON_VALIDO' | 'TS_ORDINE_STRINGHE' | 'PASSI_NON_ORDINATI'
    | 'ESTREMO_INIZIO' | 'ESTREMO_FINE' | 'FRAME_FUORI_ESTREMI'
    | 'SIMBOLO_FUORI_BARRA' | 'SIMBOLO_FUORI_REGISTRAZIONE' | 'SIMBOLO_NON_ORDINATO'
    | 'SIMBOLO_PRIMA_DELL_ISTANTE' | 'SIMBOLO_POSIZIONE'
    | 'KICKOFF_FUORI_POSTO' | 'KICKOFF_DIVERSO_DA_META' | 'KICKOFF_DISCORDANTE' | 'KICKOFF_IN_RITARDO'
    | 'SOSPENSIONE_LUNGHEZZA' | 'SOSPENSIONE_DISCORDANTE' | 'SOSPENSIONE_FUORI_ESTREMI' | 'SOSPENSIONE_NON_VISIBILE'
    | 'BUCO_REGISTRAZIONE' | 'INIZIO_IN_CORSO' | 'FUNZIONE_PAGINA_ERRORE'
    // calcio
    | 'TABELLONE_DIVERSO_DAL_FEED' | 'TABELLONE_SCENDE' | 'TABELLONE_CORREZIONE_FEED' | 'TABELLONE_FINALE'
    | 'GOL_SENZA_SIMBOLO' | 'SIMBOLO_GOL_SENZA_AUMENTO' | 'GOL_SQUADRA_DIVERSA' | 'GOL_ANNULLATO'
    | 'CARTELLINI_DIVERSI' | 'ANGOLI_DIVERSI' | 'MOTORE_PUNTEGGIO' | 'PUNTEGGIO_ASSENTE' | 'CONTEGGI_ASSENTI'
    // tennis (`tennisReplayVerificaBarra.ts`)
    | 'TENNIS_EVENTO_SENZA_SIMBOLO' | 'TENNIS_SIMBOLO_SENZA_EVENTO' | 'TENNIS_INPLAY_SIMBOLO' | 'TENNIS_SET_SCENDONO'
    | 'TENNIS_FINE_SET_INCOERENTE' | 'TENNIS_TIEBREAK_INCOERENTE' | 'TENNIS_BREAK_INCOERENTE' | 'TENNIS_SALTO';

export interface Rilievo {
    codice: CodiceRilievo;
    gravita: GravitaRilievo;
    ambito: AmbitoRilievo;
    /** istante (ISO) a cui si riferisce, se ne ha uno */
    istante: string | null;
    /** indice del passo della barra, se ne ha uno */
    passo: number | null;
    /** minuto mostrato dalla barra a quel passo */
    minuto: number | null;
    /** spiegazione per il trader, in italiano */
    spiegazione: string;
    /** quante volte si e' presentato (i casi ripetuti si raggruppano) */
    occorrenze: number;
    /** 08/10 (cantiere 13): presente SOLO se l'incoerenza e' dei DATI registrati (classe c: due
     *  fonti registrate discordi, buco della registrazione), non della pagina ne' del verificatore.
     *  Il testo e' il motivo, per il trader. L'incoerenza resta tale (mai silenziosa). */
    perDati?: string;
}

export interface EsitoVerificaBarra {
    rilievi: Rilievo[];
    /** errori + avvisi: devono essere ZERO per dire che la barra e' coerente */
    incoerenze: Rilievo[];
    note: Rilievo[];
    ok: boolean;
    conteggi: {
        passi: number;
        frames: number;
        simboli: Record<string, number>;
        righePunteggio: number;
        righeEvento: number;
        buchi: number;
    };
}

export interface PassoBarra { ts: string; minute: number | null }
export interface SimboloBarra {
    ts: string;
    pctLeft: number;
    kind: string;
    team?: string | null;
    minute: number | null;
    label?: string;
}
export type FrameBarra = Pick<Frame, 'market_id' | 'ts' | 'minute' | 'inplay' | 'status'>;
/** Estremi dichiarati dal server (`get_replay_meta`: ts_min, ts_max, inplay_from_ts). */
export interface EstremiRegistrazione {
    ts_min: string | null;
    ts_max: string | null;
    inplay_from_ts: string | null;
}

export interface BarraDaVerificare {
    passi: ReadonlyArray<PassoBarra>;
    simboli: ReadonlyArray<SimboloBarra>;
    frames: ReadonlyArray<FrameBarra>;
    kickoffTs: string | null;
    kickoffIndex: number;
    sospesi: ReadonlyArray<boolean>;
    /** mercati che guidano il segmento di sospensione (Match Odds); null = qualsiasi mercato */
    mercatiSospensione: ReadonlyArray<string> | null;
    estremi?: EstremiRegistrazione | null;
    /** inizio partita dichiarato da un'ALTRA fonte (calcio: riga KickOff della timeline Betfair) */
    inizioDichiarato?: string | null;
    ambito?: AmbitoRilievo;
}

// ----------------------------------------------------------------------------
// costanti di griglia: sono quelle della pagina e del server
// ----------------------------------------------------------------------------
/** bucket della griglia della barra (`MatchReplay.tsx`, TIMELINE_BUCKET_MS) */
export const BUCKET_BARRA_MS = 10_000;
/** pre-match caricato al massimo per queste ore prima del kickoff (= `live.ts`, PRE_MATCH_MAX_MS) */
const PRE_MATCH_MAX_MS = 4 * 3600_000;
/** bucket massimo del server: pre-match 300 s, in-gioco 60 s (= `live.ts`, clamp di fetchReplayChunked) */
const BUCKET_SERVER_PRE_MAX_MS = 300_000;
const BUCKET_SERVER_IN_MAX_MS = 60_000;
const TOLLERANZA_ESTREMO_INIZIO_MS = BUCKET_SERVER_PRE_MAX_MS + BUCKET_BARRA_MS;
const TOLLERANZA_ESTREMO_FINE_MS = BUCKET_SERVER_IN_MAX_MS + BUCKET_BARRA_MS;
const TOLLERANZA_ESTREMO_FINE_PRE_MS = BUCKET_SERVER_PRE_MAX_MS + BUCKET_BARRA_MS;
const TOLLERANZA_KICKOFF_META_MS = BUCKET_SERVER_IN_MAX_MS + BUCKET_BARRA_MS;
const TOLLERANZA_KICKOFF_DICHIARATO_MS = 120_000;
const RITARDO_KICKOFF_MAX_MS = 60_000;
const SOGLIA_BUCO_IN_GIOCO_MS = 75_000;
const SOGLIA_BUCO_PRE_MS = BUCKET_SERVER_PRE_MAX_MS + BUCKET_BARRA_MS + 20_000;
const MAX_NOTE_BUCHI = 30;

// ----------------------------------------------------------------------------
// utilita'
// ----------------------------------------------------------------------------
const msDi = (ts: string): number => Date.parse(ts);
const ordTs = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** "19:30:11 UTC" da un ISO (o il testo stesso se non e' una data). */
export function oraUtc(ts: string | null | undefined): string {
    if (!ts) return '?';
    const m = Date.parse(ts);
    return Number.isFinite(m) ? `${new Date(m).toISOString().slice(11, 19)} UTC` : ts;
}
function durata(ms: number): string {
    const s = Math.round(Math.abs(ms) / 1000);
    if (s < 120) return `${s} s`;
    const m = Math.floor(s / 60);
    return m < 120 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function creaRilievo(
    codice: CodiceRilievo,
    gravita: GravitaRilievo,
    spiegazione: string,
    extra: { ambito?: AmbitoRilievo; istante?: string | null; passo?: number | null; minuto?: number | null; occorrenze?: number; perDati?: string } = {},
): Rilievo {
    const r: Rilievo = {
        codice, gravita, ambito: extra.ambito ?? 'generico', spiegazione,
        istante: extra.istante ?? null, passo: extra.passo ?? null, minuto: extra.minuto ?? null,
        occorrenze: extra.occorrenze ?? 1,
    };
    // la chiave c'e' solo quando serve: i rilievi di sempre restano identici
    if (extra.perDati) r.perDati = extra.perDati;
    return r;
}

/** 08/10 (cantiere 13): la partita ha incoerenze e sono TUTTE dichiarate "per dati" (classe c). */
export function soloPerDati(e: Pick<EsitoVerificaBarra, 'incoerenze'>): boolean {
    return e.incoerenze.length > 0 && e.incoerenze.every(r => !!r.perDati);
}

// ----------------------------------------------------------------------------
// 1. COSTRUTTORI DELLA BARRA (stessa logica della pagina `MatchReplay.tsx`)
// ----------------------------------------------------------------------------

/** Passi della barra: UN passo per ogni bucket da 10 s di orologio con almeno un frame
 *  di un mercato qualsiasi; il passo prende il ts e il minuto del primo frame del
 *  bucket nell'ordine di arrivo (e il primo minuto non nullo); ordinati per ts.
 *  Copia fedele del `useMemo` `timeline` di `MatchReplay.tsx`. */
export function passiBarra(
    frames: ReadonlyArray<Pick<Frame, 'ts' | 'minute'>>,
    bucketMs: number = BUCKET_BARRA_MS,
): PassoBarra[] {
    const byBucket = new Map<number, PassoBarra>();
    for (const f of frames) {
        const b = Math.floor(new Date(f.ts).getTime() / bucketMs);
        const cur = byBucket.get(b);
        if (!cur) byBucket.set(b, { ts: f.ts, minute: f.minute });
        else if (cur.minute == null && f.minute != null) cur.minute = f.minute;
    }
    return Array.from(byBucket.values()).sort((a, b) => ordTs(a.ts, b.ts));
}

/** Calcio d'inizio: primo frame con `inplay === true` (flag di MERCATO Betfair, l'unica
 *  fonte affidabile); ripiego: primo frame in assoluto. Copia fedele del `useMemo`
 *  `kickoffTs` di `MatchReplay.tsx`. */
export function kickoffTsDaFrame(frames: ReadonlyArray<Pick<Frame, 'ts' | 'inplay'>>): string | null {
    const sorted = [...frames].sort((a, b) => ordTs(a.ts, b.ts));
    const ip = sorted.find(f => f.inplay === true);
    return ip?.ts ?? sorted[0]?.ts ?? null;
}

/** Indice del calcio d'inizio sulla barra: primo passo con ts >= kickoffTs (0 se non
 *  determinabile). Copia fedele del `useMemo` `kickoffIndex` di `MatchReplay.tsx`. */
export function kickoffIndexSuPassi(passi: ReadonlyArray<{ ts: string }>, kickoffTs: string | null): number {
    if (!kickoffTs || passi.length === 0) return 0;
    let lo = 0, hi = passi.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (passi[mid].ts < kickoffTs) lo = mid + 1; else hi = mid;
    }
    return Math.min(lo, passi.length - 1);
}

/** Segmenti di sospensione: per ogni passo, il Match Odds e' SUSPENDED? (ultimo frame
 *  del Match Odds con ts <= passo; se la partita non ha un Match Odds, QUALSIASI mercato
 *  sospeso). Copia fedele del `useMemo` `suspended` di `MatchReplay.tsx`. */
export function sospesiPerPasso(
    passi: ReadonlyArray<{ ts: string }>,
    frames: ReadonlyArray<Frame | FrameBarra>,
    markets: ReadonlyArray<Pick<Market, 'market_id' | 'market_type'>>,
): boolean[] {
    const perMercato = new Map<string, (Frame | FrameBarra)[]>();
    for (const f of frames) {
        const arr = perMercato.get(f.market_id) ?? [];
        arr.push(f);
        perMercato.set(f.market_id, arr);
    }
    for (const arr of perMercato.values()) arr.sort((a, b) => ordTs(a.ts, b.ts));
    const statoA = (arr: ReadonlyArray<Frame | FrameBarra> | undefined, ts: string): string | null => {
        if (!arr || arr.length === 0 || !ts) return null;
        let lo = 0, hi = arr.length;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (arr[mid].ts <= ts) lo = mid + 1; else hi = mid;
        }
        return lo > 0 ? arr[lo - 1].status : null;
    };
    const ids = idMercatiSospensione(markets);
    return passi.map(step => {
        if (ids.length > 0) return ids.some(id => statoA(perMercato.get(id), step.ts) === 'SUSPENDED');
        for (const arr of perMercato.values()) if (statoA(arr, step.ts) === 'SUSPENDED') return true;
        return false;
    });
}

/** Id dei mercati MATCH_ODDS del catalogo (vuoto = nessuno: conta qualsiasi mercato). */
export function idMercatiSospensione(markets: ReadonlyArray<Pick<Market, 'market_id' | 'market_type'>>): string[] {
    return markets.filter(m => (m.market_type || '').toUpperCase() === 'MATCH_ODDS').map(m => m.market_id);
}

// ----------------------------------------------------------------------------
// 2. CONTROLLI GENERICI
// ----------------------------------------------------------------------------

/** primo passo con ts >= istante (e' il passo in cui un fatto diventa visibile
 *  scorrendo la barra); ultimo passo se l'istante e' dopo l'ultimo. Scansione
 *  su millisecondi: volutamente DIVERSA dalla bisect su stringhe della pagina. */
export function passoVisibile(msPassi: ReadonlyArray<number>, istanteMs: number): number {
    for (let i = 0; i < msPassi.length; i++) if (msPassi[i] >= istanteMs) return i;
    return msPassi.length - 1;
}

export function verificaBarraGenerica(b: BarraDaVerificare): Rilievo[] {
    const ambito = b.ambito ?? 'generico';
    const out: Rilievo[] = [];
    const R = (codice: CodiceRilievo, gravita: GravitaRilievo, spiegazione: string,
        extra: { istante?: string | null; passo?: number | null; minuto?: number | null; occorrenze?: number; perDati?: string } = {}) => {
        const passo = extra.passo ?? null;
        out.push(creaRilievo(codice, gravita, spiegazione, {
            ambito, istante: extra.istante ?? null, passo,
            minuto: extra.minuto ?? (passo != null ? b.passi[passo]?.minute ?? null : null),
            occorrenze: extra.occorrenze, perDati: extra.perDati,
        }));
    };
    const passi = b.passi;
    const n = passi.length;

    if (b.frames.length === 0 || n === 0) {
        R('NESSUN_FRAME', 'errore', 'La partita non ha nessun frame registrato: non c\'e\' nessuna barra da verificare.');
        return out;
    }

    // --- ts leggibili e ordine delle stringhe (la pagina ordina CONFRONTANDO LE STRINGHE) ---
    const nonValidi = b.frames.filter(f => !Number.isFinite(msDi(f.ts)));
    if (nonValidi.length > 0) {
        R('TS_NON_VALIDO', 'errore',
            `${nonValidi.length} frame hanno un orario illeggibile (es. "${nonValidi[0].ts}"): la pagina li mette in un bucket sbagliato.`,
            { occorrenze: nonValidi.length });
    }
    const validi = b.frames.filter(f => Number.isFinite(msDi(f.ts)));
    const perStringa = [...validi].sort((x, y) => ordTs(x.ts, y.ts));
    for (let i = 1; i < perStringa.length; i++) {
        if (msDi(perStringa[i].ts) < msDi(perStringa[i - 1].ts)) {
            R('TS_ORDINE_STRINGHE', 'errore',
                `Gli orari dei frame non sono tutti nello stesso formato: "${perStringa[i - 1].ts}" viene PRIMA di "${perStringa[i].ts}" come testo ma DOPO come orario. `
                + 'La pagina ordina i frame come testo, quindi la barra e il ladder possono andare fuori tempo.',
                { istante: perStringa[i].ts });
            break;
        }
    }
    const msPassi = passi.map(p => msDi(p.ts));
    for (let i = 1; i < n; i++) {
        if (!(msPassi[i] > msPassi[i - 1])) {
            R('PASSI_NON_ORDINATI', 'errore',
                `I passi della barra non sono in ordine di tempo (passo ${i - 1} alle ${oraUtc(passi[i - 1].ts)}, passo ${i} alle ${oraUtc(passi[i].ts)}).`,
                { passo: i, istante: passi[i].ts });
            break;
        }
    }
    const msFrames = validi.map(f => msDi(f.ts));
    const minF = Math.min(...msFrames);
    const maxF = Math.max(...msFrames);

    // --- estremi ---
    if (msPassi[0] - minF < 0 || msPassi[0] - minF >= BUCKET_BARRA_MS) {
        R('ESTREMO_INIZIO', 'errore',
            `Il primo passo della barra (${oraUtc(passi[0].ts)}) non e' il primo frame della registrazione (${oraUtc(new Date(minF).toISOString())}): scarto ${durata(msPassi[0] - minF)}.`,
            { passo: 0, istante: passi[0].ts });
    }
    if (maxF - msPassi[n - 1] < 0 || maxF - msPassi[n - 1] >= BUCKET_BARRA_MS) {
        R('ESTREMO_FINE', 'errore',
            `L'ultimo passo della barra (${oraUtc(passi[n - 1].ts)}) non e' l'ultimo frame della registrazione (${oraUtc(new Date(maxF).toISOString())}): scarto ${durata(maxF - msPassi[n - 1])}.`,
            { passo: n - 1, istante: passi[n - 1].ts });
    }
    const est = b.estremi ?? null;
    const tsMin = est?.ts_min ? msDi(est.ts_min) : NaN;
    const tsMax = est?.ts_max ? msDi(est.ts_max) : NaN;
    const inplayMeta = est?.inplay_from_ts ? msDi(est.inplay_from_ts) : NaN;
    if (Number.isFinite(tsMin) && Number.isFinite(tsMax)) {
        const fuori = validi.filter(f => msDi(f.ts) < tsMin || msDi(f.ts) > tsMax);
        if (fuori.length > 0) {
            R('FRAME_FUORI_ESTREMI', 'errore',
                `${fuori.length} frame stanno fuori dagli estremi dichiarati dalla registrazione (${oraUtc(est?.ts_min)} - ${oraUtc(est?.ts_max)}), es. alle ${oraUtc(fuori[0].ts)}.`,
                { occorrenze: fuori.length, istante: fuori[0].ts });
        }
        // pre-match caricato al massimo 4 ore prima del kickoff (live.ts)
        const tsMinEff = Number.isFinite(inplayMeta) && inplayMeta - tsMin > PRE_MATCH_MAX_MS ? inplayMeta - PRE_MATCH_MAX_MS : tsMin;
        if (msPassi[0] - tsMinEff > TOLLERANZA_ESTREMO_INIZIO_MS) {
            R('ESTREMO_INIZIO', 'errore',
                `La barra inizia ${durata(msPassi[0] - tsMinEff)} dopo l'inizio della registrazione (${oraUtc(new Date(tsMinEff).toISOString())}): i primi frame non sono arrivati alla pagina.`,
                { passo: 0, istante: passi[0].ts });
        }
        const tolleranzaFine = Number.isFinite(inplayMeta) ? TOLLERANZA_ESTREMO_FINE_MS : TOLLERANZA_ESTREMO_FINE_PRE_MS;
        if (tsMax - msPassi[n - 1] > tolleranzaFine) {
            R('ESTREMO_FINE', 'errore',
                `La barra finisce ${durata(tsMax - msPassi[n - 1])} prima della fine della registrazione (${oraUtc(est?.ts_max)}): gli ultimi frame non sono arrivati alla pagina.`,
                { passo: n - 1, istante: passi[n - 1].ts });
        }
    }

    // --- simboli ---
    const span = Math.max(1, n - 1);
    let ordinati = true;
    b.simboli.forEach((s, k) => {
        const quando = oraUtc(s.ts);
        const nome = `${s.label ?? s.kind}${s.minute != null ? ` (${s.minute}')` : ''} delle ${quando}`;
        if (!Number.isFinite(s.pctLeft) || s.pctLeft < 0 || s.pctLeft > 1) {
            R('SIMBOLO_FUORI_BARRA', 'errore',
                `Il simbolo "${nome}" e' disegnato fuori dalla barra (posizione ${s.pctLeft}).`, { istante: s.ts });
            return;
        }
        const t = msDi(s.ts);
        if (!Number.isFinite(t)) {
            R('TS_NON_VALIDO', 'errore', `Il simbolo "${nome}" ha un orario illeggibile.`, { istante: s.ts });
            return;
        }
        if (t < msPassi[0] || t > msPassi[n - 1]) {
            R('SIMBOLO_FUORI_REGISTRAZIONE', 'errore',
                `Il simbolo "${nome}" e' di un fatto FUORI dalla registrazione (la barra va da ${oraUtc(passi[0].ts)} a ${oraUtc(passi[n - 1].ts)}): sulla barra finirebbe incollato a un estremo.`,
                { istante: s.ts });
            return;
        }
        const x = s.pctLeft * span;
        const idx = Math.round(x);
        const atteso = passoVisibile(msPassi, t);
        if (Math.abs(x - idx) > 1e-6) {
            R('SIMBOLO_POSIZIONE', 'errore',
                `Il simbolo "${nome}" non sta su un passo della barra (posizione ${(s.pctLeft * 100).toFixed(3)}%).`, { istante: s.ts });
        } else if (idx < atteso) {
            R('SIMBOLO_PRIMA_DELL_ISTANTE', 'errore',
                `Il simbolo "${nome}" compare al passo ${idx} (${oraUtc(passi[idx].ts)}), PRIMA dell'istante del fatto: dovrebbe comparire al passo ${atteso} (${oraUtc(passi[atteso].ts)}).`,
                { istante: s.ts, passo: idx });
        } else if (idx > atteso) {
            R('SIMBOLO_POSIZIONE', 'errore',
                `Il simbolo "${nome}" sta ${idx - atteso} passi dopo il suo istante: e' al passo ${idx} (${oraUtc(passi[idx].ts)}) invece che al ${atteso} (${oraUtc(passi[atteso].ts)}).`,
                { istante: s.ts, passo: idx });
        }
        if (k > 0) {
            const p = b.simboli[k - 1];
            if (ordTs(p.ts, s.ts) > 0 || p.pctLeft > s.pctLeft + 1e-12) ordinati = false;
        }
    });
    if (!ordinati) {
        R('SIMBOLO_NON_ORDINATO', 'errore', 'I simboli non sono in ordine di tempo: la barra e la legenda li mostrerebbero alla rinfusa.');
    }

    // --- calcio d'inizio ---
    const inplayMs = validi.filter(f => f.inplay === true).map(f => msDi(f.ts));
    const kickoffAtteso = inplayMs.length > 0 ? Math.min(...inplayMs) : minF;
    const kMs = b.kickoffTs ? msDi(b.kickoffTs) : NaN;
    if (!Number.isFinite(kMs) || kMs !== kickoffAtteso) {
        R('KICKOFF_FUORI_POSTO', 'errore',
            `Il calcio d'inizio e' a ${b.kickoffTs ? oraUtc(b.kickoffTs) : 'nessun istante'} ma il primo frame in gioco e' alle ${oraUtc(new Date(kickoffAtteso).toISOString())}.`,
            { istante: b.kickoffTs });
    }
    const kIdxAtteso = passoVisibile(msPassi, kickoffAtteso);
    if (b.kickoffIndex !== kIdxAtteso) {
        R('KICKOFF_FUORI_POSTO', 'errore',
            `La lineetta del calcio d'inizio sta al passo ${b.kickoffIndex} (${oraUtc(passi[b.kickoffIndex]?.ts)}) invece che al passo ${kIdxAtteso} (${oraUtc(passi[kIdxAtteso].ts)}), il primo con orario >= primo frame in gioco.`,
            { passo: b.kickoffIndex });
    } else if (msPassi[kIdxAtteso] - kickoffAtteso > RITARDO_KICKOFF_MAX_MS) {
        R('KICKOFF_IN_RITARDO', 'avviso',
            `Il primo passo della barra dopo il calcio d'inizio e' ${durata(msPassi[kIdxAtteso] - kickoffAtteso)} dopo il primo frame in gioco (${oraUtc(new Date(kickoffAtteso).toISOString())}): c'e' un buco della registrazione proprio al fischio d'inizio.`,
            { passo: kIdxAtteso });
    }
    if (Number.isFinite(inplayMeta)) {
        if (kickoffAtteso < inplayMeta || kickoffAtteso - inplayMeta > TOLLERANZA_KICKOFF_META_MS) {
            R('KICKOFF_DIVERSO_DA_META', 'errore',
                `Il primo frame in gioco che arriva alla pagina (${oraUtc(new Date(kickoffAtteso).toISOString())}) differisce dal primo in gioco dichiarato dalla registrazione (${oraUtc(est?.inplay_from_ts)}) di ${durata(kickoffAtteso - inplayMeta)}.`,
                { istante: est?.inplay_from_ts ?? null });
        }
    }
    if (b.inizioDichiarato) {
        const d = msDi(b.inizioDichiarato);
        // solo se l'inizio dichiarato sta DENTRO la registrazione (un feed che dichiara un
        // inizio precedente alla registrazione non si puo' confrontare con il primo frame)
        if (Number.isFinite(d) && d >= msPassi[0] && d <= msPassi[n - 1]
            && Math.abs(d - kickoffAtteso) > TOLLERANZA_KICKOFF_DICHIARATO_MS) {
            R('KICKOFF_DISCORDANTE', 'avviso',
                `L'inizio partita dichiarato dal feed e' alle ${oraUtc(b.inizioDichiarato)} ma la lineetta del calcio d'inizio (primo frame in gioco del mercato) e' alle ${oraUtc(new Date(kickoffAtteso).toISOString())}: scarto ${durata(d - kickoffAtteso)}.`,
                { istante: b.inizioDichiarato, perDati: motivoKickoffDiscordante(validi, d, kickoffAtteso) });
        }
    }
    const minutoIniziale = passi[kIdxAtteso]?.minute ?? null;
    if (kIdxAtteso === 0 && minutoIniziale != null && minutoIniziale > 3) {
        R('INIZIO_IN_CORSO', 'nota',
            `La registrazione inizia a partita in corso (minuto ${minutoIniziale}' al primo passo): i fatti precedenti non hanno un istante sulla barra.`,
            { passo: 0 });
    }

    // --- sospensioni ---
    if (b.sospesi.length !== n) {
        R('SOSPENSIONE_LUNGHEZZA', 'errore',
            `I segmenti di sospensione sono ${b.sospesi.length} ma i passi della barra sono ${n}: i segmenti non corrispondono ai passi.`);
    } else {
        const ordinatiPerMs = validi
            .map((f, i) => ({ f, i, t: msDi(f.ts) }))
            .sort((x, y) => x.t - y.t || x.i - y.i);
        const guida = b.mercatiSospensione && b.mercatiSospensione.length > 0 ? new Set(b.mercatiSospensione) : null;
        // oracolo: per ogni passo, ultimo frame <= passo di ciascun mercato guida; sospeso se ne basta uno
        const ultimoStato = new Map<string, string>();
        let cursore = 0;
        const discordi: number[] = [];
        for (let i = 0; i < n; i++) {
            while (cursore < ordinatiPerMs.length && ordinatiPerMs[cursore].t <= msPassi[i]) {
                const f = ordinatiPerMs[cursore].f;
                if (!guida || guida.has(f.market_id)) ultimoStato.set(f.market_id, f.status);
                cursore += 1;
            }
            const sospeso = [...ultimoStato.values()].some(s => s === 'SUSPENDED');
            if (sospeso !== b.sospesi[i]) discordi.push(i);
        }
        if (discordi.length > 0) {
            const i = discordi[0];
            R('SOSPENSIONE_DISCORDANTE', 'errore',
                `${discordi.length} passi mostrano un segmento di sospensione diverso dallo stato del mercato (primo: passo ${i} alle ${oraUtc(passi[i].ts)}, la barra dice ${b.sospesi[i] ? 'sospeso' : 'non sospeso'}, lo stato registrato dice il contrario).`,
                { passo: i, istante: passi[i].ts, occorrenze: discordi.length });
        }
        if (Number.isFinite(tsMin) && Number.isFinite(tsMax)) {
            const fuori = b.sospesi.map((s, i) => (s && (msPassi[i] < tsMin || msPassi[i] > tsMax) ? i : -1)).filter(i => i >= 0);
            if (fuori.length > 0) {
                R('SOSPENSIONE_FUORI_ESTREMI', 'errore',
                    `${fuori.length} segmenti di sospensione stanno fuori dagli estremi della registrazione (primo: passo ${fuori[0]}).`,
                    { passo: fuori[0], occorrenze: fuori.length });
            }
        }
        // sospensioni cosi' brevi da cadere fra due passi: non disegnabili (dichiarato, non incoerenza)
        const ivl: { da: number; a: number }[] = [];
        let apertaDa: number | null = null;
        let ultimoT = -Infinity;
        for (const { f, t } of ordinatiPerMs) {
            if (guida && !guida.has(f.market_id)) continue;
            if (f.status === 'SUSPENDED' && apertaDa == null) apertaDa = t;
            else if (f.status !== 'SUSPENDED' && apertaDa != null) { ivl.push({ da: apertaDa, a: t }); apertaDa = null; }
            ultimoT = t;
        }
        if (apertaDa != null) ivl.push({ da: apertaDa, a: ultimoT + 1 });
        const invisibili = ivl.filter(v => !msPassi.some(m => m >= v.da && m < v.a));
        if (invisibili.length > 0) {
            const lunga = invisibili.reduce((x, y) => (y.a - y.da > x.a - x.da ? y : x));
            R('SOSPENSIONE_NON_VISIBILE', 'nota',
                `${invisibili.length} sospensioni del mercato sono cosi' brevi (la piu' lunga ${durata(lunga.a - lunga.da)}) da cadere fra due passi della barra: non si vedono come segmento rosso.`,
                { occorrenze: invisibili.length, istante: new Date(lunga.da).toISOString() });
        }
    }

    // --- buchi della registrazione (dichiarati) ---
    let nBuchi = 0;
    for (let i = 0; i + 1 < n; i++) {
        const gap = msPassi[i + 1] - msPassi[i];
        const preMatch = i + 1 <= b.kickoffIndex;
        if (gap >= (preMatch ? SOGLIA_BUCO_PRE_MS : SOGLIA_BUCO_IN_GIOCO_MS)) {
            nBuchi += 1;
            if (nBuchi <= MAX_NOTE_BUCHI) {
                R('BUCO_REGISTRAZIONE', 'nota',
                    `Buco della registrazione di ${durata(gap)} fra le ${oraUtc(passi[i].ts)} e le ${oraUtc(passi[i + 1].ts)}${preMatch ? ' (pre-match)' : ''}: la barra e' a indice, qui salta da un passo al successivo.`,
                    { passo: i, istante: passi[i].ts });
            }
        }
    }
    if (nBuchi > MAX_NOTE_BUCHI) {
        R('BUCO_REGISTRAZIONE', 'nota', `... e altri ${nBuchi - MAX_NOTE_BUCHI} buchi della registrazione.`, { occorrenze: nBuchi - MAX_NOTE_BUCHI });
    }

    return out;
}

/** 08/10 (cantiere 13): KICKOFF_DISCORDANTE confronta DUE DATI registrati (il flag in gioco del
 *  mercato, che la pagina usa per la lineetta, e il KickOff del feed): la pagina e' gia' controllata
 *  da KICKOFF_FUORI_POSTO, quindi la discordanza e' SEMPRE dei dati (classe c). Il motivo dice quale:
 *  un buco della registrazione (nessun frame fra l'inizio dichiarato e il primo frame in gioco: il
 *  passaggio in gioco non e' nei dati caricati) oppure frame registrati con il
 *  mercato NON in gioco dopo l'inizio dichiarato (o in gioco prima): le due fonti non concordano. */
function motivoKickoffDiscordante(frames: ReadonlyArray<FrameBarra>, dichiaratoMs: number, kickoffMs: number): string {
    const quando = (ms: number): string => oraUtc(new Date(ms).toISOString());
    if (dichiaratoMs < kickoffMs) {
        const fra = frames.filter(f => { const t = msDi(f.ts); return t >= dichiaratoMs && t < kickoffMs; });
        if (fra.length === 0) {
            const prima = frames.map(f => msDi(f.ts)).filter(t => t < dichiaratoMs);
            const da = prima.length > 0 ? Math.max(...prima) : null;
            return `buco della registrazione${da != null ? ` fra le ${quando(da)}` : ''} e le ${quando(kickoffMs)}: nessun frame registrato `
                + `fra l'inizio dichiarato dal feed (${quando(dichiaratoMs)}) e il primo frame in gioco. Il passaggio in gioco del mercato `
                + 'non e\' nei dati caricati: la lineetta sta sul primo passo dopo il buco (se il raw lo ha, la rigenerazione dal raw lo ripristina).';
        }
        return `${fra.length} frame registrati fra l'inizio dichiarato dal feed (${quando(dichiaratoMs)}) e le ${quando(kickoffMs)} hanno `
            + 'il mercato NON in gioco: il KickOff del feed e il flag in gioco del mercato non concordano. La lineetta segue il flag '
            + 'del mercato (fonte della pagina).';
    }
    return `il mercato e' in gioco dalle ${quando(kickoffMs)}, il feed dichiara l'inizio alle ${quando(dichiaratoMs)}: il KickOff del feed `
        + 'e il flag in gioco del mercato non concordano. La lineetta segue il flag del mercato (fonte della pagina).';
}

/** Numero di buchi dichiarati (le note BUCO_REGISTRAZIONE con il loro raggruppamento). */
export function contaBuchi(rilievi: ReadonlyArray<Rilievo>): number {
    return rilievi.filter(r => r.codice === 'BUCO_REGISTRAZIONE').reduce((s, r) => s + r.occorrenze, 0);
}

/** Ordina i rilievi per istante (poi per gravita'): e' l'ordine del referto. */
export function ordinaRilievi(rilievi: ReadonlyArray<Rilievo>): Rilievo[] {
    const peso: Record<GravitaRilievo, number> = { errore: 0, avviso: 1, nota: 2 };
    return [...rilievi].sort((a, b) => {
        const ta = a.istante ? msDi(a.istante) : Infinity;
        const tb = b.istante ? msDi(b.istante) : Infinity;
        return (ta === tb ? 0 : ta < tb ? -1 : 1) || peso[a.gravita] - peso[b.gravita];
    });
}

/** Esito a partire dall'elenco dei rilievi. */
export function esitoDaRilievi(
    rilievi: ReadonlyArray<Rilievo>,
    conteggi: Omit<EsitoVerificaBarra['conteggi'], 'buchi'>,
): EsitoVerificaBarra {
    const tutti = ordinaRilievi(rilievi);
    const incoerenze = tutti.filter(r => r.gravita !== 'nota');
    return {
        rilievi: tutti,
        incoerenze,
        note: tutti.filter(r => r.gravita === 'nota'),
        ok: incoerenze.length === 0,
        conteggi: { ...conteggi, buchi: contaBuchi(tutti) },
    };
}
