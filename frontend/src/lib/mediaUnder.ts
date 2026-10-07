// ============================================================================
// mediaUnder.ts — la modalità «MEDIA UNDER» dello Scalper calcio (05/10/2026).
// Spec: Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md (par.5, par.6, par.8).
//
// Solo dati e testi per la scheda (ScalperPanel): i valori di serie, i campi
// modificabili, il controllo dei valori PRIMA di mandarli, e la lettura delle
// statistiche che la sessione scrive (`media_*` in scalper_control.stats).
// I calcoli veri li fa il servizio (media_under_bot.py): qui nessuna formula.
//
// I valori di serie sono gli STESSI di `media_under_bot.VALORI_DI_SERIE`: un test
// di contratto Python li confronta (catalogo par.7 punto 33). La sessione NON
// riempie un valore mancante: la scheda li manda sempre tutti.
// ============================================================================

export type MediaMercato = 'OVER_UNDER_25' | 'OVER_UNDER_35';

export const MEDIA_MERCATI: { key: MediaMercato; label: string }[] = [
    { key: 'OVER_UNDER_25', label: 'Under 2,5' },
    { key: 'OVER_UNDER_35', label: 'Under 3,5' },
];

export interface MediaUnderParams {
    media_stake: number;
    media_obiettivo: number;
    media_tick_chiusura: number;
    media_tick_rientro: number;
    media_max_rientri: number;
    media_rischio_max: number;
    media_quota_min: number;
    media_quota_max: number;
    media_min_size: number;
    media_min_flow: number;
    media_max_spread_ticks: number;
    media_stop_ingressi_s: number;
    media_ttl_punta_ms: number;
    media_obiettivi_live: number[];
    media_commissione_pct: number;
}

// i valori di serie (spec par.5) — specchio di media_under_bot.VALORI_DI_SERIE
export const MEDIA_UNDER_DEFAULTS = {
    media_mode: false,
    media_stake: 10,
    media_obiettivo: 0,
    media_tick_chiusura: 2,
    media_tick_rientro: 2,
    media_max_rientri: 5,
    media_rischio_max: 0,
    media_quota_min: 1.2,
    media_quota_max: 4.0,
    media_min_size: 300,
    media_min_flow: 10,
    media_max_spread_ticks: 2,
    media_stop_ingressi_s: 420,
    media_ttl_punta_ms: 30000,
    media_obiettivi_live: [0, 0.3, 1.0],
    media_commissione_pct: 5.0,
    // 07/10 «Attiva adesso»: rientri automatici pre-match coi filtri (spento =
    // il nuovo ciclo pre-match parte subito al miglior prezzo)
    media_rientro_auto_filtri: false,
};

export type MediaCampoNumerico = Exclude<keyof MediaUnderParams, 'media_obiettivi_live'>;

// i campi della scheda: testi per un non tecnico, ogni cifra dice cos'è
export const MEDIA_UNDER_CAMPI: {
    key: MediaCampoNumerico; label: string; step: number; min: number; hint: string;
}[] = [
    { key: 'media_stake', label: 'Punta d\'ingresso €', step: 0.5, min: 1, hint: 'la prima punta di ogni ciclo (da 1,00 a multipli di 0,50)' },
    { key: 'media_obiettivo', label: 'Profitto voluto € netti', step: 0.05, min: 0, hint: '0 = automatico: il profitto dei tick di chiusura sulla prima punta, uguale nei rientri' },
    { key: 'media_tick_chiusura', label: 'Tick di chiusura', step: 1, min: 1, hint: 'la banca sta tanti tick sotto la quota dell\'ultima punta' },
    { key: 'media_tick_rientro', label: 'Tick per rientrare', step: 1, min: 1, hint: 'di quanti tick deve salire la quota sopra l\'ultima punta per mediare' },
    { key: 'media_max_rientri', label: 'Rientri massimi', step: 1, min: 0, hint: 'dopo l\'ultimo non punta più e lascia la banca appoggiata' },
    { key: 'media_rischio_max', label: 'Rischio massimo €', step: 10, min: 0, hint: 'totale puntato oltre cui i rientri si bloccano (0 = spento)' },
    { key: 'media_quota_min', label: 'Quota minima', step: 0.01, min: 1.01, hint: 'sotto questa quota dell\'Under non entra' },
    { key: 'media_quota_max', label: 'Quota massima', step: 0.01, min: 1.01, hint: 'sopra questa quota dell\'Under non entra' },
    { key: 'media_min_size', label: 'Liquidità minima € ai best', step: 25, min: 0, hint: 'euro in coda sulla miglior punta e sulla miglior banca' },
    { key: 'media_min_flow', label: 'Scambi minimi €/lato (90 s)', step: 5, min: 0, hint: 'euro scambiati per lato negli ultimi 90 secondi' },
    { key: 'media_max_spread_ticks', label: 'Distanza max punta-banca (tick)', step: 1, min: 0, hint: 'tick fra miglior punta e miglior banca' },
    { key: 'media_stop_ingressi_s', label: 'Stop ingressi e rientri (s prima del fischio)', step: 30, min: 0, hint: 'secondi prima del fischio d\'inizio' },
    { key: 'media_ttl_punta_ms', label: 'Attesa della punta (ms)', step: 1000, min: 1, hint: 'millisecondi: una punta non abbinata entro questo tempo si ritira' },
    { key: 'media_commissione_pct', label: 'Commissione %', step: 0.5, min: 0, hint: 'per il netto mostrato e per il profitto voluto in netti' },
];

export function mediaUnderDefaults(): MediaUnderParams {
    // il rientro automatico coi filtri è un'opzione del solo pulsante «Attiva
    // adesso» (attivaAdessoParams): l'accensione di sempre non la manda
    const { media_mode: _spenta, media_rientro_auto_filtri: _soloPulsante, ...resto } = MEDIA_UNDER_DEFAULTS;
    return { ...resto, media_obiettivi_live: [...MEDIA_UNDER_DEFAULTS.media_obiettivi_live] };
}

const multiploDi050 = (x: number): boolean => Math.abs(x * 2 - Math.round(x * 2)) < 1e-9;
const intero = (x: number): boolean => Number.isInteger(x);

// I motivi per cui la scheda NON manda la richiesta (la sessione rifarebbe lo
// stesso controllo e si fermerebbe): nessun valore inventato.
export function erroriMediaUnder(mercato: MediaMercato | '', p: MediaUnderParams): string[] {
    const e: string[] = [];
    if (mercato !== 'OVER_UNDER_25' && mercato !== 'OVER_UNDER_35') {
        e.push('Scegli il mercato: Under 2,5 oppure Under 3,5.');
    }
    if (!(p.media_stake >= 1) || !multiploDi050(p.media_stake)) {
        e.push('La punta d\'ingresso va da 1,00 € a multipli di 0,50 (regola di Betfair.it).');
    }
    if (!(p.media_obiettivo >= 0)) e.push('Il profitto voluto non può essere negativo (0 = automatico).');
    if (!intero(p.media_tick_chiusura) || p.media_tick_chiusura < 1) e.push('I tick di chiusura sono un numero intero da 1 in su.');
    if (!intero(p.media_tick_rientro) || p.media_tick_rientro < 1) e.push('I tick per rientrare sono un numero intero da 1 in su.');
    if (!intero(p.media_max_rientri) || p.media_max_rientri < 0) e.push('I rientri massimi sono un numero intero da 0 in su.');
    if (!intero(p.media_max_spread_ticks) || p.media_max_spread_ticks < 0) e.push('La distanza punta-banca è un numero intero di tick da 0 in su.');
    if (!intero(p.media_ttl_punta_ms) || p.media_ttl_punta_ms < 1) e.push('L\'attesa della punta è un numero intero di millisecondi.');
    for (const k of ['media_rischio_max', 'media_min_size', 'media_min_flow', 'media_stop_ingressi_s'] as const) {
        if (!(p[k] >= 0)) e.push(`Il valore «${MEDIA_UNDER_CAMPI.find(c => c.key === k)?.label}» non può essere negativo.`);
    }
    if (!(p.media_quota_min >= 1.01) || !(p.media_quota_max <= 1000) || !(p.media_quota_min < p.media_quota_max)) {
        e.push('Le quote vanno da 1,01 a 1000 e la minima deve stare sotto la massima.');
    }
    if (p.media_obiettivi_live.some(x => !(x >= 0))) e.push('Gli obiettivi della segnalazione in gioco sono euro da 0 in su.');
    if (!(p.media_commissione_pct >= 0) || !(p.media_commissione_pct < 100)) e.push('La commissione va da 0 a 99 %.');
    return e;
}

// I parametri che la scheda scrive in scalper_control.params con la modalità
// accesa: tutti presenti, mai un default lasciato al servizio. Sniper, theta e
// intervallo SPENTI (una sessione media under arma solo la modalità).
export function paramsMediaUnder(mercato: MediaMercato, p: MediaUnderParams): Record<string, unknown> {
    return {
        ...p,
        media_obiettivi_live: [...p.media_obiettivi_live],
        media_mode: true,
        media_mercato: mercato,
        sniper_mode: false,
        theta_mode: false,
        ht_mode: false,
    };
}

// ---- «ATTIVA ADESSO» (07/10/2026, ordine dell'utente) ---------------------
// Il pulsante della scheda: in prova come in soldi veri, la stessa strada.
// Il clic è un COMANDO con un id unico che la sessione consuma una sola volta
// (anche dopo un riavvio). Sessione ferma: il clic la accende armata dal
// pulsante (media_a_clic) col comando dentro; sessione accesa: il comando
// arriva con la RPC scalper_media_attiva_adesso (mediaUnderAttiva.ts).
export const CHIAVE_COMANDO = 'media_attiva_adesso';

export interface ComandoAttivaAdesso {
    id: string;
    ts: string;
}

// un id unico per ogni clic (mai riusato: due clic = due comandi)
export function nuovoComandoAttivaAdesso(adesso: Date = new Date()): ComandoAttivaAdesso {
    const caso = Math.random().toString(36).slice(2, 10);
    return { id: `clic-${adesso.getTime()}-${caso}`, ts: adesso.toISOString() };
}

// I parametri che il pulsante scrive quando la sessione è FERMA: tutti quelli
// della modalità, la sessione armata dal pulsante, l'interruttore dei rientri
// automatici pre-match coi filtri, e il comando del clic.
export function paramsAttivaAdesso(
    mercato: MediaMercato, p: MediaUnderParams, rientroConFiltri: boolean,
    comando: ComandoAttivaAdesso,
): Record<string, unknown> {
    return {
        ...paramsMediaUnder(mercato, p),
        media_a_clic: true,
        media_rientro_auto_filtri: rientroConFiltri,
        [CHIAVE_COMANDO]: { id: comando.id, ts: comando.ts },
    };
}

export interface MediaComando {
    id: string;
    esito: 'ricevuto' | 'eseguito' | 'rifiutato' | string;
    motivo: string | null;
    prezzo: number | null;
    importo: number | null;
    in_gioco: boolean | null;
}

function leggiComando(v: unknown): MediaComando | null {
    if (!isObj(v) || typeof v.id !== 'string') return null;
    return {
        id: v.id,
        esito: str(v.esito) ?? 'ricevuto',
        motivo: str(v.motivo),
        prezzo: numONull(v.prezzo),
        importo: numONull(v.importo),
        in_gioco: typeof v.in_gioco === 'boolean' ? v.in_gioco : null,
    };
}

// Lo stato del comando per la scheda: l'ultimo clic mandato da QUESTA scheda
// (idInviato) e cosa ne dice la sessione (stats.media_comando).
export type StatoClic =
    | { fase: 'nessuno' }
    | { fase: 'inviato'; id: string }
    | { fase: 'eseguito'; id: string; prezzo: number | null; importo: number | null; inGioco: boolean | null }
    | { fase: 'rifiutato'; id: string; motivo: string };

export function statoDelClic(idInviato: string | null, comando: MediaComando | null): StatoClic {
    if (comando && (idInviato === null || comando.id === idInviato)) {
        if (comando.esito === 'eseguito') {
            return { fase: 'eseguito', id: comando.id, prezzo: comando.prezzo, importo: comando.importo, inGioco: comando.in_gioco };
        }
        if (comando.esito === 'rifiutato') {
            return { fase: 'rifiutato', id: comando.id, motivo: comando.motivo ?? 'motivo non scritto dalla sessione' };
        }
        return { fase: 'inviato', id: comando.id };
    }
    if (idInviato) return { fase: 'inviato', id: idInviato };
    return { fase: 'nessuno' };
}

export function testoStatoClic(s: StatoClic): string {
    switch (s.fase) {
        case 'nessuno':
            return 'Nessun clic su «Attiva adesso» in questa sessione.';
        case 'inviato':
            return 'Attiva adesso INVIATO: la sessione punta al prossimo prezzo (o dice perché no).';
        case 'eseguito':
            return `Attiva adesso ESEGUITO: punta di ${s.importo !== null ? euro(s.importo) : '—'} € ` +
                `a ${quota(s.prezzo)}${s.inGioco ? ' in gioco' : s.inGioco === false ? ' prima del fischio' : ''}.`;
        case 'rifiutato':
            return `Attiva adesso RIFIUTATO: ${s.motivo}.`;
    }
}

// La conferma ESPLICITA dei soldi veri per il clic (la stessa asimmetria della
// conferma dell'accensione: in prova nessuna conferma, in soldi veri sempre).
export function testoConfermaAttivaAdesso(
    evento: string, mercato: string, p: Pick<MediaUnderParams, 'media_stake' | 'media_max_rientri' | 'media_rischio_max'>,
): string {
    return `⚠️ ATTIVA ADESSO CON ORDINI REALI su "${evento}" (${mercato})?\n\n` +
        `Il bot PUNTA SUBITO ${euro(p.media_stake)} € sull'${mercato} al miglior prezzo, senza aspettare i filtri, ` +
        `poi gestisce la posizione come progettato (banca di chiusura e fino a ${p.media_max_rientri} rientri, ` +
        'anche in gioco). Ogni rientro è quasi il doppio del precedente. ' +
        (p.media_rischio_max > 0
            ? `Rientri bloccati oltre ${euro(p.media_rischio_max)} € puntati.\n`
            : 'Rischio massimo SPENTO.\n') +
        'Se la partita ha un ciclo aperto, il clic viene rifiutato.\n' +
        'Modalità NON certificata sul replay.\nConfermi?';
}

// i numeri della conferma letti dalla riga della sessione accesa
export function importiDallaRiga(
    params: Record<string, unknown> | null | undefined,
): Pick<MediaUnderParams, 'media_stake' | 'media_max_rientri' | 'media_rischio_max'> {
    const p = params ?? {};
    return {
        media_stake: num(p.media_stake, MEDIA_UNDER_DEFAULTS.media_stake),
        media_max_rientri: num(p.media_max_rientri, MEDIA_UNDER_DEFAULTS.media_max_rientri),
        media_rischio_max: num(p.media_rischio_max, MEDIA_UNDER_DEFAULTS.media_rischio_max),
    };
}

// Mentre l'ultimo clic è ancora «inviato» il pulsante resta fermo (niente
// doppio clic); scaduta l'attesa torna cliccabile (la sessione lo dirà).
export const ATTESA_ESITO_CLIC_MS = 20_000;

export function pulsanteCliccabile(s: StatoClic, inviatoAlle: number | null, adesso: number): boolean {
    if (s.fase !== 'inviato') return true;
    return inviatoAlle === null || adesso - inviatoAlle > ATTESA_ESITO_CLIC_MS;
}

// "0, 0,30, 1" -> [0, 0.3, 1]; null se un pezzo non è un numero
export function leggiObiettiviLive(testo: string): number[] | null {
    const pezzi = testo.split(/[;\s]+|,(?!\d)/).map(s => s.trim()).filter(Boolean);
    const out: number[] = [];
    for (const pz of pezzi) {
        const n = Number(pz.replace(',', '.'));
        if (!Number.isFinite(n)) return null;
        out.push(n);
    }
    return out;
}

// ---- lettura delle statistiche della sessione (media_* in stats) ----------
export interface MediaBanca {
    stato: string;
    importo?: number;
    quota?: number;
    abbinato?: number;
    testo?: string;
}

export interface MediaObiettivo {
    obiettivo_netto: number;
    quota_punta: number;
    quota_chiusura: number;
    punta: number;
    punta_esatta: number;
    rischio_totale: number;
    rischio_totale_esatto: number;
    quota_media_dopo: number | null;
    quota_media_dopo_esatta: number | null;
    banca_dopo: number;
    profitto_netto: number;
    piazzabile: boolean;
}

export interface MediaChiusura {
    fonte: string;
    posizione: {
        totale_puntato: number; quota_media: number | null; banche_abbinate: number;
        se_vince: number; se_perde: number;
    };
    banca: MediaBanca;
    tick: number;
    chiudi_adesso: { banca: number; quota: number; pnl_lordo: number; pnl_netto: number } | null;
    obiettivi: MediaObiettivo[];
}

export interface MediaUnderStato {
    stato: string;
    mercato: string | null;
    rientri: number;
    max_rientri: number;
    totale_puntato: number;
    quota_media: number | null;
    se_vince: number;
    se_perde: number;
    banca: MediaBanca;
    cicli_chiusi: number;
    pnl_chiuso_lordo: number;
    rientri_bloccati: string | null;
    riavvio: string | null;
    fonte: string | null;
    chiusura: MediaChiusura | null;
    // 07/10 «Attiva adesso»
    comando: MediaComando | null;
    a_clic: boolean;
    origine_ciclo: string | null;
    in_gioco: boolean;
}

const isObj = (v: unknown): v is Record<string, unknown> =>
    typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const numONull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);

function leggiBanca(v: unknown): MediaBanca {
    if (!isObj(v)) return { stato: 'nessuna' };
    return {
        stato: str(v.stato) ?? 'nessuna',
        importo: numONull(v.importo) ?? undefined,
        quota: numONull(v.quota) ?? undefined,
        abbinato: numONull(v.abbinato) ?? undefined,
        testo: str(v.testo) ?? undefined,
    };
}

function leggiChiusura(v: unknown): MediaChiusura | null {
    if (!isObj(v) || !isObj(v.posizione)) return null;
    const pos = v.posizione;
    const ca = isObj(v.chiudi_adesso) ? v.chiudi_adesso : null;
    const obiettivi: MediaObiettivo[] = (Array.isArray(v.obiettivi) ? v.obiettivi : [])
        .filter(isObj)
        .map(o => ({
            obiettivo_netto: num(o.obiettivo_netto), quota_punta: num(o.quota_punta),
            quota_chiusura: num(o.quota_chiusura), punta: num(o.punta),
            punta_esatta: num(o.punta_esatta), rischio_totale: num(o.rischio_totale),
            rischio_totale_esatto: num(o.rischio_totale_esatto),
            quota_media_dopo: numONull(o.quota_media_dopo),
            quota_media_dopo_esatta: numONull(o.quota_media_dopo_esatta),
            banca_dopo: num(o.banca_dopo), profitto_netto: num(o.profitto_netto),
            piazzabile: o.piazzabile === true,
        }));
    return {
        fonte: str(v.fonte) ?? '',
        posizione: {
            totale_puntato: num(pos.totale_puntato), quota_media: numONull(pos.quota_media),
            banche_abbinate: num(pos.banche_abbinate), se_vince: num(pos.se_vince),
            se_perde: num(pos.se_perde),
        },
        banca: leggiBanca(v.banca),
        tick: num(v.tick),
        chiudi_adesso: ca ? {
            banca: num(ca.banca), quota: num(ca.quota), pnl_lordo: num(ca.pnl_lordo),
            pnl_netto: num(ca.pnl_netto),
        } : null,
        obiettivi,
    };
}

// Le statistiche della modalità dalla riga della sessione; null se la sessione
// non ha la modalità (nessuna chiave media_stato).
export function leggiMediaUnder(stats: Record<string, unknown> | null | undefined): MediaUnderStato | null {
    if (!stats || typeof stats.media_stato !== 'string') return null;
    return {
        stato: stats.media_stato,
        mercato: str(stats.media_mercato),
        rientri: num(stats.media_rientri),
        max_rientri: num(stats.media_max_rientri),
        totale_puntato: num(stats.media_totale_puntato),
        quota_media: numONull(stats.media_quota_media),
        se_vince: num(stats.media_se_vince),
        se_perde: num(stats.media_se_perde),
        banca: leggiBanca(stats.media_banca),
        cicli_chiusi: num(stats.media_cicli_chiusi),
        pnl_chiuso_lordo: num(stats.media_pnl_chiuso_lordo),
        rientri_bloccati: str(stats.media_rientri_bloccati),
        riavvio: str(stats.media_riavvio),
        fonte: str(stats.media_fonte),
        chiusura: leggiChiusura(stats.media_chiusura),
        comando: leggiComando(stats.media_comando),
        a_clic: stats.media_a_clic === true,
        origine_ciclo: str(stats.media_origine_ciclo),
        in_gioco: stats.media_in_gioco === true,
    };
}

// lo stato del ciclo in parole (spec par.3)
export const MEDIA_STATI_TESTO: Record<string, string> = {
    FERMO: 'in attesa di un ingresso (prima del fischio)',
    INGRESSO: 'punta d\'ingresso piazzata, in attesa di abbinamento',
    IN_POSIZIONE: 'in posizione: banca di chiusura appoggiata',
    RIENTRO: 'sta mediando: banca ritirata, punta di rientro in corso',
    MASSIMO: 'rientri finiti: nessuna punta in più, banca appoggiata',
    LIVE: 'partita in gioco: NESSUN ordine, gestisci tu la chiusura',
    FINE: 'finita: nessuna posizione da gestire',
    BLOCCATA: 'ferma: posizione di una sessione precedente non ricostruibile, nessun ordine',
    RIPRESA: 'ripresa dopo un riavvio: ricostruisce la posizione dal conto, nessun ordine nuovo',
    // 07/10 «Attiva adesso»
    ATTESA_CLIC: 'in ATTESA DEL CLIC: clicca «Attiva adesso» per far partire un ciclo',
};

// lo stato in parole tenendo conto di come è stata accesa (pulsante o di sempre)
export function testoStatoMedia(s: MediaUnderStato): string {
    if (s.a_clic && s.stato === 'FERMO') {
        // in gioco il bot non riparte mai da solo (al primo prezzo diventa ATTESA_CLIC)
        return s.in_gioco ? MEDIA_STATI_TESTO.ATTESA_CLIC
            : 'ciclo chiuso prima del fischio: riparte da solo (rientro automatico)';
    }
    const base = MEDIA_STATI_TESTO[s.stato] ?? s.stato;
    if (s.a_clic && s.in_gioco && ['INGRESSO', 'IN_POSIZIONE', 'RIENTRO', 'MASSIMO'].includes(s.stato)) {
        return `${base} — in gioco gestisce la posizione come prima del fischio (avviata col pulsante)`;
    }
    return base;
}

// da dove è partito il ciclo in corso
export const MEDIA_ORIGINE_TESTO: Record<string, string> = {
    clic: 'partito dal clic su «Attiva adesso»',
    rientro_automatico: 'partito da solo dopo una chiusura prima del fischio',
    filtri: 'partito coi filtri d\'ingresso',
};

export const euro = (x: number): string =>
    x.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const quota = (x: number | null | undefined): string =>
    typeof x === 'number' ? x.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '—';

// una riga del riquadro per un obiettivo, in italiano chiaro
export function testoObiettivo(o: MediaObiettivo): string {
    const ob = o.obiettivo_netto === 0 ? 'per chiudere in pari' : `per chiudere con +${euro(o.obiettivo_netto)} € netti`;
    if (!o.piazzabile) {
        return `${ob}: servirebbe una punta di ${euro(o.punta_esatta)} €, non piazzabile su Betfair.it (sotto 1,00 €).`;
    }
    return `${ob} a ${quota(o.quota_chiusura)}: PUNTA ${euro(o.punta)} € a ${quota(o.quota_punta)} ` +
        `(importo esatto ${euro(o.punta_esatta)} €). Rischio totale ${euro(o.rischio_totale)} € ` +
        `(con l'esatto ${euro(o.rischio_totale_esatto)} €), nuova quota media ${quota(o.quota_media_dopo)} ` +
        `(con l'esatto ${quota(o.quota_media_dopo_esatta)}), poi appoggia una BANCA di ${euro(o.banca_dopo)} € ` +
        `a ${quota(o.quota_chiusura)}.`;
}
