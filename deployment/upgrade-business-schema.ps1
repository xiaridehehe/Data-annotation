$ErrorActionPreference = 'Stop'

$root = 'C:\AnnotationApp'
$app = Join-Path $root 'current'
$mysql = 'C:\MySQL84\bin'
$secrets = @{}
Get-Content -LiteralPath (Join-Path $root 'database-secrets.txt') | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { $secrets[$matches[1]] = $matches[2] }
}
if (-not $secrets['MYSQL_ROOT_PASSWORD'] -or -not $secrets['MYSQL_APP_PASSWORD']) {
    throw 'Database credentials are missing.'
}

$backupDir = Join-Path $root 'database-backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backup = Join-Path $backupDir ("annotation_db-before-business-{0}.sql" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
& (Join-Path $mysql 'mysqldump.exe') --host=127.0.0.1 --user=root "--password=$($secrets['MYSQL_ROOT_PASSWORD'])" --single-transaction --routines --events annotation_db --result-file=$backup
if ($LASTEXITCODE -ne 0) { throw "Database backup failed with exit code $LASTEXITCODE." }

$env:ANNOTATION_DATABASE_URL = "mysql+pymysql://annotation_app:$($secrets['MYSQL_APP_PASSWORD'])@127.0.0.1:3306/annotation_db"
Push-Location $app
try {
    & (Join-Path $app '.venv\Scripts\python.exe') -c "from backend.database import create_database_engine; create_database_engine().dispose()"
    if ($LASTEXITCODE -ne 0) { throw "Schema upgrade failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
    Remove-Item Env:\ANNOTATION_DATABASE_URL -ErrorAction SilentlyContinue
}

$verify = @"
SELECT CONCAT('users.role=',COUNT(*)) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='annotation_db' AND TABLE_NAME='users' AND COLUMN_NAME='role';
SELECT CONCAT('submissions=',COUNT(*)) FROM information_schema.TABLES WHERE TABLE_SCHEMA='annotation_db' AND TABLE_NAME='submissions';
SELECT CONCAT('submission_review_history=',COUNT(*)) FROM information_schema.TABLES WHERE TABLE_SCHEMA='annotation_db' AND TABLE_NAME='submission_review_history';
SELECT CONCAT('users.rows=',COUNT(*)) FROM annotation_db.users;
SELECT CONCAT('submissions.rows=',COUNT(*)) FROM annotation_db.submissions;
"@
$result = $verify | & (Join-Path $mysql 'mysql.exe') --batch --skip-column-names --host=127.0.0.1 --user=root "--password=$($secrets['MYSQL_ROOT_PASSWORD'])"
if ($LASTEXITCODE -ne 0) { throw "Schema verification failed with exit code $LASTEXITCODE." }
Write-Output "BACKUP=$backup"
$result | Write-Output
