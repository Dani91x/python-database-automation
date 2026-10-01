/* trading.js - componenti condivisi delle pagine di trading (components/trading/*),
   ridisegnati: BotHeader, ModeBanner, DayBar, KpiRow, DailyCalendar, DayDetail,
   BarreGiornaliere, EquityCurve, PerformancePanel, EventPnlTable, TradingHistory, StoricoLink. */
(function () {
  'use strict';
  var S = window.S, D = window.D;
  var C = S.C = {};

  /* ---------- dati finti per giornata (deterministici) ---------- */
  function rnd(k) { var x = Math.sin(k * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); }
  D.giorni = function (bot, mode, n) {
    n = n || 30; var out = [], base = String(bot).split('').reduce(function (a, c) { return a + c.charCodeAt(0); }, 0) % 97 + 1, m = mode === 'live' ? 0.55 : 1;
    for (var i = n - 1; i >= 0; i--) {
      var dt = new Date(2026, 9, 1 - i);
      var k = base * 100 + i + (mode === 'live' ? 50 : 0);
      if (rnd(k + 0.3) < 0.18) continue; // giornate senza operazioni: non diventano zero
      var trades = 1 + Math.floor(rnd(k + 1) * 9);
      var pnl = Math.round(((rnd(k + 2) - 0.38) * 46 * m) * 100) / 100;
      var v = Math.max(0, Math.round(trades * (pnl > 0 ? 0.7 : 0.35))), p = trades - v;
      out.push({ iso: dt.toISOString().slice(0, 10), date: dt, pnl: pnl, n: trades, v: v, p: p, omega: Math.round(pnl * 0.4 * 100) / 100, safe: Math.round(pnl * 0.25 * 100) / 100, mike: Math.round(pnl * 0.35 * 100) / 100, goal: rnd(k + 5) > 0.45 });
    }
    return out;
  };
  var GG = ['dom', 'lun', 'mar', 'mer', 'gio', 'ven', 'sab'];
  var MM = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'];
  var MESI = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'];
  C.ggData = function (d) { return GG[d.getDay()] + ' ' + d.getDate() + ' ' + MM[d.getMonth()]; };
  C.MESI = MESI;

  /* ---------- BotHeader + ModeBanner ---------- */
  // o: { key, name, symbol, accent, sub, statusLabel, statusTone, health, storico, extra, tabs }
  C.botHeader = function (o) {
    var b = D.botMode[o.key] || { mode: 'PAPER', running: false };
    var run = b.running;
    return '<section class="panel flat" style="padding:12px 14px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;border-color:' + (b.mode === 'LIVE' ? 'rgba(239,68,68,.45)' : 'hsl(var(--border))') + '">' +
      '<div style="width:40px;height:40px;border-radius:10px;display:grid;place-items:center;font:800 18px var(--f-display);background:hsl(var(--muted));border:1px solid hsl(var(--border));color:' + o.accent + '">' + o.symbol + '</div>' +
      '<div class="col" style="gap:2px;min-width:0"><div class="row" style="gap:8px"><h1 style="font-size:20px;color:' + o.accent + '" data-testid="bot-name">' + o.name + '</h1>' +
      S.chip((o.statusPrefix ? o.statusPrefix + ' ' : '') + (run ? 'IN CORSA' : 'FERMO'), run ? 'teal' : '') + (o.extraChip || '') + '</div><span class="foot">' + (o.sub || '') + '</span></div>' +
      '<div class="row" style="margin-left:auto;gap:8px">' + C.health(o.health) + (o.storico || C.storicoLink('calcio', true)) +
      '<div class="seg mode" role="group" aria-label="Modalità di trading" data-testid="mode-toggle">' +
      '<button data-act="mode" data-bot="' + o.key + '" data-v="PAPER" aria-pressed="' + (b.mode !== 'LIVE') + '">PAPER</button>' +
      '<button data-act="mode" data-bot="' + o.key + '" data-v="LIVE" aria-pressed="' + (b.mode === 'LIVE') + '">LIVE</button></div>' +
      (o.params ? '<button class="btn" data-act="params" data-bot="' + o.key + '">' + S.icon('gear') + ' Parametri</button>' : '') +
      (run ? '<button class="btn danger" data-act="botrun" data-bot="' + o.key + '" data-testid="bot-stop">' + S.icon('stop') + ' Ferma</button>'
        : '<button class="btn pri" data-act="botrun" data-bot="' + o.key + '" data-testid="bot-start">' + S.icon('play') + ' Avvia</button>') +
      '</div></section>' + C.modeBanner(o.key, o.liveText, o.paperText);
  };
  C.health = function (h) {
    h = h || {};
    return '<span class="stat" style="cursor:default" data-testid="service-health" title="Feed + battito del servizio"><span class="led ' + (h.bad ? 'warn' : 'on') + '"></span><span class="l">servizio</span> <b>' + (h.beat || 'battito 2 s') + '</b><span class="l">·</span><b>' + (h.src || 'STREAM') + '</b>' + (h.dry ? '<span class="chip amber" style="height:16px">DRY</span>' : '') + '</span>';
  };
  C.modeBanner = function (key, liveText, paperText) {
    var b = D.botMode[key] || { mode: 'PAPER' };
    if (b.mode === 'LIVE') return '<div class="strip live" role="alert" data-testid="mode-banner">' + S.chip('MODALITÀ LIVE', 'live') + '<span>' + (liveText || 'Ordini REALI su Betfair: soldi veri.') + '</span></div>';
    return '<div class="strip paper" data-testid="mode-banner">' + S.chip('MODALITÀ PAPER', 'paper') + '<span>' + (paperText || 'Simulazione fedele sui prezzi live: nessun ordine reale.') + '</span></div>';
  };
  C.storicoLink = function (sport, compact) {
    var one = function (s) { return '<a class="btn' + (compact ? ' sm' : '') + '" data-go="storico-' + s + '" href="#storico-' + s + '" title="Storico ' + s + ': i giorni precedenti, con P&L per bot, curva globale e calendario. Qui sopra c’è solo la giornata di oggi.">' + S.icon('history') + ' Storico ' + s + '</a>'; };
    return sport === 'entrambi' ? one('calcio') + one('tennis') : one(sport);
  };

  /* ---------- DayBar ---------- */
  C.dayBar = function (o) {
    var pct = o.goal ? Math.min(100, Math.max(0, o.realized / o.goal * 100)) : 0;
    var hit = o.goal && o.realized >= o.goal;
    return '<section class="panel" data-testid="day-bar" style="padding:14px 16px;display:flex;flex-direction:column;gap:10px">' +
      '<div class="row" style="justify-content:space-between;align-items:flex-start"><div><div class="row" style="gap:6px">' + S.icon('target') + '<h3 style="font-size:14px">Giornata operativa</h3></div>' +
      '<div class="foot">giornata operativa <b>gio 1 ott</b> (Europe/Rome)' + (o.note ? ' — ' + o.note : '') + '</div></div>' +
      '<div style="text-align:right"><div style="font:800 26px var(--f-display)" class="' + S.tone(o.realized) + ' num" data-testid="day-bar-realizzato">' + S.money(o.realized, { signed: true }) + (o.goal ? '<span class="mut" style="font-size:14px"> · ' + Math.round(pct) + ' %</span>' : '') + '</div>' +
      '<div class="foot">' + (o.fonte || 'realizzato netto di commissione') + '</div></div></div>' +
      '<div class="row" style="gap:6px 16px;font-size:12px" data-testid="day-bar-line">' +
      (o.goal ? '<span>Obiettivo di oggi <b class="gold">' + S.money(o.goal) + '</b></span>' : '') +
      '<span class="mut" data-testid="day-bar-counts">operazioni <b style="color:hsl(var(--foreground))">' + o.ops + '</b> · <b class="pos">' + o.v + 'V</b> <b class="neg">' + o.p + 'P</b> · <b style="color:hsl(var(--foreground))">' + (o.vive || 0) + '</b> vive</span>' +
      (o.goal ? (hit ? '<span class="pos" data-testid="day-bar-goal-hit">obiettivo <b>CENTRATO</b></span>' : '<span class="amb" data-testid="day-bar-remaining">resta <b>' + S.money(o.goal - o.realized) + '</b></span>') : '') +
      (o.locked != null ? '<span>P&L bloccato <b class="tealc">' + S.money(o.locked, { signed: true }) + '</b></span>' : '') +
      (o.total != null ? '<span class="mut">totale storico <b style="color:hsl(var(--foreground))">' + S.money(o.total, { signed: true }) + '</b></span>' : '') + '</div>' +
      (o.goal ? '<div class="bar gold" style="height:6px"><i style="width:' + pct + '%;background:linear-gradient(90deg,hsl(var(--primary)),hsl(var(--secondary)))"></i></div>' : '') + '</section>';
  };

  /* ---------- KpiRow ---------- */
  C.kpiRow = function (tiles, cols) {
    return '<div class="grid g' + (cols || tiles.length) + '" data-testid="kpi-row">' + tiles.map(function (t) { return S.kpi(t[0], t[1], t[2], t[3], t[4]); }).join('') + '</div>';
  };

  /* ---------- DailyCalendar ---------- */
  C.calendar = function (days, o) {
    o = o || {}; var y = 2026, m = o.month == null ? 8 : o.month; // settembre
    var first = new Date(y, m, 1), start = (first.getDay() + 6) % 7, nd = new Date(y, m + 1, 0).getDate();
    var map = {}; days.forEach(function (d) { map[d.iso] = d; });
    var max = Math.max.apply(null, days.map(function (d) { return Math.abs(d.pnl); }).concat([1]));
    var tot = days.filter(function (d) { return d.date.getMonth() === m; }).reduce(function (a, d) { return a + d.pnl; }, 0);
    var cnt = days.filter(function (d) { return d.date.getMonth() === m; }).length;
    var h = '<div data-testid="daily-calendar"><div class="row" style="justify-content:space-between;margin-bottom:8px"><div class="row" style="gap:4px"><button class="iconbtn" style="width:26px;height:26px" aria-label="Mese precedente" data-act="toast" data-t="Mese precedente">‹</button><b style="min-width:130px;text-align:center;font-family:var(--f-display)" data-testid="calendar-month">' + MESI[m][0].toUpperCase() + MESI[m].slice(1) + ' ' + y + '</b><button class="iconbtn" style="width:26px;height:26px" aria-label="Mese successivo" data-act="toast" data-t="Mese successivo">›</button><button class="btn sm" data-act="toast" data-t="Torna al mese corrente">Oggi</button></div>' +
      '<span class="foot" data-testid="calendar-month-total">' + cnt + ' giornate · <b class="' + S.tone(tot) + '">' + S.money(tot, { signed: true }) + '</b></span></div>' +
      '<div class="tbl-w"><div style="display:grid;grid-template-columns:repeat(7,minmax(64px,1fr));gap:3px;min-width:470px">' +
      ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'].map(function (g) { return '<div class="lbl" style="text-align:center;padding:2px">' + g + '</div>'; }).join('');
    for (var i = 0; i < start; i++) h += '<div></div>';
    for (var d = 1; d <= nd; d++) {
      var iso = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0'), x = map[iso];
      var lvl = x ? Math.abs(x.pnl) / max : 0, a = x ? (lvl > .75 ? .5 : lvl > .4 ? .34 : lvl > .15 ? .2 : .1) : 0;
      var bg = x ? (x.pnl >= 0 ? 'rgba(16,185,129,' + a + ')' : 'rgba(239,68,68,' + a + ')') : 'hsl(var(--muted)/.5)';
      var sel = o.sel === iso;
      h += '<button role="gridcell" data-testid="calendar-day" data-act="cal-day" data-scr="' + (o.scr || '') + '" data-v="' + iso + '" style="height:58px;border-radius:7px;border:1px solid ' + (sel ? 'hsl(var(--secondary))' : 'transparent') + ';background:' + bg + ';padding:4px 6px;text-align:left;cursor:pointer;display:flex;flex-direction:column;justify-content:space-between;position:relative">' +
        '<span style="font-size:10.5px;font-weight:600">' + d + '</span>' + (o.showGoal && x ? '<span style="position:absolute;top:3px;right:6px;font-size:10px" class="gold">' + (x.goal ? '●' : '○') + '</span>' : '') +
        (x ? '<span><b class="num" style="font-size:11.5px">' + S.money(x.pnl, { signed: true }) + '</b><br><span class="foot" style="font-size:9.5px">' + x.n + ' trade</span></span>' : '<span class="mut">—</span>') + '</button>';
    }
    h += '</div></div><p class="foot" style="margin:8px 0 0">verde/rosso = P&L realizzato del giorno (intensità relativa al mese)' + (o.showGoal ? ' · ● obiettivo centrato · ○ mancato · · non storicizzato' : '') + ' · frecce per muoversi, Invio per selezionare</p></div>';
    return h;
  };
  S.on('cal-day', function (t) { S.ui['day_' + t.dataset.scr] = t.dataset.v; S.rerender(); });

  /* ---------- BarreGiornaliere ---------- */
  C.barre = function (days, sel, scr) {
    if (!days.length) return '<div class="empty">nessuna giornata con operazioni in questo periodo</div>';
    var W = 560, H = 180, pad = 26, max = Math.max.apply(null, days.map(function (d) { return Math.abs(d.pnl); })) || 1;
    var mid = H / 2, bw = (W - pad * 2) / days.length;
    var h = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="spark" role="img" aria-label="' + days.length + ' giornate" data-testid="barre-giornaliere"><line x1="' + pad + '" x2="' + (W - pad) + '" y1="' + mid + '" y2="' + mid + '" stroke="hsl(155 15% 50% / .4)"/>';
    days.forEach(function (d, i) {
      var bh = Math.abs(d.pnl) / max * (mid - 14), x = pad + i * bw + 1.5, y = d.pnl >= 0 ? mid - bh : mid;
      h += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + Math.max(2, bw - 3).toFixed(1) + '" height="' + Math.max(1, bh).toFixed(1) + '" rx="2" fill="' + (d.pnl >= 0 ? '#34d399' : '#f87171') + '" opacity="' + (sel === d.iso ? 1 : .8) + '" ' + (sel === d.iso ? 'stroke="#e5f5ee"' : '') + ' style="cursor:pointer" data-act="cal-day" data-scr="' + scr + '" data-v="' + d.iso + '"><title>' + C.ggData(d.date) + ': ' + (d.pnl >= 0 ? '+' : '−') + Math.abs(d.pnl).toFixed(2).replace('.', ',') + ' €</title></rect>';
    });
    h += '<text x="' + (W - 2) + '" y="12" text-anchor="end" font-size="10" fill="hsl(155 15% 50%)">+' + max.toFixed(2).replace('.', ',') + ' €</text><text x="' + (W - 2) + '" y="' + (H - 4) + '" text-anchor="end" font-size="10" fill="hsl(155 15% 50%)">−' + max.toFixed(2).replace('.', ',') + ' €</text>' +
      '<text x="' + pad + '" y="' + (H - 4) + '" font-size="10" fill="hsl(155 15% 50%)">' + days[0].date.getDate() + ' ' + MM[days[0].date.getMonth()] + '</text><text x="' + (W - pad - 40) + '" y="' + (H - 4) + '" font-size="10" fill="hsl(155 15% 50%)">' + days[days.length - 1].date.getDate() + ' ' + MM[days[days.length - 1].date.getMonth()] + '</text></svg>';
    return h;
  };

  /* ---------- EquityCurve a gradini ---------- */
  C.equity = function (days, label) {
    if (!days.length) return '<div class="empty">nessuna giornata regolata in questo periodo — la curva compare al primo incasso</div>';
    var W = 560, H = 190, pl = 54, pr = 10, pt = 12, pb = 22, acc = 0, pts = [0];
    days.forEach(function (d) { acc += d.pnl; pts.push(Math.round(acc * 100) / 100); });
    var min = Math.min.apply(null, pts), max = Math.max.apply(null, pts), rng = max - min || 1;
    var X = function (i) { return pl + i * (W - pl - pr) / (pts.length - 1); }, Y = function (v) { return pt + (H - pt - pb) * (1 - (v - min) / rng); };
    var path = 'M' + X(0) + ' ' + Y(0);
    for (var i = 1; i < pts.length; i++) path += ' H' + X(i).toFixed(1) + ' V' + Y(pts[i]).toFixed(1);
    var col = acc >= 0 ? '#34d399' : '#f87171';
    var ticks = [max, (max + min) / 2, min];
    var h = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="spark" role="img" aria-label="' + (label || 'equity') + '">';
    ticks.forEach(function (t) { h += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + Y(t) + '" y2="' + Y(t) + '" stroke="hsl(155 10% 18%)"/><text x="' + (pl - 6) + '" y="' + (Y(t) + 3) + '" text-anchor="end" font-size="10" fill="hsl(155 15% 50%)">' + (t >= 0 ? '+' : '−') + Math.abs(t).toFixed(0) + ' €</text>'; });
    h += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + Y(0) + '" y2="' + Y(0) + '" stroke="hsl(155 15% 50% / .5)" stroke-dasharray="3 3"/>' +
      '<path d="' + path + ' V' + Y(min) + ' H' + X(0) + 'Z" fill="' + col + '" opacity=".1"/><path d="' + path + '" fill="none" stroke="' + col + '" stroke-width="1.8"/>' +
      '<circle cx="' + X(pts.length - 1) + '" cy="' + Y(pts[pts.length - 1]) + '" r="3" fill="' + col + '"/>' +
      '<text x="' + pl + '" y="' + (H - 5) + '" font-size="10" fill="hsl(155 15% 50%)">' + days[0].date.getDate() + ' ' + MM[days[0].date.getMonth()] + '</text><text x="' + (W - pr) + '" y="' + (H - 5) + '" text-anchor="end" font-size="10" fill="hsl(155 15% 50%)">' + days[days.length - 1].date.getDate() + ' ' + MM[days[days.length - 1].date.getMonth()] + '</text></svg>';
    return h;
  };
  C.equityCard = function (days, scope, testid) {
    return S.panel('Equity · P&L cumulato realizzato' + (scope ? ' <span class="mut" style="font-weight:500">· ' + scope + '</span>' : ''), C.equity(days, 'Curva ' + scope) + '<p class="foot" style="margin:6px 0 0" data-testid="equity-axis-note">asse verticale = € realizzati sommati, si parte da 0,00 € all’inizio dell’ambito; asse orizzontale = tempo (primo e ultimo passo etichettati); ogni gradino è un regolamento</p>', { icon: 'chart', id: testid });
  };

  /* ---------- DayDetail (safe/mike) ---------- */
  var SIGLE = { safe: ['BASE', 'R. ESATTO', 'PUNTA', 'MODELLO', 'MANUALE'], mike: ['INGRESSO U3.5', 'GREEN U3.5', 'COPERTURA 4.5', 'CHIUSURA U3.5', 'RE-INGRESSO U4.5'], omega: ['1T', '2T', 'SCALP'] };
  C.dayDetail = function (variant, day, mode) {
    if (!day) return '<div class="empty" data-testid="day-detail-empty">seleziona una giornata dal calendario per vedere i trade</div>';
    var matches = ['Inter v Torino', 'Real Betis v Getafe', 'Bologna v Udinese', 'Lens v Nantes', 'Napoli v Lazio', 'Brentford v Fulham', 'Benfica v Braga', 'Atalanta v Genoa', 'Feyenoord v AZ'];
    var rows = [];
    for (var i = 0; i < Math.min(day.n, 6); i++) {
      var lay = variant !== 'safe' || i % 2 === 0, q = [1.62, 2.1, 3.4, 1.38, 5.8, 2.46][i], st = [8, 10, 4, 12, 5, 6][i];
      var pnl = Math.round((i < day.v ? st * 0.42 : -st * (lay ? q - 1 : 1)) * 100) / 100;
      rows.push({ ora: ['14:02', '15:31', '17:48', '18:20', '20:46', '21:12'][i], match: matches[i], sig: (SIGLE[variant] || SIGLE.safe)[i % 5], sel: variant === 'mike' ? ['Under 3.5 Goals', 'Over 4.5 Goals'][i % 2] : ['Pareggio', '1 - 1', 'Under 2.5', '0 - 0'][i % 4], lato: lay ? 'LAY' : 'BACK', q: q, st: st, liab: lay ? st * (q - 1) : st, stato: i < day.v ? 'VINTO' : 'PERSO', pnl: pnl, uscita: i === 1 ? 'Green-up' : i === 3 ? 'Cash out manuale' : '', man: i === 3 });
    }
    var h = '<div data-testid="day-detail"><div class="row" style="justify-content:space-between;padding-bottom:8px;border-bottom:1px solid hsl(var(--border));margin-bottom:6px"><span class="row" style="gap:6px">' + S.icon('pulse') + '<b>' + C.ggData(day.date) + '</b><span class="mut">· ' + day.n + ' trade</span></span>' +
      '<span class="foot">liability piazzata <b style="color:hsl(var(--foreground))">' + S.money(rows.reduce(function (a, r) { return a + r.liab; }, 0)) + '</b> · realizzato <b class="' + S.tone(day.pnl) + '" data-testid="day-total-pnl">' + S.money(day.pnl, { signed: true }) + '</b></span></div>';
    h += '<div class="tbl-w"><table class="t"><thead><tr><th>Ora</th><th>Match</th><th>Strategia</th><th>Selezione</th><th>Lato</th><th class="r">Quota</th><th class="r">Stake</th><th class="r">Liability</th><th>Stato</th><th>Uscita</th><th class="r">P&L</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr data-testid="day-trade-row"><td class="mono">' + r.ora + '</td><td>' + r.match + (r.man ? ' <span class="chip" style="height:16px;color:#c4b5fd" title="piazzato manualmente">✋</span>' : '') + ' ' + S.chip(mode === 'live' ? 'LIVE' : 'PAPER', mode === 'live' ? 'live' : '') + '</td><td><span class="chip">' + r.sig + '</span></td><td>' + r.sel + '</td><td>' + S.chip(r.lato, r.lato === 'BACK' ? 'sky' : 'rose') + '</td><td class="r">' + S.odds(r.q) + '</td><td class="r">' + S.money(r.st) + '</td><td class="r ora">' + S.money(r.liab) + '</td><td>' + S.chip(r.stato, r.stato === 'VINTO' ? 'paper' : 'red') + '</td><td>' + (r.uscita ? S.chip(r.uscita, 'teal') : '<span class="mut">—</span>') + '</td><td class="r ' + S.tone(r.pnl) + '"><b>' + S.money(r.pnl, { signed: true }) + '</b></td></tr>';
      }).join('') + '</tbody></table></div><div class="row foot" style="justify-content:space-between;margin-top:6px"><span>' + day.n + ' regolati · 0 vivi · ' + day.v + 'V ' + day.p + 'P</span><span>totale realizzato <b class="' + S.tone(day.pnl) + '">' + S.money(day.pnl, { signed: true }) + '</b></span></div></div>';
    return h;
  };

  /* ---------- PerformancePanel ---------- */
  C.performance = function (variant, days, scr) {
    var per = S.tab(scr + '-per', 'mese');
    var tot = days.reduce(function (a, d) { return a + d.pnl; }, 0), pos = days.filter(function (d) { return d.pnl > 0; }).length;
    var v = days.reduce(function (a, d) { return a + d.v; }, 0), p = days.reduce(function (a, d) { return a + d.p; }, 0);
    var best = Math.max.apply(null, days.map(function (d) { return d.pnl; })), worst = Math.min.apply(null, days.map(function (d) { return d.pnl; }));
    var tiles = [['P&L periodo', S.money(tot, { signed: true }), days.length + ' giornate operative', S.tone(tot)], ['Giornate +/−', pos + ' / ' + (days.length - pos), '', ''], ['Win rate', S.pct(v / (v + p || 1)), v + 'V · ' + p + 'P · 0 void', ''], ['Profit factor', '1,42', 'gross profit / gross loss', ''], ['Expectancy / trade', S.money(tot / (v + p || 1), { signed: true }), '', S.tone(tot)], ['Max drawdown', S.money(-38.4), 'in corso 0,00 € dal picco', 'neg'], ['Miglior giornata', S.money(best, { signed: true }), '', 'pos'], ['Peggior giornata', S.money(worst, { signed: true }), '', 'neg'], ['Serie', '4+ / 2−', '4 giornate positive di fila', '']];
    if (variant === 'omega') tiles.push(['Obiettivo centrato', '14/24', '58 % delle giornate · 2 senza obiettivo storicizzato', 'gold']);
    tiles.push(['Liability max', S.money(variant === 'mike' ? 41.6 : 64.0), 'massima esposizione su un trade', 'ora']);
    var bk = { omega: [['Gamba 1T (Half Time Score)', 34, 22, 12, 41.2], ['Gamba 2T (Correct Score)', 31, 19, 12, 18.6], ['Scalp', 8, 6, 2, 4.1]], safe: [['BASE', 22, 15, 7, 21.4], ['R. ESATTO', 9, 5, 4, -6.2], ['PUNTA', 6, 4, 2, 3.8]], mike: [['Ingresso Under 3.5', 26, 18, 8, 22.9], ['Green-up Under 3.5', 14, 14, 0, 31.5], ['Copertura linea 4.5', 6, 2, 4, -12.3], ['Chiusura Under 3.5', 4, 1, 3, -8.8]] }[variant];
    return '<section class="panel" data-testid="performance-panel"><div class="panel-h"><h3>Performance</h3><div class="r"><span class="lbl">Periodo</span><div class="seg">' + [['mese', 'Mese corrente'], ['30', '30 giorni'], ['90', '90 giorni'], ['anno', 'Anno']].map(function (x) { return '<button data-act="tab" data-scr="' + scr + '-per" data-v="' + x[0] + '" aria-pressed="' + (per === x[0]) + '">' + x[1] + '</button>'; }).join('') + '</div><span class="foot" data-testid="period-range">1 set → 1 ott 2026</span></div></div>' +
      '<div class="panel-b stack"><div class="grid g5">' + tiles.map(function (t) { return S.kpi(t[0], t[1], t[2], t[3]); }).join('') + '</div>' +
      '<div class="grid g2"><div class="panel flat" style="padding:10px"><div class="lbl" style="margin-bottom:6px">Equity · P&L cumulato realizzato · per giornata</div>' + C.equity(days) + '</div>' +
      '<div class="panel flat" style="padding:0"><div class="tbl-w"><table class="t" data-testid="breakdown-strategy"><thead><tr><th>' + (variant === 'safe' ? 'Strategia' : 'Gamba') + '</th><th class="r">Trade</th><th class="r">Vinti</th><th class="r">Persi</th><th class="r">Win rate</th><th class="r">P&L</th></tr></thead><tbody>' +
      bk.map(function (r) { return '<tr><td>' + r[0] + '</td><td class="r">' + r[1] + '</td><td class="r pos">' + r[2] + '</td><td class="r neg">' + r[3] + '</td><td class="r">' + S.pct(r[2] / r[1]) + '</td><td class="r ' + S.tone(r[4]) + '"><b>' + S.money(r[4], { signed: true }) + '</b></td></tr>'; }).join('') +
      (variant === 'safe' ? '<tr><td colspan="6" class="lbl" style="background:hsl(var(--muted))">Sport</td></tr><tr><td>⚽ Calcio</td><td class="r">31</td><td class="r pos">21</td><td class="r neg">10</td><td class="r">67,7 %</td><td class="r pos"><b>+16,20 €</b></td></tr><tr><td>🎾 Tennis</td><td class="r">6</td><td class="r pos">3</td><td class="r neg">3</td><td class="r">50,0 %</td><td class="r pos"><b>+2,80 €</b></td></tr>' : '') +
      '<tr><td colspan="6" class="lbl" style="background:hsl(var(--muted))">Origine</td></tr><tr><td>⚙️ Automatico</td><td class="r">44</td><td class="r pos">29</td><td class="r neg">15</td><td class="r">65,9 %</td><td class="r pos"><b>+27,10 €</b></td></tr><tr><td>✋ Manuale</td><td class="r">5</td><td class="r pos">3</td><td class="r neg">2</td><td class="r">60,0 %</td><td class="r neg"><b>−2,40 €</b></td></tr></tbody></table></div></div></div></div></section>';
  };

  /* ---------- TradingHistory (tab Storico dentro i bot) ---------- */
  C.tradingHistory = function (variant, scr) {
    var mode = (D.botMode[variant] || {}).mode === 'LIVE' ? 'live' : 'paper';
    var days = D.giorni(variant, mode, 30), sel = S.ui['day_' + scr] || (days[days.length - 1] || {}).iso;
    var day = days.filter(function (d) { return d.iso === sel; })[0];
    return '<div class="stack" data-testid="trading-history"><div class="row foot" style="justify-content:space-between"><span>Giornata operativa = fuso Europe/Rome · oggi <b>gio 1 ott</b> · P&L realizzato = posizioni PIAZZATE nel giorno (chiusure incluse), anche se si regolano dopo</span><button class="btn sm" data-act="toast" data-t="Storico aggiornato">Aggiorna</button></div>' +
      '<div class="split-l" style="grid-template-columns:minmax(0,2fr) minmax(0,3fr)"><section class="panel"><div class="panel-b">' + C.calendar(days, { scr: scr, sel: sel, showGoal: variant === 'omega' }) + '</div></section>' + C.performance(variant, days, scr) + '</div>' +
      S.panel('Operazioni del giorno', C.dayDetail(variant, day, mode), { icon: 'calendar' }) + '</div>';
  };

  /* ---------- EventPnlTable (tabella operazioni per partita) ---------- */
  C.eventPnl = function (o) {
    var mode = o.mode || 'PAPER';
    var rows = o.rows;
    var tot = rows.reduce(function (a, r) { return a + (r.closed ? r.pnl : 0); }, 0);
    var aperte = rows.filter(function (r) { return !r.closed; }).length;
    var h = '<div class="grid g5" data-testid="' + (o.testId || 'event-pnl') + '-totali" data-mode="' + mode + '" style="margin-bottom:10px">' +
      S.kpi('Operazioni', rows.reduce(function (a, r) { return a + r.n; }, 0), rows.length + ' partite') + S.kpi('P&L realizzato · ' + mode, S.money(tot, { signed: true }), rows.filter(function (r) { return r.pnl > 0; }).length + ' in utile · ' + rows.filter(function (r) { return r.pnl < 0; }).length + ' in perdita', S.tone(tot)) +
      S.kpi('Se chiudo ora · ' + mode, aperte ? S.money(o.seChiudo || 3.4, { signed: true }) : '—', aperte ? aperte + ' ancora aperte' : 'niente di aperto', 'tealc', 'STIMA') + S.kpi('Investito', S.money(rows.reduce(function (a, r) { return a + r.inv; }, 0))) + S.kpi('Liability aperta', S.money(rows.reduce(function (a, r) { return a + (r.closed ? 0 : r.liab); }, 0)), '', 'ora') + '</div>' +
      (o.altra ? '<div class="strip warn" style="margin-bottom:10px">' + o.altra + ' operazioni in un’altra modalità (il servizio è in ' + mode + '): sono in tabella ma NON nei totali qui sopra — paper e live sono contabilità separate.</div>' : '') +
      '<div class="tbl-w"><table class="t"><thead><tr><th></th><th>Partita</th><th class="r">' + (o.unit || 'posizioni') + '</th><th class="r">Investito</th><th class="r">Liability aperta</th><th>Stato</th><th class="r">P&L netto</th></tr></thead><tbody>';
    rows.forEach(function (r, i) {
      var open = S.ui[(o.testId || 'ev') + '_x'] === i;
      h += '<tr style="cursor:pointer" data-act="ev-x" data-k="' + (o.testId || 'ev') + '" data-i="' + i + '"><td>' + (open ? '▾' : '▸') + '</td><td><b>' + r.match + '</b> ' + (r.live ? S.chip('soldi veri', 'amber') : '') + '</td><td class="r">' + r.n + '</td><td class="r">' + S.money(r.inv) + '</td><td class="r ora">' + (r.closed ? '—' : S.money(r.liab)) + '</td><td>' + (r.closed ? S.chip('chiusa') : S.chip('ancora aperta', 'sky')) + '</td><td class="r ' + S.tone(r.pnl) + '"><b style="font-size:13px">' + S.money(r.pnl, { signed: true }) + '</b>' + (r.closed ? '' : ' <span class="foot">parz.</span>') + '</td></tr>';
      if (open) h += '<tr><td></td><td colspan="6" style="background:hsl(var(--muted)/.5);white-space:normal"><div class="foot" style="margin-bottom:4px">' + (o.unit || 'posizioni') + ' 1: ingresso ' + S.odds(r.q) + ' → uscita ' + S.odds(r.q * 0.82) + ' | 2 ordini | netto ' + S.money(r.pnl, { signed: true }) + '</div>' +
        '<table class="t"><tbody><tr><td class="mono">' + r.ora + '</td><td>apertura</td><td>' + S.chip('LAY', 'rose') + ' ' + r.sel + '</td><td class="r">' + S.money(r.inv) + '</td><td class="r">' + S.odds(r.q) + '</td><td>' + S.chip('ABBINATO', 'paper') + '</td><td class="r">—</td></tr>' +
        (r.closed ? '<tr><td class="mono">' + r.ora2 + '</td><td>green-up</td><td>' + S.chip('BACK', 'sky') + ' ' + r.sel + '</td><td class="r">' + S.money(r.inv * 1.1) + '</td><td class="r">' + S.odds(r.q * 0.82) + '</td><td>' + S.chip('ABBINATO', 'paper') + '</td><td class="r ' + S.tone(r.pnl) + '">' + S.money(r.pnl, { signed: true }) + '</td></tr>' : '') + '</tbody></table></td></tr>';
    });
    return h + '</tbody></table></div><p class="foot" style="margin:6px 0 0">Clicca una partita per aprire le operazioni che la compongono.</p>';
  };
  S.on('ev-x', function (t) { var k = t.dataset.k + '_x', i = +t.dataset.i; S.ui[k] = S.ui[k] === i ? null : i; S.rerender(); });

  /* ---------- ActivityFeed ---------- */
  C.activity = function (rows) {
    return '<div class="col" style="gap:0;max-height:340px;overflow:auto">' + rows.map(function (r) {
      return '<div class="row" style="flex-wrap:nowrap;padding:6px 2px;border-bottom:1px solid hsl(var(--border)/.6);font-size:12px"><span class="mono mut" style="width:62px;flex:none">' + r[0] + '</span><span class="chip ' + (r[2] || '') + '" style="flex:none">' + r[1] + '</span><span style="min-width:0">' + r[3] + '</span></div>';
    }).join('') + '</div>';
  };

  /* ---------- azioni comuni ---------- */
  S.on('mode', function (t) {
    var b = D.botMode[t.dataset.bot]; if (!b || b.mode === t.dataset.v) return;
    if (t.dataset.v === 'LIVE') S.confirmLive(b.name, function () { b.mode = 'LIVE'; S.rerender(); S.toast(b.name + ' in MODALITÀ LIVE', 'Prototipo: nessun ordine reale.'); });
    else { b.mode = 'PAPER'; S.rerender(); S.toast(b.name + ' in MODALITÀ PAPER'); }
  });
  S.on('botrun', function (t) {
    var b = D.botMode[t.dataset.bot]; if (!b) return;
    if (b.running) S.modal({ danger: b.mode === 'LIVE', title: 'Fermare ' + b.name + '?', body: 'Il bot smette di aprire nuove posizioni. Le posizioni aperte restano sul mercato finché non le chiudi.', ok: 'Ferma', onOk: function () { b.running = false; S.rerender(); } });
    else { b.running = true; S.rerender(); S.toast(b.name + ' avviato', b.mode === 'LIVE' ? 'MODALITÀ LIVE · soldi veri' : 'MODALITÀ PAPER'); }
  });
})();
