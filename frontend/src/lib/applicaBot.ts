// ============================================================================
// applicaBot — le regole PURE del riquadro «Applica bot» (07/10).
// Ordini dell'utente (07/10): «portare TUTTI I BOT nella sezione "applica bot"»
// e «devo poter modificare i parametri di ognuno cosi' da provare altre
// varianti SENZA CAMBIARE LA STRATEGIA».
// Qui niente React: scelta dei bot per sport (calcio e tennis non si
// mischiano), famiglie di scenari con le due modalita', validazione dei campi
// dei parametri (stesse regole di varianti_bot.valida nel backend), le sole
// sostituzioni CAMBIATE rispetto alla serie, l'etichetta dell'istante.
// Riusate dal Match Replay (calcio) e dalla pagina Replay Tennis.
// ============================================================================
import type {
    CatalogoBot, ModalitaScenario, ScenarioBot, SportBot, ValoreParametro, VoceParametro,
} from '@/lib/replayBot';

/** I gruppi nell'ordine di presentazione (varianti_bot.GRUPPI). */
export const ORDINE_GRUPPI: readonly string[] = ['Ingresso', 'Uscita', 'Importi', 'Tetti', 'Filtri', 'Tempi'];

export const ETICHETTA_MODALITA: Record<ModalitaScenario, string> = {
    prova: 'Prova',
    soldi_veri_simulati: 'Soldi veri simulati',
};

/** I bot di UNO sport, nell'ordine del catalogo. PURA. */
export function botDelloSport(catalogo: ReadonlyArray<CatalogoBot>, sport: SportBot): CatalogoBot[] {
    return catalogo.filter(b => b.sport === sport);
}

const NOMI_MERCATO: Readonly<Record<string, string>> = { MATCH_ODDS: 'Match Odds', SET_BETTING: 'Set Betting' };

/** I tipi di mercato registrati: distinti, senza vuoti, in ordine alfabetico. PURA. */
export function tipiMercatoRegistrati(tipi: ReadonlyArray<string | null | undefined>): string[] {
    return Array.from(new Set(tipi.filter((t): t is string => !!t))).sort();
}

/**
 * 08/10 (Replay Tennis, caso 35797566): perche' il bot NON si puo' applicare a
 * questa partita, con lo stesso testo del banco (`applica_bot.risolvi_cartella_tennis`,
 * senza il nome della cartella che la pagina non conosce). null = si puo'
 * (o non si sa: mercati registrati non noti, bot senza mercati dichiarati). PURA.
 */
export function motivoMercatiMancanti(
    eventId: string, sport: SportBot, richiesti: ReadonlyArray<string> | undefined,
    registrati: ReadonlyArray<string | null | undefined> | null | undefined,
): string | null {
    if (registrati == null || !richiesti || richiesti.length === 0) return null;
    const tipi = tipiMercatoRegistrati(registrati);
    if (richiesti.some(m => tipi.includes(m))) return null;
    if (tipi.length === 0) {
        return `registrazione senza flusso di mercato (solo punteggi) per la partita ${eventId}: il bot non ha prezzi su cui girare`;
    }
    const voluti = richiesti.map(m => NOMI_MERCATO[m] ?? m).join(' / ');
    const chi = sport === 'tennis' ? 'i bot tennis lavorano' : 'il bot lavora';
    return `per la partita ${eventId} e' registrato solo il ${tipi.join(', ')}: ${chi} sul ${voluti}, che non e' stato registrato`;
}

export interface FamigliaScenari {
    famiglia: string;
    /** modalita' -> scenario del registro */
    modi: Partial<Record<ModalitaScenario, ScenarioBot>>;
}

/** Gli scenari di un bot raggruppati per famiglia (la stessa prova in «Prova»
 *  e in «Soldi veri simulati»), nell'ordine del catalogo. PURA. */
export function famiglieScenari(bot: CatalogoBot): FamigliaScenari[] {
    const out: FamigliaScenari[] = [];
    for (const s of bot.scenari) {
        let f = out.find(x => x.famiglia === s.famiglia);
        if (!f) {
            f = { famiglia: s.famiglia, modi: {} };
            out.push(f);
        }
        f.modi[s.modalita] = s;
    }
    return out;
}

/** La modalita' da usare in una famiglia: quella chiesta se c'e', altrimenti
 *  l'unica presente (prima la prova: paper = specchio del live). PURA. */
export function modalitaDisponibile(f: FamigliaScenari, voluta: ModalitaScenario): ModalitaScenario {
    if (f.modi[voluta]) return voluta;
    return f.modi.prova ? 'prova' : 'soldi_veri_simulati';
}

export interface EsitoCampo {
    ok: boolean;
    valore?: ValoreParametro;
    errore?: string;
}

function decimali(x: number): number {
    const s = String(x);
    const i = s.indexOf('.');
    return i < 0 ? 0 : s.length - i - 1;
}

/** Il valore scritto nel campo, controllato come lo controlla il backend
 *  (`varianti_bot.valida`): tipo, intero, minimo/massimo, scelte. Per gli interi
 *  anche il PASSO (multipli del passo dal minimo); per i decimali il passo
 *  guida le frecce del campo e non vieta un importo al centesimo. PURA. */
export function validaCampo(v: VoceParametro, grezzo: unknown): EsitoCampo {
    if (v.tipo === 'bool') {
        return typeof grezzo === 'boolean' ? { ok: true, valore: grezzo } : { ok: false, errore: 'atteso acceso/spento' };
    }
    if (v.tipo === 'scelta') {
        const s = String(grezzo);
        return (v.scelte ?? []).includes(s) ? { ok: true, valore: s } : { ok: false, errore: `scegli fra ${(v.scelte ?? []).join(', ')}` };
    }
    const testo = typeof grezzo === 'number' ? String(grezzo) : String(grezzo ?? '').trim().replace(',', '.');
    if (testo === '') return { ok: false, errore: 'campo vuoto' };
    const n = Number(testo);
    if (!Number.isFinite(n)) return { ok: false, errore: 'non e’ un numero' };
    if (v.tipo === 'int' && !Number.isInteger(n)) return { ok: false, errore: 'serve un numero intero' };
    if (v.min != null && n < v.min) return { ok: false, errore: `minimo ${v.min}` };
    if (v.max != null && n > v.max) return { ok: false, errore: `massimo ${v.max}` };
    if (v.tipo === 'int' && v.passo != null && v.passo > 1 && v.min != null && (n - v.min) % v.passo !== 0) {
        return { ok: false, errore: `a passi di ${v.passo}` };
    }
    if (v.tipo === 'float' && decimali(n) > 2) return { ok: false, errore: 'al massimo due decimali' };
    return { ok: true, valore: n };
}

/** Le sole sostituzioni CAMBIATE rispetto alla serie (quelle che si mandano
 *  al banco), e i campi non validi (che bloccano la prova). PURA. */
export function sostituzioni(voci: ReadonlyArray<VoceParametro>, valori: Readonly<Record<string, unknown>>):
    { cambiati: Record<string, ValoreParametro>; errori: Record<string, string> } {
    const cambiati: Record<string, ValoreParametro> = {};
    const errori: Record<string, string> = {};
    for (const v of voci) {
        if (!(v.chiave in valori)) continue;
        const e = validaCampo(v, valori[v.chiave]);
        if (!e.ok || e.valore === undefined) {
            errori[v.chiave] = e.errore ?? 'non valido';
            continue;
        }
        if (e.valore !== v.default) cambiati[v.chiave] = e.valore;
    }
    return { cambiati, errori };
}

/** Le voci divise per gruppo, nell'ordine dei gruppi (gruppi ignoti in coda). PURA. */
export function gruppiParametri(voci: ReadonlyArray<VoceParametro>): Array<{ gruppo: string; voci: VoceParametro[] }> {
    const ordine = [...ORDINE_GRUPPI, ...voci.map(v => v.gruppo).filter(g => !ORDINE_GRUPPI.includes(g))];
    const out: Array<{ gruppo: string; voci: VoceParametro[] }> = [];
    for (const g of ordine) {
        if (out.some(x => x.gruppo === g)) continue;
        const vv = voci.filter(v => v.gruppo === g);
        if (vv.length > 0) out.push({ gruppo: g, voci: vv });
    }
    return out;
}

/** Il valore per il trader (bool acceso/spento, numeri all'italiana con l'unita'). PURA. */
export function testoValore(v: VoceParametro, x: ValoreParametro | undefined): string {
    if (x === undefined) return '—';
    if (typeof x === 'boolean') return x ? 'acceso' : 'spento';
    if (typeof x === 'number') {
        const t = x.toLocaleString('it-IT', { maximumFractionDigits: 3 });
        return v.unita ? `${t} ${v.unita}` : t;
    }
    return x;
}

/** L'ora dell'istante (ora di Roma, come il resto dell'app) con i secondi. PURA. */
export function testoIstante(ms: number): string {
    return new Date(ms).toLocaleTimeString('it-IT', {
        timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}

/** Il minuto di gioco a un istante, dalla cronologia dei punteggi ORDINATA per
 *  istante (ultimo minuto noto con ts <= ms); prima del primo: «pre-partita». PURA. */
export function minutoDiGioco(cronologia: ReadonlyArray<{ ts: string; minute: number | null }>, ms: number): string {
    let minuto: number | null = null;
    for (const e of cronologia) {
        if (new Date(e.ts).getTime() > ms) break;
        if (e.minute != null) minuto = e.minute;
    }
    return minuto != null ? `${minuto}'` : 'pre-partita';
}
