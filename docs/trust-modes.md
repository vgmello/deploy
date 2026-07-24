# Trust & identity model

How the platform authenticates to Azure, isolates privilege across deploy
phases, and lets untrusted repos deploy without holding deploy-capable
credentials.

## Three deploy identities

Every tool+environment deploys through three managed identities, each with the
least privilege its phase needs:

| Identity                                                    | Scope          | Role                                                                        | Runs                         |
| ----------------------------------------------------------- | -------------- | --------------------------------------------------------------------------- | ---------------------------- |
| `id-cloudapp-bootstrap-<env>` (shared per subscription+env) | subscription   | custom `cloudapp-bootstrap` (create RGs, identities, role assignments only) | the per-tool bootstrap stack |
| `id-<tool>-<env>-plan`                                      | resource group | Reader + Storage Blob Data Reader + Key Vault Reader                        | `terraform plan`             |
| `id-<tool>-<env>-apply`                                     | resource group | Contributor                                                                 | `terraform apply`            |

The bootstrap identity can create the resource group and the two per-RG
identities, and nothing else — it is never Owner and holds no wildcard action.
The plan identity is read-only; only the apply identity writes.

## Two stacks, two state files

Per tool+environment:

- `terraform/bootstrap/` → `<tool>/<env>.bootstrap.tfstate` — the RG and the
  plan/apply identities. Written by the bootstrap identity.
- `terraform/` (main) → `<tool>/<env>.tfstate` — the actual resources. Read by
  the plan identity, written by the apply identity.

## Event-gated phases

- **Pull request** → plan only, under the plan identity. A missing RG just
  yields an all-creates plan.
- **Default branch** → bootstrap identity applies the bootstrap stack, then the
  plan identity plans the main stack, then the apply identity applies it.

`python3 -m cloudapp login-plan --event <event> --platform-file <file>` emits
the exact ordered phases the workflow runs.

## Self vs delegated

The reusable workflow takes a `mode` input (default `delegated`).

- **self** — the app repo runs the deploy in its own workflow; the identities'
  federated credentials trust the app repo's OIDC subjects.
- **delegated** — the app repo only dispatches to the central deploy repo,
  which runs the identical deploy under _its_ OIDC subject. The app repo never
  holds federation to the powerful identities.

Federated-credential subjects (written onto the identities by the per-tool
bootstrap stack, sourced from `cloudapp.identity.federation_subjects`):

| Identity  | self mode                                                 | delegated mode                               |
| --------- | --------------------------------------------------------- | -------------------------------------------- |
| plan      | `repo:<app>:pull_request`, `repo:<app>:environment:<env>` | `repo:vgmello/deploy:environment:<env>-plan` |
| apply     | `repo:<app>:environment:<env>`                            | `repo:vgmello/deploy:environment:<env>`      |
| bootstrap | `repo:<trusted>:environment:<env>`                        | same                                         |

The subject is the security boundary: a delegated app repo cannot mint an OIDC
token matching the identities' federated subjects, so it cannot assume plan or
apply — only the central repo's runner can. GitHub environment required
reviewers on `environment:<env>` remain the apply approval gate.

## State backends (Azure Blob or AWS S3)

`state_backend.type` in `environments/<env>.yml` selects the backend:

```yaml
state_backend:
  type: azurerm # or s3
  resource_group: rg-tfstate
  storage_account: sttfstateprod
  container: tfstate
```

```yaml
state_backend:
  type: s3
  bucket: my-tfstate
  region: us-east-1
  dynamodb_table: tfstate-locks
  role_arn: arn:aws:iam::123456789012:role/gha-tfstate
```

- **azurerm** — reached via `azure/login` OIDC (`use_oidc`, `use_azuread_auth`).
  bootstrap+apply identities get Storage Blob Data Contributor on the state
  container; plan gets Storage Blob Data Reader.
- **s3** — reached via `AssumeRoleWithWebIdentity` into `role_arn`. Resources
  stay Azure; the AWS login authorizes only the state backend, so an S3 run
  performs two OIDC logins (AWS for state, Azure for the plan/apply identity).

## One-time setup

A subscription owner runs `bootstrap/` once per subscription+environment (see
`bootstrap/README.md`): it creates the custom role, the shared bootstrap
identity, and its federated credential, and outputs
`bootstrap_identity_client_id` for `environments/<env>.yml`. Everything after is
automated on deploy.

## Live-only gaps

Offline tests cover backend rendering, federation-subject resolution, login
sequencing, dispatch, and the bootstrap stacks (mock providers). Not exercised
until a sandbox integration run: real OIDC token exchange (Azure + AWS), RBAC
propagation timing after the per-tool bootstrap mints the plan/apply
identities, cross-cloud two-login runs, and the end-to-end deploy workflow.
