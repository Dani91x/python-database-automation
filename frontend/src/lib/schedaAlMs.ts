// ============================================================================
// schedaAlMs.ts - LA SCHEDA DELLE PROPOSTE AL MS (24/09/2026), parte PURA.
//
// Ordine dell'utente (visto a video il 24/09): «per tutta la parte proposte
// modello, PER QUALSIASI PROPOSTA DI QUALSIASI BOT, se il prezzo cambia ricevo
// "prezzo vivo assente: non si piazza al buio" E NON POSSO PIAZZARE NULLA.
// Quello che voglio e' una scheda che ricalcola al ms tutto MA NON BLOCCA
// L'ENTRATA: me lo segnala e decido io.»
//
// Qui vivono, puri e testabili:
//   * `prezzoDaLadder` - il prezzo di una selezione dalla riga del ladder al ms
//     (`LiveLadderRow` di `lib/live.ts`, consegnata da `sorgenteLadderAlMs`);
//   * `scegliPrezzo` - ladder al ms se c'e', altrimenti ripiego DICHIARATO sul
//     feed dello scanner (il ladder_worker pubblica solo i mercati seguiti dal
//     runner: `Betfair/stream/runner.py` ladder_worker);
//   * `semaforo` - SI / QUASI / NO con gli STESSI criteri del modello
//     (`valutaAlPrezzo`, porta pura di `proposte_opportunita.valuta_al_prezzo`);
//   * `prezzoVistoAlClic` - cio' che parte al clic: il prezzo a video col suo
//     istante e la sua fonte, oppure l'ultimo noto con l'eta' e il flag
//     `prezzo_vivo_assente` (mai un clic rifiutato dalla pagina).
// NESSUNA funzione qui spegne un bottone: producono AVVISI.
// ============================================================================
import type { LiveLadderRow } from '@/lib/live';
import { fmtNum, fmtOdds } from '@/lib/format';
import { tickDown, tickUp } from '@/lib/matching';
import { ticksBetween } from '@/lib/riskMath';
import { valutaAlPrezzo, testoMotivo, type CriteriProposta, type ValutazioneAlPrezzo } from '@/lib/valutaProposta';

/** Chi ha portato il prezzo mostrato. */
export type FontePrezzo = 'canale' | 'db' | 'scanner';

export interface PrezzoScheda {
    back: number | null;
    backSize: number | null;
    lay: number | null;
    laySize: number | null;
    /** istante del prezzo (ms epoch del produttore); null = ignoto */
    istanteMs: number | null;
    fonte: FontePrezzo | null;
    /** OPEN / SUSPENDED / CLOSED; null = ignoto */
    statoMercato: string | null;
}

export const PREZZO_VUOTO: PrezzoScheda = {
    back: null, backSize: null, lay: null, laySize: null,
    istanteMs: null, fonte: null, statoMercato: null,
};

const prezzoValido = (v: unknown): number | null =>
    (typeof v === 'number' && Number.isFinite(v) && v > 1 ? v : null);
const sizeValida = (v: unknown): number | null =>
    (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null);

/** Il prezzo della selezione dalla riga del ladder al ms. null se la riga non
 *  porta quella selezione (mai un prezzo inventato). */
export function prezzoDaLadder(
    row: LiveLadderRow | null | undefined, selectionId: number | null | undefined,
    fonte: 'canale' | 'db' | null,
): PrezzoScheda | null {
    if (!row || selectionId == null || !row.ladder) return null;
    const sel = (row.ladder.selections ?? []).find((s) => Number(s.selection_id) === Number(selectionId));
    if (!sel) return null;
    const b = sel.back?.[0];
    const l = sel.lay?.[0];
    return {
        back: prezzoValido(b?.[0]), backSize: sizeValida(b?.[1]),
        lay: prezzoValido(l?.[0]), laySize: sizeValida(l?.[1]),
        istanteMs: typeof row.ladder.updated_ms === 'number' ? row.ladder.updated_ms : null,
        fonte: fonte ?? 'canale',
        statoMercato: row.status ? String(row.status).toUpperCase() : null,
    };
}

/** Ladder al ms se ha il lato che serve, altrimenti il ripiego dello scanner. */
export function scegliPrezzo(ladder: PrezzoScheda | null, scanner: PrezzoScheda | null,
    lato: 'back' | 'lay' | null): PrezzoScheda {
    const haLato = (p: PrezzoScheda | null) => !!p && (lato === 'lay' ? p.lay != null : p.back != null);
    if (haLato(ladder)) return ladder as PrezzoScheda;
    if (haLato(scanner)) return { ...(scanner as PrezzoScheda), fonte: 'scanner' };
    // nessuno dei due ha il prezzo: si tiene lo stato mercato che c'e'
    return { ...PREZZO_VUOTO, statoMercato: ladder?.statoMercato ?? scanner?.statoMercato ?? null };
}

export const prezzoDelLato = (p: PrezzoScheda, lato: 'back' | 'lay' | null) =>
    (lato === 'lay' ? p.lay : p.back);
export const sizeDelLato = (p: PrezzoScheda, lato: 'back' | 'lay' | null) =>
    (lato === 'lay' ? p.laySize : p.backSize);

export type Semaforo = 'SI' | 'QUASI' | 'NO';

/** Il blocco `valutazione` scritto dal servizio (Safe: `proposte_opportunita.
 *  valutazione_viva/non_valida`). Solo i campi che la scheda legge. */
export interface ValutazioneServizio {
    valida?: boolean | null;
    causa?: string | null;
    motivi?: { codice: string; valore: number | null; soglia: number | null; testo?: string }[] | null;
    valutata_at?: string | null;
    dal?: string | null;
}

export interface GiudizioScheda {
    semaforo: Semaforo;
    /** i numeri AL PREZZO DI ADESSO (null se il prezzo non c'e') */
    alPrezzo: ValutazioneAlPrezzo | null;
    /** i perche' del NO/QUASI, in italiano */
    motivi: string[];
}

/**
 * SI = al prezzo di adesso i criteri del modello reggono;
 * QUASI = reggono, ma UN tick contro (piu' basso su un back, piu' alto su un
 *         lay) li farebbe cadere;
 * NO = non reggono al prezzo di adesso, oppure il servizio dice che il MODELLO
 *      non la propone piu' (causa 'modello': P, confidenza, contesto), oppure
 *      il prezzo non c'e'.
 * Nessun criterio nuovo: `valutaAlPrezzo` coi criteri scritti dal servizio.
 */
export function giudica(args: {
    lato: 'back' | 'lay' | null; prezzo: number | null; abbinabile: number | null;
    pModel: unknown; criteri: CriteriProposta | null | undefined;
    valutazione?: ValutazioneServizio | null;
}): GiudizioScheda {
    const { lato, prezzo, abbinabile, pModel, criteri, valutazione } = args;
    const motiviModello = valutazione && valutazione.valida === false && valutazione.causa === 'modello'
        ? (valutazione.motivi ?? []).map((m) => testoMotivo(m))
        : [];
    if (prezzo == null || !lato) {
        return { semaforo: 'NO', alPrezzo: null,
            motivi: [...motiviModello, 'prezzo di adesso non disponibile'] };
    }
    const alPrezzo = valutaAlPrezzo({ side: lato, prezzo, abbinabile, p_model: pModel, criteri });
    const motivi = [...motiviModello, ...alPrezzo.motivi.map((m) => testoMotivo(m))];
    if (motiviModello.length || !alPrezzo.valida) return { semaforo: 'NO', alPrezzo, motivi };
    const contro = lato === 'back' ? tickDown(prezzo) : tickUp(prezzo);
    const unTick = valutaAlPrezzo({ side: lato, prezzo: contro, abbinabile, p_model: pModel, criteri });
    if (!unTick.valida) {
        return { semaforo: 'QUASI', alPrezzo,
            motivi: [`un tick contro (${fmtOdds(contro)}) la farebbe cadere: `
                + unTick.motivi.map((m) => testoMotivo(m)).join('; ')] };
    }
    return { semaforo: 'SI', alPrezzo, motivi: [] };
}

/** Differenza fra il prezzo di adesso e quello alla creazione: tick e %. */
export function scarto(prezzoOra: number | null, prezzoCreazione: unknown): { tick: number | null; pct: number | null } {
    const p0 = prezzoValido(prezzoCreazione);
    if (prezzoOra == null || p0 == null) return { tick: null, pct: null };
    return { tick: ticksBetween(p0, prezzoOra), pct: ((prezzoOra - p0) / p0) * 100 };
}

/** Il contesto del prezzo che parte al clic (va al servizio insieme al prezzo). */
export interface ContestoPrezzoVisto {
    /** eta' del prezzo al clic, ms (null = ignota) */
    eta_ms: number | null;
    fonte: FontePrezzo | 'proposta' | null;
    /** true = a video NON c'era un prezzo vivo: si manda l'ultimo noto */
    prezzo_vivo_assente: boolean;
    /** istante del clic, ms epoch del browser */
    clic_ms: number;
}

/**
 * Cio' che parte al clic: il prezzo A VIDEO se c'e'; altrimenti l'ultimo
 * prezzo noto (ultimo visto dalla scheda, o quello della proposta) con
 * `prezzo_vivo_assente=true`. Mai `null` se esiste un qualunque prezzo: la
 * pagina non rifiuta il clic, decide il servizio con la sua tolleranza.
 */
export function prezzoVistoAlClic(args: {
    vivo: number | null; vivoIstanteMs: number | null; vivoFonte: FontePrezzo | null;
    ultimoNoto: number | null; ultimoNotoIstanteMs: number | null; ultimoNotoFonte: FontePrezzo | null;
    prezzoProposta: unknown; nowMs: number;
}): { prezzo: number | null; contesto: ContestoPrezzoVisto } {
    const eta = (ms: number | null) => (ms == null ? null : Math.max(0, args.nowMs - ms));
    if (args.vivo != null) {
        return { prezzo: args.vivo, contesto: { eta_ms: eta(args.vivoIstanteMs),
            fonte: args.vivoFonte, prezzo_vivo_assente: false, clic_ms: args.nowMs } };
    }
    if (args.ultimoNoto != null) {
        return { prezzo: args.ultimoNoto, contesto: { eta_ms: eta(args.ultimoNotoIstanteMs),
            fonte: args.ultimoNotoFonte, prezzo_vivo_assente: true, clic_ms: args.nowMs } };
    }
    const p = prezzoValido(args.prezzoProposta);
    return { prezzo: p, contesto: { eta_ms: null, fonte: p == null ? null : 'proposta',
        prezzo_vivo_assente: true, clic_ms: args.nowMs } };
}

/** Testo dell'eta' e della fonte, come nel resto della Control Room. */
export function etaEFonte(istanteMs: number | null, fonte: FontePrezzo | 'proposta' | null, nowMs: number): string {
    const f = fonte === 'canale' ? 'canale al ms' : fonte === 'db' ? 'DB (ripiego)'
        : fonte === 'scanner' ? 'feed scanner (mercato non seguito dal runner)'
        : fonte === 'proposta' ? 'prezzo della proposta' : 'fonte ignota';
    if (istanteMs == null) return `età ignota · ${f}`;
    const s = Math.max(0, (nowMs - istanteMs) / 1000);
    return `${fmtNum(s, s < 10 ? 1 : 0)} s fa · ${f}`;
}
