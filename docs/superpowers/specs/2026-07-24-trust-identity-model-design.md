# Trust & Identity Model — Design

**Date:** 2026-07-24
**Status:** Approved
**Repo:** `vgmello/deploy`

## Overview

Redesign of the deploy platform's trust and identity model. Three coupled
changes: (1) two execution modes — a **self** mode where the app repo runs the
deploy action directly under its own OIDC-federated managed identities, and a
**delegated** mode where an untrusted app repo dispatches to a central trusted
repo that runs the identical action; (2) a state backend abstraction that
stores Terraform state in Azure Blob or AWS S3, each reached over OIDC; (3) a
three-tier managed-identity model — a shared, tightly-scoped bootstrap identity
that can only create resource groups and identities, plus per-RG read-only
(plan) and write (apply) identities.

Resources deployed remain Azure (azurerm) throughout; AWS appears only as an
optional state store.

This work also renames the platform `cloudtool` → `cloudapp` (package, manifest
file, docs) as a mechanical first step, so the trust-model changes layer onto
the new names.

## Goals

- Least privilege: no identity holds more than its phase needs; the root
  bootstrap identity is a custom role of four write actions, never Owner.
- Untrusted app repos can deploy without ever holding deploy-capable
  federation — the powerful identities trust only one repo's OIDC subject.
- State backend portable across Azure Blob and AWS S3, both via OIDC.
- Read/write separation: `terraform plan` runs read-only; only `apply` writes.
- Offline-testable: identity/login sequencing, federation-subject mapping, and
  backend rendering are pure functions with full unit coverage.

## Non-goals

- Deploying AWS resources (AWS is a state store only).
- Changing the manifest schema (only the file name changes).
- Automating the one-time per-subscription bootstrap (documented + scripted,
  run by a subscription owner).

## Rename: cloudtool → cloudapp

Mechanical, done first as its own PR before any trust-model code:

- `cloudtool/` package → `cloudapp/`; `python3 -m cloudtool` → `python3 -m cloudapp`.
- Manifest `.cloud-tool.yml` → `.cloud-app.yml` (workflow input default updated;
  schema `$id` updated).
- Docs, README, action adapters, spec references.
- Golden files and terraform fixtures unaffected in content; only path/module
  references change.

## Identity model

Per **subscription + environment** — one shared root, provisioned once:

- **`id-cloudapp-bootstrap-<env>`** — custom role `cloudapp-bootstrap` at
  **subscription scope**, exactly these actions (no wildcards):
  - `Microsoft.Resources/subscriptions/resourceGroups/read` + `/write`
  - `Microsoft.ManagedIdentity/userAssignedIdentities/read` + `/write`
  - `Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write`
  - `Microsoft.Authorization/roleAssignments/read` + `/write`

Per **tool + environment** — created by the bootstrap identity during a
default-branch deploy:

- **`id-<tool>-<env>-plan`** — RG-scoped **Reader**, plus the specific
  data-plane reader roles the modules need for `plan` refresh (Storage Blob
  Data Reader, Key Vault Reader). Runs `terraform plan`. **Read** on main state.
- **`id-<tool>-<env>-apply`** — RG-scoped **Contributor**. Runs `terraform
apply`. **Write** on main state.

The existing per-app/function workload identities (Key Vault / ACR access) are
unrelated and unchanged — they are runtime identities, not deploy identities.

## State backends + OIDC

Two state files per tool+env (different writers):

1. `<tool>/<env>.bootstrap.tfstate` — bootstrap stack (RG + plan/apply MIs +
   role assignments + federated creds). Written by the **bootstrap MI**.
2. `<tool>/<env>.tfstate` — the resources. Read by **plan MI**, written by
   **apply MI**.

Backend selected per environment:

```yaml
# environments/<env>.yml
state_backend:
  type: azurerm # azurerm | s3
  # azurerm:
  resource_group: rg-tfstate
  storage_account: sttfstateprod
  container: tfstate
  # s3 (when type: s3):
  # bucket: my-tfstate
  # region: us-east-1
  # dynamodb_table: tfstate-locks
  # role_arn: arn:aws:iam::123456789012:role/gha-tfstate
```

OIDC access:

- **azurerm** — `azure/login` provides the token; backend uses `use_oidc=true`,
  `use_azuread_auth=true`. Data-plane grants: bootstrap + apply MIs → Storage
  Blob Data Contributor on the state container; plan MI → Storage Blob Data
  Reader.
- **s3** — `aws-actions/configure-aws-credentials` performs
  `AssumeRoleWithWebIdentity` from the GitHub OIDC token into `role_arn`; the
  S3 backend uses that role. IAM/bucket policy scopes read vs write per phase
  (plan role read-only, apply role read-write). Native S3 locking.

`tfdeploy` renders the correct `backend` block and runs the correct OIDC
login(s) by `state_backend.type`. An S3 backend means two OIDC logins per run —
AWS for state, Azure for the plan/apply MI touching resources — from the same
GitHub token, different audiences. Documented.

## Trust modes

One `mode` input on the reusable workflow, default `delegated`.

**`mode: self`** — app repo runs the action in its own workflow; the three MIs'
federated credentials trust the app repo's OIDC subjects; the app repo
self-manages its state key.

**`mode: delegated`** — app repo's workflow only `repository_dispatch`es into
the central deploy repo (`vgmello/deploy`) with the manifest + git SHA; the
central repo runs the identical action; the MIs trust the central repo's
subjects. The app repo never holds federation to the powerful identities. The
central repo enforces an allowlist of which app repos may dispatch and which
environment each maps to.

Federated-credential subjects the bootstrap stack writes onto each MI (it takes
`mode` + resolved repo + env as input):

| MI        | self mode                                                         | delegated mode                               |
| --------- | ----------------------------------------------------------------- | -------------------------------------------- |
| plan      | `repo:<app>:pull_request`, `repo:<app>:environment:<env>`         | `repo:vgmello/deploy:environment:<env>-plan` |
| apply     | `repo:<app>:environment:<env>`                                    | `repo:vgmello/deploy:environment:<env>`      |
| bootstrap | `repo:<trusted>:environment:<env>` (set at manual bootstrap time) | same                                         |

The subject is the security boundary: a delegated app repo cannot mint a token
matching the MI's federated subject, so it cannot assume plan/apply — only the
central repo's runner can. GitHub environment required-reviewers on
`environment:<env>` remain the apply approval gate.

## Workflow: event-gated identity handoff

**PR run (plan only):**

1. Login state-backend identity (read) → init backend.
2. Login **plan MI** (read) → `terraform plan` main stack → post plan. No
   bootstrap, no apply; a missing RG just yields an all-creates plan.

**Default-branch run (plan + apply):**

1. Login **bootstrap MI** → `terraform apply` the bootstrap stack (RG + plan/apply
   MIs + role assignments + federated creds), state `<tool>/<env>.bootstrap.tfstate`.
2. Login **plan MI** → `terraform plan` main stack → plan file.
3. Login **apply MI** → `terraform apply` the plan file, state `<tool>/<env>.tfstate`.

`sync-secrets` slots between bootstrap and apply as today (unchanged logic, now
running under the apply MI). When the state backend is S3, each phase also runs
`configure-aws-credentials`.

**Delegated mode** runs the identical sequence inside the central repo's job,
triggered by the app repo's dispatch, under the central repo's OIDC subject.

New RBAC-propagation wrinkle: bootstrap creates the plan/apply MIs and their
role assignments, then step 2 immediately logs in as them. New assignments take
30–60s to propagate, so the plan login uses the same retry-with-backoff the
apply already uses.

## Manual vs automated

**Manual, once per subscription+env** (`bootstrap/` Terraform stack, run by a
subscription owner):

- Custom role `cloudapp-bootstrap` (subscription scope, the four write actions).
- `id-cloudapp-bootstrap-<env>` + that role assignment.
- Its federated credential → trusted repo's `environment:<env>` subject.
- State-backend data-plane grants for the bootstrap MI.
- Scripted; output IDs recorded in `environments/<env>.yml`.

**Automated per tool+env** (`terraform/bootstrap/` stack, under bootstrap MI on
default-branch deploys):

- `rg-<tool>-<env>`.
- `id-<tool>-<env>-plan` (RG Reader + data-plane readers + state read) + fed creds.
- `id-<tool>-<env>-apply` (RG Contributor + state write) + fed creds.

**Automated per tool+env** (existing `terraform/` main stack, plan under plan MI,
apply under apply MI): everything already built.

## Config surface

`environments/<env>.yml` gains:

```yaml
bootstrap_identity_client_id: ...       # id-cloudapp-bootstrap-<env>
state_backend:
  type: azurerm | s3
  ...
# plan/apply MI client IDs are OUTPUTS of the bootstrap stack, discovered at run
# time from bootstrap state — not hand-authored.
```

Manifest surface unchanged except the `.cloud-app.yml` rename. Trust `mode` is a
workflow input (org/repo policy), not manifest.

## Testing

**Python (`cloudapp/`, pytest):**

- Backend rendering: `azurerm` vs `s3` blocks, both state keys, error on
  missing/invalid backend config.
- Login sequencing: (event × mode) → ordered (identity, phase) login list — pure
  function, no cloud.
- Federation-subject resolution: mode + repo + env → exact subject strings;
  heavy coverage that delegated mode never yields an app-repo subject.
- Dispatch payload (delegated): app repo → central `repository_dispatch` body.

**Terraform (`terraform/bootstrap/`, `bootstrap/`, `terraform test` mocks):**

- Per-tool bootstrap: RG + plan MI (Reader + data-plane readers) + apply MI
  (Contributor) + role scopes + federated creds match mode/subject; assert plan
  MI never Contributor, apply never Owner.
- Manual root stack: custom role action list is exactly the four, no wildcard.
- tflint + `fmt -check` as today.

**Live-only gap (documented, deferred to sandbox integration):** real OIDC token
exchange (Azure + AWS), RBAC propagation timing, cross-cloud two-login runs.

## Implementation sequence

1. **Rename** `cloudtool` → `cloudapp` (mechanical, its own PR).
2. **Identity + state + trust model** (this design), layered on the renamed base.
