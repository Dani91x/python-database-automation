// ============================================================================
// tennisAuto.ts — AUTO-MODE DEI 4 BOT TENNIS, IN PAROLE (25/09).
//
// «I bot tennis non partono anche se li attivo, e ricevo un messaggio in UI»
// (utente, 25/09). Il messaggio era «acceso ma non apre: acceso, ma nessun
// evento tennis seguito»: il ponte armava solo le partite seguite a mano.
// Da oggi il ponte (`Betfair/stream/tennis_live/tennis_bot_service.py`) arma
// anche le partite del FEED UNICO e scrive in `stats.auto` QUELLO CHE HA FATTO
// (fatti, non parole): qui si traducono in una frase, senza dedurre niente.
//
// Regola: mai una frase che dica «parte» quando non è partito. «Armato» vuol
// dire che la riga per partita esiste (anche se il runner la sta ancora
// agganciando: allora lo si dice, «in attesa del runner»).
//
// Funzioni PURE (niente React, niente I/O): collaudate da `tennisAuto.test.ts`.
// ============================================================================

/** `stats.auto` di `tennis_bot_service_control`, chiave per chiave. */
export interface AutoTennis {
    attivo: boolean;
    tetto: number;
    armateFeed: number;
    armateAMano: number;
    seguiteAMano: number;
    inAttesa: number;
    feedLetto: boolean;
    feedVivo: boolean;
    feedPartite: number;
    feedEtaS: number | null;
    fonte: string | null;
    origineOk: boolean;
    liveInDryRun: boolean;
    /** null = colonna assente (migrazione non applicata): nessun interruttore */
    usciteAutomatiche: boolean | null;
    usciteSempreAutomatiche: boolean;
    posizioniAperteManuali: number;
    posizioneApertaDal: string | null;
    lettoAt: string | null;
}

const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null;
const txt = (v: unknown): string | null =>
    typeof v === 'string' && v.trim() ? v.trim() : null;

/** Da `stats` (riga di control) all'auto-mode. `null` = il servizio non l'ha
 *  scritto (bot spento o ponte di prima del 25/09): la pagina non inventa. */
export function leggiAutoTennis(stats: Record<string, unknown> | null | undefined): AutoTennis | null {
    const a = stats?.auto;
    if (a == null || typeof a !== 'object' || Array.isArray(a)) return null;
    const o = a as Record<string, unknown>;
    const u = o.uscite_automatiche;
    return {
        attivo: o.attivo === true,
        tetto: num(o.tetto) ?? 0,
        armateFeed: num(o.armate_feed) ?? 0,
        armateAMano: num(o.armate_a_mano) ?? 0,
        seguiteAMano: num(o.seguite_a_mano) ?? 0,
        inAttesa: num(o.in_attesa) ?? 0,
        feedLetto: o.feed_letto === true,
        feedVivo: o.feed_vivo === true,
        feedPartite: num(o.feed_partite) ?? 0,
        feedEtaS: num(o.feed_eta_s),
        fonte: txt(o.fonte),
        origineOk: o.origine_ok === true,
        liveInDryRun: o.live_in_dry_run === true,
        usciteAutomatiche: typeof u === 'boolean' ? u : null,
        usciteSempreAutomatiche: o.uscite_sempre_automatiche === true,
        posizioniAperteManuali: num(o.posizioni_aperte_manuali) ?? 0,
        posizioneApertaDal: txt(o.posizione_aperta_dal),
        lettoAt: txt(o.letto_at),
    };
}

function secondi(s: number): string {
    const n = Math.max(0, Math.round(s));
    return n < 60 ? `${n} s` : `${Math.floor(n / 60)} min`;
}

/**
 * La frase della riga del bot: su quante partite è armato, da dove, e com'è il
 * feed (con fonte ed età). Il PERCHÉ di un blocco non sta qui: lo dichiara il
 * servizio in `motivo_blocco` e la plancia lo mostra già in arancione.
 */
export function notaAutoTennis(a: AutoTennis | null): string | null {
    if (a == null) return null;
    const parti: string[] = [];
    parti.push(`armato su ${a.armateFeed} partite dal feed (${a.armateAMano} seguite a mano)`);
    if (a.inAttesa > 0) parti.push(`${a.inAttesa} in attesa del runner`);
    if (!a.origineOk) {
        parti.push('auto-mode spento: migrazione non applicata');
    } else if (!a.attivo) {
        parti.push('auto-mode spento (tetto 0)');
    } else {
        parti.push(`tetto ${a.tetto}`);
    }
    const fonte = a.fonte ?? 'feed';
    if (!a.feedLetto) {
        parti.push(`feed tennis non letto (${fonte})`);
    } else if (!a.feedVivo) {
        parti.push(a.feedEtaS == null
            ? `feed tennis fermo: scanner mai visto (${fonte})`
            : `feed tennis fermo: scanner muto da ${secondi(a.feedEtaS)} (${fonte})`);
    } else {
        parti.push(`feed tennis: ${a.feedPartite} partite, scanner ${a.feedEtaS == null ? '?' : secondi(a.feedEtaS)} fa (${fonte})`);
    }
    if (a.liveInDryRun) {
        parti.push('LIVE: le partite nascono in dry-run, nessun ordine reale finché non lo togli per partita');
    }
    return parti.join(' · ');
}

/**
 * L'AVVISO PERMANENTE delle uscite manuali. `null` = uscite automatiche (o
 * non dichiarate): niente da dire. Con uscite manuali si dice SEMPRE, anche a
 * posizione chiusa: il bot non prenderà profitto da solo.
 */
export function avvisoUsciteManuali(a: AutoTennis | null, nowMs: number): string | null {
    if (a == null || a.usciteAutomatiche !== false || a.usciteSempreAutomatiche) return null;
    if (a.posizioniAperteManuali <= 0 || a.posizioneApertaDal == null) {
        return 'uscite manuali: il bot non prende profitto da solo (stop e protezioni restano attivi)';
    }
    const t = Date.parse(a.posizioneApertaDal);
    const da = Number.isFinite(t) ? secondi((nowMs - t) / 1000) : '?';
    const quante = a.posizioniAperteManuali === 1 ? '' : ` (${a.posizioniAperteManuali} posizioni)`;
    return `uscite manuali: posizione aperta da ${da}${quante} — chiudi con «Chiudi» dalla scheda partita`;
}
