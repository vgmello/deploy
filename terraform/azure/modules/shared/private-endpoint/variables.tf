variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "target_resource_id" {
  type = string
}

variable "subresource" {
  description = "Private link subresource (group id), e.g. vault, blob, postgresqlServer, sqlServer"
  type        = string
}

variable "private_dns_zone_id" {
  type = string
}
