// ============================================================================
// mikeEsitoChiusura.ts - L'ESITO DELLA CHIUSURA DI UNA PARTITA DI MIKE
// (piano Mike 29/09, M7.2). Funzione PURA: legge SOLO cio' che il bot pubblica
// gia' sulla riga della partita (`mike_events`: `state`, `positions` = le gambe
// con chiesto/abbinato/prezzo medio/stato, `ctx.close_reason`, `ctx.attempts`,
// `ctx.flatten_pending`, `ctx.no_reentry`, `live.locked`, `live.pnl_totale_by_total`,
// `live.goals`, `live.published_ts`). Nessuna lettura nuova, nessun dato inventato.
//
// Parole dell'utente (29/09): «mi deve essere restituita dalla scheda il fatto
// che il cash out sia effettivamente stato fatto e che su quell'evento non
// abbiamo altra esposizione». Quindi quattro esiti, e SOLO questi:
//   in_corso      - «Chiusura in corso»: ordini di chiusura, chiesto/abbinato, tentativo;
//   chiusa        - «CHIUSA - risultato bloccato X - nessuna esposizione residua»;
//   non_completa  - «NON COMPLETA - resta esposizione di X su <selezione> ...»;
//   da_verificare - i dati non bastano per dire «nessuna esposizione»: si dice PERCHE'.
//
// «NESSUNA ESPOSIZIONE» SI SCRIVE SOLO SE I DATI LO PROVANO, e la prova si fa qui
// sui conti degli ordini ABBINATI (non sullo stato che il bot si attribuisce):
//   1. per OGNI mercato (linea 3,5 e linea 4,5) il risultato se vince l'Under e
//      quello se vince l'Over sono uguali (entro 1 centesimo). Il conto e' per
//      MERCATO e non per selezione: dal pacchetto P5 la copertura sta sull'Under
//      4,5 e la sua chiusura sull'Over 4,5 (M3.4) - due selezioni che si pareggiano
//      solo insieme. Un mercato gia' deciso dai gol (linea superata) non e' esposto:
//      il suo esito e' certo;
//   2. nessun ordine vivo sul book e nessun ordine a esito ignoto sulla partita;
//   3. il risultato bloccato e' pubblicato dal bot (`live.locked`, o la tabella per
//      gol uguale su tutti i totali ancora possibili);
//   4. i dati della partita non sono vecchi.
// ============================================================================
import { fmtMoney, fmtOdds } from '@/lib/format';
import { roleLabel, type MikeEvent, type MikeLeg } from '@/lib/mike';

export type TipoEsitoChiusura = 'in_corso' | 'chiusa' | 'non_completa' | 'da_verificare';

/** Un ordine di chiusura come lo vede il trader. */
export interface OrdineDiChiusura {
    ref: string;
    /** «Chiusura Under 3.5», «Chiusura manuale» ... */
    ruolo: string;
    /** «punta» / «banca» */
    lato: string;
    chiesto: number;
    abbinato: number;
    prezzo: number | null;
    /** «sul book» / «abbinato» / «abbinato in parte, resto ritirato» / «ritirato» / «esito ignoto» */
    stato: string;
}

export interface EsitoChiusuraMike {
    tipo: TipoEsitoChiusura;
    /** la frase principale, esattamente come va a video */
    titolo: string;
    /** perche' si e' chiusa (firmata / da sola in profitto / Chiudi-Cash out) */
    motivo: string | null;
    ordini: OrdineDiChiusura[];
    /** tentativo in corso (1-based) e massimo; null = non pertinente */
    tentativo: number | null;
    tentativiMax: number;
    /** risultato bloccato (netto commissione, dal bot) */
    bloccato: number | null;
    /** righe di dettaglio: esposizioni per linea, motivi del «da verificare» */
    dettagli: string[];
}

/** ruoli degli ordini che CHIUDONO la partita (engine `_pending_closings`) */
const RUOLI_CHIUSURA = new Set(['under_close', 'over_close', 'manual_close']);
/** linea di ogni mercato (engine `LINE`) */
const LINEA: Record<string, number> = { OU35: 3.5, OU45: 4.5 };
const NOME_LINEA: Record<string, string> = { OU35: '3.5', OU45: '4.5' };
/** stesso scarto del motore (`_FLAT_EPS`) */
const PIATTO_EPS = 0.01;
/** Oltre questa eta' dei dati della partita non si firma «nessuna esposizione».
 *  Il bot riscrive SUBITO ogni fatto (gamba, stato); la sola eta' di cortesia di
 *  una partita a riposo arriva a `publish_idle_heartbeat_s` (60 s): 75 s = 60 + margine. */
export const ESITO_DATI_VECCHI_S = 75;

const MOTIVO: Record<string, string> = {
    profit: 'chiusa da Mike in profitto (parte da sola)',
    manual: 'chiusa col tuo comando (Chiudi / Cash out)',
    loss_ht: 'uscita in perdita all’intervallo, firmata da te',
    loss_2t: 'uscita in perdita nel secondo tempo, firmata da te',
    reentry_time: 'chiusura a tempo del re-ingresso',
    loss_cap: 'tetto di perdita della partita (regola tolta il 29/09)',
};

function motivoDi(cr: string | null): string | null {
    if (!cr) return null;
    if (MOTIVO[cr]) return MOTIVO[cr];
    if (cr.startsWith('loss_')) return 'uscita in perdita firmata da te';
    return cr;
}

function num(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function statoOrdine(l: MikeLeg): string {
    const abb = Number(l.matched || 0);
    if (l.status === 'pending_reconcile') return 'esito ignoto su Betfair (in verifica)';
    if (l.status === 'pending') return abb > 0 ? 'abbinato in parte, resto sul book' : 'sul book';
    if (l.status === 'cancelled') return 'ritirato, niente abbinato';
    if (abb >= Number(l.size) - 0.005) return 'abbinato';
    return abb > 0 ? 'abbinato in parte, resto ritirato' : 'non abbinato';
}

/**
 * Risultato di UN mercato se vince l'Under (`u`) e se vince l'Over (`o`), dai
 * soli importi ABBINATI (prezzo medio abbinato). Tutte le gambe, anche quelle
 * dei cicli archiviati: sono gia' pari e non spostano niente, ma se non lo
 * fossero l'esposizione sarebbe vera e va vista.
 */
export function contiPerMercato(legs: readonly MikeLeg[]): Map<string, { u: number; o: number }> {
    const out = new Map<string, { u: number; o: number }>();
    for (const l of legs) {
        const s = Number(l.matched || 0);
        if (!(s > 0)) continue;
        const p = Number(l.avg_price ?? l.price);
        if (!Number.isFinite(p) || p <= 1) continue;
        const c = out.get(l.market) ?? { u: 0, o: 0 };
        // vince la selezione della gamba: back +s(p-1), lay -s(p-1); perde: back -s, lay +s
        const vince = l.side === 'back' ? s * (p - 1) : -s * (p - 1);
        const perde = l.side === 'back' ? -s : s;
        if (l.selection === 'UNDER') { c.u += vince; c.o += perde; } else { c.o += vince; c.u += perde; }
        out.set(l.market, c);
    }
    return out;
}

/** Linee ancora esposte: importo a rischio e selezione su cui si e' esposti. */
export function esposizioniAperte(
    legs: readonly MikeLeg[], goals: number | null,
): { mercato: string; importo: number; selezione: string; seUnder: number; seOver: number }[] {
    const out: { mercato: string; importo: number; selezione: string; seUnder: number; seOver: number }[] = [];
    for (const [m, c] of contiPerMercato(legs)) {
        // linea superata dai gol: l'Over e' certo, nessuna esposizione (engine `selection_decided`)
        if (goals != null && LINEA[m] != null && goals > LINEA[m]) continue;
        if (Math.abs(c.u - c.o) < PIATTO_EPS) continue;
        const peggio = Math.min(c.u, c.o);
        const importo = peggio < 0 ? -peggio : Math.abs(c.u - c.o);
        const linea = NOME_LINEA[m] ?? m;
        out.push({
            mercato: m, importo: Math.round(importo * 100) / 100,
            selezione: `${c.u > c.o ? 'Under' : 'Over'} ${linea}`,
            seUnder: Math.round(c.u * 100) / 100, seOver: Math.round(c.o * 100) / 100,
        });
    }
    return out;
}

/** Risultato bloccato: quello del bot; se manca, la tabella per gol se e' uguale su ogni totale ancora possibile. */
function risultatoBloccato(ev: MikeEvent, goals: number | null): number | null {
    const live = ev.live ?? {};
    const l = num(live.locked);
    if (l != null) return l;
    const tab = live.pnl_totale_by_total;
    if (!tab || typeof tab !== 'object') return null;
    const valori = Object.entries(tab)
        .filter(([k]) => goals == null || Number(k) >= goals)
        .map(([, v]) => num(v));
    if (!valori.length || valori.some((v) => v == null)) return null;
    const vs = valori as number[];
    return Math.max(...vs) - Math.min(...vs) < PIATTO_EPS ? vs[0] : null;
}

/**
 * L'esito della chiusura di una partita, o `null` se non c'e' nessuna chiusura
 * da raccontare (partita che lavora normalmente, o gia' regolata).
 */
export function esitoChiusuraMike(
    ev: MikeEvent, opts: { nowMs: number; tentativiMax: number },
): EsitoChiusuraMike | null {
    const ctx = (ev.ctx ?? {}) as Record<string, unknown>;
    const cr = typeof ctx.close_reason === 'string' && ctx.close_reason ? ctx.close_reason : null;
    const flatten = ctx.flatten_pending === true;
    const tent = num(ctx.attempts);
    const max = opts.tentativiMax;
    const legs = ev.positions ?? [];
    const goals = num(ev.live?.goals);
    const stato = ev.state;

    const inCorso = stato === 'LIVE_CLOSING'
        || (flatten && !['FLAT', 'SETTLING', 'SETTLED', 'WATCH', 'ERROR', 'SKIPPED'].includes(stato));
    const chiusaDichiarata = cr != null && (stato === 'FLAT' || stato === 'SETTLING'
        || (stato === 'WATCH' && cr === 'manual' && ctx.no_reentry === true
            && legs.some((l) => Number(l.matched || 0) > 0)));
    if (!inCorso && !chiusaDichiarata) return null;

    const ordini: OrdineDiChiusura[] = legs
        .filter((l) => RUOLI_CHIUSURA.has(l.role) && !l.archived)
        .filter((l) => l.status !== 'cancelled' || Number(l.matched || 0) > 0)
        .sort((a, b) => Number(a.placed_at) - Number(b.placed_at))
        .map((l) => ({
            ref: l.ref, ruolo: roleLabel(l.role), lato: l.side === 'back' ? 'punta' : 'banca',
            chiesto: Number(l.size), abbinato: Number(l.matched || 0),
            prezzo: num(l.avg_price) ?? num(l.price), stato: statoOrdine(l),
        }));
    const esposte = esposizioniAperte(legs, goals);
    const dettagliEsposte = esposte.map((e) =>
        `linea ${NOME_LINEA[e.mercato] ?? e.mercato}: se vince l’Under ${fmtMoney(e.seUnder, { signed: true })}`
        + ` / se vince l’Over ${fmtMoney(e.seOver, { signed: true })}`);
    const tentativo = tent == null ? null : Math.min(Math.max(1, tent + 1), max);
    const base = { motivo: motivoDi(cr ?? (flatten ? 'manual' : null)), ordini, tentativiMax: max };
    const peggiore = esposte.slice().sort((a, b) => b.importo - a.importo)[0];
    const nonCompleta = (tent: number | null, extra: string[]): EsitoChiusuraMike => ({
        ...base, tipo: 'non_completa', tentativo: tent, bloccato: null,
        titolo: `NON COMPLETA - resta esposizione di ${fmtMoney(peggiore.importo)} su ${peggiore.selezione}`
            + (tent != null ? ` - tentativo ${tent} di ${max}` : ''),
        dettagli: [...dettagliEsposte, ...extra],
    });

    if (inCorso) {
        // tentativi esauriti con esposizione: la chiusura NON e' completa (il bot aspetta)
        if (stato === 'LIVE_CLOSING' && tent != null && tent >= max && peggiore) {
            return nonCompleta(max, ['tentativi esauriti: Mike resta in attesa dell’abbinamento']);
        }
        return {
            ...base, tipo: 'in_corso', tentativo, bloccato: null,
            titolo: `Chiusura in corso${tentativo != null ? ` - tentativo ${tentativo} di ${max}` : ''}`,
            dettagli: ordini.length ? dettagliEsposte : ['nessun ordine di chiusura ancora a mercato', ...dettagliEsposte],
        };
    }

    // --- la partita risulta chiusa: la prova sui conti ---------------------
    if (peggiore) {
        return nonCompleta(null, ['Mike considera la partita chiusa: controlla su Betfair']);
    }
    const perche: string[] = [];
    const vivi = legs.filter((l) => l.status === 'pending');
    const ignoti = legs.filter((l) => l.status === 'pending_reconcile');
    if (ignoti.length) {
        perche.push(`${ignoti.length === 1 ? 'un ordine ha' : `${ignoti.length} ordini hanno`} esito ignoto su Betfair`
            + ` (${ignoti.map((l) => roleLabel(l.role)).join(', ')}): Mike lo sta verificando`);
    }
    if (vivi.length) {
        perche.push(`${vivi.length === 1 ? 'un ordine e’' : `${vivi.length} ordini sono`} ancora sul book`
            + ` (${vivi.map((l) => `${roleLabel(l.role)} ${fmtMoney(l.size - Number(l.matched || 0))} @ ${fmtOdds(l.price)}`).join(', ')})`);
    }
    const bloccato = risultatoBloccato(ev, goals);
    if (bloccato == null) perche.push('il bot non ha ancora pubblicato il risultato bloccato');
    const pub = num(ev.live?.published_ts);
    const eta = pub == null ? null : Math.max(0, opts.nowMs / 1000 - pub);
    if (eta == null) perche.push('i dati della partita non dicono quando sono stati scritti');
    else if (eta > ESITO_DATI_VECCHI_S) perche.push(`i dati della partita sono vecchi di ${Math.round(eta)} s`);
    if (perche.length) {
        return {
            ...base, tipo: 'da_verificare', tentativo: null, bloccato,
            titolo: 'CHIUSURA DA VERIFICARE - nessuna esposizione sugli ordini abbinati, ma i dati non bastano per dirla chiusa',
            dettagli: perche,
        };
    }
    return {
        ...base, tipo: 'chiusa', tentativo: null, bloccato,
        titolo: `CHIUSA - risultato bloccato ${fmtMoney(bloccato, { signed: true })} - nessuna esposizione residua su questa partita`,
        dettagli: [],
    };
}
