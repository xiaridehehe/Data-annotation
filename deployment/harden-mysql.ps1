$ErrorActionPreference = 'Stop'
$ini = 'C:\AnnotationApp\my.ini'
$content = Get-Content $ini
if ($content -notcontains 'mysqlx-bind-address=127.0.0.1') {
    $updated = foreach ($line in $content) {
        $line
        if ($line -eq 'bind-address=127.0.0.1') { 'mysqlx-bind-address=127.0.0.1' }
    }
    $updated | Set-Content -Encoding ascii $ini
}
Restart-Service AnnotationMySQL
Start-Sleep -Seconds 3
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 3306,33060 | Select-Object LocalAddress,LocalPort,State
