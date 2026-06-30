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
