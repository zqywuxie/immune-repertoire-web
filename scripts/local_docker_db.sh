#!/usr/bin/env bash
set -Eeuo pipefail

# Local Docker database helper.
# This script only operates on the local docker compose stack in this repo.
# It never uses SSH and never deletes volumes unless the "reset" command is used.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_ROOT/backups}"

MYSQL_CONTAINER="${MYSQL_CONTAINER:-ir_mysql}"
MONGO_CONTAINER="${MONGO_CONTAINER:-ir_mongodb}"
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-local-dev-root-password}"
MYSQL_USER="${MYSQL_USER:-ir_user}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-local-dev-password}"
MYSQL_DATABASE="${MYSQL_DATABASE:-immune_repertoire}"

MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27018}"
MONGO_USERNAME="${MONGO_USERNAME:-admin}"
MONGO_PASSWORD="${MONGO_PASSWORD:-local-dev-mongo-password}"
MONGO_DB_NAME="${MONGO_DB_NAME:-immune_repertoire}"

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me}"

usage() {
  cat <<'EOF'
Usage:
  scripts/local_docker_db.sh <command>

Commands:
  up       Start local MySQL and MongoDB containers.
  down     Stop containers, keep existing volumes/data.
  status   Show container status and local connection info.
  backup   Back up local MySQL and MongoDB into backups/local_YYYY-mm-dd_HHMMSS.
  migrate  Run auth/user-scope migration against local Docker MySQL and add Mongo indexes.
  init     Start DB, wait for MySQL, run migration.
  reset    DANGEROUS: stop containers and delete local Docker volumes.

Examples:
  scripts/local_docker_db.sh up
  scripts/local_docker_db.sh migrate
  scripts/local_docker_db.sh init
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

compose() {
  (cd "$PROJECT_ROOT" && $COMPOSE_CMD "$@")
}

wait_for_mysql() {
  echo "Waiting for local MySQL ${MYSQL_HOST}:${MYSQL_PORT} ..."
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
  echo "MySQL did not become reachable. Check docker status and local port mapping." >&2
  exit 1
}

check_python_mysql() {
  if ! python - <<'PY' >/dev/null 2>&1
import pymysql
PY
  then
    echo "Python package pymysql is missing."
    echo "Install dependencies first:"
    echo "  cd flask_app && pip install -r requirements.txt"
    exit 1
  fi
}

start_db() {
  require_command docker
  echo "Starting local Docker databases ..."
  compose up -d mysql mongodb
}

stop_db() {
  require_command docker
  echo "Stopping local Docker databases; volumes are kept."
  compose down
}

show_status() {
  require_command docker
  compose ps
  cat <<EOF

Local database connection:
  MySQL:   ${MYSQL_USER}@${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE}
  MongoDB: ${MONGO_USERNAME}@${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB_NAME}

Local Flask startup:
  python flask_app/app.py
EOF
}

backup_db() {
  require_command docker
  local backup_dir="$BACKUP_ROOT/local_$(date +%F_%H%M%S)"
  mkdir -p "$backup_dir"

  echo "Backing up MySQL to $backup_dir ..."
  docker exec "$MYSQL_CONTAINER" mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" > "$backup_dir/${MYSQL_DATABASE}.sql"

  echo "Backing up MongoDB to $backup_dir ..."
  docker exec "$MONGO_CONTAINER" rm -rf /tmp/local_mongo_backup
  docker exec "$MONGO_CONTAINER" mongodump \
    --username "$MONGO_USERNAME" \
    --password "$MONGO_PASSWORD" \
    --authenticationDatabase admin \
    --db "$MONGO_DB_NAME" \
    --out /tmp/local_mongo_backup
  docker cp "$MONGO_CONTAINER:/tmp/local_mongo_backup" "$backup_dir/mongo"
  docker exec "$MONGO_CONTAINER" rm -rf /tmp/local_mongo_backup

  echo "Backup complete: $backup_dir"
}

create_mongo_indexes() {
  require_command docker
  echo "Creating local MongoDB user-scope indexes ..."
  docker exec "$MONGO_CONTAINER" mongosh \
    -u "$MONGO_USERNAME" \
    -p "$MONGO_PASSWORD" \
    --authenticationDatabase admin \
    "$MONGO_DB_NAME" \
    --eval '
db.rawdata.createIndex({ user_id: 1 });
db.rawdata.createIndex({ user_id: 1, project_id: 1, asset_type: 1 });
db.results.createIndex({ user_id: 1 });
db.results.createIndex({ user_id: 1, project_id: 1, analysis_type: 1 });
db.analysis_cache.createIndex({ user_id: 1 });
db.analysis_cache.createIndex({ user_id: 1, project_id: 1 });
'
}

migrate_db() {
  check_python_mysql
  wait_for_mysql
  echo "Running local MySQL auth/user-scope migration ..."
  (
    cd "$PROJECT_ROOT/flask_app"
    export FLASK_CONFIG=development
    export MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE ADMIN_PASSWORD
    python migrations/add_auth_user_scope.py --dry-run
    python migrations/add_auth_user_scope.py --apply --admin-username "$ADMIN_USERNAME" --admin-email "$ADMIN_EMAIL"
    python migrations/add_auth_user_scope.py --verify
    python migrations/add_analysis_jobs.py --dry-run
    python migrations/add_analysis_jobs.py --apply
    python migrations/add_analysis_jobs.py --verify
  )
  create_mongo_indexes
  cat <<EOF

Local migration complete.
Default local admin:
  username: $ADMIN_USERNAME
  email:    $ADMIN_EMAIL
  password: $ADMIN_PASSWORD
EOF
}

reset_db() {
  require_command docker
  echo "DANGER: this will delete local Docker database volumes for this compose project."
  echo "Existing volumes observed by compose will be removed. This is intended only for local rebuilds."
  read -r -p "Type RESET to continue: " answer
  if [[ "$answer" != "RESET" ]]; then
    echo "Reset cancelled."
    exit 1
  fi
  compose down -v
  echo "Local database volumes removed."
}

main() {
  local command="${1:-}"
  case "$command" in
    up) start_db ;;
    down) stop_db ;;
    status) show_status ;;
    backup) backup_db ;;
    migrate) migrate_db ;;
    init) start_db; migrate_db ;;
    reset) reset_db ;;
    -h|--help|help) usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
