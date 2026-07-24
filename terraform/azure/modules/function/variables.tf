variable "name" {
  description = "Full function app name (func-<base>-<env>)"
  type        = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "function" {
  description = "Normalized function entry: env, secrets, optional image/docker"
  type        = any
}

variable "image_tag" {
  description = "Full image reference when the workflow built this function's container"
  type        = string
  default     = null
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
  type    = map(string)
  default = {}
}

variable "functions_subnet_id" {
  type = string
}
