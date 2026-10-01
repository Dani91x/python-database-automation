/* s_tennis.js - Dashboard tennis (/tennis) e Tennis Terminal (/tennis/terminal) con i 4 bot tennis. */
(function () {
  'use strict';
  var S = window.S, D = window.D, M = S.money, chip = S.chip;

  /* ---------- Partite del Giorno (TennisMatchesList) ---------- */
  S.reg({
    id: 'tennis', title: 'Tennis · Partite del Giorno', group: 'Tennis',
    render: function () {
      var day = S.ui.tday || 'Oggi', fav = S.ui.tfav || {};
      var groups = {};
      D.boardTennis.forEach(function (r) { (groups[r.torneo] = groups[r.torneo] || []).push(r); });
      var names = Object.keys(groups).sort();
      var open = S.ui.topen || names[0];
      var h = '<div class="ph"><div><h1>Partite del Giorno<em>.</em></h1><p>Tennis · Giovedì 1 ottobre</p></div><div class="act"><div class="seg">' + ['Ieri', 'Oggi', 'Domani'].map(function (d) { return '<button data-act="tday" data-v="' + d + '" aria-pressed="' + (day === d) + '">' + d + '</button>'; }).join('') + '</div><span class="chip">' + D.boardTennis.length + ' Match</span></div></div>';
      if (day !== 'Oggi') return h + '<div class="empty">' + S.icon('star') + '<p><b>Nessun match di tennis</b><br>Non ci sono partite di tennis per ' + day.toLowerCase() + '. Prova un altro giorno.</p></div>';
      h += names.map(function (n) {
        var isOpen = open === n;
        return '<section class="panel" style="padding:0"><button class="row" data-act="topen" data-v="' + n + '" style="width:100%;border:0;background:none;cursor:pointer;padding:12px 14px"><span style="width:36px;height:36px;border-radius:9px;display:grid;place-items:center;background:hsl(var(--primary)/.12);color:hsl(var(--primary))">🏆</span><div style="text-align:left"><b>' + n + '</b><div class="lbl" style="font-size:9.5px">Cina · ' + groups[n].length + ' partite</div></div><span class="cnt" style="margin-left:auto">' + groups[n].length + '</span><span>' + (isOpen ? '▾' : '▸') + '</span></button>' +
          (isOpen ? '<div class="col" style="padding:0 12px 12px;gap:6px">' + groups[n].map(function (r) {
            var cd = r.inplay ? null : D.countdown(r.open);
            return '<div style="padding:10px 12px;border-radius:10px;background:hsl(var(--muted)/.5);display:flex;flex-direction:column;gap:6px"><div class="row" style="flex-wrap:wrap">' +
              '<button class="iconbtn" style="width:28px;height:28px;' + (fav[r.id] ? 'color:hsl(var(--secondary))' : '') + '" data-act="tfav" data-v="' + r.id + '" aria-pressed="' + !!fav[r.id] + '" aria-label="' + (fav[r.id] ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti') + '">★</button>' +
              '<div style="text-align:center;min-width:52px"><div class="clock">' + D.hhmm(r.open) + '</div>' + (r.inplay ? chip('IN CORSO', 'inplay') : chip('PRE-MATCH')) + '</div>' +
              '<div class="row" style="flex:1;justify-content:center;gap:10px;min-width:280px"><b style="text-align:right;min-width:90px">' + r.sels[0].name + '</b>' + S.oddsPair(r.sels[0].back, r.sels[0].lay) + '<span class="mut">VS</span>' + S.oddsPair(r.sels[1].back, r.sels[1].lay) + '<b style="min-width:90px">' + r.sels[1].name + '</b></div>' +
              '<div style="text-align:right"><div class="lbl" style="font-size:9.5px">Volume</div><b class="gold mono">€' + (r.matched / 1000).toFixed(1).replace('.', ',') + 'k</b></div><a class="btn pri sm" data-go="tennis-terminal" href="#tennis-terminal">APRI TERMINAL →</a></div>' +
              '<div class="row foot" style="border-top:1px solid hsl(var(--border));padding-top:5px"><span>4 mercati</span><span class="mono">evt ' + r.id + '</span><span class="mono">mkt 1.2' + r.id.slice(-6) + '</span><span style="margin-left:auto">' + S.media(true) + '</span></div></div>';
          }).join('') + '</div>' : '') + '</section>';
      }).join('');
      return h + '<p class="foot">Quote moneyline del primo livello (best) back/lay da Betfair Exchange. I preferiti restano su questo computer.</p>';
    }
  });
  S.on('tday', function (t) { S.ui.tday = t.dataset.v; S.rerender(); });
  S.on('topen', function (t) { S.ui.topen = S.ui.topen === t.dataset.v ? '__none' : t.dataset.v; S.rerender(); });
  S.on('tfav', function (t) { var f = S.ui.tfav = S.ui.tfav || {}; f[t.dataset.v] = !f[t.dataset.v]; S.rerender(); });

  /* ---------- Tennis Terminal ---------- */
  function botCard(b) {
    var st = (S.ui.tb = S.ui.tb || {})[b.key] || { armed: b.key === 'tennis_pro', dry: false, open: false };
    S.ui.tb[b.key] = st;
    var mode = S.ui.tOrderMode || 'PAPER';
    var h = '<article style="border-radius:12px;border:1px solid ' + (st.armed ? b.acc : 'hsl(var(--border))') + ';background:hsl(var(--glass)/.4);padding:11px;display:flex;flex-direction:column;gap:9px;' + (st.armed ? 'box-shadow:0 0 0 1px ' + b.acc + ' inset' : '') + '">';
    h += '<div class="row" style="align-items:flex-start;flex-wrap:nowrap"><span class="led" style="background:' + b.acc + ';margin-top:5px"></span><div style="min-width:0;flex:1"><div class="row" style="gap:6px"><b style="font-family:var(--f-display)">' + b.name + '</b><span class="lbl" style="font-size:9px;color:' + b.acc + '">' + b.fase + '</span></div><div class="foot" style="font-size:10.5px">' + b.short + '</div></div>' +
      '<div style="text-align:right">' + (st.armed ? chip('Operativo', 'paper') : chip('Inattivo')) + (st.armed ? '<div class="foot mono" style="font-size:9.5px">agg. 3s fa</div>' : '') + '</div></div>';
    if (b.key === 'tennis_pro') h += '<div class="foot" data-testid="tennis-pro-superficie" style="padding:4px 8px;border-radius:6px;background:hsl(var(--muted))" title="torneo: ATP Pechino">superficie: cemento (torneo: China Open)</div>';
    h += '<div class="row" style="font-size:11.5px"><label class="row" for="tb-st-' + b.key + '" style="gap:6px">Stake €<input class="inp" id="tb-st-' + b.key + '" value="5" style="width:64px;height:24px"' + (st.armed ? ' disabled' : '') + '></label><label class="row" style="gap:5px' + (st.dry ? ';color:var(--amber)' : '') + '"><input type="checkbox" data-act="tb-dry" data-v="' + b.key + '"' + (st.dry ? ' checked' : '') + (st.armed ? ' disabled' : '') + '> Dry-run (solo log: nessun ordine, nemmeno simulato)</label></div>' +
      (!st.armed && !st.dry ? '<div class="foot amb">' + (mode === 'LIVE' ? '<span class="neg">⚠ ORDINI REALI</span>' : '⚡ ORDINI SIMULATI · visibili sul ladder') + '</div>' : '');
    h += '<div><button class="row foot" data-act="tb-open" data-v="' + b.key + '" style="border:0;background:none;cursor:pointer;padding:0;width:100%">' + (st.open ? '▼' : '▶') + ' Parametri (' + b.f.length + ')' + (!st.armed ? '<span style="margin-left:auto">↺ default</span>' : '') + '</button>' +
      (st.open ? '<div class="grid g2" style="gap:6px;margin-top:6px">' + b.f.map(function (f, i) { var id = 'tbp-' + b.key + i; return f[3] ? '<label class="field" for="' + id + '" style="font-size:10.5px">' + f[0] + '<select class="inp" id="' + id + '" style="height:26px">' + f[3].slice(2).split('|').map(function (o) { return '<option' + (o === f[2] ? ' selected' : '') + '>' + o + '</option>'; }).join('') + '</select></label>' : '<label class="field" for="' + id + '" style="font-size:10.5px">' + f[0] + '<input id="' + id + '" value="' + String(f[2]).replace('.', ',') + '" style="height:26px"></label>'; }).join('') + '</div>' : '') + '</div>';
    if (b.key === 'tennis_scalper') h += '<div class="row">' + chip('Tick pre-match …') + chip('Tick in-play …') + '</div>';
    if (st.armed) h += '<div class="grid g3" style="gap:5px">' + [['Cicli', '4'], ['Scalp', '3'], ['Scratch', '1'], ['Stop', '0'], ['P&L bloccato € (lordo)', '+1,15'], ['P&L aperto €', '+0,28']].map(function (x) { return '<div class="kpi" style="padding:5px 7px"><div class="k" style="font-size:8.5px">' + x[0] + '</div><div class="v" style="font-size:13px;color:' + b.acc + '">' + x[1] + '</div></div>'; }).join('') + '</div>';
    h += '<button class="btn ' + (st.armed ? 'danger' : 'pri') + '" style="justify-content:center;width:100%;height:34px;font-weight:800" data-act="tb-arm" data-v="' + b.key + '">' + (st.armed ? '■ DISARMA' : st.dry ? '⏻ ARMA (dry-run)' : mode === 'LIVE' ? 'ARMA ORDINI REALI' : 'ARMA SIMULATO') + '</button></article>';
    return h;
  }
  S.on('tb-dry', function (t) { var s = S.ui.tb[t.dataset.v]; s.dry = !s.dry; S.rerender(); });
  S.on('tb-open', function (t) { var s = S.ui.tb[t.dataset.v]; s.open = !s.open; S.rerender(); });
  S.on('tb-arm', function (t) {
    var s = S.ui.tb[t.dataset.v], b = S.TBOTS.filter(function (x) { return x.key === t.dataset.v; })[0];
    if (s.armed) { s.armed = false; S.rerender(); S.toast(b.name + ': disarmo richiesto — chiusura flat in corso', 'Stato "stopped" quando la posizione è verificata flat.'); return; }
    var go = function () { s.armed = true; S.rerender(); S.toast(b.name + (s.dry ? ' ARMATO (dry-run · nessun ordine)' : (S.ui.tOrderMode === 'LIVE' ? ' ARMATO · ORDINI REALI' : ' ARMATO · SIMULATO (visibile sul ladder)'))); };
    if (!s.dry && S.ui.tOrderMode === 'LIVE') S.modal({ danger: true, title: '⚠️ ARMARE "' + b.name + '" CON ORDINI REALI?', body: 'Il bot piazzerà scommesse REALI su Betfair in autonomia (stake €5). Confermi?', ok: 'Arma', onOk: go }); else go();
  });

  function stats() {
    var tab = S.tab('tt-right', 'stats');
    var h = '<div class="tabs">' + [['stats', 'Stats'], ['chart', 'Chart'], ['depth', 'Depth']].map(function (x) { return '<button aria-selected="' + (tab === x[0]) + '" data-act="tab" data-scr="tt-right" data-v="' + x[0] + '">' + x[1] + '</button>'; }).join('') + '</div>';
    if (tab === 'chart') return h + S.panel('Candele · J. Sinner', '<div class="row" style="margin-bottom:6px"><select class="inp" id="tt-sel" aria-label="Selezione"><option>J. Sinner</option><option>J. Draper</option></select><div class="seg" aria-label="Timeframe">' + ['5s', '15s', '30s', '1m', '5m'].map(function (x, i) { return '<button aria-pressed="' + (i === 0) + '">' + x + '</button>'; }).join('') + '</div></div>' + candles() + '<p class="foot">Aggiornato: 10:41:23 (canale) · linea ambra = VWAP</p>', { flush: false });
    if (tab === 'depth') return h + depth(['J. Sinner', 'J. Draper']);
    return h + '<section class="panel" style="padding:12px;display:flex;flex-direction:column;gap:10px"><div class="row"><b style="font-family:var(--f-display);letter-spacing:.06em">MATCH STATS</b><span style="margin-left:auto">' + chip('IN CORSO', 'inplay') + '</span></div>' +
      '<table class="t" style="font-size:12px"><thead><tr><th></th><th>Giocatore</th><th class="r">Set</th><th>Set-by-set</th><th class="r">Gm</th><th class="r">Pt</th></tr></thead><tbody><tr style="background:hsl(var(--primary)/.06)"><td><span class="led" style="background:hsl(var(--secondary));box-shadow:0 0 6px hsl(var(--secondary))"></span></td><td><b>J. Sinner</b></td><td class="r gold" style="font:800 16px var(--f-display)">1</td><td><span class="chip">6</span> <span class="chip" style="color:hsl(var(--primary));border-color:hsl(var(--primary)/.6)">2</span></td><td class="r">2</td><td class="r prim"><b>40</b></td></tr><tr><td><span class="led off"></span></td><td>J. Draper</td><td class="r gold" style="font:800 16px var(--f-display)">0</td><td><span class="chip" style="opacity:.6">4</span> <span class="chip">1</span></td><td class="r">1</td><td class="r">15</td></tr></tbody></table>' +
      '<div class="row foot" style="justify-content:space-between"><span class="mono">6-4 2-1</span><span>⏲ agg. 2s fa</span></div><div class="row">' + S.icon('bolt', 'amb') + chip('GAME POINT') + '</div>' +
      '<div><div class="lbl">Win Probability</div><div class="row" style="justify-content:space-between;font-weight:700"><span class="prim">81%</span><span class="gold">19%</span></div><div style="display:flex;height:8px;border-radius:99px;overflow:hidden"><i style="width:81%;background:hsl(var(--primary))"></i><i style="width:19%;background:hsl(var(--secondary))"></i></div></div>' +
      '<div class="foot">Break servizio · <b class="prim">J. Sinner 2</b> · <b class="gold">J. Draper 1</b></div>' +
      '<div><div class="lbl">Punto per punto <span class="cnt">40</span></div><div style="max-height:180px;overflow:auto">' + [['S2·G4', 'J. Sinner', 'GAME', 'sv1', '40-15'], ['S2·G3', 'J. Sinner', 'BREAK', 'sv2', '2-1'], ['S2·G3', 'J. Draper', '', 'sv2', '30-40'], ['S1·G10', 'J. Sinner', 'SET', 'sv1', '6-4']].map(function (p) { return '<div class="row" style="font-size:11.5px;padding:3px 0;border-bottom:1px solid hsl(var(--border)/.5)"><span class="mono foot">' + p[0] + '</span><span class="led" style="background:' + (p[1] === 'J. Sinner' ? 'hsl(var(--primary))' : 'hsl(var(--secondary))') + '"></span>' + p[1] + (p[2] ? chip(p[2], p[2] === 'BREAK' ? 'amber' : p[2] === 'SET' ? 'red' : '') : '') + '<span class="foot">' + p[3] + '</span><span class="mono" style="margin-left:auto">' + p[4] + '</span></div>'; }).join('') + '</div></div></section>';
  }
  function candles() {
    var W = 340, H = 150, n = 26, h = '<svg viewBox="0 0 ' + W + ' ' + (H + 40) + '" class="spark" role="img" aria-label="Candele prezzo della selezione con VWAP">', p = 1.26, vw = [];
    for (var i = 0; i < n; i++) {
      var o = p, c = p + (Math.sin(i * 1.7) * 0.012), hi = Math.max(o, c) + 0.006, lo = Math.min(o, c) - 0.006; p = c;
      var Y = function (v) { return 10 + (1.30 - v) / 0.09 * (H - 20); }, x = 10 + i * (W - 20) / n;
      var col = c >= o ? '#10b981' : '#f43f5e';
      h += '<line x1="' + (x + 4) + '" x2="' + (x + 4) + '" y1="' + Y(hi) + '" y2="' + Y(lo) + '" stroke="' + col + '"/><rect x="' + x + '" y="' + Math.min(Y(o), Y(c)) + '" width="8" height="' + Math.max(1, Math.abs(Y(o) - Y(c))) + '" fill="' + col + '"/>';
      h += '<rect x="' + x + '" y="' + (H + 38 - (8 + (i * 7) % 26)) + '" width="8" height="' + (8 + (i * 7) % 26) + '" fill="hsl(155 15% 50% / .5)"/>';
      vw.push([x + 4, Y(1.255 + i * 0.0003)]);
    }
    h += '<path d="' + vw.map(function (q, i) { return (i ? 'L' : 'M') + q[0] + ' ' + q[1]; }).join(' ') + '" fill="none" stroke="#fbbf24" stroke-width="2"/></svg>';
    return h;
  }
  function depth(sels) {
    return '<section class="panel" style="padding:12px;display:flex;flex-direction:column;gap:10px"><div class="row"><b>Profondità totale</b><div class="seg" style="margin-left:auto" title="finestra del delta flusso">' + ['10s', '30s', '60s'].map(function (x, i) { return '<button aria-pressed="' + (i === 1) + '">' + x + '</button>'; }).join('') + '</div></div>' +
      sels.map(function (s, i) { return '<div class="panel flat" style="padding:8px 10px"><div class="row foot" style="justify-content:space-between"><b style="color:hsl(var(--foreground))">' + s + '</b><span>book ' + (i ? '96' : '101') + '% back · ' + (i ? '104' : '99') + '% lay</span></div><div class="row" style="gap:4px;margin:4px 0"><span class="foot" style="width:34px">BACK</span><span style="flex:1;height:8px;display:flex;gap:2px">' + [30, 22, 18, 12].map(function (w) { return '<i style="width:' + w + '%;background:rgba(14,165,233,.7);border-radius:2px"></i>'; }).join('') + '</span><b class="mono">€' + (i ? 840 : 4120) + '</b></div><div class="row" style="gap:4px"><span class="foot" style="width:34px">LAY</span><span style="flex:1;height:8px;display:flex;gap:2px">' + [26, 20, 14, 10].map(function (w) { return '<i style="width:' + w + '%;background:rgba(236,72,153,.7);border-radius:2px"></i>'; }).join('') + '</span><b class="mono">€' + (i ? 610 : 3380) + '</b></div><div class="foot">Flusso 30s <span class="pos">back +€120</span> · <span class="neg">lay −€40</span>' + (i ? '' : ' · <span class="amb">⚖ shift WOM +6pp in 30s (pressione BACK)</span>') + '</div></div>'; }).join('') + '<p class="foot">Flusso calcolato client-side dai sample del ladder da quando il pannello è aperto.</p></section>';
  }
  S.depthPanel = depth; S.candles = candles;

  S.reg({
    id: 'tennis-terminal', title: 'Tennis Terminal', group: 'Tennis',
    render: function () {
      var mode = S.ui.tOrderMode || 'PAPER', rec = S.ui.tRec;
      var h = '<div class="strip info"><span class="lbl">Prototipo</span><span>modalità ordini del runner tennis (si sceglie dall’ambiente del runner, qui solo per vedere i tre stati):</span><div class="seg">' + ['OFF', 'PAPER', 'LIVE'].map(function (m) { return '<button data-act="t-mode" data-v="' + m + '" aria-pressed="' + (mode === m) + '">' + m + '</button>'; }).join('') + '</div></div>';
      h += '<section class="panel flat" style="padding:9px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:56px;z-index:30"><a class="btn sm" data-go="tennis" href="#tennis">‹ Torna alle partite</a><b style="font:800 15px var(--f-display)">J. Sinner <span class="mut">vs</span> J. Draper</b><span class="mono foot">· Match Odds</span><b class="mono pos" title="Punteggio set · game">6-4 2-1 · 40–15</b>' +
        (mode === 'LIVE' ? '<span class="chip live" style="background:#dc2626;color:#fff" title="Runner in LIVE: gli ordini sono REALI (soldi veri).">LIVE · REALE</span>' : mode === 'PAPER' ? '<span class="chip paper" title="Runner in PAPER: ordini SIMULATI, visibili sul ladder come dal vivo.">PAPER · SIMULATO</span>' : '<span class="chip" title="Runner ordini SPENTO">ORDINI OFF</span>') +
        '<span class="chip inplay" title="Partita seguita dal runner tennis: ladder e punteggio in arrivo.">SEGUITA</span><button class="btn sm ' + (rec ? 'danger' : '') + '" data-act="t-rec" aria-pressed="' + !!rec + '">' + (rec ? '● REC ON' : '● REC') + '</button><span style="margin-left:auto" class="row">' + S.media(true) + '<span class="mono foot">event 34813501 · market 1.24813501</span></span></section>';
      var tb = S.TBOTS.filter(function (b) { return (S.ui.tb || {})[b.key] && S.ui.tb[b.key].armed; }).length || 1;
      h += '<div class="tt-grid">' +
        '<div class="col" style="gap:10px"><div class="row"><span class="prim">' + S.icon('bot') + '</span><b style="font-family:var(--f-display)">Bot Tennis</b><span style="margin-left:auto">' + chip('⚡ ' + tb + ' armat' + (tb > 1 ? 'i' : 'o'), 'paper') + '</span></div>' + S.TBOTS.map(botCard).join('') +
        S.panel('Equity bot (live)', S.spark([0, 0.2, 0.15, 0.4, 0.6, 0.55, 0.9, 1.15, 1.43], 300, 110, { label: 'Equity bot' }) + '<div class="foot">bloccato (lordo) <b class="pos">€1,15</b> · linea ambra = bloccato</div>', { icon: 'chart', right: '<b class="pos mono">€1,43</b>' }) +
        S.panel('Attività', S.C.activity([['10:41:20', 'cycle', 'paper', 'Tennis Pro · {"setup":"break_point","side":"BACK","ticks":5}'], ['10:39:02', 'scalp', 'paper', 'Tennis Pro · {"pnl":0.42}'], ['10:30:11', 'stop', 'amber', 'Tennis Pro · {"ticks":3}']]), { icon: 'pulse' }) + '</div>' +
        '<div class="col" style="gap:8px"><div class="row foot"><span class="chip paper" title="Canale LOCALE attivo (ws://127.0.0.1:47332)">⚡ LOCALE</span><span class="chip sky">J. Sinner</span>vs<span class="chip rose">J. Draper</span></div>' +
        (mode === 'OFF' ? '<div class="strip info">Ordini OFF — il runner tennis non accetta ordini (nemmeno simulati) e il ladder non mostra ordini/posizioni. Per la DEMO: imposta TENNIS_LIVE_ORDER_MODE=PAPER e riavvia il runner.</div>' : '') +
        S.ladderView({ id: 'tt', market: 'Match Odds', sels: ['J. Sinner', 'J. Draper'], ltps: [1.25, 5.0], mode: mode, sport: 'tennis', mine: true, tennis: true }) +
        '<p class="foot">Gli ordini in overlay (colonne <span style="color:var(--back)">B</span>/<span style="color:var(--lay)">L</span>) includono sia i tuoi ordini manuali sia quelli dei bot tennis. Trascina un ordine su un altro livello per spostarlo (annulla e ripiazza).</p></div>' +
        '<div class="col" style="gap:8px">' + stats() + '</div></div>';
      return h;
    }
  });
  S.on('t-mode', function (t) { S.ui.tOrderMode = t.dataset.v; S.rerender(); });
  S.on('t-rec', function () { S.ui.tRec = !S.ui.tRec; S.rerender(); S.toast(S.ui.tRec ? 'Registrazione ATTIVA' : 'Registrazione fermata', 'Il runner rilegge il flag ogni ~5 s.'); });
})();
