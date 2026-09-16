// ============================================================================
// PannelloBot.tsx — LA PLANCIA DI COMANDO: UN INTERRUTTORE PER OGNI BOT.
//
// «Voglio poter attivare OGNI SINGOLO BOT direttamente dalla Control Room» e
// «devo poter attivare e spegnere tutto dalla UI, sia paper che live, in
// maniera facile e diretta» (utente, 16/09).
//
// COSA FA, e niente di più: usa i comandi condivisi di `@/lib/interruttori`,
// che sono gli stessi che usano le pagine dei singoli bot, e monta i fogli
// parametri che esistono già (`BotParamsSheet` di Safe, `MikeParamsSheet` di
// Mike). Qui non nasce nessun parametro nuovo e nessuna semantica nuova.
//
// UNA RIGA = UN INTERRUTTORE, NON UN PROCESSO. Safe è un servizio solo ma
// porta dentro quattro strategie: base, esatto, punta (calcio) e tennis.
// Ognuna ha la sua riga, il suo acceso/spento e la sua modalità, perché è così
// che l'utente le comanda. Lo stato di ciascuna si legge da dove il servizio
// lo scrive già (`params.variants` + `params.strategy_modes`), mai da un flag
// inventato qui.
//
// LE TRE REGOLE DI SICUREZZA
//
//  1. **Accendere in LIVE si conferma due volte.** È l'unico gesto di questa
//     pagina che mette a rischio denaro vero senza che ci sia già una
//     posizione aperta. Il secondo pulsante compare dove stava il primo, così
//     il dito non si sposta: la protezione costa un clic, non un viaggio.
//  2. **FERMA TUTTI non chiede niente.** Un freno d'emergenza con una finestra
//     di conferma davanti non è un freno d'emergenza. Ferma i SERVIZI, non le
//     singole strategie: è il gesto più grosso che c'è.
//  3. **Quello che il pulsante ha fatto si vede.** Lo stato mostrato è quello
//     che RISPONDE il servizio, non quello che speravamo: `stopping` si
//     scrive «sta fermandosi», non «fermo».
//
// COSA NON FA: non chiude posizioni. Fermare un bot lascia il banco
// sorvegliato — riconciliazione, settlement e uscite continuano a girare
// (`bot_service.py`: «SEMPRE, anche a bot fermo: mai posizioni nude»).
// ============================================================================
import { useEffect, useState, type ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Power, Square, SlidersHorizontal, AlertTriangle, Loader2, Ban } from 'lucide-react';
import { fmtMoney, fmtAge, DASH } from '@/lib/format';
import { BOT_LABEL, type Bot } from '@/lib/controlRoom';
import type {
    CampoImporto, InterruttoreId, Modalita, ComandiInterruttori,
} from '@/lib/interruttori';

export type { CampoImporto, Modalita } from '@/lib/interruttori';

/** Le parole dello stato del servizio. Ogni stato che i servizi scrivono ha
 *  una frase sua: «sta fermandosi» e «fermo» non sono la stessa cosa. */
const STATO_TESTO: Record<string, string> = {
    running: 'in esecuzione',
    stopping: 'sta fermandosi',
    stopped: 'fermo',
    idle: 'fermo',
    error: 'in errore',
    ignoto: 'stato non letto',
};

const STATO_CLS: Record<string, string> = {
    running: 'text-emerald-400',
    stopping: 'text-amber-300',
    stopped: 'text-white/40',
    idle: 'text-white/40',
    error: 'text-red-400',
    ignoto: 'text-orange-400',
};

/**
 * Una riga della plancia: UN interruttore, con tutto quello che il servizio
 * dichiara su di lui. La pagina non deduce niente: se un campo non c'è, la
 * riga lo dice invece di inventarlo.
 */
export interface RigaInterruttore {
    id: InterruttoreId;
    bot: Bot;
    /** come si chiama davanti al trader in questo contesto */
    etichetta: string;
    /** sta aprendo? Per Safe: servizio in corsa E strategia in `variants` */
    acceso: boolean;
    /** con che soldi. `null` = il servizio non la dichiara */
    modalita: Modalita | null;
    /** sappiamo davvero che cosa sta facendo? no = non si comanda */
    statoNoto: boolean;
    /** la parola da mostrare: running / stopping / stopped / error / ignoto */
    stato: string;
    /** età dell'ultimo messaggio dal canale locale del bot */
    etaPushS: number | null;
    /** perché non apre, DICHIARATO dal servizio */
    motivoBlocco: string | null;
    tettoPartite: number | null;
    partiteEsposte: number | null;
    stopFermaSoloAperture: boolean;
    fermatoAllAvvioAt: string | null;
    /** true sulla PRIMA riga di ciascun bot: lì va il foglio parametri, che è
     *  del servizio e non della singola strategia */
    primaDelBot: boolean;
}

export interface PannelloBotProps {
    righe: RigaInterruttore[];
    /** gli importi di ciascun interruttore, con le chiavi vere del servizio */
    importi: Partial<Record<InterruttoreId, CampoImporto[]>>;
    /**
     * Il foglio parametri di ciascun BOT. Arriva dalla pagina come nodo gia'
     * montato — sono gli STESSI componenti delle pagine dei bot
     * (`BotParamsSheet`, `MikeParamsSheet`), non una copia: due schede
     * parametri per lo stesso servizio sarebbero due verita'. Compare una
     * volta sola per bot, sulla sua prima riga.
     */
    parametri?: Partial<Record<Bot, ReactNode>>;
    comandi: ComandiInterruttori;
    /** il titolo della plancia: cambia quando la plancia e' ristretta a uno
     *  sport («Bot del tennis»), perche' «Comando dei bot» al plurale davanti
     *  a una riga sola e' una promessa che la pagina non sta mantenendo. */
    titolo?: string;
    /** una riga sotto la testata: che cosa fara' DAVVERO il pulsante avvia. */
    nota?: ReactNode;
    /**
     * ⚠️ REVIEW 15/09, CRITICO — L'AMBITO IN CUI SI STA COMANDANDO.
     *
     * Entra nella `key` delle righe, e serve a UNA cosa sola: quando il
     * significato dei pulsanti cambia (dalla scheda tennis «avvia in live»
     * vuol dire «solo il tennis», dalla pagina intera vuol dire «accendi
     * questa strategia»), la riga viene RIMONTATA e la conferma rossa gia'
     * armata si disarma.
     */
    ambito?: string;
    /**
     * TUTTI i servizi in corsa, anche quelli non mostrati. «Ferma tutti» e' un
     * freno d'emergenza: deve fermare tutto quello che c'e', non quello che il
     * filtro sta facendo vedere. Sono BOT, non strategie.
     */
    serviziAccesi?: { bot: Bot; modalita: Modalita | null }[];
    testId?: string;
}

export function PannelloBot({
    righe, importi, comandi, parametri, titolo = 'Comando dei bot', nota,
    ambito = 'tutti', serviziAccesi, testId = 'cr-pannello-bot',
}: PannelloBotProps) {
    const [inCorso, setInCorso] = useState<InterruttoreId | 'tutti' | null>(null);
    /** chi NON si è fermato: un freno d'emergenza deve dire che cosa ha
     *  mancato, o il trader crede che sia tutto spento. */
    const [nonFermati, setNonFermati] = useState<Bot[]>([]);
    // ⚠️ REVIEW 15/09 — il freno d'emergenza guarda TUTTI i servizi, non
    // quelli che il filtro mostra: nella scheda tennis «ferma tutti» avrebbe
    // lasciato correre Mike e Omega.
    const accesi = serviziAccesi ?? [];
    const inLive = accesi.filter((b) => b.modalita === 'live');

    const fermaTutti = async () => {
        setInCorso('tutti'); setNonFermati([]);
        const falliti: Bot[] = [];
        try {
            // uno alla volta e in sequenza: se il terzo fallisce, i primi due
            // sono comunque fermi. In parallelo un errore lascerebbe uno stato
            // che nessuno sa leggere.
            //
            // ⚠️ REVIEW 15/09 — QUI NON C'ERA IL `catch`, e il ciclo si
            // interrompeva al primo errore: i bot successivi non ricevevano
            // nemmeno la chiamata. Un freno d'emergenza che si arrende a metà
            // non è un freno d'emergenza: ADESSO LI PROVA TUTTI.
            for (const b of accesi) {
                try { await comandi.fermaBot(b.bot); } catch { falliti.push(b.bot); }
            }
        } finally {
            setInCorso(null);
            setNonFermati(falliti);
        }
    };

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60"
                    data-testid={`${testId}-titolo`}>{titolo}</span>
                <div className="flex items-center gap-2">
                    {inLive.length > 0 && (
                        <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/20 text-red-300"
                            data-testid="cr-quanti-live">
                            {inLive.length} con soldi veri
                        </span>
                    )}
                    <Button
                        type="button" size="sm" variant="outline"
                        disabled={accesi.length === 0 || inCorso != null}
                        onClick={() => void fermaTutti()}
                        data-testid="cr-ferma-tutti"
                        title={accesi.length === 0
                            ? 'nessun bot in esecuzione'
                            : 'ferma le aperture di tutti i bot. Non chiude nessuna posizione.'}
                        className="h-6 px-2 text-[10px] uppercase tracking-wider border-red-400/40 text-red-300 hover:bg-red-500/15"
                    >
                        {inCorso === 'tutti'
                            ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" />fermo tutti…</>
                            : <><Square className="w-3 h-3 mr-1" />Ferma tutti</>}
                    </Button>
                </div>
            </div>

            {nota && righe.length > 0 && (
                <div className="px-3 py-1.5 border-b border-white/10 bg-white/[0.02] text-[10.5px] text-white/55"
                    data-testid={`${testId}-nota`}>
                    {nota}
                </div>
            )}

            <div className="divide-y divide-white/8">
                {righe.length === 0 ? (
                    <div className="px-3 py-3 text-[11px] text-white/35" data-testid={`${testId}-vuoto`}>
                        Nessun bot da comandare qui.
                    </div>
                ) : righe.map((r) => (
                    <RigaBot
                        key={`${ambito}:${r.id}`} r={r}
                        importi={importi[r.id] ?? []}
                        parametri={r.primaDelBot ? (parametri?.[r.bot] ?? null) : null}
                        mostraParametri={r.primaDelBot}
                        comandi={comandi}
                        bloccato={inCorso != null}
                        segnalaInCorso={setInCorso}
                    />
                ))}
            </div>

            {nonFermati.length > 0 && (
                <div className="px-3 py-2 border-t border-red-500/40 bg-red-500/10 text-[11px] text-red-200"
                    data-testid="cr-non-fermati">
                    <strong className="text-red-300">
                        {nonFermati.length === 1 ? 'Un bot NON si è fermato' : `${nonFermati.length} bot NON si sono fermati`}:
                    </strong>{' '}
                    {nonFermati.map((b) => BOT_LABEL[b]).join(', ')}. Gli altri sì.
                    Riprova, o fermali dalla loro pagina: <strong>finché lo stato non cambia stanno ancora operando</strong>.
                </div>
            )}

            <div className="px-3 py-1.5 border-t border-white/10 text-[10px] text-white/35">
                Fermare spegne le <strong className="text-white/50">aperture</strong>: le posizioni già a
                mercato restano sorvegliate e le puoi chiudere da qui.
            </div>
        </Card>
    );
}

/**
 * Quanto deve restare inerte il pulsante di conferma dopo essere comparso.
 *
 * ⚠️ REVIEW 15/09 — la conferma nasce NELLO STESSO PUNTO del pulsante che la
 * arma, ed è più larga: un doppio clic la colpisce con il secondo clic, e
 * l'intera protezione «sono soldi veri» salta senza che l'operatore abbia
 * letto niente. 400 ms sono più della finestra di un doppio clic (~250 ms) e
 * meno di quanto serva a leggere la frase.
 */
const ATTESA_CONFERMA_MS = 400;

function RigaBot({ r, importi, parametri, mostraParametri, comandi, bloccato, segnalaInCorso }: {
    r: RigaInterruttore;
    importi: CampoImporto[];
    parametri: ReactNode;
    mostraParametri: boolean;
    comandi: ComandiInterruttori;
    bloccato: boolean;
    segnalaInCorso: (v: InterruttoreId | null) => void;
}) {
    /** istante in cui la conferma è comparsa; null = non armato */
    const [armatoDa, setArmatoDa] = useState<number | null>(null);
    const [mio, setMio] = useState(false);
    /** ridisegna quando l'attesa anti-doppio-clic scade */
    const [, setTic] = useState(0);
    const armato = armatoDa != null;

    useEffect(() => {
        if (armatoDa == null) return;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_MS + 20);
        return () => window.clearTimeout(t);
    }, [armatoDa]);

    const live = r.modalita === 'live';
    const occupato = bloccato || mio;
    /** la conferma è ancora inerte? (finestra del doppio clic) */
    const troppoPresto = armatoDa != null && Date.now() - armatoDa < ATTESA_CONFERMA_MS;

    const esegui = async (f: () => Promise<void>) => {
        setMio(true); segnalaInCorso(r.id);
        try { await f(); } finally { setMio(false); segnalaInCorso(null); setArmatoDa(null); }
    };

    return (
        <div className="px-3 py-2" data-testid={`cr-bot-riga-${r.id}`}>
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-wider w-24 shrink-0">{r.etichetta}</span>

                <span className={`text-[11px] ${STATO_CLS[r.stato] ?? 'text-white/40'}`}
                    data-testid={`cr-bot-stato-${r.id}`}>
                    {STATO_TESTO[r.stato] ?? r.stato}
                </span>

                {r.modalita == null ? (
                    <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300"
                        title="il servizio non dichiara la modalità">modalità n/d</span>
                ) : (
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                        live ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/45'
                    }`} data-testid={`cr-bot-modalita-${r.id}`}>
                        {live ? 'soldi veri' : 'prova'}
                    </span>
                )}

                <span className="text-[10px] text-white/30 font-mono"
                    title="da quanto è arrivato l'ultimo messaggio dal canale di questo bot">
                    {r.etaPushS == null ? DASH : fmtAge(r.etaPushS)}
                </span>

                {mostraParametri && (
                    <span className="ml-auto flex items-center gap-1"
                        data-testid={`cr-parametri-${r.bot}`}>
                        {parametri ?? (
                            <span className="text-[10px] text-white/25 flex items-center gap-1"
                                title="questo bot non espone una scheda parametri: si modifica dalla sua pagina">
                                <SlidersHorizontal className="w-3 h-3" />dalla sua pagina
                            </span>
                        )}
                    </span>
                )}
            </div>

            {/* PERCHÉ NON STA APRENDO — dichiarato dal servizio, non dedotto
                qui. ⚠️ 15/09: il trader ha visto Mike «fermo» mentre era
                perfettamente vivo; il tetto delle partite era pieno. Un bot
                acceso che non apre e non dice perché è indistinguibile da un
                bot rotto. */}
            {r.acceso && r.motivoBlocco && (
                <div className="mt-1.5 text-[10px] text-amber-300 flex items-center gap-1.5"
                    data-testid={`cr-motivo-blocco-${r.id}`}>
                    <Ban className="w-3 h-3 shrink-0" />
                    <span>acceso ma non apre: <strong>{r.motivoBlocco}</strong></span>
                    {r.tettoPartite != null && r.partiteEsposte != null && (
                        <span className="text-white/35 font-mono">
                            {r.partiteEsposte}/{r.tettoPartite}
                        </span>
                    )}
                </div>
            )}

            {/* FERMATO ALL'AVVIO DELL'APP — lo dichiara il SERVIZIO
                (`stats.fermato_all_avvio_at`), la pagina non lo deduce.
                «I bot li accendo solo io»: alla riapertura dell'app ogni bot
                torna fermo e in prova. Sparisce da sola quando viene riacceso. */}
            {!r.acceso && r.fermatoAllAvvioAt && (
                <div className="mt-1.5 text-[10px] text-amber-300 flex items-center gap-1.5"
                    data-testid={`cr-fermato-avvio-${r.id}`}>
                    <Power className="w-3 h-3 shrink-0" />
                    <span>
                        fermato all'avvio dell'app: <strong>attivazione manuale richiesta</strong>
                    </span>
                </div>
            )}

            {/* GLI IMPORTI, con i nomi del bot. Compaiono solo se esistono
                davvero: un campo inventato è peggio di un campo assente. */}
            {importi.length > 0 && (
                <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                    {importi.map((c) => (
                        <Importo
                            key={c.chiave} campo={c} id={r.id}
                            occupato={occupato}
                            salva={(v) => esegui(() => comandi.cambiaImporto(r.id, c.chiave, v))}
                        />
                    ))}
                </div>
            )}

            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                {!r.statoNoto ? (
                    <span className="text-[10px] text-orange-300" data-testid={`cr-stato-ignoto-${r.id}`}>
                        stato non letto: non si comanda un bot di cui non sappiamo che cosa sta facendo
                    </span>
                ) : r.stato === 'stopping' ? (
                    // ⚠️ REVIEW 15/09 — qui si nascondeva FERMA e si offriva
                    // AVVIA. Ma il servizio, al ciclo dopo, porta 'stopping' a
                    // 'stopped': un avvio dato in quella finestra viene
                    // cancellato dal servizio stesso.
                    <span className="text-[10px] text-amber-300" data-testid={`cr-in-arresto-${r.id}`}>
                        si sta fermando: attendi che abbia finito prima di riavviarlo
                    </span>
                ) : r.acceso ? (
                    <>
                        <Button
                            type="button" size="sm" variant="outline"
                            disabled={occupato}
                            onClick={() => void esegui(() => comandi.spegni(r.id))}
                            data-testid={`cr-ferma-${r.id}`}
                            // ⚠️ 15/09 — FERMA toglie le APERTURE, non le
                            // uscite: coperture, green-up, cash-out e
                            // settlement continuano, ed è giusto (una posizione
                            // aperta non si abbandona). Ma il pulsante deve
                            // dirlo. Lo dichiara il servizio.
                            title={r.stopFermaSoloAperture
                                ? 'ferma le APERTURE. Le posizioni già aperte restano sorvegliate: coperture, green-up, cash out e regolamento continuano'
                                : 'ferma il bot'}
                            className="h-6 px-2 text-[10px] uppercase tracking-wider border-red-400/40 text-red-300 hover:bg-red-500/15"
                        >{mio ? <Loader2 className="w-3 h-3 animate-spin" /> : <><Square className="w-3 h-3 mr-1" />ferma</>}</Button>

                        {r.stopFermaSoloAperture && (
                            <span className="text-[9px] text-white/30"
                                data-testid={`cr-cosa-ferma-${r.id}`}>
                                ferma le aperture, non le uscite
                            </span>
                        )}

                        {r.modalita != null && (
                            live ? (
                                <Button
                                    type="button" size="sm" variant="ghost"
                                    disabled={occupato}
                                    onClick={() => void esegui(() => comandi.cambiaModalita(r.id, 'paper'))}
                                    data-testid={`cr-a-paper-${r.id}`}
                                    className="h-6 px-2 text-[10px]"
                                    title="torna a operare in prova: nessun ordine reale"
                                >passa a prova</Button>
                            ) : armato ? (
                                <Button
                                    type="button" size="sm"
                                    disabled={occupato || troppoPresto}
                                    title={troppoPresto ? 'attendi un istante: sono soldi veri' : undefined}
                                    onClick={() => void esegui(() => comandi.cambiaModalita(r.id, 'live'))}
                                    data-testid={`cr-conferma-live-${r.id}`}
                                    className="h-6 px-2 text-[10px] uppercase tracking-wider bg-red-600/80 hover:bg-red-600 text-white font-bold"
                                >confermi? sono soldi veri</Button>
                            ) : (
                                <Button
                                    type="button" size="sm" variant="ghost"
                                    disabled={occupato}
                                    onClick={() => setArmatoDa(Date.now())}
                                    data-testid={`cr-a-live-${r.id}`}
                                    className="h-6 px-2 text-[10px] text-red-300/80 hover:text-red-300"
                                >passa a soldi veri</Button>
                            )
                        )}
                    </>
                ) : (
                    <>
                        <Button
                            type="button" size="sm" variant="outline"
                            disabled={occupato}
                            onClick={() => void esegui(() => comandi.accendi(r.id, 'paper'))}
                            data-testid={`cr-avvia-paper-${r.id}`}
                            className="h-6 px-2 text-[10px] uppercase tracking-wider"
                        ><Power className="w-3 h-3 mr-1" />avvia in prova</Button>

                        {armato ? (
                            <Button
                                type="button" size="sm"
                                disabled={occupato || troppoPresto}
                                title={troppoPresto ? 'attendi un istante: sono ordini reali' : undefined}
                                onClick={() => void esegui(() => comandi.accendi(r.id, 'live'))}
                                data-testid={`cr-conferma-avvio-live-${r.id}`}
                                className="h-6 px-2 text-[10px] uppercase tracking-wider bg-red-600/80 hover:bg-red-600 text-white font-bold"
                            >confermi? ordini reali su Betfair</Button>
                        ) : (
                            <Button
                                type="button" size="sm" variant="outline"
                                disabled={occupato}
                                onClick={() => setArmatoDa(Date.now())}
                                data-testid={`cr-avvia-live-${r.id}`}
                                className="h-6 px-2 text-[10px] uppercase tracking-wider border-red-400/40 text-red-300 hover:bg-red-500/15"
                            ><AlertTriangle className="w-3 h-3 mr-1" />avvia con soldi veri</Button>
                        )}
                    </>
                )}

                {armato && (
                    <span className="text-[10px] text-red-300" data-testid={`cr-avviso-live-${r.id}`}>
                        Da qui in poi {r.etichetta} manda ordini reali su Betfair.
                    </span>
                )}

                {/* ⚠️ REVIEW 15/09 — mentre un comando è in volo TUTTI i
                    pulsanti si spengono, compreso «ferma» su un bot in live.
                    Il `title` da solo non basta: `buttonVariants` ha
                    `disabled:pointer-events-none`, quindi su un bottone spento
                    il tooltip non si apre nemmeno. Serve una riga VISIBILE. */}
                {bloccato && !mio && (
                    <span className="text-[10px] text-white/40" data-testid={`cr-attesa-${r.id}`}>
                        un altro comando è in corso: i pulsanti tornano appena finisce
                    </span>
                )}
            </div>
        </div>
    );
}

/** Un campo importo: si scrive, si conferma. Non si salva a ogni tasto — un
 *  carattere di troppo non deve diventare un ordine da 30 €. */
function Importo({ campo, id, occupato, salva }: {
    campo: CampoImporto;
    id: InterruttoreId;
    occupato: boolean;
    salva: (v: number) => Promise<void>;
}) {
    const [bozza, setBozza] = useState('');
    const scritto = Number(bozza.replace(',', '.'));
    const valido = Number.isFinite(scritto) && scritto >= 0.01;
    /**
     * ⚠️ REVIEW 14/09 — QUI `campo.valore == null` ABILITAVA IL SALVATAGGIO.
     *
     * Era l'opposto del fail-closed: il pulsante «salva» compariva PROPRIO
     * quando il valore corrente era sconosciuto, cioè quando la lettura dello
     * stato non era tornata — ed è il caso in cui salvare sostituisce l'intero
     * oggetto parametri sul database.
     */
    const noto = campo.valore != null;
    const cambiato = bozza !== '' && valido && noto
        && Math.abs(scritto - (campo.valore as number)) > 0.0001;
    const idCampo = `cr-importo-${id}-${campo.chiave.replace(/[^a-zA-Z0-9]/g, '-')}`;

    return (
        <span className="flex items-center gap-1.5">
            <label className="text-[10px] text-white/40" htmlFor={idCampo}
                title={campo.nota ?? campo.ereditato}>
                {campo.etichetta}{(campo.nota || campo.ereditato) ? <span className="text-white/25"> *</span> : null}
            </label>
            <input
                id={idCampo} type="number" step="0.01" min="0.01"
                placeholder={campo.valore == null ? '—' : String(campo.valore)}
                value={bozza} disabled={occupato}
                onChange={(e) => setBozza(e.target.value)}
                data-testid={idCampo}
                className="w-16 px-1.5 py-0.5 rounded border border-white/15 bg-white/5 font-mono text-right text-[11px] text-white/90"
                title={campo.valore == null
                    ? 'il servizio non dichiara questo importo'
                    : `adesso vale ${fmtMoney(campo.valore)}${campo.nota ? ` — ${campo.nota}` : ''}`}
            />
            {/* L'IMPORTO EREDITATO SI DICHIARA: finché questa strategia non ha
                una chiave sua, il motore usa quella per LATO — e quella la
                condivide con un'altra strategia. Salvare qui la separa. */}
            {campo.ereditato && (
                <span className="text-[9px] text-amber-300/80" data-testid={`${idCampo}-ereditato`}>
                    {campo.ereditato}
                </span>
            )}
            {cambiato && (
                <Button
                    type="button" size="sm" variant="outline"
                    disabled={occupato}
                    onClick={() => void salva(scritto).then(() => setBozza(''))}
                    data-testid={`${idCampo}-salva`}
                    className="h-6 px-2 text-[10px]"
                >salva</Button>
            )}
            {/* un campo che non si può salvare DICE PERCHÉ, invece di restare
                muto: senza il valore corrente non sappiamo su cosa scriviamo. */}
            {bozza !== '' && valido && !noto && (
                <span className="text-[10px] text-orange-300" data-testid={`${idCampo}-bloccato`}>
                    valore corrente non letto: salvare lo sostituirebbe insieme a tutti gli altri
                </span>
            )}
        </span>
    );
}

export default PannelloBot;
