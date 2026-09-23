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
import {
    statoSaldoBetfair, leggiSaldoDalCanale, saldoPiuRecente, saldoDaMostrare, testoUltimaVerifica, type SaldoDalCanale,
} from '@/lib/saldoBetfair';
import { getLocalChannel, type LocalChannel, type LocalSport } from '@/lib/localChannel';

/** 23/09 — i canali dei processi che piazzano ordini VERI e pubblicano il
 *  topic "account" dopo ogni ordine/regolazione (`stream/saldo_evento.py`):
 *  runner calcio, runner tennis, Mike, Omega, Safe. Sono gli stessi singleton
 *  già aperti dalla Control Room: nessuna porta nuova. */
export const CANALI_SALDO: readonly LocalSport[] = ['calcio', 'tennis', 'mike', 'omega', 'safe'] as const;

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
        /** 23/09 — tutti i canali che portano il topic "account" (di default
         *  `CANALI_SALDO`). Se il test passa solo `getCanale`, si usa quello. */
        getCanali?: () => LocalChannel[];
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
    /** 23/09 — ultimo SALDO ricevuto dai canali (il più recente vince). */
    const [saldoCanale, setSaldoCanale] = useState<SaldoDalCanale | null>(null);

    const fnFetchAccount = deps?.fetchAccount ?? fetchLiveAccount;
    const fnSubscribeAccount = deps?.subscribeAccount ?? subscribeLiveAccount;
    const fnFetchHeartbeat = deps?.fetchHeartbeat ?? fetchLiveHeartbeat;
    const fnSubscribeHeartbeat = deps?.subscribeHeartbeat ?? subscribeLiveHeartbeat;
    const fnGetCanali = deps?.getCanali
        ?? (deps?.getCanale ? (() => [deps.getCanale!()]) : (() => CANALI_SALDO.map((s) => getLocalChannel(s))));

    // ref: evita di ricreare le sottoscrizioni se qualcuno passa `deps` come
    // oggetto letterale nuovo a ogni render (comodo per i test)
    const depsRef = useRef({ fnFetchAccount, fnSubscribeAccount, fnFetchHeartbeat, fnSubscribeHeartbeat, fnGetCanali });
    depsRef.current = { fnFetchAccount, fnSubscribeAccount, fnFetchHeartbeat, fnSubscribeHeartbeat, fnGetCanali };

    useEffect(() => {
        let vivo = true;
        depsRef.current.fnFetchAccount().then((r) => { if (vivo) setConto(r); })
            .catch(() => { if (vivo) setErroreLettura(true); });
        depsRef.current.fnFetchHeartbeat().then((r) => { if (vivo) setHeartbeat(r); }).catch(() => { /* non critico: si mostra "battito non letto" */ });
        const offAccount = depsRef.current.fnSubscribeAccount((r) => { if (vivo) setConto(r); });
        const offHeartbeat = depsRef.current.fnSubscribeHeartbeat((r) => { if (vivo) setHeartbeat(r); });
        // canali locali, topic "account" (23/09): la freschezza (`checked_at`)
        // E il valore. Il valore del canale è la STESSA lettura REST che il
        // processo scrive anche sul database: il socket la anticipa, non la
        // inventa. Vince il più recente; un messaggio vecchio è ignorato; a
        // canali muti resta il database, come prima.
        const offCanali = depsRef.current.fnGetCanali().map((canale) => canale.subscribe('account', (d) => {
            if (!vivo) return;
            const c = checkedAtDiMessaggioAccount(d);
            if (c) setCheckedAt((prev) => (prev && Date.parse(prev) >= Date.parse(c) ? prev : c));
            const s = leggiSaldoDalCanale(d);
            if (s) setSaldoCanale((prev) => saldoPiuRecente(prev, s));
        }));
        return () => { vivo = false; offAccount(); offHeartbeat(); offCanali.forEach((off) => off()); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 1000);
        return () => window.clearInterval(t);
    }, []);

    // 23/09: il dato mostrato è il più recente fra riga del database e canale.
    const mostrato = saldoDaMostrare(conto, saldoCanale);
    const etaSaldoS = ageSeconds(mostrato.istante, nowMs);
    // l'ultimo istante in cui QUALCUNO ha davvero letto il conto (il più
    // recente fra `checked_at` del canale e l'istante del dato mostrato):
    // è l'ora del «non aggiornato da HH:MM», mai un numero muto.
    // F2 revisore A 23/09: GG/MM HH:MM se non e' di oggi (testoUltimaVerifica).
    const ultimaVerifica = [checkedAt, mostrato.istante]
        .filter((x): x is string => typeof x === 'string' && Number.isFinite(Date.parse(x)))
        .sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null;
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

    const testoValore = nascosto ? '••••,•• €' : fmtMoney(mostrato.available);
    const testoEsposizione = nascosto ? '••••,•• €' : fmtMoney(mostrato.exposure);

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
                {conto == null && saldoCanale == null && !erroreLettura ? DASH : testoValore}
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
                    : stato.attenzione
                        ? <>non aggiornato da {testoUltimaVerifica(ultimaVerifica, nowMs)}</>
                        : <>{mostrato.fonte === 'canale' ? 'controllato' : 'ultimo cambio'}: {fmtAge(etaSaldoS)}</>}
            </div>
        </Card>
    );
}

export default SaldoBetfairCard;
