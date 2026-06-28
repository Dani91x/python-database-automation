# ============================================================================
#  Auto-avvio del Backtest Worker via Windows Task Scheduler.
#  Registra un task che parte AD OGNI LOGIN dell'utente e tiene attivo il worker
#  in background: cosi' i backtest lanciati dalla dashboard partono da soli,
#  senza dover ricordare di aprire un terminale.
#
#  USO:  click destro > "Esegui con PowerShell"   (NON serve amministratore)
#  Per rimuoverlo:  .\install_worker_autostart.ps1 -Uninstall
# ============================================================================
param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$TaskName = 'BetfairBacktestWorker'
$ProjectDir = $PSScriptRoot

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Task '$TaskName' rimosso. Il worker non parte piu' al login." -ForegroundColor Green
    } else {
        Write-Host "[i] Nessun task '$TaskName' da rimuovere." -ForegroundColor Yellow
    }
    return
}

# trova python
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "python non trovato nel PATH. Installa Python o aggiungilo al PATH." }

# Azione: lancia il modulo worker nella cartella del progetto.
$action = New-ScheduledTaskAction -Execute $python `
    -Argument '-m Betfair.stream.backtest.worker --log-level INFO' `
    -WorkingDirectory $ProjectDir

# Trigger: ad ogni logon dell'utente corrente.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Impostazioni: riavvio se cade, nessun timeout, gira in background.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3 `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Backtest Automatico worker (FlumineSimulation) - auto al login' `
    -Force | Out-Null

Write-Host "[OK] Task '$TaskName' registrato: il worker parte ad ogni login." -ForegroundColor Green
Write-Host "[i] Lo avvio anche ORA cosi' non devi rifare il login..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName
Write-Host "[OK] Worker avviato in background. I backtest dalla dashboard ora vengono processati." -ForegroundColor Green
