// ============================================================================
// replayVerificaBarraDettaglio - le PROVE di ogni incoerenza della barra (08/10,
// cantiere 13). Per classificare un'incoerenza (a: verificatore, b: pagina, c: dati)
// servono le righe VERE attorno al fatto: le righe del punteggio (fonte, minuto,
// punteggio, conteggi), le righe-evento della timeline Betfair e i simboli che la
// pagina disegna. Questa funzione PURA le elenca per ogni incoerenza (non per le
// note); la usano `scripts/verifica_barra_replay.ts --dettaglio` (database, sola
// lettura) e `scripts/verifica_barra_fixture.ts --dettaglio` (fixture dal raw).
// Non decide nulla e non cambia l'esito: e' il materiale della prova scritta.
// ============================================================================
import type { ReplayData, ScoreEvent } from '@/lib/live';
import { timelineEventMarkers, type TimelineMarker } from '@/lib/replayTimelineEvents';
import { passiBarra, type EsitoVerificaBarra, type Rilievo } from '@/lib/replayVerificaBarra';

/** finestra attorno all'istante di un'incoerenza (prima e dopo) */
export const FINESTRA_DETTAGLIO_MS = 5 * 60_000;

const msDi = (ts: string): number => Date.parse(ts);
const ordTs = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

function campo(o: unknown, k: string): unknown {
    return o != null && typeof o === 'object' ? (o as Record<string, unknown>)[k] : undefined;
}
function conteggio(r: ScoreEvent, squadra: 'home' | 'away', chiave: string): string {
    const v = campo(campo(campo(r.payload, 'score'), squadra), chiave);
    return typeof v === 'number' && Number.isFinite(v) ? String(v) : '-';
}
function rigaPunteggio(r: ScoreEvent): string {
    if (r.event_type) {
        const team = campo(r.payload, 'team');
        return `     evento     ${r.ts}  ${r.event_type}  squadra=${team == null ? '-' : String(team)}  minuto=${r.minute ?? '-'}`;
    }
    const c = (k: string) => `${conteggio(r, 'home', k)}/${conteggio(r, 'away', k)}`;
    const punteggio = r.score_home != null && r.score_away != null ? `${r.score_home}-${r.score_away}` : 'senza punteggio';
    return `     punteggio  ${r.ts}  fonte=${r.source}  minuto=${r.minute ?? '-'}  ${punteggio}  gialli=${c('numberOfYellowCards')} rossi=${c('numberOfRedCards')} angoli=${c('numberOfCorners')}`;
}
const rigaSimbolo = (s: TimelineMarker): string =>
    `     simbolo    ${s.ts}  ${s.kind}  squadra=${s.team ?? '-'}  minuto=${s.minute ?? '-'}  "${s.label}"`;

const CARTELLINI = new Set(['yellow', 'red']);
const eCartellino = (tipo: string | null): boolean => /yellow|red/i.test(String(tipo ?? ''));

/** Le righe di prova di ogni incoerenza (errori e avvisi; le note no), in testo. */
export function dettaglioIncoerenze(replay: ReplayData, esito: EsitoVerificaBarra, finestraMs: number = FINESTRA_DETTAGLIO_MS): string[] {
    if (esito.incoerenze.length === 0) return [];
    const righe = [...(replay.score_timeline ?? [])].sort((a, b) => ordTs(a.ts, b.ts));
    const frames = replay.frames ?? [];
    const passi = passiBarra(frames);
    let simboli: TimelineMarker[] = [];
    try {
        simboli = passi.length > 0
            ? timelineEventMarkers(righe, passi, replay.event?.home_name || 'Casa', replay.event?.away_name || 'Ospiti', Math.max(1, passi.length - 1))
            : [];
    } catch {
        simboli = [];
    }
    const out: string[] = [];
    const vicino = (ts: string, t: number): boolean => { const m = msDi(ts); return Number.isFinite(m) && Math.abs(m - t) <= finestraMs; };

    const blocco = (r: Rilievo): void => {
        out.push(`  >> prove di ${r.codice}${r.istante ? ` (${r.istante})` : ''}:`);
        if (r.codice === 'CARTELLINI_DIVERSI') {
            // tutti i cartellini: righe-evento della timeline, righe del punteggio in cui un conteggio cambia, simboli
            let prec = '';
            for (const x of righe) {
                if (x.event_type) {
                    if (eCartellino(x.event_type)) out.push(rigaPunteggio(x));
                    continue;
                }
                const firma = ['numberOfYellowCards', 'numberOfRedCards']
                    .map(k => `${conteggio(x, 'home', k)}/${conteggio(x, 'away', k)}`).join(' ');
                if (firma !== prec) out.push(rigaPunteggio(x));
                prec = firma;
            }
            for (const s of simboli) if (CARTELLINI.has(s.kind)) out.push(rigaSimbolo(s));
            return;
        }
        if (r.codice.startsWith('KICKOFF_')) {
            for (const x of righe) if (/kickoff/i.test(String(x.event_type ?? ''))) out.push(rigaPunteggio(x));
            const ordinati = [...frames].sort((a, b) => ordTs(a.ts, b.ts));
            const primo = ordinati[0];
            const inGioco = ordinati.find(f => f.inplay === true);
            if (primo) out.push(`     frame      primo frame ${primo.ts}`);
            if (inGioco) out.push(`     frame      primo frame in gioco ${inGioco.ts} (mercato ${inGioco.market_id})`);
            // i passi della barra attorno al primo frame in gioco (un buco si vede qui)
            if (inGioco) {
                const k = passi.findIndex(p => p.ts >= inGioco.ts);
                for (let i = Math.max(0, k - 3); i <= Math.min(passi.length - 1, k + 1); i++) {
                    out.push(`     passo ${i}${i === k ? ' (lineetta)' : ''}  ${passi[i].ts}  minuto=${passi[i].minute ?? '-'}`);
                }
            }
            return;
        }
        if (!r.istante) {
            out.push('     (nessun istante: vedere la spiegazione)');
            return;
        }
        const t = msDi(r.istante);
        if (!Number.isFinite(t)) return;
        const attorno = righe.filter(x => vicino(x.ts, t));
        for (const x of attorno) out.push(rigaPunteggio(x));
        for (const s of simboli) if (vicino(s.ts, t)) out.push(rigaSimbolo(s));
        if (attorno.length === 0) out.push(`     nessuna riga del punteggio entro ${Math.round(finestraMs / 60_000)} minuti`);
        if (r.codice.includes('GOL') || r.codice.startsWith('TABELLONE')) {
            // gol: anche ogni CAMBIO del punteggio della partita (una correzione VAR puo' stare fuori finestra)
            out.push('     -- ogni cambio del punteggio (per fonte) e ogni Goal della timeline --');
            const ultimo = new Map<string, string>();
            for (const x of righe) {
                if (x.event_type) {
                    if (/goal/i.test(x.event_type)) out.push(rigaPunteggio(x));
                    continue;
                }
                if (x.score_home == null || x.score_away == null) continue;
                const p = `${x.score_home}-${x.score_away}`;
                if (ultimo.get(x.source) !== p) out.push(rigaPunteggio(x));
                ultimo.set(x.source, p);
            }
        }
    };
    for (const r of esito.incoerenze) blocco(r);
    return out;
}
