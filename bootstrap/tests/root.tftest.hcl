mock_provider "azurerm" {}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  location        = "eastus2"
  environment     = "dev"
  trusted_repo    = "vgmello/deploy"
}

run "custom_role_is_exactly_the_seven_capabilities" {
  command = plan

  assert {
    condition = length(setsubtract(
      azurerm_role_definition.bootstrap.permissions[0].actions,
      [
        "Microsoft.Resources/subscriptions/resourceGroups/read",
        "Microsoft.Resources/subscriptions/resourceGroups/write",
        "Microsoft.ManagedIdentity/userAssignedIdentities/read",
        "Microsoft.ManagedIdentity/userAssignedIdentities/write",
        "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write",
        "Microsoft.Authorization/roleAssignments/read",
        "Microsoft.Authorization/roleAssignments/write",
      ]
    )) == 0
    error_message = "bootstrap role must contain only the approved actions"
  }

  assert {
    condition     = !contains(azurerm_role_definition.bootstrap.permissions[0].actions, "*")
    error_message = "bootstrap role must not contain a wildcard action"
  }

  assert {
    condition     = azurerm_federated_identity_credential.bootstrap.subject == "repo:vgmello/deploy:environment:dev"
    error_message = "bootstrap federation subject must trust the trusted repo environment"
  }
}
