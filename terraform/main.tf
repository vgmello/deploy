resource "azurerm_resource_group" "this" {
  name     = local.rg_name
  location = local.platform.location
}

module "keyvault" {
  source = "./modules/shared/keyvault"

  name                        = local.kv_name
  location                    = local.platform.location
  resource_group_name         = azurerm_resource_group.this.name
  tenant_id                   = local.platform.tenant_id
  public_network_access       = local.platform.runner_access == "public-allowlist"
  runner_ip                   = var.runner_ip
  private_endpoints_subnet_id = local.platform.network.subnets.private_endpoints
  private_dns_zone_id         = local.platform.network.private_dns_zone_ids.keyvault
}

module "database" {
  source = "./modules/shared/database"
  count  = local.database != null ? 1 : 0

  name                        = local.db_name
  type                        = local.database.type
  size                        = local.database.size
  storage_gb                  = local.database.storage_gb
  public_access               = local.database.public_access
  location                    = local.platform.location
  resource_group_name         = azurerm_resource_group.this.name
  keyvault_id                 = module.keyvault.id
  private_endpoints_subnet_id = local.platform.network.subnets.private_endpoints
  private_dns_zone_id         = local.database.type == "postgres" ? local.platform.network.private_dns_zone_ids.postgres : local.platform.network.private_dns_zone_ids.sqlserver
}

module "storage" {
  source = "./modules/shared/storage"
  count  = local.storage != null ? 1 : 0

  name                        = local.st_name
  location                    = local.platform.location
  resource_group_name         = azurerm_resource_group.this.name
  containers                  = try(local.storage.containers, [])
  public_access               = local.storage.public_access
  runner_ip                   = var.runner_ip
  keyvault_id                 = module.keyvault.id
  private_endpoints_subnet_id = local.platform.network.subnets.private_endpoints
  private_dns_zone_id         = local.platform.network.private_dns_zone_ids.blob
}

module "container_app" {
  source   = "./modules/container-app"
  for_each = local.apps

  name                          = local.ca_names[each.key]
  location                      = local.platform.location
  resource_group_name           = azurerm_resource_group.this.name
  container_apps_environment_id = local.platform.container_apps_environment_id
  app                           = each.value
  image_tags                    = { for k, v in var.image_tags : split("/", k)[1] => v if split("/", k)[0] == each.key }
  acr_login_server              = local.platform.acr.login_server
  acr_id                        = local.acr_id
  keyvault_id                   = module.keyvault.id
  keyvault_vault_uri            = module.keyvault.vault_uri
  extra_secret_env              = local.shared_secret_env

  depends_on = [module.database, module.storage]
}

module "function" {
  source   = "./modules/function"
  for_each = local.functions

  name                = local.func_names[each.key]
  location            = local.platform.location
  resource_group_name = azurerm_resource_group.this.name
  function            = each.value
  image_tag           = try(var.image_tags[each.key], null)
  acr_id              = local.acr_id
  keyvault_id         = module.keyvault.id
  keyvault_vault_uri  = module.keyvault.vault_uri
  extra_secret_env    = local.shared_secret_env
  functions_subnet_id = local.platform.network.subnets.functions

  depends_on = [module.database, module.storage]
}

module "static_site" {
  source   = "./modules/static-site"
  for_each = local.static_sites

  name                = local.swa_names[each.key]
  location            = local.platform.location
  resource_group_name = azurerm_resource_group.this.name
  site                = each.value
}
