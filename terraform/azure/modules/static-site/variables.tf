variable "name" {
  description = "Full static web app name (swa-<base>-<env>)"
  type        = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "site" {
  description = "Normalized static site entry: env"
  type        = any
}
