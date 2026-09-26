p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
a = "**(3) Runner tennis / bot tennis: NON sani dalle 10:42Z.**"
assert a in s
add = """**Il momento della morte della subscription (10:39:30-10:44:00Z, `morte_subscription_1040_1044.txt`, 5008
messaggi):** nessun `auto_follow`, nessun `NEW_MATCHES`, nessun errore di stream né variazione di
`mercati_sottoscritti` sul 47331 nella finestra. Il fatto è un altro: **alle 10:41:41Z TUTTI i canali tacciono
insieme**. Ultimi messaggi: safe_attivita 10:41:41, tennis_bot_stato 10:41:38-39, runner battito 10:41:30. Il
messaggio successivo arriva alle 10:42:09 (scanner_stato), poi `modo_ordini` 10:42:27 (ripubblicato), `mike_stato`
10:42:35, battito del runner 10:42:36. Quindi ~28-55 s di silenzio su processi DIVERSI (runner calcio, tennis,
Omega, Mike, Safe, scanner) nello stesso istante. È una sospensione di tutta la macchina o della rete, non un
difetto del singolo runner. Due indizi concordanti: le mie sonde verso Supabase hanno fallito con
`getaddrinfo failed` subito dopo, e Claude Code ha fermato i miei processi di registrazione «per memoria del
sistema criticamente bassa». Dopo la ripresa i battiti tornano, ma ladder/raw del runner calcio e tennis e le
decisioni dei bot tennis non ripartono più: la subscription non si è riconnessa e nessun controllo di stallo
l'ha rilevata per ~4 h (vedi l'ipotesi di admin-26 su `runner.py:1192`, non verificata da me). Numeri del
coordinatore sulle stesse registrazioni, ladder per 5 min: 10:00 1707, 10:05 2880, …, 10:35 3024, 10:40 998,
poi zero con battito vivo fino alle 10:58Z; prezzi che cambiano su 1.262887882 (3,0 → 2,66 → 2,44 → 2,42 →
2,10). **Finestra NON CERTIFICATA «runner cieco»: 10:41:41Z → riavvio dell'app. Fra le 10:01 e le 10:41Z i
controlli restano validi.**

"""
s = s.replace(a, add + a, 1)
open(p, "w", encoding="utf8").write(s)
print("ok")
