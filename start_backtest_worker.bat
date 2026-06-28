@echo off
REM ============================================================================
REM  Backtest Automatico - worker locale (FlumineSimulation).
REM  Doppio click per avviarlo e LASCIA APERTA questa finestra: consuma la coda
REM  live_backtest_requests (le richieste fatte dalla dashboard "Backtest
REM  Automatico"). Senza questo worker attivo le richieste restano "in coda".
REM ============================================================================
cd /d "%~dp0"
echo [backtest-worker] avvio... lascia aperta questa finestra.
echo [backtest-worker] Ctrl+C per fermare.
python -m Betfair.stream.backtest.worker --log-level INFO
echo.
echo [backtest-worker] terminato. Premi un tasto per chiudere.
pause >nul
