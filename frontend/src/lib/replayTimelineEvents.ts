// ============================================================================
// replayTimelineEvents — i SIMBOLI della barra di avanzamento di Match Replay
// (gol ⚽, cartellini, angoli) dalla score_timeline del replay. PURA.
//
// Estratta da MatchReplay.tsx il 06/10 (stessa logica, stessi commenti) con tre
// correzioni di coerenza simboli/eventi:
//  1. ANGOLI anche con la timeline discreta: la timeline IPS di Betfair NON
//     porta i calci d'angolo (tipi visti: KickOff, Goal, YellowCard, RedCard,
//     FirstHalfEnd, ...), quindi con la timeline gli angoli sparivano e senza
//     comparivano: si derivano dai conteggi del punteggio in entrambi i casi.
//  2. GOL DAI DELTA contro il MASSIMO gia' visto: il punteggio arriva da due
//     fonti (betfair e api_football) e una in ritardo lo faceva "tornare
//     indietro" e risalire -> lo stesso gol disegnato due volte.
//  3. Il ROSSO da doppia ammonizione (tipi come SecondYellow/YellowRedCard)
//     era ignorato: ogni tipo che nomina "red" o "secondyellow" e' un rosso.
//
// Controllo del 07/10 (barra vs simboli, dati veri di due registrazioni), tre
// correzioni in piu':
//  4. PUNTEGGIO AL CURSORE (`punteggioAlTs`): le righe-evento della timeline
//     (Goal, YellowCard, FirstHalfEnd, SecondHalfEnd, ...) NON portano il
//     punteggio (score_home/away null). La pagina prendeva "l'ultima riga <= ts"
//     di QUALUNQUE tipo e leggeva `?? 0`: dopo ogni riga-evento il tabellone
//     tornava 0-0 (per tutto l'intervallo e a fine partita, "FT" compreso, con il
//     risultato finale sbagliato). Ora il punteggio e' quello dell'ultima riga
//     CHE LO PORTA; il minuto resta quello dell'ultima riga di qualunque tipo.
//  5. FUORI REGISTRAZIONE: un fatto con ts coerente ma PRIMA del primo frame (o
//     dopo l'ultimo) veniva incollato al 0% (o al 100%). Non ha un istante sulla
//     barra: nessun simbolo (come gia' per le ri-emissioni, punto c).
//  6. GOL NEL PUNTEGGIO MA NON NELLA TIMELINE: se la timeline discreta perde un
//     poll, il punteggio salta ma sulla barra non c'era nessun simbolo. Ora il
//     gol del punteggio senza un Goal discreto vicino (entro 3 minuti) si disegna
//     dal punteggio.
// ============================================================================

import type { ScoreEvent } from '@/lib/live';

export interface TimelineMarker {
    ts: string;
    pctLeft: number;
    kind: string;
    team?: string | null;
    minute: number | null;
    label: string;
}

function stepIndexFor(timeline: ReadonlyArray<{ ts: string }>, ts: string): number {
    let lo = 0, hi = timeline.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (timeline[mid].ts < ts) lo = mid + 1; else hi = mid;
    }
    return Math.min(lo, Math.max(0, timeline.length - 1));
}

// tipo discreto Betfair -> simbolo (null = fase di gioco, nessun simbolo)
export function kindDiTipo(tipo: string | null | undefined): 'goal' | 'yellow' | 'red' | 'corner' | null {
    const ty = String(tipo || '').toLowerCase().replace(/[^a-z]/g, '');
    if (!ty) return null;
    if (ty === 'goal' || ty === 'owngoal' || ty === 'penaltygoal') return 'goal';
    if (ty.includes('red') || ty.includes('secondyellow')) return 'red';
    if (ty.includes('yellow')) return 'yellow';
    if (ty === 'corner') return 'corner';
    return null;
}

// Punteggio e minuto mostrati al cursore (07/10). `sortedScoreTimeline` e' ordinata
// per ts. Il PUNTEGGIO e' quello dell'ultima riga con ts <= `ts` CHE LO PORTA
// (score_home e score_away valorizzati): le righe-evento della timeline non lo
// portano e non devono azzerarlo. Il MINUTO e' quello dell'ultima riga di
// qualunque tipo (anche un evento: FirstHalfEnd 51', SecondHalfEnd 98'); null =
// nessuna riga ancora (il chiamante ripiega sul minuto del frame).
export function punteggioAlTs(
    sortedScoreTimeline: ReadonlyArray<ScoreEvent>,
    ts: string,
): { home: number; away: number; minute: number | null } {
    let home = 0, away = 0;
    let minute: number | null = null;
    for (const ev of sortedScoreTimeline) {
        if (ev.ts > ts) break;
        minute = ev.minute;
        if (ev.score_home != null && ev.score_away != null) { home = ev.score_home; away = ev.score_away; }
    }
    return { home, away, minute };
}

// scarto massimo fra il ts di un Goal discreto e quello della riga del punteggio
// che lo mostra per considerarli lo STESSO gol (visti sui dati veri: <= 11 s).
const FINESTRA_GOL_MS = 180_000;
// il ts dell'ultimo passo e' il primo frame dell'ultimo bucket da 10 s: i fatti
// fino a un bucket dopo stanno ancora dentro la registrazione.
const BUCKET_FINALE_MS = 10_000;

export function timelineEventMarkers(
    sortedScoreTimeline: ReadonlyArray<ScoreEvent>,
    timeline: ReadonlyArray<{ ts: string }>,
    homeName: string,
    awayName: string,
    span: number,
): TimelineMarker[] {
    // mappa minuto→ts (prima occorrenza) e funzione ts→minuto dalle sole righe
    // PUNTEGGIO (score_home valorizzato): le righe-evento possono avere ts di
    // ri-emissione e inquinerebbero la mappa.
    const minuteTs = new Map<number, string>();
    const scoreRows: { ts: string; minute: number }[] = [];
    for (const ev of sortedScoreTimeline) {
        if (ev.score_home == null || ev.minute == null) continue;
        if (!minuteTs.has(ev.minute)) minuteTs.set(ev.minute, ev.ts);
        scoreRows.push({ ts: ev.ts, minute: ev.minute });
    }
    const minMapped = minuteTs.size > 0 ? Math.min(...minuteTs.keys()) : null;
    const minuteAt = (ts: string): number | null => {
        let best: number | null = null;
        for (const r of scoreRows) {
            if (r.ts <= ts) best = r.minute; else break;
        }
        return best;
    };
    // ts a cui posizionare un evento discreto; null = fuori registrazione.
    const placedTs = (ev: ScoreEvent): string | null => {
        if (ev.minute == null) return ev.ts;
        const implied = minuteAt(ev.ts);
        if (implied != null && Math.abs(implied - ev.minute) <= 2) return ev.ts; // ts coerente col minuto
        const mapped = minuteTs.get(ev.minute)
            ?? minuteTs.get(ev.minute + 1) ?? minuteTs.get(ev.minute - 1) ?? null;
        if (mapped) return mapped;
        if (minMapped != null && ev.minute < minMapped) return null; // prima della registrazione
        return ev.ts;
    };

    const out: TimelineMarker[] = [];
    const seen = new Set<string>(); // dedup ri-emissioni feed: kind|minuto|team
    const teamName = (t: string | null | undefined) => (t === 'home' ? homeName : t === 'away' ? awayName : null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const numH = (p: any, k: string) => Number(p?.score?.home?.[k] ?? 0) || 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const numA = (p: any, k: string) => Number(p?.score?.away?.[k] ?? 0) || 0;
    const add = (ev: ScoreEvent, kind: string, team: string | null, label: string) => {
        let ts: string | null = ev.ts;
        if (ev.event_type) { // solo gli eventi discreti hanno il problema dump/ri-emissione
            const key = `${kind}|${ev.minute ?? '?'}|${team ?? ''}`;
            if (seen.has(key)) {
                // chiave già vista: è quasi sempre una RI-EMISSIONE del feed (ts
                // incoerente col minuto). Ma una doppietta REALE nello stesso
                // minuto ha ts coerente → va tenuta, non deduplicata.
                const implied = ev.minute != null ? minuteAt(ev.ts) : null;
                const coherent = implied != null && ev.minute != null && Math.abs(implied - ev.minute) <= 2;
                if (!coherent) return;
            } else {
                seen.add(key);
            }
            ts = placedTs(ev);
            if (!ts) return;
        }
        // FUORI REGISTRAZIONE (07/10): prima del primo frame o oltre l'ultimo bucket
        // non esiste un istante della barra in cui il fatto sia avvenuto.
        if (timeline.length > 0) {
            const t = Date.parse(ts);
            const primo = Date.parse(timeline[0].ts);
            const ultimo = Date.parse(timeline[timeline.length - 1].ts);
            if (Number.isFinite(t) && Number.isFinite(primo) && Number.isFinite(ultimo)) {
                if (t < primo) return;
                if (t > ultimo + BUCKET_FINALE_MS) return;
                // dentro l'ultimo bucket: visibile all'ultimo passo (il filtro della
                // pagina e' `m.ts <= ts del cursore`)
                if (t > ultimo) ts = timeline[timeline.length - 1].ts;
            }
        }
        const idx = stepIndexFor(timeline, ts);
        out.push({ ts, pctLeft: Math.min(Math.max(idx / span, 0), 1), kind, team, minute: ev.minute, label });
    };

    // se ci sono eventi DISCRETI (get_event_timeline) usiamo SOLO quelli per gol e
    // cartellini; altrimenti deriviamo dai delta (punteggio → gol; conteggi
    // payload → cartellini). Gli ANGOLI (assenti dalla timeline IPS) si derivano
    // SEMPRE dai conteggi (06/10).
    const hasDiscrete = sortedScoreTimeline.some(e => !!e.event_type);
    const angoliDiscreti = sortedScoreTimeline.some(e => kindDiTipo(e.event_type) === 'corner');
    let maxHome = 0, maxAway = 0;
    let pYH = 0, pYA = 0, pRH = 0, pRA = 0, pCH = 0, pCA = 0;

    // GOL DISCRETI col ts a cui verranno posizionati (07/10): servono a capire,
    // quando il punteggio sale, se la timeline ha gia' il Goal o se l'ha perso.
    const golDiscreti: { team: string | null; ms: number; preso: boolean }[] = [];
    if (hasDiscrete) {
        for (const e of sortedScoreTimeline) {
            if (kindDiTipo(e.event_type) !== 'goal') continue;
            const pt = placedTs(e);
            if (!pt) continue;
            golDiscreti.push({ team: (e.payload as { team?: string | null } | undefined)?.team ?? null, ms: Date.parse(pt), preso: false });
        }
    }
    const golDalPunteggio = (ev: ScoreEvent, team: 'home' | 'away', quanti: number) => {
        const msRiga = Date.parse(ev.ts);
        if (!Number.isFinite(msRiga)) return;
        for (let k = 0; k < quanti; k++) {
            let best = -1, bestD = Infinity;
            golDiscreti.forEach((g, j) => {
                if (g.preso || (g.team != null && g.team !== team)) return;
                const d = Math.abs(g.ms - msRiga);
                if (d <= FINESTRA_GOL_MS && d < bestD) { best = j; bestD = d; }
            });
            if (best >= 0) golDiscreti[best].preso = true; // c'e' gia' il Goal della timeline
            else add(ev, 'goal', team, `Gol ${teamName(team)}`); // la timeline l'ha perso
        }
    };

    for (const ev of sortedScoreTimeline) {
        // le righe-evento discrete non portano il punteggio: restano al massimo visto
        const curHome = ev.score_home ?? maxHome;
        const curAway = ev.score_away ?? maxAway;
        // 06/10: delta contro il MASSIMO visto (mai un gol due volte se una fonte
        // in ritardo fa scendere e risalire il punteggio)
        const dHome = curHome - maxHome;
        const dAway = curAway - maxAway;

        if (hasDiscrete) {
            if (ev.event_type) {
                const kind = kindDiTipo(ev.event_type);
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const pTeam = (ev.payload as any)?.team ?? null;
                if (kind === 'goal') {
                    const team = pTeam ?? (dHome > 0 ? 'home' : dAway > 0 ? 'away' : null);
                    const who = teamName(team);
                    add(ev, 'goal', team, who ? `Gol ${who}` : 'Gol');
                } else if (kind === 'yellow') {
                    const who = teamName(pTeam);
                    add(ev, 'yellow', pTeam, who ? `Giallo ${who}` : 'Cartellino giallo');
                } else if (kind === 'red') {
                    const who = teamName(pTeam);
                    add(ev, 'red', pTeam, who ? `Rosso ${who}` : 'Cartellino rosso');
                } else if (kind === 'corner') {
                    const who = teamName(pTeam);
                    add(ev, 'corner', pTeam, who ? `Angolo ${who}` : "Calcio d'angolo");
                }
                // KickOff/HalfTime/... = fasi: non renderizzate.
            } else {
                // GOL del punteggio che la timeline discreta non ha (07/10)
                if (dHome > 0) golDalPunteggio(ev, 'home', dHome);
                if (dAway > 0) golDalPunteggio(ev, 'away', dAway);
                if (!angoliDiscreti) {
                    // ANGOLI dai conteggi del punteggio (la timeline IPS non li porta)
                    const ch = numH(ev.payload, 'numberOfCorners'), ca = numA(ev.payload, 'numberOfCorners');
                    if (ch > pCH) add(ev, 'corner', 'home', `Angolo ${homeName}`);
                    if (ca > pCA) add(ev, 'corner', 'away', `Angolo ${awayName}`);
                    pCH = Math.max(pCH, ch); pCA = Math.max(pCA, ca);
                }
            }
        } else {
            // GOL dai delta di punteggio
            if (dHome > 0) add(ev, 'goal', 'home', `Gol ${homeName}`);
            if (dAway > 0) add(ev, 'goal', 'away', `Gol ${awayName}`);
            // CARTELLINI / ANGOLI dai conteggi cumulativi nel payload
            const yh = numH(ev.payload, 'numberOfYellowCards'), ya = numA(ev.payload, 'numberOfYellowCards');
            const rh = numH(ev.payload, 'numberOfRedCards'), ra = numA(ev.payload, 'numberOfRedCards');
            const ch = numH(ev.payload, 'numberOfCorners'), ca = numA(ev.payload, 'numberOfCorners');
            if (yh > pYH) add(ev, 'yellow', 'home', `Giallo ${homeName}`);
            if (ya > pYA) add(ev, 'yellow', 'away', `Giallo ${awayName}`);
            if (rh > pRH) add(ev, 'red', 'home', `Rosso ${homeName}`);
            if (ra > pRA) add(ev, 'red', 'away', `Rosso ${awayName}`);
            if (ch > pCH) add(ev, 'corner', 'home', `Angolo ${homeName}`);
            if (ca > pCA) add(ev, 'corner', 'away', `Angolo ${awayName}`);
            pYH = Math.max(pYH, yh); pYA = Math.max(pYA, ya);
            pRH = Math.max(pRH, rh); pRA = Math.max(pRA, ra);
            pCH = Math.max(pCH, ch); pCA = Math.max(pCA, ca);
        }
        maxHome = Math.max(maxHome, curHome);
        maxAway = Math.max(maxAway, curAway);
    }
    // ordina per ts (il riposizionamento può aver spostato eventi ri-emessi)
    return out.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}
