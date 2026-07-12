@echo off
REM Avvia il SERVIZIO OMEGA BOT — supervisore locale (Correct Score LAY).
REM Legge stato/parametri dalla web-app (sezione OMEGA), conta gli eventi del
REM giorno, calcola il target dinamico per match e piazza UN lay per partita in
REM finestra. Default: PAPER (soldi finti). LIVE solo con toggle esplicito da UI.
REM Fonte di verita': Betfair\omega\COSTITUZIONE_OMEGA.md
REM TIENI QUESTA FINESTRA APERTA mentre lavori. Ctrl+C per fermare.
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Avvio servizio OMEGA bot...
"%PY%" -m Betfair.omega.omega_service
echo.
pause
