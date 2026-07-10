@echo off
REM Avvia il SERVER locale quote + ordini Betfair su http://127.0.0.1:8787
REM Serve i pulsanti "Aggiorna quote" e "Invia Giocate" della web-app.
REM TIENI QUESTA FINESTRA APERTA mentre lavori. Ctrl+C per fermare.
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Avvio server quote/ordini su http://127.0.0.1:8787 ...
"%PY%" start_order_server.py
echo.
echo [server terminato]
pause
