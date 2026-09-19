param([string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path)
$ErrorActionPreference = 'Stop'
$prefix = 'immune-restore-test-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$createdVolumes = @()
$createdContainers = @()
$volumeNames = @('app_data', 'app_tmp', 'mysql_data', 'mongo_data', 'redis_data')
function Docker([string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    $result = & rtk proxy docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $result" }
    return (($result | Where-Object { $_.ToString() -notmatch '^\[rtk\]' }) -join "`n")
}
function AwaitDatabase([string]$Name, [string[]]$Command) {
    $ErrorActionPreference = 'Continue'
    $deadline = [DateTime]::UtcNow.AddSeconds(150)
    do {
        $null = & rtk proxy docker exec $Name @Command 2>&1
        if ($LASTEXITCODE -eq 0) { return }
        [Threading.Thread]::Sleep(1000)
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Database did not become ready: $Name"
}
function RunHelper([string]$Side, [string[]]$Command) {
    $arguments = @('run', '--rm', '--network', 'none', '--user', '0:0', '--mount', "type=bind,src=$Repository/docker/operations,dst=/operations,readonly", '--mount', "type=volume,src=$prefix-state,dst=/state")
    foreach ($volume in $volumeNames) {
        $mount = "type=volume,src=$prefix-$Side-$volume,dst=/volumes/$volume"
        if ($Side -eq 'source' -and $Command[0] -eq '/operations/cold_backup.py') { $mount += ',readonly' }
        $arguments += @('--mount', $mount)
    }
    $arguments += @('immune-platform-api:full', 'python') + $Command
    return Docker $arguments
}
try {
    foreach ($side in @('source', 'target')) {
        foreach ($volume in $volumeNames) {
            $name = "$prefix-$side-$volume"
            $null = Docker @('volume', 'create', $name)
            $createdVolumes += $name
        }
    }
    $null = Docker @('volume', 'create', "$prefix-state")
    $createdVolumes += "$prefix-state"
    foreach ($side in @('source', 'target')) {
        foreach ($database in @('mysql', 'mongo', 'redis')) {
            $name = "$prefix-$side-$database"
            $image = @{mysql='mysql:8.0';mongo='mongo:7.0';redis='redis:7-alpine'}[$database]
            $volume = @{mysql='mysql_data';mongo='mongo_data';redis='redis_data'}[$database]
            $path = @{mysql='/var/lib/mysql';mongo='/data/db';redis='/data'}[$database]
            $arguments = @('run', '-d', '--name', $name, '--network', 'none', '--mount', "type=volume,src=$prefix-$side-$volume,dst=$path")
            if ($database -eq 'mysql') { $arguments += @('-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes') }
            $arguments += $image
            if ($database -eq 'redis') { $arguments += @('redis-server', '--appendonly', 'yes') }
            $createdContainers += $name
            $null = Docker $arguments
            $ready = switch ($database) {
                mysql { @('mysql','-h','127.0.0.1','-uroot','-e','SELECT 1') }
                mongo { @('mongosh','--quiet','--eval','db.adminCommand({ping:1})') }
                redis { @('redis-cli','ping') }
            }
            AwaitDatabase $name $ready
            if ($side -eq 'source') {
                switch ($database) {
                    mysql { $null = Docker @('exec',$name,'mysql','-uroot','-e',"CREATE DATABASE restore_check; CREATE TABLE restore_check.samples (id varchar(20)); INSERT INTO restore_check.samples VALUES ('sample-001');") }
                    mongo { $null = Docker @('exec',$name,'mongosh','--quiet','--eval',"db.getSiblingDB('restore_check').samples.insertOne({sample:'sample-001'})") }
                    redis { $null = Docker @('exec',$name,'redis-cli','SET','restore-check','sample-001') }
                }
            } else {
                $value = switch ($database) {
                    mysql { Docker @('exec',$name,'mysql','-uroot','-N','-e','SELECT id FROM restore_check.samples') }
                    mongo { Docker @('exec',$name,'mongosh','--quiet','--eval',"db.getSiblingDB('restore_check').samples.findOne().sample") }
                    redis { Docker @('exec',$name,'redis-cli','GET','restore-check') }
                }
                if ($value.Trim() -ne 'sample-001') { throw "Restored value mismatch: $database" }
                Write-Output "$database restored data verified"
            }
            $null = Docker @('stop','--time','60',$name)
        }
        if ($side -eq 'source') {
            $null = RunHelper source @('-c', "from pathlib import Path; Path('/state/source.env').write_text('SYNTHETIC_ONLY=1\n'); Path('/volumes/app_data/sample.csv').write_text('sample,value\nsample-001,7\n'); Path('/volumes/app_tmp/check.txt').write_text('temporary-check')")
            $null = RunHelper source @('-c', "import sys; sys.path.insert(0,'/operations'); from cold_backup import backup; from pathlib import Path; backup(Path('/volumes'),Path('/state/source.env'),Path('/state/backup.tar.gz'))")
            $null = RunHelper target @('-c', "import sys; sys.path.insert(0,'/operations'); from cold_backup import restore; from pathlib import Path; config=Path('/state/restored-config'); config.mkdir(); restore(Path('/volumes'),config,Path('/state/backup.tar.gz')); assert Path('/volumes/app_data/sample.csv').read_text()=='sample,value\nsample-001,7\n'; assert Path('/volumes/app_tmp/check.txt').read_text()=='temporary-check'; assert (config/'.env.docker').read_text()=='SYNTHETIC_ONLY=1\n'")
            Write-Output 'Cold archive and file restoration verified'
        }
    }
    Write-Output 'PASS: MySQL, MongoDB, Redis and application files survived cold backup/restore'
} finally {
    $ErrorActionPreference = 'Continue'
    foreach ($name in $createdContainers) { $null = & rtk proxy docker rm -f $name 2>&1 }
    foreach ($name in $createdVolumes) { $null = & rtk proxy docker volume rm $name 2>&1 }
}
