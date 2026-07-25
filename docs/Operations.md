# Operations

## Core Commands
- Web production status: `systemctl status autohunter-web.service`
- Web dev status: `systemctl status autohunter-web-dev.service`
- Pipeline timer status: `systemctl status autohunter-pipeline.timer`
- Pipeline service status: `systemctl status autohunter-pipeline.service`

## Runtime Validation
- Production port: 5000
- Development port: 5001
- Symlink target: `/opt/carhunter/current` -> release directory

## Separation of Duties
- Production and development services must never share WorkingDirectory.
- Production and dev databases must remain directory-scoped.
