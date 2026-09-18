"""Test STRUTTURALE (AST) — sync_account_worker deve essere registrato SEMPRE nel
runner (OFF/PAPER/LIVE), fuori dal blocco ``if orders_enabled:``.

Perche' AST e non un test funzionale: ``setup_and_run`` fa login Betfair reale,
apre lo stream e gira in un ``while True`` — non e' unit-testabile senza
montare l'intero framework flumine con una sessione vera (fuori scope, vietato
da CLAUDE.md: nessuna chiamata Betfair nei test). La garanzia che ci serve e'
di CABLAGGIO: "la entry sync_account_worker sta FUORI dal ramo orders_enabled,
come heartbeat_worker" — questo si verifica sul codice sorgente, non a runtime.
La logica di sync_account_worker stessa (cadenza 20s, mode-indipendenza,
write-on-change, publish canale locale, mai sollevare) e' coperta a unita' in
``test_reconcile_worker.py`` con session/db/canale mockati.

18/09 (fix saldo sempre aggiornato): il bug che questo test previene e' quello
osservato oggi — reconcile_worker (e quindi il saldo) era registrato SOLO
dentro ``if orders_enabled:`` (mode != OFF), quindi con OFF il saldo non si
aggiornava mai per giorni anche con altri bot LIVE sullo stesso conto.
"""
from __future__ import annotations

import ast
import inspect

from Betfair.stream import runner


def _setup_and_run_source() -> str:
    return inspect.getsource(runner.setup_and_run)


def _find_call_sites(tree: ast.AST, function_name: str) -> "list[ast.Call]":
    """Tutte le chiamate ``add_worker(BackgroundWorker(..., function=<function_name>, ...))``."""
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_worker"):
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Call):
                continue
            for kw in arg.keywords:
                if kw.arg == "function" and isinstance(kw.value, ast.Name) and kw.value.id == function_name:
                    hits.append(node)
    return hits


def _is_inside_orders_enabled_if(tree: ast.FunctionDef, call_node: ast.Call) -> bool:
    """True se ``call_node`` e' annidato dentro un ``if orders_enabled:`` (o
    equivalente ``if orders_enabled`` come unica condizione) all'interno di
    ``tree``. Cammina l'albero e traccia i genitori: niente librerie esterne,
    ``ast`` non porta i puntatori al parent di default.
    """
    parent_of: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_of[id(child)] = parent

    node: ast.AST = call_node
    while True:
        parent = parent_of.get(id(node))
        if parent is None:
            return False
        if isinstance(parent, ast.If):
            test = parent.test
            if isinstance(test, ast.Name) and test.id == "orders_enabled":
                # il call_node deve stare nel ramo `body` (then), non `orelse`
                if _contained_in(parent.body, node):
                    return True
        node = parent


def _contained_in(body: "list[ast.stmt]", target: ast.AST) -> bool:
    for stmt in body:
        for sub in ast.walk(stmt):
            if sub is target:
                return True
    return False


def test_sync_account_worker_registered_outside_orders_enabled_block():
    """sync_account_worker: registrato FUORI da ``if orders_enabled:`` (come
    heartbeat_worker) — deve girare anche quando LIVE_ORDER_MODE=OFF."""
    src = _setup_and_run_source()
    tree = ast.parse(src)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)

    sync_calls = _find_call_sites(func_def, "sync_account_worker")
    assert len(sync_calls) == 1, "sync_account_worker deve avere ESATTAMENTE un add_worker"
    assert not _is_inside_orders_enabled_if(func_def, sync_calls[0]), (
        "sync_account_worker e' annidato dentro `if orders_enabled:` — il saldo "
        "NON si aggiornerebbe in OFF (regressione 18/09)."
    )

    # controllo di sanita' del test stesso (positivo E negativo su call reali
    # del file): reconcile_worker (ordini) DEVE invece stare dentro il ramo,
    # heartbeat_worker DEVE stare fuori come sync_account_worker.
    reconcile_calls = _find_call_sites(func_def, "reconcile_worker")
    assert len(reconcile_calls) == 1
    assert _is_inside_orders_enabled_if(func_def, reconcile_calls[0])

    heartbeat_calls = _find_call_sites(func_def, "heartbeat_worker")
    assert len(heartbeat_calls) == 1
    assert not _is_inside_orders_enabled_if(func_def, heartbeat_calls[0])


def test_sync_account_worker_imported_from_reconcile_worker_module():
    """Deve essere lo stesso oggetto funzione usato/testato in reconcile_worker.py
    (niente wrapper/duplicati che facciano una seconda chiamata Betfair)."""
    from Betfair.stream import reconcile_worker as rw

    assert runner.sync_account_worker is rw.sync_account_worker


def _find_plain_calls(tree: ast.AST, function_name: str) -> "list[ast.Call]":
    """Chiamate DIRETTE ``function_name(...)`` (non ``add_worker(...)``) —
    quelle del ciclo idle, che non passano da un BackgroundWorker."""
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function_name:
            hits.append(node)
    return hits


def test_run_account_sync_if_due_called_directly_from_idle_loop():
    """18/09 sera (reperto del coordinatore): sync_account_worker e' un
    BackgroundWorker, vive SOLO dentro framework.run(). Lo stato NORMALE del
    runner ad app aperta senza partite seguite e' il ciclo IDLE, dove
    ``framework`` non esiste ancora. ``run_account_sync_if_due`` deve essere
    chiamata DIRETTAMENTE (non tramite add_worker) in ENTRAMBI i punti di
    attesa del ciclo idle: `if not follows:` (nessun evento da streammare) e
    `if not market_ids:` (follow presenti ma nessun mercato sottoscrivibile).
    Senza queste due chiamate il saldo resta fermo proprio quando l'utente
    non sta seguendo live una partita — cioe' quasi sempre (causa reale dei
    3,7 giorni di vecchiaia osservati)."""
    src = _setup_and_run_source()
    tree = ast.parse(src)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)

    calls = _find_plain_calls(func_def, "run_account_sync_if_due")
    assert len(calls) == 2, (
        f"attese ESATTAMENTE 2 chiamate dirette a run_account_sync_if_due nel ciclo "
        f"idle (if not follows / if not market_ids), trovate {len(calls)}"
    )
    # nessuna delle due deve passare per un BackgroundWorker (add_worker): sono
    # chiamate SINCRONE dal thread principale del ciclo idle.
    worker_calls = _find_call_sites(func_def, "run_account_sync_if_due")
    assert worker_calls == [], (
        "run_account_sync_if_due non deve MAI essere passata come `function=` a "
        "un add_worker: e' gia' chiamata da sync_account_worker li' dentro."
    )
