// ============================================================================
// trovaEsitoUscita.ts — IL PONTE fra una proposta di uscita e la STRISCIA DI
// ESITO (raccordo, 18/09/2026).
//
// `StrisciaEsitoChiusura` vuole `{apertura, chiusure, modo}` nella forma di
// `certezzaChiusura()`. Il nastro delle uscite (`UsciteColonna.tsx`) ha solo
// bot + `trade_id` della proposta: questo file, PURO, cerca l'apertura vera
// dentro `vm.operazioni` (le righe che il raccordo porta già con
// `ordine`/`chiusureOrdini`, v. `useControlRoom.ts` `OperazionePartita`) e
// restituisce `undefined` se non la trova — in quel caso il chiamante non
// passa `esito` e la scheda resta BYTE-IDENTICA a prima.
//
// CHIAVE COMPOSTA bot+id: gli id di tabelle diverse (Safe/Omega/Mike/tennis)
// possono collidere, un solo `id` non basta.
//
// PAPER E LIVE MAI MISCHIATI: il `modo` non è quello dichiarato dalla
// proposta ma quello VERO della riga trovata (`OperazionePartita.modalita`);
// se manca, si rifiuta (nessun `esito`) invece di indovinare paper o live.
// ============================================================================
import { statoOrdine } from '@/lib/statoOrdine';
import type { Bot } from '@/lib/controlRoom';
import type { StrisciaEsitoChiusuraProps } from './StrisciaEsitoChiusura';
import type { OperazionePartita } from './useControlRoom';

/**
 * Cerca l'apertura di `bot`+`tradeId` fra le operazioni GIÀ CARICATE di UNA
 * partita (`vm.operazioni.get(eventId)`) e, se la trova, prepara la prop
 * `esito` per `StrisciaEsitoChiusura`. `undefined` = non trovata: nessuna
 * striscia, nessuna modifica visibile alla scheda.
 */
export function trovaEsitoUscita(
    operazioniPartita: readonly OperazionePartita[] | undefined,
    bot: Bot,
    tradeId: number,
): StrisciaEsitoChiusuraProps | undefined {
    if (!operazioniPartita) return undefined;
    const riga = operazioniPartita.find((o) => o.bot === bot && o.id === tradeId);
    if (!riga || !riga.modalita || !riga.ordine) return undefined;
    // difensivo: alcune righe (finte di test con cast, o bot che non
    // pubblicano ancora la catena di chiusura) possono arrivare senza
    // `chiusureOrdini` a runtime nonostante il tipo lo dichiari sempre
    // presente — `[]` equivale a «nessuna gamba», mai un'eccezione.
    const chiusure = riga.chiusureOrdini ?? [];

    const regolataDalMercato = statoOrdine(riga.ordine).esito === 'regolato'
        && chiusure.every((c) => statoOrdine(c).esito === 'regolato');

    return {
        apertura: riga.ordine,
        chiusure,
        regolataDalMercato,
        modo: riga.modalita,
    };
}

/** timestamp più recente disponibile per giudicare «la gamba più recente»:
 *  l'ultima notizia DA BETFAIR sulla chiusura, o l'istante dell'operazione
 *  se la chiusura non l'ha ancora scritta. */
function ultimaNotizia(o: OperazionePartita): string {
    const chiusure = o.chiusureOrdini ?? [];
    const ultima = chiusure[chiusure.length - 1];
    return ultima?.betfair_updated_at ?? o.at;
}

/**
 * Per il CASH OUT GLOBALE (`CashOutPartita`): non c'è UN `trade_id`, ce ne
 * sono N. Si segue la gamba con l'attività più recente fra le operazioni di
 * `bot` su questa partita che hanno almeno un tentativo di chiusura —
 * `undefined` se nessuna ce l'ha (nessun cash out in corso: nessuna striscia).
 */
export function trovaEsitoCashOut(
    operazioniPartita: readonly OperazionePartita[] | undefined,
    bot: Bot,
): StrisciaEsitoChiusuraProps | undefined {
    if (!operazioniPartita) return undefined;
    const candidati = operazioniPartita.filter(
        (o) => o.bot === bot && o.modalita && o.ordine && (o.chiusureOrdini ?? []).length > 0,
    );
    if (candidati.length === 0) return undefined;
    candidati.sort((a, b) => (ultimaNotizia(a) < ultimaNotizia(b) ? 1 : -1));
    const riga = candidati[0];
    if (!riga.modalita) return undefined;
    const chiusure = riga.chiusureOrdini ?? [];

    const regolataDalMercato = statoOrdine(riga.ordine).esito === 'regolato'
        && chiusure.every((c) => statoOrdine(c).esito === 'regolato');

    return {
        apertura: riga.ordine,
        chiusure,
        regolataDalMercato,
        modo: riga.modalita,
    };
}

export default trovaEsitoUscita;
