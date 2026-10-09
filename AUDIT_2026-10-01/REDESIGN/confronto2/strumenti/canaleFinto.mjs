// Tabellone finto sui canali locali 47331 (calcio) e 47332 (tennis), SOLO per le
// anteprime: stesse chiavi del push 'board' vero (BoardRow). Partite e quote del
// prototipo (prototipo/js/data.js), orari relativi all'orologio fisso 10:38 Roma.
// 09/10 (Programma del giorno): le chiavi del contratto
// AUDIT_2026-10-09/programma_del_giorno/CONTRATTO.md - per riga `score`,
// `fixture_id`, `bet_delay`, `updated_ms`; per selezione `back_size`/`lay_size`;
// nel push `market_types`; la richiesta `board_mercato` ({market_type}) ha
// risposta {ok:true} e da li' il push `board_mercato` del tipo chiesto, ogni 2 s.
// Allineato ai payload VERI del backend (esempio_payload_{calcio,tennis}.json del
// ramo backend): selezioni del Match Odds nell'ordine di Betfair (casa, ospite,
// «The Draw»), nomi dei tipi in italiano, `handicap: 0.0` nelle righe del mercato.
const ORA = Date.parse('2026-10-01T08:38:00Z');
const at = (min) => new Date(ORA + min * 60e3).toISOString();
// importo disponibile deterministico (niente Math.random: le anteprime si confrontano)
const disp = (prezzo, k, base) => Math.round((base / prezzo) * (1 + (k % 3) * 0.37));
const sel = (name, back, lay, k, base) => ({
  selection_id: 1000 + k, name, back, lay, ltp: null,
  back_size: disp(back, k, base), lay_size: disp(lay, k + 1, base * 0.6),
});
const riga = (id, name, min, inplay, matched, sels, extra = {}) => ({
  event_id: id, event_name: name, open_date: at(min), market_id: '1.25' + id.slice(-7), status: 'OPEN', inplay,
  total_matched: matched, selections: sels.map((s, k) => sel(s[0], s[1], s[2], k, matched / 400)),
  score: null, fixture_id: null, bet_delay: inplay ? 5 : null, updated_ms: ORA - 1500, ...extra,
});
const golCalcio = (minute, home, away, red_home = 0, red_away = 0, ht = false) =>
  ({ sport: 'calcio', minute, home, away, red_home, red_away, ht });
const puntiTennis = (sets, games, points, server) => ({ sport: 'tennis', sets, games, points, server });
export const CALCIO = [
  riga('34812001', 'Inter v Torino', -58, true, 1843210, [['Inter', 1.38, 1.39], ['Torino', 11.5, 12], ['The Draw', 5.6, 5.7]],
    { score: golCalcio(63, 2, 1, 0, 1), fixture_id: 1208891 }),
  riga('34812044', 'Real Betis v Getafe', -31, true, 512330, [['Real Betis', 2.02, 2.04], ['Getafe', 5.9, 6], ['The Draw', 3.25, 3.3]],
    { score: golCalcio(31, 0, 0), fixture_id: 1210044 }),
  riga('34812102', 'Bologna v Udinese', 14, false, 284100, [['Bologna', 1.83, 1.84], ['Udinese', 4.9, 5], ['The Draw', 3.7, 3.75]],
    { fixture_id: 1208902 }),
  riga('34812130', 'Brentford v Fulham', 44, false, 402770, [['Brentford', 2.3, 2.32], ['Fulham', 3.3, 3.35], ['The Draw', 3.45, 3.5]],
    { fixture_id: 1199130 }),
  riga('34812177', 'Lens v Nantes', 74, false, 98640, [['Lens', 1.71, 1.72], ['Nantes', 5.5, 5.6], ['The Draw', 3.9, 3.95]]),
  riga('34812190', 'Atalanta v Genoa', 104, false, 211480, [['Atalanta', 1.52, 1.53], ['Genoa', 7, 7.2], ['The Draw', 4.6, 4.7]],
    { fixture_id: 1208911 }),
  riga('34812215', 'Feyenoord v AZ Alkmaar', 134, false, 77310, [['Feyenoord', 1.95, 1.97], ['AZ Alkmaar', 3.85, 3.9], ['The Draw', 3.8, 3.85]]),
  riga('34812240', 'Benfica v Braga', 194, false, 165900, [['Benfica', 1.62, 1.63], ['Braga', 5.6, 5.7], ['The Draw', 4.1, 4.2]],
    { fixture_id: 1205240 }),
  riga('34812262', 'Napoli v Lazio', 254, false, 690420, [['Napoli', 1.91, 1.92], ['Lazio', 4.4, 4.5], ['The Draw', 3.55, 3.6]],
    { fixture_id: 1208962 }),
];
export const TENNIS = [
  riga('34813501', 'Sinner v Draper', -42, true, 2210450, [['J. Sinner', 1.24, 1.25], ['J. Draper', 5.0, 5.1]],
    { score: puntiTennis({ p1: 1, p2: 0 }, { p1: 3, p2: 2 }, { p1: '30', p2: '15' }, 'p2') }),
  riga('34813522', 'Swiatek v Paolini', -12, true, 803120, [['I. Swiatek', 1.46, 1.47], ['J. Paolini', 3.1, 3.15]],
    { score: puntiTennis({ p1: 0, p2: 0 }, { p1: 5, p2: 4 }, { p1: '40', p2: 'AD' }, 'p1') }),
  riga('34813540', 'Musetti v Fritz', 28, false, 341800, [['L. Musetti', 2.36, 2.4], ['T. Fritz', 1.7, 1.72]]),
  riga('34813561', 'Cobolli v Shelton', 65, false, 121300, [['F. Cobolli', 2.5, 2.54], ['B. Shelton', 1.64, 1.66]]),
  riga('34813580', 'Gauff v Andreeva', 120, false, 289770, [['C. Gauff', 1.88, 1.9], ['M. Andreeva', 2.06, 2.08]]),
  riga('34813601', 'Arnaldi v Etcheverry', 180, false, 22410, [['M. Arnaldi', 1.95, 1.98], ['T. Etcheverry', 1.99, 2.04]]),
];
// contratto §2: MATCH_ODDS primo; sul calcio nessun correct score
const TIPI = {
  calcio: [
    { market_type: 'MATCH_ODDS', name: 'Esito finale (1X2)', count: CALCIO.length },
    { market_type: 'OVER_UNDER_15', name: 'Under/Over 1.5 gol', count: CALCIO.length },
    { market_type: 'OVER_UNDER_25', name: 'Under/Over 2.5 gol', count: CALCIO.length },
    { market_type: 'OVER_UNDER_35', name: 'Under/Over 3.5 gol', count: CALCIO.length - 2 },
    { market_type: 'FIRST_HALF_GOALS_05', name: 'Under/Over 0.5 gol primo tempo', count: CALCIO.length - 1 },
    { market_type: 'BOTH_TEAMS_TO_SCORE', name: 'Goal / No goal', count: CALCIO.length },
    { market_type: 'DOUBLE_CHANCE', name: 'Doppia chance', count: CALCIO.length - 3 },
    { market_type: 'ASIAN_HANDICAP', name: 'Handicap asiatico', count: 4 },
  ],
  tennis: [
    { market_type: 'MATCH_ODDS', name: 'Vincente incontro', count: TENNIS.length },
    { market_type: 'SET_BETTING', name: 'Risultato in set', count: TENNIS.length },
    { market_type: 'SET_WINNER', name: 'Vincente primo set', count: TENNIS.length - 1 },
  ],
};
const payloadBoard = (sport) => ({ rows: sport === 'calcio' ? CALCIO : TENNIS, market_types: TIPI[sport] });

// le righe di `board_mercato` (contratto §3) per il tipo chiesto: una per evento
// che ha quel tipo (ASIAN_HANDICAP: due linee, una riga per mercato)
const nomiDi = (r) => r.event_name.split(' v ');
function selezioniDi(tipo, r, k) {
  const [a, b] = nomiDi(r);
  const s = (selection_id, name, back, lay, handicap = 0.0) => ({
    selection_id, name, handicap, back, lay, ltp: back,
    back_size: disp(back, selection_id, r.total_matched / 900), lay_size: disp(lay, selection_id + 1, r.total_matched / 1400),
  });
  const q = (x) => Math.round(x * 100) / 100;
  if (tipo.startsWith('OVER_UNDER') || tipo.startsWith('FIRST_HALF_GOALS')) {
    const linea = tipo.replace(/^.*_(\d)(\d)$/, '$1.$2');
    const u = q(1.6 + (k % 4) * 0.22);
    return [s(47972 + k, `Under ${linea} Goals`, u, q(u + 0.02)), s(47973 + k, `Over ${linea} Goals`, q(u / (u - 1)), q(u / (u - 1) + 0.03))];
  }
  if (tipo === 'BOTH_TEAMS_TO_SCORE') return [s(30246, 'Yes', q(1.72 + k * 0.04), q(1.74 + k * 0.04)), s(110503, 'No', q(2.2 - k * 0.03), q(2.24 - k * 0.03))];
  if (tipo === 'DOUBLE_CHANCE') return [s(6342396, 'Home or Draw', 1.21, 1.22), s(6342397, 'Draw or Away', 2.5, 2.54), s(6342398, 'Home or Away', 1.28, 1.29)];
  if (tipo === 'SET_BETTING') return [s(1, '2 - 0', 2.1, 2.14), s(2, '2 - 1', 3.9, 4), s(3, '1 - 2', 6.4, 6.6), s(4, '0 - 2', 8.2, 8.6)];
  return [s(11 + k, a, q(1.5 + k * 0.1), q(1.52 + k * 0.1)), s(12 + k, b, q(2.6 - k * 0.08), q(2.64 - k * 0.08))];
}
// i market_name delle righe sono quelli di Betfair (inglesi), come nel payload vero
const NOMI_BETFAIR = {
  OVER_UNDER_15: 'Over/Under 1.5 Goals', OVER_UNDER_25: 'Over/Under 2.5 Goals', OVER_UNDER_35: 'Over/Under 3.5 Goals',
  FIRST_HALF_GOALS_05: 'First Half Goals 0.5', BOTH_TEAMS_TO_SCORE: 'Both teams to Score?', DOUBLE_CHANCE: 'Double Chance',
  ASIAN_HANDICAP: 'Asian Handicap', SET_BETTING: 'Set Betting', SET_WINNER: 'Set 1 Winner',
};
function righeMercato(sport, tipo) {
  const base = sport === 'calcio' ? CALCIO : TENNIS;
  const conto = TIPI[sport].find((t) => t.market_type === tipo)?.count ?? 0;
  const out = [];
  base.slice(0, conto).forEach((r, k) => {
    const linee = tipo === 'ASIAN_HANDICAP' ? [-0.5, -1.5] : [null];
    linee.forEach((h, j) => {
      const nome = NOMI_BETFAIR[tipo] ?? tipo;
      const sels = selezioniDi(tipo, r, k + j).map((x, i) => (h == null ? x : { ...x, handicap: i === 0 ? h : -h }));
      out.push({
        event_id: r.event_id, market_id: `1.26${r.event_id.slice(-6)}${j}`, market_name: h == null ? nome : `${nome} ${h}`,
        status: 'OPEN', inplay: r.inplay, total_matched: Math.round(r.total_matched * (0.18 - j * 0.07)), selections: sels,
      });
    });
  });
  return out;
}
// modo_ordini.stato_corrente() (calcio) / stato_tennis() (tennis) + ts, come nell'hello vero
const modoOrdini = (sport) => (sport === 'calcio'
  ? { effettivo: 'PAPER', tetto_ambiente: 'LIVE', scelto_ui: 'PAPER', motivo: 'ok', scelto_ui_at: at(-120),
      scelto_ui_da: 'avvio_app', eta_lettura_s: 0.4, kill_switch: false, kill_switch_env: false, kill_switch_letto: true, ts: ORA - 60_000 }
  : { effettivo: 'PAPER', tetto_ambiente: 'PAPER', scelto_ui: null, motivo: 'ok', sport: 'tennis',
      scelto_ui_at: null, scelto_ui_da: null, eta_lettura_s: 0.7, ts: ORA - 60_000 });
const helloDi = (sport) => ({ sport, mode: sport === 'calcio' ? 'LIVE' : 'PAPER', modo_ordini: modoOrdini(sport) });

/** risposta alle richieste del Programma del giorno; true = gestita qui */
function richiestaBoard(sport, m, manda, stato) {
  if (m.m !== 'board_mercato') return false;
  const tipo = String(m.p?.market_type ?? '');
  if (!TIPI[sport].some((t) => t.market_type === tipo) || tipo === 'MATCH_ODDS') {
    manda({ id: m.id, ok: false, e: `tipo di mercato non servito: ${tipo}` });
    return true;
  }
  manda({ id: m.id, ok: true, d: {} });
  stato.tipo = tipo;
  const giro = () => manda({ t: 'board_mercato', d: { market_type: stato.tipo, rows: righeMercato(sport, stato.tipo), updated_ms: Date.now() } });
  if (stato.timer) clearInterval(stato.timer);
  setTimeout(giro, 150);
  stato.timer = setInterval(giro, 2000);
  return true;
}
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

function canaleSeguiLive(ws, D, statoBoard) {
  const manda = (o) => { try { ws.send(JSON.stringify(o)); } catch { /* route chiusa */ } };
  const giro = () => {
    for (const ev of [D.EV.inter, D.EV.betis]) manda({ t: 'now', d: D.liveNowDi(ev, D.MS_CANALE) });
    for (const mid of D.MERCATI_CON_LADDER) {
      const { updated_at: _scarta, ...riga } = D.ladderDi(mid, D.MS_CANALE);   // il push non porta updated_at
      manda({ t: 'ladder', d: riga });
    }
  };
  // primo giro subito, poi ogni 1,5 s (sotto i 4 s di "canale muto" della sorgente ladder)
  setTimeout(giro, 200);
  // un solo onClose per route (lo registra instradaCanali): il timer si consegna li'
  statoBoard.timerSL = setInterval(giro, 1500);
  ws.onMessage((testo) => {
    let m;
    try { m = JSON.parse(String(testo)); } catch { return; }
    if (typeof m?.id !== 'number') return;
    if (richiestaBoard('calcio', m, manda, statoBoard)) return;
    if (m.m === 'snapshot') {
      const mid = String(m.p?.market_id ?? '');
      manda({ id: m.id, ok: true, d: { orders: D.ORDINI[mid] ?? [], positions: D.POSIZIONI[mid] ?? [] } });
    } else {
      // anteprima: nessun comando viene eseguito (esito applicativo negativo, mai un silenzio)
      manda({ id: m.id, ok: false, e: 'anteprima: canale finto, nessun comando eseguito' });
    }
  });
}

// Tennis (/tennis/terminal): sul 47332 il runner tennis manda alla connessione
//   hello {sport, mode}   (local_channel.py + tennis_runner.py: set_hello(mode=live_order_mode()))
// e risponde alle richieste. NON si mandano 'ladder'/'now': sono i segni di vita
// della sorgente ladder (localTransport TOPIC_VITA) e spegnerebbero il realtime
// DB del finto (frontend/src/anteprima/tennisFinto.ts), che porta la storia del
// book per Chart e Depth. Il chip "LOCALE" della ladder resta acceso (connesso).
function canaleSemplice(ws, sport, statoBoard) {
  const manda = (o) => { try { ws.send(JSON.stringify(o)); } catch { /* route chiusa */ } };
  ws.onMessage((testo) => {
    let m;
    try { m = JSON.parse(String(testo)); } catch { return; }
    if (typeof m?.id !== 'number') return;
    if (richiestaBoard(sport, m, manda, statoBoard)) return;
    // anteprima: nessun comando viene eseguito (esito applicativo negativo, mai un silenzio)
    manda({ id: m.id, ok: false, e: 'anteprima: canale finto, nessun comando eseguito' });
  });
}

export async function instradaCanali(ctx) {
  const datiSL = await caricaDatiSeguiLive();
  await ctx.routeWebSocket(/:4733[12]/, (ws) => {
    const sport = ws.url().includes('47331') ? 'calcio' : 'tennis';
    const statoBoard = { tipo: null, timer: null, timerSL: null };
    ws.onClose(() => {
      if (statoBoard.timer) clearInterval(statoBoard.timer);
      if (statoBoard.timerSL) clearInterval(statoBoard.timerSL);
    });
    // hello come il runner: sport, tetto (`mode`) e il modo ordini applicato (`modo_ordini`)
    setTimeout(() => ws.send(JSON.stringify({ t: 'hello', d: helloDi(sport) })), 50);
    setTimeout(() => ws.send(JSON.stringify({ t: 'board', d: payloadBoard(sport) })), 300);
    if (sport === 'calcio' && datiSL) canaleSeguiLive(ws, datiSL, statoBoard);
    else canaleSemplice(ws, sport, statoBoard);
  });
}
