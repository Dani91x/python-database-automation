/* s_home.js - Programma del giorno (/board): stessi contenuti di oggi, nuova veste. */
(function () {
  'use strict';
  var S = window.S, D = window.D;

  /* pulsante diviso Video | Stats (BetfairMediaButtons) */
  S.media = function (compact) {
    return '<span class="seg" style="padding:1px" title="Pop-out ufficiale Betfair">' +
      '<button data-act="toast" data-t="Video live Betfair" data-d="Si apre il pop-out ufficiale dell’Exchange (finestra 640×780).">' + S.icon('tv') + (compact ? '' : ' Video') + '</button>' +
      '<button data-act="toast" data-t="Statistiche partita Betfair" data-d="Si apre il pop-out ufficiale (Statistiche + Visualizzazione partita).">' + S.icon('chart') + (compact ? '' : ' Stats') + '</button></span>';
  };

  function oddsCell(s) {
    return '<div style="display:flex;flex-direction:column;align-items:center;gap:2px;min-width:92px">' +
      '<span class="foot" style="max-width:96px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + s.name + '">' + s.name + '</span>' +
      '<span class="odds"><span class="o b" style="cursor:default">' + S.odds(s.back) + '</span><span class="o l" style="cursor:default">' + S.odds(s.lay) + '</span></span></div>';
  }

  function rows(sport) {
    var st = S.ui.boardState || 'dati';
    var port = sport === 'calcio' ? 47331 : 47332;
    if (st === 'off') return '<div class="empty">' + S.icon('plug') + '<p style="margin:6px 0 0">Canale locale ' + sport + ' non attivo (ws://127.0.0.1:' + port + '). Avvia l’app desktop / il runner ' + sport + ' per il programma in tempo reale.</p></div>';
    if (st === 'attesa') return '<div class="empty">Canale connesso: in attesa del primo tabellone…</div>';
    if (st === 'vuoto') return '<div class="empty">Nessun evento nel programma di oggi.</div>';
    var list = (sport === 'calcio' ? D.boardCalcio : D.boardTennis).slice().sort(function (a, b) { return Date.parse(a.open) - Date.parse(b.open); });
    var h = '<div class="tbl-w"><table class="t" style="font-size:12px"><thead><tr><th style="width:92px">Orario</th><th>Evento</th><th style="text-align:center">' + (sport === 'calcio' ? 'Match Odds · 1 X 2 (back / lay)' : 'Match Odds · testa a testa (back / lay)') + '</th><th class="r">Azioni</th></tr></thead><tbody>';
    list.forEach(function (r) {
      var cd = r.inplay ? null : D.countdown(r.open);
      var foll = S.ui.followed && S.ui.followed[r.id];
      h += '<tr><td><div class="clock">' + D.hhmm(r.open) + '</div>' +
        (r.inplay ? '<span class="chip inplay" style="height:17px;margin-top:2px"><span class="led live" style="background:var(--emerald);width:6px;height:6px"></span>IN-PLAY</span>'
          : cd ? '<div class="amb mono" style="font-size:10.5px" title="Countdown all’off">OFF in <span data-cd="' + r.open + '">' + cd + '</span></div>' : '') + '</td>' +
        '<td style="white-space:normal;min-width:180px"><div class="match"><b title="' + r.name + '">' + r.name + '</b><small class="mono">' + r.status + ' · €' + r.matched.toLocaleString('it-IT') + ' abbinati</small></div></td>' +
        '<td><div class="row" style="justify-content:center;gap:6px;flex-wrap:nowrap">' + r.sels.map(oddsCell).join('') + '</div></td>' +
        '<td class="r"><div class="row" style="justify-content:flex-end;flex-wrap:nowrap">' +
        (sport === 'tennis'
          ? '<button class="btn sm ' + (foll ? 'teal' : 'pri') + '" data-act="follow-t" data-id="' + r.id + '" title="Registra l’evento al follow tennis: il runner lo prende in carico">' + (foll ? '✓ Seguito' : 'Segui live') + '</button>' +
            '<a class="btn sm" data-go="tennis-terminal" href="#tennis-terminal" title="Apri il Tennis Trading Terminal su questo match">Terminal ' + S.icon('chev') + '</a>'
          : '<a class="btn sm" data-go="segui-live" href="#segui-live" title="I follow calcio nascono da watchlist/runner: si apre Segui live">Segui live ' + S.icon('chev') + '</a>') +
        S.media(true) + '</div></td></tr>';
    });
    return h + '</tbody></table></div>';
  }

  S.reg({
    id: 'board', title: 'Programma del giorno', group: 'Home',
    render: function () {
      var sport = S.tab('board', 'calcio');
      var tab = function (k, label, list, on) {
        return '<button role="tab" aria-selected="' + (sport === k) + '" data-act="tab" data-scr="board" data-v="' + k + '">' + label +
          ' <span class="led ' + (on ? 'on' : 'off') + '" title="' + (on ? 'Canale locale connesso' : 'Canale locale non attivo') + '"></span><span class="cnt">' + list.length + '</span></button>';
      };
      return '<div class="ph"><div><h1>Programma di <em>oggi</em></h1><p>Tabellone in tempo reale dal canale locale del runner (push ‘board’, nessuna lettura DB). Ordinato per orario d’inizio.</p></div>' +
        '<div class="act"><span class="lbl">Prototipo · stato del canale</span><div class="seg" role="group">' +
        ['dati', 'attesa', 'vuoto', 'off'].map(function (x) { return '<button data-act="board-state" data-v="' + x + '" aria-pressed="' + ((S.ui.boardState || 'dati') === x) + '">' + { dati: 'con dati', attesa: 'in attesa', vuoto: 'vuoto', off: 'canale off' }[x] + '</button>'; }).join('') + '</div></div></div>' +
        '<section class="panel flat"><div class="tabs" role="tablist" style="padding:0 8px">' + tab('calcio', '⚽ Calcio', D.boardCalcio, D.runner.calcio) + tab('tennis', '🎾 Tennis', D.boardTennis, D.runner.tennis) + '</div>' +
        rows(sport) + '</section>' +
        '<p class="foot">Il prezzo è al tick del runner. Le quote back sono azzurre, le lay rosa, come sull’Exchange.</p>';
    },
    mount: function () {
      S.every(function () {
        document.querySelectorAll('[data-cd]').forEach(function (el) { var c = D.countdown(el.dataset.cd); el.textContent = c || '00:00'; });
      }, 1000);
    }
  });
  S.on('board-state', function (t) { S.ui.boardState = t.dataset.v; S.rerender(); });
  S.on('follow-t', function (t) {
    S.ui.followed = S.ui.followed || {};
    if (S.ui.followed[t.dataset.id]) return;
    S.ui.followed[t.dataset.id] = true; S.rerender();
    S.toast('Evento registrato al follow tennis', 'Prototipo: nessuna RPC chiamata.');
  });
})();
