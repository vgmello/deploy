variable "config" {
  description = "Merged tool + platform configuration produced by resolve-config"
  type        = any
}

variable "image_tags" {
  description = "Full image references for docker-built containers, keyed '<app_key>/<container_key>' for apps and '<function_key>' for functions"
  type        = map(string)
  default     = {}
}

variable "runner_ip" {
  description = "Deploy runner public IP, allowlisted on data-plane firewalls when runner_access = public-allowlist"
  type        = string
  default     = null
}
