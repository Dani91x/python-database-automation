// ============================================================================
// Studio Ritardi — tipi, catalogo mercati (1:1 col file Excel) e accesso RPC.
// La matematica vive in Postgres (RPC get_market_delays, riproduzione fedele
// delle formule del foglio): il client riceve tutto pronto e si limita a
// renderizzare. Le stagioni per-lega arrivano dalla stessa RPC delle Frequenze.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
export { fetchLeagueSeasons, formatSeason, type LeagueSeason } from './marketFrequency';

// ---------- Tipi (specchiano l'output jsonb della RPC) ----------
export interface DelayMeta {
    league_id: number;
    market: string;
    target: string | null;
    mode: 'all' | 'last_n' | 'season';
    season_year: number | null;
    n_requested: number | null;
    n_scope: number;        // partite settlate nell'intervallo
    n_effective: number;    // eventi validi = righe DATI MATCH (denominatore)
    uses_ht: boolean;
    ht_coverage_pct: number | null;
    date_from: string | null;
    date_to: string | null;
}

export interface DelayStats {
    n_occ: number;
    frequency: number | null;        // % mercato
    media_storica: number | null;    // = quota oggettiva = "ogni Y partite"
    quota_oggettiva: number | null;
    ritardo_attuale: number;
    record: number;
    media_ritardi: number | null;
    sotto_media: number;
    sopra_media: number;
    sotto_media_pct: number | null;
    sopra_media_pct: number | null;
    rit_vs_media: number | null;     // ritardo attuale / media storica
    // valore di condizionamento dello storico (AZ13 = ultimo SUC): lo
    // storico_serie elenca cosa è uscito DOPO una serie di questa lunghezza.
    storico_cond_su?: number | null;
}

export interface SerieLen { len: number; occ_suc: number; cnt_rit: number }
export interface StoricoSerie { len: number; count: number; pct: number | null }
export interface RunSopraMedia { run_len: number; count: number; pct: number | null }
export interface DelayPoint {
    idx: number; fid: number; date: string;       // EVENTO
    home: string; away: string;                   // HOME / AWAY
    gc: number; ga: number;                        // GC / GA
    gcfh: number | null; gafh: number | null;      // GCFH / GAFH
    gcsh: number; gash: number;                    // GCSH / GASH (derivati)
    out: 0 | 1;                                    // W/L
    rit: number;                                   // RIT
    suc: number | null;                            // SUC (solo nelle righe-hit)
}

export interface DelayResult {
    meta: DelayMeta;
    stats: DelayStats;
    distribuzione_serie: SerieLen[];
    ultime_10_serie: number[];
    storico_serie: StoricoSerie[];
    run_sopra_media: RunSopraMedia[];
    // COLONNA BL: ultime 10 voci dello stream "strisce sopra media" (0 = serie
    // chiusa entro la media; N = striscia di N serie sopra media consecutive).
    // Opzionale per retro-compatibilità con RPC non ancora ridistribuita.
    ultime_10_strisce_sopra_media?: number[];
    series: DelayPoint[];
}

// ---------- Catalogo mercati: i 13 fogli del file STUDIO RITARDI ----------
// targetKind: che parametro richiede il mercato (come la cella di input C8).
export type TargetKind = 'none' | 'int' | 'line' | 'score';
export interface DelayMarketDef {
    id: string;
    label: string;
    sheet: string;              // nome foglio nel file Excel (per riferimento)
    group: 'ft' | 'ht';
    targetKind: TargetKind;
    targets?: string[];         // valori selezionabili (per int/line/score)
    defaultTarget?: string;
}

const exactScores = [
    '0-0', '1-0', '0-1', '1-1', '2-0', '0-2', '2-1', '1-2', '2-2',
    '3-0', '0-3', '3-1', '1-3', '3-2', '2-3', '3-3',
];

export const DELAY_MARKETS: DelayMarketDef[] = [
    { id: 're',    label: 'Risultato Esatto',          sheet: 'RIS.ESATTI', group: 'ft',
      targetKind: 'score', targets: exactScores, defaultTarget: '1-1' },
    { id: 'sge',   label: 'Somma Gol Esatta',          sheet: 'SGE', group: 'ft',
      targetKind: 'int', targets: ['0','1','2','3','4','5','6','7','8'], defaultTarget: '3' },
    { id: 'over',  label: 'Over',                       sheet: 'OVER', group: 'ft',
      targetKind: 'line', targets: ['0.5','1.5','2.5','3.5','4.5','5.5','6.5'], defaultTarget: '2.5' },
    { id: 'under', label: 'Under',                      sheet: 'UNDER', group: 'ft',
      targetKind: 'line', targets: ['0.5','1.5','2.5','3.5','4.5','5.5','6.5'], defaultTarget: '2.5' },
    { id: 'ovpt',  label: 'Over Primo Tempo',           sheet: 'OVPT', group: 'ht',
      targetKind: 'line', targets: ['0.5','1.5','2.5'], defaultTarget: '0.5' },
    { id: 'ggpt',  label: 'Gol Gol Primo Tempo',        sheet: 'GGPT', group: 'ht', targetKind: 'none' },
    { id: 'ggst',  label: 'Gol Gol Secondo Tempo',      sheet: 'GGST', group: 'ht', targetKind: 'none' },
    { id: 'pf1x',  label: 'Parziale/Finale 1-X',        sheet: 'PF1X', group: 'ht', targetKind: 'none' },
    { id: 'pf2x',  label: 'Parziale/Finale 2-X',        sheet: 'PF2X', group: 'ht', targetKind: 'none' },
    { id: 'pfx1',  label: 'Parziale/Finale X-1',        sheet: 'PFX1', group: 'ht', targetKind: 'none' },
    { id: 'pfx2',  label: 'Parziale/Finale X-2',        sheet: 'PFX2', group: 'ht', targetKind: 'none' },
    { id: 'x',     label: 'Pareggio (X)',               sheet: 'X', group: 'ft', targetKind: 'none' },
    { id: 'ggov25',label: 'GG & Over 2.5',              sheet: 'GG&OV25', group: 'ft', targetKind: 'none' },
];

export function targetLabel(m: DelayMarketDef, target: string | null): string {
    if (m.targetKind === 'none' || !target) return m.label;
    if (m.targetKind === 'score') return `${m.label} ${target}`;
    if (m.targetKind === 'int')   return `${m.label} = ${target}`;
    if (m.targetKind === 'line')  return `${m.label} ${target}`;
    return m.label;
}

// ---------- Chiamata RPC ----------
export interface DelayParams {
    leagueId: number;
    market: string;
    target?: string | null;
    mode: 'all' | 'last_n' | 'season';
    lastN?: number;
    seasonYear?: number | null;
}

export async function fetchMarketDelays(p: DelayParams): Promise<DelayResult> {
    const { data, error } = await supabase.rpc('get_market_delays', {
        p_league_id: p.leagueId,
        p_market: p.market,
        p_target: p.target ?? null,
        p_mode: p.mode,
        p_last_n: p.mode === 'last_n' ? (p.lastN ?? 500) : null,
        p_season_year: p.mode === 'season' ? (p.seasonYear ?? null) : null,
    });
    if (error) throw new Error(error.message);
    return data as DelayResult;
}
