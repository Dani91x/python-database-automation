// ============================================================================
// Salute.tsx - la pagina "Salute" dell'app (tappa T0A della migrazione, 09/10/2026).
//
// Che cosa mostra: per ogni servizio Python dell'app (runner, bot, scanner,
// scalper) l'ultima riga del monitor `Betfair/monitor/` (una ogni 30 s, solo con
// MONITOR_SALUTE=1 nel .env): vivo/in ritardo/muto, CPU, memoria, richieste al
// DB e a Betfair al minuto, errori di log; i tratti misurati del percorso dato ->
// ordine (L1, L3, L6, L6b, L7); versioni e Windows; vitalita' dei raccoglitori
// del cloud. Soglie: obiettivi PROVVISORI della scheda I par. 7.
//
// Da dove: UNA RPC ogni 10 s sul client Supabase che l'app ha gia'
// (`monitor_salute_stato`), una ogni 5 minuti per i raccoglitori. Nessun canale
// locale aperto, nessuna connessione nuova. Sola lettura: nessun comando.
// Calcio e tennis non si mischiano (colonna sport); paper e live non c'entrano
// (nessun denaro su questa pagina; le esecuzioni le conta il referto, separate).
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Activity, Cpu, Database, HeartPulse, Server } from 'lucide-react';
import { PageShell } from '@/components/trading/PageShell';
import { KpiRow, StatTile } from '@/components/trading/StatTile';
import { EmptyState, LoadingState, SectionCard } from '@/components/trading/EmptyState';
import { fmtAge, fmtDateTime, fmtNum, fmtPctPoints, fmtTime, ageSeconds } from '@/lib/format';
import {
    OBIETTIVI, alMinuto, leggiRaccoglitori, leggiStatoSalute, semaforo, spiegaTratto, totali,
    trattiUltimi, versioniDesktop, type Raccoglitore, type Semaforo, type StatoSalute,
} from '@/lib/salute';

const ETICHETTA: Record<Semaforo, { testo: string; cls: string }> = {
    vivo: { testo: 'VIVO', cls: 'text-emerald-400 border-emerald-500/40' },
    ritardo: { testo: 'IN RITARDO', cls: 'text-amber-300 border-amber-500/40' },
    muto: { testo: 'MUTO', cls: 'text-red-400 border-red-500/40' },
};

function Pallino({ s }: { s: Semaforo }) {
    const e = ETICHETTA[s];
    return (
        <span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider ${e.cls}`}
            data-testid={`salute-stato-${s}`}>
            {e.testo}
        </span>
    );
}

const TH = 'px-3 py-1.5 text-left font-normal text-[11px] uppercase tracking-wider text-slate-400';
const TD = 'px-3 py-1.5 tabular-nums';

export default function Salute() {
    const [stato, setStato] = useState<StatoSalute | null>(null);
    const [errore, setErrore] = useState<string | null>(null);
    const [caricato, setCaricato] = useState(false);
    const [raccoglitori, setRaccoglitori] = useState<Raccoglitore[]>([]);
    const [erroreRacc, setErroreRacc] = useState<string | null>(null);
    const [adessoMs, setAdessoMs] = useState(() => Date.now());

    useEffect(() => {
        let vivo = true;
        const carica = () => {
            leggiStatoSalute(6).then(({ stato: s, errore: e }) => {
                if (!vivo) return;
                setStato(s);
                setErrore(e);
                setCaricato(true);
                setAdessoMs(Date.now());
            }).catch((e: unknown) => {
                if (!vivo) return;
                setErrore(String(e));
                setCaricato(true);
            });
        };
        carica();
        const t = window.setInterval(carica, 10_000);
        return () => { vivo = false; window.clearInterval(t); };
    }, []);

    useEffect(() => {
        let vivo = true;
        const carica = () => {
            leggiRaccoglitori().then(({ tabelle, errore: e }) => {
                if (!vivo) return;
                setRaccoglitori(tabelle);
                setErroreRacc(e);
            }).catch(() => {});
        };
        carica();
        const t = window.setInterval(carica, 300_000);
        return () => { vivo = false; window.clearInterval(t); };
    }, []);

    const ultimi = useMemo(() => stato?.ultimi ?? [], [stato]);
    const tot = useMemo(() => totali(ultimi, adessoMs), [ultimi, adessoMs]);
    const tratti = useMemo(() => trattiUltimi(ultimi), [ultimi]);
    const mediaSerie = useMemo(() => {
        const m = new Map<string, { cpu: number[]; rss: number[] }>();
        for (const s of stato?.serie ?? []) {
            const v = m.get(s.servizio) ?? { cpu: [], rss: [] };
            if (s.cpu_media != null) v.cpu.push(Number(s.cpu_media));
            if (s.rss_max != null) v.rss.push(Number(s.rss_max));
            m.set(s.servizio, v);
        }
        return m;
    }, [stato]);
    const desktop = useMemo(() => versioniDesktop(typeof navigator !== 'undefined' ? navigator.userAgent : ''), []);
    const sistema = stato?.sistema?.find((x) => x.sistema)?.sistema as
        { python?: string; pacchetti?: Record<string, string | null>; windows?: Record<string, unknown> } | undefined;

    return (
        <PageShell
            title="Salute · AI Terminal"
            footer={(
                <>
                    Fonte: tabella monitor_metrics (una riga ogni 30 s per servizio, scritta da Betfair/monitor
                    con MONITOR_SALUTE=1). Soglie provvisorie della scheda I par. 7: CPU p95 per servizio entro
                    {' '}{OBIETTIVI.cpu_servizio_p95_pct} % di un core, app entro {OBIETTIVI.cpu_app_media_pct} %,
                    bot entro {OBIETTIVI.db_bot_al_minuto} richieste al minuto, orologio entro {OBIETTIVI.orologio_ms} ms.
                    Il referto di 24 h: python -m Betfair.monitor.referto --giorno AAAA-MM-GG.
                </>
            )}
        >
            <div className="flex items-center gap-2 text-sm text-slate-300" data-testid="salute-intestazione">
                <HeartPulse className="w-4 h-4 text-teal-300" aria-hidden />
                <span className="font-heading">Salute dell&apos;app</span>
                <span className="text-[11px] text-slate-500">
                    {caricato ? `aggiornata alle ${fmtTime(adessoMs, { seconds: true })} · ogni 10 s` : 'lettura in corso'}
                </span>
            </div>

            {!caricato ? <LoadingState label="lettura del monitor…" testId="salute-caricamento" /> : (
                errore || !stato ? (
                    <EmptyState testId="salute-vuota">
                        Nessun dato del monitor. Serve la migrazione migrations/monitor_metrics_2026-10-09.sql
                        (la applica l&apos;utente) e MONITOR_SALUTE=1 nel .env, poi il riavvio dell&apos;app.
                        {errore ? ` (${errore})` : ''}
                    </EmptyState>
                ) : (
                    <>
                        <KpiRow>
                            <StatTile label="Servizi vivi" value={`${tot.vivi}/${tot.servizi}`} icon={<Server className="w-3 h-3" />}
                                tone={tot.vivi === tot.servizi && tot.servizi > 0 ? 'pos' : 'danger'} testId="salute-kpi-servizi" />
                            <StatTile label="CPU app (% di un core)" value={fmtPctPoints(tot.cpu, 0)} icon={<Cpu className="w-3 h-3" />}
                                tone={tot.cpu != null && tot.cpu > OBIETTIVI.cpu_app_media_pct ? 'danger' : 'plain'} testId="salute-kpi-cpu" />
                            <StatTile label="Memoria app" value={tot.rssMb == null ? '—' : `${fmtNum(tot.rssMb, 0)} MB`}
                                testId="salute-kpi-ram" />
                            <StatTile label="Richieste al DB" value={tot.dbAlMinuto == null ? '—' : `${fmtNum(tot.dbAlMinuto, 0)}/min`}
                                icon={<Database className="w-3 h-3" />} testId="salute-kpi-db" />
                            <StatTile label="REST Betfair" value={tot.restAlMinuto == null ? '—' : `${fmtNum(tot.restAlMinuto, 0)}/min`}
                                icon={<Activity className="w-3 h-3" />} testId="salute-kpi-rest" />
                            <StatTile label="Orologio (limite sup.)" value={tot.orologioMs == null ? '—' : `${fmtNum(tot.orologioMs, 0)} ms`}
                                tone={tot.orologioMs != null && tot.orologioMs > OBIETTIVI.orologio_ms ? 'danger' : 'plain'}
                                sub="minimo di rx − pt: scarto del PC + latenza" testId="salute-kpi-orologio" />
                            <StatTile label="Errori di log" value={fmtNum(tot.erroriLog, 0)}
                                tone={tot.erroriLog > 0 ? 'danger' : 'plain'} sub="ultima finestra" testId="salute-kpi-errori" />
                        </KpiRow>

                        <SectionCard icon={<Server className="w-4 h-4 text-teal-300" />} title="Servizi" count={ultimi.length}
                            note={`ultima riga di ognuno · serie di ${stato.ore} h`} testId="salute-servizi">
                            {ultimi.length === 0 ? (
                                <EmptyState testId="salute-servizi-vuoti">
                                    Nessuna riga nelle ultime {stato.ore} ore: il monitor e&apos; spento (MONITOR_SALUTE=0) o l&apos;app e&apos; chiusa.
                                </EmptyState>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-xs">
                                        <thead><tr>
                                            <th className={TH}>Servizio</th><th className={TH}>Sport</th><th className={TH}>Stato</th>
                                            <th className={TH}>Ultima riga</th><th className={TH}>Vita</th><th className={TH}>CPU</th>
                                            <th className={TH}>CPU media {stato.ore} h</th><th className={TH}>RAM MB</th>
                                            <th className={TH}>RAM max {stato.ore} h</th><th className={TH}>DB/min</th><th className={TH}>REST/min</th>
                                        </tr></thead>
                                        <tbody>
                                            {ultimi.map((r) => {
                                                const s = semaforo(r.ts, adessoMs);
                                                const serie = mediaSerie.get(r.servizio);
                                                const cpuMedia = serie && serie.cpu.length
                                                    ? serie.cpu.reduce((a, b) => a + b, 0) / serie.cpu.length : null;
                                                const rssMax = serie && serie.rss.length ? Math.max(...serie.rss) : null;
                                                const cpuAlta = r.cpu_pct != null && Number(r.cpu_pct) > OBIETTIVI.cpu_servizio_p95_pct;
                                                return (
                                                    <tr key={r.servizio} className="border-t border-white/5" data-testid="salute-riga-servizio">
                                                        <td className={`${TD} text-slate-200`}>{r.servizio}</td>
                                                        <td className={TD}>{r.sport ?? '—'}</td>
                                                        <td className={TD}><Pallino s={s} /></td>
                                                        <td className={TD}>{fmtAge(ageSeconds(r.ts, adessoMs))} fa</td>
                                                        <td className={TD}>{fmtAge(r.uptime_s)}</td>
                                                        <td className={`${TD} ${cpuAlta ? 'text-orange-400' : ''}`}>{fmtPctPoints(r.cpu_pct, 1)}</td>
                                                        <td className={TD}>{fmtPctPoints(cpuMedia, 1)}</td>
                                                        <td className={TD}>{fmtNum(r.rss_mb, 0)}</td>
                                                        <td className={TD}>{fmtNum(rssMax, 0)}</td>
                                                        <td className={TD}>{fmtNum(alMinuto(r, 'db'), 1)}</td>
                                                        <td className={TD}>{fmtNum(alMinuto(r, 'rest'), 1)}</td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </SectionCard>

                        <SectionCard icon={<Activity className="w-4 h-4 text-teal-300" />} title="Tratti misurati" count={tratti.length}
                            note="ultima finestra di 30 s · ms (p50/p99 al bordo del secchio)" testId="salute-tratti">
                            {tratti.length === 0 ? (
                                <EmptyState testId="salute-tratti-vuoti">Nessun tratto nell&apos;ultima finestra.</EmptyState>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-xs">
                                        <thead><tr>
                                            <th className={TH}>Tratto</th><th className={TH}>Servizio</th><th className={TH}>n</th>
                                            <th className={TH}>p50</th><th className={TH}>p99</th><th className={TH}>max</th>
                                            <th className={TH}>Cosa misura</th>
                                        </tr></thead>
                                        <tbody>
                                            {tratti.map((t) => (
                                                <tr key={`${t.servizio}|${t.nome}`} className="border-t border-white/5" data-testid="salute-riga-tratto">
                                                    <td className={`${TD} text-slate-200`}>{t.nome}</td>
                                                    <td className={TD}>{t.servizio}</td>
                                                    <td className={TD}>{fmtNum(t.n, 0)}</td>
                                                    <td className={TD}>{fmtNum(t.p50, 1)}</td>
                                                    <td className={TD}>{fmtNum(t.p99, 1)}</td>
                                                    <td className={TD}>{fmtNum(t.max, 1)}</td>
                                                    <td className={`${TD} text-slate-400`}>{spiegaTratto(t.nome)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </SectionCard>
                    </>
                )
            )}

            <SectionCard icon={<Cpu className="w-4 h-4 text-teal-300" />} title="Sistema" testId="salute-sistema"
                note="versioni bloccate fino a T26 (manifesto di T0C)">
                <div className="px-4 py-3 text-xs text-slate-300 space-y-1">
                    <div data-testid="salute-versioni-desktop">
                        Desktop: Electron {desktop.electron ?? '—'} · Chromium {desktop.chrome ?? '—'}
                    </div>
                    <div data-testid="salute-versioni-python">
                        Python {sistema?.python ?? '—'}
                        {sistema?.pacchetti ? ` · ${Object.entries(sistema.pacchetti)
                            .map(([k, v]) => `${k} ${v ?? '—'}`).join(' · ')}` : ''}
                    </div>
                    <div data-testid="salute-windows">
                        Windows: {sistema?.windows ? Object.entries(sistema.windows)
                            .map(([k, v]) => `${k} ${String(v)}`).join(' · ') : 'non letto (serve una riga del monitor dal PC)'}
                    </div>
                </div>
            </SectionCard>

            <SectionCard icon={<Database className="w-4 h-4 text-teal-300" />} title="Raccoglitori del cloud"
                count={raccoglitori.length} note="ultimo aggiornamento per tabella · ogni 5 minuti" testId="salute-raccoglitori">
                {raccoglitori.length === 0 ? (
                    <EmptyState testId="salute-raccoglitori-vuoti">
                        Nessuna lettura{erroreRacc ? ` (${erroreRacc})` : ''}: serve la migrazione del monitor.
                    </EmptyState>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead><tr>
                                <th className={TH}>Tabella</th><th className={TH}>Ultimo dato</th><th className={TH}>Eta&apos;</th>
                            </tr></thead>
                            <tbody>
                                {raccoglitori.map((r) => (
                                    <tr key={r.tabella} className="border-t border-white/5" data-testid="salute-riga-raccoglitore">
                                        <td className={`${TD} text-slate-200`}>{r.tabella}</td>
                                        <td className={TD}>{r.errore ? `non letto: ${r.errore}` : fmtDateTime(r.max)}</td>
                                        <td className={TD}>{r.eta_ore == null ? '—' : `${fmtNum(r.eta_ore, 1)} h`}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </SectionCard>
        </PageShell>
    );
}
