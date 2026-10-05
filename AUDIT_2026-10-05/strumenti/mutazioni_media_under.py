"""Falsificazione della modalita' «media under» (05/10/2026).

Per ogni mutazione: applica UNA sostituzione di testo al codice (deve comparire
esattamente una volta), lancia i test, conta i rossi, ripristina il file con
``git checkout -- <file>`` (mai a memoria) e verifica ``git diff --quiet``.

Uso (dalla radice del repo, albero pulito):
    python AUDIT_2026-10-05/strumenti/mutazioni_media_under.py [id ...]

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import re
import subprocess
import sys
from typing import List, Tuple

MU = "Betfair/stream/scalper/media_under_bot.py"
SS = "Betfair/stream/scalper/scalper_session.py"
AM = "Betfair/stream/scalper/auto_mode.py"
CE = "Betfair/stream/scalper/certificazione.py"
RR = "Betfair/stream/scalper/tools/replay_registrazioni.py"
RB = "Betfair/stream/backtest/registro_bot.py"
TS = "frontend/src/lib/mediaUnder.ts"
SP = "frontend/src/components/live/ScalperPanel.tsx"

PY = ["python", "-m", "pytest", "Betfair/stream/tests/test_scalper_media_under_2026_10_05.py",
      "-q", "-p", "no:cacheprovider", "-p", "no:randomly"]
VT = ["npx", "vitest", "run", "src/lib/mediaUnder.test.ts",
      "src/components/live/ScalperPanel.test.tsx"]

# (id, file, vecchio, nuovo, descrizione, suite)
MUTAZIONI: List[Tuple[str, str, str, str, str, str]] = [
    ("U1", MU, '''    return (float(c) * (float(t_lordo) - pos.se_perde)
            - (pos.se_vince - pos.se_perde)) / (float(q) - float(c))''',
     '''    return (float(c) * (float(t_lordo) - pos.se_perde)
            - (pos.se_vince + pos.se_perde)) / (float(q) - float(c))''',
     "formula del rientro con il segno sbagliato", "py"),
    ("U2", MU, 'quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)',
     'quantize(Decimal("0.01"), rounding="ROUND_FLOOR")',
     "banca arrotondata per difetto invece che al centesimo", "py"),
    ("U3", MU, '    return float(netto) / (1.0 - float(commissione))',
     '    return float(netto)', "obiettivo netto usato come lordo", "py"),
    ("U4", MU, '''    v = importo_piazzabile("back", x)
    if v.via != VIA_DIRETTA:
        return 0.0, round(float(x), 2)
    return float(v.importo), round(float(x), 2)''',
     '''    v = importo_piazzabile("back", x)
    if v.via != VIA_DIRETTA:
        return 0.0, round(float(x), 2)
    return float(round(float(x) * 2) / 2), round(float(x), 2)''',
     "punta arrotondata al multiplo piu' vicino (non per difetto)", "py"),
    ("U5", MU, '''            xe_c = max(0.0, round(x, 2))''', '''            xe_c = xr''',
     "riquadro: cifre 'esatte' calcolate col multiplo", "py"),
    ("U6", MU, '''    p = price_ticks_away(get_nearest_price(float(prezzo)), -int(n))''',
     '''    p = round(float(prezzo) - 0.01 * int(n), 2)''',
     "tick calcolati a 0,01 fissi (non la scala vera)", "py"),
    ("U7", MU, '    return (params or {}).get(CHIAVE_MODO) is True',
     '    return bool((params or {}).get(CHIAVE_MODO))', "interruttore acceso da un valore 'vero' qualunque", "py"),
    ("U8", MU, '''        elif x > 0:
            obiettivo = x''', '''        else:
            obiettivo = x''', "obiettivo 0 trattato come 0 netti (non automatico)", "py"),
    ("U9", MU, '''    mancanti = [k for k in OBBLIGATORI if k not in p or p.get(k) is None]''',
     '''    mancanti = []''', "un parametro mancante non ferma la sessione", "py"),
    ("U10", MU, '''        if v.via != VIA_DIRETTA or v.residuo > 0 or abs(v.importo - stake) > 1e-6:''',
     '''        if v.via != VIA_DIRETTA:''', "stake non multiplo di 0,50 accettato", "py"),
    ("U11", MU, '''    if str(c.get("origine") or "").strip().lower() == "auto":''',
     '''    if False:''', "riga dell'auto-mode accettata", "py"),
    ("U12", SS, '''    "media_mode", "media_mercato", "media_stake", "media_obiettivo",''',
     '''    "media_mode", "media_stake", "media_obiettivo",''', "media_mercato fuori dalla whitelist", "py"),
    ("U13", MU, '''    "media_max_rientri": 5,''', '''    "media_max_rientri": 4,''',
     "valore di serie diverso dalla scheda", "py"),
    ("U14", MU, '''        o = self._piazza(market, "LAY", c, voluto, apertura=False, persistenza="PERSIST")''',
     '''        o = self._piazza(market, "LAY", c, voluto, apertura=False, persistenza="LAPSE")''',
     "banca di chiusura LAPSE", "py"),
    ("U15", MU, '''        if (sb or 0.0) < self.par.min_size or (sl or 0.0) < self.par.min_size:
            return''', '''        if False:
            return''', "ingresso senza liquidita' minima", "py"),
    ("U16", MU, '''        if now >= ko - self.par.stop_ingressi_s * 1000.0:
            return "dentro la finestra di stop prima del fischio"''',
     '''        if False:
            return "dentro la finestra di stop prima del fischio"''',
     "nessuna finestra di stop prima del fischio", "py"),
    ("U17", MU, '''        inplay = self.stato == LIVE
        self._nuovo_ciclo()''', '''        inplay = self.stato == LIVE
        return False''', "ciclo chiuso mai riconosciuto", "py"),
    ("U18", MU, '''            if self._punta is not None:
                # (d) la banca si riappoggia DOPO la punta di rientro
                return''', '''            if self._punta is not None:
                # (d) la banca si riappoggia DOPO la punta di rientro
                pass''', "banca vecchia riappoggiata mentre la punta di rientro e' in volo", "py"),
    ("U19", MU, '''        (punte if _lato(o) == "BACK" else banche).append((m, p))''',
     '''        if _lato(o) == "BACK":
            punte.append((m, p))''', "posizione che ignora le banche abbinate", "py"),
    ("U20", MU, '''            if self._punta_rientro:
                self._rientri += 1''', '''            if self._punta_rientro:
                pass''', "rientri mai contati (massimo mai raggiunto)", "py"),
    ("U21", MU, '''                if (now - self._punta_ms >= self.par.ttl_punta_ms and eseguibile(p)):''',
     '''                if False:''', "punta non abbinata mai annullata (TTL)", "py"),
    ("U22", MU, '''                if eseguibile(self._banca):
                    self._annulla(market, self._banca, "rientro: la banca si ritira "
                                                       "prima della punta")
                return''', '''                return''', "rientro bloccato con la banca in volo (annullo mai chiesto)", "py"),
    ("U23", MU, '''            if self._rientri >= self.par.max_rientri:
                self.stato = MASSIMO''', '''            if self._rientri > self.par.max_rientri:
                self.stato = MASSIMO''', "un rientro oltre il massimo", "py"),
    ("U24", MU, '''        if self.par.rischio_max > 0 and pos.puntato + xr > self.par.rischio_max + _EPS:''',
     '''        if False:''', "rischio massimo ignorato", "py"),
    ("U25", MU, '''        if inplay:
            self._in_live(now, aperto, bb, bl)
            return''', '''        if False:
            self._in_live(now, aperto, bb, bl)
            return''', "in gioco opera come prima del fischio", "py"),
    ("U26", MU, '''        self.stato = FINE if inplay else FERMO''', '''        self.stato = FERMO''',
     "in gioco dopo la chiusura ricomincia un ciclo", "py"),
    ("U27", MU, '''            vista["caduta"] = True
            self._emit(''', '''            vista["caduta"] = True
            (lambda *a, **k: None)(''', "banca caduta in gioco non detta", "py"),
    ("U28", MU, '''_VIVI = (OrderStatus.EXECUTABLE, OrderStatus.PENDING, OrderStatus.CANCELLING,''',
     '''_VIVI = (OrderStatus.EXECUTABLE, OrderStatus.CANCELLING,''', "esito ignoto (PENDING) creduto morto", "py"),
    ("U29", MU, '''        attesa_s = min(30, 2 ** (self._rifiuti - 1))''', '''        attesa_s = 0''',
     "nessun freno dopo un rifiuto", "py"),
    ("U30", MU, '''        if apertura and self.freno_live is not None:''', '''        if False:''',
     "aperture senza il freno dei soldi veri", "py"),
    ("U31", MU, '''        self.stato: str = BLOCCATA if self.riavvio else FERMO''',
     '''        self.stato: str = FERMO''', "riavvio a posizione aperta ignorato", "py"),
    ("U32", MU, '''        if not aperto:
            if not self._sospeso:
                self._sospeso = True
                self._emit("media_sospeso", market_id=self._mid,
                           msg="mercato sospeso prima del fischio: nessun ordine nuovo")
            self._pubblica(None, bb, bl)
            return''', '''        if False:
            return''', "ordini a mercato sospeso", "py"),
    ("U33", MU, '''        if self._mid is None or mid != self._mid:
            return''', '''        if self._mid is None:
            return''', "esito dal mercato sbagliato (Match Odds)", "py"),
    ("U34", SS, '''        if not theta_only and media is None:
            framework.add_strategy(strategy)''', '''        if not theta_only:
            framework.add_strategy(strategy)''', "la sessione arma anche il maker", "py"),
    ("U35", SS, '''        media_mode = _MU.media_mode_acceso(control.get("params") or {})''',
     '''        media_mode = True''', "modalita' accesa anche a interruttore spento", "py"),
    ("U36", SS, '''            if motivo_media:
                db.set_control(''', '''            if False:
                db.set_control(''', "la sessione parte con un parametro mancante", "py"),
    ("U37", AM, '''    for k in [k for k in out if str(k).startswith(PREFISSO_MEDIA_UNDER)]:
        out.pop(k, None)''', '''    pass''', "l'auto-mode passa le chiavi media_*", "py"),
    ("U38", RR, '''    if p.get("media_mode") is True:
        # 05/10: la stessa regola di `run_session` per la modalita' media under''',
     '''    if False:
        # 05/10: la stessa regola di `run_session` per la modalita' media under''',
     "replay: vita della sessione media a 10'", "py"),
    ("U39", RB, '''    "Betfair.stream.scalper.media_under_bot",
)''', ''')''', "modulo nuovo non registrato nel banco", "py"),
    ("U40", CE, '''            if all(abs(size - a) > 1e-6 for a in ammessi):''',
     '''            if all(abs(size - esatto) > 1e-6 for a in ammessi):''',
     "M4 senza l'arrotondamento a 0,50 (falso positivo)", "py"),
    ("U41", CE, '''        if tipo not in MERCATI_AMMESSI or mid != str(o.mercato_scelto or ""):''',
     '''        if tipo not in MERCATI_AMMESSI:''', "M1 non guarda il mercato scelto", "py"),
    ("U42", CE, '''        if len(fatti) > par.max_rientri:''', '''        if len(fatti) > par.max_rientri + 9:''',
     "M2 cieco sul massimo", "py"),
    ("U43", CE, '''            if su is None or su < par.tick_rientro:''', '''            if su is None:''',
     "M3 cieco sui tick", "py"),
    ("U44", CE, '''        if len(vivi) > 1:
            return ("%d %s vive insieme''', '''        if len(vivi) > 2:
            return ("%d %s vive insieme''', "M5 cieco su due ordini vivi", "py"),
    ("U45", CE, '''    if abs(resto - voluto) > 0.011:''', '''    if abs(resto - voluto) > 99.0:''',
     "M6 cieco sull'importo", "py"),
    ("U46", CE, '''    if c is None or abs(float(banca.get("price") or 0.0) - c) > 1e-9:''',
     '''    if c is None:''', "M6 cieco sulla quota", "py"),
    ("U47", CE, '''        if creato is not None and o.in_gioco_ms is not None and creato >= o.in_gioco_ms:''',
     '''        if False:''', "M7 cieco sugli ordini in gioco", "py"),
    ("U48", CE, '''        if lato == "LAY" and pt != "PERSIST":''', '''        if False:''',
     "M8 cieco sulla banca LAPSE", "py"),
    ("U49", CE, '''        if o.ko_ms is not None and creato >= o.ko_ms - par.stop_ingressi_s * 1000.0:''',
     '''        if False:''', "M9 cieco sulla finestra di stop", "py"),
    ("U50", RR, '''        if self.media is not None:
            self.controlli_media(ms, quando, fine)''', '''        if self.media is not None:
            pass''', "replay: controlli M mai chiamati", "py"),
    ("U51", RR, '''        par, _motivo = MU.leggi_parametri(self.db.control.get("params") or {})''',
     '''        par, _motivo = MU.leggi_parametri(dict(MU.VALORI_DI_SERIE, media_mercato=MU.MERCATI_AMMESSI[0]))''',
     "replay: parametri dalla scheda di serie invece che dalla riga", "py"),
    ("U52", MU, '''        if n is None or n < minimo:''', '''        if n is None:''',
     "interi sotto il minimo accettati (tick 0, rientri -1, attesa 0)", "py"),
    ("U53", MU, '''        if x is None or x < 0:
            errori.append("%s %r non valido (numero >= 0)" % (k, p.get(k)))''',
     '''        if x is None:
            errori.append("%s %r non valido (numero >= 0)" % (k, p.get(k)))''',
     "numeri negativi accettati", "py"),
    ("U54", MU, '''    if qmin is None or qmax is None or qmin < 1.01 or qmax > 1000.0 or qmin >= qmax:''',
     '''    if qmin is None or qmax is None:''', "intervallo di quota rovesciato accettato", "py"),
    ("U55", MU, '''    if not isinstance(lista, (list, tuple)):
        errori.append("media_obiettivi_live non e' una lista")''',
     '''    if not isinstance(lista, (list, tuple, str)):
        errori.append("media_obiettivi_live non e' una lista")''', "obiettivi in gioco come testo accettati", "py"),
    ("U56", MU, '''    if comm is None or comm < 0 or comm >= 100:''', '''    if comm is None or comm < 0:''',
     "commissione del 100 % accettata", "py"),
    ("U57", MU, '''        if x is None or x < 0:
            errori.append("media_obiettivo''', '''        if x is None:
            errori.append("media_obiettivo''', "obiettivo negativo accettato", "py"),
    ("U58", MU, '''    if mercato not in MERCATI_AMMESSI:''', '''    if not mercato:''',
     "un mercato qualunque accettato", "py"),
    ("U59", MU, '''    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)''', '''    if v is None:
        return None
    try:
        x = float(v)''', "un booleano letto come numero", "py"),
    ("U60", MU, '''    if params.get("theta_mode") is True or params.get("ht_mode") is True:''',
     '''    if False:''', "media insieme a theta o intervallo", "py"),
    ("U61", MU, '''    if stato in STATI_CON_POSIZIONE and (puntato > 0 or stato == INGRESSO):''',
     '''    if stato == MASSIMO and puntato > 0:''', "riavvio: solo il MASSIMO riconosciuto", "py"),
    ("U62", MU, '''        v = importo_piazzabile("back", stake)
        if v.via != VIA_DIRETTA or v.residuo > 0 or abs(v.importo - stake) > 1e-6:''',
     '''        v = importo_piazzabile("back", stake)
        if False:''', "stake qualunque accettato", "py"),
    ("U63", MU, '''    if x is None or abs(x - round(x)) > 1e-9:
        return None
    return int(round(x))''', '''    if x is None:
        return None
    return int(x)''', "interi letti troncando i decimali", "py"),
    # ---------------------------------------------------------------- frontend
    ("F1", TS, '''    if (!(p.media_stake >= 1) || !multiploDi050(p.media_stake)) {''',
     '''    if (!(p.media_stake >= 0.5)) {''', "scheda: punta non multipla accettata", "vt"),
    ("F2", TS, '''        sniper_mode: false,
        theta_mode: false,''', '''        theta_mode: false,''', "scheda: sniper non spento nel payload", "vt"),
    ("F3", TS, '''        const n = Number(pz.replace(',', '.'));''', '''        const n = Number(pz);''',
     "scheda: obiettivi con la virgola italiana non letti", "vt"),
    ("F4", TS, '''const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);''',
     '''const num = (v: unknown, d = 0): number => (v === undefined || v === null ? d : Number(v));''',
     "scheda: tipi delle stats non controllati", "vt"),
    ("F5", TS, '''    return `${ob} a ${quota(o.quota_chiusura)}: PUNTA ${euro(o.punta)} € a ${quota(o.quota_punta)} ` +''',
     '''    return `${ob} a ${quota(o.quota_chiusura)}: PUNTA ${euro(o.punta_esatta)} € a ${quota(o.quota_punta)} ` +''',
     "scheda: punta esatta al posto del multiplo", "vt"),
    ("F6", SP, '''                                    if (v === true) { setSniperMode(false); setThetaMode(false); setHtMode(false); }''',
     '''                                    if (v === true) { setThetaMode(false); setHtMode(false); }''',
     "scheda: la media non spegne lo sniper", "vt"),
    ("F7", SP, '''            if (errori.length > 0 || mediaMercato === '') {''',
     '''            if (mediaMercato === '' && false) {''', "scheda: parte senza mercato", "vt"),
    ("F8", SP, '''                    {mediaStato && (
                        <div className="rounded-lg border border-orange-400/30''',
     '''                    {mediaStato && false && (
                        <div className="rounded-lg border border-orange-400/30''',
     "scheda: stato del ciclo non mostrato", "vt"),
    ("F10", TS, '''    if (mercato !== 'OVER_UNDER_25' && mercato !== 'OVER_UNDER_35') {''',
     '''    if (mercato === 'MATCH_ODDS') {''', "scheda: nessun controllo del mercato", "vt"),
    ("F11", TS, '''    if (!(p.media_quota_min >= 1.01) || !(p.media_quota_max <= 1000) || !(p.media_quota_min < p.media_quota_max)) {''',
     '''    if (!(p.media_quota_min >= 1.01)) {''', "scheda: quote rovesciate accettate", "vt"),
    ("F12", TS, '''    if (!stats || typeof stats.media_stato !== 'string') return null;''',
     '''    if (!stats) return null;''', "scheda: vista della modalita' anche senza modalita'", "vt"),
    ("F13", TS, '''        banca: leggiBanca(stats.media_banca),''', '''        banca: leggiBanca(null),''',
     "scheda: banca appoggiata mai letta", "vt"),
    ("F14", SP, '''    const [mediaMode, setMediaMode] = useState(false);''',
     '''    const [mediaMode, setMediaMode] = useState(true);''', "scheda: modalita' accesa di serie", "vt"),
    ("F9", TS, '''    media_mode: false,''', '''    media_mode: true,''', "valore di serie: modalita' accesa", "vt+py"),
]


def _esegui(cmd: List[str], cwd: str = ".") -> Tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return 124, "FAILED TIMEOUT::suite appesa oltre 300 s"
    return r.returncode, r.stdout + r.stderr


def _rossi_py(out: str) -> List[str]:
    return sorted(set(re.findall(r"FAILED (\S+?)(?: - |\s|$)", out))
                  | set(re.findall(r"ERROR (\S+?)(?: - |\s|$)", out)))


def _rossi_vt(out: str) -> List[str]:
    return sorted(set(re.findall(r"(?:FAIL|×) +(src/\S+ > .+?)(?: \d+ms)?$", out, re.M)))


def main(scelte: List[str]) -> int:
    rc, _ = _esegui(["git", "diff", "--quiet"])
    if rc != 0:
        print("ALBERO NON PULITO: commit prima della falsificazione")
        return 2
    righe = []
    for mid, f, vecchio, nuovo, descr, suite in MUTAZIONI:
        if scelte and mid not in scelte:
            continue
        testo = open(f, encoding="utf-8").read()
        n = testo.count(vecchio)
        if n != 1:
            righe.append((mid, descr, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % n, []))
            continue
        open(f, "w", encoding="utf-8").write(testo.replace(vecchio, nuovo))
        rossi: List[str] = []
        try:
            if "py" in suite:
                _rc, out = _esegui(PY)
                rossi += _rossi_py(out)
                if "collected 0" in out or ("error" in out.lower() and not rossi):
                    rossi.append("ERRORE DI RACCOLTA: " + out.strip().splitlines()[-1])
            if "vt" in suite:
                _rc, out = _esegui(VT, cwd="frontend")
                rv = _rossi_vt(out)
                m = re.search(r"Tests +(\d+) failed", out)
                if m and not rv:
                    rv = ["%s test rossi (vitest)" % m.group(1)]
                rossi += rv
        finally:
            subprocess.run(["git", "checkout", "--", f], check=True)
        rc, _ = _esegui(["git", "diff", "--quiet"])
        if rc != 0:
            print("RIPRISTINO FALLITO dopo %s" % mid)
            return 3
        righe.append((mid, descr, "%d rossi" % len(rossi), rossi))
        print("%s | %s | %d rossi" % (mid, descr, len(rossi)), flush=True)
    print()
    print("| # | mutazione | test rossi |")
    print("|---|---|---|")
    for mid, descr, esito, rossi in righe:
        nomi = ", ".join(r.split("::")[-1] for r in rossi[:4]) + (" ..." if len(rossi) > 4 else "")
        print("| %s | %s | %s: %s |" % (mid, descr, esito, nomi))
    import json
    with open("AUDIT_2026-10-05/strumenti/mutazioni_media_under_esito.json", "w",
              encoding="utf-8") as fh:
        json.dump([{"id": m, "mutazione": d, "esito": e, "rossi": r}
                   for m, d, e, r in righe], fh, indent=1, ensure_ascii=True)
    sopravvissute = [r for r in righe if r[2].startswith("0 ")]
    print()
    print("SOPRAVVISSUTE: %s" % (", ".join(r[0] for r in sopravvissute) or "nessuna"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
