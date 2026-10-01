/* core.js - stato in memoria, router, helper, componenti comuni del prototipo.
   Nessun backend: tutto e' finto e vive in questa pagina. */
(function () {
  'use strict';
  window.addEventListener('error', function (e) { var b = document.createElement('pre'); b.id = 'errbox'; b.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:999;background:#300;color:#fcc;padding:8px;font-size:11px;max-width:90vw;white-space:pre-wrap'; b.textContent = 'ERRORE: ' + e.message + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno; document.body.appendChild(b); });
  var S = window.S = {
    route: 'board',
    sport: 'tutti',            // filtro della sidebar: tutti | calcio | tennis
    hideMoney: false,          // interruttore saldo nascosto
    tabs: {},                  // tab attiva per schermata
    ui: {},                    // stato locale delle schermate
    screens: {},               // registro schermate
    mounts: {}
  };

  /* ---------- formati (come lib/format.ts) ---------- */
  var MINUS = '−';
  S.MINUS = MINUS;
  S.money = function (v, o) {
    o = o || {};
    if (v == null || isNaN(v)) return '—';
    var d = o.decimals == null ? 2 : o.decimals;
    var a = Math.abs(v).toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d });
    var sign = v < 0 ? MINUS : (o.signed && v > 0 ? '+' : '');
    return '<span class="money">' + sign + a + ' €</span>';
  };
  S.odds = function (v) { return v == null ? '—' : Number(v).toFixed(2).replace('.', ','); };
  S.pct = function (v, d) { return v == null ? '—' : (v * 100).toFixed(d == null ? 1 : d).replace('.', ',') + ' %'; };
  S.num = function (v, d) { return v == null ? '—' : Number(v).toLocaleString('it-IT', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); };
  S.tone = function (v) { return v == null ? '' : v > 0 ? 'pos' : v < 0 ? 'neg' : 'mut'; };
  S.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };

  /* ---------- icone (tratto 1.6, 16px) ---------- */
  var P = {
    home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
    radar: 'M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0M12 12m-5 0a5 5 0 1 0 10 0 5 5 0 1 0-10 0M12 12l6-6',
    ball: 'M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0M12 7l4 3-1.5 5h-5L8 10z',
    tennis: 'M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0M5.5 5.5c3 3 3 10 0 13M18.5 5.5c-3 3-3 10 0 13',
    bot: 'M5 8h14v11H5zM12 4v4M9 13h.01M15 13h.01M9 16.5h6',
    omega: 'M5 20h4v-2a6 6 0 1 1 6 0v2h4',
    shield: 'M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z',
    target: 'M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0M12 12m-4 0a4 4 0 1 0 8 0 4 4 0 1 0-8 0M12 12h.01',
    bolt: 'M13 2 4 14h7l-1 8 9-12h-7z',
    eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0',
    eyeoff: 'M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6C3.7 8.4 2 12 2 12s3.5 7 10 7c1.9 0 3.5-.5 4.9-1.3',
    history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
    ladder: 'M7 3v18M17 3v18M7 7h10M7 11h10M7 15h10M7 19h10',
    grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
    pulse: 'M3 12h4l3-8 4 16 3-8h4',
    chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
    replay: 'M4 4v6h6M20 20v-6h-6M5 15a7 7 0 0 0 13 2M19 9A7 7 0 0 0 6 7',
    star: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z',
    book: 'M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3zM18 20H7a3 3 0 0 1 0-6h11',
    report: 'M6 3h9l5 5v13H6zM14 3v6h6M9 13h8M9 17h5',
    user: 'M12 8m-4 0a4 4 0 1 0 8 0 4 4 0 1 0-8 0M4 21a8 8 0 0 1 16 0',
    lock: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4',
    mail: 'M3 5h18v14H3zM3 6l9 7 9-7',
    menu: 'M4 6h16M4 12h16M4 18h16',
    side: 'M4 4h16v16H4zM9 4v16',
    stop: 'M6 6h12v12H6z',
    play: 'M7 5v14l11-7z',
    gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-2.7-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 15.4H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9c.3.6.9 1 1.5 1H21a2 2 0 1 1 0 4h-.1c-.6 0-1.2.4-1.5 1z',
    plug: 'M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5',
    wallet: 'M3 7h18v13H3zM3 7l3-4h12l3 4M16 13.5h.01',
    calendar: 'M4 5h16v16H4zM4 9h16M8 3v4M16 3v4',
    tv: 'M3 6h18v12H3zM8 21h8',
    popout: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
    swap: 'M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7',
    filter: 'M3 5h18l-7 8v6l-4 2v-8z',
    ext: 'M7 17 17 7M8 7h9v9',
    x: 'M6 6l12 12M18 6 6 18',
    chev: 'M9 6l6 6-6 6',
    flame: 'M12 3s5 4.5 5 9.5a5 5 0 0 1-10 0C7 9 9 7.5 9 7.5S10 10 12 10c0-3 0-7 0-7z',
    scale: 'M12 3v18M5 7h14M5 7l-3 7a3.5 3.5 0 0 0 6 0zM19 7l-3 7a3.5 3.5 0 0 0 6 0z',
    upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
    search: 'M11 11m-7 0a7 7 0 1 0 14 0 7 7 0 1 0-14 0M20 20l-4-4'
  };
  S.icon = function (n, cls) {
    return '<svg class="ic ' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + (P[n] || P.grid) + '"/></svg>';
  };

  /* ---------- registro schermate ---------- */
  // def: { id, path, title, group, render: fn -> html, mount?: fn(root) }
  S.reg = function (def) { S.screens[def.id] = def; };

  S.go = function (id, opts) {
    if (!S.screens[id]) id = 'notfound';
    S.route = id;
    if (opts && opts.tab) S.tabs[id] = opts.tab;
    try { if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id); } catch (e) {}
    S.render();
    var v = document.getElementById('view'); if (v) { v.scrollTop = 0; window.scrollTo(0, 0); }
    document.getElementById('app').classList.remove('mob');
  };

  S._iv = [];
  S.every = function (fn, ms) { S._iv.push(setInterval(fn, ms)); };
  S.render = function () {
    S._iv.forEach(clearInterval); S._iv = [];
    var d = S.screens[S.route];
    document.getElementById('sb').innerHTML = S.renderSidebar();
    document.getElementById('top').innerHTML = S.renderTop(d);
    var v = document.getElementById('view');
    v.innerHTML = d.render();
    document.body.classList.toggle('hidden-money', S.hideMoney);
    if (d.mount) d.mount(v);
    if (d.full) document.getElementById('app').dataset.full = '1'; else delete document.getElementById('app').dataset.full;
  };
  S.rerender = function () { var y = window.scrollY; S.render(); window.scrollTo(0, y); };

  /* ---------- tab ---------- */
  S.tab = function (scr, def) { return S.tabs[scr] || def; };
  S.tabbar = function (scr, items, def) {
    var cur = S.tab(scr, def);
    return '<div class="tabs" role="tablist">' + items.map(function (it) {
      return '<button role="tab" aria-selected="' + (cur === it[0]) + '" data-act="tab" data-scr="' + scr + '" data-v="' + it[0] + '">' + it[1] + (it[2] != null ? ' <span class="cnt">' + it[2] + '</span>' : '') + '</button>';
    }).join('') + '</div>';
  };

  /* ---------- micro componenti ---------- */
  S.kpi = function (k, v, s, tone, mark) {
    return '<div class="kpi"><div class="k">' + k + (mark ? ' ' + S.mk(mark) : '') + '</div><div class="v ' + (tone || '') + '">' + v + '</div>' + (s ? '<div class="s">' + s + '</div>' : '') + '</div>';
  };
  S.mk = function (m) { return '<span class="mk ' + m.toLowerCase() + '" title="Fonte della cifra: ' + m + '">' + m + '</span>'; };
  S.chip = function (t, c) { return '<span class="chip ' + (c || '') + '">' + t + '</span>'; };
  S.panel = function (title, body, o) {
    o = o || {};
    return '<section class="panel ' + (o.cls || '') + '"' + (o.id ? ' id="' + o.id + '"' : '') + '>' +
      '<div class="panel-h">' + (o.icon ? S.icon(o.icon) : '') + '<h3>' + title + '</h3>' + (o.count != null ? '<span class="cnt">' + o.count + '</span>' : '') +
      (o.note ? '<span class="note">' + o.note + '</span>' : '') + (o.right ? '<div class="r">' + o.right + '</div>' : '') + '</div>' +
      '<div class="panel-b' + (o.flush ? '" style="padding:0' : '') + '">' + body + '</div></section>';
  };
  S.sw = function (on, act, extra) { return '<button class="sw" role="switch" aria-checked="' + !!on + '" data-act="' + act + '" ' + (extra || '') + '></button>'; };
  S.oddsPair = function (b, l, name) {
    return '<span class="odds" title="' + S.esc(name || '') + '"><span class="o b" data-act="quote" data-side="BACK" data-p="' + b + '">' + S.odds(b) + '</span><span class="o l" data-act="quote" data-side="LAY" data-p="' + l + '">' + S.odds(l) + '</span></span>';
  };
  S.spark = function (pts, w, h, opt) {
    opt = opt || {}; w = w || 220; h = h || 48;
    var min = Math.min.apply(null, pts.concat([0])), max = Math.max.apply(null, pts.concat([0]));
    var rng = max - min || 1, pad = 4;
    var xy = pts.map(function (p, i) { return [pad + i * (w - 2 * pad) / (pts.length - 1), pad + (h - 2 * pad) * (1 - (p - min) / rng)]; });
    var line = xy.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var zero = pad + (h - 2 * pad) * (1 - (0 - min) / rng);
    var last = pts[pts.length - 1], col = last >= 0 ? 'var(--emerald)' : 'var(--red)';
    var area = line + ' L' + xy[xy.length - 1][0].toFixed(1) + ' ' + zero.toFixed(1) + ' L' + xy[0][0].toFixed(1) + ' ' + zero.toFixed(1) + 'Z';
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" role="img" aria-label="' + (opt.label || 'andamento') + '">' +
      '<line x1="0" x2="' + w + '" y1="' + zero + '" y2="' + zero + '" stroke="hsl(155 15% 50% / .35)" stroke-dasharray="3 3"/>' +
      '<path d="' + area + '" fill="' + col + '" opacity=".12"/><path d="' + line + '" fill="none" stroke="' + col + '" stroke-width="1.6"/>' +
      '<circle cx="' + xy[xy.length - 1][0] + '" cy="' + xy[xy.length - 1][1] + '" r="2.6" fill="' + col + '"/></svg>';
  };

  /* ---------- modali, conferme, fogli, toast ---------- */
  S.modal = function (o) {
    var L = document.getElementById('layer');
    L.innerHTML = '<div class="scrim" data-act="modal-close-bg"><div class="modal ' + (o.danger ? 'danger' : '') + '" role="dialog" aria-modal="true">' +
      '<div class="mh"><h3 style="font-size:16px">' + o.title + '</h3></div><div class="mb">' + o.body + '</div>' +
      '<div class="mf"><button class="btn" data-act="modal-close">' + (o.cancel || 'Annulla') + '</button>' +
      (o.ok ? '<button class="btn ' + (o.danger ? 'danger' : 'pri') + '" data-act="modal-ok">' + o.ok + '</button>' : '') + '</div></div></div>';
    S._modalOk = o.onOk || null;
    var b = L.querySelector('[data-act="modal-ok"]') || L.querySelector('[data-act="modal-close"]'); if (b) b.focus();
  };
  S.closeLayer = function () { document.getElementById('layer').innerHTML = ''; S._modalOk = null; };
  S.sheet = function (title, sub, body, okLabel, onOk) {
    var L = document.getElementById('layer');
    L.innerHTML = '<div class="scrim" data-act="modal-close-bg" style="place-items:stretch end;padding:0"><aside class="sheet" role="dialog" aria-modal="true">' +
      '<div class="sh"><h3 style="font-size:16px">' + title + '</h3><div class="foot" style="margin-top:4px">' + (sub || '') + '</div></div>' +
      '<div class="sbd">' + body + '</div><div class="sf"><button class="btn" data-act="modal-close">Chiudi</button>' +
      (okLabel ? '<button class="btn" data-act="toast" data-t="Parametri ripristinati ai default">Default</button><button class="btn pri" data-act="modal-ok">' + okLabel + '</button>' : '') + '</div></aside></div>';
    S._modalOk = onOk || function () { S.toast('Parametri salvati', 'Prototipo: nessun salvataggio reale.'); };
  };
  S.toast = function (t, d) {
    var box = document.getElementById('toasts'), el = document.createElement('div');
    el.className = 'toast'; el.innerHTML = '<b>' + t + '</b>' + (d ? '<span class="mut">' + d + '</span>' : '');
    box.appendChild(el); setTimeout(function () { el.remove(); }, 3200);
  };
  /* Conferma prima di passare a LIVE: stessa forma di LiveConfirmDialog */
  S.confirmLive = function (bot, onOk) {
    S.modal({
      danger: true, title: 'Passare a LIVE (soldi veri)?',
      body: '<p style="margin:0 0 8px"><b>' + bot + '</b> piazzerà ordini <b>veri</b> sul conto Betfair.</p>' +
        '<div class="strip live" style="font-size:11.5px">Le posizioni in prova restano in prova: soldi veri e prova non si sommano mai.</div>' +
        '<p class="foot" style="margin:10px 0 0">Promemoria del processo: il bot è certificato sul replay? Senza certificazione resta in prova.</p>',
      ok: 'Passa a LIVE', onOk: onOk
    });
  };

  /* ---------- delega dei click ---------- */
  S.actions = {};
  S.on = function (name, fn) { S.actions[name] = fn; };
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-act],[data-go]');
    if (!t) return;
    if (t.dataset.go) { e.preventDefault(); S.go(t.dataset.go, { tab: t.dataset.tab }); return; }
    var a = t.dataset.act;
    if (a === 'modal-close') { S.closeLayer(); return; }
    if (a === 'modal-close-bg') { if (e.target === t) S.closeLayer(); return; }
    if (a === 'modal-ok') { var f = S._modalOk; S.closeLayer(); if (f) f(); return; }
    if (a === 'tab') { S.tabs[t.dataset.scr] = t.dataset.v; S.rerender(); return; }
    if (a === 'toast') { S.toast(t.dataset.t, t.dataset.d || 'Prototipo: azione simulata, nessun ordine reale.'); return; }
    if (S.actions[a]) { e.preventDefault(); S.actions[a](t, e); }
  });
  document.addEventListener('submit', function (e) { e.preventDefault(); });
  document.addEventListener('change', function (e) { var t = e.target.closest('[data-chg]'); if (t && S.actions[t.dataset.chg]) S.actions[t.dataset.chg](t, e); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') S.closeLayer(); });
})();
