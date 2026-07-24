# Stack lock registry

Each file binds a stack name (in one environment) to the repositories allowed to
deploy it. The `deploy-stack` gate (`.github/scripts/validate_and_lock.py`)
enforces this on every delegated deploy: the first repo to deploy a given stack
name claims it (trust-on-first-use), and any later caller not in `allowed_repos`
is rejected before Terraform runs.

## Layout

```
registries/
├── dev/
│   ├── cloud-app.yml       # owner: repo-a
│   └── payment-stack.yml   # owner: repo-b
└── staging/
    └── cloud-app.yml       # owner: repo-a
```

One directory per environment; one file per stack name (`<stack-name>.yml`).

## File format

```yaml
stack_name: cloud-app
environment: staging
allowed_repos:
  - owner/repo-a
registered_at: 2026-07-24T12:00:00Z
```

- `allowed_repos` — full `owner/name` entries permitted to deploy this stack.
  Add an entry here (via PR to this repo) to grant another repo access.
- The gate creates the file automatically on first deploy; edit it to add or
  remove authorized repos.

## Caller usage

An app repo triggers a delegated deploy with the dispatch action:

```yaml
- name: Deploy Staging Stack
  uses: <owner>/deploy/.github/actions/cloud-app@main
  with:
    app-id: ${{ vars.APP_ID }}
    app-private-key: ${{ secrets.APP_PRIVATE_KEY }}
    branch: 'feature/v2-migration'
    env: 'staging'
```

`repo` and `stack-name` default to the caller repository name and `cloud-app`;
override them when the manifest name or target stack differ.
