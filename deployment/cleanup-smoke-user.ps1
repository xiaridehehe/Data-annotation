param([Parameter(Mandatory = $true)][string]$Username)
$ErrorActionPreference = 'Stop'
$secrets = @{}
Get-Content 'C:\AnnotationApp\database-secrets.txt' | ForEach-Object {
    $pair = $_ -split '=', 2
    if ($pair.Length -eq 2) { $secrets[$pair[0]] = $pair[1] }
}
if ($Username -notmatch '^[A-Za-z0-9]+$') { throw 'Invalid smoke-test username' }
$sql = "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE username='$Username'); DELETE FROM users WHERE username='$Username'; SELECT COUNT(*) AS remaining FROM users WHERE username='$Username';"
& 'C:\MySQL84\bin\mysql.exe' --user=annotation_app "--password=$($secrets['MYSQL_APP_PASSWORD'])" annotation_db "--execute=$sql"
if ($LASTEXITCODE -ne 0) { throw 'Smoke-test account cleanup failed' }
