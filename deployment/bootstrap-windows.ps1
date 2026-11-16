$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$root = 'C:\AnnotationApp'
$downloads = Join-Path $root 'downloads'
New-Item -ItemType Directory -Force -Path $root, $downloads | Out-Null

function Download-IfMissing([string]$Url, [string]$Path) {
    if (-not (Test-Path $Path) -or (Get-Item $Path).Length -eq 0) {
        Remove-Item -Force $Path -ErrorAction SilentlyContinue
        & curl.exe --fail --location --retry 5 --retry-delay 3 --output $Path $Url
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Path) -or (Get-Item $Path).Length -eq 0) {
            throw "Download failed: $Url"
        }
    }
}

$vcRedist = Join-Path $downloads 'vc_redist.x64.exe'
Download-IfMissing 'https://aka.ms/vs/17/release/vc_redist.x64.exe' $vcRedist
Start-Process -FilePath $vcRedist -ArgumentList '/install /quiet /norestart' -Wait

$pythonInstaller = Join-Path $downloads 'python-3.12.10-amd64.exe'
Download-IfMissing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' $pythonInstaller
if (-not (Test-Path 'C:\Python312\python.exe')) {
    Start-Process -FilePath $pythonInstaller -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 TargetDir=C:\Python312' -Wait
}

$nodeHome = 'C:\Node22'
$nodeZip = Join-Path $downloads 'node-v22.23.0-win-x64.zip'
Download-IfMissing 'https://nodejs.org/dist/v22.23.0/node-v22.23.0-win-x64.zip' $nodeZip
if (-not (Test-Path (Join-Path $nodeHome 'node.exe'))) {
    $nodeExtract = Join-Path $downloads 'node-extract'
    Remove-Item -Recurse -Force $nodeExtract -ErrorAction SilentlyContinue
    Expand-Archive -Path $nodeZip -DestinationPath $nodeExtract
    Move-Item (Join-Path $nodeExtract 'node-v22.23.0-win-x64') $nodeHome
    Remove-Item -Recurse -Force $nodeExtract
}

$mysqlHome = 'C:\MySQL84'
$mysqlZip = Join-Path $downloads 'mysql-8.4.13-winx64.zip'
Download-IfMissing 'https://dev.mysql.com/get/Downloads/MySQL-8.4/mysql-8.4.13-winx64.zip' $mysqlZip
if (-not (Test-Path (Join-Path $mysqlHome 'bin\mysqld.exe'))) {
    $extract = Join-Path $downloads 'mysql-extract'
    Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
    Expand-Archive -Path $mysqlZip -DestinationPath $extract
    Move-Item (Join-Path $extract 'mysql-8.4.13-winx64') $mysqlHome
    Remove-Item -Recurse -Force $extract
}

$mysqlData = Join-Path $root 'mysql-data'
$mysqlIni = Join-Path $root 'my.ini'
@"
[mysqld]
basedir=C:/MySQL84
datadir=C:/AnnotationApp/mysql-data
port=3306
bind-address=127.0.0.1
mysqlx-bind-address=127.0.0.1
character-set-server=utf8mb4
collation-server=utf8mb4_bin
secure-file-priv=NULL
[client]
port=3306
default-character-set=utf8mb4
"@ | Set-Content -Encoding ascii $mysqlIni

if (-not (Test-Path $mysqlData)) {
    & (Join-Path $mysqlHome 'bin\mysqld.exe') --defaults-file=$mysqlIni --initialize-insecure --console
}
if (-not (Get-Service AnnotationMySQL -ErrorAction SilentlyContinue)) {
    & (Join-Path $mysqlHome 'bin\mysqld.exe') --install AnnotationMySQL --defaults-file=$mysqlIni
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install AnnotationMySQL service' }
}
Set-Service AnnotationMySQL -StartupType Automatic
Start-Service AnnotationMySQL

$secretFile = Join-Path $root 'database-secrets.txt'
if (-not (Test-Path $secretFile)) {
    $rootPassword = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $appPassword = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $sqlFile = Join-Path $root 'initialize.sql'
    @"
ALTER USER 'root'@'localhost' IDENTIFIED BY '$rootPassword';
CREATE DATABASE IF NOT EXISTS annotation_db CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER IF NOT EXISTS 'annotation_app'@'localhost' IDENTIFIED BY '$appPassword';
ALTER USER 'annotation_app'@'localhost' IDENTIFIED BY '$appPassword';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON annotation_db.* TO 'annotation_app'@'localhost';
FLUSH PRIVILEGES;
"@ | Set-Content -Encoding ascii $sqlFile
    Get-Content $sqlFile | & (Join-Path $mysqlHome 'bin\mysql.exe') -u root
    Remove-Item -Force $sqlFile
    @"
MYSQL_ROOT_PASSWORD=$rootPassword
MYSQL_APP_PASSWORD=$appPassword
"@ | Set-Content -Encoding ascii $secretFile
    icacls $secretFile /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null
}

$caddyZip = Join-Path $downloads 'caddy_2.11.9_windows_amd64.zip'
Download-IfMissing 'https://github.com/caddyserver/caddy/releases/download/v2.11.9/caddy_2.11.9_windows_amd64.zip' $caddyZip
$caddyDir = Join-Path $root 'caddy'
if (-not (Test-Path (Join-Path $caddyDir 'caddy.exe'))) {
    New-Item -ItemType Directory -Force -Path $caddyDir | Out-Null
    Expand-Archive -Path $caddyZip -DestinationPath $caddyDir -Force
}

New-NetFirewallRule -DisplayName 'Annotation HTTP' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -ErrorAction SilentlyContinue | Out-Null

Write-Output 'BOOTSTRAP_OK'
& 'C:\Python312\python.exe' --version
& (Join-Path $nodeHome 'node.exe') --version
& (Join-Path $mysqlHome 'bin\mysql.exe') --version
& (Join-Path $caddyDir 'caddy.exe') version
