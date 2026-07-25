# Release Process

## v2.9 Promotion Summary
- Source: `/opt/carhunter/v2.9-dev`
- Target: `/opt/carhunter/v2.9`
- Production symlink updated to `/opt/carhunter/v2.9`
- Development successor created at `/opt/carhunter/v3.0-dev`

## Standard Steps
1. Pre-flight: git, DB health, schema checks, version checks
2. Stop production services/timer
3. Archive previous production release
4. Copy release directory
5. Promote development DB into release directory
6. Convert release markers to production
7. Activate via symlink + services
8. Execute smoke tests
9. Create next development environment
10. Execute release audit

## Required Validations
- Production: service active, port 5000, correct version, healthy DB
- Development: service active, port 5001, correct version
- Pipeline timer active
