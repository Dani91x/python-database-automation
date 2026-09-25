// ============================================================================
// chiusuraAlMs.ts - 25/09 (residui B17): IL «CHIUDI» DI RIGA E LE GAMBE DELLE
// COMBO, AL PREZZO DEL MS PRIMA DEL CLIC. Parte PURA (nessun React).
//
// Prima: il «se chiudo ora» di una riga e i prezzi vivi delle gambe di una
// combo venivano SOLO dal feed dello scanner (`prezzoVivo` sul payload di
// scansione, eta' di secondi). Ora il prezzo e' quello del ladder del mercato
// al ms (`usePrezzoAlMs` / `sorgenteLadderAlMs`, lo stesso delle schede delle
// proposte); dove il canale non porta quel mercato (il runner non lo segue) si
// ripiega sul prezzo dello scanner e lo si DICHIARA con l'eta'.
//
// Qui, puri e testati:
//   * `chiusuraAlPrezzo`: prezzo, abbinabile e P&L BLOCCABILE ricalcolati al
//     prezzo di adesso con la STESSA matematica di sempre (`greenPrice` /
//     `partialLockedPnl` di `CashOutButton`, specchio di `trading/greenup.py`);
//   * `ripiegoScanner`: il prezzo dello scanner come `PrezzoScheda` dichiarato;
//   * `testoFonte`: «ladder al ms, 1 s fa» / «prezzo dello scanner, 12 s fa»;
//   * `valutaComboAlMs`: per una combo, la differenza per gamba e un LIMITE
//     INFERIORE certo del profitto bloccato per euro al prezzo di adesso.
// Nessuna funzione qui spegne un bottone e nessuna cambia cio' che parte.
// ============================================================================
import { greenPrice, partialLockedPnl } from '@/components/trading/CashOutButton';
import { fmtNum } from '@/lib/format';
import { ticksBetween } from '@/lib/riskMath';
import type { PrezzoScheda } from '@/lib/schedaAlMs';

/** Cio' che serve per ricalcolare il «se chiudo ora» al prezzo di adesso. */
export interface DatiChiusuraAlMs {
    /** esposizione della posizione sui due esiti (stessa di `tradeExposureNow`) */
    win: number;
    lose: number;
    marketId: string | null;
    selectionId: number | null;
    sport: 'calcio' | 'tennis';
    /** istante del prezzo dello scanner (ms), per il ripiego dichiarato */
    istanteScannerMs: number | null;
    /** i due lati dello scanner (il ripiego), con l'abbinabile */
    scanner: { back: number | null; backSize: number | null; lay: number | null; laySize: number | null };
}

export interface ChiusuraAlPrezzo {
    lato: 'back' | 'lay';
    prezzo: number | null;
    abbinabile: number | null;
    bloccabile: number | null;
}

/** Il prezzo dello scanner come `PrezzoScheda` (fonte 'scanner'), o null. */
export function ripiegoScanner(d: DatiChiusuraAlMs | null | undefined): PrezzoScheda | null {
    if (!d) return null;
    const s = d.scanner;
    if (s.back == null && s.lay == null) return null;
    return {
        back: s.back, backSize: s.backSize, lay: s.lay, laySize: s.laySize,
        istanteMs: d.istanteScannerMs, fonte: 'scanner', statoMercato: null,
    };
}

/**
 * Il «se chiudo ora» al prezzo mostrato: il lato di copertura dall'esposizione,
 * il miglior prezzo di quel lato, il P&L garantito chiudendo per intero.
 * Stesse funzioni di `useControlRoom.chiusuraViva`: nessuna seconda formula.
 */
export function chiusuraAlPrezzo(
    win: number, lose: number, lato: 'back' | 'lay', p: PrezzoScheda,
): ChiusuraAlPrezzo {
    const prezzo = greenPrice(win, lose, lato === 'back' ? p.back : null, lato === 'lay' ? p.lay : null);
    const abbinabile = lato === 'back' ? p.backSize : p.laySize;
    return {
        lato, prezzo,
        abbinabile: prezzo == null ? null : abbinabile,
        bloccabile: prezzo == null ? null : partialLockedPnl(prezzo, win, lose, 1),
    };
}

/** Eta' (s) del prezzo mostrato; null = ignota. */
export function etaPrezzoS(p: PrezzoScheda, nowMs: number): number | null {
    return p.istanteMs == null ? null : Math.max(0, (nowMs - p.istanteMs) / 1000);
}

function testoEta(s: number | null): string {
    return s == null ? 'eta\' ignota' : `${fmtNum(s, s < 10 ? 1 : 0)} s fa`;
}

/**
 * Da dove viene il prezzo del «Chiudi», con l'eta', a parole:
 *  - canale: «ladder al ms, 0,4 s fa»
 *  - db:     «ladder al ms (DB, il canale tace), 3 s fa»
 *  - scanner (ripiego): «prezzo dello scanner, 12 s fa (il canale non porta questo mercato)»
 *  - nessuno: «prezzo non disponibile»
 */
export function testoFonte(p: PrezzoScheda, nowMs: number): string {
    const eta = testoEta(etaPrezzoS(p, nowMs));
    if (p.fonte === 'canale') return `ladder al ms, ${eta}`;
    if (p.fonte === 'db') return `ladder al ms (DB, il canale tace), ${eta}`;
    if (p.fonte === 'scanner') return `prezzo dello scanner, ${eta} (il canale non porta questo mercato)`;
    return 'prezzo non disponibile';
}

/** Una gamba di una combo al prezzo di adesso. */
export interface GambaComboAlMs {
    lato: 'back' | 'lay' | null;
    /** prezzo della proposta (quello con cui il motore ha calcolato il lock) */
    prezzoProposta: number | null;
    size: number | null;
    /** prezzo di adesso sul lato della gamba (null = assente) */
    prezzoOra: number | null;
}

export interface ValutazioneComboAlMs {
    /** tick fra proposta e adesso, per gamba (null se un prezzo manca) */
    tick: (number | null)[];
    /** per gamba: il prezzo di adesso e' contro la gamba (peggiora il lock)? */
    contro: (boolean | null)[];
    /** limite INFERIORE certo del profitto bloccato per euro al prezzo di adesso */
    evMinimo: number | null;
    semaforo: 'SI' | 'QUASI' | 'NO';
    motivi: string[];
}

const valida = (v: unknown): number | null =>
    (typeof v === 'number' && Number.isFinite(v) && v > 1 ? v : null);

/**
 * LA COMBO AL PREZZO DI ADESSO. Il motore (`safe_strategy/combos._evaluate`)
 * pubblica `ev` = profitto NETTO bloccato nel caso PEGGIORE, per euro di stake
 * totale, ai prezzi della proposta. Gli esiti della partita non sono sulla
 * proposta, quindi qui non si ricalcola il lock esatto: se ne da' un LIMITE
 * INFERIORE CERTO. Una gamba BACK il cui prezzo scende da p0 a p1 perde al
 * massimo size*(p0-p1) nell'esito in cui vince, una LAY che sale da p0 a p1
 * perde al massimo size*(p1-p0); la commissione (solo sui profitti) non puo'
 * amplificare una perdita. Quindi, con S = somma delle size:
 *     evMinimo = ev - somma_gambe_contro(size * |p1 - p0|) / S
 * Le gambe mosse A FAVORE non si contano (limite prudente).
 * Semaforo: SI = nessuna gamba contro (lock >= quello proposto); QUASI =
 * qualche gamba contro ma il limite resta > 0; NO = limite <= 0, un prezzo
 * di adesso manca, o `ev` della proposta non e' un numero.
 */
export function valutaComboAlMs(ev: unknown, gambe: readonly GambaComboAlMs[]): ValutazioneComboAlMs {
    const tick: (number | null)[] = [];
    const contro: (boolean | null)[] = [];
    const motivi: string[] = [];
    let perdita = 0;
    let totale = 0;
    let manca = false;
    gambe.forEach((g, i) => {
        const p0 = valida(g.prezzoProposta);
        const p1 = valida(g.prezzoOra);
        const s = typeof g.size === 'number' && Number.isFinite(g.size) && g.size > 0 ? g.size : null;
        if (s !== null) totale += s;
        if (p0 === null || p1 === null || g.lato === null || s === null) {
            tick.push(null); contro.push(null); manca = true;
            motivi.push(`gamba ${i + 1}: prezzo di adesso non disponibile`);
            return;
        }
        tick.push(ticksBetween(p0, p1));
        const c = g.lato === 'back' ? p1 < p0 - 1e-9 : p1 > p0 + 1e-9;
        contro.push(c);
        if (c) perdita += s * Math.abs(p1 - p0);
    });
    const ev0 = typeof ev === 'number' && Number.isFinite(ev) ? ev : Number(ev);
    const evOk = ev !== null && ev !== undefined && ev !== '' && Number.isFinite(ev0);
    if (!evOk) motivi.push('profitto bloccato della proposta non dichiarato dal servizio');
    const evMinimo = evOk && !manca && totale > 0 ? ev0 - perdita / totale : null;
    let semaforo: 'SI' | 'QUASI' | 'NO';
    if (evMinimo === null) semaforo = 'NO';
    else if (evMinimo <= 0) {
        semaforo = 'NO';
        motivi.push('al prezzo di adesso il profitto bloccato non e\' piu\' garantito positivo');
    } else if (contro.some((c) => c === true)) {
        semaforo = 'QUASI';
        motivi.push('almeno una gamba si e\' mossa contro: il profitto bloccato e\' sceso');
    } else semaforo = 'SI';
    return { tick, contro, evMinimo, semaforo, motivi };
}
