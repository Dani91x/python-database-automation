// ============================================================================
// CashOutGlobale.tsx - 30/09 (P12a): il riquadro «CASH OUT DELLA PARTITA (se
// chiudo TUTTO adesso)». SOLO presentazione: la cifra arriva gia' calcolata
// da `lib/cashOutPartita.ts` (via `useCashOutPartita`).
//
// Ordine dell'utente (30/09): «DEVE FARE LA SOMMA DI TUTTE LE OPERAZIONI CHE
// CI SONO ORA E DARMI IL VALORE ESATTO DI QUANDO GUADAGNO/PERDO CHIUDENDO
// TUTTO IN QUELLO SPECIFICO MOMENTO».
//
// Regole a schermo:
//   * LIVE e PROVA in due righe separate, mai una somma sola;
//   * NETTO di commissione, scritto; fonte (STIMA della pagina) ed eta' del
//     prezzo piu' vecchio usato;
//   * se manca anche UN prezzo: «NON CALCOLABILE: manca il prezzo di ...» e
//     NESSUNA cifra (una somma monca e' una bugia);
//   * accanto, la cifra del servizio del bot (Mike) con la SUA fonte ed eta':
//     due cifre diverse per la stessa cosa si spiegano, non si nascondono;
//   * liquidita' insufficiente al miglior prezzo: la cifra resta, marcata
//     «caso migliore».
// Nessun pulsante qui: chiudere e' un altro gesto (P16, su richiesta).
// ============================================================================
import { useContext, useMemo } from 'react';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import { ChiusuraRigaContext } from '@/components/controlroom/BottoneChiudiRiga';
import { useCashOutPartita, type ArgsCashOutPartita } from '@/components/controlroom/useCashOutPartita';
import { dueEsitiMike, esitoDecisoMike, valoreBotMike } from '@/lib/cashOutPartita';
import type { MikeEvent } from '@/lib/mike';
import { fmtMoney, fmtNum, fmtOdds } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import { BOT_LABEL, type Bot } from '@/lib/controlRoom';
import type {
    CashOutModalita, CashOutPartitaRisultato, PosizioneCashOut,
} from '@/lib/cashOutPartita';
import type { FontePrezzo } from '@/lib/schedaAlMs';

/** La cifra che il SERVIZIO di un bot pubblica per la stessa partita. */
export interface ValoreBotCashOut {
    bot: string;
    /** la cifra va accanto alla somma della STESSA modalita'; assente = live */
    modalita?: 'live' | 'paper';
    /** netto dichiarato dal servizio; null = il servizio non lo da' */
    netto: number | null;
    /** il servizio dichiara la cifra completa (tutti i prezzi presenti)? */
    completo: boolean;
    /** eta' del book con cui il servizio ha calcolato (s); null = ignota */
    etaS: number | null;
    /** perche' puo' differire (es. «chiude la copertura bancando l'Over 4,5») */
    nota?: string | null;
}

export interface CashOutGlobaleProps {
    /** null = nessuna gamba abbinata di nessun bot sulla partita */
    risultato: CashOutPartitaRisultato | null;
    /** le cifre dei servizi dei bot (Mike: `live.cashout.net`) */
    valoriBot?: readonly ValoreBotCashOut[];
    testId?: string;
}

const nomeBot = (b: string) => (BOT_LABEL as Record<string, string>)[b as Bot] ?? b;

function testoFontePrezzo(f: FontePrezzo | null): string {
    if (f === 'canale') return 'ladder al ms';
    if (f === 'db') return 'ladder al ms (DB, il canale tace)';
    if (f === 'scanner') return 'prezzo dello scanner';
    return 'prezzo non disponibile';
}

function testoEtaBreve(s: number | null): string {
    return s == null ? 'eta\' ignota' : `${fmtNum(s, s < 10 ? 1 : 0)} s fa`;
}

const lato = (l: 'back' | 'lay' | null) => (l === 'lay' ? 'banca' : l === 'back' ? 'punta' : '');

function RigaGamba({ p, modo, testId }: { p: PosizioneCashOut; modo: 'LIVE' | 'PROVA'; testId: string }) {
    const ingresso = p.componenti.length === 1
        ? `${lato(p.lato)} ${p.selezione ?? `selezione ${p.selectionId}`} ${fmtMoney(p.abbinato)} @ ${fmtOdds(p.prezzoIngresso)}`
        : `${p.selezione ?? `selezione ${p.selectionId}`}: ${p.componenti.length} gambe (${p.componenti
            .map((c) => `${lato(c.lato)} ${fmtMoney(c.abbinato)} @ ${fmtOdds(c.prezzo)}`).join(', ')})`;
    let chiusura: string;
    if (p.stato === 'decisa') chiusura = 'esito gia\' deciso: nessuna chiusura';
    else if (p.stato === 'piatta') {
        chiusura = p.residuoNonPiazzabile
            ? 'chiusura sotto il centesimo: non si piazza, resta il bloccato'
            : 'gia\' pareggiata: niente da chiudere';
    } else if (p.stato === 'senza_prezzo') chiusura = `chiudo ${lato(p.latoChiusura)}: prezzo assente`;
    else if (p.stato === 'mercato_non_aperto') chiusura = 'mercato non aperto: adesso non si chiude';
    else chiusura = `chiudo ${lato(p.latoChiusura)} ${fmtMoney(p.importoChiusura)} @ ${fmtOdds(p.prezzoChiusura)}`;
    return (
        <div className="flex items-baseline gap-1.5 flex-wrap text-[11px]" data-testid={testId}
            data-chiave={p.chiave} data-stato={p.stato}>
            <span className="text-white/70">{p.bot.map(nomeBot).join(' + ')}</span>
            <span className={`text-[9px] font-bold uppercase px-1 rounded ${modo === 'LIVE'
                ? 'bg-red-500/15 text-red-300' : 'bg-sky-500/10 text-sky-300'}`}>{modo}</span>
            <span className="text-white/60 font-mono">{ingresso}</span>
            <span className="text-white/45 font-mono" data-testid={`${testId}-chiudo`}>{chiusura}</span>
            <span className={`font-mono font-semibold ${pnlClass(p.pnl)}`} data-testid={`${testId}-pnl`}>
                {fmtMoney(p.pnl, { signed: true })}
            </span>
            {p.fontePrezzo && (
                <span className="text-[9px] text-white/30">
                    {testoFontePrezzo(p.fontePrezzo)} · {testoEtaBreve(p.etaPrezzoS)}
                </span>
            )}
            {p.liquiditaSufficiente === false && (
                <span className="text-[9px] text-amber-300" data-testid={`${testId}-liquidita`}>
                    solo {fmtMoney(p.abbinabile)} al miglior prezzo: caso migliore
                </span>
            )}
        </div>
    );
}

function Blocco({ r, modo, testId, valoriBot }: {
    r: CashOutModalita; modo: 'LIVE' | 'PROVA'; testId: string; valoriBot: readonly ValoreBotCashOut[];
}) {
    const eta = r.etaIgnota ? null : r.etaPrezziS;
    return (
        <div className="flex flex-col gap-1" data-testid={testId}>
            <div className="flex items-baseline gap-2 flex-wrap">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${modo === 'LIVE' ? 'text-white/80' : 'text-sky-300/80'}`}>
                    {modo === 'LIVE'
                        ? 'Cash out della partita (se chiudo TUTTO adesso)'
                        : 'Prova (simulato, mai sommato ai soldi veri)'}
                </span>
                {r.netto != null ? (
                    <>
                        <span className={`font-mono text-[15px] font-bold ${pnlClass(r.netto)}`} data-testid={`${testId}-netto`}>
                            {fmtMoney(r.netto, { signed: true })}
                        </span>
                        <span className="text-[10px] text-white/50">netto commissione</span>
                        {r.commissione != null && r.commissione > 0 && (
                            <span className="text-[9px] text-white/35" data-testid={`${testId}-commissione`}>
                                (lordo {fmtMoney(r.lordo, { signed: true })}, commissione {fmtMoney(r.commissione)} sul netto di ogni mercato)
                            </span>
                        )}
                        {r.gambe.some((p) => p.fontePrezzo != null) || modo === 'PROVA' ? (
                            <MarchioSoldi fonte={modo === 'LIVE' ? 'pagina' : 'prova'} etaS={eta}
                                dettaglio={modo === 'LIVE'
                                    ? 'somma per mercato e selezione di tutte le gambe abbinate dei bot LIVE, chiuse al miglior prezzo di adesso; eta\' = il prezzo piu\' vecchio usato'
                                    : 'stessa somma sulle gambe PROVA'}
                                testId={`${testId}-marchio`} />
                        ) : (
                            <MarchioSoldi fonte={modo === 'LIVE' ? 'pagina' : 'prova'}
                                dettaglio="nessun prezzo serve: posizioni gia' pareggiate o decise"
                                testId={`${testId}-marchio`} />
                        )}
                        {r.liquiditaInsufficiente && (
                            <span className="text-[10px] text-amber-300" data-testid={`${testId}-caso-migliore`}>
                                liquidita' insufficiente al miglior prezzo: e' il caso migliore
                            </span>
                        )}
                    </>
                ) : (
                    <span className="text-[11px] font-semibold text-orange-400" data-testid={`${testId}-non-calcolabile`}>
                        NON CALCOLABILE: {r.mancanti.join('; ')}
                    </span>
                )}
            </div>
            {r.gambe.map((p) => (
                <RigaGamba key={p.chiave} p={p} modo={modo} testId={`${testId}-gamba`} />
            ))}
            {r.avvisi.filter((a) => !/liquidita' insufficiente/.test(a)).map((a) => (
                <div key={a} className="text-[9px] text-amber-300/80" data-testid={`${testId}-avviso`}>{a}</div>
            ))}
            {valoriBot.map((v) => {
                // una cifra che il bot stesso dichiara incompleta non si mostra
                const cifra = v.completo ? v.netto : null;
                const diff = cifra != null && r.netto != null ? Math.round((r.netto - cifra) * 100) / 100 : null;
                return (
                    <div key={v.bot} className="flex items-baseline gap-1.5 flex-wrap text-[10px] text-white/50"
                        data-testid={`${testId}-bot-${v.bot}`}>
                        <span>il bot {nomeBot(v.bot)} calcola:</span>
                        <span className={`font-mono ${cifra == null ? 'text-orange-400' : pnlClass(cifra)}`}
                            data-testid={`${testId}-bot-${v.bot}-netto`}>
                            {!v.completo ? 'non calcolabile' : cifra == null ? 'non pubblicato' : fmtMoney(cifra, { signed: true })}
                        </span>
                        <MarchioSoldi fonte="bot" etaS={v.etaS} dettaglio="book letto dal servizio del bot"
                            testId={`${testId}-bot-${v.bot}-marchio`} />
                        {diff != null && diff !== 0 && (
                            <span className="text-white/40" data-testid={`${testId}-bot-${v.bot}-differenza`}>
                                differenza {fmtMoney(Math.abs(diff))}: prezzi letti in istanti diversi
                                (pagina {testoEtaBreve(eta)}, bot {testoEtaBreve(v.etaS)})
                                {v.nota ? `; ${v.nota}` : ''}
                            </span>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

export function CashOutGlobale({ risultato, valoriBot = [], testId = 'cr-cashout-globale' }: CashOutGlobaleProps) {
    if (risultato == null) {
        return (
            <div className="text-[10px] text-white/40" data-testid={testId} data-vuoto="1">
                Cash out della partita: nessuna gamba abbinata di nessun bot su questa partita
            </div>
        );
    }
    const haLive = risultato.live.nGambe > 0 || risultato.live.mancanti.length > 0;
    const haProva = risultato.paper.nGambe > 0 || risultato.paper.mancanti.length > 0;
    const botLive = valoriBot.filter((v) => (v.modalita ?? 'live') === 'live');
    const botProva = valoriBot.filter((v) => v.modalita === 'paper');
    return (
        <div className="flex flex-col gap-1.5 rounded border border-white/10 px-2 py-1.5" data-testid={testId}>
            {haLive ? (
                <Blocco r={risultato.live} modo="LIVE" testId={`${testId}-live`} valoriBot={botLive} />
            ) : (
                <div className="text-[10px] text-white/40" data-testid={`${testId}-live-vuoto`}>
                    Cash out della partita: nessuna gamba LIVE abbinata su questa partita
                </div>
            )}
            {haProva && (
                <Blocco r={risultato.paper} modo="PROVA" testId={`${testId}-prova`} valoriBot={botProva} />
            )}
        </div>
    );
}

/**
 * P12b - IL RIQUADRO NELLA SCHEDA DELLA PARTITA: le righe della partita (di
 * TUTTI i bot) -> `useCashOutPartita` (ladder al ms dal contesto della
 * Control Room, ripiego scanner dichiarato) -> `CashOutGlobale`, con accanto
 * la cifra del servizio di Mike. Una partita senza gambe abbinate non mostra
 * niente e non apre sottoscrizioni.
 */
export function CashOutGlobalePartita({ sport, operazioni, mike = null }: {
    sport: 'calcio' | 'tennis';
    operazioni: NonNullable<ArgsCashOutPartita['operazioni']>;
    /** la partita di Mike come il servizio la pubblica (gia' in pagina) */
    mike?: MikeEvent | null;
}) {
    const sorgente = useContext(ChiusuraRigaContext)?.sorgenteLadder ?? null;
    const dueEsiti = useMemo(() => dueEsitiMike(mike), [mike]);
    const esitoDeciso = useMemo(() => esitoDecisoMike(mike, operazioni), [mike, operazioni]);
    const r = useCashOutPartita({ operazioni, sorgente, sport, dueEsiti, esitoDeciso });
    if (r == null) return null;
    if (r.live.nGambe === 0 && r.paper.nGambe === 0
        && r.live.mancanti.length === 0 && r.paper.mancanti.length === 0) return null;
    const vb = valoreBotMike(mike, Date.now());
    return (
        <div className="px-2.5 pt-1.5">
            <CashOutGlobale risultato={r} valoriBot={vb ? [vb] : []} />
        </div>
    );
}

export default CashOutGlobale;
