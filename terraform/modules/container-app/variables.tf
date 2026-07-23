variable "name" {
  description = "Full container app name (ca-<base>-<env>)"
  type        = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "container_apps_environment_id" {
  type = string
}

variable "app" {
  description = "Normalized app entry from tool.<env>.json: replicas, containers map, optional ingress object"
  type        = any
}

variable "image_tags" {
  description = "Container key -> full image reference for docker-built containers"
  type        = map(string)
  default     = {}
}

variable "acr_login_server" {
  type = string
}

variable "acr_id" {
  type = string
}

variable "keyvault_id" {
  type = string
}

variable "keyvault_vault_uri" {
  type = string
}

variable "extra_secret_env" {
  description = "Reserved env var -> Key Vault secret name (DATABASE_URL, STORAGE_CONNECTION)"
  type        = map(string)
  default     = {}
}
