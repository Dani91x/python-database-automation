// ============================================================================
// avvisiBanco — l'ONESTA' del clic e dei parametri (07/10 sera, punto 5).
// Caso vero dell'utente: aveva chiesto «accendi dal cursore», l'esito diceva
// «acceso dall'inizio della registrazione» e non si capiva perche' (worker del
// Backtest col codice vecchio: l'app non era stata riavviata). Qui si confronta
// cio' che la pagina ha MANDATO con cio' che il banco ha RICEVUTO e con cio'
// che il BOT ha avuto, e si dice chiaramente cosa non torna. PURA.
// ============================================================================
import type { EsitoBot, OpzioniApplica, ValoreParametro } from '@/lib/replayBot';
import { testoIstante } from '@/lib/applicaBot';

export interface AvvisoBanco {
    grave: boolean;
    testo: string;
}

const RIAVVIA = 'riavvia l’app: il worker del Backtest gira col codice vecchio';

function uguale(a: ValoreParametro | undefined, b: ValoreParametro | undefined): boolean {
    if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-9;
    return a === b;
}

/** Gli avvisi su un esito, dato cio' che la pagina aveva mandato
 *  (`inviato` null = non si sa: nessun avviso sul confronto). PURA. */
export function avvisiBanco(esito: EsitoBot, inviato: OpzioniApplica | null | undefined): AvvisoBanco[] {
    const out: AvvisoBanco[] = [];
    const vecchio = esito.versione == null;
    if (vecchio) {
        out.push({ grave: true, testo: `Questo esito viene da un banco col codice VECCHIO (manca la versione dell’esito): ${RIAVVIA}. Registro, ladder e P&L restano parziali.` });
    }
    if (!inviato) return out;
    if (inviato.dal_ms != null) {
        if (esito.dal_ms == null || (esito.richiesta && esito.richiesta.dal_ms == null)) {
            out.push({ grave: true, testo: `Il banco NON ha ricevuto l’accensione dal cursore (chiesta alle ${testoIstante(inviato.dal_ms)}): il bot è stato acceso dall’inizio della registrazione. ${RIAVVIA}.` });
        } else if (esito.dal_ms !== Math.round(inviato.dal_ms)) {
            out.push({ grave: true, testo: `Il banco ha ricevuto un’accensione DIVERSA da quella chiesta (${testoIstante(inviato.dal_ms)} chiesta, ${testoIstante(esito.dal_ms)} ricevuta).` });
        } else if (esito.conferme && esito.conferme.dal_ms === false) {
            out.push({ grave: true, testo: `Il banco ha ricevuto l’accensione delle ${testoIstante(inviato.dal_ms)} ma il BOT non risulta acceso a quell’istante (nessuna riga di accensione nel referto).` });
        }
    }
    const chiesti = (inviato.clic_ms ?? []).map(Math.round);
    if (chiesti.length > 0) {
        const ricevuti = new Set((esito.clic_ms ?? []).map(Math.round));
        const persi = chiesti.filter(c => !ricevuti.has(c));
        if (persi.length > 0) {
            out.push({ grave: true, testo: `Il banco NON ha ricevuto ${persi.length === 1 ? 'il clic' : `${persi.length} clic`} «Attiva adesso» delle ${persi.map(testoIstante).join(', ')}. ${vecchio ? RIAVVIA : 'Rilancia la prova.'}` });
        }
        const nonEseguiti = (esito.conferme?.clic_ms ?? []).filter(c => !c.ricevuto && ricevuti.has(c.ms));
        if (nonEseguiti.length > 0) {
            out.push({ grave: true, testo: `${nonEseguiti.length === 1 ? 'Un clic ricevuto dal banco non è stato mandato' : `${nonEseguiti.length} clic ricevuti dal banco non sono stati mandati`} alla sessione del bot (${nonEseguiti.map(c => testoIstante(c.ms)).join(', ')}): istante fuori dalla registrazione o dopo la fine della sessione.` });
        }
    }
    const param = inviato.parametri ?? {};
    const usati = esito.parametri_usati;
    for (const [k, v] of Object.entries(param)) {
        if (!usati) {
            out.push({ grave: true, testo: `Il banco non dichiara i parametri usati: non si può verificare ${k} = ${String(v)}. ${RIAVVIA}.` });
            break;
        }
        if (!uguale(usati[k], v)) {
            out.push({ grave: true, testo: `Parametro ${k}: chiesto ${String(v)}, il banco ha usato ${usati[k] === undefined ? 'il valore di serie (non l’ha ricevuto)' : String(usati[k])}.` });
        }
    }
    return out;
}

/** La conferma positiva (cosa il banco ha ricevuto), per il trader. PURA. */
export function confermaBanco(esito: EsitoBot): string | null {
    if (esito.versione == null) return null;
    const pezzi: string[] = [];
    if (esito.dal_ms != null) pezzi.push(`acceso alle ${testoIstante(esito.dal_ms)}${esito.conferme?.dal_ms ? ' (confermato dal bot)' : ''}`);
    const n = esito.clic_ms?.length ?? 0;
    if (n > 0) {
        const letti = (esito.clic_bot ?? []).filter(c => c.letto_ms != null).length;
        pezzi.push(`${n} clic «Attiva adesso» ricevuti${esito.clic_bot ? ` (${letti} letti dalla sessione del bot)` : ''}`);
    }
    const cambiati = Object.keys(esito.parametri_cambiati ?? {}).length;
    if (cambiati > 0) pezzi.push(`${cambiati} parametri cambiati applicati`);
    return pezzi.length ? `Il banco ha ricevuto: ${pezzi.join(' · ')}` : null;
}
