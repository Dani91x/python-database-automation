// ============================================================================
// replayBot — "APPLICA BOT" del Match Replay (06/10; TUTTI i bot dal 07/10).
// Il bot gira col CODICE DI PRODUZIONE sulla registrazione della partita (banco
// comune, Betfair/stream/backtest/applica_bot.py) nel worker del Backtest
// Automatico; la richiesta passa dalla coda esistente (request_backtest con
// params.tipo = 'applica_bot'), l'esito da get_replay_bot_esito (migrazione
// replay_applica_bot_2026-10-06.sql).
// L'esito e' la CRONOLOGIA degli ordini del bot: righe betfair_live_orders (le
// stesse che il ladder legge dal vivo) con l'istante `_ms` del banco (= publish
// time Betfair, lo stesso orologio dei frame del replay). Qui si ricostruisce lo
// stato degli ordini a un istante della timeline e lo si mostra nel ladder.
// 07/10: il catalogo dei bot (sport, scenari, parametri modificabili con i
// valori di serie) NON e' piu' un elenco a mano: e' il file GENERATO
// `replayBotCatalogo.ts` (applica_bot.py --catalogo-ts), qui solo i tipi.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import type { LadderOrderApi } from '@/components/live/LadderView';
import type { LiveOrderRow } from '@/lib/liveOrders';

// --------------------------------------------------------------------------
// il catalogo (stesse chiavi di varianti_bot.voce / applica_bot.catalogo_del_bot)
// --------------------------------------------------------------------------
export type SportBot = 'calcio' | 'tennis';
export type TipoParametro = 'int' | 'float' | 'bool' | 'scelta';
export type ValoreParametro = number | boolean | string;
export type ModalitaScenario = 'prova' | 'soldi_veri_simulati';

/** Una voce del catalogo dei parametri (contratto del banco, `varianti_bot.voce`). */
export interface VoceParametro {
    chiave: string;
    etichetta: string;
    tipo: TipoParametro;
    /** il valore di SERIE (quello di produzione con sopra lo scenario) */
    default: ValoreParametro;
    min: number | null;
    max: number | null;
    passo: number | null;
    unita: string;
    gruppo: string;
    scelte: string[] | null;
}

export interface ScenarioBot {
    scenario: string;
    /** le due modalita' dello STESSO scenario condividono la famiglia */
    famiglia: string;
    modalita: ModalitaScenario;
    etichetta: string;
    nota: string;
    descrizione: string;
    parametri: VoceParametro[];
    errore_parametri?: string;
}

export interface CatalogoBot {
    bot: string;
    sport: SportBot;
    etichetta: string;
    descrizione: string;
    scenari: ScenarioBot[];
    /** la funzione di replay accetta gli istanti di clic «Attiva adesso» */
    clic_ms: boolean;
    /** non null = il bot non si puo' applicare, con il motivo */
    disattivato: string | null;
    errore_parametri?: string;
    /** 08/10: i tipi di mercato Betfair che servono al bot (registro del banco) */
    mercati?: string[];
}

// --------------------------------------------------------------------------
// la richiesta e l'esito
// --------------------------------------------------------------------------
// una riga della cronologia: la riga dello specchio + l'istante del banco.
// 07/10 sera (REPLAY PROFESSIONALE, `varianti_bot.campi_ordine`): i campi `_`
// del banco, assenti negli esiti di prima (opzionali):
//   _ordine        id dell'ordine flumine (IDENTITA': un replace di flumine crea
//                  un ordine nuovo con lo STESSO client_order_ref del vecchio)
//   _trade_id      il trade flumine (operazione del bot)
//   _strategia     la strategia flumine che lo ha piazzato
//   _sostituisce   l'_ordine sostituito da questo (replace di Betfair/flumine)
//   _profitto_flumine  sull'ultima riga: il profitto regolato da flumine
export type RigaBot = Omit<LiveOrderRow, 'id' | 'updated_at'> & {
    _ms: number;
    _ordine?: string | null;
    _trade_id?: string | null;
    _strategia?: string | null;
    _sostituisce?: string | null;
    _profitto_flumine?: number | null;
};

/** Il risultato di un mercato letto dal RAW (`applica_bot.esiti_dal_raw`). */
export interface EsitoMercato {
    market_type: string | null;
    /** selection_id (stringa) -> stato finale del runner (WINNER/LOSER/REMOVED/ACTIVE) */
    runners: Record<string, string>;
    /** i runner nell'ordine di Betfair */
    ordine_runner: number[];
    stato: string | null;
    in_gioco_ms: number | null;
    chiuso_ms: number | null;
    aliquota: number | null;
    vincitori: number[];
}

/** Un conto (lordo/commissione/netto) come lo scrive il banco. */
export interface ContoBanco {
    lordo: number;
    commissione: number;
    netto: number;
    mercati?: Record<string, number>;
    mercati_non_regolati?: string[];
}

export interface ContoDichiarato {
    /** media_conto (riepilogo per ciclo del bot) o nota «P&L del replay» */
    fonte: 'media_conto' | 'nota';
    /** cicli = profitto bloccato dei cicli chiusi; regolamento = risultato del mercato */
    metodo: 'cicli' | 'regolamento';
    lordo: number;
    commissione: number;
    netto: number;
    aliquota: number;
    cicli_esito_ignoto?: number;
    testo?: string;
}

export interface ConfermeBanco {
    /** null = non chiesto; true = il bot l'ha avuto; false = NON l'ha avuto */
    dal_ms: boolean | null;
    clic_ms: Array<{ ms: number; ricevuto: boolean }>;
}

export interface EsitoBot {
    bot: string;
    scenario: string;
    event_id: string;
    etichetta: string;
    righe: RigaBot[];
    ordini: number;
    violazioni: string[];
    note: string[];
    // 07/10 (assenti negli esiti del 06/10: opzionali)
    sport?: SportBot;
    modalita?: ModalitaScenario;
    parametri_usati?: Record<string, ValoreParametro>;
    parametri_cambiati?: Record<string, ValoreParametro>;
    dal_ms?: number | null;
    accensione?: string | null;
    clic_ms?: number[] | null;
    // 07/10 sera (REPLAY PROFESSIONALE; assenti negli esiti di un worker vecchio)
    /** forma dell'esito: assente = worker del Backtest col codice VECCHIO */
    versione?: number;
    /** la richiesta come l'ha ricevuta il banco */
    richiesta?: { dal_ms: number | null; clic_ms: number[] | null; parametri: Record<string, ValoreParametro> };
    /** che cosa il BOT ha davvero ricevuto */
    conferme?: ConfermeBanco;
    esiti_mercati?: Record<string, EsitoMercato>;
    /** P&L a regolamento dalle righe (Python, stesse regole della UI) */
    conto_banco?: ContoBanco;
    /** P&L regolato da flumine nel banco (null: nessun ordine regolato) */
    conto_flumine?: { lordo: number; mercati: Record<string, number>; ordini_regolati: number } | null;
    /** P&L dichiarato dal referto del bot (null: il bot non lo dichiara) */
    conto_dichiarato?: ContoDichiarato | null;
    /** i cicli come li riepiloga il bot (oggi la media under), null = non li dichiara */
    cicli_bot?: CicloDichiarato[] | null;
    /** i clic «Attiva adesso» col loro esito per il banco, null = nessun clic */
    clic_bot?: ClicDichiarato[] | null;
}

/** Un rientro del ciclo (`riepilogo_cicli_media`, chiave `rientri`). */
export interface RientroDichiarato {
    quota: number;
    /** l'importo esatto prima del multiplo di 0,50 (null se l'attivita' non lo dice) */
    esatto: number | null;
    piazzato: number;
    abbinato: number;
}

/** La banca finale del ciclo (`riepilogo_cicli_media`, chiave `banca`). */
export interface BancaDichiarata {
    importo: number;
    quota: number;
    abbinato: number;
    dove: string | null;
    fine: string;
}

/** Un ciclo come lo riepiloga il bot nel referto (`riepilogo_cicli_media`).
 *  08/10 (cantiere 10): chiavi IDENTICHE a quelle che scrive Python
 *  (`applica_bot.cicli_dichiarati`), controllate dal test di contratto
 *  `Betfair/stream/tests/test_contratto_cicli_bot_ts_2026_10_08.py`. */
export interface CicloDichiarato {
    ciclo: number;
    /** numero di ordini del ciclo */
    ordini: number;
    rientri: RientroDichiarato[];
    /** la banca finale; {} se il ciclo non ne ha */
    banca: BancaDichiarata | Record<string, never>;
    esito: string;
    lordo: number | null;
    netto: number | null;
    inizio_ms: number | null;
    fine_ms: number | null;
    puntato: number;
    ordini_id: string[];
    /** 'clic' | 'rientro_automatico' | null */
    origine: string | null;
    clic: string | null;
    prima_punta_ordine: string | null;
    prima_punta_ms: number | null;
    riga: string;
}

/** Un clic «Attiva adesso» col suo esito per il banco. */
export interface ClicDichiarato {
    id: string;
    clic_ms: number;
    mandato_ms: number | null;
    letto_ms: number | null;
    esito: 'eseguito' | 'rifiutato' | 'non letto' | 'non deciso';
    motivo: string | null;
    prima_punta: { ordine: string; quota: number | null; importo: number | null; ms: number } | null;
}

export interface StatoRichiestaBot {
    status: 'PENDING' | 'RUNNING' | 'DONE' | 'ERROR';
    error_detail: string | null;
    esito: EsitoBot | null;
}

/** Le opzioni della prova: varianti dei parametri, accensione e clic. */
export interface OpzioniApplica {
    /** SOLO le chiavi cambiate rispetto alla serie */
    parametri?: Record<string, ValoreParametro>;
    /** istante di accensione (ms del banco); assente = acceso dall'inizio */
    dal_ms?: number;
    /** istanti di clic «Attiva adesso» (solo i bot che li dichiarano) */
    clic_ms?: number[];
}

/** Il payload della richiesta: le chiavi opzionali compaiono SOLO se usate
 *  (il worker passa al replay solo cio' che c'e'). PURA. */
export function payloadApplicaBot(eventId: string, bot: string, scenario: string,
    opzioni: OpzioniApplica = {}): Record<string, unknown> {
    const p: Record<string, unknown> = { tipo: 'applica_bot', bot, scenario, event_id: eventId };
    if (opzioni.parametri && Object.keys(opzioni.parametri).length > 0) p.parametri = opzioni.parametri;
    if (opzioni.dal_ms != null) p.dal_ms = Math.round(opzioni.dal_ms);
    if (opzioni.clic_ms && opzioni.clic_ms.length > 0) p.clic_ms = opzioni.clic_ms.map(Math.round);
    return p;
}

export async function richiediApplicaBot(eventId: string, bot: string, scenario: string,
    opzioni: OpzioniApplica = {}): Promise<string> {
    const { data, error } = await supabase.rpc('request_backtest', {
        p_params: payloadApplicaBot(eventId, bot, scenario, opzioni),
    });
    if (error) throw new Error(error.message);
    return String(data);
}

export async function leggiEsitoBot(requestId: string): Promise<StatoRichiestaBot> {
    const { data, error } = await supabase.rpc('get_replay_bot_esito', { p_request_id: requestId });
    if (error) throw new Error(error.message);
    return data as StatoRichiestaBot;
}

function chiave(r: RigaBot): string {
    // 07/10 sera: l'identita' dell'ordine e' `_ordine` (un replace di flumine ha lo
    // STESSO ref del vecchio); gli esiti di prima ricadono sul ref
    return r._ordine ? `o:${r._ordine}` : String(r.client_order_ref ?? r.bet_id ?? '');
}

/** Le righe del referto che spiegano COSA ha fatto il bot e PERCHE' non
 *  entrava (cicli, P&L, motivi di non ingresso). PURA. */
export function noteUtili(note: ReadonlyArray<string>): string[] {
    return note.filter(n => /ciclo \d+:|P&L del replay|motivi di non ingresso|non entra/i.test(n))
        .map(n => n.replace(/^nota:\s*/, '').replace(/^MEDIA UNDER:?\s*/, ''));
}

/** 07/10 sera: le pagine NON usano piu' questa funzione ne' `conOrdiniDelBot`
 *  (gli ordini del bot passavano dagli ordini del training: filtrati per
 *  modalita' e riletti ogni 5 s, «sul ladder non si vede niente»). Il registro,
 *  il ladder e il P&L del bot vengono da `replayOperazioni.ts`. Restano per
 *  compatibilita' (i loro test).
 *  Gli ordini del bot come erano all'istante `ms` (ultima riga di ogni ordine
 *  con _ms <= ms), come righe LiveOrderRow (quelle che il ladder legge).
 *  `marketId` filtra un mercato. PURA. */
export function ordiniBotAlMs(righe: ReadonlyArray<RigaBot>, ms: number, marketId?: string): LiveOrderRow[] {
    const ultima = new Map<string, RigaBot>();
    for (const r of righe) {
        if (r._ms > ms) break;                     // righe ordinate per _ms
        if (marketId && r.market_id !== marketId) continue;
        ultima.set(chiave(r), r);
    }
    const out: LiveOrderRow[] = [];
    let i = 0;
    for (const r of ultima.values()) {
        i += 1;
        const { _ms, ...riga } = r;
        // id negativo: mai in collisione con gli ordini del training (id >= 1)
        out.push({ ...riga, id: -i, updated_at: new Date(_ms).toISOString() });
    }
    return out;
}

/** L'orderApi del ladder training con IN PIU' gli ordini del bot (sola
 *  lettura): fetchOrders aggiunge quelli del bot del mercato all'istante
 *  corrente; un annullo di un ordine del bot e' rifiutato. */
export function conOrdiniDelBot(base: LadderOrderApi, ordiniBot: (marketId: string) => LiveOrderRow[]): LadderOrderApi {
    return {
        ...base,
        fetchOrders: async (marketId, mode) => [
            ...(await base.fetchOrders(marketId, mode)),
            ...ordiniBot(marketId),
        ],
        send: async (cmd) => {
            if (cmd.action === 'cancel' && cmd.bet_id && cmd.market_id
                && ordiniBot(cmd.market_id).some(o => o.bet_id === cmd.bet_id)) {
                return { ok: false, action: 'cancel', mode: 'paper',
                         error: 'ordine del bot applicato: sola lettura' };
            }
            return base.send(cmd);
        },
    };
}
