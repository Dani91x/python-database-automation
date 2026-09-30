// ============================================================================
// cashOutPartita.ts - 30/09 (P12a, blocco B12 del monitor veritiero).
// IL CASH OUT DELLA PARTITA: quanto guadagno/perdo SE CHIUDO TUTTO ADESSO.
// Parte PURA: niente React, niente I/O.
//
// Ordine dell'utente (30/09): «deve fare la somma di tutte le operazioni che
// ci sono ora e darmi il valore esatto di quando guadagno/perdo chiudendo
// tutto in quello specifico momento». Prima la scheda diceva «nessuna
// posizione viva del bot» (contava solo Safe) con due gambe vive di Mike.
//
// MATEMATICA: porting di `Betfair/mike/engine.py::cashout_value` (:933-1005)
// e di `Betfair/stream/trading/greenup.py::compute_greenup` (:118-247), la
// stessa gia' rispecchiata in `components/trading/CashOutButton.tsx`
// (`hedgeSide`/`partialLockedPnl`). Nessuna terza formula:
//   1. solo l'ABBINATO e' una posizione (il residuo sul book no);
//   2. l'esposizione si raggruppa per (mercato, selezione), NON per riga, e
//      per TUTTI i bot della stessa modalita': gambe che si compensano si
//      nettano (una partita pareggiata vale ~0, non due gambe in perdita);
//      su un mercato a DUE esiti con gambe su entrambe le selezioni la gamba
//      sull'altra selezione pesa rovesciata (engine.exposure :680-715) e la
//      chiave e' la selezione LUNGA (engine._chiave_ou45 :795-798);
//   3. green-up PIENO al miglior prezzo corrente del lato opposto:
//      W > L -> banca al miglior lay, W <= L -> punta al miglior back;
//      importo = round(|W - L| / p, 2) (greenup._hedge_size :109-111);
//      esiti dopo la chiusura, P&L bloccato = il peggiore dei due;
//   4. commissione per MERCATO sul netto positivo (engine :978-992), ripartita
//      pro-rata sulle selezioni in utile, residuo di arrotondamento sulla
//      selezione di peso maggiore (engine :993-1002);
//   5. FAIL-CLOSED (engine `complete=false` :966-968): se anche UNA selezione
//      viva non ha prezzo -> nessuna cifra (`netto: null`), `mancanti` dice
//      quale. Una somma monca sarebbe una bugia.
// Arrotondamenti come Betfair: profitto di OGNI scommessa al centesimo
// (anche l'ordine di chiusura), commissione = round(aliquota x netto del
// mercato, 2). Sulle cifre dei test Python i numeri coincidono con l'engine
// (tabella nel referto C_P12a.md).
//
// LIVE e PAPER sono due somme separate, mai una: una gamba PROVA non entra
// mai nel live, e una gamba con modalita' NON dichiarata rende il live non
// calcolabile (non si sa se sono soldi veri).
//
// DIFFERENZE DICHIARATE rispetto all'engine di Mike (nel referto):
//   * una selezione PIATTA (|W - L| < 0,01) qui vale il suo bloccato
//     min(W, L) (l'engine la esclude: per lui non c'e' niente da chiudere; per
//     il trader quel +0,05 e' denaro della partita);
//   * una chiusura che arrotondata al centesimo varrebbe 0,00 (|W-L|/p <
//     0,005): qui vale min(W, L) con `residuoNonPiazzabile` (l'engine la
//     rende incompleta);
//   * la copertura come BANCA di apertura su una sola selezione (Mike, banca
//     Under 4,5) qui si chiude PUNTANDO la stessa selezione (come il «chiudi
//     ora» della riga); Mike la chiude bancando l'Over 4,5 (engine
//     _chiave_ou45 :788-792). Stesso rischio tolto, prezzo di un altro libro:
//     le due cifre possono differire di qualche centesimo.
// ============================================================================
import type { FontePrezzo, PrezzoScheda } from '@/lib/schedaAlMs';
import { statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';
import { etaQuoteS, type MikeEvent } from '@/lib/mike';

/** Sotto 1 centesimo di sbilancio la selezione e' piatta (greenup.FLAT_EPS). */
export const PIATTO_EPS = 0.01;
/** W_C: sotto 2 centesimi e SENZA prezzo, la selezione e' «pareggiata». */
export const PAREGGIATA_EPS = 0.02;

const fmtCent = (v: number) => `${r2(v).toFixed(2).replace('.', ',')}`;
/** Sotto mezzo centesimo un abbinato non esiste (statoOrdine.EPS). */
const ABBINATO_EPS = 0.005;
/** L'aliquota quando la gamba non la porta (`useControlRoom.aliquotaDi`). */
export const ALIQUOTA_DI_RIPIEGO_PARTITA = 0.05;

/** Arrotondamento al centesimo, simmetrico sul segno, robusto sui float
 *  (0,145 -> 0,15; -0,5066 -> -0,51). */
export function r2(x: number): number {
    const s = x < 0 ? -1 : 1;
    return (s * Math.round(Math.abs(x) * 100 + 1e-7)) / 100;
}

/** Una gamba ABBINATA (o parzialmente abbinata) di un bot sulla partita. */
export interface GambaViva {
    /** id della riga del bot (per la scomposizione) */
    id: number | string;
    bot: string;
    /** null = non dichiarata: rende il LIVE non calcolabile (fail-closed) */
    modalita: 'live' | 'paper' | null;
    marketId: string | null;
    selectionId: number | null;
    /** nome della selezione, per il trader */
    selezione: string | null;
    lato: 'back' | 'lay' | null;
    /** importo ABBINATO (null = non dichiarato) */
    abbinato: number | null;
    /** prezzo MEDIO abbinato (null = non dichiarato) */
    prezzoMedio: number | null;
    /** aliquota della riga (0,05 o 5); null = ripiego 5 % */
    aliquota: number | null;
    /** true = mercato a DUE esiti (Over/Under, testa a testa tennis) */
    dueEsiti?: boolean;
    /** una gamba che la pagina NON sa scomporre (es. sessione scalper): il
     *  motivo va in `mancanti` se e' abbinata */
    nonScomponibile?: string | null;
    /** W_C (30/09 sera): esposizione GIA' calcolata dal bot per la selezione
     *  (sessione scalper, `esposizioneScalper`): P&L se vince / se perde
     *  dell'ABBINATO. Se c'e', `lato`/`abbinato`/`prezzoMedio` non servono. */
    esposizione?: { win: number; lose: number } | null;
}

/** Una componente della posizione (la gamba come la ha fatta il bot). */
export interface ComponenteCashOut {
    id: number | string;
    bot: string;
    /** null = componente «esposizione» (W/L gia' calcolati dal bot) */
    lato: 'back' | 'lay' | null;
    abbinato: number | null;
    prezzo: number | null;
    selectionId: number;
    selezione: string | null;
    esposizione?: { win: number; lose: number };
}

export type StatoPosizione = 'da_chiudere' | 'piatta' | 'decisa' | 'senza_prezzo' | 'mercato_non_aperto';

/** Una posizione per (mercato, selezione): cio' che si chiude con UN ordine. */
export interface PosizioneCashOut {
    chiave: string;
    marketId: string;
    selectionId: number;
    selezione: string | null;
    /** bot presenti nella posizione (uno o piu') */
    bot: string[];
    componenti: ComponenteCashOut[];
    /** lato/abbinato/prezzo d'ingresso quando la posizione e' UNA gamba sola */
    lato: 'back' | 'lay' | null;
    abbinato: number | null;
    prezzoIngresso: number | null;
    /** P&L se la selezione vince / perde (al centesimo, come Betfair) */
    seVince: number;
    sePerde: number;
    latoChiusura: 'back' | 'lay' | null;
    importoChiusura: number | null;
    prezzoChiusura: number | null;
    /** P&L bloccato LORDO; null = non calcolabile */
    pnlLordo: number | null;
    /** P&L bloccato NETTO (quota della commissione del suo mercato) */
    pnl: number | null;
    fontePrezzo: FontePrezzo | null;
    etaPrezzoS: number | null;
    /** euro disponibili al prezzo di chiusura */
    abbinabile: number | null;
    /** il miglior prezzo copre l'importo di chiusura? null = non si sa */
    liquiditaSufficiente: boolean | null;
    residuoNonPiazzabile: boolean;
    stato: StatoPosizione;
}

export interface MercatoCashOut {
    marketId: string;
    lordo: number | null;
    aliquota: number;
    commissione: number | null;
    netto: number | null;
}

export interface CashOutModalita {
    /** NETTO di commissione se chiudo TUTTO adesso; null = NON CALCOLABILE */
    netto: number | null;
    lordo: number | null;
    commissione: number | null;
    completo: boolean;
    /** perche' non e' calcolabile, una frase per selezione/gamba */
    mancanti: string[];
    /** avvisi che NON tolgono la cifra (liquidita', aliquote diverse) */
    avvisi: string[];
    gambe: PosizioneCashOut[];
    perMercato: MercatoCashOut[];
    /** eta' del prezzo PIU' VECCHIO usato (s); null = ignota o nessun prezzo */
    etaPrezziS: number | null;
    /** almeno un prezzo usato ha eta' ignota */
    etaIgnota: boolean;
    /** almeno una chiusura supera la liquidita' al miglior prezzo */
    liquiditaInsufficiente: boolean;
    /** quante gambe ABBINATE (righe dei bot) sono entrate */
    nGambe: number;
}

export interface CashOutPartitaRisultato {
    live: CashOutModalita;
    paper: CashOutModalita;
}

export interface OpzioniCashOut {
    /** prezzo corrente della selezione (ladder al ms o scanner, dichiarato) */
    prezzo: (marketId: string, selectionId: number) => PrezzoScheda | null;
    nowMs: number;
    /** esito GIA' certo della selezione (linea superata dai gol, engine C2):
     *  true vinta, false persa, null in gioco. Assente = nessuna decisa. */
    esitoDeciso?: (marketId: string, selectionId: number) => boolean | null;
}

const valido = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const quotaValida = (v: unknown): number | null => (valido(v) && v > 1 ? v : null);

function aliquotaDi(g: GambaViva): number {
    const a = g.aliquota;
    if (!valido(a) || a <= 0) return ALIQUOTA_DI_RIPIEGO_PARTITA;
    return a > 1 ? a / 100 : a;
}

function nomeSel(g: { selezione: string | null; selectionId: number | null }): string {
    return g.selezione ?? (g.selectionId != null ? `selezione ${g.selectionId}` : 'selezione ignota');
}

/** Profitto della scommessa quando VINCE la selezione su cui e' fatta, al
 *  centesimo (Betfair regola ogni scommessa al centesimo). */
const vincitaPunta = (s: number, p: number) => r2(s * (p - 1));

/** Esposizione (W, L) della selezione `sel` dalle componenti del mercato:
 *  una gamba sull'ALTRA selezione (mercato a due esiti) pesa rovesciata. */
function esposizione(componenti: readonly ComponenteCashOut[], sel: number): { w: number; l: number } {
    let w = 0;
    let l = 0;
    for (const c of componenti) {
        if (c.esposizione) {
            // W/L gia' della selezione della componente; sull'ALTRA selezione di
            // un mercato a due esiti si scambiano (vince l'una = perde l'altra)
            if (c.selectionId === sel) { w += c.esposizione.win; l += c.esposizione.lose; } else { w += c.esposizione.lose; l += c.esposizione.win; }
            continue;
        }
        if (c.abbinato == null || c.prezzo == null) continue;
        const vinc = vincitaPunta(c.abbinato, c.prezzo);
        if (c.selectionId === sel) {
            if (c.lato === 'back') { w += vinc; l -= c.abbinato; } else { w -= vinc; l += c.abbinato; }
        } else if (c.lato === 'back') {
            w -= c.abbinato; l += vinc;
        } else {
            w += c.abbinato; l -= vinc;
        }
    }
    return { w: r2(w), l: r2(l) };
}

function vuoto(): CashOutModalita {
    return {
        netto: 0, lordo: 0, commissione: 0, completo: true, mancanti: [], avvisi: [], gambe: [],
        perMercato: [], etaPrezziS: null, etaIgnota: false, liquiditaInsufficiente: false, nGambe: 0,
    };
}

/** Il cash out di UNA modalita' (le gambe sono gia' filtrate per modalita'). */
function calcolaModalita(
    gambe: readonly GambaViva[], o: OpzioniCashOut, extraMancanti: string[],
    nomi: ReadonlyMap<string, string> = new Map(),
): CashOutModalita {
    const out = vuoto();
    out.mancanti.push(...extraMancanti);
    // 1. solo l'ABBINATO, con mercato, selezione, lato e prezzo medio dichiarati
    const perMercato = new Map<string, { componenti: ComponenteCashOut[]; aliquote: Set<number>; dueEsiti: boolean }>();
    for (const g of gambe) {
        const a = g.abbinato;
        if (g.nonScomponibile) {
            if (a == null || a > ABBINATO_EPS) out.mancanti.push(`${g.bot} #${g.id}: ${g.nonScomponibile}`);
            continue;
        }
        if (g.esposizione) {
            const e = g.esposizione;
            if (!g.marketId || g.selectionId == null || !valido(e.win) || !valido(e.lose)) {
                out.mancanti.push(`esposizione incompleta: ${g.bot} #${g.id} (${nomeSel(g)})`);
                continue;
            }
            out.nGambe += 1;
            const me = perMercato.get(g.marketId) ?? { componenti: [], aliquote: new Set<number>(), dueEsiti: false };
            me.componenti.push({
                id: g.id, bot: g.bot, lato: null, abbinato: null, prezzo: null,
                selectionId: Number(g.selectionId), selezione: g.selezione, esposizione: { win: r2(e.win), lose: r2(e.lose) },
            });
            me.aliquote.add(aliquotaDi(g));
            me.dueEsiti = me.dueEsiti || g.dueEsiti === true;
            perMercato.set(g.marketId, me);
            continue;
        }
        if (a == null || !valido(a)) {
            out.mancanti.push(`importo abbinato non dichiarato: ${g.bot} #${g.id} (${nomeSel(g)})`);
            continue;
        }
        if (a <= ABBINATO_EPS) continue;      // residuo sul book: non e' una posizione
        const p = quotaValida(g.prezzoMedio);
        if (p == null) {
            out.mancanti.push(`prezzo abbinato non dichiarato: ${g.bot} #${g.id} (${nomeSel(g)})`);
            continue;
        }
        if (!g.marketId || g.selectionId == null || !valido(Number(g.selectionId))) {
            out.mancanti.push(`mercato/selezione non pubblicati: ${g.bot} #${g.id} (${nomeSel(g)})`);
            continue;
        }
        if (g.lato !== 'back' && g.lato !== 'lay') {
            out.mancanti.push(`lato non dichiarato: ${g.bot} #${g.id} (${nomeSel(g)})`);
            continue;
        }
        out.nGambe += 1;
        const m = perMercato.get(g.marketId) ?? { componenti: [], aliquote: new Set<number>(), dueEsiti: false };
        m.componenti.push({
            id: g.id, bot: g.bot, lato: g.lato, abbinato: r2(a), prezzo: p,
            selectionId: Number(g.selectionId), selezione: g.selezione,
        });
        m.aliquote.add(aliquotaDi(g));
        m.dueEsiti = m.dueEsiti || g.dueEsiti === true;
        perMercato.set(g.marketId, m);
    }

    let lordoTot = 0;
    let commTot = 0;
    let nettoTot = 0;
    let etaMax: number | null = null;
    for (const [marketId, m] of perMercato) {
        // aliquota del mercato: se le righe non concordano si usa la PIU' ALTA
        // (prudente: la cifra non si gonfia) e lo si dice
        const aliquote = Array.from(m.aliquote);
        const aliquota = Math.max(...aliquote);
        if (aliquote.length > 1) {
            out.avvisi.push(`mercato ${marketId}: aliquote diverse fra le righe (${aliquote.map((x) => `${r2(x * 100)} %`).join(', ')}), usata la piu' alta`);
        }
        // 2. le chiavi del mercato: una per selezione; su un mercato a due
        //    esiti con gambe su entrambe, UNA chiave (la selezione lunga)
        const selezioni = Array.from(new Set(m.componenti.map((c) => c.selectionId))).sort((x, y) => x - y);
        const chiavi: { sel: number; w: number; l: number; comp: ComponenteCashOut[] }[] = [];
        if (m.dueEsiti && selezioni.length === 2) {
            const [a, b] = selezioni;
            const ea = esposizione(m.componenti, a);
            // W_b = L_a, L_b = W_a: in un mercato a due esiti b vince se a perde
            if (ea.w - ea.l >= 0) chiavi.push({ sel: a, w: ea.w, l: ea.l, comp: m.componenti });
            else chiavi.push({ sel: b, w: ea.l, l: ea.w, comp: m.componenti });
        } else {
            for (const s of selezioni) {
                const comp = m.componenti.filter((c) => c.selectionId === s);
                const e = esposizione(comp, s);
                chiavi.push({ sel: s, w: e.w, l: e.l, comp });
            }
        }
        const posizioni: PosizioneCashOut[] = [];
        let lordoMercato: number | null = 0;
        for (const k of chiavi) {
            const uno = k.comp.length === 1 ? k.comp[0] : null;
            const pos: PosizioneCashOut = {
                chiave: `${marketId}|${k.sel}`, marketId, selectionId: k.sel,
                // il nome della selezione CHIAVE; se nessuna gamba e' su quella
                // (mercato a due esiti) il nome non si inventa: null
                // W_C: prima dell'id grezzo, il nome dalle altre gambe della
                // stessa (mercato, selezione) di qualunque bot/modalita'
                selezione: k.comp.find((c) => c.selectionId === k.sel)?.selezione
                    ?? nomi.get(`${marketId}|${k.sel}`) ?? null,
                bot: Array.from(new Set(k.comp.map((c) => c.bot))),
                componenti: k.comp,
                lato: uno ? uno.lato : null, abbinato: uno ? uno.abbinato : null,
                prezzoIngresso: uno ? uno.prezzo : null,
                seVince: k.w, sePerde: k.l,
                latoChiusura: null, importoChiusura: null, prezzoChiusura: null,
                pnlLordo: null, pnl: null, fontePrezzo: null, etaPrezzoS: null,
                abbinabile: null, liquiditaSufficiente: null, residuoNonPiazzabile: false,
                stato: 'da_chiudere',
            };
            const nomeTrader = pos.selezione ?? `selezione ${k.sel}`;
            const deciso = o.esitoDeciso?.(marketId, k.sel) ?? null;
            const d = k.w - k.l;
            if (deciso !== null) {
                // engine C2: esito gia' certo, vale W o L senza prezzo
                pos.stato = 'decisa';
                pos.pnlLordo = deciso ? k.w : k.l;
            } else if (Math.abs(d) < PIATTO_EPS) {
                pos.stato = 'piatta';
                pos.pnlLordo = r2(Math.min(k.w, k.l));
            } else {
                const lato: 'back' | 'lay' = d > 0 ? 'lay' : 'back';
                pos.latoChiusura = lato;
                const pz = o.prezzo(marketId, k.sel);
                const prezzo = pz ? quotaValida(lato === 'lay' ? pz.lay : pz.back) : null;
                const statoM = pz?.statoMercato ? String(pz.statoMercato).toUpperCase() : null;
                if (statoM && statoM !== 'OPEN') {
                    pos.stato = 'mercato_non_aperto';
                    out.mancanti.push(`mercato ${statoM === 'SUSPENDED' ? 'SOSPESO' : statoM === 'CLOSED' ? 'CHIUSO' : statoM} per ${nomeTrader}: adesso non si chiude`);
                } else if ((prezzo == null || !pz) && r2(Math.abs(d)) < PAREGGIATA_EPS) {
                    // W_C (basso del revisore): sbilancio sotto 2 centesimi e
                    // prezzo assente: e' una partita PAREGGIATA, vale il bloccato
                    pos.stato = 'piatta';
                    pos.pnlLordo = r2(Math.min(k.w, k.l));
                    out.avvisi.push(`${nomeTrader}: pareggiata (±${fmtCent(Math.abs(d))}), prezzo assente: vale il bloccato`);
                } else if (prezzo == null || !pz) {
                    pos.stato = 'senza_prezzo';
                    out.mancanti.push(`manca il prezzo di ${nomeTrader} (${lato === 'lay' ? 'banca' : 'punta'})`);
                } else {
                    const importo = r2(Math.abs(d) / prezzo);
                    pos.prezzoChiusura = prezzo;
                    pos.fontePrezzo = pz.fonte;
                    pos.etaPrezzoS = pz.istanteMs == null ? null : Math.max(0, (o.nowMs - pz.istanteMs) / 1000);
                    if (pos.etaPrezzoS == null) out.etaIgnota = true;
                    else etaMax = etaMax == null ? pos.etaPrezzoS : Math.max(etaMax, pos.etaPrezzoS);
                    if (importo <= 0) {
                        // la chiusura arrotondata al centesimo vale 0,00: non si piazza
                        pos.stato = 'piatta';
                        pos.residuoNonPiazzabile = true;
                        pos.pnlLordo = r2(Math.min(k.w, k.l));
                    } else {
                        pos.importoChiusura = importo;
                        const vinc = vincitaPunta(importo, prezzo);
                        const w2 = lato === 'lay' ? r2(k.w - vinc) : r2(k.w + vinc);
                        const l2 = lato === 'lay' ? r2(k.l + importo) : r2(k.l - importo);
                        pos.pnlLordo = Math.min(w2, l2);
                        const abb = lato === 'lay' ? pz.laySize : pz.backSize;
                        pos.abbinabile = valido(abb) ? abb : null;
                        pos.liquiditaSufficiente = pos.abbinabile == null ? null : pos.abbinabile + 1e-9 >= importo;
                        if (pos.liquiditaSufficiente === false) {
                            out.liquiditaInsufficiente = true;
                            out.avvisi.push(`liquidita' insufficiente al miglior prezzo per ${nomeTrader}: ${r2(pos.abbinabile ?? 0)} disponibili su ${importo} da chiudere - la cifra e' il caso migliore`);
                        }
                    }
                }
            }
            if (pos.pnlLordo == null) lordoMercato = null;
            else if (lordoMercato != null) lordoMercato = r2(lordoMercato + pos.pnlLordo);
            posizioni.push(pos);
        }
        // 4. commissione per MERCATO sul netto positivo, ripartita pro-rata
        const merc: MercatoCashOut = { marketId, lordo: lordoMercato, aliquota, commissione: null, netto: null };
        if (lordoMercato != null) {
            const comm = lordoMercato > 0 ? r2(aliquota * lordoMercato) : 0;
            merc.commissione = comm;
            merc.netto = r2(lordoMercato - comm);
            const positivi = posizioni.reduce((s, p) => s + (p.pnlLordo != null && p.pnlLordo > 0 ? p.pnlLordo : 0), 0);
            for (const p of posizioni) {
                const quota = p.pnlLordo != null && p.pnlLordo > 0 && positivi > 0 ? comm * (p.pnlLordo / positivi) : 0;
                p.pnl = p.pnlLordo == null ? null : r2(p.pnlLordo - quota);
            }
            // il residuo di arrotondamento sulla posizione di peso maggiore:
            // la somma delle righe fa il netto del mercato (engine :993-1002)
            const somma = r2(posizioni.reduce((s, p) => s + (p.pnl ?? 0), 0));
            const scarto = r2(merc.netto - somma);
            if (scarto !== 0 && posizioni.length > 0) {
                const pesante = posizioni.reduce((a, b) => (Math.abs(b.pnl ?? 0) > Math.abs(a.pnl ?? 0) ? b : a));
                pesante.pnl = r2((pesante.pnl ?? 0) + scarto);
            }
            lordoTot += lordoMercato;
            commTot += comm;
            nettoTot += merc.netto;
        }
        out.perMercato.push(merc);
        out.gambe.push(...posizioni);
    }
    out.etaPrezziS = etaMax;
    out.completo = out.mancanti.length === 0;
    if (out.completo) {
        out.lordo = r2(lordoTot);
        out.commissione = r2(commTot);
        out.netto = r2(nettoTot);
    } else {
        out.lordo = null;
        out.commissione = null;
        out.netto = null;
    }
    return out;
}

/**
 * IL CASH OUT DELLA PARTITA, separato per LIVE e PAPER. `gambe` = tutte le
 * gambe dei bot sulla partita (aperture E chiusure non ancora regolate, di
 * qualunque bot); qui si tengono solo quelle abbinate.
 */
export function cashOutPartita(gambe: readonly GambaViva[], o: OpzioniCashOut): CashOutPartitaRisultato {
    const live = gambe.filter((g) => g.modalita === 'live');
    const paper = gambe.filter((g) => g.modalita === 'paper');
    const ignote = gambe.filter((g) => g.modalita !== 'live' && g.modalita !== 'paper'
        && !(g.abbinato != null && valido(g.abbinato) && g.abbinato <= ABBINATO_EPS));
    // fail-closed: una gamba abbinata senza modalita' potrebbe essere di soldi
    // veri: il LIVE non si calcola finche' non e' dichiarata
    const manc = ignote.map((g) => `modalita' non dichiarata: ${g.bot} #${g.id} (${nomeSel(g)})`);
    // i nomi delle selezioni noti a QUALUNQUE gamba (per non stampare l'id grezzo)
    const nomi = new Map<string, string>();
    for (const g of gambe) {
        if (g.marketId && g.selectionId != null && g.selezione && !nomi.has(`${g.marketId}|${g.selectionId}`)) {
            nomi.set(`${g.marketId}|${g.selectionId}`, g.selezione);
        }
    }
    return {
        live: calcolaModalita(live, o, manc, nomi),
        paper: calcolaModalita(paper, o, [], nomi),
    };
}

// ============================================================================
// DALLE RIGHE DELLA SCHEDA ALLE GAMBE. Forma strutturale di `OperazionePartita`
// (`components/controlroom/useControlRoom.ts`): solo i campi che servono, cosi'
// questo file resta puro e senza dipendenze dal modello di vista.
// ============================================================================

/** Gli identificativi di una gamba di CHIUSURA (`closes_trade_id`), nello
 *  stesso ordine di `chiusureOrdini`. OGGI la pagina NON li riceve
 *  (`useControlRoom.agg` tiene solo `ordineDi(c)`): senza, una chiusura
 *  abbinata rende la partita NON CALCOLABILE (non si indovina la selezione:
 *  la chiusura di Mike della copertura banca Under 4,5 sta sull'OVER 4,5). */
export interface IdGambaChiusura {
    id: number | null;
    marketId: string | null;
    selectionId: number | null;
}

export interface OperazionePerCashOut {
    bot: string;
    id: number;
    selezione: string | null;
    lato: 'back' | 'lay' | null;
    modalita: 'live' | 'paper' | null;
    marketId: string | null;
    selectionId: number | null;
    ordine: RigaOrdine;
    chiusureOrdini: RigaOrdine[];
    chiusura: { alMs?: { aliquota?: number | null } | undefined } | null;
    /** P&L dell'operazione; per i 4 bot tennis non nullo = ordine REGOLATO
     *  (`useControlRoom`: `pnl` solo con `settled_at`): non e' una gamba viva */
    pnl?: number | null;
    /** opzionale finche' la pagina non lo porta (v. `IdGambaChiusura`) */
    chiusureGambe?: (IdGambaChiusura | null)[];
    /** W_C: solo la sessione scalper, esposizioni per selezione dell'abbinato */
    esposizioneSelezioni?: { marketId: string; selectionId: number; selezione: string | null; win: number; lose: number }[];
    /** stato della riga (scalper: stato della SESSIONE) e residuo scoperto */
    stato?: string;
    residuo?: boolean;
}

/** Sessione scalper ferma (`chiudiRiga.SCALPER_FERMABILE` e' il complemento). */
const SESSIONE_FERMA = new Set(['stopped', 'done', 'error']);

function latoDi(side: unknown): 'back' | 'lay' | null {
    const s = String(side ?? '').toLowerCase();
    return s === 'back' ? 'back' : s === 'lay' ? 'lay' : null;
}

/** Una riga (o una sua chiusura) come gamba; null = regolata (non e' viva). */
function gambaDaOrdine(args: {
    id: number | string; bot: string; modalita: 'live' | 'paper' | null;
    marketId: string | null; selectionId: number | null; selezione: string | null;
    lato: 'back' | 'lay' | null; ordine: RigaOrdine; aliquota: number | null;
    dueEsiti: boolean;
}): GambaViva | null {
    const so = statoOrdine(args.ordine);
    if (so.esito === 'regolato') return null;
    // una riga `error` (tentativo mai abbinato: ritirato dal bot, rifiutato da
    // Betfair) o un rifiuto non e' una posizione: SOLO se non ha abbinato
    // niente. Con abbinato > 0 dichiarato conta: e' denaro sul mercato.
    const stato = String(args.ordine.status ?? '').toLowerCase();
    const abb = so.abbinato.valore;
    if ((stato === 'error' || so.esito === 'rifiutato') && !(abb != null && abb > ABBINATO_EPS)) return null;
    const g: GambaViva = {
        id: args.id, bot: args.bot, modalita: args.modalita,
        marketId: args.marketId, selectionId: args.selectionId, selezione: args.selezione,
        lato: args.lato, abbinato: so.abbinato.valore, prezzoMedio: so.prezzoMedio.valore,
        aliquota: args.aliquota, dueEsiti: args.dueEsiti,
    };
    // esito IGNOTO su Betfair: l'ordine potrebbe essere abbinato per intero
    if (so.esito === 'riconciliazione') {
        g.nonScomponibile = 'esito dell\'ordine ignoto su Betfair (in riconciliazione)';
        g.abbinato = null;
    }
    return g;
}

/**
 * Le gambe della partita dalle righe della scheda, di TUTTI i bot:
 *  - l'apertura con l'abbinato e il prezzo medio dichiarati (`statoOrdine`);
 *  - le sue chiusure (`chiusureOrdini`), che la NETTANO (partita pareggiata
 *    ~0), con i LORO mercato/selezione (`chiusureGambe`); assenti -> la gamba
 *    resta senza mercato e, se abbinata, rende la cifra NON calcolabile;
 *  - la sessione dello SCALPER: non scomponibile per selezione dalla scheda
 *    (la riga porta solo l'abbinato totale) -> dichiarato;
 *  - le righe REGOLATE non entrano.
 * `dueEsiti(marketId)` = mercato a due esiti (Over/Under, testa a testa).
 */
export function gambeDaOperazioni(
    ops: readonly OperazionePerCashOut[],
    opzioni: { dueEsiti?: (marketId: string) => boolean } = {},
): GambaViva[] {
    const out: GambaViva[] = [];
    const due = (m: string | null) => (m ? opzioni.dueEsiti?.(m) === true : false);
    for (const op of ops) {
        const aliquota = op.chiusura?.alMs?.aliquota ?? null;
        // R_C (review): i 4 bot tennis non scrivono won/lost/void (lo stato
        // flumine resta EXECUTION_COMPLETE): regolato = `pnl` valorizzato
        if (op.bot.startsWith('tennis_') && op.pnl != null && Number.isFinite(Number(op.pnl))) continue;
        if (op.bot === 'scalper') {
            const so = statoOrdine(op.ordine ?? {});
            if (so.esito === 'regolato') continue;
            // P&L reale del conto = sessione chiusa e regolata: non e' viva;
            // sessione ferma senza residuo scoperto: niente da chiudere
            if (op.pnl != null && Number.isFinite(Number(op.pnl))) continue;
            if (SESSIONE_FERMA.has(String(op.stato ?? '').toLowerCase()) && !op.residuo) continue;
            // W_C: le esposizioni ABBINATE per selezione della sessione
            // (`esposizioneScalper`): una gamba «esposizione» per selezione
            if (op.esposizioneSelezioni) {
                for (const e of op.esposizioneSelezioni) {
                    out.push({
                        id: `${op.id}/${e.selectionId}`, bot: op.bot, modalita: op.modalita,
                        marketId: e.marketId, selectionId: e.selectionId, selezione: e.selezione,
                        lato: null, abbinato: null, prezzoMedio: null, aliquota,
                        dueEsiti: due(e.marketId), esposizione: { win: e.win, lose: e.lose },
                    });
                }
                continue;
            }
            out.push({
                id: op.id, bot: op.bot, modalita: op.modalita, marketId: null, selectionId: null,
                selezione: op.selezione, lato: null, abbinato: so.abbinato.valore, prezzoMedio: null,
                aliquota,
                nonScomponibile: 'sessione dello scalper: le esposizioni per selezione non arrivano alla scheda',
            });
            continue;
        }
        const ap = gambaDaOrdine({
            id: op.id, bot: op.bot, modalita: op.modalita, marketId: op.marketId, selectionId: op.selectionId,
            selezione: op.selezione, lato: op.lato ?? latoDi(op.ordine?.side), ordine: op.ordine ?? {},
            aliquota, dueEsiti: due(op.marketId),
        });
        if (ap == null) continue;           // regolata: nemmeno le sue chiusure sono vive
        out.push(ap);
        // righe costruite a mano (test storici) possono non avere la catena
        (op.chiusureOrdini ?? []).forEach((c, i) => {
            const ids = op.chiusureGambe?.[i] ?? null;
            const g = gambaDaOrdine({
                id: ids?.id ?? `${op.id}/chiusura ${i + 1}`, bot: op.bot, modalita: op.modalita,
                marketId: ids?.marketId ?? null, selectionId: ids?.selectionId ?? null,
                selezione: ids && ids.marketId === op.marketId && ids.selectionId === op.selectionId
                    ? op.selezione : null,
                lato: latoDi(c.side), ordine: c, aliquota, dueEsiti: due(ids?.marketId ?? null),
            });
            if (g) out.push(g);
        });
    }
    return out;
}

// ============================================================================
// P12b - I PONTI CON MIKE (dati gia' in pagina: `MikeEvent` di `get_mike_state`
// / canale, nessuna lettura nuova).
// ============================================================================

/** Linea dei mercati di Mike (engine.LINE, `Betfair/mike/engine.py:35`). */
const LINEA_MIKE: Record<string, number> = { OU35: 3.5, OU45: 4.5 };

/** I mercati di Mike sono Over/Under: DUE esiti. `null` = nessun mercato noto. */
export function dueEsitiMike(mike: MikeEvent | null | undefined): ((marketId: string) => boolean) | undefined {
    const ids = new Set(Object.values(mike?.markets ?? {})
        .map((m) => m?.market_id).filter((x): x is string => typeof x === 'string' && x !== ''));
    return ids.size === 0 ? undefined : (marketId: string) => ids.has(marketId);
}

/**
 * W_C - i mercati a DUE esiti della partita: quelli di Mike (O/U) e, nel
 * TENNIS, il Match Odds (`mo_market_id` della scheda: due giocatori). Solo il
 * Match Odds del tennis: set betting e altri mercati tennis hanno piu' esiti e
 * restano per selezione.
 */
export function dueEsitiPartita(
    sport: 'calcio' | 'tennis', moMarketId: string | null | undefined,
    altri?: ((marketId: string) => boolean) | undefined,
): ((marketId: string) => boolean) | undefined {
    const mo = sport === 'tennis' && moMarketId ? String(moMarketId) : null;
    if (mo == null) return altri;
    return (m: string) => m === mo || (altri ? altri(m) : false);
}

/**
 * ESITO GIA' CERTO (engine.selection_decided, `engine.py:666-677`): con piu'
 * gol della linea l'Over ha VINTO e l'Under ha PERSO, qualunque cosa faccia il
 * mercato (la linea viene potata dal feed). Il lato della selezione (Under/
 * Over) si legge dal NOME della selezione sulle righe: se non si riconosce, la
 * selezione resta «in gioco» e senza prezzo la cifra e' NON calcolabile.
 */
export function esitoDecisoMike(
    mike: MikeEvent | null | undefined,
    nomi: readonly { marketId: string | null; selectionId: number | null; selezione: string | null }[],
): ((marketId: string, selectionId: number) => boolean | null) | undefined {
    const gol = mike?.live?.goals;
    if (mike == null || gol == null || !Number.isFinite(Number(gol))) return undefined;
    const lineaDi = new Map<string, number>();
    for (const [k, m] of Object.entries(mike.markets ?? {})) {
        if (m?.market_id && LINEA_MIKE[k] != null) lineaDi.set(m.market_id, LINEA_MIKE[k]);
    }
    return (marketId: string, selectionId: number) => {
        const linea = lineaDi.get(marketId);
        if (linea == null || Number(gol) <= linea) return null;
        const n = nomi.find((x) => x.marketId === marketId && x.selectionId === selectionId && x.selezione)?.selezione ?? '';
        if (/\bunder\b/i.test(n)) return false;
        if (/\bover\b/i.test(n)) return true;
        return null;
    };
}

/** La cifra che il SERVIZIO di Mike pubblica per la partita (`live.cashout`),
 *  con l'eta' del SUO book (`etaQuoteS`: feed + tempo dalla pubblicazione). */
export function valoreBotMike(mike: MikeEvent | null | undefined, nowMs: number): {
    bot: string; modalita: 'live' | 'paper'; netto: number | null; completo: boolean; etaS: number | null; nota: string;
} | null {
    const c = mike?.live?.cashout;
    if (!mike || !c) return null;
    const n = Number(c.net);
    return {
        bot: 'mike', modalita: mike.mode === 'live' ? 'live' : 'paper',
        netto: c.net == null || !Number.isFinite(n) ? null : n,
        completo: c.complete === true,
        etaS: etaQuoteS(mike.live, nowMs),
        nota: 'il bot conta solo le gambe di Mike, sul suo book; una copertura in banca Under 4,5 la chiude bancando l\'Over 4,5',
    };
}
