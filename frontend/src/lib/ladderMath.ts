// ============================================================================
// ladderMath.ts — matematica PURA del ladder (display), testabile a unità.
// Nessun I/O, nessun React: solo aritmetica condivisa da LadderView.
// ============================================================================

// P&L "what-if" bloccato chiudendo l'INTERA posizione (green-up) a `price`:
//   locked = L + (W − L)/price     con W = profit se vince, L = profit se perde.
// Vale identico chiudendo con BACK o con LAY (formula di hedge standard di settore,
// stessa del backend trading/greenup.py). price<=1 → non chiudibile → ritorna L.
export function lockedPnlAt(price: number, win: number, lose: number): number {
    if (!Number.isFinite(price) || price <= 1) return lose;
    return lose + (win - lose) / price;
}

// PIQ (Position In Queue) — denaro davanti a te, APPROSSIMATO, al prezzo del tuo ordine.
// Un ordine NON abbinato risiede sul lato OPPOSTO del book (un tuo BACK è "disponibile al
// LAY" per gli altri; un tuo LAY è "disponibile al BACK"). La size disponibile a quel
// livello include il tuo ordine: la coda altrui ≈ disponibile_a_quel_livello − tua_size.
// È la stima live mostrata dai ladder pro (Geeks Toy): non è la posizione esatta in coda
// (Betfair non la espone) ma scende mentre il livello viene tradato. >0 solo se hai un
// ordine non abbinato a quel prezzo; restingAvail è layAvail per un BACK, backAvail per un LAY.
export function piqAhead(mySize: number, restingAvail: number): number {
    if (!Number.isFinite(mySize) || mySize <= 0) return 0;
    const ahead = (Number.isFinite(restingAvail) ? restingAvail : 0) - mySize;
    return ahead > 0 ? ahead : 0;
}

// Finestra di al più `maxRows` elementi da una lista ASCENDENTE di prezzi, centrata sul
// prezzo più vicino a `center`. Ai bordi la finestra viene CLAMPATA (mai meno di maxRows
// righe quando la lista ne ha abbastanza): è il comportamento dei ladder pro, dove il
// centro "scivola" quando si naviga vicino a 1.01 o al massimo del range.
export function windowAround(asc: number[], center: number, maxRows: number): number[] {
    if (!Array.isArray(asc) || asc.length === 0) return [];
    if (!(maxRows > 0)) return [];
    if (asc.length <= maxRows) return asc.slice();
    const c = Number.isFinite(center) ? center : asc[Math.floor(asc.length / 2)];
    let bestI = 0;
    let bestD = Infinity;
    for (let i = 0; i < asc.length; i++) {
        const d = Math.abs(asc[i] - c);
        if (d < bestD) { bestD = d; bestI = i; }
    }
    let start = bestI - Math.floor(maxRows / 2);
    start = Math.max(0, Math.min(start, asc.length - maxRows));
    return asc.slice(start, start + maxRows);
}

// Direzione del flash di una cella quando il valore cambia tra due update del book:
// 'up' (verde, denaro in aumento), 'down' (rosso, in calo), null (invariato/appena nato).
// Sotto EPS di 0.5€ il rumore di arrotondamento non produce flash.
const FLASH_EPS = 0.5;
export function flashDir(prev: number | undefined, curr: number): 'up' | 'down' | null {
    if (prev == null || !Number.isFinite(prev) || !Number.isFinite(curr)) return null;
    const d = curr - prev;
    if (d > FLASH_EPS) return 'up';
    if (d < -FLASH_EPS) return 'down';
    return null;
}

// Step dello stake da hotkey (+/−): passo 0,50€, MAI sotto il minimo (0,50€),
// arrotondato ai 2 decimali (denaro).
export const STAKE_STEP = 0.5;
export const STAKE_MIN = 0.5;
export function stepStake(current: number, dir: 1 | -1, step = STAKE_STEP, min = STAKE_MIN): number {
    const cur = Number.isFinite(current) && current > 0 ? current : min;
    const next = cur + dir * step;
    return Math.round(Math.max(min, next) * 100) / 100;
}

// Prossimo preset di stake (ciclico). Se lo stake corrente non è un preset,
// riparte dal primo. Lista vuota → stake invariato.
export function nextPreset(presets: readonly number[], current: number): number {
    if (!presets.length) return current;
    const i = presets.findIndex(p => Math.abs(p - current) < 1e-9);
    return presets[(i + 1) % presets.length];
}
