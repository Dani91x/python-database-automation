/* s_account.js - Accesso (landing), Scelta sport, Conferma email, Reimposta password, 404.
   Pagine fuori dalla shell: si vedono a tutto schermo come oggi. */
(function () {
  'use strict';
  var S = window.S;
  var back = '<a class="btn sm backproto" data-go="board" href="#board">' + '← Torna al prototipo</a>';
  var wrap = function (inner, max) { return '<div style="min-height:100vh;display:grid;place-items:center;padding:32px 16px;background:radial-gradient(circle at 50% 0%, hsl(155 84% 42% / .14), transparent 60%)"><div style="width:min(' + (max || 520) + 'px,100%)">' + inner + '</div></div>' + back; };

  /* ---------- Landing / accesso ---------- */
  S.reg({
    id: 'landing', title: 'Accesso', group: 'Account', full: true,
    render: function () {
      var authTab = S.tab('landing', 'reg');
      var f = function (id, label, ph, type) { return '<label class="field" for="' + id + '">' + label + '<input id="' + id + '" type="' + (type || 'text') + '" placeholder="' + ph + '"></label>'; };
      var h = '<div style="max-width:1120px;margin:0 auto;padding:0 20px">';
      // Hero
      h += '<header class="row" style="justify-content:space-between;padding:18px 0"><div class="row"><div class="logo">AS</div><b style="font:800 16px var(--f-display)">Alpha <span class="prim">Score</span></b></div>' +
        '<div class="row"><button class="btn ghost" data-act="scroll-auth">Login</button><button class="btn" title="Oggi il bottone non ha azione">Register</button></div></header>';
      h += '<section style="padding:64px 0 48px;display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:32px;align-items:center" class="land-hero">' +
        '<div class="col" style="gap:16px"><span class="chip">Data-Driven Football Analysis</span><h1 style="font-size:56px;font-weight:800;line-height:1">Alpha <span class="prim">Score</span></h1>' +
        '<p style="font:600 22px var(--f-display);margin:0">Non scommettere. <span class="gold">Investi.</span></p>' +
        '<p class="mut" style="max-width:56ch;margin:0">Il primo algoritmo a <b>3 Livelli</b> che trasforma le scommesse in asset finanziari. Smetti di giocare d’azzardo. Inizia ad operare con metodo.</p>' +
        '<div class="row"><button class="btn pri" data-act="scroll-auth">INIZIA ORA</button><button class="btn ghost" data-act="scroll-auth">Accedi alla Dashboard</button></div></div>' +
        '<div class="panel" style="aspect-ratio:4/3;max-width:100%;display:grid;place-items:center;background:radial-gradient(circle at 60% 40%, hsl(155 84% 42% / .25), transparent 60%),hsl(var(--card))"><span class="foot">immagine di sfondo del pallone (asset esistente)</span></div></section>';
      // StatsBar
      h += '<section class="panel flat" style="padding:16px"><div class="grid g4">' + [['50.000+', 'Pronostici Generati'], ['87%', 'Accuratezza Media'], ['120+', 'Campionati Analizzati'], ['Real-Time', 'Aggiornamento Dati']].map(function (x) { return '<div><div style="font:800 24px var(--f-display)" class="prim">' + x[0] + '</div><div class="foot">' + x[1] + '</div></div>'; }).join('') + '</div><p class="foot" style="margin:10px 0 0">* Valori dimostrativi basati su backtesting storico</p></section>';
      // SystemWorkflow
      h += '<section style="padding:48px 0 0"><h2 style="font-size:28px;text-align:center">Il Protocollo <span class="prim">Alpha</span></h2><p class="mut" style="text-align:center;max-width:60ch;margin:8px auto 20px">Non ci fidiamo di un solo modello. Processiamo ogni partita attraverso <b>3 livelli di validazione</b> prima di darti un consiglio.</p><div class="grid g3">' +
        [['1', 'Livello 1: L’Algoritmo', 'Deep Data Analysis', 'Analisi di 200+ metriche: xG, Poisson, Form State e trend statistici puri.'], ['2', 'Livello 2: La Storia', 'Historical Validation', 'Il database confronta il pronostico con 10 anni di storico: è già successo? Con che esito?'], ['3', 'Livello 3: Il verdetto', 'AI Financial Advisor', 'L’AI confronta i dati dell’algoritmo con i dati storici e news in tempo reale come infortuni, meteo, o imprevisti dell’ultimo minuto e ti consiglia le scelte statisticamente più probabili per quello specifico evento.']]
          .map(function (x) { return '<div class="panel" style="padding:16px"><div class="chip gold">' + x[0] + '</div><h3 style="font-size:15px;margin-top:10px">' + x[1] + '</h3><div class="lbl" style="margin:4px 0 8px">' + x[2] + '</div><p class="mut" style="margin:0;font-size:12px">' + x[3] + '</p></div>'; }).join('') + '</div></section>';
      // FeaturesGrid
      h += '<section style="padding:48px 0 0"><h2 style="font-size:28px;text-align:center">Perché Alpha Score?</h2><p class="mut" style="text-align:center;max-width:64ch;margin:8px auto 20px">Non siamo un altro sito di statistiche. Siamo il tuo vantaggio competitivo. Saprai esattamente come affrontare ogni investimento con i dati dalla tua</p><div class="grid g4">' +
        [['Edge Matematico', 'Algoritmo + Database + Intelligenza Artificiale, nessuna opinione personale solo dati e scelte consapevoli.'], ['Copertura Globale', '1200+ Campionati monitorati H24. Dalla Premier League alla Serie B brasiliana, non ti perdi mai un’occasione di profitto.'], ['Gestione del Rischio', 'Il sistema a 3 livelli filtra i falsi positivi. Non cerchiamo di indovinare tutto, ma di proteggere il tuo capitale nel lungo periodo.'], ['Risparmio di Tempo', 'Da 4 ore di studio a 30 secondi. Tu devi solo decidere l’investimento, a tutta l’analisi complessa ci pensiamo noi.']]
          .map(function (x) { return '<div class="panel" style="padding:16px"><h3 style="font-size:14px">' + x[0] + '</h3><p class="mut" style="margin:8px 0 0;font-size:12px">' + x[1] + '</p></div>'; }).join('') + '</div></section>';
      // DashboardPreview
      h += '<section style="padding:48px 0 0"><div class="panel land-prev" style="padding:20px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px"><div><h2 style="font-size:22px">Una Dashboard Completa<br><span class="prim">Per Ogni Partita</span></h2><ul style="padding-left:18px;color:hsl(var(--foreground)/.85);line-height:1.9">' +
        ['Pronostico AI con advice e percentuali 1X2', 'Statistiche dettagliate Home vs Away', 'Grafici goals by minute e cards heatmap', 'Confronto squadre con matrice comparativa', 'Distribuzione Under/Over per soglia', 'Head-to-Head e ultimi 5 match'].map(function (x) { return '<li>' + x + '</li>'; }).join('') +
        '</ul></div><div class="panel flat" style="padding:16px"><div class="row" style="justify-content:center"><span class="home-b chip" style="color:hsl(var(--primary))">HOME</span><b>VS</b><span class="chip gold">AWAY</span></div><div class="grid g3" style="margin:14px 0">' +
        [['1', '45%'], ['X', '28%'], ['2', '27%']].map(function (x) { return '<div class="kpi" style="text-align:center"><div class="k" style="justify-content:center">' + x[0] + '</div><div class="v">' + x[1] + '</div></div>'; }).join('') +
        '</div>' + [75, 60, 85].map(function (v) { return '<div class="bar" style="margin:8px 0"><i style="width:' + v + '%"></i></div>'; }).join('') + '<p class="foot">Preview dimostrativa</p></div></div></section>';
      // Pricing
      h += '<section style="padding:48px 0 0;display:grid;place-items:center"><div class="panel" style="padding:24px;width:min(380px,100%);border-color:hsl(var(--secondary)/.5)"><span class="chip gold">PROVA GRATUITA</span><div style="font:800 40px var(--f-display);margin-top:10px">€0</div><div class="foot">per 7 giorni, poi €9.99/mese</div><ul style="padding-left:18px;line-height:1.9;font-size:12.5px">' +
        ['Accesso completo alla dashboard AI', 'Pronostici illimitati', 'Tutti i campionati', 'Aggiornamenti in tempo reale', 'Grafici e heatmap interattivi', 'Supporto via Telegram'].map(function (x) { return '<li>' + x + '</li>'; }).join('') + '</ul><button class="btn pri" style="width:100%;justify-content:center" data-act="scroll-auth">Registrati Ora</button></div></section>';
      // Auth
      h += '<section id="auth-section" style="padding:48px 0;display:grid;place-items:center"><div class="panel" style="width:min(460px,100%)">' +
        '<div class="tabs" role="tablist" style="padding:0 10px"><button role="tab" aria-selected="' + (authTab === 'reg') + '" data-act="tab" data-scr="landing" data-v="reg">Registrati</button><button role="tab" aria-selected="' + (authTab === 'log') + '" data-act="tab" data-scr="landing" data-v="log">Accedi</button></div><form class="panel-b col" style="gap:10px">';
      if (authTab === 'reg') {
        h += '<div class="grid g2">' + f('r-nome', 'Nome *', 'Mario') + f('r-cogn', 'Cognome *', 'Rossi') + '</div>' + f('r-mail', 'Email *', 'mario@email.com', 'email') + f('r-tel', 'Telefono *', '+39 333 1234567', 'tel') + f('r-tg', 'Telegram (opzionale)', '@username') + f('r-pw', 'Password *', 'Min. 8 caratteri', 'password') + f('r-pw2', 'Conferma Password *', 'Ripeti password', 'password') +
          '<label class="row" style="font-size:12px"><input type="checkbox" id="r-tos"> Accetto i Termini e Condizioni e la Privacy Policy</label><button class="btn pri" style="justify-content:center" data-act="early">Inizia la Prova Gratuita</button>';
      } else {
        h += f('l-mail', 'Email', 'mario@email.com', 'email') + f('l-pw', 'Password', 'La tua password', 'password') + '<a class="foot" style="text-align:right;cursor:pointer" data-act="toast" data-t="Email di reset inviata!" data-d="Controlla la tua casella di posta (anche Spam).">Password dimenticata?</a><button class="btn pri" style="justify-content:center" data-go="select-sport">Accedi</button>';
      }
      h += '</form></div></section><footer class="row" style="justify-content:space-between;padding:20px 0 60px;border-top:1px solid hsl(var(--border))"><span class="foot">© 2025 Alpha Score — Don’t bet. Invest.</span><span class="foot">Privacy Policy · Termini · Contatti</span></footer></div>';
      return h + back;
    }
  });
  S.on('scroll-auth', function () { var el = document.getElementById('auth-section'); if (el) el.scrollIntoView({ behavior: 'smooth' }); });
  S.on('early', function () { S.modal({ title: 'Non siamo ancora pronti', body: 'Ti avviseremo quando lo sapremo! Per tutte le info segui le nostre pagine social.', cancel: 'Ho capito' }); });

  /* ---------- Scelta sport ---------- */
  S.reg({
    id: 'select-sport', title: 'Scegli lo sport', group: 'Account',
    render: function () {
      var cards = [['dashboard', '⚽', 'Football', 'Partite del Giorno · motori AI · trading live', 'prim'], ['tennis', '🎾', 'Tennis', 'Betfair Exchange · ladder pro · bot trading', 'gold'], ['omega', 'Ω', 'Omega', 'Correct Score · obiettivo €/giorno · set-and-forget', 'prim'], ['safe-strategy', '🛡️', 'Safe Strategy', 'Segnali live calcio + tennis · ingresso sempre manuale', 'gold'], ['mike', '🎯', 'Mike', 'Under 3.5 / Over 4.5 · green-up e cash-out · paper-first', 'tealc']];
      return '<div class="ph"><div><h1>Scegli lo <em>sport</em></h1><p>Seleziona il terminale operativo su cui vuoi lavorare.</p></div><div class="act"><span class="foot">daniele.r…@gmail.com</span><button class="btn gold" data-go="control-room">CONTROL ROOM</button><button class="btn" data-go="landing">Esci</button></div></div>' +
        '<div class="grid g5">' + cards.map(function (c) {
          return '<a class="panel" href="#' + c[0] + '" data-go="' + c[0] + '" style="text-decoration:none;padding:18px;display:flex;flex-direction:column;gap:10px" aria-label="Apri sezione ' + c[2] + '"><div style="width:56px;height:56px;border-radius:14px;display:grid;place-items:center;font-size:26px;background:hsl(var(--muted));border:1px solid hsl(var(--border))">' + c[1] + '</div><h3 style="font-size:16px">' + c[2] + '</h3><p class="mut" style="margin:0;font-size:12px;flex:1">' + c[3] + '</p><span class="' + c[4] + '" style="font-weight:700;font-size:12px">Entra →</span></a>';
        }).join('') + '</div><p class="foot">© 2026 Alpha Score AI. All rights reserved.</p>' +
        '<div class="strip info"><span class="lbl">Nel redesign</span><span>la scelta resta come oggi ma la sidebar porta ovunque: la Control Room e il Programma sono sempre a un click.</span></div>';
    }
  });

  /* ---------- Conferma email ---------- */
  S.reg({
    id: 'check-email', title: 'Controlla la tua email', group: 'Account', full: true,
    render: function () {
      return wrap('<div class="panel" style="padding:28px;text-align:center"><div style="width:64px;height:64px;margin:0 auto 14px;border-radius:50%;display:grid;place-items:center;background:hsl(var(--primary)/.14);color:hsl(var(--primary))">' + S.icon('mail') + '</div>' +
        '<h1 style="font-size:24px">Controlla la tua email</h1><p class="mut">Ti abbiamo inviato un link di conferma. Clicca sul link per attivare il tuo account.</p><div class="col" style="text-align:left;margin:18px 0">' +
        [['Apri la tua casella di posta', 'Cerca l’email di conferma'], ['Clicca su “Conferma Email”', 'Si aprirà una pagina di conferma'], ['Accedi alla Dashboard', 'Il tuo account è pronto!']].map(function (x, i) { return '<div class="row" style="flex-wrap:nowrap"><span class="chip gold">' + (i + 1) + '</span><div><b style="font-size:13px">' + x[0] + '</b><div class="foot">' + x[1] + '</div></div></div>'; }).join('') +
        '</div><div class="strip warn" style="justify-content:center">Non trovi l’email? Controlla la cartella <b>Spam</b> o <b>Promozioni</b>.</div><div class="row" style="justify-content:center;margin-top:16px"><button class="btn pri" data-go="landing">Torna alla Home</button><button class="btn" data-go="landing">Non hai ricevuto l’email?</button></div></div>');
    }
  });

  /* ---------- Reimposta password (3 stati) ---------- */
  S.reg({
    id: 'reset-password', title: 'Reimposta password', group: 'Account', full: true,
    render: function () {
      var st = S.tab('reset-password', 'ready'), body;
      if (st === 'checking') body = '<p class="mut" style="text-align:center">Verifica del link in corso…</p>';
      else if (st === 'invalid') body = '<h1 style="font-size:22px">Link non valido o scaduto</h1><div class="strip warn" style="margin:12px 0">Il link di reset è scaduto o è stato già usato. Richiedine uno nuovo dalla schermata di accesso con “Password dimenticata?”.</div><button class="btn pri" data-go="landing">Torna al login</button>';
      else body = '<h1 style="font-size:22px">Imposta nuova password</h1><p class="mut">Scegli una nuova password per il tuo account.</p><form class="col"><label class="field" for="np1">Nuova password<input id="np1" type="password" placeholder="Min. 8 caratteri"></label><label class="field" for="np2">Conferma password<input id="np2" type="password" placeholder="Ripeti password"></label><button class="btn pri" style="justify-content:center" data-act="toast" data-t="Password aggiornata!" data-d="Ora puoi accedere con la nuova password.">Salva nuova password</button></form>';
      return wrap('<div class="row" style="justify-content:center;margin-bottom:10px"><span class="lbl">Prototipo · stato</span><div class="seg">' + [['checking', 'verifica'], ['invalid', 'scaduto'], ['ready', 'pronto']].map(function (x) { return '<button data-act="tab" data-scr="reset-password" data-v="' + x[0] + '" aria-pressed="' + (st === x[0]) + '">' + x[1] + '</button>'; }).join('') + '</div></div><div class="panel" style="padding:26px">' + body + '</div>', 440);
    }
  });

  /* ---------- 404 ---------- */
  S.reg({
    id: 'notfound', title: 'Pagina non trovata', group: 'Account', full: true,
    render: function () {
      return wrap('<div style="text-align:center"><div class="ora" style="font:800 72px var(--f-display)">404</div><p class="mut">La pagina che stai cercando non esiste o è stata spostata.</p><button class="btn gold" data-go="landing">Torna alla Home</button></div>', 420);
    }
  });
})();
