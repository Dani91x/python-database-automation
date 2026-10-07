// ============================================================================
// !!! COPIA DIFETTOSA, SOLO PER FALSIFICARE IL VERIFICATORE DELLA BARRA !!!
// E' `lib/replayTimelineEvents.ts` cosi' com'era PRIMA del commit 94af2eb (07/10/2026)
// (`git show 94af2eb^:frontend/src/lib/replayTimelineEvents.ts`), con i soli caratteri
// non ASCII sostituiti. Contiene DI PROPOSITO due dei quattro difetti trovati quel giorno:
//   D3  un fatto fuori registrazione (prima del primo frame / dopo l'ultimo) viene
//       incollato al 0% / 100% della barra;
//   D4  con la timeline discreta, un gol presente nel punteggio ma assente dalla
//       timeline (poll perso) NON ha nessun simbolo.
// Il test `replayVerificaBarra.partite.test.ts` la passa al verificatore
// (`opzioni.funzioni.timelineEventMarkers`) e pretende che diventi ROSSO.
// NON importarla da codice di produzione. Non correggerla: deve restare difettosa.
// ============================================================================
// ============================================================================
// replayTimelineEvents - i SIMBOLI della barra di avanzamento di Match Replay
// (gol (gol), cartellini, angoli) dalla score_timeline del replay. PURA.
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

export function timelineEventMarkers(
    sortedScoreTimeline: ReadonlyArray<ScoreEvent>,
    timeline: ReadonlyArray<{ ts: string }>,
    homeName: string,
    awayName: string,
    span: number,
): TimelineMarker[] {
    // mappa minuto->ts (prima occorrenza) e funzione ts->minuto dalle sole righe
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
                // chiave gia vista: e quasi sempre una RI-EMISSIONE del feed (ts
                // incoerente col minuto). Ma una doppietta REALE nello stesso
                // minuto ha ts coerente -> va tenuta, non deduplicata.
                const implied = ev.minute != null ? minuteAt(ev.ts) : null;
                const coherent = implied != null && ev.minute != null && Math.abs(implied - ev.minute) <= 2;
                if (!coherent) return;
            } else {
                seen.add(key);
            }
            ts = placedTs(ev);
            if (!ts) return;
        }
        const idx = stepIndexFor(timeline, ts);
        out.push({ ts, pctLeft: Math.min(Math.max(idx / span, 0), 1), kind, team, minute: ev.minute, label });
    };

    // se ci sono eventi DISCRETI (get_event_timeline) usiamo SOLO quelli per gol e
    // cartellini; altrimenti deriviamo dai delta (punteggio -> gol; conteggi
    // payload -> cartellini). Gli ANGOLI (assenti dalla timeline IPS) si derivano
    // SEMPRE dai conteggi (06/10).
    const hasDiscrete = sortedScoreTimeline.some(e => !!e.event_type);
    const angoliDiscreti = sortedScoreTimeline.some(e => kindDiTipo(e.event_type) === 'corner');
    let maxHome = 0, maxAway = 0;
    let pYH = 0, pYA = 0, pRH = 0, pRA = 0, pCH = 0, pCA = 0;

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
            } else if (!angoliDiscreti) {
                // ANGOLI dai conteggi del punteggio (la timeline IPS non li porta)
                const ch = numH(ev.payload, 'numberOfCorners'), ca = numA(ev.payload, 'numberOfCorners');
                if (ch > pCH) add(ev, 'corner', 'home', `Angolo ${homeName}`);
                if (ca > pCA) add(ev, 'corner', 'away', `Angolo ${awayName}`);
                pCH = Math.max(pCH, ch); pCA = Math.max(pCA, ca);
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
    // ordina per ts (il riposizionamento puo aver spostato eventi ri-emessi)
    return out.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}
