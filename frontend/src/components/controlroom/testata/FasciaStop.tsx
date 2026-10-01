// ============================================================================
// FasciaStop.tsx - gli STOP DI PERDITA nella testata (contenitore `cr-freni`).
//
// P4 (30/09): ogni stop col NOME del proprietario e la sua MODALITA'.
// 01/10 (ordine dell'utente: "che roba e'? illeggibile" / "stop perdita devo
// poterlo modificare direttamente da qui"):
//   * UNA RIGA PER STOP: NOME - modalita' (PAPER/LIVE col suo colore) - cifra
//     grande - stato (attivo / SPENTO / SCATTATO / assente / non letto) - fonte
//     ed eta';
//   * la cifra si MODIFICA SUL POSTO: clic -> campo in euro al centesimo
//     (negativo = perdita massima) + Salva/Annulla. Il salvataggio passa da
//     `salvaStop.ts`, cioe' dalle STESSE funzioni e chiavi dei fogli parametri
//     e del pannello del conto, col loro cancello "parametri non letti" (campo
//     disabilitato, e lo dice). In LIVE (o modalita' non letta) serve una
//     conferma esplicita, che scade da sola dopo 10 s. Dopo il salvataggio si
//     mostra la cifra RESTITUITA dal database, mai quella digitata;
//   * via le frasi criptiche: "Omega non pubblica se lo stop e' scattato";
//     "Tennis e Scalper: nessuno stop proprio" con la verita' sullo stop del
//     conto (verificata nel codice, vedi `NOTA_TENNIS_SCALPER`).
// Assente si scrive "assente", mai 0,00; scattato si scrive "SCATTATO".
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Pencil, SlidersHorizontal } from 'lucide-react';
import { fmtMoney, fmtAge, fmtNum } from '@/lib/format';
import { BOT_LABEL } from '@/lib/controlRoom';
import type { StopPerditaTestata, StopBot, StopConto, BotConStop } from './stopPerdita';
import { leggiImporto, salvaStop as salvaStopVero, type ProprietarioStop } from './salvaStop';

/** Porta il trader alla riga del bot in "Comando dei bot" (il foglio
 *  parametri completo), o al pannello se la riga non e' visibile. */
export function vaiAllaRigaDelBot(bot: string, doc: Document = document): boolean {
    const riga = doc.querySelector<HTMLElement>(`[data-testid="cr-parametri-${bot}"]`);
    const bersaglio = riga ?? doc.querySelector<HTMLElement>('[data-testid="cr-pannello-bot"]');
    if (!bersaglio) return false;
    if (typeof bersaglio.scrollIntoView === 'function') bersaglio.scrollIntoView({ block: 'center', behavior: 'smooth' });
    const pulsante = riga?.querySelector<HTMLElement>('button');
    if (pulsante) pulsante.focus();
    return riga != null;
}

/**
 * 01/10 - verificato nel codice prima di scriverlo:
 *  - nessuno stop di perdita giornaliera nei bot tennis (`Betfair/stream/
 *    tennis_live/`) ne' nello scalper (`Betfair/stream/scalper/`);
 *  - lo stop del conto lo calcola SOLO il runner calcio (`daily_stop_worker`,
 *    P&L da `betfair_live_settled` + posizioni del suo framework): tennis e
 *    scalper non scrivono li' e non registrano quel worker;
 *  - quando scatta tira il freno generale (`betfair_live_settings.kill_switch`)
 *    che entrambi leggono (`guardie_tennis.kill_switch_attivo`,
 *    `scalper_session.motivo_freno`): da li' solo chiusure.
 */
// R-07 (rilievi bassi 01/10): la verita' COMPLETA. Nessuno stop GIORNALIERO
// proprio (nessun daily loss in `stream/tennis_live/` ne' in `stream/scalper/`),
// ma lo scalper ha due tetti suoi, verificati nel codice: per PARTITA
// `event_loss_cap` (scalper_session.py: 1,50 di serie, al massimo 1,00 nella
// modalita' intervallo; scalper_bot.py: oltre il tetto chiude tutto su quella
// partita) e per SELEZIONE il tetto di esposizione che la sessione passa alla
// strategia (stake x (quota massima - 1) x 2).
export const NOTA_TENNIS_SCALPER = {
    testo: 'Tennis e Scalper: nessuno stop giornaliero proprio. Li ferma lo stop del Conto quando scatta, ma le loro perdite non lo fanno scattare. '
        + 'Lo Scalper ha in piu\' due tetti suoi, nei parametri della sessione: perdita massima per partita ed esposizione massima per selezione.',
    titolo: 'I 4 bot tennis e lo scalper calcio non hanno uno stop di perdita giornaliera. Lo stop del Conto e\' calcolato dal runner calcio '
        + 'sulle SUE operazioni (regolate dal conto Betfair + posizioni aperte del runner calcio): quando scatta tira il freno generale, '
        + 'che tennis e scalper leggono (da quel momento solo chiusure), ma le perdite di tennis e scalper non entrano nel suo conteggio. '
        + 'Lo scalper calcio ha due tetti suoi, non giornalieri: per PARTITA una perdita massima (di serie 1,50 EUR, al massimo 1,00 EUR '
        + 'nella modalita\' intervallo) oltre la quale chiude tutto su quella partita; per SELEZIONE un\'esposizione massima '
        + '(stake x (quota massima - 1) x 2).',
};

const CONFERMA_SCADE_MS = 10_000;

type Modo = 'live' | 'paper' | null;

function ChipModo({ m, testId }: { m: Modo; testId: string }) {
    if (m === 'live') return <span data-testid={testId} className="text-[9.5px] font-bold px-1 rounded bg-red-500/20 text-red-300">LIVE</span>;
    if (m === 'paper') return <span data-testid={testId} className="text-[9.5px] px-1 rounded border border-white/15 text-slate-300">PAPER</span>;
    return <span data-testid={testId} className="text-[9.5px] px-1 rounded text-orange-300">modo ?</span>;
}

interface Stato { testo: string; cls: string }

function statoConto(c: StopConto | null, live: boolean): { cifra: string; cifraCls: string; stato: Stato } {
    if (c == null || !c.letto) return { cifra: 'non letto', cifraCls: 'text-orange-400', stato: { testo: 'stato del runner non letto', cls: 'text-orange-300' } };
    if (c.scattato) return { cifra: 'SCATTATO: freno generale tirato', cifraCls: 'text-red-400', stato: { testo: 'SCATTATO', cls: 'text-red-400 font-semibold' } };
    // R_T (30/09): nessun freno di conto con soldi veri in gioco = ambra
    if (c.soglia == null) return { cifra: 'SPENTO', cifraCls: live ? 'text-amber-300' : 'text-white/60', stato: { testo: 'nessuno stop', cls: live ? 'text-amber-300' : 'text-white/45' } };
    return { cifra: fmtMoney(-c.soglia), cifraCls: 'text-white', stato: { testo: 'attivo', cls: 'text-emerald-400' } };
}

function statoBot(s: StopBot): { cifra: string; cifraCls: string; stato: Stato } {
    if (s.scattato) return { cifra: s.soglia != null ? fmtMoney(-s.soglia) : 'SCATTATO', cifraCls: 'text-red-400', stato: { testo: 'SCATTATO', cls: 'text-red-400 font-semibold' } };
    // Safe: lo stop lo DICHIARA il servizio, se manca e' assente; Mike e
    // Omega: e' un parametro, se la riga non e' letta non si sa
    if (!s.letto || s.soglia == null) {
        return s.bot === 'safe'
            ? { cifra: 'assente', cifraCls: 'text-orange-400', stato: { testo: 'non dichiarato dal servizio', cls: 'text-orange-300' } }
            : { cifra: 'non letto', cifraCls: 'text-orange-400', stato: { testo: 'parametri non letti', cls: 'text-orange-300' } };
    }
    if (s.soglia === 0) return { cifra: 'spento', cifraCls: 'text-white/50', stato: { testo: 'spento (0)', cls: 'text-white/45' } };
    // R_T (30/09): Omega non pubblica lo scatto: mai presentare la soglia come "armata"
    if (!s.scattoPubblicato) {
        return { cifra: fmtMoney(-s.soglia), cifraCls: 'text-white', stato: { testo: `${BOT_LABEL[s.bot]} non pubblica se lo stop e' scattato`, cls: 'text-white/55' } };
    }
    return { cifra: fmtMoney(-s.soglia), cifraCls: 'text-white', stato: { testo: 'attivo', cls: 'text-emerald-400' } };
}

/**
 * R-03 (review 01/10): lo stop del CONTO chiede conferma a meno che la sua
 * modalita' sia LETTA e sia PAPER e nessun bot (ne' il runner tennis) possa
 * essere LIVE: tira il freno anche per tennis e scalper, e una modalita' non
 * letta potrebbe essere LIVE (stessa regola dei bot).
 */
export function confermaStopConto(qualcheLive: boolean, modoConto: Modo, runnerTennisForseLive = false): boolean {
    return qualcheLive || runnerTennisForseLive || modoConto !== 'paper';
}

/** Perche' lo stop del conto chiede conferma, detto in parole. */
function motivoConfermaConto(qualcheLive: boolean, modoConto: Modo, runnerTennisForseLive: boolean): string {
    if (qualcheLive || modoConto === 'live') return 'Lo stop del Conto protegge i soldi veri';
    if (modoConto == null) return "modalita' del conto non letta (potrebbe essere LIVE): lo stop del Conto protegge i soldi veri";
    if (runnerTennisForseLive) {
        return "il runner tennis consente ordini veri (o il suo stato non e' letto): lo stop del Conto ferma anche tennis e scalper";
    }
    return 'Lo stop del Conto protegge i soldi veri';
}

/**
 * Il valore iniziale del campo: la cifra in vigore col segno meno.
 * R-04 (review 01/10): `fmtNum` NON mette i punti delle migliaia
 * (`itFixed` = toFixed + virgola), quindi il campo si apre gia' con
 * «-12500,00»; esportata solo perche' un test lo tiene fermo.
 */
export function testoIniziale(soglia: number | null | undefined): string {
    if (soglia == null || soglia === 0) return soglia === 0 ? '0' : '';
    return `-${fmtNum(soglia, 2)}`;
}

type Fase =
    | { k: 'vista' }
    | { k: 'modifica'; testo: string; errore: string | null }
    | { k: 'conferma'; testo: string; perdita: number | null }
    | { k: 'salvataggio'; testo: string };

export type SalvaStopFn = typeof salvaStopVero;

/**
 * La cifra di UNO stop, modificabile sul posto.
 * `modificabile=false` = cancello chiuso (parametri non letti): la cifra non
 * apre il campo e il motivo e' scritto accanto.
 */
function CifraStop({
    id, nome, cifra, cifraCls, soglia, modificabile, motivoBlocco, chiedeConferma, motivoConferma,
    raw, salva, onSalvato, etichettaSpento,
}: {
    id: ProprietarioStop;
    nome: string;
    cifra: string;
    cifraCls: string;
    soglia: number | null | undefined;
    modificabile: boolean;
    motivoBlocco: string | null;
    chiedeConferma: boolean;
    motivoConferma: string;
    raw: Record<string, unknown> | null;
    salva: SalvaStopFn;
    onSalvato?: () => void;
    etichettaSpento: string;
}) {
    const [fase, setFase] = useState<Fase>({ k: 'vista' });
    const [esito, setEsito] = useState<{ ok: boolean; testo: string } | null>(null);
    const vivo = useRef(true);
    useEffect(() => () => { vivo.current = false; }, []);

    // la conferma armata scade da sola: una conferma dimenticata non scrive mai
    useEffect(() => {
        if (fase.k !== 'conferma') return undefined;
        const t = window.setTimeout(() => {
            if (vivo.current) setFase({ k: 'modifica', testo: fase.testo, errore: 'conferma scaduta: premi di nuovo Salva' });
        }, CONFERMA_SCADE_MS);
        return () => window.clearTimeout(t);
    }, [fase]);

    async function scrivi(perdita: number | null, testo: string) {
        setFase({ k: 'salvataggio', testo });
        try {
            const letto = await salva(id, perdita, raw);
            if (!vivo.current) return;
            setEsito({
                ok: true,
                testo: letto === undefined
                    ? 'salvato (il database non ha restituito la cifra: attendi la rilettura)'
                    : `salvato: ${letto == null ? etichettaSpento : fmtMoney(-letto)} (letto dal database)`,
            });
            setFase({ k: 'vista' });
            onSalvato?.();
        } catch (e) {
            if (!vivo.current) return;
            const msg = e instanceof Error ? e.message : String(e);
            setFase({ k: 'modifica', testo, errore: `non salvato: ${msg}` });
        }
    }

    function salvaDaCampo(testo: string) {
        const l = leggiImporto(testo, id);
        if (!l.ok) { setFase({ k: 'modifica', testo, errore: l.errore }); return; }
        if (chiedeConferma) { setFase({ k: 'conferma', testo, perdita: l.perdita }); return; }
        void scrivi(l.perdita, testo);
    }

    if (fase.k === 'modifica' || fase.k === 'conferma' || fase.k === 'salvataggio') {
        const testo = fase.testo;
        return (
            <span className="flex flex-col gap-0.5" data-testid={`cr-stop-${id}-editor`}>
                <span className="flex items-center gap-1">
                    <input
                        type="text" inputMode="decimal" autoFocus
                        aria-label={`stop di perdita di ${nome} in euro (negativo = perdita massima)`}
                        className="w-24 rounded border border-white/20 bg-black/40 px-1 py-0.5 text-[12px] font-mono text-white"
                        data-testid={`cr-stop-${id}-campo`}
                        value={testo}
                        disabled={fase.k !== 'modifica'}
                        onChange={(e) => setFase({ k: 'modifica', testo: e.target.value, errore: null })}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && fase.k === 'modifica') salvaDaCampo(fase.testo);
                            if (e.key === 'Escape') setFase({ k: 'vista' });
                        }}
                    />
                    <span className="text-[10px] text-white/40">{'\u20ac'}</span>
                    {fase.k === 'modifica' && (
                        <>
                            <button type="button" data-testid={`cr-stop-${id}-salva`}
                                className="text-[10.5px] px-1.5 py-0.5 rounded bg-secondary/20 text-secondary hover:bg-secondary/30"
                                onClick={() => salvaDaCampo(fase.testo)}>Salva</button>
                            <button type="button" data-testid={`cr-stop-${id}-annulla`}
                                className="text-[10.5px] px-1.5 py-0.5 rounded text-white/60 hover:text-white"
                                onClick={() => setFase({ k: 'vista' })}>Annulla</button>
                        </>
                    )}
                    {fase.k === 'salvataggio' && <span className="text-[10.5px] text-white/50" data-testid={`cr-stop-${id}-in-corso`}>{'salvataggio\u2026'}</span>}
                </span>
                {fase.k === 'modifica' && fase.errore && (
                    <span className="text-[10px] text-red-300" data-testid={`cr-stop-${id}-errore`}>{fase.errore}</span>
                )}
                {fase.k === 'modifica' && !fase.errore && (
                    <span className="text-[9.5px] text-white/35">
                        {id === 'conto' ? 'euro al centesimo, es. \u221250; vuoto = stop spento' : 'euro al centesimo, es. \u221250; 0 = stop spento'}
                    </span>
                )}
                {fase.k === 'conferma' && (
                    <span className="flex items-center gap-1 flex-wrap text-[10.5px]" data-testid={`cr-stop-${id}-richiesta-conferma`}>
                        <span className="text-red-300 font-semibold">{motivoConferma}: confermi {fase.perdita == null ? etichettaSpento : `lo stop a ${fmtMoney(-fase.perdita)}`}?</span>
                        <button type="button" data-testid={`cr-stop-${id}-conferma`}
                            className="px-1.5 py-0.5 rounded bg-red-500/25 text-red-200 hover:bg-red-500/35 font-semibold"
                            onClick={() => void scrivi(fase.perdita, fase.testo)}>Conferma</button>
                        <button type="button" data-testid={`cr-stop-${id}-annulla-conferma`}
                            className="px-1.5 py-0.5 rounded text-white/60 hover:text-white"
                            onClick={() => setFase({ k: 'modifica', testo: fase.testo, errore: null })}>Annulla</button>
                    </span>
                )}
            </span>
        );
    }

    return (
        <span className="flex flex-col">
            <span className="flex items-center gap-1">
                <button
                    type="button"
                    data-testid={`cr-stop-${id}-valore`}
                    disabled={!modificabile}
                    onClick={() => { setEsito(null); setFase({ k: 'modifica', testo: testoIniziale(soglia), errore: null }); }}
                    className={`font-mono text-[13px] font-bold tabular-nums ${cifraCls} ${modificabile ? 'hover:underline decoration-dotted cursor-pointer' : 'cursor-not-allowed'}`}
                    title={modificabile ? `clic per modificare lo stop di ${nome}` : (motivoBlocco ?? 'non modificabile')}
                >{cifra}</button>
                {modificabile && (
                    <button type="button" data-testid={`cr-stop-${id}-matita`}
                        onClick={() => { setEsito(null); setFase({ k: 'modifica', testo: testoIniziale(soglia), errore: null }); }}
                        className="text-white/35 hover:text-white/80" aria-label={`modifica lo stop di ${nome}`}>
                        <Pencil className="w-3 h-3" />
                    </button>
                )}
            </span>
            {!modificabile && motivoBlocco && (
                <span className="text-[9.5px] text-orange-300/80" data-testid={`cr-stop-${id}-non-modificabile`}>{motivoBlocco}</span>
            )}
            {esito && (
                <span className={`text-[9.5px] ${esito.ok ? 'text-emerald-300' : 'text-red-300'}`} data-testid={`cr-stop-${id}-esito`}>{esito.testo}</span>
            )}
        </span>
    );
}

export interface StatoServizio { fonte?: 'canale' | 'database'; etaS?: number | null }

function fonteServizio(s: StatoServizio | undefined): string {
    if (!s?.fonte) return 'stato del servizio non letto';
    const eta = s.etaS == null ? '?' : fmtAge(s.etaS);
    return `${s.fonte === 'canale' ? 'canale' : 'database'} \u00b7 ${eta} fa`;
}

export function StopPerdita({
    stop, vai = vaiAllaRigaDelBot, qualcheBotLive, runnerTennisForseLive, params, statoServizio, strategieLive, salva = salvaStopVero, onSalvato,
}: {
    /** R-03 (review 01/10): il runner tennis PUO' servire ordini veri (tetto
     *  LIVE_ORDER_MODE letto e non PAPER/OFF) o il suo stato non e' letto.
     *  Lo stop del conto ferma anche tennis e scalper: si conferma. Solo per
     *  la conferma, non cambia i colori della riga. */
    runnerTennisForseLive?: boolean;
    /** 01/10: Safe con almeno una strategia in LIVE (`modiStrategia`) anche
     *  se la sua modalita' di servizio e' PAPER: lo stop e' comune, si conferma */
    strategieLive?: Partial<Record<BotConStop, boolean>>;
    stop: StopPerditaTestata | undefined;
    /** iniettabile per i test */
    vai?: (bot: string) => boolean;
    /** R_T (30/09): almeno un bot (qualunque, acceso o fermo) dichiara LIVE.
     *  Assente = si guarda solo Safe/Mike/Omega. */
    qualcheBotLive?: boolean;
    /** 01/10: i parametri GREZZI di ogni bot (`vm.bots[].params`): il cancello
     *  "parametri non letti" e la base del salvataggio. Assenti = non modificabile. */
    params?: Partial<Record<BotConStop, Record<string, unknown> | null>>;
    /** 01/10: fonte ed eta' dello stato di ogni servizio (`vm.bots[].fonteStato/etaStatoS`) */
    statoServizio?: Partial<Record<BotConStop, StatoServizio>>;
    /** iniettabile per i test: di default le funzioni di scrittura vere */
    salva?: SalvaStopFn;
    /** dopo un salvataggio riuscito (la pagina rilegge: `vm.ricarica`) */
    onSalvato?: () => void;
}) {
    const c = stop?.conto ?? null;
    const live = qualcheBotLive ?? (stop?.bot ?? []).some((b) => b.modalita === 'live');
    const sc = statoConto(c, live);
    const letti = (p: Record<string, unknown> | null | undefined) => p != null && Object.keys(p).length > 0;

    return (
        <div className="flex flex-col gap-0.5" data-testid="cr-stop-perdita">
            <span className="text-[10px] uppercase tracking-wider text-white/45">Stop perdita giornaliera</span>
            <div className="grid grid-cols-[auto_auto_auto_auto_auto] items-start gap-x-2.5 gap-y-1 text-[11px]">
                {/* --- CONTO */}
                <div className="contents" data-testid="cr-stop-conto"
                    title={c?.letto
                        ? `stop del CONTO (betfair_live_settings.daily_loss_limit, applicato dal runner calcio): raggiunto, tira il freno generale.${c.motivo ? ` Stato del runner: ${c.motivo}.` : ''} Riga aggiornata al cambio, ultimo cambio ${fmtAge(c.etaS)} fa.`
                        : 'stato dello stop del conto (betfair_live_risk_state) non ancora letto'}>
                    <span className="font-semibold text-white/85" data-testid="cr-stop-conto-nome">Conto</span>
                    <span title="la modalita' su cui il runner calcola lo stop del conto"><ChipModo m={c?.modo ?? null} testId="cr-stop-conto-modo" /></span>
                    <span data-testid="cr-stop-conto-cifra">
                        <CifraStop
                            id="conto" nome="Conto" cifra={sc.cifra} cifraCls={sc.cifraCls} soglia={c?.soglia ?? null}
                            modificabile={c?.letto === true}
                            motivoBlocco={c?.letto ? null : 'stato del runner non letto: modifica non disponibile qui'}
                            chiedeConferma={confermaStopConto(live, c?.modo ?? null, runnerTennisForseLive === true)}
                            motivoConferma={motivoConfermaConto(live, c?.modo ?? null, runnerTennisForseLive === true)}
                            raw={null} salva={salva} onSalvato={onSalvato}
                            etichettaSpento="lo stop del conto SPENTO"
                        />
                    </span>
                    <span className={sc.stato.cls} data-testid="cr-stop-conto-stato">
                        {sc.stato.testo}
                        {c?.letto && c.soglia != null && c.oggi != null && (
                            <span className={`block font-mono ${c.oggi < 0 ? 'text-red-300' : 'text-white/50'}`} data-testid="cr-stop-conto-oggi"
                                title="P&L di giornata secondo il runner calcio (regolato dal conto + aperto stimato)">
                                oggi {fmtMoney(c.oggi, { signed: true })}{c.degradato ? ' (stima degradata)' : ''}
                            </span>
                        )}
                    </span>
                    <span className="text-[9.5px] text-white/35" data-testid="cr-stop-conto-fonte">
                        {c?.letto ? `runner calcio \u00b7 cambio ${c.etaS == null ? '?' : fmtAge(c.etaS)} fa` : 'runner: non letto'}
                    </span>
                </div>

                {/* --- BOT */}
                {(stop?.bot ?? []).map((s) => {
                    const v = statoBot(s);
                    const raw = params?.[s.bot] ?? null;
                    const aperto = letti(raw);
                    return (
                        <div key={s.bot} className="contents" data-testid={`cr-stop-${s.bot}`}
                            title={`stop di ${BOT_LABEL[s.bot]}: ${s.fonte}. Foglio completo: ${s.dove}. Vale solo per le aperture di ${BOT_LABEL[s.bot]}.`}>
                            <span className="font-semibold text-white/85 flex items-center gap-1">
                                {BOT_LABEL[s.bot]}
                                <button type="button" onClick={() => vai(s.bot)} data-testid={`cr-stop-${s.bot}-modifica`}
                                    className="text-white/30 hover:text-white/70"
                                    aria-label={`apri tutti i parametri di ${BOT_LABEL[s.bot]}`}
                                    title={`tutti i parametri di ${BOT_LABEL[s.bot]} (Comando dei bot)`}>
                                    <SlidersHorizontal className="w-3 h-3" />
                                </button>
                            </span>
                            <ChipModo m={s.modalita} testId={`cr-stop-${s.bot}-modo`} />
                            <span data-testid={`cr-stop-${s.bot}-cifra`}>
                                <CifraStop
                                    id={s.bot} nome={BOT_LABEL[s.bot]} cifra={v.cifra} cifraCls={v.cifraCls}
                                    soglia={s.soglia}
                                    modificabile={aperto}
                                    motivoBlocco={aperto ? null : 'parametri non letti: modifica disabilitata'}
                                    chiedeConferma={s.modalita !== 'paper' || strategieLive?.[s.bot] === true}
                                    motivoConferma={s.modalita === 'live'
                                        ? `${BOT_LABEL[s.bot]} e' in LIVE (soldi veri)`
                                        : s.modalita == null
                                            ? `modalita' di ${BOT_LABEL[s.bot]} non letta (potrebbe essere LIVE)`
                                            : `${BOT_LABEL[s.bot]} ha strategie in LIVE (soldi veri): lo stop vale anche per loro`}
                                    raw={raw} salva={salva} onSalvato={onSalvato}
                                    etichettaSpento="stop spento (0)"
                                />
                            </span>
                            <span className={v.stato.cls} data-testid={`cr-stop-${s.bot}-stato`}>{v.stato.testo}</span>
                            <span className="text-[9.5px] text-white/35" data-testid={`cr-stop-${s.bot}-fonte`}>
                                {s.bot === 'safe' ? 'servizio Safe' : `parametro ${BOT_LABEL[s.bot]}`}{' \u00b7 '}{fonteServizio(statoServizio?.[s.bot])}
                            </span>
                        </div>
                    );
                })}
            </div>
            <span className="text-white/45 text-[10px]" data-testid="cr-stop-altri" title={NOTA_TENNIS_SCALPER.titolo}>
                {NOTA_TENNIS_SCALPER.testo}
            </span>
        </div>
    );
}

export default StopPerdita;
