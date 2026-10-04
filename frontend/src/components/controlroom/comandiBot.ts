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
// del modello per strategia (tennis acceso A 3 EURO), non un percorso a parte.
//
// ⚠️ 28/09 — «acceso, le altre tre spente» non vale piu': accendere il tennis
// da questa scheda AGGIUNGE il tennis alle accensioni correnti, senza toccare
// base/esatto/punta gia' accese (vedi il commento su `soloTennis`, sotto).
// ============================================================================
import {
    creaInterruttori, interruttoreDi, accensioniCorrenti, assicuraSoldiVeriServiti,
    type ComandiInterruttori, type InterruttoreId, type Modalita,
    type SorgenteInterruttori, type StatoServizio, type Accensioni,
} from '@/lib/interruttori';
import { extraSoloTennis } from '@/components/controlroom/soloTennis';
import { fetchSafeState } from '@/lib/safeBot';

// ============================================================================
// REPERTO A (18/09) — LA RILETTURA FRESCA DI SAFE PER LA CONTROL ROOM.
//
// `interruttori.ts` sa comporre una scrittura da uno stato fresco quando il
// chiamante gliene passa uno (`SorgenteInterruttori.rileggiSafe`), ma non sa
// COME leggerlo: quello e' un dettaglio di CHI usa i comandi. Qui, per la
// Control Room, "fresco" vuol dire "dal database", non da `vm.bots` (che il
// refetch di pagina aggiorna in modo fire-and-forget — il cuore del reperto:
// due comandi ravvicinati su righe DIVERSE di Safe leggevano lo stesso
// `vm.bots` vecchio, e il secondo dimenticava l'effetto del primo).
//
// Non e' un refetch atteso: e' UNA LETTURA IN PIU', fatta apposta al momento
// di scrivere. Il secondo click legge quello che il primo ha appena scritto
// sul database (la RPC del primo click e' gia' tornata quando parte questo
// comando, essendo i due comandi sequenziali sulla stessa riga del pannello),
// non quello che React non ha ancora ricevuto.
// ============================================================================
async function rileggiSafeDalDatabase(): Promise<{
    params: Record<string, unknown> | null;
    servizio: StatoServizio | null;
}> {
    const stato = await fetchSafeState();
    const c = stato.control;
    if (c == null) return { params: null, servizio: null };
    const params = (c.params ?? null) as Record<string, unknown> | null;
    const varianti = Array.isArray(params?.variants)
        ? (params!.variants as unknown[]).map(String) : null;
    const modiRaw = params?.strategy_modes;
    const modiStrategia = (modiRaw != null && typeof modiRaw === 'object' && !Array.isArray(modiRaw))
        ? Object.fromEntries(
            Object.entries(modiRaw as Record<string, unknown>).map(
                ([k, v]) => [k, String(v ?? '').toLowerCase() === 'live' ? 'live' as const : 'paper' as const],
            ),
        )
        : null;
    return {
        params,
        servizio: {
            inCorsa: String(c.status ?? '').toLowerCase() === 'running',
            modalita: c.mode === 'live' || c.mode === 'paper' ? c.mode : null,
            varianti, modiStrategia,
        },
    };
}

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
 * soldi veri) vuol dire «aggiungi il tennis alle strategie gia' accese», con
 * lo stake a 3,00 €. Spegnere una variante e' sempre un gesto esplicito (il
 * pulsante «spegni» di quella riga): il tennis non lo fa per nessuno.
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
    // ⚠️ REPERTO A — si aggancia la rilettura FRESCA di Safe dal database,
    // a meno che il chiamante non ne abbia gia' fornita una sua (le pagine
    // dei singoli bot passano `sorgente` diretto a `creaInterruttori`, non da
    // qui: per loro questo ramo non e' mai attraversato).
    const sorgenteConRilettura: SorgenteInterruttori = {
        ...sorgente,
        rileggiSafe: sorgente.rileggiSafe ?? rileggiSafeDalDatabase,
    };
    const base = creaInterruttori(sorgenteConRilettura, dopo);
    if (sport !== 'tennis') return base;

    /**
     * 28/09 — AGGIUNGE il tennis alle accensioni CORRENTI di Safe: non spegne
     * piu' base/esatto/punta gia' accese (reperto CRONOSTORIA 26/09, h11:25:
     * «avvia in prova» dalla scheda tennis con Safe calcio gia' acceso
     * riscriveva `variants=["tennis"]` e spegneva il calcio per 3 minuti).
     * Ordine dell'utente: calcio e tennis sono distinti, i bot li accende e
     * li spegne SOLO lui — spegnere una variante resta un gesto esplicito
     * (il pulsante «spegni» di quella riga, non un effetto collaterale
     * dell'accensione del tennis). `puoAccendere`: solo il gesto di
     * ACCENSIONE puo' portare il servizio da fermo a in corsa; un cambio di
     * modalita' non accende mai niente.
     *
     * ⚠️ Fino al 28/09 questo gesto era SOSTITUTIVO (`accensioniSoloTennis`):
     * spegneva sempre base/esatto/punta, per un ordine del 15/09 («deve
     * partire solo lui, come ieri»). I due ordini si contraddicono: questa
     * correzione applica il piu' recente (28/09, Cantiere G). Vedi il
     * referto per la decisione da riconfermare con l'utente.
     */
    const soloTennis = async (modalita: Modalita, puoAccendere: boolean) => {
        // 04/10: «soldi veri» sul tennis solo se il runner tennis li sa servire
        await assicuraSoldiVeriServiti(sorgenteConRilettura, interruttoreDi('safe-tennis'), modalita);
        const fresco = await sorgenteConRilettura.rileggiSafe!();
        const acc: Accensioni = { ...accensioniCorrenti(fresco.servizio), tennis: modalita };
        return base.scriviAccensioni(acc, { altre: 'prova', extra: extraSoloTennis, puoAccendere });
    };

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
