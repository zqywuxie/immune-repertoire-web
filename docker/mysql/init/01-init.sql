-- MySQL initialization for Immune Repertoire Analysis
-- This runs on first container startup

CREATE DATABASE IF NOT EXISTS immune_repertoire
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Grant privileges to the application user
GRANT ALL PRIVILEGES ON immune_repertoire.* TO 'ir_user'@'%';
FLUSH PRIVILEGES;

-- Table creation is handled by SQLAlchemy db.create_all().
-- Existing databases must be upgraded with:
--   python flask_app/migrations/add_auth_user_scope.py --apply
-- This init file only runs when the mysql_data volume is empty.
