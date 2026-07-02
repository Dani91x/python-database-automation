@echo off
REM Avvia il SERVIZIO SCALPER BOT (pre-match) — supervisore locale.
REM Legge le attivazioni dalla web-app (Segui Live -> pannello Scalper),
REM arma il bot per evento e scrive stato/statistiche/log nel database.
REM TIENI QUESTA FINESTRA APERTA mentre lavori. Ctrl+C per fermare.
REM Kill-switch di emergenza: crea un file STOP_SCALPER in questa cartella.
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Avvio servizio scalper bot...
"%PY%" -m Betfair.stream.scalper.scalper_service
echo.
pause
