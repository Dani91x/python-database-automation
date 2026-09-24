// ============================================================================
// chiudiRiga.ts — IL «CHIUDI» DI UNA RIGA, CABLATO PER SINGOLO BOT (B16, 24/09).
//
// IL REPERTO (l'utente lo definisce GRAVISSIMO). Il bottone «Chiudi» di una
// riga della Control Room accodava `safe_request('cashout', {trade_id})` per
// QUALUNQUE bot. Il servizio di Safe legge `trade_id` nella SUA tabella: su una
// riga di Omega o di Mike il clic non chiudeva niente - oppure chiudeva la riga
// di Safe con lo stesso numero (gli id delle tabelle dei bot collidono).
//
// ORA: ogni riga va al percorso di chiusura manuale che IL SUO BOT esegue gia'.
//   · Omega → `omega_request('cashout', …)` → `omega_manual_requests` →
//     `omega_service.process_manual` → `_manual_cashout` (green-up
//     dell'ABBINATO, modalita' della riga).
//   · Safe (calcio e tennis) → `safe_request('cashout', …)` →
//     `safe_strategy_requests` → `bot_service.process_requests` (corsia veloce
//     delle chiusure) → `_request_cashout`.
//   · Mike → `mike_request('cashout', {event_id, …})` → `mike_requests` →
//     `service.process_requests` → `_request_flatten`: Mike chiude la PARTITA
//     (il ciclo intero), non una riga sola - e' il suo modo di chiudere.
//   · I 4 bot tennis → NESSUN percorso di chiusura manuale esiste nel loro
//     servizio: costruirlo vuol dire toccare le loro strategie (decisione
//     dell'utente). Il bottone lo DICE, non sparisce in silenzio.
//
// Il payload porta SEMPRE `bot`, `event_id` e `mode` della riga: il servizio
// li confronta con la riga vera e rifiuta una richiesta ambigua (fail-closed,
// mai un ordine «per sicurezza»). Paper e live mai mischiati: la modalita' e'
// quella DELLA RIGA, dichiarata dal servizio; assente = non si chiude.
// ============================================================================
import { isBotTennis, type Bot } from '@/lib/controlRoom';
import { isSettled, isErrorRow } from '@/lib/eventGroups';
import { requestManual, fetchManualRequests } from '@/lib/omega';
import { requestSafe, fetchSafeRequests } from '@/lib/safeBot';
import { requestMike, fetchMikeRequests } from '@/lib/mike';
import { fetchScalperState } from '@/lib/scalper';
import { stopScalperSessione } from '@/lib/scalperControlRoom';

// 24/09 - LO SCALPER CALCIO. La sua "riga" in Control Room e' la SESSIONE di
// una partita (id = event_id numerico). Chiudere = fermare la sessione:
// `scalper_stop_sessione` porta la riga `scalper_control` a 'stopping', la
// sessione (che la rilegge ogni 5 s) fa force-flat di maker/sniper/theta,
// aspetta il flat fino a 30 s e scrive 'stopped' (`scalper_session.py`). La
// GUARDIA D'IDENTITA' e' la firma della sessione (`requested_at`) + la
// modalita': una sessione riarmata nel frattempo, o in un'altra modalita',
// fa rifiutare la richiesta ('richiesta_ambigua'), mai uno stop a caso.
export type BotConChiusura = 'omega' | 'safe' | 'mike' | 'scalper';

/** Cio' che serve per chiudere UNA riga: la sua identita', non il suo aspetto. */
export interface RigaDaChiudere {
    bot: Bot;
    id: number;
    /** partita della riga (serve a Mike, che chiude per partita) */
    eventId: string | null;
    /** modalita' DICHIARATA dal servizio; null = non si chiude alla cieca */
    modalita: 'paper' | 'live' | null;
    /** stato della riga come lo scrive il servizio */
    stato: string;
    /** `closes_trade_id`: una gamba di CHIUSURA non si chiude a sua volta */
    chiudeId?: number | null;
    /** risultato gia' certo (regolata dal mercato): non e' una posizione */
    regolata?: boolean;
    /** 24/09 - scalper: la FIRMA della sessione (`requested_at`, esattamente
     *  come l'ha scritta il database). Senza firma non si ferma niente. */
    firma?: string | null;
    /** 24/09 - scalper: sessione gia' ferma ma con esposizione abbinata non
     *  coperta (lo stop non ha trovato il flat in 30 s) */
    residuo?: boolean;
}

/** Gli stati della sessione scalper in cui uno stop ha qualcosa da fermare. */
const SCALPER_FERMABILE = new Set(['requested', 'arming', 'armed', 'running']);

export type Chiudibile = { ok: true } | { ok: false; motivo: string };

const STATI_NON_POSIZIONE = new Set(['cancelled', 'lapsed', 'void', 'won', 'lost']);

/**
 * La riga si puo' chiudere adesso? `null` = non e' una posizione (regolata,
 * errore, annullata): nessun bottone. `{ok:false, motivo}` = e' una posizione
 * ma il clic non partirebbe: il bottone resta, spento, e dice perche'.
 */
export function chiudibile(r: RigaDaChiudere): Chiudibile | null {
    const s = String(r.stato ?? '').toLowerCase();
    if (r.bot === 'scalper') return chiudibileScalper(r, s);
    if (r.regolata || isSettled(s) || isErrorRow(s) || STATI_NON_POSIZIONE.has(s)) return null;
    if (isBotTennis(r.bot)) {
        return {
            ok: false,
            motivo: 'chiusura manuale non cablata per i bot tennis: le loro uscite le guida la '
                + 'strategia del bot (costruirla vuol dire toccarla: decisione dell\'utente)',
        };
    }
    if (r.chiudeId != null) {
        return { ok: false, motivo: 'e\' una gamba di chiusura: si chiude con la sua apertura' };
    }
    if (r.modalita !== 'paper' && r.modalita !== 'live') {
        return { ok: false, motivo: 'modalita\' della riga non dichiarata dal servizio: non si chiude alla cieca' };
    }
    if (s === 'hedged') return { ok: false, motivo: 'posizione gia\' coperta per intero: nulla da chiudere' };
    if (s === 'pending_reconcile') {
        return { ok: false, motivo: 'in riconciliazione: l\'esito dell\'ordine e\' ancora ignoto' };
    }
    if (r.bot === 'omega' && s === 'pending') {
        return { ok: false, motivo: 'ordine di apertura in volo: si chiude quando e\' abbinato' };
    }
    if (r.bot === 'mike' && !r.eventId) {
        return { ok: false, motivo: 'partita della riga sconosciuta: Mike chiude per partita' };
    }
    return { ok: true };
}

/** La sessione scalper: fermabile se attiva, con firma e modalita' dichiarate. */
function chiudibileScalper(r: RigaDaChiudere, s: string): Chiudibile | null {
    if (s === 'stopping') {
        return { ok: false, motivo: 'la sessione si sta gia\' fermando (force-flat in corso)' };
    }
    if (!SCALPER_FERMABILE.has(s)) {
        // ferma (stopped/done/error): non c'e' una sessione da fermare. Se e'
        // rimasta un'esposizione, lo si dice: la chiude il trader dal ladder.
        return r.residuo
            ? {
                ok: false,
                motivo: 'sessione gia\' ferma con esposizione non coperta: '
                    + 'chiudila dal ladder di Segui Live (lo scalper non riapre una sessione per chiudere)',
            }
            : null;
    }
    if (r.modalita !== 'paper' && r.modalita !== 'live') {
        return { ok: false, motivo: 'modalita\' della sessione non dichiarata: non si ferma alla cieca' };
    }
    if (!r.eventId) return { ok: false, motivo: 'partita della sessione sconosciuta' };
    if (!r.firma) {
        return { ok: false, motivo: 'firma della sessione assente (requested_at): non si ferma alla cieca' };
    }
    return { ok: true };
}

/** Cosa fa il clic, per bot: detto nel `title` del bottone. */
export function cosaFaIlClic(bot: Bot): string {
    if (bot === 'scalper') {
        return 'ferma la SESSIONE dello scalper su questa partita: force-flat di tutti gli ordini '
            + '(maker, sniper, theta) e attesa del flat fino a 30 s, nella modalita\' della sessione';
    }
    if (bot === 'mike') {
        return 'Mike chiude l\'intera posizione della PARTITA (ciclo: ingresso, copertura, ordini vivi), '
            + 'sull\'abbinato, nella modalita\' della partita';
    }
    if (bot === 'omega') return 'Omega chiude questa posizione (green-up dell\'abbinato), nella modalita\' della riga';
    if (bot === 'safe') return 'Safe chiude questa posizione (green-up dell\'abbinato), nella modalita\' della riga';
    return 'nessuna chiusura manuale per questo bot';
}

/** I tre percorsi. Sostituibili solo nei test (stesse firme delle vere). */
export const INVIO: Record<BotConChiusura, (r: RigaDaChiudere) => Promise<number>> = {
    omega: (r) => requestManual('cashout', {
        trade_id: r.id, fraction: 1, bot: 'omega', event_id: r.eventId, mode: r.modalita,
    }),
    safe: (r) => requestSafe('cashout', {
        trade_id: r.id, fraction: 1, bot: 'safe', event_id: r.eventId, mode: r.modalita,
    }),
    mike: (r) => requestMike('cashout', {
        event_id: r.eventId, trade_id: r.id, bot: 'mike', mode: r.modalita,
    }),
    // la "richiesta" dello scalper e' la riga `scalper_control` stessa: il suo
    // id e' quello della riga (l'event_id numerico), riletto da `LETTURA`
    scalper: async (r) => {
        await stopScalperSessione(String(r.eventId), String(r.firma), r.modalita as 'paper' | 'live');
        return r.id;
    },
};

/**
 * Scrive la richiesta di chiusura sulla coda DEL BOT DELLA RIGA. Lancia con il
 * motivo se la riga non e' chiudibile (mai una richiesta mandata «per
 * provare»). Ritorna l'id della richiesta nella tabella di quel bot.
 */
export async function inviaChiusura(r: RigaDaChiudere): Promise<{ bot: BotConChiusura; requestId: number }> {
    const c = chiudibile(r);
    if (c == null) throw new Error('la riga non e\' una posizione aperta');
    if (!c.ok) throw new Error(c.motivo);
    const bot = r.bot as BotConChiusura;
    const requestId = await INVIO[bot](r);
    return { bot, requestId: Number(requestId) };
}

// ------------------------------------------------------------ esito

export type FaseChiusura = 'inviata' | 'presa_in_carico' | 'eseguita' | 'rifiutata' | 'ignota';

/** La riga della coda del bot, nelle chiavi VERE delle tre tabelle. */
export interface RichiestaLetta {
    id: number;
    status: string;
    result: Record<string, unknown> | null;
}

function testo(v: unknown): string | null {
    if (v == null) return null;
    const s = String(v).trim();
    return s ? s : null;
}

/** Il motivo scritto dal servizio: il messaggio in italiano se c'e', se no il codice. */
export function motivoDelServizio(result: Record<string, unknown> | null | undefined): string | null {
    const r = result ?? {};
    const m = testo(r.message) ?? testo(r.rejected) ?? testo(r.error) ?? testo(r.err) ?? testo(r.code);
    return m == null ? null : m.replace(/_/g, ' ');
}

/**
 * Fase della chiusura letta dalla riga della coda del bot.
 *  · pending → inviata (se il servizio ha scritto un messaggio - Safe «in
 *    attesa: riserva non ancora risolta» - lo si mostra);
 *  · processing → presa in carico;
 *  · done → eseguita per Omega/Safe (l'ordine di chiusura e' partito); per
 *    Mike `phase='armed'` = presa in carico (la chiusura la guida il bot nei
 *    giri seguenti: l'«eseguita» arriva dalla riga che cambia);
 *  · rejected / error → rifiutata, col motivo del servizio.
 */
export function faseDaRichiesta(
    bot: BotConChiusura, req: RichiestaLetta,
): { fase: FaseChiusura; motivo: string | null; chiusa: boolean } {
    const st = String(req.status ?? '').toLowerCase();
    const res = req.result ?? null;
    if (st === 'pending' || st === 'proposed') return { fase: 'inviata', motivo: motivoDelServizio(res), chiusa: false };
    if (st === 'processing') return { fase: 'presa_in_carico', motivo: null, chiusa: false };
    if (st === 'done') {
        if (bot === 'mike' && String((res ?? {}).phase ?? '') === 'armed') {
            return { fase: 'presa_in_carico', motivo: motivoDelServizio(res), chiusa: true };
        }
        return { fase: 'eseguita', motivo: motivoDelServizio(res), chiusa: true };
    }
    if (st === 'rejected' || st === 'error') {
        return { fase: 'rifiutata', motivo: motivoDelServizio(res) ?? 'rifiutata dal servizio senza motivo', chiusa: true };
    }
    return { fase: 'ignota', motivo: `stato della richiesta non riconosciuto: ${st || 'assente'}`, chiusa: true };
}

/**
 * 24/09 - LA SESSIONE SCALPER LETTA COME UNA RICHIESTA, cosi' l'esito passa
 * dalla STESSA `faseDaRichiesta` degli altri bot:
 *  - requested/arming/armed/running -> 'pending'   (inviata: la sessione non
 *    ha ancora visto lo stop; la rilegge ogni 5 s);
 *  - stopping                       -> 'processing' (presa in carico:
 *    force-flat in corso);
 *  - stopped / done                 -> 'done'       (eseguita), col motivo se
 *    la sessione ha scritto che il flat NON e' arrivato in 30 s;
 *  - error                          -> 'error'      (rifiutata, col suo errore).
 */
export function richiestaDaSessioneScalper(
    id: number,
    control: { status?: string | null; error?: string | null } | null,
    attivita: readonly { kind?: string | null; payload?: Record<string, unknown> | null }[] = [],
): RichiestaLetta | null {
    if (!control) return null;
    const st = String(control.status ?? '').toLowerCase();
    if (st === 'stopping') return { id, status: 'processing', result: null };
    if (st === 'stopped' || st === 'done') {
        const nonFlat = attivita.find((a) => String(a.kind ?? '') === 'error'
            && /NON flat/i.test(String((a.payload ?? {}).msg ?? '')));
        return {
            id, status: 'done',
            result: nonFlat
                ? { message: 'sessione ferma, ma la posizione NON era flat dopo 30 s: controlla il ladder' }
                : { message: 'sessione ferma' },
        };
    }
    if (st === 'error') {
        return { id, status: 'error', result: { message: control.error ?? 'sessione in errore' } };
    }
    return { id, status: 'pending', result: null };
}

/** Rilegge UNA richiesta dalla coda del suo bot (ripiego del canale). */
export const LETTURA: Record<BotConChiusura, (id: number) => Promise<RichiestaLetta | null>> = {
    scalper: async (id) => {
        const st = await fetchScalperState(String(id), 5);
        return richiestaDaSessioneScalper(id, st.control, st.activity);
    },
    omega: async (id) => {
        const righe = await fetchManualRequests(30);
        const r = righe.find((x) => Number(x.id) === id);
        return r ? { id: Number(r.id), status: String(r.status), result: r.result ?? null } : null;
    },
    safe: async (id) => {
        const righe = await fetchSafeRequests(30);
        const r = righe.find((x) => Number(x.id) === id);
        return r ? { id: Number(r.id), status: String(r.status), result: r.result ?? null } : null;
    },
    mike: async (id) => {
        const righe = await fetchMikeRequests(30);
        const r = righe.find((x) => Number(x.id) === id);
        return r ? { id: Number(r.id), status: String(r.status), result: (r.result ?? null) as Record<string, unknown> | null } : null;
    },
};

/** Lo stato che la pagina mostra accanto al bottone. */
export interface StatoChiusuraRiga {
    bot: Bot;
    id: number;
    requestId: number | null;
    /** fase letta dalla coda del bot */
    faseRichiesta: FaseChiusura;
    /** la riga della coda e' in uno stato finale: non si rilegge piu' */
    richiestaChiusa: boolean;
    motivo: string | null;
    /** la riga e' cambiata sul canale (gamba di chiusura nuova, coperta, regolata) */
    rigaCambiata: boolean;
    inviataMs: number;
}

/** Fase MOSTRATA: il rifiuto del servizio vince; poi la riga cambiata. */
export function faseMostrata(s: StatoChiusuraRiga): FaseChiusura {
    if (s.faseRichiesta === 'rifiutata') return 'rifiutata';
    if (s.rigaCambiata) return 'eseguita';
    return s.faseRichiesta;
}

/** Oltre questo tempo senza un esito finale dalla coda, l'esito e' IGNOTO
 *  (servizio spento o fermo): lo si dice, non si aspetta per sempre. */
export const SCADENZA_ESITO_MS = 180_000;

/** Va riletta la coda del bot? Solo se aperta, con un id, e non scaduta. */
export function richiestaDaRileggere(s: StatoChiusuraRiga, nowMs: number): boolean {
    return !s.richiestaChiusa && s.requestId != null && nowMs - s.inviataMs < SCADENZA_ESITO_MS;
}

/** Lo stato con la scadenza applicata (derivato, mai scritto). */
export function statoConScadenza(s: StatoChiusuraRiga, nowMs: number): StatoChiusuraRiga {
    if (s.richiestaChiusa || s.rigaCambiata || nowMs - s.inviataMs < SCADENZA_ESITO_MS) return s;
    return {
        ...s, faseRichiesta: 'ignota', richiestaChiusa: true,
        motivo: 'nessun esito dal bot da 3 minuti: il servizio e\' acceso? Controlla la riga prima di riprovare',
    };
}

/** Un clic in corso (il bottone si spegne e lo dice). */
export function inCorso(s: StatoChiusuraRiga | null | undefined): boolean {
    if (!s) return false;
    const f = faseMostrata(s);
    return f === 'inviata' || f === 'presa_in_carico';
}

/** Firma della riga al momento del clic: se cambia, la chiusura e' a mercato. */
export function firmaRiga(stato: string, nChiusure: number): string {
    return `${String(stato ?? '').toLowerCase()}|${nChiusure}`;
}

/** La riga e' cambiata DOPO il clic nel senso di una chiusura? */
export function cambiataPerChiusura(firmaAlClic: string, stato: string, nChiusure: number): boolean {
    const [statoPrima, nPrima] = firmaAlClic.split('|');
    const s = String(stato ?? '').toLowerCase();
    if (nChiusure > Number(nPrima)) return true;
    if (s !== statoPrima && (s === 'hedged' || isSettled(s))) return true;
    return false;
}

export const TESTO_FASE: Record<FaseChiusura, string> = {
    inviata: 'richiesta inviata',
    presa_in_carico: 'presa in carico',
    eseguita: 'eseguita',
    rifiutata: 'rifiutata',
    ignota: 'esito ignoto',
};
