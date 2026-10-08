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
// 30/09 sera (W_C, P16): «Chiudi tutte le gambe dei bot». NESSUN comando
// backend nuovo: si ORCHESTRANO in sequenza i comandi per-bot GIA' esistenti,
// con la STESSA funzione dei pulsanti di riga (`ChiusuraRigaContext.chiudi`,
// `chiudiRiga.ts`): Mike una volta per PARTITA (chiude il ciclo intero), Safe,
// Omega e i 4 bot tennis per riga, lo scalper per sessione (con la firma). Una
// gamba senza comando si DICE prima del clic e resta aperta.
// ============================================================================
import { useContext, useEffect, useMemo, useState } from 'react';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import { ChiusuraRigaContext } from '@/components/controlroom/BottoneChiudiRiga';
import {
    chiudibile, faseMostrata, TESTO_FASE, type RigaDaChiudere,
} from '@/components/controlroom/chiudiRiga';
import { ATTESA_CONFERMA_USCITE_MS } from '@/components/controlroom/InterruttoreUscite';
/** review incrociata 30/09 (M1): dopo questo tempo l'armatura di «Chiudi tutte» cade da sola */
export const SCADENZA_ARMATURA_MS = 10_000;
import { feedFreshness } from '@/lib/mike';
import { isBotTennis } from '@/lib/controlRoom';
import {
    useCashOutPartita, useRiportaSintesi, type ArgsCashOutPartita, type SintesiCashOut,
} from '@/components/controlroom/useCashOutPartita';
import { dueEsitiMike, dueEsitiPartita, esitoDecisoMike, valoreBotMike } from '@/lib/cashOutPartita';
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
    /** P16: le righe della partita; assenti = nessun «Chiudi tutte le gambe» */
    operazioni?: readonly OperazionePerChiusura[];
    /** 08/10 sera (D-6, pagina Cash Out): motivo per cui «Chiudi tutte le gambe»
     *  e' spento a prescindere dalla cifra (partita conclusa: mercato CHIUSO da
     *  Betfair); assente = come prima */
    spentoPerche?: string | null;
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

// ============================================================================
// P16 - «CHIUDI TUTTE LE GAMBE DEI BOT» (piano puro + pulsante)
// ============================================================================

/** La riga della scheda come serve al piano (forma strutturale di `OperazionePartita`). */
export interface OperazionePerChiusura {
    bot: Bot;
    id: number;
    eventId?: string;
    marketId: string | null;
    modalita: 'paper' | 'live' | null;
    stato: string;
    chiudeId?: number | null;
    /** tennis: `pnl` valorizzato = ordine regolato (non e' una posizione) */
    pnl: number | null;
    firma?: string | null;
    residuo?: boolean;
}

export interface ComandoChiusura {
    bot: Bot;
    riga: RigaDaChiudere;
    /** quante posizioni del bot il comando chiude (Mike: tutte quelle della partita) */
    gambe: number;
}

export interface PianoChiusura {
    comandi: ComandoChiusura[];
    /** posizioni per cui NON esiste un comando adesso, col motivo del bot */
    senzaComando: { bot: Bot; id: number; motivo: string }[];
}

/** La riga come la vede il «Chiudi» di riga (stessi campi di `DettaglioRigaView`). */
function rigaDa(o: OperazionePerChiusura): RigaDaChiudere {
    return {
        bot: o.bot, id: o.id, eventId: o.eventId ?? null, marketId: o.marketId ?? null,
        modalita: o.modalita, stato: o.stato, chiudeId: o.chiudeId ?? null,
        regolata: isBotTennis(o.bot) && o.pnl != null,
        ...(o.firma != null ? { firma: o.firma } : {}),
        ...(o.residuo ? { residuo: true } : {}),
    };
}

/**
 * IL PIANO, per UNA modalita': quali comandi partono e in che ordine.
 *  - la regola di chi e' una posizione e chi e' chiudibile e' `chiudiRiga.
 *    chiudibile` (la stessa del pulsante di riga): nessuna seconda regola;
 *  - Mike: UN comando per partita (con la prima riga chiudibile; `mike_request
 *    ('cashout')` chiude l'intero ciclo), che copre tutte le sue gambe;
 *  - Safe, Omega, 4 bot tennis: un comando per riga; scalper: per sessione;
 *  - una posizione non chiudibile adesso va in `senzaComando` col motivo.
 */
export function pianoChiusuraPartita(
    ops: readonly OperazionePerChiusura[], modalita: 'paper' | 'live',
): PianoChiusura {
    const comandi: ComandoChiusura[] = [];
    const senzaComando: PianoChiusura['senzaComando'] = [];
    const mike: { riga: RigaDaChiudere; ok: boolean; motivo: string | null }[] = [];
    // review incrociata 30/09 (M2): un bot TENNIS chiude la sua posizione sulla
    // PARTITA (`chiudiRiga.ts`, `chiudi_bot` per event/market): UN comando per
    // (bot, partita, mercato), non uno per riga, come per Mike
    const tennis = new Map<string, { riga: RigaDaChiudere; ok: boolean; motivo: string | null }[]>();
    for (const o of ops) {
        if (o.modalita !== modalita) continue;
        const riga = rigaDa(o);
        const c = chiudibile(riga);
        if (c == null) continue;                        // non e' una posizione
        if (o.bot === 'mike') { mike.push({ riga, ok: c.ok, motivo: c.ok ? null : c.motivo }); continue; }
        if (isBotTennis(o.bot)) {
            const k = `${o.bot}|${riga.eventId ?? ''}|${riga.marketId ?? ''}`;
            tennis.set(k, [...(tennis.get(k) ?? []), { riga, ok: c.ok, motivo: c.ok ? null : c.motivo }]);
            continue;
        }
        if (c.ok) comandi.push({ bot: o.bot, riga, gambe: 1 });
        else senzaComando.push({ bot: o.bot, id: o.id, motivo: c.motivo });
    }
    for (const gruppo of tennis.values()) {
        const ok = gruppo.find((g) => g.ok);
        if (ok) comandi.push({ bot: ok.riga.bot, riga: ok.riga, gambe: gruppo.length });
        else for (const g of gruppo) senzaComando.push({ bot: g.riga.bot, id: g.riga.id, motivo: g.motivo ?? '' });
    }
    const primaOk = mike.find((m) => m.ok);
    if (primaOk) comandi.unshift({ bot: 'mike', riga: primaOk.riga, gambe: mike.length });
    else for (const m of mike) senzaComando.push({ bot: 'mike', id: m.riga.id, motivo: m.motivo ?? '' });
    return { comandi, senzaComando };
}

/** «2 gambe di Mike, 1 di Safe; Scalper calcio #7 non ha un comando: resta aperto (motivo)» */
export function testoPiano(p: PianoChiusura): string {
    const perBot = new Map<string, number>();
    for (const c of p.comandi) perBot.set(c.bot, (perBot.get(c.bot) ?? 0) + c.gambe);
    const parti = Array.from(perBot.entries()).map(([b, n], i) =>
        (i === 0 ? `${n} ${n === 1 ? 'gamba' : 'gambe'} di ${nomeBot(b)}` : `${n} di ${nomeBot(b)}`));
    const senza = p.senzaComando.map((s) => `${nomeBot(s.bot)} #${s.id} non ha un comando adesso: resta aperta (${s.motivo})`);
    return [parti.join(', ') || 'nessuna gamba chiudibile', ...senza].join('; ');
}

function ChiudiTutteLeGambe({ piano, modalita, spentoPerche, testId }: {
    piano: PianoChiusura; modalita: 'paper' | 'live'; spentoPerche: string | null; testId: string;
}) {
    const api = useContext(ChiusuraRigaContext);
    const [armatoDa, setArmatoDa] = useState<number | null>(null);
    const [inVolo, setInVolo] = useState(false);
    const [inviati, setInviati] = useState<ComandoChiusura[]>([]);
    const [, setTic] = useState(0);
    useEffect(() => {
        if (armatoDa == null) return undefined;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_USCITE_MS + 20);
        // review incrociata 30/09 (M1): l'armatura SCADE: un «Confermo» lasciato
        // armato non deve restare pronto per minuti (le gambe cambiano)
        const s = window.setTimeout(() => setArmatoDa(null), SCADENZA_ARMATURA_MS);
        return () => { window.clearTimeout(t); window.clearTimeout(s); };
    }, [armatoDa]);
    // review incrociata 30/09 (M1): se il PIANO cambia (una gamba si chiude da
    // sola, ne compare una nuova) o scatta il BLOCCO (prezzi fermi/ignoti,
    // cifra non calcolabile) l'armatura cade: si riparte da «avvia»
    const firmaPiano = piano.comandi.map((c) => `${c.bot}:${c.riga.id}:${c.gambe}`).join(',')
        + '|' + piano.senzaComando.map((s) => `${s.bot}:${s.id}`).join(',');
    useEffect(() => { setArmatoDa(null); }, [firmaPiano, spentoPerche]);
    if (!api) return null;
    if (piano.comandi.length === 0 && piano.senzaComando.length === 0) return null;
    const troppoPresto = armatoDa != null && Date.now() - armatoDa < ATTESA_CONFERMA_USCITE_MS;
    const nBot = new Set(piano.comandi.map((c) => c.bot)).size;
    const blocco = piano.comandi.length === 0 ? 'nessuna gamba chiudibile adesso' : spentoPerche;
    // IN SEQUENZA: il comando successivo parte solo quando il precedente ha
    // avuto il suo esito d'invio (`chiudi` scrive lo stato e non lancia)
    const esegui = async () => {
        setArmatoDa(null);
        setInVolo(true);
        const mandati: ComandoChiusura[] = [];
        try {
            for (const c of piano.comandi) {
                await api.chiudi(c.riga);
                mandati.push(c);
                setInviati([...mandati]);
            }
        } finally {
            setInVolo(false);
        }
    };
    return (
        <div className="flex flex-col gap-0.5" data-testid={testId}>
            <div className="text-[10px] text-white/50" data-testid={`${testId}-piano`}>{testoPiano(piano)}</div>
            <div className="flex items-baseline gap-1.5 flex-wrap">
                {armatoDa != null ? (
                    <>
                        <button type="button" data-testid={`${testId}-conferma`}
                            // review finale 30/09 (R2-1): il cancello «prezzi fermi/ignoti o cifra
                            // non calcolabile» vale ANCHE dopo l'armatura: se il feed si ferma fra
                            // «avvia» e «confermo», la conferma si spegne e il motivo si legge
                            disabled={troppoPresto || inVolo || blocco != null}
                            title={blocco ?? undefined}
                            onClick={() => { if (!troppoPresto && blocco == null) void esegui(); }}
                            className="h-6 px-2 text-[10px] rounded bg-orange-500 text-black font-bold uppercase disabled:opacity-40">
                            Confermo: chiudi tutte le gambe
                        </button>
                        <span className="text-[10px] text-orange-300" data-testid={`${testId}-armato`}>
                            Sono soldi veri: {piano.comandi.length} {piano.comandi.length === 1 ? 'comando' : 'comandi'} a {nBot} {nBot === 1 ? 'bot' : 'bot'}
                            {' '}<span className="text-white/50" title="Mike chiude l'intero ciclo della partita; un bot tennis chiude la sua posizione sulla partita e non rientra finche' non lo riarmi; lo scalper ferma la sessione; Omega e Safe chiudono la singola posizione">(effetti: vedi il title)</span>.{' '}
                            <button type="button" className="underline" onClick={() => setArmatoDa(null)}
                                data-testid={`${testId}-annulla`}>annulla</button>
                        </span>
                    </>
                ) : (
                    <button type="button" data-testid={`${testId}-avvia`}
                        disabled={blocco != null || inVolo}
                        title={blocco ?? 'manda in sequenza, bot per bot, gli stessi comandi dei pulsanti «Chiudi» di riga'}
                        onClick={() => { if (modalita === 'live') setArmatoDa(Date.now()); else void esegui(); }}
                        className="h-6 px-2 text-[10px] rounded border border-rose-500/40 bg-rose-500/10 text-rose-200 font-semibold uppercase disabled:opacity-40">
                        Chiudi tutte le gambe dei bot
                    </button>
                )}
                {blocco != null && (
                    <span className="text-[10px] text-white/40" data-testid={`${testId}-bloccato`}>{blocco}</span>
                )}
            </div>
            {inviati.map((c) => {
                const s = api.stato(c.bot, c.riga.id);
                const fase = s ? TESTO_FASE[faseMostrata(s)] : 'in invio';
                const chi = c.bot === 'mike' ? `Mike (partita, ${c.gambe} ${c.gambe === 1 ? 'gamba' : 'gambe'})` : `${nomeBot(c.bot)} #${c.riga.id}`;
                return (
                    <div key={`${c.bot}:${c.riga.id}`} className="text-[10px] text-white/60"
                        data-testid={`${testId}-esito`} data-bot={c.bot}>
                        {chi}: {fase}{s?.motivo ? `: ${s.motivo}` : ''}
                    </div>
                );
            })}
        </div>
    );
}

/** Pulsanti di soldi spenti con prezzi fermi/ignoti (`feedFreshness`: oltre 20 s = fermo). */
// 08/10 (W1): esportata per il cash out della posizione col conto (pagina Cash Out)
export function motivoPrezziFermi(r: CashOutModalita): string | null {
    if (r.etaIgnota) return 'prezzi di eta\' ignota: non si chiude alla cieca';
    if (r.etaPrezziS != null && feedFreshness(r.etaPrezziS).tone === 'stale') {
        return `prezzi fermi da ${Math.round(r.etaPrezziS)} s: non si chiude su prezzi vecchi`;
    }
    return null;
}

function RigaGamba({ p, modo, testId }: { p: PosizioneCashOut; modo: 'LIVE' | 'PROVA'; testId: string }) {
    // W_C: una componente «esposizione» (sessione scalper) si scrive coi suoi W/L
    const pezzo = (c: PosizioneCashOut['componenti'][number]) => (c.esposizione
        ? `esposizione ${nomeBot(c.bot)}: se vince ${fmtMoney(c.esposizione.win, { signed: true })} / se perde ${fmtMoney(c.esposizione.lose, { signed: true })}`
        : `${lato(c.lato)} ${fmtMoney(c.abbinato)} @ ${fmtOdds(c.prezzo)}`);
    const nome = p.selezione ?? `selezione ${p.selectionId}`;
    const ingresso = p.componenti.length === 1
        ? (p.componenti[0].esposizione ? `${nome}: ${pezzo(p.componenti[0])}`
            : `${lato(p.lato)} ${nome} ${fmtMoney(p.abbinato)} @ ${fmtOdds(p.prezzoIngresso)}`)
        : `${nome}: ${p.componenti.length} gambe (${p.componenti.map(pezzo).join(', ')})`;
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

function Blocco({ r, modo, testId, valoriBot, operazioni, spentoEsterno = null }: {
    r: CashOutModalita; modo: 'LIVE' | 'PROVA'; testId: string; valoriBot: readonly ValoreBotCashOut[];
    operazioni?: readonly OperazionePerChiusura[];
    spentoEsterno?: string | null;
}) {
    const eta = r.etaIgnota ? null : r.etaPrezziS;
    const modalita = modo === 'LIVE' ? 'live' : 'paper';
    const piano = operazioni ? pianoChiusuraPartita(operazioni, modalita) : null;
    // pulsante di soldi: spento su prezzi fermi/ignoti e se la cifra non e' calcolabile
    const spentoPerche = spentoEsterno ?? motivoPrezziFermi(r)
        ?? (r.netto == null ? 'cifra della partita non calcolabile: non si chiude alla cieca' : null);
    return (
        <div className="flex flex-col gap-1" data-testid={testId}>
            <div className="flex items-baseline gap-2 flex-wrap">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${modo === 'LIVE' ? 'text-white/80' : 'text-sky-300/80'}`}>
                    {modo === 'LIVE'
                        ? 'Cash out della partita: gambe dei bot (se le chiudo tutte adesso)'
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
            {/* R_C (review): la cifra NON vede gli ordini fatti fuori dai bot:
                sempre scritto, non nel tooltip (su FC Vsetin il sito ha chiuso) */}
            {modo === 'LIVE' && (
                <div className="text-[10px] text-amber-300/70" data-testid={`${testId}-solo-bot`}>
                    solo ordini dei bot: gli ordini fatti dal sito o dall&apos;app Betfair non sono inclusi
                </div>
            )}
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
                                differenza {fmtMoney(Math.abs(diff))} · cause possibili: prezzi letti in istanti
                                diversi (pagina {testoEtaBreve(eta)}, bot {testoEtaBreve(v.etaS)}); il bot chiude la
                                copertura su un altro libro; il bot conta solo le sue gambe
                            </span>
                        )}
                    </div>
                );
            })}
            {piano && (
                <ChiudiTutteLeGambe piano={piano} modalita={modalita} spentoPerche={spentoPerche}
                    testId={`${testId}-chiudi-tutte`} />
            )}
        </div>
    );
}

export function CashOutGlobale({ risultato, valoriBot = [], testId = 'cr-cashout-globale', operazioni, spentoPerche = null }: CashOutGlobaleProps) {
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
                <Blocco r={risultato.live} modo="LIVE" testId={`${testId}-live`} valoriBot={botLive} operazioni={operazioni}
                    spentoEsterno={spentoPerche} />
            ) : (
                <div className="text-[10px] text-white/40" data-testid={`${testId}-live-vuoto`}>
                    Cash out della partita: nessuna gamba LIVE abbinata su questa partita
                </div>
            )}
            {haProva && (
                <Blocco r={risultato.paper} modo="PROVA" testId={`${testId}-prova`} valoriBot={botProva} operazioni={operazioni}
                    spentoEsterno={spentoPerche} />
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
export function CashOutGlobalePartita({ sport, operazioni, mike = null, moMarketId = null, onSintesi, spentoPerche = null }: {
    sport: 'calcio' | 'tennis';
    /** W_C: il Match Odds della partita (`p.marketId` = `mo_market_id`); nel
     *  TENNIS e' a due esiti (P1/P2): le gambe sui due giocatori si nettano */
    moMarketId?: string | null;
    operazioni: readonly (NonNullable<ArgsCashOutPartita['operazioni']>[number] & OperazionePerChiusura)[];
    /** la partita di Mike come il servizio la pubblica (gia' in pagina) */
    mike?: MikeEvent | null;
    /** 08/10 (W1, secondo giro) - riceve la sintesi di QUESTA cifra (pagina Cash
     *  Out, riepilogo in testa); assente = niente, come prima */
    onSintesi?: (s: SintesiCashOut | null) => void;
    /** 08/10 sera (D-6, pagina Cash Out): «Chiudi tutte le gambe» spento con
     *  questo motivo (partita conclusa); assente = come prima */
    spentoPerche?: string | null;
}) {
    const sorgente = useContext(ChiusuraRigaContext)?.sorgenteLadder ?? null;
    const dueEsiti = useMemo(() => dueEsitiPartita(sport, moMarketId, dueEsitiMike(mike)), [sport, moMarketId, mike]);
    const esitoDeciso = useMemo(() => esitoDecisoMike(mike, operazioni), [mike, operazioni]);
    const r = useCashOutPartita({ operazioni, sorgente, sport, dueEsiti, esitoDeciso });
    useRiportaSintesi(r, onSintesi);
    if (r == null) return null;
    if (r.live.nGambe === 0 && r.paper.nGambe === 0
        && r.live.mancanti.length === 0 && r.paper.mancanti.length === 0) return null;
    const vb = valoreBotMike(mike, Date.now());
    return (
        <div className="px-2.5 pt-1.5">
            <CashOutGlobale risultato={r} valoriBot={vb ? [vb] : []} operazioni={operazioni} spentoPerche={spentoPerche} />
        </div>
    );
}

export default CashOutGlobale;
