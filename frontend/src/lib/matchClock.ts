// ============================================================================
// matchClock.ts — countdown all'off, minuto di gioco e score (roadmap D32).
// Matematica PURA: nessun I/O, nessun timer. Il componente passa nowMs e i dati
// del match; qui solo formattazione. null = dato assente: la UI mostra "—",
// MAI un valore inventato.
// ============================================================================

const pad2 = (n: number): string => String(n).padStart(2, '0');

// Countdown all'off (open_date ISO). null se openDate mancante/invalida o già
// passata (nowMs >= off). Formato: >=24h → "2g 03h"; >=1h → "H:MM:SS"; <1h → "MM:SS".
export function countdownToOff(openDate: string | null | undefined, nowMs: number): string | null {
    if (!openDate || !Number.isFinite(nowMs)) return null;
    const off = Date.parse(openDate);
    if (!Number.isFinite(off)) return null;
    if (nowMs >= off) return null; // esattamente all'off (o oltre) → niente countdown
    const totSec = Math.floor((off - nowMs) / 1000);
    const days = Math.floor(totSec / 86_400);
    const hours = Math.floor((totSec % 86_400) / 3600);
    const mins = Math.floor((totSec % 3600) / 60);
    const secs = totSec % 60;
    if (days >= 1) return `${days}g ${pad2(hours)}h`;
    if (hours >= 1) return `${hours}:${pad2(mins)}:${pad2(secs)}`;
    return `${pad2(mins)}:${pad2(secs)}`;
}

// Minuto di gioco: "63'". null se minute null/undefined, non finito o negativo.
// 0 è un minuto valido ("0'": calcio d'inizio).
export function formatMinute(minute: number | null | undefined): string | null {
    if (minute == null || !Number.isFinite(minute) || minute < 0) return null;
    return `${Math.floor(minute)}'`;
}

// Score "1–2" (en dash U+2013). null se uno dei due punteggi è null/undefined
// o non finito. 0 è un punteggio valido (0–0 mostrato, non "—").
export function formatScore(home: number | null | undefined, away: number | null | undefined): string | null {
    if (home == null || away == null) return null;
    if (!Number.isFinite(home) || !Number.isFinite(away)) return null;
    return `${home}–${away}`;
}
