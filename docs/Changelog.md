# Changelog (Consolidated)

## v2.9 (Production)
- Release Date: 2026-07-25
- Base Commit: `dd0df77`
- Notable Tag in history: `v2.9.0`

### Major Features
- Canonical orchestration pipeline for CLI/Web processing consistency
- Expanded scoring and deal score refresh workflows
- Data repair engine integration and operational hardening

### Bug Fixes
- Personal scoring coverage and rescore flow consistency fixes
- Search filter UX and full-list rendering improvements

### Architecture Changes
- Centralized mutable execution flow through `orchestration.py`
- Clearer production/dev environment separation

### Migration Notes
- Production promoted from `v2.9-dev` to `v2.9`
- Next development environment created as `v3.0-dev`

### Operational Notes
- Production web on port 5000
- Development web on port 5001
- Pipeline scheduler managed by systemd timer

### Lessons Learned
- Validate service file targets after creating next dev environment
- Always verify symlink, ports, and DB path before declaring success

## Legacy Release Notes
Historical notes remain in:
- `CHANGELOG_v2.8-dev.md`
- `CHANGELOG_v2.9-dev.md`
