// ============================================================================
// provaGiornata.ts - LA CORSIA PROVA: «OGGI» CONTRO «ARRETRATI REGOLATI OGGI».
//
// 30/09 (blocco P8, progetto monitor veritiero §2.C, decisione del
// coordinatore): il 30/09 la pagina scriveva «in prova +7,60 EUR» come se
// fosse la prova di oggi. Erano 4 partite di Safe del 26/09 regolate stamattina
// al riavvio; e mancavano 5 righe di Mike (2 partite del 26/09, -18,29) che la
// RPC `get_mike_state` non porta. Per la PROVA «oggi» = le partite di OGGI
// (giorno di Roma della partita); le righe di partite di giorni precedenti
// regolate oggi sono ARRETRATI, mostrati a parte con le loro date e MAI sommati
// alle cifre di oggi. Il LIVE non passa di qui: resta per giorno di
// regolamento (e' cio' che muove il saldo del conto).
//
// Stessa regola del ciclo di `righeGiornataPerCiclo` (26/09, F-2): un ciclo
// entra quando e' CHIUSO e la sua ultima gamba e' regolata oggi. Qui lo si
// riusa ciclo per ciclo (nessuna seconda formula di somma) e si aggiunge il
// giorno della PARTITA, dichiarando da DOVE viene:
//   * 'fischio'  = `kickoff` della riga (Omega) o `ko_at` (arretrati di Mike
//     dal backend): «partite del 26/09»;
//   * 'apertura' = giorno del PIAZZAMENTO DELL'APERTURA del ciclo (Safe e Mike
//     non hanno una colonna col calcio d'inizio, verificato sul DB il 30/09):
//     «operazioni aperte il 26/09». Due origini non si fondono mai.
// ============================================================================
import { groupTradesIntoCicli, isErrorRow } from './eventGroups';
import {
    righeGiornataPerCiclo, type RigaComponente, type RigaTradeReale,
} from './composizioneObiettivo';
import type { DailyBreakdown } from './dailyHistory';

/** Riga di trade con i campi del giorno partita che le tabelle possono portare. */
export interface RigaTradeProva extends RigaTradeReale {
    /** `omega_trades.kickoff` */
    kickoff?: string | null;
    /** `mike_events.ko_at` (arretrati di Mike dal backend) */
    ko_at?: string | null;
    /** `safe_strategy_trades.strategy` (base/esatto/punta/tennis/...) */
    strategy?: string | null;
}

/** Da dove viene il giorno della partita. */
export type OrigineGiorno = 'fischio' | 'apertura';

/** Una riga-ciclo della prova con il suo giorno partita (YYYY-MM-DD, Roma). */
export interface RigaProva extends RigaComponente {
    eventId: string;
    giornoPartita: string;
    origineGiorno: OrigineGiorno;
    /** strategia dell'APERTURA del ciclo (Safe), null se la riga non la porta */
    strategia: string | null;
}

export interface OpzioniProva {
    oggi: string;
    giornoDi: (iso: string | null | undefined) => string;
    sport?: string;
}

/**
 * Le righe PAPER regolate oggi (un ciclo = una riga), divise fra partite di
 * OGGI e arretrati (partite di giorni precedenti). Le righe live sono ignorate.
 */
export function provaPerGiornoPartita<T extends RigaTradeProva>(
    trades: readonly T[], opts: OpzioniProva,
): { oggi: RigaProva[]; arretrati: RigaProva[] } {
    const oggi: RigaProva[] = [];
    const arretrati: RigaProva[] = [];
    const vere = trades.filter((t) => !isErrorRow(t.status)
        && String(t.mode ?? '').toLowerCase() === 'paper');
    for (const c of groupTradesIntoCicli(vere)) {
        const righe = righeGiornataPerCiclo([c.open, ...c.closes], {
            oggi: opts.oggi, giornoDi: opts.giornoDi, sport: opts.sport,
        });
        if (righe.length === 0) continue;
        const a = c.open;
        const fischio = a.kickoff ?? a.ko_at ?? null;
        const origine: OrigineGiorno = fischio ? 'fischio' : 'apertura';
        const giorno = opts.giornoDi(fischio ?? a.placed_at);
        for (const r of righe) {
            const riga: RigaProva = {
                ...r, eventId: String(a.event_id), giornoPartita: giorno, origineGiorno: origine,
                strategia: typeof a.strategy === 'string' ? a.strategy : null,
            };
            // giorno illeggibile: mai spacciato per «oggi», va negli arretrati
            if (giorno === opts.oggi) oggi.push(riga); else arretrati.push(riga);
        }
    }
    return { oggi, arretrati };
}

/** Il riassunto di un gruppo di righe della prova. */
export interface RiassuntoProva {
    pnl: number;
    operazioni: number;
    vinte: number;
    perse: number;
    /** partite distinte (event_id) */
    partite: number;
}

/** Un gruppo di arretrati: UNA data e UNA origine della data. */
export interface GruppoArretrati extends RiassuntoProva {
    /** YYYY-MM-DD (Roma); '' = illeggibile */
    giorno: string;
    origine: OrigineGiorno;
}

const r2 = (cent: number) => cent / 100;

export function riassumiProva(righe: readonly RigaProva[]): RiassuntoProva {
    let cent = 0;
    let vinte = 0;
    let perse = 0;
    const partite = new Set<string>();
    for (const r of righe) {
        const v = typeof r.pnl === 'number' && Number.isFinite(r.pnl) ? r.pnl : 0;
        cent += Math.round(v * 100);
        if (r.status === 'won') vinte += 1;
        else if (r.status === 'lost') perse += 1;
        partite.add(r.eventId);
    }
    return { pnl: r2(cent), operazioni: righe.length, vinte, perse, partite: partite.size };
}

/** Arretrati raggruppati per (giorno, origine), in ordine di data. */
export function gruppiArretrati(righe: readonly RigaProva[]): GruppoArretrati[] {
    const per = new Map<string, RigaProva[]>();
    for (const r of righe) {
        const k = `${r.giornoPartita}|${r.origineGiorno}`;
        const arr = per.get(k) ?? [];
        arr.push(r);
        per.set(k, arr);
    }
    return [...per.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, rr]) => {
            const [giorno, origine] = k.split('|') as [string, OrigineGiorno];
            return { ...riassumiProva(rr), giorno, origine };
        });
}

/**
 * 30/09 (P8bis) - la cifra PROVA di una riga della PLANCIA dei bot: le sole
 * partite di OGGI (null = niente regolato oggi, la plancia scrive «—») e gli
 * arretrati a parte, per gruppo (data, origine). Mai sommati.
 */
export function provaDellaRiga(
    p: { oggi: readonly RigaProva[]; arretrati: readonly RigaProva[] },
    filtro: (r: RigaProva) => boolean = () => true,
): { oggi: number | null; arretrati: GruppoArretrati[] } {
    const oggi = p.oggi.filter(filtro);
    return {
        oggi: oggi.length === 0 ? null : riassumiProva(oggi).pnl,
        arretrati: gruppiArretrati(p.arretrati.filter(filtro)),
    };
}

/** Fonde i gruppi di piu' voci: somma SOLO gruppi con stessa data e stessa origine. */
export function fondiGruppi(gruppi: readonly GruppoArretrati[]): GruppoArretrati[] {
    const per = new Map<string, GruppoArretrati>();
    for (const g of gruppi) {
        const k = `${g.giorno}|${g.origine}`;
        const p = per.get(k);
        if (!p) { per.set(k, { ...g }); continue; }
        p.pnl = r2(Math.round(p.pnl * 100) + Math.round(g.pnl * 100));
        p.operazioni += g.operazioni;
        p.vinte += g.vinte;
        p.perse += g.perse;
        p.partite += g.partite;
    }
    return [...per.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, g]) => g);
}

/** «partite del 26/09» (dal fischio) / «operazioni aperte il 26/09» (dall'apertura). */
export function etichettaArretrati(g: Pick<GruppoArretrati, 'giorno' | 'origine' | 'partite' | 'operazioni'>): string {
    const d = /^\d{4}-\d{2}-\d{2}$/.test(g.giorno) ? `${g.giorno.slice(8, 10)}/${g.giorno.slice(5, 7)}` : null;
    if (g.origine === 'fischio') {
        const n = `${g.partite} ${g.partite === 1 ? 'partita' : 'partite'}`;
        return d ? `${n} del ${d}` : `${n} di data ignota`;
    }
    const n = `${g.operazioni} ${g.operazioni === 1 ? 'operazione aperta' : 'operazioni aperte'}`;
    return d ? `${n} il ${d}` : `${n} in data ignota`;
}

/**
 * Arretrati di Mike dal backend (chiave `arretrati_prova` di `get_mike_state`,
 * forma concordata il 30/09). `null` = chiave assente o illeggibile = NON
 * LETTI (la pagina lo dice, mai silenzio e mai 0,00). Righe con le chiavi di
 * `mike_trades` (+ `ko_at`).
 */
export function leggiArretratiProva(grezzo: unknown, oggi: string): RigaTradeProva[] | null {
    if (!grezzo || typeof grezzo !== 'object') return null;
    const g = grezzo as Record<string, unknown>;
    if (typeof g.day !== 'string' || g.day !== oggi) return null;
    if (!Array.isArray(g.righe)) return null;
    const out: RigaTradeProva[] = [];
    for (const x of g.righe) {
        if (!x || typeof x !== 'object') return null;
        const r = x as Record<string, unknown>;
        if (typeof r.id !== 'number' || typeof r.status !== 'string' || typeof r.placed_at !== 'string') return null;
        out.push({
            id: r.id,
            event_id: String(r.event_id ?? ''),
            event_name: typeof r.event_name === 'string' ? r.event_name : null,
            mode: typeof r.mode === 'string' ? r.mode : null,
            status: r.status,
            pnl: typeof r.pnl === 'number' ? r.pnl : null,
            placed_at: r.placed_at,
            settled_at: typeof r.settled_at === 'string' ? r.settled_at : null,
            closes_trade_id: typeof r.closes_trade_id === 'number' ? r.closes_trade_id : null,
            ko_at: typeof r.ko_at === 'string' ? r.ko_at : null,
        });
    }
    return out;
}

// ---------------------------------------------------------------- per bot

export type ChiaveProva = 'omega' | 'safe_calcio' | 'safe_tennis' | 'mike' | 'bot_tennis';
export type SportProva = 'calcio' | 'tennis';

export interface VoceProva {
    chiave: ChiaveProva;
    etichetta: string;
    sport: SportProva;
    /** partite di OGGI regolate oggi; null = righe del bot non lette */
    oggi: RiassuntoProva | null;
    /** partite di giorni precedenti regolate oggi; null = NON LETTI; [] = nessuno */
    arretrati: GruppoArretrati[] | null;
    /** true = «oggi» e' per giorno di REGOLAMENTO (la fonte non porta il giorno partita) */
    perRegolamento?: boolean;
    /** perche' il dato manca, in chiaro */
    nota?: string | null;
}

export interface ProvaGiornata {
    voci: VoceProva[];
    /** totali per SPORT delle sole partite di oggi (mai con gli arretrati); null = nessuna voce letta */
    oggiPerSport: Record<SportProva, RiassuntoProva | null>;
    /** arretrati per sport, un gruppo per (data, origine) */
    arretratiPerSport: Record<SportProva, GruppoArretrati[]>;
    /** voci i cui arretrati NON sono stati letti (es. ['Mike']) */
    arretratiNonLetti: Record<SportProva, string[]>;
    /** voci la cui cifra di oggi e' per giorno di regolamento */
    perRegolamento: Record<SportProva, string[]>;
}

/** Riga del giorno della RPC `get_tennis_bot_daily` (p_mode='paper'): solo i campi usati. */
export interface TennisProvaGiorno {
    pnl_netto: number | null;
    ordini?: number | null;
    vinti?: number | null;
    persi?: number | null;
}

/** Il riassunto nella forma delle tessere sport (`DailyBreakdown`); null = 0 (lettura riuscita). */
export function breakdownProva(r: RiassuntoProva | null): DailyBreakdown {
    return r ? { n: r.operazioni, pnl: r.pnl, won: r.vinte, lost: r.perse }
        : { n: 0, pnl: 0, won: 0, lost: 0 };
}

function sommaRiassunti(xs: readonly (RiassuntoProva | null)[]): RiassuntoProva | null {
    const letti = xs.filter((x): x is RiassuntoProva => x != null);
    if (letti.length === 0) return null;
    let cent = 0;
    const out: RiassuntoProva = { pnl: 0, operazioni: 0, vinte: 0, perse: 0, partite: 0 };
    for (const x of letti) {
        cent += Math.round(x.pnl * 100);
        out.operazioni += x.operazioni;
        out.vinte += x.vinte;
        out.perse += x.perse;
        out.partite += x.partite;
    }
    out.pnl = r2(cent);
    return out;
}

/**
 * La corsia PROVA per bot. `null` in ingresso = righe di quel bot non lette.
 * `mikeArretrati`: righe dal backend (`leggiArretratiProva`); `null` = non letti.
 * Tennis bot: la RPC e' aggregata per giorno di REGOLAMENTO e non porta il
 * giorno della partita: tutto in «oggi», DICHIARATO; arretrati non separabili.
 */
export function provaGiornata(input: {
    oggi: string;
    giornoDi: (iso: string | null | undefined) => string;
    omega: readonly RigaTradeProva[] | null;
    safe: readonly RigaTradeProva[] | null;
    mike: readonly RigaTradeProva[] | null;
    mikeArretrati: readonly RigaTradeProva[] | null;
    tennisPaper: readonly TennisProvaGiorno[] | null;
    /**
     * 30/09 (R_G) - i gruppi per bot GIA' calcolati con `provaPerGiornoPartita`
     * (stesso giorno): se presenti si usano al posto di ricalcolarli dalle righe.
     */
    precalcolati?: {
        omega: ReturnType<typeof provaPerGiornoPartita>;
        safe: ReturnType<typeof provaPerGiornoPartita>;
        mike: ReturnType<typeof provaPerGiornoPartita>;
    };
}): ProvaGiornata {
    const o = { oggi: input.oggi, giornoDi: input.giornoDi };
    const pre = input.precalcolati;
    const omega = pre ? pre.omega : input.omega ? provaPerGiornoPartita(input.omega, { ...o, sport: 'calcio' }) : null;
    const safe = pre ? pre.safe : input.safe ? provaPerGiornoPartita(input.safe, o) : null;
    const mike = pre ? pre.mike : input.mike ? provaPerGiornoPartita(input.mike, { ...o, sport: 'calcio' }) : null;
    const di = (s: SportProva) => (r: RigaProva) => String(r.sport ?? '').toLowerCase() === s;

    // Mike: la RPC principale porta solo le righe di oggi (o aperte): i suoi
    // arretrati vengono SOLO dalla chiave del backend. Senza, «non letti».
    // Dalla chiave si prendono solo le partite di giorni precedenti: una
    // partita di oggi e' gia' nelle righe principali (mai contata due volte).
    const mikeArr = input.mikeArretrati
        ? provaPerGiornoPartita(input.mikeArretrati, { ...o, sport: 'calcio' }).arretrati
        : null;

    let tennisBot: RiassuntoProva | null = null;
    if (input.tennisPaper) {
        let cent = 0;
        const t: RiassuntoProva = { pnl: 0, operazioni: 0, vinte: 0, perse: 0, partite: 0 };
        for (const r of input.tennisPaper) {
            if (typeof r.pnl_netto === 'number') cent += Math.round(r.pnl_netto * 100);
            t.operazioni += r.ordini ?? 0;
            t.vinte += r.vinti ?? 0;
            t.perse += r.persi ?? 0;
        }
        t.pnl = r2(cent);
        tennisBot = t;
    }

    const voci: VoceProva[] = [
        {
            chiave: 'omega', etichetta: 'Omega', sport: 'calcio',
            oggi: omega ? riassumiProva(omega.oggi) : null,
            arretrati: omega ? gruppiArretrati(omega.arretrati) : null,
            nota: omega ? null : 'righe di Omega non lette',
        },
        {
            chiave: 'safe_calcio', etichetta: 'Safe calcio', sport: 'calcio',
            oggi: safe ? riassumiProva(safe.oggi.filter(di('calcio'))) : null,
            arretrati: safe ? gruppiArretrati(safe.arretrati.filter(di('calcio'))) : null,
            nota: safe ? null : 'righe di Safe non lette',
        },
        {
            chiave: 'mike', etichetta: 'Mike', sport: 'calcio',
            oggi: mike ? riassumiProva(mike.oggi) : null,
            arretrati: mikeArr ? gruppiArretrati(mikeArr) : null,
            nota: mikeArr ? null : 'arretrati di Mike: non letti',
        },
        {
            chiave: 'safe_tennis', etichetta: 'Safe tennis', sport: 'tennis',
            oggi: safe ? riassumiProva(safe.oggi.filter(di('tennis'))) : null,
            arretrati: safe ? gruppiArretrati(safe.arretrati.filter(di('tennis'))) : null,
            nota: safe ? null : 'righe di Safe non lette',
        },
        {
            chiave: 'bot_tennis', etichetta: 'Bot tennis (Scalper · Pro · FLB · Swing)', sport: 'tennis',
            oggi: tennisBot,
            // per regolamento: nessuna separazione possibile, non «nessun arretrato»
            arretrati: tennisBot ? [] : null,
            perRegolamento: true,
            nota: tennisBot ? null : 'giornata dei bot tennis in prova non letta',
        },
    ];

    const perSport = (s: SportProva) => sommaRiassunti(voci.filter((v) => v.sport === s).map((v) => v.oggi));
    const arrPerSport = (s: SportProva) => fondiGruppi(
        voci.filter((v) => v.sport === s).flatMap((v) => v.arretrati ?? []));
    const nonLetti = (s: SportProva) =>
        voci.filter((v) => v.sport === s && v.arretrati == null).map((v) => v.etichetta);
    const regol = (s: SportProva) =>
        voci.filter((v) => v.sport === s && v.perRegolamento && v.oggi != null).map((v) => v.etichetta);
    return {
        voci,
        oggiPerSport: { calcio: perSport('calcio'), tennis: perSport('tennis') },
        arretratiPerSport: { calcio: arrPerSport('calcio'), tennis: arrPerSport('tennis') },
        arretratiNonLetti: { calcio: nonLetti('calcio'), tennis: nonLetti('tennis') },
        perRegolamento: { calcio: regol('calcio'), tennis: regol('tennis') },
    };
}
