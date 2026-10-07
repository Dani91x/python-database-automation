// ============================================================================
// replayOperazioni — L'OPERATIVITA' DEL BOT nel replay, ricostruita dalla
// cronologia degli ordini (07/10 sera, ordine dell'utente: «la sezione replay
// e' uno strumento professionale: per qualsiasi bot e qualsiasi strategia devo
// vedere dal ladder esattamente come avrebbe operato il bot nella realta', con
// importi, P&L, abbinamenti»).
//
// Ingresso UNICO: le righe `betfair_live_orders` + `_ms` che il banco scrive a
// ogni cambio di firma dell'ordine (write-on-change come la produzione), per
// QUALSIASI bot (`varianti_bot.SpecchioOrdini`, specchio della sessione dello
// scalper). Nessuna logica per bot: tutto dalle righe.
//
// Ne escono, PURE e testate:
//   * ordiniDaRighe     gli ordini (identita' vera: `_ordine` del banco),
//   * eventiOrdini      il registro delle operazioni (piazzato, appoggiato,
//                       abbinato parziale/totale, annullo, riprezzo/sostituzione,
//                       annullato, scaduto, rifiutato) con quota, importi, residuo,
//   * cicliOperativi    i cicli/trade per mercato (da piatto a piatto) con
//                       origine della chiusura e P&L,
//   * statoOrdiniAl     cio' che e' VERO a un istante t (appoggiati e abbinati),
//   * posizioneAl       la posizione a t per selezione (P&L se vince / se perde),
//   * contoRegolato     il P&L a regolamento (stesse regole di
//                       `applica_bot.conto_regolato` e di flumine),
//   * contoCicli        il P&L dei cicli col metodo del banco della media under
//                       (`riepilogo_cicli_media`: chiuso = profitto bloccato).
// ============================================================================
import type { EsitoMercato, RigaBot } from '@/lib/replayBot';
import { roundToTick } from '@/lib/matching';

export type Lato = 'back' | 'lay';
const EPS = 0.005;

// --------------------------------------------------------------------------
// ordini
// --------------------------------------------------------------------------
export interface OrdineBot {
    /** chiave univoca dell'ordine nel replay */
    chiave: string;
    marketId: string;
    selectionId: number;
    lato: Lato;
    quota: number | null;
    importo: number | null;
    persistenza: string | null;
    /** le righe dell'ordine in ordine di tempo */
    righe: RigaBot[];
    primoMs: number;
    ultimoMs: number;
    betId: string | null;
    ref: string | null;
    tradeId: string | null;
    strategia: string | null;
    /** chiave dell'ordine sostituito da questo (riprezzo / ripiazzo) */
    sostituisce: string | null;
    /** il legame viene dal banco (replace di flumine) o e' dedotto dalla cronologia */
    sostituzioneDichiarata: boolean;
    /** chiave dell'ordine che ha preso il posto di questo */
    sostituitoDa: string | null;
    /** integrazione: alla nascita c'era gia' sul book un ordine dello stesso
     *  lato, selezione e quota (chiave di quell'ordine) */
    integra: string | null;
    ciclo: number | null;
}

function latoDi(r: RigaBot): Lato {
    return String(r.side ?? '').toLowerCase() === 'lay' ? 'lay' : 'back';
}

const num = (x: unknown): number => (typeof x === 'number' && Number.isFinite(x) ? x : 0);

/** Le righe in ordine di tempo (stabile: a pari `_ms` l'ordine di scrittura). PURA. */
export function righeOrdinate(righe: ReadonlyArray<RigaBot>): RigaBot[] {
    return righe.map((r, i) => ({ r, i }))
        .sort((a, b) => (a.r._ms - b.r._ms) || (a.i - b.i))
        .map(x => x.r);
}

/** Finestra in cui un ordine nuovo dello stesso lato e selezione, nato dopo
 *  il ritiro di un ordine, ne prende il posto (annulla e ripiazza). */
export const FINESTRA_SOSTITUZIONE_MS = 5000;

/** Gli ordini del bot dalla cronologia. L'identita' e' `_ordine` (id flumine)
 *  quando il banco lo scrive; per gli esiti di prima ricade sul ref, separando
 *  due bet id diversi con lo stesso ref (replace di flumine). PURA. */
export function ordiniDaRighe(righe: ReadonlyArray<RigaBot>): OrdineBot[] {
    const ordinate = righeOrdinate(righe);
    const perChiave = new Map<string, OrdineBot>();
    const correntePerRef = new Map<string, string>();
    const contaRef = new Map<string, number>();
    let anonimi = 0;
    const chiaveDi = (r: RigaBot): string => {
        if (r._ordine) return `o:${r._ordine}`;
        const ref = r.client_order_ref ?? null;
        if (!ref) return r.bet_id ? `b:${r.bet_id}` : `#${anonimi++}`;
        let k = correntePerRef.get(ref);
        const o = k ? perChiave.get(k) : undefined;
        if (!k || (o && r.bet_id && o.betId && o.betId !== r.bet_id)) {
            const n = (contaRef.get(ref) ?? 0) + 1;
            contaRef.set(ref, n);
            k = n === 1 ? `r:${ref}` : `r:${ref}#${n}`;
            correntePerRef.set(ref, k);
        }
        return k;
    };
    for (const r of ordinate) {
        const k = chiaveDi(r);
        let o = perChiave.get(k);
        if (!o) {
            o = {
                chiave: k, marketId: String(r.market_id), selectionId: Number(r.selection_id),
                lato: latoDi(r), quota: r.price ?? null, importo: r.size ?? null,
                persistenza: r.persistence ?? null, righe: [], primoMs: r._ms, ultimoMs: r._ms,
                betId: r.bet_id ?? null, ref: r.client_order_ref ?? null,
                tradeId: r._trade_id ?? null, strategia: r._strategia ?? null,
                sostituisce: null, sostituzioneDichiarata: false, sostituitoDa: null, integra: null, ciclo: null,
            };
            perChiave.set(k, o);
        }
        o.righe.push(r);
        o.ultimoMs = r._ms;
        if (r.bet_id) o.betId = r.bet_id;
        if (r.price != null) o.quota = r.price;
        if (r.size != null) o.importo = r.size;
    }
    const ordini = [...perChiave.values()].sort((a, b) => a.primoMs - b.primoMs);
    // legame dichiarato dal banco (replace di flumine)
    const perOrdineFlumine = new Map<string, OrdineBot>();
    for (const o of ordini) if (o.chiave.startsWith('o:')) perOrdineFlumine.set(o.chiave.slice(2), o);
    for (const o of ordini) {
        const s = o.righe.find(r => r._sostituisce)?._sostituisce;
        const vecchio = s ? perOrdineFlumine.get(String(s)) : undefined;
        if (vecchio && !vecchio.sostituitoDa) {
            o.sostituisce = vecchio.chiave;
            o.sostituzioneDichiarata = true;
            vecchio.sostituitoDa = o.chiave;
        }
    }
    // legame dedotto: un ordine RITIRATO (annullato) e il primo ordine nuovo dello
    // stesso mercato, selezione e lato nato fra la richiesta di annullo e
    // FINESTRA_SOSTITUZIONE_MS dopo il ritiro (annulla e ripiazza)
    for (const vecchio of ordini) {
        if (vecchio.sostituitoDa) continue;
        const ritiro = vecchio.righe.find(r => num(r.size_cancelled) > EPS && (r.status === 'EXECUTION_COMPLETE'));
        if (!ritiro) continue;
        const richiesta = vecchio.righe.find(r => r.status === 'CANCELLING' || r.status === 'REPLACING') ?? ritiro;
        const candidati = ordini.filter(n => n !== vecchio && !n.sostituisce
            && n.marketId === vecchio.marketId && n.selectionId === vecchio.selectionId && n.lato === vecchio.lato
            && n.primoMs >= richiesta._ms && n.primoMs <= ritiro._ms + FINESTRA_SOSTITUZIONE_MS);
        // prima lo STESSO trade con importo uguale a quello tolto (lo spostamento
        // della banca con replace), poi lo stesso trade, poi il primo nato
        const tolto = num(ritiro.size_cancelled);
        const nuovo = candidati.find(n => n.tradeId != null && n.tradeId === vecchio.tradeId && Math.abs(num(n.importo) - tolto) < EPS)
            ?? candidati.find(n => n.tradeId != null && n.tradeId === vecchio.tradeId)
            ?? candidati[0];
        if (nuovo) {
            nuovo.sostituisce = vecchio.chiave;
            vecchio.sostituitoDa = nuovo.chiave;
        }
    }
    // integrazione: un ordine nuovo (non sostitutivo) nato mentre sul book c'era
    // gia' un ordine vivo dello stesso mercato, selezione, lato e quota
    for (const n of ordini) {
        if (n.sostituisce || n.quota == null) continue;
        const gia = ordini.find(o => o !== n && o.primoMs < n.primoMs && o.marketId === n.marketId
            && o.selectionId === n.selectionId && o.lato === n.lato && o.quota != null && Math.abs(o.quota - n.quota!) < 1e-9
            && (() => { const r = ultimaAl(o, n.primoMs); return r != null && vivo(r); })());
        if (gia) n.integra = gia.chiave;
    }
    return ordini;
}

// --------------------------------------------------------------------------
// posizione e P&L
// --------------------------------------------------------------------------
export interface Abbinamento {
    marketId: string;
    selectionId: number;
    lato: Lato;
    importo: number;
    prezzo: number;
}

/** P&L di un insieme di abbinamenti se vince `vincitore` (null = vince un
 *  runner senza ordini). PURA. */
export function pnlSeVince(abb: ReadonlyArray<Abbinamento>, vincitore: number | null): number {
    let v = 0;
    for (const a of abb) {
        const suo = vincitore != null && a.selectionId === vincitore;
        if (a.lato === 'back') v += suo ? a.importo * (a.prezzo - 1) : -a.importo;
        else v += suo ? -a.importo * (a.prezzo - 1) : a.importo;
    }
    return v;
}

/** I runner di un mercato: dal raw (esiti del banco), poi quelli passati, poi
 *  quelli con ordini. `completo` = l'elenco e' quello di Betfair. PURA. */
export function runnerDelMercato(marketId: string, abb: ReadonlyArray<Abbinamento>,
    esiti?: Record<string, EsitoMercato> | null, runnerNoti?: ReadonlyArray<number>): { runner: number[]; completo: boolean } {
    const dalRaw = esiti?.[marketId]?.ordine_runner;
    if (dalRaw && dalRaw.length > 0) return { runner: [...dalRaw], completo: true };
    if (runnerNoti && runnerNoti.length > 0) return { runner: [...runnerNoti], completo: true };
    const visti: number[] = [];
    for (const a of abb) if (a.marketId === marketId && !visti.includes(a.selectionId)) visti.push(a.selectionId);
    return { runner: visti, completo: false };
}

/** Il P&L di ogni esito possibile del mercato (Betfair «profit & loss if wins»):
 *  selection_id -> P&L se vince quella; `altro` = se vince un runner non in
 *  elenco (solo quando l'elenco non e' quello di Betfair). PURA. */
export function esitiPossibili(marketId: string, abb: ReadonlyArray<Abbinamento>,
    esiti?: Record<string, EsitoMercato> | null, runnerNoti?: ReadonlyArray<number>):
    { perRunner: Record<number, number>; altro: number | null } {
    const delMercato = abb.filter(a => a.marketId === marketId);
    const { runner, completo } = runnerDelMercato(marketId, delMercato, esiti, runnerNoti);
    const perRunner: Record<number, number> = {};
    for (const s of runner) perRunner[s] = pnlSeVince(delMercato, s);
    return { perRunner, altro: completo ? null : pnlSeVince(delMercato, null) };
}

function abbinamentiDi(ordini: ReadonlyArray<OrdineBot>, ms: number): Abbinamento[] {
    const out: Abbinamento[] = [];
    for (const o of ordini) {
        const r = ultimaAl(o, ms);
        if (!r) continue;
        const m = num(r.size_matched);
        const p = num(r.average_price_matched);
        if (m > EPS && p > 1) out.push({ marketId: o.marketId, selectionId: o.selectionId, lato: o.lato, importo: m, prezzo: p });
    }
    return out;
}

function ultimaAl(o: OrdineBot, ms: number): RigaBot | null {
    let u: RigaBot | null = null;
    for (const r of o.righe) {
        if (r._ms > ms) break;
        u = r;
    }
    return u;
}

const STATI_VIVI = new Set(['PENDING', 'EXECUTABLE', 'CANCELLING', 'REPLACING', 'UPDATING']);
/** L'ordine e' ancora sul mercato (o in volo) secondo la sua riga? */
export function vivo(r: RigaBot): boolean {
    if (r.status === 'EXECUTION_COMPLETE' || r.status === 'EXPIRED' || r.status === 'VIOLATION') return false;
    return STATI_VIVI.has(String(r.status)) ? num(r.size_remaining) > EPS || r.status === 'PENDING' : num(r.size_remaining) > EPS;
}

// --------------------------------------------------------------------------
// stato all'istante t (ladder)
// --------------------------------------------------------------------------
export interface OrdineAlMs {
    ordine: OrdineBot;
    riga: RigaBot;
    /** in volo (inviato, non ancora sul book) */
    inVolo: boolean;
    /** non abbinato sul book */
    residuo: number;
    abbinato: number;
    prezzoMedio: number;
    vivo: boolean;
}

/** Gli ordini come erano all'istante `ms` (ultima riga con _ms <= ms). PURA. */
export function statoOrdiniAl(ordini: ReadonlyArray<OrdineBot>, ms: number, marketId?: string): OrdineAlMs[] {
    const out: OrdineAlMs[] = [];
    for (const o of ordini) {
        if (marketId && o.marketId !== marketId) continue;
        const r = ultimaAl(o, ms);
        if (!r) continue;
        const v = vivo(r);
        out.push({
            ordine: o, riga: r, vivo: v, inVolo: v && r.status === 'PENDING',
            residuo: v ? num(r.size_remaining) : 0,
            abbinato: num(r.size_matched), prezzoMedio: num(r.average_price_matched),
        });
    }
    return out;
}

/** Livello del ladder evidenziato per una selezione (sovrapposizione del bot). */
export interface LivelloBot {
    lato: Lato;
    /** quota (tick) */
    quota: number;
    /** importo non abbinato appoggiato a questa quota */
    appoggiato: number;
    /** importo abbinato a questa quota (prezzo medio dell'ordine arrotondato al tick) */
    abbinato: number;
    /** ordini in volo (inviati, non ancora sul book) */
    inVolo: number;
}

export interface SelezioneBotAlMs {
    selectionId: number;
    livelli: LivelloBot[];
    /** P&L della selezione da sola (stile flumine/ladder: se vince / se perde) */
    seVinceSel: number;
    sePerdeSel: number;
    /** P&L del MERCATO se vince questa selezione (Betfair «if wins») */
    seVinceMercato: number | null;
    abbinatoBack: number;
    abbinatoLay: number;
}

/** La sovrapposizione del bot per il ladder di UN mercato all'istante `ms`. PURA. */
export function ladderBotAl(ordini: ReadonlyArray<OrdineBot>, ms: number, marketId: string,
    esiti?: Record<string, EsitoMercato> | null, runnerNoti?: ReadonlyArray<number>): Record<number, SelezioneBotAlMs> {
    const stato = statoOrdiniAl(ordini, ms, marketId);
    const out: Record<number, SelezioneBotAlMs> = {};
    const sel = (sid: number): SelezioneBotAlMs => {
        let s = out[sid];
        if (!s) {
            s = { selectionId: sid, livelli: [], seVinceSel: 0, sePerdeSel: 0, seVinceMercato: null, abbinatoBack: 0, abbinatoLay: 0 };
            out[sid] = s;
        }
        return s;
    };
    const livello = (s: SelezioneBotAlMs, lato: Lato, quota: number): LivelloBot => {
        let l = s.livelli.find(x => x.lato === lato && Math.abs(x.quota - quota) < 1e-9);
        if (!l) {
            l = { lato, quota, appoggiato: 0, abbinato: 0, inVolo: 0 };
            s.livelli.push(l);
        }
        return l;
    };
    for (const x of stato) {
        const s = sel(x.ordine.selectionId);
        const q = x.riga.price;
        if (x.vivo && q != null) {
            const l = livello(s, x.ordine.lato, roundToTick(q));
            if (x.inVolo) l.inVolo += x.residuo; else l.appoggiato += x.residuo;
        }
        if (x.abbinato > EPS && x.prezzoMedio > 1) {
            livello(s, x.ordine.lato, roundToTick(x.prezzoMedio)).abbinato += x.abbinato;
            if (x.ordine.lato === 'back') {
                s.abbinatoBack += x.abbinato;
                s.seVinceSel += x.abbinato * (x.prezzoMedio - 1);
                s.sePerdeSel -= x.abbinato;
            } else {
                s.abbinatoLay += x.abbinato;
                s.seVinceSel -= x.abbinato * (x.prezzoMedio - 1);
                s.sePerdeSel += x.abbinato;
            }
        }
    }
    const abb = abbinamentiDi(ordini, ms).filter(a => a.marketId === marketId);
    if (abb.length > 0) {
        const { perRunner } = esitiPossibili(marketId, abb, esiti, runnerNoti);
        for (const [sid, v] of Object.entries(perRunner)) sel(Number(sid)).seVinceMercato = v;
    }
    for (const s of Object.values(out)) s.livelli.sort((a, b) => b.quota - a.quota);
    return out;
}

// --------------------------------------------------------------------------
// eventi (registro delle operazioni)
// --------------------------------------------------------------------------
export type TipoEvento =
    | 'piazzato' | 'appoggiato' | 'abbinato_parziale' | 'abbinato_totale'
    | 'annullo_richiesto' | 'riprezzo_richiesto' | 'annullato' | 'scaduto' | 'void' | 'rifiutato'
    | 'ciclo_chiuso' | 'mercato_chiuso';

export interface EventoOperazione {
    id: string;
    ms: number;
    tipo: TipoEvento;
    /** chiave dell'ordine (null per gli eventi di ciclo e di mercato) */
    ordine: string | null;
    marketId: string;
    selectionId: number | null;
    lato: Lato | null;
    /** quota chiesta e importo chiesto dell'ordine */
    quota: number | null;
    importo: number | null;
    /** abbinato in QUESTO evento e il suo prezzo medio */
    abbinatoEvento: number;
    prezzoEvento: number | null;
    /** dopo l'evento: totale abbinato, prezzo medio, residuo sul book */
    abbinato: number;
    prezzoMedio: number;
    residuo: number;
    /** annullato/scaduto/void: l'importo tolto in questo evento */
    tolto: number;
    /** piazzato in sostituzione di un altro ordine: quello vecchio e la sua quota */
    sostituisce: string | null;
    daQuota: number | null;
    daImporto: number | null;
    /** il legame viene dal banco (replace di flumine) */
    riprezzoDichiarato: boolean;
    /** perche' e' stato tolto e rimesso (es. per il rientro), se si vede */
    motivoSostituzione: string | null;
    /** piazzato come integrazione di un ordine gia' sul book alla stessa quota */
    integra: string | null;
    /** il non abbinato dell'ordine integrato in quell'istante */
    integraResiduo: number | null;
    /** annullato perche' sostituito da un altro ordine */
    sostituitoDa: string | null;
    ciclo: number | null;
    /** solo per ciclo_chiuso */
    cicloInfo?: CicloOperativo;
}

export interface CicloOperativo {
    n: number;
    marketId: string;
    daMs: number;
    aMs: number | null;
    ordini: string[];
    /** P&L di ogni esito (selection_id -> P&L se vince) dai soli ordini del ciclo */
    esiti: Record<number, number>;
    altro: number | null;
    /** profitto bloccato (il peggiore degli esiti) */
    garantito: number;
    /** P&L col risultato del mercato registrato (null se il raw non lo dice) */
    regolato: number | null;
    /** chiuso dagli ordini, regolato dalla chiusura del mercato, o aperto */
    stato: 'chiuso' | 'regolato' | 'aperto';
    origine: string;
    /** il contributo al conto dei cicli (metodo del banco), null = esito ignoto */
    lordoConto: number | null;
    /** il ciclo e' «pari» col criterio del banco (posizione coperta) */
    coperto: boolean;
    abbinatoBack: number;
    abbinatoLay: number;
}

function eventoBase(o: OrdineBot, r: RigaBot, tipo: TipoEvento, n: number): EventoOperazione {
    return {
        id: `${o.chiave}:${n}:${tipo}`, ms: r._ms, tipo, ordine: o.chiave, marketId: o.marketId,
        selectionId: o.selectionId, lato: o.lato, quota: r.price ?? o.quota, importo: r.size ?? o.importo,
        abbinatoEvento: 0, prezzoEvento: null, abbinato: num(r.size_matched),
        prezzoMedio: num(r.average_price_matched), residuo: vivo(r) ? num(r.size_remaining) : 0, tolto: 0,
        sostituisce: null, daQuota: null, daImporto: null, riprezzoDichiarato: false, motivoSostituzione: null,
        integra: null, integraResiduo: null, sostituitoDa: null, ciclo: o.ciclo,
    };
}

/** Gli eventi di UN ordine, dalla sua cronologia di righe. PURA. */
export function eventiDellOrdine(o: OrdineBot, perChiave?: ReadonlyMap<string, OrdineBot>,
    tutti?: ReadonlyArray<OrdineBot>): EventoOperazione[] {
    const out: EventoOperazione[] = [];
    let prev: RigaBot | null = null;
    let appoggiato = false;
    let n = 0;
    for (const r of o.righe) {
        const add = (tipo: TipoEvento): EventoOperazione => {
            const e = eventoBase(o, r, tipo, n++);
            out.push(e);
            return e;
        };
        if (!prev) {
            const e = add('piazzato');
            if (o.sostituisce) {
                const v = perChiave?.get(o.sostituisce);
                e.sostituisce = o.sostituisce;
                e.daQuota = v?.quota ?? null;
                e.daImporto = v?.importo ?? null;
                e.riprezzoDichiarato = o.sostituzioneDichiarata;
                e.motivoSostituzione = v && tutti ? motivoSostituzione(o, v, tutti) : null;
            }
            if (o.integra) {
                const g = perChiave?.get(o.integra);
                const rg = g ? ultimaAl(g, r._ms) : null;
                e.integra = o.integra;
                e.integraResiduo = rg ? num(rg.size_remaining) : null;
            }
        }
        const mPrev = prev ? num(prev.size_matched) : 0;
        const pPrev = prev ? num(prev.average_price_matched) : 0;
        const m = num(r.size_matched);
        const p = num(r.average_price_matched);
        if (!appoggiato && r.status === 'EXECUTABLE' && num(r.size_remaining) > EPS) {
            appoggiato = true;
            add('appoggiato');
        }
        if (m - mPrev > EPS) {
            const totale = m + EPS >= num(r.size ?? o.importo);
            const e = add(totale ? 'abbinato_totale' : 'abbinato_parziale');
            e.abbinatoEvento = round2(m - mPrev);
            const pe = (m * p - mPrev * pPrev) / (m - mPrev);
            e.prezzoEvento = Number.isFinite(pe) && pe > 1 ? Math.round(pe * 100) / 100 : (p || null);
        }
        if (r.status === 'CANCELLING' && prev?.status !== 'CANCELLING') add('annullo_richiesto');
        if (r.status === 'REPLACING' && prev?.status !== 'REPLACING') add('riprezzo_richiesto');
        const dC = num(r.size_cancelled) - (prev ? num(prev.size_cancelled) : 0);
        const dL = num(r.size_lapsed) - (prev ? num(prev.size_lapsed) : 0);
        const dV = num(r.size_voided) - (prev ? num(prev.size_voided) : 0);
        if (dC > EPS) {
            const e = add('annullato');
            e.tolto = round2(dC);
            // il ritiro definitivo e' quello che lascia l'ordine chiuso
            if (r.status === 'EXECUTION_COMPLETE') e.sostituitoDa = o.sostituitoDa;
        }
        if (dL > EPS) add('scaduto').tolto = round2(dL);
        if (dV > EPS) add('void').tolto = round2(dV);
        const finito = r.status === 'EXECUTION_COMPLETE' || r.status === 'EXPIRED' || r.status === 'VIOLATION';
        if (finito && m <= EPS && dC <= EPS && dL <= EPS && dV <= EPS
            && num(r.size_cancelled) + num(r.size_lapsed) + num(r.size_voided) <= EPS
            && !(prev && (prev.status === 'EXECUTION_COMPLETE'))) {
            add('rifiutato');
        }
        prev = r;
    }
    return out;
}

/** Arrotondamento al centesimo IDENTICO a `round(x, 2)` di Python (quello di
 *  flumine e del banco): sul valore binario ESATTO del numero, e nei pareggi
 *  esatti (0,125) al pari (0,12), non per eccesso come Math.round (0,13).
 *  `toFixed(20)` da' le cifre esatte del valore binario. PURA. */
export function round2(x: number): number {
    if (!Number.isFinite(x)) return x;
    const segno = x < 0 ? -1 : 1;
    const esatte = Math.abs(x).toFixed(20);
    const [intera, frazione] = esatte.split('.');
    const resto = frazione.slice(2);
    if (/^50*$/.test(resto)) {
        // pareggio esatto: al centesimo PARI
        const cent = Number(`${intera}${frazione.slice(0, 2)}`);
        const pari = cent % 2 === 0 ? cent : cent + 1;
        return (segno * pari) / 100 || 0;
    }
    return (segno * Number(Math.abs(x).toFixed(2))) || 0;
}

/** Lo stato finale (o all'istante) di un ordine per il trader. Un ordine con
 *  abbinato 0 tolto dal mercato e' «annullato» (o «scaduto»), MAI «chiuso». PURA. */
export function statoOrdineTesto(r: RigaBot, sostituito = false): string {
    const m = num(r.size_matched);
    const size = num(r.size);
    if (vivo(r)) {
        if (r.status === 'PENDING') return 'in volo';
        if (r.status === 'CANCELLING') return m > EPS ? `abbinato ${m.toFixed(2)}, annullo in corso` : 'annullo in corso';
        if (r.status === 'REPLACING') return 'riprezzo in corso';
        return m > EPS ? `abbinato ${m.toFixed(2)}, resto appoggiato` : 'appoggiato';
    }
    const tolto = num(r.size_cancelled) > EPS ? (sostituito ? 'sostituito' : 'annullato')
        : num(r.size_lapsed) > EPS ? 'scaduto'
        : num(r.size_voided) > EPS ? 'annullato da Betfair' : null;
    if (m + EPS >= size && m > EPS) return 'abbinato per intero';
    if (m > EPS) return `abbinato ${m.toFixed(2)}, resto ${tolto ?? 'tolto'}`;
    return tolto ?? 'rifiutato (mai sul book)';
}

// --------------------------------------------------------------------------
// cicli
// --------------------------------------------------------------------------
/** Il criterio di «posizione coperta» del banco della media under
 *  (`riepilogo_cicli_media`): |se vince - se perde| <= 0,02 + 0,005 x quota
 *  dell'ultima banca del ciclo (2,00 se non ce n'e'). Per piu' esiti: il
 *  divario fra il migliore e il peggiore. */
export function coperto(valori: ReadonlyArray<number>, quotaUltimaBanca: number | null): boolean {
    if (valori.length === 0) return true;
    const c = quotaUltimaBanca ?? 2.0;
    return Math.max(...valori) - Math.min(...valori) <= 0.02 + 0.005 * c + 1e-9;
}

interface Analisi {
    ordini: OrdineBot[];
    cicli: CicloOperativo[];
}

/** I cicli operativi del bot per mercato: un ciclo nasce col primo ordine a
 *  posizione piatta e si chiude quando, senza ordini vivi, la posizione del
 *  ciclo e' coperta (o a importi pari), oppure senza abbinamenti; altrimenti
 *  lo chiude il mercato (regolamento) o resta aperto. Assegna `ciclo` agli
 *  ordini. PURA (non modifica le righe; modifica gli ordini che riceve). */
export function cicliOperativi(ordini: OrdineBot[], esiti?: Record<string, EsitoMercato> | null,
    runnerNoti?: (marketId: string) => ReadonlyArray<number> | undefined): CicloOperativo[] {
    // istanti in cui qualcosa cambia, in ordine
    const istanti = [...new Set(ordini.flatMap(o => o.righe.map(r => r._ms)))].sort((a, b) => a - b);
    const nati = new Map<number, OrdineBot[]>();
    for (const o of ordini) {
        const a = nati.get(o.primoMs) ?? [];
        a.push(o);
        nati.set(o.primoMs, a);
    }
    const cicli: CicloOperativo[] = [];
    const aperto = new Map<string, CicloOperativo>();
    const ordiniDel = (c: CicloOperativo) => ordini.filter(o => o.ciclo === c.n);
    const chiudi = (c: CicloOperativo, ms: number | null, stato: CicloOperativo['stato'], origine: string) => {
        c.aMs = ms;
        c.stato = stato;
        c.origine = origine;
        aperto.delete(c.marketId);
    };
    for (const t of istanti) {
        for (const o of nati.get(t) ?? []) {
            let c = aperto.get(o.marketId);
            if (!c) {
                c = {
                    n: cicli.length + 1, marketId: o.marketId, daMs: t, aMs: null, ordini: [], esiti: {}, altro: null,
                    garantito: 0, regolato: null, stato: 'aperto', origine: 'aperto a fine registrazione',
                    lordoConto: null, coperto: false, abbinatoBack: 0, abbinatoLay: 0,
                };
                cicli.push(c);
                aperto.set(o.marketId, c);
            }
            o.ciclo = c.n;
            c.ordini.push(o.chiave);
        }
        for (const c of [...aperto.values()]) {
            const oo = ordiniDel(c);
            if (oo.some(o => { const r = ultimaAl(o, t); return r != null && vivo(r); })) continue;
            const abb = abbinamentiDi(oo, t);
            if (abb.length === 0) {
                chiudi(c, t, 'chiuso', 'nessun abbinamento (ordini tolti)');
                continue;
            }
            const { perRunner, altro } = esitiPossibili(c.marketId, abb, esiti, runnerNoti?.(c.marketId));
            const valori = [...Object.values(perRunner), ...(altro != null ? [altro] : [])];
            const ultimaBanca = [...oo].reverse().find(o => o.lato === 'lay')?.quota ?? null;
            const pariImporti = Object.entries(nettoPerSelezione(abb)).every(([, v]) => Math.abs(v) <= 0.01);
            if (coperto(valori, ultimaBanca) && abb.some(a => a.lato === 'back') && abb.some(a => a.lato === 'lay')) {
                const g = Math.min(...valori);
                chiudi(c, t, 'chiuso', g > EPS ? 'uscita in profitto' : g < -EPS ? 'uscita in perdita' : 'uscita in pari');
            } else if (pariImporti) {
                chiudi(c, t, 'chiuso', 'uscita a importi pari (il P&L dipende dal risultato)');
            }
        }
    }
    // i numeri di ogni ciclo, dagli ordini del ciclo a fine cronologia
    for (const c of cicli) {
        const oo = ordiniDel(c);
        const abb = abbinamentiDi(oo, Number.MAX_SAFE_INTEGER);
        const { perRunner, altro } = esitiPossibili(c.marketId, abb, esiti, runnerNoti?.(c.marketId));
        c.esiti = perRunner;
        c.altro = altro;
        const valori = [...Object.values(perRunner), ...(altro != null ? [altro] : [])];
        c.garantito = valori.length ? Math.min(...valori) : 0;
        c.abbinatoBack = round2(abb.filter(a => a.lato === 'back').reduce((s, a) => s + a.importo, 0));
        c.abbinatoLay = round2(abb.filter(a => a.lato === 'lay').reduce((s, a) => s + a.importo, 0));
        const vincitori = esiti?.[c.marketId]?.vincitori ?? [];
        const statiRunner = esiti?.[c.marketId]?.runners ?? {};
        const regolabile = Object.values(statiRunner).some(s => s === 'WINNER' || s === 'LOSER');
        c.regolato = regolabile ? pnlSeVince(abb, vincitori.length === 1 ? vincitori[0] : null) : null;
        const ultimaBanca = [...oo].reverse().find(o => o.lato === 'lay')?.quota ?? null;
        c.coperto = abb.length > 0 && coperto(valori, ultimaBanca);
        const conLay = abb.some(a => a.lato === 'lay');
        const conBack = abb.some(a => a.lato === 'back');
        // il metodo del banco (riepilogo_cicli_media): nessuna posizione -> 0;
        // coperto con entrambi i lati abbinati -> profitto bloccato; altrimenti
        // il risultato del mercato; senza risultato: esito ignoto
        if (abb.length === 0) c.lordoConto = 0;
        else if (c.coperto && conLay && conBack) c.lordoConto = c.garantito;
        else c.lordoConto = c.regolato;
        if (c.stato === 'aperto') {
            const chiusoMs = esiti?.[c.marketId]?.chiuso_ms ?? null;
            if (abb.length > 0 && c.regolato != null) {
                c.stato = 'regolato';
                c.aMs = chiusoMs;
                c.origine = 'chiusura del mercato (posizione regolata col risultato)';
            }
        }
    }
    return cicli;
}

function nettoPerSelezione(abb: ReadonlyArray<Abbinamento>): Record<number, number> {
    const out: Record<number, number> = {};
    for (const a of abb) out[a.selectionId] = (out[a.selectionId] ?? 0) + (a.lato === 'back' ? a.importo : -a.importo);
    return out;
}

/** Tutto il registro: ordini, cicli ed eventi in ordine di tempo (a pari
 *  istante: prima gli eventi degli ordini, poi le chiusure di ciclo). PURA. */
export function analizza(righe: ReadonlyArray<RigaBot>, esiti?: Record<string, EsitoMercato> | null,
    runnerNoti?: (marketId: string) => ReadonlyArray<number> | undefined): Analisi & { eventi: EventoOperazione[] } {
    const ordini = ordiniDaRighe(righe);
    const cicli = cicliOperativi(ordini, esiti, runnerNoti);
    const perChiave = new Map(ordini.map(o => [o.chiave, o]));
    const eventi: EventoOperazione[] = [];
    for (const o of ordini) eventi.push(...eventiDellOrdine(o, perChiave, ordini));
    for (const c of cicli) {
        if (c.aMs == null) continue;
        eventi.push({
            id: `ciclo:${c.n}`, ms: c.aMs, tipo: c.stato === 'regolato' ? 'mercato_chiuso' : 'ciclo_chiuso',
            ordine: null, marketId: c.marketId, selectionId: null, lato: null, quota: null, importo: null,
            abbinatoEvento: 0, prezzoEvento: null, abbinato: 0, prezzoMedio: 0, residuo: 0, tolto: 0,
            sostituisce: null, daQuota: null, daImporto: null, riprezzoDichiarato: false, motivoSostituzione: null,
            integra: null, integraResiduo: null, sostituitoDa: null, ciclo: c.n, cicloInfo: c,
        });
    }
    const peso = (e: EventoOperazione) => (e.ordine ? 0 : 1);
    const pos = new Map(eventi.map((e, i) => [e.id, i]));
    eventi.sort((a, b) => (a.ms - b.ms) || (peso(a) - peso(b)) || ((pos.get(a.id) ?? 0) - (pos.get(b.id) ?? 0)));
    return { ordini, cicli, eventi };
}

// --------------------------------------------------------------------------
// conti
// --------------------------------------------------------------------------
export interface Conto {
    lordo: number;
    commissione: number;
    netto: number;
    mercati: Record<string, number>;
    mercatiNonRegolati: string[];
}

/** Profitto di UNA scommessa a regolamento (formula e arrotondamento di
 *  flumine `SimulatedOrder.profit`, come `applica_bot._profitto_ordine`). PURA. */
export function profittoOrdine(lato: Lato, abbinato: number, prezzo: number, statoRunner: string): number {
    if (abbinato <= 0) return 0;
    if (statoRunner === 'WINNER') {
        const v = round2(abbinato * (prezzo - 1));
        return lato === 'back' ? v : -v;
    }
    if (statoRunner === 'LOSER') return lato === 'back' ? -abbinato : abbinato;
    return 0;
}

/** Il P&L A REGOLAMENTO (risultato del mercato registrato) dall'ultima riga di
 *  ogni ordine: stesse regole di `applica_bot.conto_regolato`. PURA. */
export function contoRegolato(ordini: ReadonlyArray<OrdineBot>, esiti: Record<string, EsitoMercato> | null | undefined,
    aliquota?: number | null, finoA: number = Number.MAX_SAFE_INTEGER): Conto {
    const perMercato: Record<string, number> = {};
    const nonRegolati: string[] = [];
    for (const o of ordini) {
        const r = ultimaAl(o, finoA);
        if (!r) continue;
        const stati = esiti?.[o.marketId]?.runners ?? {};
        if (!Object.values(stati).some(s => s === 'WINNER' || s === 'LOSER')) {
            if (num(r.size_matched) > 0 && !nonRegolati.includes(o.marketId)) nonRegolati.push(o.marketId);
            continue;
        }
        const p = profittoOrdine(o.lato, num(r.size_matched), num(r.average_price_matched), stati[String(o.selectionId)] ?? '');
        perMercato[o.marketId] = round2((perMercato[o.marketId] ?? 0) + round2(p));
    }
    const aliq = (m: string) => aliquota ?? esiti?.[m]?.aliquota ?? 0.05;
    const comm: Record<string, number> = {};
    for (const [m, v] of Object.entries(perMercato)) comm[m] = v > 0 ? round2(v * aliq(m)) : 0;
    const lordo = round2(Object.values(perMercato).reduce((s, v) => s + v, 0));
    return {
        lordo,
        commissione: round2(Object.values(comm).reduce((s, v) => s + v, 0)),
        netto: round2(Object.entries(perMercato).reduce((s, [m, v]) => s + round2(v - comm[m]), 0)),
        mercati: perMercato,
        mercatiNonRegolati: nonRegolati,
    };
}

/** Il P&L dei cicli col metodo del banco della media under
 *  (`riepilogo_cicli_media`): somma dei contributi dei cicli con esito noto,
 *  commissione sul totale positivo, arrotondamenti alla fine. PURA. */
export function contoCicli(cicli: ReadonlyArray<CicloOperativo>, aliquota: number):
    { lordo: number; commissione: number; netto: number; cicliEsitoIgnoto: number } {
    let lordo = 0;
    let ignoti = 0;
    for (const c of cicli) {
        if (c.lordoConto == null) ignoti += 1;
        else lordo += c.lordoConto;
    }
    const comm = Math.max(lordo, 0) * aliquota;
    return { lordo: round2(lordo), commissione: round2(comm), netto: round2(lordo - comm), cicliEsitoIgnoto: ignoti };
}

/** Il riepilogo del bot all'istante `ms`: abbinato, esposizione (la perdita
 *  peggiore delle posizioni aperte), P&L dei cicli chiusi fino a t. PURA. */
export function riepilogoAl(ordini: ReadonlyArray<OrdineBot>, cicli: ReadonlyArray<CicloOperativo>, ms: number,
    esiti?: Record<string, EsitoMercato> | null, runnerNoti?: (marketId: string) => ReadonlyArray<number> | undefined):
    { abbinato: number; esposizione: number; pnlCicliChiusi: number; cicliChiusi: number; ordiniVivi: number; appoggiato: number } {
    const abb = abbinamentiDi(ordini, ms);
    let esposizione = 0;
    for (const mid of [...new Set(abb.map(a => a.marketId))]) {
        const { perRunner, altro } = esitiPossibili(mid, abb, esiti, runnerNoti?.(mid));
        const valori = [...Object.values(perRunner), ...(altro != null ? [altro] : [])];
        const peggio = valori.length ? Math.min(...valori) : 0;
        if (peggio < 0) esposizione += -peggio;
    }
    const chiusi = cicli.filter(c => c.stato === 'chiuso' && c.aMs != null && c.aMs <= ms);
    const stato = statoOrdiniAl(ordini, ms);
    return {
        abbinato: round2(abb.reduce((s, a) => s + a.importo, 0)),
        esposizione: round2(esposizione),
        pnlCicliChiusi: round2(chiusi.reduce((s, c) => s + c.garantito, 0)),
        cicliChiusi: chiusi.length,
        ordiniVivi: stato.filter(x => x.vivo).length,
        appoggiato: round2(stato.reduce((s, x) => s + x.residuo, 0)),
    };
}

// --------------------------------------------------------------------------
// il salto della timeline (seek)
// --------------------------------------------------------------------------
/** L'indice del passo della timeline che CONTIENE l'istante `ms` (l'ultimo
 *  passo con inizio <= ms; 0 se ms precede la timeline). PURA. */
export function indiceTimelineAl(timeline: ReadonlyArray<{ ts: string }>, ms: number): number {
    let lo = 0;
    let hi = timeline.length;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (Date.parse(timeline[mid].ts) <= ms) lo = mid + 1; else hi = mid;
    }
    return Math.max(0, lo - 1);
}

/** Il cursore ESATTO: l'istante voluto vale solo finche' la barra resta sul
 *  passo in cui e' stato messo (muovere la barra lo annulla). PURA. */
export function istanteCursore(timeline: ReadonlyArray<{ ts: string }>, indice: number,
    esatto: { index: number; ms: number } | null): { ts: string; ms: number; esatto: boolean } {
    const passo = timeline[indice]?.ts ?? '';
    if (esatto && esatto.index === indice) return { ts: new Date(esatto.ms).toISOString(), ms: esatto.ms, esatto: true };
    return { ts: passo, ms: passo ? Date.parse(passo) : 0, esatto: false };
}

// --------------------------------------------------------------------------
// testi per il trader (registro)
// --------------------------------------------------------------------------
/** Un importo/quota all'italiana con due decimali. PURA. */
export function eur(x: number | null | undefined): string {
    if (x == null || !Number.isFinite(x)) return '—';
    return x.toFixed(2).replace('.', ',');
}
/** Un P&L col segno. PURA. */
export function pnl(x: number | null | undefined): string {
    if (x == null || !Number.isFinite(x)) return '—';
    const v = Math.round(x * 100) / 100;
    return `${v > 0 ? '+' : v < 0 ? '−' : ''}${eur(Math.abs(v))}`;
}
export const nomeLato = (l: Lato | null): string => (l === 'lay' ? 'BANCA' : l === 'back' ? 'PUNTA' : '');

/** La frase dell'evento per il registro (quota, importi, residuo, legami). PURA. */
export function testoEvento(e: EventoOperazione): string {
    const lato = nomeLato(e.lato);
    switch (e.tipo) {
        case 'piazzato': {
            const base = `${lato} ${eur(e.importo)} @ ${eur(e.quota)} inviata`;
            if (!e.sostituisce) {
                return e.integra
                    ? `INTEGRAZIONE della ${lato}: +${eur(e.importo)} @ ${eur(e.quota)} (alla stessa quota della ${lato} già sul book${e.integraResiduo != null ? `, ${eur(e.integraResiduo)} non abbinati` : ''})`
                    : base;
            }
            const comeDichiarato = e.riprezzoDichiarato ? ' (replace di Betfair)' : '';
            const motivo = e.motivoSostituzione ? ` ${e.motivoSostituzione}` : '';
            if (e.daQuota != null && e.quota != null && Math.abs(e.daQuota - e.quota) > 1e-9) {
                return `${lato} SPOSTATA da ${eur(e.daQuota)} a ${eur(e.quota)} (riprezzo, ${eur(e.importo)})${comeDichiarato}${motivo}`;
            }
            const stessoImporto = e.daImporto != null && e.importo != null && Math.abs(e.daImporto - e.importo) < EPS;
            return stessoImporto
                ? `${lato} tolta e RIMESSA identica ${eur(e.importo)} @ ${eur(e.quota)}${motivo}${comeDichiarato}`
                : `${lato} RIMESSA @ ${eur(e.quota)}: importo da ${eur(e.daImporto)} a ${eur(e.importo)}${motivo}${comeDichiarato}`;
        }
        case 'appoggiato':
            return `appoggiata sul book: ${eur(e.residuo)} non abbinati @ ${eur(e.quota)}`;
        case 'abbinato_parziale':
            return `abbinata IN PARTE ${eur(e.abbinatoEvento)} @ ${eur(e.prezzoEvento)} — totale ${eur(e.abbinato)} su ${eur(e.importo)}, residuo ${eur(e.residuo)}`;
        case 'abbinato_totale':
            return `abbinata PER INTERO: ${eur(e.abbinatoEvento)} @ ${eur(e.prezzoEvento)} (totale ${eur(e.abbinato)} @ media ${eur(e.prezzoMedio)})`;
        case 'annullo_richiesto':
            return 'richiesta di annullo';
        case 'riprezzo_richiesto':
            return 'richiesta di riprezzo (replace)';
        case 'annullato':
            return e.sostituitoDa
                ? `TOLTA ${eur(e.tolto)} non abbinati (abbinato ${eur(e.abbinato)}): sostituita dal nuovo ordine`
                : `ANNULLATA ${eur(e.tolto)} non abbinati (abbinato ${eur(e.abbinato)})`;
        case 'scaduto':
            return `SCADUTA (lapse) ${eur(e.tolto)} non abbinati (abbinato ${eur(e.abbinato)})`;
        case 'void':
            return `annullata da Betfair (void) ${eur(e.tolto)}`;
        case 'rifiutato':
            return 'RIFIUTATA o mai arrivata sul book (nessun abbinamento)';
        case 'ciclo_chiuso':
        case 'mercato_chiuso': {
            const c = e.cicloInfo;
            if (!c) return 'ciclo chiuso';
            const esiti = Object.values(c.esiti);
            const forbice = esiti.length > 1 && Math.max(...esiti) - Math.min(...esiti) > EPS
                ? ` (esiti da ${pnl(Math.min(...esiti))} a ${pnl(Math.max(...esiti))})` : '';
            const valore = c.stato === 'regolato' ? `P&L regolato ${pnl(c.regolato)}` : `P&L ${pnl(c.garantito)}${forbice}`;
            return `CICLO ${c.n} ${c.stato === 'regolato' ? 'regolato alla chiusura del mercato' : 'chiuso'}: ${c.origine} — ${valore}`;
        }
        default:
            return e.tipo;
    }
}

/** Il motivo per il trader quando un ordine nuovo prende il posto di uno
 *  tolto: se fra la richiesta di annullo e la nascita del nuovo e' nata una
 *  scommessa dell'altro lato sulla stessa selezione (un rientro), l'ordine e'
 *  stato tolto «per il rientro» e rimesso. PURA. */
export function motivoSostituzione(nuovo: OrdineBot, vecchio: OrdineBot, ordini: ReadonlyArray<OrdineBot>): string | null {
    const richiesta = vecchio.righe.find(r => r.status === 'CANCELLING' || r.status === 'REPLACING' || num(r.size_cancelled) > EPS);
    const da = richiesta?._ms ?? vecchio.ultimoMs;
    // la scommessa dell'altro lato deve essere NUOVA (non a sua volta una quota
    // spostata: uno scalper sposta le sue due quote insieme, non e' un rientro)
    const rientro = ordini.find(o => o !== nuovo && o !== vecchio && !o.sostituisce && o.marketId === nuovo.marketId
        && o.selectionId === nuovo.selectionId && o.lato !== nuovo.lato && o.primoMs >= da && o.primoMs <= nuovo.primoMs);
    if (!rientro) return null;
    // «rientro» solo se la nuova scommessa AUMENTA una posizione gia' abbinata
    // dello stesso lato (la media under: punta in piu', banca da rifare); altrimenti
    // si dice soltanto cosa e' nato insieme (es. le due quote di uno scalper)
    const aumenta = rientro.ciclo != null && ordini.some(o => o !== rientro && o.ciclo === rientro.ciclo
        && o.marketId === rientro.marketId && o.selectionId === rientro.selectionId
        && o.lato === rientro.lato && o.primoMs < rientro.primoMs && num(ultimaAl(o, rientro.primoMs)?.size_matched) > EPS);
    return aumenta
        ? `(tolta per il rientro: ${nomeLato(rientro.lato)} ${eur(rientro.importo)} @ ${eur(rientro.quota)}, poi rimessa)`
        : `(tolta e rimessa insieme a una nuova ${nomeLato(rientro.lato)} ${eur(rientro.importo)} @ ${eur(rientro.quota)})`;
}

// --------------------------------------------------------------------------
// i clic «Attiva adesso» (dati del banco) nel registro
// --------------------------------------------------------------------------
export interface ClicRegistro {
    id: string;
    ms: number;
    esito: string;
    eseguito: boolean;
    /** frase per il trader: «ESEGUITO: prima punta ...» o «RIFIUTATO: motivo» */
    testo: string;
    /** dove portare la timeline col clic sull'esito (la prima punta, se c'e') */
    seekMs: number;
    ordine: string | null;
    marketId: string | null;
}

export interface ClicIn {
    id: string;
    clic_ms: number;
    letto_ms: number | null;
    esito: string;
    motivo: string | null;
    prima_punta: { ordine: string; quota: number | null; importo: number | null; ms: number } | null;
}

/** Il ciclo aperto a un istante (su un mercato, se dato). PURA. */
export function cicloApertoAl(cicli: ReadonlyArray<CicloOperativo>, ms: number, marketId?: string): CicloOperativo | null {
    return cicli.find(c => (!marketId || c.marketId === marketId) && c.daMs <= ms && (c.aMs == null || c.aMs > ms)) ?? null;
}

/** I clic col loro esito leggibile. Un rifiuto per «posizione aperta» viene
 *  spiegato con la cronologia: quale ciclo era aperto e che cosa lo teneva
 *  aperto (es. «il ciclo 3 e' ancora aperto: BANCA 50,19 @ 2,14 non
 *  abbinata, abbinata per intero solo alle 3'28"»). PURA. */
export function clicNelRegistro(clic: ReadonlyArray<ClicIn> | null | undefined, ordini: ReadonlyArray<OrdineBot>,
    cicli: ReadonlyArray<CicloOperativo>, etichetta: (ms: number) => string = () => ''): ClicRegistro[] {
    if (!clic) return [];
    const quando = (ms: number) => etichetta(ms) || new Date(ms).toISOString().slice(11, 19);
    return clic.map(c => {
        const ms = c.letto_ms ?? c.clic_ms;
        if (c.esito === 'eseguito') {
            const p = c.prima_punta;
            const o = p ? ordini.find(x => x.chiave === `o:${p.ordine}`) : undefined;
            return {
                // la timeline va alla PRIMA RIGA dell'ordine (quando lo specchio lo
                // vede: lo scalper specchia ogni secondo come in produzione), cosi'
                // che sul ladder l'ordine ci sia
                id: c.id, ms: c.clic_ms, esito: c.esito, eseguito: true, seekMs: o?.primoMs ?? p?.ms ?? c.clic_ms,
                ordine: o?.chiave ?? null, marketId: o?.marketId ?? null,
                testo: p ? `ESEGUITO: prima punta ${eur(p.importo)} @ ${eur(p.quota)} alle ${quando(p.ms)}`
                    : 'ESEGUITO per il banco, ma nessuna prima punta è nata',
            };
        }
        let motivo = c.motivo ?? c.esito;
        let marketId: string | null = null;
        if (/posizione aperta|ordine vivo/i.test(motivo)) {
            const ciclo = cicloApertoAl(cicli, ms);
            if (ciclo) {
                marketId = ciclo.marketId;
                const perche = ordini.filter(o => o.ciclo === ciclo.n)
                    .map(o => ({ o, r: ultimaAl(o, ms) }))
                    .filter((x): x is { o: OrdineBot; r: RigaBot } => x.r != null && vivo(x.r))
                    .map(({ o, r }) => {
                        const intero = o.righe.find(z => num(z.size_matched) > EPS && num(z.size_matched) + EPS >= num(z.size));
                        const abb = num(r.size_matched);
                        return `${nomeLato(o.lato)} ${eur(o.importo)} @ ${eur(o.quota)} ${abb > EPS ? `abbinata ${eur(abb)}` : 'non ancora abbinata'}`
                            + (intero ? `, abbinata per intero solo alle ${quando(intero._ms)}` : ', mai abbinata per intero');
                    });
                motivo = `il ciclo ${ciclo.n} è ancora aperto${perche.length ? `: ${perche.join('; ')}` : ' (posizione non coperta)'}`;
            }
        }
        return {
            id: c.id, ms: c.clic_ms, esito: c.esito, eseguito: false, seekMs: c.clic_ms, ordine: null, marketId,
            testo: `${c.esito === 'rifiutato' ? 'RIFIUTATO' : c.esito.toUpperCase()}: ${motivo}`,
        };
    });
}
