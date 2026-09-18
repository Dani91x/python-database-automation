// ============================================================================
// SaldoBetfairCard.tsx — SALDO DEL CONTO BETFAIR nella Control Room (Task 3).
//
// Riusa `betfair_live_account`/`betfair_live_heartbeat` (`lib/liveOrders.ts`),
// stesso schema d'uso di `pages/SeguiLive.tsx`: NESSUNA lettura nuova, nessuna
// tabella nuova. Il componente è AUTOSUFFICIENTE (non passa da
// `useControlRoom`): apre le sue sottoscrizioni Realtime sulla stessa riga
// singleton già usata altrove — stesso pattern di pagina-per-pagina già in
// uso nel resto della piattaforma.
//
// ETÀ DEL DATO: la regola sta isolata e testata in `lib/saldoBetfair.ts`
// (`statoSaldoBetfair`) — qui solo presentazione.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { fmtMoney, fmtAge, ageSeconds, DASH } from '@/lib/format';
import {
    fetchLiveAccount, subscribeLiveAccount, fetchLiveHeartbeat, subscribeLiveHeartbeat,
    type LiveAccountRow, type LiveHeartbeatRow,
} from '@/lib/liveOrders';
import { statoSaldoBetfair } from '@/lib/saldoBetfair';
import { getLocalChannel, type LocalChannel } from '@/lib/localChannel';

const CHIAVE_NASCOSTO = 'cr-saldo-nascosto';

function leggiPreferenzaNascosto(): boolean {
    try { return window.localStorage.getItem(CHIAVE_NASCOSTO) === '1'; } catch { return false; }
}
function scriviPreferenzaNascosto(v: boolean): void {
    try { window.localStorage.setItem(CHIAVE_NASCOSTO, v ? '1' : '0'); } catch { /* preferenza persa, non bloccante */ }
}

export interface SaldoBetfairCardProps {
    testId?: string;
    /** dipendenze iniettabili per i test: di default le funzioni vere di `lib/liveOrders` */
    deps?: {
        fetchAccount?: typeof fetchLiveAccount;
        subscribeAccount?: typeof subscribeLiveAccount;
        fetchHeartbeat?: typeof fetchLiveHeartbeat;
        subscribeHeartbeat?: typeof subscribeLiveHeartbeat;
        /** 18/09 (raccordo) — il canale locale del runner calcio (porta
         *  47331): di default `getLocalChannel('calcio')`, iniettabile per i
         *  test senza aprire un vero WebSocket. */
        getCanale?: () => LocalChannel;
    };
}

/** Il messaggio "account" del canale locale porta ENTRAMBI i tipi di push
 *  (saldo e manuale): si distinguono guardando le chiavi presenti (B1 §6/§19).
 *  Qui interessa SOLO `checked_at` — il valore del saldo resta quello del
 *  database (write-on-change, ma corretto): il canale serve a dire "quando è
 *  stato controllato l'ultima volta", non a sostituire il numero. */
export function checkedAtDiMessaggioAccount(d: unknown): string | null {
    const msg = d as { checked_at?: unknown; available?: unknown } | null;
    if (!msg || typeof msg !== 'object') return null;
    if (typeof msg.available !== 'number') return null; // messaggio "manuale", non "saldo"
    return typeof msg.checked_at === 'string' ? msg.checked_at : null;
}

export function SaldoBetfairCard({ testId = 'saldo-betfair', deps }: SaldoBetfairCardProps) {
    const [conto, setConto] = useState<LiveAccountRow | null>(null);
    const [heartbeat, setHeartbeat] = useState<LiveHeartbeatRow | null>(null);
    const [erroreLettura, setErroreLettura] = useState(false);
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [nascosto, setNascosto] = useState(leggiPreferenzaNascosto);
    /** ultimo "checked_at" ricevuto dal canale locale; null = mai ricevuto
     *  (app non desktop, o canale non connesso). */
    const [checkedAt, setCheckedAt] = useState<string | null>(null);

    const fnFetchAccount = deps?.fetchAccount ?? fetchLiveAccount;
    const fnSubscribeAccount = deps?.subscribeAccount ?? subscribeLiveAccount;
    const fnFetchHeartbeat = deps?.fetchHeartbeat ?? fetchLiveHeartbeat;
    const fnSubscribeHeartbeat = deps?.subscribeHeartbeat ?? subscribeLiveHeartbeat;
    const fnGetCanale = deps?.getCanale ?? (() => getLocalChannel('calcio'));

    // ref: evita di ricreare le sottoscrizioni se qualcuno passa `deps` come
    // oggetto letterale nuovo a ogni render (comodo per i test)
    const depsRef = useRef({ fnFetchAccount, fnSubscribeAccount, fnFetchHeartbeat, fnSubscribeHeartbeat, fnGetCanale });
    depsRef.current = { fnFetchAccount, fnSubscribeAccount, fnFetchHeartbeat, fnSubscribeHeartbeat, fnGetCanale };

    useEffect(() => {
        let vivo = true;
        depsRef.current.fnFetchAccount().then((r) => { if (vivo) setConto(r); })
            .catch(() => { if (vivo) setErroreLettura(true); });
        depsRef.current.fnFetchHeartbeat().then((r) => { if (vivo) setHeartbeat(r); }).catch(() => { /* non critico: si mostra "battito non letto" */ });
        const offAccount = depsRef.current.fnSubscribeAccount((r) => { if (vivo) setConto(r); });
        const offHeartbeat = depsRef.current.fnSubscribeHeartbeat((r) => { if (vivo) setHeartbeat(r); });
        // canale locale (47331, topic "account"): SOLO per la freschezza
        // (`checked_at`), mai per sostituire il valore letto dal database
        // (regola 1 della Control Room: il socket accelera, non sostituisce).
        const canale = depsRef.current.fnGetCanale();
        const offCanale = canale.subscribe('account', (d) => {
            const c = checkedAtDiMessaggioAccount(d);
            if (vivo && c) setCheckedAt(c);
        });
        return () => { vivo = false; offAccount(); offHeartbeat(); offCanale(); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 1000);
        return () => window.clearInterval(t);
    }, []);

    const etaSaldoS = ageSeconds(conto?.updated_at ?? null, nowMs);
    // il battito RUNNER (non il watchdog): dice se qualcuno sta davvero
    // guardando il conto in questo momento.
    const etaHeartbeatS = ageSeconds(heartbeat?.ts ?? null, nowMs);
    const etaCanaleS = ageSeconds(checkedAt, nowMs);
    const stato = statoSaldoBetfair({
        etaSaldoS,
        etaHeartbeatS: heartbeat ? etaHeartbeatS : null,
        etaCanaleS: checkedAt ? etaCanaleS : null,
    });

    const toggleNascosto = () => {
        setNascosto((prev) => { const next = !prev; scriviPreferenzaNascosto(next); return next; });
    };

    const testoValore = nascosto ? '••••,•• €' : fmtMoney(conto?.available ?? null);
    const testoEsposizione = nascosto ? '••••,•• €' : fmtMoney(conto?.exposure ?? null);

    return (
        <Card className="glass-card border-white/10 p-4 flex flex-col gap-2.5" data-testid={testId}>
            <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-white/50">Saldo conto Betfair</span>
                <button
                    type="button"
                    onClick={toggleNascosto}
                    aria-pressed={nascosto}
                    title={nascosto ? 'mostra il saldo' : 'nascondi il saldo'}
                    data-testid={`${testId}-occhio`}
                    className="text-white/40 hover:text-white/80 p-1 rounded border border-white/10"
                >
                    {nascosto ? <EyeOff className="w-3.5 h-3.5" aria-hidden /> : <Eye className="w-3.5 h-3.5" aria-hidden />}
                </button>
            </div>

            <div className="font-display font-extrabold text-2xl tabular-nums" data-testid={`${testId}-valore`}>
                {conto == null && !erroreLettura ? DASH : testoValore}
            </div>

            <div className="flex items-baseline justify-between text-[11.5px] pt-2 border-t border-white/10">
                <span className="text-white/50">Esposizione</span>
                <span className="font-mono text-orange-400" data-testid={`${testId}-esposizione`}>{testoEsposizione}</span>
            </div>

            <div
                className={`text-[10.5px] flex items-center gap-1.5 ${stato.attenzione ? 'text-orange-400' : 'text-white/40'}`}
                data-testid={`${testId}-nota`}
                title={stato.messaggio}
            >
                <span className={`w-1.5 h-1.5 rounded-full ${stato.attenzione ? 'bg-orange-400' : 'bg-emerald-400'}`} aria-hidden />
                {etaSaldoS == null
                    ? (erroreLettura ? 'saldo non leggibile' : 'saldo non ancora letto')
                    : <>ultimo cambio: {fmtAge(etaSaldoS)}{stato.attenzione ? ' · saldo non verificato di recente' : ''}</>}
            </div>
        </Card>
    );
}

export default SaldoBetfairCard;
