variable "subscription_id" {
  type = string
}

variable "location" {
  type = string
}

variable "environment" {
  type = string
}

variable "trusted_repo" {
  description = "owner/name of the repo whose environment subject the bootstrap identity trusts"
  type        = string
}
