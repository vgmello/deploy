# Using the cloudapp platform

## 1. Add a manifest

`.cloud-app.yml` at your repo root:

```yaml
name: orders-api
app:
  port: 8080
database:
  size: small
environments:
  dev: {}
  prod:
    database:
      size: medium
```

## 2. Call the reusable workflow

`.github/workflows/deploy.yml` in your repo:

```yaml
name: deploy
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    uses: vgmello/deploy/.github/workflows/deploy.yml@v1
    secrets: inherit
    with:
      plan_only: ${{ github.event_name == 'pull_request' }}
      deploy_ref: v1   # keep in lockstep with the @v1 pin above
```

## 3. Configure GitHub environments

Create a GitHub environment per manifest env key (`dev`, `prod`, ...). Put
required reviewers on `prod` — that is the approval gate. Add any manifest
`secrets:` names as environment secrets.

## Notes

- Push to main deploys every environment in manifest order; the chain stops
  on first failure. Max 4 environments.
- PRs run plan-only.
- Docker: a `Dockerfile` at the repo root (or `docker:` sections) triggers
  image builds; images are built once and promoted across environments.
  Docker settings must not vary per environment; the ACR is assumed shared.
- `workflow_dispatch`-style single-env deploys: pass `environment: dev`.
- PR plan-only runs plan against the first environment only, so protected
  environment gates are never touched by PRs.
- Azure OIDC: each environment's deploy service principal (client id in
  `environments/<env>.yml`) needs a federated credential for your repo, plus
  Key Vault Secrets Officer at resource-group (or subscription) scope so
  sync-secrets can write manifest secrets.
- `runner_access: private` environments require self-hosted runners inside
  the VNet — GitHub-hosted runners cannot reach a firewalled Key Vault.
- One manifest (one platform call) per workflow run: the config artifact
  name is fixed, so calling the reusable workflow twice in a single run is
  not supported.
