# Development

## Branch Environment
- Development target: v3.0-dev
- Service: `autohunter-web-dev.service`
- Port: 5001

## Rules
- Do not modify production service or symlink while developing.
- Validate features in dev first.
- Keep release process deterministic and scriptable.

## Validation Checklist
- Unit tests
- Rescore run
- Pipeline run
- UI smoke checks
- DB integrity checks
