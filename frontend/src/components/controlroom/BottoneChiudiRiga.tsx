// ============================================================================
// BottoneChiudiRiga.tsx — il «Chiudi» di UNA riga, cablato per singolo bot
// (B16, 24/09). La logica sta in `chiudiRiga.ts`; qui c'e' solo il montaggio.
//
// Il bottone arriva alla riga da un CONTESTO (`ChiusuraRigaContext`) che la
// pagina della Control Room fornisce: le schede che mostrano le righe
// (`SchedaPartita`, `SchedaPreMatch`) non cambiano firma, e dove il contesto
// manca (test storici, altre pagine) il bottone non si monta - nessun comando
// che non ha dietro un servizio.
//
// Cosa dice, sempre, invece di sparire in silenzio:
//   · riga chiudibile → «Chiudi» acceso, `title` = cosa fara' QUEL bot;
//   - riga non chiudibile (bot tennis senza partita/mercato, gamba di
//     chiusura, coperta, in volo, modalita' ignota) -> "Chiudi" spento,
//     `title` = il motivo (D3, 24/09: i bot tennis ora si chiudono);
//   · dopo il clic → «richiesta inviata / presa in carico / eseguita /
//     rifiutata: motivo / esito ignoto» accanto al bottone.
//
// 30/09 (decisione dell'utente, difetto D5; estesa a TUTTI i bot alle 16:20):
// «un clic in paper, conferma in live». In PAPER il primo clic chiude; in LIVE il primo clic
// ARMA (compare «Conferma»: soldi veri, con la stima di chiusura se la scheda
// la conosce) e solo la conferma manda la richiesta. La richiesta e' la stessa
// di prima. Stesso gesto di `CashOutPartita` (primo clic arma, secondo manda).
// ============================================================================
import { createContext, useContext, useEffect, useState } from 'react';
import { ATTESA_CONFERMA_USCITE_MS } from './InterruttoreUscite';

/** dopo quanto una conferma armata e non usata si disarma da sola */
export const SCADENZA_CONFERMA_MS = 10_000;
import { BOT_LABEL } from '@/lib/controlRoom';
import { fmtMoney } from '@/lib/format';
import {
    chiudibile, cosaFaIlClic, faseMostrata, inCorso, TESTO_FASE,
    type RigaDaChiudere, type StatoChiusuraRiga, type FaseChiusura,
} from './chiudiRiga';
import type { Bot } from '@/lib/controlRoom';
import type { ClicOrdine } from '@/lib/esitoAbbinamento';
import type { ContestoPrezzoVisto } from '@/lib/schedaAlMs';
import type { EsitoSeguito } from './useSeguiOrdini';
import type { SorgenteLadder } from './usePrezzoAlMs';

export interface ChiusuraRigaApi {
    chiudi: (riga: RigaDaChiudere) => Promise<void>;
    stato: (bot: Bot, id: number) => StatoChiusuraRiga | null;
    /** B17 (25/09) — l'esito dell'ORDINE di chiusura (abbinato a che prezzo). Opzionale. */
    esito?: (bot: Bot, id: number) => EsitoSeguito | null;
    /** B17 — per le schede nella partita (Mike): seguire un clic e leggerne l'esito */
    seguiClic?: (clic: Omit<ClicOrdine, 'idsNotiAlClic'>) => void;
    esitoOrdine?: (chiave: string) => EsitoSeguito | null;
    esitiOrdini?: EsitoSeguito[];
    /**
     * 25/09 (residui B17) - la sorgente del ladder AL MS per il "se chiudo
     * ora" delle righe (`useChiusuraAlMs`). Assente = solo lo scanner, dichiarato.
     */
    sorgenteLadder?: SorgenteLadder | null;
}

export const ChiusuraRigaContext = createContext<ChiusuraRigaApi | null>(null);

const CLS_FASE: Record<FaseChiusura, string> = {
    inviata: 'text-sky-300',
    presa_in_carico: 'text-amber-300',
    eseguita: 'text-emerald-400',
    rifiutata: 'text-red-400',
    ignota: 'text-orange-400',
};

const CLS_BOTTONE: Record<'riga' | 'orfana', string> = {
    riga: 'h-5 px-1.5 text-[9px] uppercase tracking-wider rounded border border-white/15 text-white/70 '
        + 'hover:text-white hover:border-emerald-500/50 disabled:opacity-40 disabled:hover:text-white/70 '
        + 'disabled:hover:border-white/15 disabled:cursor-not-allowed',
    orfana: 'ml-auto h-6 px-2 text-[10px] uppercase tracking-wider rounded border border-white/15 text-white/70 '
        + 'hover:text-white hover:border-emerald-500/50 disabled:opacity-40 disabled:cursor-not-allowed',
};

export function BottoneChiudiRiga({ riga, testId = 'cr-op-chiudi', variante = 'riga', prezzoAlClic, stimaOra }: {
    riga: RigaDaChiudere;
    testId?: string;
    variante?: 'riga' | 'orfana';
    /**
     * 25/09 (residui B17) - il prezzo "se chiudo ora" A VIDEO nell'istante del
     * clic (al ms o scanner) col suo contesto: va alla scheda per il delta dopo
     * l'abbinamento, MAI nel payload della richiesta.
     */
    prezzoAlClic?: () => { prezzo: number | null; contesto: ContestoPrezzoVisto };
    /** 30/09 - P&L stimato chiudendo ora, se la scheda lo conosce: solo per la
     *  frase della conferma live, MAI nel payload della richiesta. */
    stimaOra?: number | null;
}) {
    const api = useContext(ChiusuraRigaContext);
    const [inVolo, setInVolo] = useState(false);
    // review incrociata 30/09 (M2): «Conferma» compare nello stesso punto del
    // «Chiudi», quindi un doppio clic mandava soldi veri senza una conferma
    // voluta. Come per gli interruttori delle uscite (review 15/09), il
    // «Conferma» resta INERTE per ATTESA_CONFERMA_USCITE_MS dall'armamento.
    /** istante in cui la conferma e' comparsa; null = non armata */
    const [armatoDa, setArmatoDa] = useState<number | null>(null);
    const [, setTic] = useState(0);
    useEffect(() => {
        if (armatoDa == null) return;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_USCITE_MS + 20);
        return () => window.clearTimeout(t);
    }, [armatoDa]);
    // review incrociata 30/09 (M1 del secondo giro): una conferma armata e
    // dimenticata non deve restare valida per sempre. Si DISARMA quando il
    // bottone si spegne (riga occupata, non piu' chiudibile, contesto assente)
    // e comunque allo scadere di SCADENZA_CONFERMA_MS: riaprendo la scheda
    // piu' tardi, il primo clic torna a essere «Chiudi», mai «Conferma».
    const cPre = chiudibile(riga);
    const sPre = api ? api.stato(riga.bot, riga.id) : null;
    const accesoPre = !!api && cPre != null && cPre.ok && !(inVolo || inCorso(sPre));
    useEffect(() => { if (!accesoPre) setArmatoDa(null); }, [accesoPre]);
    useEffect(() => {
        if (armatoDa == null) return;
        const t = window.setTimeout(() => setArmatoDa(null), SCADENZA_CONFERMA_MS);
        return () => window.clearTimeout(t);
    }, [armatoDa]);
    const armato = armatoDa != null;
    const troppoPresto = armatoDa != null && Date.now() - armatoDa < ATTESA_CONFERMA_USCITE_MS;
    const setArmato = (v: boolean) => setArmatoDa(v ? Date.now() : null);
    if (!api) return null;
    const c = cPre;
    if (c == null) return null;
    const s = sPre;
    const occupato = inVolo || inCorso(s);
    const acceso = c.ok && !occupato;
    const titolo = !c.ok
        ? `non chiudibile: ${c.motivo}`
        : occupato
            ? 'richiesta di chiusura gia\' in corso su questa riga'
            : `${BOT_LABEL[riga.bot]}: ${cosaFaIlClic(riga.bot)}`;
    const fase = s ? faseMostrata(s) : null;
    // B17 (25/09) — dopo la richiesta, l'ORDINE: a che prezzo e quanto abbinato
    const es = api.esito?.(riga.bot, riga.id) ?? null;
    // FAIL-CLOSED: una modalita' non paper (live o ignota) chiede la conferma.
    const chiedeConferma = riga.modalita !== 'paper';
    const manda = () => {
        setArmato(false);
        setInVolo(true);
        const visto = prezzoAlClic?.();
        void api.chiudi(visto ? { ...riga, prezzoVisto: visto.prezzo, contestoVisto: visto.contesto } : riga)
            .finally(() => setInVolo(false));
    };
    return (
        <span className="inline-flex items-baseline gap-1" data-testid={`${testId}-box`}>
            {armato && acceso ? (
                <>
                    <button
                        type="button"
                        className={`${CLS_BOTTONE[variante]} border-orange-500/60 text-orange-300`}
                        title="conferma la chiusura: sono soldi veri"
                        data-testid={`${testId}-conferma`}
                        data-bot={riga.bot}
                        disabled={troppoPresto}
                        onClick={() => { if (!troppoPresto) manda(); }}
                    >Conferma</button>
                    <span className="text-[9px] text-orange-300" data-testid={`${testId}-armato`}>
                        Live, soldi veri: confermi la chiusura?
                        {stimaOra != null ? ` Stima chiudendo ora ${fmtMoney(stimaOra, { signed: true })}.` : ''}
                        {' '}
                        <button type="button" className="underline" onClick={() => setArmato(false)}
                            data-testid={`${testId}-annulla`}>annulla</button>
                    </span>
                </>
            ) : (
            <button
                type="button"
                className={CLS_BOTTONE[variante]}
                disabled={!acceso}
                title={titolo}
                aria-label={titolo}
                data-testid={testId}
                data-bot={riga.bot}
                data-motivo={c.ok ? undefined : c.motivo}
                onClick={() => {
                    if (!acceso) return;
                    if (chiedeConferma) { setArmato(true); return; }
                    manda();
                }}
            >Chiudi</button>
            )}
            {fase && (
                <span className={`text-[9px] ${CLS_FASE[fase]}`} data-testid={`${testId}-esito`}
                    data-fase={fase} title={s?.motivo ?? undefined}>
                    {TESTO_FASE[fase]}{s?.motivo && (fase === 'rifiutata' || fase === 'ignota'
                        || fase === 'presa_in_carico' || fase === 'inviata') ? `: ${s.motivo}` : ''}
                </span>
            )}
            {es && (es.gambe.length > 0 || es.esito.terminale) && (
                <span className="text-[9px] text-white/70" data-testid={`${testId}-ordine`}
                    data-fase={es.esito.fase} title={`esito: ${es.esito.fonte}`}>
                    {es.esito.simulato ? '[paper] ' : ''}{es.esito.testo}
                </span>
            )}
        </span>
    );
}
