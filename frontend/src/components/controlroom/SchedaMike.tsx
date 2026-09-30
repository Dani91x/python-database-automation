// ============================================================================
// SchedaMike.tsx — I DATI DI MODELLO DI MIKE nella Control Room (17/09).
//
// PERCHÉ. Nella sua pagina, Mike mostra la carta più ricca dell'applicazione:
// P(4 gol) del mercato contro quella del modello, i gol attesi (λ) e da dove
// arrivano, le quote Under 3.5 / Over 4.5 di adesso, il prezzo d'ingresso e
// quello al fischio d'inizio con la deriva in tick, i cicli, il P&L per numero
// di gol, il valore del cash out e la sua soglia. Nella Control Room di quella
// partita si vedevano quattro numeri generici. Non mancava un dato: mancava il
// montaggio — `get_mike_state()` porta già tutto questo dentro `events[].live`
// e `events[].dossier`, ed è la stessa lettura che la pagina fa comunque.
//
// REGOLE: **nessuna fetch nuova** (l'evento arriva dall'`useControlRoom`),
// nessuna formula nuova (le etichette dei mercati e i numeri vengono da
// `lib/mike.ts`), e un valore che non c'è è `—`, mai zero.
//
// FRESCHEZZA DEL FEED (18/09, priorità massima — money-critical). La pagina
// originale di Mike porta un badge che TICKA ogni secondo (`MikeMatchCard.tsx`
// ~riga 521: `etaQuoteS`/`feedFreshness`, nato dal difetto certificato il
// 13/09: «si poteva chiudere su prezzi vecchi di minuti credendoli di
// adesso»). Qui in Control Room lo stesso `ev.live` (quindi `feed_age_s`)
// arriva senza nessun indicatore di età: un trader poteva leggere "Under 3.5
// back 1.85" e agire come se fosse il prezzo di ADESSO. Si monta la STESSA
// funzione, con le STESSE soglie (≤5s verde, ≤20s ambra, oltre FEED FERMO),
// nessuna nuova lettura né una seconda formula. Su una partita TERMINALE
// (`MIKE_TERMINAL_STATES`: SETTLED/ERROR/SKIPPED) il feed non arriva più: si
// dichiara "partita chiusa", MAI il rosso "FEED FERMO" — falso allarme
// (stesso comportamento di `MikeMatchCard.tsx:633-639`).
//
// AZIONI DI CHIUSURA: verificato (18/09) che la Control Room oggi non porta
// NESSUN comando che muove ordini di Mike (cash out/flatten sono solo di
// Safe, via `AzioniPartita`/`CashOutPartita`: grep mirato, zero occorrenze di
// "mike" in quei due file). Non c'è quindi nessun pulsante da proteggere qui
// oggi. Se in futuro un comando Mike venisse aggiunto a questa scheda, deve
// disabilitarsi esattamente come `MikeMatchCard.tsx:564-567`
// (`freshness.tone === 'stale' || 'unknown'`), mai una condizione nuova.
// ============================================================================
import { fmtMoney, fmtNum, fmtOdds, fmtPct, DASH } from '@/lib/format';
import { pnlClass, T } from '@/lib/tradeStatus';
import { etaQuoteS, feedFreshness, MIKE_TERMINAL_STATES, roleLabelGamba, type MikeEvent } from '@/lib/mike';
import { useSecondTick } from '@/components/mike/useMikeClock';
import { cycleText } from '@/components/mike/MikeMatchCard';
import { PropostaUscitaMike } from './PropostaUscitaMike';
import { EsitoChiusuraMike } from './EsitoChiusuraMike';
import { MarchioSoldi } from './MarchioSoldi';

/** Una coppia «etichetta / valore», il mattone di tutta la scheda. */
function Voce({ label, children, title, testId }: {
    label: string; children: React.ReactNode; title?: string; testId?: string;
}) {
    return (
        <div className="flex items-baseline gap-1.5" data-testid={testId} title={title}>
            <span className="text-[10px] uppercase tracking-wider text-white/35">{label}</span>
            <span className="text-[11px] font-mono text-white/80">{children}</span>
        </div>
    );
}

/** Da dove arrivano i gol attesi: `none` vuol dire che il bot è CIECO sul
 *  modello e decide su tabella empirica e mercato. Va detto, non nascosto. */
const FONTE_LAMBDA: Record<string, string> = {
    fixture: 'statistiche partita',
    pre_ko_odds: 'quote pre-partita',
    live_ou: 'quote in gioco',
    none: 'nessuna (bot cieco sul modello)',
};

function num(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * La scheda di UNA partita di Mike. `ev` è la riga che `get_mike_state()`
 * pubblica: non si legge niente d'altro.
 */
export function SchedaMike({ ev, testId = 'cr-mike' }: { ev: MikeEvent; testId?: string }) {
    const live = ev.live ?? {};
    const dos = ev.dossier ?? {};
    const books = live.books ?? {};
    const u35 = books['OU35|UNDER'] ?? books['OU35'] ?? null;
    const o45 = books['OU45|OVER'] ?? books['OU45'] ?? null;
    // 30/09 (B2, A3) - la banca della copertura di serie e il re-ingresso stanno
    // sull'Under 4,5 (`engine.py` `_place("over_cover", OU45, UNDER, "lay")`,
    // `_place("reentry", OU45, UNDER, "back")`): chiave vera del servizio
    const u45 = books['OU45|UNDER'] ?? null;
    // la forma della copertura la scheda la conosce solo se la partita ha gia'
    // una gamba di copertura (i parametri non arrivano qui): altrimenti non la dice
    const gambaCopertura = (ev.positions ?? []).find((g) => g.role === 'over_cover' && !g.archived) ?? null;
    const coperturaDiQuesta = gambaCopertura
        ? ` · su questa partita: ${roleLabelGamba(gambaCopertura)}` : '';
    const cash = live.cashout ?? null;
    const perGol = live.pnl_totale_by_total ?? live.pnl_by_total ?? null;
    const lamHome = num(dos.lambda_home);
    const lamAway = num(dos.lambda_away);

    // CERT. 13/09 — l'età si calcola ADESSO e cresce da sola (stesso tick
    // condiviso della pagina Mike): un valore congelato alla scrittura del
    // servizio poteva restare verde per sempre.
    const terminal = MIKE_TERMINAL_STATES.includes(ev.state);
    const adesso = useSecondTick(!terminal);
    const etaQuote = etaQuoteS(live, adesso);
    const freshness = feedFreshness(etaQuote);

    return (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2.5 py-2 space-y-1.5"
            data-testid={testId}>
            <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase tracking-wider text-white/40">
                    Mike — modello e mercato su questa partita
                </div>
                {/* su una partita chiusa il feed non arriva più: dirlo, mai il
                    rosso "FEED FERMO", che sarebbe un falso allarme */}
                {terminal
                    ? <span className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-600/30 text-slate-300 border-slate-500/40"
                        data-testid={`${testId}-feed-age`}>
                        partita chiusa
                    </span>
                    : <span className={`text-[10px] px-1.5 py-0.5 rounded border ${freshness.cls}`}
                        data-testid={`${testId}-feed-age`}
                        title="età delle quote Under/Over di questa partita: sopra 20 s il servizio non le userebbe per chiudere">
                        {freshness.label}
                    </span>}
            </div>

            {/* 25/09 — uscite MANUALI: l'uscita che Mike vorrebbe fare, da
                approvare (compare solo se c'e' una proposta viva) */}
            <PropostaUscitaMike ev={ev} testId={`${testId}-proposta`} />
            {/* 29/09 (M7.2) — com'e' finita la chiusura: stesso componente della pagina di Mike */}
            <EsitoChiusuraMike ev={ev} testId={`${testId}-esito-chiusura`} />

            {/* ── P(4 gol ESATTI): il numero su cui Mike decide (engine.py
                `hold_expectation`: 4 gol esatti = l'unico esito in cui perdono
                entrambe le linee). 26/09 (F-13): il title diceva «4+ gol» ma il
                numero e' P(esattamente 4) = P(O3.5) − P(O4.5) (feed.py `implied_p4`):
                letto come «4 o più» sottostimava il rischio dell'Under 3.5. ── */}
            <div className="flex items-baseline gap-x-3 gap-y-1 flex-wrap">
                <Voce label="P(4 gol esatti) mercato" testId={`${testId}-p4-mercato`}
                    title="probabilità di ESATTAMENTE 4 gol (perdono l’Under 3,5 e la copertura) implicita nelle quote di adesso: P(Over 3.5) − P(Over 4.5)">
                    {fmtPct(num(live.p4_market))}
                </Voce>
                <Voce label="modello" testId={`${testId}-p4-modello`}
                    title="probabilità di ESATTAMENTE 4 gol secondo il modello del bot">
                    {fmtPct(num(live.p4_model))}
                </Voce>
                {num(dos.p4_pre) != null && (
                    <Voce label="pre-partita" testId={`${testId}-p4-pre`}
                        title="P(esattamente 4 gol) calcolata prima del calcio d'inizio">
                        {fmtPct(num(dos.p4_pre))}
                    </Voce>
                )}
            </div>

            {/* ── gol attesi e la loro FONTE ── */}
            <div className="flex items-baseline gap-x-3 gap-y-1 flex-wrap">
                <Voce label="gol attesi" testId={`${testId}-lambda`}
                    title="λ casa e λ trasferta: i gol attesi che alimentano il modello">
                    {lamHome == null && lamAway == null ? DASH : (
                        <>{fmtNum(lamHome, 2)}
                            <span className="text-white/30"> · </span>
                            {fmtNum(lamAway, 2)}</>
                    )}
                </Voce>
                <span className="text-[10px] text-white/35" data-testid={`${testId}-lambda-fonte`}
                    title="da dove arrivano i gol attesi: 'nessuna' vuol dire che il modello è cieco">
                    fonte {FONTE_LAMBDA[String(live.lambda_source ?? '')] ?? (live.lambda_source ?? DASH)}
                </span>
            </div>

            {/* ── le due linee che Mike opera ── */}
            <div className="flex items-baseline gap-x-3 gap-y-1 flex-wrap">
                <Voce label="Under 3.5" testId={`${testId}-u35`}
                    title="miglior BACK / miglior LAY di adesso sulla linea 3.5">
                    {fmtOdds(u35?.best_back ?? null)}<span className="text-white/25"> / </span>{fmtOdds(u35?.best_lay ?? null)}
                </Voce>
                <Voce label="Over 4.5" testId={`${testId}-o45`}
                    title={`miglior BACK / miglior LAY di adesso sull’Over 4.5 (linea 4,5): qui va la copertura solo nella forma «punta Over 4.5»; la chiusura della copertura è una banca Over 4.5${coperturaDiQuesta}`}>
                    {fmtOdds(o45?.best_back ?? null)}<span className="text-white/25"> / </span>{fmtOdds(o45?.best_lay ?? null)}
                </Voce>
                <Voce label="Under 4.5" testId={`${testId}-u45`}
                    title={`miglior BACK / miglior LAY di adesso sull’Under 4.5 (linea 4,5): qui va la copertura nella forma «banca Under 4.5» e il re-ingresso dopo un gol${coperturaDiQuesta}`}>
                    {fmtOdds(u45?.best_back ?? null)}<span className="text-white/25"> / </span>{fmtOdds(u45?.best_lay ?? null)}
                </Voce>
                {num(live.total_matched) != null && (
                    <Voce label="volume" testId={`${testId}-volume`} title="euro già scambiati sul mercato">
                        {fmtMoney(num(live.total_matched))}
                    </Voce>
                )}
            </div>

            {/* ── ingresso, fischio d'inizio e deriva ── */}
            <div className="flex items-baseline gap-x-3 gap-y-1 flex-wrap">
                <Voce label="ingresso" testId={`${testId}-entry`}
                    title="prezzo del primo back Under 3.5 della partita">
                    {fmtOdds(ev.entry_price_initial)}
                </Voce>
                <Voce label="al fischio" testId={`${testId}-ko`}
                    title="prezzo Under 3.5 registrato al calcio d'inizio">
                    {fmtOdds(num(live.ko_price_under))}
                </Voce>
                {num(live.ko_drift_ticks) != null && (
                    <span className={`text-[10px] font-mono ${
                        (num(live.ko_drift_ticks) ?? 0) < 0 ? 'text-emerald-400' : 'text-red-400'
                    }`} data-testid={`${testId}-ko-drift`}
                        title="tick fra il nostro ingresso e il prezzo al fischio: NEGATIVO = prezzo sceso, a nostro favore su un back Under">
                        {fmtNum(num(live.ko_drift_ticks), 0)} tick
                    </span>
                )}
                {/* 30/09 (B2, M9) - numerato come la pagina di Mike (`cycleText`
                    della card: `cycle_no` = cicli gia' chiusi, il ciclo in corso
                    e' il successivo). Il massimo per partita e' un parametro
                    che la scheda non riceve: non lo si scrive. */}
                <Voce label="ciclo" testId={`${testId}-cicli`}
                    title={terminal
                        ? 'partita chiusa: cicli completati sulla partita'
                        : 'ciclo in corso (il primo è 1, come nella pagina di Mike) e cicli già chiusi sulla partita'}>
                    {cycleText(ev.cycle_no, null, terminal).value}
                    {terminal
                        ? <span className="text-white/35"> usati</span>
                        : live.cicli_chiusi != null && <span className="text-white/35"> · {live.cicli_chiusi} chiusi</span>}
                </Voce>
            </div>

            {/* ── soldi: liability, bloccato, cash out (30/09 B2, M10: la parola
                del glossario, `T.openLiability`, come la card e i KPI) ── */}
            <div className="flex items-baseline gap-x-3 gap-y-1 flex-wrap">
                {/* W_B2 (30/09, M1): la NETTA del servizio, detta tale e marcata
                    BOT (la scheda della partita mostra accanto la LORDA delle righe) */}
                <Voce label={`${T.openLiability} (netta)`} testId={`${testId}-liability`}
                    title="liability NETTA della partita calcolata dal servizio di Mike: le gambe che si compensano (copertura, green-up) sono già nettate">
                    {fmtMoney(num(live.liability))}
                    {num(live.liability) != null && <>{' '}<MarchioSoldi fonte="bot" testId={`${testId}-liability-fonte`} /></>}
                </Voce>
                <Voce label="bloccato" testId={`${testId}-locked`} title="P&L già bloccato sulla partita">
                    <span className={pnlClass(num(live.locked))}>
                        {num(live.locked) == null ? DASH : fmtMoney(num(live.locked), { signed: true })}
                    </span>
                </Voce>
                {/* 30/09 (B2, A9) - `complete=false` = una selezione ancora VIVA
                    non ha prezzo e il netto del servizio la ESCLUDE
                    (`engine.cashout_value`): la cifra sarebbe una somma monca.
                    Come la card di Mike: nessuna cifra. */}
                {cash && (cash.complete ? (
                    <Voce label="cash out" testId={`${testId}-cashout`}
                        title="valore NETTO di chiusura pubblicato dal servizio, con la soglia oltre la quale chiude da solo">
                        <span className={pnlClass(cash.net)}>{fmtMoney(cash.net, { signed: true })}</span>
                        {cash.pct != null && <span className="text-white/35"> · {fmtPct(cash.pct / 100)}</span>}
                        {cash.target_pct != null && (
                            <span className="text-white/25" title="soglia di chiusura automatica"> / soglia {fmtPct(cash.target_pct / 100)}</span>
                        )}
                    </Voce>
                ) : (
                    <Voce label="cash out" testId={`${testId}-cashout`}
                        title="una linea ancora in gioco non ha prezzo sul book: il valore di chiusura di tutta la partita non si può calcolare">
                        <span className="text-amber-300" data-testid={`${testId}-cashout-parziale`}>
                            non calcolabile (manca il prezzo di una linea)
                        </span>
                    </Voce>
                ))}
            </div>

            {/* ── come finisce, per numero di gol ── */}
            {perGol && Object.keys(perGol).length > 0 && (
                <div className="flex items-baseline gap-x-2 gap-y-1 flex-wrap pt-1 border-t border-white/8"
                    data-testid={`${testId}-per-gol`}
                    title="come finisce la PARTITA INTERA (cicli chiusi compresi) per numero di gol totali, netto commissione">
                    <span className="text-[10px] uppercase tracking-wider text-white/35">se finisce con</span>
                    {Object.keys(perGol).sort((a, b) => Number(a) - Number(b)).map((k) => (
                        <span key={k} className="text-[10px] font-mono" data-testid={`${testId}-gol-${k}`}>
                            <span className="text-white/40">{k} gol </span>
                            <span className={pnlClass(perGol[k])}>{fmtMoney(perGol[k], { signed: true })}</span>
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}
