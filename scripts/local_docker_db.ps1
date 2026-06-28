param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "status", "backup", "migrate", "init", "reset", "help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackupRoot = if ($env:BACKUP_ROOT) { $env:BACKUP_ROOT } else { Join-Path $ProjectRoot "backups" }

$MysqlContainer = if ($env:MYSQL_CONTAINER) { $env:MYSQL_CONTAINER } else { "ir_mysql" }
$MongoContainer = if ($env:MONGO_CONTAINER) { $env:MONGO_CONTAINER } else { "ir_mongodb" }

$MysqlHost = if ($env:MYSQL_HOST) { $env:MYSQL_HOST } else { "127.0.0.1" }
$MysqlPort = if ($env:MYSQL_PORT) { $env:MYSQL_PORT } else { "3307" }
$MysqlRootPassword = if ($env:MYSQL_ROOT_PASSWORD) { $env:MYSQL_ROOT_PASSWORD } else { "local-dev-root-password" }
$MysqlUser = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "ir_user" }
$MysqlPassword = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "local-dev-password" }
$MysqlDatabase = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "immune_repertoire" }

$MongoUsername = if ($env:MONGO_USERNAME) { $env:MONGO_USERNAME } else { "admin" }
$MongoPassword = if ($env:MONGO_PASSWORD) { $env:MONGO_PASSWORD } else { "local-dev-mongo-password" }
$MongoDbName = if ($env:MONGO_DB_NAME) { $env:MONGO_DB_NAME } else { "immune_repertoire" }

$AdminUsername = if ($env:ADMIN_USERNAME) { $env:ADMIN_USERNAME } else { "admin" }
$AdminEmail = if ($env:ADMIN_EMAIL) { $env:ADMIN_EMAIL } else { "admin@example.com" }
$AdminPassword = if ($env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD } else { "change-me" }

function Show-Help {
    @"
Usage:
  powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 <command>

Commands:
  up       Start local MySQL and MongoDB containers.
  down     Stop containers, keep existing volumes/data.
  status   Show container status and local connection info.
  backup   Back up local MySQL and MongoDB into backups\local_YYYY-mm-dd_HHMMSS.
  migrate  Run auth/user-scope migration against local Docker MySQL and add Mongo indexes.
  init     Start DB, wait for MySQL, run migration.
  reset    DANGEROUS: stop containers and delete local Docker volumes.

Examples:
  powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 up
  powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 migrate
  powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 init
"@
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    Push-Location $ProjectRoot
    try {
        & docker compose @Args
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose $($Args -join ' ') failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Start-Db {
    Require-Command docker
    Write-Host "Starting local Docker databases..."
    Invoke-Compose up -d mysql mongodb
}

function Stop-Db {
    Require-Command docker
    Write-Host "Stopping local Docker databases; volumes are kept."
    Invoke-Compose down
}

function Show-Status {
    Require-Command docker
    Invoke-Compose ps
    Write-Host ""
    Write-Host "Local database connection:"
    Write-Host "  MySQL:   $MysqlUser@$MysqlHost`:$MysqlPort/$MysqlDatabase"
    Write-Host "  MongoDB: $MongoUsername@127.0.0.1:27018/$MongoDbName"
    Write-Host ""
    Write-Host "Local Flask startup:"
    Write-Host "  python flask_app\app.py"
}

function Wait-ForMysql {
    Write-Host "Waiting for local MySQL $MysqlHost`:$MysqlPort ..."
    for ($i = 0; $i -lt 60; $i++) {
        $env:MYSQL_HOST = $MysqlHost
        $env:MYSQL_PORT = $MysqlPort
        $env:MYSQL_USER = $MysqlUser
        $env:MYSQL_PASSWORD = $MysqlPassword
        $env:MYSQL_DATABASE = $MysqlDatabase
        $probe = @'
import os
import pymysql
conn = pymysql.connect(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DATABASE"],
    connect_timeout=3,
)
conn.close()
'@
        $probe | python - 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "MySQL is ready."
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "MySQL did not become reachable. Check Docker Desktop and local port mapping."
}

function Check-PythonMysql {
    "import pymysql" | python - 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python package pymysql is missing. Run: cd flask_app; pip install -r requirements.txt"
    }
}

function Backup-Db {
    Require-Command docker
    $stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $backupDir = Join-Path $BackupRoot "local_$stamp"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

    Write-Host "Backing up MySQL to $backupDir ..."
    $mysqlBackup = Join-Path $backupDir "$MysqlDatabase.sql"
    & docker exec $MysqlContainer mysqldump -uroot "-p$MysqlRootPassword" $MysqlDatabase | Out-File -FilePath $mysqlBackup -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL backup failed."
    }

    Write-Host "Backing up MongoDB to $backupDir ..."
    & docker exec $MongoContainer rm -rf /tmp/local_mongo_backup
    & docker exec $MongoContainer mongodump --username $MongoUsername --password $MongoPassword --authenticationDatabase admin --db $MongoDbName --out /tmp/local_mongo_backup
    if ($LASTEXITCODE -ne 0) {
        throw "MongoDB backup failed."
    }
    & docker cp "${MongoContainer}:/tmp/local_mongo_backup" (Join-Path $backupDir "mongo")
    if ($LASTEXITCODE -ne 0) {
        throw "MongoDB docker cp failed."
    }
    & docker exec $MongoContainer rm -rf /tmp/local_mongo_backup

    Write-Host "Backup complete: $backupDir"
}

function Create-MongoIndexes {
    Require-Command docker
    Write-Host "Creating local MongoDB user-scope indexes..."
    $js = @'
db.rawdata.createIndex({ user_id: 1 });
db.rawdata.createIndex({ user_id: 1, project_id: 1, asset_type: 1 });
db.results.createIndex({ user_id: 1 });
db.results.createIndex({ user_id: 1, project_id: 1, analysis_type: 1 });
db.analysis_cache.createIndex({ user_id: 1 });
db.analysis_cache.createIndex({ user_id: 1, project_id: 1 });
'@
    & docker exec $MongoContainer mongosh -u $MongoUsername -p $MongoPassword --authenticationDatabase admin $MongoDbName --eval $js
    if ($LASTEXITCODE -ne 0) {
        throw "Mongo index creation failed."
    }
}

function Migrate-Db {
    Check-PythonMysql
    Wait-ForMysql
    Write-Host "Running local MySQL auth/user-scope migration..."

    Push-Location (Join-Path $ProjectRoot "flask_app")
    try {
        $env:FLASK_CONFIG = "development"
        $env:MYSQL_HOST = $MysqlHost
        $env:MYSQL_PORT = $MysqlPort
        $env:MYSQL_USER = $MysqlUser
        $env:MYSQL_PASSWORD = $MysqlPassword
        $env:MYSQL_DATABASE = $MysqlDatabase
        $env:ADMIN_PASSWORD = $AdminPassword

        python migrations/add_auth_user_scope.py --dry-run
        if ($LASTEXITCODE -ne 0) { throw "Migration dry-run failed." }
        python migrations/add_auth_user_scope.py --apply --admin-username $AdminUsername --admin-email $AdminEmail
        if ($LASTEXITCODE -ne 0) { throw "Migration apply failed." }
        python migrations/add_auth_user_scope.py --verify
        if ($LASTEXITCODE -ne 0) { throw "Migration verify failed." }
        python migrations/add_analysis_jobs.py --dry-run
        if ($LASTEXITCODE -ne 0) { throw "Analysis job migration dry-run failed." }
        python migrations/add_analysis_jobs.py --apply
        if ($LASTEXITCODE -ne 0) { throw "Analysis job migration apply failed." }
        python migrations/add_analysis_jobs.py --verify
        if ($LASTEXITCODE -ne 0) { throw "Analysis job migration verify failed." }
    }
    finally {
        Pop-Location
    }

    Create-MongoIndexes
    Write-Host ""
    Write-Host "Local migration complete."
    Write-Host "Default local admin:"
    Write-Host "  username: $AdminUsername"
    Write-Host "  email:    $AdminEmail"
    Write-Host "  password: $AdminPassword"
}

function Reset-Db {
    Require-Command docker
    Write-Host "DANGER: this will delete local Docker database volumes for this compose project."
    Write-Host "This is intended only for local rebuilds."
    $answer = Read-Host "Type RESET to continue"
    if ($answer -ne "RESET") {
        Write-Host "Reset cancelled."
        exit 1
    }
    Invoke-Compose down -v
    Write-Host "Local database volumes removed."
}

switch ($Command) {
    "up" { Start-Db }
    "down" { Stop-Db }
    "status" { Show-Status }
    "backup" { Backup-Db }
    "migrate" { Migrate-Db }
    "init" { Start-Db; Migrate-Db }
    "reset" { Reset-Db }
    "help" { Show-Help }
}
