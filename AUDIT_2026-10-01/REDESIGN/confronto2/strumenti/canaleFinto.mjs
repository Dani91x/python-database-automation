// Tabellone finto sui canali locali 47331 (calcio) e 47332 (tennis), SOLO per le
// anteprime: stesse chiavi del push 'board' vero (BoardRow). Partite e quote del
// prototipo (prototipo/js/data.js), orari relativi all'orologio fisso 10:38 Roma.
const ORA = Date.parse('2026-10-01T08:38:00Z');
const at = (min) => new Date(ORA + min * 60e3).toISOString();
const sel = (name, back, lay, k) => ({ selection_id: 1000 + k, name, back, lay, ltp: null });
const riga = (id, name, min, inplay, matched, sels) => ({
  event_id: id, event_name: name, open_date: at(min), market_id: '1.25' + id.slice(-7), status: 'OPEN', inplay,
  total_matched: matched, selections: sels.map((s, k) => sel(s[0], s[1], s[2], k)),
});
export const CALCIO = [
  riga('34812001', 'Inter v Torino', -58, true, 1843210, [['Inter', 1.38, 1.39], ['Pareggio', 5.6, 5.7], ['Torino', 11.5, 12]]),
  riga('34812044', 'Real Betis v Getafe', -31, true, 512330, [['Real Betis', 2.02, 2.04], ['Pareggio', 3.25, 3.3], ['Getafe', 5.9, 6]]),
  riga('34812102', 'Bologna v Udinese', 14, false, 284100, [['Bologna', 1.83, 1.84], ['Pareggio', 3.7, 3.75], ['Udinese', 4.9, 5]]),
  riga('34812130', 'Brentford v Fulham', 44, false, 402770, [['Brentford', 2.3, 2.32], ['Pareggio', 3.45, 3.5], ['Fulham', 3.3, 3.35]]),
  riga('34812177', 'Lens v Nantes', 74, false, 98640, [['Lens', 1.71, 1.72], ['Pareggio', 3.9, 3.95], ['Nantes', 5.5, 5.6]]),
  riga('34812190', 'Atalanta v Genoa', 104, false, 211480, [['Atalanta', 1.52, 1.53], ['Pareggio', 4.6, 4.7], ['Genoa', 7, 7.2]]),
  riga('34812215', 'Feyenoord v AZ Alkmaar', 134, false, 77310, [['Feyenoord', 1.95, 1.97], ['Pareggio', 3.8, 3.85], ['AZ Alkmaar', 3.85, 3.9]]),
  riga('34812240', 'Benfica v Braga', 194, false, 165900, [['Benfica', 1.62, 1.63], ['Pareggio', 4.1, 4.2], ['Braga', 5.6, 5.7]]),
  riga('34812262', 'Napoli v Lazio', 254, false, 690420, [['Napoli', 1.91, 1.92], ['Pareggio', 3.55, 3.6], ['Lazio', 4.4, 4.5]]),
];
export const TENNIS = [
  riga('34813501', 'Sinner v Draper', -42, true, 2210450, [['J. Sinner', 1.24, 1.25], ['J. Draper', 5.0, 5.1]]),
  riga('34813522', 'Swiatek v Paolini', -12, true, 803120, [['I. Swiatek', 1.46, 1.47], ['J. Paolini', 3.1, 3.15]]),
  riga('34813540', 'Musetti v Fritz', 28, false, 341800, [['L. Musetti', 2.36, 2.4], ['T. Fritz', 1.7, 1.72]]),
  riga('34813561', 'Cobolli v Shelton', 65, false, 121300, [['F. Cobolli', 2.5, 2.54], ['B. Shelton', 1.64, 1.66]]),
  riga('34813580', 'Gauff v Andreeva', 120, false, 289770, [['C. Gauff', 1.88, 1.9], ['M. Andreeva', 2.06, 2.08]]),
  riga('34813601', 'Arnaldi v Etcheverry', 180, false, 22410, [['M. Arnaldi', 1.95, 1.98], ['T. Etcheverry', 1.99, 2.04]]),
];
// Segui live (/segui-live): il canale calcio porta anche i topic che il terminal
// ascolta, con le STESSE chiavi dei push veri del runner (Betfair/stream):
//   hello    {sport}                                    (local_channel.py, alla connessione)
//   now      riga live_now                              (db.update_live_now -> _lpub("now", row))
//   ladder   {event_id, market_id, market_type, market_name, status, ladder}  (runner.py ladder-worker)
//   risposta a 'snapshot' {id, ok, d: {orders, positions}}  (live_order_worker._local_snapshot)
// Le righe NON sono ricopiate qui: si chiedono al server Vite dell'anteprima
// (frontend/src/anteprima/seguiLiveDati.ts, solo `import type`: il JS servito
// non ha dipendenze), cosi' canale e finti del database dicono la stessa cosa.
// Il canale e' piu' fresco del database di 2 s (MS_CANALE > MS_DB): vince lui.
async function caricaDatiSeguiLive() {
  const porta = Number(process.env.PORTA || 5198);
  try {
    const r = await fetch(`http://127.0.0.1:${porta}/src/anteprima/seguiLiveDati.ts`);
    if (!r.ok) return null;
    const js = await r.text();
    return await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
  } catch {
    return null;   // server spento o file assente: il canale resta quello di prima (solo 'board')
  }
}

function canaleSeguiLive(ws, D) {
  const manda = (o) => { try { ws.send(JSON.stringify(o)); } catch { /* route chiusa */ } };
  setTimeout(() => manda({ t: 'hello', d: { sport: 'calcio' } }), 50);
  const giro = () => {
    for (const ev of [D.EV.inter, D.EV.betis]) manda({ t: 'now', d: D.liveNowDi(ev, D.MS_CANALE) });
    for (const mid of D.MERCATI_CON_LADDER) {
      const { updated_at: _scarta, ...riga } = D.ladderDi(mid, D.MS_CANALE);   // il push non porta updated_at
      manda({ t: 'ladder', d: riga });
    }
  };
  // primo giro subito, poi ogni 1,5 s (sotto i 4 s di "canale muto" della sorgente ladder)
  setTimeout(giro, 200);
  const t = setInterval(giro, 1500);
  ws.onClose(() => clearInterval(t));
  ws.onMessage((testo) => {
    let m;
    try { m = JSON.parse(String(testo)); } catch { return; }
    if (typeof m?.id !== 'number') return;
    if (m.m === 'snapshot') {
      const mid = String(m.p?.market_id ?? '');
      manda({ id: m.id, ok: true, d: { orders: D.ORDINI[mid] ?? [], positions: D.POSIZIONI[mid] ?? [] } });
    } else {
      // anteprima: nessun comando viene eseguito (esito applicativo negativo, mai un silenzio)
      manda({ id: m.id, ok: false, e: 'anteprima: canale finto, nessun comando eseguito' });
    }
  });
}

export async function instradaCanali(ctx) {
  const datiSL = await caricaDatiSeguiLive();
  await ctx.routeWebSocket(/:4733[12]/, (ws) => {
    const sport = ws.url().includes('47331') ? 'calcio' : 'tennis';
    setTimeout(() => ws.send(JSON.stringify({ t: 'board', d: { rows: sport === 'calcio' ? CALCIO : TENNIS } })), 300);
    if (sport === 'calcio' && datiSL) canaleSeguiLive(ws, datiSL);
  });
}
