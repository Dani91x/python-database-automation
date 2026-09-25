// ============================================================================
// SchedaPropostaOpportunita.tsx — LA SCHEDA CHE DECIDE UN'APERTURA.
//
// Ordine dell'utente (17/09): «Le opportunita' modello (SIA CALCIO CHE TENNIS)
// devono apparirmi come la card della chiusura, sotto e con card dedicata, con
// TUTTE LE INFORMAZIONI e i due tasti: PIAZZA parte l'ordine, RIFIUTA la
// scheda viene rifiutata.»
//
// Stessa forma della scheda della chiusura (`SchedaChiusura.tsx`), perché è lo
// stesso gesto: il bot ha visto qualcosa, lo mette per iscritto, decide una
// persona. Qui però si APRE una posizione, quindi cambiano i numeri che
// contano: non «chiudere o tenere» ma quanto vale entrare — p del modello
// contro p implicita del mercato, vantaggio, valore atteso, confidenza e il
// perché in parole.
//
// PIAZZA non apre una seconda strada verso Betfair: promuove la riga della
// coda da 'proposed' a 'pending' (RPC `safe_request_approve`) ed è il servizio
// a eseguirla, con le stesse barriere di ogni richiesta manuale. RIFIUTA la
// porta a 'rejected' (`safe_request_ignore`): finché la chiave resta uguale
// quella scheda non torna.
//
// In LIVE il primo clic ARMA e il secondo manda: sono soldi veri.
//
// 24/09 — ORDINE DELL'UTENTE (visto a video): «se il prezzo cambia ricevo
// "prezzo vivo assente: non si piazza al buio" E NON POSSO PIAZZARE NULLA.
// Voglio una scheda che ricalcola al ms tutto MA NON BLOCCA L'ENTRATA: me lo
// segnala e decido io.» Da oggi:
//   * il prezzo arriva AL MS dal ladder del mercato (`usePrezzoAlMs`:
//     `sorgenteLadderAlMs`, sottoscritto con la scheda e staccato alla
//     chiusura); per i mercati che il runner non segue ripiega sul feed dello
//     scanner, e la scheda lo DICHIARA con l'eta';
//   * EV, vantaggio, P implicita e responsabilita' si ricalcolano a ogni tick
//     coi CRITERI del modello scritti dal servizio (`valutaAlPrezzo`); il
//     semaforo dice SI / QUASI / NO;
//   * NESSUN motivo spegne PIAZZA: prezzo assente o vecchio, prezzo mosso,
//     «fuori criterio», «non piu' valida per il modello» sono AVVISI. Al clic
//     parte il prezzo a video (o l'ultimo noto con `prezzo_vivo_assente`),
//     col suo istante e la sua fonte: decide il servizio con la tolleranza.
// ============================================================================
import { useEffect, useState } from 'react';
import { Loader2, ShieldAlert, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtNum, fmtOdds, fmtPct, fmtAge, fmtTicks, DASH } from '@/lib/format';
import type { PropostaOpportunita, PropostaOpportunitaLeg, PrezziViviGambe } from '@/lib/safeBot';
import type { CriteriProposta } from '@/lib/valutaProposta';
import {
    giudica, scarto, prezzoVistoAlClic, etaEFonte, prezzoDelLato, sizeDelLato, prezzoSegnaleDi,
    type ContestoPrezzoVisto, type PrezzoScheda, type Semaforo, type ValutazioneServizio,
} from '@/lib/schedaAlMs';
import { usePrezzoAlMs, type SorgenteLadder } from './usePrezzoAlMs';

/** Oltre questa età le quote non si usano per piazzare: stessa soglia del
 *  resto della piattaforma (`safeBot.FEED_ROW_STALE_MS`). */
export const ETA_QUOTE_MAX_S = 20;

export interface SchedaPropostaOpportunitaProps {
    proposta: PropostaOpportunita;
    /** importo abbinabile CORRENTE sul lato da operare (dal feed vivo);
     *  null = la fonte non lo pubblica, e allora si dice, non si inventa */
    abbinabileOra?: number | null;
    /** età delle quote in secondi; null = non lo sappiamo (fail-closed) */
    etaQuoteS?: number | null;
    /**
     * 18/09 — ORDINE DELL'UTENTE: «il prezzo può muoversi, io devo vedere la
     * tab aggiornata e quando clicco prendiamo QUEL NUMERO CHE VEDO.» Il
     * prezzo VIVO di UNA gamba (proposta non-combo): questo è il numero che
     * la card mostra in grande ed è ESATTAMENTE quello che PIAZZA manda
     * all'approvazione — mai il prezzo congelato della proposta.
     * `null`/assente = non lo si conosce ora: PIAZZA resta spento.
     */
    prezzoVivo?: number | null;
    /**
     * 18/09 — lo stesso, per OGNI gamba di una proposta COMBO, indicizzato
     * dalla posizione della gamba in `payload.legs` (vedi `PrezziViviGambe`
     * in `lib/safeBot.ts`). Prop preparata da `useControlRoom.ts` (fuori dal
     * perimetro di questa modifica): finché non arriva, la card mostra i
     * prezzi della fotografia e PIAZZA resta spento (nessun prezzo vivo
     * noto — non si approva una combo al buio).
     */
    prezziViviGambe?: PrezziViviGambe | null;
    /** Lo slippage che l'utente ha impostato a video (se la pagina lo
     *  espone): viaggia con l'approvazione così il servizio ricontrolla la
     *  tolleranza con LA STESSA soglia che l'utente vede, non un default
     *  invisibile. Assente → il servizio usa il suo default. */
    slippagePct?: number | null;
    /**
     * 24/09 — la sorgente del ladder AL MS (`sorgenteLadderAlMs` di
     * `lib/localTransport.ts`). Assente = nessuna sottoscrizione: la scheda
     * usa il feed dello scanner (`prezzoVivo`/`etaQuoteS`) e lo dichiara.
     */
    sorgenteLadder?: SorgenteLadder | null;
    /** 24/09 — il contesto del prezzo al clic (eta', fonte, prezzo vivo assente). */
    onPiazza: (id: number, prezzoVisto?: number, legsPricesVisti?: PrezziViviGambe,
              slippagePct?: number, contesto?: ContestoPrezzoVisto) => Promise<void>;
    onRifiuta: (id: number) => Promise<void>;
}

// I numeri si formattano da UN solo posto (`@/lib/format`): denaro, quote e
// percentuali hanno gia' la forma italiana decisa per tutta la piattaforma, e
// un `toFixed` scritto a mano qui vorrebbe dire una card che parla una lingua
// diversa dalle altre (`designGuard.test.ts` lo vieta).
const PCT = (v: unknown): string => fmtPct(v as number | null | undefined, 1);
const NUM = (v: unknown, cifre = 3): string => fmtNum(v as number | null | undefined, cifre);

const KIND_IT: Record<string, string> = {
    model: 'modello', tennis: 'modello tennis',
    anomaly: 'anomalia', combo: 'combinazione',
};

/** Che cosa AVVISARE prima della firma (24/09: NON spegne più PIAZZA — ordine
 *  dell'utente «me lo segnala e decido io»; il nome resta per compatibilità).
 *
 * 18/09 — ORDINE DELL'UTENTE: PIAZZA manda il prezzo VIVO, non quello della
 * proposta: senza un `prezzoVivo` noto e fresco non c'è NIENTE da mandare,
 * quindi il bottone resta spento a prescindere da quanto sia valida la
 * fotografia. `prezzo`/`size` restano controllati (dati della proposta
 * comunque incoerenti = scheda da non firmare), ma il vero cancelletto
 * nuovo è `prezzoVivo`. */
export function motivoNonPiazzabile(p: {
    prezzo: unknown; size: unknown; abbinabileOra: number | null | undefined;
    etaQuoteS: number | null | undefined;
    prezzoVivo?: number | null;
}): string | null {
    const prezzo = Number(p.prezzo);
    if (!Number.isFinite(prezzo) || prezzo <= 1) return 'prezzo della proposta non valido';
    const size = Number(p.size);
    if (!Number.isFinite(size) || size <= 0) return 'importo della proposta non valido';
    if (p.etaQuoteS == null) return 'età delle quote ignota: controlla il prezzo prima di firmare';
    if (p.etaQuoteS > ETA_QUOTE_MAX_S) {
        return `quote vecchie di ${Math.round(p.etaQuoteS)} s: il prezzo può non essere quello di adesso`;
    }
    if (p.prezzoVivo == null || !Number.isFinite(p.prezzoVivo) || p.prezzoVivo <= 1) {
        return 'prezzo vivo assente: al clic parte l’ultimo prezzo noto, il servizio lo confronta col mercato';
    }
    if (p.abbinabileOra != null && p.abbinabileOra <= 0) {
        return 'nessun importo abbinabile al miglior prezzo in questo momento';
    }
    if (p.abbinabileOra != null && size > p.abbinabileOra + 0.005) {
        return `abbinabili solo ${fmtMoney(p.abbinabileOra)}: in LIVE l'ordine è `
            + 'FILL_OR_KILL e verrebbe annullato per intero';
    }
    return null;
}

/**
 * Perché una proposta COMBO (18/09) NON si può firmare adesso.
 *
 * A differenza di una gamba sola, qui non c'è un `abbinabileOra`/`etaQuoteS`
 * per l'INTERA combinazione: `useControlRoom.ts` (fuori dal perimetro di
 * questa modifica) calcola quei due numeri da un solo `market_id`/
 * `selection_id`, che una combo non ha in cima al payload. Il controllo che
 * resta qui è quello che i dati della proposta permettono da soli: ogni
 * gamba ha un prezzo e un importo validi.
 *
 * 18/09 — ORDINE DELL'UTENTE: in più, OGNI gamba deve avere un prezzo VIVO
 * noto (`prezziViviGambe`, indicizzato dalla posizione della gamba): senza,
 * PIAZZA manderebbe un prezzo che nessuno sta più guardando. La riprova vera
 * (gamba sparita, prezzo fuori tolleranza, clic troppo vecchio) la fa il
 * servizio all'approvazione (`_request_place_combo`): se una gamba non
 * regge più, PIAZZA torna un rifiuto dichiarato.
 */
export function motivoNonPiazzabileCombo(p: {
    legs: PropostaOpportunitaLeg[] | null | undefined;
    prezziViviGambe?: PrezziViviGambe | null;
}): string | null {
    const legs = p.legs;
    if (!Array.isArray(legs) || legs.length < 2) return 'proposta combo senza gambe valide';
    for (const leg of legs) {
        const prezzo = Number(leg.price);
        if (!Number.isFinite(prezzo) || prezzo <= 1) return 'prezzo di una gamba non valido';
        const size = Number(leg.size);
        if (!Number.isFinite(size) || size <= 0) return 'importo di una gamba non valido';
    }
    const vivi = p.prezziViviGambe;
    if (vivi == null) return 'prezzo vivo assente: al clic partono i prezzi della proposta';
    for (let i = 0; i < legs.length; i++) {
        const v = vivi[i];
        if (v == null || !Number.isFinite(v) || v <= 1) {
            return `prezzo vivo assente per la gamba ${i + 1}: al clic parte il suo prezzo della proposta`;
        }
    }
    return null;
}

export function SchedaPropostaOpportunita({
    proposta, abbinabileOra = null, etaQuoteS = null, prezzoVivo = null,
    prezziViviGambe = null, slippagePct = null, sorgenteLadder = null, onPiazza, onRifiuta,
}: SchedaPropostaOpportunitaProps) {
    const p = proposta.payload;
    const [armato, setArmato] = useState(false);
    const [inCorso, setInCorso] = useState(false);
    // l'orologio della scheda: l'eta' del prezzo scorre anche a mercato fermo
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setNowMs(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    const live = p.mode === 'live';
    const lato = (p.side ?? null) as 'back' | 'lay' | null;
    // 18/09 — una COMBO porta N gambe in `payload.legs`, non un market_id/
    // selection_id/side/price in cima: e' un'altra forma di scheda.
    const isCombo = p.kind === 'combo' && Array.isArray(p.legs) && p.legs.length >= 2;

    // 24/09 — IL PREZZO AL MS: ladder del mercato se c'e', altrimenti il feed
    // dello scanner che la scheda riceveva gia' (ripiego DICHIARATO).
    const ripiego: PrezzoScheda | null = prezzoVivo == null ? null : {
        back: lato === 'back' ? prezzoVivo : null, backSize: lato === 'back' ? abbinabileOra : null,
        lay: lato === 'lay' ? prezzoVivo : null, laySize: lato === 'lay' ? abbinabileOra : null,
        istanteMs: etaQuoteS == null ? null : nowMs - etaQuoteS * 1000,
        fonte: 'scanner', statoMercato: null,
    };
    const { prezzo: alMs, ultimoNoto } = usePrezzoAlMs({
        sorgente: isCombo ? null : sorgenteLadder,
        sport: p.sport === 'tennis' ? 'tennis' : 'calcio',
        marketId: p.market_id ?? null, selectionId: p.selection_id ?? null, lato, ripiego,
    });
    const vivo = prezzoDelLato(alMs, lato);
    const abbinabile = sizeDelLato(alMs, lato);
    // eta' del prezzo mostrato; senza prezzo, quella del feed (se nota)
    const etaS = alMs.istanteMs == null ? etaQuoteS : Math.max(0, (nowMs - alMs.istanteMs) / 1000);

    // i numeri AL PREZZO DI ADESSO coi criteri del modello (solo se il
    // servizio li ha scritti: una proposta vecchia mostra i numeri di allora)
    const criteri = (p as { criteri?: CriteriProposta | null }).criteri ?? null;
    const valutazione = (p as { valutazione?: ValutazioneServizio | null }).valutazione ?? null;
    const giudizio = !isCombo && criteri
        ? giudica({ lato, prezzo: vivo, abbinabile, pModel: p.p_model, criteri, valutazione })
        : null;
    const semaforo: Semaforo | null = isCombo
        ? (valutazione && valutazione.valida === false ? 'NO' : null)
        : giudizio?.semaforo ?? null;
    const sc = scarto(vivo, p.price_at_decision);
    const ap = giudizio?.alPrezzo ?? null;

    // GLI AVVISI (mai un bottone spento): dati/prezzo, prezzo mosso, criteri.
    const avvisi: string[] = [];
    const base = isCombo
        ? motivoNonPiazzabileCombo({ legs: p.legs, prezziViviGambe })
        : motivoNonPiazzabile({ prezzo: p.price, size: p.size, abbinabileOra: abbinabile,
            etaQuoteS: etaS, prezzoVivo: vivo });
    if (base) avvisi.push(base);
    if (!isCombo && vivo == null && ultimoNoto) {
        const eta = ultimoNoto.istanteMs == null ? null : (nowMs - ultimoNoto.istanteMs) / 1000;
        avvisi.push(`prezzo vivo assente da ${eta == null ? 'un tempo ignoto' : fmtAge(eta)}: `
            + `ultimo noto ${fmtOdds(ultimoNoto.prezzo)}`);
    }
    if (sc.tick != null && sc.tick !== 0) {
        avvisi.push(`prezzo mosso di ${fmtTicks(sc.tick)} (${sc.tick > 0 ? '+' : '−'}`
            + `${fmtNum(Math.abs(sc.pct ?? 0), 2)} %) dalla proposta`);
    }
    if (valutazione && valutazione.valida === false) {
        avvisi.push(valutazione.causa === 'modello'
            ? 'opportunità non più valida per il modello (lo dice il servizio)'
            : 'opportunità non più valida al prezzo dell’ultima valutazione del servizio');
    }
    if (giudizio && giudizio.semaforo !== 'SI') {
        avvisi.push(`fuori criterio: ${giudizio.motivi.join('; ')}`);
    }

    // 18/09 + 24/09 — ORDINE DELL'UTENTE: PIAZZA manda ESATTAMENTE il numero
    // a video in quell'istante (con eta' e fonte); senza prezzo vivo manda
    // l'ultimo noto col flag `prezzo_vivo_assente`. Mai un clic rifiutato qui.
    const piazza = async () => {
        setInCorso(true);
        try {
            const adesso = Date.now();
            if (isCombo) {
                const pulite: PrezziViviGambe = {};
                let assente = false;
                (p.legs ?? []).forEach((leg, i) => {
                    const v = prezziViviGambe?.[i];
                    if (v != null && Number.isFinite(v) && v > 1) { pulite[i] = v; return; }
                    assente = true;
                    const foto = Number(leg.price);
                    if (Number.isFinite(foto) && foto > 1) pulite[i] = foto;
                });
                await onPiazza(proposta.id, undefined, pulite, slippagePct ?? undefined, {
                    eta_ms: null, fonte: assente ? 'proposta' : 'scanner',
                    prezzo_vivo_assente: assente, clic_ms: adesso });
            } else {
                const scelto = prezzoVistoAlClic({
                    vivo, vivoIstanteMs: alMs.istanteMs, vivoFonte: alMs.fonte,
                    ultimoNoto: ultimoNoto?.prezzo ?? null,
                    ultimoNotoIstanteMs: ultimoNoto?.istanteMs ?? null,
                    ultimoNotoFonte: ultimoNoto?.fonte ?? null,
                    prezzoProposta: p.price, nowMs: adesso,
                });
                // B17 (25/09) — col prezzo visto parte anche quello del SEGNALE
                // (alla nascita della proposta): dopo il clic la colonna dice a
                // quanti tick da tutti e due si e' abbinato l'ordine
                await onPiazza(proposta.id, scelto.prezzo ?? undefined, undefined,
                    slippagePct ?? undefined, { ...scelto.contesto, prezzo_segnale: prezzoSegnaleDi(p) });
            }
        } finally { setInCorso(false); setArmato(false); }
    };
    const rifiuta = async () => {
        setInCorso(true);
        try { await onRifiuta(proposta.id); } finally { setInCorso(false); setArmato(false); }
    };

    return (
        <article
            className={`rounded border bg-white/[0.02] overflow-hidden ${
                live ? 'border-orange-500/40' : 'border-white/10'
            }`}
            data-testid="cr-proposta-opp"
            data-mode={p.mode ?? ''}
        >
            {/* ---- testata: che cos'è, su quale partita, con quali soldi ---- */}
            <div className="px-3 py-2 border-b border-white/10 flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                    Safe · opportunità {KIND_IT[String(p.kind)] ?? p.kind}
                </span>
                <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/60"
                    data-testid="cr-opp-sport">
                    {p.sport === 'tennis' ? 'tennis' : 'calcio'}
                </span>
                {live
                    ? <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300" data-testid="cr-opp-modalita">soldi veri · live</span>
                    : <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/50" data-testid="cr-opp-modalita">paper</span>}
                <span className="ml-auto text-[11px] text-white/50 text-right" data-testid="cr-opp-partita">
                    {p.event_name ?? p.event_id}
                    {p.minute != null && <> · <span className="font-mono">{p.minute}&apos;</span></>}
                    {p.score && <> · <span className="font-mono">{p.score}</span></>}
                </span>
            </div>

            {/* ---- l'operazione: una gamba sola, o TUTTE le gambe della combo ----
                 18/09 — ORDINE DELL'UTENTE: il numero GRANDE è il prezzo VIVO
                 (quello che PIAZZA manderà); la fotografia della proposta resta
                 sotto, piccola, con la differenza — mai il contrario. */}
            {isCombo ? (
                <div className="border-t border-white/5" data-testid="cr-opp-combo-legs">
                    {(p.legs ?? []).map((leg, i) => {
                        const vivo = prezziViviGambe?.[i] ?? null;
                        return (
                            <div key={i}
                                className="px-3 py-1.5 flex items-baseline gap-2.5 flex-wrap border-b border-white/5 last:border-b-0"
                                data-testid="cr-opp-combo-gamba">
                                <span className={`text-[10px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded ${
                                    leg.side === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                                }`}>
                                    {leg.side === 'lay' ? 'Banca' : 'Punta'}
                                </span>
                                <span className="text-[12px] font-semibold">{leg.selection_name ?? DASH}</span>
                                <span className="text-[10.5px] text-white/45 font-mono">{leg.market_type ?? DASH}</span>
                                <span className="ml-auto text-right">
                                    <span className="font-mono text-[13px] font-bold tabular-nums"
                                        data-testid="cr-opp-combo-gamba-vivo">
                                        {vivo == null
                                            ? <span className="text-orange-400">{DASH}</span>
                                            : fmtOdds(vivo)}
                                    </span>
                                    <span className="block font-mono text-[9.5px] text-white/40">
                                        proposta {fmtOdds(leg.price)}
                                    </span>
                                </span>
                                <span className="font-mono text-[11px] text-white/50 tabular-nums w-16 text-right">
                                    {fmtMoney(leg.size)}
                                </span>
                            </div>
                        );
                    })}
                </div>
            ) : (
                <div className="px-3 pt-2.5 pb-1 flex items-baseline gap-2.5 flex-wrap">
                    <span className={`text-[12px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
                        lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                    }`} data-testid="cr-opp-lato">
                        {lato === 'lay' ? 'Banca' : 'Punta'}
                    </span>
                    <span className="text-[13px] font-semibold" data-testid="cr-opp-selezione">
                        {p.selection_name ?? DASH}
                    </span>
                    <span className="text-[11px] text-white/45 font-mono" data-testid="cr-opp-mercato">
                        {p.market_type ?? DASH}
                    </span>
                    <span className="ml-auto text-right">
                        <span className="font-mono text-lg font-bold tabular-nums" data-testid="cr-opp-prezzo-vivo">
                            {vivo == null
                                ? <span className="text-orange-400">{DASH}</span>
                                : fmtOdds(vivo)}
                        </span>
                        {/* 24/09 — punta/banca migliori di adesso, con l'importo */}
                        <span className="block font-mono text-[10.5px] text-white/50" data-testid="cr-opp-book">
                            punta {fmtOdds(alMs.back)} ({alMs.backSize == null ? DASH : fmtMoney(alMs.backSize)})
                            {' · '}banca {fmtOdds(alMs.lay)} ({alMs.laySize == null ? DASH : fmtMoney(alMs.laySize)})
                        </span>
                        <span className="block font-mono text-[11px] text-white/40" data-testid="cr-opp-prezzo">
                            <TrendingUp className="w-3 h-3 inline mr-0.5" />
                            proposta a {fmtOdds(p.price_at_decision)}
                            {vivo != null && sc.tick != null && (
                                <span className={
                                    sc.tick === 0 ? 'text-white/40'
                                        : sc.tick > 0 ? 'text-emerald-400' : 'text-orange-400'
                                } data-testid="cr-opp-scarto">
                                    {' '}({vivo >= Number(p.price_at_decision) ? '+' : ''}
                                    {fmtNum(vivo - Number(p.price_at_decision), 2)} · {fmtTicks(sc.tick)}
                                    {' · '}{fmtNum(sc.pct, 2)} %)
                                </span>
                            )}
                        </span>
                        <span className="block text-[10px] text-white/40" data-testid="cr-opp-fonte">
                            {etaEFonte(alMs.istanteMs, alMs.fonte, nowMs)}
                        </span>
                    </span>
                </div>
            )}

            {p.riproposta_perche && (
                <div className="px-2.5 py-1.5 border-t border-secondary/30 bg-secondary/10 text-[11px] text-secondary"
                    data-testid="cr-opp-riproposta">
                    <strong>Torna:</strong> {p.riproposta_perche}
                </div>
            )}

            {/* ---- i numeri dei soldi ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 mt-2 border-t border-white/5">
                <Cella etichetta="Stake previsto" valore={fmtMoney(p.size)} testId="cr-opp-stake" />
                <Cella etichetta="Responsabilità"
                    valore={(ap?.liability ?? p.liability) == null ? DASH : fmtMoney(ap?.liability ?? p.liability)}
                    tono="cattivo" testId="cr-opp-liability" />
                <Cella etichetta="Abbinabile ora"
                    valore={abbinabile == null
                        ? (p.size_available == null ? DASH : `${fmtMoney(p.size_available)} (alla proposta)`)
                        : fmtMoney(abbinabile)}
                    tono={abbinabile != null && Number(p.size) <= abbinabile + 0.005 ? 'buono' : undefined}
                    testId="cr-opp-abbinabile" />
                <Cella etichetta="Valore atteso (EV)"
                    valore={NUM(ap?.ev ?? p.ev)} tono={Number(ap?.ev ?? p.ev) > 0 ? 'buono' : 'cattivo'}
                    testId="cr-opp-ev" />
            </div>

            {/* ---- i numeri del modello (24/09: P del mercato e vantaggio AL PREZZO DI ADESSO) ---- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5 border-t border-white/5">
                <Cella etichetta="P modello" valore={PCT(p.p_model)} testId="cr-opp-pmodel" />
                <Cella etichetta="P del mercato" valore={PCT(ap?.p_implicita ?? p.p_implied)} testId="cr-opp-pimplied" />
                <Cella etichetta="Vantaggio" valore={NUM(ap?.edge ?? p.edge)} testId="cr-opp-edge" />
                <Cella etichetta="Confidenza" valore={PCT(p.confidence)} testId="cr-opp-confidence" />
            </div>

            {/* ---- 24/09: c'e' ancora? semaforo coi criteri del modello ---- */}
            {semaforo && (
                <div className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider border-t ${
                    semaforo === 'SI' ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                        : semaforo === 'QUASI' ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
                            : 'bg-red-500/10 text-red-300 border-red-500/20'
                }`} data-testid="cr-opp-semaforo" data-semaforo={semaforo}>
                    opportunità ancora valida: {semaforo === 'SI' ? 'sì' : semaforo === 'QUASI' ? 'quasi' : 'no'}
                </div>
            )}

            {/* ---- perché, in italiano ---- */}
            <div className="px-3 py-2 text-[12px] text-white/70 border-t border-white/5">
                <b className="text-white">Perché:</b>{' '}
                <span data-testid="cr-opp-rationale">{p.rationale ?? 'nessuna spiegazione dal modello'}</span>
                <span className="block text-[11px] text-white/40 mt-0.5" data-testid="cr-opp-eta">
                    quote {etaS == null ? <span className="text-orange-400">età ignota</span> : fmtAge(etaS)}
                    {' · '}partirebbe in <b className={live ? 'text-orange-300' : 'text-white/60'}>{String(p.mode ?? 'paper').toUpperCase()}</b>
                </span>
            </div>

            {/* 24/09 — AVVISI, non blocchi: PIAZZA resta acceso, decide l'utente */}
            {avvisi.length > 0 && (
                <div className="px-3 py-2 bg-amber-500/10 text-amber-300 text-[12px] font-medium border-t border-amber-500/20"
                    data-testid="cr-opp-avviso">
                    {avvisi.map((a, i) => <div key={i}>⚠ {a}</div>)}
                </div>
            )}

            {/* ---- le due azioni ---- */}
            <div className="grid grid-cols-2 gap-px bg-white/5 border-t border-white/5">
                {armato ? (
                    <Button
                        onClick={() => void piazza()} disabled={inCorso}
                        className="rounded-none h-10 bg-orange-500 text-black hover:bg-orange-400 font-bold uppercase tracking-wider text-[12px]"
                        data-testid="cr-opp-conferma-live"
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Confermo: soldi veri</>}
                    </Button>
                ) : (
                    <Button
                        onClick={() => (live ? setArmato(true) : void piazza())}
                        disabled={inCorso}
                        className="rounded-none h-10 bg-emerald-600/80 text-white hover:bg-emerald-600 font-bold uppercase tracking-wider text-[12px] disabled:opacity-40"
                        data-testid="cr-opp-piazza"
                        title={avvisi.length ? `attenzione: ${avvisi.join(' · ')}` : 'invia l’ordine di apertura'}
                    >
                        {inCorso ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Piazza'}
                    </Button>
                )}
                <Button
                    variant="ghost" onClick={() => void rifiuta()} disabled={inCorso}
                    className="rounded-none h-10 text-white/60 hover:text-white uppercase tracking-wider text-[12px]"
                    data-testid="cr-opp-rifiuta"
                >
                    Rifiuta
                </Button>
            </div>

            <div className="px-3 py-1.5 text-[10.5px] text-white/40 bg-white/[0.02]">
                {armato
                    ? <span className="text-orange-300">Sono soldi veri: conferma per mandare l’ordine.</span>
                    : isCombo
                        ? <>Se rifiuti, questa combinazione non torna finché resta la stessa. PIAZZA manda TUTTE le
                            gambe insieme: se anche una sola non è più valida, non parte nessuna.</>
                        : <>Se rifiuti, questa opportunità non torna finché resta la stessa. Nessun ordine parte da solo.</>}
            </div>

            {live && (
                <div className="px-3 py-1.5 flex items-start gap-2 text-[11px] text-orange-300 bg-orange-500/5">
                    <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>Apertura con soldi veri: la responsabilità qui sopra è quella che rischi.</span>
                </div>
            )}
        </article>
    );
}

function Cella({ etichetta, valore, tono, testId }: {
    etichetta: string; valore: string; tono?: 'buono' | 'cattivo'; testId?: string;
}) {
    const cls = tono === 'buono' ? 'text-emerald-400' : tono === 'cattivo' ? 'text-orange-400' : '';
    return (
        <div className="bg-background/40 px-3 py-1.5">
            <div className="text-[9px] uppercase tracking-wider text-white/40">{etichetta}</div>
            <div className={`font-mono text-[13px] font-semibold tabular-nums ${cls}`} data-testid={testId}>
                {valore}
            </div>
        </div>
    );
}

export default SchedaPropostaOpportunita;
