-- MySQL initialization for Immune Repertoire Analysis
-- This runs on first container startup

CREATE DATABASE IF NOT EXISTS immune_repertoire
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Grant privileges to the application user
GRANT ALL PRIVILEGES ON immune_repertoire.* TO 'ir_user'@'%';
FLUSH PRIVILEGES;
