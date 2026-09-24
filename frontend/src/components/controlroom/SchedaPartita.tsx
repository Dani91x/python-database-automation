// ============================================================================
// SchedaPartita.tsx — LA RIGA DI UNA PARTITA nel banco operativo.
//
// Non inventa niente: **monta insieme cose che il software ha già** —
//   · `BetfairMediaButtons`  video e statistiche ufficiali Betfair (lo stesso
//                            componente di Mike, Omega, Safe e Tennis);
//   · il terminale di trading su QUESTA partita, con la rotta che usano già
//     Omega (`/segui-live?event=…`) e la lista tennis (`/tennis/terminal?…`);
//   · `fmtMoney` / `fmtOdds` / `fmtAge` del design system, mai un formato nuovo.
//
// COSA AGGIUNGE, e serve a un trader:
//  1. **il target di QUESTA partita e quanto ne manca** — la barra è un metro,
//     non un grafico: dice una grandezza, e basta;
//  2. **i tre bot come simboli cliccabili**: acceso = ha operato qui, e il clic
//     apre COSA ha fatto, riga per riga, con prezzo, importo ed esito;
//  3. **lo stato del prezzo** distinto fra «fermo» (il mercato non si muove: è
//     il prezzo corrente) e «vecchio» (non sappiamo cosa fa il mercato).
//
// REGOLE DEL DESIGN SYSTEM rispettate alla lettera: i soldi passano da
// `fmtMoney`, le quote da `fmtOdds`, nessuno stato in inglese sotto gli occhi
// del trader, e un valore che non c'è è `—`, mai `0,00 €`.
// ============================================================================
import { useState } from 'react';
import { Circle } from 'lucide-react';
import { AzioniPartita } from '@/components/controlroom/AzioniPartita';
import { CashOutPartita } from '@/components/controlroom/CashOutPartita';
import { fmtMoney, fmtOdds, fmtAge, fmtTime, DASH } from '@/lib/format';
import { isErrorRow, isSettled } from '@/lib/eventGroups';
import type { StatoChiusuraEvento } from '@/lib/chiusuraUtente';
import { pnlClass } from '@/lib/tradeStatus';
import { RigaOperazione } from '@/components/controlroom/DettaglioRigaView';
import { trovaEsitoCashOut } from '@/components/controlroom/trovaEsitoUscita';
import {
    BOT_LABEL, BOT_TENNIS, isBotTennis, type Bot, type Freschezza, type PartitaGiornata, type Sport, type StatoQuote,
} from '@/lib/controlRoom';
import type { OperazionePartita } from '@/components/controlroom/useControlRoom';
import { SchedaMike } from '@/components/controlroom/SchedaMike';
import { marketStatusMeta, type MikeEvent } from '@/lib/mike';
import { useTennisVivo, nomeSelezioneTennis } from '@/components/controlroom/useTennisVivo';

const BOT_SIGLA: Record<Bot, string> = {
    omega: 'Ω', safe: 'S', mike: 'M', scalper: 'Sc',
    tennis_scalper: 'Sc', tennis_pro: 'Pr', tennis_flb: 'Fl', tennis_swing: 'Sw',
};
const BOT_CLS: Record<Bot, string> = {
    omega: 'text-primary border-primary/40 bg-primary/10',
    safe: 'text-secondary border-secondary/40 bg-secondary/10',
    mike: 'text-teal-300 border-teal-400/40 bg-teal-400/10',
    // 24/09 - lo scalper calcio: compare solo sulle partite di calcio, quindi
    // la sigla 'Sc' non si confonde con quella dello scalper tennis
    scalper: 'text-violet-300 border-violet-400/40 bg-violet-400/10',
    // i quattro del tennis: una famiglia di colore sola (ambra), perche' sono
    // quattro bot dello stesso sport e si leggono insieme
    tennis_scalper: 'text-amber-300 border-amber-400/40 bg-amber-400/10',
    tennis_pro: 'text-amber-200 border-amber-300/40 bg-amber-300/10',
    tennis_flb: 'text-orange-300 border-orange-400/40 bg-orange-400/10',
    tennis_swing: 'text-yellow-300 border-yellow-400/40 bg-yellow-400/10',
};

/**
 * QUALI BOT PUO' AVER TOCCATO QUESTA PARTITA. Su una partita di tennis non
 * esistono Omega e Mike (sono del calcio) e i quattro bot tennis non esistono
 * sul calcio: mostrare simboli sempre spenti insegna a non guardarli. Safe
 * c'e' in tutti e due, perche' ha una strategia per ciascuno sport.
 */
export function botDiSport(sport: Sport): Bot[] {
    return sport === 'tennis' ? ['safe', ...BOT_TENNIS] : ['omega', 'safe', 'mike', 'scalper'];
}

/** «fermo» NON è un allarme: è un mercato che non si muove, e quel prezzo è
 *  quello corrente. Solo «vecchio» e «ignoto» meritano l'arancione.
 *  Esportate (18/09, secondo giro): `SchedaPreMatch.tsx` le riusa per le
 *  quote pre-match — stesso concetto, stessa parola, stesso colore. */
export const QUOTE_CLS: Record<StatoQuote, string> = {
    fresco: 'text-emerald-400',
    fermo: 'text-white/50',
    vecchio: 'text-orange-400',
    ignoto: 'text-orange-400',
};
export const QUOTE_TESTO: Record<StatoQuote, (s: string) => string> = {
    fresco: (s) => s,
    fermo: (s) => `fermo ${s}`,
    vecchio: (s) => `vecchio ${s}`,
    ignoto: () => 'età ignota',
};

/** Stessa palette di `QUOTE_CLS` (colore solo come segnale, §3.3 regola 5):
 *  `fresca` non merita nessun accento, `lenta`/`vecchia`/`ignota` sì. */
const FRESCHEZZA_CLS: Record<Freschezza, string> = {
    fresca: 'text-emerald-400',
    lenta: 'text-white/50',
    vecchia: 'text-orange-400',
    ignota: 'text-orange-400',
};

/**
 * TASK 2 (18/09) — IL TENNIS VIVO della partita: punto, chi serve, tie-break,
 * stato del mercato e l'età del dato, dalla STESSA `tennis_live_now` che la
 * pagina tennis già usa (`useTennisVivo`, una sottoscrizione condivisa per
 * evento). Monta SOLO quando c'è una posizione aperta su questa partita
 * (`abilitato`): niente sottoscrizione, niente rendering, per non aprire un
 * canale su ogni card tennis del giorno (regola del respiro DB, 13/09).
 *
 * SECONDO GIRO (18/09, REPERTO 1 del coordinatore) — CORREZIONE. `sets`/`games`
 * sono GIÀ nella testata (`p.punteggio`, via `StatoPill`): NON è un dato
 * "calcio-centrico" ereditato per sbaglio, è il punteggio TENNIS vero,
 * scritto dallo stesso scanner Safe Strategy nel campo tennis-nativo
 * `ev["sets"]`/`ev["games"]` (`Betfair/safe_strategy/service.py:1425-1426`,
 * `parse_tennis_scores`, la STESSA funzione che alimenta `tennis_live_now`).
 * Il commento precedente lo chiamava erroneamente "calcio-centrico": corretto
 * qui. Questa barra NON ripete set/game (sarebbe la stessa cosa scritta due
 * volte in due posti): aggiunge solo ciò che la testata non ha — punto,
 * servizio, tie-break, stato mercato, età — dalla fonte più ricca
 * (`tennis_live_now`), che però copre SOLO gli eventi che il runner tennis
 * segue (`tennis_live_follow`, vedi `tennis_runner.py:1541-1542`): una
 * posizione di Safe Strategy tennis su un evento non seguito dal runner non
 * avrà MAI questa riga. Non è un guasto («punto e servizio: evento non
 * seguito dal runner tennis», grigio, mai arancione: non è un allarme).
 *
 * REPERTO 2 — il servizio si etichetta col NOME del giocatore quando il feed
 * lo dichiara (`p.giocatori.p1`/`.p2`, dal payload `p1`/`p2` — split di
 * `event_name`, `scanner.split_event_name`). Verificato sul codice Python
 * (non a intuito): `tennis_score_state()`/`server` (`tennis_runner.py:284`,
 * `1 = IPS "home"`) e `PartitaFeedLike.sets/games` (`service.py:1024-1033`,
 * STESSA base `parse_tennis_scores`) condividono la stessa convenzione
 * home=p1/away=p2 — INTERNAMENTE COERENTI fra loro. Ma NESSUN codice trovato
 * lega quella base (IPS "home"/"away") all'ORDINE del nome nell'`event_name`
 * (`p1`/`p2` del payload): è una convenzione già assunta altrove nel software
 * (`lib/tennis.ts:294`, commento "p1 = home (sortPriority 1)"), non
 * dimostrata da un test o da una funzione che le mette in relazione. Uso
 * `p.giocatori` quando c'è (eredita quell'assunzione preesistente, dichiarata
 * qui); quando manca — o per la correlazione con `row.state.markets[]`
 * (nessun campo lega neppure QUELLA all'ordine home/away: le selezioni
 * arrivano nell'ordine del dizionario `book.get("runners")`, mai ordinate
 * per `sortPriority`, `tennis_runner.py:993-1005`) — resto su "P1"/"P2"
 * letterali, come richiesto: un nome sbagliato è peggio di un trattino.
 */
function TennisVivoBar({ eventId, abilitato, giocatori }: {
    eventId: string; abilitato: boolean;
    giocatori?: { p1: string | null; p2: string | null } | null;
}) {
    const vivo = useTennisVivo(abilitato ? eventId : null);
    if (!abilitato) return null;
    const score = vivo.row?.score ?? null;
    const nomeServer = (n: 1 | 2): string => {
        const nome = n === 1 ? giocatori?.p1 : giocatori?.p2;
        return nome && nome.trim() ? nome.trim() : `P${n}`;
    };
    return (
        <div className="px-2.5 pt-1.5 flex items-center gap-2 flex-wrap text-[11px]"
            data-testid="cr-tennis-vivo">
            {score ? (
                <>
                    {/* punto: chi appartiene ogni numero è dichiarato, non intuito */}
                    <span className="font-mono tabular-nums text-white/85" data-testid="cr-tennis-vivo-punteggio"
                        title="punto corrente, dal punteggio live tennis (set e game sono già in testata)">
                        <span className={score.server === 1 ? 'text-secondary font-semibold' : 'text-white/50'}>
                            P1 {score.points.p1}
                        </span>
                        <span className="text-white/25"> · </span>
                        <span className={score.server === 2 ? 'text-secondary font-semibold' : 'text-white/50'}>
                            P2 {score.points.p2}
                        </span>
                        {score.tiebreak && <span className="text-secondary"> TB</span>}
                    </span>
                    {score.server != null && (
                        <span className="text-[10px] text-white/40" data-testid="cr-tennis-vivo-server"
                            title="chi è al servizio ora">
                            servizio <Circle className="inline w-1.5 h-1.5 fill-secondary text-secondary" />{' '}
                            {nomeServer(score.server)}
                        </span>
                    )}
                </>
            ) : (
                <span className="text-[10px] text-white/40" data-testid="cr-tennis-vivo-punteggio">
                    {!vivo.loaded
                        ? 'caricamento punteggio…'
                        : vivo.row
                            ? 'punto e servizio: in attesa del primo aggiornamento'
                            : 'punto e servizio: evento non seguito dal runner tennis'}
                </span>
            )}
            {vivo.statoMercato && (
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${vivo.statoMercato.cls} border-current/40`}
                    data-testid="cr-tennis-vivo-mercato" title="stato del mercato Match Odds, da Betfair">
                    {vivo.statoMercato.label}
                </span>
            )}
            {/* Match Odds vivo (18/09, richiesta utente "quote vive principali del
                mercato"): il NOME viaggia CON il prezzo nella stessa selezione
                (`TennisNowSelection`), quindi qui non serve nessuna assunzione
                sull'ordine p1/p2 — a differenza del servizio sopra, dove
                l'assunzione è dichiarata e circoscritta. */}
            {(vivo.row?.state?.markets ?? []).flatMap((m) => m.selections ?? []).length > 0 && (
                <span className="font-mono tabular-nums text-[10px] text-white/50"
                    data-testid="cr-tennis-vivo-quote" title="Match Odds: miglior BACK / miglior LAY di adesso, per selezione">
                    {(vivo.row?.state?.markets ?? []).flatMap((m) => m.selections ?? []).map((s, i) => (
                        <span key={s.selection_id}>
                            {i > 0 && <span className="text-white/25"> · </span>}
                            {s.name ?? `#${s.selection_id}`} {fmtOdds(s.back)}/{fmtOdds(s.lay)}
                        </span>
                    ))}
                </span>
            )}
            {vivo.row && (
                <span className={`ml-auto font-mono text-[10px] ${FRESCHEZZA_CLS[vivo.freschezza]}`}
                    data-testid="cr-tennis-vivo-eta"
                    title="età del punteggio/mercato tennis: sopra 20 s il dato è vecchio">
                    {vivo.etaS == null ? 'età ignota' : fmtAge(vivo.etaS)}
                </span>
            )}
        </div>
    );
}

export interface SchedaPartitaProps {
    p: PartitaGiornata;
    operazioni: OperazionePartita[];
    /** la scheda aperta adesso: serve a tornare ESATTAMENTE qui */
    scheda?: string;
    /** questa partita sta registrando? */
    registra?: boolean | null;
    /** il registratore di questo sport e' vivo? Senza, REC mentirebbe. */
    registratoreVivo?: boolean | null;
    /**
     * 16/09 — IL GESTO «cash out globale della partita» + «Riprendi», che
     * parlano col servizio SAFE. Assente = non si monta (una scheda che non ha
     * un servizio dietro non deve mostrare un pulsante che non fa niente).
     * Lo stato «chiusa da te» lo DICHIARA il servizio: qui si legge e basta.
     */
    safe?: {
        modalita: 'paper' | 'live' | null;
        chiusa: StatoChiusuraEvento;
        onCashOut: (eventId: string) => Promise<void>;
        onRiprendi: (eventId: string) => Promise<void>;
    };
    /**
     * 17/09 — LA PARTITA DI MIKE come il servizio la pubblica (`get_mike_state`,
     * già letta dall'hook: NESSUNA lettura in più). Assente = Mike non lavora
     * questa partita, e la scheda non si monta.
     */
    mike?: MikeEvent | null;
}

export function SchedaPartita({
    p, operazioni, scheda = 'live', registra = null, registratoreVivo = null, safe, mike = null,
}: SchedaPartitaProps) {
    const [aperto, setAperto] = useState<Bot | null>(null);

    // TASK A2 (18/09, raccordo) — nome della selezione per i 4 bot tennis, che
    // non lo pubblicano nella riga (`o.selezione` sempre `null`): si risolve
    // dallo STESSO canale condiviso `useTennisVivo(eventId)` che la barra
    // tennis già apre (una sottoscrizione per evento, mai una seconda). GATE
    // su `aperto` (pannello del bot tennis aperto): senza, si aprirebbe una
    // sottoscrizione su OGNI card tennis del giorno anche senza posizione né
    // pannello aperto — la stessa regressione che il "respiro DB" (13/09)
    // vieta (falsificato dal test "NESSUNA sottoscrizione, nessuna barra").
    const vivoSelezioniTennis = useTennisVivo(
        p.sport === 'tennis' && aperto != null && isBotTennis(aperto) ? p.event_id : null,
    );

    // posizioni del bot SAFE ancora a mercato su questa partita: sono quelle
    // che un cash-out globale chiuderebbe. Regolate ed `error` non contano.
    const viveSafe = operazioni.filter(
        (o) => o.bot === 'safe' && !isSettled(o.stato) && !isErrorRow(o.stato),
    ).length;

    const soldi = p.soldi;
    // IL NUMERO GRANDE E' QUELLO DEI SOLDI VERI. Il paper esiste, si vede, ma
    // sta sotto e non si somma: sul tennis la stessa partita può avere righe
    // di entrambe le modalità, e un solo numero sarebbe la media di due mondi.
    const net = soldi?.live.netPnl ?? null;
    const netPaper = soldi?.paper.netPnl ?? null;
    const apertaLive = soldi?.live.aperta ?? false;
    const apertaPaper = soldi?.paper.aperta ?? false;
    const target = p.target?.valore ?? null;
    const manca = target != null && net != null ? Math.max(0, target - net) : target;

    const bordo = p.stato === 'live' ? 'border-l-secondary'
        : apertaLive ? 'border-l-primary'
            : apertaPaper ? 'border-l-white/25' : 'border-l-white/12';

    const perBot = (b: Bot) => operazioni.filter((o) => o.bot === b);

    return (
        <div className={`rounded border border-white/10 border-l-[3px] ${bordo} bg-white/[0.02]`}
            data-testid="cr-partita" data-event-id={p.event_id}>
            {/* ── riga 1: chi gioca, stato, e gli strumenti ── */}
            <div className="px-2.5 pt-2 flex items-start gap-2">
                <span className="text-white/25 text-[13px] leading-none mt-0.5"
                    aria-label={p.sport === 'tennis' ? 'tennis' : 'calcio'}>
                    {p.sport === 'tennis' ? '🎾' : '⚽'}
                </span>
                <span className="text-[13px] font-medium leading-tight flex-1 min-w-0">{p.nome}</span>
                <StatoPill p={p} />
            </div>

            <div className="px-2.5 pt-1 flex items-center gap-1.5 flex-wrap">
                {/* la STESSA riga di pulsanti di ogni altra scheda: video,
                    statistiche, trading, segui live — e ognuno si segna il
                    punto di ritorno prima di portare il trader altrove. */}
                <AzioniPartita p={p} scheda={scheda} registra={registra}
                    registratoreVivo={registratoreVivo} />
                {p.stato === 'live' && (
                    <span className={`text-[10px] font-mono ml-auto ${QUOTE_CLS[p.statoQuote]}`}
                        data-testid="cr-latenza"
                        title={p.statoQuote === 'fermo'
                            ? 'il prezzo non cambia da questo tempo, ma lo scanner sta guardando: è il prezzo CORRENTE'
                            : 'da quando il prezzo è cambiato l’ultima volta'}>
                        {p.latenzaQuoteS == null
                            ? QUOTE_TESTO[p.statoQuote]('')
                            : QUOTE_TESTO[p.statoQuote](fmtAge(p.latenzaQuoteS))}
                    </span>
                )}
            </div>

            {/* ── calcio vivo (18/09, secondo giro, REPERTO 3): stato del
                mercato Match Odds quando NON è OPEN, volume abbinato, età del
                PUNTEGGIO (`etaFeedS`/`freschezza`) distinta da quella delle
                QUOTE (`cr-latenza` sopra, da `odds_ts_ms`) — sono due fatti
                diversi (§ commento su `odds_ts_ms`, `lib/controlRoom.ts`).
                Tutto da campi GIÀ nel payload (`mo_status`/`mo_total_matched`,
                `Betfair/safe_strategy/service.py:1369,1386`): nessuna lettura
                nuova. NON sommato nessun +3 s a mano: `IPS_SCORE_LAG_SEC`
                (`scan_feed.py:67`) è una costante SOLO lato Python, mai
                scritta nella riga — dichiarato come limite noto, non stimato. */}
            {p.sport === 'calcio' && p.stato === 'live' && (() => {
                const statoMercato = marketStatusMeta(p.statoMercato ?? null);
                const volume = p.volumeMercato ?? null;
                const odds = p.odds;
                const haQuote = Boolean(odds?.home || odds?.draw || odds?.away);
                if (!statoMercato && volume == null && p.etaFeedS == null && !haQuote) return null;
                return (
                    <div className="px-2.5 pt-1 flex items-center gap-2 flex-wrap text-[11px]"
                        data-testid="cr-calcio-vivo">
                        {statoMercato && (
                            <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${statoMercato.cls} border-current/40`}
                                data-testid="cr-calcio-vivo-mercato" title="stato del mercato Match Odds, da Betfair">
                                {statoMercato.label}
                            </span>
                        )}
                        {haQuote && (
                            <span className="font-mono tabular-nums text-[10px] text-white/60"
                                data-testid="cr-calcio-vivo-quote"
                                title="Match Odds: miglior BACK / miglior LAY di adesso, 1 · X · 2">
                                1 {fmtOdds(odds?.home?.back ?? null)}/{fmtOdds(odds?.home?.lay ?? null)}
                                <span className="text-white/25"> · </span>
                                X {fmtOdds(odds?.draw?.back ?? null)}/{fmtOdds(odds?.draw?.lay ?? null)}
                                <span className="text-white/25"> · </span>
                                2 {fmtOdds(odds?.away?.back ?? null)}/{fmtOdds(odds?.away?.lay ?? null)}
                            </span>
                        )}
                        {volume != null && (
                            <span className="text-[10px] text-white/40 font-mono tabular-nums"
                                data-testid="cr-calcio-vivo-volume" title="euro già scambiati sul Match Odds">
                                vol. {fmtMoney(volume)}
                            </span>
                        )}
                        {p.etaFeedS != null && (
                            <span className={`ml-auto font-mono text-[10px] ${FRESCHEZZA_CLS[p.freschezza]}`}
                                data-testid="cr-calcio-vivo-eta-punteggio"
                                title="età del PUNTEGGIO (non delle quote): quanto è vecchia la riga del feed. Nota: non include il ritardo IPS dichiarato (2-3 s), che qui non si somma a mano">
                                punteggio {fmtAge(p.etaFeedS)}
                            </span>
                        )}
                    </div>
                );
            })()}

            {/* ── tennis vivo: AGGIUNGE punto/servizio/tie-break/stato mercato/età
                a quello che la testata mostra già (set/game, dal feed scanner
                tennis-nativo — vedi il commento di TennisVivoBar) ── */}
            {p.sport === 'tennis' && (
                <TennisVivoBar eventId={p.event_id} abilitato={apertaLive || apertaPaper}
                    giocatori={p.giocatori} />
            )}

            {/* ── il gesto dell'utente: chiudo io TUTTA la partita, o la riprendo ── */}
            {safe && (
                <div className="px-2.5 pt-1.5">
                    <CashOutPartita
                        eventId={p.event_id}
                        modalita={safe.modalita}
                        posizioniVive={viveSafe}
                        stato={safe.chiusa}
                        onCashOut={safe.onCashOut}
                        onRiprendi={safe.onRiprendi}
                        compatto
                        esito={trovaEsitoCashOut(operazioni, 'safe')}
                    />
                </div>
            )}

            {/* ── riga 2: il METRO — target, fatto, quanto manca ── */}
            <div className="px-2.5 pt-2">
                <div className="flex items-baseline justify-between gap-2 text-[11px]">
                    <span className="text-white/40">
                        target <span className="font-mono text-white/70">{target == null ? DASH : fmtMoney(target)}</span>
                        {p.target?.fonte === 'ripiego' && <span className="text-white/30" title="calcolato dalla pagina: il servizio non lo pubblica"> *</span>}
                    </span>
                    <span className="flex items-baseline gap-2">
                        <span className={`font-mono text-[14px] font-bold tabular-nums ${pnlClass(net)}`}
                            data-testid="cr-pnl-partita">{net == null ? DASH : fmtMoney(net)}</span>
                        {manca != null && manca > 0 && net != null && (
                            <span className="text-[10px] text-white/40">manca {fmtMoney(manca)}</span>
                        )}
                        {target != null && net != null && net >= target && (
                            <span className="text-[10px] text-emerald-400 font-semibold">target centrato</span>
                        )}
                    </span>
                </div>
                {netPaper != null && (
                    <div className="text-[10px] text-white/35 mt-0.5" data-testid="cr-pnl-partita-paper">
                        in prova <span className={`font-mono ${netPaper >= 0 ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
                            {fmtMoney(netPaper, { signed: true })}
                        </span> — non entra nel target
                    </div>
                )}
                {p.avanzamento != null && (
                    <div className="h-1 mt-1 rounded-sm bg-white/8 overflow-hidden">
                        <div className={`h-full ${net != null && net < 0 ? 'bg-red-400' : 'bg-emerald-400'}`}
                            style={{ width: `${p.avanzamento}%` }} />
                    </div>
                )}
            </div>

            {/* ── riga 3: i bot DI QUESTO SPORT, cliccabili se hanno operato ── */}
            <div className="px-2.5 py-2 flex items-center gap-1.5">
                {botDiSport(p.sport).map((b) => {
                    const ops = perBot(b);
                    const attivo = ops.length > 0;
                    return (
                        <button
                            key={b} type="button"
                            disabled={!attivo}
                            onClick={() => setAperto(aperto === b ? null : b)}
                            aria-expanded={aperto === b}
                            data-testid={`cr-bot-${b}-${p.event_id}`}
                            title={attivo
                                ? `${BOT_LABEL[b]}: ${ops.length} ${ops.length === 1 ? 'operazione' : 'operazioni'} — clicca per il dettaglio`
                                : `${BOT_LABEL[b]}: nessuna operazione su questa partita`}
                            className={`w-6 h-5 rounded-sm grid place-items-center text-[10px] font-bold border transition-colors ${
                                attivo ? `${BOT_CLS[b]} hover:brightness-125 cursor-pointer`
                                    : 'border-white/8 bg-white/[0.02] text-white/15 cursor-default'
                            } ${aperto === b ? 'ring-1 ring-white/40' : ''}`}
                        >{BOT_SIGLA[b]}</button>
                    );
                })}
                {soldi && (soldi.live.liability > 0 || soldi.paper.liability > 0) ? (
                    <span className="ml-auto text-[10px] text-white/40 flex items-baseline gap-1.5">
                        {soldi.live.liability > 0 && (
                            <span title="responsabilità impegnata con SOLDI VERI">
                                resp. <span className="font-mono text-white/65">{fmtMoney(soldi.live.liability)}</span>
                            </span>
                        )}
                        {soldi.paper.liability > 0 && (
                            <span className="text-white/30" title="responsabilità impegnata in PROVA: non sono soldi veri e non si sommano">
                                prova <span className="font-mono">{fmtMoney(soldi.paper.liability)}</span>
                            </span>
                        )}
                    </span>
                ) : null}
            </div>

            {/* ── dettaglio: COSA ha fatto quel bot su questa partita ── */}
            {aperto && (
                <div className="px-2.5 pb-2 border-t border-white/8 pt-1.5" data-testid="cr-dettaglio-bot">
                    <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1">
                        {BOT_LABEL[aperto]} — operazioni su questa partita
                    </div>
                    {/* 17/09 — MIKE porta con sé un modello: mostrarlo qui è la
                        stessa carta della sua pagina, dalla stessa lettura. */}
                    {aperto === 'mike' && mike && (
                        <div className="mb-1.5"><SchedaMike ev={mike} /></div>
                    )}
                    <div className="space-y-1">
                        {/* 18/09 (secondo giro) — riga condivisa con `SchedaPreMatch.tsx`
                            (`RigaOperazione`, `DettaglioRigaView.tsx`): stesso ordine dei
                            campi in ogni tab, per costruzione, non per convenzione. */}
                        {perBot(aperto).map((o) => (
                            <RigaOperazione key={`${o.bot}-${o.id}`} o={o}
                                nomeSelezioneRisolto={isBotTennis(o.bot)
                                    ? nomeSelezioneTennis(vivoSelezioniTennis.row, o.selectionId)
                                    : undefined}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function StatoPill({ p }: { p: PartitaGiornata }) {
    if (p.stato === 'live') {
        const testa = p.minuto != null ? `${p.minuto}′` : p.punteggio ? '' : 'in gioco';
        return (
            <span className="shrink-0 flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded bg-secondary/15 text-secondary">
                <Circle className="w-1.5 h-1.5 fill-current" />
                {testa}{p.punteggio && <span>{testa ? ' ' : ''}{p.punteggio}</span>}
            </span>
        );
    }
    if (p.stato === 'pre') {
        return (
            <span className="shrink-0 text-[11px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-white/50">
                {p.koMs != null ? fmtTime(p.koMs) : 'orario ignoto'}
            </span>
        );
    }
    return <span className="shrink-0 text-[11px] px-1.5 py-0.5 rounded bg-white/5 text-white/30">conclusa</span>;
}

export default SchedaPartita;
