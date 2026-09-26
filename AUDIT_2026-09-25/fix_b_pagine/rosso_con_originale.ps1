# RED con il codice di PRIMA: rimette per un attimo la versione HEAD di un file di
# produzione, lancia UN test (vitest o pytest), poi ripristina la versione nuova e
# verifica che sia byte-identica (hash SHA256 prima = dopo). Mai `git checkout`.
# Uso: powershell -File rosso_con_originale.ps1 <file_repo_relativo> <tipo:vitest|pytest> <test>
param([string]$File, [string]$Tipo, [string]$Test)
$ErrorActionPreference = 'Continue'
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$abs = Join-Path $repo $File
$bak = "$abs.fixb_bak"
$h0 = (Get-FileHash $abs -Algorithm SHA256).Hash
Copy-Item $abs $bak -Force
try {
    $orig = git -C $repo show "HEAD:$($File -replace '\\','/')"
    # git show restituisce righe: si riscrive con CRLF come nel checkout
    [System.IO.File]::WriteAllText($abs, (($orig -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding $false))
    if ($Tipo -eq 'vitest') {
        Push-Location (Join-Path $repo 'frontend')
        $out = npx vitest run $Test 2>&1
        Pop-Location
    } else {
        $env:SUPABASE_URL = 'http://127.0.0.1:9'; $env:SUPABASE_SERVICE_ROLE_KEY = 'x'; $env:SUPABASE_KEY = 'x'
        $out = & (Join-Path $repo '.venv\Scripts\python.exe') -m pytest $Test -q -p no:cacheprovider 2>&1
    }
    $out | Select-String -Pattern 'Tests |passed|failed|FAILED|×' | Select-Object -First 15 | ForEach-Object { $_.Line }
} finally {
    Copy-Item $bak $abs -Force
    Remove-Item $bak -Force
    $h1 = (Get-FileHash $abs -Algorithm SHA256).Hash
    "ripristino byte-identico: $($h0 -eq $h1)"
}
