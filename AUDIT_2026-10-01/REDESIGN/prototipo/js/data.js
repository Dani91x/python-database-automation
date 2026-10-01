/* data.js - DATI FINTI realistici. Nessun dato e' letto dal DB o dal conto. */
(function () {
  'use strict';
  var now = Date.now();
  function at(minFromNow) { return new Date(now + minFromNow * 60000).toISOString(); }
  var D = window.D = {};

  D.runner = { calcio: true, tennis: true };
  D.channels = [
    { name: 'Runner calcio', port: 47331, on: true },
    { name: 'Runner tennis', port: 47332, on: true },
    { name: 'Mike', port: 47333, on: true },
    { name: 'Omega', port: 47334, on: true },
    { name: 'Safe', port: 47335, on: true },
    { name: 'Scanner', port: 47336, on: true },
    { name: 'Bot tennis (4)', port: 47337, on: true },
    { name: 'Scalper calcio', port: 47338, on: false }
  ];
  /* modalita' per bot: la cambia solo l'utente, dentro il bot */
  D.botMode = {
    omega: { name: 'Omega', route: 'omega', mode: 'PAPER', running: true },
    safe: { name: 'Safe Strategy', route: 'safe-strategy', mode: 'PAPER', running: true },
    mike: { name: 'Mike', route: 'mike', mode: 'LIVE', running: true },
    scalper: { name: 'Scalper calcio', route: 'segui-live', mode: 'PAPER', running: false },
    tbot: { name: 'Bot tennis', route: 'tennis-bot', mode: 'PAPER', running: true }
  };
  D.liveCount = function () { var n = 0; for (var k in D.botMode) if (D.botMode[k].mode === 'LIVE') n++; return n; };
  D.paperCount = function () { var n = 0; for (var k in D.botMode) if (D.botMode[k].mode !== 'LIVE') n++; return n; };

  D.conto = { disponibile: 1842.37, esposizione: 96.40, pnlOggi: 23.85, pnlOggiProva: 41.20, rischioBotLive: 96.40, scarto: 0 };

  /* Programma di oggi: forma del push 'board' (BoardRow) */
  function sel(n, b, l) { return { name: n, back: b, lay: l }; }
  D.boardCalcio = [
    { id: '34812001', name: 'Inter v Torino', open: at(-58), inplay: true, status: 'OPEN', matched: 1843210, sels: [sel('Inter', 1.38, 1.39), sel('Pareggio', 5.6, 5.7), sel('Torino', 11.5, 12)], score: '1-0', min: "58'" },
    { id: '34812044', name: 'Real Betis v Getafe', open: at(-31), inplay: true, status: 'OPEN', matched: 512330, sels: [sel('Real Betis', 2.02, 2.04), sel('Pareggio', 3.25, 3.3), sel('Getafe', 5.9, 6)], score: '0-0', min: "31'" },
    { id: '34812102', name: 'Bologna v Udinese', open: at(14), inplay: false, status: 'OPEN', matched: 284100, sels: [sel('Bologna', 1.83, 1.84), sel('Pareggio', 3.7, 3.75), sel('Udinese', 4.9, 5)] },
    { id: '34812130', name: 'Brentford v Fulham', open: at(44), inplay: false, status: 'OPEN', matched: 402770, sels: [sel('Brentford', 2.3, 2.32), sel('Pareggio', 3.45, 3.5), sel('Fulham', 3.3, 3.35)] },
    { id: '34812177', name: 'Lens v Nantes', open: at(74), inplay: false, status: 'OPEN', matched: 98640, sels: [sel('Lens', 1.71, 1.72), sel('Pareggio', 3.9, 3.95), sel('Nantes', 5.5, 5.6)] },
    { id: '34812190', name: 'Atalanta v Genoa', open: at(104), inplay: false, status: 'OPEN', matched: 211480, sels: [sel('Atalanta', 1.52, 1.53), sel('Pareggio', 4.6, 4.7), sel('Genoa', 7, 7.2)] },
    { id: '34812215', name: 'Feyenoord v AZ Alkmaar', open: at(134), inplay: false, status: 'OPEN', matched: 77310, sels: [sel('Feyenoord', 1.95, 1.97), sel('Pareggio', 3.8, 3.85), sel('AZ Alkmaar', 3.85, 3.9)] },
    { id: '34812240', name: 'Benfica v Braga', open: at(194), inplay: false, status: 'OPEN', matched: 165900, sels: [sel('Benfica', 1.62, 1.63), sel('Pareggio', 4.1, 4.2), sel('Braga', 5.6, 5.7)] },
    { id: '34812262', name: 'Napoli v Lazio', open: at(254), inplay: false, status: 'OPEN', matched: 690420, sels: [sel('Napoli', 1.91, 1.92), sel('Pareggio', 3.55, 3.6), sel('Lazio', 4.4, 4.5)] }
  ];
  D.boardTennis = [
    { id: '34813501', name: 'Sinner v Draper', open: at(-42), inplay: true, status: 'OPEN', matched: 2210450, sels: [sel('J. Sinner', 1.24, 1.25), sel('J. Draper', 5.0, 5.1)], score: '6-4 2-1', torneo: 'ATP Pechino' },
    { id: '34813522', name: 'Swiatek v Paolini', open: at(-12), inplay: true, status: 'OPEN', matched: 803120, sels: [sel('I. Swiatek', 1.46, 1.47), sel('J. Paolini', 3.1, 3.15)], score: '3-3', torneo: 'WTA Pechino' },
    { id: '34813540', name: 'Musetti v Fritz', open: at(28), inplay: false, status: 'OPEN', matched: 341800, sels: [sel('L. Musetti', 2.36, 2.4), sel('T. Fritz', 1.7, 1.72)], torneo: 'ATP Pechino' },
    { id: '34813561', name: 'Cobolli v Shelton', open: at(65), inplay: false, status: 'OPEN', matched: 121300, sels: [sel('F. Cobolli', 2.5, 2.54), sel('B. Shelton', 1.64, 1.66)], torneo: 'ATP Tokyo' },
    { id: '34813580', name: 'Gauff v Andreeva', open: at(120), inplay: false, status: 'OPEN', matched: 289770, sels: [sel('C. Gauff', 1.88, 1.9), sel('M. Andreeva', 2.06, 2.08)], torneo: 'WTA Pechino' },
    { id: '34813601', name: 'Arnaldi v Etcheverry', open: at(180), inplay: false, status: 'OPEN', matched: 22410, sels: [sel('M. Arnaldi', 1.95, 1.98), sel('T. Etcheverry', 1.99, 2.04)], torneo: 'Challenger Orleans' }
  ];
  D.countdown = function (iso) {
    var s = Math.round((Date.parse(iso) - Date.now()) / 1000); if (s <= 0) return null;
    var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), ss = s % 60;
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return h ? h + ':' + p(m) + ':' + p(ss) : p(m) + ':' + p(ss);
  };
  D.hhmm = function (iso) { return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }); };

  /* ladder finta attorno a un prezzo */
  var TICKS = [];
  (function () { var p = 1.01; while (p < 20) { TICKS.push(Math.round(p * 100) / 100); p += p < 2 ? 0.01 : p < 3 ? 0.02 : p < 4 ? 0.05 : p < 6 ? 0.1 : p < 10 ? 0.2 : 0.5; } })();
  D.ladder = function (ltp, rows, seed) {
    rows = rows || 15; seed = seed || 7;
    var i = TICKS.findIndex(function (t) { return t >= ltp; }), out = [];
    function rnd(k) { var x = Math.sin(k * 999 + seed) * 10000; return x - Math.floor(x); }
    for (var k = i + Math.floor(rows / 2); k > i - Math.ceil(rows / 2); k--) {
      var p = TICKS[k]; if (!p) continue;
      var lay = p > ltp ? Math.round(20 + rnd(k) * 900) : 0, back = p < ltp ? Math.round(20 + rnd(k + 3) * 900) : 0;
      if (p === TICKS[i]) { back = Math.round(150 + rnd(k) * 400); }
      out.push({ p: p, back: p <= ltp ? back : 0, lay: p > ltp ? lay : 0, traded: Math.round(rnd(k + 9) * 4000), ltp: p === TICKS[i] });
    }
    return out;
  };
})();
