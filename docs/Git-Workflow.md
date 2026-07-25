# Git Workflow

## Release Workflow
1. Stabilize development branch/version.
2. Verify clean working tree.
3. Run release validations.
4. Promote directory + DB.
5. Finalize production documentation.
6. Create next dev environment.

## Commit Hygiene
- Separate documentation/release metadata commits from feature commits.
- Avoid mixing production and development documentation updates in one commit when possible.

## Tags
- Do not auto-create tags during operational changes.
- Tag only when release validation is complete.
