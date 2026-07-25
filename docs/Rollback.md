# Rollback

## Preconditions
- Previous production archive exists and is verified.
- Previous production directory (or restored directory) is available.

## Rollback Procedure
1. Stop production web service.
2. Point symlink back:
   - `ln -sfn /opt/carhunter/<previous_release> /opt/carhunter/current`
3. Start production web service and timer.
4. Validate port 5000, UI version, and DB access.

## v2.9 Rollback Asset
- Archive created during promotion under:
  - `/opt/carhunter/backups/release-archives/`
