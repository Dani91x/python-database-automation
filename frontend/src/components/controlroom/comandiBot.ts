// ============================================================================
// comandiBot.ts — I COMANDI DEI TRE BOT, in un posto solo.
//
// «Devo poter fermare uno o tutti i bot come e quando voglio» e «attivare e
// modificare i parametri di ciascun bot (live o paper) e gli importi con cui
// devono operare» (utente, 14/09).
//
// PERCHÉ UN FILE A PARTE, e non dentro il componente: qui c'è la parte che
// tocca i SOLDI VERI, ed è l'unica di questa pagina che può accendere un bot
// in live. Deve stare dove si può collaudare senza montare React.
//
// TRE COSE CHE NON SI FANNO QUI:
//  1. **Non si inventa un parametro.** Ogni chiave scritta è una chiave che il
//     servizio legge davvero: `stake.backSize` e `stake.laySize` per Safe,
//     `stake` per Mike, `min_stake` per Omega. Un nome sbagliato non dà
//     errore: si salva, non ha effetto, e il trader crede di aver cambiato
//     l'importo mentre il bot continua col vecchio.
//  2. **Non si perde quello che non si tocca.** `X_update_params` riceve
//     l'oggetto intero, quindi si parte SEMPRE dai parametri correnti e si
//     cambia una chiave sola. Mandare `{stake: 3}` e basta azzererebbe tutto
//     il resto.
//  3. **Non si indovina la modalità.** Avviare vuole un `mode` esplicito.
// ============================================================================
import { activateOmega, stopOmega, updateOmegaParams, type OmegaParams } from '@/lib/omega';
import { activateSafe, stopSafe, updateSafeParams, type SafeBotParams } from '@/lib/safeBot';
import { activateMike, stopMike, updateMikeParams, type MikeParams } from '@/lib/mike';
import type { Bot } from '@/lib/controlRoom';
import type { CampoImporto, Modalita } from '@/components/controlroom/PannelloBot';

/** Le chiavi d'importo che ciascun servizio legge DAVVERO, con le sue parole. */
export const IMPORTI_DI: Record<Bot, readonly { chiave: string; etichetta: string; nota?: string }[]> = {
    // Safe ne ha due: chi punta usa backSize, chi banca usa laySize
    // (`safeBot.ts`: «backSize entra su TENNIS e PUNTA, laySize su BASE ed ESATTO»).
    safe: [
        { chiave: 'stake.backSize', etichetta: 'punta' },
        { chiave: 'stake.laySize', etichetta: 'banca' },
    ],
    mike: [
        { chiave: 'stake', etichetta: 'stake Under 3.5' },
    ],
    // ⚠️ `min_stake` è un MINIMO, non l'importo di lavoro: Omega dimensiona
    // dall'obiettivo di giornata. Chiamarlo «importo» sarebbe falso.
    omega: [
        {
            chiave: 'min_stake', etichetta: 'stake minimo',
            nota: 'è un minimo, non l’importo di lavoro: Omega dimensiona dall’obiettivo',
        },
    ],
};

/** Legge una chiave anche annidata ('stake.backSize') senza esplodere. */
export function leggiChiave(params: Record<string, unknown> | null | undefined, chiave: string): number | null {
    let nodo: unknown = params ?? null;
    for (const passo of chiave.split('.')) {
        if (nodo == null || typeof nodo !== 'object') return null;
        nodo = (nodo as Record<string, unknown>)[passo];
    }
    return typeof nodo === 'number' && Number.isFinite(nodo) ? nodo : null;
}

/**
 * Scrive una chiave anche annidata, **senza toccare il resto**.
 * Ritorna una copia: i parametri correnti non si mutano mai sul posto, o due
 * salvataggi in fila partirebbero da uno stato già sporcato dal primo.
 */
export function scriviChiave(
    params: Record<string, unknown> | null | undefined,
    chiave: string, valore: number,
): Record<string, unknown> {
    const radice: Record<string, unknown> = { ...(params ?? {}) };
    const passi = chiave.split('.');
    let nodo = radice;
    for (let i = 0; i < passi.length - 1; i += 1) {
        const k = passi[i];
        const dentro = nodo[k];
        nodo[k] = (dentro != null && typeof dentro === 'object') ? { ...(dentro as object) } : {};
        nodo = nodo[k] as Record<string, unknown>;
    }
    nodo[passi[passi.length - 1]] = valore;
    return radice;
}

/** Gli importi di un bot, pronti per il pannello. */
export function importiDi(bot: Bot, params: Record<string, unknown> | null): CampoImporto[] {
    return IMPORTI_DI[bot].map((c) => ({ ...c, valore: leggiChiave(params, c.chiave) }));
}

export interface SorgenteParametri {
    /** i parametri correnti di quel bot, dalla riga di control */
    params: (bot: Bot) => Record<string, unknown> | null;
    /** solo Omega: l'obiettivo del giorno vive fuori da `params` e
     *  `omega_activate` lo pretende */
    obiettivoOmega: () => number | null;
}

/**
 * L'obiettivo con cui riaccendere Omega quando non ne conosciamo uno.
 * NON è un default di comodo: `omega_activate` richiede un numero, e passare
 * 0 spegnerebbe di fatto il dimensionamento. Se non sappiamo l'obiettivo
 * corrente, meglio rifiutarsi che indovinarlo.
 */
export class ObiettivoOmegaIgnoto extends Error {
    constructor() {
        super('non conosco l’obiettivo di giornata di Omega: aprilo dalla sua pagina e riprova');
        this.name = 'ObiettivoOmegaIgnoto';
    }
}

/**
 * ⚠️ REVIEW 14/09 — `omega_activate` NON e' come le altre due.
 *
 *   safe_activate  → params = coalesce(p_params, params)      conserva
 *   mike_activate  → params = coalesce(p_params, params)      conserva
 *   omega_activate → params = coalesce(p_params, '{}'::jsonb) SOVRASCRIVE SEMPRE
 *
 * `{}` non e' NULL: passarlo AZZERA la colonna. E i tetti di rischio di Omega
 * nascono a ZERO, che nel suo codice significa TETTO SPENTO:
 *   · `max_liability_per_match` → `apply_liability_cap`: `if not cap or cap <= 0: return size`
 *   · `max_open_liability`      → `omega_service.py:1201`: controllo saltato
 *   · `daily_loss_cap`          → `omega_service.py:963`: lo stop perdite non scatta MAI
 *
 * Avviare Omega con `{}` gli toglieva tutti e tre i freni, in live, in
 * silenzio. Quindi: si riavvia con i parametri CORRENTI, e se non li
 * conosciamo non si avvia affatto. Fail-closed: meglio un bot che non parte
 * di un bot che parte senza freni.
 */
export class ParametriOmegaIgnoti extends Error {
    constructor() {
        super('non conosco i parametri di Omega: avviarlo adesso azzererebbe i suoi '
            + 'tetti di rischio (perdita giornaliera, responsabilità aperta, per partita). '
            + 'Apri la pagina di Omega, controlla i parametri, e riprova.');
        this.name = 'ParametriOmegaIgnoti';
    }
}

/**
 * ⚠️ REVIEW 14/09, CRITICO — SCRIVERE SENZA AVER LETTO CANCELLA.
 *
 * Tutte e tre le RPC di aggiornamento fanno `coalesce(p_params, params)`:
 * conservano solo se ricevono NULL. Un oggetto — anche minuscolo — SOSTITUISCE
 * l'intera colonna. E `scriviChiave(null, 'stake', 3)` produce `{stake: 3}`,
 * che non è NULL.
 *
 * `correnti` è `null` ogni volta che la lettura di stato non è ancora tornata
 * o è FALLITA (il 13/09 il DB ha risposto 503 per budget IO): la pagina resta
 * interattiva e il campo importo invita a salvare proprio in quel momento.
 *
 * Su Safe si perderebbero `strategy_modes` e `tennis_exit_approval`, cioè le
 * DUE COSE che oggi tengono i soldi veri sul solo tennis: il calcio
 * erediterebbe la modalità del servizio e le chiusure smetterebbero di
 * passare dall'approvazione. Quindi: se non abbiamo letto, non si scrive.
 */
export class ParametriNonLetti extends Error {
    constructor(bot: Bot) {
        super(`non ho ancora letto i parametri di ${bot}: salvare adesso `
            + 'sostituirebbe TUTTI gli altri (modalità per strategia, uscite, '
            + 'tetti di rischio) con i valori predefiniti. Attendi che lo stato '
            + 'sia caricato, o ricarica la pagina.');
        this.name = 'ParametriNonLetti';
    }
}

/**
 * Costruisce i comandi. `dopo` viene chiamato a ogni cambiamento riuscito,
 * perché la pagina deve rileggere lo stato dal SERVIZIO invece di fidarsi di
 * quello che credeva di aver appena fatto.
 */
export function creaComandi(sorgente: SorgenteParametri, dopo: () => void) {
    const avvia = async (bot: Bot, modalita: Modalita) => {
        if (bot === 'safe') await activateSafe(modalita);
        else if (bot === 'mike') await activateMike(modalita);
        else {
            const obiettivo = sorgente.obiettivoOmega();
            if (obiettivo == null) throw new ObiettivoOmegaIgnoto();
            // i parametri CORRENTI, mai un oggetto vuoto: vedi ParametriOmegaIgnoti
            const correnti = sorgente.params('omega');
            if (correnti == null || Object.keys(correnti).length === 0) {
                throw new ParametriOmegaIgnoti();
            }
            await activateOmega(modalita, obiettivo, correnti as Partial<OmegaParams>);
        }
        dopo();
    };

    const ferma = async (bot: Bot) => {
        if (bot === 'safe') await stopSafe();
        else if (bot === 'mike') await stopMike();
        else await stopOmega();
        dopo();
    };

    const cambiaModalita = async (bot: Bot, modalita: Modalita) => {
        // `update_params` di Omega e Mike accetta il mode; Safe no, e la sua
        // modalità si cambia riattivandolo — che è esattamente quello che fa
        // la sua pagina, non una scorciatoia inventata qui.
        if (bot === 'omega') await updateOmegaParams({ mode: modalita });
        else if (bot === 'mike') {
            // `mike_update_params` riceve i parametri INTERI: se non li
            // abbiamo letti, cambiare modalità gli porterebbe via tutto.
            const correnti = sorgente.params('mike');
            if (correnti == null || Object.keys(correnti).length === 0) {
                throw new ParametriNonLetti('mike');
            }
            await updateMikeParams(correnti as MikeParams, modalita);
        }
        else await activateSafe(modalita);
        dopo();
    };

    const cambiaImporto = async (bot: Bot, chiave: string, importo: number) => {
        // si riparte SEMPRE dai parametri correnti: mandare la sola chiave
        // cambiata cancellerebbe tutto il resto.
        const correnti = sorgente.params(bot);
        // ...e se non li abbiamo letti NON si scrive: vedi ParametriNonLetti.
        if (correnti == null || Object.keys(correnti).length === 0) {
            throw new ParametriNonLetti(bot);
        }
        const nuovi = scriviChiave(correnti, chiave, importo);
        if (bot === 'safe') await updateSafeParams(nuovi as Partial<SafeBotParams>);
        else if (bot === 'mike') await updateMikeParams(nuovi as MikeParams);
        else await updateOmegaParams({ params: nuovi as Partial<OmegaParams> });
        dopo();
    };

    return { avvia, ferma, cambiaModalita, cambiaImporto };
}
