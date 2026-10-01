/* boot.js - sidebar, testata globale, avvio. */
(function () {
  'use strict';
  var S = window.S, D = window.D;

  /* La sidebar: OGNI rotta di App.tsx ha la sua voce. sport: 'c' calcio, 't' tennis, '' comune */
  var NAV = [
    { g: null, items: [
      ['board', 'Programma del giorno', 'home', ''],
      ['control-room', 'Control Room', 'radar', '', 'cr']
    ] },
    { g: 'Calcio', dot: 'hsl(155 84% 42%)', sport: 'c', items: [
      ['dashboard', 'Cruscotto partite', 'chart', 'c'],
      ['omega', 'Omega', 'omega', 'c', 'omega'],
      ['safe-strategy', 'Safe Strategy', 'shield', 'c', 'safe'],
      ['mike', 'Mike', 'target', 'c', 'mike'],
      ['segui-live', 'Segui live · Scalper', 'pulse', 'c', 'scalper'],
      ['storico-calcio', 'Storico calcio', 'history', 'c']
    ] },
    { g: 'Tennis', dot: 'hsl(45 93% 55%)', sport: 't', items: [
      ['tennis', 'Dashboard tennis', 'tennis', 't'],
      ['tennis-terminal', 'Tennis Terminal', 'ladder', 't'],
      ['tennis-terminal', 'Bot tennis (4)', 'bot', 't', 'tbot', 'bot'],
      ['safe-strategy', 'Safe Strategy · Tennis', 'shield', 't', null, 'tennis'],
      ['storico-tennis', 'Storico tennis', 'history', 't']
    ] },
    { g: 'Trading', items: [
      ['multi-ladder', 'Multi-ladder', 'grid', ''],
      ['ladder-popout', 'Ladder pop-out', 'popout', ''],
      ['market-watch', 'Market watch', 'eye', ''],
      ['live-pnl', 'Live P&L', 'wallet', ''],
      ['watchlist', 'Watchlist', 'star', '']
    ] },
    { g: 'Analisi', items: [
      ['match-replay', 'Match replay', 'replay', ''],
      ['analytics', 'Analytics', 'chart', ''],
      ['report-personale', 'Report personale', 'report', ''],
      ['trade-journal', 'Trade journal', 'book', '']
    ] },
    { g: 'Account', items: [
      ['select-sport', 'Scelta sport', 'swap', ''],
      ['landing', 'Accesso', 'lock', ''],
      ['check-email', 'Conferma email', 'mail', ''],
      ['reset-password', 'Reimposta password', 'lock', ''],
      ['notfound', 'Pagina non trovata', 'x', '']
    ] }
  ];
  S.NAV = NAV;

  function botTag(key) {
    if (!key) return '';
    if (key === 'cr') return D.liveCount() ? '<span class="tag chip live" style="height:16px">' + D.liveCount() + ' LIVE</span>' : '';
    var b = D.botMode[key]; if (!b) return '';
    if (!b.running) return '<span class="tag chip" style="height:16px">FERMO</span>';
    return '<span class="tag chip ' + (b.mode === 'LIVE' ? 'live' : 'paper') + '" style="height:16px">' + (b.mode === 'LIVE' ? 'LIVE' : 'PROVA') + '</span>';
  }

  S.renderSidebar = function () {
    var cur = S.route, h = '';
    h += '<div class="sb-brand"><div class="logo">AI</div><div class="brand-t">AI <b>TERMINAL</b></div></div>';
    h += '<div class="sb-sport" role="group" aria-label="Sport nella barra">' + [['tutti', 'Tutti'], ['calcio', '⚽ Calcio'], ['tennis', '🎾 Tennis']].map(function (x) {
      return '<button data-act="sb-sport" data-v="' + x[0] + '" aria-pressed="' + (S.sport === x[0]) + '">' + x[1] + '</button>';
    }).join('') + '</div>';
    h += '<nav class="sb-nav">';
    NAV.forEach(function (grp) {
      if (grp.sport === 'c' && S.sport === 'tennis') return;
      if (grp.sport === 't' && S.sport === 'calcio') return;
      h += '<div class="sb-g">';
      if (grp.g) h += '<div class="sb-gt">' + (grp.dot ? '<i class="dot" style="background:' + grp.dot + '"></i>' : '') + '<span>' + grp.g + '</span></div>';
      grp.items.forEach(function (it) {
        var active = cur === it[0] && (!it[5] || S.tab(it[0]) === it[5]) && !(it[0] === 'safe-strategy' && !it[5] && S.tab('safe-strategy') === 'tennis');
        h += '<a class="it" href="#' + it[0] + '" data-go="' + it[0] + '"' + (it[5] ? ' data-tab="' + it[5] + '"' : '') + (active ? ' aria-current="page"' : '') + ' title="' + it[1] + '">' + S.icon(it[2]) + '<span>' + it[1] + '</span>' + botTag(it[4]) + '</a>';
      });
      h += '</div>';
    });
    h += '</nav>';
    h += '<div class="sb-foot"><div class="avatar">DR</div><div class="who" style="min-width:0"><div style="font-size:12px;font-weight:600">Daniele R.</div><div class="foot">Betfair.it · sessione attiva</div></div>' +
      '<button class="iconbtn" style="margin-left:auto" data-act="sb-collapse" title="Comprimi la barra">' + S.icon('side') + '</button></div>';
    return h;
  };

  S.renderTop = function (d) {
    var o = S.ui.top || '';
    var ch = D.channels, on = ch.filter(function (c) { return c.on; }).length;
    var h = '<button class="iconbtn" data-act="mob-menu" title="Menu" style="display:none" id="mobbtn">' + S.icon('menu') + '</button>';
    h += '<div class="crumb"><small>' + (d.group || '') + '</small><b>' + d.title + '</b></div><div class="sp"></div>';
    // runner calcio / tennis
    h += '<div class="stat hide-s" data-act="top-pop" data-v="runner" title="Runner e canali locali">' +
      '<span class="led ' + (D.runner.calcio ? 'on' : 'off') + '"></span><span class="l">Runner</span> ⚽' +
      '<span class="led ' + (D.runner.tennis ? 'on' : 'off') + '" style="margin-left:4px"></span>🎾' +
      '<span class="l" style="margin-left:6px">Canali</span> <b class="num">' + on + '/' + ch.length + '</b>' +
      (o === 'runner' ? S.popRunner() : '') + '</div>';
    // modalita' ordini: riepilogo per bot (la scelta resta dentro ogni bot)
    var lc = D.liveCount();
    h += '<div class="stat" data-act="top-pop" data-v="mode" title="Modalità ordini dei bot">' +
      '<span class="led ' + (lc ? 'live' : 'on') + '"></span><span class="l">Ordini</span> ' +
      (lc ? '<b style="color:#fca5a5">' + lc + ' LIVE</b><span class="l">·</span><b style="color:#6ee7b7">' + D.paperCount() + ' PROVA</b>' : '<b style="color:#6ee7b7">tutti in PROVA</b>') +
      (o === 'mode' ? S.popMode() : '') + '</div>';
    // saldo del conto (CONTO) con occhio
    h += '<div class="stat" title="Saldo disponibile sul conto Betfair (fonte: CONTO)">' + S.mk('CONTO') +
      '<b class="num">' + S.money(D.conto.disponibile) + '</b><span class="l hide-s">esp.</span><b class="num ora hide-s">' + S.money(D.conto.esposizione) + '</b>' +
      '<button class="btn ghost sm" data-act="hide-money" title="' + (S.hideMoney ? 'Mostra' : 'Nascondi') + ' le cifre" aria-pressed="' + S.hideMoney + '" style="padding:0 2px;height:20px">' + S.icon(S.hideMoney ? 'eyeoff' : 'eye') + '</button></div>';
    return h;
  };

  S.popRunner = function () {
    return '<div class="pop" data-act="noop"><h4>Runner e canali locali (ws://127.0.0.1)</h4>' +
      '<div class="row"><span class="led ' + (D.runner.calcio ? 'on' : 'off') + '"></span>Runner calcio<span class="r">' + (D.runner.calcio ? 'connesso · stream' : 'spento') + '</span></div>' +
      '<div class="row"><span class="led ' + (D.runner.tennis ? 'on' : 'off') + '"></span>Runner tennis<span class="r">' + (D.runner.tennis ? 'connesso · stream' : 'spento') + '</span></div><div class="sep"></div>' +
      D.channels.map(function (c) { return '<div class="row"><span class="led ' + (c.on ? 'on' : 'off') + '"></span>' + c.name + '<span class="r mono">:' + c.port + '</span></div>'; }).join('') +
      '<p class="foot" style="margin:8px 6px 2px">I runner li avvia l’app desktop; se un canale è spento la schermata lo dice, non mostra dati vecchi.</p></div>';
  };
  S.popMode = function () {
    return '<div class="pop" data-act="noop"><h4>Modalità ordini per bot</h4>' +
      Object.keys(D.botMode).filter(function (k) { return k !== 'cr'; }).map(function (k) {
        var b = D.botMode[k];
        return '<div class="row" data-go="' + b.route + '" style="cursor:pointer">' + b.name + '<span class="r">' + (b.running ? '' : 'fermo · ') + '</span>' + S.chip(b.mode === 'LIVE' ? 'LIVE · soldi veri' : 'PAPER · prova', b.mode === 'LIVE' ? 'live' : 'paper') + '</div>';
      }).join('') + '<p class="foot" style="margin:8px 6px 2px">La modalità si cambia dentro ogni bot, con conferma per LIVE.</p></div>';
  };

  S.on('sb-sport', function (t) { S.sport = t.dataset.v; S.rerender(); });
  S.on('sb-collapse', function () { document.getElementById('app').classList.toggle('collapsed'); });
  S.on('mob-menu', function () { document.getElementById('app').classList.toggle('mob'); });
  S.on('hide-money', function () { S.hideMoney = !S.hideMoney; S.rerender(); });
  S.on('top-pop', function (t, e) { if (e.target.closest('.pop')) return; S.ui.top = S.ui.top === t.dataset.v ? '' : t.dataset.v; S.rerender(); });
  S.on('noop', function () {});
  document.addEventListener('click', function (e) { if (S.ui.top && !e.target.closest('.stat')) { S.ui.top = ''; S.rerender(); } });

  var start = (location.hash || '').slice(1);
  S.go(S.screens[start] ? start : 'board');
  var mq = window.matchMedia('(max-width:760px)');
  function mob() { var b = document.getElementById('mobbtn'); if (b) b.style.display = mq.matches ? 'grid' : 'none'; }
  mob(); mq.addEventListener && mq.addEventListener('change', mob);
  var orig = S.render; S.render = function () { orig(); mob(); };
})();
