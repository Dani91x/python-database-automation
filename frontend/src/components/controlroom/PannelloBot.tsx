// ============================================================================
// PannelloBot.tsx — LA PLANCIA DI COMANDO DEI TRE BOT.
//
// «Voglio massimo controllo dalla control room e devo poter fermare uno o
// tutti i bot come e quando voglio» (utente, 14/09).
//
// COSA FA, e niente di più: usa i comandi che i tre servizi ESPONGONO GIÀ
// (`X_activate`, `X_stop`, `X_update_params`) e i fogli parametri che
// esistono già (`BotParamsSheet` di Safe, `MikeParamsSheet` di Mike). Qui
// non nasce nessun parametro nuovo e nessuna semantica nuova: sarebbe una
// seconda verità accanto a quella delle pagine dei bot.
//
// LE TRE REGOLE DI SICUREZZA
//
//  1. **Accendere in LIVE si conferma due volte.** È l'unico gesto di questa
//     pagina che mette a rischio denaro vero senza che ci sia già una
//     posizione aperta. Il secondo pulsante compare dove stava il primo, così
//     il dito non si sposta: la protezione costa un clic, non un viaggio.
//  2. **FERMA TUTTI non chiede niente.** Un freno d'emergenza con una finestra
//     di conferma davanti non è un freno d'emergenza. Fermare è sempre
//     reversibile e non chiude nessuna posizione: spegne le APERTURE.
//  3. **Quello che il pulsante ha fatto si vede.** Lo stato mostrato è quello
//     che RISPONDE il servizio, non quello che speravamo: `stopping` si
//     scrive «sta fermandosi», non «fermo».
//
// COSA NON FA: non chiude posizioni. Fermare un bot lascia il banco
// sorvegliato — riconciliazione, settlement e uscite continuano a girare
// (`bot_service.py`: «SEMPRE, anche a bot fermo: mai posizioni nude»).
// ============================================================================
import { useState, type ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Power, Square, SlidersHorizontal, AlertTriangle, Loader2 } from 'lucide-react';
import { fmtMoney, fmtAge, DASH } from '@/lib/format';
import { BOT_LABEL, type Bot } from '@/lib/controlRoom';
import type { StatoBot } from '@/components/controlroom/useControlRoom';

export type Modalita = 'paper' | 'live';

/** Le parole dello stato del servizio. Ogni stato che i servizi scrivono ha
 *  una frase sua: «sta fermandosi» e «fermo» non sono la stessa cosa. */
const STATO_TESTO: Record<string, string> = {
    running: 'in esecuzione',
    stopping: 'sta fermandosi',
    stopped: 'fermo',
    idle: 'fermo',
    error: 'in errore',
};

const STATO_CLS: Record<string, string> = {
    running: 'text-emerald-400',
    stopping: 'text-amber-300',
    stopped: 'text-white/40',
    idle: 'text-white/40',
    error: 'text-red-400',
};

/**
 * UN IMPORTO di un bot. Non ce n'è uno solo, e fingere di sì sarebbe falso:
 * Safe ne ha DUE (`stake.backSize` per chi punta, `stake.laySize` per chi
 * banca), Mike ne ha uno (`stake`, «Under 3.5»), e quello di Omega
 * (`min_stake`) è un MINIMO — Omega dimensiona dall'obiettivo, quindi
 * chiamarlo «l'importo con cui opera» sarebbe una terza bugia.
 */
export interface CampoImporto {
    /** chiave vera nei parametri del servizio, es. 'stake.backSize' */
    chiave: string;
    /** come lo chiama IL BOT, non come lo chiamerei io */
    etichetta: string;
    valore: number | null;
    /** quando il numero non significa «opera con tanto» */
    nota?: string;
}

export interface ComandiBot {
    /** accende il bot nella modalità scelta */
    avvia: (bot: Bot, modalita: Modalita) => Promise<void>;
    /** spegne le APERTURE. Non chiude niente. */
    ferma: (bot: Bot) => Promise<void>;
    /** cambia modalità a bot già acceso */
    cambiaModalita: (bot: Bot, modalita: Modalita) => Promise<void>;
    /** cambia UN importo, per chiave (es. 'stake.backSize') */
    cambiaImporto: (bot: Bot, chiave: string, importo: number) => Promise<void>;
}

export interface PannelloBotProps {
    bots: StatoBot[];
    /** gli importi di ciascun bot, con i nomi del bot */
    importi: Record<Bot, CampoImporto[]>;
    /**
     * Il foglio parametri di ciascun bot. Arriva dalla pagina come nodo gia'
     * montato — sono gli STESSI componenti delle pagine dei bot
     * (`BotParamsSheet`, `MikeParamsSheet`), non una copia: due schede
     * parametri per lo stesso servizio sarebbero due verita'.
     */
    parametri?: Partial<Record<Bot, ReactNode>>;
    comandi: ComandiBot;
    testId?: string;
}

export function PannelloBot({
    bots, importi, comandi, parametri, testId = 'cr-pannello-bot',
}: PannelloBotProps) {
    const [inCorso, setInCorso] = useState<Bot | 'tutti' | null>(null);
    const accesi = bots.filter((b) => b.inCorsa);
    const inLive = bots.filter((b) => b.inCorsa && b.modalita === 'live');

    const fermaTutti = async () => {
        setInCorso('tutti');
        try {
            // uno alla volta e in sequenza: se il terzo fallisce, i primi due
            // sono comunque fermi. In parallelo un errore lascerebbe uno stato
            // che nessuno sa leggere.
            for (const b of accesi) await comandi.ferma(b.bot);
        } finally { setInCorso(null); }
    };

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Comando dei bot</span>
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

            <div className="divide-y divide-white/8">
                {bots.map((b) => (
                    <RigaBot
                        key={b.bot} b={b}
                        importi={importi[b.bot] ?? []}
                        parametri={parametri?.[b.bot] ?? null}
                        comandi={comandi}
                        bloccato={inCorso != null}
                        segnalaInCorso={setInCorso}
                    />
                ))}
            </div>

            <div className="px-3 py-1.5 border-t border-white/10 text-[10px] text-white/35">
                Fermare spegne le <strong className="text-white/50">aperture</strong>: le posizioni già a
                mercato restano sorvegliate e le puoi chiudere da qui.
            </div>
        </Card>
    );
}

function RigaBot({ b, importi, parametri, comandi, bloccato, segnalaInCorso }: {
    b: StatoBot;
    importi: CampoImporto[];
    parametri: ReactNode;
    comandi: ComandiBot;
    bloccato: boolean;
    segnalaInCorso: (v: Bot | null) => void;
}) {
    const [armato, setArmato] = useState(false);
    const [mio, setMio] = useState(false);

    const stato = b.stato ?? (b.inCorsa ? 'running' : 'stopped');
    const live = b.modalita === 'live';
    const occupato = bloccato || mio;

    const esegui = async (f: () => Promise<void>) => {
        setMio(true); segnalaInCorso(b.bot);
        try { await f(); } finally { setMio(false); segnalaInCorso(null); setArmato(false); }
    };

    return (
        <div className="px-3 py-2" data-testid={`cr-bot-riga-${b.bot}`}>
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-wider w-16 shrink-0">{BOT_LABEL[b.bot]}</span>

                <span className={`text-[11px] ${STATO_CLS[stato] ?? 'text-white/40'}`}
                    data-testid={`cr-bot-stato-${b.bot}`}>
                    {STATO_TESTO[stato] ?? stato}
                </span>

                {b.modalita == null ? (
                    <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300"
                        title="il servizio non dichiara la modalità">modalità n/d</span>
                ) : (
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                        live ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/45'
                    }`} data-testid={`cr-bot-modalita-${b.bot}`}>
                        {live ? 'soldi veri' : 'prova'}
                    </span>
                )}

                <span className="text-[10px] text-white/30 font-mono"
                    title="da quanto è arrivato l'ultimo messaggio dal canale di questo bot">
                    {b.etaPushS == null ? DASH : fmtAge(b.etaPushS)}
                </span>

                <span className="ml-auto flex items-center gap-1"
                    data-testid={`cr-parametri-${b.bot}`}>
                    {parametri ?? (
                        <span className="text-[10px] text-white/25 flex items-center gap-1"
                            title="questo bot non espone una scheda parametri: si modifica dalla sua pagina">
                            <SlidersHorizontal className="w-3 h-3" />dalla sua pagina
                        </span>
                    )}
                </span>
            </div>

            {/* GLI IMPORTI, con i nomi del bot. Compaiono solo se esistono
                davvero: un campo inventato è peggio di un campo assente. */}
            {importi.length > 0 && (
                <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                    {importi.map((c) => (
                        <Importo
                            key={c.chiave} campo={c} bot={b.bot}
                            occupato={occupato}
                            salva={(v) => esegui(() => comandi.cambiaImporto(b.bot, c.chiave, v))}
                        />
                    ))}
                </div>
            )}

            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                {b.inCorsa ? (
                    <>
                        <Button
                            type="button" size="sm" variant="outline"
                            disabled={occupato}
                            onClick={() => void esegui(() => comandi.ferma(b.bot))}
                            data-testid={`cr-ferma-${b.bot}`}
                            className="h-6 px-2 text-[10px] uppercase tracking-wider border-red-400/40 text-red-300 hover:bg-red-500/15"
                        >{mio ? <Loader2 className="w-3 h-3 animate-spin" /> : <><Square className="w-3 h-3 mr-1" />ferma</>}</Button>

                        {b.modalita != null && (
                            live ? (
                                <Button
                                    type="button" size="sm" variant="ghost"
                                    disabled={occupato}
                                    onClick={() => void esegui(() => comandi.cambiaModalita(b.bot, 'paper'))}
                                    data-testid={`cr-a-paper-${b.bot}`}
                                    className="h-6 px-2 text-[10px]"
                                    title="torna a operare in prova: nessun ordine reale"
                                >passa a prova</Button>
                            ) : armato ? (
                                <Button
                                    type="button" size="sm"
                                    disabled={occupato}
                                    onClick={() => void esegui(() => comandi.cambiaModalita(b.bot, 'live'))}
                                    data-testid={`cr-conferma-live-${b.bot}`}
                                    className="h-6 px-2 text-[10px] uppercase tracking-wider bg-red-600/80 hover:bg-red-600 text-white font-bold"
                                >confermi? sono soldi veri</Button>
                            ) : (
                                <Button
                                    type="button" size="sm" variant="ghost"
                                    disabled={occupato}
                                    onClick={() => setArmato(true)}
                                    data-testid={`cr-a-live-${b.bot}`}
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
                            onClick={() => void esegui(() => comandi.avvia(b.bot, 'paper'))}
                            data-testid={`cr-avvia-paper-${b.bot}`}
                            className="h-6 px-2 text-[10px] uppercase tracking-wider"
                        ><Power className="w-3 h-3 mr-1" />avvia in prova</Button>

                        {armato ? (
                            <Button
                                type="button" size="sm"
                                disabled={occupato}
                                onClick={() => void esegui(() => comandi.avvia(b.bot, 'live'))}
                                data-testid={`cr-conferma-avvio-live-${b.bot}`}
                                className="h-6 px-2 text-[10px] uppercase tracking-wider bg-red-600/80 hover:bg-red-600 text-white font-bold"
                            >confermi? ordini reali su Betfair</Button>
                        ) : (
                            <Button
                                type="button" size="sm" variant="outline"
                                disabled={occupato}
                                onClick={() => setArmato(true)}
                                data-testid={`cr-avvia-live-${b.bot}`}
                                className="h-6 px-2 text-[10px] uppercase tracking-wider border-red-400/40 text-red-300 hover:bg-red-500/15"
                            ><AlertTriangle className="w-3 h-3 mr-1" />avvia con soldi veri</Button>
                        )}
                    </>
                )}

                {armato && (
                    <span className="text-[10px] text-red-300" data-testid={`cr-avviso-live-${b.bot}`}>
                        Da qui in poi {BOT_LABEL[b.bot]} manda ordini reali su Betfair.
                    </span>
                )}
            </div>
        </div>
    );
}

/** Un campo importo: si scrive, si conferma. Non si salva a ogni tasto — un
 *  carattere di troppo non deve diventare un ordine da 30 €. */
function Importo({ campo, bot, occupato, salva }: {
    campo: CampoImporto;
    bot: Bot;
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
     * oggetto parametri sul database. Un valore assente deve BLOCCARE la
     * scrittura, non invitarla.
     */
    const noto = campo.valore != null;
    const cambiato = bozza !== '' && valido && noto
        && Math.abs(scritto - (campo.valore as number)) > 0.0001;
    const id = `cr-importo-${bot}-${campo.chiave.replace(/[^a-zA-Z0-9]/g, '-')}`;

    return (
        <span className="flex items-center gap-1.5">
            <label className="text-[10px] text-white/40" htmlFor={id} title={campo.nota}>
                {campo.etichetta}{campo.nota ? <span className="text-white/25"> *</span> : null}
            </label>
            <input
                id={id} type="number" step="0.01" min="0.01"
                placeholder={campo.valore == null ? '—' : String(campo.valore)}
                value={bozza} disabled={occupato}
                onChange={(e) => setBozza(e.target.value)}
                data-testid={id}
                className="w-16 px-1.5 py-0.5 rounded border border-white/15 bg-white/5 font-mono text-right text-[11px] text-white/90"
                title={campo.valore == null
                    ? 'il servizio non dichiara questo importo'
                    : `adesso vale ${fmtMoney(campo.valore)}${campo.nota ? ` — ${campo.nota}` : ''}`}
            />
            {cambiato && (
                <Button
                    type="button" size="sm" variant="outline"
                    disabled={occupato}
                    onClick={() => void salva(scritto).then(() => setBozza(''))}
                    data-testid={`${id}-salva`}
                    className="h-6 px-2 text-[10px]"
                >salva</Button>
            )}
            {/* un campo che non si può salvare DICE PERCHÉ, invece di restare
                muto: senza il valore corrente non sappiamo su cosa scriviamo. */}
            {bozza !== '' && valido && !noto && (
                <span className="text-[10px] text-orange-300" data-testid={`${id}-bloccato`}>
                    valore corrente non letto: salvare lo sostituirebbe insieme a tutti gli altri
                </span>
            )}
        </span>
    );
}

export default PannelloBot;
