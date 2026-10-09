# Brief comune dei certificatori (fase 2, 09/10/2026)

R = C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation. Cartella audit: R/ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/ (= AU).
Leggi: AU/BRIEF_FASE2_CERTIFICA_E_FIX_DUTCHING.md (par. 0-1), AU/verifica_coordinatore/ESITO_VERIFICA.md e i referti
V1_ML.md, V2_POISSON.md, V3_BOT.md nella stessa cartella (INPUT, non verita': riverifica dove li contraddici o li estendi).

VINCOLI: sola lettura su tutto il repo. Scrivi SOLO il tuo file in AU/lavori/fase2/ ed eventuali sonde in AU/lavori/fase2/sonde/.
Niente git commit/checkout/stash/add. MAI terminare processi (niente kill/taskkill/Stop-Process). Niente grep ricorsivi
sulla radice (log da 3 GB): usa `git grep`. DB: solo se indispensabile, max 3 SELECT con LIMIT <= 500. Nessuna rete Betfair.
Python: R/.venv/Scripts/python.exe -I.

PER OGNI REPERTO ASSEGNATO:
1. Rileggi il codice citato alle righe ATTUALI (le righe possono essere cambiate): la riga dice cio' che il reperto afferma?
   il percorso e' VIVO (chiamato da codice di produzione, workflow, UI)? CHI lo consuma (bot, UI, foglio, report)? quale
   decisione dipende da quel numero? Cita file:riga attuali.
2. Cerca se e' gia' noto, gia' deciso o gia' corretto: `git grep -n -i "<parole chiave>" -- CRONOSTORIA.md`
   (leggi le righe intorno), `Betfair/*/COSTITUZIONE_*.md`, `PIANO_MODIFICHE_MIKE_2026-09-29.md`,
   `AUDIT_2026-10-02/AUDIT_ML_POISSON.md` e gli altri `AUDIT_2026-*/`. Una scelta documentata dell'utente NON e' un errore.
3. Stato di certificazione dei bot: SOLO da CRONOSTORIA.md e referti del banco (citali con riga); mai "non risulta".
4. I numeri del reperto si rifanno con codice TUO (sonda nuova), non con le sonde della fase 1.
5. Verdetto: CONFERMATO / FALSO / RIDIMENSIONATO / SCELTA DOCUMENTATA / GIA' NOTO (riferimento) — si possono combinare
   (es. "CONFERMATO, GIA' NOTO (CRONOSTORIA.md:4888)"). Gravita' ricalcolata: CRITICO / ALTO / MEDIO / BASSO / NESSUNA,
   con il criterio: soldi dei bot su percorso vivo > strumento manuale con soldi veri > numeri mostrati/report > coerenza.
   Cio' che non puoi verificare: "NON VERIFICATO" + motivo.

FORMATO DEL FILE (scrivilo man mano, PRIMA di rispondere):
| reperto | verdetto | gravita' (prima -> dopo) | prova (file:riga attuali, output sonda) | gia' noto/deciso (riferimento) | come ho verificato | NON VERIFICATO |
Poi una sezione "Correzioni da applicare alle consegne" (file, punto, testo sbagliato -> testo giusto).
Risposta finale al coordinatore: max 20 righe.
