// ============================================================================
// RigaFreno.tsx - R3 (25/09): IL FRENO UNICO in Control Room.
//
// Ordine dell'utente (25/09 sera): «un freno unico che ferma ogni cosa sia
// live che paper». Il freno e' uno solo: `betfair_live_settings.kill_switch`
// (RPC owner-only `set_live_kill_switch`, la stessa del pulsante di Segui
// Live) piu' `LIVE_KILL_SWITCH` del .env. Tirato, NESSUN bot apre (Omega,
// Mike, Safe calcio e tennis, i 4 bot tennis, lo scalper), ne' in live ne' in
// paper; le chiusure passano sempre.
//
// E' una riga della plancia dei bot, subito sotto «Ordini reali», con lo
// stesso stile. Mostra:
//   * lo stato del freno: dal canale del runner calcio (47331, topic
//     `modo_ordini` e `hello.modo_ordini`, chiavi `kill_switch`,
//     `kill_switch_env`, `kill_switch_letto`) se piu' recente della lettura
//     del database, altrimenti dal database (`get_live_settings`, all'apertura,
//     dopo ogni comando e ogni 30 s come ripiego). Fonte ed eta' a video.
//   * TIRA IL FRENO: UN clic, nessuna domanda (come «FERMA TUTTI»: un freno
//     d'emergenza con una conferma davanti non e' un freno d'emergenza).
//   * RILASCIA: DUE conferme. E' l'unica via per rialzarlo: mai automatico.
// Se il freno viene dal .env lo dice: da qui non si toglie.
// ============================================================================
import { useCallback, useEffect, useState } from 'react';
import { getLocalChannel } from '@/lib/localChannel';
import { getLiveSettings, setKillSwitch, type LiveSettings } from '@/lib/liveOrders';
import { fmtDateTime } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Loader2, OctagonX } from 'lucide-react';

/** stessa finestra anti-doppio-clic delle altre righe della plancia */
const ATTESA_CONFERMA_MS = 400;
const RILETTURA_MS = 30_000;

/** Il freno come lo dichiara il runner calcio sul canale. */
export interface FrenoCanale {
    tirato: boolean;
    /** true = tirato dal .env del runner (LIVE_KILL_SWITCH): da qui non si toglie */
    env: boolean;
    /** ms del produttore (`ts` del messaggio) */
    ms: number;
}

/**
 * Legge il freno da un messaggio `modo_ordini` (o `hello.modo_ordini`):
 * `modo_ordini.stato_corrente()` + `ts`. `null` = messaggio storto, runner di
 * prima del 25/09 (senza le chiavi del freno) o riga non letta di recente dal
 * runner (`kill_switch_letto` false e nessun freno dal .env): in quel caso vale
 * la lettura del database.
 */
export function leggiFrenoCanale(d: unknown): FrenoCanale | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    if (typeof o.ts !== 'number' || !Number.isFinite(o.ts)) return null;
    if (typeof o.kill_switch !== 'boolean') return null;
    const env = o.kill_switch_env === true;
    if (o.kill_switch_letto !== true && !env) return null;
    return { tirato: o.kill_switch, env, ms: o.ts };
}

function piuRecente(p: FrenoCanale | null, m: FrenoCanale | null): FrenoCanale | null {
    if (m == null) return p;
    return p != null && p.ms >= m.ms ? p : m;
}

export interface StatoFreno {
    /** null = non si sa (nessuna lettura riuscita, nessun push valido) */
    tirato: boolean | null;
    env: boolean;
    fonte: 'canale' | 'db' | null;
    etaS: number | null;
}

/** Il piu' recente fra la lettura del database e il push del runner. */
export function statoFreno(riga: LiveSettings | null, lettoMs: number | null,
    canale: FrenoCanale | null, nowMs: number): StatoFreno {
    const eta = (ms: number | null) => (ms == null ? null : Math.max(0, Math.round((nowMs - ms) / 1000)));
    if (canale != null && (riga == null || lettoMs == null || canale.ms > lettoMs)) {
        return { tirato: canale.tirato, env: canale.env, fonte: 'canale', etaS: eta(canale.ms) };
    }
    if (riga != null && typeof riga.kill_switch === 'boolean') {
        return { tirato: riga.kill_switch, env: false, fonte: 'db', etaS: eta(lettoMs) };
    }
    return { tirato: null, env: false, fonte: null, etaS: null };
}

export interface RigaFrenoProps {
    /** iniettabili per i test: di serie le RPC vere */
    leggi?: () => Promise<LiveSettings | null>;
    scrivi?: (on: boolean) => Promise<LiveSettings | null>;
    riletturaMs?: number;
}

export function RigaFreno({
    leggi = getLiveSettings, scrivi = setKillSwitch, riletturaMs = RILETTURA_MS,
}: RigaFrenoProps) {
    const [riga, setRiga] = useState<LiveSettings | null>(null);
    const [lettoMs, setLettoMs] = useState<number | null>(null);
    const [erroreLettura, setErroreLettura] = useState<string | null>(null);
    const [errore, setErrore] = useState<string | null>(null);
    const [inCorso, setInCorso] = useState(false);
    /** 0 = niente; 1 = prima conferma del rilascio; 2 = seconda conferma */
    const [passo, setPasso] = useState<0 | 1 | 2>(0);
    const [armatoDa, setArmatoDa] = useState<number | null>(null);
    const [, setTic] = useState(0);
    const [freno, setFreno] = useState<FrenoCanale | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());

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

    // il canale del runner calcio (47331): hello e topic `modo_ordini`
    useEffect(() => {
        const ch = getLocalChannel('calcio');
        const daHello = (h: unknown) => leggiFrenoCanale(
            h && typeof h === 'object' ? (h as Record<string, unknown>).modo_ordini : null);
        const helloDi = () => (typeof ch.getHello === 'function' ? ch.getHello() : null);
        if (ch.getStatus() === 'connected') setFreno(daHello(helloDi()));
        const offStato = ch.onStatus((st) => {
            // canale giu': il push non vale piu', resta il database
            if (st !== 'connected') setFreno(null);
            else setFreno((p) => piuRecente(p, daHello(helloDi())));
        });
        const offHello = ch.subscribe('hello', (d) => setFreno((p) => piuRecente(p, daHello(d))));
        const offModo = ch.subscribe('modo_ordini', (d) => {
            const m = leggiFrenoCanale(d);
            if (m) setFreno((p) => piuRecente(p, m));
        });
        const t = window.setInterval(() => setNowMs(Date.now()), 1_000);
        return () => { offStato(); offHello(); offModo(); window.clearInterval(t); };
    }, []);

    useEffect(() => {
        void ricarica();
        const t = window.setInterval(() => void ricarica(), riletturaMs);
        return () => window.clearInterval(t);
    }, [ricarica, riletturaMs]);

    // la finestra anti-doppio-clic si chiude da sola (ridisegno)
    useEffect(() => {
        if (armatoDa == null) return;
        const t = window.setTimeout(() => setTic((n) => n + 1), ATTESA_CONFERMA_MS + 20);
        return () => window.clearTimeout(t);
    }, [armatoDa]);

    const st = statoFreno(erroreLettura ? null : riga, lettoMs, freno, nowMs);
    const troppoPresto = armatoDa != null && Date.now() - armatoDa < ATTESA_CONFERMA_MS;

    const esegui = async (on: boolean) => {
        setInCorso(true); setErrore(null);
        try {
            const nuova = await scrivi(on);
            if (nuova) { setRiga(nuova); setLettoMs(Date.now()); setErroreLettura(null); }
            await ricarica();
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally {
            setInCorso(false); setPasso(0); setArmatoDa(null);
        }
    };

    const avanza = (p: 1 | 2) => { setPasso(p); setArmatoDa(Date.now()); };
    const annulla = () => { setPasso(0); setArmatoDa(null); };

    const tirato = st.tirato === true;

    return (
        <div className={`px-3 py-2 border-b border-white/10 ${tirato ? 'bg-red-500/10' : ''}`}
            data-testid="cr-freno">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-wider w-24 shrink-0">Freno</span>

                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                    tirato ? 'bg-red-500/30 text-red-200'
                        : st.tirato === false ? 'bg-white/10 text-white/45'
                            : 'bg-orange-500/15 text-orange-300'
                }`} data-testid="cr-freno-stato"
                    title="tirato: nessun bot apre, ne' in live ne' in paper; le chiusure passano sempre">
                    {tirato ? 'TIRATO - nessuna apertura'
                        : st.tirato === false ? 'rilasciato' : 'non letto'}
                </span>

                {st.fonte != null && (
                    <span className="text-[10px] text-white/30" data-testid="cr-freno-fonte"
                        title="da dove viene lo stato: canale del runner calcio (47331, al cambio) o database (get_live_settings, ogni 30 s)">
                        {st.fonte}{' '}{st.etaS == null ? '-' : `${st.etaS} s`}
                    </span>
                )}

                {st.fonte === 'db' && riga?.updated_at && (
                    <span className="text-[10px] text-white/30" data-testid="cr-freno-quando">
                        riga aggiornata il {fmtDateTime(riga.updated_at)}
                    </span>
                )}
            </div>

            {st.env && (
                <div className="mt-1.5 text-[10px] text-amber-300 flex items-center gap-1.5" data-testid="cr-freno-env">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    <span>il freno e' tirato anche dal .env del runner (LIVE_KILL_SWITCH): da qui non si toglie.</span>
                </div>
            )}

            {st.tirato == null && (
                <div className="mt-1.5 text-[10px] text-orange-300" data-testid="cr-freno-non-letto">
                    stato del freno non letto{erroreLettura ? ` (${erroreLettura})` : ''}: tirarlo resta sempre possibile.
                </div>
            )}

            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                {!tirato && (
                    <Button
                        type="button" size="sm"
                        disabled={inCorso}
                        onClick={() => void esegui(true)}
                        data-testid="cr-freno-tira"
                        title="ferma OGNI apertura di tutti i bot, live e paper. Le chiusure restano servite."
                        className="h-6 px-2 text-[10px] uppercase tracking-wider bg-red-600/80 hover:bg-red-600 text-white font-bold"
                    >{inCorso ? <Loader2 className="w-3 h-3 animate-spin" /> : <><OctagonX className="w-3 h-3 mr-1" />tira il freno</>}</Button>
                )}

                {tirato && passo === 0 && (
                    <Button
                        type="button" size="sm" variant="outline"
                        disabled={inCorso}
                        onClick={() => avanza(1)}
                        data-testid="cr-freno-rilascia"
                        title="rialza il freno: si conferma due volte"
                        className="h-6 px-2 text-[10px] uppercase tracking-wider"
                    >rilascia</Button>
                )}

                {tirato && passo === 1 && (
                    <Button
                        type="button" size="sm" variant="outline"
                        disabled={inCorso || troppoPresto}
                        onClick={() => avanza(2)}
                        data-testid="cr-freno-conferma-1"
                        className="h-6 px-2 text-[10px] uppercase tracking-wider border-amber-400/40 text-amber-300"
                    >confermi? i bot accesi tornano ad aprire</Button>
                )}

                {tirato && passo === 2 && (
                    <Button
                        type="button" size="sm"
                        disabled={inCorso || troppoPresto}
                        onClick={() => void esegui(false)}
                        data-testid="cr-freno-conferma-2"
                        className="h-6 px-2 text-[10px] uppercase tracking-wider bg-amber-600/80 hover:bg-amber-600 text-white font-bold"
                    >{inCorso ? <Loader2 className="w-3 h-3 animate-spin" /> : 'si, rilascia il freno'}</Button>
                )}

                {tirato && passo > 0 && (
                    <Button
                        type="button" size="sm" variant="outline"
                        disabled={inCorso}
                        onClick={annulla}
                        data-testid="cr-freno-annulla"
                        className="h-6 px-2 text-[10px] uppercase tracking-wider"
                    >annulla</Button>
                )}
            </div>

            {errore && (
                <div className="mt-1.5 text-[10px] text-red-300" data-testid="cr-freno-errore">
                    il comando non e' andato a buon fine: {errore}. Il freno resta quello mostrato.
                </div>
            )}
        </div>
    );
}

export default RigaFreno;
