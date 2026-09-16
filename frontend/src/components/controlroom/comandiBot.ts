// ============================================================================
// comandiBot.ts — I COMANDI DELLA CONTROL ROOM.
//
// ⚠️ 16/09 — QUI NON C'E' PIU' NESSUNA IMPLEMENTAZIONE.
//
// I comandi che accendono, spengono e riconfigurano i bot vivono in
// `@/lib/interruttori`, perche' le PAGINE DEI SINGOLI BOT devono poter fare
// gli stessi gesti con lo stesso codice: «devo poter attivare e spegnere
// tutto dalla UI, sia paper che live, sia dalle singole schede che dalla
// Control Room» (utente, 16/09). Due implementazioni dello stesso
// interruttore sono due verita', e divergono sempre.
//
// Quello che resta qui e' l'unica cosa che e' davvero DELLA CONTROL ROOM: la
// scheda tennis, dove «avvia» ha un significato in piu' che l'utente ha
// chiesto per nome il 15/09 — «deve partire solo lui, come ieri, a 3 euro».
// Anche quello, pero', passa dalle funzioni condivise: e' un caso particolare
// del modello per strategia (tennis acceso, le altre tre spente), non un
// percorso a parte.
// ============================================================================
import {
    creaInterruttori, interruttoreDi,
    type ComandiInterruttori, type InterruttoreId, type Modalita,
    type SorgenteInterruttori,
} from '@/lib/interruttori';
import {
    accensioniSoloTennis, extraSoloTennis,
} from '@/components/controlroom/soloTennis';

export {
    INTERRUTTORI, interruttoriDiSport, interruttoreDi, statoInterruttore,
    importoDi, importiInterruttori, leggiChiave, scriviChiave,
    paramsAccensioni, accensioniCorrenti, modalitaServizio, nessunaAccesa,
    creaInterruttori,
    ObiettivoOmegaIgnoto, ParametriOmegaIgnoti, ParametriNonLetti,
} from '@/lib/interruttori';
export type {
    Interruttore, InterruttoreId, Modalita, SportBot, StrategiaSafe,
    Accensioni, CampoImporto, ComandiInterruttori, SorgenteInterruttori,
    StatoServizio, StatoInterruttore,
} from '@/lib/interruttori';

/**
 * I comandi della Control Room. `sport` cambia UNA cosa sola, e la cambia in
 * modo dichiarato: nella scheda tennis accendere `safe-tennis` (o portarlo a
 * soldi veri) vuol dire «accendi il tennis e spegni il resto», con lo stake a
 * 3,00 € e le entrate automatiche accese.
 *
 * PERCHE' NON UN FLAG DENTRO `creaInterruttori`: qui cambia il SIGNIFICATO del
 * pulsante, non un dettaglio. Due significati nello stesso nome, distinti da
 * un flag, si confondono alla prima lettura distratta — e questo e' il punto
 * della pagina dove confondersi costa denaro. Il pannello lo scrive PRIMA del
 * clic (`differenzeSoloTennis`).
 */
export function creaComandiControlRoom(
    sorgente: SorgenteInterruttori, dopo: () => void, sport?: string | null,
): ComandiInterruttori {
    const base = creaInterruttori(sorgente, dopo);
    if (sport !== 'tennis') return base;

    /** `puoAccendere`: solo il gesto di ACCENSIONE puo' portare il servizio da
     *  fermo a in corsa. Un cambio di modalita' non accende mai niente. */
    const soloTennis = (modalita: Modalita, puoAccendere: boolean) =>
        base.scriviAccensioni(accensioniSoloTennis(modalita), {
            altre: 'prova', extra: extraSoloTennis, puoAccendere,
        });

    return {
        ...base,
        accendi: async (id: InterruttoreId, modalita: Modalita) => {
            if (interruttoreDi(id).strategia !== 'tennis') return base.accendi(id, modalita);
            await soloTennis(modalita, true);
        },
        cambiaModalita: async (id: InterruttoreId, modalita: Modalita) => {
            if (interruttoreDi(id).strategia !== 'tennis') return base.cambiaModalita(id, modalita);
            // ⚠️ REVIEW 15/09 — «PASSA A PROVA» NON CONFIGURA NIENTE.
            // E' un gesto di de-escalation: portava con se' lo stake a 3 e
            // ACCENDEVA le entrate automatiche, che l'operatore puo' avere
            // spento apposta. Si cambia solo la modalita' del tennis.
            if (modalita === 'live') return soloTennis('live', false);
            await base.cambiaModalita(id, 'paper');
        },
    };
}
