// ============================================================================
// rilettureMirate.ts - 24/09: "righe nuove dei bot in Control Room subito, non
// al poll dei 30 s" (decisione dell'utente).
//
// Il canale di un bot NON aggiunge righe (overlay sul poll, mai unione:
// `righeCanale.ts`). Quando pero' dal canale arriva una riga che la pagina non
// conosce (una posizione NUOVA) o che diventa terminale (una posizione CHIUSA),
// aspettare il giro dei 30 s vuol dire mostrare al trader una posizione 30 s
// dopo che esiste. Qui si chiede SUBITO una rilettura del blocco del database
// di QUEL bot: la riga entra dal database (fonte dichiarata), e da li' in poi
// il canale la aggiorna al ms.
//
// ANTI-TEMPESTA (il 13/09 il database e' caduto per IO): per gruppo (un bot, o
// i 4 bot tennis che hanno UNA lettura sola) al massimo UNA rilettura ogni
// `minimoMs` (2 s). Le richieste che arrivano nel frattempo si COALESCONO in
// una sola rilettura programmata allo scadere dei 2 s: una raffica di 50 righe
// nuove costa al piu' due letture, non cinquanta.
//
// Modulo PURO: nessun import di rete, nessun React. Orologio e timer si
// iniettano (i test li controllano).
// ============================================================================

export const MINIMO_RILETTURA_MS = 2_000;

export interface OrologioRiletture {
    ora: () => number;
    programma: (cb: () => void, ms: number) => unknown;
    annulla: (h: unknown) => void;
}

const OROLOGIO_VERO: OrologioRiletture = {
    ora: () => Date.now(),
    programma: (cb, ms) => setTimeout(cb, ms),
    annulla: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

interface StatoGruppo {
    /** istante dell'ultima rilettura PARTITA */
    ultimaMs: number | null;
    /** rilettura gia' programmata (coalescenza) */
    programmata: unknown;
}

export class RilettureMirate {
    private readonly minimoMs: number;
    private readonly orologio: OrologioRiletture;
    private readonly gruppi = new Map<string, StatoGruppo>();
    private readonly esecutori = new Map<string, () => void>();
    private chiuso = false;
    /** per gruppo: quante riletture sono PARTITE (diagnostica e test) */
    readonly conti = new Map<string, number>();

    constructor(minimoMs: number = MINIMO_RILETTURA_MS, orologio: OrologioRiletture = OROLOGIO_VERO) {
        this.minimoMs = Math.max(0, minimoMs);
        this.orologio = orologio;
    }

    /** Registra (o sostituisce) la lettura di un gruppo. */
    registra(gruppo: string, esegui: () => void): void {
        this.esecutori.set(gruppo, esegui);
    }

    /**
     * Chiede una rilettura del gruppo. Parte SUBITO se l'ultima e' piu'
     * vecchia di `minimoMs`; altrimenti una sola rilettura resta programmata
     * allo scadere del minimo (le richieste successive non ne aggiungono).
     * Ritorna 'subito' | 'programmata' | 'coalescita' | 'ignota'.
     */
    chiedi(gruppo: string): 'subito' | 'programmata' | 'coalescita' | 'ignota' {
        if (this.chiuso || !this.esecutori.has(gruppo)) return 'ignota';
        let st = this.gruppi.get(gruppo);
        if (!st) { st = { ultimaMs: null, programmata: null }; this.gruppi.set(gruppo, st); }
        if (st.programmata != null) return 'coalescita';
        const ora = this.orologio.ora();
        const trascorso = st.ultimaMs == null ? Infinity : ora - st.ultimaMs;
        if (trascorso >= this.minimoMs) {
            this.parti(gruppo, st, ora);
            return 'subito';
        }
        const stato = st;
        stato.programmata = this.orologio.programma(() => {
            stato.programmata = null;
            if (this.chiuso) return;
            this.parti(gruppo, stato, this.orologio.ora());
        }, this.minimoMs - trascorso);
        return 'programmata';
    }

    /** Smonta: nessuna rilettura parte piu' (unmount della pagina). */
    chiudi(): void {
        this.chiuso = true;
        for (const st of this.gruppi.values()) {
            if (st.programmata != null) this.orologio.annulla(st.programmata);
            st.programmata = null;
        }
    }

    private parti(gruppo: string, st: StatoGruppo, ora: number): void {
        st.ultimaMs = ora;
        this.conti.set(gruppo, (this.conti.get(gruppo) ?? 0) + 1);
        const esegui = this.esecutori.get(gruppo);
        try { esegui?.(); } catch { /* la lettura gestisce i suoi errori: il giro dei 30 s riprova */ }
    }
}
