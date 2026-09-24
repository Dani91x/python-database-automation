// ============================================================================
// SchedaChiusuraOmega.tsx — LA SCHEDA CHE DECIDE UN'USCITA DI OMEGA.
//
// Stessa forma della scheda della Safe (`SchedaChiusura.tsx`), perché è lo
// stesso gesto: il bot propone, l'utente decide. Quello che cambia sono i
// numeri, perché Omega banca un risultato e non punta una squadra:
//   · **risultato bloccabile** — EUR netti, uguali in ogni esito, se si chiude
//     ORA. Può essere NEGATIVO: dal 17/09 il bot propone anche le uscite in
//     PERDITA (protezione, cap), perché tenere può costare di più. È l'ordine
//     dell'utente: «la scheda vale sia in profit che in loss»;
//   · **EV di tenere** — quanto vale portarla al settlement con la P di adesso;
//   · **la traiettoria** — se il punteggio regge, quanto si bloccherebbe più
//     avanti e a che minuto. È la ragione per cui una proposta può NON partire.
//
// LA MEMORIA (12/09): su un lay la liability è già impegnata. Chiudere sotto
// l'EV non riduce il rischio: lo trasforma in perdita certa. Per questo la
// scheda mostra i tre numeri insieme, e non solo quello che fa comodo.
//
// IN LIVE SERVE LA DOPPIA CONFERMA.
// ============================================================================
//
// 24/09 — ORDINE DELL'UTENTE (visto a video): «una scheda che ricalcola al ms
// tutto MA NON BLOCCA: me lo segnala e decido io». Il prezzo di back arriva al
// ms (`usePrezzoAlMs`, ripiego sullo scanner dichiarato); «Blocchi adesso» e la
// DECISIONE del bot si ricalcolano a ogni tick con `esitoUscitaAlPrezzo` (porta
// pura di `omega_proposte.esito_uscita_al_prezzo`, legata dal file d'oro), coi
// soli ingredienti scritti dal servizio. Nessun motivo spegne il bottone: sono
// AVVISI. NB: `omega_request_approve` accetta solo l'id (nessun prezzo visto):
// il servizio chiude a mercato (decisione B17 aperta).
import { useEffect, useState } from 'react';
import { Loader2, Hourglass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, fmtPctPoints, fmtTime, fmtTicks, fmtAge, DASH } from '@/lib/format';
import {
    motivoNonApprovabileOmega, motivoUscitaOmegaLabel, eUnaProtezioneOmega, esitoUscitaAlPrezzo,
    type PropostaUscitaOmega,
} from '@/lib/omegaProposte';
import type { PrezzoVivo } from '@/lib/controlRoomProposte';
import { tickDown } from '@/lib/matching';
import { scarto, etaEFonte, type PrezzoScheda, type Semaforo } from '@/lib/schedaAlMs';
import { usePrezzoAlMs, type SorgenteLadder } from './usePrezzoAlMs';
import { StrisciaEsitoChiusura, type StrisciaEsitoChiusuraProps } from '@/components/controlroom/StrisciaEsitoChiusura';

export interface SchedaChiusuraOmegaProps {
    proposta: PropostaUscitaOmega;
    onApprova: (id: number) => Promise<void>;
    onIgnora: (id: number) => Promise<void>;
    /** LA STRISCIA DI ESITO (18/09, additiva): v. `SchedaChiusura.tsx`. OPZIONALE. */
    esito?: StrisciaEsitoChiusuraProps;
    /** 24/09 — sorgente del ladder al ms (assente = nessuna sottoscrizione) */
    sorgenteLadder?: SorgenteLadder | null;
    /** 24/09 — prezzo di back dal feed dello scanner (ripiego dichiarato) */
    vivoScanner?: PrezzoVivo | null;
    etaQuoteS?: number | null;
}

export function SchedaChiusuraOmega({
    proposta, onApprova, onIgnora, esito, sorgenteLadder = null, vivoScanner = null, etaQuoteS = null,
}: SchedaChiusuraOmegaProps) {
    const p = proposta.payload;
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);
    const [errore, setErrore] = useState<string | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setNowMs(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    const live = p.mode === 'live';
    // 24/09 — il prezzo di BACK (la chiusura di un lay) AL MS
    const ripiego: PrezzoScheda | null = vivoScanner?.prezzo == null ? null : {
        back: vivoScanner.prezzo, backSize: vivoScanner.abbinabile, lay: null, laySize: null,
        istanteMs: etaQuoteS == null ? null : nowMs - etaQuoteS * 1000,
        fonte: 'scanner', statoMercato: vivoScanner.statoMercato ?? null,
    };
    const { prezzo: alMs, ultimoNoto } = usePrezzoAlMs({
        sorgente: sorgenteLadder, sport: 'calcio', marketId: p.market_id ?? null,
        selectionId: p.selection_id ?? null, lato: 'back', ripiego,
    });
    const backOra = alMs.back;
    const ingredienti = p.commissione != null && p.margine_attesa != null && p.ev_tenere != null
        && p.p_evento != null;
    const calcola = (back: number | null) => esitoUscitaAlPrezzo({
        lay_price: p.entry_price, size: p.size, back_price: back, back_size: alMs.backSize,
        ev_tenere: p.ev_tenere, max_attesa: p.max_attesa, p_evento: p.p_evento,
        commissione: p.commissione, margine_attesa: p.margine_attesa,
        cap_scattato: p.cap_scattato ?? null, p_lose_max: p.p_lose_max ?? 0,
    });
    const ora = ingredienti && backOra != null ? calcola(backOra) : null;
    const semaforo: Semaforo | null = ora == null ? null
        : !ora.proponi ? 'NO'
            : calcola(tickDown(backOra as number)).proponi ? 'SI' : 'QUASI';
    const sc = scarto(backOra, p.back_price ?? p.price_at_decision);

    // AVVISI (mai un bottone spento)
    const avvisi: string[] = [];
    const strutturale = motivoNonApprovabileOmega(p);
    if (strutturale) avvisi.push(strutturale);
    if (backOra == null) {
        const eta = ultimoNoto?.istanteMs == null ? null : (nowMs - ultimoNoto.istanteMs) / 1000;
        avvisi.push(ultimoNoto
            ? `prezzo vivo assente da ${eta == null ? 'un tempo ignoto' : fmtAge(eta)}: ultimo noto ${fmtOdds(ultimoNoto.prezzo)}`
            : 'prezzo vivo assente: i numeri sono quelli della proposta');
    }
    if (sc.tick != null && sc.tick !== 0) avvisi.push(`prezzo mosso di ${fmtTicks(sc.tick)} dalla proposta`);
    if (p.valutazione && p.valutazione.valida === false) {
        avvisi.push(`il bot non la proporrebbe più: ${motivoUscitaOmegaLabel(p.valutazione.motivo_codice) ?? 'motivo non dichiarato'}`);
    }
    if (ora && !ora.proponi) {
        avvisi.push(`al prezzo di adesso: ${motivoUscitaOmegaLabel(ora.motivo_codice) ?? ora.motivo_codice}`);
    }
    const bloccabile = ora?.profitto != null ? ora.profitto
        : p.profitto_bloccabile == null ? null : Number(p.profitto_bloccabile);
    const evTenere = p.ev_tenere == null ? null : Number(p.ev_tenere);
    const aspetta = p.meglio_aspettare === true;
    // 17/09 — ORDINE DELL'UTENTE: la scheda vale «sia in profit che in loss».
    // Una PROTEZIONE non e' un affare: si chiude perche' tenere costa di piu'.
    // Scriverci sopra «Chiudi ora» in verde direbbe al trader il contrario di
    // quello che sta facendo.
    const protezione = eUnaProtezioneOmega(p);

    const azione = async (fn: (id: number) => Promise<void>) => {
        setInCorso(true);
        setErrore(null);
        try { await fn(proposta.id); } catch (e) {
            // migrazione non applicata → la RPC non esiste: si mostra, non si nasconde
            setErrore(e instanceof Error ? e.message : String(e));
        } finally { setInCorso(false); setArmato(false); }
    };

    return (
        <article
            className={`rounded border bg-white/[0.02] overflow-hidden ${
                avvisi.length ? 'border-white/10' : 'border-primary/40'
            }`}
            data-testid="cr-proposta-omega"
            data-approvabile="1"
        >
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-primary">
                    Omega · uscita
                </span>
                {live
                    ? <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300">soldi veri</span>
                    : <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/50">paper</span>}
                {protezione && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/20 text-red-300"
                        data-testid="cr-omega-protezione"
                        title="non e’ un guadagno: si chiude perche’ tenere costa di piu’">
                        protezione · si blocca una perdita
                    </span>
                )}
                {aspetta && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300"
                        title="se il punteggio regge, piu’ avanti si bloccherebbe di piu’">
                        <Hourglass className="w-2.5 h-2.5 inline mr-0.5" />aspettare puo’ valere di piu’
                    </span>
                )}
                <span className="ml-auto text-[11px] text-white/50 text-right">
                    {p.event_name ?? p.event_id}
                    {p.score && <> · <span className="font-mono">{p.score}</span></>}
                    {p.minute != null && <> · <span className="font-mono">{Math.round(Number(p.minute))}′</span></>}
                </span>
            </div>

            <div className="px-3 pt-2.5 pb-1 flex items-baseline gap-2.5 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-widest px-2 py-0.5 rounded bg-sky-500/15 text-sky-300">
                    Punta per chiudere
                </span>
                <span className="text-[13px] font-semibold">{p.selection_name ?? DASH}</span>
                <span className="ml-auto text-right">
                    <span className="font-mono text-lg font-bold tabular-nums" data-testid="cr-omega-back-price">
                        {fmtOdds(backOra ?? p.back_price)}
                    </span>
                    <span className="block font-mono text-[11px] text-white/45" data-testid="cr-omega-back-size">
                        per {(ora?.back_stake ?? p.back_size) == null ? DASH : fmtMoney(ora?.back_stake ?? p.back_size)}
                        {p.price_at_decision != null && <> · bancata a {fmtOdds(p.entry_price)}</>}
                        {backOra != null && <> · proposta a {fmtOdds(p.back_price ?? p.price_at_decision)}</>}
                    </span>
                    <span className="block text-[10px] text-white/40" data-testid="cr-omega-fonte">
                        {backOra == null ? 'numeri della proposta (prezzo vivo assente)'
                            : etaEFonte(alMs.istanteMs, alMs.fonte, nowMs)}
                    </span>
                </span>
            </div>

            {/* ---- i tre numeri che decidono, insieme ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 mt-2 border-t border-white/5">
                <Cella etichetta="Blocchi adesso"
                    valore={bloccabile == null ? DASH : fmtMoney(bloccabile, { signed: true })}
                    tono={bloccabile == null ? undefined : bloccabile > 0 ? 'buono' : 'cattivo'} />
                <Cella etichetta="Tenere vale"
                    valore={evTenere == null ? DASH : fmtMoney(evTenere, { signed: true })}
                    nota={p.p_evento == null ? undefined
                        : `P che il risultato esca ${fmtPctPoints(Number(p.p_evento) * 100, 2)}`} />
                <Cella etichetta="Se il punteggio regge"
                    valore={p.bloccabile_max_atteso == null ? DASH : fmtMoney(Number(p.bloccabile_max_atteso), { signed: true })}
                    nota={p.minuto_del_massimo == null ? undefined
                        : `al ${Math.round(Number(p.minuto_del_massimo))}′`} />
                <Cella etichetta={p.liability == null ? 'Controparte alla decisione' : 'Rischio impegnato'}
                    valore={p.liability != null ? fmtMoney(Number(p.liability))
                        : p.size_available_at_decision == null ? DASH
                        : fmtMoney(Number(p.size_available_at_decision))}
                    nota={p.decided_at ? `decisa alle ${fmtTime(p.decided_at)}` : 'istante non dichiarato'} />
            </div>

            <div className="px-3 py-2 text-[12px] text-white/70 border-t border-white/5">
                <b className="text-white">Perché:</b>{' '}
                {motivoUscitaOmegaLabel(p.motivo_codice) ?? 'motivo non dichiarato'}
                {p.cap_scattato && <> <span className="font-mono text-[11px] text-white/50">({p.cap_scattato})</span></>}
                {p.riproposta_perche && (
                    <span className="block text-[11px] text-sky-300/80 mt-0.5">
                        torna a chiedertelo perché {p.riproposta_perche}
                    </span>
                )}
                <span className="block text-[11px] text-white/40 mt-0.5">
                    aggiornata {p.proposed_at ? `alle ${fmtTime(p.proposed_at)}` : DASH}
                    {' · '}il prezzo su cui si piazza lo guardi tu, vivo, un istante prima
                </span>
            </div>

            {/* 24/09 — il semaforo al prezzo di adesso, con la decisione del bot */}
            {semaforo && (
                <div className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider border-t ${
                    semaforo === 'SI' ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                        : semaforo === 'QUASI' ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
                            : 'bg-red-500/10 text-red-300 border-red-500/20'
                }`} data-testid="cr-omega-semaforo" data-semaforo={semaforo}>
                    uscita ancora valida: {semaforo === 'SI' ? 'sì' : semaforo === 'QUASI' ? 'quasi (un tick la farebbe cadere)' : 'no'}
                </div>
            )}

            {/* 24/09 — AVVISI, non blocchi: il bottone resta acceso, decidi tu */}
            {avvisi.length > 0 && (
                <div className="px-3 py-2 bg-amber-500/10 text-amber-300 text-[12px] font-medium border-t border-amber-500/20"
                    data-testid="cr-proposta-omega-avviso">
                    {avvisi.map((a, i) => <div key={i}>⚠ {a}</div>)}
                </div>
            )}

            <div className="grid grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                {armato ? (
                    <Button
                        onClick={() => void azione(onApprova)} disabled={inCorso}
                        className="rounded-none h-10 bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider text-[12px]"
                        data-testid="cr-omega-conferma-live"
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Confermo: soldi veri</>}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (live ? setArmato(true) : void azione(onApprova))}
                        disabled={inCorso}
                        className={`rounded-none h-10 text-white font-bold uppercase tracking-wider text-[12px] disabled:opacity-40 ${
                            protezione ? 'bg-red-600/80 hover:bg-red-600' : 'bg-emerald-600/80 hover:bg-emerald-600'
                        }`}
                        data-testid="cr-omega-approva"
                        title={avvisi.length ? `attenzione: ${avvisi.join(' · ')}` : 'invia l’ordine di chiusura'}
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" />
                            : protezione ? 'Chiudi in perdita' : 'Chiudi ora'}
                    </Button>
                )}
                <Button
                    variant="ghost" onClick={() => void azione(onIgnora)} disabled={inCorso}
                    className="rounded-none h-10 text-white/60 hover:text-white uppercase tracking-wider text-[12px]"
                    data-testid="cr-omega-ignora"
                >
                    Ignora
                </Button>
            </div>

            <div className="px-3 py-1.5 text-[10.5px] text-white/40 bg-white/[0.02]">
                {armato
                    ? <span className="text-orange-300">Sono soldi veri: conferma per mandare l’ordine.</span>
                    : <>Nessuna chiusura parte da sola: la proposta resta viva finché non decidi. Se la ignori, torna alla prossima occasione.</>}
            </div>

            {errore && (
                <div className="px-3 py-1.5 text-[11px] text-red-300 bg-red-500/10"
                    data-testid="cr-proposta-omega-errore">
                    ⛔ il servizio ha rifiutato: {errore}
                </div>
            )}

            {esito && <StrisciaEsitoChiusura {...esito} testId={esito.testId ?? 'cr-proposta-omega-esito'} />}
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

export default SchedaChiusuraOmega;
