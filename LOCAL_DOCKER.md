# Local Docker Database

This project uses local Docker for MySQL and MongoDB during development. The Flask app still runs on the host with:

```bash
python flask_app/app.py
```

## Current Local Ports

```text
MySQL   127.0.0.1:3307 -> container 3306
MongoDB 127.0.0.1:27018 -> container 27017
```

The local `.env` should point to those ports:

```text
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MONGO_HOST=127.0.0.1
MONGO_PORT=27018
```

## Windows First Run Or Upgrade Existing Local DB

Use PowerShell from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 init
```

This starts the existing local Docker database containers, waits for MySQL, runs the auth/user-scope migration, and adds MongoDB indexes.

## Windows Daily Use

```powershell
powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 up
python flask_app\app.py
```

Check status:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 status
```

Stop containers without deleting data:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 down
```

Back up local database:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 backup
```

Reset local database only when you intentionally want to delete local Docker volumes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\local_docker_db.ps1 reset
```

The reset command requires typing `RESET`.

## Linux/WSL Alternative

```bash
scripts/local_docker_db.sh init
```

## Linux/WSL Daily Use

```bash
scripts/local_docker_db.sh up
python flask_app/app.py
```

Check status:

```bash
scripts/local_docker_db.sh status
```

Stop containers without deleting data:

```bash
scripts/local_docker_db.sh down
```

## Linux/WSL Backup

```bash
scripts/local_docker_db.sh backup
```

Backups are written to `backups/local_YYYY-mm-dd_HHMMSS/`.

## Linux/WSL Reset Local DB

Only use this for local rebuilds:

```bash
scripts/local_docker_db.sh reset
```

The reset command requires typing `RESET` and removes local Docker volumes.

## Notes

- These local scripts never use SSH and never touch the server database.
- On Windows, prefer `scripts\local_docker_db.ps1`.
- Server database updates still use `scripts/update_database_linux.sh`.
- The default local admin password is `admin123`; change it for any non-local environment.
