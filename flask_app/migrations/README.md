# Database Migrations

This directory contains database migration scripts for the Immune Repertoire Analysis application.

## Available Migrations

### add_auth_user_scope.py

Adds local users, authentication ownership columns, default admin assignment, and user-level project/file/analysis scoping fields.

Recommended existing Docker database upgrade:

```bash
python migrations/add_auth_user_scope.py --dry-run
ADMIN_PASSWORD='change-this-password' python migrations/add_auth_user_scope.py --apply --admin-username admin --admin-email admin@example.com
python migrations/add_auth_user_scope.py --verify
```

This migration is idempotent and can be run multiple times. Existing rows with `user_id IS NULL` are assigned to the admin user.

### add_analysis_jobs.py

Adds the persistent `analysis_jobs` table used by the global background task center.

```bash
python migrations/add_analysis_jobs.py --dry-run
python migrations/add_analysis_jobs.py --apply
python migrations/add_analysis_jobs.py --verify
```

### migrate_analysis_history.py

Migrates existing analysis records to the unified analysis format by adding:
- `mode` field ('scheme' or 'custom')
- `scheme_id` field (for scheme-based analyses)
- `scheme_name` field (display name for schemes)
- `selected_fields` field (for custom analyses)

**Requirements:** 7.6, 10.1

#### Usage

**Dry run (preview changes without saving):**
```bash
python migrations/migrate_analysis_history.py --dry-run
```

**Run migration:**
```bash
python migrations/migrate_analysis_history.py
```

**Verify migration:**
```bash
python migrations/migrate_analysis_history.py --verify
```

**Quiet mode (minimal output):**
```bash
python migrations/migrate_analysis_history.py --quiet
```

#### Migration Logic

The script automatically determines the mode and scheme based on the analysis type:

**Scheme-based analyses:**
- `bcell_isotype`, `bcell_isotype_analysis`, `b_cell_isotype` → `bcell_isotype` scheme
- `shm`, `shm_analysis`, `somatic_hypermutation` → `shm_analysis` scheme
- `ig_metrics`, `ig_metrics_analysis`, `immunoglobulin_metrics` → `ig_metrics` scheme

**Custom analyses:**
- `custom_field`, `field_analysis`, `generic_field` → custom mode
- Selected fields are extracted from the `field_mapping` dictionary

#### Safety Features

1. **Idempotent:** Can be run multiple times safely - already migrated records are skipped
2. **Dry run mode:** Preview changes before applying them
3. **Verification:** Check that all records were migrated correctly
4. **Transaction safety:** Changes are committed per record with rollback on error
5. **Detailed logging:** Shows exactly what changes are being made

#### Example Output

```
Found 150 analysis records to process
Mode: LIVE (changes will be saved)
--------------------------------------------------------------------------------

Processing 1/150: Analysis abc-123-def
  Type: bcell_isotype_analysis
  Created: 2024-01-15 10:30:00
  ✓ Migrated:
    - Set mode to 'scheme'
    - Set scheme_id to 'bcell_isotype'
    - Set scheme_name to 'B细胞同型分析'

Processing 2/150: Analysis xyz-456-ghi
  Type: custom_field
  Created: 2024-01-16 14:20:00
  ✓ Migrated:
    - Set mode to 'custom'
    - Extracted 5 selected fields

...

================================================================================
Migration Summary:
  Total records: 150
  Migrated: 145
  Already migrated: 5
  Errors: 0

  ✓ Changes have been saved to the database
================================================================================
```

### add_unified_analysis_fields.py

Adds the new fields to the Analysis table schema. This migration should be run before `migrate_analysis_history.py`.

**Note:** This migration was already applied during the unified analysis implementation.

## Migration Order

When setting up a new database or migrating an existing one:

1. Run `add_unified_analysis_fields.py` (if not already applied)
2. Run `migrate_analysis_history.py --dry-run` to preview changes
3. Run `migrate_analysis_history.py` to apply changes
4. Run `migrate_analysis_history.py --verify` to confirm success

## Rollback

If you need to rollback the migration:

1. The original `type` field is preserved, so old code can still function
2. You can manually set `mode`, `scheme_id`, `scheme_name`, and `selected_fields` to NULL if needed
3. Consider backing up the database before running migrations

## Troubleshooting

**Issue:** Migration fails with "column does not exist" error

**Solution:** Run `add_unified_analysis_fields.py` first to add the new columns

---

**Issue:** Some records show as "already migrated" but have incorrect values

**Solution:** Manually update those records or set the fields to NULL and re-run the migration

---

**Issue:** Verification shows invalid records

**Solution:** Check the issues list and manually fix problematic records, then re-run verification
