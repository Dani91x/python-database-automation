// ============================================================================
// ApplicaBotPanel — il riquadro «Applica bot» del replay (06/10; TUTTI i bot
// dal 07/10). Riusabile: Match Replay (sport="calcio") e Replay Tennis
// (sport="tennis"); calcio e tennis non si mischiano.
// Ordine delle scelte: BOT (solo quelli dello sport) -> SCENARIO del bot ->
// «Prova» / «Soldi veri simulati» dove lo scenario li ha entrambi -> PARAMETRI
// (pannello a tendina, valori di serie sempre visibili) -> «accendi il bot
// all'istante del cursore» -> Applica. Il catalogo e' quello GENERATO dal
// backend (replayBotCatalogo.ts): niente elenchi a mano.
// La richiesta e il suo stato li tiene `useApplicaBot` (prop `applica`): il
// risultato si mostra con EsitoBotPanel e sul ladder con ordiniBotAlMs.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { ParametriBotPanel } from '@/components/replay/ParametriBotPanel';
import {
    ETICHETTA_MODALITA, botDelloSport, famiglieScenari, modalitaDisponibile, motivoMercatiMancanti, sostituzioni,
    testoIstante, tipiMercatoRegistrati,
} from '@/lib/applicaBot';
import { CATALOGO_BOT } from '@/lib/replayBotCatalogo';
import type { CatalogoBot, ModalitaScenario, SportBot } from '@/lib/replayBot';
import { ATTESA_BANCO_SPENTO_MS, type ApplicaBot } from '@/lib/useApplicaBot';

// lo stesso select del Match Replay (tema scuro della pagina)
const CLS_SELECT = 'px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]';
const CLS_OPZIONE = 'bg-neutral-900 text-white';

export interface ApplicaBotPanelProps {
    /** lo sport della pagina: si offrono SOLO i bot di questo sport */
    sport: SportBot;
    /** la partita registrata aperta ('' = nessuna) */
    eventId: string;
    /** l'istante corrente della barra del replay (ms, orologio dei frame) */
    cursoreMs: number;
    /** richiesta ed esito (useApplicaBot) */
    applica: ApplicaBot;
    /** di serie il catalogo generato; i test ne passano uno loro */
    catalogo?: ReadonlyArray<CatalogoBot>;
    /** testo in piu' per un istante (es. il minuto di gioco) */
    etichettaIstante?: (ms: number) => string;
    /**
     * 08/10 (Replay Tennis): i tipi di mercato REGISTRATI per la partita (dal
     * catalogo del replay). undefined = non noti (Match Replay calcio: nessun
     * controllo). Se il bot non ha il suo mercato, «Applica» resta spento col motivo.
     */
    mercatiRegistrati?: ReadonlyArray<string | null> | null;
}

function testoStato(a: ApplicaBot): { testo: string; errore: boolean } {
    const r = a.richiesta;
    if (!r) return { testo: 'codice di produzione sul banco: coda, bet delay, minimi .it', errore: false };
    if (r.errore) return { testo: `errore: ${r.errore}`, errore: true };
    const st = r.stato?.status;
    if (st === 'PENDING') {
        return (Date.now() - (r.inviataMs ?? Date.now())) > ATTESA_BANCO_SPENTO_MS
            ? { testo: 'il BANCO DEL REPLAY NON È ACCESO: parte all’avvio dell’app, quindi CHIUDI e RIAPRI l’app (dopo l’aggiornamento) e la richiesta partirà da sola', errore: true }
            : { testo: 'richiesta inviata, il banco la sta prendendo…', errore: false };
    }
    if (st === 'RUNNING') {
        const n = r.inviato?.opzioni.clic_ms?.length ?? 0;
        return { testo: `ricalcolo: il bot sta girando sulla registrazione${n ? ` con ${n} clic «Attiva adesso»` : ''} (qualche minuto)…`, errore: false };
    }
    if (st === 'ERROR') return { testo: `errore: ${r.stato?.error_detail ?? ''}`, errore: true };
    if (st === 'DONE' && r.stato?.esito) {
        return { testo: `${r.stato.esito.etichetta}: ${r.stato.esito.ordini} ordini — scorri la timeline`, errore: false };
    }
    return { testo: '', errore: false };
}

export function ApplicaBotPanel({
    sport, eventId, cursoreMs, applica, catalogo = CATALOGO_BOT, etichettaIstante, mercatiRegistrati,
}: ApplicaBotPanelProps) {
    const bots = useMemo(() => botDelloSport(catalogo, sport), [catalogo, sport]);
    const [botScelto, setBotScelto] = useState('');
    const [famigliaScelta, setFamigliaScelta] = useState('');
    const [modalitaVoluta, setModalitaVoluta] = useState<ModalitaScenario>('prova');
    const [valori, setValori] = useState<Record<string, unknown>>({});
    const [accendiDalCursore, setAccendiDalCursore] = useState(false);
    const [clic, setClic] = useState<number[]>([]);

    const bot = bots.find(b => b.bot === botScelto) ?? null;
    const famiglie = useMemo(() => (bot ? famiglieScenari(bot) : []), [bot]);
    const famiglia = famiglie.find(f => f.famiglia === famigliaScelta) ?? null;
    const modalita = famiglia ? modalitaDisponibile(famiglia, modalitaVoluta) : modalitaVoluta;
    const scenario = famiglia?.modi[modalita] ?? null;
    const voci = scenario?.parametri ?? [];
    const { cambiati, errori } = sostituzioni(voci, valori);
    const nErrori = Object.keys(errori).length;
    const stato = testoStato(applica);
    // 08/10: il bot non ha il suo mercato registrato su questa partita -> nessun clic a vuoto
    const motivoMercati = bot ? motivoMercatiMancanti(eventId, sport, bot.mercati, mercatiRegistrati) : null;
    const istante = (ms: number) => `${testoIstante(ms)}${etichettaIstante ? ` · ${etichettaIstante(ms)}` : ''}`;

    const scegliBot = (b: string) => {
        setBotScelto(b);
        setFamigliaScelta('');
        setValori({});
        setClic([]);
    };
    const scegliFamiglia = (f: string) => {
        setFamigliaScelta(f);
        setValori({});
    };
    const cambia = (chiave: string, valore: unknown) => setValori(v => {
        const n = { ...v };
        if (valore === undefined) delete n[chiave]; else n[chiave] = valore;
        return n;
    });
    // l'istante di accensione resta quello del momento in cui e' stato deciso
    // (spunta + Applica): un clic «Attiva adesso» successivo rilancia la STESSA
    // prova con un clic in piu', non sposta l'accensione al nuovo cursore
    const [dalMs, setDalMs] = useState<number | undefined>(undefined);
    const avvia = (clicDaMandare: number[] = clic, dal: number | undefined = accendiDalCursore ? (dalMs ?? cursoreMs) : undefined) => {
        if (!bot || !scenario || !eventId) return;
        if (accendiDalCursore && dal != null) setDalMs(dal);
        applica.invia(eventId, bot.bot, scenario.scenario, {
            parametri: cambiati,
            dal_ms: dal,
            // un clic allo STESSO istante dell'accensione e' gia' l'accensione
            // (la media under tratta dal_ms come il primo clic): non si raddoppia
            clic_ms: bot.clic_ms && clicDaMandare.some(c => c !== dal) ? clicDaMandare.filter(c => c !== dal) : undefined,
        });
    };
    const puoAvviare = !!bot && !bot.disattivato && !motivoMercati && !!scenario && !!eventId && nErrori === 0 && !applica.inCorso;
    // 07/10 sera (caso vero dell'utente: clic accodati in silenzio, mai partiti):
    // i clic NON ancora mandati al banco sono quelli che non sono nell'ultima
    // richiesta; finita la richiesta in corso, partono da soli
    const mandati = [...(applica.inviato?.clic_ms ?? []),
        ...(applica.inviato?.dal_ms != null ? [applica.inviato.dal_ms] : [])];
    const daMandare = clic.filter(c => !mandati.includes(c));
    const tolti = (applica.inviato?.clic_ms ?? []).filter(c => !clic.includes(c));
    const modificheClic = daMandare.length > 0 || tolti.length > 0;
    const pronto = !!bot && !bot.disattivato && !motivoMercati && !!scenario && !!eventId && nErrori === 0;
    useEffect(() => {
        if (!applica.inCorso && modificheClic && pronto && applica.inviato != null) avvia(clic, applica.inviato.dal_ms);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [applica.inCorso]);
    const attivaAdesso = () => {
        if (!pronto || cursoreMs <= 0 || clic.includes(cursoreMs)) return;
        const nuovi = [...clic, cursoreMs].sort((a, b) => a - b);
        setClic(nuovi);
        // il clic AGISCE SUBITO: si rilancia il banco con tutti i clic (il replay
        // e' deterministico: stesso risultato della realta'); se una prova e' gia'
        // in corso, il clic resta «da mandare» (ben visibile) e parte alla fine
        if (!applica.inCorso) avvia(nuovi, applica.inviato ? applica.inviato.dal_ms : (accendiDalCursore ? cursoreMs : undefined));
    };
    const togliClic = (ms: number) => {
        const nuovi = clic.filter(x => x !== ms);
        setClic(nuovi);
        if (!applica.inCorso && applica.inviato) avvia(nuovi, applica.inviato.dal_ms);
    };

    return (
        <div className="rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2 space-y-2 text-[11px]"
            data-testid="applica-bot">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-black text-amber-200">🤖 Applica bot</span>
                <select
                    value={botScelto}
                    onChange={e => scegliBot(e.target.value)}
                    aria-label="Bot da applicare al replay"
                    style={{ colorScheme: 'dark' }}
                    className={CLS_SELECT}
                    data-testid="applica-bot-bot"
                >
                    <option value="" className={CLS_OPZIONE}>— scegli un bot —</option>
                    <optgroup label={sport === 'calcio' ? 'Calcio' : 'Tennis'} className={CLS_OPZIONE}>
                        {bots.map(b => (
                            <option key={b.bot} value={b.bot} disabled={!!b.disattivato}
                                title={b.disattivato ?? b.descrizione} className={CLS_OPZIONE}>
                                {b.etichetta}{b.disattivato ? ' (non disponibile)' : ''}
                            </option>
                        ))}
                    </optgroup>
                </select>
                {bot && (
                    <select
                        value={famigliaScelta}
                        onChange={e => scegliFamiglia(e.target.value)}
                        aria-label="Scenario del bot"
                        style={{ colorScheme: 'dark' }}
                        className={CLS_SELECT}
                        data-testid="applica-bot-scenario"
                    >
                        <option value="" className={CLS_OPZIONE}>— scegli lo scenario —</option>
                        {famiglie.map(f => (
                            <option key={f.famiglia} value={f.famiglia} className={CLS_OPZIONE}
                                title={(f.modi.soldi_veri_simulati ?? f.modi.prova)?.descrizione}>
                                {f.famiglia}
                            </option>
                        ))}
                    </select>
                )}
                {famiglia && (
                    <div role="radiogroup" aria-label="Modalita'" className="flex gap-1" data-testid="applica-bot-modalita">
                        {(['prova', 'soldi_veri_simulati'] as const).map(m => (
                            <Button key={m} type="button" size="sm" role="radio" aria-checked={modalita === m}
                                variant={modalita === m ? 'default' : 'outline'}
                                disabled={!famiglia.modi[m]}
                                title={famiglia.modi[m] ? famiglia.modi[m]?.nota : 'questo scenario non ha questa modalita’'}
                                onClick={() => setModalitaVoluta(m)}
                                className="h-7 text-[11px]">
                                {ETICHETTA_MODALITA[m]}
                            </Button>
                        ))}
                    </div>
                )}
                <Button
                    size="sm" variant="outline"
                    disabled={!puoAvviare}
                    onClick={() => avvia(clic)}
                    className="h-7 border-amber-300/40 text-amber-100 hover:bg-amber-500/20 text-[11px] font-bold"
                    title="Fa girare il bot con il codice di produzione sulla registrazione di questa partita (worker del Backtest Automatico): coda, bet delay e minimi come dal vivo"
                    data-testid="applica-bot-avvia"
                >
                    Applica
                </Button>
                <span data-testid="stato-applica-bot" className={stato.errore ? 'text-red-300 font-bold' : 'text-white/70'}>
                    {stato.testo}
                </span>
            </div>
            {mercatiRegistrati != null && (
                <div className="text-white/60" data-testid="applica-bot-mercati-registrati">
                    mercati registrati: {tipiMercatoRegistrati(mercatiRegistrati).join(', ') || 'nessuno (solo punteggi)'}
                </div>
            )}
            {motivoMercati && (
                <div className="text-red-300 font-bold" data-testid="applica-bot-mercato-mancante">
                    Applica non disponibile: {motivoMercati}
                </div>
            )}
            {bot?.disattivato && (
                <div className="text-red-300" data-testid="applica-bot-disattivato">
                    {bot.etichetta} non si può applicare: {bot.disattivato}
                </div>
            )}
            {scenario && (
                <>
                    <div className="text-white/60" data-testid="applica-bot-descrizione">{scenario.descrizione}</div>
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex items-center gap-2">
                            <Checkbox id="applica-bot-accendi" checked={accendiDalCursore}
                                onCheckedChange={c => setAccendiDalCursore(c === true)}
                                data-testid="applica-bot-accendi" />
                            <Label htmlFor="applica-bot-accendi" className="text-[11px] font-normal">
                                accendi il bot all&apos;istante del cursore
                            </Label>
                            {accendiDalCursore && cursoreMs > 0 && (
                                <Badge variant="secondary" className="text-[10px]" data-testid="applica-bot-istante">
                                    acceso dalle {istante(cursoreMs)}
                                </Badge>
                            )}
                        </div>
                        {bot?.clic_ms && (
                            <div className="flex items-center gap-1 flex-wrap" data-testid="applica-bot-clic">
                                <Button type="button" size="sm" className="h-7 text-[11px] font-black bg-amber-500 text-black hover:bg-amber-400"
                                    disabled={!pronto || cursoreMs <= 0 || clic.includes(cursoreMs)}
                                    onClick={attivaAdesso}
                                    title="Come il pulsante vero: il bot riceve «Attiva adesso» all'istante del cursore. Il banco rilancia SUBITO la prova con tutti i clic (deterministico: stesso risultato della realta')."
                                    data-testid="applica-bot-attiva-adesso">
                                    ⚡ Attiva adesso al cursore
                                </Button>
                                {clic.map(ms => {
                                    const inviato = mandati.includes(ms);
                                    return (
                                        <Badge key={ms} variant="outline" data-testid="applica-bot-clic-voce" data-inviato={inviato ? '1' : '0'}
                                            className={`text-[10px] gap-1 ${inviato ? '' : 'border-red-400 text-red-200 bg-red-500/20'}`}>
                                            {istante(ms)}{inviato ? (applica.inCorso ? ' · in ricalcolo' : '') : ' · NON ANCORA INVIATO'}
                                            <button type="button" aria-label={`togli il clic delle ${testoIstante(ms)}`}
                                                onClick={() => togliClic(ms)}>×</button>
                                        </Badge>
                                    );
                                })}
                                {modificheClic && (
                                    <span className="text-red-300 font-bold" data-testid="applica-bot-clic-pendenti">
                                        {daMandare.length > 0 ? `${daMandare.length} clic non ancora inviati al banco` : 'clic tolti non ancora ricalcolati'}
                                        {applica.inCorso ? ': partono appena finisce il ricalcolo in corso' : ''}
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                    <ParametriBotPanel voci={voci} valori={valori} onCambia={cambia}
                        onRipristina={() => setValori({})} disabilitato={applica.inCorso} />
                    {scenario.errore_parametri && (
                        <div className="text-red-300">parametri non disponibili: {scenario.errore_parametri}</div>
                    )}
                </>
            )}
        </div>
    );
}
