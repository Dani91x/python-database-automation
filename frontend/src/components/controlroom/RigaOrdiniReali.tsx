// ============================================================================
// RigaOrdiniReali.tsx - L'INTERRUTTORE "ORDINI REALI: OFF / PAPER / LIVE".
//
// "Devo operare dalla UI, non dal codice" (utente, 24/09). Fino a oggi il
// modo ordini (`LIVE_ORDER_MODE`) stava solo nel .env: gate del trading
// manuale dal ladder E freno di Safe/Mike/Omega sugli ordini reali.
//
// E' UNA RIGA DELLA PLANCIA dei bot (`PannelloBot`), con lo stesso stile delle
// righe dei bot: nessun riquadro nuovo. Mostra:
//   * il modo EFFETTIVO (il piu' restrittivo fra tetto del .env e scelta);
//   * il TETTO dell'ambiente dichiarato dal runner: se la scelta lo supera,
//     lo dice ("tetto dell'ambiente: PAPER") e LIVE non si puo' scegliere;
//   * chi e quando l'ha cambiato (o "avvio dell'app", che la riporta a PAPER).
// LIVE si conferma DUE volte, come l'avvio di un bot in soldi veri; OFF e PAPER
// no: scendere e' sempre permesso senza domande.
//
// La lettura e' la RPC owner-only `get_live_settings` (la stessa del
// kill-switch): una volta all'apertura, dopo ogni comando, e ogni 30 s come
// ripiego (la riga cambia solo per un gesto dell'utente o all'avvio dell'app).
//
// 25/09 (voce 6 dell'audit tempo reale) - IL CANALE DEL RUNNER CALCIO (47331)
// PRIMA DEL POLL: il tetto e' quello dell'`hello` del runner collegato (il SUO
// .env), il modo EFFETTIVO quello che il runner dichiara nel `now`
// (`state.order_mode`, runner.py:292-302) se fresco; se il runner dichiara una
// SCELTA diversa da quella letta, la riga si rilegge SUBITO (chi/quando stanno
// solo sul database). Fonte ed eta' scritte a video (`lib/runnerCanale.ts`).
// ============================================================================
import { useCallback, useEffect, useRef, useState } from 'react';
import { getLocalChannel } from '@/lib/localChannel';
import {
    leggiModoDalNow, sovrapponiModoOrdini, type ModoOrdiniCanale,
} from '@/lib/runnerCanale';
import { fmtDateTime } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Loader2 } from 'lucide-react';
import {
    leggiModoOrdini, scegliModoOrdini, statoOrdiniReali, type ModoOrdini,
} from '@/lib/interruttori';
import type { LiveSettings } from '@/lib/liveOrders';

/** stessa finestra anti-doppio-clic delle righe dei bot (`PannelloBot`) */
const ATTESA_CONFERMA_MS = 400;
const RILETTURA_MS = 30_000;
/** una rilettura chiesta dal canale al piu' ogni 2 s (anti-tempesta) */
const RILETTURA_CANALE_MIN_MS = 2_000;

interface CanaleModo {
    connesso: boolean;
    hello: Record<string, unknown> | null;
    modo: ModoOrdiniCanale | null;
}

const TESTO_MODO: Record<ModoOrdini, string> = {
    OFF: 'nessun ordine',
    PAPER: 'prova',
    LIVE: 'soldi veri',
};

function fmtQuando(iso: string | null): string {
    // design system: un solo formato per date e ore, quello di lib/format
    if (!iso) return '';
    if (Number.isNaN(Date.parse(iso))) return iso;
    return fmtDateTime(iso);
}

function chi(da: string | null): string {
    if (!da) return 'sconosciuto';
    if (da === 'avvio_app') return "avvio dell'app";
    return da;
}

export interface RigaOrdiniRealiProps {
    /** iniettabili per i test: di serie le RPC vere */
    leggi?: () => Promise<LiveSettings | null>;
    scrivi?: (m: ModoOrdini) => Promise<LiveSettings | null>;
    riletturaMs?: number;
}

export function RigaOrdiniReali({
    leggi = leggiModoOrdini, scrivi = scegliModoOrdini, riletturaMs = RILETTURA_MS,
}: RigaOrdiniRealiProps) {
    const [riga, setRiga] = useState<LiveSettings | null>(null);
    const [erroreLettura, setErroreLettura] = useState<string | null>(null);
    const [errore, setErrore] = useState<string | null>(null);
    const [inCorso, setInCorso] = useState(false);
    const [armatoDa, setArmatoDa] = useState<number | null>(null);
    const [, setTic] = useState(0);
    /** 25/09: inizio dell'ultima lettura riuscita (per l'eta' e la freschezza) */
    const [lettoMs, setLettoMs] = useState<number | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [canale, setCanale] = useState<CanaleModo>({ connesso: false, hello: null, modo: null });

    const ricarica = useCallback(async () => {
        const inizio = Date.now();
        try {
            const r = await leggi();
            setRiga(r);
            setErroreLettura(null);
            setLettoMs(inizio);
        } catch (e) {
            setErroreLettura(e instanceof Error ? e.message : String(e));
        }
    }, [leggi]);

    // 25/09 (voce 6): il canale 47331 - stato, hello, `now` col modo ordini
    useEffect(() => {
        const ch = getLocalChannel('calcio');
        const helloDi = () => (typeof ch.getHello === 'function'
            ? (ch.getHello() as Record<string, unknown> | null) : null);
        setCanale({ connesso: ch.getStatus() === 'connected', hello: helloDi(), modo: null });
        const offStato = ch.onStatus((st) => setCanale((p) => (st === 'connected'
            ? { ...p, connesso: true, hello: helloDi() ?? p.hello }
            : { connesso: false, hello: null, modo: null })));
        const offHello = ch.subscribe('hello', (d) => setCanale((p) => ({
            ...p, hello: d && typeof d === 'object' ? d as Record<string, unknown> : null,
        })));
        const offNow = ch.subscribe('now', (d) => {
            const m = leggiModoDalNow(d);
            if (!m) return;
            setCanale((p) => (p.modo != null && p.modo.ms >= m.ms ? p : { ...p, modo: m }));
        });
        const t = window.setInterval(() => setNowMs(Date.now()), 1_000);
        return () => { offStato(); offHello(); offNow(); window.clearInterval(t); };
    }, []);

    useEffect(() => {
        void ricarica();
        const t = window.setInterval(() => void ricarica(), riletturaMs);
        return () => window.clearInterval(t);
    }, [ricarica, riletturaMs]);

    useEffect(() => {
        if (armatoDa == null) return;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_MS + 20);
        return () => window.clearTimeout(t);
    }, [armatoDa]);

    const st = sovrapponiModoOrdini(statoOrdiniReali(erroreLettura ? null : riga), lettoMs, canale, nowMs);
    // il runner dichiara una scelta diversa da quella letta: si rilegge SUBITO
    const ultimaRiletturaCanale = useRef(0);
    useEffect(() => {
        if (!st.daRileggere) return;
        const ora = Date.now();
        if (ora - ultimaRiletturaCanale.current < RILETTURA_CANALE_MIN_MS) return;
        ultimaRiletturaCanale.current = ora;
        void ricarica();
    }, [st.daRileggere, ricarica, nowMs]);
    const troppoPresto = armatoDa != null && Date.now() - armatoDa < ATTESA_CONFERMA_MS;
    // LIVE si puo' scegliere solo se il runner ha dichiarato un tetto LIVE
    const liveConsentito = st.tetto === 'LIVE';

    const esegui = async (m: ModoOrdini) => {
        setInCorso(true); setErrore(null);
        try {
            const nuova = await scrivi(m);
            if (nuova) setRiga(nuova);
            await ricarica();
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally {
            setInCorso(false); setArmatoDa(null);
        }
    };

    const live = st.effettivo === 'LIVE';

    return (
        <div className="px-3 py-2 border-b border-white/10" data-testid="cr-ordini-reali">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-wider w-24 shrink-0">Ordini reali</span>

                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                    live ? 'bg-red-500/20 text-red-300'
                        : st.effettivo === 'PAPER' ? 'bg-white/10 text-white/45'
                            : 'bg-white/5 text-white/35'
                }`} data-testid="cr-ordini-reali-effettivo"
                    title="modo effettivo: il piu' restrittivo fra il tetto del .env e la scelta da qui">
                    {st.effettivo} - {TESTO_MODO[st.effettivo]}
                </span>

                {st.letto && (
                    <span className="text-[10px] text-white/30" data-testid="cr-ordini-reali-fonte"
                        title="da dove viene il modo mostrato: canale del runner calcio (47331, hello/now) o database (get_live_settings, ogni 30 s)">
                        {st.fonte === 'canale' ? 'canale' : 'db'}{' '}
                        {st.etaS == null ? '-' : `${st.etaS} s`}
                    </span>
                )}

                {st.tetto != null ? (
                    <span className={`text-[10px] ${st.limitatoDalTetto ? 'text-amber-300' : 'text-white/35'}`}
                        data-testid="cr-ordini-reali-tetto"
                        title={st.tettoAlle ? `dichiarato dal runner il ${fmtQuando(st.tettoAlle)}` : undefined}>
                        tetto dell'ambiente: {st.tetto}
                    </span>
                ) : st.letto && !st.migrazioneMancante ? (
                    <span className="text-[10px] text-amber-300" data-testid="cr-ordini-reali-tetto">
                        tetto dell'ambiente non dichiarato: il runner non e' ancora partito
                    </span>
                ) : null}

                {st.scelto != null && st.cambiatoAlle && (
                    <span className="text-[10px] text-white/30" data-testid="cr-ordini-reali-chi">
                        scelto {st.scelto} da {chi(st.cambiatoDa)} il {fmtQuando(st.cambiatoAlle)}
                    </span>
                )}
            </div>

            {st.limitatoDalTetto && (
                <div className="mt-1.5 text-[10px] text-amber-300 flex items-center gap-1.5"
                    data-testid="cr-ordini-reali-limitato">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    <span>
                        hai scelto {st.scelto}, ma il tetto dell'ambiente e' {st.tetto}: vale {st.effettivo}.
                        Il tetto si alza solo dal .env, con il riavvio.
                    </span>
                </div>
            )}

            {(!st.letto || st.migrazioneMancante) && (
                <div className="mt-1.5 text-[10px] text-orange-300" data-testid="cr-ordini-reali-non-letto">
                    {st.migrazioneMancante
                        ? 'la riga non ha ancora il modo ordini (migrazione live_order_mode_control da applicare): vale OFF'
                        : `modo ordini non letto${erroreLettura ? ` (${erroreLettura})` : ''}: il runner lo tratta come OFF`}
                </div>
            )}

            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                <Button
                    type="button" size="sm" variant="outline"
                    disabled={inCorso || !st.letto || st.migrazioneMancante || st.scelto === 'OFF'}
                    onClick={() => void esegui('OFF')}
                    data-testid="cr-ordini-reali-off"
                    title="nessun ordine dal ladder, nessun ordine reale dai bot. Le chiusure restano servite."
                    className="h-6 px-2 text-[10px] uppercase tracking-wider"
                >{inCorso ? <Loader2 className="w-3 h-3 animate-spin" /> : 'off'}</Button>

                <Button
                    type="button" size="sm" variant="outline"
                    disabled={inCorso || !st.letto || st.migrazioneMancante || st.scelto === 'PAPER'}
                    onClick={() => void esegui('PAPER')}
                    data-testid="cr-ordini-reali-paper"
                    title="ordini simulati: nessun ordine reale"
                    className="h-6 px-2 text-[10px] uppercase tracking-wider"
                >paper</Button>

                {armatoDa != null ? (
                    <Button
                        type="button" size="sm"
                        disabled={inCorso || troppoPresto}
                        title={troppoPresto ? 'attendi un istante: sono soldi veri' : undefined}
                        onClick={() => void esegui('LIVE')}
                        data-testid="cr-ordini-reali-conferma-live"
                        className="h-6 px-2 text-[10px] uppercase tracking-wider bg-red-600/80 hover:bg-red-600 text-white font-bold"
                    >confermi? ordini reali su Betfair</Button>
                ) : (
                    <Button
                        type="button" size="sm" variant="outline"
                        disabled={inCorso || !st.letto || st.migrazioneMancante
                            || st.scelto === 'LIVE' || !liveConsentito}
                        onClick={() => setArmatoDa(Date.now())}
                        data-testid="cr-ordini-reali-live"
                        title={!liveConsentito
                            ? `tetto dell'ambiente: ${st.tetto ?? 'non dichiarato'} - LIVE non si puo' scegliere da qui`
                            : 'ordini reali: si conferma due volte'}
                        className="h-6 px-2 text-[10px] uppercase tracking-wider border-red-400/40 text-red-300 hover:bg-red-500/15"
                    ><AlertTriangle className="w-3 h-3 mr-1" />live</Button>
                )}

                {armatoDa != null && (
                    <span className="text-[10px] text-red-300" data-testid="cr-ordini-reali-avviso-live">
                        Da qui in poi il ladder e i bot in live mandano ordini reali su Betfair.
                    </span>
                )}
            </div>

            {errore && (
                <div className="mt-1.5 text-[10px] text-red-300" data-testid="cr-ordini-reali-errore">
                    il comando non e' andato a buon fine: {errore}. Il modo resta quello mostrato.
                </div>
            )}
        </div>
    );
}

export default RigaOrdiniReali;
