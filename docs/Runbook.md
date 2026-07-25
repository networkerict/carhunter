# Runbook

## Purpose
Operational playbook for release promotion and runtime recovery.

## Promotion Checklist
- Validate pre-flight health and schema
- Stop production units
- Archive previous production version
- Promote directory + database
- Update production markers
- Activate symlink
- Start services/timer
- Run smoke tests and audit

## Recovery Checklist
- Confirm failure scope (service, DB lock, config, path)
- Restore known-good symlink target
- Restart minimal required units
- Verify production UI and pipeline scheduler

## Common Pitfalls
- Editing wrong environment directory
- Confusing `vX.Y-dev` and production paths
- Forgetting `daemon-reload` after service changes
- Assuming ports without `ss -ltn` verification
