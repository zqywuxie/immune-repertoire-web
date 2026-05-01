"""
Database connection configuration for MySQL (SQLAlchemy) and MongoDB (pymongo).
Reads from environment variables with sensible defaults for Docker Compose.
"""
import os

# ── MySQL (SQLAlchemy) ────────────────────────────────────────────

MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3307))
MYSQL_USER = os.environ.get('MYSQL_USER', 'ir_user')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'ir_pass_2024')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'immune_repertoire')

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    "?charset=utf8mb4"
)

# ── MongoDB (pymongo) ─────────────────────────────────────────────

MONGO_HOST = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT = int(os.environ.get('MONGO_PORT', 27018))
MONGO_USERNAME = os.environ.get('MONGO_USERNAME', 'admin')
MONGO_PASSWORD = os.environ.get('MONGO_PASSWORD', 'mongo_root_2024')
MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'immune_repertoire')

MONGO_URI = (
    f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}"
    f"@{MONGO_HOST}:{MONGO_PORT}"
    f"/?authSource=admin"
)
