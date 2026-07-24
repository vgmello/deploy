provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

locals {
  rg = "rg-${var.name}-${var.environment}"
}

resource "azurerm_resource_group" "this" {
  name     = local.rg
  location = var.location
}

resource "azurerm_user_assigned_identity" "plan" {
  name                = "id-${var.name}-${var.environment}-plan"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
}

resource "azurerm_user_assigned_identity" "apply" {
  name                = "id-${var.name}-${var.environment}-apply"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
}

# plan identity: read-only across the RG, plus the data-plane reads plan refresh needs
resource "azurerm_role_assignment" "plan_reader" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

resource "azurerm_role_assignment" "plan_blob" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

resource "azurerm_role_assignment" "plan_kv" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Key Vault Reader"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

# apply identity: write across the RG
resource "azurerm_role_assignment" "apply_contributor" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.apply.principal_id
}

resource "azurerm_federated_identity_credential" "plan" {
  count     = length(var.plan_subjects)
  name      = "gha-plan-${count.index}"
  parent_id = azurerm_user_assigned_identity.plan.id
  audience  = ["api://AzureADTokenExchange"]
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = var.plan_subjects[count.index]
}

resource "azurerm_federated_identity_credential" "apply" {
  count     = length(var.apply_subjects)
  name      = "gha-apply-${count.index}"
  parent_id = azurerm_user_assigned_identity.apply.id
  audience  = ["api://AzureADTokenExchange"]
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = var.apply_subjects[count.index]
}
