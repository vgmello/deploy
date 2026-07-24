mock_provider "azurerm" {}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  location        = "eastus2"
  name            = "orders-api"
  environment     = "prod"
  plan_subjects   = ["repo:acme/orders:pull_request"]
  apply_subjects  = ["repo:acme/orders:environment:prod"]
}

run "identities_and_scoped_roles" {
  command = plan

  assert {
    condition     = azurerm_resource_group.this.name == "rg-orders-api-prod"
    error_message = "resource group name"
  }
  assert {
    condition     = azurerm_role_assignment.plan_reader.role_definition_name == "Reader"
    error_message = "plan identity must be Reader"
  }
  assert {
    condition     = azurerm_role_assignment.apply_contributor.role_definition_name == "Contributor"
    error_message = "apply identity must be Contributor"
  }
  assert {
    condition     = azurerm_role_assignment.plan_blob.role_definition_name == "Storage Blob Data Reader" && azurerm_role_assignment.plan_kv.role_definition_name == "Key Vault Reader"
    error_message = "plan identity must get the data-plane reader roles for refresh"
  }
  assert {
    condition     = azurerm_federated_identity_credential.apply[0].subject == "repo:acme/orders:environment:prod"
    error_message = "apply federation subject passthrough"
  }
}
