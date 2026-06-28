#!/usr/bin/env bash
set -Eeuo pipefail

# One-command database upgrade for the Linux Docker database deployment.
#
# Typical local-on-DB-server usage:
#   chmod +x scripts/update_database_linux.sh
#   MYSQL_ROOT_PASSWORD='your-root-password' ADMIN_PASSWORD='change-me' scripts/update_database_linux.sh --yes
#
# Typical remote-DB usage from a machine with this project code:
#   DB_SSH='user@db-server' DB_COMPOSE_DIR='/opt/immune-repertoire-web' \
#   MYSQL_HOST='db-server-ip' MYSQL_ROOT_PASSWORD='your-root-password' ADMIN_PASSWORD='change-me' \
#   scripts/update_database_linux.sh --yes

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups/db_$(date +%F_%H%M%S)}"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
DB_COMPOSE_DIR="${DB_COMPOSE_DIR:-$PROJECT_ROOT}"
DB_SSH="${DB_SSH:-}"

MYSQL_CONTAINER="${MYSQL_CONTAINER:-ir_mysql}"
MONGO_CONTAINER="${MONGO_CONTAINER:-ir_mongodb}"
MYSQL_DATABASE="${MYSQL_DATABASE:-immune_repertoire}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-local-dev-root-password}"
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
MYSQL_USER="${MYSQL_USER:-ir_user}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-local-dev-password}"

MONGO_USERNAME="${MONGO_USERNAME:-admin}"
MONGO_PASSWORD="${MONGO_PASSWORD:-local-dev-mongo-password}"
MONGO_DB_NAME="${MONGO_DB_NAME:-immune_repertoire}"

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me}"

YES=0
SKIP_BACKUP=0
SKIP_RESTART=0
SKIP_MYSQL_MIGRATION=0
SKIP_MONGO_INDEXES=0

usage() {
  cat <<'EOF'
Usage:
  scripts/update_database_linux.sh [--yes] [options]

Options:
  --yes                   Run without confirmation.
  --skip-backup           Skip MySQL/MongoDB backups.
  --skip-restart          Skip docker compose restart.
  --skip-mysql-migration  Skip SQL migration script.
  --skip-mongo-indexes    Skip MongoDB index creation.
  -h, --help              Show help.

Important env vars:
  MYSQL_ROOT_PASSWORD     MySQL root password inside Docker.
  MYSQL_HOST              Host/IP reachable by the migration script. Default: 127.0.0.1.
  MYSQL_PORT              Host MySQL port. Default: 3307.
  MYSQL_USER              App MySQL user. Default: ir_user.
  MYSQL_PASSWORD          App MySQL password. Default: local-dev-password.
  ADMIN_PASSWORD          Initial/admin password used by the migration.
  DB_SSH                  Optional SSH target for Docker commands, e.g. user@server.
  DB_COMPOSE_DIR          docker-compose.yml path on DB server. Default: project root.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --skip-backup) SKIP_BACKUP=1 ;;
    --skip-restart) SKIP_RESTART=1 ;;
    --skip-mysql-migration) SKIP_MYSQL_MIGRATION=1 ;;
    --skip-mongo-indexes) SKIP_MONGO_INDEXES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

run_db() {
  if [[ -n "$DB_SSH" ]]; then
    ssh "$DB_SSH" "cd '$DB_COMPOSE_DIR' && $*"
  else
    (cd "$DB_COMPOSE_DIR" && bash -lc "$*")
  fi
}

copy_from_db() {
  local remote_path="$1"
  local local_path="$2"
  if [[ -n "$DB_SSH" ]]; then
    scp -r "$DB_SSH:$remote_path" "$local_path"
  else
    cp -r "$remote_path" "$local_path"
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

confirm() {
  if [[ "$YES" -eq 1 ]]; then
    return
  fi
  echo "This will upgrade the database schema for user/auth/path isolation."
  echo "Backups will be written to: $BACKUP_DIR"
  echo "MySQL target for migration: ${MYSQL_USER}@${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE}"
  echo "Docker target: ${DB_SSH:-local}:${DB_COMPOSE_DIR}"
  read -r -p "Continue? [y/N] " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]] || exit 1
}

backup_mysql() {
  mkdir -p "$BACKUP_DIR"
  local remote_backup="/tmp/${MYSQL_DATABASE}_$(date +%F_%H%M%S).sql"
  echo "[1/5] Backing up MySQL to $BACKUP_DIR ..."
  run_db "docker exec '$MYSQL_CONTAINER' mysqldump -uroot -p'$MYSQL_ROOT_PASSWORD' '$MYSQL_DATABASE' > '$remote_backup'"
  copy_from_db "$remote_backup" "$BACKUP_DIR/"
  run_db "rm -f '$remote_backup'"
}

backup_mongo() {
  mkdir -p "$BACKUP_DIR"
  local stamp
  stamp="$(date +%F_%H%M%S)"
  local remote_dir="/tmp/mongo_backup_${stamp}"
  echo "[2/5] Backing up MongoDB to $BACKUP_DIR ..."
  run_db "docker exec '$MONGO_CONTAINER' rm -rf '$remote_dir'"
  run_db "docker exec '$MONGO_CONTAINER' mongodump --username '$MONGO_USERNAME' --password '$MONGO_PASSWORD' --authenticationDatabase admin --db '$MONGO_DB_NAME' --out '$remote_dir'"
  run_db "rm -rf '$remote_dir' && docker cp '$MONGO_CONTAINER:$remote_dir' '$remote_dir'"
  copy_from_db "$remote_dir" "$BACKUP_DIR/"
  run_db "rm -rf '$remote_dir'"
}

restart_databases() {
  echo "[3/5] Restarting database containers without deleting volumes ..."
  run_db "$COMPOSE_CMD down"
  run_db "$COMPOSE_CMD up -d mysql mongodb"
}

wait_for_mysql() {
  echo "Waiting for MySQL ${MYSQL_HOST}:${MYSQL_PORT} ..."
  for _ in $(seq 1 60); do
    if MYSQL_HOST="$MYSQL_HOST" MYSQL_PORT="$MYSQL_PORT" MYSQL_USER="$MYSQL_USER" MYSQL_PASSWORD="$MYSQL_PASSWORD" MYSQL_DATABASE="$MYSQL_DATABASE" \
      python - <<'PY' >/dev/null 2>&1
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
PY
    then
      echo "MySQL is ready."
      return
    fi
    sleep 2
  done
  echo "MySQL did not become reachable. Check MYSQL_HOST/MYSQL_PORT/firewall." >&2
  exit 1
}

run_mysql_migration() {
  echo "[4/5] Running MySQL auth/user-scope migration ..."
  [[ -f "$PROJECT_ROOT/flask_app/migrations/add_auth_user_scope.py" ]] || {
    echo "Migration script not found. Run this script from the updated project code." >&2
    exit 1
  }
  if ! python - <<'PY' >/dev/null 2>&1
import pymysql
PY
  then
    echo "Python package pymysql is missing. Install dependencies first:"
    echo "  cd flask_app && pip install -r requirements.txt"
    exit 1
  fi
  if [[ -z "$ADMIN_PASSWORD" ]]; then
    echo "ADMIN_PASSWORD is not set. Refusing to create a random admin password in one-click mode." >&2
    echo "Set ADMIN_PASSWORD='your-secure-password' and rerun." >&2
    exit 1
  fi

  (
    cd "$PROJECT_ROOT/flask_app"
    export FLASK_CONFIG=production
    export MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE ADMIN_PASSWORD
    python migrations/add_auth_user_scope.py --dry-run
    python migrations/add_auth_user_scope.py --apply --admin-username "$ADMIN_USERNAME" --admin-email "$ADMIN_EMAIL"
    python migrations/add_auth_user_scope.py --verify
    python migrations/add_analysis_jobs.py --dry-run
    python migrations/add_analysis_jobs.py --apply
    python migrations/add_analysis_jobs.py --verify
  )
}

create_mongo_indexes() {
  echo "[5/5] Creating MongoDB user-scope indexes ..."
  local js
  js='
db.rawdata.createIndex({ user_id: 1 });
db.rawdata.createIndex({ user_id: 1, project_id: 1, asset_type: 1 });
db.results.createIndex({ user_id: 1 });
db.results.createIndex({ user_id: 1, project_id: 1, analysis_type: 1 });
db.analysis_cache.createIndex({ user_id: 1 });
db.analysis_cache.createIndex({ user_id: 1, project_id: 1 });
'
  run_db "docker exec '$MONGO_CONTAINER' mongosh -u '$MONGO_USERNAME' -p '$MONGO_PASSWORD' --authenticationDatabase admin '$MONGO_DB_NAME' --eval '$js'"
}

print_summary() {
  cat <<EOF

Database update finished.

Backup directory:
  $BACKUP_DIR

Admin login:
  username: $ADMIN_USERNAME
  email:    $ADMIN_EMAIL

Rollback MySQL example:
  docker exec -i $MYSQL_CONTAINER mysql -uroot -p'\$MYSQL_ROOT_PASSWORD' $MYSQL_DATABASE < $BACKUP_DIR/${MYSQL_DATABASE}_*.sql

Next production env suggestions:
  REQUIRE_LOGIN=true
  AUTH_REGISTER_ENABLED=false
  USER_DATA_ROOT=/data/immune-repertoire/users
  DEFAULT_USER_ALLOWED_PATHS=/data/immune-repertoire/shared
EOF
}

main() {
  require_command python
  if [[ -n "$DB_SSH" ]]; then
    require_command ssh
    require_command scp
  else
    require_command docker
  fi

  confirm

  if [[ "$SKIP_BACKUP" -eq 0 ]]; then
    backup_mysql
    backup_mongo
  else
    echo "[skip] Backups skipped."
  fi

  if [[ "$SKIP_RESTART" -eq 0 ]]; then
    restart_databases
  else
    echo "[skip] Docker restart skipped."
  fi

  if [[ "$SKIP_MYSQL_MIGRATION" -eq 0 ]]; then
    wait_for_mysql
    run_mysql_migration
  else
    echo "[skip] MySQL migration skipped."
  fi

  if [[ "$SKIP_MONGO_INDEXES" -eq 0 ]]; then
    create_mongo_indexes
  else
    echo "[skip] Mongo indexes skipped."
  fi

  print_summary
}

main "$@"
