-- D1: Checksum & lineage tracking for assets
-- Run this after the initial schema to add asset integrity and job-asset relationship tracking.
-- This is idempotent — safe to run multiple times.

-- Add checksum column to project_assets (if not already present)
SET @dbname = IFNULL(@dbname, 'immune_repertoire');

SET @sql = CONCAT(
    'ALTER TABLE `', @dbname, '`.`project_assets` ',
    'ADD COLUMN `checksum` VARCHAR(128) NULL AFTER `size`, ',
    'ADD COLUMN `checksum_algorithm` VARCHAR(16) NULL DEFAULT ''sha256'' AFTER `checksum`'
);

-- Only execute if columns don't exist
SET @col_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
      AND TABLE_NAME = 'project_assets'
      AND COLUMN_NAME = 'checksum'
);

SET @sql = IF(@col_exists = 0, @sql, 'SELECT ''checksum column already exists'' AS msg');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Create job_assets join table for lineage tracking
SET @sql2 = CONCAT(
    'CREATE TABLE IF NOT EXISTS `', @dbname, '`.`job_assets` (',
    '  `id` VARCHAR(36) NOT NULL,',
    '  `job_id` VARCHAR(64) NOT NULL,',
    '  `asset_id` VARCHAR(36) NOT NULL,',
    '  `role` VARCHAR(50) NOT NULL DEFAULT ''output'',',
    '  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,',
    '  PRIMARY KEY (`id`),',
    '  INDEX `ix_job_assets_job` (`job_id`),',
    '  INDEX `ix_job_assets_asset` (`asset_id`),',
    '  CONSTRAINT `fk_job_assets_job` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs`(`id`) ON DELETE CASCADE,',
    '  CONSTRAINT `fk_job_assets_asset` FOREIGN KEY (`asset_id`) REFERENCES `project_assets`(`id`) ON DELETE CASCADE',
    ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;
