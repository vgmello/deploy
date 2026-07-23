output "account_name" {
  value = azurerm_storage_account.this.name
}

output "secret_env" {
  description = "Reserved env var -> Key Vault secret name"
  value       = { STORAGE_CONNECTION = "storage-connection" }
}
