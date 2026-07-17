// ============================================================================
// omegaMissions.ts — client del tab MISSIONE di /omega (centro di controllo
// PER PARTITA). Parla SOLO con le RPC owner-only già esistenti:
//   omega_mission_activate / omega_mission_stop / omega_mission_follow /
//   get_omega_missions.
// Il servizio locale aggiorna punteggio/fase e scrive i SUGGERIMENTI; la UI
// legge lo specchio DB e piazza SOLO su click esplicito (mai automatico).
// Gli helper in fondo sono PURI e testati in omegaMissions.test.ts.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ------------------------------------------------------------------- tipi
export type MissionStatus = 'active' | 'paused' | 'closed';
export type MissionPhase = 'pre' | '1t' | 'ht' | '2t' | 'finita';
export type MissionLegKey = 'ht_cs' | 'ft_cs' | 'scalp';

// CONSULENTE DATI — blocco PURAMENTE INFORMATIVO scritto dal servizio dentro
// le suggestion CS (Poisson interno, frequenza lega, H2H). Mai usato per i
// payload degli ordini: market_id/selection_id/prezzi restano della suggestion.
export interface MissionAdvisor {
    matched_fixture_id: number | null;
    poisson_prob: number | null;                     // 0..1 (pre-match)
    freq_league: { p: number; n: number } | null;    // baseline storica lega
    h2h: { n_meetings: number; n_score: number } | null;
    sources: Record<string, string> | null;
}

// Suggerimento LAY (gambe 1T/2T sul Correct Score)
export interface MissionSuggestionLay {
    market_id: string;
    market_name: string | null;
    market_type: string | null;
    selection_id: number;
    runner_name: string | null;
    lay_price: number | null;
    lay_size: number | null;
    advisor?: MissionAdvisor | null;   // informativo, opzionale (null dichiarato)
    updated_at: string | null;
}

// Suggerimento BACK (scalp sull'Under)
export interface MissionSuggestionScalp {
    market_id: string;
    market_name: string | null;
    market_type: string | null;
    selection_id: number;
    runner_name: string | null;
    back_price: number | null;
    back_size: number | null;
    line: number | null;
    updated_at: string | null;
}

export interface MissionTrade {
    id: number;
    runner_name: string | null;
    side: string;
    price: number | null;
    size: number | null;
    liability: number | null;
    status: string;
    pnl: number | null;
    mode: string;
}

export interface MissionLeg {
    realized: number | null;
    open_liability: number | null;
    n_open: number | null;
    n_settled: number | null;
    trades: MissionTrade[];
}

export type MissionLegs = Partial<Record<MissionLegKey, MissionLeg | null>>;

export interface MissionScalper {
    status: string;
    dry_run: boolean;
    /** ⚠️ P&L LORDO (flumine non detrae la commissione 4,5-5%), a differenza
     *  dei realized delle gambe Omega che sono NETTI: in UI va etichettato
     *  "lordo" ovunque compaia. */
    pnl_locked: number | null;
    /** ⚠️ P&L LORDO dei soli cicli regolati (validazione paper); opzionale. */
    pnl_settled?: number | null;
}

export interface MissionRow {
    event_id: string;
    event_name: string | null;
    kickoff: string | null;
    mission_date: string | null;
    target: number | null;
    status: MissionStatus;
    phase_now: MissionPhase | null;
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    score_status: string | null;
    suggestion_ht: MissionSuggestionLay | null;
    suggestion_ft: MissionSuggestionLay | null;
    suggestion_scalp: MissionSuggestionScalp | null;
    error: string | null;
    created_at: string | null;
    updated_at: string | null;
    legs: MissionLegs | null;
    scalper: MissionScalper | null;
    followed: boolean;
}

export interface MissionsSummary {
    missions_total: number;
    missions_active: number;
}

export interface MissionsPayload {
    missions: MissionRow[];
    summary: MissionsSummary;
}

// --------------------------------------------------------------------- RPC
export async function activateMission(
    eventId: string, eventName: string, kickoff: string | null, target: number,
): Promise<MissionRow> {
    const { data, error } = await supabase.rpc('omega_mission_activate', {
        p_event_id: eventId,
        p_event_name: eventName,
        p_kickoff: kickoff,
        p_target: target,
    });
    if (error) throw new Error(error.message);
    return data as unknown as MissionRow;
}

// close=false → PAUSA · close=true → CHIUDI definitivamente la missione
export async function stopMission(eventId: string, close: boolean): Promise<MissionRow> {
    const { data, error } = await supabase.rpc('omega_mission_stop', {
        p_event_id: eventId,
        p_close: close,
    });
    if (error) throw new Error(error.message);
    return data as unknown as MissionRow;
}

// Prerequisito dello scalper: registra l'evento tra i "seguiti".
export async function followMission(
    eventId: string, home: string, away: string, openDate: string | null,
): Promise<{ followed: boolean; already: boolean }> {
    const { data, error } = await supabase.rpc('omega_mission_follow', {
        p_event_id: eventId,
        p_home: home,
        p_away: away,
        p_open_date: openDate,
    });
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as Partial<{ followed: boolean; already: boolean }>;
    return { followed: d.followed === true, already: d.already === true };
}

export async function fetchMissions(): Promise<MissionsPayload> {
    const { data, error } = await supabase.rpc('get_omega_missions', {});
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as Partial<MissionsPayload>;
    return {
        missions: d.missions ?? [],
        summary: {
            missions_total: Number(d.summary?.missions_total ?? 0) || 0,
            missions_active: Number(d.summary?.missions_active ?? 0) || 0,
        },
    };
}

// Realtime su omega_missions + omega_trades (audit L12 16/07: fill/settle dei
// trade arrivavano solo col poll 10s → la scheda mostrava una gamba "senza
// trade" già piazzata). Stesso pattern di subscribeOmega.
export function subscribeOmegaMissions(onChange: () => void): () => void {
    const channel = supabase
        .channel('omega-missions-live')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'omega_missions' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'omega_trades' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

// ----------------------------------------------------------- helper PURI
// Numero SEMPRE finito: mai NaN in UI né nei calcoli money-critical.
export function toNum(v: unknown, dflt = 0): number {
    const n = Number(v);
    return Number.isFinite(n) ? n : dflt;
}

// "Roma v Lazio" → {home:'Roma', away:'Lazio'}. Separatore Betfair ' v ',
// fallback ' vs '. La regex / vs? /i copre entrambi in un colpo solo
// (greedy: su " vs " NON spezza dentro come farebbe split(' v ')).
// Senza separatore: tutto in home, away vuoto (conservativo).
export function splitEventName(name: string | null | undefined): { home: string; away: string } {
    const s = String(name ?? '').trim();
    const m = s.match(/ vs? /i);
    if (!m || m.index === undefined) return { home: s, away: '' };
    return {
        home: s.slice(0, m.index).trim(),
        away: s.slice(m.index + m[0].length).trim(),
    };
}

// Σ realized delle sole gambe lay/scalp (senza lo scalper pre-match).
export function missionLegsRealized(m: Pick<MissionRow, 'legs'>): number {
    const legs = m.legs ?? {};
    return (Object.keys(legs) as MissionLegKey[])
        .reduce((sum, k) => sum + toNum(legs[k]?.realized), 0);
}

// Realizzato TOTALE della missione = gambe + pnl_locked dello scalper.
// È il numero che avanza verso il target (e nella barra di giornata).
// AUDIT H2 16/07: lo scalper in DRY-RUN produce P&L SIMULATO — non deve mai
// ridurre il gap che l'utente copre a soldi veri, né gonfiare la barra di
// giornata. Conta solo se dry_run === false.
// ⚠️ 17/07: il contributo scalper è LORDO (flumine non detrae la commissione
// 4,5-5%), i realized delle gambe sono NETTI → l'aggregato è leggermente
// ottimista sulla parte scalper; la UI etichetta "lordo" dove lo mostra.
export function scalperRealized(m: Pick<MissionRow, 'scalper'>): number {
    return m.scalper?.dry_run === false ? toNum(m.scalper.pnl_locked) : 0;
}

// P&L simulato dello scalper dry-run (da mostrare come voce separata, mai sommato).
export function scalperSimulated(m: Pick<MissionRow, 'scalper'>): number {
    return m.scalper && m.scalper.dry_run !== false ? toNum(m.scalper.pnl_locked) : 0;
}

export function missionRealized(m: Pick<MissionRow, 'legs' | 'scalper'>): number {
    return missionLegsRealized(m) + scalperRealized(m);
}

// Gap residuo verso il target: target − scalper REALE − Σ legs.realized.
export function missionGap(m: Pick<MissionRow, 'target' | 'legs' | 'scalper'>): number {
    return toNum(m.target) - missionRealized(m);
}

// ------------------------------------------------- CONSULENTE DATI (advisor)
// Parti testuali del blocco advisor, es. ["Poisson ~1/140", "Lega 0.8% (n=300)",
// "H2H mai in 6 scontri"]. Solo i segnali DISPONIBILI: i null spariscono.
// PURO e difensivo (mai NaN in UI); [] se advisor assente → la riga non si mostra.
export function formatAdvisorParts(a: MissionAdvisor | null | undefined): string[] {
    if (!a) return [];
    const parts: string[] = [];
    // null/undefined = segnale ASSENTE (Number(null)=0 mentirebbe con "≈0")
    if (a.poisson_prob !== null && a.poisson_prob !== undefined) {
        const p = Number(a.poisson_prob);
        if (Number.isFinite(p) && p > 0) {
            parts.push(`Poisson ~1/${Math.max(1, Math.round(1 / p))}`);
        } else if (p === 0) {
            parts.push('Poisson ≈0');
        }
    }
    if (a.freq_league && Number.isFinite(Number(a.freq_league.p))) {
        parts.push(`Lega ${(toNum(a.freq_league.p) * 100).toFixed(1)}% (n=${toNum(a.freq_league.n)})`);
    }
    if (a.h2h && toNum(a.h2h.n_meetings) > 0) {
        const n = toNum(a.h2h.n_meetings);
        const k = toNum(a.h2h.n_score);
        parts.push(k === 0 ? `H2H mai in ${n} scontri` : `H2H ${k}/${n} scontri`);
    }
    return parts;
}

// Tooltip con le FONTI dei segnali (una per riga); '' se non ci sono fonti.
export function advisorTooltip(a: MissionAdvisor | null | undefined): string {
    if (!a?.sources) return '';
    return Object.values(a.sources).join('\n');
}
