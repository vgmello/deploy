variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "containers" {
  type    = list(string)
  default = []
}

variable "public_access" {
  type = bool
}

variable "runner_ip" {
  type    = string
  default = null
}

variable "keyvault_id" {
  type = string
}

variable "private_endpoints_subnet_id" {
  type = string
}

variable "private_dns_zone_id" {
  type = string
}
