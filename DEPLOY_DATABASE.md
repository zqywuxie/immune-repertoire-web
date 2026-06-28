# Linux Docker Database Redeploy Guide

This project uses Docker Compose for MySQL and MongoDB. The `docker/mysql/init`
and `docker/mongo/init` files only run when the named volumes are empty.

## Existing Server Upgrade

Do not delete volumes for an upgrade.

1. Back up MySQL:

```bash
docker exec ir_mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" immune_repertoire > backup_immune_repertoire_$(date +%F_%H%M).sql
```

2. Back up MongoDB:

```bash
docker exec ir_mongodb mongodump --username "$MONGO_USERNAME" --password "$MONGO_PASSWORD" --authenticationDatabase admin --db immune_repertoire --out /tmp/mongo_backup
docker cp ir_mongodb:/tmp/mongo_backup ./mongo_backup_$(date +%F_%H%M)
```

3. Restart only database containers:

```bash
docker compose down
docker compose up -d mysql mongodb
```

4. Run the SQL ownership/auth migration:

```bash
cd flask_app
python migrations/add_auth_user_scope.py --dry-run
ADMIN_PASSWORD='change-this-password' python migrations/add_auth_user_scope.py --apply --admin-username admin --admin-email admin@example.com
python migrations/add_auth_user_scope.py --verify
```

5. Start the Flask app:

```bash
python flask_app/app.py
```

## Fresh Database

Only use this when old data is not needed.

```bash
docker compose down -v
docker compose up -d mysql mongodb
cd flask_app
python init_db.py
ADMIN_PASSWORD='change-this-password' python migrations/add_auth_user_scope.py --apply --admin-username admin --admin-email admin@example.com
python flask_app/app.py
```

## Required Production Environment

When the app runs on the host and databases run in Docker:

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MONGO_HOST=127.0.0.1
MONGO_PORT=27018
REQUIRE_LOGIN=true
AUTH_REGISTER_ENABLED=false
USER_DATA_ROOT=/data/immune-repertoire/users
DEFAULT_USER_ALLOWED_PATHS=/data/immune-repertoire/shared
```

When the app also runs inside Docker on the same Compose network:

```bash
MYSQL_HOST=mysql
MYSQL_PORT=3306
MONGO_HOST=mongodb
MONGO_PORT=27017
```

Create the Linux data roots before production use:

```bash
sudo mkdir -p /data/immune-repertoire/users /data/immune-repertoire/shared
sudo chown -R <app-user>:<app-user> /data/immune-repertoire
```
