"""
aggiorna_mm_sheets.py
=====================
Genera fogli Google Sheets con Money Management.
Ora i fogli sono RESPONSIVI/LIVE usando le API di traduzione
automatica di Google Sheets (formulaValue), aggirando i problemi di
sintassi della lingua italiana (#ERROR! / virgole vs punti).
"""

import json
import os
import sys
import logging
import time as time_module

import gspread

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config

logger = logging.getLogger("mm_sheets")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

HISTORY_FILE = os.path.join(ROOT, "Betfair", "mm_history.json")
COLS = 16
MIN_SIGNALS = 3

# Betfair charges commission on NET winnings only. The live P&L formula on the MM
# sheet must net it out to stay consistent with money_management.py (same 5%).
# Without it the sheet's P&L / Cassa / Yield were overstated by COMMISSION * net
# profit on every winning bet (both the ML and Poisson columns).
MM_COMMISSION = 0.05
MM_NET_FACTOR = round(1.0 - MM_COMMISSION, 4)  # 0.95

# max_stake_pct per masaniello_puro:
#   La garanzia matematica (profitto invariante all'ordine) richiede che il cap NON
#   vincoli mai gli stake naturali del sistema. Calcoli mostrano che per q≈2.0
#   lo stake massimo naturale è ~25-38% del bankroll corrente (caso PPP...VVV).
#   Con cap=35%: garanzia quasi sempre rispettata per N≥15 e q≥2.0.
#   Con cap=20%: più conservativo, ma il profitto può scendere sotto il target
#   nei casi sfavorevoli (ordine perdite-prima). Abbassare solo in caso di
#   gestione del rischio critica.
DEFAULTS = {
    "masaniello":      {"bankroll": 100, "target": 20, "wr_pct": 50, "max_stake_pct": 20},
    "masaniello_sl":   {"bankroll": 100, "target": 20, "wr_pct": 50, "stop_loss_pct": 50, "max_stake_pct": 20},
    "flat":            {"bankroll": 100, "stake_pct": 3, "stop_profit": 20, "stop_loss": 30},
    "masaniello_puro": {"bankroll": 100, "target": 20, "wr_pct": 50, "max_stake_pct": 35},
}

def _find_pvirt_normalized(W_tot: int, N: int, avg_q: float, p: float, n_iters: int = 80) -> float:
    """
    Calcola il P_virt per unità di target (target = 1.0, bankroll = 0).

    Il Masaniello puro garantisce che vincendo esattamente W_tot su N scommesse
    il profitto sia esattamente = target, indipendentemente dall'ordine.
    Questa funzione restituisce il fattore di scala:
        P_virt = _find_pvirt_normalized(...) * target
    da moltiplicare poi per $B$3 nella formula Sheets.

    La ricerca binaria simula lo scenario worst-case (tutte le perdite prima delle
    vittorie) che è invariante all'ordine per costruzione del Masaniello.
    """
    from math import comb as _comb

    def _cdf(k, n, q):
        if k < 0: return 0.0
        if k >= n: return 1.0
        return sum(_comb(n, i) * (q ** i) * ((1 - q) ** (n - i)) for i in range(k + 1))

    def _profit(PV: float) -> float:
        bank = 0.0
        wins = 0
        for i in range(N):
            won = i >= (N - W_tot)          # ultime W_tot posizioni = vittorie
            rem_after = N - i - 1
            wn = W_tot - wins
            if wn <= 0 or wn > (rem_after + 1):
                continue
            c_lose = PV * _cdf(wn - 1, rem_after, p)
            c_win  = PV * _cdf(wn - 2, rem_after, p)
            stake  = max(1e-12, (c_lose - c_win) / avg_q)
            bank  += stake * (avg_q - 1) if won else -stake
            if won:
                wins += 1
        return bank

    lo, hi = 1e-9, 1e9
    for _ in range(n_iters):
        mid = (lo + hi) / 2
        if _profit(mid) < 1.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _sheets_retry(func, *args, max_retries=5, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if attempt < max_retries - 1:
                time_module.sleep(5 * (2 ** attempt))
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                time_module.sleep(5 * (2 ** attempt))
            else:
                raise
    return None

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_signals(day, key):
    out = []
    for s in day.get(key, []):
        won = "VINTO" in str(s.get("result", ""))
        out.append({
            "slot_id": s.get("slot_id", ""),
            "event_name": s.get("event_name", ""),
            "market_label": s.get("market_label", ""),
            "odds": max(s.get("odds", 1.01), 1.01),
            "won": won,
            "is_pending": s.get("result") == "PENDING",
            "original_result": s.get("result", "PENDING"),
        })
    return out

def read_sheet_config(ws, strategy):
    defaults = DEFAULTS[strategy].copy()
    try:
        row3 = _sheets_retry(ws.row_values, 3)
        if row3 and len(row3) >= len(defaults):
            keys = list(defaults.keys())
            for i, k in enumerate(keys):
                try:
                    val = str(row3[i]).strip().replace(",", ".").replace("%", "").replace("€", "")
                    if val:
                        defaults[k] = float(val)
                except:
                    pass
    except Exception:
        pass
    return defaults

def build_config_rows(strategy, params):
    keys = list(DEFAULTS[strategy].keys())
    labels_map = {
        "bankroll": "Bankroll (EUR)", "target": "Target (EUR)", "wr_pct": "WR Atteso %",
        "max_stake_pct": "Max Stake %", "stop_loss_pct": "Stop Loss %",
        "stake_pct": "Stake %", "stop_profit": "Stop Profit (EUR)", "stop_loss": "Stop Loss (EUR)",
    }
    labels = [labels_map.get(k, k) for k in keys]
    values = [params[k] for k in keys]
    labels += [""] * (COLS - len(labels))
    values += [""] * (COLS - len(values))
    return labels[:COLS], values[:COLS]

DARK_BG = {"red": 0.06, "green": 0.06, "blue": 0.12}
WHITE = {"red": 1, "green": 1, "blue": 1}
GOLD = {"red": 1, "green": 0.84, "blue": 0}
POIS_BG = {"red": 0.1, "green": 0.3, "blue": 0.15}
POIS_HEADER = {"red": 0.85, "green": 0.93, "blue": 0.85}
POIS_LIGHT = {"red": 0.93, "green": 0.97, "blue": 0.93}
ML_BG = {"red": 0.2, "green": 0.1, "blue": 0.35}
ML_HEADER = {"red": 0.88, "green": 0.85, "blue": 0.95}
ML_LIGHT = {"red": 0.95, "green": 0.93, "blue": 0.98}
STATS_BG = {"red": 0.95, "green": 0.95, "blue": 0.95}
WIN_BG = {"red": 0.85, "green": 0.95, "blue": 0.85}
LOSS_BG = {"red": 0.97, "green": 0.87, "blue": 0.87}
PEND_BG = {"red": 0.96, "green": 0.96, "blue": 0.96}
GREEN_TXT = {"red": 0.05, "green": 0.5, "blue": 0.05}
RED_TXT = {"red": 0.7, "green": 0.1, "blue": 0.1}
CFG_BG = {"red": 0.95, "green": 0.95, "blue": 0.80}
CFG_LABEL_BG = {"red": 0.90, "green": 0.90, "blue": 0.75}

def get_live_formulas(strategy, r_idx, start_r, N_day, avg_q, side, pvirt_norm=None):
    """
    Ritorna le stringhe delle formule in formato INGLESE usando il punto-virgola (;)
    come separatore di argomenti (standard italiano per Google Sheets).
    Google Sheets API (userEnteredValue.formulaValue) le interpreta correttamente.

    pvirt_norm: per masaniello_puro, il fattore P_virt/target pre-calcolato in Python
                tramite _find_pvirt_normalized(). Se None, viene calcolato qui.
    """
    is_pois = (side == "P")
    bank_in = "$A$3"

    if is_pois:
        c_Q, c_R, c_S, c_P, _ = f"D{r_idx}", f"E{r_idx}", f"F{r_idx}", f"G{r_idx}", f"H{r_idx}"
        past_R = f"$E${start_r}:E{r_idx-1}"
        past_S = f"$F${start_r}:F{r_idx-1}"
        prev_C = bank_in if r_idx == start_r else f"H{r_idx-1}"
    else:
        c_Q, c_R, c_S, c_P, _ = f"L{r_idx}", f"M{r_idx}", f"N{r_idx}", f"O{r_idx}", f"P{r_idx}"
        past_R = f"$M${start_r}:M{r_idx-1}"
        past_S = f"$N${start_r}:N{r_idx-1}"
        prev_C = bank_in if r_idx == start_r else f"P{r_idx-1}"

    # VINTO → net profit = stake*(quota-1)*(1-commission); PERSO → -stake.
    # The (1-commission) factor nets out the Betfair commission charged on winnings.
    f_pnl   = f'=IF(OR({c_S}="--"; LEFT({c_R}; 7)="PENDING"; {c_R}=""); "--"; IF(LEFT({c_R}; 5)="VINTO"; ROUND({c_S}*({c_Q}-1)*{MM_NET_FACTOR}; 2); -{c_S}))'
    f_cassa = f'=IF({c_S}="--"; {prev_C}; ROUND({prev_C} + {c_P}; 2))'

    wins_p = "0" if r_idx == start_r else f'COUNTIFS({past_R}; "VINTO*"; {past_S}; "<>--")'
    rem    = f"({N_day} - {r_idx} + {start_r})"

    if strategy == "flat":
        # Flat stake: % fissa del bankroll corrente, fermati al stop-profit/loss.
        cond_skip = f'OR({c_R}=""; LEFT({c_R}; 7)="PENDING"; {prev_C}>={bank_in}+$C$3; {prev_C}<={bank_in}-$D$3)'
        f_stk = f'=IF({cond_skip}; "--"; ROUND(MAX(1/100; ROUND({prev_C}*$B$3/100; 2)); 2))'

    elif strategy == "masaniello_puro":
        # -----------------------------------------------------------------------
        # MASANIELLO PURO (binomiale) — FORMULA CORRETTA
        #
        # P_virt = pvirt_norm * $B$3   dove pvirt_norm è calcolato in Python
        # in modo che, vincendo esattamente W su N, il profitto = $B$3 (target).
        #
        # La formula delle stake è:
        #   stake_i = P_virt * [CDF(wn-1; rem-1; p) - CDF(wn-2; rem-1; p)] / quota_i
        #           = P_virt * PMF(wn-1; rem-1; p) / quota_i
        #
        # Proprietà garantita: profitto invariante all'ordine delle vincite/perdite.
        # -----------------------------------------------------------------------
        W_tot_int = max(1, int(N_day * DEFAULTS["masaniello_puro"]["wr_pct"] / 100))
        p = 1.0 / max(avg_q, 1.05)
        if pvirt_norm is None:
            pvirt_norm = _find_pvirt_normalized(W_tot_int, N_day, max(avg_q, 1.05), p)

        q_int  = int(round(avg_q * 100))
        W_tot  = f'MAX(1; INT({N_day} * $C$3 / 100))'
        wn     = f'({W_tot} - {wins_p})'

        # P_virt scala con $B$3 (target): se l'utente modifica il target, le stake
        # si adeguano proporzionalmente. pvirt_norm è costante per questa giornata.
        P_virt = f'({pvirt_norm:.10f} * $B$3)'

        c_loss = f'{P_virt} * IFERROR(BINOMDIST({wn}-1; {rem}-1; 100/{q_int}; 1); 0)'
        c_win  = f'{P_virt} * IFERROR(BINOMDIST({wn}-2; {rem}-1; 100/{q_int}; 1); 0)'

        cond_skip = f'OR({c_R}=""; LEFT({c_R}; 7)="PENDING"; {wn}<=0; {prev_C}<=1/100; {wn}>{rem})'
        raw    = f'(({c_loss} - {c_win}) / {c_Q})'
        f_stk  = f'=IF({cond_skip}; "--"; ROUND(MAX(1/100; MIN({prev_C} * $D$3 / 100; {raw})); 2))'

    elif strategy == "masaniello_sl":
        # -----------------------------------------------------------------------
        # MASANIELLO CON STOP-LOSS — formula lineare + protezione floor
        #
        # BUG FIX: lo stake è ora cappato a (prev_C - floor_val) per garantire
        # che dopo una perdita la cassa non scenda MAI sotto il floor.
        # In precedenza il cap era applicato solo dopo la perdita (troppo tardi).
        # -----------------------------------------------------------------------
        W_tot     = f'MAX(1; INT({N_day} * $C$3 / 100))'
        wn        = f'({W_tot} - {wins_p})'
        tgt_val   = f'({bank_in} + $B$3)'
        floor_val = f'({bank_in} * (1 - $D$3/100))'

        # Skip se: risultato mancante/pending, vittorie raggiunte, cassa già a floor,
        # o gap residuo al target troppo piccolo.
        cond_skip  = f'OR({c_R}=""; LEFT({c_R}; 7)="PENDING"; {wn}<=0; {prev_C}<={floor_val}; ({tgt_val}-{prev_C})<=1/100)'
        raw        = f'IFERROR((({tgt_val} - {prev_C}) * ({wn} / {rem}) / ({c_Q} - 1)); 1/100)'
        # floor_cap: stake massimo che evita di bucare il floor in caso di perdita
        floor_cap  = f'MAX(1/100; {prev_C} - {floor_val})'
        f_stk      = f'=IF({cond_skip}; "--"; ROUND(MAX(1/100; MIN({prev_C} * $E$3 / 100; {floor_cap}; {raw})); 2))'

    else:
        # -----------------------------------------------------------------------
        # MASANIELLO LINEARE ("fake-linear")
        # Attenzione: questa formula NON è invariante all'ordine delle vincite.
        # Il profitto varia tra ~(target * 0.75) e target a seconda dell'ordine.
        # -----------------------------------------------------------------------
        W_tot     = f'MAX(1; INT({N_day} * $C$3 / 100))'
        wn        = f'({W_tot} - {wins_p})'
        tgt_val   = f'({bank_in} + $B$3)'
        cond_skip = f'OR({c_R}=""; LEFT({c_R}; 7)="PENDING"; {wn}<=0; {prev_C}<=1/2; {prev_C}>={tgt_val})'
        raw       = f'IFERROR((({tgt_val} - {prev_C}) * ({wn} / {rem}) / ({c_Q} - 1)); 1/100)'
        f_stk     = f'=IF({cond_skip}; "--"; ROUND(MAX(1/100; MIN({prev_C} * $D$3 / 100; {raw})); 2))'

    return f_stk, f_pnl, f_cassa

def build_sheet(sh, sheet_name, strategy, history):
    if sheet_name in {"Report Ven Dom", "Analytics", "Dashboard", "Prediction", "Betfair"}:
        return

    logger.info(f"Generazione foglio '{sheet_name}' LIVE FORMULAS...")

    try:
        ws = sh.worksheet(sheet_name)
        params = read_sheet_config(ws, strategy)
        _sheets_retry(ws.clear)
        old_rows = ws.row_count
        try:
            _sheets_retry(sh.batch_update, {"requests": [
                {"unmergeCells": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": old_rows, "startColumnIndex": 0, "endColumnIndex": COLS}}}
            ]})
        except: pass
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=3000, cols=COLS)
        params = DEFAULTS[strategy].copy()

    time_module.sleep(1)

    all_data = []
    fmt_reqs = []

    def add_row(values):
        padded = list(values) + [""] * (COLS - len(values))
        all_data.append(padded[:COLS])
        return len(all_data) - 1

    def add_fmt(r1, r2, fmt, c1=0, c2=COLS):
        fmt_reqs.append({"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": r1, "endRowIndex": r2 + 1, "startColumnIndex": c1, "endColumnIndex": c2},
            "cell": {"userEnteredFormat": fmt}, "fields": "userEnteredFormat"}})

    def add_merge(r_idx, c1, c2):
        fmt_reqs.append({"mergeCells": {"range": {"sheetId": ws.id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1, "startColumnIndex": c1, "endColumnIndex": c2}, "mergeType": "MERGE_ALL"}})

    labels_map = {"masaniello": "MASANIELLO", "masaniello_sl": "MASANIELLO + STOP LOSS", "flat": "FLAT STAKE", "masaniello_puro": "MASANIELLO PURO"}
    r = add_row([f"MM {labels_map.get(strategy, '')} -- Poisson vs ML (FORMULE LIVE)"])
    add_merge(r, 0, COLS)
    add_fmt(r, r, {"backgroundColor": DARK_BG, "textFormat": {"foregroundColor": {"red": 1, "green": 0.84, "blue": 0}, "bold": True, "fontSize": 16}, "horizontalAlignment": "CENTER"})

    labels_row, values_row = build_config_rows(strategy, params)
    r_lab = add_row(labels_row)
    add_fmt(r_lab, r_lab, {"backgroundColor": CFG_LABEL_BG, "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"})
    r_val = add_row(values_row)
    add_fmt(r_val, r_val, {"backgroundColor": CFG_BG, "textFormat": {"bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"})

    add_row([""]) 

    r = add_row(["POISSON", "", "", "", "", "", "", "", "MACHINE LEARNING", "", "", "", "", "", "", ""])
    add_merge(r, 0, 8)
    add_merge(r, 8, 16)
    add_fmt(r, r, {"backgroundColor": POIS_BG, "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13}, "horizontalAlignment": "CENTER"}, 0, 8)
    add_fmt(r, r, {"backgroundColor": ML_BG, "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13}, "horizontalAlignment": "CENTER"}, 8, 16)

    r = add_row(["P&L", "Yield", "Win Rate", "Vinte", "Perse", "Pend.", "Giorni", "", "P&L", "Yield", "Win Rate", "Vinte", "Perse", "Pend.", "Giorni", ""])
    add_fmt(r, r, {"backgroundColor": STATS_BG, "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": {"red": 0.3, "green": 0.3, "blue": 0.3}}, "horizontalAlignment": "CENTER"})

    def kpi_form(start_col, stk_col, pnl_col, res_col, n_days):
        won = f'COUNTIFS({res_col}11:{res_col}; "VINTO*"; {stk_col}11:{stk_col}; "<>--")'
        played = f'COUNTIF({stk_col}11:{stk_col}; "<>--")'
        lost = f'({played} - {won})'
        pend = f'COUNTIFS({res_col}11:{res_col}; "PENDING*"; {stk_col}11:{stk_col}; "<>--")'
        stk_sum = f'SUMIF({stk_col}11:{stk_col}; "<>--")'
        pnl_sum = f'SUMIF({pnl_col}11:{pnl_col}; "<>--")'
        wr = f'=IF({played}=0; "--"; ROUND({won}/{played}*100; 1) & "%")'
        yld = f'=IF({stk_sum}=0; "--"; ROUND({pnl_sum}/{stk_sum}*100; 2) & "%")'
        return [f'={pnl_sum}', f'={yld}', wr, f'={won}', f'={lost}', f'={pend}', str(n_days), ""]

    sorted_days = sorted(history, key=lambda d: d["date"])
    valid_d_p = sum(1 for d in sorted_days if len(extract_signals(d, "slots")) >= MIN_SIGNALS)
    valid_d_m = sum(1 for d in sorted_days if len(extract_signals(d, "ml_slots")) >= MIN_SIGNALS)

    r = add_row(kpi_form("A", "F", "G", "E", valid_d_p) + kpi_form("I", "N", "O", "M", valid_d_m))
    add_fmt(r, r, {"textFormat": {"bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"})
    add_fmt(r, r, {"backgroundColor": POIS_LIGHT}, 0, 8)
    add_fmt(r, r, {"backgroundColor": ML_LIGHT}, 8, 16)

    add_row([""]) 

    for day in sorted_days:
        p_sigs = extract_signals(day, "slots")
        m_sigs = extract_signals(day, "ml_slots")
        
        p_count = len(p_sigs) if len(p_sigs) >= MIN_SIGNALS else 0
        m_count = len(m_sigs) if len(m_sigs) >= MIN_SIGNALS else 0
        max_count = max(p_count, m_count)
        if max_count == 0: continue

        date_str = day["date"]
        p_q = sum(s["odds"] for s in p_sigs)/p_count if p_count else 1.5
        m_q = sum(s["odds"] for s in m_sigs)/m_count if m_count else 1.5
        p_q = max(p_q, 1.05)
        m_q = max(m_q, 1.05)

        # Per masaniello_puro: pre-calcola pvirt_norm una volta per lato per giornata.
        # Questo evita di ricalcolarlo per ogni riga e garantisce consistenza interna.
        pvirt_norm_p = pvirt_norm_m = None
        if strategy == "masaniello_puro":
            wr_pct = params.get("wr_pct", DEFAULTS["masaniello_puro"]["wr_pct"])
            if p_count >= MIN_SIGNALS:
                W_p = max(1, int(p_count * wr_pct / 100))
                pvirt_norm_p = _find_pvirt_normalized(W_p, p_count, p_q, 1.0 / p_q)
            if m_count >= MIN_SIGNALS:
                W_m = max(1, int(m_count * wr_pct / 100))
                pvirt_norm_m = _find_pvirt_normalized(W_m, m_count, m_q, 1.0 / m_q)

        r = add_row([f"{date_str} -- {p_count} Poisson", "","","","","","","", f"{date_str} -- {m_count} ML", "","","","","","",""])
        add_merge(r, 0, 8)
        add_merge(r, 8, 16)
        add_fmt(r, r, {"backgroundColor": POIS_BG, "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"}, 0, 8)
        add_fmt(r, r, {"backgroundColor": ML_BG, "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"}, 8, 16)

        r = add_row(["#", "Evento", "Mercato", "Quota", "Risultato", "Stake", "P&L", "Cassa", "#", "Evento", "Mercato", "Quota", "Risultato", "Stake", "P&L", "Cassa"])
        add_fmt(r, r, {"backgroundColor": POIS_HEADER, "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}, 0, 8)
        add_fmt(r, r, {"backgroundColor": ML_HEADER, "textFormat": {"bold": True, "fontSize": 9}, "horizontalAlignment": "CENTER"}, 8, 16)

        first_data = len(all_data)
        start_r = first_data + 1

        for i in range(max_count):
            row = [""] * COLS
            r_idx = start_r + i
            
            if i < p_count:
                s = p_sigs[i]
                row[0] = s.get("slot_id", "")
                row[1] = s.get("event_name", "")[:20]
                row[2] = s.get("market_label", "")
                row[3] = s.get("odds", "")
                row[4] = s.get("original_result", "")
                row[5], row[6], row[7] = get_live_formulas(strategy, r_idx, start_r, p_count, p_q, "P", pvirt_norm=pvirt_norm_p)

            if i < m_count:
                s = m_sigs[i]
                row[8] = s.get("slot_id", "")
                row[9] = s.get("event_name", "")[:20]
                row[10] = s.get("market_label", "")
                row[11] = s.get("odds", "")
                row[12] = s.get("original_result", "")
                row[13], row[14], row[15] = get_live_formulas(strategy, r_idx, start_r, m_count, m_q, "M", pvirt_norm=pvirt_norm_m)

            ri = add_row(row)

            if i < p_count:
                bg = PEND_BG if p_sigs[i]["is_pending"] else (WIN_BG if p_sigs[i]["won"] else LOSS_BG)
                add_fmt(ri, ri, {"backgroundColor": bg}, 0, 8)
            if i < m_count:
                bg = ML_LIGHT if m_sigs[i]["is_pending"] else (WIN_BG if m_sigs[i]["won"] else LOSS_BG)
                add_fmt(ri, ri, {"backgroundColor": bg}, 8, 16)

        last_r = first_data + max_count
        
        def day_tot_form(pf, col_stk, col_pnl, col_res, col_cas, cnt):
            if cnt == 0: return ["", "TOTALE", "--", "", "", "--", "--", ""]
            stk_sum = f'SUMIF({col_stk}{start_r}:{col_stk}{last_r}; "<>--")'
            pnl_sum = f'SUMIF({col_pnl}{start_r}:{col_pnl}{last_r}; "<>--")'
            won_cnt = f'COUNTIFS({col_res}{start_r}:{col_res}{last_r}; "VINTO*"; {col_stk}{start_r}:{col_stk}{last_r}; "<>--")'
            played = f'COUNTIF({col_stk}{start_r}:{col_stk}{last_r}; "<>--")'
            wr = f'=IF({played}=0; "--"; ROUND({won_cnt}/{played}*100; 1) & "%")'
            cas_end = f'={col_cas}{last_r}'
            return ["", "TOTALE", wr, "", "", f'={stk_sum}', f'={pnl_sum}', cas_end]

        r = add_row(day_tot_form("P", "F", "G", "E", "H", p_count) + day_tot_form("M", "N", "O", "M", "P", m_count))
        add_fmt(r, r, {"backgroundColor": POIS_HEADER, "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"}, 0, 8)
        add_fmt(r, r, {"backgroundColor": ML_HEADER, "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"}, 8, 16)

        add_row([""]) 

    end_row = len(all_data)
    # Margine dinamico: il foglio deve coprire almeno tutti i dati + buffer
    max_rows = max(end_row + 200, ws.row_count)
    
    # Ridimensiona il foglio se necessario
    if ws.row_count < end_row + 10:
        _sheets_retry(ws.resize, rows=max_rows, cols=COLS)
        time_module.sleep(1)
    
    if all_data:
        # CRUCIAL FIX: Translate all strings starting with "=" to formulaValue natively, skipping USER_ENTERED bugs
        requests = []
        rows = []
        for row in all_data:
            cell_vals = []
            for val in row:
                if isinstance(val, str) and val.startswith("="):
                    cell_vals.append({"userEnteredValue": {"formulaValue": val}})
                elif isinstance(val, (int, float)):
                    cell_vals.append({"userEnteredValue": {"numberValue": float(val)}})
                else:
                    cell_vals.append({"userEnteredValue": {"stringValue": str(val)}})
            rows.append({"values": cell_vals})

        update_cells_req = {
            "updateCells": {
                "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": COLS},
                "rows": rows,
                "fields": "userEnteredValue"
            }
        }
        fmt_reqs.insert(0, update_cells_req)

    if end_row < max_rows:
        _sheets_retry(ws.batch_clear, [f"A{end_row + 1}:P{max_rows}"])
        fmt_reqs.append({"unmergeCells": {"range": {"sheetId": ws.id, "startRowIndex": end_row, "endRowIndex": max_rows, "startColumnIndex": 0, "endColumnIndex": COLS}}})
        fmt_reqs.append({"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": end_row, "endRowIndex": max_rows, "startColumnIndex": 0, "endColumnIndex": COLS},
            "cell": {"userEnteredFormat": {"backgroundColor": WHITE, "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": False, "fontSize": 10}}},
            "fields": "userEnteredFormat"}})

    if fmt_reqs:
        for i in range(0, len(fmt_reqs), 100):
            _sheets_retry(sh.batch_update, {"requests": fmt_reqs[i:i + 100]})
            time_module.sleep(1)

    logger.info(f"Foglio '{sheet_name}' completato (FORMULE LIVE TRADOTTE).")

def main():
    logger.info("=" * 55)
    logger.info("  AGGIORNA FOGLI MONEY MANAGEMENT (LIVE FORMULAS)")
    logger.info("=" * 55)
    history = load_history()
    if not history: return
    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
    sh = gc.open_by_key(config.SPREADSHEET_ID)

    for sheet_name, strategy in [
        ("MM Masaniello", "masaniello"),
        ("MM Masaniello SL", "masaniello_sl"),
        ("MM Flat Stake", "flat"),
        ("MM Masaniello Puro", "masaniello_puro"),
    ]:
        try:
            build_sheet(sh, sheet_name, strategy, history)
            time_module.sleep(3)
        except Exception as e:
            logger.error(f"Errore nel foglio '{sheet_name}': {e}", exc_info=True)

if __name__ == "__main__":
    main()
