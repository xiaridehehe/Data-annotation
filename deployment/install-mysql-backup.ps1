$ErrorActionPreference = 'Stop'

$root = 'C:\AnnotationApp'
$backupRoot = Join-Path $root 'mysql-backups'
$runner = Join-Path $root 'backup-mysql.ps1'
$secretFile = Join-Path $root 'database-secrets.txt'

$dumpCandidates = @(
    'C:\MySQL84\bin\mysqldump.exe',
    'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe',
    'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe',
    'C:\AnnotationApp\mysql\bin\mysqldump.exe'
)
$dumpExe = $dumpCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $dumpExe) {
    $dumpExe = Get-ChildItem -Path 'C:\Program Files\MySQL','C:\AnnotationApp' -Filter mysqldump.exe -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $dumpExe) { throw 'mysqldump.exe was not found' }
if (-not (Test-Path -LiteralPath $secretFile)) { throw 'database-secrets.txt was not found' }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
icacls $backupRoot /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null

$template = @'
$ErrorActionPreference = 'Stop'
$backupRoot = '__BACKUP_ROOT__'
$secretFile = '__SECRET_FILE__'
$dumpExe = '__DUMP_EXE__'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$sqlFile = Join-Path $backupRoot ("annotation_db-$stamp.sql")
$zipFile = Join-Path $backupRoot ("annotation_db-$stamp.zip")
$errorFile = Join-Path $backupRoot ("annotation_db-$stamp.error.log")

$secrets = @{}
Get-Content -LiteralPath $secretFile | ForEach-Object {
    $pair = $_ -split '=', 2
    if ($pair.Length -eq 2) { $secrets[$pair[0]] = $pair[1] }
}
$password = $secrets['MYSQL_APP_PASSWORD']
if (-not $password) { throw 'MYSQL_APP_PASSWORD is missing' }

$env:MYSQL_PWD = $password
try {
    $arguments = @(
        '--host=127.0.0.1', '--port=3306', '--user=annotation_app',
        '--single-transaction', '--quick', '--no-tablespaces', '--triggers',
        '--hex-blob', '--default-character-set=utf8mb4',
        "--result-file=$sqlFile", 'annotation_db'
    )
    $process = Start-Process -FilePath $dumpExe -ArgumentList $arguments -Wait -PassThru -NoNewWindow -RedirectStandardError $errorFile
    if ($process.ExitCode -ne 0) {
        Remove-Item -LiteralPath $sqlFile -Force -ErrorAction SilentlyContinue
        throw "mysqldump failed with exit code $($process.ExitCode): $(Get-Content -LiteralPath $errorFile -Raw)"
    }
} finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $sqlFile) -or (Get-Item -LiteralPath $sqlFile).Length -le 0) {
    throw 'Backup SQL file is empty or missing'
}
Compress-Archive -LiteralPath $sqlFile -DestinationPath $zipFile -CompressionLevel Optimal -Force
if (-not (Test-Path -LiteralPath $zipFile) -or (Get-Item -LiteralPath $zipFile).Length -le 0) {
    throw 'Compressed backup is empty or missing'
}
Remove-Item -LiteralPath $sqlFile -Force
Remove-Item -LiteralPath $errorFile -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $backupRoot -Filter 'annotation_db-*.zip' -File |
    Where-Object LastWriteTime -lt (Get-Date).AddDays(-14) |
    Remove-Item -Force
Write-Output "BACKUP_OK=$zipFile"
'@

$content = $template.Replace('__BACKUP_ROOT__', $backupRoot.Replace("'", "''"))
$content = $content.Replace('__SECRET_FILE__', $secretFile.Replace("'", "''"))
$content = $content.Replace('__DUMP_EXE__', $dumpExe.Replace("'", "''"))
$content | Set-Content -LiteralPath $runner -Encoding UTF8
icacls $runner /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null

Unregister-ScheduledTask -TaskName 'AnnotationMySQLBackup' -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -Daily -At '02:00'
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'AnnotationMySQLBackup' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Daily annotation_db backup; retain 14 days' | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner
if ($LASTEXITCODE -ne 0) { throw 'Initial backup validation failed' }
Get-ScheduledTask -TaskName 'AnnotationMySQLBackup' | Select-Object TaskName,State
Get-ScheduledTaskInfo -TaskName 'AnnotationMySQLBackup' | Select-Object LastRunTime,LastTaskResult,NextRunTime
Get-ChildItem -LiteralPath $backupRoot -Filter 'annotation_db-*.zip' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1 FullName,Length,LastWriteTime
