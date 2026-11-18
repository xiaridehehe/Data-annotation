$ErrorActionPreference = 'Stop'
$root = 'C:\AnnotationApp'
$app = Join-Path $root 'current'
$archive = Join-Path $root 'project.tar.gz'

if (Test-Path $app) {
    $backup = Join-Path $root ('previous-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Move-Item $app $backup
}
New-Item -ItemType Directory -Force -Path $app | Out-Null
tar.exe -xzf $archive -C $app

& 'C:\Python312\python.exe' -m venv (Join-Path $app '.venv')
& (Join-Path $app '.venv\Scripts\python.exe') -m pip install --upgrade pip
& (Join-Path $app '.venv\Scripts\python.exe') -m pip install -r (Join-Path $app 'backend\requirements.txt')

$env:Path = 'C:\Node22;' + $env:Path
& 'C:\Node22\npm.cmd' --prefix (Join-Path $app 'frontend') ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
& (Join-Path $app '.venv\Scripts\python.exe') (Join-Path $app 'verify.py')
if ($LASTEXITCODE -ne 0) { throw 'Project verification failed; services were not started' }

$secrets = @{}
Get-Content (Join-Path $root 'database-secrets.txt') | ForEach-Object {
    $pair = $_ -split '=', 2
    if ($pair.Length -eq 2) { $secrets[$pair[0]] = $pair[1] }
}
$appPassword = $secrets['MYSQL_APP_PASSWORD']
$backendCmd = Join-Path $root 'run-backend.cmd'
@"
@echo off
set ANNOTATION_DATABASE_URL=mysql+pymysql://annotation_app:$appPassword@127.0.0.1:3306/annotation_db
set ANNOTATION_ALLOWED_ORIGINS=https://annotation.com.cn
set ANNOTATION_COOKIE_SECURE=1
cd /d C:\AnnotationApp\current
C:\AnnotationApp\current\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 2
"@ | Set-Content -Encoding ascii $backendCmd
icacls $backendCmd /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null

$caddyFile = Join-Path $root 'Caddyfile'
@"
annotation.com.cn {
    encode zstd gzip
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        root * C:\AnnotationApp\current\frontend\dist
        try_files {path} /index.html
        file_server
    }
}

www.annotation.com.cn {
    redir https://annotation.com.cn{uri} permanent
}
"@ | Set-Content -Encoding ascii $caddyFile

function Register-RestartingTask([string]$Name, [string]$Executable, [string]$Arguments, [string]$WorkingDirectory) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $WorkingDirectory
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Start-ScheduledTask -TaskName $Name
}

Register-RestartingTask 'AnnotationBackend' 'C:\Windows\System32\cmd.exe' '/c C:\AnnotationApp\run-backend.cmd' $app
Register-RestartingTask 'AnnotationCaddy' 'C:\AnnotationApp\caddy\caddy.exe' 'run --config C:\AnnotationApp\Caddyfile --adapter caddyfile' (Join-Path $root 'caddy')

Start-Sleep -Seconds 8
$api = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/docs' -TimeoutSec 10
$site = Invoke-WebRequest -UseBasicParsing -Uri 'https://annotation.com.cn/' -TimeoutSec 30
Write-Output ('API_STATUS=' + $api.StatusCode)
Write-Output ('SITE_STATUS=' + $site.StatusCode)
Get-ScheduledTask -TaskName AnnotationBackend,AnnotationCaddy | Select-Object TaskName,State
Get-Service AnnotationMySQL | Select-Object Name,Status,StartType
