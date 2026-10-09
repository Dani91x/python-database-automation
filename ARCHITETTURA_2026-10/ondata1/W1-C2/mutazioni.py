"""Mutazioni di W1-C2 (comparto C: libro ordini del conto, attribuzione, P&L di
mercato, riconciliazione in ombra): ogni mutazione deve far diventare ROSSO almeno
un test del comparto (``Betfair/nucleo/ordini/tests/test_c2_*.py``).

Uso (dalla radice del repository):
    python ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py .
    python ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py . M64 M65   (solo alcune)

Per ogni mutazione: sha256 del file, sostituzione esatta (UNA sola occorrenza,
altrimenti ERRORE), tutti i test W1-C2 con ``-x``, ripristino dei byte originali,
sha256 ricontrollato. Una riga per mutazione e il totale in coda; codice d'uscita
1 se una mutazione sopravvive, se una sostituzione non si trova o se uno sha256
cambia. M01-M43: consegna ``5b958ba7`` (stringhe adeguate alle correzioni);
M44-M63: correzioni dopo la revisione (``99e75fbe``); M64-M93: un ramo per
mutazione dopo la verifica del coordinatore su ``83f376e0``.
ASCII-only.
"""
import hashlib
import os
import subprocess
import sys

R = sys.argv[1] if len(sys.argv) > 1 else "."
SOLO = set(sys.argv[2:])
O = "Betfair/nucleo/ordini/"
TEST = O + "tests/"

MUT = [
    ('M01 G1 ref manuale torna desktop senza evidenza', 'attribuzione.py',
     'return Attribuzione(SCONOSCIUTO, f"strategia_manuale_da_confermare:{s}", "riferimenti",\n                            provvisoria=True)',
     'return Attribuzione(DESKTOP, f"strategia_manuale:{s}", "riferimenti")'),
    ('M02 ref storico condiviso ignorato', 'attribuzione.py',
     '    if sl in r.rif_storici_condivisi:',
     '    if False:'),
    ('M03 Safe tennis REST letto come Safe', 'attribuzione.py',
     'if autore == "safe" and dal_ref == "safe_tennis":',
     'if False:'),
    ('M04 scalper senza event_id numerico', 'attribuzione.py',
     'if csr.startswith(p) and resto.isdigit():',
     'if csr.startswith(p):'),
    ('M05 precedenza degli indizi rovesciata', 'attribuzione.py',
     'key=lambda i: (_FORZA.get(i.tipo, 9), i.valore)',
     'key=lambda i: (-_FORZA.get(i.tipo, 9), i.valore)'),
    ('M06 riga utente di Mike letta come Mike', 'attribuzione.py',
     '    if ind.tipo in ("adottato", "utente"):\n        return None',
     '    if ind.tipo == "utente":\n        return None'),
    ('M07 sito letto come sconosciuto', 'attribuzione.py',
     'return Attribuzione(SITO, "sito", "riferimenti")',
     'return Attribuzione(SCONOSCIUTO, "sito", "riferimenti")'),
    ('M08 prefisso del risk sbagliato', 'attribuzione.py',
     'PREFISSO_CODA_RISCHIO = "risk"',
     'PREFISSO_CODA_RISCHIO = "rsk"'),
    ('M09 ref confrontato con le maiuscole', 'attribuzione.py',
     '    sl = s.lower()',
     '    sl = s'),
    ('M10 classi tennis tagliate a 14', 'attribuzione.py',
     'classi[str(voce[0].__name__)[:15].lower()]',
     'classi[str(voce[0].__name__)[:14].lower()]'),
    ('M11 ref manuale con customerOrderRef di un bot', 'attribuzione.py',
     '        bot = _autore_da_prefisso(o, r) if o else None\n        if bot is not None:\n            return Attribuzione(bot, f"ref:{o}", "riferimenti")\n        # revisione 09/10 (G1)',
     '        bot = None\n        if bot is not None:\n            return Attribuzione(bot, f"ref:{o}", "riferimenti")\n        # revisione 09/10 (G1)'),
    ('M12 messaggio vecchio sovrascrive', 'libro_conto.py',
     'if voce is not None and int(o.ricevuto_ms) < int(voce.ordine.ricevuto_ms):',
     'if False:'),
    ('M13 paper e live sulla stessa chiave', 'libro_conto.py',
     'chiave = (modo, str(o.bet_id))',
     'chiave = ("live", str(o.bet_id))'),
    ('M14 modo sempre live', 'libro_conto.py',
     'ref=(o.customer_order_ref or None), modo=modo,',
     'ref=(o.customer_order_ref or None), modo="live",'),
    ('M15 tetto dimentica ordini vivi', 'libro_conto.py',
     'if k[0] != modo or v.ordine.stato != "EXECUTION_COMPLETE":',
     'if k[0] != modo:'),
    ('M16 consumatore rotto propaga', 'libro_conto.py',
     'except Exception:  # noqa: BLE001 - un consumatore rotto non ferma il libro',
     'except ZeroDivisionError:'),
    ('M17 lucchetto del libro tolto', 'libro_conto.py',
     'self._lock = threading.RLock()',
     'self._lock = __import__("contextlib").nullcontext()'),
    ('M18 indizi ignorati dal libro', 'libro_conto.py',
     'a = attr.attribuisci(o, self._indizi.get(str(o.bet_id), ()), regole)',
     'a = attr.attribuisci(o, (), regole)'),
    ('M19 prezzo medio 0 al posto di assente', 'libro_conto.py',
     'prezzo_medio=float(avp) if avp is not None and float(avp) > 0 else None,',
     'prezzo_medio=float(avp or 0.0),'),
    ('M20 lato rovesciato', 'libro_conto.py',
     'lato="back" if lato == "BACK" else "lay",',
     'lato="lay" if lato == "BACK" else "back",'),
    ("M21 comandi su ordini non dell'utente", 'libro_conto.py',
     'if o.residuo <= 0 or o.autore not in attr.AUTORI_UTENTE:',
     'if o.residuo <= 0:'),
    ('M22 formula del lay sbagliata', 'pnl_mercato.py',
     'v += -importo * (prezzo - 1) if suo else importo',
     'v += importo * (prezzo - 1) if suo else importo'),
    ('M23 paper e live sommati nel P&L', 'pnl_mercato.py',
     '        if o.modo != modo:',
     '        if False:'),
    ('M24 commissione applicata', 'pnl_mercato.py',
     'se_vince = {s: round(pnl_se_vince(buoni, s), 2) for s in selezioni}',
     'se_vince = {s: round(pnl_se_vince(buoni, s) * 0.95, 2) for s in selezioni}'),
    ('M25 prezzo medio non pesato', 'pnl_mercato.py',
     '    return float(media) if media else None',
     '    return float(sum(p for p, _ in coppie) / len(coppie))'),
    ("M26 G2 esito fittizio 'vince un altro'", 'pnl_mercato.py',
     'esposizione = round(min([0.0] + list(se_vince.values())), 2)',
     'esposizione = round(min([0.0] + list(se_vince.values()) + [pnl_se_vince(buoni, None)]), 2)'),
    ('M27 handicap ignorato', 'pnl_mercato.py',
     'a_linee = any(abs(float(o.handicap)) > 1e-9 for o in tutti)',
     'a_linee = False'),
    ('M28 esposizione sul prezzo chiesto', 'pnl_mercato.py',
     '(mb if o.lato == "back" else ml).append((float(o.prezzo_medio or 0.0), float(o.abbinato)))',
     '(mb if o.lato == "back" else ml).append((float(o.prezzo), float(o.abbinato)))'),
    ('M29 lockedPnlAt sbagliato', 'pnl_mercato.py',
     '    return se_perde + (se_vince - se_perde) / prezzo',
     '    return se_perde + (se_vince - se_perde) / (prezzo - 1)'),
    ('M30 prezzo medio <= 1 accettato', 'pnl_mercato.py',
     'if o.prezzo_medio is None or not o.prezzo_medio > 1.0:',
     'if o.prezzo_medio is None:'),
    ('M31 esposizione massima positiva', 'pnl_mercato.py',
     'esposizione = round(min([0.0] + list(se_vince.values())), 2)',
     'esposizione = round(min(list(se_vince.values()) or [0.0]), 2)'),
    ('M32 tolleranza R1 tolta', 'riconciliazione.py',
     'if abs(sm_s - float(o.abbinato)) > TOLLERANZA_ABBINATO:',
     'if abs(sm_s - float(o.abbinato)) > 0.0:'),
    ('M33 stato diverso ignorato', 'riconciliazione.py',
     '            elif st_s != o.stato:',
     '            elif False:'),
    ('M34 bot con tabella non saltato', 'riconciliazione.py',
     'if csr and csr in bot_tabella:',
     'if False:'),
    ('M35 righe account contate mancanti', 'riconciliazione.py',
     'and not src.startswith("bot:") and src != "account"):',
     'and not src.startswith("bot:")):'),
    ('M36 avviso al primo giro', 'riconciliazione.py',
     'GIRI_AVVISO_MANCANTE = 2',
     'GIRI_AVVISO_MANCANTE = 1'),
    ('M37 contatore dei mancanti mai azzerato', 'riconciliazione.py',
     '            if b not in ora:\n                self._mancanti.pop(b, None)',
     '            if b not in ora:\n                pass'),
    ('M38 righe ripresa del diario ignorate', 'riconciliazione.py',
     'elif tipo in ("esito", "ripresa"):',
     'elif tipo == "esito":'),
    ('M39 R2 ritrovato mai', 'riconciliazione.py',
     '        elif trovati:\n            esito = "ritrovato"',
     '        elif False:\n            esito = "ritrovato"'),
    ('M40 specchio di tutti i modi', 'riconciliazione.py',
     'righe = [r for r in specchio if _testo(r.get("mode")) == self.modo]',
     'righe = list(specchio)'),
    ('M41 app scambiata per il sito', 'riconciliazione.py',
     '                elif a.autore == attr.SITO:',
     '                elif a.autore in attr.AUTORI_UTENTE:'),
    ('M42 fase parziale come abbinato', 'riconciliazione.py',
     '"abbinato_parziale": "parziale"',
     '"abbinato_parziale": "abbinato"'),
    ('M43 blotter diverso ignorato', 'riconciliazione.py',
     'if abs(sm - float(o.abbinato)) > TOLLERANZA_ABBINATO:',
     'if False:'),
    ('M44 G1 evidenza positiva ignorata', 'attribuzione.py',
     '            if ind.tipo in ("utente", "adottato"):\n                return Attribuzione(DESKTOP,',
     '            if False:\n                return Attribuzione(DESKTOP,'),
    ('M45 M5 classi scalper standalone tolte', 'attribuzione.py',
     '        classi[str(cls.__name__)[:15].lower()] = SCALPER',
     '        pass'),
    ("M46 G1 riga di coda dell'app non e' utente", 'attribuzione.py',
     '    return (Indizio("utente", f"coda:{cref}"),)',
     '    return ()'),
    ('M47 M1 guardia delle regressioni tolta', 'libro_conto.py',
     '                regr = self._regressione(voce.ordine, o)',
     '                regr = None'),
    ('M48 M1 sizeVoided non ammesso', 'libro_conto.py',
     '        annullati = max(0.0, float(nuovo.annullato_da_betfair) - float(vecchio.annullato_da_betfair))',
     '        annullati = 0.0'),
    ('M49 G3 seme mai fatto', 'libro_conto.py',
     '            self._seme["live"] = True\n',
     '            pass\n'),
    ("M50 G3 riconnessione con ripresa rifa' il seme", 'libro_conto.py',
     '        if con_ripresa:\n            return\n',
     '        return\n'),
    ('M51 G3 motivo seme_non_fatto tolto', 'libro_conto.py',
     '            if not self._seme.get(modo, False):\n                extra.append("seme_non_fatto")',
     '            if False:\n                extra.append("seme_non_fatto")'),
    ('M52 G3 mb/ml ignorati', 'libro_conto.py',
     '                if stream - noto[lato] > EPS_ABBINATO:',
     '                if False:'),
    ('M53 M2 chiusi non prima degli aperti', 'libro_conto.py',
     '            aperto = 0 if (info is not None and info.chiuso) else 1',
     '            aperto = 1'),
    ('M54 M2 aperti dimenticati senza riassunto', 'libro_conto.py',
     '            if aperto:\n                self._riassumi(k)',
     '            if False:\n                self._riassumi(k)'),
    ('M55 M3 indizi duplicati', 'libro_conto.py',
     '                if ind not in tenuti:\n                    tenuti.append(ind)',
     '                tenuti.append(ind)'),
    ('M56 M3 potatura non chiamata', 'libro_conto.py',
     '                self._pota_indizi()',
     '                pass'),
    ("M57 M3 indizi non tolti con l'ordine", 'libro_conto.py',
     '        if chiave[0] == "live":\n            self._indizi.pop(chiave[1], None)',
     '        if False:\n            self._indizi.pop(chiave[1], None)'),
    ('M58 consegna ai consumatori non serializzata', 'libro_conto.py',
     '        with self._consegna:\n            with self._lock:\n                voce = self._voci.get(chiave)',
     '        if True:\n            with self._lock:\n                voce = self._voci.get(chiave)'),
    ('M59 M4 tipo ignoto accettato', 'pnl_mercato.py',
     '    if tipo_scommessa is None:\n        motivi.append("tipo_ignoto")',
     '    if tipo_scommessa is None:\n        pass'),
    ("M60 M4 piu' vincitori accettati", 'pnl_mercato.py',
     '    if vincitori is not None and int(vincitori) != 1:',
     '    if False:'),
    ('M61 tolleranza R1 0,5', 'riconciliazione.py',
     'TOLLERANZA_ABBINATO = 0.01',
     'TOLLERANZA_ABBINATO = 0.5'),
    ('M62 G3 ombra senza seme confronta lo specchio', 'riconciliazione.py',
     '            if conto_completo:\n                div += self._specchio_contro_conto(per_bet, righe)',
     '            if True:\n                div += self._specchio_contro_conto(per_bet, righe)'),
    ('M63 G3 R2 non trovato senza seme', 'riconciliazione.py',
     '    if v.esito == "non_trovato" and not conto_completo:',
     '    if False:'),
    ('M64 M1 abbinato che cala fra stati uguali', 'libro_conto.py',
     '        if float(nuovo.abbinato) < float(vecchio.abbinato) - annullati - 1e-9:',
     '        if False:'),
    ('M65 M1 completo che torna eseguibile', 'libro_conto.py',
     '        if vecchio.stato == "EXECUTION_COMPLETE" and nuovo.stato == "EXECUTABLE":',
     '        if False:'),
    ('M66 G1 riga di coda del risk', 'attribuzione.py',
     '    if cref.startswith(r.prefisso_coda_rischio):',
     '    if False:'),
    ("M67 G1 ack del desktop non e' utente", 'attribuzione.py',
     '    return Indizio("utente", f"ack_desktop:{_testo(bet_id)}")',
     '    return Indizio("coda", f"ack_desktop:{_testo(bet_id)}")'),
    ('M68 G1 indizio utente letto come bot', 'attribuzione.py',
     '    if ind.tipo in ("adottato", "utente"):\n        return None',
     '    if ind.tipo == "adottato":\n        return None'),
    ('M69 G1 specchio bot:tennis toglie il provvisorio', 'attribuzione.py',
     '        if a.provvisoria:\n            return None',
     '        if False:\n            return None'),
    ('M70 G1 riga utente di Mike non conferma', 'attribuzione.py',
     '            if ind.tipo in ("utente", "adottato"):\n                return Attribuzione(DESKTOP,',
     '            if ind.tipo in ("utente",):\n                return Attribuzione(DESKTOP,'),
    ('M71 G1 motivo di bot della coda ignorato', 'attribuzione.py',
     '    if motivo:\n        ind = indizio_da_motivo(motivo)\n        return (ind,) if ind is not None else ()',
     '    if False:\n        ind = indizio_da_motivo(motivo)\n        return (ind,) if ind is not None else ()'),
    ('M72 G3 seme KO creduto fatto', 'libro_conto.py',
     '"possono mancare (P&L incompleto)", exc_info=True)\n            return -1',
     '"possono mancare (P&L incompleto)", exc_info=True)\n            letti = []'),
    ('M73 G3 un ordine illeggibile ferma il seme', 'libro_conto.py',
     '                                 getattr(co, "bet_id", None))\n                continue',
     '                                 getattr(co, "bet_id", None))\n                return -1'),
    ('M74 G3 riconnessione senza ripresa tiene il seme', 'libro_conto.py',
     '            self._seme["live"] = False\n        logger.warning("[libro] stream ordini riconnesso',
     '            pass\n        logger.warning("[libro] stream ordini riconnesso'),
    ('M75 G3 il live nasce col seme fatto', 'libro_conto.py',
     'self._seme: Dict[str, bool] = {"live": False, "paper": True}',
     'self._seme: Dict[str, bool] = {"live": True, "paper": True}'),
    ('M76 G3 mancanza mai tolta', 'libro_conto.py',
     '            else:\n                self._mancanze.pop(chiave, None)',
     '            else:\n                pass'),
    ('M77 G3 motivo abbinato_mancante tolto', 'libro_conto.py',
     '                extra.append("abbinato_mancante")',
     '                pass'),
    ('M78 G3 ombra senza la divergenza seme_non_fatto', 'riconciliazione.py',
     '                div.append(Divergenza("seme_non_fatto", "info", None, None,',
     '                div.append(Divergenza("in_volo_ritrovato", "info", None, None,'),
    ('M79 M2 avviso dei mercati aperti tolto', 'libro_conto.py',
     '        if aperti:\n            self.conti["dimenticati_aperti"] += aperti',
     '        if False:\n            self.conti["dimenticati_aperti"] += aperti'),
    ('M80 M2 riassunto anche senza abbinato', 'libro_conto.py',
     '        if c.abbinato <= 0 or c.prezzo_medio is None or not c.prezzo_medio > 1.0:\n            return',
     '        if False:\n            return'),
    ('M81 M2 riassunti fuori dal P&L', 'libro_conto.py',
     '            ordini = self._ordini_del_mercato(mid, modo) + self._ordini_riassunti(mid, modo)',
     '            ordini = self._ordini_del_mercato(mid, modo)'),
    ('M82 M2 motivo ordini_riassunti tolto', 'libro_conto.py',
     '                extra.append("ordini_riassunti")',
     '                pass'),
    ('M83 dimentica_mercato tiene i riassunti', 'libro_conto.py',
     '                self._riassunti.pop((m, mid), None)',
     '                pass'),
    ('M84 dimentica_mercato tiene le mancanze', 'libro_conto.py',
     '                    self._mancanze.pop(k, None)\n            if modo is None:',
     '                    pass\n            if modo is None:'),
    ('M85 dimentica_mercato tiene runner e tipo', 'libro_conto.py',
     '            if modo is None:\n                self._mercati.pop(mid, None)',
     '            if False:\n                self._mercati.pop(mid, None)'),
    ('M86 M3 potatura degli indizi orfani vuota', 'libro_conto.py',
     '        for b in orfani[:max(0, len(orfani) - self._max_indizi)]:',
     '        for b in orfani[:0]:'),
    ('M87 G2 imposta_mercato ignora i runner', 'libro_conto.py',
     '                info.runner = tuple(int(r) for r in runner)',
     '                pass'),
    ('M88 M4 imposta_mercato ignora il tipo', 'libro_conto.py',
     '                info.tipo_scommessa = str(tipo_scommessa)',
     '                pass'),
    ('M89 M4 imposta_mercato ignora i vincitori', 'libro_conto.py',
     '                info.vincitori = int(vincitori)',
     '                pass'),
    ('M90 M2 imposta_mercato ignora il chiuso', 'libro_conto.py',
     '                info.chiuso = bool(chiuso)',
     '                pass'),
    ('M91 G2 motivo runner_ignoti tolto', 'pnl_mercato.py',
     '        motivi.append("runner_ignoti")',
     '        pass'),
    ('M92 G2 zero al posto di NaN', 'pnl_mercato.py',
     '                           else math.nan)',
     '                           else 0.0)'),
    ('M93 M4 tipo non ODDS accettato', 'pnl_mercato.py',
     '    elif str(tipo_scommessa).upper() not in TIPI_UN_VINCITORE:',
     '    elif False:'),
]


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    rossi, provate, guasti = 0, 0, 0
    for nome, rel, vecchio, nuovo in MUT:
        if SOLO and nome.split()[0] not in SOLO:
            continue
        path = os.path.join(R, O, rel)
        prima = sha(path)
        with open(path, "rb") as fh:
            originale = fh.read()
        testo = originale.decode("utf-8")
        n = testo.count(vecchio)
        if n != 1:
            print(f"ERRORE  {nome}: occorrenze {n}")
            guasti += 1
            continue
        provate += 1
        with open(path, "wb") as fh:
            fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
        try:
            res = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-x",
                                  "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning"],
                                 cwd=R, capture_output=True, text=True, timeout=900)
        finally:
            with open(path, "wb") as fh:
                fh.write(originale)
        dopo = sha(path)
        if dopo != prima:
            guasti += 1
        ultima = (res.stdout.strip().splitlines() or ["?"])[-1]
        rosso = res.returncode != 0
        rossi += rosso
        print(f"{'ROSSO' if rosso else 'VERDE!'}  {nome}  [{ultima}]  "
              f"sha256 {'uguale' if prima == dopo else 'DIVERSO'} {dopo[:12]}", flush=True)
    print(f"TOTALE rosse {rossi}/{provate} (guasti {guasti})")
    return 0 if rossi == provate and not guasti else 1


sys.exit(main())
