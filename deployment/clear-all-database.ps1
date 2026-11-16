$ErrorActionPreference = 'Stop'

$mysqlHome = 'C:\MySQL84\bin'
$secretFile = 'C:\AnnotationApp\database-secrets.txt'
$backupDir = 'C:\AnnotationApp\database-backups'
$database = 'annotation_db'

$secrets = @{}
Get-Content -LiteralPath $secretFile | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { $secrets[$matches[1]] = $matches[2] }
}
$rootPassword = $secrets['MYSQL_ROOT_PASSWORD']
if (-not $rootPassword) { throw 'MYSQL_ROOT_PASSWORD is missing.' }

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $backupDir "$database-$stamp.sql"

& "$mysqlHome\mysqldump.exe" --host=127.0.0.1 --user=root "--password=$rootPassword" --single-transaction --routines --events $database --result-file=$backup
if ($LASTEXITCODE -ne 0) { throw "Database backup failed with exit code $LASTEXITCODE." }

$tables = & "$mysqlHome\mysql.exe" --batch --skip-column-names --host=127.0.0.1 --user=root "--password=$rootPassword" --execute="SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='$database' AND TABLE_TYPE='BASE TABLE';"
if ($LASTEXITCODE -ne 0) { throw "Could not list database tables (exit $LASTEXITCODE)." }

$statements = @('SET FOREIGN_KEY_CHECKS=0;')
foreach ($table in $tables) {
    if ($table) { $statements += "TRUNCATE TABLE ``$table``;" }
}
$statements += 'SET FOREIGN_KEY_CHECKS=1;'
$sqlFile = Join-Path $env:TEMP "clear-$database-$stamp.sql"
[System.IO.File]::WriteAllLines($sqlFile, $statements, [System.Text.UTF8Encoding]::new($false))
try {
    Get-Content -Raw -LiteralPath $sqlFile | & "$mysqlHome\mysql.exe" --host=127.0.0.1 --user=root "--password=$rootPassword" $database
    if ($LASTEXITCODE -ne 0) { throw "Database clear failed with exit code $LASTEXITCODE." }
} finally {
    Remove-Item -LiteralPath $sqlFile -Force -ErrorAction SilentlyContinue
}

$remaining = & "$mysqlHome\mysql.exe" --batch --skip-column-names --host=127.0.0.1 --user=root "--password=$rootPassword" --execute="SELECT COALESCE(SUM(TABLE_ROWS),0) FROM information_schema.TABLES WHERE TABLE_SCHEMA='$database' AND TABLE_TYPE='BASE TABLE';"
if ($LASTEXITCODE -ne 0) { throw "Verification failed with exit code $LASTEXITCODE." }

Write-Output "BACKUP=$backup"
Write-Output "TABLES=$($tables.Count)"
Write-Output "REMAINING_ROWS=$remaining"
