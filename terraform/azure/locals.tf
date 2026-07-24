locals {
  cfg      = var.config
  platform = local.cfg.platform
  env      = local.cfg.environment
  prefix   = try(local.platform.naming_prefix, "")
  base     = "${local.prefix}${local.cfg.name}"

  apps         = try(local.cfg.apps, {})
  functions    = try(local.cfg.functions, {})
  static_sites = try(local.cfg.static_sites, {})
  database     = try(local.cfg.database, null)
  storage      = try(local.cfg.storage, null)

  # entry base name: explicit name > manifest name (single entry) > manifest name + key
  app_bases = {
    for k, v in local.apps :
    k => coalesce(try(v.name, null), length(local.apps) == 1 ? local.base : "${local.base}-${k}")
  }
  function_bases = {
    for k, v in local.functions :
    k => coalesce(try(v.name, null), length(local.functions) == 1 ? local.base : "${local.base}-${k}")
  }
  static_site_bases = {
    for k, v in local.static_sites :
    k => coalesce(try(v.name, null), length(local.static_sites) == 1 ? local.base : "${local.base}-${k}")
  }

  ca_names   = { for k, b in local.app_bases : k => "ca-${b}-${local.env}" }
  func_names = { for k, b in local.function_bases : k => "func-${b}-${local.env}" }
  swa_names  = { for k, b in local.static_site_bases : k => "swa-${b}-${local.env}" }

  rg_name = "rg-${local.base}-${local.env}"
  kv_name = trimsuffix(substr("kv-${local.base}-${local.env}", 0, 24), "-")
  st_name = substr("st${replace("${local.base}${local.env}", "-", "")}", 0, 24)
  db_name = local.database == null ? null : (
    local.database.type == "postgres" ? "psql-${local.base}-${local.env}" : "sql-${local.base}-${local.env}"
  )

  acr_name = split(".", local.platform.acr.login_server)[0]
  acr_id   = "/subscriptions/${local.platform.subscription_id}/resourceGroups/${local.platform.acr.resource_group}/providers/Microsoft.ContainerRegistry/registries/${local.acr_name}"

  # reserved env var -> Key Vault secret name wiring for platform-generated secrets
  shared_secret_env = merge(
    local.database != null ? { DATABASE_URL = "database-url" } : {},
    local.storage != null ? { STORAGE_CONNECTION = "storage-connection" } : {},
  )
}
