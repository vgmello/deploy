output "server_name" {
  value = var.name
}

output "secret_env" {
  description = "Reserved env var -> Key Vault secret name"
  value       = { DATABASE_URL = "database-url" }
}
