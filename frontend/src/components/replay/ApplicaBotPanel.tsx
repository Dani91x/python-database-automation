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
import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { ParametriBotPanel } from '@/components/replay/ParametriBotPanel';
import {
    ETICHETTA_MODALITA, botDelloSport, famiglieScenari, modalitaDisponibile, sostituzioni, testoIstante,
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
    if (st === 'RUNNING') return { testo: 'il bot sta girando sulla registrazione (qualche minuto)…', errore: false };
    if (st === 'ERROR') return { testo: `errore: ${r.stato?.error_detail ?? ''}`, errore: true };
    if (st === 'DONE' && r.stato?.esito) {
        return { testo: `${r.stato.esito.etichetta}: ${r.stato.esito.ordini} ordini — scorri la timeline`, errore: false };
    }
    return { testo: '', errore: false };
}

export function ApplicaBotPanel({
    sport, eventId, cursoreMs, applica, catalogo = CATALOGO_BOT, etichettaIstante,
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
    const avvia = () => {
        if (!bot || !scenario || !eventId) return;
        applica.invia(eventId, bot.bot, scenario.scenario, {
            parametri: cambiati,
            dal_ms: accendiDalCursore ? cursoreMs : undefined,
            clic_ms: bot.clic_ms && clic.length > 0 ? clic : undefined,
        });
    };
    const puoAvviare = !!bot && !bot.disattivato && !!scenario && !!eventId && nErrori === 0 && !applica.inCorso;

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
                    onClick={avvia}
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
                                <Button type="button" size="sm" variant="outline" className="h-7 text-[11px]"
                                    disabled={cursoreMs <= 0 || clic.includes(cursoreMs)}
                                    onClick={() => setClic(c => [...c, cursoreMs].sort((a, b) => a - b))}>
                                    + clic «Attiva adesso» al cursore
                                </Button>
                                {clic.map(ms => (
                                    <Badge key={ms} variant="outline" className="text-[10px] gap-1">
                                        {istante(ms)}
                                        <button type="button" aria-label={`togli il clic delle ${testoIstante(ms)}`}
                                            onClick={() => setClic(c => c.filter(x => x !== ms))}>×</button>
                                    </Badge>
                                ))}
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
