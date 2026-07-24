variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "public_network_access" {
  description = "True when runner_access = public-allowlist; the vault stays firewalled to runner_ip"
  type        = bool
}

variable "runner_ip" {
  type    = string
  default = null
}

variable "private_endpoints_subnet_id" {
  type = string
}

variable "private_dns_zone_id" {
  type = string
}
