# Subscription bootstrap (run once per subscription + environment)

A subscription **Owner** runs this stack one time per environment. It creates
the `cloudapp-bootstrap` custom role, the shared `id-cloudapp-bootstrap-<env>`
identity, its role assignment, and a federated credential trusting the trusted
repo's `environment:<env>` subject.

```bash
terraform -chdir=terraform/azure/subscription-bootstrap init
terraform -chdir=terraform/azure/subscription-bootstrap apply \
  -var subscription_id=<sub> -var location=eastus2 \
  -var environment=dev -var trusted_repo=vgmello/deploy
```

Record `bootstrap_identity_client_id` in `environments/<env>.yml` as
`bootstrap_identity_client_id`. In delegated mode `trusted_repo` is the central
deploy repo; in self mode it is the app repo.
