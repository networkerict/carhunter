# Deployment

## Model
- Production deployment is directory-based.
- `/opt/carhunter/current` defines active production version.

## Production Activation
1. Prepare release directory (`/opt/carhunter/vX.Y`).
2. Confirm production config (port 5000, production version markers).
3. Switch symlink: `ln -sfn /opt/carhunter/vX.Y /opt/carhunter/current`.
4. Reload/restart production services.
5. Run smoke tests.

## Services
- `autohunter-web.service` must point to `/opt/carhunter/current`.
- `autohunter-pipeline.service` must point to `/opt/carhunter/current`.
- `autohunter-pipeline.timer` schedules daily pipeline.

## Dev Isolation
- Development service must point to explicit dev directory.
- Development port remains 5001.
