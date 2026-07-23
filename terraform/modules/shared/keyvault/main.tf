resource "azurerm_key_vault" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = var.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled    = true
  purge_protection_enabled      = false
  soft_delete_retention_days    = 7
  public_network_access_enabled = var.public_network_access

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules       = var.runner_ip != null ? [var.runner_ip] : []
  }
}

module "private_endpoint" {
  source = "../private-endpoint"

  name                = "pe-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoints_subnet_id
  target_resource_id  = azurerm_key_vault.this.id
  subresource         = "vault"
  private_dns_zone_id = var.private_dns_zone_id
}
