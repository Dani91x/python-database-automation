// ============================================================================
// SchedaChiusura.tsx — LA SCHEDA CHE DECIDE UN'USCITA.
//
// Il bot tennis apre da solo; quando matura un'uscita NON la esegue: propone.
// Questa è la scheda su cui il trader dice sì o no, e ogni numero che mostra
// deve essere quello vero **in questo istante**, non quello di quando il bot
// ha deciso.
//
// COSA LA RENDE VIVA: il prezzo e l'importo abbinabile arrivano dal FEED, che
// alla pagina viaggia in push. La proposta conserva solo la FOTOGRAFIA, che
// serve a due cose: sapere su cosa il bot ha deciso, e misurare di quanto il
// mercato si è mosso da allora.
//
// COSA LA RENDE SICURA: non si approva mai al buio. Prezzo assente, età delle
// quote ignota, scostamento oltre la tolleranza, mercato che non abbina quanto
// serve → il bottone si spegne **e dice perché**. In live un ordine che non
// trova controparte viene annullato per intero, e il trader crederebbe di aver
// chiuso una posizione che è ancora aperta.
// ============================================================================
//
// 24/09 — ORDINE DELL'UTENTE (visto a video): «una scheda che ricalcola al ms
// tutto MA NON BLOCCA: me lo segnala e decido io». Prezzo al ms dal ladder del
// mercato (`usePrezzoAlMs`, ripiego sullo scanner dichiarato), e i motivi di
// sopra diventano AVVISI: CHIUDI ORA resta acceso. Al clic parte il prezzo a
// video con eta' e fonte (o l'ultimo noto con `prezzo_vivo_assente`). NB: per
// le CHIUSURE il servizio esegue ancora a mercato (decisione B17 aperta).
// ============================================================================
import { useEffect, useState } from 'react';
import { Loader2, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, fmtAge, fmtNum, fmtTicks, DASH } from '@/lib/format';
import {
    scarto, prezzoVistoAlClic, etaEFonte, prezzoDelLato, sizeDelLato,
    type ContestoPrezzoVisto, type PrezzoScheda,
} from '@/lib/schedaAlMs';
import { usePrezzoAlMs, type SorgenteLadder } from './usePrezzoAlMs';
import { StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import { safeExitKindLabel, safeReasonLabel } from '@/components/safestrategy/safeActivity';
import {
    scostamento, motivoNonApprovabile, abbinabileSufficiente, stakeDiChiusura,
    type PropostaChiusura, type PrezzoVivo,
} from '@/lib/controlRoomProposte';
import { StrisciaEsitoChiusura, type StrisciaEsitoChiusuraProps } from '@/components/controlroom/StrisciaEsitoChiusura';

/** Oltre questa età le quote non si usano per piazzare. Stessa soglia del
 *  resto della piattaforma (`safeBot.FEED_ROW_STALE_MS`): non se ne inventano. */
export const ETA_QUOTE_MAX_S = 20;

export interface SchedaChiusuraProps {
    proposta: PropostaChiusura;
    /** prezzo e abbinabile CORRENTI, presi dal feed */
    vivo: PrezzoVivo;
    /** età delle quote in secondi; null = non lo sappiamo (fail-closed) */
    etaQuoteS: number | null;
    /**
     * Quanto si blocca chiudendo ADESSO, al prezzo corrente.
     *
     * ⚠️ REVIEW 15/09 — qui si stampava `locked_at_decision`, cioè il valore
     * di ALLORA sotto un'etichetta che dice «adesso», mentre la colonna delle
     * posizioni della stessa pagina mostrava quello vivo. Due numeri diversi
     * per la stessa posizione.
     */
    bloccabileOra?: number | null;
    /** da quanto lo SCANNER non scrive: distingue «prezzo fermo» (corrente)
     *  da «prezzo vecchio» (non lo stiamo guardando). Senza, un mercato poco
     *  scambiato spegneva APPROVA su un'uscita urgente in live. */
    etaScannerS?: number | null;
    slippagePct: number;
    /** in LIVE serve la doppia conferma: sono soldi veri */
    onApprova: (id: number, prezzoVisto?: number, contesto?: ContestoPrezzoVisto) => Promise<void>;
    /** 24/09 — sorgente del ladder al ms (assente = solo feed dello scanner) */
    sorgenteLadder?: SorgenteLadder | null;
    onIgnora: (id: number) => Promise<void>;
    /**
     * LA STRISCIA DI ESITO (18/09, additiva): dopo l'approvazione, segue la
     * chiusura fino alla verità («inviata → a mercato → abbinata → CHIUSA
     * CONFERMATA»). OPZIONALE: senza questa prop la scheda resta ESATTAMENTE
     * com'era. Il chiamante la passa già calcolata da `certezzaChiusura()`
     * sulle righe che ha GIA' in memoria/realtime di questa proposta —
     * nessuna lettura nuova qui dentro.
     */
    esito?: StrisciaEsitoChiusuraProps;
}

export function SchedaChiusura({
    proposta, vivo: vivoScanner, etaQuoteS: etaScanner, etaScannerS = null, bloccabileOra = null,
    slippagePct, onApprova, onIgnora, esito, sorgenteLadder = null,
}: SchedaChiusuraProps) {
    const p = proposta.payload;
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setNowMs(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    const live = p.mode === 'live';
    const lato = p.side ?? null;
    // 24/09 — IL PREZZO AL MS: ladder del mercato se il runner lo segue,
    // altrimenti il feed dello scanner di prima (ripiego dichiarato).
    const ripiego: PrezzoScheda = {
        back: lato === 'back' ? vivoScanner.prezzo : null, backSize: lato === 'back' ? vivoScanner.abbinabile : null,
        lay: lato === 'lay' ? vivoScanner.prezzo : null, laySize: lato === 'lay' ? vivoScanner.abbinabile : null,
        istanteMs: etaScanner == null ? null : nowMs - etaScanner * 1000,
        fonte: 'scanner', statoMercato: vivoScanner.statoMercato ?? null,
    };
    const { prezzo: alMs, ultimoNoto } = usePrezzoAlMs({
        sorgente: sorgenteLadder, sport: p.sport === 'tennis' ? 'tennis' : 'calcio',
        marketId: p.market_id ?? null, selectionId: p.selection_id ?? null, lato, ripiego,
    });
    const vivo: PrezzoVivo = {
        prezzo: prezzoDelLato(alMs, lato), abbinabile: sizeDelLato(alMs, lato),
        statoMercato: alMs.statoMercato ?? vivoScanner.statoMercato ?? null,
    };
    const etaQuoteS = alMs.istanteMs == null ? null : Math.max(0, (nowMs - alMs.istanteMs) / 1000);
    const sc = scarto(vivo.prezzo, p.price_at_decision);
    const scost = scostamento({
        prezzoDecisione: p.price_at_decision,
        prezzoCorrente: vivo.prezzo,
        lato, slippagePct,
    });
    // QUANTO SI PIAZZA DAVVERO per chiudere: non la size di ingresso.
    // Su una copertura a quota più bassa è più GRANDE, e il controllo di
    // liquidità con il numero sbagliato lasciava passare un ordine che in
    // live viene annullato per intero.
    const daChiudere = stakeDiChiusura(p.size, p.entry_price, vivo.prezzo) ?? p.size ?? null;
    // 24/09 — ORDINE DELL'UTENTE: «me lo segnala e decido io». Il motivo e' un
    // AVVISO, il bottone resta acceso (il servizio esegue a mercato: B17).
    const avvisi: string[] = [];
    const motivo = motivoNonApprovabile({
        scost, etaQuoteS, etaMassimaS: ETA_QUOTE_MAX_S,
        daChiudere, abbinabileOra: vivo.abbinabile,
        etaScannerS,
        statoMercato: vivo.statoMercato ?? null,
    });
    if (motivo) avvisi.push(motivo);
    if (vivo.prezzo == null && ultimoNoto) {
        const eta = ultimoNoto.istanteMs == null ? null : (nowMs - ultimoNoto.istanteMs) / 1000;
        avvisi.push(`prezzo vivo assente da ${eta == null ? 'un tempo ignoto' : fmtAge(eta)}: `
            + `ultimo noto ${fmtOdds(ultimoNoto.prezzo)}`);
    }
    if (sc.tick != null && sc.tick !== 0) {
        avvisi.push(`prezzo mosso di ${fmtTicks(sc.tick)} (${fmtNum(sc.pct, 2)} %) dalla proposta`);
    }
    // il numero VIVO se c'e', altrimenti quello della decisione — e in quel
    // caso l'etichetta lo dice, invece di spacciare una fotografia per presente.
    const bloccato = bloccabileOra ?? p.locked_at_decision ?? null;
    const bloccatoEVivo = bloccabileOra != null;
    const urgente = p.urgente === true;

    const azione = async (fn: (id: number) => Promise<void>) => {
        setInCorso(true);
        try { await fn(proposta.id); } finally { setInCorso(false); setArmato(false); }
    };
    // 24/09 — APPROVA manda il prezzo a video (o l'ultimo noto col flag)
    const approva = async () => {
        setInCorso(true);
        try {
            const adesso = Date.now();
            const scelto = prezzoVistoAlClic({
                vivo: vivo.prezzo, vivoIstanteMs: alMs.istanteMs, vivoFonte: alMs.fonte,
                ultimoNoto: ultimoNoto?.prezzo ?? null, ultimoNotoIstanteMs: ultimoNoto?.istanteMs ?? null,
                ultimoNotoFonte: ultimoNoto?.fonte ?? null, prezzoProposta: p.price_at_decision,
                nowMs: adesso,
            });
            await onApprova(proposta.id, scelto.prezzo ?? undefined, scelto.contesto);
        } finally { setInCorso(false); setArmato(false); }
    };

    return (
        <article
            className={`rounded border bg-white/[0.02] overflow-hidden ${
                urgente ? 'border-orange-500/50' : 'border-white/10'
            }`}
            data-testid="cr-proposta"
            data-urgente={urgente ? '1' : '0'}
        >
            {/* ---- testata: chi, dove, e se è urgente ---- */}
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                    Safe · uscita {p.strategy ?? ''}
                </span>
                {live
                    ? <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300">soldi veri</span>
                    : <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/50">paper</span>}
                {urgente && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300"
                        title="uscita in perdita o obbligatoria: NON approvarla costa">
                        urgente
                    </span>
                )}
                <span className="ml-auto text-[11px] text-white/50 text-right">
                    {p.event_name ?? p.event_id}
                    {p.score && <> · <span className="font-mono">{p.score}</span></>}
                </span>
            </div>

            {/* ---- l'operazione: lato, selezione, prezzo VIVO ---- */}
            <div className="px-3 pt-2.5 pb-1 flex items-baseline gap-2.5 flex-wrap">
                <span className={`text-[12px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
                    lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                }`}>
                    {lato === 'lay' ? 'Banca' : 'Punta'}
                </span>
                <span className="text-[13px] font-semibold">{p.selection_name ?? DASH}</span>
                {/* C.12b (16/09) — la POSIZIONE che si sta chiudendo: chiesto,
                    abbinato, residuo. Il servizio non pubblica ancora abbinato e
                    residuo dentro la proposta: li' la scheda scrive «—», che non
                    e' uno zero, invece di far credere che sia tutto abbinato. */}
                <StatoOrdineCompatto
                    riga={{
                        status: 'open', side: p.entry_side ?? null,
                        price: p.entry_price ?? null, size: p.size ?? null,
                        size_requested: p.size_requested ?? null,
                        size_matched: p.size_matched ?? null,
                        size_remaining: p.size_remaining ?? null,
                        avg_price_matched: p.avg_price_matched ?? null,
                        betfair_updated_at: p.betfair_updated_at ?? null,
                    }}
                    testId="cr-proposta-stato-ordine"
                />
                <span className="ml-auto text-right">
                    <span className="font-mono text-lg font-bold tabular-nums" data-testid="cr-prezzo-vivo">
                        {fmtOdds(vivo.prezzo)}
                    </span>
                    <span className={`block font-mono text-[11px] ${
                        scost.delta == null ? 'text-white/40' : scost.controDiNoi ? 'text-orange-400' : 'text-emerald-400'
                    }`} data-testid="cr-scostamento">
                        {scost.delta == null
                            ? 'prezzo corrente non disponibile'
                            : <>
                                {scost.controDiNoi ? <TrendingDown className="w-3 h-3 inline mr-0.5" /> : <TrendingUp className="w-3 h-3 inline mr-0.5" />}
                                proposta a {fmtOdds(p.price_at_decision)}
                                {sc.tick != null && <> · {fmtTicks(sc.tick)}</>}
                              </>}
                    </span>
                    <span className="block text-[10px] text-white/40" data-testid="cr-proposta-fonte">
                        {etaEFonte(alMs.istanteMs, alMs.fonte, nowMs)}
                    </span>
                </span>
            </div>

            {/* TORNA DOPO UN RIFIUTO: si dice COSA è cambiato, o sembra
                insistenza invece che una situazione nuova. */}
            {p.riproposta_perche && (
                <div className="px-2.5 py-1.5 border-t border-secondary/30 bg-secondary/10 text-[11px] text-secondary"
                    data-testid="cr-riproposta">
                    <strong>Torna dopo il tuo rifiuto:</strong> {p.riproposta_perche}
                </div>
            )}

            {/* ---- i numeri che decidono ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 mt-2 border-t border-white/5">
                <Cella etichetta="Da chiudere"
                    valore={daChiudere == null ? DASH : fmtMoney(daChiudere)} />
                <Cella
                    etichetta="Abbinabile ora"
                    valore={vivo.abbinabile == null ? DASH : fmtMoney(vivo.abbinabile)}
                    tono={abbinabileSufficiente(daChiudere, vivo.abbinabile) ? 'buono' : 'cattivo'}
                />
                <Cella
                    etichetta={bloccatoEVivo ? 'Chiudere adesso' : 'Chiudere (alla proposta)'}
                    valore={bloccato == null ? DASH : fmtMoney(bloccato, { signed: true })}
                    tono={bloccato == null ? undefined : bloccato >= 0 ? 'buono' : 'cattivo'}
                />
                <Cella
                    etichetta="Tenere"
                    valore={p.hold_profit == null ? DASH : fmtMoney(p.hold_profit)}
                    nota={p.loss_if_lose != null ? `se perde: ${fmtMoney(-Math.abs(p.loss_if_lose))}` : undefined}
                />
            </div>

            {/* ---- perché, in italiano, da UNA sola tabella di traduzione ---- */}
            <div className="px-3 py-2 text-[12px] text-white/70 border-t border-white/5">
                <b className="text-white">Perché:</b>{' '}
                {safeExitKindLabel(p.exit_kind) ?? 'uscita'}
                {p.exit_reason && <> — {safeReasonLabel(p.exit_reason) ?? p.exit_reason}</>}
                <span className="block text-[11px] text-white/40 mt-0.5">
                    ingresso {p.entry_side === 'lay' ? 'banca' : 'punta'} a {fmtOdds(p.entry_price)}
                    {' · '}quote {etaQuoteS == null ? <span className="text-orange-400">età ignota</span> : fmtAge(etaQuoteS)}
                </span>
            </div>

            {/* ---- 24/09: gli AVVISI, con la RAGIONE; il bottone resta acceso ---- */}
            {avvisi.length > 0 && (
                <div className="px-3 py-2 bg-amber-500/10 text-amber-300 text-[12px] font-medium border-t border-amber-500/20"
                    data-testid="cr-proposta-avviso">
                    {avvisi.map((a, i) => <div key={i}>⚠ {a}</div>)}
                </div>
            )}

            {/* ---- le due azioni ---- */}
            <div className="grid grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                {armato ? (
                    <Button
                        onClick={() => void approva()} disabled={inCorso}
                        className="rounded-none h-10 bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider text-[12px]"
                        data-testid="cr-conferma-live"
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Confermo: soldi veri</>}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (live ? setArmato(true) : void approva())}
                        disabled={inCorso}
                        className="rounded-none h-10 bg-emerald-600/80 text-white hover:bg-emerald-600 font-bold uppercase tracking-wider text-[12px] disabled:opacity-40"
                        data-testid="cr-approva"
                        title={avvisi.length ? `attenzione: ${avvisi.join(' · ')}` : 'invia l’ordine di chiusura'}
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Chiudi ora'}
                    </Button>
                )}
                <Button
                    variant="ghost" onClick={() => void azione(onIgnora)} disabled={inCorso}
                    className="rounded-none h-10 text-white/60 hover:text-white uppercase tracking-wider text-[12px]"
                    data-testid="cr-ignora"
                >
                    Ignora
                </Button>
            </div>

            <div className="px-3 py-1.5 text-[10.5px] text-white/40 bg-white/[0.02]">
                {armato
                    ? <span className="text-orange-300">Sono soldi veri: conferma per mandare l’ordine.</span>
                    : <>La proposta resta viva finché non chiudi o la ignori. Se la ignori, torna alla prossima occasione.</>}
            </div>

            {urgente && (
                <div className="px-3 py-1.5 flex items-start gap-2 text-[11px] text-orange-300 bg-orange-500/5">
                    <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>Uscita del manuale: non approvarla ha un costo, non è una scelta neutra.</span>
                </div>
            )}

            {esito && <StrisciaEsitoChiusura {...esito} testId={esito.testId ?? 'cr-proposta-esito'} />}
        </article>
    );
}

function Cella({ etichetta, valore, tono, nota }: {
    etichetta: string; valore: string; tono?: 'buono' | 'cattivo'; nota?: string;
}) {
    const cls = tono === 'buono' ? 'text-emerald-400' : tono === 'cattivo' ? 'text-orange-400' : '';
    return (
        <div className="bg-background/40 px-3 py-1.5">
            <div className="text-[9px] uppercase tracking-wider text-white/40">{etichetta}</div>
            <div className={`font-mono text-[13px] font-semibold tabular-nums ${cls}`}>{valore}</div>
            {nota && <div className="text-[10px] text-white/40">{nota}</div>}
        </div>
    );
}

export default SchedaChiusura;
