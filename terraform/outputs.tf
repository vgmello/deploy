output "names" {
  description = "Every resource name the naming convention produces for this tool+env"
  value = {
    resource_group = local.rg_name
    keyvault       = local.kv_name
    storage        = local.storage != null ? local.st_name : null
    database       = local.db_name
    apps           = local.ca_names
    functions      = local.func_names
    static_sites   = local.swa_names
  }
}
