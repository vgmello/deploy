provider "azurerm" {
  features {}

  subscription_id = local.platform.subscription_id
  tenant_id       = local.platform.tenant_id
}
