provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

locals {
  scope = "/subscriptions/${var.subscription_id}"
}

resource "azurerm_role_definition" "bootstrap" {
  name        = "cloudapp-bootstrap"
  scope       = local.scope
  description = "Create resource groups, user-assigned identities, and role assignments only"

  permissions {
    actions = [
      "Microsoft.Resources/subscriptions/resourceGroups/read",
      "Microsoft.Resources/subscriptions/resourceGroups/write",
      "Microsoft.ManagedIdentity/userAssignedIdentities/read",
      "Microsoft.ManagedIdentity/userAssignedIdentities/write",
      "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write",
      "Microsoft.Authorization/roleAssignments/read",
      "Microsoft.Authorization/roleAssignments/write",
    ]
    not_actions = []
  }

  assignable_scopes = [local.scope]
}

resource "azurerm_resource_group" "identities" {
  name     = "rg-cloudapp-identities-${var.environment}"
  location = var.location
}

resource "azurerm_user_assigned_identity" "bootstrap" {
  name                = "id-cloudapp-bootstrap-${var.environment}"
  location            = var.location
  resource_group_name = azurerm_resource_group.identities.name
}

resource "azurerm_role_assignment" "bootstrap" {
  scope              = local.scope
  role_definition_id = azurerm_role_definition.bootstrap.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.bootstrap.principal_id
}

resource "azurerm_federated_identity_credential" "bootstrap" {
  name      = "gha-${var.environment}"
  parent_id = azurerm_user_assigned_identity.bootstrap.id
  audience  = ["api://AzureADTokenExchange"]
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = "repo:${var.trusted_repo}:environment:${var.environment}"
}
