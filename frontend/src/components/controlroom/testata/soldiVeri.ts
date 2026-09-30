// ============================================================================
// soldiVeri.ts - P3 (30/09): la fascia "SOLDI VERI ADESSO" della testata.
//
// Ordine dell'utente (30/09, sezione 1): "esposizione incoerente [...] deve
// essere un monitor veritiero". La testata scriveva "Esposizione 39,15": la
// somma LORDA della colonna `liability` di ogni riga live non regolata (conta
// le posizioni pareggiate, quelle chiuse dal sito, la richiesta invece
// dell'abbinato). Il conto, nello stesso istante, rischiava 9,95.
//
// Da qui:
//   * ESPOSIZIONE = quella del CONTO (getAccountFunds), la stessa catena di
//     `SaldoBetfairCard`: riga `betfair_live_account` + topic `account` dei
//     canali locali, vince il piu' recente (`saldoDaMostrare`), stessa regola
//     di freschezza (`statoSaldoBetfair`). Nessuna lettura nuova.
//   * RISCHIO SECONDO I BOT = la liability NETTA che i servizi pubblicano
//     (`aggregates.open_liability`), SOLO quando il servizio la dichiara per la
//     modalita' LIVE. Un aggregato paper o misto non e' rischio vero: se non si
//     puo' separare lo si DICE, mai lo si somma.
//   * SCARTO conto <-> bot: se non tornano oltre il centesimo, lo si scrive,
//     senza inventare la causa.
// Funzioni PURE: la presentazione sta in `FasciaSoldiVeri.tsx`.
// ============================================================================
import type { Bot } from '@/lib/controlRoom';
import {
    saldoDaMostrare, statoSaldoBetfair, type SaldoDalCanale,
} from '@/lib/saldoBetfair';

// --------------------------------------------------------------------- conto

export interface ContoAdesso {
    /** true = almeno una lettura del conto (database o canale) */
    letto: boolean;
    /** come la scrive Betfair (negativa = perdita massima del conto); null = non letta */
    esposizione: number | null;
    disponibile: number | null;
    /** istante del dato mostrato (ISO) */
    istante: string | null;
    /** 'canale' = lettura REST pubblicata dal processo (checked_at); 'database' = riga
     *  `betfair_live_account` (scritta SOLO al cambio: l'eta' e' dell'ultimo CAMBIO) */
    fonte: 'canale' | 'database' | null;
    etaS: number | null;
    /** true = non verificato di recente (stessa regola di `SaldoBetfairCard`) */
    attenzione: boolean;
    /** la frase della regola di freschezza, per il tooltip */
    messaggio: string;
}

function etaDa(iso: string | null, nowMs: number): number | null {
    if (iso == null) return null;
    const ms = Date.parse(iso);
    if (!Number.isFinite(ms)) return null;
    return Math.max(0, Math.round((nowMs - ms) / 1000));
}

/**
 * Il conto, adesso. `riga` = `betfair_live_account` gia' in memoria del hook;
 * `canale` = l'ultimo saldo arrivato dal topic `account` (il piu' recente fra
 * i canali); `etaRunnerS` = eta' del battito del runner calcio (la stessa
 * notizia che la card legge da `betfair_live_heartbeat`).
 */
export function contoAdesso(input: {
    riga: { available: number | null; exposure: number | null; updated_at: string } | null;
    canale: SaldoDalCanale | null;
    etaRunnerS: number | null;
    nowMs: number;
}): ContoAdesso {
    const { riga, canale, etaRunnerS, nowMs } = input;
    const mostrato = saldoDaMostrare(riga, canale);
    const etaS = etaDa(mostrato.istante, nowMs);
    const letto = mostrato.istante != null;
    const stato = statoSaldoBetfair({
        etaSaldoS: etaS,
        etaHeartbeatS: etaRunnerS,
        etaCanaleS: canale ? etaDa(canale.checkedAt, nowMs) : null,
    });
    return {
        letto,
        esposizione: letto ? mostrato.exposure : null,
        disponibile: letto ? mostrato.available : null,
        istante: mostrato.istante,
        fonte: letto ? mostrato.fonte : null,
        etaS,
        attenzione: stato.attenzione,
        messaggio: stato.messaggio,
    };
}

// ------------------------------------------------------ rischio dei bot LIVE

/** La forma minima di un aggregato di servizio (Omega/Safe/Mike, SQL). */
interface AggregatoLike {
    open_liability?: unknown;
    /** modalita' filtrata dalla RPC: 'live' | 'paper' | null (= tutte) */
    mode?: unknown;
    /** solo Mike: battito del servizio vecchio di oltre 60 s */
    liability_stale?: unknown;
}

export interface StatoServizioLike {
    aggregates?: unknown;
    /** Omega (FIX-A 26/09): aggregati per modalita' */
    aggregates_by_mode?: unknown;
}

function comeAggregato(v: unknown): AggregatoLike | null {
    return v != null && typeof v === 'object' && !Array.isArray(v) ? v as AggregatoLike : null;
}

function numeroFinito(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * La liability NETTA che il servizio DICHIARA per la modalita' LIVE, o null
 * se non la dichiara separata:
 *   1. `aggregates_by_mode.live.open_liability` (Omega);
 *   2. `aggregates.open_liability` se `aggregates.mode === 'live'` (Mike, che
 *      filtra sulla modalita' del bot);
 *   3. `aggregates.open_liability` di un aggregato di TUTTE le modalita'
 *      (`mode` nullo: Safe senza `p_mode`) SOLO se il bot non ha nessuna
 *      posizione paper aperta: allora e' tutto live. Altrimenti null.
 * Un aggregato `mode: 'paper'` non e' mai rischio vero.
 */
export function liabilityLiveDichiarata(
    stato: StatoServizioLike | null | undefined,
    apertePaper: number,
): { valore: number | null; stantio: boolean } {
    const agg = comeAggregato(stato?.aggregates);
    const perModo = comeAggregato(stato?.aggregates_by_mode);
    const live = comeAggregato(perModo ? (perModo as Record<string, unknown>).live : null);
    const stantio = agg?.liability_stale === true;
    const daLive = numeroFinito(live?.open_liability);
    if (daLive != null) return { valore: daLive, stantio };
    if (agg == null) return { valore: null, stantio };
    const v = numeroFinito(agg.open_liability);
    if (v == null) return { valore: null, stantio };
    if (agg.mode === 'live') return { valore: v, stantio };
    if ((agg.mode == null) && apertePaper === 0) return { valore: v, stantio };
    return { valore: null, stantio };
}

export interface VoceRischio {
    bot: Bot;
    /** perdita massima LIVE secondo il bot (positiva); null = non separabile / non pubblicata */
    valore: number | null;
    /** perche' manca, o perche' va letta con cautela */
    nota: string | null;
    /** posizioni LIVE aperte del bot secondo le sue righe */
    aperteLive: number;
    /** R_T (30/09): il servizio dichiara il numero stantio (battito vecchio) */
    stantio?: boolean;
}

export interface RischioBotLive {
    /** somma delle voci note (arrotondata al centesimo); null = nessuna voce nota */
    totale: number | null;
    /** true = ogni bot con posizioni LIVE ha una voce nota */
    completo: boolean;
    voci: VoceRischio[];
}

/** i tre servizi che pubblicano una liability netta */
const SERVIZI_CON_LIABILITY = ['omega', 'safe', 'mike'] as const;

const r2 = (x: number) => Math.round(x * 100) / 100;

export function rischioBotLive(input: {
    /** false = righe dei bot non ancora lette: nessuna cifra */
    letti: boolean;
    stati: Partial<Record<'omega' | 'safe' | 'mike', StatoServizioLike | null>>;
    /** posizioni APERTE (aperture non regolate) come le vede il hook */
    aperte: ReadonlyArray<{ bot: Bot; modalita: 'paper' | 'live' | null }>;
}): RischioBotLive {
    if (!input.letti) return { totale: null, completo: false, voci: [] };
    const conta = (bot: Bot, modo: 'paper' | 'live') =>
        input.aperte.filter((p) => p.bot === bot && p.modalita === modo).length;
    const voci: VoceRischio[] = [];
    for (const bot of SERVIZI_CON_LIABILITY) {
        const aperteLive = conta(bot, 'live');
        const d = liabilityLiveDichiarata(input.stati[bot], conta(bot, 'paper'));
        if (d.valore != null) {
            voci.push({
                bot, valore: r2(d.valore), aperteLive, stantio: d.stantio,
                nota: d.stantio ? 'numero del servizio stantio (battito oltre 60 s)' : null,
            });
        } else if (aperteLive === 0) {
            voci.push({ bot, valore: 0, aperteLive, nota: null });
        } else {
            voci.push({
                bot, valore: null, aperteLive,
                nota: 'il servizio non dichiara il rischio LIVE separato dal paper',
            });
        }
    }
    // gli altri bot (4 tennis, scalper calcio) non pubblicano una liability
    // netta: con posizioni LIVE aperte il loro rischio NON e' nella somma.
    const altri = new Set<Bot>();
    for (const p of input.aperte) {
        if (p.modalita === 'live' && !(SERVIZI_CON_LIABILITY as readonly string[]).includes(p.bot)) altri.add(p.bot);
    }
    for (const bot of altri) {
        voci.push({
            bot, valore: null, aperteLive: conta(bot, 'live'),
            nota: 'il bot non pubblica un rischio netto',
        });
    }
    const note = voci.filter((v) => v.valore != null);
    return {
        totale: note.length ? r2(note.reduce((s, v) => s + (v.valore as number), 0)) : null,
        completo: voci.every((v) => v.valore != null),
        voci,
    };
}

// ------------------------------------------------------------- scarto

export interface ScartoContoBot {
    /** |esposizione del conto| - rischio dei bot, in valore assoluto (> 0,01) */
    differenza: number;
    /** true = il conto rischia PIU' di quanto dicono i bot */
    contoPiuAlto: boolean;
}

/**
 * Conto e bot tornano? null = tornano (entro il centesimo) OPPURE non si puo'
 * dire (conto non letto, rischio dei bot incompleto). Chi chiama distingue i
 * due casi con `conto.esposizione` e `rischio.completo`.
 */
export function scartoContoBot(esposizione: number | null, rischio: RischioBotLive): ScartoContoBot | null {
    if (esposizione == null || !rischio.completo || rischio.totale == null) return null;
    const d = r2(Math.abs(esposizione) - rischio.totale);
    if (Math.abs(d) <= 0.01) return null;
    return { differenza: Math.abs(d), contoPiuAlto: d > 0 };
}

// ------------------------------------------------------------- partite

export interface PartiteConPosizione {
    /** partite distinte con almeno una posizione LIVE aperta */
    live: number;
    /** partite distinte con almeno una posizione in PROVA aperta */
    prova: number;
    /** partite con posizioni la cui modalita' non e' dichiarata */
    ignota: number;
}

export function partiteConPosizione(
    aperte: ReadonlyArray<{ eventId: string; modalita: 'paper' | 'live' | null }>,
): PartiteConPosizione {
    const live = new Set<string>();
    const prova = new Set<string>();
    const ignota = new Set<string>();
    for (const p of aperte) {
        if (p.modalita === 'live') live.add(p.eventId);
        else if (p.modalita === 'paper') prova.add(p.eventId);
        else ignota.add(p.eventId);
    }
    return { live: live.size, prova: prova.size, ignota: ignota.size };
}

// ------------------------------------------------------------- insieme

/** Il campo del modello di vista che la testata legge (additivo). */
export interface SoldiVeriTestata {
    conto: ContoAdesso;
    rischioBot: RischioBotLive;
    /** eta' della lettura degli aggregati dei servizi (giro del database della
     *  pagina, `lettoAlle`); null = mai letti */
    etaBotS: number | null;
    scarto: ScartoContoBot | null;
    /** null = righe dei bot non ancora lette */
    partite: PartiteConPosizione | null;
    /** righe del programma dello scanner (calcio + tennis): NON partite operate */
    programmaScanner: number;
}
