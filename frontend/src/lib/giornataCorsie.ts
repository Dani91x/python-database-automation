// ============================================================================
// giornataCorsie.ts - LE DUE CORSIE DI OGNI SPORT: LIVE (soldi veri) e PROVA.
//
// 30/09 (blocco P2, progetto `AUDIT_2026-09-30/PROGETTO_UI_MONITOR_VERITIERO.md`
// §3): la tessera del calcio diceva «MODALITA' PAPER» guardando SOLO Safe,
// mentre Mike operava con soldi veri sullo stesso sport. Una «modalita' dello
// sport» non esiste: esistono i BOT, ciascuno con la sua `control.mode`.
// Qui si elencano TUTTI i bot di uno sport, ciascuno nella corsia della SUA
// modalita' dichiarata dal servizio; un bot fermo resta elencato (spento),
// una modalita' non dichiarata non vale mai «paper» (fail-closed).
//
// Funzione pura: nessuna lettura, nessun calcolo di soldi.
// ============================================================================
import type { Bot } from '@/lib/controlRoom';

export type SportCorsie = 'calcio' | 'tennis';

/** Il minimo di `StatoBot` (useControlRoom) che serve: stesse chiavi e tipi. */
export interface BotPerCorsie {
    bot: Bot;
    modalita: 'paper' | 'live' | null;
    inCorsa: boolean;
    varianti?: string[] | null;
    modiStrategia?: Record<string, 'paper' | 'live'> | null;
}

/** Una voce della tessera: un bot (o una strategia di Safe). */
export interface VoceCorsia {
    /** chiave stabile (testid): 'omega', 'safe-base', 'mike', 'tennis_pro', ... */
    chiave: string;
    nome: string;
    /** la modalita' DICHIARATA dal servizio; null = non dichiarata */
    modalita: 'paper' | 'live' | null;
    /** true = sta operando; false = fermo/spento; null = riga del bot non letta */
    acceso: boolean | null;
}

export interface CorsieSport {
    /** bot con `mode = live` (accesi o spenti) */
    live: VoceCorsia[];
    /** bot con `mode = paper` (accesi o spenti) */
    prova: VoceCorsia[];
    /** modalita' non dichiarata (o riga non letta): mai contati come prova */
    ignote: VoceCorsia[];
    /** almeno un bot LIVE sta operando: la tessera dichiara «SOLDI VERI» */
    liveAcceso: boolean;
}

/** I bot di ogni sport, nell'ordine della plancia. Safe si divide per strategia. */
const CALCIO: readonly { chiave: string; nome: string; bot: Bot; variante?: string }[] = [
    { chiave: 'omega', nome: 'Omega', bot: 'omega' },
    { chiave: 'safe-base', nome: 'Safe base', bot: 'safe', variante: 'base' },
    { chiave: 'safe-esatto', nome: 'Safe esatto', bot: 'safe', variante: 'esatto' },
    { chiave: 'safe-punta', nome: 'Safe punta', bot: 'safe', variante: 'punta' },
    { chiave: 'mike', nome: 'Mike', bot: 'mike' },
    { chiave: 'scalper', nome: 'Scalper calcio', bot: 'scalper' },
];
const TENNIS: readonly { chiave: string; nome: string; bot: Bot; variante?: string }[] = [
    { chiave: 'safe-tennis', nome: 'Safe tennis', bot: 'safe', variante: 'tennis' },
    { chiave: 'tennis_scalper', nome: 'Scalper', bot: 'tennis_scalper' },
    { chiave: 'tennis_pro', nome: 'Pro', bot: 'tennis_pro' },
    { chiave: 'tennis_flb', nome: 'FLB', bot: 'tennis_flb' },
    { chiave: 'tennis_swing', nome: 'Swing', bot: 'tennis_swing' },
];

/**
 * Modalita' e accensione di UNA strategia di Safe. Stessa regola che la
 * tessera usava per lo sport intero (`modalitaPerSport`, 26/09), ora per voce:
 * il `mode` del servizio e' un TETTO (in paper nessuna strategia usa soldi
 * veri); `strategy_modes` dice con che soldi; `varianti` dice chi puo' APRIRE.
 * Una strategia non dichiarata vale PAPER solo se il servizio ha dichiarato il
 * suo modo: ai soldi veri si arriva scrivendolo, mai ereditandolo.
 */
function voceSafe(safe: BotPerCorsie | null, variante: string): Pick<VoceCorsia, 'modalita' | 'acceso'> {
    if (safe == null) return { modalita: null, acceso: null };
    const servizio = safe.modalita;
    const modalita: 'paper' | 'live' | null = servizio == null ? null
        : servizio !== 'live' ? 'paper'
            : safe.modiStrategia?.[variante] === 'live' ? 'live' : 'paper';
    const apre = safe.varianti == null || safe.varianti.includes(variante);
    return { modalita, acceso: safe.inCorsa && apre };
}

function corsieDi(elenco: typeof CALCIO, bots: readonly BotPerCorsie[]): CorsieSport {
    const out: CorsieSport = { live: [], prova: [], ignote: [], liveAcceso: false };
    for (const d of elenco) {
        const b = bots.find((x) => x.bot === d.bot) ?? null;
        const stato = d.variante != null
            ? voceSafe(b, d.variante)
            : b == null ? { modalita: null, acceso: null } : { modalita: b.modalita, acceso: b.inCorsa };
        const voce: VoceCorsia = { chiave: d.chiave, nome: d.nome, ...stato };
        if (voce.modalita === 'live') {
            out.live.push(voce);
            if (voce.acceso === true) out.liveAcceso = true;
        } else if (voce.modalita === 'paper') {
            out.prova.push(voce);
        } else {
            out.ignote.push(voce);
        }
    }
    return out;
}

/** Le due corsie di calcio e tennis dalla riga `control` di TUTTI i bot. */
export function corsiePerSport(bots: readonly BotPerCorsie[]): Record<SportCorsie, CorsieSport> {
    return { calcio: corsieDi(CALCIO, bots), tennis: corsieDi(TENNIS, bots) };
}
