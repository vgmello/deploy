resource "azurerm_storage_account" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  min_tls_version               = "TLS1_2"
  public_network_access_enabled = var.public_access || var.runner_ip != null

  network_rules {
    default_action = var.public_access ? "Allow" : "Deny"
    bypass         = ["AzureServices"]
    ip_rules       = var.runner_ip != null ? [var.runner_ip] : []
  }
}

resource "azurerm_storage_container" "this" {
  for_each = toset(var.containers)

  name                  = each.value
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

module "private_endpoint" {
  source = "../private-endpoint"
  count  = var.public_access ? 0 : 1

  name                = "pe-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoints_subnet_id
  target_resource_id  = azurerm_storage_account.this.id
  subresource         = "blob"
  private_dns_zone_id = var.private_dns_zone_id
}

resource "azurerm_key_vault_secret" "storage_connection" {
  name         = "storage-connection"
  value        = azurerm_storage_account.this.primary_connection_string
  key_vault_id = var.keyvault_id
}
