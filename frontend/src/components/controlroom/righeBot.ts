// ============================================================================
// righeBot.ts — DA QUELLO CHE DICONO I SERVIZI ALLE RIGHE DELLA PLANCIA.
//
// Funzione pura, senza React e senza I/O: e' la traduzione fra lo stato dei
// tre servizi (`StatoBot`) e le righe della plancia di comando, una per
// interruttore. Sta da sola, e non dentro `useControlRoom`, perche' i test di
// pagina sostituiscono quel modulo con un finto: se vivesse la' dentro,
// sostituire il collegamento al database sostituirebbe anche questa — e le
// righe della plancia smetterebbero di essere collaudate.
// ============================================================================
import {
    interruttoriDiSport, statoInterruttore,
    type Interruttore, type SportBot, type StatoServizio,
} from '@/lib/interruttori';
import type { RigaInterruttore } from '@/components/controlroom/PannelloBot';
import type { Bot, Modalita } from '@/lib/interruttori';

/**
 * Il minimo che serve per disegnare le righe di un bot. `StatoBot` della
 * Control Room lo soddisfa per costruzione; le PAGINE DEI SINGOLI BOT, che
 * hanno il loro stato e non `useControlRoom`, possono costruirlo dalla propria
 * riga di control. Cosi' la plancia e' la stessa dappertutto.
 */
export interface StatoBotPlancia {
    bot: Bot;
    inCorsa: boolean;
    modalita: Modalita | null;
    varianti: string[] | null;
    modiStrategia: Record<string, 'paper' | 'live'> | null;
    stato: string | null;
    etaPushS: number | null;
    motivoBlocco: string | null;
    tettoPartite: number | null;
    partiteEsposte: number | null;
    stopFermaSoloAperture: boolean;
    fermatoAllAvvioAt: string | null;
    /** P&L di OGGI nelle due modalita', mai sommate. Facoltativi: le pagine dei
     *  singoli bot che non li leggono non devono inventarli. */
    pnlOggi?: number | null;
    pnlOggiPaper?: number | null;
}

/** Lo stato del SERVIZIO di un bot, nella forma che il modello condiviso legge. */
export function statoServizioDi(b: StatoBotPlancia): StatoServizio {
    return {
        inCorsa: b.inCorsa, modalita: b.modalita,
        varianti: b.varianti, modiStrategia: b.modiStrategia,
    };
}

/**
 * Le righe della plancia: UN interruttore per bot e per strategia, filtrate
 * per sport. Nella scheda calcio il tennis non compare, e viceversa.
 *
 * Qui non si DEDUCE niente: acceso, modalità e stato escono da
 * `statoInterruttore`, che legge `variants` + `strategy_modes` + il `mode` del
 * servizio. La pagina si limita a scegliere le parole.
 */
export function righeInterruttori(
    bots: readonly StatoBotPlancia[], sport: SportBot | null | undefined,
    etichette?: Partial<Record<string, string>>,
): RigaInterruttore[] {
    const perBot = new Map<Bot, StatoBotPlancia>(bots.map((b) => [b.bot, b]));
    const visti = new Set<Bot>();
    const out: RigaInterruttore[] = [];
    for (const i of interruttoriDiSport(sport ?? null)) {
        const b = perBot.get(i.bot);
        if (b == null) continue;
        const st = statoInterruttore(i, statoServizioDi(b));
        const primaDelBot = !visti.has(i.bot);
        visti.add(i.bot);
        out.push({
            id: i.id, bot: i.bot,
            etichetta: etichette?.[i.id] ?? i.etichetta,
            acceso: st.acceso, modalita: st.modalita, statoNoto: st.noto,
            stato: parolaStato(i, b, st.acceso, st.noto),
            etaPushS: b.etaPushS,
            motivoBlocco: b.motivoBlocco,
            tettoPartite: b.tettoPartite,
            partiteEsposte: b.partiteEsposte,
            stopFermaSoloAperture: b.stopFermaSoloAperture,
            fermatoAllAvvioAt: b.fermatoAllAvvioAt,
            // IL P&L DELLA MODALITA' IN CUI STA OPERANDO, mai la somma delle
            // due: soldi veri ed esercitazione non stanno nello stesso numero.
            // Modalita' non dichiarata = nessun numero: non si sceglie a caso
            // quale dei due mostrare.
            pnlOggi: st.modalita === 'live' ? (b.pnlOggi ?? null)
                : st.modalita === 'paper' ? (b.pnlOggiPaper ?? null) : null,
            primaDelBot,
        });
    }
    return out;
}

/**
 * La parola dello stato. Per un bot intero è quella che scrive il servizio;
 * per una STRATEGIA di Safe il servizio non ne scrive una, quindi si dice
 * quello che si sa: si sta fermando (vale per tutte), accesa, o ferma.
 * `stato non letto` non è mai «fermo»: sono due cose diverse.
 */
function parolaStato(i: Interruttore, b: StatoBotPlancia, acceso: boolean, noto: boolean): string {
    if (!noto) return 'ignoto';
    if (i.strategia == null) return b.stato ?? (b.inCorsa ? 'running' : 'ignoto');
    if (b.stato === 'stopping') return 'stopping';
    if (b.stato === 'error') return 'error';
    return acceso ? 'running' : 'stopped';
}
