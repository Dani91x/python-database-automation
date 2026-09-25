// ============================================================================
// PropostaUscitaMike.tsx — 25/09: L'USCITA CHE MIKE VORREBBE FARE, DA APPROVARE.
//
// «se disattivo il pulsante (TUTTO IN UI PER SINGOLO BOT), le uscite le
// gestisco io manualmente tramite l'apposita scheda» (utente, 25/09).
//
// Con «Uscite automatiche» SPENTO il motore di Mike non esegue le uscite
// discrezionali (green-up, uscita al fischio, cash out, uscita in perdita a
// modello): scrive la PROPOSTA nel contesto della partita
// (`mike_events.ctx.uscita_proposta`, `engine.gate_uscite`). Qui la si mostra
// con tutto quello che serve per decidere, e il bottone APPROVA manda la
// richiesta `approva_uscita` con la chiave della proposta e il contesto del
// clic (prezzo visto, età, fonte). L'uscita poi la esegue il bot ESATTAMENTE
// come la strategia la vuole in quel momento. Per chiudere a mano resta il
// «Chiudi» di sempre della riga di Mike.
//
// REGOLE: nessuna fetch nuova (l'evento arriva già con `ctx` e `live`),
// stessa freschezza della scheda (`feedFreshness`): con il feed fermo o
// ignoto il bottone si spegne, come `MikeMatchCard` (regola della scheda).
// ============================================================================
import { useContext, useState } from 'react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, DASH } from '@/lib/format';
import { etaQuoteS, feedFreshness, requestMike, roleLabel, type MikeBook, type MikeEvent } from '@/lib/mike';
import { useSecondTick } from '@/components/mike/useMikeClock';
import { sorgenteLadderAlMs } from '@/lib/localTransport';
import { prezzoDelLato, type PrezzoScheda } from '@/lib/schedaAlMs';
import { ChiusuraRigaContext } from './BottoneChiudiRiga';
import { EsitoAbbinamentoStriscia } from './EsitoAbbinamentoStriscia';
import { usePrezzoAlMs, type SorgenteLadder } from './usePrezzoAlMs';

/** La proposta come la scrive `engine.gate_uscite` (chiavi VERE). */
export interface PropostaUscitaMikeDati {
    chiave: string;
    categoria: string;
    ciclo: number;
    stato: string;
    stato_voluto: string;
    motivo: string;
    close_reason: string | null;
    ordini: { ruolo: string; mercato: string; selezione: string; lato: string; prezzo: number | null; size: number | null }[];
    bloccabile: number | null;
    urgente: boolean;
    minuto: number | null;
    gol: number | null;
    decided_at: number;
    proposed_at: number;
}

const CATEGORIA: Record<string, string> = {
    green_pre: 'green-up pre-partita',
    ko_green: 'uscita al fischio',
    chiusura: 'cash out della posizione',
    reentry_green: 'uscita del re-ingresso',
};

export function propostaDi(ev: MikeEvent): PropostaUscitaMikeDati | null {
    const p = (ev.ctx ?? {})['uscita_proposta'];
    if (p == null || typeof p !== 'object' || Array.isArray(p)) return null;
    const d = p as Partial<PropostaUscitaMikeDati>;
    if (typeof d.chiave !== 'string' || !d.chiave) return null;
    return d as PropostaUscitaMikeDati;
}

/** B17 (25/09) — la chiave del seguito di un'uscita di Mike (per partita + proposta). */
export function chiaveUscitaMike(eventId: string, chiaveProposta: string): string {
    return `mike:uscita:${eventId}:${chiaveProposta}`;
}

/**
 * D7 (25/09) — gli id VERI di un ordine proposto. La proposta di `engine.
 * gate_uscite` parla per simboli (mercato `OU35`, selezione `UNDER`); gli id
 * Betfair sono sulla STESSA riga della partita, scritti dal servizio dal feed
 * (`mike_events.markets[mercato].market_id` e `ctx.selections["OU35|UNDER"]`,
 * `Betfair/mike/service.py`). Se un giorno la proposta li portera' da sola
 * (`market_id`/`selection_id` sull'ordine), vincono quelli. Mai un id inventato:
 * senza, la scheda resta sul feed della partita e lo dichiara.
 */
export function idsOrdineMike(
    ev: Pick<MikeEvent, 'markets' | 'ctx'>,
    o: { mercato: string; selezione: string; market_id?: unknown; selection_id?: unknown } | null | undefined,
): { marketId: string | null; selectionId: number | null } {
    if (!o) return { marketId: null, selectionId: null };
    const midProp = typeof o.market_id === 'string' && o.market_id ? o.market_id : null;
    const sidProp = typeof o.selection_id === 'number' && Number.isFinite(o.selection_id) ? o.selection_id : null;
    const mid = midProp ?? ev.markets?.[o.mercato]?.market_id ?? null;
    const sels = ((ev.ctx as { selections?: Record<string, unknown> } | null)?.selections) ?? {};
    const grezzo = sels[`${o.mercato}|${o.selezione}`];
    const sid = sidProp ?? (typeof grezzo === 'number' && Number.isFinite(grezzo) ? grezzo : null);
    return { marketId: mid ? String(mid) : null, selectionId: sid };
}

/** Il book della partita (mike_events.live, tick di 1 s) come ripiego della scheda al ms. */
function ripiegoDaBook(bk: MikeBook | undefined, istanteMs: number | null): PrezzoScheda | null {
    if (!bk) return null;
    return {
        back: bk.best_back ?? null, backSize: Number.isFinite(bk.back_size) ? bk.back_size : null,
        lay: bk.best_lay ?? null, laySize: Number.isFinite(bk.lay_size) ? bk.lay_size : null,
        istanteMs, fonte: 'scanner', statoMercato: bk.status ? String(bk.status).toUpperCase() : null,
    };
}

const SORGENTE_DI_SERIE: SorgenteLadder = (sport) => sorgenteLadderAlMs(sport);

type OrdineProposto = PropostaUscitaMikeDati['ordini'][number];

/** Un ordine proposto AL MS (gli ordini dopo il primo: il primo lo segue gia'
 *  la scheda, una sottoscrizione sola per mercato e selezione). */
function OrdineMikeAlMs({ ev, o, istanteFeedMs, sorgente, testId }: {
    ev: MikeEvent; o: OrdineProposto; istanteFeedMs: number | null;
    sorgente: SorgenteLadder | null; testId: string;
}) {
    const { marketId, selectionId } = idsOrdineMike(ev, o);
    const lato = o.lato === 'back' || o.lato === 'lay' ? o.lato : null;
    const bk = (ev.live?.books ?? {})[`${o.mercato}|${o.selezione}`];
    const { prezzo } = usePrezzoAlMs({
        sorgente, sport: 'calcio', marketId, selectionId, lato,
        ripiego: ripiegoDaBook(bk, istanteFeedMs),
    });
    return <OrdineMikeRiga o={o} prezzo={prezzo} testId={testId} />;
}

/** «ruolo lato size @ prezzo (ora back / lay, fonte)». */
function OrdineMikeRiga({ o, prezzo, testId }: { o: OrdineProposto; prezzo: PrezzoScheda; testId: string }) {
    const fonte = prezzo.fonte === 'canale' || prezzo.fonte === 'db' ? 'al ms' : 'feed della partita';
    return (
        <span data-testid={testId} data-fonte={prezzo.fonte ?? ''}>
            {`${roleLabel(o.ruolo)} ${o.lato} ${o.size == null ? DASH : fmtMoney(o.size)} @ ${fmtOdds(o.prezzo)}`
                + ` (ora ${prezzo.back == null && prezzo.lay == null ? DASH
                    : `${fmtOdds(prezzo.back)} / ${fmtOdds(prezzo.lay)}`}, ${fonte})`}
        </span>
    );
}

export function PropostaUscitaMike({ ev, testId = 'cr-mike-proposta', sorgenteLadder = SORGENTE_DI_SERIE }: {
    ev: MikeEvent; testId?: string;
    /** D7 (25/09) — la sorgente del ladder al ms (test: una finta; null = solo il feed) */
    sorgenteLadder?: SorgenteLadder | null;
}) {
    const prop = propostaDi(ev);
    const adesso = useSecondTick(prop != null);
    // D7 (25/09) — il prezzo AL MS del primo ordine proposto (quello che va
    // nel contesto del clic): ladder del mercato vero, ripiego sul feed della
    // partita dichiarato. Hook chiamato SEMPRE (anche senza proposta).
    const o0 = prop?.ordini?.[0];
    const ids0 = idsOrdineMike(ev, o0);
    const lato0 = o0 && (o0.lato === 'back' || o0.lato === 'lay') ? o0.lato : null;
    const etaFeed = prop ? etaQuoteS(ev.live ?? {}, adesso) : null;
    const istanteFeedMs = etaFeed == null ? null : adesso - etaFeed * 1000;
    const { prezzo: alMs0 } = usePrezzoAlMs({
        sorgente: prop ? sorgenteLadder : null, sport: 'calcio',
        marketId: ids0.marketId, selectionId: ids0.selectionId, lato: lato0,
        ripiego: o0 ? ripiegoDaBook((ev.live?.books ?? {})[`${o0.mercato}|${o0.selezione}`], istanteFeedMs) : null,
    });
    const [esito, setEsito] = useState<string | null>(null);
    const [inVolo, setInVolo] = useState(false);
    // B17 (25/09) — dopo APPROVA la proposta sparisce (il motore la consuma):
    // l'esito dell'uscita resta qui, seguito fino all'abbinamento delle gambe
    const api = useContext(ChiusuraRigaContext);
    const prefisso = `mike:uscita:${ev.event_id}:`;
    const esitiEvento = (api?.esitiOrdini ?? []).filter((e) => e.clic.chiave.startsWith(prefisso));
    const striscie = esitiEvento.map((e) => (
        <EsitoAbbinamentoStriscia key={e.clic.chiave} seguito={e} testId={`${testId}-ordine`} />
    ));
    if (prop == null) return striscie.length ? <div data-testid={`${testId}-esiti`}>{striscie}</div> : null;

    const live = ev.live ?? {};
    const eta = etaQuoteS(live, adesso);
    const fresh = feedFreshness(eta);
    const spento = fresh.tone === 'stale' || fresh.tone === 'unknown' || inVolo;
    const daDecisioneS = Math.max(0, Math.round(adesso / 1000 - Number(prop.decided_at)));
    const bloccabileOra = typeof live.cashout?.net === 'number' ? live.cashout.net : null;

    const approva = async () => {
        setInVolo(true); setEsito(null);
        const o = prop.ordini[0];
        // D7 (25/09) — il prezzo visto e' quello A VIDEO: al ms dal ladder del
        // mercato vero se c'e', altrimenti il feed della partita (dichiarato)
        const visto = o ? prezzoDelLato(alMs0, o.lato === 'lay' ? 'lay' : 'back') : null;
        const alMsVero = alMs0.fonte === 'canale' || alMs0.fonte === 'db';
        const clicMs = Date.now();
        try {
            const requestId = await requestMike('approva_uscita', {
                event_id: ev.event_id, bot: 'mike', mode: ev.mode, chiave: prop.chiave,
                contesto: {
                    prezzo_visto: visto,
                    // B17 (25/09) — il prezzo del SEGNALE (quello della decisione della strategia)
                    prezzo_segnale: o?.prezzo ?? null,
                    eta_ms: alMsVero
                        ? (alMs0.istanteMs == null ? null : Math.max(0, clicMs - alMs0.istanteMs))
                        : (eta == null ? null : Math.round(eta * 1000)),
                    fonte: alMsVero ? `ladder al ms (${alMs0.fonte})` : 'mike_events.live (get_mike_state)',
                    market_id: ids0.marketId, selection_id: ids0.selectionId,
                    clic_ms: clicMs,
                },
            });
            setEsito('approvazione inviata: parte al prossimo giro del bot');
            const lato = o?.lato === 'back' || o?.lato === 'lay' ? o.lato : null;
            api?.seguiClic?.({
                chiave: chiaveUscitaMike(ev.event_id, prop.chiave), bot: 'mike', tipo: 'chiusura',
                etichetta: `Mike · uscita (${CATEGORIA[prop.categoria] ?? prop.categoria})`,
                requestId: typeof requestId === 'number' ? requestId : Number(requestId) || null,
                tradeIdApertura: null, eventId: ev.event_id, lato,
                prezzoVisto: typeof visto === 'number' ? visto : null,
                prezzoSegnale: o?.prezzo ?? null, contesto: null,
                modo: ev.mode === 'live' || ev.mode === 'paper' ? ev.mode : null,
                clicMs,
                // le gambe NUOVE di Mike sulla partita coi ruoli proposti sono l'uscita
                ruoli: prop.ordini.map((x) => x.ruolo),
            });
        } catch (e) {
            setEsito(`approvazione non inviata: ${e instanceof Error ? e.message : String(e)}`);
        } finally { setInVolo(false); }
    };

    return (
        <div className={`rounded border px-2.5 py-2 space-y-1 ${prop.urgente
            ? 'border-red-500/40 bg-red-500/10' : 'border-amber-400/40 bg-amber-400/10'}`}
            data-testid={testId}>
            <div className="flex items-center justify-between gap-2">
                <span className="text-[10.5px] font-semibold text-amber-200" data-testid={`${testId}-titolo`}>
                    Mike vorrebbe uscire: {CATEGORIA[prop.categoria] ?? prop.categoria}
                    {prop.urgente ? ' (in perdita)' : ''}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${fresh.cls}`}>{fresh.label}</span>
            </div>
            <div className="text-[10.5px] text-white/70" data-testid={`${testId}-motivo`}>{prop.motivo}</div>
            <div className="text-[10.5px] font-mono text-white/80" data-testid={`${testId}-ordini`}>
                {prop.ordini.map((o, i) => (
                    <span key={`${o.ruolo}-${i}`}>
                        {i > 0 ? ' + ' : ''}
                        {i === 0
                            ? <OrdineMikeRiga o={o} prezzo={alMs0} testId={`${testId}-ordine-al-ms-${i}`} />
                            : <OrdineMikeAlMs ev={ev} o={o} istanteFeedMs={istanteFeedMs}
                                sorgente={sorgenteLadder} testId={`${testId}-ordine-al-ms-${i}`} />}
                    </span>
                ))}
            </div>
            {/* D7 (25/09) — come parte l'uscita al clic (non la decide la scheda) */}
            <div className="text-[10px] text-white/55" data-testid={`${testId}-esecuzione`}>
                al clic: il bot esce a mercato con la sua macchina d’uscita (prezzi e size di quel
                momento), come la strategia la vuole; dopo il clic qui sotto il prezzo reale di abbinamento
            </div>
            <div className="text-[10.5px] text-white/60" data-testid={`${testId}-numeri`}>
                chiudendo ora {bloccabileOra == null ? DASH : fmtMoney(bloccabileOra, { signed: true })}
                {' · '}alla decisione {prop.bloccabile == null ? DASH : fmtMoney(prop.bloccabile, { signed: true })}
                {' · '}deciso {daDecisioneS} s fa
                {prop.minuto != null ? ` · ${prop.minuto}′` : ''}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
                <Button type="button" size="sm" disabled={spento}
                    onClick={() => void approva()}
                    data-testid={`${testId}-approva`}
                    title={spento ? 'feed fermo o ignoto: non si approva su prezzi vecchi' : 'il bot esegue questa uscita al prossimo giro'}
                    className="h-6 px-2 text-[10px] uppercase tracking-wider bg-amber-600/80 hover:bg-amber-600 text-white">
                    approva uscita
                </Button>
                <span className="text-[10px] text-white/40">oppure chiudi a mano con «Chiudi» di Mike</span>
            </div>
            {esito && <div className="text-[10px] text-white/60" data-testid={`${testId}-esito`}>{esito}</div>}
            {striscie}
        </div>
    );
}

export default PropostaUscitaMike;
