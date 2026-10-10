"""Falsificazione W1-A1: ogni mutazione rompe UNA regola; i test devono diventare rossi.
Gira su una COPIA del repo (sandbox) e ripristina ogni file con sha256 identico.
Uso: python3 -P mutazioni_a1.py <sandbox> <uscita.json> [ID...]"""
import hashlib
import json
import os
import re
import subprocess
import sys

SB = sys.argv[1]
OUT = sys.argv[2]
SOLO = set(sys.argv[3:])
B = "Betfair/nucleo/betfair/"
T = B + "tests/"

M = [
    # ---------------- limiti.py
    ("L01", B + "limiti.py", '"EX_ALL_OFFERS": 17,', '"EX_ALL_OFFERS": 15,', "peso EX_ALL_OFFERS sbagliato"),
    ("L02", B + "limiti.py", '    if "EX_ALL_OFFERS" in voci:\n        chiavi.append(',
     '    if "EX_ALL_OFFERS" in voci and "EX_BEST_OFFERS" not in voci:\n        chiavi.append(', "ALL non prevale su BEST"),
    ("L03", B + "limiti.py", 'chiavi.append("EX_BEST_OFFERS+EX_TRADED" if traded else "EX_BEST_OFFERS")',
     'chiavi.extend(["EX_BEST_OFFERS", "EX_TRADED"] if traded else ["EX_BEST_OFFERS"])', "combinazione sommata"),
    ("L04", B + "limiti.py", "base = base * max(Fraction(1), Fraction(profondita, 3))", "base = base", "profondita' ignorata"),
    ("L05", B + "limiti.py", "n = math.floor(Fraction(PESO_MASSIMO_RICHIESTA) / p)",
     "n = math.ceil(Fraction(PESO_MASSIMO_RICHIESTA) / p)", "arrotondamento per eccesso"),
    ("L06", B + "limiti.py", "        n = min(n, int(blocco_massimo))", "        pass", "blocco_massimo ignorato"),
    ("L07", B + "limiti.py", 'return parametri.get("order_projection") is not None or parametri.get("match_projection") is not None',
     "return False", "listMarketBook con ordini non conteso"),
    ("L08", B + "limiti.py", "return int(n_istruzioni) > tetto", "return int(n_istruzioni) >= tetto", "bordo istruzioni"),
    ("L09", B + "limiti.py", "return max(1, LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO // p)",
     "return max(1, LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO // (p + 1))", "quota login"),
    ("L10", B + "limiti.py", '"RUNNER_METADATA": 1,', '"RUNNER_METADATA": 0,', "peso catalogo"),
    ("L11", B + "limiti.py", '        raise ValueError(f"proiezione di prezzo sconosciuta: {sorted(sconosciute)}")', "        pass",
     "proiezione ignota accettata"),
    ("L12", B + "limiti.py", "PESO_LIST_MARKET_PROFIT_AND_LOSS = 4", "PESO_LIST_MARKET_PROFIT_AND_LOSS = 2", "peso P&L"),
    ("L13", B + "limiti.py", 'URL_KEEPALIVE_ITALIA = "https://identitysso.betfair.it/api/keepAlive"',
     'URL_KEEPALIVE_ITALIA = "https://identitysso.betfair.com/api/keepAlive"', "endpoint keepAlive .com"),
    ("L14", B + "limiti.py", "    if p <= 0:\n", "    if p < 0:\n", "peso zero accettato"),
    # ---------------- salute.py
    ("H01", B + "salute.py", "                    h.aggiungi(float(ms))", "                    pass", "latenza non registrata"),
    ("H02", B + "salute.py", 'GRUPPO_ESITI = "betfair_rest_esiti"', 'GRUPPO_ESITI = "betfair_rest"', "gruppo che collide col gancio HTTP"),
    ("H03", B + "salute.py", '                raise KeyError(f"voce di sessione sconosciuta: {chiave}")',
     '                self._sessione[chiave] = 0', "voce ignota accettata"),
    ("H04", B + "salute.py", "            self._ritenti[metodo] = self._ritenti.get(metodo, 0) + 1", "            pass", "ritenti non contati"),
    ("H05", B + "salute.py", "            self._attesa_tetto.aggiungi(float(ms))", "            pass", "attesa tetto non contata"),
    ("H06", B + "salute.py", "            self._inoltra.conta(gruppo, chiave, 1)\n        except Exception as e:",
     "            self._inoltra.conta(gruppo, chiave, 1)\n        except ZeroDivisionError as e:", "inoltro rotto risale"),
    ("H07", B + "salute.py", '            per_metodo[classe] = per_metodo.get(classe, 0) + 1',
     '            per_metodo["ok"] = per_metodo.get("ok", 0) + 1', "classe d'esito persa"),
    # ---------------- sessione.py
    ("S01", B + "sessione.py", "            if motivo is None:\n                return", "            if True:\n                return", "freno spento"),
    ("S02", B + "sessione.py", "            self._ban_fino = a + self.ban_s", "            pass", "ban ignorato"),
    ("S03", B + "sessione.py", "            if self.generazione != generazione_vista:\n                return True\n", "",
     "nessun controllo di generazione"),
    ("S04", B + "sessione.py", "        for _ in range(n):\n            for cb in consumatori:",
     "        for _ in range(0):\n            for cb in consumatori:", "sessione_rifatta mai notificata"),
    ("S05", B + "sessione.py", "            relogin = self._custode is not None", "            relogin = True",
     "notifica anche al primo login"),
    ("S06", B + "sessione.py", "        if _SESSIONE_DI_PROCESSO is None:\n            _SESSIONE_DI_PROCESSO = SessioneBetfair(**opzioni)",
     "        if True:\n            _SESSIONE_DI_PROCESSO = SessioneBetfair(**opzioni)", "nuova sessione a ogni chiamata"),
    ("S07", B + "sessione.py", '            raise auth.BetfairStreamAuthError(f"Cert login Betfair fallito ({type(e).__name__})") from e',
     "            raise", "errore del primo login grezzo"),
    ("S08", B + "sessione.py", "        return self._sessione._keep_alive_contato()", "        return self._sessione._login_frenato()",
     "keepAlive sostituito dal login"),
    ("S09", B + "sessione.py", "PERIODO_KEEPALIVE_DI_SERIE_S = 480.0", "PERIODO_KEEPALIVE_DI_SERIE_S = 900.0",
     "periodo di serie diverso da oggi"),
    ("S10", B + "sessione.py", "        t.start()", "        pass", "avvia non avvia"),
    ("S11", B + "sessione.py", "        while not self._ferma.wait(intervallo_s):", "        while not time.sleep(intervallo_s):",
     "ferma non ferma"),
    ("S12", B + "sessione.py", '                "nome": self.nome,',
     '                "nome": self.nome + str(getattr(self._client, "session_token", "")),', "token nello stato"),
    ("S13", B + "sessione.py", '        self.salute.evento_sessione("login")\n', "", "login non contato"),
    ("S14", B + "sessione.py", "            auth.safe_logout(client)", "            pass", "nessun logout alla chiusura"),
    ("S15", B + "sessione.py", "            if self._custode is None:\n                self._primo_login()",
     "            if True:\n                self._primo_login()", "login a ogni client()"),
    ("S16", B + "sessione.py", "            return bool(custode.segnala_errore(exc))\n", "            return True\n", "segnala accetta tutto"),
    ("S17", B + "sessione.py", "TETTO_LOGIN_RIUSCITI_DI_SERIE = limiti.tetto_login_per_processo(10)",
     "TETTO_LOGIN_RIUSCITI_DI_SERIE = 100", "tetto di serie = tutto il conto"),
    ("S18", B + "sessione.py", "    return limiti.CODICE_BAN_LOGIN in _testo_catena(exc)", "    return False", "ban non riconosciuto"),
    ("S19", B + "sessione.py",
     '        if tetto_riusciti_al_minuto > limiti.LOGIN_RIUSCITI_AL_MINUTO_PER_CONTO:\n            raise ValueError("tetto dei login oltre il limite del conto (100/min)")\n',
     "", "tetto oltre il conto accettato"),
    ("S20", B + "sessione.py", "            elif len(self._tentativi) >= self.tetto_tentativi:", "            elif False:",
     "tetto dei tentativi spento"),
    ("S21", B + "sessione.py", "        freno.registra_tentativo(adesso)\n", "", "tentativi non registrati"),
    ("S22", B + "sessione.py", '            self.salute.evento_sessione("keepalive_falliti")\n', "", "keepAlive falliti non contati"),
    ("S23", B + "sessione.py", "            esito = self._custode.tick(adesso)", "            esito = None", "rinnova non rinnova"),
    ("S24", B + "sessione.py", '                "periodo_keepalive_s": self.periodo_keepalive_s,\n', "", "stato senza periodo"),
    ("S25", B + "sessione.py", "        except LoginFrenato as e:\n            self.salute.evento_sessione(\"login_frenati\")",
     "        except LoginFrenato as e:\n            self.salute.evento_sessione(\"login\")", "frenati contati come login"),
    # ---------------- rest.py
    ("R01", B + "rest.py", "            if not self._rifai_mutazione or not rifiuto_di_sessione(e):\n                raise",
     "            if False:\n                raise", "MUTAZIONE RITENTATA su qualunque errore"),
    ("R02", B + "rest.py", "            if not self._rifai_mutazione or not rifiuto_di_sessione(e)", "            if not rifiuto_di_sessione(e)",
     "interruttore della ripetizione ignorato"),
    ("R03", B + "rest.py", '                if classe == "limite":\n', '                if classe == "limitex":\n', "limite ritentato"),
    ("R04", B + "rest.py", '                if classe == "permanente" or tentativo', '                if tentativo', "permanente ritentato"),
    ("R05", B + "rest.py", "                    self._dormi(self.politica.pausa(tentativo))", "                    pass",
     "nessuna pausa sulla rete"),
    ("R06", B + "rest.py",
     '                if classe == "sessione":\n                    if not self._sessione.rifai_login(e, self._generazione_usata()):\n                        raise',
     '                if classe == "sessione":\n                    pass', "sessione ritentata senza relogin"),
    ("R07", B + "rest.py", "        if peso is None or \"market_ids\" not in kwargs:", "        if True:", "nessuna suddivisione per peso"),
    ("R08", B + "rest.py", "        sem = self._semaforo() if limiti.e_metodo_conteso(metodo, kwargs) else None", "        sem = None",
     "nessun tetto delle 3 concorrenti"),
    ("R09", B + "rest.py", "            self._tetto = tetto_del_conto(self._sessione.conto, self._concorrenti)",
     "            self._tetto = threading.BoundedSemaphore(self._concorrenti)", "tetto per cliente e non per conto"),
    ("R10", B + "rest.py", "        if metodo in MUTAZIONI:\n            raise ValueError", "        if False:\n            raise ValueError",
     "lettura accetta le mutazioni"),
    ("R11", B + "rest.py", '    if isinstance(exc, (ValueError, LookupError)):\n        return "permanente"',
     '    if isinstance(exc, (ZeroDivisionError,)):\n        return "permanente"', "permanenti non riconosciuti"),
    ("R12", B + "rest.py", "    base = _descrivi_errore(exc)", "    base = str(exc)", "descrizione col testo intero (token)"),
    ("R13", B + "rest.py", "        self._tls.generazione = self._sessione.generazione\n", "", "generazione letta prima del login"),
    ("R14", B + "rest.py", "            risultati.extend(parziale or [])", "            risultati[:0] = list(parziale or [])", "ordine dei blocchi perso"),
    ("R15", B + "rest.py", "            if i and self._pausa_blocchi > 0:", "            if self._pausa_blocchi > 0:",
     "pausa anche prima del primo blocco"),
    ("R16", B + "rest.py", "            if not preso:\n                raise CodaContoPiena", "            if False:\n                raise CodaContoPiena",
     "coda piena ignorata"),
    ("R17", B + "rest.py", '                self.salute.esito_rest(metodo, classifica_errore(e), ms, descrivi_errore(e))\n', "",
     "esiti d'errore non contati"),
    ("R18", B + "rest.py", "        return float(self.pause_s[min(ritento - 1, len(self.pause_s) - 1)])", "        return float(self.pause_s[0])",
     "pause sempre la prima"),
    ("R19", B + "rest.py", "    if isinstance(exc, Exception) and _is_limit(exc):\n        return \"limite\"",
     "    if False:\n        return \"limite\"", "limite non riconosciuto"),
    ("R20", B + "rest.py", '            raise ValueError(f"metodo REST sconosciuto: {metodo}")', "            pass", "metodo sconosciuto chiamato"),
    ("R21", B + "rest.py", "        if metodo not in MUTAZIONI:\n            raise ValueError", "        if False:\n            raise ValueError",
     "mutazione accetta le letture"),
    ("R22", B + "rest.py", "            self.salute.esito_rest(metodo, \"ok\", (self._orologio() - t0) * 1000.0)",
     "            self.salute.esito_rest(metodo, \"ok\", 0.0)", "latenza falsa"),
    ("R23", B + "rest.py", "        elif _CAPIENZA_PER_CONTO[conto] != int(capienza):", "        elif False:", "capienze diverse accettate"),
    ("R24", B + "rest.py", "            self.salute.attesa_tetto((self._orologio() - t0) * 1000.0)\n", "", "attesa non misurata"),
    ("L15", B + "limiti.py", 'METODI_CONTESI: Tuple[str, ...] = ("listCurrentOrders", "listMarketProfitAndLoss")',
     'METODI_CONTESI: Tuple[str, ...] = ("listMarketProfitAndLoss",)', "listCurrentOrders non conteso"),
    ("L16", B + "limiti.py", "        return parametri.get(\"order_projection\") is not None or parametri.get(\"match_projection\") is not None\n    return False",
     "        return parametri.get(\"order_projection\") is not None or parametri.get(\"match_projection\") is not None\n    return True", "tutto conteso"),
    ("L17", B + "limiti.py", '    "": 2,', '    "": 3,', "peso senza proiezione"),
    ("L18", B + "limiti.py", '    "EX_BEST_OFFERS": 5,', '    "EX_BEST_OFFERS": 4,', "peso EX_BEST_OFFERS"),
    ("R25", B + "rest.py", '    if e_errore_di_sessione(exc):\n        return "sessione"', '    if False:\n        return "sessione"', "sessione non riconosciuta"),
    ("R26", B + "rest.py", '        return "permanente"\n    return "rete"', '        return "permanente"\n    return "permanente"', "rete come permanente"),
    ("R27", B + "rest.py", "    def lettura(self, metodo: str, **kwargs: Any) -> Any:", "    def lettura(self, nome_metodo: str, **kwargs: Any) -> Any:\n        metodo = nome_metodo", "firma diversa dal contratto"),
    ("S26", B + "sessione.py", "    def rinnova_se_serve(self) -> None:", "    def rinnova_se_occorre(self) -> None:", "metodo del contratto mancante"),
    ("L19", B + "limiti.py", 'METODI_CONTESI: Tuple[str, ...] = ("listCurrentOrders", "listMarketProfitAndLoss")',
     'METODI_CONTESI: Tuple[str, ...] = ("listCurrentOrders",)', "P&L non conteso"),
    ("L20", B + "limiti.py", 'return parametri.get("order_projection") is not None or', 'return parametri.get("order_projection") is None or', "conteso senza ordini"),
    # ---------------- correzioni dopo la revisione indipendente
    ("R28", B + "rest.py", "    for anello in (exc, exc.__cause__):", "    for anello in (exc, exc.__cause__, exc.__context__):",
     "ALTA-1: rifiuto letto anche dal __context__"),
    ("R29", B + "rest.py", "            if not self._rifai_mutazione or not rifiuto_di_sessione(e)",
     "            if not self._rifai_mutazione or classifica_errore(e) != \"sessione\"", "ALTA-1: mutazione classificata come le letture"),
    ("R30", B + "rest.py", "            if not self._rifai_mutazione or not rifiuto_di_sessione(e)", "            if not self._rifai_mutazione",
     "mutazione ripetuta su qualunque errore dopo un relogin di altri (mutazione sopravvissuta)"),
    ("R31", B + "rest.py", '        if isinstance(kwargs.get("market_ids"), str):', '        if False:', "market_ids stringa spezzata"),
    ("R32", B + "rest.py", "        if peso > limiti.PESO_MASSIMO_RICHIESTA:", "        if False:", "un mercato oltre 200: ValueError locale"),
    # (10/10: la stringa porta la riga dopo: ``if self.in_backoff():`` c'e' anche in ``segnala_errore``)
    ("S27", B + "sessione.py", "            if self.in_backoff():\n                logger.warning(",
     "            if False:\n                logger.warning(", "ALTA-2: backoff scavalcato"),
    ("S28", B + "sessione.py", "        return freno_del_conto(self.conto, self._ora)", "        return FrenoLogin(ora=self._ora)", "MEDIA-5: freno per istanza"),
    ("S29", B + "sessione.py", "        if client is not None and self._custode is not None:\n            return client",
     "        if False:\n            return client", "MEDIA-3: niente via veloce"),
    ("S30", B + "sessione.py", "        if not 0 < float(periodo_keepalive_s) <= PERIODO_KEEPALIVE_MASSIMO_S:", "        if False:", "periodo non validato"),
    ("S31", B + "sessione.py", "            loggata, self._custode = self._custode is not None, None",
     "            loggata, self._custode = self._custode is not None, None\n            self.generazione = 0", "generazione azzerata da chiudi"),
    ("S32", B + "sessione.py", "MARGINE_BAN_S = 30.0", "MARGINE_BAN_S = 0.0", "ban senza margine"),
    ("S33", B + "sessione.py", "        if custode is None or custode.fallimenti <= 0:\n            return False\n        return not custode.dovuto(adesso)",
     "        return False", "in_backoff sempre falso"),
    ("L21", B + "limiti.py", "max(Fraction(1), Fraction(profondita, 3))", "Fraction(profondita, 3)", "profondita' < 3 sotto il peso base"),
    ("L22", B + "limiti.py", "if isinstance(profondita, bool) or not isinstance(profondita, int) or profondita < 1:",
     "if profondita < 1:", "profondita' bool/decimale accettata"),
    ("S34", B + "sessione.py", "        if not 0 < float(periodo_keepalive_s) <= PERIODO_KEEPALIVE_MASSIMO_S:",
     "        if not 0 < float(periodo_keepalive_s) < PERIODO_KEEPALIVE_MASSIMO_S:", "bordo del periodo escluso"),
    ("R33", B + "rest.py", "        if any(k in testo for k in _ERRORI_DI_SESSIONE):\n            return True",
     "        if False:\n            return True", "rifiuto di sessione mai riconosciuto"),
    ("R34", B + "rest.py", "    return False\n\n\ndef descrivi_errore", "    return True\n\n\ndef descrivi_errore", "ogni errore e' un rifiuto di sessione"),
    # ---------------- mutazioni del REVISORE (seconda revisione, scratchpad/rev_w1a1_2/mie_mut.py)
    ('X01', B + 'rest.py', '            if not self._sessione.rifai_login(e, self._generazione_usata()):\n                raise\n            logger.warning("[rest-a1] %s: sessione non valida, relogin fatto',
     '            if False:\n                raise\n            logger.warning("[rest-a1] %s: sessione non valida, relogin fatto', "ALTA-1/2: mutazione ripetuta anche se il relogin e' rifiutato (backoff/freno)"),
    ('X02', B + 'limiti.py', '    if metodo in METODI_CONTESI:\n        return True',
     '    if metodo in METODI_CONTESI or metodo in METODI_MUTAZIONE:\n        return True', 'ALTA-1: le mutazioni si mettono in coda sul semaforo del conto'),
    ('X03', B + 'sessione.py', '        return not custode.dovuto(adesso)',
     '        return custode.dovuto(adesso)', 'ALTA-2: in_backoff invertito'),
    ('X04', B + 'sessione.py', '        if custode is None or custode.fallimenti <= 0:',
     '        if custode is None or custode.fallimenti < 0:', 'ALTA-2: in_backoff vero anche senza fallimenti'),
    ('X05', B + 'sessione.py', '        with self._lock_custode:\n            if self._custode is None:\n                return None\n            esito = self._custode.tick(adesso)',
     '        with self._lock_custode, self._lock:\n            if self._custode is None:\n                return None\n            esito = self._custode.tick(adesso)', "MEDIA-3: rinnova tiene anche il lucchetto dei campi durante l'HTTP"),
    ('X06', B + 'sessione.py', '        with self._lock_custode, self._lock:\n            client, self._client = self._client, None',
     '        with self._lock:\n            client, self._client = self._client, None', 'MEDIA-3: chiudi senza lucchetto del custode'),
    ('X07', B + 'sessione.py', '    chiave = (str(conto), id(orologio))',
     '    chiave = (id(orologio),)', 'MEDIA-5: freno condiviso fra conti diversi'),
    ('X08', B + 'sessione.py', '    if s is not None:\n        s.chiudi()',
     '    if s is not None:\n        s.chiudi()\n        _FRENI_PER_CONTO.clear()', 'MEDIA-5: chiudi_sessione_del_processo dimentica freno e ban'),
    ('X09', B + 'rest.py', '            blocchi = [[m] for m in kwargs["market_ids"]]',
     '            blocchi = [list(kwargs["market_ids"])]', 'MEDIA-6: oltre 200 punti: tutti i mercati in UNA richiesta'),
    ('X10', B + 'limiti.py', '        if "BEST_OFFERS" in k and "ALL_OFFERS" not in k:',
     '        if k == "EX_BEST_OFFERS":', "MEDIA-6: profondita' non applicata alla combinazione BEST+TRADED"),
    ('X11', B + 'limiti.py', 'base = base * max(Fraction(1), Fraction(profondita, 3))',
     'base = base * max(Fraction(1), Fraction(profondita, 2))', 'MEDIA-6: divisore 2 al posto di 3'),
    ('X12', B + 'rest.py', '    for anello in (exc, exc.__cause__):',
     '    for anello in (exc,):', 'ALTA-1: rifiuto non letto dalla causa esplicita'),
    ('X13', B + 'sessione.py', '            if not self._custode.segnala_errore(exc):\n                return False\n            esito = self._custode.tick()',
     '            esito = self._custode.tick()', "ALTA-2: rifai_login rifa' il login anche per errori NON di sessione (se tick e' dovuto)"),
    ('X14', B + 'sessione.py', '            if self.generazione != generazione_vista:\n                return True\n            if self.in_backoff():',
     '            if self.generazione < generazione_vista:\n                return True\n            if self.in_backoff():', 'E: generazione: > diventa <'),
    # ---------------- decisione 2 dell'utente (10/10/2026): anche segnala_errore rispetta il backoff
    ("D2a", B + "sessione.py", "            if self.in_backoff():\n                # adesso = +inf",
     "            if False:\n                # adesso = +inf", "D2: scavalcamento del backoff rimesso (come auth.py di oggi)"),
    ("D2b", B + "sessione.py", "                return bool(custode.segnala_errore(exc, adesso=math.inf))",
     "                return True", "D2: errore nel backoff accettato ma NON preso in carico"),
    ("D2c", B + "sessione.py", "                return bool(custode.segnala_errore(exc, adesso=math.inf))",
     "                return False", "D2: errore nel backoff rifiutato (perso)"),
    ("D2d", B + "sessione.py", "                return bool(custode.segnala_errore(exc, adesso=math.inf))",
     "                return bool(custode.segnala_errore(exc))", "D2: nel backoff il giro torna ad ADESSO"),
    ("D2e", B + "sessione.py", "            return bool(custode.segnala_errore(exc))\n",
     "            return bool(custode.segnala_errore(exc, adesso=math.inf))\n", "D2: fuori dal backoff il giro NON e' piu' anticipato"),
    # (revisione di 2d38504f: R7 del revisore, ora falsificata dalla proprieta' "nessun keepAlive in volo al ritorno")
    ("D2f", B + "sessione.py",
     "        with self._lock_custode:\n            custode = self._custode\n            if custode is None:\n                return False\n            if self.in_backoff():",
     "        if True:\n            custode = self._custode\n            if custode is None:\n                return False\n            if self.in_backoff():",
     "D2/R7: segnala_errore senza il lucchetto del custode (non aspetta il keepAlive in volo)"),
    # ---------------- il finto (le sue prove devono saper diventare rosse)
    ("F01", T + "test_a1_finto_betfair.py", '"Content-Encoding": "gzip",', '"Content-Encoding": "identity",', "finto senza gzip dichiarato"),
    ("F02", T + "test_a1_finto_betfair.py", "            if peso_finto(params.get(\"priceProjection\")) * len(ids) > 200:", "            if False:",
     "finto senza TOO_MUCH_DATA"),
    ("F03", T + "test_a1_finto_betfair.py", "return t is not None and self.ora() - t < VITA_SESSIONE_FINTO_S", "return t is not None",
     "finto senza scadenza"),
    ("F04", T + "test_a1_finto_betfair.py", "            self.ban_fino = a + 1200.0", "            self.ban_fino = a + 30.0", "finto con ban corto"),
    ("F05", T + "test_a1_finto_betfair.py", '"availableToBack": [{"price": b, "size": 120.5}',
     '"availableToBack": [{"price": b + 1, "size": 120.5}', "finto con prezzo diverso"),
    ("F06", T + "test_a1_finto_betfair.py", "            troppi = conteso and self.applica_concorrenza and self.contesi_in_volo > 3",
     "            troppi = False", "finto senza tetto delle concorrenti"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def gira():
    try:
        return _gira()
    except subprocess.TimeoutExpired:
        return ["TIMEOUT (test bloccato: la mutazione e' vista)"], "timeout"


def _gira():
    r = subprocess.run([sys.executable, "-P", "-m", "pytest", os.path.join(SB, T), "-q", "-p", "no:cacheprovider",
                        "--tb=no", "-rf"],
                       env={**os.environ, "PYTHONPATH": SB}, capture_output=True, text=True, timeout=300)
    rossi = sorted(set(re.findall(r"^FAILED (\S+)", r.stdout, re.M)) | set(re.findall(r"^ERROR (\S+)", r.stdout, re.M)))
    righe = [l for l in r.stdout.splitlines() if l.strip()]
    return rossi, (righe[-1] if righe else r.stderr[-300:])


risultati = []
for mid, rel, vecchio, nuovo, descr in M:
    if SOLO and mid not in SOLO:
        continue
    p = os.path.join(SB, rel)
    prima = sha(p)
    testo = open(p, encoding="utf-8").read()
    if testo.count(vecchio) < 1:
        risultati.append({"id": mid, "descr": descr, "errore": "stringa non trovata"})
        print(mid, "STRINGA NON TROVATA", flush=True)
        continue
    open(p, "w", encoding="utf-8").write(testo.replace(vecchio, nuovo, 1))
    try:
        rossi, ultima = gira()
    finally:
        open(p, "w", encoding="utf-8").write(testo)
    dopo = sha(p)
    risultati.append({"id": mid, "file": rel, "descr": descr, "rossi": rossi, "n_rossi": len(rossi),
                      "riepilogo": ultima, "sha_prima": prima, "sha_dopo": dopo, "ripristino_ok": prima == dopo})
    print(mid, len(rossi), "rossi |", ultima, "| sha ok" if prima == dopo else "| SHA DIVERSO", flush=True)

json.dump(risultati, open(OUT, "w"), indent=1)
